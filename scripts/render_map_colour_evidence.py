#!/usr/bin/env python3
"""Evidence for lane map-colour, Goal D: three region composites.

Province outlines + the resampled ``colormap.dds`` + a hillshade of the
heightmap, for three named regions, straight from a real converter output
directory (no game engine involved — this is what the coordinator's in-game
check should compare against, not a substitute for it).

Region centres, all `verified` against this lane's own full-run output
(``/home/cvdbdo/git/paradox/ck3/wt/_out/map-colour``), canvas pixels
(8320x6784, top-down y):

* **Sword Coast** (2080, 940) 2048x2048 — the Waterdeep-Baldur's Gate crop
  established by ``scripts/render_map_paint_evidence.py`` (lane
  map-paint-seeds), reused unchanged so the two lanes' evidence lines up.
* **Anauroch** (3321, 1067) 2048x2048 — the centroid of the largest connected
  "desert"-terrain blob in the *north* half of the canvas (there are several
  disconnected deserts on Faerun; the north/west position matches Anauroch's
  own lore geography, the others are the southern deserts). Found via
  ``scipy.ndimage.label`` on the desert mask built from
  ``common/province_terrain`` + ``map_data/definition.csv`` +
  ``map_data/provinces.png``.
* **Spine of the World** (2429, 453) 2048x1024 — the exact province named
  "Spine of the World" in ``docs/evidence/province_id_map.csv``
  (CK3 id 4056, rgb (161, 200, 228)), an `impassable_mountains` range at the
  far north edge of the canvas, hence the shorter crop height.

Run: uv run python scripts/render_map_colour_evidence.py [out_dir]
out_dir defaults to /home/cvdbdo/git/paradox/ck3/wt/_out/map-colour.
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
OUT_DIR = REPO / "docs" / "evidence" / "map_colour"

WATER = 4883
MAXLVL = 49205

#: (name, x0, y0, w, h) in canvas pixels, top-down y
REGIONS: tuple[tuple[str, int, int, int, int], ...] = (
    ("sword_coast", 2080, 940, 2048, 2048),
    ("anauroch", 2297, 43, 2048, 2048),
    ("spine_of_the_world", 1405, 0, 2048, 1024),
)

#: target long-side px for the saved PNG (keeps every file well under 400 KB)
MAX_SAVE_PX = 900


def load_province_terrain(mod: Path) -> dict[int, str]:
    out: dict[int, str] = {}
    d = mod / "common" / "province_terrain"
    row_re = re.compile(r"^\s*(\d+)\s*=\s*(\w+)", re.M)
    for p in sorted(d.glob("*.txt")):
        text = p.read_text(encoding="utf-8-sig", errors="replace")
        for m in row_re.finditer(text):
            out[int(m.group(1))] = m.group(2)
    return out


def load_definition_rgb(mod: Path) -> dict[int, tuple[int, int, int]]:
    out = {}
    with (mod / "map_data" / "definition.csv").open(
        "r", encoding="utf-8-sig", newline=""
    ) as fh:
        r = csv.reader(fh, delimiter=";")
        next(r, None)
        for row in r:
            if len(row) < 4:
                continue
            try:
                pid, red, g, b = int(row[0]), int(row[1]), int(row[2]), int(row[3])
            except ValueError:
                continue
            out[pid] = (red, g, b)
    return out


def find_anauroch_centre(mod: Path) -> tuple[int, int]:
    """The centroid of the largest north-half "desert" blob (module docstring)."""
    from scipy.ndimage import label

    pt = load_province_terrain(mod)
    id_rgb = load_definition_rgb(mod)
    desert_rgbs = {
        id_rgb[pid] for pid, key in pt.items() if key == "desert" and pid in id_rgb
    }
    with Image.open(mod / "map_data" / "provinces.png") as im:
        rgb = np.asarray(im.convert("RGB"))
    key = (
        rgb[..., 0].astype(np.int64) << 16
        | rgb[..., 1].astype(np.int64) << 8
        | rgb[..., 2].astype(np.int64)
    )
    desert_keys = {(r << 16 | g << 8 | b) for r, g, b in desert_rgbs}
    mask = np.isin(key, list(desert_keys))
    small = mask[::4, ::4]
    lbl, n = label(small)
    sizes = np.bincount(lbl.ravel())
    sizes[0] = 0
    # among the biggest few blobs, the northernmost (smallest mean y) is
    # Anauroch; the others are the southern deserts (Calim/Raurin analogues)
    top = np.argsort(sizes)[::-1][:6]
    best = min(top, key=lambda c: np.nonzero(lbl == c)[0].mean())
    ys, xs = np.nonzero(lbl == best)
    return int(xs.mean() * 4), int(ys.mean() * 4)


def crop_rgb(path: Path, box: tuple[int, int, int, int]) -> np.ndarray:
    x0, y0, w, h = box
    with Image.open(path) as im:
        return np.asarray(im.crop((x0, y0, x0 + w, y0 + h)).convert("RGB"))


def crop_gray16(path: Path, box: tuple[int, int, int, int]) -> np.ndarray:
    x0, y0, w, h = box
    with Image.open(path) as im:
        return np.asarray(im.crop((x0, y0, x0 + w, y0 + h)))


def province_outline(prov_rgb: np.ndarray) -> np.ndarray:
    """Boolean edge mask: a pixel whose right or down neighbour is a different colour."""
    h, w = prov_rgb.shape[:2]
    edge = np.zeros((h, w), dtype=bool)
    diff_x = np.any(prov_rgb[:, 1:] != prov_rgb[:, :-1], axis=-1)
    diff_y = np.any(prov_rgb[1:, :] != prov_rgb[:-1, :], axis=-1)
    edge[:, :-1] |= diff_x
    edge[:, 1:] |= diff_x
    edge[:-1, :] |= diff_y
    edge[1:, :] |= diff_y
    return edge


def hillshade_rgb(h: np.ndarray, water: np.ndarray, az=315.0, alt=45.0, z=6.0) -> np.ndarray:
    """Same formula as scripts/heightmap_detail_evidence.py, inlined to avoid a dep."""
    gy, gx = np.gradient(h.astype(np.float32) * z / 65535.0 * 200.0)
    slope = np.arctan(np.hypot(gx, gy))
    aspect = np.arctan2(-gx, gy)
    a, e = np.radians(az), np.radians(alt)
    shade = np.sin(e) * np.cos(slope) + np.cos(e) * np.sin(slope) * np.cos(a - aspect)
    return np.clip(shade, 0, 1)


def colormap_crop(mod: Path, box: tuple[int, int, int, int], canvas: tuple[int, int]) -> np.ndarray:
    """The resampled colormap.dds, cropped to ``box`` (full canvas pixel space).

    ``colormap.dds`` ships at ``[map] colormap_scale`` of canvas resolution
    (0.25 by default): crop in the colormap's own smaller pixel space, then
    upsample back to ``box``'s size so it aligns with the province/heightmap
    layers pixel-for-pixel.
    """
    x0, y0, w, h = box
    cw, ch = canvas
    with Image.open(mod / "gfx" / "map" / "terrain" / "colormap.dds") as im:
        im = im.convert("RGB")
        sx, sy = im.width / cw, im.height / ch
        sx0, sy0 = int(x0 * sx), int(y0 * sy)
        sw, sh = max(1, round(w * sx)), max(1, round(h * sy))
        small = im.crop((sx0, sy0, sx0 + sw, sy0 + sh))
        return np.asarray(small.resize((w, h), Image.LANCZOS))


def compose(mod: Path, name: str, box: tuple[int, int, int, int]) -> np.ndarray:
    with Image.open(mod / "map_data" / "provinces.png") as im:
        canvas = im.size  # (w, h)
    prov = crop_rgb(mod / "map_data" / "provinces.png", box)
    heights = crop_gray16(mod / "map_data" / "heightmap.png", box)
    water = heights <= WATER
    shade = hillshade_rgb(heights, water)
    cmap = colormap_crop(mod, box, canvas).astype(np.float32)

    out = cmap * (0.55 + 0.45 * shade[..., None])
    out[water] = np.array([46, 66, 96], dtype=np.float32)
    out = np.clip(out, 0, 255).astype(np.uint8)

    edges = province_outline(prov)
    out[edges] = (20, 20, 20)
    return out


def save(img: np.ndarray, path: Path) -> None:
    im = Image.fromarray(img)
    if max(im.size) > MAX_SAVE_PX:
        scale = MAX_SAVE_PX / max(im.size)
        im = im.resize(
            (round(im.width * scale), round(im.height * scale)), Image.LANCZOS
        )
    im = im.quantize(colors=96, method=Image.MEDIANCUT, dither=Image.Dither.NONE)
    im.save(path, optimize=True)
    kb = path.stat().st_size / 1024
    print(f"  {path.name}  {im.size}  {kb:.0f} KiB" + ("  !! over 400 KiB" if kb > 400 else ""))


def main() -> None:
    mod = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
        "/home/cvdbdo/git/paradox/ck3/wt/_out/map-colour"
    )
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"reading from {mod}")
    for name, x0, y0, w, h in REGIONS:
        img = compose(mod, name, (x0, y0, w, h))
        save(img, OUT_DIR / f"{name}.png")


if __name__ == "__main__":
    main()
