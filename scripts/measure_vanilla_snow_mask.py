#!/usr/bin/env python3
"""Measure vanilla's own per-material `snow_mask.dds` R-channel value.

Lane `water-border` needs a measured "no-snow" value per CK3 terrain
material, because `gfx/FX/dynamic_masks.fxh` samples `snow_mask.dds`
**channel R only** in whole-map UV space (V flipped) to build
`_NoSnowMask`::

    _NoSnowMask = 1.0f - PdxTex2D(SnowMaskMap, float2(MapCoords.x, 1.0f - MapCoords.y)).r;

(`verified`, `gfx/FX/dynamic_masks.fxh:134` and `:209`) - R=255 means "snow
never falls here", R=0 means "snow allowed". A custom map that ships no
override of this file inherits vanilla's Earth heat belt (low R at the poles,
high R over the Sahara/Arabia/India band) painted over its own, differently
shaped continent. This script measures vanilla's own R value per terrain
*material*, the same way `scripts/measure_vanilla_colormap_tints.py` measures
colormap.dds tints, to test whether a custom map could paint R from its own
terrain-code grid. It cannot — see the rejection note below.

G, B and A of `snow_mask.dds` are sampled **tiled**, not map-projected
(`SampleNoTile(SnowMaskMap, Coords * _SnowNoiseTiling)` at
`dynamic_masks.fxh:105`, and `MapCoords * 5.0` at `:144`/`:218`) - they are a
noise texture, not geography, so this script only records their *global*
means (printed, not per-material) as a flat fallback fill for whatever the
writer puts in those channels.

Resolution mismatch, `verified` (PIL `.size`): `snow_mask.dds` is
4608x2304, but `detail_index.tga` and `provinces.png` (used for the
material-ordinal and water masks, exactly as in
`measure_vanilla_colormap_tints.py`) are 9216x4608 - exactly double in both
dimensions. This script decimates `detail_index` and the province-id raster
by 2 with `[::2, ::2]` (nearest-neighbour subsample, not an area average) to
align them to `snow_mask`'s grid, and asserts the resulting shapes match
`snow_mask`'s before measuring.

Decode method, `verified`: `snow_mask.dds` is BC7 (`DX10` header, unlike
colormap.dds's DXT5/BC3); Pillow 12.3 decodes it natively via
`Image.open(...).convert("RGBA")` in well under a second for the full
4608x2304 image, a full per-pixel decode exactly as
`measure_vanilla_colormap_tints.py` does for colormap.dds.

Water definition: identical to `measure_vanilla_colormap_tints.py` - vanilla's
own `sea_zones` + `lakes` province ids from `map_data/default.map`,
rasterised via `map_data/provinces.png` + `definition.csv` (decimated by 2 to
match `snow_mask`'s resolution).

Output: docs/evidence/vanilla_snow_mask.csv (material id, name, sample count,
mean/std R, mean G/B/A), one row per material ordinal actually present in
vanilla's own (decimated) detail_index primary channel, plus a synthetic
"water" row (material_id = -1).

**The per-material measurement is evidence for a rejected approach, kept
because the rejection is the finding.** Terrain material turns out to be a
*weak* proxy for vanilla's no-snow belt: the per-material standard deviation
routinely exceeds the mean (``desert_02`` mean 48, std 81), and the ranking it
produces is nonsense — ``desert`` 48 against ``mountains`` 198, ``taiga`` the
only unambiguous key at 0.01 +/- 0.23. Vanilla reuses one material across
every latitude it occurs at, so the material id carries almost no climate.
What R *does* vary with is **latitude**: the 16-band north-to-south profile
runs 0, 0, 0, 2, 4, 59, 85, 72, 88, 149, 159, 138, 143, 122, 44, 0. So this
script also writes the per-row-fraction profile, which is what settles the
question: vanilla's R is an **Earth-latitude painting**, and Faerûn's map
carries no Earth latitudes to transfer it onto. Both derivations are therefore
rejected and ``ck2ck3.map.water`` ships a flat ``R = 0`` — see
``docs/step_map_water_border.md`` §4 for why that is the neutral value and not
the raster mean.

Outputs:
    docs/evidence/vanilla_snow_mask.csv      per-material R (rejected proxy)
    docs/evidence/vanilla_snow_latitude.csv  per-latitude R (rejected proxy)

Usage::

    uv run scripts/measure_vanilla_snow_mask.py [ck3_game_dir]
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

#: `measure_vanilla_colormap_tints.py`'s own DEFAULT_GAME points at the Steam
#: path, which does not resolve on this machine; this is the dir that does
#: (`verified`: it is the `game/` dir itself - `gfx/`, `map_data/` are direct
#: children).
DEFAULT_GAME = Path("/home/cvdbdo/git/paradox/ck3/claudespace/game_files")
OUT_CSV = REPO / "docs" / "evidence" / "vanilla_snow_mask.csv"
LATITUDE_CSV = REPO / "docs" / "evidence" / "vanilla_snow_latitude.csv"

#: rows of the latitude profile; 64 bands over 2304 texels is 36 texels each,
#: fine enough for a belt that varies over thousands.
LATITUDE_BANDS = 64

LATITUDE_HEADER = """\
# GENERATED by scripts/measure_vanilla_snow_mask.py from vanilla's own
# gfx/map/textures/snow_mask.dds. Evidence, not a table the converter reads.
#
# gfx/FX/dynamic_masks.fxh:134 and :209 read this texture's R channel at a
# whole-map UV as `_NoSnowMask = 1 - R`: 255 means snow never falls at that
# spot of the map, 0 means the engine's own winter model decides. Ship no
# override and a custom map inherits the Sahara's heat belt at the Sahara's
# latitude.
#
# R varies with latitude, not with terrain material: per-material the standard
# deviation exceeds the mean and the ranking inverts (desert 48, mountains
# 198), because vanilla reuses one material at every latitude it occurs at.
# See docs/evidence/vanilla_snow_mask.csv for that rejected measurement and
# docs/step_map_water_border.md for the decision.
#
#   band       0 = northernmost, LATITUDE_BANDS-1 = southernmost
#   row_frac   the band's centre as a fraction of map height, north to south
#   no_snow_r  vanilla's own mean R over that band, 0-255
#
# This profile is Earth's, and Faerun's map carries no Earth latitudes to map
# it onto, so the converter ships a flat R = 0 instead and lets the shader's
# own hemisphere term (dynamic_masks.fxh:110, _SnowHemisphere) place the snow
# line. docs/step_map_water_border.md section 4.
"""

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

    print("decoding snow_mask.dds (BC7, full decode via Pillow)...")
    with Image.open(game_dir / "gfx" / "map" / "textures" / "snow_mask.dds") as im:
        snow_mask = np.asarray(im.convert("RGBA")).astype(np.int32)
    print(f"  {snow_mask.shape} in {time.time() - t0:.2f}s")

    print("decoding detail_index.tga...")
    t1 = time.time()
    with Image.open(game_dir / "gfx" / "map" / "terrain" / "detail_index.tga") as im:
        detail_index_full = np.asarray(im.convert("RGBA"))
    print(f"  {detail_index_full.shape} in {time.time() - t1:.2f}s")

    # snow_mask (4608x2304) is exactly half detail_index's resolution
    # (9216x4608) in both dimensions - decimate by 2 to align.
    detail_index = detail_index_full[::2, ::2]
    if detail_index.shape[:2] != snow_mask.shape[:2]:
        raise SystemExit(
            f"decimated detail_index {detail_index.shape[:2]} != snow_mask "
            f"{snow_mask.shape[:2]}; pixel-alignment assumption broken"
        )
    primary_ord = detail_index[..., 0]

    print("rasterising province ids...")
    t2 = time.time()
    with Image.open(game_dir / "map_data" / "provinces.png") as im:
        provinces_png = np.asarray(im.convert("RGB"))
    definition = read_definition(game_dir / "map_data" / "definition.csv")
    province_ids_full = province_id_raster(provinces_png, definition)
    province_ids = province_ids_full[::2, ::2]
    if province_ids.shape != snow_mask.shape[:2]:
        raise SystemExit(
            f"decimated province_ids {province_ids.shape} != snow_mask "
            f"{snow_mask.shape[:2]}; pixel-alignment assumption broken"
        )
    print(f"  {province_ids.shape} in {time.time() - t2:.2f}s (decimated)")

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
    land_r = snow_mask[..., 0][land_mask]

    rows = []
    counts = np.bincount(land_ord, minlength=n_ord)
    sums_r = np.bincount(land_ord, weights=land_r, minlength=n_ord)
    sumsq_r = np.bincount(land_ord, weights=land_r.astype(np.float64) ** 2, minlength=n_ord)
    sums_g = np.bincount(land_ord, weights=snow_mask[..., 1][land_mask], minlength=n_ord)
    sums_b = np.bincount(land_ord, weights=snow_mask[..., 2][land_mask], minlength=n_ord)
    sums_a = np.bincount(land_ord, weights=snow_mask[..., 3][land_mask], minlength=n_ord)

    for ordv in range(n_ord):
        cnt = int(counts[ordv])
        if cnt == 0:
            continue
        mean_r = sums_r[ordv] / cnt
        var_r = max(sumsq_r[ordv] / cnt - mean_r**2, 0)
        rows.append(
            {
                "material_id": ordv,
                "material_name": name_by_ordinal.get(ordv, f"<unknown ordinal {ordv}>"),
                "sample_count": cnt,
                "mean_r": round(float(mean_r), 2),
                "std_r": round(float(var_r**0.5), 2),
                "mean_g": round(float(sums_g[ordv] / cnt), 2),
                "mean_b": round(float(sums_b[ordv] / cnt), 2),
                "mean_a": round(float(sums_a[ordv] / cnt), 2),
            }
        )

    # water: a synthetic "material" row, material_id = -1
    wpix = snow_mask[water_mask].astype(np.float64)
    wmean = wpix.mean(axis=0)
    wstd_r = wpix[:, 0].std()
    rows.append(
        {
            "material_id": -1,
            "material_name": "water (sea_zones + lakes provinces)",
            "sample_count": int(water_mask.sum()),
            "mean_r": round(float(wmean[0]), 2),
            "std_r": round(float(wstd_r), 2),
            "mean_g": round(float(wmean[1]), 2),
            "mean_b": round(float(wmean[2]), 2),
            "mean_a": round(float(wmean[3]), 2),
        }
    )

    rows.sort(key=lambda r: -r["sample_count"])
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "material_id", "material_name", "sample_count",
        "mean_r", "std_r", "mean_g", "mean_b", "mean_a",
    ]
    with OUT_CSV.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    print(f"wrote {OUT_CSV} ({len(rows)} rows) in {time.time() - t0:.2f}s total")
    print("\ntop 15 by sample count:")
    for row in rows[:15]:
        print(
            f"  {row['material_name']:32s} n={row['sample_count']:>9} "
            f"mean_r={row['mean_r']:>6.1f} std_r={row['std_r']:>5.1f} "
            f"mean_gba=({row['mean_g']:.0f},{row['mean_b']:.0f},{row['mean_a']:.0f})"
        )

    # global fallback values for the flat noise channels (G/B/A), and the
    # overall land mean R, needed by the writer as a whole-raster fallback.
    all_r = snow_mask[..., 0]
    all_g = snow_mask[..., 1]
    all_b = snow_mask[..., 2]
    all_a = snow_mask[..., 3]
    land_mean_r = float(land_r.mean())
    global_mean_g = float(all_g.mean())
    global_mean_b = float(all_b.mean())
    global_mean_a = float(all_a.mean())
    print(f"\nALL-LAND mean R: {land_mean_r:.2f}")
    print(f"GLOBAL (whole raster) mean G: {global_mean_g:.2f}")
    print(f"GLOBAL (whole raster) mean B: {global_mean_b:.2f}")
    print(f"GLOBAL (whole raster) mean A: {global_mean_a:.2f}")
    print(f"(reference, unused above) whole-raster mean R: {float(all_r.mean()):.2f}")

    write_latitude_profile(all_r)
    return 0


def write_latitude_profile(red: np.ndarray, bands: int = LATITUDE_BANDS) -> None:
    """The north-to-south mean of R: the evidence that R is a latitude belt.

    Measured over every pixel, land and water alike: the shader reads R at the
    pixel's own map position without asking what is under it, and vanilla's own
    oceans carry the same belt as the land beside them.
    """
    h = red.shape[0]
    per_band = np.array_split(red.astype(np.float64), bands, axis=0)
    LATITUDE_CSV.parent.mkdir(parents=True, exist_ok=True)
    with LATITUDE_CSV.open("w", newline="", encoding="utf-8") as fh:
        fh.write(LATITUDE_HEADER)
        w = csv.DictWriter(fh, fieldnames=["band", "row_frac", "no_snow_r"])
        w.writeheader()
        start = 0
        for i, chunk in enumerate(per_band):
            centre = (start + chunk.shape[0] / 2.0) / h
            start += chunk.shape[0]
            w.writerow({
                "band": i,
                "row_frac": round(float(centre), 5),
                "no_snow_r": int(round(float(chunk.mean()))),
            })
    print(f"wrote {LATITUDE_CSV} ({bands} bands)")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
