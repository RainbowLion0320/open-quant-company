from types import SimpleNamespace

from fastapi.testclient import TestClient

from cybernetics.orchestrator import MarketRegime


def test_market_regime_pipeline_route_contract(monkeypatch, tmp_path):
    from web.api import auth
    from web.api.app import create_app
    from web.api.services.pipelines import market_regime as market_regime_pipeline

    class FakeOrchestrator:
        params = {"position_size": 0.22, "stop_loss": -0.05, "max_positions": 6}

        def detect(self):
            return SimpleNamespace(
                regime=MarketRegime.BULL,
                raw_regime=MarketRegime.SIDEWAYS,
                regime_score=63.4,
                index_ma_trend="多指数趋势 62% · 全A上涨 57%",
                volume_trend="正常",
                breadth=0.57,
                breadth_detail={"sample_size": 5000, "above_ma20": 0.61, "as_of": "2026-05-29"},
                score_components={"trend_raw": 0.62, "breadth_raw": 0.57, "risk_raw": 0.66, "volume_raw": 0.58},
                regime_state={
                    "confirmed_value": "bull",
                    "raw_value": "sideways",
                    "pending_value": "sideways",
                    "pending_count": 1,
                    "min_dwell": 3,
                },
                date="2026-05-29",
                regime_probs={"bull": 0.42, "sideways": 0.48, "bear": 0.10},
                detection_method="hybrid",
                hmm_confidence=0.48,
                hmm_entropy=1.02,
                decision_reason="hybrid_low_confidence_blend",
            )

    model_dir = tmp_path / "regime_hmm"
    model_dir.mkdir()
    (model_dir / "meta.json").write_text('{"n_samples": 3921, "trained_at": "2026-05-29"}', encoding="utf-8")

    monkeypatch.setattr(auth, "get_api_key", lambda: "")
    monkeypatch.setattr(market_regime_pipeline, "QuantOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        market_regime_pipeline,
        "get_section",
        lambda name, default=None: {"regime_engine": "hybrid", "hmm": {"model_path": str(model_dir)}},
    )

    res = TestClient(create_app()).get("/api/pipeline/market-regime")

    assert res.status_code == 200
    payload = res.json()
    assert payload["pipeline_key"] == "market_regime"
    node_ids_ordered = [node["id"] for node in payload["nodes"]]
    for required in [
        "inputs",
        "trend",
        "breadth",
        "risk",
        "volume",
        "hmm_features",
        "rule_score",
        "hmm_inference",
        "engine_route",
        "hmm_availability",
        "mode_hmm_only",
        "mode_rule_only",
        "hybrid_compare",
        "path_consensus",
        "confidence_gate",
        "path_override",
        "path_blend",
        "raw_regime",
        "stability",
        "outputs",
    ]:
        assert required in node_ids_ordered
    assert len(node_ids_ordered) >= 18
    node_ids = {node["id"] for node in payload["nodes"]}
    assert payload["edges"]
    assert all(edge["source"] in node_ids and edge["target"] in node_ids for edge in payload["edges"])
    assert any(node.get("kind") == "decision" for node in payload["nodes"])
    assert any(node.get("kind") == "path" for node in payload["nodes"])
    assert any(edge["source"] == "hybrid_compare" and edge["target"] == "path_consensus" for edge in payload["edges"])
    assert any(edge["source"] == "confidence_gate" and edge["target"] == "path_blend" for edge in payload["edges"])
    for key in ("confirmed_regime", "raw_regime", "score", "engine", "detection_method", "confidence", "entropy"):
        assert key in payload["summary"]


def test_market_regime_pipeline_marks_hmm_only_path_active(monkeypatch, tmp_path):
    from web.api.services.pipelines import market_regime as market_regime_pipeline

    class FakeOrchestrator:
        params = {"position_size": 0.15, "stop_loss": -0.05, "max_positions": 5}

        def detect(self):
            return SimpleNamespace(
                regime=MarketRegime.BULL,
                raw_regime=MarketRegime.BULL,
                regime_score=70.0,
                breadth_detail={"sample_size": 5000, "above_ma20": 0.61, "as_of": "2026-05-29"},
                score_components={"trend_raw": 0.62, "breadth_raw": 0.57, "risk_raw": 0.66, "volume_raw": 0.58},
                regime_state={"confirmed_value": "bull", "pending_value": None, "pending_count": 0, "min_dwell": 3},
                date="2026-05-29",
                regime_probs={"bull": 0.82, "sideways": 0.12, "bear": 0.06},
                detection_method="hmm",
                hmm_confidence=0.82,
                hmm_entropy=0.56,
                decision_reason="hmm_only",
            )

    model_dir = tmp_path / "regime_hmm"
    model_dir.mkdir()
    (model_dir / "meta.json").write_text('{"n_samples": 3921, "n_features": 8}', encoding="utf-8")

    monkeypatch.setattr(market_regime_pipeline, "QuantOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        market_regime_pipeline,
        "get_section",
        lambda name, default=None: {"regime_engine": "hmm", "hmm": {"model_path": str(model_dir)}},
    )

    payload = market_regime_pipeline.build_market_regime_pipeline()
    active_decision_edges = [
        edge for edge in payload["edges"]
        if edge.get("active", True)
        and edge.get("label") == "hmm only"
        and edge["target"] == "mode_hmm_only"
    ]

    assert [edge["label"] for edge in active_decision_edges] == ["hmm only"]


def test_market_regime_pipeline_exposes_configured_thresholds_and_weights(monkeypatch, tmp_path):
    from web.api.services.pipelines import market_regime as market_regime_pipeline

    class FakeOrchestrator:
        params = {"position_size": 0.22, "stop_loss": -0.05, "confidence_threshold": 0.66, "max_positions": 6}

        def detect(self):
            return SimpleNamespace(
                regime=MarketRegime.BULL,
                raw_regime=MarketRegime.BULL,
                regime_score=72.0,
                breadth_detail={
                    "sample_size": 5000,
                    "advance_ratio": 0.62,
                    "above_ma20": 0.61,
                    "above_ma60": 0.58,
                    "above_ma120": 0.55,
                    "as_of": "2026-05-29",
                },
                score_components={
                    "trend": 25.2,
                    "breadth": 15.5,
                    "risk": 24.0,
                    "volume": 7.3,
                    "trend_raw": 0.72,
                    "breadth_raw": 0.62,
                    "risk_raw": 0.80,
                    "volume_raw": 0.73,
                },
                regime_state={"confirmed_value": "bull", "pending_value": None, "pending_count": 0, "min_dwell": 4},
                date="2026-05-29",
                regime_probs={"bull": 0.64, "sideways": 0.30, "bear": 0.06},
                detection_method="hybrid",
                hmm_confidence=0.64,
                hmm_entropy=0.72,
                decision_reason="hybrid_low_confidence_blend",
            )

    model_dir = tmp_path / "regime_hmm"
    model_dir.mkdir()
    (model_dir / "meta.json").write_text('{"n_samples": 3921, "n_features": 8}', encoding="utf-8")

    monkeypatch.setattr(market_regime_pipeline, "QuantOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        market_regime_pipeline,
        "get_section",
        lambda name, default=None: {
            "regime_engine": "hybrid",
            "hmm": {"model_path": str(model_dir)},
            "hmm_confidence_override": 0.77,
            "score_weights": {"trend": 35, "breadth": 25, "risk": 30, "volume": 10},
            "breadth_weights": {"advance_ratio": 0.40, "above_ma20": 0.30, "above_ma60": 0.20, "above_ma120": 0.10},
            "risk_strength_weights": {"drawdown": 0.55, "volatility": 0.25, "pressure": 0.20},
            "adaptive": {
                "detection": {
                    "regime_bull_threshold": 65,
                    "regime_bear_threshold": 35,
                    "regime_trend_confirm": 0.58,
                    "breadth_bull_threshold": 0.56,
                    "regime_min_dwell": 4,
                    "volume_expansion": 1.30,
                    "volume_contraction": 0.70,
                }
            },
        },
    )

    payload = market_regime_pipeline.build_market_regime_pipeline()
    by_id = {node["id"]: node for node in payload["nodes"]}

    def metrics(node_id):
        return {item["label"]: item["value"] for item in by_id[node_id]["metrics"]}

    assert metrics("rule_score")["Trend"] == "25.2 · W 35%"
    assert metrics("rule_score")["Bull gate"] == "≥ 65"
    assert metrics("rule_score")["Bear gate"] == "≤ 35"
    assert metrics("breadth")["Adv W"] == "40%"
    assert metrics("breadth")["MA60 W"] == "20%"
    assert metrics("risk")["DD W"] == "55%"
    assert metrics("risk")["Vol W"] == "25%"
    assert metrics("volume")["Expand"] == "> 1.30"
    assert metrics("volume")["Contract"] == "< 0.70"
    assert metrics("confidence_gate")["Threshold"] == "0.77"
    assert metrics("stability")["Min dwell"] == "4"
    assert metrics("outputs")["Conf th"] == "66.0%"


def test_pipeline_builders_use_granular_nodes(monkeypatch):
    from web.api.services.pipelines import data_quality, portfolio_execution, strategy_evidence

    monkeypatch.setattr(data_quality, "freshness_gate_from_health_check", lambda: ({"ok": False, "stale": ["stock"], "missing": []}, []))

    class FakeRegistry:
        def get_enabled(self):
            return [object(), object()]

    monkeypatch.setattr(data_quality, "get_registry", lambda: FakeRegistry())
    monkeypatch.setattr(
        strategy_evidence,
        "list_evidence_artifacts",
        lambda: [
            {"exists": True, "promotion_decision": "passed"},
            {"exists": True, "promotion_decision": "blocked"},
            {"exists": False},
        ],
    )

    expectations = {
        "data_quality": (
            data_quality.build_data_quality_pipeline(),
            {"dimension_filter", "schema_probe", "freshness_calc", "stale_gate", "missing_gate", "repair_policy"},
        ),
        "strategy_evidence": (
            strategy_evidence.build_strategy_evidence_pipeline(),
            {"artifact_gate", "walk_forward", "baseline_compare", "cost_model", "promotion_gate", "evidence_export"},
        ),
        "portfolio_execution": (
            portfolio_execution.build_portfolio_execution_pipeline(),
            {"signal_validation", "regime_snapshot", "risk_overlay", "rebalance_gate", "order_intents", "fill_model"},
        ),
    }
    for payload, required_nodes in expectations.values():
        node_ids = {node["id"] for node in payload["nodes"]}
        assert required_nodes <= node_ids
        assert len(payload["nodes"]) >= 10
        assert all(edge["source"] in node_ids and edge["target"] in node_ids for edge in payload["edges"])
