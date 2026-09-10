#!/usr/bin/env python3
"""The finished 2x canvas, measured: spectrum to 0.6 cycles/km, cliffs, moat.

Reads a `map` run made with `[map.heightmap] resolution_factor = 2` and puts
it next to the 1x build and vanilla on the report's own patch geometry
(48 all-land 256 px patches, `scripts/report_map_paint_plots.py`).

Usage:
  uv run python scripts/relief_sharp_2x_full.py --two-x DIR --one-x DIR
Writes: docs/evidence/relief_sharp/two_x_canvas.csv
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import relief_sharp_common as C  # noqa: E402
from relief_sharp_2x import mean_spectrum, radial, sharpness  # noqa: E402,F401


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--two-x", required=True)
    ap.add_argument("--one-x", required=True)
    args = ap.parse_args()

    rows = []
    van = C.load16(C.GAME / "map_data/heightmap.png")
    k_v, a_v, n_v = mean_spectrum(van, van > C.VANILLA_WATER,
                                  C.KM_PX_VANILLA, want=48)
    del van
    print(f"vanilla {n_v} patches", flush=True)

    out = {}
    for name, d, kmpx in (("ours_1x", args.one_x, C.KM_PX_OURS),
                          ("ours_2x", args.two_x, C.KM_PX_OURS / 2)):
        a = C.load16(Path(d) / "map_data/heightmap.png")
        land = C.province_land_mask(a)
        k, amp, n = mean_spectrum(a, land, kmpx, want=48)
        out[name] = (k, amp)
        print(f"{name} {a.shape[1]}x{a.shape[0]} {n} patches "
              f"Nyquist {0.5 / kmpx:.3f} c/km", flush=True)
        # cliff sharpness on the Thay crop, per km so the two compare
        f = 2 if name == "ours_2x" else 1
        ci = C.crops()["thay"]
        y, x, s = ci["crop_y"] * f, ci["crop_x"] * f, ci["crop_side"] * f
        crop = a[y:y + s, x:x + s]
        sh = sharpness(crop, kmpx, land[y:y + s, x:x + s])
        print(f"  thay {sh}", flush=True)
        rows.append({"map": name, "kind": "sharpness", **sh})
        del a, land

    for f in (0.02, 0.03, 0.05, 0.07, 0.1, 0.15, 0.2, 0.25, 0.3,
              0.35, 0.4, 0.5, 0.6):
        r = {"map": "-", "kind": "spectrum", "cycles_per_km": f,
             "vanilla": round(float(np.interp(f, k_v, a_v)), 1)}
        for name, (k, amp) in out.items():
            r[name] = (round(float(np.interp(f, k, amp)), 1)
                       if f <= k[-1] else None)
            r[f"{name}_over_vanilla"] = (
                round(r[name] / r["vanilla"], 2) if r[name] else None)
        rows.append(r)
        print(r, flush=True)

    keys: list[str] = []
    for r in rows:
        for kk in r:
            if kk not in keys:
                keys.append(kk)
    p = C.OUT / "two_x_canvas.csv"
    with p.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {p}")


if __name__ == "__main__":
    main()
