import importlib
from pathlib import Path

import pandas as pd
from fastapi.testclient import TestClient


def test_strategy_jobs_route_is_not_shadowed(monkeypatch):
    from web.api.app import create_app
    from web.api import jobs

    monkeypatch.setattr(
        jobs,
        "get_job",
        lambda job_id: {
            "job_id": job_id,
            "status": "running",
            "progress": 42,
            "message": "unit",
            "result": None,
        },
    )

    res = TestClient(create_app()).get("/api/strategies/jobs/unit-job")
    assert res.status_code == 200
    assert res.json()["job_id"] == "unit-job"
    assert res.json()["progress"] == 42


def test_macro_gdp_tushare_normalizes_quarter_to_date():
    from data.fetchers.macro import MacroFetcher, derive_macro_factors

    raw = pd.DataFrame(
        [
            {"QUARTER": "2025Q4", "GDP": "100", "GDP_YOY": "5.1"},
            {"QUARTER": "2026Q1", "GDP": "110", "GDP_YOY": "4.8"},
        ]
    )
    df = MacroFetcher()._normalize("gdp", raw, source="tushare")

    assert "date" in df.columns
    assert str(df.iloc[-1]["date"].date()) == "2026-03-31"
    factors = derive_macro_factors({"gdp": df}, "2026-05-20")
    assert factors["macro_gdp_yoy"] == 4.8


def test_db_health_scans_new_registry_dimensions(tmp_path, monkeypatch):
    from data.datahub import DataHub, reset_datahub

    store = tmp_path / "store"
    cache = tmp_path / "cache"
    monkeypatch.setenv("QUANT_AGENT_STORE", str(store))
    monkeypatch.setenv("QUANT_AGENT_CACHE", str(cache))
    reset_datahub()

    hub = DataHub(store_root=store, cache_root=cache)
    samples = {
        "stock/dividend/all_dividends.parquet": pd.DataFrame({"ann_date": ["20260501"], "cash_div": [1.2]}),
        "fund/daily/510300.SH.parquet": pd.DataFrame({"trade_date": ["20260520"], "close": [4.2]}),
        "fund/portfolio/20260331.parquet": pd.DataFrame({"end_date": ["20260331"], "mkv": [100.0]}),
        "fund/nav/510300.SH.parquet": pd.DataFrame({"end_date": ["20260520"], "unit_nav": [1.1]}),
        "futures/daily/IF.CFX.parquet": pd.DataFrame({"trade_date": ["20260520"], "close": [3900.0]}),
    }
    for rel, df in samples.items():
        hub.write_parquet(df, store / rel)

    import scripts.db_health_check as health

    health = importlib.reload(health)
    result = health.run_health_check(output_path=store / "db_health.parquet")
    tables = set(result["table"])

    assert {"stock_dividend", "fund_daily", "fund_portfolio", "fund_nav", "futures_daily"}.issubset(tables)
    assert (store / "db_health.parquet").exists()
    reset_datahub()


def test_limit_list_fetch_does_not_sleep_before_first_request(tmp_path, monkeypatch):
    import scripts.cron_fetch_extra as extra
    from data.datahub import DataHub

    class FakeApi:
        def __init__(self):
            self.calls = []

        def trade_cal(self, exchange, start_date, end_date):
            return pd.DataFrame(
                [
                    {"cal_date": "20260520", "is_open": 1},
                    {"cal_date": "20260519", "is_open": 1},
                ]
            )

        def limit_list_d(self, trade_date, limit_type):
            self.calls.append(trade_date)
            return pd.DataFrame({"trade_date": [trade_date], "ts_code": ["000001.SZ"]})

    fake = FakeApi()
    sleeps = []
    hub = DataHub(store_root=tmp_path / "store", cache_root=tmp_path / "cache")
    limit_store = hub.store_dir("stock") / "limit_list"
    limit_store.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(extra, "api", lambda: fake)
    monkeypatch.setattr(extra, "HUB", hub)
    monkeypatch.setattr(extra, "LIMIT_STORE", limit_store)
    monkeypatch.setattr(extra, "_throttle", lambda secs=0.5: sleeps.append(secs))

    assert extra.fetch_limit_list(full_history=False) == 1
    assert fake.calls == ["20260520"]
    assert sleeps == []


def test_deepseek_cdp_parser_joins_daily_cost_with_monthly_tokens():
    from scripts.ingest_deepseek_cdp import _parse_daily

    amount_payload = {
        "data": {
            "biz_data": {
                "total": [
                    {
                        "model": "deepseek-v4-pro",
                        "usage": [
                            {"type": "PROMPT_CACHE_MISS_TOKEN", "amount": "10"},
                            {"type": "RESPONSE_TOKEN", "amount": "5"},
                            {"type": "REQUEST", "amount": "2"},
                        ],
                        "cost": "0.12",
                    }
                ]
            }
        }
    }
    cost_payload = {
        "data": {
            "biz_data": {
                "days": [
                    {
                        "date": "2026-06-02",
                        "data": [
                            {
                                "model": "deepseek-v4-pro",
                                "usage": [
                                    {"type": "PROMPT_CACHE_MISS_TOKEN", "amount": "0.08"},
                                    {"type": "RESPONSE_TOKEN", "amount": "0.04"},
                                ],
                            }
                        ],
                    }
                ]
            }
        }
    }

    df = _parse_daily(cost_payload, amount_payload)
    row = df.iloc[0].to_dict()
    assert row["utc_date"] == "2026-06-02"
    assert row["total_tokens"] == 15
    assert row["requests"] == 2
    assert row["cost_cny"] == 0.12
