#!/usr/bin/env python3
"""
一次性批计算：运行所有策略，结果存入 Parquet 信号库。

策略:
  buffett     — 巴菲特三层过滤器 (能力圈→护城河→安全边际)
  multifactor — 多因子打分 (质量40%+估值30%+技术15%+市场15%)
  cybernetic  — 控制论市场状态信号 (基于当前市场regime)
  ml_lgbm     — LightGBM PIT特征模型

后续:
  每日 cron: 只更新价格敏感列 (safety_margin / dcf_value / current_price)
  财报季: 重新跑 buffett 全量

Usage:
  python scripts/compute_signals.py [--strategy buffett] [--limit N]
"""

import argparse
import os
import socket
import time
from datetime import datetime

from core.settings import get_section
from data.datahub import get_datahub
from data.results_db import load_strategy_signals, list_strategies
from signals.runners import compute_buffett, compute_cybernetic, compute_multifactor

HUB = get_datahub()


def _configure_runtime_for_cli() -> None:
    """Apply network settings only when this file is run as a CLI."""
    for key in list(os.environ.keys()):
        if key.lower() in {"http_proxy", "https_proxy", "all_proxy"}:
            del os.environ[key]
    os.environ["no_proxy"] = "*"
    socket.setdefaulttimeout(30)


def main():
    from data.registry import list_strategy_names, get_status, can_run_production, status_label
    from data.strategy_plugins import run_registered_strategies

    _configure_runtime_for_cli()

    parser = argparse.ArgumentParser()
    all_names = list_strategy_names()
    parser.add_argument('--strategy', default='all', choices=['all'] + all_names)
    parser.add_argument('--limit', type=int, default=0, help='Limit to N stocks (0=all)')
    parser.add_argument('--skip-quality-gate', action='store_true', help='Skip pre-scan data freshness check')
    parser.add_argument('--allow-candidate', action='store_true', help='Allow candidate/validated strategies (dev/testing)')
    parser.add_argument('--mode', choices=['production', 'research'], default='production', help='Strategy runtime mode')
    args = parser.parse_args()
    if args.allow_candidate:
        args.mode = 'research'

    start = time.time()
    print(f"Compute signals: strategy={args.strategy} mode={args.mode}")

    # P2-12: Status gate — only production strategies produce production signals
    if args.mode == "production" and args.strategy != "all":
        st = get_status(args.strategy)
        if not can_run_production(args.strategy):
            print(f"  ⛔ Strategy '{args.strategy}' status={st} ({status_label(st)}) — not production. Skipping.")
            print(f"  Use --mode research to run candidate/validated strategies for development/testing.")
            return
        print(f"  ✅ Strategy '{args.strategy}' status={st} ({status_label(st)}) — production ✓")

    # Pre-scan data quality gate
    if not args.skip_quality_gate:
        from data.quality import pre_scan_gate
        ok, reports = pre_scan_gate()
        stale_dims = [r for r in reports if r.status in ("stale", "missing", "error")]
        if stale_dims:
            print(f"\n  Data quality gate WARNING — {len(stale_dims)} dimension(s) not fresh:")
            for r in stale_dims:
                print(f"    {r.dimension} [{r.status}] score={r.health_score} freshness={r.freshness_days}d SLA={r.sla_days}d")
            print(f"  Scan will proceed with degraded data confidence.\n")
        else:
            print(f"  Data quality gate: {len(reports)} dimensions fresh ✓\n")
    else:
        print("  Data quality gate: skipped (--skip-quality-gate)\n")

    from data.results_db import init
    from data.db import reset_db
    reset_db()
    init()

    run_registered_strategies(args.strategy, limit=args.limit, mode=args.mode)

    elapsed = time.time() - start
    print(f"\nTotal: {elapsed:.0f}s")

    # Summary
    strategies = list_strategies()
    print("\n策略总览:")
    for s in strategies:
        print(f"  {s['label']}: {s['total']} stocks, {s['buys']} buys @ {s['last_computed']}")

    # ── 信号变更检测 + 推送 ──
    notify_signals(strategies)

    return strategies


def notify_signals(strategies: list[dict]):
    """检测信号变更，只推送有变化的股票，发送到Telegram"""
    try:
        notify_cfg = get_section("trading.notification", {}) or {}
        if not notify_cfg.get("enabled", False):
            print("\n📵 通知已关闭 (trading.notification.enabled=false)")
            return
    except Exception:
        print("\n⚠️ 无法读取通知配置，跳过推送")
        return

    # 对比上一次结果
    changes = []
    for s in strategies:
        current = load_strategy_signals(s["name"])
        if not current:
            continue
        current_map = {r["symbol"]: r["signal"] for r in current}
        name_map = {r["symbol"]: r["name"] for r in current}

        # 尝试加载上一次（文件名带日期）
        prev = _load_prev_signals(s["name"])
        if not prev:
            continue
        prev_map = {r["symbol"]: r["signal"] for r in prev}

        for sym, cur_sig in current_map.items():
            prev_sig = prev_map.get(sym, "new")
            if cur_sig != prev_sig:
                changes.append({
                    "strategy": s["label"],
                    "symbol": sym,
                    "name": name_map.get(sym, sym),
                    "from": prev_sig,
                    "to": cur_sig,
                })

    # 备份当前结果
    _save_prev_signals()

    if not changes:
        print("\n📊 无信号变更")
        return

    # 格式化推送
    print(f"\n📊 信号变更: {len(changes)}条")
    lines = [f"📡 星盘信号变更 ({datetime.now().strftime('%m/%d %H:%M')})", ""]
    by_strategy = {}
    for c in changes:
        by_strategy.setdefault(c["strategy"], []).append(c)

    for strat, items in by_strategy.items():
        lines.append(f"── {strat} ──")
        for item in items[:10]:  # 每种策略最多10条
            arrow = "🟢→" if item["to"] == "buy" else "🔴→" if item["to"] == "hold" else "→"
            lines.append(f"  {item['symbol']} {item['name']}: {item['from']} {arrow} {item['to']}")
        if len(items) > 10:
            lines.append(f"  ... 共{len(items)}条变更")

    body = "\n".join(lines)

    # 发送到Telegram
    try:
        from notify import push_report
        push_report("星盘日频信号", body)
        print("  📤 已推送到Telegram")
    except Exception as e:
        print(f"  ⚠️ 推送失败: {e}")


def _save_prev_signals():
    """把当前信号 Parquet 备份为上一次（用于下次对比）"""
    import shutil
    signals_dir = HUB.signals_dir()
    prev_dir = HUB.signals_prev_dir()
    try:
        prev_dir.mkdir(parents=True, exist_ok=True)
        for pq in signals_dir.glob("*.parquet"):
            shutil.copy2(pq, prev_dir / pq.name)
    except Exception:
        pass


def _load_prev_signals(strategy: str) -> list[dict] | None:
    """加载上一次的信号快照"""
    prev_path = HUB.signal_prev_path(strategy)
    if not prev_path.exists():
        return None
    try:
        df = HUB.read_parquet(prev_path)
        if "computed_at" in df.columns and len(df):
            latest_ts = df["computed_at"].max()
            df = df[df["computed_at"] == latest_ts]
        return df[["symbol", "signal"]].to_dict("records")
    except Exception:
        return None


if __name__ == '__main__':
    from data.cron_logger import cron_run
    with cron_run("compute_signals"):
        main()
