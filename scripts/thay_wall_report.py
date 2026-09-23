#!/usr/bin/env python3
"""Lane `thay-relief`: the wall-concentration metric table, docs §2h ii.

For each region (`thay`, `spine`) and each map (the plain rescale, the
shipped build-17 `heightmap.png`, and the current lane output), writes one
row of `scripts/relief_pits_common.wall_stats`: the axis-aligned/diagonal
giant-step ratio at k in {2, 3, 5} risers, and the drop-concentration
percentiles at the source's own cliff pixels.

Usage:
  uv run python scripts/thay_wall_report.py [--ours PNG] [--out CSV]
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import relief_pits_common as P  # noqa: E402
import relief_sharp_common as C  # noqa: E402
import thay_render as R  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--ours",
        default="/home/cvdbdo/git/paradox/ck3/wt/_out/thay-relief/map_data/heightmap.png",
    )
    ap.add_argument("--out", default=str(C.ROOT / "docs/evidence/thay_relief/wall_stats.csv"))
    args = ap.parse_args()

    ours_full = C.load16(Path(args.ours))
    build17_full = C.load16(C.LIVE_MOD / "map_data/heightmap.png")

    rows = []
    for region in R.REGIONS:
        ys, xs = R.crop_slices(region)
        base = C.plain_rescale_canvas()[ys, xs]
        build17 = build17_full[ys, xs]
        ours = ours_full[ys, xs]
        land = build17 > C.WATER_LEVEL
        for label, arr in (("source", base), ("build17", build17), ("ours", ours)):
            row = P.wall_stats(base, arr, land)
            row = {"region": region, "map": label, **row}
            rows.append(row)
            print(f"{region:6s} {label:8s} axis/diag k2={row['axis_over_diag_k2']:.2f} "
                  f"k5={row['axis_over_diag_k5']:.2f}  drop-conc p50/p95/max="
                  f"{row['drop_concentration_p50']:.2f}/"
                  f"{row['drop_concentration_p95']:.2f}/"
                  f"{row['drop_concentration_max']:.2f}")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    keys: list[str] = []
    for r in rows:
        for k in r:
            if k not in keys:
                keys.append(k)
    with out.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)
    print("wrote", out)


if __name__ == "__main__":
    main()
