"""``gfx/map/surround_map/surround_mask.dds`` — the frame around the map.

The build-13 playtest: *"the map border is broken at the top — probably to
hide northern Siberia in vanilla, but here it hides real content."*  That is
exactly what this file does, and the playtest's guess at why is right.

Three shaders read it, all at a whole-map UV with V flipped, all hard-coding
the path in the sampler declaration (`verified`, 1.19 game files):

* ``gfx/FX/pdxterrain.shader:398-407`` declares it, and ``:777-778``
  ``SurroundMapAlpha = 1 - mask.b; SurroundMapAlpha *= FlatMapLerp`` — the
  **B channel makes the terrain itself transparent** as the camera pulls out
  to the flat map (``FLAT_MAP_ZOOM_STEP = 21``).  B=255 hides the map, B=0
  shows it.
* ``gfx/FX/pdxborder.shader:93-104`` and ``:115-116``
  ``clip( 1 - mask.b - 0.1f )`` — the same channel throws away the political
  borders there, so the realm colours stop before the terrain does.
* ``gfx/FX/surroundmap.shader:137`` draws the surround plane itself with
  ``alpha = mask.b``; ``:230``/``:292`` read ``mask.g`` as the cloud mask
  ("don't draw clouds over map"); ``:352-354`` read ``mask.r`` as the map's
  drop shadow onto that plane.

Vanilla's own mask is hand-painted around **Earth's** coastline.  Measured
(`scripts/measure_vanilla_surround.py`, `verified`): its B channel eats a
median 6.5 % and a maximum **67 %** of the map height at the top, which is
empty Arctic on vanilla's map and the Spine of the World on ours.  Copying the
file is therefore not an option, and neither is shipping none.

What is transferable is the **thinnest frame vanilla itself uses** — the
profile it paints where its own content runs to the edge.  That is
``mappings/surround_profile.csv``: the element-wise minimum, over the four
edges, of each channel's 5th-percentile inward profile.  It is 54 texels deep
in total, B reaching 0 by texel 11, G by 44, R by 54 — at half canvas that is
108 canvas pixels, comfortably inside the 128 px sea margin our canvas is
built with (`docs/map_scale.md` §7), so the frame never touches land.

This module paints that one profile against ``min(distance to any of the four
canvas edges)``, which is the only sane generalisation: a rectangular frame of
constant width, on a canvas whose content reaches every edge.

Format: DXT1, vanilla's own (`ck2ck3.map.dxt1`, the encoder the flat map
already uses).  Elder Kings 2 re-authors this file as DXT5 4128x2752 for its
8256x5504 canvas and Godherja ships vanilla's 4096x2048 DXT1 byte-for-byte,
so neither the size nor the compression is load-bearing — the content is.
Alpha is unused by all three shaders (vanilla's is a constant 255), which is
what makes an alpha-less BC1 correct here.
"""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

from . import dxt1

#: where the engine looks; the path is hard-coded in three shader samplers
SURROUND_MASK_PATH = "gfx/map/surround_map/surround_mask.dds"

#: fallback frame when mappings/surround_profile.csv is missing: no frame at
#: all.  A missing table must not silently hide the map, which is the very bug
#: this module exists to fix.
EMPTY_PROFILE: np.ndarray = np.zeros((1, 3), dtype=np.uint8)


def read_profile(path: str | Path) -> np.ndarray:
    """``(depth, 3)`` uint8 R/G/B frame profile from the mapping table.

    Row ``d`` is the value at ``d`` texels in from the nearest edge.  ``#``
    comment lines are skipped (CLAUDE.md: every ``mappings/*.csv`` reader must).
    A missing or empty table gives :data:`EMPTY_PROFILE`.
    """
    p = Path(path)
    if not p.exists():
        return EMPTY_PROFILE
    with p.open("r", encoding="utf-8", newline="") as fh:
        lines = [line for line in fh if not line.lstrip().startswith("#")]
    rows: dict[int, tuple[int, int, int]] = {}
    for row in csv.DictReader(lines):
        try:
            rows[int(row["depth"])] = (
                int(row["r"]), int(row["g"]), int(row["b"])
            )
        except (KeyError, ValueError, TypeError):
            continue
    if not rows:
        return EMPTY_PROFILE
    out = np.zeros((max(rows) + 1, 3), dtype=np.uint8)
    for depth, rgb in rows.items():
        out[depth] = rgb
    return out


def edge_depth(width: int, height: int) -> np.ndarray:
    """``(h, w)`` int32: distance in texels to the nearest of the four edges."""
    ys = np.arange(height, dtype=np.int32)
    xs = np.arange(width, dtype=np.int32)
    dy = np.minimum(ys, height - 1 - ys)[:, None]
    dx = np.minimum(xs, width - 1 - xs)[None, :]
    return np.minimum(dy, dx)


def build(width: int, height: int, profile: np.ndarray) -> np.ndarray:
    """``(height, width, 3)`` uint8 mask: the measured frame on all four edges.

    Everything deeper than the profile is 0 — map fully visible, borders
    drawn, no clouds, no shadow.
    """
    depth = edge_depth(width, height)
    table = np.zeros((int(depth.max()) + 1, 3), dtype=np.uint8)
    usable = min(len(profile), len(table))
    table[:usable] = profile[:usable]
    return table[depth]


def save(rgb: np.ndarray, path: Path) -> None:
    """Write the mask as DXT1, vanilla's own format for this file."""
    dxt1.save(rgb, path)
