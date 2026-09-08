"""Painted-layer comparison: CK2 terrain/trees/rivers vs CK3 (lane map-fidelity).

Writes docs/evidence/map_fidelity/{terrain_classes.csv,trees.csv,rivers_palette.csv}
and prints a summary. Read-only on both game installs.
Run: uv run python scripts/map_fidelity_paint.py
"""
from __future__ import annotations

import csv
import re
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None

CK2V = Path("/home/cvdbdo/.local/share/Steam/steamapps/common/Crusader Kings II/map")
FAE = Path("Faerun/Faerun/map")
CK3 = Path("/home/cvdbdo/.local/share/Steam/steamapps/common/Crusader Kings III/game")
OUT = Path("docs/evidence/map_fidelity")

TEXT_RE = re.compile(r"text_(\d+)\s*=\s*\{\s*type\s*=\s*(\w+)")


def ck2_texture_types(path: Path) -> dict[int, str]:
    txt = path.read_text(encoding="latin-1")
    return {int(m.group(1)): m.group(2) for m in TEXT_RE.finditer(txt)}


def terrain_rows(tag: str, mapdir: Path) -> list[dict]:
    types = ck2_texture_types(mapdir / "terrain.txt")
    with Image.open(mapdir / "terrain.bmp") as im:
        idx = np.asarray(im)
        pal = im.getpalette() or []
    with Image.open(mapdir / "topology.bmp") as im:
        topo = np.asarray(im)
    land = topo > 95
    total = idx.size
    rows = []
    counts = np.bincount(idx.ravel(), minlength=256)
    land_counts = np.bincount(idx[land].ravel(), minlength=256)
    for i in np.nonzero(counts)[0]:
        rgb = tuple(pal[3 * i:3 * i + 3]) if len(pal) >= 3 * i + 3 else ()
        rows.append({
            "set": tag, "index": int(i), "ck2_type": types.get(int(i), "?"),
            "palette_rgb": "/".join(str(c) for c in rgb),
            "px": int(counts[i]), "pct": round(100.0 * counts[i] / total, 3),
            "land_px": int(land_counts[i]),
            "land_pct": round(100.0 * land_counts[i] / max(int(land.sum()), 1), 3),
        })
    return rows


def trees_rows(tag: str, mapdir: Path) -> list[dict]:
    with Image.open(mapdir / "trees.bmp") as im:
        a = np.asarray(im)
        pal = im.getpalette() or []
        size = im.size
    with Image.open(mapdir / "provinces.bmp") as im:
        pw, ph = im.size
    counts = np.bincount(a.ravel(), minlength=256)
    rows = []
    for i in np.nonzero(counts)[0]:
        rgb = tuple(pal[3 * i:3 * i + 3]) if len(pal) >= 3 * i + 3 else ()
        rows.append({
            "set": tag, "index": int(i), "palette_rgb": "/".join(str(c) for c in rgb),
            "px": int(counts[i]), "pct": round(100.0 * counts[i] / a.size, 3),
            "trees_size": f"{size[0]}x{size[1]}",
            "province_size": f"{pw}x{ph}",
            "downscale": round(pw / size[0], 3),
        })
    return rows


def river_rows(tag: str, path: Path) -> list[dict]:
    with Image.open(path) as im:
        a = np.asarray(im)
        pal = im.getpalette() or []
    counts = np.bincount(a.ravel(), minlength=256)
    rows = []
    for i in np.nonzero(counts)[0]:
        rgb = tuple(pal[3 * i:3 * i + 3]) if len(pal) >= 3 * i + 3 else ()
        rows.append({"set": tag, "index": int(i),
                     "palette_rgb": "/".join(str(c) for c in rgb),
                     "px": int(counts[i]),
                     "pct": round(100.0 * counts[i] / a.size, 4)})
    return rows


def write(name: str, rows: list[dict]) -> None:
    if not rows:
        return
    with (OUT / name).open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"--- {name}")
    for r in rows:
        print("   " + "  ".join(f"{k}={v}" for k, v in r.items()))


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    write("terrain_classes.csv",
          terrain_rows("ck2_vanilla", CK2V) + terrain_rows("ck2_faerun", FAE))
    write("trees.csv", trees_rows("ck2_vanilla", CK2V) + trees_rows("ck2_faerun", FAE))
    write("rivers_palette.csv",
          river_rows("ck2_vanilla", CK2V / "rivers.bmp")
          + river_rows("ck2_faerun", FAE / "rivers.bmp")
          + river_rows("ck3_vanilla", CK3 / "map_data/rivers.png"))


if __name__ == "__main__":
    main()
