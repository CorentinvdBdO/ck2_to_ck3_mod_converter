#!/usr/bin/env python3
"""Lane `heightmap-2x`: interior-patch spectrum vs vanilla, for a heightmap
built at any `[map.heightmap] resolution_factor`.

Reuses `ck2ck3.map.heightmap_detail._interior_patch_spectrum` (the exact
estimator the pass itself measures its own deficit with, and the one
`scripts/report_map_paint_plots.py`/`heightmap_erosion_evidence.py` use) and
its baked-in `VANILLA_LAND_SPECTRUM` table -- so the number this script
prints is the same measurement the pass's own log line is built from, not a
second, possibly-disagreeing implementation.

`_interior_patch_spectrum` takes `km_per_px` explicitly and reads 256
heightmap-pixel all-land patches, so it is resolution-correct by
construction: at `resolution_factor = 2`, `km_per_px` is half vanilla's own
canvas figure and the same code path applies (docs/step_map_heightmap.md
§2i) -- no separate "2x mode" needed in this script, unlike
`measure_relief_shape.py`'s crop origins/pooling, which are canvas-px and
needed an explicit `--resolution-factor` flag.

Usage:
    uv run scripts/heightmap_2x_spectrum.py <heightmap.png> \\
        --resolution-factor 2 --tag ours_2x [--seed 1]
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ck2ck3.map.heightmap_detail import (  # noqa: E402
    VANILLA_LAND_SPECTRUM,
    _interior_patch_spectrum,
)

VANILLA_KM_PER_PX = 1.4839  # configs/faerun.toml [map.scale] vanilla_km_per_px
WATER_LEVEL = 4883


def load16(path: Path) -> np.ndarray:
    with Image.open(path) as im:
        return np.asarray(im.convert("I;16")).astype(np.float32)


def vanilla_ratio(k: np.ndarray, amp: np.ndarray) -> np.ndarray:
    vk = np.array([p[0] for p in VANILLA_LAND_SPECTRUM])
    va = np.array([p[1] for p in VANILLA_LAND_SPECTRUM])
    v_at_k = np.interp(k, vk, va)
    return amp / np.maximum(v_at_k, 1e-9)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("heightmap", type=Path)
    ap.add_argument("--resolution-factor", type=int, default=1)
    ap.add_argument("--tag", default="ours")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--out", type=Path,
                    default=ROOT / "docs/evidence/heightmap_2x/spectrum.csv")
    ap.add_argument("--append", action="store_true",
                    help="append to --out instead of overwriting (so 1x and "
                         "2x runs land in the same CSV)")
    args = ap.parse_args(argv)

    km_per_px = VANILLA_KM_PER_PX / args.resolution_factor
    heights = load16(args.heightmap)
    land = heights > WATER_LEVEL
    rng = np.random.default_rng(args.seed)
    k, amp, n_patches = _interior_patch_spectrum(heights, land, km_per_px, rng)
    if n_patches == 0:
        print(f"{args.tag}: no all-land interior patch fit -- nothing measured")
        return 1
    ratio = vanilla_ratio(k, amp)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if args.append and args.out.exists() else "w"
    write_header = mode == "w"
    with args.out.open(mode, newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        if write_header:
            w.writerow(["tag", "resolution_factor", "n_patches",
                        "cycles_per_km", "km", "amplitude_levels",
                        "ratio_to_vanilla"])
        for kk, aa, rr in zip(k, amp, ratio):
            w.writerow([args.tag, args.resolution_factor, n_patches,
                        round(float(kk), 5), round(1.0 / max(kk, 1e-9), 2),
                        round(float(aa), 2), round(float(rr), 3)])

    print(f"{args.tag} (resolution_factor={args.resolution_factor}, "
          f"{n_patches} interior patches):")
    print(f"{'cycles/km':>10} {'km':>7} {'amplitude':>10} {'vs vanilla':>11}")
    for target in (0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.50, 0.60):
        i = int(np.argmin(np.abs(k - target)))
        print(f"{k[i]:>10.4f} {1.0/max(k[i],1e-9):>7.2f} {amp[i]:>10.1f} "
              f"{ratio[i]:>10.2f}x")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
