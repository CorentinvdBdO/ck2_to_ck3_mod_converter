#!/usr/bin/env python3
"""Lane `thay-relief`, §2h (d) follow-up: is the ring still visible in
`scripts/thay_render.py`'s hillshade a water pin, or a real escarpment?

The coordinator's own diagnostic (`docs/evidence/thay_relief/diag_water_pin.png`,
made ad hoc, not scripted) overlaid every pixel at or below the water level on
the Thay hillshade to show the ring WAS a chain of pinned water provinces. This
lane's `final_v2` render (after `overrides/river_valleys.csv`) still shows a
visually near-identical ring in the same place -- expected only if the ring is
mostly the *real* Thaymount escarpment (§2h: a genuine 7,480-9,521-level closed
depression in the CK2 source itself, only ~20-30% reduced by
`heightmap_detail_source_adaptive_gain`, not the water pin this lane's own
five river provinces (`RIVER_MURGHOL` and neighbours) caused. This script makes
that distinction checkable by eye instead of asserted: pixels at/below the
water level are red, everything else is the ordinary greyscale hillshade. If
the six carved provinces (`overrides/river_valleys.csv`) no longer show red,
the fix reads correctly; whatever red remains is a defect this lane did not
touch.

Usage:
  uv run --with matplotlib python scripts/thay_water_pin_overlay.py
      [--mod DIR] [--region thay|spine] [--out FILE]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import relief_sharp_common as C  # noqa: E402
from thay_render import REGIONS, crop_slices, hillshade, world_height  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mod", default="/home/cvdbdo/git/paradox/ck3/wt/_out/thay-relief")
    ap.add_argument("--region", choices=sorted(REGIONS), default="thay")
    ap.add_argument("--out", default=str(ROOT / "docs/evidence/thay_relief/diag_water_pin_v2.png"))
    args = ap.parse_args()

    ys, xs = crop_slices(args.region)
    heights = C.load16(Path(args.mod) / "map_data/heightmap.png")[ys, xs]
    pinned = heights <= C.WATER_LEVEL

    z = world_height(heights)
    shade = hillshade(z)
    print(f"{args.region}: crop {heights.shape}, {int(pinned.sum())} px "
          f"({100 * pinned.mean():.2f} %) at/below water level {C.WATER_LEVEL}")

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    rgb = np.dstack([shade, shade, shade])
    rgb[pinned] = [1.0, 0.0, 0.0]
    fig, ax = plt.subplots(figsize=(8, 8 * z.shape[0] / z.shape[1]))
    ax.imshow(rgb, origin="upper")
    ax.set_title(
        f"{args.region.capitalize()} - water-pinned pixels in red "
        f"({int(pinned.sum())} px, {Path(args.mod).name})",
        fontsize=10,
    )
    ax.axis("off")
    fig.tight_layout()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
