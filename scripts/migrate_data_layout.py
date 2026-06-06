"""Migrate legacy runtime files from data/ into var/.

The script is intentionally conservative: it never overwrites an existing
target and writes an auditable manifest for apply runs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path


@dataclass
class MigrationItem:
    source: str
    target: str
    kind: str
    status: str = "planned"
    size_bytes: int = 0
    sha256: str = ""


def build_plan(root: Path) -> list[MigrationItem]:
    data = root / "data"
    var = root / "var"
    items: list[MigrationItem] = []

    def add(source: Path, target: Path, kind: str) -> None:
        if source.exists():
            items.append(
                MigrationItem(
                    source=str(source),
                    target=str(target),
                    kind=kind,
                    size_bytes=_size_bytes(source),
                    sha256=_sha256(source) if source.is_file() else "",
                )
            )

    add(data / "store", var / "store", "directory")
    add(data / "cache", var / "cache", "directory")
    add(data / "tournament", var / "artifacts" / "tournaments", "directory")

    for pattern in ("price_matrix_*.pkl", "backtest_price_matrix_*.pkl", "backtest_valuation_matrix_*.pkl"):
        for source in sorted(data.glob(pattern)):
            add(source, var / "cache" / "backtest" / source.name, "file")

    for source in sorted(data.glob("backtest_*.pkl")):
        if source.name.startswith(("backtest_price_matrix_", "backtest_valuation_matrix_")):
            continue
        add(source, var / "artifacts" / "backtests" / source.name, "file")

    models = data / "models"
    if models.exists():
        for source in sorted(models.iterdir()):
            if source.is_file() and (source.suffix in {".pkl", ".json", ".jsonl"} or source.name == "report.md"):
                add(source, var / "artifacts" / "models" / source.name, "file")

    for source in sorted(data.glob("quant_results*.db")) + sorted(data.glob("quant_results*.duckdb")):
        add(source, var / "db" / source.name, "file")

    add(data / ".financials_progress.json", var / "cache" / "runtime" / "financials_progress.json", "file")
    return _dedupe(items)


def apply_plan(items: list[MigrationItem], *, root: Path) -> Path:
    for item in items:
        source = Path(item.source)
        target = Path(item.target)
        if not source.exists():
            item.status = "missing"
            continue
        if source.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            item.status = "moved" if _merge_directory(source, target) else "conflict"
            continue
        if target.exists():
            item.status = "conflict"
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(target))
        item.status = "moved"

    _remove_empty_legacy_dirs(root / "data")
    manifest_dir = root / "var" / "migration"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = manifest_dir / f"data-layout-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    manifest_path.write_text(json.dumps(_payload(items, manifest_path), ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=Path(__file__).resolve().parents[1], type=Path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON summary")
    args = parser.parse_args(argv)

    root = args.root.expanduser().resolve()
    items = build_plan(root)
    manifest_path: Path | None = None
    if args.apply:
        manifest_path = apply_plan(items, root=root)
    else:
        for item in items:
            item.status = "planned"

    payload = _payload(items, manifest_path)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"mode={'apply' if args.apply else 'dry-run'} items={len(items)}")
        for item in items:
            print(f"{item.status:8} {item.source} -> {item.target}")
        if manifest_path:
            print(f"manifest={manifest_path}")
    return 0


def _payload(items: list[MigrationItem], manifest_path: Path | None) -> dict:
    return {
        "manifest_path": str(manifest_path) if manifest_path else "",
        "items": [asdict(item) for item in items],
    }


def _dedupe(items: list[MigrationItem]) -> list[MigrationItem]:
    seen: set[tuple[str, str]] = set()
    out: list[MigrationItem] = []
    for item in items:
        key = (item.source, item.target)
        if key not in seen:
            out.append(item)
            seen.add(key)
    return out


def _size_bytes(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _remove_empty_legacy_dirs(data_root: Path) -> None:
    for rel in ("models", "tournament", "cache", "store"):
        path = data_root / rel
        if not path.exists() or not path.is_dir():
            continue
        for child in sorted(path.rglob("*"), reverse=True):
            if child.is_dir():
                try:
                    child.rmdir()
                except OSError:
                    pass
        try:
            path.rmdir()
        except OSError:
            pass


def _merge_directory(source: Path, target: Path) -> bool:
    """Merge source into target without overwriting existing files."""
    had_conflict = False
    for child in sorted(source.iterdir()):
        destination = target / child.name
        if child.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
            if not _merge_directory(child, destination):
                had_conflict = True
            continue
        if destination.exists():
            had_conflict = True
            continue
        shutil.move(str(child), str(destination))
    try:
        source.rmdir()
    except OSError:
        had_conflict = True
    return not had_conflict


if __name__ == "__main__":
    raise SystemExit(main())
