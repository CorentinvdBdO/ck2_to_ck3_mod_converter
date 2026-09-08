"""Prototype: paint CK3 terrain from CK2 terrain.bmp + trees.bmp.

CK3 renders terrain from `gfx/map/terrain/detail_index.tga` (four material
ordinals per pixel, in `materials.settings` declaration order) and
`detail_intensity.tga` (their weights, summing to exactly 255).  This script
builds that pair from the CK2 painted layers for one region, renders a preview,
and measures what the whole canvas would cost on disk.

Nothing is wired into the converter.
Run: uv run python scripts/prototype_terrain_masks.py
"""
from __future__ import annotations

import csv
import io
import re
import tomllib
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter

from ck2ck3.map.config import ScaleConfig, plan_canvas

Image.MAX_IMAGE_PIXELS = None

CK3 = Path("/home/cvdbdo/.local/share/Steam/steamapps/common/Crusader Kings III/game")
TER = CK3 / "gfx/map/terrain"
OUT = Path("docs/evidence/map_fidelity")
TILE = (2080, 940, 2048, 2048)   # Sword Coast + hinterland, canvas px
QUANT = 16                       # blend-weight quantisation step (1 = none)

#: CK3 terrain key -> vanilla material id, and the second material blended in.
#: Vanilla ids come from gfx/map/terrain/materials.settings; picking existing
#: vanilla materials means no new .dds has to be authored.
MATERIALS: dict[str, tuple[str, str]] = {
    "plains": ("plains_01", "plains_01_noisy"),
    "farmlands": ("farmland_01", "plains_01"),
    "hills": ("hills_01", "hills_01_rocks"),
    "terraced_hills": ("hills_01_rocks_medi", "hills_01"),
    "mountains": ("mountain_02", "mountain_02_c"),
    "desert_mountains": ("mountain_02_desert_c", "desert_rocky"),
    "desert": ("desert_02", "desert_wavy_01"),
    "drylands": ("drylands_01", "drylands_01_grassy"),
    "oasis": ("oasis", "medi_grass_01"),
    "jungle": ("forest_jungle_01", "forestfloor"),
    "forest": ("forest_pine_01", "forestfloor"),
    "taiga": ("forest_pine_01", "snow"),
    "wetlands": ("wetlands_02", "wetlands_02_mud"),
    "steppe": ("steppe_grass", "steppe_bushes"),
    "floodplains": ("floodplains_01", "mud_wet_01"),
    "sea": ("beach_02", "beach_02_pebbles"),
    "coastal_sea": ("beach_02", "beach_02_pebbles"),
}


def material_ordinals() -> dict[str, int]:
    txt = (TER / "materials.settings").read_text(encoding="utf-8-sig", errors="replace")
    out, i = {}, 0
    for blk in re.finditer(r"\{([^{}]*)\}", txt):
        m = re.search(r'\bid\s*=\s*"([^"]+)"', blk.group(1))
        if m:
            out[m.group(1)] = i
            i += 1
    return out


def terrain_crop(cfg, canvas, crop) -> np.ndarray:
    from ck2ck3.map.ck2read import read_terrain_texture_map
    from ck2ck3.map.terrain import CK2_TO_CK3_TERRAIN

    ck2_map = Path(cfg["input"]["ck2_map_dir"])
    tex = read_terrain_texture_map(ck2_map / "terrain.txt")
    with Image.open(ck2_map / "terrain.bmp") as im:
        tidx = np.asarray(im)
    with Image.open(ck2_map / "trees.bmp") as im:
        trees = np.asarray(im)
    x0, y0, w, h = crop
    xs = (np.arange(x0, x0 + w) - canvas.offset_x) / canvas.factor + canvas.crop_x0
    ys = (np.arange(y0, y0 + h) - canvas.offset_y) / canvas.factor + canvas.crop_y0
    sx = np.clip(np.round(xs).astype(int), 0, tidx.shape[1] - 1)
    sy = np.clip(np.round(ys).astype(int), 0, tidx.shape[0] - 1)
    idx = tidx[np.ix_(sy, sx)]
    tr = trees[np.ix_(np.clip(sy // 8, 0, trees.shape[0] - 1),
                      np.clip(sx // 8, 0, trees.shape[1] - 1))]
    lut = np.array([CK2_TO_CK3_TERRAIN.get(tex.get(i, "plains"), "plains")
                    for i in range(256)], dtype=object)
    out = lut[idx].astype("U18")
    return np.where(np.isin(tr, [3, 4, 7, 10]) & (out != "mountains"), "forest", out)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    cfg = tomllib.loads(Path("configs/faerun_map.toml").read_text())
    ck2_map = Path(cfg["input"]["ck2_map_dir"])
    with Image.open(ck2_map / "provinces.bmp") as im:
        sw, sh = im.size
    sc = cfg["scale"]
    canvas = plan_canvas(sw, sh, ScaleConfig(
        vanilla_km_per_px=sc["vanilla_km_per_px"], source_km_per_px=sc["source_km_per_px"],
        sea_margin_px=sc["sea_margin_px"], canvas_multiple=sc["canvas_multiple"],
        max_canvas_px=sc["max_canvas_px"]))

    ords_ = material_ordinals()
    terr = terrain_crop(cfg, canvas, TILE)
    x0, y0, w, h = TILE

    rng = np.random.default_rng(11)
    # noise breaks the straight CK2 palette edges the way vanilla's hand paint does
    n = gaussian_filter(rng.standard_normal((h, w)).astype(np.float32), 1.5)
    n = (n - n.mean()) / (n.std() or 1.0)

    idx = np.zeros((h, w, 4), dtype=np.uint8)
    inten = np.zeros((h, w, 4), dtype=np.uint8)
    missing = set()
    for key in sorted(set(terr.ravel().tolist())):
        prim, sec = MATERIALS.get(key, ("plains_01", "plains_01_noisy"))
        for mid in (prim, sec):
            if mid not in ords_:
                missing.add(mid)
        m = terr == key
        idx[m, 0] = ords_.get(prim, 0)
        idx[m, 1] = ords_.get(sec, 0)
        w1 = np.clip(0.72 + 0.22 * n, 0.30, 0.98)
        # quantising the blend weight costs nothing visually and is what makes
        # detail_intensity.tga compressible: 16 steps instead of 256.
        q = np.round(w1 * 255 / QUANT) * QUANT
        inten[m, 0] = np.clip(q[m], 1, 254).astype(np.uint8)
        inten[m, 1] = 255 - inten[m, 0]
    if missing:
        print("material ids not in materials.settings:", sorted(missing))

    assert (inten.astype(int).sum(axis=2) == 255).all(), "intensity must sum to 255"

    rows = []
    full = (8320 * 6784) / (w * h)
    for name, arr in (("detail_index", idx), ("detail_intensity", inten)):
        buf = io.BytesIO()
        Image.fromarray(arr).save(buf, "TGA", rle=True)
        rle = buf.tell()
        buf = io.BytesIO()
        Image.fromarray(arr).save(buf, "PNG", optimize=True)
        png = buf.tell()
        rows.append({"file": name + ".tga", "tile": f"{w}x{h}",
                     "raw_MB": round(arr.nbytes / 1e6, 1),
                     "tga_rle_MB": round(rle / 1e6, 2),
                     "png_MB": round(png / 1e6, 2),
                     "full_canvas_raw_MB": round(arr.nbytes * full / 1e6),
                     "full_canvas_tga_rle_MB": round(rle * full / 1e6),
                     "full_canvas_png_MB": round(png * full / 1e6)})
    with (OUT / "terrain_paint_sizing.csv").open("w", newline="") as f:
        wri = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        wri.writeheader()
        wri.writerows(rows)
    for r in rows:
        print("  " + "  ".join(f"{k}={v}" for k, v in r.items()))

    # preview: colour each pixel by its primary material ordinal
    pal = (np.array([(37, 79, 43), (120, 130, 60), (86, 74, 52), (150, 150, 155),
                     (196, 172, 110), (60, 96, 70), (70, 100, 120), (150, 170, 90)],
                    dtype=np.uint8))
    keys = sorted(set(terr.ravel().tolist()))
    look = {k: pal[i % len(pal)] for i, k in enumerate(keys)}
    prev = np.zeros((h, w, 3), dtype=np.uint8)
    for k, c in look.items():
        prev[terr == k] = c
    img = Image.fromarray(prev).resize((640, 640), Image.NEAREST).quantize(colors=64)
    img.save(OUT / "terrain_paint_preview.png", optimize=True)
    print(f"  preview -> {OUT / 'terrain_paint_preview.png'} "
          f"({(OUT / 'terrain_paint_preview.png').stat().st_size / 1024:.0f} KiB), "
          f"classes: {', '.join(keys)}")


if __name__ == "__main__":
    main()
