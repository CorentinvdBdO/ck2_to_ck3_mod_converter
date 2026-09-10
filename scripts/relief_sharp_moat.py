#!/usr/bin/env python3
"""Measure the cliff-foot moat the build-13 playtest reported on Thay.

`--mode live`     the shipped map against the plain rescale, both study crops.
`--mode isolate`  every pass toggled on the crop, so the moat can be pinned on
                  one of them (Perona-Malik overshoot, the erosion's
                  stream-power incision, or the deficit-mode fill).

Usage:
  uv run python scripts/relief_sharp_moat.py --mode live
  uv run python scripts/relief_sharp_moat.py --mode isolate --region thay
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import relief_sharp_common as C  # noqa: E402


def water_distance_km(base: np.ndarray) -> float:
    from scipy.ndimage import distance_transform_edt
    land = base > C.WATER_LEVEL
    if land.all():
        return float("inf")
    return float(distance_transform_edt(land).max() * C.KM_PX_OURS)


def mode_live(args) -> None:
    """The shipped map, and any other finished map, against the plain rescale."""
    base_canvas = C.plain_rescale_canvas()
    maps = {"build13_live": C.LIVE_MOD / "map_data/heightmap.png"}
    for spec in args.maps or []:
        name, _, path = spec.partition("=")
        maps[name] = Path(path)
    loaded = {n: C.load16(p) for n, p in maps.items() if p.exists()}
    # the province land mask, not a threshold on the rescale: see
    # `province_land_mask`.  Taken off every finished map at once, so one
    # mask serves them all.
    land_canvas = np.logical_and.reduce(
        [C.province_land_mask(a) for a in loaded.values()])
    rows = []
    for region in C.crops():
        ys, xs = C.crop_box(region)
        base = base_canvas[ys, xs]
        land = land_canvas[ys, xs] & (base > C.WATER_LEVEL)
        print(f"\n== {region} crop {base.shape} land {land.mean():.3%} "
              f"water-free radius {water_distance_km(base):.0f} km")
        for label, arr in [("plain_rescale", base)] + [
                (n, a[ys, xs]) for n, a in loaded.items()]:
            r = C.moat_stats(base, arr, land, label)
            r["region"] = region
            r.update({f"tr_{k}": v for k, v in
                      C.monotonic_violation(base, arr, land).items()})
            d = arr.astype(np.float64) - base.astype(np.float64)
            r["delta_std"] = round(float(d[land].std()), 0)
            r["clamp_floor_pct"] = round(
                100.0 * float((arr[land] <= C.WATER_LEVEL + 1).mean()), 3)
            rows.append(r)
            print(f"  {label:20s} undershoot {r.get('tr_undershoot_mean',0):7.0f}"
                  f"  control {r.get('tr_control_undershoot_mean',0):7.0f}"
                  f"  MOAT {r.get('tr_moat_excess_mean',0):7.0f}"
                  f"  moat_p95 {r['moat_p95_near']:6.0f}"
                  f"  dstd {r['delta_std']:6.0f}"
                  f"  floor {r['clamp_floor_pct']:6.3f}%")
    _write(C.OUT / "moat_live.csv", rows)


def _write(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    keys: list[str] = []
    for r in rows:
        for k in r:
            if k not in keys:
                keys.append(k)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)
    print(f"\nwrote {path}")


#: every candidate the goal names, plus the fix, each one toggle away from
#: the build-13 configuration.  `fill_min_cycles_per_km = 0.01` reproduces
#: build 13 (its fill started at KEEP_STRUCTURE_BELOW_KM).
B13 = dict(fill_min_cycles_per_km=0.01, erosion_slope_ceiling_steps=0.0)
VARIANTS: dict[str, dict] = {
    "b13_default":            dict(B13),
    # (a) Perona-Malik overshoot on a step
    "b13_deterrace_gaussian": dict(B13, deterrace_mode="gaussian",
                                   deterrace_sigma_px=1.6),
    # (b) the erosion's stream-power incision at the cliff foot
    "b13_no_incision":        dict(B13, erosion_incision=0.0),
    "b13_isotropic_relief":   dict(B13, relief_mode="isotropic"),
    # (c) the deficit-mode gain
    "b13_gain_hf_target":     dict(B13, gain_mode="hf_target"),
    # pass 3 and pass 4, ruled in or out
    "b13_no_rivers":          dict(B13, river_depth=0.0),
    "b13_no_coast_smooth":    dict(B13, coast_smooth_px=0.0),
    # fix half 1: the erosion may not re-carve the macro escarpment
    "fix_slopecap_2.0":       dict(B13, erosion_slope_ceiling_steps=2.0),
    "fix_slopecap_1.0":       dict(B13, erosion_slope_ceiling_steps=1.0),
    # fix half 2: the fill only owns the band the source cannot carry
    "fix_fillmin_only":       dict(fill_min_cycles_per_km=0.05,
                                   erosion_slope_ceiling_steps=0.0),
    # both, at three fill bands
    "fix_both_0.03":          dict(fill_min_cycles_per_km=0.03),
    "fix_both_0.05":          dict(fill_min_cycles_per_km=0.05),
    "fix_both_0.05_cap1":     dict(fill_min_cycles_per_km=0.05,
                                   erosion_slope_ceiling_steps=1.0),
    "fix_both_0.08":          dict(fill_min_cycles_per_km=0.08),
}


def _crop_inputs(region: str, base_canvas, margin: int):
    """`(base_wide, land_wide, river_body, width_index, inner_slice)`."""
    c = C.crops()[region]
    y, x, s = c["crop_y"], c["crop_x"], c["crop_side"]
    ys = slice(y - margin, y + s + margin)
    xs = slice(x - margin, x + s + margin)
    base = base_canvas[ys, xs]
    land = base > C.WATER_LEVEL
    import numpy as _np
    from PIL import Image
    with Image.open(C.LIVE_MOD / "map_data/rivers.png") as im:
        riv = _np.asarray(im.convert("P"))[ys, xs]
    body = (riv >= 3) & (riv <= 11)
    inner = (slice(margin, margin + s), slice(margin, margin + s))
    return base, land, body, riv.astype(_np.float32), inner


def mode_isolate(args) -> None:
    from ck2ck3.map import heightmap_detail as hd
    from ck2ck3.map import heightmap_erosion as he
    from ck2ck3.map.config import HeightmapDetailConfig

    base_canvas = C.plain_rescale_canvas()
    live = C.load16(C.LIVE_MOD / "map_data/heightmap.png")
    margin = args.margin
    rows = []
    for region in ([args.region] if args.region != "both" else list(C.crops())):
        base, land, body, widx, inner = _crop_inputs(region, base_canvas, margin)
        b_in, land_in = base[inner], land[inner]
        # one terrain class over the crop: `_relative_terrain_gain` then has
        # a land mean of exactly 1, so the isolation measures the fill and
        # not the per-terrain envelope
        tcode = np.zeros(base.shape, dtype=np.int16)
        tkeys = ["mountains"]

        def emit(label, arr, elapsed=None, extra=None):
            r = C.moat_stats(b_in, arr, land_in, label)
            r["region"] = region
            r["elapsed_s"] = elapsed
            r.update({f"tr_{k}": v for k, v in
                      C.monotonic_violation(b_in, arr, land_in).items()})
            d = arr.astype(np.float64) - b_in.astype(np.float64)
            r["delta_std"] = round(float(d[land_in].std()), 0)
            r["delta_p01"] = round(float(np.percentile(d[land_in], 1)), 0)
            r["clamp_floor_pct"] = round(
                100.0 * float((arr[land_in] <= C.WATER_LEVEL + 1).mean()), 3)
            if extra:
                r.update(extra)
            rows.append(r)
            print(f"  {label:24s} undershoot {r.get('tr_undershoot_mean', 0):7.0f}"
                  f"  control {r.get('tr_control_undershoot_mean', 0):7.0f}"
                  f"  MOAT {r.get('tr_moat_excess_mean', 0):7.0f}"
                  f"  moat_p95 {r['moat_p95_near']:6.0f}"
                  f"  dstd {r['delta_std']:6.0f}"
                  f"  floor {r['clamp_floor_pct']:6.3f}%", flush=True)

        print(f"\n== {region} crop {b_in.shape} (+{margin} px margin)")
        emit("plain_rescale", b_in)
        emit("live_build13_map", live[C.crop_box(region)[0], C.crop_box(region)[1]])
        emit("deterrace_pm_only",
             he.deterrace_cliff_aware(base.astype(np.float32), 2.2, 415.5)[inner])
        for label, over in VARIANTS.items():
            if args.only and label not in args.only:
                continue
            cfg = HeightmapDetailConfig(enabled=True, **over)
            t0 = time.time()
            out, stats = hd.apply(
                base, land_mask=land, terrain_code=tcode, terrain_keys=tkeys,
                river_body=body, river_width_index=widx,
                km_per_px=C.KM_PX_OURS, water_level=C.WATER_LEVEL,
                max_level=C.MAX_LEVEL, cfg=cfg,
            )
            emit(label, out[inner], round(time.time() - t0, 1),
                 {"deficit_scale": stats.get("deficit_scale")})
    _write(C.OUT / f"moat_isolate_{args.region}.csv", rows)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="live", choices=["live", "isolate"])
    ap.add_argument("--region", default="thay")
    ap.add_argument("--margin", type=int, default=128)
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--maps", nargs="*",
                    help="extra finished maps as name=path/to/heightmap.png")
    args = ap.parse_args()
    if args.mode == "live":
        mode_live(args)
    else:
        mode_isolate(args)


if __name__ == "__main__":
    main()
