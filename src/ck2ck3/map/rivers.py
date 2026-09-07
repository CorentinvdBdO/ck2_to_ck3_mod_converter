"""CK2 ``rivers.bmp`` -> CK3 ``rivers.png``, by tracing and redrawing.

Rivers are the one map layer a plain image resize destroys: they are 1-pixel
lines whose *connectivity* is the data.  Any resample either breaks a line into
dashes or thickens it past the 1-pixel width the game requires.  So the
converter vectorises: trace the river pixels into polylines at CK2 resolution,
scale the vertices, redraw with Bresenham at target resolution.  Connectivity is
then true by construction, at any scale factor.

The palette is byte-identical between CK2 and CK3 (`verified`: CK2
``Faerun/Faerun/map/rivers.bmp`` and CK3 ``game/map_data/rivers.png`` both give
index 0 = (0,255,0), 1 = (255,0,0), 2 = (255,252,0), 3..11 = blues,
254 = (255,0,128), 255 = (255,255,255)), so indices pass through unchanged.

Two bugs in the previous implementation this module exists to fix
(``docs/converter_code_assessment.md`` §3):

* **SPLIT (index 2, yellow) was not followed.**  A split is where a distributary
  leaves a larger river; it starts a path just like a source does.  Not
  following it dropped every delta branch.  Faerûn only has 9 such pixels, but
  they are 9 whole river branches.
* **WATER (index 254, magenta) was treated as river continuation.**  254 marks
  open water, not river; walking into it merges a river with the sea and drags
  the trace across the whole ocean.  Here 254 terminates a path.

Additionally, CK2 Faerûn never writes 254 at all — its ocean is plain land-white
(`verified`: no index 254 in ``rivers.bmp``), whereas vanilla CK3 marks all
18.8 M of its sea pixels 254.  So the converter paints 254 from the province
raster's water mask rather than copying the source, and only then draws rivers,
which are clipped to land.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image

from .config import Canvas

Image.MAX_IMAGE_PIXELS = None

SOURCE = 0
MERGE = 1
SPLIT = 2
BODY_MIN, BODY_MAX = 3, 11
WATER = 254
LAND = 255

SPECIAL = (SOURCE, MERGE, SPLIT)

#: the shared CK2/CK3 rivers palette, index -> RGB
PALETTE: dict[int, tuple[int, int, int]] = {
    0: (0, 255, 0),
    1: (255, 0, 0),
    2: (255, 252, 0),
    3: (0, 225, 255),
    4: (0, 200, 255),
    5: (0, 150, 255),
    6: (0, 100, 255),
    7: (0, 0, 255),
    8: (0, 0, 225),
    9: (0, 0, 200),
    10: (0, 0, 150),
    11: (0, 0, 100),
    254: (255, 0, 128),
    255: (255, 255, 255),
}

_NEIGHBOURS = [
    (-1, -1), (-1, 0), (-1, 1),
    (0, -1), (0, 1),
    (1, -1), (1, 0), (1, 1),
]


#: every palette index that is part of a river (not 254 water, not 255 land)
RIVER_INDICES: tuple[int, ...] = tuple(SPECIAL) + tuple(range(BODY_MIN, BODY_MAX + 1))


def is_river(idx: int) -> bool:
    """River pixels are the three specials plus the width bodies. 254 is not."""
    return idx in SPECIAL or BODY_MIN <= idx <= BODY_MAX


def river_mask(idx_map: np.ndarray) -> np.ndarray:
    """Vectorised ``is_river`` over a whole bitmap.

    ``np.isin`` against the index list, not ``np.vectorize(is_river)``: the
    latter is a Python call per pixel and takes minutes on a 13.6 Mpx bitmap.
    """
    return np.isin(idx_map, RIVER_INDICES)


@dataclass
class RiverPath:
    """One traced polyline in source pixel coordinates."""

    points: list[tuple[int, int]] = field(default_factory=list)  # (y, x)
    #: palette index of each point, so specials keep their meaning
    values: list[int] = field(default_factory=list)

    @property
    def width_index(self) -> int:
        bodies = [v for v in self.values if BODY_MIN <= v <= BODY_MAX]
        if not bodies:
            return BODY_MIN
        return int(np.bincount(bodies).argmax())


def trace(idx_map: np.ndarray) -> list[RiverPath]:
    """Trace every river pixel into polylines.

    Walk order: start from the specials (source / merge / split) first so their
    pixel is the head of a path, then from plain endpoints, then from anything
    left over (rings).  Every river pixel ends up in exactly one path, so
    nothing is silently dropped — which is what made the old follow-the-river
    code lose branches.
    """
    h, w = idx_map.shape
    river = river_mask(idx_map)
    degree = _degree(river)
    visited = np.zeros_like(river)

    def neighbours(y: int, x: int) -> list[tuple[int, int]]:
        out = []
        for dy, dx in _NEIGHBOURS:
            ny, nx = y + dy, x + dx
            if 0 <= ny < h and 0 <= nx < w and river[ny, nx]:
                out.append((ny, nx))
        return out

    def walk(sy: int, sx: int) -> RiverPath:
        path = RiverPath()
        y, x = sy, sx
        while True:
            visited[y, x] = True
            path.points.append((y, x))
            path.values.append(int(idx_map[y, x]))
            nxt = [
                (ny, nx)
                for ny, nx in neighbours(y, x)
                if not visited[ny, nx]
            ]
            if not nxt:
                return path
            # prefer continuing along a body pixel of the same width, and
            # prefer 4-connected steps so the redrawn line is not needlessly
            # diagonal
            nxt.sort(
                key=lambda p: (
                    int(idx_map[p] in SPECIAL),
                    abs(p[0] - y) + abs(p[1] - x),
                )
            )
            y, x = nxt[0]
            if degree[y, x] > 2:  # junction: end the path here, on the junction
                visited[y, x] = True
                path.points.append((y, x))
                path.values.append(int(idx_map[y, x]))
                return path

    paths: list[RiverPath] = []
    # Seed order matters: specials first so a source/merge/split is the head of
    # its path, then plain endpoints, then whatever is left (closed loops).
    # All three seed lists are computed ONCE. Recomputing "which river pixels
    # are still unvisited" inside the loop is a full 13.6 Mpx scan per leftover
    # pixel and never finishes on a real map.
    specials = _coords(np.isin(idx_map, SPECIAL))
    endpoints = _coords(river & (degree == 1))
    everything = _coords(river)

    for seeds in (specials, endpoints, everything):
        for y, x in seeds:
            if not visited[y, x]:
                paths.append(walk(y, x))
    return [p for p in paths if p.points]


def _coords(mask: np.ndarray) -> list[tuple[int, int]]:
    ys, xs = np.nonzero(mask)
    return list(zip(ys.tolist(), xs.tolist()))


def _degree(river: np.ndarray) -> np.ndarray:
    """8-neighbour river-pixel count per pixel."""
    padded = np.pad(river.astype(np.int16), 1)
    deg = np.zeros_like(padded)
    for dy, dx in _NEIGHBOURS:
        deg += np.roll(np.roll(padded, dy, axis=0), dx, axis=1)
    return deg[1:-1, 1:-1] * river


def bresenham(y0: int, x0: int, y1: int, x1: int) -> list[tuple[int, int]]:
    """Integer line from (y0,x0) to (y1,x1) inclusive, 8-connected, 1 px wide."""
    points = []
    dy, dx = abs(y1 - y0), abs(x1 - x0)
    sy = 1 if y1 >= y0 else -1
    sx = 1 if x1 >= x0 else -1
    err = dx - dy
    y, x = y0, x0
    while True:
        points.append((y, x))
        if y == y1 and x == x1:
            return points
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            x += sx
        if e2 < dx:
            err += dx
            y += sy


def render(
    ck2_rivers_bmp: str | Path,
    canvas: Canvas,
    water_mask: np.ndarray,
) -> np.ndarray:
    """Build the target ``rivers.png`` index array.

    ``water_mask`` is a boolean array of the canvas shape, True where the
    province raster says sea or lake; those pixels become 254.  Rivers are drawn
    only on land, so a river never overwrites the water mask it flows into.
    """
    with Image.open(ck2_rivers_bmp) as im:
        if im.mode != "P":
            raise ValueError(
                f"CK2 rivers.bmp must be an 8-bit palette image, got mode {im.mode}"
            )
        src = np.asarray(im).astype(np.int16)

    if water_mask.shape != (canvas.height, canvas.width):
        raise ValueError(
            f"water_mask {water_mask.shape} does not match canvas "
            f"{(canvas.height, canvas.width)}"
        )

    out = np.full((canvas.height, canvas.width), LAND, dtype=np.uint8)
    out[water_mask] = WATER

    for path in trace(src):
        scaled = [canvas.to_target(x, y) for (y, x) in path.points]  # -> (x, y)
        width = path.width_index
        # body first, so a special pixel is never overdrawn by the next segment
        for (x0, y0), (x1, y1) in zip(scaled, scaled[1:]):
            for py, px in bresenham(y0, x0, y1, x1):
                if 0 <= py < canvas.height and 0 <= px < canvas.width:
                    if not water_mask[py, px]:
                        out[py, px] = width
        for (x, y), value in zip(scaled, path.values):
            if value in SPECIAL and 0 <= y < canvas.height and 0 <= x < canvas.width:
                if not water_mask[y, x]:
                    out[y, x] = value
    return out


def write_png(idx: np.ndarray, path: str | Path) -> None:
    """Write ``map_data/rivers.png`` as an 8-bit palette PNG with CK3's palette."""
    im = Image.fromarray(idx, mode="P")
    flat = [0] * 768
    for i, (r, g, b) in PALETTE.items():
        flat[i * 3 : i * 3 + 3] = [r, g, b]
    im.putpalette(flat)
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    im.save(p, optimize=True)


def stats(idx: np.ndarray) -> dict[str, int]:
    uniq, counts = np.unique(idx, return_counts=True)
    by = dict(zip(uniq.tolist(), counts.tolist()))
    return {
        "sources": by.get(SOURCE, 0),
        "merges": by.get(MERGE, 0),
        "splits": by.get(SPLIT, 0),
        "body": sum(by.get(i, 0) for i in range(BODY_MIN, BODY_MAX + 1)),
        "water": by.get(WATER, 0),
        "land": by.get(LAND, 0),
    }
