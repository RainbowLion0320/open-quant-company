from __future__ import annotations

import importlib.util
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from core.settings import get_section


DEFAULT_QMT_SDK_MODULES = ("xtquant.xttrader", "xtquant.xttype")
REQUIRED_PERMISSIONS = ("query", "trade")
DEFAULT_COMMISSION_RATE = 0.00025
MIN_COMMISSION = 5.0


@dataclass(frozen=True)
class LiveBrokerHealth:
    broker: str
    mode: str
    enabled: bool
    sdk_available: bool
    logged_in: bool
    account_id_masked: str
    permissions: list[str]
    kill_switch: bool
    paper_fallback: bool
    last_probe_at: str
    blockers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class MiniQmtLiveBroker:
    """MiniQMT/QMT readiness probe.

    This class only reports readiness. It deliberately does not submit orders and
    never falls back to PaperBroker when live readiness is blocked.
    """

    def __init__(
        self,
        *,
        enabled: bool | None = None,
        broker: str | None = None,
        sdk_modules: tuple[str, ...] | None = None,
        import_checker: Callable[[str], object | None] | None = None,
        logged_in: bool | None = None,
        account_id: str | None = None,
        permissions: list[str] | None = None,
        account: dict[str, Any] | None = None,
        kill_switch: bool | None = None,
    ):
        cfg = get_section("execution.live", {}) or {}
        self.enabled = bool(cfg.get("enabled", False) if enabled is None else enabled)
        self.broker = str(broker or cfg.get("broker") or "miniqmt")
        self.sdk_modules = sdk_modules or tuple(cfg.get("sdk_modules") or DEFAULT_QMT_SDK_MODULES)
        self.import_checker = import_checker or importlib.util.find_spec
        self.logged_in = bool(cfg.get("logged_in", False) if logged_in is None else logged_in)
        self.account_id = str(account_id if account_id is not None else cfg.get("account_id", "") or "")
        self.permissions = [str(item) for item in (permissions if permissions is not None else cfg.get("permissions", []) or [])]
        self.account = dict(account if account is not None else cfg.get("account", {}) or {})
        self.kill_switch = bool(cfg.get("kill_switch", True) if kill_switch is None else kill_switch)

    def health(self) -> dict[str, Any]:
        blockers: list[str] = []
        sdk_available = False
        if not self.enabled:
            blockers.append("live_disabled")
            mode = "live_disabled"
        else:
            missing_modules = [name for name in self.sdk_modules if not self._module_available(name)]
            sdk_available = not missing_modules
            if missing_modules:
                blockers.extend(f"missing_sdk:{name}" for name in missing_modules)
            if not self.logged_in:
                blockers.append("not_logged_in")
            missing_permissions = [item for item in REQUIRED_PERMISSIONS if item not in set(self.permissions)]
            blockers.extend(f"missing_permission:{item}" for item in missing_permissions)
            if not self.kill_switch:
                blockers.append("kill_switch_disabled")
            mode = "live_ready" if not blockers else "blocked"

        return LiveBrokerHealth(
            broker=self.broker,
            mode=mode,
            enabled=self.enabled,
            sdk_available=sdk_available,
            logged_in=self.logged_in,
            account_id_masked=_mask_account(self.account_id),
            permissions=self.permissions,
            kill_switch=self.kill_switch,
            paper_fallback=False,
            last_probe_at=_now(),
            blockers=blockers,
        ).to_dict()

    def _module_available(self, name: str) -> bool:
        try:
            return self.import_checker(name) is not None
        except Exception:
            return False

    def preview_order(self, intent: dict[str, Any]) -> dict[str, Any]:
        """Return a live order preview without submitting anything."""
        health = self.health()
        normalized = self._normalize_intent(intent)
        risk_gate = self._risk_gate(health, normalized)
        quantity = int(normalized["quantity"])
        price = float(normalized["limit_price"])
        gross_value = quantity * price
        fees = _estimate_fees(gross_value)
        cash_sign = -1.0 if normalized["side"] == "buy" else 1.0
        position_sign = 1 if normalized["side"] == "buy" else -1

        return {
            "status": "preview_ready" if risk_gate["passed"] else "blocked",
            "broker": self.broker,
            "intent": normalized,
            "approval_required": True,
            "paper_fallback": False,
            "submitted": False,
            "health": health,
            "risk_gate": risk_gate,
            "notional": gross_value,
            "fees": {
                "commission_rate": DEFAULT_COMMISSION_RATE,
                "estimated_commission": fees,
                "estimated_total": fees,
            },
            "estimated_cash_effect": (gross_value - fees) if cash_sign > 0 else -(gross_value + fees),
            "estimated_position_effect": {
                "symbol": normalized["symbol"],
                "quantity_delta": position_sign * quantity,
                "notional_delta": position_sign * gross_value,
            },
            "price_source": {
                "type": "limit_price",
                "adjustment": "raw_required",
                "price": price,
            },
            "account_snapshot": {
                "cash": _as_float(self.account.get("cash")),
                "total_asset": _as_float(self.account.get("total_asset")),
                "market_value": _as_float(self.account.get("market_value")),
            },
            "warnings": [],
            "created_at": _now(),
        }

    def _normalize_intent(self, intent: dict[str, Any]) -> dict[str, Any]:
        side = str(intent.get("side") or "").strip().lower()
        return {
            "symbol": str(intent.get("symbol") or "").strip().upper(),
            "side": side,
            "quantity": max(_as_int(intent.get("quantity")), 0),
            "order_type": str(intent.get("order_type") or "limit").strip().lower(),
            "limit_price": max(_as_float(intent.get("limit_price")), 0.0),
            "strategy": str(intent.get("strategy") or "manual").strip() or "manual",
            "reason": str(intent.get("reason") or "").strip(),
            "evidence_refs": [str(item) for item in intent.get("evidence_refs", []) if str(item).strip()],
            "risk_snapshot": dict(intent.get("risk_snapshot") or {}),
        }

    def _risk_gate(self, health: dict[str, Any], intent: dict[str, Any]) -> dict[str, Any]:
        blockers = list(health.get("blockers") or [])
        checks: list[dict[str, Any]] = [
            {"name": "live_readiness", "passed": health.get("mode") == "live_ready", "blockers": list(health.get("blockers") or [])}
        ]
        if not intent["symbol"]:
            blockers.append("missing_symbol")
        if intent["side"] not in {"buy", "sell"}:
            blockers.append("invalid_side")
        if intent["quantity"] <= 0:
            blockers.append("invalid_quantity")
        if intent["order_type"] != "limit":
            blockers.append("unsupported_order_type")
        if intent["limit_price"] <= 0:
            blockers.append("invalid_limit_price")
        if not intent["evidence_refs"]:
            blockers.append("missing_evidence")

        cash = _as_float(self.account.get("cash"))
        notional = int(intent["quantity"]) * float(intent["limit_price"])
        estimated_cost = notional + _estimate_fees(notional)
        if intent["side"] == "buy":
            cash_passed = cash > 0 and estimated_cost <= cash
            if health.get("mode") == "live_ready" and not cash_passed:
                blockers.append("insufficient_cash" if cash > 0 else "missing_account_cash")
            checks.append(
                {
                    "name": "cash",
                    "passed": cash_passed,
                    "available_cash": cash,
                    "estimated_cost": estimated_cost,
                }
            )

        unique_blockers = list(dict.fromkeys(blockers))
        return {
            "passed": not unique_blockers,
            "blockers": unique_blockers,
            "checks": checks,
        }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _mask_account(value: str) -> str:
    text = value.strip()
    if not text:
        return ""
    if len(text) <= 4:
        return "*" * len(text)
    return f"{text[:2]}{'*' * (len(text) - 4)}{text[-2:]}"


def _as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _estimate_fees(notional: float) -> float:
    if notional <= 0:
        return 0.0
    return max(notional * DEFAULT_COMMISSION_RATE, MIN_COMMISSION)
