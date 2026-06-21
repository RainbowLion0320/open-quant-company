import importlib
import os
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import subprocess
import sys

from astrolabe_cli.commands.docs import DRIFT_TOKENS, REMOVED_COMPATIBILITY_TOKENS


def _joined(*parts: str) -> str:
    return "".join(parts)


def _path(*parts: str) -> Path:
    return Path(*parts)


REMOVED_COMPATIBILITY_MODULES = (
    (_joined("web.api.", "settings_schema"), _path("web", "api", "settings_schema.py")),
    (_joined("data.llm.", "deepseek_usage"), _path("data", "llm", "deepseek_usage.py")),
    (_joined("cybernetics.", "hmm_engine"), _path("cybernetics", "hmm_engine.py")),
    (_joined("cybernetics.", "market_observations"), _path("cybernetics", "market_observations.py")),
    (_joined("research.", "regime_training"), _path("research", "regime_training.py")),
    (_joined("research.regime.", "core"), _path("research", "regime", "core.py")),
    (_joined("data.market.", "sectors"), _path("data", "market", "sectors.py")),
)


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


def test_paper_order_preview_marks_invalid_numeric_inputs_explicitly():
    from broker import PaperBroker

    broker = PaperBroker(initial_cash=100000, enable_risk=False)
    preview = broker.preview_order(
        {
            "symbol": "000001",
            "side": "buy",
            "quantity": "not-a-number",
            "order_type": "limit",
            "limit_price": 10.0,
            "evidence_refs": ["ev_demo"],
        }
    )

    assert preview["status"] == "blocked"
    assert "invalid_quantity_format" in preview["risk_gate"]["blockers"]


def test_agent_provider_confidence_has_one_canonical_validator():
    router_source = Path("agent_os/router.py").read_text(encoding="utf-8")
    planner_source = Path("agent_os/tool_planner.py").read_text(encoding="utf-8")

    assert "def _bounded_confidence" not in router_source
    assert "def _bounded_confidence" not in planner_source
    assert "from agent_os.validation import bounded_confidence" in router_source
    assert "from agent_os.validation import bounded_confidence" in planner_source


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


def test_paper_broker_order_lifecycle_is_composed_not_mixin_inherited():
    core_text = Path("broker/paper_core.py").read_text(encoding="utf-8")
    orders_text = Path("broker/paper_orders.py").read_text(encoding="utf-8")

    assert "PaperOrderMixin" not in core_text
    assert "class PaperOrderService" in orders_text
    assert "class PaperOrderMixin" not in orders_text
    assert "from broker.paper_core" not in orders_text


def test_enabled_strategy_plugins_have_runners():
    from data.strategy.plugins import iter_strategy_plugins

    plugins = list(iter_strategy_plugins("all"))
    assert plugins
    for plugin in plugins:
        assert callable(plugin.load_runner())


def test_strategy_runners_do_not_point_at_cli_scripts():
    from data.strategy.plugins import DEFAULT_RUNNERS

    offenders = {name: runner for name, runner in DEFAULT_RUNNERS.items() if runner.startswith("scripts.")}

    assert offenders == {}


def test_api_serialization_helpers_have_single_source():
    serializers = Path("web/api/serializers.py").read_text(encoding="utf-8")
    system_common = Path("web/api/services/system_common.py").read_text(encoding="utf-8")

    assert "def safe_float(" in serializers
    assert "def safe_int(" in serializers
    assert "def json_value(" in serializers
    assert "def json_map(" in serializers
    assert "def safe_float(" not in system_common
    assert "def safe_int(" not in system_common
    assert "def json_value(" not in system_common
    assert "def json_map(" not in system_common


def test_datahub_snapshot_discovery_is_not_reimplemented_in_signal_or_web_layers():
    checked_paths = [
        Path("signals/multifactor.py"),
        Path("web/api/services/sectors.py"),
    ]
    offenders = []
    for path in checked_paths:
        text = path.read_text(encoding="utf-8")
        if 'glob("*.parquet")' in text or "glob('*.parquet')" in text:
            offenders.append(str(path))

    assert offenders == []
    assert "latest_dimension_snapshot" in Path("signals/multifactor.py").read_text(encoding="utf-8")
    assert "latest_dimension_snapshot" in Path("web/api/services/sectors.py").read_text(encoding="utf-8")


def test_backtest_strategy_scorers_reuse_shared_signal_scoring_helpers():
    text = Path("backtest/strategy_scorers.py").read_text(encoding="utf-8")

    assert "technical_factors_from_series" in text
    assert "score_cybernetic_from_factors" in text
    assert "np.diff(" not in text
    assert "np.std(" not in text
    assert "bull_sectors =" not in text
    assert "bear_sectors =" not in text
    assert "sideways_sectors =" not in text


def test_backtest_runner_covers_all_enabled_backtest_strategies():
    from data.strategy.catalog import get_enabled_strategies
    from backtest.run_all_strategies import backtest_strategy_names

    enabled_backtest = {
        item["name"]
        for item in get_enabled_strategies()
        if "backtest" in item.get("capabilities", ["backtest"])
    }

    assert enabled_backtest <= set(backtest_strategy_names())


def test_multifactor_backtest_uses_point_in_time_financial_snapshots(monkeypatch):
    import backtest.strategy_scorers as scorers

    series = pd.Series(
        [10.0 + i * 0.01 for i in range(160)],
        index=pd.date_range("2020-01-02", periods=160, freq="B"),
    )
    pit_inputs = {
        "AAA": {
            "fcf": 1.0,
            "growth_rate": 0.05,
            "shares_outstanding": 1.0,
            "roe_history": [0.12, 0.13, 0.14, 0.15, 0.16],
            "gross_margin_history": [0.35, 0.36, 0.37, 0.38, 0.39],
            "net_margin_history": [0.12, 0.12, 0.13, 0.13, 0.14],
            "debt_equity": 0.3,
            "sector": "consumer",
            "industry": "测试行业",
        }
    }
    built_years = []

    def fake_build_pit_financial_inputs(year, pool, *, log_label="财务PIT"):
        built_years.append((year, list(pool), log_label))
        return pit_inputs

    def fail_realtime_financial_inputs(*args, **kwargs):
        raise AssertionError("multifactor backtest must not call realtime Buffett inputs")

    monkeypatch.setattr(scorers, "build_pit_financial_inputs", fake_build_pit_financial_inputs)
    monkeypatch.setattr("data.market.financials.get_buffett_inputs", fail_realtime_financial_inputs)
    scorers._multifactor_fin_cache.clear()
    scorers.multifactor_scorer._pool = ["AAA"]

    score = scorers.multifactor_scorer("AAA", series, len(series) - 1, "sideways")

    assert score >= 0
    assert built_years == [(2020, ["AAA"], "多因子")]


def test_buffett_pit_builder_reuses_symbol_source_frames(monkeypatch):
    import backtest.buffett_real_scorer as scorer

    financial_reads = []
    daily_reads = []
    financial = pd.DataFrame(
        {
            "报告期": pd.to_datetime(
                [
                    "2014-12-31",
                    "2015-12-31",
                    "2016-12-31",
                    "2017-12-31",
                    "2018-12-31",
                    "2019-12-31",
                    "2020-12-31",
                ]
            ),
            "净利润": ["100"] * 7,
            "净利润同比增长率": ["5%"] * 7,
            "销售毛利率": ["35%"] * 7,
            "销售净利率": ["12%"] * 7,
            "净资产收益率": ["15%"] * 7,
            "产权比率": ["0.3"] * 7,
        }
    )
    daily = pd.DataFrame(
        {
            "date": pd.to_datetime(["2019-12-30", "2020-12-30"]),
            "outstanding_share": [100_000_000.0, 120_000_000.0],
        }
    )

    def fake_financial_summary(symbol):
        financial_reads.append(symbol)
        return financial.copy()

    def fake_stock_daily(symbol):
        daily_reads.append(symbol)
        return daily.copy()

    monkeypatch.setattr("data.market.financials.get_financial_summary", fake_financial_summary)
    monkeypatch.setattr("data.ingestion.fetcher.get_stock_daily", fake_stock_daily)
    scorer._PIT_FINANCIAL_INPUTS_CACHE.clear()
    scorer._PIT_SYMBOL_SOURCE_CACHE.clear()

    first = scorer.build_pit_financial_inputs(2020, ["AAA"], log_label="测试")
    second = scorer.build_pit_financial_inputs(2021, ["AAA"], log_label="测试")

    assert "AAA" in first
    assert "AAA" in second
    assert financial_reads == ["AAA"]
    assert daily_reads == ["AAA"]


def test_backtest_runner_persists_each_strategy_result_file():
    text = Path("backtest/run_all_strategies.py").read_text(encoding="utf-8")

    assert 'BACKTEST_ARTIFACT_DIR / f"backtest_{name}.pkl"' in text


def test_multi_asset_tournament_reuses_shared_momentum_helpers():
    text = Path("scripts/multi_asset_tournament.py").read_text(encoding="utf-8")

    assert "from backtest.momentum import" in text
    assert "def momentum_score(" not in text
    assert "def run_strat(" not in text


def test_feature_scripts_use_shared_feature_store_loaders():
    checked_paths = [
        Path("signals/ml_signals.py"),
        Path("scripts/build_features.py"),
        Path("scripts/enrich_pe_pb.py"),
        Path("research/factors/hypothesis/cli.py"),
        Path("scripts/lookahead_check.py"),
        Path("scripts/strategy_tournament.py"),
        Path("scripts/tune_model.py"),
        Path("scripts/train_regime_models.py"),
    ]
    offenders = []
    for path in checked_paths:
        text = path.read_text(encoding="utf-8")
        if 'FEATURES_DIR.glob("*.parquet")' in text or "FEATURES_DIR.glob('*.parquet')" in text:
            offenders.append(str(path))

    assert offenders == []

    feature_store = Path("data/features/feature_store.py").read_text(encoding="utf-8")
    assert "def iter_feature_files(" in feature_store
    assert "def load_feature_panel(" in feature_store
    assert "def latest_feature_frame(" in feature_store


def test_health_check_uses_datahub_dimension_snapshot_listing():
    text = Path("scripts/db_health_check.py").read_text(encoding="utf-8")

    assert "list_dimension_snapshots" in text
    assert "iter_feature_files" in text
    assert "root.glob(\"*.parquet\")" not in text
    assert 'feat_dir.glob("*.parquet")' not in text
    assert 'STORE / "features"' not in text


def test_feature_store_registry_enrichment_uses_dimension_snapshot_listing():
    text = Path("data/features/feature_store.py").read_text(encoding="utf-8")

    assert 'list_dimension_snapshots("moneyflow_monthly")' in text
    assert 'HUB.store_dir("stock") / "moneyflow" / "monthly"' not in text


def test_moneyflow_scripts_use_registry_dimension_paths():
    text = Path("scripts/fetch_moneyflow_full.py").read_text(encoding="utf-8")

    assert 'dimension_root("moneyflow_monthly")' in text
    assert 'HUB.store_dir("stock") / "moneyflow" / "monthly"' not in text


def test_regime_ml_training_uses_production_regime_replay():
    text = Path("scripts/train_regime_models.py").read_text(encoding="utf-8")

    assert "build_production_regime_map" in text
    assert "current > ma5 > ma20 > ma60" not in text
    assert "current < ma5 < ma20 < ma60" not in text
    assert "ma5 = " not in text


def test_compute_signals_import_has_no_runtime_side_effects(monkeypatch):
    import socket

    monkeypatch.setenv("http_proxy", "http://proxy.invalid")
    before_timeout = socket.getdefaulttimeout()

    module = importlib.import_module("scripts.compute_signals")

    assert callable(module.main)
    assert socket.getdefaulttimeout() == before_timeout
    assert "http_proxy" in os.environ


def test_datahub_catalog_includes_data_registry_dimensions():
    from data.storage.datahub import get_datahub

    catalog = get_datahub().catalog()
    assert "signals" in catalog
    assert any(key.startswith("dimension:") for key in catalog)


def test_stock_daily_read_path_does_not_implicitly_fetch_api(monkeypatch):
    from data.ingestion import fetcher
    import data.ingestion.fetchers.stock_daily as stock_daily

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
    import web.api.services.system_data_ops as data_ops
    import web.api.services.system_integrations as integrations

    route_text = Path("web/api/routes/system.py").read_text()

    assert not Path("web/api/services/system_monitor.py").exists()
    assert "system_monitor_payload" not in route_text
    assert "system_history_payload" not in route_text
    assert callable(data_health.db_health_payload)
    assert callable(data_ops.quality_gate_payload)
    assert callable(integrations.api_health_payload)
    assert callable(integrations.cron_jobs_payload)
    assert "def _query(" not in route_text
    assert "def _read_token(" not in route_text
    assert "def _run_repair(" not in route_text
    assert "def _repairable_tables(" not in route_text
    assert "from data.quality.quality import DataQualityGate" not in route_text


def test_removed_token_usage_and_system_metric_cron_artifacts_do_not_reappear():
    stale_tokens = (
        _joined("update_", "token_cache"),
        _joined("collect_", "system_metrics"),
        _joined("ingest_", "deepseek_cdp"),
        _joined("hind", "sight_", "tokens_path"),
        _joined("system_", "monitor_path"),
        _joined("token_", "usage_path"),
        _joined("llm_", "usage_today"),
    )
    tracked = subprocess.check_output(["git", "ls-files"], text=True).splitlines()
    checked_suffixes = (".py", ".md", ".ts", ".vue", ".css", ".json", ".yaml", ".yml")
    offenders = []
    for filename in tracked:
        if not filename.endswith(checked_suffixes):
            continue
        path = Path(filename)
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for token in stale_tokens:
            if token in text:
                offenders.append(f"{filename}:{token}")

    assert offenders == []


def test_web_api_routes_do_not_import_data_layer_directly():
    offenders = []
    for path in Path("web/api/routes").glob("*.py"):
        text = path.read_text(encoding="utf-8")
        for token in ("from data.", "import data."):
            if token in text:
                offenders.append(f"{path}:{token}")

    assert offenders == []


def test_web_api_does_not_depend_on_cli_commands():
    offenders = []
    for path in Path("web/api").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "astrolabe_cli" in text:
            offenders.append(str(path))

    assert offenders == []


def test_pipeline_service_does_not_depend_on_entrypoint_scripts():
    text = Path("web/api/services/pipeline.py").read_text(encoding="utf-8")

    assert "from scripts." not in text
    assert "import scripts." not in text


def test_pipeline_service_is_registry_facade_not_monolithic_builders():
    service_text = Path("web/api/services/pipeline.py").read_text(encoding="utf-8")
    pipeline_modules = {
        path.name
        for path in Path("web/api/services/pipelines").glob("*.py")
        if path.name != "__init__.py"
    }

    assert {"common.py", "market_regime.py", "data_quality.py", "strategy_evidence.py", "portfolio_execution.py"}.issubset(
        pipeline_modules
    )
    assert "from cybernetics.orchestrator import QuantOrchestrator" not in service_text
    assert "from core.settings import get_section" not in service_text
    assert "from research.strategy_evaluation import list_evidence_artifacts" not in service_text
    assert "def build_market_regime_pipeline(" not in service_text
    assert "def build_data_quality_pipeline(" not in service_text
    assert "def build_strategy_evidence_pipeline(" not in service_text
    assert "def build_portfolio_execution_pipeline(" not in service_text


def test_cybernetics_runtime_types_live_in_dedicated_module():
    orchestrator_text = Path("cybernetics/orchestrator.py").read_text(encoding="utf-8")
    types_path = Path("cybernetics/types.py")

    assert types_path.exists()
    assert "from cybernetics.types import" in orchestrator_text
    assert "class MarketContext" not in orchestrator_text
    assert "class MarketBreadth" not in orchestrator_text
    assert "class MarketVolume" not in orchestrator_text
    assert "class TradeRecord" not in orchestrator_text


def test_backtest_regime_replay_lives_in_dedicated_module():
    runner_text = Path("backtest/run_all_strategies.py").read_text(encoding="utf-8")
    replay_text = Path("backtest/regime_replay.py").read_text(encoding="utf-8")

    assert "from backtest.regime_replay import build_production_regime_map" in runner_text
    assert "def build_production_regime_map(" not in runner_text
    assert "def _benchmark_close_frame(" not in runner_text
    assert "def build_production_regime_map(" in replay_text
    assert "CHAMPION_POLICY" in replay_text
    assert "apply_policy" in replay_text


def test_regime_training_policy_types_live_in_dedicated_module():
    policies_text = Path("research/regime/policies.py").read_text(encoding="utf-8")
    evaluation_text = Path("research/regime/evaluation.py").read_text(encoding="utf-8")
    types_text = Path("research/regime_types.py").read_text(encoding="utf-8")

    assert "from research.regime_types import" in policies_text
    assert "from research.regime_types import" in evaluation_text
    assert "class RegimePolicy" not in policies_text
    assert "class PromotionGateResult" not in evaluation_text
    assert "class RegimePolicy" in types_text
    assert "class PromotionGateResult" in types_text


def test_pipeline_vue_uses_shared_layout_utility():
    vue_text = Path("web/frontend/src/views/Pipeline.vue").read_text(encoding="utf-8")
    utility_text = Path("web/frontend/src/utils/pipelineLayout.ts").read_text(encoding="utf-8")
    package_text = Path("web/frontend/package.json").read_text(encoding="utf-8")

    assert "elkjs" in package_text
    assert "layoutPipelineGraph" in vue_text
    assert "visiblePipelineEdges" in vue_text
    assert "export async function layoutPipelineGraph" in utility_text
    assert "elk.algorithm" in utility_text
    assert "layered" in utility_text
    assert "elk.edgeRouting" in utility_text
    assert "ORTHOGONAL" in utility_text
    assert "balanceLayerCenters" in utility_text
    assert "routePipelineEdges" in utility_text
    assert "isSelectedEdge" in vue_text
    assert "flow-edge-highlight" in vue_text
    assert "pipeline-flow" in vue_text
    assert "stroke-dashoffset" in vue_text
    assert "Compute depth via topological BFS" not in vue_text


def test_data_freshness_gate_is_shared_outside_cli_layer():
    from data.quality.freshness_gate import freshness_gate, health_result_to_gate_data

    rows = health_result_to_gate_data([
        {"table": "stock_daily", "freshness_status": "stale", "missing_pct": 0},
        {"table": "macro_gdp", "freshness_status": "missing", "missing_pct": 100},
        {"table": "features_all", "freshness_status": "fresh", "missing_pct": 0},
        {"table": "stock_income_statement", "freshness_status": "fresh", "missing_pct": 60.85},
    ])

    gate = freshness_gate(rows)

    assert gate["ok"] is False
    assert gate["stale"] == ["stock_daily"]
    assert gate["missing"] == ["macro_gdp"]
    assert gate["warnings"] == []
    assert {item["key"] for item in gate["details"]} == {"stock_daily", "macro_gdp"}


def test_rate_limited_market_event_freshness_is_warning_until_required():
    from data.quality.freshness_gate import freshness_gate, health_result_to_gate_data

    rows = health_result_to_gate_data([
        {
            "table": "stock_limit_list",
            "registry_key": "limit_list",
            "freshness_status": "stale",
            "repair_policy": "rate_limited",
            "data_domain": "market_event",
            "freshness_reason": "rate_limited_background_collection",
        }
    ])

    global_gate = freshness_gate(rows)
    required_gate = freshness_gate(rows, required=["stock_limit_list"])

    assert global_gate["ok"] is True
    assert global_gate["stale"] == []
    assert global_gate["warnings"] == ["stock_limit_list"]
    assert global_gate["details"][0]["severity"] == "warning"
    assert required_gate["ok"] is False
    assert required_gate["stale"] == ["stock_limit_list"]


def test_registry_warning_freshness_is_observable_but_not_global_blocker():
    from data.quality.freshness_gate import freshness_gate, health_result_to_gate_data

    rows = health_result_to_gate_data([
        {
            "table": "stock_moneyflow_daily",
            "registry_key": "moneyflow_daily",
            "freshness_status": "stale",
            "freshness_severity": "warning",
            "freshness_reason": "source_unavailable",
        }
    ])

    global_gate = freshness_gate(rows)
    required_gate = freshness_gate(rows, required=["stock_moneyflow_daily"])

    assert global_gate["ok"] is True
    assert global_gate["warnings"] == ["stock_moneyflow_daily"]
    assert global_gate["details"][0]["severity"] == "warning"
    assert required_gate["ok"] is False
    assert required_gate["stale"] == ["stock_moneyflow_daily"]


def test_formal_lifecycle_does_not_silently_fill_core_evidence_gaps():
    price_service = Path("data/market/price_service.py").read_text(encoding="utf-8")
    competition = Path("research/strategy_competition.py").read_text(encoding="utf-8")
    ml_strategy = Path("backtest/strategies/ml_strategy.py").read_text(encoding="utf-8")
    runners = Path("signals/runners.py").read_text(encoding="utf-8")

    assert "strict: bool = False" in price_service
    assert "raise FileNotFoundError" in price_service
    assert "alpha_ic = None" not in competition
    assert "missing_score_panel" in competition
    assert "missing_data_readiness" in competition
    assert "X = X.replace([np.inf, -np.inf], np.nan).fillna(0)" not in ml_strategy
    assert "missing_required_features" in ml_strategy
    assert "return latest cached/refreshed close price, or 0" not in runners.lower()
    assert "SignalDataUnavailable" in runners


def test_portfolio_sector_exposure_alias_is_removed():
    route_text = Path("web/api/routes/portfolio.py").read_text()
    sectors_route_text = Path("web/api/routes/sectors.py").read_text()

    assert "build_sector_exposure" not in route_text
    assert "build_sector_exposure" in sectors_route_text
    assert 'dimension_root("sector_exposure_snapshot")' not in route_text
    assert "root.glob(\"*.parquet\")" not in route_text


def test_regime_training_reuses_shared_metric_helpers():
    feature_text = Path("research/regime/features.py").read_text()
    evaluation_text = Path("research/regime/evaluation.py").read_text()

    assert "from research.performance import portfolio_metrics" in evaluation_text
    assert "from research.forward_labels import" in feature_text
    assert "def _portfolio_metrics(" not in evaluation_text
    assert "def _future_compound_return(" not in feature_text


def test_frontend_sector_metrics_are_shared():
    sectors = Path("web/frontend/src/views/Sectors.vue").read_text()
    sectors_view_model = Path("web/frontend/src/view-models/useSectorsView.ts").read_text()
    market = Path("web/frontend/src/views/Market.vue").read_text()
    sector_utils = Path("web/frontend/src/utils/sector.ts").read_text()

    assert "../utils/sector" in sectors_view_model
    assert "../utils/sector" in market
    assert "export function signalPower" in sector_utils
    assert "export function dataSourceLabel" in sector_utils
    assert "function signalPower(" not in sectors_view_model
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
    excluded = {Path("docs/project/documentation.md")}
    forbidden_tokens = DRIFT_TOKENS

    offenders = []
    for path in checked_paths:
        if path in excluded:
            continue
        text = path.read_text(encoding="utf-8")
        for token in forbidden_tokens:
            if token in text:
                offenders.append(f"{path}:{token}")

    assert offenders == []


def test_runtime_code_and_docs_do_not_keep_removed_compatibility_entrypoints():
    tracked_files = subprocess.check_output(["git", "ls-files"], text=True).splitlines()
    forbidden_tokens = REMOVED_COMPATIBILITY_TOKENS
    checked_suffixes = {".py", ".md", ".ts", ".tsx", ".vue", ".yaml", ".yml", ".json"}
    excluded_paths: set[Path] = set()
    excluded_roots = {
        "tests",
        "var",
        "web/frontend/node_modules",
        "web/frontend/dist",
    }

    offenders = []
    for raw_path in tracked_files:
        path = Path(raw_path)
        if (
            path in excluded_paths
            or not path.exists()
            or path.suffix not in checked_suffixes
            or any(raw_path == root or raw_path.startswith(root + "/") for root in excluded_roots)
        ):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        offenders.extend(f"{path}:{token}" for token in forbidden_tokens if token in text)

    assert offenders == []


def test_removed_compatibility_modules_are_absent_and_imports_fail():
    for module_name, path in REMOVED_COMPATIBILITY_MODULES:
        sys.modules.pop(module_name, None)
        assert not path.exists(), f"{path} should be removed"
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module(module_name)


def test_workflow_runner_supports_canonical_module_steps():
    text = Path("scripts/run_workflow.py").read_text(encoding="utf-8")
    workflow = Path("config/workflows/factor_discovery.yaml").read_text(encoding="utf-8")

    assert 'module = step.get("module")' in text
    assert '"-m", module' in text
    assert "module: research.factors.hypothesis.cli" in workflow
    removed_script_step = "script: " + "/".join(["scripts", "factor_hypothesis.py"])
    assert removed_script_step not in workflow


def test_web_docs_match_current_market_regime_layout_contract():
    spec = Path("docs/specs/05-web-platform.md").read_text(encoding="utf-8")
    decision = Path("wiki/decisions/web-architecture.md").read_text(encoding="utf-8")
    acceptance = Path("docs/product/acceptance-matrix.md").read_text(encoding="utf-8")
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
        "REGIME / FRESH",
    )

    missing = [token for token in required_tokens if token not in combined]
    assert missing == []


def test_web_docs_match_current_api_pipeline_and_schema_contracts():
    spec = Path("docs/specs/05-web-platform.md").read_text(encoding="utf-8")
    decision = Path("wiki/decisions/web-architecture.md").read_text(encoding="utf-8")
    acceptance = Path("docs/product/acceptance-matrix.md").read_text(encoding="utf-8")
    schema_reference = Path("wiki/reference/data-schema.md").read_text(encoding="utf-8")
    api_init = Path("web/api/__init__.py").read_text(encoding="utf-8")

    required_by_source = {
        "web spec": (
            "routes/ (14 domain modules)",
            "`elkjs` layered + orthogonal routing",
            "GET /api/stocks",
            "POST /api/stocks/dcf",
            "GET /api/system/quality-gate",
            "GET /api/system/providers/health",
            "GET /api/strategies/jobs/{job_id}",
        ),
        "web decision": (
            "四条关键链路",
            "`elkjs` layered + orthogonal routing",
            "Three.js WebGL 3D 星空图",
        ),
        "acceptance matrix": (
            "GET /api/system/db-health",
            "GET /api/strategies/buffett",
            "ECharts、Vue ECharts adapter、Three、ELK、Vue/Pinia/Router",
            "当前无 Vite chunk warning",
        ),
        "schema reference": (
            "`web/api/schemas/*` 分域 schema",
            "路由 response models",
        ),
        "api init": (
            "14个业务路由模块",
            "Pydantic 类型分域定义",
        ),
    }
    source_text = {
        "web spec": spec,
        "web decision": decision,
        "acceptance matrix": acceptance,
        "schema reference": schema_reference,
        "api init": api_init,
    }

    missing = []
    for source, tokens in required_by_source.items():
        text = source_text[source]
        missing.extend(f"{source}:{token}" for token in tokens if token not in text)

    assert missing == []


def test_frontend_vite_splits_heavy_runtime_vendor_chunks():
    vite_config = Path("web/frontend/vite.config.ts").read_text(encoding="utf-8")
    acceptance = Path("docs/product/acceptance-matrix.md").read_text(encoding="utf-8")

    required_chunk_rules = (
        'id.includes("/echarts/")',
        'id.includes("/vue-echarts/")',
        'id.includes("/three/")',
        'id.includes("/elkjs/")',
        'id.includes("/@vue/")',
        'id.includes("/pinia/")',
        'id.includes("/vue-router/")',
    )

    missing = [rule for rule in required_chunk_rules if rule not in vite_config]
    assert missing == []
    assert "chunkSizeWarningLimit: 1500" in vite_config
    assert "vendor / ECharts / DWP chunk 仍超过 Vite warning threshold" not in acceptance
    assert "| 5.13 | 前端构建通过且 bundle 体积可追踪" in acceptance
    assert "| OK | — |" in acceptance


def test_backtest_entrypoint_no_longer_exposes_legacy_runner():
    text = Path("backtest/run_all_strategies.py").read_text(encoding="utf-8")

    assert "def run_backtest(" not in text
    assert "--legacy" not in text
    assert "legacy hand-rolled" not in text


def test_backtest_script_entrypoint_resolves_project_pipeline_package():
    result = subprocess.run(
        [sys.executable, "backtest/run_all_strategies.py", "--help"],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def test_backtest_regime_replay_uses_production_policy_not_monthly_ma_chain():
    text = Path("backtest/regime_replay.py").read_text(encoding="utf-8")
    runner = Path("backtest/run_all_strategies.py").read_text(encoding="utf-8")
    tournament = Path("scripts/strategy_tournament.py").read_text(encoding="utf-8")
    multi_asset = Path("scripts/multi_asset_tournament.py").read_text(encoding="utf-8")

    assert "build_production_regime_map" in runner
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
    import backtest.regime_replay as regime_replay
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

    monkeypatch.setattr(regime_replay, "build_regime_feature_history", fake_feature_history)
    monkeypatch.setattr(regime_replay, "apply_policy", fake_apply_policy)

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


def test_tracked_project_context_uses_canonical_open_quant_company_branding():
    tracked_files = subprocess.check_output(["git", "ls-files"], text=True).splitlines()
    forbidden = [
        "QUANT" + "_AGENT_",
        "XING" + "PAN_",
        "quant" + "-agent",
        "xing" + "pan",
        "Astro" + "labe Quant",
        "astro" + "labe-quant",
        "星" + "盘",
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


def test_deepseek_usage_no_longer_depends_on_platform_scraping_backfills():
    assert not Path("scripts", "ingest_deepseek_" + "cdp.py").exists()
    assert not Path("scripts", "ingest_deepseek_" + "usage.py").exists()
    monitor_logic = Path("web/frontend/src/view-models/useActivityMonitor.ts").read_text(encoding="utf-8")
    settings_view = Path("web/frontend/src/views/Settings.vue").read_text(encoding="utf-8")
    system_api = Path("web/frontend/src/api/modules/system.ts").read_text(encoding="utf-8")
    system_routes = Path("web/api/routes/system.py").read_text(encoding="utf-8")
    datahub = Path("data/storage/datahub.py").read_text(encoding="utf-8")
    factor_llm = Path("research/factors/hypothesis/llm.py").read_text(encoding="utf-8")

    assert _joined("api.", "llmUsage()") not in monitor_logic
    assert _joined("LLM ", "USAGE") not in settings_view
    assert "llm-panel" not in settings_view
    assert _joined("/api/system/", "llm-usage") not in system_api
    assert _joined('"/', 'llm-usage"') not in system_routes
    assert "llm_project_usage_path" in datahub
    assert "resolve_llm_use_case" in factor_llm
    assert "https://api.deepseek.com/v1" not in factor_llm
    assert "DEEPSEEK_API_KEY" not in factor_llm

    tracked_files = subprocess.check_output(["git", "ls-files"], text=True).splitlines()
    offenders = []
    forbidden = [
        "/api/v0/usage/" + "cost",
        "/api/v0/usage/" + "amount",
        "daily_" + "usage.parquet",
        "ingest_deepseek_" + "cdp",
        "ingest_deepseek_" + "usage",
        "usage_" + "data_",
        "amount-*" + ".csv",
        "cost-*" + ".csv",
    ]
    for raw_path in tracked_files:
        path = Path(raw_path)
        if not path.exists() or path.suffix not in {".py", ".md", ".ts", ".vue", ".yaml"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        offenders.extend(f"{path}:{token}" for token in forbidden if token in text)

    assert offenders == []
