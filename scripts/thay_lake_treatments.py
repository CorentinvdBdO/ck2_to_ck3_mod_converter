#!/usr/bin/env python3
"""Lane `thay-relief`: illustrative renders of the two lake treatments
proposed in `docs/step_map_heightmap.md` §2h iii, for the user to choose
between (or reject). Neither is wired into the real pipeline -- this is a
cheap, output-side visualisation of each idea on the Thay window only, not
an implementation: a wider shore ramp is a per-province coast-smoothing
change (`heightmap_detail_coast_smooth_px`, radius-selected by "how far
above the surrounding region is this water province"), and a marsh/land
conversion is a province-classification change, not a heightmap one -- both
belong to a human decision, not this script.

Usage: uv run python scripts/thay_lake_treatments.py [--heightmap PNG]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.ndimage import distance_transform_edt, gaussian_filter

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import relief_sharp_common as C  # noqa: E402
import thay_render as R  # noqa: E402

Image.MAX_IMAGE_PIXELS = None

#: illustrative only: how far the wider ramp reaches, canvas px (vs the
#: shipped heightmap_detail_coast_smooth_px = 4)
WIDE_RAMP_PX = 40.0


def wide_shore_ramp(h: np.ndarray, land: np.ndarray, wide_px: float = WIDE_RAMP_PX,
                    water_level: int = 4883) -> np.ndarray:
    """Land within ``wide_px`` of water eases down toward the shore instead
    of holding its height to a hard 4-px cliff edge."""
    out = h.astype(np.float32).copy()
    d = distance_transform_edt(land).astype(np.float32)
    near = land & (d <= wide_px)
    taper = np.clip(1.0 - d / wide_px, 0.0, 1.0) ** 1.5
    target = float(water_level) + 400.0  # a shore, not the water plane itself
    out[near] = out[near] * (1 - taper[near]) + target * taper[near]
    out[~land] = h[~land]
    return out


def marsh_fill(h: np.ndarray, land: np.ndarray, iterations: int = 400) -> tuple[np.ndarray, np.ndarray]:
    """Harmonic (Laplace) inpaint of every water pixel from its land
    neighbours -- what the lake's *surrounding* terrain implies should be
    there, i.e. a plausible marsh/land elevation. Returns ``(heights, land)``
    with the water pixels now land."""
    out = h.astype(np.float32).copy()
    water = ~land
    # seed with a smoothed version so the iteration starts close to converged
    seed = gaussian_filter(np.where(land, out, 0.0), 3, mode="nearest")
    norm = gaussian_filter(land.astype(np.float32), 3, mode="nearest")
    out[water] = (seed[water] / np.maximum(norm[water], 1e-3))
    for _ in range(iterations):
        blurred = gaussian_filter(out, 1.0, mode="nearest")
        out[water] = blurred[water]
    return out, np.ones_like(land, dtype=bool)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--heightmap",
                    default="/home/cvdbdo/git/paradox/ck3/wt/_out/thay-relief/map_data/heightmap.png")
    ap.add_argument("--out-dir", default=str(C.ROOT / "docs/evidence/thay_relief"))
    args = ap.parse_args()

    ys, xs = R.crop_slices()
    full = C.load16(Path(args.heightmap))
    h = full[ys, xs]
    land = h > C.WATER_LEVEL
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    ramp = wide_shore_ramp(h, land)
    R.save_hillshade(ramp, out / "hillshade_lake_wide_ramp.png",
                     "Thay - illustrative: wider shore ramp (not implemented)")
    R.save_oblique(ramp, out / "oblique_lake_wide_ramp.png",
                   "Thay - illustrative: wider shore ramp (not implemented)")

    filled, land_all = marsh_fill(h, land)
    R.save_hillshade(filled, out / "hillshade_lake_marsh_fill.png",
                     "Thay - illustrative: lake to marsh/land (not implemented)")
    R.save_oblique(filled, out / "oblique_lake_marsh_fill.png",
                   "Thay - illustrative: lake to marsh/land (not implemented)")
    print("wrote", out)


if __name__ == "__main__":
    main()
