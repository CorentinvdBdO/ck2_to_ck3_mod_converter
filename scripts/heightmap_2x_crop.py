#!/usr/bin/env python3
"""Lane `heightmap-2x`: a fast crop harness for the 2x wall-concentration
hunt (coordinator's own catch, docs/evidence/HANDOFF_heightmap_2x.md §4).

`scripts/relief_pits_ablate_canvas.py` already found that a crop cannot
charge the *spectral fill/erosion's own amplitude* with anything (no
256 px all-land interior patch -> `_interior_patch_spectrum` degenerates,
every relief-mode variant reads byte-identical). That limitation is about
GAIN CALIBRATION, not about a STRUCTURAL artifact: the axis-aligned
hairline stripes this lane found in the full-canvas 2x render are a shape
defect (a raster-aligned bias in some pass), and those survive on a crop
just as well as on the canvas -- so this harness ignores the amplitude
caveat on purpose and runs `heightmap_detail.apply` on a padded crop with
the REAL inputs (real topology.bmp resample, real province/terrain/river
data), seconds per run instead of ~10.5 minutes.

Inputs are built ONCE at full 2x canvas resolution and cached to
``--cache-dir`` (a LANCZOS resize + two image reads, a few seconds), then
cropped per call -- the expensive part (the detail pass itself) is what
gets re-run per ablation, on ~1-2 M px instead of 226 M.

Usage:
  uv run python scripts/heightmap_2x_crop.py [--region spine] [--pad 128]
      [--variant NAME] [--list-variants] [--out-dir DIR]
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import relief_pits_common as P  # noqa: E402
import relief_sharp_common as C  # noqa: E402
from thay_render import (  # noqa: E402
    CAMERA_TILT_DEG, REGIONS, SUN_AZ_DEG, SUN_ELEV_DEG, hillshade, world_height,
)

from ck2ck3.map import heightmap_detail as hd  # noqa: E402
from ck2ck3.map.config import HeightmapDetailConfig  # noqa: E402

#: the real 2x output this lane's own `map` step produced (has heightmap.png
#: -- `ship_heightmap_png=true` locally, see docs/step_map_heightmap.md §2i)
OUT_2X = Path("/home/cvdbdo/git/paradox/ck3/wt/_out/heightmap-2x-verify")
#: the shipped 2x output (no heightmap.png, but has provinces.png/rivers.png/
#: common/province_terrain -- everything canvas_inputs_2x needs except the
#: land mask, which comes from OUT_2X instead)
OUT_2X_SHIPPED = Path("/home/cvdbdo/git/paradox/ck3/wt/_out/heightmap-2x")
CACHE_DIR = ROOT.parent.parent.parent / "wt/_out/heightmap-2x-crop-cache"


def canvas_inputs_2x(cache_dir: Path = CACHE_DIR):
    """Real whole-canvas 2x inputs, exactly what `ck2ck3.map.build` hands
    `heightmap_detail.apply` -- built once, cached to .npy."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    paths = {k: cache_dir / f"{k}.npy" for k in
             ("base", "land", "tcode", "body", "width")}
    keys_path = cache_dir / "tkeys.txt"
    if all(p.exists() for p in paths.values()) and keys_path.exists():
        base = np.load(paths["base"])
        land = np.load(paths["land"])
        tcode = np.load(paths["tcode"])
        body = np.load(paths["body"])
        width = np.load(paths["width"])
        tkeys = keys_path.read_text().splitlines()
        return base, land, tcode, tkeys, body, width

    print("  building whole-canvas 2x inputs (cached after this run)...")
    t0 = time.time()
    base = C.plain_rescale_canvas(resolution_factor=2)
    finished = C.load16(OUT_2X / "map_data/heightmap.png")
    land = C.province_land_mask(finished)
    del finished
    tcode, tkeys = P.terrain_codes_from_mod(
        OUT_2X_SHIPPED, slice(None), slice(None), resolution_factor=2)
    with Image.open(OUT_2X_SHIPPED / "map_data/rivers.png") as im:
        riv = np.asarray(im.convert("P"))
    riv2 = np.repeat(np.repeat(riv, 2, axis=0), 2, axis=1)
    body = (riv2 >= 3) & (riv2 <= 11)
    width = riv2.astype(np.float32)
    print(f"  built in {time.time() - t0:.1f}s, shape {base.shape}")

    np.save(paths["base"], base)
    np.save(paths["land"], land)
    np.save(paths["tcode"], tcode)
    np.save(paths["body"], body)
    np.save(paths["width"], width)
    keys_path.write_text("\n".join(tkeys))
    return base, land, tcode, tkeys, body, width


def crop_all(arrays, ys: slice, xs: slice):
    return tuple(a[ys, xs] for a in arrays)


#: variants to ablate, each a dict of HeightmapDetailConfig overrides on top
#: of the real shipped config (configs/faerun.toml [map] heightmap_detail_*)
VARIANTS: dict[str, dict] = {
    "shipped": {},
    "no_wall_spread": dict(wall_spread_enabled=False),
    "no_ridged": dict(ridged_weight=0.0),
    "isotropic_relief": dict(relief_mode="isotropic"),
    "no_erosion_diffusion": dict(erosion_diffusion=0.0),
    "no_source_bound": dict(bound_tolerance_sigmas=0.0),
    "no_source_adaptive_gain": dict(source_adaptive_gain=False),
    "gaussian_deterrace": dict(deterrace_mode="gaussian"),
    "no_deterrace_sigma": dict(deterrace_sigma_px=0.01),
    "diffusion_x4": dict(erosion_diffusion=0.24),
}


def _shipped_cfg() -> dict:
    """The real `configs/faerun.toml [map] heightmap_detail_*` values, at
    `resolution_factor = 1` (the crop harness scales them itself, the same
    way `ck2ck3.map.build` does -- see `main()`)."""
    import tomllib

    raw = tomllib.loads((ROOT / "configs/faerun.toml").read_text("utf-8"))
    from ck2ck3.map.config import heightmap_detail_config
    cfg = heightmap_detail_config(raw.get("map", {}))
    return cfg


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--region", choices=sorted(REGIONS), default="spine")
    ap.add_argument("--pad", type=int, default=128,
                    help="crop padding, 2x canvas px, beyond the region box")
    ap.add_argument("--variant", nargs="*", default=None,
                    help="run only these variants (default: all)")
    ap.add_argument("--list-variants", action="store_true")
    ap.add_argument("--out-dir", default=str(ROOT / "docs/evidence/heightmap_2x/crop_ablation"))
    ap.add_argument("--cache-dir", default=str(CACHE_DIR))
    ap.add_argument("--seed", type=int, default=1357)
    args = ap.parse_args(argv)

    if args.list_variants:
        for name in VARIANTS:
            print(name)
        return 0

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    y0, x0, y1, x1 = REGIONS[args.region]
    f = 2
    ys = slice(max(0, y0 * f - args.pad), y1 * f + args.pad)
    xs = slice(max(0, x0 * f - args.pad), x1 * f + args.pad)

    base_full, land_full, tcode_full, tkeys, body_full, width_full = canvas_inputs_2x(
        Path(args.cache_dir))
    base, land, tcode, body, width = crop_all(
        (base_full, land_full, tcode_full, body_full, width_full), ys, xs)
    del base_full, land_full, tcode_full, body_full, width_full
    print(f"crop {args.region}: shape {base.shape}, land {100*land.mean():.1f}%")

    shipped = _shipped_cfg()
    # ck2ck3.map.build's own resolution_factor scaling (docs/step_map_heightmap.md
    # §2i) -- the crop harness must apply exactly the same one, or a variant
    # run here is not comparable to the real shipped 2x build.
    from dataclasses import replace
    base_cfg = replace(
        shipped,
        deterrace_sigma_px=shipped.deterrace_sigma_px * f,
        gain_blur_px=shipped.gain_blur_px * f,
        coast_smooth_px=shipped.coast_smooth_px * f,
        wall_spread_window_px=max(1, round(shipped.wall_spread_window_px * f)),
        wall_spread_sigma_px=shipped.wall_spread_sigma_px * f,
        bound_window_px=max(1, round(shipped.bound_window_px * f)),
        source_adaptive_window_px=shipped.source_adaptive_window_px * f,
    )

    km_per_px = 1.4839 / f
    names = args.variant or list(VARIANTS)
    for name in names:
        overrides = VARIANTS[name]
        cfg = replace(base_cfg, **overrides)
        t0 = time.time()
        out, stats = hd.apply(
            base.copy(), land_mask=land, terrain_code=tcode, terrain_keys=tkeys,
            river_body=body, river_width_index=width, km_per_px=km_per_px,
            water_level=4883, max_level=49205, cfg=cfg, resolution_factor=f,
        )
        dt = time.time() - t0
        print(f"  {name:24s} {dt:5.2f}s")

        z = world_height(out)
        shade = hillshade(z)
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(8, 8 * z.shape[0] / z.shape[1]))
        ax.imshow(shade, cmap="gray", vmin=0, vmax=1, origin="upper")
        ax.set_title(f"{args.region} - {name} ({dt:.1f}s)", fontsize=10)
        ax.axis("off")
        fig.tight_layout()
        fig.savefig(out_dir / f"crop_{args.region}_{name}.png", dpi=150)
        plt.close(fig)
        np.save(out_dir / f"crop_{args.region}_{name}.npy", out)

    print(f"done -> {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
