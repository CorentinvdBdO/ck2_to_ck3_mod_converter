#!/usr/bin/env python3
"""Land/water mean + stddev of a generated ``colormap.dds``, vs. vanilla.

Lane `colormap-fix` VERIFY step: independent of `ck2ck3.map.build`'s own
in-run report (which prints land/water mean but not stddev), this reads the
*output* files a real run wrote and recomputes both from scratch, the same
way `scripts/measure_vanilla_colormap_tints.py` measures vanilla's own file.

Usage::

    uv run scripts/verify_colormap_land_water.py <out_dir> [vanilla_csv]
"""

from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None

REPO = Path(__file__).resolve().parents[1]
DEFAULT_VANILLA_CSV = REPO / "docs" / "evidence" / "vanilla_colormap_tints.csv"

_RANGE_RE = re.compile(r"(?:sea_zones|lakes)\s*=\s*RANGE\s*\{\s*(\d+)\s+(\d+)\s*\}")
_LIST_RE = re.compile(r"(?:sea_zones|lakes)\s*=\s*LIST\s*\{([^}]*)\}")


def read_water_ids(default_map: Path) -> set[int]:
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
    if len(argv) < 2:
        print(__doc__)
        return 1
    out_dir = Path(argv[1])
    vanilla_csv = Path(argv[2]) if len(argv) > 2 else DEFAULT_VANILLA_CSV

    with Image.open(out_dir / "gfx" / "map" / "terrain" / "colormap.dds") as im:
        cm = np.asarray(im.convert("RGB")).astype(np.float64)
        cm_bytes = (out_dir / "gfx" / "map" / "terrain" / "colormap.dds").stat().st_size

    with Image.open(out_dir / "map_data" / "provinces.png") as im:
        provinces_png = np.asarray(im.convert("RGB"))
    definition = read_definition(out_dir / "map_data" / "definition.csv")
    province_ids = province_id_raster(provinces_png, definition)
    water_ids = read_water_ids(out_dir / "map_data" / "default.map")
    water_mask_full = np.isin(province_ids, list(water_ids))

    # colormap.dds is downsampled (colormap_scale); nearest-neighbour resize
    # the water mask down to the same shape rather than resizing the colour
    # data (which is already final).
    ch, cw = cm.shape[:2]
    fh, fw = water_mask_full.shape
    yi = np.minimum((np.arange(ch) * fh // ch), fh - 1)
    xi = np.minimum((np.arange(cw) * fw // cw), fw - 1)
    water_mask = water_mask_full[yi][:, xi]

    land = cm[~water_mask]
    water = cm[water_mask]

    def stats(px):
        return px.mean(axis=0), px.std(axis=0)

    land_mean, land_std = stats(land)
    water_mean, water_std = stats(water)

    def sat(mean):
        return float(max(mean) - min(mean))

    print(f"colormap.dds: {cw}x{ch}, {cm_bytes / 1e6:.2f} MB")
    print(f"land  n={len(land):>10}  mean={tuple(round(float(x),1) for x in land_mean)}  "
          f"std={tuple(round(float(x),1) for x in land_std)}  saturation={sat(land_mean):.2f}")
    print(f"water n={len(water):>10}  mean={tuple(round(float(x),1) for x in water_mean)}  "
          f"std={tuple(round(float(x),1) for x in water_std)}  saturation={sat(water_mean):.2f}")

    if vanilla_csv.exists():
        with vanilla_csv.open(encoding="utf-8", newline="") as fh:
            rows = list(csv.DictReader(fh))
        vland = [r for r in rows if not r["material_name"].startswith("water")]
        n = sum(int(r["sample_count"]) for r in vland)
        vsat = sum(
            (max(float(r["mean_r"]), float(r["mean_g"]), float(r["mean_b"]))
             - min(float(r["mean_r"]), float(r["mean_g"]), float(r["mean_b"])))
            * int(r["sample_count"])
            for r in vland
        ) / n
        vwater = next(r for r in rows if r["material_name"].startswith("water"))
        vwsat = sat((float(vwater["mean_r"]), float(vwater["mean_g"]), float(vwater["mean_b"])))
        print(f"\nvanilla land weighted-mean saturation: {vsat:.2f} (ours: {sat(land_mean):.2f})")
        print(f"vanilla water saturation: {vwsat:.2f} (ours: {sat(water_mean):.2f})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
