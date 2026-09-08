"""Inventory of CK2 vs CK3 map raster + script assets (lane map-fidelity).

Writes docs/evidence/map_fidelity/inventory.csv and prints a summary.
Read-only on the game installs.
"""
from __future__ import annotations
import csv, os, struct, sys
from pathlib import Path

from PIL import Image
Image.MAX_IMAGE_PIXELS = None

CK2 = Path("/home/cvdbdo/.local/share/Steam/steamapps/common/Crusader Kings II/map")
FAE = Path("Faerun/Faerun/map")
CK3 = Path("/home/cvdbdo/.local/share/Steam/steamapps/common/Crusader Kings III/game")
OUT = Path("docs/evidence/map_fidelity")


def dds_header(p: Path) -> tuple[int, int, str]:
    with p.open("rb") as f:
        h = f.read(148)
    if h[:4] != b"DDS ":
        return (0, 0, "not-dds")
    height, width = struct.unpack_from("<II", h, 12)
    fourcc = h[84:88].decode("latin-1").strip("\x00")
    if fourcc == "DX10":
        dxgi = struct.unpack_from("<I", h, 128)[0]
        fourcc = f"DX10:{dxgi}"
    return (width, height, fourcc)


def tga_header(p: Path) -> tuple[int, int, str]:
    with p.open("rb") as f:
        h = f.read(18)
    w, hgt = struct.unpack_from("<HH", h, 12)
    depth = h[16]
    imtype = h[2]
    return (w, hgt, f"tga type{imtype} {depth}bpp")


def probe(p: Path) -> dict:
    row = {"path": str(p), "bytes": p.stat().st_size}
    try:
        if p.suffix.lower() == ".dds":
            w, h, mode = dds_header(p)
        elif p.suffix.lower() == ".tga":
            w, h, mode = tga_header(p)
        else:
            with Image.open(p) as im:
                w, h, mode = im.width, im.height, im.mode
                if im.mode == "P":
                    mode = f"P({len(im.getpalette() or [])//3} colours)"
        row.update(width=w, height=h, mode=mode)
    except Exception as exc:  # pragma: no cover
        row.update(width=0, height=0, mode=f"ERR {exc}")
    return row


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    targets = [
        ("ck2_vanilla", CK2, ["provinces.bmp", "topology.bmp", "terrain.bmp", "trees.bmp",
                              "rivers.bmp", "world_normal_height.bmp"]),
        ("ck2_faerun", FAE, ["provinces.bmp", "topology.bmp", "terrain.bmp", "trees.bmp",
                             "rivers.bmp", "world_normal_height.bmp"]),
        ("ck3_vanilla", CK3 / "map_data", ["provinces.png", "heightmap.png", "rivers.png",
                                           "packed_heightmap.png", "indirection_heightmap.png"]),
        ("ck3_vanilla", CK3 / "gfx/map/terrain", ["detail_index.tga", "detail_intensity.tga",
                                                  "colormap.dds", "colormap_water.dds"]),
    ]
    for tag, base, names in targets:
        for n in names:
            p = base / n
            if p.exists():
                r = probe(p)
                r["set"] = tag
                r["name"] = n
                rows.append(r)
    masks = sorted((CK3 / "gfx/map/terrain/masks").glob("*_mask.png"))
    for p in masks:
        r = probe(p)
        r["set"] = "ck3_mask"
        r["name"] = p.name
        rows.append(r)
    with (OUT / "inventory.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["set", "name", "width", "height", "mode", "bytes", "path"])
        w.writeheader()
        for r in rows:
            w.writerow(r)
    for r in rows:
        print(f"{r['set']:<12} {r['name']:<34} {r['width']:>6}x{r['height']:<6} {r['mode']:<22} {r['bytes']:>12}")
    print(f"\nmask count: {len(masks)}")


if __name__ == "__main__":
    main()
