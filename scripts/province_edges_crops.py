"""Before/after crops of ``provinces.png``, so the staircase is visible.

Lane ``province-edges``.  The metrics in
``docs/evidence/province_edges/staircase_*.csv`` say the boundary runs got
shorter; these panels are what that looks like.  Each figure is one window of
ground at the same canvas coordinates in both builds, magnified with NEAREST
so every pixel of the province map is a visible square — the point is the
pixels, so they must not be resampled away.

Two panels ship by default:

``sword_coast``
    The coastline north of Waterdeep.  Coast is the boundary that matters
    most: ``provinces.png``'s land/water line is the mask the colormap, the
    water rasters, the tree eligibility and the heightmap detail pass all
    read, so its shape is the shape of four other files.
``inland``
    A cluster of county borders with no water in it, picked automatically as
    the window holding the most distinct provinces (``--auto-inland``), so the
    figure is not a hand-chosen best case.

Usage::

    uv run scripts/province_edges_crops.py \
        --before ../claudespace/mods/faerun_ck2_to_ck3_converted/map_data \
        --after  ../wt/_out/province-edges/map_data \
        --out-dir docs/evidence/province_edges
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))

Image.MAX_IMAGE_PIXELS = None

#: (name, centre x, centre y) in **canvas** pixels, top-left origin.
#: Waterdeep's castle locator is logged at X 2345 Z 5724 and a locator z is
#: bottom-up (`z = height - y`, CLAUDE.md), so on the 6784-row canvas that is
#: y = 1060 -- the same row `docs/evidence/report_map_paint/panel_extents.csv`
#: uses for its Sword Coast panels.
DEFAULT_PANELS = (("sword_coast", 2345, 1060),)


def crop(path: Path, cx: int, cy: int, size: int) -> np.ndarray:
    with Image.open(path) as im:
        w, h = im.size
        x0 = max(0, min(w - size, cx - size // 2))
        y0 = max(0, min(h - size, cy - size // 2))
        return np.asarray(im.convert("RGB").crop((x0, y0, x0 + size, y0 + size)))


def find_busiest_window(
    path: Path, size: int, step: int, forbidden: set[int]
) -> tuple[int, int]:
    """Centre of the window with the most distinct provinces and no ``forbidden``.

    ``forbidden`` is the set of packed water colours, so the "inland" panel is
    genuinely inland: the figure has to show county borders on land, not the
    coastline the other panel already shows.  Scanned on a decimated copy so
    the search costs one pass, not one per candidate window.
    """
    with Image.open(path) as im:
        w, h = im.size
        arr = np.asarray(im.convert("RGB"))
    key = (
        (arr[..., 0].astype(np.int32) << 16)
        | (arr[..., 1].astype(np.int32) << 8)
        | arr[..., 2].astype(np.int32)
    )
    bad = np.fromiter(forbidden, dtype=np.int32) if forbidden else None
    best = (0, w // 2, h // 2)
    for y in range(0, h - size, step):
        for x in range(0, w - size, step):
            win = key[y : y + size : 2, x : x + size : 2]
            if bad is not None and np.isin(win, bad).any():
                continue
            n = np.unique(win).size
            if n > best[0]:
                best = (n, x + size // 2, y + size // 2)
    return best[1], best[2]


def outline(rgb: np.ndarray, width: int = 1) -> np.ndarray:
    """Darken the province boundaries so the shape reads at a glance."""
    key = (
        (rgb[..., 0].astype(np.int32) << 16)
        | (rgb[..., 1].astype(np.int32) << 8)
        | rgb[..., 2].astype(np.int32)
    )
    edge = np.zeros(key.shape, dtype=bool)
    edge[:-1, :] |= key[:-1, :] != key[1:, :]
    edge[1:, :] |= key[:-1, :] != key[1:, :]
    edge[:, :-1] |= key[:, :-1] != key[:, 1:]
    edge[:, 1:] |= key[:, :-1] != key[:, 1:]
    del width
    out = rgb.copy()
    out[edge] = (out[edge].astype(np.int32) * 40 // 100).astype(np.uint8)
    return out


def panel(arrays: list[tuple[str, np.ndarray]], zoom: int, title: str) -> Image.Image:
    """Side-by-side magnified crops with a caption strip."""
    tiles = [
        Image.fromarray(outline(a)).resize(
            (a.shape[1] * zoom, a.shape[0] * zoom), Image.NEAREST
        )
        for _label, a in arrays
    ]
    gap, bar, top = 12, 26, 24
    w = sum(t.width for t in tiles) + gap * (len(tiles) - 1)
    im = Image.new("RGB", (w, top + tiles[0].height + bar), (250, 250, 250))
    d = ImageDraw.Draw(im)
    d.text((2, 6), title, fill=(20, 20, 20))
    x = 0
    for (label, _a), t in zip(arrays, tiles):
        im.paste(t, (x, top))
        d.text((x + 4, top + t.height + 6), label, fill=(20, 20, 20))
        x += t.width + gap
    return im


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--before", type=Path, required=True, help="map_data dir")
    ap.add_argument("--after", type=Path, required=True, help="map_data dir")
    ap.add_argument("--out-dir", type=Path,
                    default=Path("docs/evidence/province_edges"))
    ap.add_argument("--size", type=int, default=120, help="crop side, canvas px")
    ap.add_argument("--zoom", type=int, default=5)
    ap.add_argument("--panel", action="append", default=[],
                    help="NAME=x,y (repeatable); replaces the defaults")
    ap.add_argument("--auto-inland", action="store_true", default=True)
    ap.add_argument("--no-auto-inland", dest="auto_inland", action="store_false")
    ap.add_argument("--search-step", type=int, default=256)
    args = ap.parse_args(argv)

    panels = list(DEFAULT_PANELS)
    if args.panel:
        panels = []
        for spec in args.panel:
            name, _, xy = spec.partition("=")
            x, y = (int(v) for v in xy.split(","))
            panels.append((name, x, y))
    if args.auto_inland and not args.panel:
        from province_edges_report import read_definition, water_name_indices

        defs = read_definition(args.after)
        index: dict[str, int] = {}
        water_names = water_name_indices(
            args.after, defs, {n: i for i, (n, _c) in enumerate(defs.values(), 1)}
        )
        del index
        by_name = {n: i for i, (n, _c) in enumerate(defs.values(), 1)}
        forbidden = {
            (r << 16) | (g << 8) | b
            for _pid, (name, (r, g, b)) in defs.items()
            if by_name.get(name) in water_names
        }
        x, y = find_busiest_window(
            args.after / "provinces.png", args.size, args.search_step, forbidden
        )
        panels.append(("inland", x, y))
        print(f"inland panel auto-picked at ({x}, {y})")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    for name, cx, cy in panels:
        arrays = [
            ("before (NEAREST)", crop(args.before / "provinces.png", cx, cy, args.size)),
            ("after (smooth argmax)", crop(args.after / "provinces.png", cx, cy, args.size)),
        ]
        img = panel(
            arrays,
            args.zoom,
            f"{name} — provinces.png at ({cx}, {cy}), {args.size} canvas px "
            f"({args.size * 1.4839:.0f} km) across, x{args.zoom} NEAREST",
        )
        out = args.out_dir / f"fig_{name}_before_after.png"
        img.save(out, optimize=True)
        print(f"wrote {out} ({img.width}x{img.height})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
