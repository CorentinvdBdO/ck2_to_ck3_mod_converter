"""Evidence for lane map-paint-seeds (docs/step_map_paint.md, Goal C).

Two things:

1. A before/after crop of the Sword Coast (Waterdeep - Baldur's Gate) composited
   in Python straight from the generated ``gfx/map/terrain/detail_index.tga`` /
   ``detail_intensity.tga`` layers. "Before" is the hard class edge CK2's
   palette gives (primary material only, no blend); "after" is what
   ``ck2ck3.map.terrain_paint`` actually ships (the two materials blended by a
   Gaussian-noise field, docs/map_fidelity.md §4.1). The colours are a small
   hand-picked swatch per vanilla material id, not the real ``.dds`` textures
   (this script never touches the game's art), so read it as "where the class
   boundary is" and "how much it dithers", not as a screenshot.
2. The seed-move table: every barony whose seed source is now
   ``port_position`` (CK2 positions.txt slot 4), with its old ("sampled")
   region centroid distance, for docs/step_map_paint.md and the handoff.

Run: uv run python scripts/render_map_paint_evidence.py [mod_dir]
mod_dir defaults to /home/cvdbdo/git/paradox/ck3/wt/_out/map-paint-seeds.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "docs" / "evidence" / "map_paint"

# Waterdeep (2344, 1098) to Baldur's Gate (2576, 1676) in canvas pixels, same
# crop docs/map_fidelity.md §4.2 prototyped the heightmap detail pass on.
TILE = (2080, 940, 2048, 2048)  # x0, y0, w, h

#: material id -> an approximate swatch colour (hand-picked, not sampled from
#: the vanilla .dds - this script never reads game art). Only the materials
#: mappings/terrain_paint.csv actually names need one.
SWATCH: dict[str, tuple[int, int, int]] = {
    "plains_01": (137, 160, 84),
    "plains_01_noisy": (124, 148, 78),
    "farmland_01": (176, 165, 90),
    "hills_01": (140, 132, 90),
    "hills_01_rocks": (128, 118, 100),
    "hills_01_rocks_medi": (150, 128, 92),
    "mountain_02": (120, 116, 118),
    "mountain_02_c": (150, 148, 150),
    "mountain_02_desert_c": (176, 140, 104),
    "desert_rocky": (170, 132, 96),
    "desert_02": (214, 186, 132),
    "desert_wavy_01": (222, 196, 148),
    "drylands_01": (188, 170, 118),
    "drylands_01_grassy": (168, 164, 104),
    "oasis": (96, 150, 96),
    "medi_grass_01": (118, 150, 88),
    "forest_jungle_01": (54, 104, 58),
    "forestfloor": (74, 90, 52),
    "forest_pine_01": (58, 92, 62),
    "snow": (232, 236, 240),
    "wetlands_02": (92, 108, 78),
    "wetlands_02_mud": (94, 84, 62),
    "steppe_grass": (156, 158, 96),
    "steppe_bushes": (140, 138, 84),
    "floodplains_01": (140, 156, 108),
    "mud_wet_01": (110, 96, 70),
    "beach_02": (206, 190, 150),
    "beach_02_pebbles": (176, 168, 148),
}
FALLBACK = (160, 160, 160)


def swatch(idx: int, ordinal_to_id: dict[int, str]) -> tuple[int, int, int]:
    return SWATCH.get(ordinal_to_id.get(idx, ""), FALLBACK)


def crop_rgba(path: Path, box: tuple[int, int, int, int]) -> np.ndarray:
    x0, y0, w, h = box
    with Image.open(path) as im:
        return np.asarray(im.crop((x0, y0, x0 + w, y0 + h)).convert("RGBA"))


def compose(idx: np.ndarray, inten: np.ndarray, ordinal_to_id: dict[int, str],
            *, blend: bool) -> np.ndarray:
    h, w = idx.shape[:2]
    pal = np.array(
        [swatch(i, ordinal_to_id) for i in range(256)], dtype=np.float32
    )
    prim = pal[idx[..., 0]]
    if not blend:
        return prim.astype(np.uint8)
    sec = pal[idx[..., 1]]
    w0 = (inten[..., 0].astype(np.float32) / 255.0)[..., None]
    w1 = (inten[..., 1].astype(np.float32) / 255.0)[..., None]
    out = prim * w0 + sec * w1
    return np.clip(out, 0, 255).astype(np.uint8)


def ordinals_reverse(mod: Path) -> dict[int, str]:
    sys.path.insert(0, str(REPO / "src"))
    from ck2ck3.map.terrain_paint import material_ordinals

    game = Path.home() / (
        ".local/share/Steam/steamapps/common/Crusader Kings III/game"
    )
    ords_ = material_ordinals(game / "gfx" / "map" / "terrain" / "materials.settings")
    return {v: k for k, v in ords_.items()}


def render_before_after(mod: Path) -> None:
    idx = crop_rgba(mod / "gfx" / "map" / "terrain" / "detail_index.tga", TILE)
    inten = crop_rgba(mod / "gfx" / "map" / "terrain" / "detail_intensity.tga", TILE)
    ordinal_to_id = ordinals_reverse(mod)

    before = compose(idx, inten, ordinal_to_id, blend=False)
    after = compose(idx, inten, ordinal_to_id, blend=True)

    OUT.mkdir(parents=True, exist_ok=True)
    for name, arr in (("sword_coast_before.png", before), ("sword_coast_after.png", after)):
        p = OUT / name
        Image.fromarray(arr).save(p, optimize=True)
        print(f"{name}: {p.stat().st_size / 1024:.0f} KiB")

    # a small side-by-side zoom, same idea as docs/map_fidelity.md §4.2's
    # zoom_before/zoom_after, so the edge dithering is visible without
    # opening two files
    zh, zw = 512, 512
    zy, zx = (TILE[3] - zh) // 2, (TILE[2] - zw) // 2
    combo = np.concatenate(
        [before[zy:zy + zh, zx:zx + zw], after[zy:zy + zh, zx:zx + zw]], axis=1
    )
    Image.fromarray(combo).save(OUT / "sword_coast_zoom_before_after.png", optimize=True)


def render_seed_moves() -> None:
    """Baronies whose seed source is port_position: docs/step_map_paint.md table."""
    ev = REPO / "docs" / "evidence" / "barony_set.csv"
    if not ev.exists():
        print(f"skip: {ev} not found (run the map step first)")
        return
    rows = list(csv.DictReader(ev.open()))
    placed = [r for r in rows if r["status"] in ("placed", "override")]
    ports = [r for r in placed if r["seed_source"] == "port_position"]
    by_source_placed, by_source_all = {}, {}
    for r in placed:
        by_source_placed[r["seed_source"]] = by_source_placed.get(r["seed_source"], 0) + 1
    for r in rows:
        by_source_all[r["seed_source"]] = by_source_all.get(r["seed_source"], 0) + 1

    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "seed_source_counts.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["seed_source", "placed", "placed_and_demoted"])
        for k in sorted(by_source_all):
            w.writerow([k, by_source_placed.get(k, 0), by_source_all[k]])
    with (OUT / "port_position_seeds.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(ports)
    demoted = sum(1 for r in rows if r["status"] == "demoted")
    print(f"seed sources (placed): {by_source_placed}")
    print(f"total placed {len(placed)}, demoted {demoted}")
    print(f"port_position, placed (new slot-4 seeds): {len(ports)} -> "
          f"{OUT / 'port_position_seeds.csv'}")


def main() -> None:
    mod = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
        "/home/cvdbdo/git/paradox/ck3/wt/_out/map-paint-seeds"
    )
    render_before_after(mod)
    render_seed_moves()


if __name__ == "__main__":
    main()
