"""Human-input tables: `overrides/*.csv` in the converter repository.

`docs/PROJECT.md`: "Anything that needs human judgement takes an **override
file** as input; defaults are heuristic." This module is the single reader for
those files so every step resolves them the same way and a missing table is a
warning, never a crash.

Location: `<repo root>/overrides/`, derived from the config file's path
(`configs/faerun.toml` → repo root), so the CLI behaves the same from any
directory. Comment lines (`#`) and blank lines are skipped; the first
non-comment line is the header.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterator

from .config import Config


def overrides_dir(config: Config) -> Path:
    """`<repo root>/overrides`, from the config file's own location."""
    return config.path.resolve().parent.parent / "overrides"


def read_rows(config: Config, name: str) -> list[dict[str, str]]:
    """Every row of `overrides/<name>`, comments skipped. `[]` when absent."""
    path = overrides_dir(config) / name
    if not path.is_file():
        return []
    return list(_rows(path))


def read_map(
    config: Config, name: str, key: str, value: str
) -> dict[str, str]:
    """Two columns of `overrides/<name>` as a dict; blank values are dropped."""
    out: dict[str, str] = {}
    for row in read_rows(config, name):
        k = (row.get(key) or "").strip()
        v = (row.get(value) or "").strip()
        if k and v:
            out[k] = v
    return out


def _rows(path: Path) -> Iterator[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        lines = [
            line
            for line in handle
            if line.strip() and not line.lstrip().startswith("#")
        ]
    yield from csv.DictReader(lines)
