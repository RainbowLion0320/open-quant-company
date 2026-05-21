#!/usr/bin/env python3
"""
Cache cleanup — remove stale parquet files beyond retention.

安全策略:
  - 只清理 data/cache/ 目录 (派生/缓存数据)
  - 不碰 data/store/ 和 data/store/stock/ 等一级数据
  - 默认保留 90 天, 可通过 --days 调整
  - dry-run 模式 (默认): 只报告, 不删除

用法:
  python scripts/cleanup_cache.py              # dry-run
  python scripts/cleanup_cache.py --execute    # 真删
  python scripts/cleanup_cache.py --days 30    # 30天保留
  python scripts/cleanup_cache.py --dir api        # 指定 cache 子目录
"""
import sys, os, time, argparse
from pathlib import Path


from data.datahub import get_datahub

HUB = get_datahub()
CLEAN_DIRS = [
    HUB.cache_root / "api",
]


def _safe_clean_dir(raw: str | None) -> Path:
    if not raw:
        target = CLEAN_DIRS[0]
    else:
        raw_path = Path(raw)
        if not raw_path.is_absolute() and not str(raw_path).startswith("data/cache"):
            target = HUB.cache_root / raw_path
        else:
            target = HUB.resolve_path(raw)
    try:
        target.relative_to(HUB.cache_root)
    except ValueError as exc:
        raise SystemExit(f"--dir must stay inside cache root: {HUB.cache_root}") from exc
    return target


def _display_path(path: Path, project: Path) -> str:
    try:
        return str(path.relative_to(project))
    except ValueError:
        return str(path)


def main():
    parser = argparse.ArgumentParser(description="Cache cleanup")
    parser.add_argument("--days", type=int, default=90, help="Retention days (default 90)")
    parser.add_argument("--execute", action="store_true", help="Actually delete (default: dry-run)")
    parser.add_argument("--dir", type=str, help="Single directory to clean")
    args = parser.parse_args()

    project = Path(__file__).resolve().parent.parent
    dirs = [_safe_clean_dir(args.dir)] if args.dir else CLEAN_DIRS

    cutoff = time.time() - args.days * 86400
    total_files = 0
    total_size = 0
    deleted = 0

    for d in dirs:
        if not d.exists():
            continue
        stale = []
        keep_size = 0
        stale_size = 0
        scanned = 0

        for f in sorted(d.glob("*.parquet")):
            scanned += 1
            total_files += 1
            sz = f.stat().st_size
            total_size += sz
            if f.stat().st_mtime < cutoff:
                stale.append(f)
                stale_size += sz
            else:
                keep_size += sz

        if args.execute:
            for f in stale:
                f.unlink()
                deleted += 1
            action = "🗑 Deleted"
        else:
            action = "📋 Would delete"

        if stale:
            print(f"  {action} {len(stale)} files ({stale_size/1024/1024:.1f} MB) from {_display_path(d, project)}")
            print(f"    Keep: {scanned - len(stale)} files ({keep_size/1024/1024:.1f} MB)")
        else:
            print(f"  ✓ {_display_path(d, project)}: {scanned} files, no stale ({keep_size/1024/1024:.1f} MB)")

    if not args.execute:
        print(f"\n  总计: {total_files} 文件, {total_size/1024/1024:.0f} MB")
        print(f"  过期(>{args.days}d): {sum(1 for d in dirs if d.exists() for f in d.glob('*.parquet') if f.stat().st_mtime < cutoff)} 文件")
        print(f"  运行 --execute 执行删除")


if __name__ == "__main__":
    main()
