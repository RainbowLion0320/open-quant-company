import importlib
import pickle
from pathlib import Path

import pandas as pd
from fastapi.testclient import TestClient


def test_strategy_jobs_route_is_not_shadowed(monkeypatch):
    from web.api.app import create_app
    from web.api import jobs

    # Disable auth for this test (empty key = open mode)
    monkeypatch.setattr("web.api.auth.get_api_key", lambda: "")

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


def test_backtest_api_reads_current_artifact_dir(tmp_path, monkeypatch):
    from data.storage.datahub import get_datahub, reset_datahub
    from web.api.app import create_app

    monkeypatch.setattr("web.api.auth.get_api_key", lambda: "")
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "var"))
    reset_datahub()

    artifact_dir = get_datahub().artifact_dir("backtests")
    comparison = {
        "strategies": {"multifactor": {"total_return": 0.12}},
        "bench_return": 0.05,
        "start": "2024-01-02",
        "end": "2024-01-08",
    }
    detail = {
        "total_return": 0.12,
        "sharpe": 1.1,
        "max_drawdown": -0.04,
        "win_rate": 0.55,
        "trade_count": 2,
        "daily_returns": pd.Series([0.01, -0.02, 0.03], index=pd.date_range("2024-01-02", periods=3)),
        "bench_returns": pd.Series([0.005, -0.01, 0.02], index=pd.date_range("2024-01-02", periods=3)),
    }
    with open(artifact_dir / "backtest_comparison.pkl", "wb") as f:
        pickle.dump(comparison, f)
    with open(artifact_dir / "backtest_multifactor.pkl", "wb") as f:
        pickle.dump(detail, f)

    client = TestClient(create_app())
    overview = client.get("/api/backtest")
    strategy = client.get("/api/backtest/multifactor")

    assert overview.status_code == 200
    assert overview.json()["strategies"]["multifactor"]["total_return"] == 0.12
    assert strategy.status_code == 200
    assert strategy.json()["trade_count"] == 2
    assert strategy.json()["equity_curve"]
    reset_datahub()


def test_assets_overview_api_respects_config_enabled_flags(monkeypatch):
    from web.api.app import create_app

    monkeypatch.setattr("web.api.auth.get_api_key", lambda: "")

    res = TestClient(create_app()).get("/api/assets/overview")
    assert res.status_code == 200
    payload = res.json()
    by_type = {item["asset_type"]: item for item in payload["items"]}

    assert payload["total"] == len(payload["items"])
    assert by_type["stock"]["enabled"] is True
    assert by_type["etf"]["enabled"] is True
    assert by_type["bond"]["enabled"] is False
    assert by_type["futures"]["enabled"] is False
    assert by_type["crypto"]["enabled"] is False
    assert by_type["crypto"]["data_source"] == "placeholder"
    assert by_type["crypto"]["error"] == ""


def test_data_sources_capabilities_api_returns_no_artifact(monkeypatch, tmp_path):
    from data.storage.datahub import reset_datahub
    from web.api.app import create_app

    monkeypatch.setattr("web.api.auth.get_api_key", lambda: "")
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "var"))
    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("API must not audit sources")))
    reset_datahub()

    res = TestClient(create_app()).get("/api/data-sources/capabilities")

    assert res.status_code == 200
    payload = res.json()
    assert payload["status"] == "no_artifact"
    assert payload["summary"]["source_count"] >= 9
    assert payload["capabilities"] == []
    assert payload["recommended_command"] == "astroq data sources audit --source all --discovery-depth catalog --json"
    reset_datahub()


def test_db_health_freshness_color_uses_backend_sla_status():
    health = Path("web/frontend/src/views/DatabaseHealth.vue").read_text(encoding="utf-8")
    logic = Path("web/frontend/src/view-models/useDatabaseHealth.ts").read_text(encoding="utf-8")

    assert "freshness_sla_days" in logic
    assert "freshness_status" in logic
    assert "status === \"fresh\"" in logic
    assert "status === \"stale\"" in logic
    assert "freshnessClass(row)" in health
    assert "freshnessClass(row.freshness_days)" not in health


def test_db_health_repair_is_bulk_action_not_per_row_control():
    health = Path("web/frontend/src/views/DatabaseHealth.vue").read_text(encoding="utf-8")
    logic = Path("web/frontend/src/view-models/useDatabaseHealth.ts").read_text(encoding="utf-8")
    system_api = Path("web/frontend/src/api/modules/system.ts").read_text(encoding="utf-8")
    css = Path("web/frontend/src/styles/views/database-health.css").read_text(encoding="utf-8")

    assert "startRepairAll" in health
    assert "startRepairAll" in logic
    assert "dbHealthRepairAll" in system_api
    assert "dbHealthRepair: (table" not in system_api
    assert "repairAllDisabled" in health
    assert "<th>{{ t('database.repair') }}</th>" not in health
    assert 'class="repair-cell"' not in health
    assert "startRepair(row.table)" not in health
    assert "repairing[row.table]" not in health
    assert 'colspan="12"' in health
    assert 'colspan="13"' not in health
    assert ".repair-cell" not in css
    assert ".repair-btn" not in css


def test_db_health_bulk_repair_api_starts_only_requested_repairable_tables(monkeypatch):
    from web.api.app import create_app
    from web.api.routes import system as system_routes

    monkeypatch.setattr("web.api.auth.get_api_key", lambda: "")
    monkeypatch.setattr(system_routes, "_repairable_tables", lambda: {"macro_gdp", "stock_limit_list"})
    started: list[str] = []

    def fake_start(table: str) -> dict:
        started.append(table)
        return {"status": "started", "job_id": f"job-{table}", "table": table}

    monkeypatch.setattr(system_routes, "start_repair_job", fake_start)

    res = TestClient(create_app()).post(
        "/api/system/db-health/repair",
        json={"tables": ["macro_gdp", "not_repairable", "stock_limit_list"]},
    )

    assert res.status_code == 200
    payload = res.json()
    assert payload["status"] == "started"
    assert payload["total"] == 3
    assert payload["started"] == 2
    assert started == ["macro_gdp", "stock_limit_list"]
    assert [job["table"] for job in payload["jobs"]] == ["macro_gdp", "not_repairable", "stock_limit_list"]
    assert payload["jobs"][1]["status"] == "skipped"
    assert payload["jobs"][1]["message"] == "Not a repairable table"


def test_data_sources_capabilities_api_reads_latest_artifact(monkeypatch, tmp_path):
    import json
    from data.storage.datahub import get_datahub, reset_datahub
    from web.api.app import create_app

    monkeypatch.setattr("web.api.auth.get_api_key", lambda: "")
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "var"))
    reset_datahub()

    artifact = get_datahub().artifact_path("data-sources", "latest.json")
    artifact.write_text(
        json.dumps(
            {
                "status": "ok",
                "generated_at": "2026-06-11T08:00:00+00:00",
                "recommended_command": "astroq data sources audit --source all --discovery-depth catalog --json",
                "summary": {"source_count": 9, "capability_count": 2},
                "sources": [{"source": "akshare", "capability_count": 2}],
                "capabilities": [{"source": "akshare", "interface": "stock_zh_a_daily"}],
                "diff": {"summary": {"capability_unmapped_count": 1}},
            }
        ),
        encoding="utf-8",
    )

    res = TestClient(create_app()).get("/api/data-sources/capabilities")

    assert res.status_code == 200
    payload = res.json()
    assert payload["status"] == "ok"
    assert payload["latest"]["artifact_path"].endswith("var/artifacts/data-sources/latest.json")
    assert payload["summary"]["artifact_age_seconds"] is not None
    assert payload["sources"][0]["source"] == "akshare"
    assert payload["diff"]["summary"]["capability_unmapped_count"] == 1
    reset_datahub()


def test_strategy_evidence_api_lists_catalog_gaps(monkeypatch):
    from web.api.app import create_app

    monkeypatch.setattr("web.api.auth.get_api_key", lambda: "")

    res = TestClient(create_app()).get("/api/strategies/evidence")
    assert res.status_code == 200
    payload = res.json()
    by_strategy = {item["strategy"]: item for item in payload["items"]}

    assert payload["total"] == len(payload["items"])
    assert "trend_following" in by_strategy
    assert "exists" in by_strategy["trend_following"]
    assert "promotion_decision" in by_strategy["trend_following"]


def test_stock_list_route_is_not_shadowed(monkeypatch):
    from web.api.app import create_app

    monkeypatch.setattr("web.api.auth.get_api_key", lambda: "")

    res = TestClient(create_app()).get("/api/stocks?limit=5")
    assert res.status_code == 200
    data = res.json()
    assert "stocks" in data
    assert "total" in data
    assert data["limit"] == 5
    assert data["total"] >= len(data["stocks"])
    if data["stocks"]:
        row = data["stocks"][0]
        for key in ("symbol", "name", "industry", "price", "change_pct", "pe_ttm", "pb", "buffett_score", "signal_score"):
            assert key in row


def test_system_artifact_services_use_shared_artifact_reader():
    from web.api.services import system_ast, system_lifecycle, system_tests

    assert "_read_json" not in system_ast.__dict__
    assert "_read_json" not in system_tests.__dict__
    assert "_read_json" not in system_lifecycle.__dict__
    assert "_artifact_age_seconds" not in system_ast.__dict__
    assert "_artifact_age_seconds" not in system_tests.__dict__
    assert "_artifact_age_seconds" not in system_lifecycle.__dict__


def test_macro_gdp_tushare_normalizes_quarter_to_date():
    from data.ingestion.fetchers.macro import MacroFetcher, derive_macro_factors

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


def test_macro_money_supply_normalizes_chinese_month_to_date():
    from data.ingestion.fetchers.macro import MacroFetcher

    raw = pd.DataFrame({
        "月份": ["2026年04月份", "2026年03月份"],
        "货币和准货币(M2)-数量(亿元)": [3530425.21, 3492159.91],
        "货币和准货币(M2)-同比增长": [8.6, 9.0],
        "货币(M1)-数量(亿元)": [1145833.73, 1159258.82],
        "货币(M1)-同比增长": [5.0, 5.9],
        "流通中的现金(M0)-数量(亿元)": [147477.38, 151436.41],
        "流通中的现金(M0)-同比增长": [12.2, 14.1],
    })

    df = MacroFetcher()._normalize("money_supply", raw, source="akshare")

    assert df["date"].tolist() == [pd.Timestamp("2026-04-01"), pd.Timestamp("2026-03-01")]
    assert df["M2_yoy"].tolist() == [8.6, 9.0]


def test_db_health_scans_new_registry_dimensions(tmp_path, monkeypatch):
    from data.storage.datahub import DataHub, reset_datahub

    store = tmp_path / "store"
    cache = tmp_path / "cache"
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
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
    from data.storage.datahub import DataHub

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


def test_llm_usage_normalizes_provider_response_usage_with_configured_pricing():
    from data.llm.usage import normalize_llm_usage

    row = normalize_llm_usage(
        "deepseek",
        "deepseek-v4-pro",
        {
            "prompt_cache_hit_tokens": 1000,
            "prompt_cache_miss_tokens": 2000,
            "completion_tokens": 3000,
            "total_tokens": 6000,
        },
        source="unit",
        created_at="2026-06-02T12:00:00+00:00",
    )

    assert row["utc_date"] == "2026-06-02"
    assert row["provider"] == "deepseek"
    assert row["pricing_model"] == "deepseek-v4-pro"
    assert row["usage_source"] == "api_response"
    assert row["usage_schema"] == "openai_cache"
    assert row["input_cache_hit"] == 1000
    assert row["input_cache_miss"] == 2000
    assert row["output_tokens"] == 3000
    assert row["total_tokens"] == 6000
    assert row["estimated_cost_usd"] == round((1000 * 0.003625 + 2000 * 0.435 + 3000 * 0.87) / 1_000_000, 9)
    assert row["estimated_cost_cny"] > row["estimated_cost_usd"]


def test_llm_factor_hypothesis_runtime_resolves_from_use_case_config():
    from data.llm.usage import resolve_llm_use_case

    runtime = resolve_llm_use_case("factor_hypothesis")

    assert runtime["provider"] == "mimo"
    assert runtime["model"] == "mimo-v2.5-pro"
    assert runtime["base_url"] == "https://token-plan-cn.xiaomimimo.com/v1"
    assert runtime["credential_env"] == "MIMO_API_KEY"
    assert "api_key_env" not in runtime


def test_llm_runtime_resolves_custom_openai_compatible_provider(monkeypatch):
    import data.llm.usage as usage

    monkeypatch.setattr(
        usage,
        "get_settings",
        lambda: {
            "llm": {
                "default_provider": "qwen",
                "use_cases": {"agent_planning": {"provider": "qwen", "model": "qwen-plus"}},
                "providers": {
                    "qwen": {
                        "enabled": True,
                        "label": "Qwen",
                        "protocol": "openai_compatible",
                        "api_key_env": "DASHSCOPE_API_KEY",
                        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                        "default_model": "qwen-plus",
                        "request": {
                            "chat_path": "/chat/completions",
                            "response_format_json": False,
                            "temperature": 0.2,
                            "timeout_seconds": 12,
                        },
                        "pricing": {"models": {"qwen-plus": {"input": 0.2, "output": 0.6}}},
                    }
                },
            }
        },
    )

    runtime = usage.resolve_llm_use_case("agent_planning")

    assert runtime["provider"] == "qwen"
    assert runtime["model"] == "qwen-plus"
    assert runtime["configured"] is True
    assert runtime["enabled"] is True
    assert runtime["protocol"] == "openai_compatible"
    assert runtime["base_url"] == "https://dashscope.aliyuncs.com/compatible-mode/v1"
    assert runtime["credential_env"] == "DASHSCOPE_API_KEY"
    assert runtime["chat_path"] == "/chat/completions"
    assert runtime["response_format_json"] is False
    assert runtime["temperature"] == 0.2
    assert runtime["timeout_seconds"] == 12.0
    assert runtime["block_reason"] == ""


def test_llm_use_case_request_overrides_provider_request_without_inheriting_extra_body(monkeypatch):
    import data.llm.usage as usage

    monkeypatch.setattr(
        usage,
        "get_settings",
        lambda: {
            "llm": {
                "default_provider": "mimo",
                "use_cases": {
                    "agent_planning": {"provider": "mimo", "model": "mimo-v2.5-pro"},
                    "agent_routing": {
                        "provider": "mimo",
                        "model": "mimo-v2.5-pro",
                        "request": {
                            "chat_path": "/chat/completions",
                            "response_format_json": True,
                            "temperature": 0.0,
                            "timeout_seconds": 6,
                            "extra_body": {"max_completion_tokens": 512},
                        },
                    },
                },
                "providers": {
                    "mimo": {
                        "enabled": True,
                        "label": "Mimo",
                        "protocol": "openai_compatible",
                        "api_key_env": "MIMO_API_KEY",
                        "base_url": "https://token-plan-cn.xiaomimimo.com/v1",
                        "default_model": "mimo-v2.5-pro",
                        "request": {
                            "chat_path": "/chat/completions",
                            "response_format_json": True,
                            "temperature": 0.1,
                            "reasoning_level": "max",
                            "reasoning_provider_parameter": "extra_body.thinking.type",
                            "reasoning_provider_value": "enabled",
                            "context_window_tokens": 1048576,
                            "timeout_seconds": 20,
                            "extra_body": {
                                "max_completion_tokens": 1200,
                                "thinking": {"type": "enabled"},
                            },
                        },
                    }
                },
            }
        },
    )

    planning = usage.resolve_llm_use_case("agent_planning")
    routing = usage.resolve_llm_use_case("agent_routing")

    assert planning["provider"] == "mimo"
    assert planning["temperature"] == 0.1
    assert planning["timeout_seconds"] == 20.0
    assert planning["reasoning_level"] == "max"
    assert planning["extra_body"]["thinking"] == {"type": "enabled"}
    assert routing["provider"] == "mimo"
    assert routing["model"] == "mimo-v2.5-pro"
    assert routing["temperature"] == 0.0
    assert routing["timeout_seconds"] == 6.0
    assert routing["reasoning_level"] == ""
    assert routing["reasoning_provider_parameter"] == ""
    assert routing["context_window_tokens"] == 0
    assert routing["extra_body"] == {"max_completion_tokens": 512}


def test_global_llm_runtime_profile_overrides_controlled_use_cases(tmp_path, monkeypatch):
    import data.llm.runtime_profile as runtime_profile
    import data.llm.usage as usage

    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "runtime"))
    monkeypatch.setenv("UNIT_API_KEY", "unit-secret")
    settings = {
            "llm": {
                "default_provider": "mimo",
                "use_cases": {
                    "agent_routing": {
                        "provider": "mimo",
                        "model": "mimo-v2.5-pro",
                        "request": {"temperature": 0.0, "timeout_seconds": 6, "extra_body": {"max_completion_tokens": 512}},
                    },
                    "agent_tool_planning": {
                        "provider": "mimo",
                        "model": "mimo-v2.5-pro",
                        "request": {"temperature": 0.0, "timeout_seconds": 30, "extra_body": {"max_completion_tokens": 1024}},
                    },
                    "agent_response": {
                        "provider": "mimo",
                        "model": "mimo-v2.5-pro",
                        "request": {
                            "temperature": 0.1,
                            "timeout_seconds": 120,
                            "context_window_tokens": 1048576,
                            "reasoning_level": "max",
                            "reasoning_provider_parameter": "extra_body.thinking.type",
                            "reasoning_provider_value": "enabled",
                            "extra_body": {"max_completion_tokens": 4096, "thinking": {"type": "enabled"}},
                        },
                    },
                    "factor_hypothesis": {"provider": "mimo", "model": "mimo-v2.5-pro"},
                },
                "providers": {
                    "mimo": {
                        "enabled": True,
                        "label": "Mimo",
                        "protocol": "openai_compatible",
                        "api_key_env": "MIMO_API_KEY",
                        "base_url": "https://token-plan-cn.xiaomimimo.com/v1",
                        "default_model": "mimo-v2.5-pro",
                        "request": {"temperature": 0.1, "timeout_seconds": 20},
                    },
                    "unit": {
                        "enabled": True,
                        "label": "Unit",
                        "protocol": "openai_compatible",
                        "api_key_env": "UNIT_API_KEY",
                        "base_url": "https://unit.example/v1",
                        "default_model": "unit-large",
                        "request": {
                            "temperature": 0.3,
                            "timeout_seconds": 18,
                            "context_window_tokens": 32000,
                            "reasoning_level": "max",
                            "reasoning_provider_parameter": "extra_body.thinking.type",
                            "reasoning_provider_value": "enabled",
                            "extra_body": {"thinking": {"type": "enabled"}},
                        },
                        "reasoning_modes": {
                            "max": {
                                "label": "Max",
                                "request": {
                                    "reasoning_level": "max",
                                    "reasoning_provider_parameter": "extra_body.thinking.type",
                                    "reasoning_provider_value": "enabled",
                                    "extra_body": {"thinking": {"type": "enabled"}},
                                },
                            },
                            "off": {
                                "label": "Off",
                                "request": {
                                    "reasoning_level": "off",
                                    "reasoning_provider_parameter": "extra_body.thinking.type",
                                    "reasoning_provider_value": "disabled",
                                    "extra_body": {"thinking": {"type": "disabled"}},
                                },
                            },
                        },
                        "pricing": {"models": {"unit-large": {"input": 1, "output": 2}}},
                    },
                },
            }
        }
    monkeypatch.setattr(usage, "get_settings", lambda: settings)
    monkeypatch.setattr(runtime_profile, "get_settings", lambda: settings)

    runtime_profile.save_active_profile(provider="unit", model="unit-large", reasoning_mode="off")

    routing = usage.resolve_llm_use_case("agent_routing")
    planning = usage.resolve_llm_use_case("agent_tool_planning")
    response = usage.resolve_llm_use_case("agent_response")
    factor = usage.resolve_llm_use_case("factor_hypothesis")

    assert {routing["provider"], planning["provider"], response["provider"], factor["provider"]} == {"unit"}
    assert {routing["model"], planning["model"], response["model"], factor["model"]} == {"unit-large"}
    assert routing["temperature"] == 0.0
    assert routing["timeout_seconds"] == 6.0
    assert routing["extra_body"]["max_completion_tokens"] == 512
    assert routing["extra_body"]["thinking"] == {"type": "disabled"}
    assert response["timeout_seconds"] == 120.0
    assert response["context_window_tokens"] == 1048576
    assert response["reasoning_level"] == "off"
    assert response["extra_body"]["thinking"] == {"type": "disabled"}


def test_llm_runtime_unknown_provider_fails_closed_without_default_fallback(monkeypatch):
    import data.llm.usage as usage

    monkeypatch.setattr(
        usage,
        "get_settings",
        lambda: {
            "llm": {
                "default_provider": "deepseek",
                "use_cases": {"agent_planning": {"provider": "missing-provider", "model": "missing-model"}},
                "providers": {
                    "deepseek": {
                        "enabled": True,
                        "api_key_env": "DEEPSEEK_API_KEY",
                        "base_url": "https://api.deepseek.com/v1",
                        "default_model": "deepseek-v4-pro",
                    }
                },
            }
        },
    )

    runtime = usage.resolve_llm_use_case("agent_planning")

    assert runtime["provider"] == "missing-provider"
    assert runtime["model"] == "missing-model"
    assert runtime["configured"] is False
    assert runtime["enabled"] is False
    assert runtime["base_url"] == ""
    assert runtime["credential_env"] == ""
    assert runtime["block_reason"] == "provider_not_configured"


def test_llm_usage_supports_total_token_and_request_pricing(monkeypatch):
    import data.llm.usage as usage

    monkeypatch.setattr(
        usage,
        "get_settings",
        lambda: {
            "llm": {
                "providers": {
                    "unit": {
                        "enabled": True,
                        "label": "Unit",
                        "pricing": {
                            "usd_cny": 7.0,
                            "models": {"unit-total": {"total": 1.5, "request": 0.01}},
                        },
                    }
                }
            }
        },
    )

    row = usage.normalize_llm_usage(
        "unit",
        "unit-total",
        {"total_tokens": 2000},
        source="unit",
        created_at="2026-06-02T12:00:00+00:00",
    )

    assert row["pricing_model"] == "unit-total"
    assert row["pricing_status"] == "ok"
    assert row["estimated_cost_usd"] == round((2000 * 1.5 / 1_000_000) + 0.01, 9)
    assert row["estimated_cost_cny"] == round(row["estimated_cost_usd"] * 7.0, 9)


def test_llm_usage_marks_missing_pricing_without_deepseek_fallback(monkeypatch):
    import data.llm.usage as usage

    monkeypatch.setattr(
        usage,
        "get_settings",
        lambda: {
            "llm": {
                "providers": {
                    "qwen": {
                        "enabled": True,
                        "label": "Qwen",
                        "api_key_env": "DASHSCOPE_API_KEY",
                        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                        "default_model": "qwen-plus",
                    }
                }
            }
        },
    )

    row = usage.normalize_llm_usage(
        "qwen",
        "qwen-plus",
        {"prompt_tokens": 1000, "completion_tokens": 500, "total_tokens": 1500},
        source="unit",
        created_at="2026-06-02T12:00:00+00:00",
    )

    assert row["provider"] == "qwen"
    assert row["model"] == "qwen-plus"
    assert row["pricing_model"] == ""
    assert row["pricing_status"] == "missing_provider_pricing"
    assert row["estimated_cost_usd"] == 0.0
    assert row["estimated_cost_cny"] == 0.0
    assert row["pricing_source"] == ""


def test_llm_provider_balance_reports_unknown_provider_without_default_fallback(monkeypatch):
    import data.llm.usage as usage

    monkeypatch.setattr(usage, "get_settings", lambda: {"llm": {"providers": {}}})

    balances = usage.fetch_provider_balances("missing-provider")

    assert balances["missing-provider"]["status"] == "unknown"
    assert balances["missing-provider"]["message"] == "provider not configured"


def test_llm_usage_payload_combines_provider_balance_and_project_ledger(monkeypatch):
    import web.api.services.system_monitor as monitor

    monkeypatch.setattr(
        monitor,
        "fetch_provider_balances",
        lambda provider=None: {
            provider or "deepseek": {
                "provider": provider or "deepseek",
                "label": "DeepSeek",
                "status": "ok",
                "is_available": True,
                "balance_infos": [{"currency": "CNY", "total_balance": "88.00", "granted_balance": "8.00", "topped_up_balance": "80.00"}],
            }
        },
    )
    monkeypatch.setattr(
        monitor,
        "summarize_llm_project_usage",
        lambda days=30, provider=None: {
            "daily": [
                {
                    "utc_date": "2026-06-02",
                    "provider": provider or "deepseek",
                    "model": "deepseek-v4-pro",
                    "input_cache_hit": 1000,
                    "input_cache_miss": 2000,
                    "output_tokens": 3000,
                    "total_tokens": 6000,
                    "requests": 1,
                    "estimated_cost_usd": 0.0009,
                    "estimated_cost_cny": 0.0065,
                    "usage_source": "api_response",
                }
            ],
            "providers": [provider or "deepseek"],
            "models": ["deepseek-v4-pro"],
            "dates": ["2026-06-02"],
            "totals": {"tokens": 6000, "requests": 1, "estimated_cost_usd": 0.0009, "estimated_cost_cny": 0.0065},
            "pricing_status": "ok",
            "unpriced_rows": 0,
            "unpriced_reasons": [],
            "status": "ok",
        },
    )

    payload = monitor.llm_usage_payload(provider="deepseek")

    assert payload["status"] == "ok"
    assert payload["source"] == "provider_balance_api+project_usage_ledger"
    assert payload["provider"] == "deepseek"
    assert payload["providers"] == ["deepseek"]
    assert payload["balance"]["is_available"] is True
    assert payload["usage"]["totals"]["tokens"] == 6000
    assert payload["usage"]["pricing_status"] == "ok"
    assert payload["data"][0]["usage_source"] == "api_response"


def test_monitor_is_read_only_but_keeps_system_status_cards():
    monitor = Path("web/frontend/src/views/ActivityMonitor.vue").read_text()
    monitor_logic = Path("web/frontend/src/view-models/useActivityMonitor.ts").read_text()

    assert "api.saveSettings" not in monitor
    assert "saveWithConfirm" not in monitor
    assert "API HEALTH" in monitor
    assert "CRON JOBS" in monitor
    assert "RESOURCE HISTORY" in monitor
    assert "TOP PROCESSES" in monitor
    assert "Telegram" in monitor
    assert "api.apiHealth()" in monitor_logic
    assert "api.cronJobs()" in monitor_logic
    assert "activity.unpricedUsage" in monitor
    assert "pricingStatus" in monitor_logic
    assert "unpricedRows" in monitor_logic
    assert "serviceStatus" not in monitor


def test_legacy_service_status_route_is_removed(monkeypatch):
    from web.api.app import create_app

    monkeypatch.setattr("web.api.auth.get_api_key", lambda: "")

    res = TestClient(create_app()).get("/api/system/service-status")

    assert res.status_code == 404


def test_system_tests_design_returns_no_artifact_without_design_artifact(monkeypatch, tmp_path):
    from data.storage.datahub import reset_datahub
    from web.api.app import create_app

    monkeypatch.setattr("web.api.auth.get_api_key", lambda: "")
    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("API must not run pytest")))
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "var"))
    reset_datahub()

    res = TestClient(create_app()).get("/api/system/tests/design")

    assert res.status_code == 200
    payload = res.json()
    assert payload["status"] == "no_artifact"
    assert payload["latest"] is None
    assert payload["recommended_command"] == "astroq test design --json"
    assert payload["summary"]["test_count"] == 0
    assert payload["cases"] == []
    reset_datahub()


def test_system_tests_design_reads_latest_artifact(monkeypatch, tmp_path):
    import json
    from data.storage.datahub import get_datahub, reset_datahub
    from web.api.app import create_app

    monkeypatch.setattr("web.api.auth.get_api_key", lambda: "")
    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("API must not run pytest")))
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "var"))
    reset_datahub()

    artifact_dir = get_datahub().artifact_dir("tests") / "design"
    latest = {
        "status": "ok",
        "generated_at": "2026-06-07T10:00:00Z",
        "recommended_command": "astroq test design --json",
        "summary": {
            "test_count": 1,
            "file_count": 1,
            "target_count": 1,
            "spec_count": 1,
            "risk_count": 1,
            "risk_covered": 1,
            "risk_coverage_rate": 1.0,
            "target_link_rate": 1.0,
            "spec_link_rate": 1.0,
            "smell_count": 1,
            "severity_counts": {"P2": 1},
            "design_score": 97,
            "truncated": False,
        },
        "matrix": {"kinds": ["unit", "contract"], "risks": [{"key": "api_contract", "counts": {"unit": 0, "contract": 1}, "total": 1}]},
        "graph": {"nodes": [{"id": "risk:api_contract", "label": "api_contract", "kind": "risk"}], "links": []},
        "cases": [{"nodeid": "tests/test_api.py::test_contract", "kind": "contract", "risks": ["api_contract"], "target_modules": ["web.api"], "specs": ["docs/specs/05-web-platform.md"], "fixtures": [], "assert_count": 1, "mock_count": 0, "smells": []}],
        "smells": [{"id": "no_spec:unit", "severity": "P2", "kind": "no_spec", "title": "unit", "subject": "unit", "path": "tests/test_api.py", "evidence": {}, "recommendation": "unit"}],
    }
    artifact_dir.mkdir(parents=True, exist_ok=True)
    (artifact_dir / "latest.json").write_text(json.dumps(latest), encoding="utf-8")

    client = TestClient(create_app())
    res = client.get("/api/system/tests/design")

    assert res.status_code == 200
    payload = res.json()
    assert payload["status"] == "ok"
    assert payload["latest"]["generated_at"] == "2026-06-07T10:00:00Z"
    assert payload["summary"]["design_score"] == 97
    assert payload["summary"]["artifact_age_seconds"] is not None
    assert payload["matrix"]["risks"][0]["key"] == "api_contract"
    assert payload["cases"][0]["target_modules"] == ["web.api"]
    assert payload["smells"][0]["severity"] == "P2"
    reset_datahub()


def test_legacy_system_tests_endpoints_are_removed(monkeypatch):
    from web.api.app import create_app

    monkeypatch.setattr("web.api.auth.get_api_key", lambda: "")
    client = TestClient(create_app())

    prefix = "/api/system/tests/"
    assert client.get(prefix + "summary").status_code == 404
    assert client.get(prefix + "domains").status_code == 404
    assert client.get(prefix + "runs").status_code == 404


def test_cron_jobs_payload_coerces_nullable_status_fields(monkeypatch, tmp_path):
    import json
    import web.api.services.system_integrations as integrations

    cron_root = tmp_path / ".hermes" / "cron"
    cron_root.mkdir(parents=True)
    (cron_root / "jobs.json").write_text(
        json.dumps({
            "jobs": [
                {
                    "name": "nullable",
                    "schedule_display": "daily",
                    "last_run_at": None,
                    "last_status": None,
                    "next_run_at": None,
                    "enabled": True,
                }
            ]
        }),
        encoding="utf-8",
    )

    monkeypatch.setattr(integrations.Path, "home", lambda: tmp_path)

    payload = integrations.cron_jobs_payload()

    assert payload["jobs"][0]["last_run"] == ""
    assert payload["jobs"][0]["last_status"] == ""
    assert payload["jobs"][0]["next_run"] == ""


def test_settings_cancel_reverts_pending_toggle():
    settings = Path("web/frontend/src/views/Settings.vue").read_text()

    assert "confirmSnapshot" in settings
    assert "cancelConfirm" in settings
    assert "restoreConfig" in settings
    assert "@click.self=\"cancelConfirm\"" in settings


def test_config_center_preserves_dotted_section_paths():
    config_center = Path("web/frontend/src/views/ConfigCenter.vue").read_text()
    config_center_logic = Path("web/frontend/src/view-models/useConfigCenter.ts").read_text()
    api_client = Path("web/frontend/src/api/client.ts").read_text()
    settings_api = Path("web/frontend/src/api/modules/settings.ts").read_text()

    assert "function getNestedValue" in config_center_logic
    assert "function setNestedValue" in config_center_logic
    assert "function isSafePathPart" in config_center_logic
    assert '"__proto__"' in config_center_logic
    assert '"prototype"' in config_center_logic
    assert '"constructor"' in config_center_logic
    assert "setNestedValue(config, sectionKey" in config_center_logic
    assert "config[activeSection.value]" not in config_center_logic
    assert "function patch<T>" in api_client
    assert "saveSettingsSection" in settings_api
    assert "patch<Record<string, any>>" in settings_api


def test_frontend_auth_token_is_not_persisted_in_browser_storage():
    api_client = Path("web/frontend/src/api/client.ts").read_text()
    settings_logic = Path("web/frontend/src/view-models/useSettingsView.ts").read_text()

    assert "setAuthToken" in api_client
    assert "let bearerToken" in api_client
    assert "quant_api_key" not in api_client
    assert "quant_api_key" not in settings_logic
    assert 'localStorage.setItem("quant_api_key"' not in settings_logic
    assert 'localStorage.getItem("quant_api_key"' not in settings_logic
    assert 'localStorage.removeItem("quant_api_key"' not in api_client


def test_config_center_uses_grouped_expandable_settings_model():
    config_center = Path("web/frontend/src/views/ConfigCenter.vue").read_text()
    config_center_logic = Path("web/frontend/src/view-models/useConfigCenter.ts").read_text()
    css = Path("web/frontend/src/styles/views/config-center.css").read_text()

    assert "activeGroup" in config_center_logic
    assert "groups.value = schemaData.groups" in config_center_logic
    assert "groupedSections" in config_center_logic
    assert "sectionHasChanges(section.key)" in config_center
    assert 'v-for="group in groups"' in config_center
    assert 'v-for="subgroup in groupedSections"' in config_center
    assert 'v-for="section in subgroup.sections"' in config_center
    assert 'v-for="section in schema"' not in config_center
    assert ".config-subgroup" in css
    assert ".section-panel" in css
    assert ".field-switch" in css


def test_config_center_strategy_management_has_secondary_navigation():
    config_center = Path("web/frontend/src/views/ConfigCenter.vue").read_text()
    config_center_logic = Path("web/frontend/src/view-models/useConfigCenter.ts").read_text()
    css = Path("web/frontend/src/styles/views/config-center.css").read_text()

    assert "data-strategy-subnav" in config_center
    assert "strategyNavItems" in config_center
    assert "strategy-status-dot" in config_center
    assert "strategyStatusLabel(item)" in config_center
    assert "jumpToSubgroup(item.key)" in config_center
    assert "sectionStrategyName" in config_center_logic
    assert "strategy:${strategyName}" in config_center_logic
    assert "strategies.${group.strategyName}.enabled" in config_center_logic
    assert "strategyNavItems = computed" in config_center_logic
    assert ".config-body.has-strategy-nav" in css
    assert ".strategy-subnav" in css
    assert ".strategy-status-dot.enabled" in css
    assert ".strategy-status-dot.disabled" in css


def test_frontend_router_does_not_keep_legacy_redirect_routes():
    router = Path("web/frontend/src/router/index.ts").read_text()

    assert "redirectWithTab" not in router
    for path in ("/strategies", "/signals", "/backtest", "/sectors", "/monitor", "/settings", "/db-health"):
        assert f'path: "{path}"' not in router
    assert 'path: "/pipeline"' in router
    assert 'path: "/stocks/:code"' in router
    assert 'path: "/stocks"' not in router


def test_system_graph_tab_uses_codegraph_surface():
    hub = Path("web/frontend/src/views/SystemHub.vue").read_text(encoding="utf-8")
    system_api = Path("web/frontend/src/api/modules/system.ts").read_text(encoding="utf-8")
    system_types = Path("web/frontend/src/api/types/system.ts").read_text(encoding="utf-8")
    zh_modules = Path("web/frontend/src/i18n/messages/zh-CN/modules.ts").read_text(encoding="utf-8")
    en_modules = Path("web/frontend/src/i18n/messages/en-US/modules.ts").read_text(encoding="utf-8")

    assert "CodeGraph" in hub
    assert '{ key: "codegraph" }' in hub
    assert "codeGraphStatus" in system_api
    assert "codeGraphGraph" in system_api
    assert "CodeGraphStatusResponse" in system_types
    assert "codegraph" in zh_modules
    assert "代码图谱" in zh_modules
    assert "codegraph" in en_modules
    assert "CodeGraph" in en_modules


def test_system_ast_intelligence_tab_and_api_contract():
    hub = Path("web/frontend/src/views/SystemHub.vue").read_text(encoding="utf-8")
    system_api = Path("web/frontend/src/api/modules/system.ts").read_text(encoding="utf-8")
    system_types = Path("web/frontend/src/api/types/system.ts").read_text(encoding="utf-8")
    zh_modules = Path("web/frontend/src/i18n/messages/zh-CN/modules.ts").read_text(encoding="utf-8")
    en_modules = Path("web/frontend/src/i18n/messages/en-US/modules.ts").read_text(encoding="utf-8")

    assert "AstIntelligence" in hub
    assert '{ key: "ast" }' in hub
    assert "astIntelligence" in system_api
    assert "/api/system/ast-intelligence" in system_api
    assert "AstIntelligenceResponse" in system_types
    assert "AST 检测" in zh_modules
    assert "AST Intelligence" in en_modules


def test_datahub_sources_tab_and_api_contract():
    hub = Path("web/frontend/src/views/DataHub.vue").read_text(encoding="utf-8")
    data_sources_view = Path("web/frontend/src/views/DataSources.vue").read_text(encoding="utf-8")
    api_index = Path("web/frontend/src/api/index.ts").read_text(encoding="utf-8")
    data_sources_api = Path("web/frontend/src/api/modules/dataSources.ts").read_text(encoding="utf-8")
    types = Path("web/frontend/src/api/types.ts").read_text(encoding="utf-8")
    data_source_types = Path("web/frontend/src/api/types/dataSources.ts").read_text(encoding="utf-8")
    zh_modules = Path("web/frontend/src/i18n/messages/zh-CN/modules.ts").read_text(encoding="utf-8")
    en_modules = Path("web/frontend/src/i18n/messages/en-US/modules.ts").read_text(encoding="utf-8")
    zh_index = Path("web/frontend/src/i18n/messages/zh-CN/index.ts").read_text(encoding="utf-8")
    en_index = Path("web/frontend/src/i18n/messages/en-US/index.ts").read_text(encoding="utf-8")

    assert "DataSources" in hub
    assert '{ key: "sources" }' in hub
    assert "dataSourcesApi" in api_index
    assert "dataSourceCapabilities" in data_sources_api
    assert "/api/data-sources/capabilities" in data_sources_api
    assert "types/dataSources" in types
    assert "DataSourceCapabilityResponse" in data_source_types
    assert "discovery_status" in data_source_types
    assert "discovery_scope" in data_source_types
    assert "probe_status" in data_source_types
    assert "probe_block_reason" in data_source_types
    assert "probe_contract_id" in data_source_types
    assert "sample_probe" in data_source_types
    assert "discoveryFilter" in data_sources_view
    assert "probeFilter" in data_sources_view
    assert "blockReasonFilter" in data_sources_view
    assert "probeDetail" in data_sources_view
    assert 'class="capability-filter-bar"' in data_sources_view
    assert 'class="sources-filters glass-card"' not in data_sources_view
    assert "currentPage" in data_sources_view
    assert "pageSize" in data_sources_view
    assert "pagedCapabilities" in data_sources_view
    assert "paginationRange" in data_sources_view
    assert "slice(0, 300)" not in data_sources_view
    assert "dataSources" in zh_index
    assert "dataSources" in en_index
    assert "数据源能力" in zh_modules
    assert "Source Capabilities" in en_modules
    assert "auditSources" not in data_sources_view
    assert "Web scan" not in data_sources_view


def test_market_view_surfaces_regime_stability_state():
    market = Path("web/frontend/src/views/Market.vue").read_text(encoding="utf-8")

    assert "regimeStabilityState" in market
    assert "regimeStatusCards" in market
    assert "raw_value" in market
    assert "pending_count" in market
    assert "min_dwell" in market
    assert "Confirmed" in market
    assert "Pending" in market
    assert "{ key: \"dwell\", label: \"Dwell\", value: regimeStabilityState.value.dwell }" in market
    assert "{{ item.value }}" in market
    assert "Idle" in market
    assert "stability.min_dwell ?? 1" not in market
    assert "Regime Score" not in market
    assert "regime-score-line span" not in market
    assert "align-items: center;" in market
    assert "regime-stability-strip" not in market
    assert "regime-status-card" in market
    assert "regime-status-row" not in market
    assert "regime-status-card is-inline" in market
    assert "min-height: 28px;" in market
    assert "padding: 4px 6px;" in market


    score_block = market.split(".regime-score-line {", 1)[1].split("}", 1)[0]
    assert "border:" not in score_block
    assert "background:" not in score_block
    assert "padding:" not in score_block
    assert "justify-content: center;" in score_block

    gauge_block = market.split("const regimeGaugeMetrics = computed(() => [", 1)[1].split("]);", 1)[0]
    assert 'key: "risk"' in gauge_block
    assert 'key: "breadth"' in gauge_block
    assert 'key: "trend"' in gauge_block
    assert 'key: "above-ma20"' in gauge_block
    assert 'key: "liquidity"' not in gauge_block
    assert 'key: "capacity"' not in gauge_block


def test_strategy_lab_exposes_catalog_and_candidate_language():
    strategies = Path("web/frontend/src/views/Strategies.vue").read_text(encoding="utf-8")
    api = Path("web/frontend/src/api/modules/strategy.ts").read_text(encoding="utf-8")

    assert "strategyCatalog" in api
    assert "strategyEvaluation" in api
    assert "策略目录" in strategies
    assert "候选策略" in strategies
    assert "生命周期" in strategies
    assert "生产隔离" in strategies


def test_market_macro_panel_supports_six_indicator_layout():
    market = Path("web/frontend/src/views/Market.vue").read_text(encoding="utf-8")

    assert "GDP · PMI · CPI · LIQUIDITY · PROFIT" in market
    assert 'm.key === "m1_m2_spread"' in market
    assert 'm.key === "ppi_cpi_spread"' in market

    grid_block = market.split(".macro-grid {", 1)[1].split("}", 1)[0]
    assert "grid-template-columns: repeat(2, minmax(0, 1fr));" in grid_block

    card_block = market.split(".macro-grid article {", 1)[1].split("}", 1)[0]
    assert "min-height: 88px;" in card_block


def test_sector_radar_view_uses_sector_block_grid_as_primary_visual():
    sectors = Path("web/frontend/src/views/Sectors.vue").read_text(encoding="utf-8")
    sector_logic = Path("web/frontend/src/view-models/useSectorsView.ts").read_text(encoding="utf-8")
    sector_css = Path("web/frontend/src/styles/views/sectors.css").read_text(encoding="utf-8")
    api = "\n".join([
        Path("web/frontend/src/api/modules/sectors.ts").read_text(encoding="utf-8"),
        Path("web/frontend/src/api/types/sectors.ts").read_text(encoding="utf-8"),
    ])

    assert "sectorBlockTiles" in sectors
    assert "sector-block-grid" in sectors
    assert "sector-toolbar-metrics" in sectors
    assert "强势行业 5日" in sectors
    assert "信号分化度" in sectors
    assert "资金集中度" in sectors
    assert "{{ capitalConcentration }}" in sectors
    assert "信号集中度" not in sectors
    assert "signal_dispersion" in api
    assert "signal_concentration" not in api
    assert "资金最大行业" not in sectors
    assert "资金最大企业" not in sectors
    assert "sector-insight-card" not in sectors
    assert "capitalLeader" not in sectors
    assert "stat-row" not in sectors
    assert "stat-chip" not in sectors
    assert "industry-block" in sectors
    assert '<button\n            v-for="tile in sectorBlockTiles"' in sectors
    assert "industry-block-button" not in sectors
    assert "stock-block" not in sectors
    assert "sectorBlockSpan" in sectors
    assert "gridColumn: `span ${tile.span}`" in sector_logic
    assert "gridRow: `span ${tile.span}`" in sector_logic
    assert "stockSquareSpan" not in sector_logic
    assert "stockMosaicBlocks" not in sector_logic
    assert "openConstituent" not in sector_logic
    assert "memberStocks" not in sector_logic
    assert "sectorBlockSizeClass" not in sector_logic
    assert "splitTreemap" not in sector_logic
    assert "linear-gradient" not in sector_css
    assert "backgroundColor: tone.backgroundColor" in sector_logic
    assert "boxShadow: tone.boxShadow" in sector_logic
    assert "资金热力" in sectors
    assert "动量热力" in sectors
    assert "信号热力" in sectors
    assert "amount_5d_avg" in api
    assert "amount_share" in api
    assert "SectorConstituent" not in api
    assert "constituents" not in api
    assert "sectorStocks" not in api

    map_head = sectors.split('class="sector-map-head"', 1)[1].split('class="sector-block-grid"', 1)[0]
    assert 'class="sector-map-title-row"' in map_head
    assert 'class="block-map-meta"' in map_head
    assert map_head.index("行业资金方块图") < map_head.index('class="block-map-meta"')
    assert map_head.index('class="block-map-meta"') < map_head.index('class="block-mode-tabs"')
    assert '</div>\n        <div class="block-map-meta">' not in sectors

    block_grid_style = sector_css.split(".sector-block-grid {", 1)[1].split("}", 1)[0]
    assert "margin-top: 12px;" in block_grid_style


def test_sector_capital_blocks_prioritize_metric_then_centered_industry_name():
    sectors = Path("web/frontend/src/views/Sectors.vue").read_text(encoding="utf-8")
    sector_logic = Path("web/frontend/src/view-models/useSectorsView.ts").read_text(encoding="utf-8")
    sector_css = Path("web/frontend/src/styles/views/sectors.css").read_text(encoding="utf-8")

    block_template = sectors.split('class="industry-block"', 1)[1].split("</button>", 1)[0]
    assert 'class="industry-amount"' in block_template
    assert 'class="industry-center-stack"' in block_template
    assert 'class="industry-name"' in block_template
    assert 'class="industry-metric"' in block_template
    assert ':data-tooltip="industryTooltip(tile)"' in block_template
    assert block_template.index('class="industry-name"') < block_template.index('class="industry-metric"')
    assert 'class="industry-code"' not in block_template
    assert "tile.sector.sector_code || 'SW1'" not in block_template

    tooltip_block = sector_logic.split("function industryTooltip", 1)[1].split("function heatStyle", 1)[0]
    assert "行业代码" in tooltip_block

    name_style = sector_css.split(".industry-name {", 1)[1].split("}", 1)[0]
    assert "align-self: center;" in name_style
    assert "justify-self: center;" in name_style
    assert "text-align: center;" in name_style
    assert "font-size: var(--industry-name-size, 12px);" in name_style
    assert "sizeRatio" in sector_logic
    assert "function industryNameFontSize" in sector_logic
    assert '"--industry-name-size": industryNameFontSize(tile.sizeRatio)' in sector_logic
    assert "Math.pow(clampNumber(sizeRatio, 0, 1), 0.8)" in sector_logic
    assert "12 + visualWeight * 18" in sector_logic

    metric_style = sector_css.split(".industry-metric {", 1)[1].split("}", 1)[0]
    assert "--industry-name-size" not in metric_style
    assert "justify-self: center;" in metric_style
    assert "text-align: center;" in metric_style

    stack_style = sector_css.split(".industry-center-stack {", 1)[1].split("}", 1)[0]
    assert "align-self: center;" in stack_style
    assert "justify-self: center;" in stack_style
    assert "align-items: center;" in stack_style

    tooltip_style = sector_css.split(".industry-block::after {", 1)[1].split("}", 1)[0]
    assert "content: attr(data-tooltip);" in tooltip_style


def test_stock_search_view_defaults_to_stock_table():
    stocks = Path("web/frontend/src/views/Stocks.vue").read_text(encoding="utf-8")
    stocks_logic = Path("web/frontend/src/view-models/useStocksView.ts").read_text(encoding="utf-8")
    api = Path("web/frontend/src/api/modules/stocks.ts").read_text(encoding="utf-8")

    assert "api.stockList" in stocks_logic
    assert "onMounted(loadStockList)" in stocks_logic
    assert "stock-list-table" in stocks
    assert "defaultRows" in stocks
    assert "filteredRows" in stocks
    assert "listTotal" in stocks
    assert "stock-list-stats" in stocks
    assert "股票池概览" in stocks
    assert 'stockList: (limit = 300' in api
    assert 'get<StockListResponse>(`/api/stocks?limit=${limit}`)' in api
