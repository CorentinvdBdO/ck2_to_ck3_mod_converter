#!/usr/bin/env python3
"""Lane `relief-pits`: the interior land spectrum of any finished map vs vanilla.

The same measurement §2c and §2d quote -- 48 all-land 256 px interior patches,
`heightmap_erosion_evidence`'s own estimator -- but runnable against an
arbitrary list of `heightmap.png` files, so the cost of moving
`heightmap_detail_fill_min_cycles_per_km` can be read off without a second
full conversion.

Usage:
  uv run python scripts/relief_pits_spectrum.py \
      after=/path/to/heightmap.png [name=path ...]
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import heightmap_erosion_evidence as E  # noqa: E402
import relief_sharp_common as C  # noqa: E402
from relief_pits_diagnose import write_csv  # noqa: E402

OUT = C.ROOT / "docs/evidence/relief_pits"
#: the bands §2c/§2d report, cycles/km
BANDS = (0.0105, 0.0158, 0.0211, 0.029, 0.0395, 0.05, 0.0711,
         0.10, 0.15, 0.20, 0.30)


def main() -> None:
    specs = [s for s in sys.argv[1:] if "=" in s]
    if not specs:
        print(__doc__.strip())
        raise SystemExit(2)
    base = C.plain_rescale_canvas()
    maps = {"plain_rescale": base}
    for s in specs:
        name, _, path = s.partition("=")
        maps[name] = C.load16(Path(path))
    # one patch set, all-land in every map, so every column is the same ground
    patches = E.find_land_patches(
        [(a, C.WATER_LEVEL) for a in maps.values()], E.PATCH, E.PATCHES)
    print(f"{len(patches)} all-land {E.PATCH} px interior patches")
    van = E.load(E.GAME / "map_data/heightmap.png")
    vp = E.find_land_patches([(van, E.VANILLA_WATER)], E.PATCH, E.PATCHES)
    vk, va = E.mean_spectrum(van, vp, E.KM_PX_VANILLA)
    del van
    # one spectrum per map, not one per (map, band): the patch FFTs are the
    # expensive part
    spectra = {n: E.mean_spectrum(a, patches, C.KM_PX_OURS)
               for n, a in maps.items()}
    rows = []
    for band in BANDS:
        v = float(np.interp(band, vk, va))
        row = {"cycles_per_km": band, "km": round(1.0 / band, 1),
               "vanilla_levels": round(v, 1)}
        for name, (k, a) in spectra.items():
            row[name] = round(float(np.interp(band, k, a)) / max(v, 1e-9), 3)
        rows.append(row)
        print("  " + "  ".join(f"{k}={v}" for k, v in row.items()))
    write_csv(OUT / "spectrum_bands.csv", rows)


if __name__ == "__main__":
    main()
