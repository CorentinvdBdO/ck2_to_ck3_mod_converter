#!/usr/bin/env python3
"""Measure vanilla CK3's own regional tree-species mix.

For every instance in vanilla's 18 ``gfx/map/map_object_data/generated/*.txt``
files, look up the province it stands on (``map_data/provinces.png`` +
``map_data/definition.csv``), that province's terrain key
(``common/province_terrain``) and winter climate zone
(``map_data/climate.txt``), and the instance's own latitude band (canvas row
decile, north = band 0).  The result is
``P(generator file | terrain, climate, latitude band)`` with counts — the
table ``ck2ck3.map.tree_scatter`` samples our own mesh choice from
(``mappings/tree_mix.csv``, written by ``scripts/build_tree_mix_csv.py``).

Why these three conditioning variables: they are the three signals the
converter *also* has on the Faerûn side.  Terrain is the per-province
majority vote the paint step already computes, the winter climate zone is
ported straight from the CK2 mod's own ``map/climate.txt``, and the latitude
band is a fractional canvas row on both maps (`assumed`: fractional
north-south position transfers between a real-world map and a fantasy one —
vanilla's own band 0 is Iceland/Scandinavia and band 9 central Africa, ours
is the Spine of the World down to Chult).

Outputs:

* ``docs/evidence/vanilla_tree_mix.csv`` — one row per
  (terrain, climate, band, file) with ``count`` and ``p``.
* ``docs/evidence/vanilla_tree_bands.csv`` — the marginal band x file table
  (what the report figure plots for the vanilla side).
* ``docs/evidence/vanilla_tree_patch_scale.csv`` — how species-pure vanilla's
  own stands are at cell sizes 8..256 px, the measurement that sets our
  sampling cell size (`[map] trees_cell_px`).

Usage::

    uv run scripts/measure_vanilla_tree_mix.py [ck3_game_dir]
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parent.parent
DEFAULT_GAME = Path(
    "/home/cvdbdo/.local/share/Steam/steamapps/common/Crusader Kings III/game"
)
GENERATED_DIR = "gfx/map/map_object_data/generated"
#: north-to-south canvas row bands.  10 = deciles.
N_BANDS = 10
#: cell sizes the patch-scale measurement reports
PATCH_CELLS = (8, 16, 24, 32, 48, 64, 96, 128, 192, 256)
#: a cell needs this many instances before its purity means anything
PATCH_MIN_INSTANCES = 8

_TRANSFORM_RE = re.compile(r'transform="([^"]*)"', re.S)
_TERRAIN_RE = re.compile(r"^\s*(\d+)\s*=\s*([a-z_]+)\s*$")


def province_raster(game_dir: Path) -> tuple[np.ndarray, int, int]:
    """``provinces.png`` decoded to a per-pixel CK3 province id array."""
    defs: dict[int, int] = {}
    with (game_dir / "map_data/definition.csv").open(
        "r", encoding="utf-8-sig", errors="replace"
    ) as fh:
        for line in fh:
            parts = line.strip().split(";")
            if len(parts) < 4 or not parts[0].isdigit():
                continue
            try:
                pid, r, g, b = (int(parts[0]), int(parts[1]), int(parts[2]),
                                int(parts[3]))
            except ValueError:
                continue
            defs[(r << 16) | (g << 8) | b] = pid
    with Image.open(game_dir / "map_data/provinces.png") as im:
        rgb = np.asarray(im.convert("RGB"))
    h, w = rgb.shape[:2]
    key = (
        rgb[:, :, 0].astype(np.int64) << 16
        | rgb[:, :, 1].astype(np.int64) << 8
        | rgb[:, :, 2].astype(np.int64)
    )
    keys = np.array(sorted(defs), dtype=np.int64)
    vals = np.array([defs[int(k)] for k in keys], dtype=np.int32)
    pos = np.searchsorted(keys, key)
    pos = np.clip(pos, 0, len(keys) - 1)
    out = np.where(keys[pos] == key, vals[pos], 0).astype(np.int32)
    return out, h, w


def terrain_of_province(game_dir: Path) -> tuple[dict[int, str], str]:
    """``common/province_terrain/00_province_terrain.txt`` -> id -> key."""
    path = game_dir / "common/province_terrain/00_province_terrain.txt"
    out: dict[int, str] = {}
    default = "plains"
    for line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        if line.strip().startswith("default_land"):
            default = line.split("=", 1)[1].strip()
            continue
        m = _TERRAIN_RE.match(line)
        if m:
            out[int(m.group(1))] = m.group(2)
    return out, default


def climate_of_province(game_dir: Path) -> dict[int, str]:
    """``map_data/climate.txt`` -> id -> ``mild``/``normal``/``severe``.

    A province in no block has no winter zone at all in CK3; we call that
    ``none`` rather than inventing one (vanilla leaves most of Africa and
    Arabia out).
    """
    text = (game_dir / "map_data/climate.txt").read_text(
        encoding="utf-8-sig", errors="replace"
    )
    out: dict[int, str] = {}
    for m in re.finditer(r"([a-z_]+)\s*=\s*\{(.*?)\}", text, re.S):
        zone = m.group(1).replace("_winter", "")
        body = re.sub(r"#[^\n]*", " ", m.group(2))
        for tok in body.split():
            if tok.isdigit():
                out.setdefault(int(tok), zone)
    return out


def instances_of_file(path: Path) -> np.ndarray:
    """Every instance of one generated file as an ``(n, 2)`` (x, z) array."""
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    chunks = []
    for m in _TRANSFORM_RE.finditer(text):
        arr = np.fromstring(m.group(1), sep=" ")
        if arr.size % 10:
            arr = arr[: arr.size - arr.size % 10]
        if arr.size:
            chunks.append(arr.reshape(-1, 10)[:, [0, 2]])
    if not chunks:
        return np.zeros((0, 2), dtype=np.float64)
    return np.concatenate(chunks, axis=0)


def band_of_y(y: np.ndarray, height: int, n_bands: int = N_BANDS) -> np.ndarray:
    """Canvas row -> north-to-south band index (0 = northernmost)."""
    return np.clip((y * n_bands / float(height)).astype(np.int32), 0, n_bands - 1)


def patch_purity(
    xy: dict[str, np.ndarray], height: int, cells: tuple[int, ...] = PATCH_CELLS
) -> list[dict[str, object]]:
    """How single-species vanilla's stands are, per square cell size.

    For each cell size, bucket every instance of every file into a cell and
    report the instance-weighted mean share of the cell's dominant file, over
    cells holding at least ``PATCH_MIN_INSTANCES`` instances.  1.0 means
    "a cell of this size is one species"; 1/18 would be a uniform mixture.
    """
    rows = []
    files = sorted(xy)
    for cell in cells:
        counts: dict[tuple[int, int], Counter] = defaultdict(Counter)
        for fi, f in enumerate(files):
            pts = xy[f]
            if not pts.size:
                continue
            cx = (pts[:, 0] / cell).astype(np.int64)
            cy = ((height - pts[:, 1]) / cell).astype(np.int64)
            for k, n in Counter(zip(cx.tolist(), cy.tolist())).items():
                counts[k][fi] += n
        tot_inst = 0
        tot_dom = 0
        n_cells = 0
        for c in counts.values():
            n = sum(c.values())
            if n < PATCH_MIN_INSTANCES:
                continue
            tot_inst += n
            tot_dom += max(c.values())
            n_cells += 1
        rows.append(
            {
                "cell_px": cell,
                "cells": n_cells,
                "instances": tot_inst,
                "mean_dominant_share": round(tot_dom / tot_inst, 4) if tot_inst else "",
            }
        )
    return rows


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("game_dir", nargs="?", type=Path, default=DEFAULT_GAME)
    ap.add_argument("--out-dir", type=Path, default=REPO / "docs/evidence")
    ap.add_argument("--bands", type=int, default=N_BANDS)
    args = ap.parse_args(argv[1:])

    src_dir = args.game_dir / GENERATED_DIR
    if not src_dir.is_dir():
        print(f"no such directory: {src_dir}", file=sys.stderr)
        return 1

    print("reading provinces.png + definition.csv ...", flush=True)
    raster, height, width = province_raster(args.game_dir)
    print(f"  {width}x{height}, {int(raster.max())} max province id", flush=True)
    terrain, default_land = terrain_of_province(args.game_dir)
    climate = climate_of_province(args.game_dir)
    print(
        f"  {len(terrain)} province_terrain rows (default {default_land}), "
        f"{len(climate)} climate rows",
        flush=True,
    )

    max_id = int(raster.max())
    terrain_lut = np.array(
        [terrain.get(i, default_land) for i in range(max_id + 1)], dtype=object
    )
    climate_lut = np.array(
        [climate.get(i, "none") for i in range(max_id + 1)], dtype=object
    )

    table: Counter = Counter()
    band_totals: Counter = Counter()
    per_file_total: Counter = Counter()
    xy: dict[str, np.ndarray] = {}
    for path in sorted(src_dir.glob("*.txt")):
        pts = instances_of_file(path)
        xy[path.name] = pts
        if not pts.size:
            print(f"  {path.name}: 0 instances", flush=True)
            continue
        x = np.clip(pts[:, 0].astype(np.int64), 0, width - 1)
        y = np.clip((height - pts[:, 1]).astype(np.int64), 0, height - 1)
        pid = raster[y, x]
        band = band_of_y(y, height, args.bands)
        tkeys = terrain_lut[np.clip(pid, 0, max_id)]
        ckeys = climate_lut[np.clip(pid, 0, max_id)]
        for t, c, b in zip(tkeys.tolist(), ckeys.tolist(), band.tolist()):
            table[(t, c, b, path.name)] += 1
            band_totals[(b, path.name)] += 1
        per_file_total[path.name] += int(pts.shape[0])
        print(f"  {path.name}: {pts.shape[0]} instances", flush=True)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    cond_totals: Counter = Counter()
    for (t, c, b, f), n in table.items():
        cond_totals[(t, c, b)] += n
    mix_path = args.out_dir / "vanilla_tree_mix.csv"
    with mix_path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["ck3_terrain", "climate", "lat_band", "file", "count", "p"])
        for (t, c, b, f), n in sorted(table.items()):
            w.writerow([t, c, b, f, n, round(n / cond_totals[(t, c, b)], 6)])
    print(f"wrote {mix_path} ({len(table)} rows)")

    bands_path = args.out_dir / "vanilla_tree_bands.csv"
    band_sum: Counter = Counter()
    for (b, f), n in band_totals.items():
        band_sum[b] += n
    with bands_path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["lat_band", "file", "count", "share_of_band"])
        for (b, f), n in sorted(band_totals.items()):
            w.writerow([b, f, n, round(n / band_sum[b], 6)])
    print(f"wrote {bands_path} ({len(band_totals)} rows)")

    patch_path = args.out_dir / "vanilla_tree_patch_scale.csv"
    rows = patch_purity(xy, height)
    with patch_path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(
            fh, fieldnames=["cell_px", "cells", "instances", "mean_dominant_share"]
        )
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {patch_path}")
    for r in rows:
        print(f"  cell {r['cell_px']:>4} px: purity {r['mean_dominant_share']}")

    print(f"total instances: {sum(per_file_total.values()):,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
