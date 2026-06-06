"""Path helpers used by the DataHub facade."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PLACEHOLDER_RE = re.compile(r"\{([A-Za-z0-9_]+)\}")


def resolve_path(path: str | os.PathLike, base: Path = PROJECT_ROOT) -> Path:
    raw = os.path.expandvars(os.path.expanduser(str(path)))
    resolved = Path(raw)
    if not resolved.is_absolute():
        resolved = base / resolved
    return resolved.resolve()


def safe_leaf(value: str, label: str = "name") -> str:
    text = str(value).strip()
    if not text or "/" in text or "\\" in text or text in {".", ".."}:
        raise ValueError(f"Invalid {label}: {value!r}")
    return text


def env_first(*names: str) -> str:
    for name in names:
        value = os.environ.get(name, "")
        if value:
            return value
    return ""


def ensure_relative_store_pattern(pattern: str) -> Path:
    path = Path(str(pattern).strip())
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"Invalid registry cache pattern: {pattern!r}")
    return path


class DataHubPaths:
    """Resolve canonical project, store, cache, and logical dataset paths."""

    def __init__(
        self,
        project_root: str | os.PathLike,
        runtime_root: str | os.PathLike,
        store_root: str | os.PathLike,
        cache_root: str | os.PathLike,
        artifact_root: str | os.PathLike,
        db_root: str | os.PathLike,
    ):
        self.project_root = resolve_path(project_root)
        self.runtime_root = resolve_path(runtime_root, self.project_root)
        self.store_root = resolve_path(store_root, self.project_root)
        self.cache_root = resolve_path(cache_root, self.project_root)
        self.artifact_root = resolve_path(artifact_root, self.project_root)
        self.db_root = resolve_path(db_root, self.project_root)
        self.legacy_store_root: Path | None = None
        self.legacy_cache_root: Path | None = None
        self._legacy_warning_emitted = False

    def ensure_layout(self) -> None:
        for path in [
            self.runtime_root,
            self.store_root,
            self.cache_root,
            self.artifact_root,
            self.db_root,
            self.manifest_dir(),
            self.signals_dir(),
            self.signals_prev_dir(),
            self.features_dir(),
            self.paper_dir(),
            self.artifact_dir("backtests"),
            self.artifact_dir("models"),
            self.artifact_dir("tournaments"),
            self.artifact_dir("reports"),
            self.migration_dir(),
            self.store_path("stock"),
            self.store_path("macro"),
            self.store_path("fund"),
            self.store_path("futures"),
            self.store_path("bond"),
            self.store_path("sector"),
        ]:
            path.mkdir(parents=True, exist_ok=True)

    def resolve_path(self, path: str | os.PathLike, base: Path | None = None) -> Path:
        return resolve_path(path, base or self.project_root)

    def enable_legacy_read_fallback(
        self,
        *,
        store_root: str | os.PathLike | None = None,
        cache_root: str | os.PathLike | None = None,
    ) -> None:
        if store_root is not None:
            self.legacy_store_root = resolve_path(store_root, self.project_root)
        if cache_root is not None:
            self.legacy_cache_root = resolve_path(cache_root, self.project_root)

    def legacy_read_path(self, path: str | os.PathLike) -> Path | None:
        target = self.resolve_path(path)
        candidates = [
            (self.store_root, self.legacy_store_root),
            (self.cache_root, self.legacy_cache_root),
        ]
        for current_root, legacy_root in candidates:
            if legacy_root is None:
                continue
            try:
                rel = target.relative_to(current_root)
            except ValueError:
                continue
            legacy = legacy_root / rel
            if legacy.exists():
                return legacy
        return None

    def store_path(self, asset_type: str | None = None) -> Path:
        if asset_type is None:
            return self.store_root
        return self.store_root / safe_leaf(asset_type, "asset_type")

    def store_dir(self, asset_type: str | None = None) -> Path:
        if asset_type is None:
            return self.store_root
        path = self.store_path(asset_type)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def runtime_dir(self) -> Path:
        return self.runtime_root

    def artifact_dir(self, kind: str | None = None) -> Path:
        if kind is None:
            return self.artifact_root
        path = self.artifact_root / safe_leaf(kind, "artifact kind")
        path.mkdir(parents=True, exist_ok=True)
        return path

    def artifact_path(self, kind: str, name: str) -> Path:
        return self.artifact_dir(kind) / safe_leaf(name, "artifact name")

    def db_path(self, name: str) -> Path:
        path = self.db_root / safe_leaf(name, "database name")
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def migration_dir(self) -> Path:
        path = self.runtime_root / "migration"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def stock_data_dir(self, name: str) -> Path:
        path = self.store_root / "stock" / safe_leaf(name, "name")
        path.mkdir(parents=True, exist_ok=True)
        return path

    def signals_dir(self) -> Path:
        return self.store_root / "signals"

    def signals_prev_dir(self) -> Path:
        return self.store_root / "signals_prev"

    def signal_path(self, strategy: str) -> Path:
        return self.signals_dir() / f"{safe_leaf(strategy, 'strategy')}.parquet"

    def signal_prev_path(self, strategy: str) -> Path:
        return self.signals_prev_dir() / f"{safe_leaf(strategy, 'strategy')}.parquet"

    def buffett_scan_path(self) -> Path:
        return self.signals_dir() / "buffett_scan.parquet"

    def scan_meta_path(self) -> Path:
        return self.store_root / "scan_meta.parquet"

    def features_dir(self) -> Path:
        return self.store_root / "features"

    def feature_path(self, month: str) -> Path:
        return self.features_dir() / f"{safe_leaf(month, 'month')}.parquet"

    def paper_dir(self) -> Path:
        return self.store_root / "paper"

    def paper_path(self, name: str) -> Path:
        return self.paper_dir() / f"{safe_leaf(name, 'paper dataset')}.parquet"

    def macro_path(self, name: str) -> Path:
        return self.store_path("macro") / f"{safe_leaf(name, 'macro dataset')}.parquet"

    def asset_daily_path(self, asset_type: str, symbol: str) -> Path:
        return self.store_path(asset_type) / "daily" / f"{safe_leaf(symbol, 'symbol')}.parquet"

    def stock_daily_path(self, symbol: str) -> Path:
        return self.store_path("stock") / "daily" / f"{safe_leaf(symbol, 'symbol')}.parquet"

    def stock_daily_raw_path(self, symbol: str) -> Path:
        return self.store_path("stock") / "daily_raw" / f"{safe_leaf(symbol, 'symbol')}.parquet"

    def stock_daily_hfq_path(self, symbol: str) -> Path:
        return self.store_path("stock") / "daily_hfq" / f"{safe_leaf(symbol, 'symbol')}.parquet"

    def stock_adj_factor_path(self, symbol: str) -> Path:
        return self.store_path("stock") / "adj_factor" / f"{safe_leaf(symbol, 'symbol')}.parquet"

    def stock_corporate_actions_path(self, symbol: str) -> Path:
        return self.store_path("stock") / "corporate_actions" / f"{safe_leaf(symbol, 'symbol')}.parquet"

    def stock_financial_path(self, symbol: str) -> Path:
        return self.store_path("stock") / "financials" / f"{safe_leaf(symbol, 'symbol')}.parquet"

    def stock_fina_indicator_path(self, symbol: str) -> Path:
        return self.store_path("stock") / "fina_indicator" / f"{safe_leaf(symbol, 'symbol')}.parquet"

    def stock_valuation_path(self, symbol: str) -> Path:
        return self.store_path("stock") / "valuation" / f"{safe_leaf(symbol, 'symbol')}.parquet"

    def model_path(self, name: str) -> Path:
        return self.artifact_path("models", f"{safe_leaf(name, 'model dataset')}.parquet")

    def system_monitor_path(self) -> Path:
        return self.db_path("system_monitor.db")

    def token_usage_path(self) -> Path:
        return self.cache_root / "token_usage.json"

    def llm_usage_path(self) -> Path:
        return self.cache_root / "llm_usage_today.json"

    def hindsight_tokens_path(self) -> Path:
        return self.cache_root / "hindsight_tokens.json"

    def llm_project_usage_path(self) -> Path:
        return self.store_path("llm") / "project_usage_ledger.parquet"

    def deepseek_project_usage_path(self) -> Path:
        return self.store_path("deepseek") / "project_usage_ledger.parquet"

    def manifest_dir(self) -> Path:
        return self.store_root / "_manifest"

    def manifest_path(self) -> Path:
        return self.manifest_dir() / "datasets.parquet"

    def registry_cache_root(self, pattern: str) -> Path:
        rel = ensure_relative_store_pattern(pattern)
        parts = []
        for part in rel.parts:
            if "{" in part and "}" in part:
                break
            parts.append(part)
        return self.store_root.joinpath(*parts) if parts else self.store_root

    def expand_registry_cache(self, key: str, pattern: str, values: dict[str, Any]) -> Path:
        rel_pattern = str(ensure_relative_store_pattern(pattern))
        missing: list[str] = []

        def repl(match: re.Match[str]) -> str:
            name = match.group(1)
            if name not in values:
                missing.append(name)
                return match.group(0)
            return safe_leaf(str(values[name]), name)

        expanded = PLACEHOLDER_RE.sub(repl, rel_pattern)
        if missing:
            raise KeyError(f"Missing cache placeholder(s) for {key}: {', '.join(sorted(set(missing)))}")
        rel = ensure_relative_store_pattern(expanded)
        return self.store_root.joinpath(*rel.parts)
