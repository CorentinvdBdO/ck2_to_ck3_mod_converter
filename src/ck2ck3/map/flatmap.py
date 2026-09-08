"""``gfx/map/terrain/flat_maps/flatmap.dds`` — the zoomed-out paper map.

Above ``NGraphics.FLAT_MAP_ZOOM_STEP`` (21 in vanilla) CK3 stops drawing terrain
and draws a single texture the size of the canvas.  A mod that ships none
inherits vanilla's 9216x4608 painting of **Earth**, stretched over whatever
shape the mod's map is — which is what the Faerûn playtest saw
(`docs/evidence/map_ui_research.md` §4).

`_flat_map_styles.info` in the game files is explicit: *"Be sure to leave a
default flatmap.dds file in the folder anyway, it will be used when loading the
game."*  Elder Kings 2 and Godherja both ship one at their own canvas size.

This module paints a legible substitute rather than a work of art: parchment
for land, shaded by altitude so mountains read, and a muted blue-grey for
water.  It is deliberately not a downscale of ``provinces.png`` — province
colours are random ids and would make the paper map look like confetti.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from . import dxt1

#: where the engine looks; the style that selects it is
#: `gfx/map/flat_map_styles/flat_map_styles.txt` -> `paper_map_style_western`
FLATMAP_PATH = "gfx/map/terrain/flat_maps/flatmap.dds"


@dataclass(frozen=True)
class Palette:
    """Parchment-and-ink colours, tuned to read at a glance, not to be pretty."""

    #: land at the water line
    lowland: tuple[int, int, int] = (216, 200, 164)
    #: land at the highest point on the map
    highland: tuple[int, int, int] = (150, 124, 96)
    #: open water
    water: tuple[int, int, int] = (138, 158, 172)


def render(
    water_mask: np.ndarray,
    heights: np.ndarray | None = None,
    *,
    palette: Palette = Palette(),
    water_level: int = 4883,
) -> np.ndarray:
    """``(h, w, 3)`` uint8 paper map from the land/water mask and the heightmap.

    ``water_mask`` is the canvas-sized boolean the map step already builds for
    the rivers pass.  ``heights`` is the 16-bit heightmap; when it is a
    different resolution than the mask (``resolution_factor > 1``) it is
    decimated, and when it is ``None`` the land is painted flat.
    """
    h, w = water_mask.shape
    out = np.empty((h, w, 3), dtype=np.uint8)
    out[...] = np.array(palette.water, dtype=np.uint8)

    land = ~water_mask
    if heights is None:
        out[land] = np.array(palette.lowland, dtype=np.uint8)
        return out

    hm = heights
    if hm.shape != water_mask.shape:
        fy = hm.shape[0] // h
        fx = hm.shape[1] // w
        if fy < 1 or fx < 1:
            raise ValueError(
                f"heightmap {hm.shape[1]}x{hm.shape[0]} is smaller than the "
                f"canvas {w}x{h}"
            )
        hm = hm[::fy, ::fx][:h, :w]

    above = np.clip(hm.astype(np.float32) - water_level, 0, None)
    top = float(above.max())
    # sqrt so the first few hundred metres already tint: a linear ramp against
    # the map's single highest peak leaves the whole continent one flat colour.
    t = np.sqrt(above / top) if top > 0 else np.zeros_like(above)

    lo = np.array(palette.lowland, dtype=np.float32)
    hi = np.array(palette.highland, dtype=np.float32)
    shaded = lo + (hi - lo) * t[..., None]
    out[land] = shaded[land].astype(np.uint8)
    return out


def save(rgb: np.ndarray, path: Path) -> None:
    """Write the paper map as DXT1, the format all three reference maps use."""
    dxt1.save(rgb, path)
