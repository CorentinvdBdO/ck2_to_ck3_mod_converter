"""The whole-map water rasters — ``gfx/map/water/*`` and the snow mask.

Three of CK3's map textures are sampled with a **whole-map UV**: the shader
divides the world position by the map size and reads the texture at that
fraction, so every texel is pinned to one spot of the map.  Ship none and a
custom map draws vanilla's Earth under its own geography — which is exactly
what the build-13 playtest saw: *"when zooming in the water, the map of Europe
appears"*.

The three, with the shader line that does it (`verified`, 1.19 game files):

===================================  ==========================================
``water/watercolor_rgb_waterspec_a`` ``jomini/jomini_water_default.fxh:505``
                                     ``PdxTex2D( WaterColorTexture, _WorldUV )``
                                     — RGB is the water's own colour, A is its
                                     gloss.  ``:42`` builds ``_WorldUV`` as
                                     ``(x / MapSize.x, 1 - z / MapSize.y)``.
                                     ``:346`` samples it again for refraction,
                                     and ``rivers/riverwater.settings:1`` points
                                     rivers at the same file, so the **land**
                                     texels are not dead — they are the colour
                                     of our rivers.
``water/foam_map``                   ``:289`` ``FoamMap = 1 - foam_map.r`` — the
                                     shore-foam allowance, so a **high** R means
                                     foam.  ``:275`` ``foam_map.g`` masks the
                                     approaching-wave pass.  B and A are
                                     constant across vanilla's whole raster
                                     (140 and 255).
``textures/snow_mask``               ``dynamic_masks.fxh:134``/``:209``
                                     ``_NoSnowMask = 1 - snow_mask.r`` at the
                                     whole-map UV: R = 255 means snow never
                                     falls here.  G, B and A are sampled
                                     *tiled* (``:105`` ``* _SnowNoiseTiling``,
                                     ``:144`` ``* 5.0``), so they are noise, not
                                     geography.
===================================  ==========================================

**Both shipped total conversions override all three** (`verified` by reading
their headers, `docs/step_map_water_border.md` §2): Elder Kings 2 at
4128x2752 / 4128x2752 / 2064x1376 for its 8256x5504 canvas, Godherja at
4096x2048 / 1024x512 / 2048x1024 for its 8192x4096 one.  Neither is at the
canvas's own resolution and their formats disagree (EK2 uncompressed A8R8G8B8
for the water colour, DXT3 for the foam; Godherja uncompressed and DXT5), so
the resolution and the compression are free choices — the **content** is not.

What this module writes is derived, never guessed:

* the colour, gloss and foam ramps come from ``mappings/water_profile.csv``,
  which is vanilla's own per-coast-distance mean, measured by
  ``scripts/measure_vanilla_water.py`` and indexed in **canvas pixels** so a
  change of ``[map] water_scale`` does not rescale the coastline;
* every pixel's index into that profile is *our* distance to *our* coast,
  from the map step's own ``water_mask``;
* the snow mask's R is flat 0 — both candidate derivations were measured and
  rejected (:func:`build_snow_mask`) — and its three noise channels are a
  resample of vanilla's own, because tiled noise carries no geography.

Format follows ``ck2ck3.map.colormap``: uncompressed A8R8G8B8 (BGRA on disk),
which is what both reference mods use for the water colour map and what this
repo already writes and tests for ``colormap.dds``.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

from . import colormap

#: where the engine looks; all three paths are hard-coded in the shaders
WATERCOLOR_PATH = "gfx/map/water/watercolor_rgb_waterspec_a.dds"
FOAM_MAP_PATH = "gfx/map/water/foam_map.dds"
SNOW_MASK_PATH = "gfx/map/textures/snow_mask.dds"

#: vanilla's own snow mask, resampled for the three tiled noise channels
VANILLA_SNOW_MASK = "gfx/map/textures/snow_mask.dds"

#: `verified` constant over the whole of vanilla's foam_map
FOAM_B_CONST = 140
FOAM_A_CONST = 255

#: used when mappings/water_profile.csv is missing: vanilla's own measured
#: deep-water colour and gloss, so a build without the table is still blue
#: rather than black (docs/evidence/vanilla_water_summary.csv).
FALLBACK_WATER = (24, 57, 58, 73)
FALLBACK_LAND = (59, 66, 61, 74)
FALLBACK_FOAM = (18, 255)

#: R = 0 means "the engine decides where snow falls"; see build_snow_mask
DEFAULT_NO_SNOW = 0
#: vanilla's own global means for the three tiled noise channels, the fallback
#: when the CK3 install is not readable (docs/evidence/vanilla_snow_mask.csv)
FALLBACK_SNOW_NOISE = (92, 85, 170)


@dataclass(frozen=True)
class ProfileRow:
    """One measured row of ``mappings/water_profile.csv``."""

    depth_px: int
    wc: tuple[int, int, int, int]
    foam: tuple[int, int]


def read_water_profile(path: str | Path) -> dict[str, list[ProfileRow]]:
    """``{"water": [...], "land": [...]}`` sorted by depth; ``{}`` if absent.

    ``#`` comment lines are skipped, like every other table reader here
    (a ``mappings/*.csv`` may open with a comment block — CLAUDE.md).
    """
    p = Path(path)
    if not p.exists():
        return {}
    with p.open("r", encoding="utf-8", newline="") as fh:
        lines = [line for line in fh if not line.lstrip().startswith("#")]
    out: dict[str, list[ProfileRow]] = {}
    for row in csv.DictReader(lines):
        zone = (row.get("zone") or "").strip()
        if zone not in ("water", "land"):
            continue
        try:
            out.setdefault(zone, []).append(
                ProfileRow(
                    depth_px=int(row["depth_px"]),
                    wc=(int(row["wc_r"]), int(row["wc_g"]),
                        int(row["wc_b"]), int(row["wc_a"])),
                    foam=(int(row["foam_r"]), int(row["foam_g"])),
                )
            )
        except (KeyError, ValueError):
            continue
    for rows in out.values():
        rows.sort(key=lambda r: r.depth_px)
    return out


def coast_distance(water_mask: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """``(into_water, into_land)`` Euclidean distance to the coast, in pixels.

    Each array is zero outside its own zone, so ``into_water`` is the depth of
    a sea pixel below the shoreline and ``into_land`` the same for land.  This
    is the quantity ``mappings/water_profile.csv`` is indexed by.
    """
    into_water = ndimage.distance_transform_edt(water_mask)
    into_land = ndimage.distance_transform_edt(~water_mask)
    return into_water, into_land


def _ramp(rows: list[ProfileRow], picker, depth: np.ndarray,
          px_per_texel: float, fallback: int) -> np.ndarray:
    """Interpolate one measured channel at every pixel's own coast distance.

    ``depth`` is in raster texels; the table is in canvas pixels, so the two
    are reconciled by ``px_per_texel``.  Past the table's last row the value is
    held, which is what "open ocean" means.
    """
    if not rows:
        return np.full(depth.shape, fallback, dtype=np.float32)
    xs = np.array([r.depth_px for r in rows], dtype=np.float32)
    ys = np.array([picker(r) for r in rows], dtype=np.float32)
    return np.interp(depth * px_per_texel, xs, ys).astype(np.float32)


def build_watercolor(
    water_mask: np.ndarray,
    *,
    profile: dict[str, list[ProfileRow]],
    px_per_texel: float = 2.0,
) -> np.ndarray:
    """``(h, w, 4)`` uint8 water colour + gloss, from our own coastline.

    ``water_mask`` is the raster-resolution boolean (``True`` = sea or lake).
    Every pixel takes vanilla's own measured colour at *its* distance to *our*
    coast, so the shelf ring that reads as shallow water follows Faerûn's
    shoreline instead of Europe's.
    """
    into_water, into_land = coast_distance(water_mask)
    out = np.zeros((*water_mask.shape, 4), dtype=np.float32)
    for zone, depth, mask, fallback in (
        ("water", into_water, water_mask, FALLBACK_WATER),
        ("land", into_land, ~water_mask, FALLBACK_LAND),
    ):
        rows = profile.get(zone, [])
        for c in range(4):
            band = _ramp(rows, lambda r, c=c: r.wc[c], depth, px_per_texel,
                         fallback[c])
            out[..., c] = np.where(mask, band, out[..., c])
    return np.clip(out, 0, 255).astype(np.uint8)


def build_foam_map(
    water_mask: np.ndarray,
    *,
    profile: dict[str, list[ProfileRow]],
    px_per_texel: float = 2.0,
) -> np.ndarray:
    """``(h, w, 4)`` uint8 foam map: R = foam allowance, G = the water mask.

    B and A are the constants vanilla holds across its whole raster
    (:data:`FOAM_B_CONST`, :data:`FOAM_A_CONST`).
    """
    into_water, into_land = coast_distance(water_mask)
    out = np.zeros((*water_mask.shape, 4), dtype=np.float32)
    for zone, depth, mask, fallback in (
        ("water", into_water, water_mask, FALLBACK_FOAM),
        ("land", into_land, ~water_mask, (71, 0)),
    ):
        rows = profile.get(zone, [])
        for c in range(2):
            band = _ramp(rows, lambda r, c=c: r.foam[c], depth, px_per_texel,
                         fallback[c])
            out[..., c] = np.where(mask, band, out[..., c])
    out[..., 2] = FOAM_B_CONST
    out[..., 3] = FOAM_A_CONST
    return np.clip(out, 0, 255).astype(np.uint8)


def snow_noise_channels(
    shape: tuple[int, int], game_dir: Path | None
) -> np.ndarray:
    """``(h, w, 3)`` uint8 G/B/A for the snow mask.

    These three are sampled *tiled* by the snow shader, never at a whole-map
    UV, so vanilla's own values carry no geography and a resample of them is
    the right override rather than an invention.  With no readable CK3 install
    they fall back to vanilla's measured global means, which costs the noise
    but keeps the mask valid.
    """
    h, w = shape
    if game_dir is not None:
        src = Path(game_dir) / VANILLA_SNOW_MASK
        if src.exists():
            with Image.open(src) as im:
                arr = np.asarray(im.convert("RGBA"))
            resized = np.asarray(
                Image.fromarray(arr[..., [1, 2, 3]]).resize(
                    (w, h), Image.LANCZOS
                )
            )
            return resized.astype(np.uint8)
    return np.broadcast_to(
        np.array(FALLBACK_SNOW_NOISE, dtype=np.uint8), (h, w, 3)
    ).copy()


def build_snow_mask(
    shape: tuple[int, int],
    *,
    no_snow: int = DEFAULT_NO_SNOW,
    game_dir: Path | None = None,
) -> np.ndarray:
    """``(h, w, 4)`` uint8 snow mask: flat R, vanilla's own noise in G/B/A.

    **R is flat by decision, and the neutral value is 0, not the mean.**  Two
    derivations were measured and both rejected
    (``scripts/measure_vanilla_snow_mask.py``,
    ``docs/step_map_water_border.md`` §4):

    * per terrain **material** — the per-material standard deviation exceeds
      the mean and the ranking inverts (``desert`` 48 against ``mountains``
      198), because vanilla reuses one material at every latitude it occurs
      at;
    * per **latitude** — that is what R really varies with, but the profile is
      Earth's own, and Faerûn's canvas carries no Earth latitudes to transfer
      it onto.

    R is a *suppression* mask, so vanilla's own raster mean (66) would suppress
    a quarter of the snow everywhere rather than nowhere; 0 hands the snow line
    back to the shader's own hemisphere term
    (``dynamic_masks.fxh:110``, ``_SnowHemisphere``) and the game's winter
    severity, which is where a fantasy map's climate should come from.
    ``[map] snow_mask_no_snow`` raises it for a map that wants a hot belt.
    """
    red = np.full(shape, max(0, min(255, no_snow)), dtype=np.uint8)
    out = np.empty((*shape, 4), dtype=np.uint8)
    out[..., 0] = red
    out[..., 1:] = snow_noise_channels(shape, game_dir)
    return out


def downsample(rgba: np.ndarray, scale: float) -> np.ndarray:
    """Lanczos-resample ``(h, w, 4)`` by ``scale``; a no-op at 1.0."""
    if scale == 1.0:
        return rgba
    h, w = rgba.shape[:2]
    nw = max(4, round(w * scale))
    nh = max(4, round(h * scale))
    return np.asarray(Image.fromarray(rgba).resize((nw, nh), Image.LANCZOS))


def save(rgba: np.ndarray, path: Path, *, mips: bool = False) -> None:
    """Write ``(h, w, 4)`` uint8 as an uncompressed BGRA8 DDS.

    The alpha is kept, not overwritten: it is the water colour map's gloss and
    the snow mask's third noise channel.  ``mips=False`` is Elder Kings 2's own
    shape for this file (`verified`, ``mips=1`` in its header).
    """
    colormap.save(rgba, path, mips=mips)
