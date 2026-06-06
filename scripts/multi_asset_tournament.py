#!/usr/bin/env python3
"""
Multi-Asset Tournament — 干净版
对比: stock-only vs ETF-only vs multi-asset (stock+ETF分配)
"""
import os, json
from pathlib import Path
from datetime import datetime

for k in list(os.environ.keys()):
    if k.lower() in ('http_proxy', 'https_proxy', 'all_proxy'):
        del os.environ[k]
os.environ['no_proxy'] = '*'

import pandas as pd

from data.market.symbols import CIRCLE_STOCKS
from data.ingestion.fetcher import get_stock_daily, get_index_daily
from data.market.assets.etf import ETFAsset
from data.storage.datahub import get_datahub
from backtest.momentum import (
    buy_equal_weight_selection,
    liquidate_positions,
    portfolio_value,
    run_monthly_rebalance_strategy,
    select_top_momentum,
)
from broker.exchange import AShareExchange, ETFExchange
from broker.allocator import AssetAllocator

HUB = get_datahub()

# ════════════════ config ════════════════
N_STOCKS, N_ETFS = 50, 5
START, END = "2020-01-01", "2026-04-30"
CASH = 1_000_000

# ── ETF → Price proxy mapping ──
# SHORT-TERM PROXY: 用指数/收益率构造ETF近似价格
# 长期方案: 等AKShare fund_etf_hist_em 网络恢复后，切换为真实ETF行情
#           或接入wind/tushare etf_daily (需更高积分)
ETF_PROXY = {
    # 权益 — 指数代理 (已通)
    "510050": "sh000016", "510300": "sh000300", "510500": "sh000905",
    "512100": "sh000852", "588000": "sh000688",
    # 黄金 — SGE金价代理 (SHORT-TERM)
    "518880": "gold_sge",
    # 国债 — 收益率曲线代理 (SHORT-TERM)
    "511010": "bond_yield",
    # 货币 — Shibor隔夜代理 (SHORT-TERM)
    "511880": "money_shibor",
}

N_ETFS = len(ETF_PROXY)  # use all 8

def _load_gold_proxy():
    """[SHORT-TERM] SGE黄金现货 → 518880 ETF价格 (1份≈0.01克)"""
    import akshare as ak
    df = ak.spot_golden_benchmark_sge()
    df["date"] = pd.to_datetime(df["交易时间"])
    # 518880 tracks ~0.01g per share, SGE price in CNY/g
    df["close"] = df["晚盘价"] * 0.01
    return df.set_index("date").sort_index()[["close"]]

def _load_bond_proxy():
    """[SHORT-TERM] 10Y国债收益率 → 国债ETF近似价格
    近似: 价格变化 ≈ -久期 × 收益率变化
    久期=7, 基准价格=100, 从2015年起累积"""
    import akshare as ak
    df = ak.bond_zh_us_rate()
    df["date"] = pd.to_datetime(df["日期"])
    df = df.set_index("date").sort_index()
    yld = df["中国国债收益率10年"].dropna() / 100.0  # decimal
    if len(yld) < 60:
        return None
    # 近似: daily_return = -duration * daily_yield_change
    d = 7.0  # 10Y bond duration
    rets = -d * yld.diff().fillna(0)
    price = 100.0 * (1 + rets).cumprod()
    return pd.DataFrame({"close": price}, index=yld.index)

def _load_money_proxy():
    """[SHORT-TERM] Shibor隔夜 → 货币ETF净值 (日复利)"""
    pq = HUB.macro_path("shibor")
    if not pq.exists():
        return None
    df = HUB.read_parquet(pq)
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    on = df["O/N-定价"].dropna() / 100.0  # decimal
    if len(on) < 60:
        return None
    daily = on / 365.0
    price = 100.0 * (1 + daily).cumprod()
    return pd.DataFrame({"close": price}, index=on.index)

PROXY_LOADERS = {
    "gold_sge": _load_gold_proxy,
    "bond_yield": _load_bond_proxy,
    "money_shibor": _load_money_proxy,
}

stock_ex, etf_ex = AShareExchange(), ETFExchange()
allocator = AssetAllocator()
etf_asset = ETFAsset(HUB.store_dir())

# ════════════════ load ════════════════
print("Loading data...")
stock_syms = list(CIRCLE_STOCKS)[:N_STOCKS]
prices_s = {}
for s in stock_syms:
    df = get_stock_daily(s)
    if df is not None and len(df) >= 60:
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date").sort_index()
        prices_s[s] = df["close"].dropna()

prices_e = {}
for etf in list(ETF_PROXY.keys()):
    proxy_key = ETF_PROXY[etf]
    df = None
    # Try real ETF data first
    try:
        df = etf_asset.fetch_daily(etf, "20180101")
    except Exception:
        pass

    # Fallback: proxy
    if df is None or len(df) < 60:
        if proxy_key in PROXY_LOADERS:
            try:
                df = PROXY_LOADERS[proxy_key]()
                tag = "SHORT-TERM PROXY"
            except Exception as e:
                print(f"  {etf} proxy failed: {e}")
                continue
        elif proxy_key.startswith("sh"):
            idx_df = get_index_daily(proxy_key)
            if idx_df is not None and len(idx_df) >= 60:
                idx_df["date"] = pd.to_datetime(idx_df["date"])
                idx_df = idx_df.set_index("date").sort_index()
                col = "close" if "close" in idx_df.columns else "收盘"
                df = pd.DataFrame({"close": idx_df[col] * 0.001}, index=idx_df.index)
                tag = "index proxy"
            else:
                continue
        else:
            continue

        # Check if loading succeeded and has 'close'
        if df is None or len(df) < 60 or "close" not in df.columns:
            continue

        # Normalize: ensure index sorted, close column exists
        if not isinstance(df.index, pd.DatetimeIndex):
            if "date" in df.columns:
                df["date"] = pd.to_datetime(df["date"])
                df = df.set_index("date")
        df = df.sort_index()
        if proxy_key not in ("gold_sge", "bond_yield", "money_shibor"):
            print(f"  ETF {etf} → {tag} {proxy_key}")

    if df is not None and len(df) >= 60 and "close" in df.columns:
        prices_e[etf] = df["close"].dropna()

prices_s_df = pd.DataFrame(prices_s).sort_index()
prices_e_df = pd.DataFrame(prices_e).sort_index()

# Common timeline
common = prices_s_df.index.intersection(prices_e_df.index)
mask = (common >= START) & (common <= END)
dates = common[mask]
print(f"  Stocks: {len(prices_s_df.columns)}/{N_STOCKS}, ETFs: {len(prices_e_df.columns)}/{N_ETFS}")
print(f"  Period: {dates[0].strftime('%Y-%m-%d')} → {dates[-1].strftime('%Y-%m-%d')}, {len(dates)} days")

# ════════════════ run ════════════════
print("\nRunning...")
results = {}

# Stock-only
r, t = run_monthly_rebalance_strategy(prices_s_df, dates, stock_ex, n_pos=8, cash=CASH)
results["stock_only"] = ("纯股票 动量", r, t)
print(f"  stock-only: {r:+.2f}% ({t} trades)")

# ETF-only
r, t = run_monthly_rebalance_strategy(prices_e_df, dates, etf_ex, n_pos=3, cash=CASH)
results["etf_only"] = ("纯ETF 动量", r, t)
print(f"  etf-only:   {r:+.2f}% ({t} trades)")

# Multi-asset: regime → weights → split capital
# Build regime-by-month map by replaying the production policy without look-ahead.
_bench_for_regime = get_index_daily("sh000001")
if _bench_for_regime is not None and len(_bench_for_regime) > 60:
    _bench_for_regime["date"] = pd.to_datetime(_bench_for_regime["date"])
    _bench_for_regime = _bench_for_regime.set_index("date").sort_index()
    _bench_close = _bench_for_regime["close"]
else:
    _bench_close = None

if _bench_close is not None:
    from backtest.run_all_strategies import build_production_regime_map

    _production_regime_by_month = build_production_regime_map(_bench_close)
else:
    _production_regime_by_month = {}

def _historical_regime(dt):
    """Return the production-regime replay available for this month."""
    return _production_regime_by_month.get(pd.Timestamp(dt).strftime("%Y-%m"), "sideways")

holdings = {}
cash = CASH
vals2, trades2 = [], 0
for di, dt in enumerate(dates):
    if di == 0 or dt.month != dates[di-1].month:
        try:
            rs = _historical_regime(dt)
        except Exception:
            rs = 'unknown'
        w = allocator.get_weights(rs)
        w_s, w_e = w.get("stock", 0.5), w.get("etf", 0.3)

        cash, holdings = liquidate_positions(
            holdings,
            cash,
            [(prices_s_df, stock_ex), (prices_e_df, etf_ex)],
            dt,
        )

        total = cash
        budget_s, budget_e = total * w_s, total * w_e

        # Buy stocks
        if budget_s > 10000:
            sel_s = select_top_momentum(prices_s_df, dt, 5)
            if sel_s:
                cash, holdings, new_trades = buy_equal_weight_selection(
                    holdings,
                    cash,
                    prices_s_df,
                    dt,
                    stock_ex,
                    sel_s,
                    budget_s,
                )
                trades2 += new_trades

        # Buy ETFs
        if budget_e > 10000:
            sel_e = select_top_momentum(prices_e_df, dt, 3)
            if sel_e:
                cash, holdings, new_trades = buy_equal_weight_selection(
                    holdings,
                    cash,
                    prices_e_df,
                    dt,
                    etf_ex,
                    sel_e,
                    budget_e,
                )
                trades2 += new_trades

    # NAV
    vals2.append(portfolio_value(cash, holdings, [prices_s_df, prices_e_df], dt))

ret2 = (vals2[-1] / vals2[0] - 1) * 100 if vals2[0] > 0 else 0
results["multi"] = ("二资产分配", ret2, trades2)
print(f"  multi:      {ret2:+.2f}% ({trades2} trades)")

# ════════════════ report ════════════════
print(f"\n{'='*60}")
print("🏆 Multi-Asset Tournament")
print(f"{'='*60}")
ranked = sorted(results.items(), key=lambda x: -x[1][1])
for i, (k, (label, ret, tr)) in enumerate(ranked):
    m = ["🥇", "🥈", "🥉"][i] if i < 3 else f"  {i+1}."
    print(f"  {m} {label:20s} {ret:+.2f}% ({tr} trades)")

# Save
out = Path(__file__).resolve().parent.parent / "data" / "tournament" / f"multi_asset_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
out.parent.mkdir(parents=True, exist_ok=True)
json.dump({k: {"label": v[0], "return": round(v[1], 2), "trades": v[2]} for k, v in results.items()}, open(out, "w"), indent=2)
print(f"\n→ {out}")
