#!/usr/bin/env python3
"""
日频模拟交易执行脚本

每天 15:30 compute_signals.py 后运行:
  1. 从 Parquet 恢复 PaperBroker 状态
  2. 读取各策略最新信号 (data/store/signals/*.parquet)
  3. 用次日开盘价 (≈ 今日收盘) 模拟成交
  4. 记录 NAV 快照 + 交易记录
  5. 写回状态 Parquet

可选: 指定历史日期跑回放 (用于初始化历史 NAV)

用法:
  # 当日执行
  python scripts/execute_paper_trades.py

  # 历史回放 (构建 NAV 历史)
  python scripts/execute_paper_trades.py --date 2026-01-02 --init-cash 1000000

  # 仅查看状态 (不交易)
  python scripts/execute_paper_trades.py --dry-run
"""

from __future__ import annotations
import sys
import os
from pathlib import Path
from datetime import date, timedelta, datetime
from typing import Dict, List, Tuple, Optional
import argparse

import pandas as pd
import yaml

# 项目根
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from broker import PaperBroker
from broker.persistence import (
    load_state, save_state, append_nav, append_trade,
    load_nav, load_trades, PaperState, _resolve_store,
)
from data.symbols import CIRCLE_STOCKS


# ── 配置 ──

def load_config() -> dict:
    cfg_path = ROOT / "config" / "settings.yaml"
    with open(cfg_path) as f:
        return yaml.safe_load(f)


# ── 价格获取 ──

def _get_close_prices(symbols: List[str], target_date: Optional[date] = None) -> Dict[str, float]:
    """
    获取股票最近收盘价。
    通过 data.fetcher.get_stock_daily (含两层缓存) 获取，取最后一根K线收盘价。
    """
    from data.fetcher import get_stock_daily

    prices: Dict[str, float] = {}
    for sym in symbols:
        try:
            df = get_stock_daily(sym)
            if df is None or df.empty:
                continue
            if target_date:
                mask = pd.to_datetime(df["date"]) <= pd.Timestamp(target_date)
                if mask.any():
                    prices[sym] = float(df[mask].iloc[-1]["close"])
            else:
                prices[sym] = float(df.iloc[-1]["close"])
        except Exception:
            continue

    return prices


# ── 信号读取 ──

def _read_latest_signals() -> Dict[str, List[Tuple[str, str, int]]]:
    """
    读取各策略最新信号。
    Returns: {strategy: [(code, side, shares), ...]}
    信号 parquet 使用 computed_at 列 (ISO格式), 取最新批次。
    """
    signals_dir = ROOT / "data" / "store" / "signals"
    cfg = load_config()
    strategies = cfg.get("strategies", {})

    result: Dict[str, List[Tuple[str, str, int]]] = {}

    for strategy_name, strategy_cfg in strategies.items():
        if not strategy_cfg.get("enabled", True):
            continue
        sig_file = signals_dir / f"{strategy_name}.parquet"
        if not sig_file.exists():
            continue
        try:
            df = pd.read_parquet(sig_file)
            if df.empty or "signal" not in df.columns:
                continue

            # 用 computed_at 列取最新批次
            if "computed_at" in df.columns:
                latest_ts = df["computed_at"].max()
                latest = df[df["computed_at"] == latest_ts]
            else:
                latest = df

            # 信号过滤 (大小写兼容)
            buys = latest[latest["signal"].str.lower().isin(["buy", "strong_buy"])]
            sells = latest[latest["signal"].str.lower().isin(["sell", "strong_sell"])]

            items = []
            for _, row in buys.iterrows():
                code = str(row.get("symbol", row.get("code", "")))
                code = code.split(".")[0] if "." in code else code
                items.append((code, "buy", 100))
            for _, row in sells.iterrows():
                code = str(row.get("symbol", row.get("code", "")))
                code = code.split(".")[0] if "." in code else code
                items.append((code, "sell", 100))

            if items:
                result[strategy_name] = items
        except Exception as e:
            print(f"  ⚠ 读取 {strategy_name} 信号失败: {e}")

    return result


# ── 主逻辑 ──

def execute_daily(run_date: Optional[date] = None, dry_run: bool = False,
                  init_cash: float = 1_000_000, initial_setup: bool = False,
                  limit: int = 0):
    """执行一个模拟交易日"""

    if run_date is None:
        run_date = date.today()

    print(f"\n{'═' * 60}")
    print(f"  Paper Trading 日频执行 — {run_date}")
    print(f"{'═' * 60}")

    # 1) 恢复/初始化 Broker
    if initial_setup:
        state = PaperState(cash=init_cash, peak_equity=init_cash)
        print(f"  ★ 初始化账户: ¥{init_cash:,.0f}")
    else:
        state = load_state()
        print(f"  恢复状态: 现金 ¥{state.cash:,.2f}  |  持仓 {len(state.positions)} 只")

    broker = PaperBroker(
        initial_cash=state.cash,
        commission_rate=0.00081,
        t_plus_1=True,
        enable_risk=True,
    )
    broker._cash = state.cash
    broker._frozen_cash = state.frozen_cash
    broker._peak_equity = state.peak_equity
    broker._order_counter = state.order_counter
    broker._today_buys = {}
    broker._today_sells = {}

    # 恢复持仓
    for code, pos_data in state.positions.items():
        from broker import Position
        broker._positions[code] = Position(
            code=code,
            name=pos_data.get("name", ""),
            volume=pos_data["volume"],
            avg_cost=pos_data["avg_cost"],
        )

    # 2) 获取价格
    all_symbols = list(broker._positions.keys())
    signals = _read_latest_signals()
    for strat_name, items in signals.items():
        for code, side, _ in items:
            if code not in all_symbols:
                all_symbols.append(code)

    prices = _get_close_prices(all_symbols, run_date)
    broker.set_prices(prices)
    print(f"  价格覆盖: {len(prices)}/{len(all_symbols)} 只")

    # 3) 处理信号 → 下单
    total_trades = 0
    trade_count = 0
    for strat_name, items in signals.items():
        for code, side, shares in items:
            if limit > 0 and trade_count >= limit:
                break
            if code not in prices:
                print(f"  ⚠ {code} 无价格，跳过")
                continue

            price = prices[code]
            amount = price * shares

            print(f"  {'买' if side == 'buy' else '卖'} {code} {shares}股 @{price:.2f} [{strat_name}]")

            if dry_run:
                continue

            result = broker.submit_order(code=code, price=price, volume=shares, side=side)
            if result and result.startswith("PAPER_"):
                append_trade(run_date, code, side, price, shares, amount, strat_name)
                total_trades += 1
                trade_count += 1
            else:
                print(f"    ✗ {result}")

    if dry_run:
        print(f"\n  [DRY RUN] 将执行 {total_trades} 笔交易")

    # 4) 日末结算 + NAV
    broker.end_of_day()
    balance = broker.get_balance()

    if not dry_run:
        append_nav(run_date, balance.total_asset, balance.cash, balance.market_value)

        # 写回状态
        new_state = PaperState(
            cash=broker._cash,
            frozen_cash=broker._frozen_cash,
            peak_equity=broker._peak_equity,
            positions={
                code: {
                    "volume": p.volume,
                    "avg_cost": p.avg_cost,
                    "name": p.name or "",
                }
                for code, p in broker._positions.items() if p.volume > 0
            },
            order_counter=broker._order_counter,
        )
        save_state(new_state)
        print(f"\n  状态已保存 → {_resolve_store() / 'state.parquet'}")

    # 5) 汇总
    positions = broker.get_positions()
    print(f"\n{'─' * 40}")
    print(f"  总资产:  ¥{balance.total_asset:,.2f}")
    print(f"  现金:    ¥{balance.cash:,.2f}")
    print(f"  持仓市值: ¥{balance.market_value:,.2f}")
    print(f"  持仓数:  {len(positions)}")
    print(f"  今日成交: {total_trades} 笔")
    if positions:
        print(f"\n  持仓明细:")
        for p in sorted(positions, key=lambda x: -x.market_value)[:10]:
            print(f"    {p.code} x{p.volume}  "
                  f"成本{p.avg_cost:.2f}  现价{p.current_price:.2f}  "
                  f"盈亏{p.pnl_pct*100:+.1f}%")
    print(f"{'─' * 40}\n")

    return broker


def replay_history(start_date: date, end_date: Optional[date] = None,
                   init_cash: float = 1_000_000):
    """
    历史回放: 按天执行模拟交易，构建完整 NAV 历史。
    用于首次初始化或策略切换后的历史重建。
    """
    if end_date is None:
        end_date = date.today()

    # 获取交易日历
    from data.fetcher import get_trade_calendar
    try:
        trade_days = get_trade_calendar(start_date.strftime("%Y%m%d"), end_date.strftime("%Y%m%d"))
    except Exception:
        # fallback: business days
        trade_days = pd.bdate_range(start_date, end_date)

    print(f"\n历史回放: {start_date} → {end_date}, {len(trade_days)} 个交易日")

    # 清空历史
    store = _resolve_store()
    for f in ["state.parquet", "nav.parquet", "trades.parquet"]:
        fp = store / f
        if fp.exists():
            fp.unlink()

    first = True
    for td in trade_days:
        if isinstance(td, pd.Timestamp):
            td = td.date()
        execute_daily(run_date=td, init_cash=init_cash, initial_setup=first)
        first = False

    # 最终汇总
    nav_df = load_nav()
    trades_df = load_trades()
    if not nav_df.empty:
        start_val = nav_df.iloc[0]["total_asset"]
        end_val = nav_df.iloc[-1]["total_asset"]
        ret = (end_val - start_val) / start_val * 100
        print(f"\n回放完成: {start_date}→{end_date} 收益 {ret:+.2f}%, {len(trades_df)} 笔交易")


# ── CLI ──

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Paper Trading 日频执行")
    parser.add_argument("--date", type=str, default=None, help="执行日期 YYYY-MM-DD")
    parser.add_argument("--dry-run", action="store_true", help="不实际执行")
    parser.add_argument("--init-cash", type=float, default=1_000_000, help="初始资金")
    parser.add_argument("--replay", type=str, default=None,
                        help="历史回放: YYYY-MM-DD,YYYY-MM-DD 或 YYYY-MM-DD(从该日到今日)")
    parser.add_argument("--setup", action="store_true", help="初始化账户(清空所有历史)")
    parser.add_argument("--limit", type=int, default=0, help="限制交易笔数 (0=全部)")

    args = parser.parse_args()

    # 处理 --replay
    if args.replay:
        parts = args.replay.split(",")
        start = date.fromisoformat(parts[0].strip())
        end = date.fromisoformat(parts[1].strip()) if len(parts) > 1 else None
        replay_history(start, end, init_cash=args.init_cash)
        sys.exit(0)

    # 处理 --setup
    if args.setup:
        store = _resolve_store()
        for f in ["state.parquet", "nav.parquet", "trades.parquet"]:
            fp = store / f
            if fp.exists():
                fp.unlink()
        state = PaperState(cash=args.init_cash, peak_equity=args.init_cash)
        save_state(state)
        print(f"账户已初始化: ¥{args.init_cash:,.0f}")
        sys.exit(0)

    # 普通日执行
    run_date = date.fromisoformat(args.date) if args.date else None
    execute_daily(run_date=run_date, dry_run=args.dry_run,
                  init_cash=args.init_cash, limit=args.limit)

    sys.exit(0)
