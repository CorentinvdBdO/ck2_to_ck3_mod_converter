#!/usr/bin/env python3
"""Why the eroded relief field has a trench around every escarpment.

`heightmap_erosion.eroded_relief` runs its stream-power law on the *macro*
surface, so `S` at Thay's escarpments is the escarpment itself (up to 4,505
16-bit levels per pixel against a land median of 128).  The law cuts the
plateau rim by up to `_INCISION_SLOPE_CAP * S` per iteration, sixteen times,
and the uniform uplift hands the mean of that back to every land pixel: the
returned field then reads deeply negative on cliff pixels and positive in the
interior, which is the cliff-foot moat playtest 3 reported
(docs/step_map_heightmap.md §2d).

This sweeps `slope_ceiling_steps` and reports the trench it leaves.

Usage: uv run python scripts/relief_sharp_slope_ceiling.py [--region thay]
Writes: docs/evidence/relief_sharp/erosion_slope_ceiling.csv
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import numpy as np
from scipy.ndimage import distance_transform_edt

sys.path.insert(0, str(Path(__file__).resolve().parent))
import relief_sharp_common as C  # noqa: E402

CEILINGS = (0.0, 4.0, 2.0, 1.0, 0.5)
#: "on the cliff" and "well away from any cliff", px
NEAR, FAR = 1.0, 12.0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--regions", nargs="*", default=["thay", "spine"])
    ap.add_argument("--margin", type=int, default=128)
    args = ap.parse_args()
    from ck2ck3.map import heightmap_erosion as he

    canvas = C.plain_rescale_canvas()
    rows = []
    for region in args.regions:
        ys, xs = C.crop_box(region, margin=args.margin)
        b = canvas[ys, xs].astype(np.float32)
        land = b > C.WATER_LEVEL
        h2 = he.deterrace_cliff_aware(b, 2.2, 415.5)
        inner = (slice(args.margin, -args.margin), slice(args.margin, -args.margin))
        bi, li = b[inner], land[inner]
        dist = distance_transform_edt(~C.cliff_mask(bi, li))
        on_cliff, far = li & (dist < NEAR), li & (dist >= FAR)
        for cap in CEILINGS:
            rng = np.random.default_rng(1357)
            field, diag = he.eroded_relief(
                h2, land, rng, seed_amplitude=300.0, iterations=16,
                accum_iterations=3, mfd_exponent=4.0, incision=0.5,
                diffusion=0.06, slope_ceiling_steps=cap,
            )
            f = field[inner] * diag["erosion_field_rms_levels"]
            row = {
                "region": region,
                "slope_ceiling_steps": cap,
                "slope_ceiling_levels_px": round(cap * he.QUANTISATION_STEP_LEVELS, 1),
                "field_rms_levels": diag["erosion_field_rms_levels"],
                "uplift_levels": diag["erosion_uplift_levels"],
                "field_mean_on_cliff": round(float(f[on_cliff].mean()), 0),
                "field_mean_far": round(float(f[far].mean()), 0),
                "trench_levels": round(
                    float(f[far].mean() - f[on_cliff].mean()), 0),
                "field_min": round(float(f[li].min()), 0),
            }
            rows.append(row)
            print(row, flush=True)
    out = C.OUT / "erosion_slope_ceiling.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
