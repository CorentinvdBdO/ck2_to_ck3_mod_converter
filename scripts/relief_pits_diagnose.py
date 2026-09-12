#!/usr/bin/env python3
"""Lane `relief-pits` part A: what the pits on Thay actually are.

`--mode live`    every finished map against the plain rescale on the study
                 windows: the pit metric, closed-depression depth, the bound
                 hit fraction, signed-difference and hillshade PNGs, and
                 transects across the plateau *interior* as well as its rims.
`--mode ablate`  one `heightmap_detail.apply` run per candidate on the Thay
                 crop, so each pass can be charged with its own share of the
                 pits.

Usage:
  uv run python scripts/relief_pits_diagnose.py --mode live
  uv run python scripts/relief_pits_diagnose.py --mode ablate --region thay
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import relief_pits_common as P  # noqa: E402
import relief_sharp_common as C  # noqa: E402

OUT = C.ROOT / "docs/evidence/relief_pits"
#: the Thay window the playtest brief names, canvas px (y0, x0, y1, x1)
WINDOWS = {
    "thay": (1583, 4752, 2222, 5311),
    "spine": (416, 2032, 516, 2315),
}


def write_csv(path: Path, rows: list[dict]) -> None:
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
    print(f"wrote {path}")


def _maps(args) -> dict[str, Path]:
    maps = {"build15": C.LIVE_MOD / "map_data/heightmap.png"}
    for spec in args.maps or []:
        name, _, path = spec.partition("=")
        maps[name] = Path(path)
    return {n: p for n, p in maps.items() if p.exists()}


# --------------------------------------------------------------------------- #
# mode live
# --------------------------------------------------------------------------- #
def mode_live(args) -> None:
    import heightmap_structure_metrics as M
    from PIL import Image

    base_canvas = C.plain_rescale_canvas()
    loaded = {n: C.load16(p) for n, p in _maps(args).items()}
    if not loaded:
        raise SystemExit("no finished map found")
    land_canvas = np.logical_and.reduce(
        [C.province_land_mask(a) for a in loaded.values()])
    OUT.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    for region, (y0, x0, y1, x1) in WINDOWS.items():
        if args.region not in ("both", region):
            continue
        ys, xs = slice(y0, y1), slice(x0, x1)
        base = base_canvas[ys, xs]
        land = land_canvas[ys, xs]
        tcode, tkeys = P.terrain_codes_from_mod(C.LIVE_MOD, ys, xs)
        tol = P.tolerance_field(tcode, tkeys)
        print(f"\n== {region} window {base.shape} land {land.mean():.1%} "
              f"tol median {np.median(tol[land]):.0f} levels")
        for label, arr in [("plain_rescale", base)] + [
                (n, a[ys, xs]) for n, a in loaded.items()]:
            r = P.pit_stats(base, arr, land, label)
            r["region"] = region
            r.update(P.bound_violation(base, arr, land, tol))
            dep = P.closed_depression_depth(arr, land)
            r["sink_p99"] = round(float(np.percentile(dep[land], 99)), 1)
            r["sink_max"] = round(float(dep[land].max()), 1)
            r["sink_frac_gt_riser"] = round(
                float((dep[land] > P.QUANT_LEVELS).mean()), 5)
            d = arr.astype(np.float64) - base.astype(np.float64)
            r["delta_mean"] = round(float(d[land].mean()), 1)
            r["delta_std"] = round(float(d[land].std()), 1)
            r.update(P.shape_metrics(arr.astype(np.float32), land, C.KM_PX_OURS))
            rows.append(r)
            print(f"  {label:16s} pit p95 {r['pit_p95']:7.0f} p99 {r['pit_p99']:7.0f}"
                  f" >riser {r['pit_frac_gt_riser']:7.4f}"
                  f"  sink p99 {r['sink_p99']:6.0f}"
                  f"  bound-under {r['bound_under_frac']:7.4f}"
                  f"  ridge {r['ridge_share']:.3f}")
            # figures
            # `window_` prefix: `relief_pits_shape.py` writes its own
            # `hillshade_<crop>_<map>.png` at a fixed 512 px (760 km) for the
            # vanilla comparison, and the two must not collide -- the study
            # *windows* here are whatever size the region's bounding box is.
            Image.fromarray(M.hillshade(arr.astype(np.float32), C.KM_PX_OURS)).save(
                OUT / f"hillshade_window_{region}_{label}.png")
        # signed difference, build vs rescale
        for n, a in loaded.items():
            d = a[ys, xs].astype(np.float32) - base.astype(np.float32)
            d = np.where(land, d, 0.0)
            lim = max(float(np.percentile(np.abs(d[land]), 99)), 1.0)
            img = np.clip(d / lim, -1, 1)
            rgb = np.zeros(d.shape + (3,), dtype=np.uint8)
            rgb[..., 0] = np.clip(255 * (0.5 - 0.5 * img), 0, 255)  # blue-ish down
            rgb[..., 2] = np.clip(255 * (0.5 + 0.5 * img), 0, 255)
            rgb[..., 1] = np.clip(255 * (1.0 - np.abs(img)), 0, 255)
            Image.fromarray(rgb).save(OUT / f"signed_diff_{region}_{n}.png")
            print(f"  signed_diff_{region}_{n}.png  +-{lim:.0f} levels full scale")
        _transects(region, base, land, loaded, ys, xs)
    write_csv(OUT / f"pits_live_{args.region}.csv", rows)


def _transects(region, base, land, loaded, ys, xs) -> None:
    """Interior and rim transects as a CSV, plus a PNG if matplotlib is here."""
    h, w = base.shape
    # the flattest row of the source inside the window (plateau interior) and
    # the row carrying the biggest one-pixel source step (a rim)
    rowvar = np.where(land.sum(1) > 0.8 * w,
                      np.abs(np.diff(base.astype(np.float64), axis=1)).mean(1),
                      np.inf)
    interior_y = int(np.argmin(rowvar))
    rim_y = int(np.argmax(np.where(land.sum(1) > 0.8 * w,
                                   np.abs(np.diff(base.astype(np.float64),
                                                  axis=1)).max(1), -1)))
    rows = []
    for name, y in (("interior", interior_y), ("rim", rim_y)):
        for x in range(w):
            r = {"region": region, "transect": name, "y": int(ys.start + y),
                 "x": int(xs.start + x), "land": int(land[y, x]),
                 "plain_rescale": int(base[y, x])}
            for n, a in loaded.items():
                r[n] = int(a[ys, xs][y, x])
            rows.append(r)
    write_csv(OUT / f"transects_{region}.csv", rows)
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return
    fig, axes = plt.subplots(2, 1, figsize=(13, 7), sharex=True)
    for ax, (name, y) in zip(axes, (("interior", interior_y), ("rim", rim_y))):
        ax.plot(base[y], color="0.5", lw=1.2, label="plain rescale (CK2 source)")
        for n, a in loaded.items():
            ax.plot(a[ys, xs][y], lw=1.0, label=n)
        ax.set_title(f"{region} {name} transect, canvas row {ys.start + y}")
        ax.set_ylabel("16-bit level")
        ax.legend(fontsize=8)
    axes[-1].set_xlabel("canvas px along the window")
    fig.tight_layout()
    fig.savefig(OUT / f"transects_{region}.png", dpi=110)
    plt.close(fig)
    print(f"wrote {OUT / f'transects_{region}.png'}")


# --------------------------------------------------------------------------- #
# mode ablate
# --------------------------------------------------------------------------- #
#: build 15's shipped configuration is the dataclass default except for the
#: slope ceiling, which configs/faerun.toml sets to 0.5.
B15 = dict(erosion_slope_ceiling_steps=0.5)
VARIANTS: dict[str, dict] = {
    "b15_default": dict(B15),
    # candidate (iii): Perona-Malik overshoot, pass 1 alone
    "pass1_only": dict(B15, _pass1_only=True),
    # candidate (i): the stream-power erosion carving the flat plateau top
    "no_incision": dict(B15, erosion_incision=0.0),
    "isotropic_relief": dict(B15, relief_mode="isotropic"),
    # candidate (ii): the fill's long-wavelength undulation
    "fill_from_0.10": dict(B15, fill_min_cycles_per_km=0.10),
    "fill_from_0.172": dict(B15, fill_min_cycles_per_km=0.172),
    "no_fill": dict(B15, fill_gain=0.0),
    # the other two passes, ruled in or out
    "no_rivers": dict(B15, river_depth=0.0),
    "no_coast_smooth": dict(B15, coast_smooth_px=0.0),
}


def mode_ablate(args) -> None:
    from ck2ck3.map import heightmap_detail as hd
    from ck2ck3.map import heightmap_erosion as he
    from ck2ck3.map.config import HeightmapDetailConfig

    base_canvas = C.plain_rescale_canvas()
    live = C.load16(C.LIVE_MOD / "map_data/heightmap.png")
    margin = args.margin
    rows: list[dict] = []
    regions = [args.region] if args.region != "both" else list(C.crops())
    for region in regions:
        c = C.crops()[region]
        y, x, s = c["crop_y"], c["crop_x"], c["crop_side"]
        ys = slice(y - margin, y + s + margin)
        xs = slice(x - margin, x + s + margin)
        inner = (slice(margin, margin + s), slice(margin, margin + s))
        base = base_canvas[ys, xs]
        land = C.province_land_mask(live[ys, xs])
        from PIL import Image
        with Image.open(C.LIVE_MOD / "map_data/rivers.png") as im:
            riv = np.asarray(im.convert("P"))[ys, xs]
        body = (riv >= 3) & (riv <= 11)
        tcode, tkeys = P.terrain_codes_from_mod(C.LIVE_MOD, ys, xs)
        b_in, land_in = base[inner], land[inner]
        tol_in = P.tolerance_field(tcode[inner], tkeys)

        def emit(label, arr, elapsed=None, extra=None):
            r = P.pit_stats(b_in, arr, land_in, label)
            r["region"] = region
            r["elapsed_s"] = elapsed
            r.update(P.bound_violation(b_in, arr, land_in, tol_in))
            dep = P.closed_depression_depth(arr, land_in)
            r["sink_p99"] = round(float(np.percentile(dep[land_in], 99)), 1)
            d = arr.astype(np.float64) - b_in.astype(np.float64)
            r["delta_std"] = round(float(d[land_in].std()), 0)
            r.update(C.monotonic_violation(b_in, arr, land_in))
            r.update(P.shape_metrics(arr.astype(np.float32), land_in, C.KM_PX_OURS))
            if extra:
                r.update(extra)
            rows.append(r)
            print(f"  {label:20s} pit p95 {r['pit_p95']:7.0f} p99 {r['pit_p99']:7.0f}"
                  f" >riser {r['pit_frac_gt_riser']:7.4f}"
                  f"  sink p99 {r['sink_p99']:6.0f}"
                  f"  MOAT {r.get('moat_excess_mean', 0):6.0f}"
                  f"  dstd {r['delta_std']:6.0f}"
                  f"  ridge {r['ridge_share']:.3f}", flush=True)

        print(f"\n== {region} crop {b_in.shape} (+{margin} px margin), "
              f"land {land_in.mean():.1%}")
        emit("plain_rescale", b_in)
        emit("live_build15", live[ys, xs][inner])
        for label, over in VARIANTS.items():
            if args.only and label not in args.only:
                continue
            over = dict(over)
            if over.pop("_pass1_only", False):
                arr = he.deterrace_cliff_aware(
                    base.astype(np.float32), 2.2, 415.5)[inner]
                emit(label, np.clip(np.rint(arr), 0, 65535).astype(np.uint16))
                continue
            cfg = HeightmapDetailConfig(enabled=True, **over)
            t0 = time.time()
            out, stats = hd.apply(
                base, land_mask=land, terrain_code=tcode, terrain_keys=tkeys,
                river_body=body, river_width_index=riv.astype(np.float32),
                km_per_px=C.KM_PX_OURS, water_level=C.WATER_LEVEL,
                max_level=C.MAX_LEVEL, cfg=cfg,
            )
            emit(label, out[inner], round(time.time() - t0, 1),
                 {"deficit_scale": stats.get("deficit_scale")})
    write_csv(OUT / f"pits_ablate_{args.region}.csv", rows)


def mode_zones(args) -> None:
    """Split the pit metric into coast band / river band / plateau interior."""
    from PIL import Image

    base_canvas = C.plain_rescale_canvas()
    loaded = {n: C.load16(p) for n, p in _maps(args).items()}
    land_canvas = np.logical_and.reduce(
        [C.province_land_mask(a) for a in loaded.values()])
    with Image.open(C.LIVE_MOD / "map_data/rivers.png") as im:
        riv_canvas = np.asarray(im.convert("P"))
    rows: list[dict] = []
    for region, (y0, x0, y1, x1) in WINDOWS.items():
        if args.region not in ("both", region):
            continue
        ys, xs = slice(y0, y1), slice(x0, x1)
        base, land = base_canvas[ys, xs], land_canvas[ys, xs]
        body = (riv_canvas[ys, xs] >= 3) & (riv_canvas[ys, xs] <= 11)
        print(f"\n== {region}")
        for label, arr in [("plain_rescale", base)] + [
                (n, a[ys, xs]) for n, a in loaded.items()]:
            for r in P.pit_by_zone(base, arr, land, body):
                r["region"], r["map"] = region, label
                rows.append(r)
                print(f"  {label:16s} {r['zone']:12s} share {r['share_of_land']:.3f}"
                      f"  pit p95 {r['pit_p95']:8.0f} p99 {r['pit_p99']:8.0f}"
                      f" max {r['pit_max']:8.0f} >riser {r['pit_frac_gt_riser']:.4f}")
    write_csv(OUT / f"pits_zones_{args.region}.csv", rows)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="live", choices=["live", "ablate", "zones"])
    ap.add_argument("--region", default="thay")
    ap.add_argument("--margin", type=int, default=128)
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--maps", nargs="*",
                    help="extra finished maps as name=path/to/heightmap.png")
    args = ap.parse_args()
    if args.mode == "live":
        mode_live(args)
    elif args.mode == "zones":
        mode_zones(args)
    else:
        mode_ablate(args)


if __name__ == "__main__":
    main()
