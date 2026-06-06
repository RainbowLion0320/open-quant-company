import pandas as pd
import yaml


def test_candidate_signal_row_contract():
    from signals.candidates.common import build_signal_row

    row = build_signal_row(
        symbol="000001",
        name="平安银行",
        industry="银行",
        score=82.5,
        signal="buy",
        detail={"reason": "test"},
    )

    assert row["symbol"] == "000001"
    assert row["name"] == "平安银行"
    assert row["industry"] == "银行"
    assert row["score"] == 82.5
    assert row["signal"] == "buy"
    assert row["detail"]["reason"] == "test"


def test_cross_section_percentile_score_bounds():
    from signals.candidates.common import percentile_score

    scores = percentile_score(pd.Series([10, 20, 30], index=["a", "b", "c"]))

    assert scores["a"] == 0.0
    assert scores["c"] == 100.0
    assert all(0.0 <= value <= 100.0 for value in scores.values())


def test_candidate_strategy_runners_return_signal_rows_for_small_limit():
    modules = [
        "signals.candidates.trend_following",
        "signals.candidates.donchian_breakout",
        "signals.candidates.rps_relative_strength",
        "signals.candidates.sector_rotation",
        "signals.candidates.quality_value",
        "signals.candidates.low_vol_defensive",
        "signals.candidates.volume_confirmation",
        "signals.candidates.regime_gated",
    ]

    for module_name in modules:
        module = __import__(module_name, fromlist=["compute"])
        rows = module.compute(limit=5)
        assert isinstance(rows, list)
        for row in rows:
            assert {"symbol", "name", "industry", "score", "signal", "detail"}.issubset(row)
            assert row["signal"] in {"buy", "hold", "sell"}
            assert 0 <= row["score"] <= 100


def test_quality_value_backtest_inputs_are_cut_to_rebalance_date(monkeypatch):
    from backtest import candidate_alpha

    fin = pd.DataFrame(
        {
            "报告期": ["2019-12-31", "2025-12-31"],
            "净资产收益率": ["10%", "50%"],
            "销售毛利率": ["20%", "80%"],
        }
    )
    valuation = pd.DataFrame(
        {
            "trade_date": ["2020-01-02", "2025-01-02"],
            "pe_ttm": [20.0, 1.0],
            "pb": [3.0, 0.5],
        }
    )

    monkeypatch.setattr("data.ingestion.fetchers.financial.read_financial_summary", lambda symbol: fin)
    monkeypatch.setattr("data.ingestion.fetchers.financial.read_valuation", lambda symbol: valuation)
    candidate_alpha._quality_inputs.cache_clear()

    inputs = candidate_alpha._quality_inputs("000001", 1, "2020-06-01")

    assert inputs == {
        "roe": 0.10,
        "gross_margin": 0.20,
        "pe_ttm": 20.0,
        "pb": 3.0,
    }


def test_trend_following_reads_core_params_from_settings(tmp_path, monkeypatch):
    from core.settings import clear_settings_cache
    from signals.candidates import trend_following

    settings_path = tmp_path / "settings.yaml"
    settings_path.write_text(
        yaml.safe_dump(
            {
                "strategies": {
                    "trend_following": {
                        "params": {
                            "min_history_days": 5,
                            "short_ma_window": 2,
                            "medium_ma_window": 3,
                            "long_ma_window": 4,
                            "momentum_window": 2,
                            "score_weights": {
                                "trend": 1.0,
                                "above_long_ma": 0.0,
                                "momentum": 0.0,
                            },
                            "trend_score_values": {
                                "strong": 12.0,
                                "medium": 8.0,
                                "price_above_medium": 4.0,
                                "price_above_long": 2.0,
                            },
                        }
                    }
                },
                "signal_selection": {
                    "strategies": {
                        "trend_following": {
                            "min_score": 0,
                            "top_pct": 1.0,
                            "min_buys": 1,
                            "max_buys": 5,
                        }
                    }
                },
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("ASTROLABE_SETTINGS", str(settings_path))
    clear_settings_cache()

    seen_min_rows: list[int] = []

    def fake_price_frame(symbol: str, min_rows: int = 2) -> pd.DataFrame:
        seen_min_rows.append(min_rows)
        frame = pd.DataFrame(
            {
                "date": pd.date_range("2026-01-01", periods=6, freq="D"),
                "close": [10.0, 11.0, 12.0, 13.0, 14.0, 16.0],
                "volume": [100.0, 110.0, 120.0, 130.0, 140.0, 150.0],
            }
        )
        return frame if len(frame) >= min_rows else pd.DataFrame()

    monkeypatch.setattr(trend_following, "candidate_symbols", lambda limit=0: ["000001"])
    monkeypatch.setattr(trend_following, "price_frame", fake_price_frame)

    rows = trend_following.compute(limit=1)

    assert seen_min_rows == [5]
    assert len(rows) == 1
    assert rows[0]["detail"]["trend_score"] == 12.0
    assert rows[0]["score"] == 12.0


def test_candidate_selection_runtime_override_can_tighten_max_buys(tmp_path, monkeypatch):
    from core.settings import clear_settings_cache
    from signals.candidates.common import build_signal_row, selected_candidate_rows

    settings_path = tmp_path / "settings.yaml"
    settings_path.write_text(
        yaml.safe_dump(
            {
                "signal_selection": {
                    "top_pct": 1.0,
                    "min_buys": 1,
                    "max_buys": 20,
                    "min_score": 0,
                    "strategies": {
                        "regime_gated": {
                            "top_pct": 1.0,
                            "min_buys": 1,
                            "max_buys": 20,
                            "min_score": 0,
                        }
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("ASTROLABE_SETTINGS", str(settings_path))
    clear_settings_cache()

    rows = [
        build_signal_row(str(i), str(i), "", 100.0 - i, "hold", {"strategy": "regime_gated"})
        for i in range(5)
    ]

    selected = selected_candidate_rows(
        rows,
        "regime_gated",
        selection_overrides={"max_buys": 2},
    )

    assert sum(1 for row in selected if row["signal"] == "buy") == 2
