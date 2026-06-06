#!/usr/bin/env python3
"""
日频模拟交易执行脚本

每天 15:30 compute_signals.py 后运行:
  1. 从 Parquet 恢复 PaperBroker 状态
  2. 读取各策略最新信号 (var/store/signals/*.parquet)
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
from datetime import date
from typing import Dict, List, Tuple, Optional
import argparse

import pandas as pd

from core.settings import get_settings
from broker import PaperBroker
from broker.persistence import (
    load_state, save_state, append_nav, append_trade,
    load_nav, load_trades, PaperState, _resolve_store,
)
from data.storage.datahub import get_datahub
from data.market.symbols import CIRCLE_STOCKS

HUB = get_datahub()
DEFAULT_REGIME = "sideways"


# ── 配置 ──

def load_config() -> dict:
    return get_settings()


# ── 价格获取 ──

def _get_close_prices(symbols: List[str], target_date: Optional[date] = None) -> Dict[str, float]:
    """
    获取股票最近收盘价。
    通过 data.market.price_service 获取 raw 最新价；无 raw 时允许最新 qfq 兼容回退。
    Paper trading 需要实时价格 — 启用 API fallback，允许从 AKShare 拉取未缓存的股票。
    """
    import os as _os
    _os.environ.setdefault("QUANT_ALLOW_API_FALLBACK", "1")
    from data.market.price_service import get_stock_prices
    from data.market.price_types import PriceUseCase

    prices: Dict[str, float] = {}
    for sym in symbols:
        try:
            df = get_stock_prices(sym, use_case=PriceUseCase.EXECUTION)
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

def _iter_paper_strategy_configs(cfg: dict):
    from data.strategy.catalog import can_run_paper

    strategies = cfg.get("strategies", {}) or {}
    configured = cfg.get("paper_trading", {}).get("strategies") or list(strategies.keys())
    for strategy_name in configured:
        strategy_cfg = strategies.get(strategy_name, {})
        if not strategy_cfg.get("enabled", True):
            continue
        if not can_run_paper(strategy_name):
            continue
        yield strategy_name, strategy_cfg


def _latest_fresh_signal_batch(sig_file, paper_cfg: dict) -> pd.DataFrame:
    df = HUB.latest_batch(sig_file)
    if df is None or df.empty:
        return pd.DataFrame()
    max_age_days = int(paper_cfg.get("max_signal_age_days", 2))
    if max_age_days <= 0 or "computed_at" not in df.columns:
        return df
    computed = pd.to_datetime(df["computed_at"], errors="coerce").dropna()
    if computed.empty:
        return pd.DataFrame()
    age = pd.Timestamp.now(tz=None) - computed.max().tz_localize(None)
    if age > pd.Timedelta(days=max_age_days):
        return pd.DataFrame()
    return df

def _read_latest_signals() -> Dict[str, List[Tuple[str, str, float]]]:
    """
    读取各策略最新信号。
    Returns: {strategy: [(code, side, score), ...]}
    信号 parquet 使用 computed_at 列 (ISO格式), 取最新批次。
    """
    cfg = load_config()
    paper_cfg = cfg.get("paper_trading", {})
    max_per_strategy = int(paper_cfg.get("max_orders_per_strategy", 5))

    result: Dict[str, List[Tuple[str, str, float]]] = {}

    for strategy_name, strategy_cfg in _iter_paper_strategy_configs(cfg):
        signal_name = strategy_cfg.get("signal_name", strategy_name)
        sig_file = HUB.signal_path(signal_name)
        if not sig_file.exists():
            continue
        try:
            df = _latest_fresh_signal_batch(sig_file, paper_cfg)
            if df.empty or "signal" not in df.columns:
                continue

            # 信号过滤 (大小写兼容)
            signal_col = df["signal"].astype(str).str.lower()
            buys = df[signal_col.isin(["buy", "strong_buy"])]
            sells = df[signal_col.isin(["sell", "strong_sell"])]
            if "score" in buys.columns:
                buys = buys.sort_values("score", ascending=False)
            if max_per_strategy > 0:
                buys = buys.head(max_per_strategy)

            items = []
            for _, row in buys.iterrows():
                code = str(row.get("symbol", row.get("code", "")))
                code = code.split(".")[0] if "." in code else code
                items.append((code, "buy", float(row.get("score", 0) or 0)))
            for _, row in sells.iterrows():
                code = str(row.get("symbol", row.get("code", "")))
                code = code.split(".")[0] if "." in code else code
                items.append((code, "sell", float(row.get("score", 0) or 0)))

            if items:
                result[strategy_name] = items
        except Exception as e:
            print(f"  ⚠ 读取 {strategy_name} 信号失败: {e}")

    return result


def _calc_order_volume(broker: PaperBroker, code: str, side: str, price: float, paper_cfg: dict) -> int:
    lot_size = int(paper_cfg.get("lot_size", 100))
    lot_size = max(1, lot_size)

    if side == "sell":
        pos = broker.get_position(code)
        if not pos:
            return 0
        if paper_cfg.get("sell_all_on_sell_signal", True):
            return int(pos.volume // lot_size) * lot_size
        configured = int(paper_cfg.get("sell_shares", lot_size))
        return min(pos.volume, int(configured // lot_size) * lot_size)

    balance = broker.get_balance()
    order_value_pct = float(paper_cfg.get("order_value_pct", 0.05))
    max_order_value = float(paper_cfg.get("max_order_value", balance.total_asset * order_value_pct))
    budget = min(balance.total_asset * order_value_pct, balance.cash, max_order_value)
    return int(budget / max(price, 1e-9) // lot_size) * lot_size


def detect_live_regime(default: str = DEFAULT_REGIME) -> str:
    """Return the confirmed production Market Regime for paper execution."""
    try:
        from cybernetics.orchestrator import QuantOrchestrator

        snapshot = QuantOrchestrator().detect()
        regime = snapshot.regime.value if hasattr(snapshot.regime, "value") else str(snapshot.regime)
        return regime if regime in {"bull", "bear", "sideways"} else default
    except Exception:
        return default


# ── 主逻辑 ──

def _execute_signals_via_pipeline(
    broker: PaperBroker,
    run_date: date,
    cfg: dict,
    limit: int = 0,
    dry_run: bool = False,
) -> int:
    """Execute signals using the pipeline stages (Alpha→Portfolio→Risk→Execution)."""
    from pipeline.types import PipelineContext
    from pipeline.alpha import SignalParquetAlphaModel
    from pipeline.portfolio import EqualWeightConstructor
    from pipeline.risk import RiskAdjuster
    from broker.exchange import AShareExchange
    from pipeline.execution import ExecutionRouter, ExecutionConfig
    from pipeline.scheduler import RebalanceScheduler, RebalanceConfig

    balance = broker.get_balance()
    holdings = {p.code: p.volume for p in broker.get_positions()}
    prices = {p.code: p.current_price for p in broker.get_positions()}
    cost_basis = {p.code: p.avg_cost for p in broker.get_positions()}
    live_regime = detect_live_regime()

    ctx = PipelineContext(
        date=run_date,
        universe=list(set(list(holdings.keys()))),
        prices=prices,
        regime=live_regime,
        cash=balance.cash,
        holdings=holdings,
        cost_basis=cost_basis,
    )

    paper_cfg = cfg.get("paper_trading", {})
    max_signals = int(paper_cfg.get("max_orders_per_strategy", 5))

    lot_size = int(paper_cfg.get("lot_size", 100))
    exec_cfg = ExecutionConfig(
        lot_size=lot_size,
        exchange=AShareExchange(lot_size=lot_size),
    )
    router = ExecutionRouter(exec_cfg)
    portfolio = EqualWeightConstructor(
        max_positions=int(paper_cfg.get("max_positions", 8)),
        position_pct=float(paper_cfg.get("order_value_pct", 0.05)),
    )
    risk = RiskAdjuster()

    all_fills = []
    total_trades = 0

    for strat_name, strat_cfg in _iter_paper_strategy_configs(cfg):
        signal_name = strat_cfg.get("signal_name", strat_name)
        sig_file = HUB.signal_path(signal_name)
        if not sig_file.exists():
            continue
        if _latest_fresh_signal_batch(sig_file, paper_cfg).empty:
            continue

        alpha = SignalParquetAlphaModel(
            name=strat_name,
            label=strat_cfg.get("label", strat_name),
            signal_path=sig_file,
            max_signals=max_signals,
        )

        ctx.signals = alpha.generate_alpha([], pd.DataFrame(), 0, ctx.regime)
        if not ctx.signals:
            continue

        # Extend universe and prices with signal symbols
        for s in ctx.signals:
            if s.symbol not in ctx.universe:
                ctx.universe.append(s.symbol)
                if s.symbol not in ctx.prices:
                    try:
                        from data.market.price_service import get_stock_prices
                        from data.market.price_types import PriceUseCase
                        df = get_stock_prices(s.symbol, use_case=PriceUseCase.EXECUTION)
                        if df is not None and len(df):
                            ctx.prices[s.symbol] = float(df.iloc[-1]["close"])
                    except Exception:
                        ctx.prices[s.symbol] = 0

        ctx.targets = portfolio.construct(ctx.signals, ctx)
        ctx.adjusted_targets = risk.adjust(ctx.targets, ctx)
        ctx.intents = router.targets_to_intents(ctx.adjusted_targets, ctx)

        for intent in ctx.intents:
            if limit > 0 and total_trades >= limit:
                break
            price = ctx.prices.get(intent.symbol, intent.price)
            if price <= 0:
                continue

            print(f"  {'买' if intent.side=='buy' else '卖'} {intent.symbol} "
                  f"{intent.shares}股 @{price:.2f} [{strat_name}]")

            if dry_run:
                total_trades += 1
                continue

            result = broker.submit_order(
                code=intent.symbol, price=price,
                volume=intent.shares, side=intent.side,
            )
            if result and str(result).startswith("PAPER_"):
                amount = price * intent.shares
                append_trade(run_date, intent.symbol, intent.side, price,
                            intent.shares, amount, strat_name)
                total_trades += 1
            else:
                print(f"    ✗ {result}")

    return total_trades


def execute_daily(run_date: Optional[date] = None, dry_run: bool = False,
                  init_cash: float = 1_000_000, initial_setup: bool = False,
                  limit: int = 0, use_pipeline: bool = False):
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

    broker = PaperBroker.from_state(
        state,
        commission_rate=0.00081,
        t_plus_1=True,
        enable_risk=True,
    )

    # 2) 获取价格
    cfg = load_config()
    paper_cfg = cfg.get("paper_trading", {})
    all_symbols = broker.get_position_codes()
    signals = _read_latest_signals()
    for strat_name, items in signals.items():
        for code, side, _ in items:
            if code not in all_symbols:
                all_symbols.append(code)

    prices = _get_close_prices(all_symbols, run_date)
    broker.set_prices(prices)
    print(f"  价格覆盖: {len(prices)}/{len(all_symbols)} 只")

    # 3) 处理信号 → 下单
    if use_pipeline:
        total_trades = _execute_signals_via_pipeline(
            broker, run_date, cfg, limit=limit, dry_run=dry_run,
        )
    else:
        total_trades = 0
        trade_count = 0
        for strat_name, items in signals.items():
            if limit > 0 and trade_count >= limit:
                break
            for code, side, score in items:
                if limit > 0 and trade_count >= limit:
                    break
                if code not in prices:
                    print(f"  ⚠ {code} 无价格，跳过")
                    continue

                price = prices[code]
                shares = _calc_order_volume(broker, code, side, price, paper_cfg)
                if shares <= 0:
                    print(f"  ⚠ {code} 无可执行数量，跳过")
                    continue
                amount = price * shares

                print(f"  {'买' if side == 'buy' else '卖'} {code} {shares}股 @{price:.2f} score={score:.1f} [{strat_name}]")

                if dry_run:
                    total_trades += 1
                    trade_count += 1
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
        save_state(broker.snapshot_state())
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
    from data.ingestion.fetcher import get_trade_calendar
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
    parser.add_argument("--pipeline", action="store_true", help="使用流水线 Alpha→Portfolio→Risk→Execution 执行")

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
    from data.ops.cron_logger import cron_run
    with cron_run("execute_paper_trades"):
        run_date = date.fromisoformat(args.date) if args.date else None
        execute_daily(run_date=run_date, dry_run=args.dry_run,
                      init_cash=args.init_cash, limit=args.limit,
                      use_pipeline=args.pipeline)

    sys.exit(0)
