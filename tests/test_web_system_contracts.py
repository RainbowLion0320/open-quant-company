import importlib
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


def test_macro_money_supply_normalizes_chinese_month_to_date():
    from data.fetchers.macro import MacroFetcher

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
    from data.datahub import DataHub, reset_datahub

    store = tmp_path / "store"
    cache = tmp_path / "cache"
    monkeypatch.setenv("ASTROLABE_STORE", str(store))
    monkeypatch.setenv("ASTROLABE_CACHE", str(cache))
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


def test_monitor_is_read_only_but_keeps_system_status_cards():
    monitor = Path("web/frontend/src/views/ActivityMonitor.vue").read_text()

    assert "api.saveSettings" not in monitor
    assert "saveWithConfirm" not in monitor
    assert "API HEALTH" in monitor
    assert "SERVICES" in monitor
    assert "CRON JOBS" in monitor
    assert "RESOURCE HISTORY" in monitor
    assert "TOP PROCESSES" in monitor
    assert "Telegram" in monitor
    assert "api.apiHealth()" in monitor
    assert "api.serviceStatus()" in monitor
    assert "api.cronJobs()" in monitor


def test_settings_cancel_reverts_pending_toggle():
    settings = Path("web/frontend/src/views/Settings.vue").read_text()

    assert "confirmSnapshot" in settings
    assert "cancelConfirm" in settings
    assert "restoreConfig" in settings
    assert "@click.self=\"cancelConfirm\"" in settings


def test_frontend_router_does_not_keep_legacy_redirect_routes():
    router = Path("web/frontend/src/router/index.ts").read_text()

    assert "redirectWithTab" not in router
    for path in ("/strategies", "/signals", "/backtest", "/sectors", "/monitor", "/settings", "/db-health", "/hindsight"):
        assert f'path: "{path}"' not in router
    assert 'path: "/stocks/:code"' in router
    assert 'path: "/stocks"' not in router


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
    api = Path("web/frontend/src/api/index.ts").read_text(encoding="utf-8")

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
    assert "gridColumn: `span ${tile.span}`" in sectors
    assert "gridRow: `span ${tile.span}`" in sectors
    assert "stockSquareSpan" not in sectors
    assert "stockMosaicBlocks" not in sectors
    assert "openConstituent" not in sectors
    assert "memberStocks" not in sectors
    assert "sectorBlockSizeClass" not in sectors
    assert "splitTreemap" not in sectors
    assert "linear-gradient" not in sectors
    assert "backgroundColor: tone.backgroundColor" in sectors
    assert "boxShadow: tone.boxShadow" in sectors
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

    block_grid_style = sectors.split(".sector-block-grid {", 1)[1].split("}", 1)[0]
    assert "margin-top: 12px;" in block_grid_style


def test_sector_capital_blocks_prioritize_metric_then_centered_industry_name():
    sectors = Path("web/frontend/src/views/Sectors.vue").read_text(encoding="utf-8")

    block_template = sectors.split('class="industry-block"', 1)[1].split("</button>", 1)[0]
    assert 'class="industry-amount"' in block_template
    assert 'class="industry-center-stack"' in block_template
    assert 'class="industry-name"' in block_template
    assert 'class="industry-metric"' in block_template
    assert ':data-tooltip="industryTooltip(tile)"' in block_template
    assert block_template.index('class="industry-name"') < block_template.index('class="industry-metric"')
    assert 'class="industry-code"' not in block_template
    assert "tile.sector.sector_code || 'SW1'" not in block_template

    tooltip_block = sectors.split("function industryTooltip", 1)[1].split("function heatStyle", 1)[0]
    assert "行业代码" in tooltip_block

    name_style = sectors.split(".industry-name {", 1)[1].split("}", 1)[0]
    assert "align-self: center;" in name_style
    assert "justify-self: center;" in name_style
    assert "text-align: center;" in name_style
    assert "font-size: var(--industry-name-size, 12px);" in name_style
    assert "sizeRatio" in sectors
    assert "function industryNameFontSize" in sectors
    assert '"--industry-name-size": industryNameFontSize(tile.sizeRatio)' in sectors
    assert "Math.pow(clampNumber(sizeRatio, 0, 1), 0.8)" in sectors
    assert "12 + visualWeight * 18" in sectors

    metric_style = sectors.split(".industry-metric {", 1)[1].split("}", 1)[0]
    assert "--industry-name-size" not in metric_style
    assert "justify-self: center;" in metric_style
    assert "text-align: center;" in metric_style

    stack_style = sectors.split(".industry-center-stack {", 1)[1].split("}", 1)[0]
    assert "align-self: center;" in stack_style
    assert "justify-self: center;" in stack_style
    assert "align-items: center;" in stack_style

    tooltip_style = sectors.split(".industry-block::after {", 1)[1].split("}", 1)[0]
    assert "content: attr(data-tooltip);" in tooltip_style
