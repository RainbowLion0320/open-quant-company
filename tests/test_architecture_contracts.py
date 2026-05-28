import importlib
import os
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd


def test_build_features_import_is_safe():
    module = importlib.import_module("scripts.build_features")
    assert callable(module.build_features)
    assert callable(module.rebuild_recent)


def test_rebuild_recent_targets_completed_months():
    module = importlib.import_module("scripts.build_features")
    assert module._recent_month_window(3, pd.Timestamp("2026-05-18")) == ("2026-02", "2026-04")


def test_model_evaluate_datetime_index_icir_does_not_crash():
    from models import BaseModel

    class DummyModel(BaseModel):
        def predict(self, X):
            return np.arange(len(X), dtype=float)

    X = pd.DataFrame({"x": range(8)}, index=pd.date_range("2024-01-01", periods=8, freq="D"))
    y = pd.Series(range(8), index=X.index)
    result = DummyModel().evaluate(X, y)
    assert result["ic"] > 0
    assert "icir" in result


def test_prepare_xy_drops_missing_targets():
    from models import prepare_xy

    df = pd.DataFrame(
        {
            "symbol": ["A", "B", "C"],
            "factor": [1.0, None, 3.0],
            "ret_fwd_20d": [0.1, None, -0.2],
        }
    )
    X, y = prepare_xy(df)
    assert len(X) == 2
    assert len(y) == 2
    assert X["factor"].isna().sum() == 0


def test_paper_broker_never_sells_more_than_position_when_t0():
    from broker import PaperBroker

    broker = PaperBroker(initial_cash=100000, t_plus_1=False, enable_risk=False)
    broker.set_prices({"000001": 10.0})
    assert broker.submit_order("000001", price=10.0, volume=100, side="buy").startswith("PAPER_")
    assert broker.submit_order("000001", price=10.0, volume=300, side="sell").startswith("PAPER_")
    broker.end_of_day()
    assert broker.get_positions() == []


def test_paper_broker_is_exported_from_dedicated_module():
    import broker
    from broker.paper import PaperBroker

    assert broker.PaperBroker is PaperBroker


def test_paper_broker_state_round_trips_through_public_api():
    from broker import PaperBroker
    from broker.state import PaperBrokerState

    state = PaperBrokerState(
        cash=12345.0,
        frozen_cash=25.0,
        peak_equity=15000.0,
        order_counter=42,
        positions={
            "000001": {
                "name": "平安银行",
                "volume": 200,
                "avg_cost": 8.5,
                "current_price": 9.1,
            }
        },
    )

    broker = PaperBroker.from_state(state, enable_risk=False)

    balance = broker.get_balance()
    assert balance.cash == 12345.0
    assert balance.frozen_cash == 25.0
    assert broker.get_position("000001").volume == 200
    assert broker.get_position_codes() == ["000001"]

    restored = broker.snapshot_state()
    assert restored.cash == 12345.0
    assert restored.peak_equity == 15000.0
    assert restored.order_counter == 42
    assert restored.positions["000001"]["avg_cost"] == 8.5


def test_paper_broker_private_state_is_not_used_outside_broker_package():
    forbidden = (
        "broker._cash",
        "broker._frozen_cash",
        "broker._positions",
        "broker._order_counter",
        "broker._today_buys",
        "broker._today_sells",
        "broker._peak_equity",
    )
    checked_files = [
        Path("scripts/execute_paper_trades.py"),
        Path("web/api/routes/portfolio.py"),
    ]

    offenders = []
    for path in checked_files:
        text = path.read_text()
        offenders.extend(f"{path}:{token}" for token in forbidden if token in text)

    assert offenders == []


def test_enabled_strategy_plugins_have_runners():
    from data.strategy_plugins import iter_strategy_plugins

    plugins = list(iter_strategy_plugins("all"))
    assert plugins
    for plugin in plugins:
        assert callable(plugin.load_runner())


def test_strategy_runners_do_not_point_at_cli_scripts():
    from data.strategy_plugins import DEFAULT_RUNNERS

    offenders = {name: runner for name, runner in DEFAULT_RUNNERS.items() if runner.startswith("scripts.")}

    assert offenders == {}


def test_compute_signals_import_has_no_runtime_side_effects(monkeypatch):
    import socket

    monkeypatch.setenv("http_proxy", "http://proxy.invalid")
    before_timeout = socket.getdefaulttimeout()

    module = importlib.import_module("scripts.compute_signals")

    assert callable(module.main)
    assert socket.getdefaulttimeout() == before_timeout
    assert "http_proxy" in os.environ


def test_datahub_catalog_includes_data_registry_dimensions():
    from data.datahub import get_datahub

    catalog = get_datahub().catalog()
    assert "signals" in catalog
    assert any(key.startswith("dimension:") for key in catalog)


def test_stock_daily_read_path_does_not_implicitly_fetch_api(monkeypatch):
    from data import fetcher
    import data.fetchers.stock_daily as stock_daily

    monkeypatch.delenv("QUANT_ALLOW_API_FALLBACK", raising=False)

    def fail_fetch(*args, **kwargs):
        raise AssertionError("API fetch should not be called by default")

    monkeypatch.setattr(stock_daily, "fetch_one", fail_fetch)
    df = fetcher.get_stock_daily("999998")
    assert df.empty


def test_repairable_tables_are_sourced_from_repair_map():
    from scripts.repair_table import REPAIR_MAP
    from web.api.routes.system import _repairable_tables

    assert _repairable_tables() == set(REPAIR_MAP)
    assert "stock_moneyflow_daily" in _repairable_tables()


def test_system_route_delegates_large_status_domains_to_services():
    import web.api.services.system_data_health as data_health
    import web.api.services.system_integrations as integrations
    import web.api.services.system_monitor as monitor

    route_text = Path("web/api/routes/system.py").read_text()

    assert callable(monitor.system_monitor_payload)
    assert callable(data_health.db_health_payload)
    assert callable(integrations.service_status_payload)
    assert "def _query(" not in route_text
    assert "def _read_token(" not in route_text
    assert "def _run_repair(" not in route_text
    assert "def _repairable_tables(" not in route_text


def test_portfolio_sector_exposure_reuses_sector_service():
    route_text = Path("web/api/routes/portfolio.py").read_text()

    assert "build_sector_exposure" in route_text
    assert 'dimension_root("sector_exposure_snapshot")' not in route_text
    assert "root.glob(\"*.parquet\")" not in route_text


def test_regime_training_reuses_shared_metric_helpers():
    text = Path("research/regime_training.py").read_text()

    assert "from research.performance import portfolio_metrics" in text
    assert "from research.forward_labels import" in text
    assert "def _portfolio_metrics(" not in text
    assert "def _future_compound_return(" not in text


def test_frontend_sector_metrics_are_shared():
    sectors = Path("web/frontend/src/views/Sectors.vue").read_text()
    market = Path("web/frontend/src/views/Market.vue").read_text()
    sector_utils = Path("web/frontend/src/utils/sector.ts").read_text()

    assert "../utils/sector" in sectors
    assert "../utils/sector" in market
    assert "export function signalPower" in sector_utils
    assert "export function dataSourceLabel" in sector_utils
    assert "function signalPower(" not in sectors
    assert "function signalPower(" not in market


def test_scripts_do_not_import_regime_helpers_from_orchestrator():
    checked_files = [
        Path("scripts/multi_asset_tournament.py"),
        Path("scripts/train_regime_models.py"),
    ]

    offenders = []
    for path in checked_files:
        text = path.read_text()
        if "from cybernetics.orchestrator import detect_market_regime" in text:
            offenders.append(str(path))
        if "from cybernetics.orchestrator import MarketRegime" in text:
            offenders.append(str(path))

    assert offenders == []


def test_repository_keeps_completed_plans_out_of_active_context():
    forbidden_paths = [
        Path("docs/plans/archive"),
        Path("wiki/_archive"),
        Path("wiki/log.md"),
    ]
    existing = [str(path) for path in forbidden_paths if path.exists()]
    existing.extend(str(path) for path in Path("docs/plans").glob("20*.md"))

    assert existing == []


def test_current_docs_do_not_point_agents_to_archived_context():
    checked_roots = [Path("docs"), Path("wiki")]
    excluded = {Path("docs/plans/README.md")}
    forbidden_tokens = (
        "docs/plans/archive",
        "wiki/_archive",
        "log-2026-05-23",
        "2026-05-25-market-regime-research-trainer.md",
        "2026-05-26-market-regime-profit-trainer.md",
    )

    offenders = []
    for root in checked_roots:
        for path in root.rglob("*.md"):
            if path in excluded:
                continue
            text = path.read_text(encoding="utf-8")
            for token in forbidden_tokens:
                if token in text:
                    offenders.append(f"{path}:{token}")

    assert offenders == []


def test_current_project_docs_do_not_repeat_known_stale_facts():
    checked_paths = [
        Path("README.md"),
        Path("CLAUDE.md"),
        *Path("docs").rglob("*.md"),
        *Path("wiki").rglob("*.md"),
    ]
    excluded = {Path("docs/DOCUMENTATION.md")}
    forbidden_tokens = (
        "34维度",
        "34 维度",
        "四维加权",
        "多因子四维",
        "9 页",
        "9页",
        "FastAPI（9",
        "3页",
        "3 页",
        "5517",
        "全局 ticker",
        "底部 ticker",
        "点位与日涨跌",
        "Regime Score",
    )

    offenders = []
    for path in checked_paths:
        if path in excluded:
            continue
        text = path.read_text(encoding="utf-8")
        for token in forbidden_tokens:
            if token in text:
                offenders.append(f"{path}:{token}")

    assert offenders == []


def test_web_docs_match_current_market_regime_layout_contract():
    spec = Path("docs/specs/05-web-platform.md").read_text(encoding="utf-8")
    decision = Path("wiki/decisions/web-architecture.md").read_text(encoding="utf-8")
    acceptance = Path("docs/acceptance-matrix.md").read_text(encoding="utf-8")
    combined = "\n".join([spec, decision, acceptance])

    required_tokens = (
        "Risk Buffer",
        "A-share Breadth",
        "Index Trend",
        "Above MA20",
        "Confirmed",
        "Raw",
        "Pending",
        "Dwell",
        "MODE / REGIME / FRESH",
    )

    missing = [token for token in required_tokens if token not in combined]
    assert missing == []


def test_backtest_entrypoint_no_longer_exposes_legacy_runner():
    text = Path("backtest/run_all_strategies.py").read_text(encoding="utf-8")

    assert "def run_backtest(" not in text
    assert "--legacy" not in text
    assert "legacy hand-rolled" not in text


def test_backtest_regime_replay_uses_production_policy_not_monthly_ma_chain():
    text = Path("backtest/run_all_strategies.py").read_text(encoding="utf-8")
    tournament = Path("scripts/strategy_tournament.py").read_text(encoding="utf-8")
    multi_asset = Path("scripts/multi_asset_tournament.py").read_text(encoding="utf-8")

    assert "build_production_regime_map" in text
    assert "CHAMPION_POLICY" in text
    assert "apply_policy" in text
    assert "c > ma5 > ma20 > ma60" not in text
    assert "c < ma5 < ma20 < ma60" not in text
    assert "build_monthly_regime" not in tournament
    assert "build_production_regime_map" in multi_asset
    assert "c > ma5 > ma20 > ma60" not in multi_asset
    assert "c < ma5 < ma20 < ma60" not in multi_asset


def test_production_regime_map_uses_previous_month_policy_result(monkeypatch):
    import research.regime_training as regime_training
    from backtest.run_all_strategies import build_production_regime_map

    dates = pd.date_range("2024-01-01", periods=180, freq="D")
    close = pd.Series(np.linspace(100.0, 120.0, len(dates)), index=dates)

    def fake_feature_history(index_frame):
        assert {"date", "close", "volume"}.issubset(index_frame.columns)
        return pd.DataFrame({"feature": 1.0}, index=dates)

    def fake_apply_policy(features, _policy):
        regimes = pd.Series("sideways", index=features.index)
        regimes.loc[regimes.index >= pd.Timestamp("2024-02-29")] = "bull"
        regimes.loc[regimes.index >= pd.Timestamp("2024-03-31")] = "bear"
        return pd.DataFrame({"regime": regimes}, index=features.index)

    monkeypatch.setattr(regime_training, "build_regime_feature_history", fake_feature_history)
    monkeypatch.setattr(regime_training, "apply_policy", fake_apply_policy)

    result = build_production_regime_map(close)

    assert result["2024-01"] == "sideways"
    assert result["2024-02"] == "sideways"
    assert result["2024-03"] == "bull"
    assert result["2024-04"] == "bear"


def test_paper_pipeline_uses_live_regime_context_not_sideways_constant():
    text = Path("scripts/execute_paper_trades.py").read_text(encoding="utf-8")

    assert "detect_live_regime" in text
    assert 'regime="sideways"' not in text
    assert 'generate_alpha([], pd.DataFrame(), 0, ctx.regime)' in text


def test_signal_spec_describes_current_regime_formula():
    text = Path("docs/specs/02-signal-system.md").read_text(encoding="utf-8")

    assert "trend 30%" in text
    assert "breadth 30%" in text
    assert "risk 30%" in text
    assert "volume 10%" in text
    assert "价格 > MA5 > MA20 > MA60" not in text
    assert "月度 K 线判断" not in text


def test_tracked_project_context_uses_canonical_astrolabe_names():
    tracked_files = subprocess.check_output(["git", "ls-files"], text=True).splitlines()
    forbidden = [
        "QUANT" + "_AGENT_",
        "XING" + "PAN_",
        "quant" + "-agent",
        "xing" + "pan",
    ]

    offenders = []
    for raw_path in tracked_files:
        path = Path(raw_path)
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for marker in forbidden:
            if marker in text:
                offenders.append(str(path))
                break

    assert offenders == []
