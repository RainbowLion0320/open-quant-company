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

    def submit_order(self, intent: dict[str, Any], *, approval_id: str) -> dict[str, Any]:
        """Fail closed until a real MiniQMT/QMT submit adapter is configured."""
        return {
            "status": "blocked",
            "submitted": False,
            "broker_order_id": "",
            "submitted_at": "",
            "broker_status": "not_integrated",
            "raw_response_hash": "",
            "ledger_id": approval_id,
            "error": "live_submission_not_integrated",
            "paper_fallback": False,
            "intent": self._normalize_intent(intent),
        }

    def reconcile(self, ack: dict[str, Any]) -> dict[str, Any]:
        return {
            "status": "not_integrated",
            "as_of": _now(),
            "positions_matched": False,
            "cash_matched": False,
            "open_orders": [],
            "fills": [],
            "mismatches": [{"reason": "live_reconciliation_not_integrated", "ack": dict(ack)}],
            "recommended_actions": ["connect_miniqmt_adapter"],
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
        extended_checks, extended_blockers = self._extended_risk_checks(
            health=health,
            intent=intent,
            notional=notional,
        )
        checks.extend(extended_checks)
        blockers.extend(extended_blockers)

        unique_blockers = list(dict.fromkeys(blockers))
        return {
            "passed": not unique_blockers,
            "blockers": unique_blockers,
            "checks": checks,
        }

    def _extended_risk_checks(
        self,
        *,
        health: dict[str, Any],
        intent: dict[str, Any],
        notional: float,
    ) -> tuple[list[dict[str, Any]], list[str]]:
        snapshot = dict(intent.get("risk_snapshot") or {})
        blockers: list[str] = []
        checks: list[dict[str, Any]] = []
        live_ready = health.get("mode") == "live_ready"
        required = {
            "max_position_pct",
            "max_total_exposure_pct",
            "daily_order_count",
            "max_daily_orders",
            "tradable",
            "data_freshness_status",
            "broker_account_consistent",
        }
        portfolio_required = {
            "current_drawdown_pct",
            "max_drawdown_pct",
            "portfolio_var_pct",
            "max_portfolio_var_pct",
            "portfolio_cvar_pct",
            "max_portfolio_cvar_pct",
            "current_sector_notional",
            "max_sector_exposure_pct",
            "intraday_limit_state",
        }
        missing = sorted(name for name in required if name not in snapshot)
        if live_ready and missing:
            blockers.append("missing_risk_snapshot")
        missing_portfolio = sorted(name for name in portfolio_required if name not in snapshot)
        if live_ready and missing_portfolio:
            blockers.append("missing_portfolio_risk_snapshot")
        total_asset = _as_float(self.account.get("total_asset"))
        market_value = _as_float(self.account.get("market_value"))
        current_symbol_notional = max(_as_float(snapshot.get("current_symbol_notional")), 0.0)
        position_after = max(current_symbol_notional + (notional if intent["side"] == "buy" else -notional), 0.0)
        exposure_after = max(market_value + (notional if intent["side"] == "buy" else -notional), 0.0)
        max_position_pct = _as_float(snapshot.get("max_position_pct"))
        max_total_exposure_pct = _as_float(snapshot.get("max_total_exposure_pct"))
        position_pct = position_after / total_asset if total_asset > 0 else 0.0
        exposure_pct = exposure_after / total_asset if total_asset > 0 else 0.0

        concentration_passed = total_asset > 0 and max_position_pct > 0 and position_pct <= max_position_pct
        if live_ready and not concentration_passed:
            blockers.append(
                "position_concentration_limit"
                if total_asset > 0 and max_position_pct > 0
                else "missing_position_concentration_limit"
            )
        checks.append(
            {
                "name": "position_concentration",
                "passed": concentration_passed,
                "position_pct": position_pct,
                "limit": max_position_pct,
                "position_after": position_after,
                "total_asset": total_asset,
            }
        )

        exposure_passed = total_asset > 0 and max_total_exposure_pct > 0 and exposure_pct <= max_total_exposure_pct
        if live_ready and not exposure_passed:
            blockers.append(
                "total_exposure_limit"
                if total_asset > 0 and max_total_exposure_pct > 0
                else "missing_total_exposure_limit"
            )
        checks.append(
            {
                "name": "total_exposure",
                "passed": exposure_passed,
                "exposure_pct": exposure_pct,
                "limit": max_total_exposure_pct,
                "exposure_after": exposure_after,
                "total_asset": total_asset,
            }
        )

        daily_order_count = _as_int(snapshot.get("daily_order_count"))
        max_daily_orders = _as_int(snapshot.get("max_daily_orders"))
        daily_order_passed = max_daily_orders > 0 and daily_order_count < max_daily_orders
        if live_ready and not daily_order_passed:
            blockers.append("daily_order_limit" if max_daily_orders > 0 else "missing_daily_order_limit")
        checks.append(
            {
                "name": "daily_order_count",
                "passed": daily_order_passed,
                "current_count": daily_order_count,
                "limit": max_daily_orders,
            }
        )

        tradable = _as_bool(snapshot.get("tradable"))
        if live_ready and not tradable:
            blockers.append("not_tradable")
        checks.append({"name": "tradability", "passed": tradable, "tradable": tradable})

        freshness = str(snapshot.get("data_freshness_status") or "").strip().lower()
        freshness_passed = freshness in {"fresh", "ready", "ok"}
        if live_ready and not freshness_passed:
            blockers.append("data_freshness_stale" if freshness else "missing_data_freshness")
        checks.append({"name": "data_freshness", "passed": freshness_passed, "status": freshness})

        account_consistent = _as_bool(snapshot.get("broker_account_consistent"))
        if live_ready and not account_consistent:
            blockers.append("broker_account_inconsistent")
        checks.append(
            {
                "name": "broker_account_consistency",
                "passed": account_consistent,
                "consistent": account_consistent,
            }
        )

        current_drawdown_pct = _as_float(snapshot.get("current_drawdown_pct"))
        max_drawdown_pct = _as_float(snapshot.get("max_drawdown_pct"))
        drawdown_passed = max_drawdown_pct > 0 and 0 <= current_drawdown_pct <= max_drawdown_pct
        if live_ready and not missing_portfolio and not drawdown_passed:
            blockers.append("drawdown_limit" if max_drawdown_pct > 0 else "missing_drawdown_limit")
        checks.append(
            {
                "name": "drawdown_state",
                "passed": drawdown_passed,
                "current_drawdown_pct": current_drawdown_pct,
                "limit": max_drawdown_pct,
            }
        )

        portfolio_var_pct = _as_float(snapshot.get("portfolio_var_pct"))
        max_portfolio_var_pct = _as_float(snapshot.get("max_portfolio_var_pct"))
        var_passed = max_portfolio_var_pct > 0 and 0 <= portfolio_var_pct <= max_portfolio_var_pct
        if live_ready and not missing_portfolio and not var_passed:
            blockers.append("portfolio_var_limit" if max_portfolio_var_pct > 0 else "missing_portfolio_var_limit")
        checks.append(
            {
                "name": "portfolio_var",
                "passed": var_passed,
                "portfolio_var_pct": portfolio_var_pct,
                "limit": max_portfolio_var_pct,
            }
        )

        portfolio_cvar_pct = _as_float(snapshot.get("portfolio_cvar_pct"))
        max_portfolio_cvar_pct = _as_float(snapshot.get("max_portfolio_cvar_pct"))
        cvar_passed = max_portfolio_cvar_pct > 0 and 0 <= portfolio_cvar_pct <= max_portfolio_cvar_pct
        if live_ready and not missing_portfolio and not cvar_passed:
            blockers.append("portfolio_cvar_limit" if max_portfolio_cvar_pct > 0 else "missing_portfolio_cvar_limit")
        checks.append(
            {
                "name": "portfolio_cvar",
                "passed": cvar_passed,
                "portfolio_cvar_pct": portfolio_cvar_pct,
                "limit": max_portfolio_cvar_pct,
            }
        )

        current_sector_notional = max(_as_float(snapshot.get("current_sector_notional")), 0.0)
        sector_after = max(current_sector_notional + (notional if intent["side"] == "buy" else -notional), 0.0)
        max_sector_exposure_pct = _as_float(snapshot.get("max_sector_exposure_pct"))
        sector_pct = sector_after / total_asset if total_asset > 0 else 0.0
        sector_passed = total_asset > 0 and max_sector_exposure_pct > 0 and sector_pct <= max_sector_exposure_pct
        if live_ready and not missing_portfolio and not sector_passed:
            blockers.append(
                "sector_concentration_limit"
                if total_asset > 0 and max_sector_exposure_pct > 0
                else "missing_sector_concentration_limit"
            )
        checks.append(
            {
                "name": "sector_concentration",
                "passed": sector_passed,
                "sector_pct": sector_pct,
                "limit": max_sector_exposure_pct,
                "sector_after": sector_after,
                "total_asset": total_asset,
            }
        )

        intraday_state = str(snapshot.get("intraday_limit_state") or "").strip().lower()
        intraday_passed = intraday_state in {"normal", "open", "continuous", "ready"}
        if live_ready and not missing_portfolio and not intraday_passed:
            blockers.append("intraday_limit_state_blocked" if intraday_state else "missing_intraday_limit_state")
        checks.append(
            {
                "name": "intraday_limit_state",
                "passed": intraday_passed,
                "state": intraday_state,
            }
        )

        return checks, blockers


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


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "ok", "ready", "fresh"}
    return False


def _estimate_fees(notional: float) -> float:
    if notional <= 0:
        return 0.0
    return max(notional * DEFAULT_COMMISSION_RATE, MIN_COMMISSION)
