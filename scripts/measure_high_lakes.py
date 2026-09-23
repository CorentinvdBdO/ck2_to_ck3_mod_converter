#!/usr/bin/env python3
"""Lane `thay-relief`: which CK2 lake provinces sit high enough on a plateau
that CK3's single global water level turns them into a vertical shaft.

**Not measurable from the lake's own pixels.** The first version of this
script tried that (CK2 `topology.bmp` median under the lake's own colour)
and every one of Faerûn's 95 lakes came back within 0.1 riser of each other
(`verified`): CK2 paints a lake's own bed near sea level regardless of what
is around it (Lake Thaylambar is raw bytes 85-92 of 255, whatever the
plateau), so the lake's own pixels carry no information about how high it
sits. What does carry that information is the **land around it** -- exactly
what the brief asked for.

**The measurement.** For every CK2 lake province (`Ck2DefaultMap.lake_ids()`,
never `sea_zones` proper or `major_rivers`): dilate its CK3-canvas footprint
by `--ring-px`, intersect with land (any pixel not itself water, by the
finished mod's own province classification -- never `plain_rescale >
water_level`, CLAUDE.md), and take the median of the **plain rescale**
elevation there (not the finished `heightmap.png`: the detail pass has
already run its own bound and coast damping by then, and this measurement
wants the CK2 author's own drawn shore, undamped). "Risers above the water
level" is that median minus `ck3_water_level`, divided by 277.0125 (one CK2
8-bit quantisation step).

Needs a generated mod (`--mod`, default `wt/_out/thay-relief`) for the
province raster and `docs/evidence/province_id_map.csv` (written by every
`map` run) for the CK2<->CK3 id and "kind" lookup.

Two outputs:
* `docs/evidence/lake_to_land_candidates.csv` -- every lake at or above
  `--min-risers`, whole canvas, `region` flagged `thay` when its centroid
  falls inside the Thay window (+margin) this lane's renders use.
* stdout -- the riser distribution, so `--min-risers` is a measured choice.

`scripts/propose_lake_to_land_csv.py` turns this into
`overrides/lake_to_land.csv` (Thay only, pre-filled) and
`docs/evidence/lake_to_land_proposed.csv` (everywhere else, proposals).

Usage:
  uv run python scripts/measure_high_lakes.py [--mod DIR] [--ring-px N]
      [--min-risers N] [--out docs/evidence/lake_to_land_candidates.csv]
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.ndimage import binary_dilation

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import relief_sharp_common as C  # noqa: E402

Image.MAX_IMAGE_PIXELS = None

ROOT = Path(__file__).resolve().parents[1]

#: the Thay window this lane's renders use, canvas px (y0, x0, y1, x1), +margin
THAY_WINDOW = (1583 - 100, 4752 - 100, 2222 + 100, 5311 + 100)

DEFAULT_MIN_RISERS = 10.0
DEFAULT_RING_PX = 15


def read_province_id_map(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--mod", default="/home/cvdbdo/git/paradox/ck3/wt/_out/thay-relief"
    )
    ap.add_argument("--id-map", default=str(ROOT / "docs/evidence/province_id_map.csv"))
    ap.add_argument("--ring-px", type=int, default=DEFAULT_RING_PX)
    ap.add_argument("--min-risers", type=float, default=DEFAULT_MIN_RISERS)
    ap.add_argument("--out", default=str(ROOT / "docs/evidence/lake_to_land_candidates.csv"))
    args = ap.parse_args()

    mod = Path(args.mod)
    id_rows = read_province_id_map(Path(args.id_map))
    lake_rows = [r for r in id_rows if r["kind"] == "lake" and r["ck2_id"]]
    print(f"{len(lake_rows)} CK3 lake provinces in {args.id_map}")

    rgb_to_ck2: dict[tuple[int, int, int], tuple[int, str]] = {}
    for r in lake_rows:
        rgb_to_ck2[(int(r["r"]), int(r["g"]), int(r["b"]))] = (int(r["ck2_id"]), r["name"])

    with Image.open(mod / "map_data/provinces.png") as im:
        prov = np.asarray(im.convert("RGB"))
    plain = C.plain_rescale_canvas()
    if plain.shape != prov.shape[:2]:
        raise SystemExit(f"plain rescale {plain.shape} != provinces.png {prov.shape[:2]}")

    # water everywhere, from the finished mod's own classification (never a
    # height threshold, CLAUDE.md)
    finished = C.load16(mod / "map_data/heightmap.png")
    water_mask_all = finished <= C.WATER_LEVEL
    del finished

    key = (prov[..., 0].astype(np.int64) << 16
           | prov[..., 1].astype(np.int64) << 8 | prov[..., 2])

    rows: list[dict] = []
    all_risers: list[float] = []
    y0, x0, y1, x1 = THAY_WINDOW
    for rgb, (ck2_id, name) in rgb_to_ck2.items():
        k = rgb[0] << 16 | rgb[1] << 8 | rgb[2]
        mask = key == k
        n = int(mask.sum())
        if n == 0:
            continue
        ring = binary_dilation(mask, iterations=args.ring_px) & ~mask & ~water_mask_all
        if not ring.any():
            continue
        land_levels = plain[ring].astype(np.float64)
        med = float(np.median(land_levels))
        risers = (med - C.WATER_LEVEL) / C.QUANT
        all_risers.append(risers)
        ys, xs = np.nonzero(mask)
        cy, cx = float(ys.mean()), float(xs.mean())
        in_thay = (y0 <= cy <= y1) and (x0 <= cx <= x1)
        # every Thay lake is in the candidates list regardless of --min-risers:
        # the render evidence already implicates them; --min-risers gates
        # only the whole-canvas *proposals* scripts/propose_lake_to_land_csv.py
        # writes for everywhere else.
        if risers >= args.min_risers or in_thay:
            rows.append({
                "ck2_id": ck2_id,
                "name": name,
                "pixel_count": n,
                "ring_px": args.ring_px,
                "ring_land_pixel_count": int(ring.sum()),
                "shore_median_level": round(med, 1),
                "risers_above_water": round(risers, 2),
                "canvas_centroid_y": round(cy, 1),
                "canvas_centroid_x": round(cx, 1),
                "region": "thay" if in_thay else "other",
            })

    rows.sort(key=lambda r: -r["risers_above_water"])
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=[
            "ck2_id", "name", "pixel_count", "ring_px", "ring_land_pixel_count",
            "shore_median_level", "risers_above_water",
            "canvas_centroid_y", "canvas_centroid_x", "region",
        ])
        w.writeheader()
        w.writerows(rows)

    arr = np.array(all_risers)
    print(f"{arr.size} lakes measured (ring {args.ring_px} px)")
    for p in (50, 75, 90, 95, 99):
        print(f"  risers p{p}: {np.percentile(arr, p):.1f}")
    print(f"  max: {arr.max():.1f}" if arr.size else "  (empty)")
    print(f"{len(rows)} at or above --min-risers {args.min_risers} "
          f"({sum(1 for r in rows if r['region'] == 'thay')} in the Thay window)")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
