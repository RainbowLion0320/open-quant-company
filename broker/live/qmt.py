from __future__ import annotations

import hashlib
import importlib
import importlib.util
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from broker.numeric import coerce_float as _as_float
from broker.numeric import coerce_int as _as_int
from broker.numeric import parse_required_float
from broker.numeric import parse_required_int
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
    sdk_gateway_configured: bool
    sdk_gateway_error: str
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
        sdk_gateway: Any | None = None,
        sdk_gateway_factory: str | None = None,
        sdk_gateway_config: dict[str, Any] | None = None,
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
        self.sdk_gateway_factory = str(
            sdk_gateway_factory if sdk_gateway_factory is not None else cfg.get("sdk_gateway_factory", "") or ""
        ).strip()
        self.sdk_gateway_config = dict(
            sdk_gateway_config if sdk_gateway_config is not None else cfg.get("sdk_gateway_config", {}) or {}
        )
        self.sdk_gateway_error = ""
        if sdk_gateway is not None:
            self.sdk_gateway = sdk_gateway
        elif self.enabled and self.sdk_gateway_factory:
            self.sdk_gateway, self.sdk_gateway_error = _build_sdk_gateway(
                self.sdk_gateway_factory,
                config=self.sdk_gateway_config,
                account_id=self.account_id,
                broker=self.broker,
            )
        else:
            self.sdk_gateway = None

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
            if self.sdk_gateway_error:
                blockers.append("sdk_gateway_load_failed")
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
            sdk_gateway_configured=self.sdk_gateway is not None,
            sdk_gateway_error=self.sdk_gateway_error,
            last_probe_at=_now(),
            blockers=blockers,
        ).to_dict()

    def validate_environment(self) -> dict[str, Any]:
        """Validate the local MiniQMT/QMT environment without submitting orders."""
        health = self.health()
        checks = {
            "enabled": _validation_check(
                passed=self.enabled,
                blocker="live_disabled",
                details={"enabled": self.enabled},
            ),
            "sdk_modules": _validation_check(
                passed=bool(health.get("sdk_available")),
                blocker="missing_sdk",
                details={"modules": list(self.sdk_modules)},
            ),
            "account": _validation_check(
                passed=bool(self.logged_in and self.account_id),
                blocker="not_logged_in" if not self.logged_in else "missing_account_id",
                details={"logged_in": self.logged_in, "account_id_masked": _mask_account(self.account_id)},
            ),
            "permissions": _validation_check(
                passed=all(item in set(self.permissions) for item in REQUIRED_PERMISSIONS),
                blocker="missing_permission",
                details={
                    "required": list(REQUIRED_PERMISSIONS),
                    "configured": list(self.permissions),
                    "missing": [item for item in REQUIRED_PERMISSIONS if item not in set(self.permissions)],
                },
            ),
            "kill_switch": _validation_check(
                passed=self.kill_switch,
                blocker="kill_switch_disabled",
                details={"kill_switch": self.kill_switch},
            ),
            "gateway": _validation_check(
                passed=self.sdk_gateway is not None and not self.sdk_gateway_error,
                blocker="sdk_gateway_load_failed" if self.sdk_gateway_error else "sdk_gateway_not_configured",
                details={
                    "configured": self.sdk_gateway is not None,
                    "factory": self.sdk_gateway_factory,
                    "error": self.sdk_gateway_error,
                },
            ),
            "userdata_path": _validation_check(
                passed=bool(str(self.sdk_gateway_config.get("userdata_path") or "").strip()),
                blocker="missing_userdata_path",
                details={"configured": bool(str(self.sdk_gateway_config.get("userdata_path") or "").strip())},
            ),
        }
        terminal_result = self._validate_terminal_session()
        checks["terminal_session"] = terminal_result["check"]
        blockers = list(dict.fromkeys([
            *[str(item) for item in health.get("blockers", [])],
            *[
                str(check["blocker"])
                for check in checks.values()
                if check.get("status") != "passed" and str(check.get("blocker") or "")
            ],
        ]))
        status = "validated" if not blockers else "blocked"
        return {
            "status": status,
            "broker": self.broker,
            "mode": health.get("mode"),
            "enabled": self.enabled,
            "paper_fallback": False,
            "account_id_masked": _mask_account(self.account_id),
            "checked_at": _now(),
            "blockers": blockers,
            "checks": checks,
            "terminal_probe": terminal_result["probe"],
        }

    def _module_available(self, name: str) -> bool:
        try:
            return self.import_checker(name) is not None
        except Exception:
            return False

    def _validate_terminal_session(self) -> dict[str, Any]:
        if self.sdk_gateway is None:
            return {
                "check": _validation_check(
                    passed=False,
                    blocker="sdk_gateway_not_configured",
                    details={"configured": False},
                ),
                "probe": {},
            }
        validate = getattr(self.sdk_gateway, "validate_environment", None)
        if not callable(validate):
            return {
                "check": _validation_check(
                    passed=False,
                    blocker="gateway_validation_not_supported",
                    details={"configured": True},
                ),
                "probe": {},
            }
        try:
            probe = _safe_payload(validate(account_id=self.account_id))
        except Exception:
            return {
                "check": _validation_check(
                    passed=False,
                    blocker="terminal_validation_failed",
                    details={"error": "terminal_validation_failed"},
                ),
                "probe": {},
            }
        probe_status = str(_response_get(probe, "status") or "").strip().lower()
        passed = probe_status in {"validated", "ready", "ok", "matched"}
        return {
            "check": _validation_check(
                passed=passed,
                blocker="terminal_validation_failed",
                details={"status": probe_status or "unknown"},
            ),
            "probe": probe,
        }

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
        """Submit through an explicitly injected SDK gateway, otherwise fail closed."""
        normalized = self._normalize_intent(intent)
        if self.sdk_gateway_error:
            return {
                "status": "blocked",
                "submitted": False,
                "broker_order_id": "",
                "submitted_at": "",
                "broker_status": "gateway_unavailable",
                "raw_response_hash": "",
                "ledger_id": approval_id,
                "error": "live_sdk_gateway_unavailable",
                "error_message": self.sdk_gateway_error,
                "paper_fallback": False,
                "intent": normalized,
            }
        if self.sdk_gateway is None:
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
                "intent": normalized,
            }

        preview = self.preview_order(normalized)
        if preview["status"] != "preview_ready":
            return {
                "status": "blocked",
                "submitted": False,
                "broker_order_id": "",
                "submitted_at": "",
                "broker_status": "preview_blocked",
                "raw_response_hash": "",
                "ledger_id": approval_id,
                "error": "live_preview_blocked",
                "paper_fallback": False,
                "intent": normalized,
                "preview": preview,
            }

        try:
            response = self.sdk_gateway.submit_order(
                normalized,
                approval_id=approval_id,
                account_id=self.account_id,
            )
        except Exception:
            return {
                "status": "blocked",
                "submitted": False,
                "broker_order_id": "",
                "submitted_at": "",
                "broker_status": "submit_failed",
                "raw_response_hash": "",
                "ledger_id": approval_id,
                "error": "live_submission_failed",
                "paper_fallback": False,
                "intent": normalized,
                "preview": preview,
            }

        raw_response_masked = _safe_payload(response)
        broker_order_id = _extract_broker_order_id(response)
        if not broker_order_id:
            return {
                "status": "blocked",
                "submitted": False,
                "broker_order_id": "",
                "submitted_at": "",
                "broker_status": "missing_broker_order_id",
                "raw_response_hash": _payload_hash(raw_response_masked),
                "raw_response_masked": raw_response_masked,
                "ledger_id": approval_id,
                "error": "missing_broker_order_id",
                "paper_fallback": False,
                "intent": normalized,
                "preview": preview,
            }

        return {
            "status": "submitted",
            "submitted": True,
            "broker_order_id": broker_order_id,
            "submitted_at": _now(),
            "broker_status": str(
                _response_get(response, "broker_status")
                or _response_get(response, "status")
                or "submitted"
            ),
            "raw_response_hash": _payload_hash(raw_response_masked),
            "raw_response_masked": raw_response_masked,
            "ledger_id": approval_id,
            "error": "",
            "paper_fallback": False,
            "intent": normalized,
            "preview": preview,
        }

    def reconcile(self, ack: dict[str, Any]) -> dict[str, Any]:
        if self.sdk_gateway is not None and hasattr(self.sdk_gateway, "reconcile"):
            try:
                response = self.sdk_gateway.reconcile(ack, account_id=self.account_id)
            except Exception:
                return {
                    "status": "blocked",
                    "as_of": _now(),
                    "positions_matched": False,
                    "cash_matched": False,
                    "open_orders": [],
                    "fills": [],
                    "mismatches": [
                        {
                            "reason": "live_reconciliation_failed",
                        }
                    ],
                    "recommended_actions": ["review_live_reconciliation_failure"],
                    "paper_fallback": False,
                }

            raw_response_masked = _safe_payload(response)
            mismatches = _safe_payload(list(_response_get(response, "mismatches") or []))
            positions_matched = bool(_response_get(response, "positions_matched"))
            cash_matched = bool(_response_get(response, "cash_matched"))
            matched = positions_matched and cash_matched and not mismatches
            return {
                "status": "matched" if matched else "needs_review",
                "as_of": _now(),
                "positions_matched": positions_matched,
                "cash_matched": cash_matched,
                "open_orders": _safe_payload(list(_response_get(response, "open_orders") or [])),
                "fills": _safe_payload(list(_response_get(response, "fills") or [])),
                "mismatches": mismatches,
                "recommended_actions": [] if matched else ["review_live_reconciliation_mismatches"],
                "paper_fallback": False,
                "raw_response_hash": _payload_hash(raw_response_masked),
                "raw_response_masked": raw_response_masked,
            }

        return {
            "status": "not_integrated",
            "as_of": _now(),
            "positions_matched": False,
            "cash_matched": False,
            "open_orders": [],
            "fills": [],
            "mismatches": [{"reason": "live_reconciliation_not_integrated", "ack": dict(ack)}],
            "recommended_actions": ["connect_miniqmt_adapter"],
            "paper_fallback": False,
        }

    def cancel_order(self, ack: dict[str, Any], *, reason: str = "") -> dict[str, Any]:
        """Request broker-side cancellation for an already-submitted live order."""
        broker_order_id = str(ack.get("broker_order_id") or "").strip()
        if not broker_order_id:
            return {
                "status": "blocked",
                "broker_order_id": "",
                "broker_status": "missing_broker_order_id",
                "canceled": False,
                "canceled_at": "",
                "raw_response_hash": "",
                "error": "missing_broker_order_id",
                "paper_fallback": False,
            }
        if self.sdk_gateway_error:
            return {
                "status": "blocked",
                "broker_order_id": broker_order_id,
                "broker_status": "gateway_unavailable",
                "canceled": False,
                "canceled_at": "",
                "raw_response_hash": "",
                "error": "live_sdk_gateway_unavailable",
                "error_message": self.sdk_gateway_error,
                "paper_fallback": False,
            }
        if self.sdk_gateway is None or not callable(getattr(self.sdk_gateway, "cancel_order", None)):
            return {
                "status": "blocked",
                "broker_order_id": broker_order_id,
                "broker_status": "not_integrated",
                "canceled": False,
                "canceled_at": "",
                "raw_response_hash": "",
                "error": "broker_cancel_not_supported",
                "paper_fallback": False,
            }

        try:
            response = self.sdk_gateway.cancel_order(ack, account_id=self.account_id, reason=reason)
        except Exception:
            return {
                "status": "blocked",
                "broker_order_id": broker_order_id,
                "broker_status": "cancel_failed",
                "canceled": False,
                "canceled_at": "",
                "raw_response_hash": "",
                "error": "live_cancel_failed",
                "paper_fallback": False,
            }

        raw_response_masked = _safe_payload(response)
        response_status = str(_response_get(response, "status") or "").strip().lower()
        broker_status = str(_response_get(response, "broker_status") or response_status or "cancel_requested")
        canceled = response_status in {"canceled", "cancel_requested", "accepted", "submitted", "ok", "success"}
        return {
            "status": "canceled" if canceled else "blocked",
            "broker_order_id": str(_response_get(response, "broker_order_id") or broker_order_id),
            "broker_status": broker_status,
            "canceled": canceled,
            "canceled_at": _now() if canceled else "",
            "raw_response_hash": _payload_hash(raw_response_masked),
            "raw_response_masked": raw_response_masked,
            "error": "" if canceled else broker_status,
            "reason": reason,
            "paper_fallback": False,
        }

    def _normalize_intent(self, intent: dict[str, Any]) -> dict[str, Any]:
        side = str(intent.get("side") or "").strip().lower()
        existing_errors = [str(error) for error in intent.get("numeric_errors", []) if str(error).strip()]
        quantity, quantity_error = parse_required_int(
            intent.get("quantity"),
            missing="missing_quantity",
            invalid="invalid_quantity_format",
        )
        limit_price, price_error = parse_required_float(
            intent.get("limit_price"),
            missing="missing_limit_price",
            invalid="invalid_limit_price_format",
        )
        return {
            "symbol": str(intent.get("symbol") or "").strip().upper(),
            "side": side,
            "quantity": max(quantity, 0),
            "order_type": str(intent.get("order_type") or "limit").strip().lower(),
            "limit_price": max(limit_price, 0.0),
            "strategy": str(intent.get("strategy") or "manual").strip() or "manual",
            "reason": str(intent.get("reason") or "").strip(),
            "evidence_refs": [str(item) for item in intent.get("evidence_refs", []) if str(item).strip()],
            "risk_snapshot": dict(intent.get("risk_snapshot") or {}),
            "numeric_errors": [*existing_errors, *[error for error in (quantity_error, price_error) if error]],
        }

    def _risk_gate(self, health: dict[str, Any], intent: dict[str, Any]) -> dict[str, Any]:
        blockers = [*list(health.get("blockers") or []), *list(intent.get("numeric_errors") or [])]
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


def _validation_check(*, passed: bool, blocker: str, details: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "passed" if passed else "blocked",
        "passed": passed,
        "blocker": "" if passed else blocker,
        "details": _safe_payload(details),
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


def _response_get(response: Any, key: str) -> Any:
    if isinstance(response, dict):
        return response.get(key)
    return getattr(response, key, None)


def _build_sdk_gateway(
    factory_path: str,
    *,
    config: dict[str, Any],
    account_id: str,
    broker: str,
) -> tuple[Any | None, str]:
    try:
        factory = _load_factory(factory_path)
        gateway = factory(config=dict(config), account_id=account_id, broker=broker)
        missing = [name for name in ("submit_order", "reconcile") if not callable(getattr(gateway, name, None))]
        if missing:
            return None, f"AttributeError: sdk gateway missing methods {','.join(missing)}"
        return gateway, ""
    except Exception:
        return None, "sdk_gateway_load_failed"


def _load_factory(factory_path: str) -> Callable[..., Any]:
    path = factory_path.strip()
    if not path:
        raise ValueError("sdk gateway factory path is empty")
    if ":" in path:
        module_name, attr_path = path.split(":", 1)
    else:
        module_name, _, attr_path = path.rpartition(".")
    if not module_name or not attr_path:
        raise ValueError("sdk gateway factory must use module:callable or module.callable")
    obj: Any = importlib.import_module(module_name)
    for part in attr_path.split("."):
        obj = getattr(obj, part)
    if not callable(obj):
        raise TypeError("sdk gateway factory is not callable")
    return obj


def _extract_broker_order_id(response: Any) -> str:
    for key in ("broker_order_id", "order_id", "entrust_no", "order_sysid", "order_ref"):
        value = _response_get(response, key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _safe_payload(value: Any, *, depth: int = 0) -> Any:
    if depth > 4:
        return "<truncated>"
    if isinstance(value, dict):
        return {
            str(key): _safe_field(str(key), item, depth=depth + 1)
            for key, item in sorted(value.items(), key=lambda entry: str(entry[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_safe_payload(item, depth=depth + 1) for item in list(value)[:20]]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if hasattr(value, "__dict__"):
        return _safe_payload(vars(value), depth=depth + 1)
    return str(value)


def _safe_field(key: str, value: Any, *, depth: int) -> Any:
    normalized = key.lower()
    if any(token in normalized for token in ("secret", "token", "password", "api_key", "apikey", "key")):
        return "***"
    if "account" in normalized and isinstance(value, (str, int)):
        return _mask_account(str(value))
    return _safe_payload(value, depth=depth)


def _payload_hash(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"
