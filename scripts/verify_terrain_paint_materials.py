#!/usr/bin/env python3
"""What material vanilla itself paints per CK3 terrain type.

Goal C of lane `map-colour`: `mappings/terrain_paint.csv` flags two judgement
calls (`taiga` secondary = `snow`, `terraced_hills` primary =
`hills_01_rocks_medi`) and this script settles them, and checks every other
row for the same class of mistake, by reading vanilla's own bake directly:

1. `common/province_terrain/*.txt` -> province id -> CK3 terrain key.
2. `map_data/provinces.png` + `definition.csv` -> province id -> pixel mask.
3. `gfx/map/terrain/detail_index.tga` (channel 0, the primary material
   ordinal) + `materials.settings` (ordinal -> material id).
4. For every terrain key, the material histogram of its own provinces'
   pixels in vanilla's real map — i.e. what vanilla itself paints there.

Usage::

    uv run scripts/verify_terrain_paint_materials.py [ck3_game_dir]
"""

from __future__ import annotations

import csv
import re
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from ck2ck3.map import terrain_paint  # noqa: E402

DEFAULT_GAME = Path(
    "/home/cvdbdo/.local/share/Steam/steamapps/common/Crusader Kings III/game"
)

_TERRAIN_ROW_RE = re.compile(r"^\s*(\d+)\s*=\s*(\w+)", re.M)


def read_province_terrain(game_dir: Path) -> dict[int, str]:
    """``common/province_terrain/*.txt``: ``<province id>=<terrain key>`` rows.

    Vanilla's own format is flat, not nested (`verified`,
    ``00_province_terrain.txt``): ``default_land=plains`` then one
    ``<id>=<key>`` per province. The ``default_*`` rows do not match
    ``\\d+=``, so they are skipped automatically.
    """
    out: dict[int, str] = {}
    d = game_dir / "common" / "province_terrain"
    for p in sorted(d.glob("*.txt")):
        text = p.read_text(encoding="utf-8-sig", errors="replace")
        for m in _TERRAIN_ROW_RE.finditer(text):
            out[int(m.group(1))] = m.group(2)
    return out


def read_definition(path: Path) -> dict[tuple[int, int, int], int]:
    out = {}
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        r = csv.reader(fh, delimiter=";")
        next(r, None)
        for row in r:
            if len(row) < 4:
                continue
            try:
                pid, red, green, blue = (int(row[0]), int(row[1]), int(row[2]), int(row[3]))
            except ValueError:
                continue
            out[(red, green, blue)] = pid
    return out


def main(argv: list[str]) -> int:
    game_dir = Path(argv[1]) if len(argv) > 1 else DEFAULT_GAME

    print("reading province_terrain...")
    prov_terrain = read_province_terrain(game_dir)

    print("reading provinces.png + definition.csv...")
    rgb_to_id = read_definition(game_dir / "map_data" / "definition.csv")
    with Image.open(game_dir / "map_data" / "provinces.png") as im:
        prov_rgb = np.asarray(im.convert("RGB"))
    h, w = prov_rgb.shape[:2]
    key = (
        prov_rgb[..., 0].astype(np.int64) << 16
        | prov_rgb[..., 1].astype(np.int64) << 8
        | prov_rgb[..., 2].astype(np.int64)
    )
    rgb_key_to_id = {
        (r << 16 | g << 8 | b): pid for (r, g, b), pid in rgb_to_id.items()
    }
    max_key = int(key.max())
    lut = np.full(max_key + 1, -1, dtype=np.int32)
    for k, pid in rgb_key_to_id.items():
        if k <= max_key:
            lut[k] = pid
    province_ids = lut[key]

    print("reading detail_index.tga (primary channel)...")
    with Image.open(game_dir / "gfx" / "map" / "terrain" / "detail_index.tga") as im:
        idx = np.asarray(im.convert("RGBA"))
    primary = idx[..., 0]

    ordinals = terrain_paint.material_ordinals(
        game_dir / "gfx" / "map" / "terrain" / "materials.settings"
    )
    name_of_ordinal = {v: k for k, v in ordinals.items()}

    # terrain key per pixel, via province id
    max_pid = max(prov_terrain) if prov_terrain else 0
    tlut = np.full(max_pid + 1, "", dtype=object)
    for pid, tkey in prov_terrain.items():
        tlut[pid] = tkey
    valid = (province_ids >= 0) & (province_ids <= max_pid)
    terrain_per_px = np.full(province_ids.shape, "", dtype=object)
    terrain_per_px[valid] = tlut[province_ids[valid]]

    # The "gen_*"/"central_*" families are per-climate-zone variants of a base
    # look (gen_tropical_hills, gen_steppe_hills, ... - 100+ ids, all with
    # generic-sounding names but geography-specific masks). Faerun has no
    # equivalent climate-zone bake, and counting them dilutes the vote into
    # dozens of <20%-share buckets that say nothing about the terrain *type* -
    # they say which of Earth's climate zones that terrain happened to sit in
    # on vanilla's own map. Excluded so the histogram answers "what does
    # vanilla paint for this terrain key, independent of where on Earth it
    # is", which is the only question relevant to a different planet's map.
    _REGIONAL_PREFIXES = ("gen_", "central_")

    def _is_regional(ordinal: int) -> bool:
        name = name_of_ordinal.get(ordinal, "")
        return name.startswith(_REGIONAL_PREFIXES)

    print()
    print(f"{'terrain':<20} {'top material':<26} {'share':>7}   runner-up (share)")
    print("(regional gen_*/central_* climate-zone materials excluded - see comment)")
    by_terrain: dict[str, Counter] = {}
    for tkey in sorted(set(prov_terrain.values())):
        mask = terrain_per_px == tkey
        n_total = int(mask.sum())
        if n_total == 0:
            print(f"{tkey:<20} {'(no pixels in vanilla)':<26}")
            continue
        vals, counts = np.unique(primary[mask], return_counts=True)
        counter = Counter(
            {v: c for v, c in zip(vals.tolist(), counts.tolist()) if not _is_regional(v)}
        )
        n = sum(counter.values())
        by_terrain[tkey] = counter
        if n == 0:
            print(f"{tkey:<20} {'(only regional materials painted)':<26}")
            continue
        top = counter.most_common(3)
        top_name, top_n = top[0]
        line = (
            f"{tkey:<20} {name_of_ordinal.get(top_name, f'ord{top_name}'):<26} "
            f"{100*top_n/n:6.1f}% of {100*n/n_total:.0f}% non-regional   "
        )
        line += ", ".join(
            f"{name_of_ordinal.get(o, f'ord{o}')} ({100*c/n:.1f}%)" for o, c in top[1:]
        )
        print(line)

    # cross-check against our own table
    print()
    print("=== mappings/terrain_paint.csv vs. vanilla's own top material ===")
    ours = terrain_paint.read_material_map(REPO / "mappings" / "terrain_paint.csv")
    for tkey, (prim, sec) in sorted(ours.items()):
        counter = by_terrain.get(tkey)
        if not counter:
            print(f"{tkey:<20} ours: {prim}/{sec:<20}  vanilla: n/a (not painted, or no CK3 vanilla province of this terrain)")
            continue
        vanilla_top = name_of_ordinal.get(counter.most_common(1)[0][0], "?")
        match = "OK" if prim == vanilla_top else "DIFFERS"
        print(f"{tkey:<20} ours: {prim}/{sec:<20}  vanilla top: {vanilla_top:<24} [{match}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
