#!/usr/bin/env python3
"""
一次性批计算：运行所有策略，结果存入 SQLite。

策略:
  buffett     — 巴菲特三层过滤器 (能力圈→护城河→安全边际)
  multifactor — 多因子打分 (质量40%+估值30%+技术15%+市场15%)
  cybernetic  — 控制论市场状态信号 (基于当前市场regime)

后续:
  每日 cron: 只更新价格敏感列 (safety_margin / dcf_value / current_price)
  财报季: 重新跑 buffett 全量

Usage:
  python scripts/compute_signals.py [--strategy buffett] [--limit N]
"""

import os, sys, json, time, argparse
from pathlib import Path
from datetime import datetime

# Proxy bypass
for k in list(os.environ.keys()):
    if k.lower() in ('http_proxy', 'https_proxy', 'all_proxy'):
        del os.environ[k]
os.environ['no_proxy'] = '*'

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

import pandas as pd
import numpy as np

from data.results_db import (
    save_buffett_results, save_strategy_signals,
    load_buffett_results, load_strategy_signals,
    get_buffett_meta, list_strategies,
)
from signals.ml_signals import compute_ml_signals as compute_ml


def _get_latest_price(symbol: str) -> float:
    """Return latest cached/refreshed close price, or 0 when unavailable."""
    try:
        from data.fetcher import get_stock_daily
        df = get_stock_daily(symbol)
        if df is None or len(df) == 0:
            return 0.0
        return float(df.sort_values("date").iloc[-1]["close"])
    except Exception:
        return 0.0


def compute_buffett(limit: int = 0) -> list[dict]:
    """运行巴菲特全量扫描，返回结果列表"""
    from data.symbols import CIRCLE_STOCKS, SYMBOL_INDUSTRY, SYMBOL_SECTOR, FALLBACK_SECTOR, SYMBOL_NAME
    from data.financials import get_buffett_inputs
    from buffett.filters import buffett_filter as bf

    symbols = list(CIRCLE_STOCKS)
    if limit and limit < len(symbols):
        symbols = symbols[:limit]

    results = []
    total = len(symbols)
    passed = 0

    for i, sym in enumerate(symbols):
        try:
            ind = SYMBOL_INDUSTRY.get(sym, "待分类")
            price = _get_latest_price(sym)
            inputs = get_buffett_inputs(sym, current_price=price, industry=ind)
            if not inputs or not inputs.get("roe_history"):
                continue

            r = bf(symbol=sym, name=SYMBOL_NAME.get(sym, sym), **inputs)
            passed_flag = "✅" in r.verdict.value if hasattr(r.verdict, 'value') else "通过" in str(r.verdict)

            results.append({
                "symbol": r.symbol,
                "name": r.name,
                "industry": r.industry,
                "sector": r.sector,
                "verdict": r.verdict.value if hasattr(r.verdict, 'value') else str(r.verdict),
                "score": r.score,
                "roe": round(r.avg_roe_5y * 100, 1),
                "gross_margin": round(r.avg_gross_margin_5y * 100, 1) if r.avg_gross_margin_5y > 0 else None,
                "net_margin": round(r.avg_net_margin_5y * 100, 1) if r.avg_net_margin_5y > 0 else None,
                "de": round(r.debt_equity_ratio, 1),
                "safety_margin": round(r.safety_margin_pct * 100, 1),
                "dcf_value": round(r.dcf_value, 1),
                "current_price": round(price, 2),
            })

            if passed_flag:
                passed += 1

        except Exception as e:
            pass  # skip problematic stocks

        if (i + 1) % 100 == 0:
            print(f"  Buffett [{i+1}/{total}] {passed} passed ...")

    print(f"  Buffett done: {len(results)} scanned, {passed} passed")
    return results


def compute_multifactor(limit: int = 0) -> list[dict]:
    """运行多因子打分"""
    from data.symbols import CIRCLE_STOCKS, SYMBOL_INDUSTRY, SYMBOL_NAME
    from signals.multifactor import MultiFactorScorer
    from cybernetics.orchestrator import QuantOrchestrator
    from buffett.filters import buffett_filter as bf

    # 先检测市场状态
    orch = QuantOrchestrator()
    try:
        snapshot = orch.detect()
        regime = snapshot.regime.value if hasattr(snapshot.regime, 'value') else str(snapshot.regime)
    except Exception:
        regime = "sideways"

    scorer = MultiFactorScorer(regime=regime)
    symbols = list(CIRCLE_STOCKS)
    if limit and limit < len(symbols):
        symbols = symbols[:limit]

    results = []
    total = len(symbols)

    for i, sym in enumerate(symbols):
        try:
            # 从已缓存巴菲特结果拿基础数据
            name = SYMBOL_NAME.get(sym, sym)
            ind = SYMBOL_INDUSTRY.get(sym, "待分类")

            # 简单多因子：基于巴菲特评分 + 行业 + regime
            from data.financials import get_buffett_inputs
            price = _get_latest_price(sym)
            inputs = get_buffett_inputs(sym, current_price=price, industry=ind)
            if not inputs:
                continue
            br = bf(symbol=sym, name=name, **inputs)

            tech = _get_technical_factors(sym)
            factors = {
                "buffett_score": br.score if br.score > 0 else _estimate_buffett_score(inputs),
                "safety_margin": max(0, br.safety_margin_pct),
                "roe_5y": (sum(inputs.get("roe_history", [0])[-5:]) / max(1, len(inputs.get("roe_history", [0])[-5:]))) if inputs.get("roe_history") else 0,
                "roe_trend": _roe_trend(inputs.get("roe_history", [])),
                "momentum_1m": tech["momentum_1m"],
                "momentum_3m": tech["momentum_3m"],
                "volatility": tech["volatility"],
                "sector": inputs.get("sector", ""),
            }

            score = scorer.score(factors)
            signal = "buy" if score >= 45 else "hold"

            results.append({
                "symbol": sym, "name": name, "industry": ind,
                "score": round(score, 1), "signal": signal,
                "detail": {
                    "regime": regime,
                    "quality": round(score * 0.40, 1),
                    "valuation": round(score * 0.30, 1),
                    "technical": round(score * 0.15, 1),
                    "market": round(score * 0.15, 1),
                }
            })

        except Exception:
            pass

        if (i + 1) % 100 == 0:
            buys = sum(1 for r in results if r["signal"] == "buy")
            print(f"  Multifactor [{i+1}/{total}] {buys} buys ...")

    buys = sum(1 for r in results if r["signal"] == "buy")
    print(f"  Multifactor done: {len(results)} scored, {buys} buys (regime={regime})")
    return results


def _estimate_buffett_score(inputs: dict) -> float:
    """从财务指标估算巴菲特评分 (0-100)"""
    roe = (sum(inputs.get("roe_history", [0])[-5:]) / max(1, len(inputs.get("roe_history", [0])[-5:])))
    score = min(100, roe * 500)  # 15% ROE → 75分
    return score


def _roe_trend(history: list) -> str:
    if len(history) < 3:
        return "flat"
    recent = history[-3:]
    if recent[-1] > recent[0] * 1.05:
        return "up"
    elif recent[-1] < recent[0] * 0.95:
        return "down"
    return "flat"


def _get_technical_factors(symbol: str) -> dict:
    """从行情数据计算动量 + 波动率"""
    try:
        from data.fetcher import get_stock_daily
        from signals.multifactor import compute_momentum, compute_volatility
        df = get_stock_daily(symbol)
        if df is None or len(df) < 63:
            return {"momentum_1m": 0, "momentum_3m": 0, "volatility": 0.30}
        mom = compute_momentum(df, [21, 63])
        vol = compute_volatility(df, 20)
        return {"momentum_1m": mom.get(21, 0), "momentum_3m": mom.get(63, 0), "volatility": vol}
    except Exception:
        return {"momentum_1m": 0, "momentum_3m": 0, "volatility": 0.30}


def compute_cybernetic(limit: int = 0) -> list[dict]:
    """控制论市场状态信号 — 基于当前市场 regime 给板块轮动建议"""
    from data.symbols import CIRCLE_STOCKS, SYMBOL_INDUSTRY, SYMBOL_NAME, SYMBOL_SECTOR, FALLBACK_SECTOR
    from cybernetics.orchestrator import QuantOrchestrator

    orch = QuantOrchestrator()
    try:
        snapshot = orch.detect()
        regime = snapshot.regime.value if hasattr(snapshot.regime, 'value') else str(snapshot.regime)
        params = orch.get_params()
    except Exception:
        regime = "sideways"
        params = {"position_pct": 0.15, "max_positions": 5, "stop_loss": -0.05}

    # 板块轮动逻辑
    regime_sectors = {
        "bull": ["证券", "电子", "计算机", "电力设备", "国防军工"],
        "bear": ["银行", "公用事业", "交通运输", "食品饮料", "医药生物"],
        "sideways": ["银行", "公用事业", "煤炭", "石油石化", "建筑装饰"],
    }
    favored = regime_sectors.get(regime, regime_sectors["sideways"])

    symbols = list(CIRCLE_STOCKS)
    if limit and limit < len(symbols):
        symbols = symbols[:limit]

    results = []
    for sym in symbols:
        ind = SYMBOL_INDUSTRY.get(sym, "待分类")
        sec = SYMBOL_SECTOR.get(sym, FALLBACK_SECTOR)
        name = SYMBOL_NAME.get(sym, sym)

        if ind in favored:
            score = 75.0
            signal = "buy"
        else:
            score = 40.0
            signal = "hold"

        results.append({
            "symbol": sym, "name": name, "industry": ind,
            "score": score, "signal": signal,
            "detail": {
                "regime": regime,
                "favored_sectors": favored,
                "position_pct": params.get("position_pct", 0.15),
                "max_positions": params.get("max_positions", 5),
            }
        })

    buys = sum(1 for r in results if r["signal"] == "buy")
    print(f"  Cybernetic done: {len(results)} signals, {buys} buys (regime={regime})")
    return results


def main():
    from data.registry import get_enabled_strategies, list_strategy_names

    parser = argparse.ArgumentParser()
    all_names = list_strategy_names()
    parser.add_argument('--strategy', default='all', choices=['all'] + all_names)
    parser.add_argument('--limit', type=int, default=0, help='Limit to N stocks (0=all)')
    args = parser.parse_args()

    start = time.time()
    print(f"Compute signals: strategy={args.strategy}")

    from data.results_db import init
    from data.db import reset_db
    reset_db()  # 清除可能持有的只读连接，获取写锁
    init()

    # ── 策略→计算函数映射 ──
    _compute_map = {
        "buffett": (compute_buffett, save_buffett_results, get_buffett_meta, "buffett"),
        "multifactor": (compute_multifactor, None, None, "multifactor"),
        "cybernetic": (compute_cybernetic, None, None, "cybernetic"),
        "ml_lgbm": (compute_ml, None, None, "ml_lgbm"),
    }

    for s in get_enabled_strategies():
        name = s["name"]
        label = s["label"]

        if args.strategy != 'all' and args.strategy != name:
            continue

        entry = _compute_map.get(name)
        if entry is None:
            print(f"\n── {label} ──\n  跳过: 无计算函数")
            continue

        compute_fn, save_fn, meta_fn, sig_name = entry
        print(f"\n── {label} ──")
        results = compute_fn(limit=args.limit)

        # 特殊处理: buffett 同时写入 buffett_results 和 strategy_signals
        if save_fn:
            save_fn(results)
            if meta_fn:
                meta = meta_fn()
                print(f"  Saved: {meta['total']} stocks, {meta['passed']} passed")

        # 写入 strategy_signals
        if name == "buffett":
            signals = []
            for r in results:
                passed = "通过" in r["verdict"] or "✅" in r["verdict"]
                signals.append({
                    "symbol": r["symbol"], "name": r["name"], "industry": r["industry"],
                    "score": r["score"], "signal": "buy" if passed else "hold",
                    "detail": {"verdict": r["verdict"], "safe_margin": r["safety_margin"], "roe": r["roe"]}
                })
        else:
            signals = results  # multifactor/cybernetic already return signal format
        save_strategy_signals(sig_name, signals)

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
        import yaml
        cfg_path = PROJECT / "config" / "settings.yaml"
        with open(cfg_path) as f:
            cfg = yaml.safe_load(f)
        notify_cfg = cfg.get("trading", {}).get("notification", {})
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
    lines = [f"📡 Quant Agent 信号变更 ({datetime.now().strftime('%m/%d %H:%M')})", ""]
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
        push_report("Quant Agent 日频信号", body)
        print("  📤 已推送到Telegram")
    except Exception as e:
        print(f"  ⚠️ 推送失败: {e}")


def _save_prev_signals():
    """把当前信号备份为上一次（用于下次对比）"""
    import shutil
    db_path = PROJECT / "data" / "quant_results.db"
    prev_path = PROJECT / "data" / "quant_results_prev.db"
    try:
        shutil.copy(db_path, prev_path)
    except Exception:
        pass


def _load_prev_signals(strategy: str) -> list[dict] | None:
    """加载上一次的信号快照"""
    prev_path = PROJECT / "data" / "quant_results_prev.db"
    if not prev_path.exists():
        return None
    try:
        import sqlite3
        db = sqlite3.connect(str(prev_path))
        db.row_factory = sqlite3.Row
        rows = db.execute(
            "SELECT symbol, name, signal FROM strategy_signals WHERE strategy=?",
            (strategy,)
        ).fetchall()
        db.close()
        return [{"symbol": r["symbol"], "signal": r["signal"]} for r in rows]
    except Exception:
        return None


if __name__ == '__main__':
    main()
