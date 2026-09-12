#!/usr/bin/env python3
"""Lane `relief-pits`: the per-candidate ablation, run on the WHOLE canvas.

**Why not on the crop.** `relief_sharp_moat.py --mode isolate` toggles each
pass on a 768 px crop, which is what §2d's table was built from. Under build
15's settings that is degenerate: the crop has no all-land 256 px interior
patch, so `_interior_patch_spectrum` returns nothing, the fall-back
whole-crop spectrum of a terraced window already exceeds vanilla's curve
everywhere above 0.05 cycles/km, the deficit comes out identically zero and
**every** relief-mode variant produces byte-identical output (`verified`:
`eroded`, `isotropic` and `erosion_incision = 0` all gave delta RMS 474.9 on
the Thay crop). A crop ablation therefore cannot charge the fill or the
erosion with anything. The pass has to run at the size it ships at.

Each variant is one `heightmap_detail.apply` over the real 8320 x 6784 canvas
(~60 s, ~6 GB), measured on the two study windows with `relief_pits_common`.

Usage:
  uv run python scripts/relief_pits_ablate_canvas.py [--only NAME ...]
      [--variants build15|fixed] [--save-dir DIR]
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import relief_pits_common as P  # noqa: E402
import relief_sharp_common as C  # noqa: E402
from relief_pits_diagnose import WINDOWS, write_csv  # noqa: E402

OUT = C.ROOT / "docs/evidence/relief_pits"

#: build 15's shipped configuration: the dataclass defaults except the slope
#: ceiling, which configs/faerun.toml sets to 0.5.
B15 = dict(erosion_slope_ceiling_steps=0.5)

#: one toggle per candidate reading of "the pits", plus the two passes that
#: have to be ruled out.
VARIANTS: dict[str, dict] = {
    "b15_default": dict(B15),
    # (iii) Perona-Malik overshoot: pass 1 on its own
    "pass1_only": dict(B15, _pass1_only=True),
    # (i) the stream-power erosion carving basins into a flat plateau top
    "no_incision": dict(B15, erosion_incision=0.0),
    "isotropic_relief": dict(B15, relief_mode="isotropic"),
    # (ii) the spectral fill's long-wavelength undulation
    "fill_from_0.10": dict(B15, fill_min_cycles_per_km=0.10),
    "fill_from_0.172": dict(B15, fill_min_cycles_per_km=0.172),
    "no_fill": dict(B15, fill_gain=0.0),
    # pass 3 and pass 4
    "no_rivers": dict(B15, river_depth=0.0),
    "no_coast_smooth": dict(B15, coast_smooth_px=0.0),
}


def canvas_inputs():
    """`(plain rescale, land, terrain code, keys, river body, width index)`."""
    base = C.plain_rescale_canvas()
    live = C.load16(C.LIVE_MOD / "map_data/heightmap.png")
    land = C.province_land_mask(live)
    del live
    full = (slice(None), slice(None))
    tcode, tkeys = P.terrain_codes_from_mod(C.LIVE_MOD, *full)
    with Image.open(C.LIVE_MOD / "map_data/rivers.png") as im:
        riv = np.asarray(im.convert("P"))
    body = (riv >= 3) & (riv <= 11)
    return base, land, tcode, tkeys, body, riv.astype(np.float32)


def measure(base, arr, land, tcode, tkeys, label: str,
            stats: dict | None = None, fast: bool = False) -> list[dict]:
    rows = []
    for region, (y0, x0, y1, x1) in WINDOWS.items():
        ys, xs = slice(y0, y1), slice(x0, x1)
        b, o, m = base[ys, xs], arr[ys, xs], land[ys, xs]
        tol = P.tolerance_field(tcode[ys, xs], tkeys)
        r = P.pit_stats(b, o, m, label)
        r["region"] = region
        r.update(P.bound_violation(b, o, m, tol))
        dep = P.closed_depression_depth(o, m)
        r["sink_p99"] = round(float(np.percentile(dep[m], 99)), 1)
        r["sink_frac_gt_riser"] = round(float((dep[m] > P.QUANT_LEVELS).mean()), 5)
        d = o.astype(np.float64) - b.astype(np.float64)
        r["delta_std"] = round(float(d[m].std()), 1)
        if not fast:
            # a Python loop over every cliff pixel: minutes on a full window
            r.update(C.monotonic_violation(b, o, m))
        r.update(P.shape_metrics(o.astype(np.float32), m, C.KM_PX_OURS))
        for k in ("bound_limited_pct_of_land", "bound_excess_below_p99",
                  "erosion_gate_land_mean", "erosion_ridged_land_mean",
                  "land_pct_on_clamp_floor", "coast_mode"):
            if stats and k in stats:
                r[k] = stats[k]
        rows.append(r)
        print(f"  {region:6s} {label:18s} pit p95 {r['pit_p95']:7.0f}"
              f" p99 {r['pit_p99']:7.0f} >riser {r['pit_frac_gt_riser']:7.4f}"
              f"  sink p99 {r['sink_p99']:6.0f}"
              f"  bound {r['bound_under_frac']:7.4f}"
              f"  MOAT {r.get('moat_excess_mean', 0):6.0f}"
              f"  dstd {r['delta_std']:6.0f}"
              f"  ridge {r['ridge_share']:.3f}", flush=True)
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--out-csv", default="pits_ablate_canvas.csv")
    ap.add_argument("--save-dir", help="write each variant's heightmap.png here")
    ap.add_argument("--fast", action="store_true",
                    help="skip the O(cliff px) Python-loop MOAT metric")
    ap.add_argument("--extra", nargs="*", default=[],
                    help="name:key=value,key=value -- an extra variant")
    args = ap.parse_args()

    from ck2ck3.map import heightmap_detail as hd
    from ck2ck3.map import heightmap_erosion as he
    from ck2ck3.map.config import HeightmapDetailConfig

    variants = dict(VARIANTS)
    for spec in args.extra:
        name, _, body = spec.partition(":")
        over = dict(B15)
        for kv in filter(None, body.split(",")):
            k, _, v = kv.partition("=")
            try:
                over[k] = float(v) if "." in v or v.isdigit() else v
            except ValueError:
                over[k] = v
        variants[name] = over

    base, land, tcode, tkeys, body, widx = canvas_inputs()
    print(f"canvas {base.shape} land {land.mean():.1%} "
          f"terrain classes {len(tkeys)}", flush=True)
    rows = measure(base, base, land, tcode, tkeys, "plain_rescale",
                   fast=args.fast)
    live = C.load16(C.LIVE_MOD / "map_data/heightmap.png")
    rows += measure(base, live, land, tcode, tkeys, "live_build15",
                    fast=args.fast)
    del live
    for name, over in variants.items():
        if args.only and name not in args.only:
            continue
        over = dict(over)
        t0 = time.time()
        if over.pop("_pass1_only", False):
            out = he.deterrace_cliff_aware(base.astype(np.float32), 2.2, 415.5)
            out = np.where(land, np.clip(np.rint(out), 0, 65535), base
                           ).astype(np.uint16)
            st = {}
        else:
            cfg = HeightmapDetailConfig(enabled=True, **over)
            out, st = hd.apply(
                base, land_mask=land, terrain_code=tcode, terrain_keys=tkeys,
                river_body=body, river_width_index=widx,
                km_per_px=C.KM_PX_OURS, water_level=C.WATER_LEVEL,
                max_level=C.MAX_LEVEL, cfg=cfg)
        print(f"{name}: {time.time() - t0:.0f} s "
              f"bound-limited {st.get('bound_limited_pct_of_land', 0)} % "
              f"gate {st.get('erosion_gate_land_mean', 1)} "
              f"ridged {st.get('erosion_ridged_land_mean', 0)}", flush=True)
        rows += measure(base, out, land, tcode, tkeys, name, st, fast=args.fast)
        if args.save_dir:
            d = Path(args.save_dir)
            d.mkdir(parents=True, exist_ok=True)
            Image.fromarray(out).save(d / f"{name}.png")
        del out
    write_csv(OUT / args.out_csv, rows)


if __name__ == "__main__":
    main()
