#!/usr/bin/env python3
"""
Multi-Asset Tournament — 二资产分配 vs 单资产基准

对比:
  1. Stock-only: 100% A股 ML策略 (baseline)
  2. ETF-only: 100% ETF 动量+资金流策略
  3. Multi-asset: AssetAllocator regime驱动 stock+etf 动态分配

目的: 验证跨资产分配是否优于单资产满仓
"""
import os, sys, json, time
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

for k in list(os.environ.keys()):
    if k.lower() in ('http_proxy', 'https_proxy', 'all_proxy'):
        del os.environ[k]
os.environ['no_proxy'] = '*'

import pandas as pd
import numpy as np

from data.symbols import CIRCLE_STOCKS
from data.fetcher import get_stock_daily
from data.assets.etf import ETFAsset, ETF_UNIVERSE
from data.db import get_store_dir
from cybernetics.orchestrator import MarketRegime, detect_market_regime
from broker.exchange import AShareExchange, ETFExchange, MultiAssetExchange, OrderSide
from broker.allocator import AssetAllocator
from backtest.analytics import RiskAnalytics

# ══════════════════════════════════════════════════════════
N_STOCKS = 50
N_ETFS = 15
START, END = "2020-01-01", "2026-05-10"
CASH = 1_000_000
# ══════════════════════════════════════════════════════════

LIQUID_ETFS = [
    "510050", "510300", "510500", "512100",  # 宽基
    "512880", "512800",                         # 行业(证券/银行)
    "511010", "511260",                         # 债券
    "518880",                                   # 黄金
    "513100", "513500",                         # 跨境(QDII)
    "511880",                                   # 货币
    "515790", "588000",                         # 主题(光伏/科创)
][:N_ETFS]

store_root = get_store_dir()
etf_asset = ETFAsset(store_root)

# ── Exchanges ──
stock_ex = AShareExchange()
etf_ex = ETFExchange()
allocator = AssetAllocator()


def load_prices(symbols: list, asset_type: str = "stock") -> pd.DataFrame:
    """Load OHLCV for a list of symbols. Returns close-only price matrix."""
    closes = {}
    for sym in symbols:
        try:
            if asset_type == "stock":
                df = get_stock_daily(sym)
                if df is None or len(df) < 60:
                    continue
                df["date"] = pd.to_datetime(df["date"])
                df = df.set_index("date").sort_index()
            else:
                df = etf_asset.fetch_daily(sym, "20180101")
                if df is None or len(df) < 60:
                    continue

            close = df["close"].dropna()
            if len(close) >= 60:
                closes[sym] = close
        except Exception:
            pass

    if not closes:
        return pd.DataFrame()

    result = pd.DataFrame(closes)
    result = result.sort_index()
    mask = (result.index >= START) & (result.index <= END)
    return result.loc[mask]


def score_etf_momentum(etf_close: pd.Series, idx: int) -> float:
    """Simple ETF scoring: momentum(50%) + flow(30%) + discount(20%)."""
    vals = etf_close.values[:idx+1]
    if len(vals) < 60:
        return 0

    # Momentum (3-month)
    mom_3m = vals[-1] / vals[-min(60, len(vals))] - 1

    # Volatility penalty
    rets = np.diff(vals[-20:]) / vals[-21:-1]
    vol = np.std(rets) * np.sqrt(252)

    # Discount rate (from fundamentals cache)
    try:
        fund = etf_asset.fetch_fundamentals(etf_close.name) if hasattr(etf_close, 'name') else {}
        discount = fund.get("discount_rate", 0)
        flow_pct = fund.get("main_flow_pct", 0)
    except Exception:
        discount = 0
        flow_pct = 0

    # Score: momentum heavy, penalize high vol, prefer discount, prefer inflow
    score = 50 + mom_3m * 100 - vol * 20 + discount * 50 + flow_pct * 30
    return max(0, min(100, score))


def run_tournament():
    print(f"{'='*60}")
    print(f"Multi-Asset Tournament: {N_STOCKS} stocks + {N_ETFS} ETFs")
    print(f"{START} → {END} | Capital: {CASH:,.0f} 元")
    print(f"{'='*60}")

    # 1. Load data
    print("\n[1/3] 加载行情...")
    stock_syms = list(CIRCLE_STOCKS)[:N_STOCKS]
    stock_prices = load_prices(stock_syms, "stock")
    print(f"  股票: {len(stock_prices.columns)}/{N_STOCKS}")

    etf_syms = LIQUID_ETFS
    etf_prices = load_prices(etf_syms, "etf")
    print(f"  ETF:  {len(etf_prices.columns)}/{N_ETFS}")

    # Common timeline
    common_dates = stock_prices.index.intersection(etf_prices.index)
    if len(common_dates) == 0:
        print("ERROR: No common dates between stock and ETF data")
        return
    stock_prices = stock_prices.loc[common_dates]
    etf_prices = etf_prices.loc[common_dates]
    total_days = len(common_dates)

    # Bench
    bench_vals = []
    for dt in common_dates:
        if "510050" in stock_prices.columns:
            bench_vals.append(stock_prices["510050"].loc[dt] if "510050" in stock_prices.columns else None)
    bench_start = bench_vals[0] if bench_vals and bench_vals[0] else 1
    bench_end = bench_vals[-1] if bench_vals and bench_vals[-1] else 1

    # 2. Run three strategies
    print("\n[2/3] 运行对比...")
    results = {}

    for strategy_name, runner in [
        ("stock_only", _run_stock_only),
        ("etf_only", _run_etf_only),
        ("multi_asset", _run_multi_asset),
    ]:
        key = strategy_name
        try:
            r = runner(stock_prices, etf_prices, common_dates, total_days)
            results[key] = r
            label_map = {
                "stock_only": "纯股票 ML",
                "etf_only": "纯ETF 动量",
                "multi_asset": "二资产分配",
            }
            print(f"\n  ── {label_map.get(key, key)} ──")
            print(f"    {r['label']}: {r['total_return']:+.2f}% | Sharpe {r['sharpe']:.2f} | MaxDD {r['max_drawdown']:.1f}% | {r['trade_count']}笔")
        except Exception as e:
            print(f"  {key} 失败: {e}")
            import traceback; traceback.print_exc()

    # 3. Rankings
    print(f"\n{'='*60}")
    print("🏆 Multi-Asset Tournament Results")
    print(f"{'='*60}")
    ranked = sorted(results.items(), key=lambda x: -x[1]["total_return"])
    medals = ["🥇", "🥈", "🥉"]
    for i, (name, r) in enumerate(ranked):
        medal = medals[i] if i < 3 else f"  {i+1}."
        print(f"  {medal} {r['label']:20s} {r['total_return']:+.2f}% | MaxDD {r['max_drawdown']:.1f}% | {r['trade_count']}笔")

    print(f"\n  基准 (510050): {(bench_end/bench_start-1)*100:+.2f}%")

    # Save
    report = {
        "timestamp": datetime.now().isoformat(),
        "stock_count": len(stock_prices.columns),
        "etf_count": len(etf_prices.columns),
        "period": f"{START} → {END}",
        "bench_return": round((bench_end / bench_start - 1) * 100, 2) if bench_start > 0 else 0,
        "results": {k: {
            "label": v["label"],
            "total_return": round(v["total_return"], 2),
            "sharpe": round(v["sharpe"], 2),
            "max_drawdown": round(v["max_drawdown"], 1),
            "trade_count": v["trade_count"],
        } for k, v in results.items()},
    }
    out_path = Path(__file__).resolve().parent.parent / "data" / "tournament" / f"multi_asset_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\n报告已保存: {out_path}")


# ══════════════════════════════════════════════════════════
# Strategy runners
# ══════════════════════════════════════════════════════════

def _run_stock_only(stock_prices, etf_prices, dates, total_days):
    """100% in stocks, momentum+vol scoring monthly (fast in-memory)."""
    holdings = {}
    cash = CASH
    daily_values = []
    trade_log = []

    for day_idx in range(total_days):
        dt = dates[day_idx]

        if day_idx == 0 or dt.month != dates[day_idx - 1].month:
            scores = {}
            for sym in stock_prices.columns:
                close = stock_prices[sym].values[:day_idx+1]
                if len(close) < 63:
                    continue
                mom_1m = close[-1] / close[-21] - 1
                mom_3m = close[-1] / close[-63] - 1
                rets = np.diff(close[-20:]) / close[-21:-1]
                vol = np.std(rets) * np.sqrt(252)
                scores[sym] = 50 + mom_1m * 80 + mom_3m * 40 - vol * 25
                if pd.isna(scores[sym]):
                    scores[sym] = 0

            top_n = 8
            selected = sorted(scores.items(), key=lambda x: -x[1])[:top_n]

            for sym in list(holdings.keys()):
                p = stock_prices[sym].iloc[day_idx]
                if pd.isna(p):
                    continue
                cash += holdings[sym] * p - stock_ex.calc_cost(p, holdings[sym], OrderSide.SELL)
                trade_log.append((dt, "SELL", sym, holdings[sym], p))
                del holdings[sym]

            if selected:
                per_stock = cash / len(selected) * 0.99
                for sym, _ in selected:
                    p = stock_prices[sym].iloc[day_idx]
                    if pd.isna(p) or p <= 0:
                        continue
                    shares = int(per_stock / p / 100) * 100
                    if shares >= 100:
                        cost = stock_ex.calc_cost(p, shares, OrderSide.BUY)
                        if shares * p + cost <= cash:
                            cash -= shares * p + cost
                            holdings[sym] = holdings.get(sym, 0) + shares
                            trade_log.append((dt, "BUY", sym, shares, p))

        mv = cash
        for sym, shares in holdings.items():
            if sym in stock_prices.columns:
                p = stock_prices[sym].iloc[day_idx]
                if not pd.isna(p):
                    mv += shares * p
        daily_values.append(mv)

    return _compute_metrics("纯股票 动量", daily_values, trade_log)


def _run_etf_only(stock_prices, etf_prices, dates, total_days):
    """100% in ETFs, momentum+flow scoring monthly."""
    holdings = {}
    cash = CASH
    daily_values = []
    trade_log = []

    for day_idx in range(total_days):
        dt = dates[day_idx]

        if day_idx == 0 or dt.month != dates[day_idx - 1].month:
            # Score all ETFs
            scores = {}
            for sym in etf_prices.columns:
                series = etf_prices[sym]
                val = series.iloc[day_idx]
                if pd.isna(val):
                    continue
                scores[sym] = score_etf_momentum(series, day_idx)

            top_n = 5
            selected = sorted(scores.items(), key=lambda x: -x[1])[:top_n]

            # Sell all
            for sym in list(holdings.keys()):
                p = etf_prices[sym].iloc[day_idx]
                if pd.isna(p):
                    continue
                cash += holdings[sym] * p - etf_ex.calc_cost(p, holdings[sym], OrderSide.SELL)
                trade_log.append((dt, "SELL_ETF", sym, holdings[sym], p))
                del holdings[sym]

            # Buy new
            if selected:
                per_etf_cash = cash / len(selected)
                for sym, _ in selected:
                    p = etf_prices[sym].iloc[day_idx]
                    if pd.isna(p) or p <= 0:
                        continue
                    shares = int(per_etf_cash / p / 100) * 100
                    if shares >= 100:
                        cost = etf_ex.calc_cost(p, shares, OrderSide.BUY)
                        if shares * p + cost <= cash:
                            cash -= shares * p + cost
                            holdings[sym] = holdings.get(sym, 0) + shares
                            trade_log.append((dt, "BUY_ETF", sym, shares, p))

        # Daily NAV
        mv = cash
        for sym, shares in holdings.items():
            if sym in etf_prices.columns:
                p = etf_prices[sym].iloc[day_idx]
                if not pd.isna(p):
                    mv += shares * p
        daily_values.append(mv)

    return _compute_metrics("纯ETF 动量", daily_values, trade_log)


def _run_multi_asset(stock_prices, etf_prices, dates, total_days):
    """AssetAllocator decides stock/ETF split each month."""
    holdings = {}  # {symbol: shares} mixed stock+etf
    cash = CASH
    daily_values = []
    trade_log = []
    regime_history = []

    for day_idx in range(total_days):
        dt = dates[day_idx]

        # Monthly: detect regime, allocate, rebalance
        if day_idx == 0 or dt.month != dates[day_idx - 1].month:
            # Regime detection
            try:
                regime = detect_market_regime()
                regime_str = regime.value if hasattr(regime, 'value') else str(regime)
            except Exception:
                regime_str = "unknown"
            regime_history.append((dt, regime_str))

            # Allocate
            weights = allocator.get_weights(regime_str)
            stock_weight = weights.get("stock", 0.50)
            etf_weight = weights.get("etf", 0.30)
            cash_weight = weights.get("cash", 0.10)

            # Rebalance: sell everything first
            for sym in list(holdings.keys()):
                if sym in stock_prices.columns:
                    p = stock_prices[sym].iloc[day_idx]
                    ex = stock_ex
                elif sym in etf_prices.columns:
                    p = etf_prices[sym].iloc[day_idx]
                    ex = etf_ex
                else:
                    continue
                if pd.isna(p):
                    continue
                cash += holdings[sym] * p - ex.calc_cost(p, holdings[sym], OrderSide.SELL)
                trade_log.append((dt, "SELL", sym, holdings[sym], p))
                del holdings[sym]

            total = cash  # all positions liquidated
            stock_budget = total * stock_weight
            etf_budget = total * etf_weight

            # Buy stocks (momentum scoring)
            if stock_budget > 10000:
                stock_scores = {}
                for sym in stock_prices.columns:
                    close = stock_prices[sym].values[:day_idx+1]
                    if len(close) < 63:
                        continue
                    mom_1m = close[-1] / close[-21] - 1
                    mom_3m = close[-1] / close[-63] - 1
                    rets = np.diff(close[-20:]) / close[-21:-1]
                    vol = np.std(rets) * np.sqrt(252)
                    stock_scores[sym] = 50 + mom_1m * 80 + mom_3m * 40 - vol * 25
                top_stocks = sorted(stock_scores.items(), key=lambda x: -x[1])[:5]
                if top_stocks:
                    per_stock = stock_budget / len(top_stocks)
                    for sym, _ in top_stocks:
                        p = stock_prices[sym].iloc[day_idx]
                        if pd.isna(p) or p <= 0:
                            continue
                        shares = int(per_stock / p / 100) * 100
                        if shares >= 100:
                            cost = stock_ex.calc_cost(p, shares, OrderSide.BUY)
                            if shares * p + cost <= cash:
                                cash -= shares * p + cost
                                holdings[sym] = holdings.get(sym, 0) + shares
                                trade_log.append((dt, "BUY", sym, shares, p))

            # Buy ETFs (momentum + flow)
            if etf_budget > 10000:
                etf_scores = {}
                for sym in etf_prices.columns:
                    val = etf_prices[sym].iloc[day_idx]
                    if not pd.isna(val):
                        etf_scores[sym] = score_etf_momentum(etf_prices[sym], day_idx)
                top_etfs = sorted(etf_scores.items(), key=lambda x: -x[1])[:3]
                if top_etfs:
                    per_etf = etf_budget / len(top_etfs)
                    for sym, _ in top_etfs:
                        p = etf_prices[sym].iloc[day_idx]
                        if pd.isna(p) or p <= 0:
                            continue
                        shares = int(per_etf / p / 100) * 100
                        if shares >= 100:
                            cost = etf_ex.calc_cost(p, shares, OrderSide.BUY)
                            if shares * p + cost <= cash:
                                cash -= shares * p + cost
                                holdings[sym] = holdings.get(sym, 0) + shares
                                trade_log.append((dt, "BUY_ETF", sym, shares, p))

        # Daily NAV
        mv = cash
        for sym, shares in holdings.items():
            if sym in stock_prices.columns:
                p = stock_prices[sym].iloc[day_idx]
            elif sym in etf_prices.columns:
                p = etf_prices[sym].iloc[day_idx]
            else:
                continue
            if not pd.isna(p):
                mv += shares * p
        daily_values.append(mv)

    return _compute_metrics("二资产分配", daily_values, trade_log)


def _compute_metrics(label: str, daily_values: list, trade_log: list) -> dict:
    """Compute risk/return metrics from daily NAV."""
    vals = np.array([float(v) for v in daily_values])
    if len(vals) < 2:
        return {"label": label, "total_return": 0, "sharpe": 0, "max_drawdown": 0, "trade_count": 0}

    start_val = vals[0]
    end_val = vals[-1]
    total_return = (end_val / start_val - 1) * 100 if start_val > 0 else 0

    daily_rets = np.diff(vals) / vals[:-1]
    ann_ret = np.mean(daily_rets) * 252
    ann_vol = np.std(daily_rets) * np.sqrt(252)
    sharpe = ann_ret / ann_vol if ann_vol > 0 else 0

    peak = np.maximum.accumulate(vals)
    drawdowns = (vals - peak) / peak
    max_drawdown = np.min(drawdowns) * 100

    return {
        "label": label,
        "total_return": round(total_return, 2),
        "sharpe": round(sharpe, 2),
        "max_drawdown": round(max_drawdown, 1),
        "trade_count": len([t for t in trade_log if "BUY" in t[2]]),
    }


if __name__ == "__main__":
    run_tournament()
