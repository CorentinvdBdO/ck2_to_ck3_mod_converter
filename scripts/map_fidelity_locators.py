"""CK3 map-object inventory + coordinate-frame check (lane map-fidelity).

Counts every locator/object entry under gfx/map/map_object_data and verifies
the coordinate frame of `building_locators.txt` against province centroids
measured on map_data/provinces.png.

Writes docs/evidence/map_fidelity/{ck3_map_objects.csv,locator_frame.csv}.
Run: uv run python scripts/map_fidelity_locators.py
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None

CK3 = Path("/home/cvdbdo/.local/share/Steam/steamapps/common/Crusader Kings III/game")
MOD = CK3 / "gfx/map/map_object_data"
OUT = Path("docs/evidence/map_fidelity")

NAME_RE = re.compile(rb'name="([^"]+)"')
KIND_RE = re.compile(rb'(game_object_locator|object)=\{')
INST_RE = re.compile(rb'\bid=(\d+)\s*\n\s*position=\{\s*([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s*\}')
COUNT_RE = re.compile(rb'count=(\d+)')


def inventory() -> list[dict]:
    rows = []
    for p in sorted(MOD.rglob("*.txt")):
        b = p.read_bytes()
        rows.append({
            "file": str(p.relative_to(CK3)),
            "bytes": p.stat().st_size,
            "blocks": len(KIND_RE.findall(b)),
            "named_objects": len(set(NAME_RE.findall(b))),
            "id_instances": len(INST_RE.findall(b)),
            "generated_count_sum": sum(int(x) for x in COUNT_RE.findall(b)),
        })
    return rows


def frame_check(n: int = 400) -> list[dict]:
    b = (MOD / "building_locators.txt").read_bytes()
    loc = {int(m.group(1)): (float(m.group(2)), float(m.group(3)), float(m.group(4)))
           for m in INST_RE.finditer(b)}
    rgb2id = {}
    with (CK3 / "map_data/definition.csv").open(encoding="latin-1") as f:
        for line in f:
            q = line.strip().split(";")
            if len(q) < 5 or not q[0].isdigit():
                continue
            rgb2id[(int(q[1]) << 16) | (int(q[2]) << 8) | int(q[3])] = int(q[0])
    with Image.open(CK3 / "map_data/provinces.png") as im:
        prov = np.asarray(im.convert("RGB"))
    H, W = prov.shape[:2]
    key = (prov[:, :, 0].astype(np.uint32) << 16) | (prov[:, :, 1].astype(np.uint32) << 8) | prov[:, :, 2]
    del prov
    uniq, inv = np.unique(key, return_inverse=True)
    ids = np.array([rgb2id.get(int(u), 0) for u in uniq])
    idmap = ids[inv].reshape(H, W)
    del key, inv

    rows = []
    want = sorted(loc)[:n]
    for pid in want:
        ys, xs = np.nonzero(idmap == pid)
        if ys.size == 0:
            continue
        cx, cy_top = float(xs.mean()), float(ys.mean())
        lx, ly, lz = loc[pid]
        rows.append({
            "province": pid, "centroid_x": round(cx, 1), "centroid_y_top": round(cy_top, 1),
            "loc_x": lx, "loc_y": ly, "loc_z": lz,
            "dx": round(lx - cx, 1),
            "dz_if_bottom_origin": round((H - lz) - cy_top, 1),
            "dz_if_top_origin": round(lz - cy_top, 1),
        })
    return rows


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    inv = inventory()
    with (OUT / "ck3_map_objects.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(inv[0].keys()))
        w.writeheader()
        w.writerows(inv)
    for r in sorted(inv, key=lambda r: -r["id_instances"])[:18]:
        print(f"{r['file']:<58} blocks={r['blocks']:<4} ids={r['id_instances']:<7} gen={r['generated_count_sum']}")

    rows = frame_check()
    with (OUT / "locator_frame.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    dx = np.array([r["dx"] for r in rows])
    bot = np.abs([r["dz_if_bottom_origin"] for r in rows])
    top = np.abs([r["dz_if_top_origin"] for r in rows])
    print(f"\nlocator frame over {len(rows)} provinces:")
    print(f"  |dx| median            {np.median(np.abs(dx)):.1f} px")
    print(f"  |dz| median bottom-org {np.median(bot):.1f} px")
    print(f"  |dz| median top-origin {np.median(top):.1f} px")


if __name__ == "__main__":
    main()
