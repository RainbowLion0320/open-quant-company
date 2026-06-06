from pathlib import Path


def _line_count(path: str) -> int:
    return len(Path(path).read_text(encoding="utf-8").splitlines())


def _assert_exists(paths: list[str]) -> None:
    missing = [path for path in paths if not Path(path).exists()]
    assert missing == []


def test_regime_training_is_split_by_research_responsibility():
    _assert_exists(
        [
            "research/regime/__init__.py",
            "research/regime/core.py",
            "research/regime/features.py",
            "research/regime/policies.py",
            "research/regime/evaluation.py",
            "research/regime/reports.py",
            "research/regime/assets.py",
            "research/regime/profit_evaluation.py",
            "research/regime/profit_training.py",
            "research/regime_training.py",
        ]
    )
    assert _line_count("research/regime_training.py") <= 120
    assert _line_count("research/regime/core.py") <= 700
    assert _line_count("research/regime/profit_evaluation.py") <= 700


def test_cybernetics_orchestrator_is_a_thin_facade():
    _assert_exists(
        [
            "cybernetics/config.py",
            "cybernetics/market_observations.py",
            "cybernetics/hybrid_decision.py",
            "cybernetics/adaptive_params.py",
            "cybernetics/orchestrator.py",
        ]
    )
    assert _line_count("cybernetics/orchestrator.py") <= 360


def test_pipeline_payload_builders_are_split_into_small_units():
    _assert_exists(
        [
            "web/api/services/pipelines/market_regime.py",
            "web/api/services/pipelines/market_regime_config.py",
            "web/api/services/pipelines/market_regime_context.py",
            "web/api/services/pipelines/market_regime_nodes.py",
            "web/api/services/pipelines/market_regime_edges.py",
        ]
    )
    assert _line_count("web/api/services/pipelines/market_regime.py") <= 160
    assert _line_count("web/api/services/pipelines/market_regime_nodes.py") <= 360


def test_frontend_heavy_views_are_componentized():
    _assert_exists(
        [
            "web/frontend/src/api/client.ts",
            "web/frontend/src/api/types.ts",
            "web/frontend/src/api/modules/market.ts",
            "web/frontend/src/api/modules/portfolio.ts",
            "web/frontend/src/api/modules/system.ts",
            "web/frontend/src/components/market/RegimeHero.vue",
            "web/frontend/src/components/pipeline/PipelineCanvas.vue",
            "web/frontend/src/composables/useMarketOverview.ts",
            "web/frontend/src/composables/usePipelineData.ts",
            "web/frontend/src/composables/useHindsightThreeGraph.ts",
            "web/frontend/src/composables/hindsight/types.ts",
            "web/frontend/src/composables/hindsight/scene.ts",
            "web/frontend/src/composables/hindsight/graphBuilder.ts",
            "web/frontend/src/composables/hindsight/simulation.ts",
            "web/frontend/src/composables/hindsight/interaction.ts",
            "web/frontend/src/i18n/messages/zh-CN.ts",
            "web/frontend/src/i18n/messages/en-US.ts",
        ]
    )
    assert _line_count("web/frontend/src/views/Market.vue") <= 760
    assert _line_count("web/frontend/src/views/Pipeline.vue") <= 520
    assert _line_count("web/frontend/src/views/HindsightGraph.vue") <= 420
    assert _line_count("web/frontend/src/composables/useHindsightThreeGraph.ts") <= 260
    assert _line_count("web/frontend/src/api/index.ts") <= 120
    assert _line_count("web/frontend/src/i18n/messages.ts") <= 80


def test_market_regime_hero_keeps_ring_gauge_styles_local_to_component():
    hero = Path("web/frontend/src/components/market/RegimeHero.vue").read_text(encoding="utf-8")

    assert ".regime-orb" in hero
    assert ".mini-gauge" in hero
    assert "conic-gradient" in hero


def test_api_routes_and_schemas_are_domain_split():
    _assert_exists(
        [
            "web/api/schemas/__init__.py",
            "web/api/schemas/market.py",
            "web/api/schemas/strategy.py",
            "web/api/schemas/portfolio.py",
            "web/api/schemas/system.py",
            "web/api/schemas/pipeline.py",
            "web/api/services/stocks.py",
            "web/api/services/dcf.py",
            "web/api/services/system_orders.py",
        ]
    )
    assert not (Path("web/api") / "models.py").exists()
    assert _line_count("web/api/routes/stocks.py") <= 180
    assert _line_count("web/api/routes/system.py") <= 260


def test_p0_p2_modularization_hotspots_are_split():
    _assert_exists(
        [
            "web/frontend/src/view-models/useActivityMonitor.ts",
            "web/frontend/src/view-models/useDatabaseHealth.ts",
            "web/frontend/src/view-models/useSectorsView.ts",
            "web/frontend/src/styles/views/activity-monitor.css",
            "web/frontend/src/styles/views/database-health.css",
            "web/frontend/src/styles/views/sectors.css",
            "web/frontend/src/styles/base/tokens.css",
            "web/frontend/src/styles/base/base.css",
            "web/frontend/src/styles/layout/app-shell.css",
            "web/frontend/src/styles/layout/nav.css",
            "web/frontend/src/styles/components/common.css",
            "web/frontend/src/api/types/market.ts",
            "web/frontend/src/api/types/strategy.ts",
            "web/frontend/src/api/types/portfolio.ts",
            "web/frontend/src/api/types/system.ts",
            "web/frontend/src/api/types/sectors.ts",
            "web/frontend/src/api/types/stocks.ts",
            "web/frontend/src/api/types/pipeline.ts",
            "web/frontend/src/i18n/messages/zh-CN/index.ts",
            "web/frontend/src/i18n/messages/en-US/index.ts",
            "cybernetics/observations/sources.py",
            "cybernetics/observations/breadth.py",
            "cybernetics/observations/trend_risk.py",
            "cybernetics/observations/volume.py",
            "cybernetics/observations/scoring.py",
            "cybernetics/observations/hmm_detection.py",
            "cybernetics/hmm/core.py",
            "cybernetics/hmm/io.py",
            "cybernetics/hmm/preprocessing.py",
            "research/factors/hypothesis/core.py",
            "research/factors/hypothesis/candidates.py",
            "research/factors/hypothesis/llm.py",
            "research/factors/hypothesis/persistence.py",
            "data/market/sector_pipeline/membership.py",
            "data/market/sector_pipeline/performance.py",
            "data/market/sector_pipeline/amounts.py",
            "data/market/sector_pipeline/signals.py",
            "data/market/sector_pipeline/exposure.py",
            "broker/models.py",
            "broker/base.py",
            "broker/paper_orders.py",
            "broker/paper_state.py",
        ]
    )

    assert _line_count("web/frontend/src/views/ActivityMonitor.vue") <= 240
    assert _line_count("web/frontend/src/views/DatabaseHealth.vue") <= 240
    assert _line_count("web/frontend/src/views/Sectors.vue") <= 240
    assert _line_count("web/frontend/src/views/Strategies.vue") <= 240
    assert _line_count("web/frontend/src/views/Settings.vue") <= 240
    assert _line_count("web/frontend/src/views/ConfigCenter.vue") <= 180
    assert _line_count("web/frontend/src/views/Stocks.vue") <= 260
    assert _line_count("web/frontend/src/views/Portfolio.vue") <= 260

    assert _line_count("web/frontend/src/assets/astrolabe-quant.css") <= 80
    assert _line_count("web/frontend/src/api/types.ts") <= 80
    assert _line_count("web/frontend/src/i18n/messages/zh-CN.ts") <= 80
    assert _line_count("web/frontend/src/i18n/messages/en-US.ts") <= 80

    assert _line_count("cybernetics/market_observations.py") <= 120
    assert _line_count("cybernetics/hmm_engine.py") <= 120
    assert _line_count("scripts/factor_hypothesis.py") <= 140
    assert _line_count("data/market/sectors.py") <= 140
    assert _line_count("broker/paper.py") <= 260
