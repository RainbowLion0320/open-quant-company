#!/usr/bin/env python3
"""Bump the project release version from the pyproject.toml source of truth.

Usage:
    scripts/bump_version.py 2.1.0

The canonical version lives in pyproject.toml. This script updates derived
display references that cannot read pyproject.toml at render time.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SEMVER = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")


def _replace_once(path: Path, pattern: str, replacement: str) -> None:
    text = path.read_text(encoding="utf-8")
    new_text, count = re.subn(pattern, replacement, text, count=1, flags=re.MULTILINE)
    if count != 1:
        raise RuntimeError(f"Expected one version occurrence in {path}")
    path.write_text(new_text, encoding="utf-8")


def bump(version: str) -> None:
    if not SEMVER.match(version):
        raise SystemExit(f"Invalid version '{version}'. Expected semantic version like 2.1.0")

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


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        raise SystemExit("Usage: scripts/bump_version.py <version>")
    bump(argv[1])
    print(f"Bumped project version to {argv[1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
