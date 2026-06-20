#!/usr/bin/env python3
"""Bump the project release version from the pyproject.toml source of truth.

Usage:
    scripts/bump_version.py 2026.6.20.2

The canonical version lives in pyproject.toml. This script updates derived
display references that cannot read pyproject.toml at render time.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
CALVER = re.compile(r"^\d{4}\.\d{1,2}\.\d{1,2}\.\d+$")


def _replace_once(path: Path, pattern: str, replacement: str) -> None:
    text = path.read_text(encoding="utf-8")
    new_text, count = re.subn(pattern, replacement, text, count=1, flags=re.MULTILINE)
    if count != 1:
        raise RuntimeError(f"Expected one version occurrence in {path}")
    path.write_text(new_text, encoding="utf-8")


def _replace_once_or_append(path: Path, pattern: str, replacement: str) -> None:
    text = path.read_text(encoding="utf-8")
    new_text, count = re.subn(pattern, replacement, text, count=1, flags=re.MULTILINE)
    if count == 0:
        suffix = "" if text.endswith("\n") else "\n"
        new_text = f"{text}{suffix}{replacement}\n"
    elif count != 1:
        raise RuntimeError(f"Expected at most one version occurrence in {path}")
    path.write_text(new_text, encoding="utf-8")


def bump(version: str) -> None:
    match = CALVER.match(version)
    if not match:
        raise SystemExit(f"Invalid version '{version}'. Expected calendar version like 2026.6.20.2")
    year, month, day, _sequence = version.split(".")
    release_date = f"{int(year):04d}-{int(month):02d}-{int(day):02d}"

    _replace_once(
        ROOT / "pyproject.toml",
        r'^version = "[^"]+"$',
        f'version = "{version}"',
    )
    _replace_once(
        ROOT / "README.md",
        r"version-[^-]+-orange",
        f"version-{version}-orange",
    )
    _replace_once(
        ROOT / "README.en.md",
        r"version-[^-]+-orange",
        f"version-{version}-orange",
    )
    _replace_once(
        ROOT / "CITATION.cff",
        r'^version: "[^"]+"$',
        f'version: "{version}"',
    )
    _replace_once_or_append(
        ROOT / "CITATION.cff",
        r'^date-released: "[^"]+"$',
        f'date-released: "{release_date}"',
    )


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        raise SystemExit("Usage: scripts/bump_version.py <version>")
    bump(argv[1])
    print(f"Bumped project version to {argv[1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
