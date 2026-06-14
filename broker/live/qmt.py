from __future__ import annotations

import importlib.util
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from core.settings import get_section


DEFAULT_QMT_SDK_MODULES = ("xtquant.xttrader", "xtquant.xttype")
REQUIRED_PERMISSIONS = ("query", "trade")


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


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _mask_account(value: str) -> str:
    text = value.strip()
    if not text:
        return ""
    if len(text) <= 4:
        return "*" * len(text)
    return f"{text[:2]}{'*' * (len(text) - 4)}{text[-2:]}"
