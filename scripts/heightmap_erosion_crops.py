#!/usr/bin/env python3
"""Locate the two named study regions of lane `erosion` on the canvas.

Thay (`k_thay`, the terraced plateau the CK2 author drew with real cliffs) and
the Spine of the World (`k_spine_of_the_world`, a mountain range) are named in
the goal because they are the two places where a *real* multi-step cliff and a
quantisation riser have to be told apart.  This script turns those two CK2
kingdom titles into canvas pixel boxes, so every later measurement and every
hillshade uses the same ground.

Method: read the barony ids under each kingdom out of the CK2
`landed_titles` (Latin-1, so `command grep -a` / cp1252 decode), map them to
CK3 province ids through the generated mod's `map_data/definition.csv`
(column 5 IS the barony title id -- CLAUDE.md), and take the bounding box of
those provinces' colours in `map_data/provinces.png`.

Usage:  uv run scripts/heightmap_erosion_crops.py [mod_dir] [--json OUT]
Writes: docs/evidence/heightmap_erosion/crops.json
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None

ROOT = Path(__file__).resolve().parents[1]
LANDED = ROOT / "Faerun/Faerun/common/landed_titles/01_landed_titles.txt"
OUT_JSON = ROOT / "docs/evidence/heightmap_erosion/crops.json"

#: kingdom title -> short name used in every evidence filename
REGIONS = {
    "k_thay": "thay",
    "k_spine_of_the_world": "spine",
}


def baronies_under(text: str, title: str) -> list[str]:
    """Every `b_*` id inside the brace block of `title`."""
    m = re.search(rf"^\s*{re.escape(title)}\s*=\s*\{{", text, re.M)
    if not m:
        raise SystemExit(f"{title} not found in {LANDED}")
    depth, i = 0, m.end() - 1
    start = i
    while i < len(text):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                break
        i += 1
    block = text[start : i + 1]
    return re.findall(r"^\s*(b_\w+)\s*=\s*\{", block, re.M)


def definition_rgb(path: Path) -> dict[str, tuple[int, int, int]]:
    out: dict[str, tuple[int, int, int]] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        parts = line.split(";")
        if len(parts) < 5 or not parts[0].isdigit():
            continue
        out[parts[4]] = (int(parts[1]), int(parts[2]), int(parts[3]))
    return out


def bbox_of(prov: np.ndarray, rgbs: list[tuple[int, int, int]]) -> tuple[int, int, int, int]:
    """(y0, x0, y1, x1) bounding box of the union of those province colours."""
    key = (prov[:, :, 0].astype(np.uint32) << 16) | (
        prov[:, :, 1].astype(np.uint32) << 8
    ) | prov[:, :, 2].astype(np.uint32)
    want = np.array([(r << 16) | (g << 8) | b for r, g, b in rgbs], dtype=np.uint32)
    mask = np.isin(key, want)
    ys, xs = np.nonzero(mask)
    if ys.size == 0:
        raise SystemExit("no pixels for those provinces")
    return int(ys.min()), int(xs.min()), int(ys.max()) + 1, int(xs.max()) + 1


def square_crop(box, side: int, shape) -> tuple[int, int, int]:
    """A `side`x`side` window centred on `box`, clipped into the canvas."""
    y0, x0, y1, x1 = box
    cy, cx = (y0 + y1) // 2, (x0 + x1) // 2
    H, W = shape
    y = max(0, min(H - side, cy - side // 2))
    x = max(0, min(W - side, cx - side // 2))
    return int(y), int(x), int(side)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("mod", nargs="?", default=str(ROOT / "../_out/seafloor"))
    ap.add_argument("--side", type=int, default=512)
    ap.add_argument("--json", default=str(OUT_JSON))
    args = ap.parse_args()

    mod = Path(args.mod)
    text = LANDED.read_text(encoding="cp1252", errors="replace")
    rgb_of = definition_rgb(mod / "map_data/definition.csv")
    with Image.open(mod / "map_data/provinces.png") as im:
        prov = np.asarray(im.convert("RGB"))

    out = {}
    for title, short in REGIONS.items():
        bar = baronies_under(text, title)
        rgbs = [rgb_of[b] for b in bar if b in rgb_of]
        box = bbox_of(prov, rgbs)
        y, x, side = square_crop(box, args.side, prov.shape[:2])
        out[short] = {
            "title": title,
            "baronies_in_ck2": len(bar),
            "provinces_on_map": len(rgbs),
            "bbox_yxyx": list(box),
            "crop_y": y, "crop_x": x, "crop_side": side,
        }
        print(f"{short:6s} {title:24s} {len(rgbs):4d} provinces  "
              f"bbox={box}  crop=({y},{x},{side})")

    Path(args.json).parent.mkdir(parents=True, exist_ok=True)
    Path(args.json).write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
