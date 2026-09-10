#!/usr/bin/env python3
"""The pictures for §2d: transects across Thay's escarpments and hillshades.

One PNG per crop with the plain rescale, build 13 and this build overlaid on
the same transect, plus a side-by-side hillshade -- the moat is a shape, and
a shape is settled by a picture and a profile, not only by a statistic.

Usage:
  uv run --with matplotlib python scripts/relief_sharp_figures.py \
      --after /path/to/lane/out/map_data/heightmap.png
Writes: docs/evidence/relief_sharp/transect_<crop>.png, hillshade_<crop>.png
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import relief_sharp_common as C  # noqa: E402


def hillshade(a: np.ndarray, az: float = 315.0, alt: float = 35.0,
              z: float = 0.02) -> np.ndarray:
    """Standard hillshade.  `z` is small on purpose: the array is in 16-bit
    levels, so a gradient is hundreds of units per pixel and any `z` near 1
    drives `arctan` to 90 degrees everywhere and prints a black-and-white
    threshold instead of a relief."""
    gy, gx = np.gradient(a.astype(np.float32) * z)
    slope = np.pi / 2 - np.arctan(np.hypot(gx, gy))
    aspect = np.arctan2(-gx, gy)
    a_r, l_r = np.radians(360.0 - az + 90.0), np.radians(alt)
    v = (np.sin(l_r) * np.sin(slope)
         + np.cos(l_r) * np.cos(slope) * np.cos(a_r - aspect))
    v = np.clip(v, 0, 1)
    lo, hi = np.percentile(v, (2, 98))
    return np.clip((v - lo) / max(hi - lo, 1e-6), 0, 1)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--after", required=True)
    ap.add_argument("--rows", type=int, nargs="*", default=[196, 300])
    args = ap.parse_args()
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    base_c = C.plain_rescale_canvas()
    b13 = C.load16(C.LIVE_MOD / "map_data/heightmap.png")
    after = C.load16(Path(args.after))
    C.OUT.mkdir(parents=True, exist_ok=True)

    for region in C.crops():
        ys, xs = C.crop_box(region)
        b, o, f = base_c[ys, xs], b13[ys, xs], after[ys, xs]
        land = C.province_land_mask(f) & C.province_land_mask(o)

        fig, axes = plt.subplots(len(args.rows), 1,
                                 figsize=(11, 3.2 * len(args.rows)), sharex=True)
        axes = np.atleast_1d(axes)
        for ax, row in zip(axes, args.rows):
            x = np.arange(b.shape[1]) * C.KM_PX_OURS
            ax.plot(x, b[row], lw=1.4, color="#444", label="plain rescale")
            ax.plot(x, o[row], lw=1.0, color="#c1442a", label="build 13")
            ax.plot(x, f[row], lw=1.0, color="#2a6fc1", label="this build")
            ax.axhline(C.WATER_LEVEL, lw=0.7, ls=":", color="#888")
            ax.set_ylabel("16-bit level")
            ax.set_title(f"{region}, canvas row {C.crops()[region]['crop_y'] + row}",
                         fontsize=9, loc="left")
            ax.grid(alpha=0.25)
        axes[0].legend(fontsize=8, ncol=3)
        axes[-1].set_xlabel("km across the crop")
        fig.tight_layout()
        out = C.OUT / f"transect_{region}.png"
        fig.savefig(out, dpi=110)
        plt.close(fig)
        print(f"wrote {out}")

        fig, axes = plt.subplots(1, 3, figsize=(15, 5.2))
        for ax, (name, arr) in zip(axes, (("plain rescale", b),
                                          ("build 13", o),
                                          ("this build", f))):
            ax.imshow(hillshade(arr), cmap="gray", vmin=0, vmax=1)
            ax.set_title(f"{region}: {name}", fontsize=10)
            ax.set_xticks([]); ax.set_yticks([])
        fig.tight_layout()
        out = C.OUT / f"hillshade_{region}.png"
        fig.savefig(out, dpi=110)
        plt.close(fig)
        print(f"wrote {out} (land {land.mean():.1%})")


if __name__ == "__main__":
    main()
