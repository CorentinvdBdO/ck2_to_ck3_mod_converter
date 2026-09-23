#!/usr/bin/env python3
"""Lane `thay-relief`: which CK2 river provinces sit high enough on a
plateau that CK3's global water level cuts them as a canyon, not a river in
a valley.

The coordinator's §2h (d) diagnosis: Thay's remaining closed loop is five
CK2 river provinces (`RIVER_MURGHOL` and neighbours), 2-4 px wide, pinned
flat by `heightmap_detail.apply`'s water-province clamp. Every one of their
own `topology.bmp` pixels is a flat 92 of 255 -- CK2's sea-level anchor,
exactly like the lakes (`scripts/measure_high_lakes.py`'s own finding) -- so
this measures the same way: a ring of *surrounding land*, never the river
province's own pixels.

Two outputs, the same shape as `measure_high_lakes.py`:
* `docs/evidence/river_valley_candidates.csv` -- every river province at or
  above `--min-risers`, whole canvas, `region` flagged `thay` inside this
  lane's Thay window (+margin).
* stdout -- the riser distribution.

`scripts/propose_river_valleys_csv.py` turns this into
`overrides/river_valleys.csv` (Thay pre-filled, `valley`) and
`docs/evidence/river_valleys_proposed.csv` (everywhere else, proposals).

Usage:
  uv run python scripts/measure_high_rivers.py [--mod DIR] [--ring-px N]
      [--min-risers N] [--out docs/evidence/river_valley_candidates.csv]
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
THAY_WINDOW = (1583 - 100, 4752 - 100, 2222 + 100, 5311 + 100)
#: the coordinator's own five named provinces (§2h (d)) -- always treated as
#: "Thay" regardless of centroid geometry, the same "the render put it here,
#: not the threshold" rule §2h(c) already uses for the lakes. Names, not
#: ids: CK2 ids are opaque, and this makes the list checkable by eye.
#: Upper Rauthenflow River's own centroid sits ~14-64 px past even a
#: widened +150 px window (`verified`), which is exactly the case this
#: exists for.
ALWAYS_THAY_NAMES = {
    "river murghol", "lower river murghol", "river umber",
    "upper rauthenflow river", "lower rauthenflow river",
}
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
    ap.add_argument("--out", default=str(ROOT / "docs/evidence/river_valley_candidates.csv"))
    args = ap.parse_args()

    mod = Path(args.mod)
    id_rows = read_province_id_map(Path(args.id_map))
    river_rows = [r for r in id_rows if r["kind"] == "river" and r["ck2_id"]]
    print(f"{len(river_rows)} CK3 river provinces in {args.id_map}")

    rgb_to_ck2: dict[tuple[int, int, int], tuple[int, str]] = {}
    for r in river_rows:
        rgb_to_ck2[(int(r["r"]), int(r["g"]), int(r["b"]))] = (int(r["ck2_id"]), r["name"])

    with Image.open(mod / "map_data/provinces.png") as im:
        prov = np.asarray(im.convert("RGB"))
    plain = C.plain_rescale_canvas()
    if plain.shape != prov.shape[:2]:
        raise SystemExit(f"plain rescale {plain.shape} != provinces.png {prov.shape[:2]}")

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
        in_thay = ((y0 <= cy <= y1) and (x0 <= cx <= x1)) or (
            name.strip().lower() in ALWAYS_THAY_NAMES
        )
        width_px = round(2 * float(np.sqrt(n / np.pi)), 1)  # crude, for a 2-4 px line
        if risers >= args.min_risers or in_thay:
            rows.append({
                "ck2_id": ck2_id,
                "name": name,
                "pixel_count": n,
                "approx_width_px": width_px,
                "ring_px": args.ring_px,
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
            "ck2_id", "name", "pixel_count", "approx_width_px", "ring_px",
            "shore_median_level", "risers_above_water",
            "canvas_centroid_y", "canvas_centroid_x", "region",
        ])
        w.writeheader()
        w.writerows(rows)

    arr = np.array(all_risers)
    print(f"{arr.size} river provinces measured (ring {args.ring_px} px)")
    if arr.size:
        for p in (50, 75, 90, 95, 99):
            print(f"  risers p{p}: {np.percentile(arr, p):.1f}")
        print(f"  max: {arr.max():.1f}")
    print(f"{len(rows)} at or above --min-risers {args.min_risers} "
          f"({sum(1 for r in rows if r['region'] == 'thay')} in the Thay window)")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
