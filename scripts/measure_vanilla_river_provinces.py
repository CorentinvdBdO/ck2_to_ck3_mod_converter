#!/usr/bin/env python3
"""Lane `thay-relief`: does vanilla CK3 ever draw a `river_provinces` pixel
above its own water level?

The coordinator's §2h (d) diagnosis: Thay's remaining rings are CK2 river
provinces (`RIVER_MURGHOL`, ...), 2-4 px wide, pinned to CK3's global water
level by `heightmap_detail.apply`'s own land/water invariant, cutting a
canyon round the plateau. Before proposing a `valley` treatment that keeps a
province in `river_provinces` but does NOT pin its heightmap, this checks
whether vanilla itself ever does that -- if vanilla's own river-province
pixels are always at or below `WATERLEVEL`, an above-water river province is
not a legal shape CK3 expects and `valley` should fall back to plain `land`
(+ a drawn `rivers.png` line) instead.

Usage:  uv run python scripts/measure_vanilla_river_provinces.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

Image.MAX_IMAGE_PIXELS = None

ROOT = Path(__file__).resolve().parents[1]
GAME = ROOT / "../claudespace/game_files"

# vanilla common/defines/00_defines.txt:74-77
VANILLA_WATERLEVEL_16BIT = round(3.0 / 50 * 65535)  # 3932


def read_definition_ids(path: Path) -> dict[tuple[int, int, int], int]:
    out = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        parts = line.split(";")
        if len(parts) < 5 or not parts[0].strip().isdigit():
            continue
        pid = int(parts[0])
        out[(int(parts[1]), int(parts[2]), int(parts[3]))] = pid
    return out


def expand_ranges(spec: str) -> set[int]:
    import re
    ids: set[int] = set()
    for m in re.finditer(r"RANGE\s*\{\s*(\d+)\s+(\d+)\s*\}", spec):
        ids.update(range(int(m.group(1)), int(m.group(2)) + 1))
    body = re.sub(r"RANGE\s*\{[^}]*\}", " ", spec)
    ids.update(int(t) for t in re.findall(r"\b\d+\b", body))
    return ids


def main() -> None:
    dm_text = (GAME / "map_data/default.map").read_text(encoding="utf-8", errors="replace")
    import re
    river_spec = " ".join(re.findall(r"^river_provinces\s*=\s*(.*)$", dm_text, re.M))
    river_ids = expand_ranges(river_spec)
    print(f"vanilla river_provinces: {len(river_ids)} ids")

    rgb_to_id = read_definition_ids(GAME / "map_data/definition.csv")
    id_to_rgb = {v: k for k, v in rgb_to_id.items()}

    with Image.open(GAME / "map_data/provinces.png") as im:
        prov = np.asarray(im.convert("RGB"))
    with Image.open(GAME / "map_data/heightmap.png") as im:
        heights = np.asarray(im)
    print(f"heightmap dtype {heights.dtype}, shape {heights.shape}, "
          f"provinces.png shape {prov.shape[:2]}")

    key = (prov[..., 0].astype(np.int64) << 16
           | prov[..., 1].astype(np.int64) << 8 | prov[..., 2])
    # vanilla's heightmap.png is 2x provinces.png in each dimension
    # (CLAUDE.md: "vanilla map is 9216x4608, heightmap 16-bit at 2x") --
    # nearest-neighbour upsample the province-id key to match, the same
    # convention ck2ck3.map.build._nn_upsample uses for resolution_factor
    fy = heights.shape[0] // key.shape[0]
    fx = heights.shape[1] // key.shape[1]
    if (fy, fx) != (1, 1):
        key = np.repeat(np.repeat(key, fy, axis=0), fx, axis=1)
        print(f"upsampled province key {fy}x{fx} to match heightmap.png")

    all_vals = []
    above = []
    per_province_max = []
    for pid in sorted(river_ids):
        rgb = id_to_rgb.get(pid)
        if rgb is None:
            continue
        k = rgb[0] << 16 | rgb[1] << 8 | rgb[2]
        mask = key == k
        n = int(mask.sum())
        if n == 0:
            continue
        vals = heights[mask].astype(np.int64)
        all_vals.append(vals)
        per_province_max.append((pid, int(vals.max()), n))
        if vals.max() > VANILLA_WATERLEVEL_16BIT:
            above.append((pid, int(vals.min()), int(vals.max()), n))

    if all_vals:
        allv = np.concatenate(all_vals)
        print(f"{len(all_vals)} river provinces with pixels, {allv.size} px total")
        print(f"water level (16-bit) = {VANILLA_WATERLEVEL_16BIT}")
        print(f"river-province pixel heights: min {allv.min()} p50 {int(np.median(allv))} "
              f"p99 {int(np.percentile(allv, 99))} max {allv.max()}")
        print(f"{(allv > VANILLA_WATERLEVEL_16BIT).sum()} / {allv.size} px "
              f"({100 * (allv > VANILLA_WATERLEVEL_16BIT).mean():.3f} %) strictly above water level")
    print(f"{len(above)} river provinces with at least one px above water level:")
    for pid, lo, hi, n in sorted(above, key=lambda r: -r[2])[:20]:
        print(f"  province {pid}: {n} px, height [{lo}, {hi}]")


if __name__ == "__main__":
    main()
