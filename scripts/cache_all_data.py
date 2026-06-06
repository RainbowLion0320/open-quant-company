"""
批量数据预缓存脚本 — Phase 4.1

一次性预拉全部新增数据维度到本地 Parquet 缓存。
后续 PIT 特征构建和 LLM 因子发现直接读本地文件。

用法:
  python scripts/cache_all_data.py --moneyflow --holders --macro
  python scripts/cache_all_data.py --all  # 全部拉取
"""
import sys
import time
from pathlib import Path


from data.market.symbols import CIRCLE_STOCKS
from data.ingestion.fetchers.moneyflow import MoneyflowFetcher
from data.ingestion.fetchers.holders import HolderFetcher
from data.ingestion.fetchers.macro import MacroFetcher, MACRO_INDICATORS


def cache_moneyflow(limit: int = 0):
    """拉取全部股票资金流向。limit=0 → 全量1000只"""
    symbols = CIRCLE_STOCKS[:limit] if limit > 0 else CIRCLE_STOCKS
    print(f"\n{'='*60}")
    print(f"💰 资金流向 — {len(symbols)} 只股票")
    print(f"{'='*60}")

    mf = MoneyflowFetcher()
    results = mf.batch_fetch(symbols)
    print(f"  完成: {len(results)}/{len(symbols)} 只有数据")
    return results


def cache_holders(limit: int = 0):
    """拉取全部股票股东户数。limit=0 → 全量1000只"""
    symbols = CIRCLE_STOCKS[:limit] if limit > 0 else CIRCLE_STOCKS
    print(f"\n{'='*60}")
    print(f"👥 股东户数 — {len(symbols)} 只股票")
    print(f"{'='*60}")

    hf = HolderFetcher()
    results = hf.batch_fetch(symbols)
    print(f"  完成: {len(results)}/{len(symbols)} 只有数据")
    return results


def cache_macro():
    """拉取全部宏观经济指标"""
    print(f"\n{'='*60}")
    print(f"🌐 宏观经济指标 — {len(MACRO_INDICATORS)} 个指标")
    print(f"{'='*60}")

    mf = MacroFetcher()
    results = mf.fetch_all()
    print(f"  完成: {len(results)}/{len(MACRO_INDICATORS)} 个指标")
    return results


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="批量预缓存数据")
    ap.add_argument("--all", action="store_true", help="拉取全部数据")
    ap.add_argument("--moneyflow", action="store_true", help="拉取资金流向")
    ap.add_argument("--holders", action="store_true", help="拉取股东户数")
    ap.add_argument("--macro", action="store_true", help="拉取宏观经济")
    ap.add_argument("--limit", type=int, default=0, help="限制股票数量 (0=全部)")
    args = ap.parse_args()

    if args.all:
        args.moneyflow = args.holders = args.macro = True

    total_start = time.time()

    if args.moneyflow:
        cache_moneyflow(limit=args.limit)

    if args.holders:
        cache_holders(limit=args.limit)

    if args.macro:
        cache_macro()

    elapsed = time.time() - total_start
    print(f"\n{'='*60}")
    print(f"🎉 全部完成 — 耗时 {elapsed/60:.1f} 分钟")
    print(f"{'='*60}")
