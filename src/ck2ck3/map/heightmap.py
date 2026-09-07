"""CK2 ``topology.bmp`` (8-bit) -> CK3 ``heightmap.png`` (16-bit).

Two things have to line up or the coastline moves:

* CK2 stores the water surface at one 8-bit value (Faerûn ``topology.bmp`` has
  its sea floor around 33-47 and its lowest land around 97; the configured
  ``ck2_sea_level`` is what the mod's own ``default.map`` implies).
* CK3 stores the water surface at one 16-bit value, measured off vanilla's own
  coastline — see ``docs/map_scale.md``.  Everything below that value is under
  water in game, whatever ``provinces.png`` says.

So the transfer function is a piecewise-linear curve pinned at three points:
``0 -> 0``, ``ck2_sea_level -> ck3_water_level``, ``255 -> ck3_max_level``.
Extra control points from the config are inserted in between, which is how the
old GIMP-curve mountain compression is expressed without hardcoding it.

The resize is LANCZOS on the 8-bit source *before* the curve is applied, so the
interpolation happens in the source's own value space and the sea level stays a
single exact value on flat water.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from .config import Canvas, HeightmapConfig

Image.MAX_IMAGE_PIXELS = None


def build_curve(cfg: HeightmapConfig) -> np.ndarray:
    """256-entry uint16 lookup table, CK2 8-bit value -> CK3 16-bit value."""
    pts: dict[int, int] = {
        0: 0,
        int(cfg.ck2_sea_level): int(cfg.ck3_water_level),
        255: int(cfg.ck3_max_level),
    }
    for x, y in cfg.curve:
        pts[int(x)] = int(y)
    xs = np.array(sorted(pts), dtype=np.float64)
    ys = np.array([pts[int(x)] for x in xs], dtype=np.float64)
    if not np.all(np.diff(ys) >= 0):
        raise ValueError(
            f"heightmap curve must be non-decreasing, got {list(zip(xs.astype(int), ys.astype(int)))}"
        )
    lut = np.interp(np.arange(256), xs, ys)
    return np.clip(np.rint(lut), 0, 65535).astype(np.uint16)


def target_size(canvas: Canvas, cfg: HeightmapConfig) -> tuple[int, int]:
    """``(width, height)`` of ``heightmap.png``.

    ``resolution_factor`` 1 matches Elder Kings 2 (8256x5504) and Godherja
    (8192x4096), both of which declare ``original_heightmap_size`` equal to
    their provinces.png size; vanilla uses 2.  1 is the default here because it
    halves a 120 MB image and both shipping total conversions prove the game
    accepts it.
    """
    f = cfg.resolution_factor
    if f < 1:
        raise ValueError(f"heightmap resolution_factor must be >= 1, got {f}")
    return canvas.width * f, canvas.height * f


def build(
    ck2_topology_bmp: str | Path, canvas: Canvas, cfg: HeightmapConfig
) -> np.ndarray:
    """Return the 16-bit heightmap array, ready for ``packed_heightmap.write_packed``."""
    w, h = target_size(canvas, cfg)
    f = cfg.resolution_factor

    with Image.open(ck2_topology_bmp) as im:
        src = im.convert("L")
        scaled = src.resize(
            (canvas.scaled_width * f, canvas.scaled_height * f), Image.LANCZOS
        )
        scaled_arr = np.asarray(scaled)

    # the ocean margin sits at the CK2 sea level, so the curve puts it exactly
    # at the CK3 water level and the padding province reads as open sea
    out8 = np.full((h, w), cfg.ck2_sea_level, dtype=np.uint8)
    y0, x0 = canvas.offset_y * f, canvas.offset_x * f
    out8[y0 : y0 + scaled_arr.shape[0], x0 : x0 + scaled_arr.shape[1]] = scaled_arr

    return build_curve(cfg)[out8]


def write_png(heights: np.ndarray, path: str | Path) -> None:
    """Write a 16-bit greyscale PNG (PIL mode ``I;16``)."""
    if heights.dtype != np.uint16:
        raise ValueError(f"heightmap must be uint16, got {heights.dtype}")
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(heights, mode="I;16").save(p, optimize=True)


def measure_sea_level(
    topology: np.ndarray, province_ids: np.ndarray, water_ids: set[int]
) -> dict[str, float]:
    """Empirical CK2 sea level: the topology histogram over known water provinces.

    Used to check the configured ``ck2_sea_level`` against the mod's own data
    rather than trusting the CK2 default of 95.  Returns the water and land
    medians and the midpoint between the water 99th and land 1st percentile,
    which is the value the coastline actually sits at.
    """
    water_mask = np.isin(province_ids, list(water_ids))
    land_mask = (province_ids > 0) & ~water_mask
    water = topology[water_mask]
    land = topology[land_mask]
    if water.size == 0 or land.size == 0:
        raise ValueError("need both water and land pixels to measure a sea level")
    w99 = float(np.percentile(water, 99))
    l01 = float(np.percentile(land, 1))
    return {
        "water_median": float(np.median(water)),
        "water_p99": w99,
        "land_p01": l01,
        "land_median": float(np.median(land)),
        "suggested_sea_level": (w99 + l01) / 2.0,
    }
