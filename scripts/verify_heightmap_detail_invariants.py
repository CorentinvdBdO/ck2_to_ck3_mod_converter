#!/usr/bin/env python3
"""Verify the heightmap-detail pass's invariants on a real generated mod.

Usage:  uv run scripts/verify_heightmap_detail_invariants.py <out_mod_dir>

Checks, entirely from files on disk (no import of the converter's own
land/water classification, so this is an independent check of what
`ck2ck3.map.heightmap_detail.apply` promises, docs/step_map_heightmap.md §3):

1. every land province (a `definition.csv` barony/land row not in
   `default.map`'s `sea_zones`/`lakes`/`river_provinces`) has every
   `heightmap.png` pixel of its colour strictly above the water level;
2. every water province (sea/lake/river-type, plus the padding ocean colour)
   has every pixel at or below the water level;
3. distinct 16-bit value count, reported for before/after comparison.

Exit 0 when every check holds, 1 otherwise.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None

WATER_LEVEL = 4883  # docs/map_scale.md §4; overridable via argv[2]


def read_definition(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        parts = line.split(";")
        if len(parts) < 5 or not parts[0].isdigit():
            continue
        pid = int(parts[0])
        if pid == 0:
            continue
        rows.append({
            "id": pid,
            "rgb": (int(parts[1]), int(parts[2]), int(parts[3])),
            "name": parts[4],
        })
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
    water_level = int(argv[2]) if len(argv) > 2 else WATER_LEVEL

    definition = read_definition(out / "map_data/definition.csv")
    dm = read_default_map(out / "map_data/default.map")
    water_ids = set()
    for key in ("sea_zones", "lakes", "river_provinces"):
        water_ids |= expand_ranges(dm[key])

    with (out / "map_data/provinces.png").open("rb") as fh:
        prov = np.asarray(Image.open(fh).convert("RGB"))
    with (out / "map_data/heightmap.png").open("rb") as fh:
        heights = np.asarray(Image.open(fh))
    if heights.dtype != np.uint16:
        print(f"heightmap.png is not 16-bit (got {heights.dtype})")
        return 1
    if prov.shape[:2] != heights.shape:
        print(
            f"provinces.png {prov.shape[:2]} and heightmap.png {heights.shape} "
            "are different sizes"
        )
        return 1

    key = (prov[..., 0].astype(np.int64) << 16) | (prov[..., 1].astype(np.int64) << 8) | prov[..., 2]

    problems: list[str] = []
    land_below = 0
    land_provinces_checked = 0
    water_above = 0
    water_provinces_checked = 0
    for row in definition:
        k = (row["rgb"][0] << 16) | (row["rgb"][1] << 8) | row["rgb"][2]
        mask = key == k
        if not mask.any():
            continue
        vals = heights[mask].astype(np.int64)
        is_water = row["id"] in water_ids
        if is_water:
            water_provinces_checked += 1
            bad = int((vals > water_level).sum())
            if bad:
                water_above += bad
                problems.append(
                    f"water province {row['id']} ({row['name']}): "
                    f"{bad}/{vals.size} px above water level {water_level} "
                    f"(max {int(vals.max())})"
                )
        else:
            land_provinces_checked += 1
            bad = int((vals <= water_level).sum())
            if bad:
                land_below += bad
                problems.append(
                    f"land province {row['id']} ({row['name']}): "
                    f"{bad}/{vals.size} px at or below water level {water_level} "
                    f"(min {int(vals.min())})"
                )

    distinct = int(np.unique(heights).size)
    print(f"out                     {out}")
    print(f"water level             {water_level}")
    print(f"land provinces checked  {land_provinces_checked}")
    print(f"water provinces checked {water_provinces_checked}")
    print(f"distinct height values  {distinct}")
    print(f"land px at/below water  {land_below}")
    print(f"water px above water    {water_above}")

    if problems:
        print("\nINVARIANT BROKEN")
        for p in problems[:20]:
            print(f"  - {p}")
        if len(problems) > 20:
            print(f"  ... and {len(problems) - 20} more")
        return 1
    print("\ninvariants hold")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
