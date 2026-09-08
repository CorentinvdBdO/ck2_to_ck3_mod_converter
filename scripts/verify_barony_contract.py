#!/usr/bin/env python3
"""Verify the barony contract lane `titles-history` depends on, on a real run.

Usage:  uv run scripts/verify_barony_contract.py <out_mod_dir> [barony_set.csv]

Checks, all against generated files (no library imports, so it also validates
what actually landed on disk):

1. `docs/evidence/barony_set.csv` starts with the contract columns
   `county,barony,holding,built_date,seed_source,pixels,status` and every
   `status` is one of `placed`, `demoted`, `override`.
2. `map_data/definition.csv` has exactly one row per **placed** barony, and its
   `name` column is that barony's CK3 title id `b_<ck2 barony name>`.
3. No demoted barony has a province.
4. Barony title ids in `definition.csv` are unique, and every non-barony row
   keeps an uppercase CK2 slug (no stray `b_` rows).

Exit 0 when the contract holds, 1 otherwise. Also prints the province and
canvas counts, so a run report does not depend on scrollback.
"""

from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

CONTRACT_COLUMNS = [
    "county",
    "barony",
    "holding",
    "built_date",
    "seed_source",
    "pixels",
    "status",
]
PLACED = {"placed", "override"}
STATUSES = {"placed", "demoted", "override"}


def read_definition(path: Path) -> list[dict[str, str]]:
    """definition.csv is `id;r;g;b;name;x` with a `#` header line, ';'-separated."""
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        parts = line.split(";")
        if len(parts) < 5 or not parts[0].isdigit():
            continue
        # Vanilla and every TC open the file with the `0;0;0;0;x;x;` placeholder
        # row; it is not a province.
        if int(parts[0]) == 0:
            continue
        rows.append({"id": int(parts[0]), "name": parts[4]})
    return rows


def read_default_map(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    out = {}
    for key in ("sea_zones", "river_provinces", "lakes", "impassable_mountains"):
        out[key] = " ".join(re.findall(rf"^{key}\s*=\s*(.*)$", text, re.M))
    return out


def expand_ranges(spec: str) -> set[int]:
    ids: set[int] = set()
    for m in re.finditer(r"RANGE\s*\{\s*(\d+)\s+(\d+)\s*\}", spec):
        ids.update(range(int(m.group(1)), int(m.group(2)) + 1))
    body = re.sub(r"RANGE\s*\{[^}]*\}", " ", spec)
    ids.update(int(t) for t in re.findall(r"\b\d+\b", body))
    return ids


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__.strip())
        return 2
    out = Path(argv[1])
    repo = Path(__file__).resolve().parent.parent
    barony_set = Path(argv[2]) if len(argv) > 2 else repo / "docs/evidence/barony_set.csv"

    problems: list[str] = []

    with barony_set.open(newline="", encoding="utf-8") as fh:
        reader = csv.reader(fh)
        header = next(reader)
        rows = [r for r in reader if r]
    if header[: len(CONTRACT_COLUMNS)] != CONTRACT_COLUMNS:
        problems.append(
            f"barony_set.csv columns are {header[:7]}, contract wants {CONTRACT_COLUMNS}"
        )
    si = header.index("status")
    bi = header.index("barony")
    bad = {r[si] for r in rows} - STATUSES
    if bad:
        problems.append(f"barony_set.csv has status values outside the contract: {sorted(bad)}")

    placed = [r[bi] for r in rows if r[si] in PLACED]
    demoted = [r[bi] for r in rows if r[si] == "demoted"]
    if len(set(placed)) != len(placed):
        problems.append("barony_set.csv lists the same placed barony twice")

    definition = read_definition(out / "map_data/definition.csv")
    names = [r["name"] for r in definition]
    barony_rows = [n for n in names if n.startswith("b_")]
    if len(set(barony_rows)) != len(barony_rows):
        problems.append("definition.csv repeats a barony title id")
    if set(barony_rows) != set(placed):
        missing = sorted(set(placed) - set(barony_rows))[:5]
        extra = sorted(set(barony_rows) - set(placed))[:5]
        problems.append(
            f"definition.csv baronies != placed baronies "
            f"(missing {len(set(placed) - set(barony_rows))} e.g. {missing}; "
            f"extra {len(set(barony_rows) - set(placed))} e.g. {extra})"
        )
    still_placed = sorted(set(demoted) & set(barony_rows))
    if still_placed:
        problems.append(f"demoted baronies got a province: {still_placed[:5]}")
    lower_nonbarony = [n for n in names if not n.startswith("b_") and n != n.upper()]
    if lower_nonbarony:
        problems.append(f"non-barony rows are not uppercase slugs: {lower_nonbarony[:5]}")

    dm = read_default_map(out / "map_data/default.map")
    water = set()
    for key in ("sea_zones", "river_provinces", "lakes"):
        water |= expand_ranges(dm[key])
    impassable = expand_ranges(dm["impassable_mountains"])
    total = len(definition)

    print(f"out              {out}")
    print(f"definition rows  {total}")
    print(f"barony provinces {len(barony_rows)}")
    print(f"placed baronies  {len(placed)}   demoted {len(demoted)}")
    print(f"water provinces  {len(water)}   impassable {len(impassable)}")
    print(f"other land       {total - len(barony_rows) - len(water) - len(impassable)}")
    provinces_png = out / "map_data/provinces.png"
    if provinces_png.exists():
        with provinces_png.open("rb") as fh:
            fh.seek(16)
            w = int.from_bytes(fh.read(4), "big")
            h = int.from_bytes(fh.read(4), "big")
        print(f"canvas           {w} x {h}")

    if problems:
        print("\nCONTRACT BROKEN")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("\ncontract holds")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
