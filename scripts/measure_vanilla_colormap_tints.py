#!/usr/bin/env python3
"""Measure vanilla's own per-material `colormap.dds` tint.

Lane `colormap-fix`: `docs/step_map_paint.md` §9.6 found the CK2-colormap
resample wrong twice over (satellite-image content, saturated colour). The
replacement is a **measured tint per CK3 terrain material**, and vanilla's
own files give us the measurement for free: `gfx/map/terrain/detail_index.tga`
channel 0 is the primary material ordinal per pixel (`verified`,
`ck2ck3.map.terrain_paint`), and `colormap.dds` is the tint at the exact same
pixel (both 9216x4608 - `verified`, PIL `.size`) - so the per-material mean
colour is a direct measurement of "what tint does vanilla itself use where it
paints this material", not a guess.

Decode method, `verified`: Pillow 12.3 decodes vanilla's DXT5 `colormap.dds`
to a full per-pixel RGB array natively (`Image.open(...).convert("RGB")`) in
~0.3 s for the whole 9216x4608 image - this is a **full BC3 decode**, not the
per-4x4-block colour-endpoint approximation the lane brief allowed for if a
decoder were not available. Using the real per-pixel result is strictly more
accurate and no slower, so that is what this script does.

Water definition, `verified`: vanilla's own sea/lake province ids from
`map_data/default.map` (`sea_zones` + `lakes`, both `RANGE`/`LIST` forms),
rasterised via `map_data/provinces.png` + `definition.csv` - not "pixels
whose material is a sea material", because vanilla's own `materials.settings`
has no material named for water at all (open ocean is never sampled by the
detail_index/intensity renderer either, `mappings/terrain_paint.csv`'s own
`sea`/`coastal_sea` notes) - the colormap tint over water is a real, sampled
value all the same (`docs/step_map_paint.md` §9.6's own 131,129,131 ocean
sample), so vanilla province geometry is the only available water/land
signal.

Output: docs/evidence/vanilla_colormap_tints.csv (material id, name, sample
count, mean RGB, per-channel stddev), one row per material ordinal actually
present in vanilla's own detail_index primary channel, plus a synthetic
"water" row (material_id = -1).

Usage::

    uv run scripts/measure_vanilla_colormap_tints.py [ck3_game_dir]
"""

from __future__ import annotations

import csv
import re
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from ck2ck3.map import terrain_paint  # noqa: E402

DEFAULT_GAME = Path(
    "/home/cvdbdo/.local/share/Steam/steamapps/common/Crusader Kings III/game"
)
OUT_CSV = REPO / "docs" / "evidence" / "vanilla_colormap_tints.csv"

_RANGE_RE = re.compile(r"(?:sea_zones|lakes)\s*=\s*RANGE\s*\{\s*(\d+)\s+(\d+)\s*\}")
_LIST_RE = re.compile(r"(?:sea_zones|lakes)\s*=\s*LIST\s*\{([^}]*)\}")


def read_water_ids(default_map: Path) -> set[int]:
    """``sea_zones``/``lakes`` province ids from ``map_data/default.map``."""
    txt = default_map.read_text(encoding="utf-8-sig", errors="replace")
    ids: set[int] = set()
    for a, b in _RANGE_RE.findall(txt):
        ids.update(range(int(a), int(b) + 1))
    for body in _LIST_RE.findall(txt):
        ids.update(int(x) for x in body.split())
    return ids


def read_definition(path: Path) -> dict[tuple[int, int, int], int]:
    out: dict[tuple[int, int, int], int] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        r = csv.reader(fh, delimiter=";")
        next(r, None)
        for row in r:
            if len(row) < 4:
                continue
            try:
                pid, red, green, blue = (
                    int(row[0]), int(row[1]), int(row[2]), int(row[3]),
                )
            except ValueError:
                continue
            out[(red, green, blue)] = pid
    return out


def province_id_raster(provinces_png: np.ndarray, definition: dict) -> np.ndarray:
    """RGB provinces.png -> province id array, vectorised via a colour LUT."""
    h, w = provinces_png.shape[:2]
    flat = provinces_png.reshape(-1, 3)
    keys = (flat[:, 0].astype(np.int64) << 16) | (flat[:, 1].astype(np.int64) << 8) | flat[:, 2]
    uniq_keys, inverse = np.unique(keys, return_inverse=True)
    lut = np.zeros(len(uniq_keys), dtype=np.int32)
    for i, k in enumerate(uniq_keys.tolist()):
        r, g, b = (k >> 16) & 0xFF, (k >> 8) & 0xFF, k & 0xFF
        lut[i] = definition.get((r, g, b), -1)
    return lut[inverse].reshape(h, w)


def main(argv: list[str]) -> int:
    game_dir = Path(argv[1]) if len(argv) > 1 else DEFAULT_GAME
    t0 = time.time()

    print("decoding colormap.dds (DXT5, full BC3 via Pillow)...")
    with Image.open(game_dir / "gfx" / "map" / "terrain" / "colormap.dds") as im:
        colormap = np.asarray(im.convert("RGB")).astype(np.int32)
    print(f"  {colormap.shape} in {time.time() - t0:.2f}s")

    print("decoding detail_index.tga...")
    t1 = time.time()
    with Image.open(game_dir / "gfx" / "map" / "terrain" / "detail_index.tga") as im:
        detail_index = np.asarray(im.convert("RGBA"))
    print(f"  {detail_index.shape} in {time.time() - t1:.2f}s")
    if detail_index.shape[:2] != colormap.shape[:2]:
        raise SystemExit(
            f"detail_index {detail_index.shape[:2]} != colormap "
            f"{colormap.shape[:2]}; pixel-alignment assumption broken"
        )
    primary_ord = detail_index[..., 0]

    print("rasterising province ids...")
    t2 = time.time()
    with Image.open(game_dir / "map_data" / "provinces.png") as im:
        provinces_png = np.asarray(im.convert("RGB"))
    definition = read_definition(game_dir / "map_data" / "definition.csv")
    province_ids = province_id_raster(provinces_png, definition)
    print(f"  {province_ids.shape} in {time.time() - t2:.2f}s")

    water_ids = read_water_ids(game_dir / "map_data" / "default.map")
    water_mask = np.isin(province_ids, list(water_ids))
    land_mask = (~water_mask) & (province_ids > 0)
    print(
        f"water pixels: {int(water_mask.sum())}, land pixels: {int(land_mask.sum())}, "
        f"unclaimed/id<=0: {int((province_ids <= 0).sum())}"
    )

    ordinals = terrain_paint.material_ordinals(
        game_dir / "gfx" / "map" / "terrain" / "materials.settings"
    )
    name_by_ordinal = {v: k for k, v in ordinals.items()}
    n_ord = int(primary_ord.max()) + 1

    land_ord = primary_ord[land_mask].astype(np.int64)
    land_rgb = colormap[land_mask]

    rows = []
    counts = np.bincount(land_ord, minlength=n_ord)
    sums = np.zeros((n_ord, 3), dtype=np.float64)
    sumsq = np.zeros((n_ord, 3), dtype=np.float64)
    for c in range(3):
        sums[:, c] = np.bincount(land_ord, weights=land_rgb[:, c], minlength=n_ord)
        sumsq[:, c] = np.bincount(
            land_ord, weights=land_rgb[:, c].astype(np.float64) ** 2, minlength=n_ord
        )

    for ordv in range(n_ord):
        cnt = int(counts[ordv])
        if cnt == 0:
            continue
        mean = sums[ordv] / cnt
        var = np.clip(sumsq[ordv] / cnt - mean**2, 0, None)
        std = np.sqrt(var)
        rows.append(
            {
                "material_id": ordv,
                "material_name": name_by_ordinal.get(ordv, f"<unknown ordinal {ordv}>"),
                "sample_count": cnt,
                "mean_r": round(float(mean[0]), 2),
                "mean_g": round(float(mean[1]), 2),
                "mean_b": round(float(mean[2]), 2),
                "std_r": round(float(std[0]), 2),
                "std_g": round(float(std[1]), 2),
                "std_b": round(float(std[2]), 2),
            }
        )

    # water: a synthetic "material" row, material_id = -1
    wrgb = colormap[water_mask].astype(np.float64)
    wmean = wrgb.mean(axis=0)
    wstd = wrgb.std(axis=0)
    rows.append(
        {
            "material_id": -1,
            "material_name": "water (sea_zones + lakes provinces)",
            "sample_count": int(water_mask.sum()),
            "mean_r": round(float(wmean[0]), 2),
            "mean_g": round(float(wmean[1]), 2),
            "mean_b": round(float(wmean[2]), 2),
            "std_r": round(float(wstd[0]), 2),
            "std_g": round(float(wstd[1]), 2),
            "std_b": round(float(wstd[2]), 2),
        }
    )

    rows.sort(key=lambda r: -r["sample_count"])
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    print(f"wrote {OUT_CSV} ({len(rows)} rows) in {time.time() - t0:.2f}s total")
    print("\ntop 15 by sample count:")
    for row in rows[:15]:
        print(
            f"  {row['material_name']:32s} n={row['sample_count']:>9} "
            f"mean=({row['mean_r']:.0f},{row['mean_g']:.0f},{row['mean_b']:.0f}) "
            f"std=({row['std_r']:.1f},{row['std_g']:.1f},{row['std_b']:.1f})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
