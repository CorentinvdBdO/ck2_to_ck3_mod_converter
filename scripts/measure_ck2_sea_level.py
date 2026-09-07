#!/usr/bin/env python
"""Measure the CK2 source map's own sea level from its topology bitmap.

The CK2 default is documented as 95/255, but a total conversion can paint its
topology however it likes, and the heightmap curve is pinned to this value - get
it wrong and the whole coastline moves.  So measure it: classify pixels as water
or land using ``provinces.bmp`` + ``definition.csv`` + ``default.map``'s sea
zones, then look at where the two topology histograms meet.

    uv run python scripts/measure_ck2_sea_level.py \
        --ck2-map-dir Faerun/Faerun/map \
        --out docs/evidence/ck2_sea_level.md
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image

from ck2ck3.map import ck2read, heightmap, provinces

Image.MAX_IMAGE_PIXELS = None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ck2-map-dir", required=True)
    ap.add_argument("--out", default="docs/evidence/ck2_sea_level.md")
    args = ap.parse_args()

    src = Path(args.ck2_map_dir)
    provs = ck2read.read_definitions(src / "definition.csv")
    dm = ck2read.read_default_map(src / "default.map")
    water_ids = dm.sea_ids()

    with Image.open(src / "provinces.bmp") as im:
        rgb = np.asarray(im.convert("RGB"))
    lookup = {(p.rgb[0] << 16) | (p.rgb[1] << 8) | p.rgb[2]: p.id for p in provs}
    ids, _ = provinces._keys_to_ids(provinces.rgb_key(rgb), lookup)

    with Image.open(src / "topology.bmp") as im:
        topo = np.asarray(im.convert("L"))

    m = heightmap.measure_sea_level(topo, ids, water_ids)

    water_mask = np.isin(ids, list(water_ids))
    land_mask = (ids > 0) & ~water_mask
    hist_w = np.bincount(topo[water_mask], minlength=256)
    hist_l = np.bincount(topo[land_mask], minlength=256)

    lines = [
        "# CK2 source sea level (measured)",
        "",
        f"Source: `{src}`  ·  script: `scripts/measure_ck2_sea_level.py`",
        "",
        "Method: classify every province pixel as water or land from",
        "`definition.csv` + the `sea_zones` ranges in `default.map`, then compare the",
        "`topology.bmp` histograms of the two sets. The coastline sits where they meet.",
        "",
        "| measure | value |",
        "|---|---|",
        f"| water pixels | {int(water_mask.sum()):,} |",
        f"| land pixels | {int(land_mask.sum()):,} |",
        f"| water median | {m['water_median']:.0f} |",
        f"| water 99th percentile | {m['water_p99']:.0f} |",
        f"| land 1st percentile | {m['land_p01']:.0f} |",
        f"| land median | {m['land_median']:.0f} |",
        f"| **suggested `ck2_sea_level`** | **{m['suggested_sea_level']:.0f}** |",
        "",
        "## Histogram around the boundary",
        "",
        "| topology value | water px | land px |",
        "|---|---|---|",
    ]
    lo = max(0, int(m["water_p99"]) - 6)
    hi = min(255, int(m["land_p01"]) + 6)
    for v in range(lo, hi + 1):
        lines.append(f"| {v} | {int(hist_w[v]):,} | {int(hist_l[v]):,} |")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    for k, v in m.items():
        print(f"{k:24s} {v:.2f}")
    print(f"-> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
