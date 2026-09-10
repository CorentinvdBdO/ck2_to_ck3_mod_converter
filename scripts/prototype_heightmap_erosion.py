#!/usr/bin/env python3
"""Crop-sized bench for lane `erosion`'s two passes.

Not the shipped code -- `src/ck2ck3/map/heightmap_erosion.py` is.  This runs
the same two functions over one 512x512 canvas crop (Thay or the Spine of the
World, located by `scripts/heightmap_erosion_crops.py`) in about a second, so
the de-terrace threshold and the landscape-evolution constants can be swept
without a two-minute full-canvas conversion for every value.

It needs the plain rescale as a cached ``.npy`` because rebuilding it is the
slow part; `scripts/heightmap_erosion_evidence.py::plain_rescale_canvas` is
the function that makes one.

Usage:
  uv run python scripts/prototype_heightmap_erosion.py --npy /tmp/before.npy \
      [--region thay|spine] [--iterations 16] [--out /tmp/hillshade.png]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from ck2ck3.map import heightmap_erosion as he  # noqa: E402
import heightmap_structure_metrics as M  # noqa: E402

WATER_LEVEL = 4883
KM_PER_PX = 1.4839


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--npy", required=True, help="cached plain-rescale canvas")
    ap.add_argument("--region", default="thay")
    ap.add_argument("--sigma", type=float, default=2.2)
    ap.add_argument("--cliff-step", type=float, default=415.5)
    ap.add_argument("--iterations", type=int, default=16)
    ap.add_argument("--accum-iterations", type=int, default=3)
    ap.add_argument("--seed", type=int, default=1357)
    ap.add_argument("--out", default=None, help="write a hillshade PNG here")
    args = ap.parse_args()

    crops = json.loads(
        (ROOT / "docs/evidence/heightmap_erosion/crops.json").read_text()
    )
    c = crops[args.region]
    y, x, s = c["crop_y"], c["crop_x"], c["crop_side"]
    base = np.load(args.npy)[y:y + s, x:x + s].astype(np.float32)
    land = base > WATER_LEVEL

    t0 = time.time()
    h2 = he.deterrace_cliff_aware(base, args.sigma, args.cliff_step)
    t1 = time.time()
    field, diag = he.eroded_relief(
        h2, land, np.random.default_rng(args.seed),
        iterations=args.iterations, accum_iterations=args.accum_iterations,
    )
    t2 = time.time()
    print(f"{args.region}: de-terrace {t1 - t0:.2f}s "
          f"({he.deterrace_iterations(args.sigma)} steps), "
          f"erosion {t2 - t1:.2f}s  {diag}")
    for name, arr in (("plain", base), ("de-terraced", h2),
                      ("+ relief", h2 + 450.0 * field)):
        m = M.all_metrics(arr, land)
        print(f"  {name:12s} coherence {m['coherence']:.3f}  "
              f"drain_top1 {m['drain_top1_share']:.3f}  "
              f"align {M.channel_alignment(arr, land):.3f}")
    if args.out:
        from PIL import Image
        Image.fromarray(
            M.hillshade(h2 + 450.0 * field, KM_PER_PX)
        ).save(args.out)
        print(f"  wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
