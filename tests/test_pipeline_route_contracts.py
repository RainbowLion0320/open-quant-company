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
    assert [node["id"] for node in payload["nodes"]] == [
        "inputs",
        "features",
        "rule_score",
        "hmm_inference",
        "hybrid_decision",
        "stability",
        "outputs",
    ]
    node_ids = {node["id"] for node in payload["nodes"]}
    assert payload["edges"]
    assert all(edge["source"] in node_ids and edge["target"] in node_ids for edge in payload["edges"])
    for key in ("confirmed_regime", "raw_regime", "score", "engine", "detection_method", "confidence", "entropy"):
        assert key in payload["summary"]
