#!/usr/bin/env python3
"""Lane `thay-relief`: render Thay the way the *player* sees it, not the way
a spectrum estimator sees it.

Two failures already happened here: build 14 fixed a measured cause
(erosion planing the rims) and playtest 4 still saw pits; build 16 fixed a
second measured cause (coast smoothing cratering the lakes) and the user
still said "Thay was still broken" after build 17. A whole-canvas FFT patch
or a p95 table cannot be trusted to see what is wrong here a third time, so
this script renders a hillshade and an oblique 3-D view of the Thay window
for four heights -- the CK2 source, our plain rescale, a reconstruction of
build 15, and the actual shipped build-17 ``heightmap.png`` -- using the
renderer's own vertical scale, not an arbitrary exaggeration.

**The vertical scale.** ``common/defines`` (``docs/step_map_heightmap.md``
CLAUDE.md invariant): a custom map sets ``WORLD_EXTENTS_X`` = width-1 and
``WORLD_EXTENTS_Z`` = height-1, i.e. one heightmap texel is one world unit
horizontally on both axes; ``WORLD_EXTENTS_Y`` (51 for Faerun,
``common/defines/fae_defines.txt``) is the *same* world-unit scale applied to
the 16-bit height channel, so ``world_height = level / 65535 * WORLD_EXTENTS_Y``
is not a choice, it is what the GPU does with this texture
(``gfx/FX/pdxterrain.shader``, ``jomini/map_lighting.fxh``). A hillshade
built from ``np.gradient`` on that array with unit pixel spacing is therefore
the same surface normal the game's own terrain shader computes.

**The sun.** ``gfx/map/environment/environment.txt`` (vanilla game files):
``sun_direction = { -4.5 3 -1 }`` (x, y-up, z) is the constant the terrain
shader lights the map with outside the flat-map zoom-out
(``pdxterrain.shader`` ``ToSunDir`` / ``GetMapLightingProperties``); elevation
= asin(3 / |v|) = 33.1 deg above the horizon, which is corroborated by the
same file's ``terrain_sunny_sun_elevation = 0.4`` (0..1 = 0..90 deg -> 36
deg). Low, as CK3's terrain lighting always is.

**The camera pitch.** ``common/defines/graphic/00_graphics.txt``
``ZOOM_STEPS_TILT`` -- degrees of camera tilt above the horizontal, 50 deg at
the closest zoom step (index 0) ramping to 85 (near top-down) at the
zoomed-out end. The close-zoom value is what a player crouched over an
escarpment actually sees, so the oblique view uses ``elev=50``.

Usage:
  uv run python scripts/thay_render.py [--out-dir DIR] [--skip-3d]
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import relief_pits_common as P  # noqa: E402
import relief_sharp_common as C  # noqa: E402

Image.MAX_IMAGE_PIXELS = None

# --------------------------------------------------------------------------- #
# geometry
# --------------------------------------------------------------------------- #
#: the Thay window the brief names, canvas px (y0, x0, y1, x1), no margin
THAY_CORE = (1583, 4752, 2222, 5311)
MARGIN_PX = 100

#: WORLD_EXTENTS_Y for Faerun (common/defines/fae_defines.txt), world units
WORLD_EXTENTS_Y = 51.0
#: sun_direction = { -4.5 3 -1 } (x, y-up, z), gfx/map/environment/environment.txt
SUN_VEC = np.array([-4.5, 3.0, -1.0])
SUN_ELEV_DEG = float(np.degrees(np.arcsin(SUN_VEC[1] / np.linalg.norm(SUN_VEC))))
SUN_AZ_DEG = float(np.degrees(np.arctan2(-SUN_VEC[2], SUN_VEC[0])))  # (col, row) axes
#: ZOOM_STEPS_TILT[0] = 50 (common/defines/graphic/00_graphics.txt), the
#: closest-zoom camera pitch above the horizontal
CAMERA_TILT_DEG = 50.0

#: build-15's heightmap_detail config, reconstructed field by field from
#: docs/step_map_heightmap.md §2f/§2g and docs/evidence/HANDOFF_relief_*.md
#: -- NOT read off the dataclass defaults, which have since moved on.
BUILD15_OVERRIDES = dict(
    deterrace_mode="cliff_aware", deterrace_sigma_px=2.2, cliff_step_levels=415.5,
    relief_mode="eroded", erosion_iterations=16, erosion_accum_iterations=3,
    erosion_seed_amplitude=300.0, erosion_mfd_exponent=4.0,
    erosion_incision=0.5, erosion_diffusion=0.06,
    erosion_slope_ceiling_steps=0.5,      # introduced at build 15, unchanged since
    erosion_slope_gate_steps=0.0,         # the gate did not exist yet: 0 disables it
    target_mode="vanilla_curve", target_gain=1.0,
    gain_mode="deficit", fill_gain=0.70, gain_blur_px=6.0,
    fill_min_cycles_per_km=0.05,          # build 15's value (raised to 0.10 at build 16)
    headroom_fraction=0.5,
    ridged_weight=0.0,                    # ridged relief (§2g) postdates build 15
    ridged_diffusion_scale=1.0,
    bound_tolerance_sigmas=0.0,           # the source bound (§2f) postdates build 15
    coast_mode="blend_to_water",          # build 15's coast pass (contracts to water level)
    coast_smooth_px=4.0, river_depth=900.0, seed=1357,
)


def world_height(level: np.ndarray) -> np.ndarray:
    return level.astype(np.float64) / 65535.0 * WORLD_EXTENTS_Y


def hillshade(z: np.ndarray, sun_elev_deg: float = SUN_ELEV_DEG,
              sun_az_deg: float = SUN_AZ_DEG) -> np.ndarray:
    """Lambertian shade in [0, 1], unit pixel spacing on both axes.

    ``z`` is in world-height units already (``world_height``), so ``dz/dpx``
    over a 1-world-unit pixel is exactly the slope the terrain shader's own
    normal map encodes -- no separate vertical-exaggeration knob to get
    wrong.
    """
    gy, gx = np.gradient(z)
    nx, ny, nz = -gx, -gy, np.ones_like(z)
    n = np.sqrt(nx * nx + ny * ny + nz * nz)
    nx, ny, nz = nx / n, ny / n, nz / n
    el = np.radians(sun_elev_deg)
    az = np.radians(sun_az_deg)
    lx, ly, lz = np.cos(el) * np.cos(az), np.cos(el) * np.sin(az), np.sin(el)
    shade = nx * lx + ny * ly + nz * lz
    return np.clip(shade, 0.0, 1.0)


def crop_slices(margin: int = MARGIN_PX) -> tuple[slice, slice]:
    y0, x0, y1, x1 = THAY_CORE
    return slice(y0 - margin, y1 + margin), slice(x0 - margin, x1 + margin)


# --------------------------------------------------------------------------- #
# the four sources
# --------------------------------------------------------------------------- #
def ck2_source_truth_crop() -> np.ndarray:
    """CK2's own ``topology.bmp``, at its NATIVE resolution, LUT-applied.

    Native, not LANCZOS-upsampled onto the canvas: this is the author's own
    raster with nothing of ours done to it yet, so it answers "did the CK2
    author draw a pit here" independent of any resample or synthesis. Cropped
    via the exact canvas<->source affine ``plain_rescale_canvas`` uses
    (``OFFSET_X/Y``, ``SCALED_W/H`` = the LANCZOS target size, which is
    ``topology.bmp``'s own size x the canvas scale factor).
    """
    from ck2ck3.map import heightmap as hm
    from ck2ck3.map.config import HeightmapConfig

    lut = hm.build_curve(HeightmapConfig(
        ck2_sea_level=C.CK2_SEA_LEVEL, ck3_water_level=C.WATER_LEVEL,
        ck3_max_level=C.MAX_LEVEL,
    ))
    ys, xs = crop_slices()
    y0, y1, x0, x1 = ys.start, ys.stop, xs.start, xs.stop
    # canvas -> scaled-topology (LANCZOS target) -> native topology.bmp
    sy0, sy1 = y0 - C.OFFSET_Y, y1 - C.OFFSET_Y
    sx0, sx1 = x0 - C.OFFSET_X, x1 - C.OFFSET_X
    with Image.open(C.CK2_MAP / "topology.bmp") as im:
        nw, nh = im.size  # 4096 x 3328
        fx, fy = nw / C.SCALED_W, nh / C.SCALED_H
        native_box = (
            max(int(sx0 * fx) - 2, 0), max(int(sy0 * fy) - 2, 0),
            min(int(np.ceil(sx1 * fx)) + 2, nw), min(int(np.ceil(sy1 * fy)) + 2, nh),
        )
        native = np.asarray(im.convert("L").crop(native_box))
    return lut[native], native_box


def build15_reconstruction_canvas(cache_dir: Path) -> np.ndarray:
    """Whole-canvas ``heightmap_detail.apply`` at build-15 settings.

    Cached to ``cache_dir`` (npy) because it is a ~1-minute pass; every
    other source here is either a direct file read or a cheap resample.
    """
    cache = cache_dir / "build15_recon_canvas.npy"
    if cache.exists():
        return np.load(cache)
    from ck2ck3.map import heightmap_detail as hd
    from ck2ck3.map.config import HeightmapDetailConfig
    from relief_pits_ablate_canvas import canvas_inputs

    base, land, tcode, tkeys, river_body, river_width = canvas_inputs()
    cfg = HeightmapDetailConfig(enabled=True, **BUILD15_OVERRIDES)
    t0 = time.time()
    out, stats = hd.apply(
        base, land_mask=land, terrain_code=tcode, terrain_keys=tkeys,
        river_body=river_body, river_width_index=river_width,
        km_per_px=C.KM_PX_OURS, water_level=C.WATER_LEVEL, max_level=C.MAX_LEVEL,
        cfg=cfg,
    )
    print(f"  build15 reconstruction: {time.time() - t0:.1f}s, stats={stats}")
    cache_dir.mkdir(parents=True, exist_ok=True)
    np.save(cache, out)
    return out


def load_sources(cache_dir: Path) -> dict[str, np.ndarray]:
    ys, xs = crop_slices()
    ck2_crop, native_box = ck2_source_truth_crop()
    print(f"  ck2 source native box (topology.bmp px) = {native_box}, "
          f"crop shape {ck2_crop.shape}")
    plain = C.plain_rescale_canvas()[ys, xs]
    build15 = build15_reconstruction_canvas(cache_dir)[ys, xs]
    build17 = C.load16(C.LIVE_MOD / "map_data/heightmap.png")[ys, xs]
    return {
        "ck2_source": ck2_crop,
        "plain_rescale": plain,
        "build15": build15,
        "build17": build17,
    }


# --------------------------------------------------------------------------- #
# rendering
# --------------------------------------------------------------------------- #
def save_hillshade(level: np.ndarray, path: Path, title: str) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    z = world_height(level)
    shade = hillshade(z)
    fig, ax = plt.subplots(figsize=(8, 8 * z.shape[0] / z.shape[1]))
    ax.imshow(shade, cmap="gray", vmin=0, vmax=1, origin="upper")
    ax.set_title(title, fontsize=10)
    ax.axis("off")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def save_oblique(level: np.ndarray, path: Path, title: str,
                  stride: int = 3) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d import Axes3D  # noqa: F401

    z = world_height(level)[::stride, ::stride]
    shade = hillshade(world_height(level))[::stride, ::stride]
    h, w = z.shape
    xs, ys = np.meshgrid(np.arange(w), np.arange(h))
    face = plt.cm.gray(shade)
    fig = plt.figure(figsize=(8, 7))
    ax = fig.add_subplot(111, projection="3d")
    ax.plot_surface(
        xs, ys, z, facecolors=face, rstride=1, cstride=1,
        linewidth=0, antialiased=False, shade=False,
    )
    ax.set_box_aspect((w, h, max((z.max() - z.min()) * 1.0, 1.0)))
    ax.view_init(elev=CAMERA_TILT_DEG, azim=-60)
    ax.set_axis_off()
    ax.set_title(title, fontsize=10)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default=str(C.ROOT / "docs/evidence/thay_relief"))
    ap.add_argument("--cache-dir",
                    default="/home/cvdbdo/git/paradox/ck3/wt/_out/thay-relief")
    ap.add_argument("--skip-3d", action="store_true")
    args = ap.parse_args()

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    cache_dir = Path(args.cache_dir)

    print(f"sun elevation {SUN_ELEV_DEG:.1f} deg, azimuth {SUN_AZ_DEG:.1f} deg "
          f"(gfx/map/environment/environment.txt sun_direction)")
    print(f"camera tilt {CAMERA_TILT_DEG:.0f} deg "
          f"(common/defines/graphic/00_graphics.txt ZOOM_STEPS_TILT[0])")

    t0 = time.time()
    sources = load_sources(cache_dir)
    for name, arr in sources.items():
        print(f"  {name}: shape {arr.shape}, level "
              f"[{int(arr.min())}, {int(arr.max())}]")
        save_hillshade(arr, out / f"hillshade_{name}.png",
                        f"Thay - {name} (hillshade, sun {SUN_ELEV_DEG:.0f} deg)")
        if not args.skip_3d:
            save_oblique(arr, out / f"oblique_{name}.png",
                         f"Thay - {name} (oblique, tilt {CAMERA_TILT_DEG:.0f} deg)")
    print(f"done in {time.time() - t0:.1f}s -> {out}")


if __name__ == "__main__":
    main()
