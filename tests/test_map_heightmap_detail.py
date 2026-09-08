"""Tests for the vanilla-matched heightmap detail synthesis pass.

``docs/map_fidelity.md`` §4.2: a synthetic island stands in for the real
Faerûn heightmap so these run in milliseconds. The invariants that matter are
the sea-level pin, the coastline (no land pixel below water, no water pixel
touched at all), determinism, and terrain-aware amplitude -- not any exact
numeric output, which is stochastic by design.
"""

from __future__ import annotations

import numpy as np
import pytest
from scipy.ndimage import distance_transform_edt, gaussian_filter

from ck2ck3.map import heightmap_detail as hd
from ck2ck3.map.config import HeightmapDetailConfig

WATER = 4883
MAXLVL = 49205
KM_PER_PX = 1.4839


def _island(h: int = 120, w: int = 140, margin: int = 20, plateau: int = 20000):
    """A square island with a smooth (not cliff) coastal ramp, all plains."""
    land = np.zeros((h, w), dtype=bool)
    land[margin : h - margin, margin : w - margin] = True
    d_land = distance_transform_edt(land)
    taper = np.clip(d_land / 8, 0, 1)
    land_height = WATER + 1 + taper * (plateau - WATER - 1)
    heights = np.where(land, land_height, WATER)
    heights = np.clip(heights, 0, MAXLVL).astype(np.uint16)
    terrain_code = np.zeros((h, w), dtype=np.uint8)
    river_body = np.zeros((h, w), dtype=bool)
    river_width_index = np.zeros((h, w), dtype=np.float32)
    return heights, land, terrain_code, river_body, river_width_index


def _apply(heights, land, terrain_code, river_body, river_width_index,
           terrain_keys=("plains",), **cfg_kw):
    cfg_kw.setdefault("seed", 1357)
    cfg = HeightmapDetailConfig(enabled=True, **cfg_kw)
    return hd.apply(
        heights,
        land_mask=land,
        terrain_code=terrain_code,
        terrain_keys=list(terrain_keys),
        river_body=river_body,
        river_width_index=river_width_index,
        km_per_px=KM_PER_PX,
        water_level=WATER,
        max_level=MAXLVL,
        cfg=cfg,
    )


# --------------------------------------------------------------------------- #
# the sea-level pin and the coastline
# --------------------------------------------------------------------------- #
def test_water_pixels_are_byte_identical_to_the_input():
    heights, land, tc, rb, rw = _island()
    out, _ = _apply(heights, land, tc, rb, rw)
    assert np.array_equal(out[~land], heights[~land])


def test_every_land_pixel_stays_strictly_above_the_water_level():
    heights, land, tc, rb, rw = _island()
    out, _ = _apply(heights, land, tc, rb, rw)
    assert (out[land].astype(np.int64) > WATER).all()


def test_every_land_pixel_stays_at_or_below_the_configured_ceiling():
    heights, land, tc, rb, rw = _island()
    out, _ = _apply(heights, land, tc, rb, rw)
    assert (out[land].astype(np.int64) <= MAXLVL).all()


def test_output_is_uint16():
    heights, land, tc, rb, rw = _island()
    out, _ = _apply(heights, land, tc, rb, rw)
    assert out.dtype == np.uint16


def test_output_shape_matches_input():
    heights, land, tc, rb, rw = _island()
    out, _ = _apply(heights, land, tc, rb, rw)
    assert out.shape == heights.shape


def test_water_pixels_above_the_pin_in_the_input_are_clamped_down():
    """The plain rescale (heightmap.build) can itself leave a water pixel
    above the water level -- provinces.png's land/water classification and
    topology.bmp's own value do not perfectly agree at every coastline pixel.
    This pass must not pass such a pixel through unfixed.
    """
    heights, land, tc, rb, rw = _island()
    heights = heights.copy()
    stray = ~land
    ys, xs = np.nonzero(stray)
    heights[ys[0], xs[0]] = WATER + 500  # a pre-existing rescale artefact
    out, stats = _apply(heights, land, tc, rb, rw)
    assert int(out[ys[0], xs[0]]) <= WATER
    assert stats["water_px_clamped"] == 1


def test_all_sea_no_land_is_a_no_op():
    """A province set with no land at all must not crash or touch anything."""
    h, w = 40, 40
    heights = np.full((h, w), WATER, dtype=np.uint16)
    land = np.zeros((h, w), dtype=bool)
    tc = np.zeros((h, w), dtype=np.uint8)
    rb = np.zeros((h, w), dtype=bool)
    rw = np.zeros((h, w), dtype=np.float32)
    out, stats = _apply(heights, land, tc, rb, rw)
    assert np.array_equal(out, heights)
    assert stats["distinct_values_after"] == 1


# --------------------------------------------------------------------------- #
# determinism
# --------------------------------------------------------------------------- #
def test_same_seed_is_deterministic():
    heights, land, tc, rb, rw = _island()
    out1, _ = _apply(heights, land, tc, rb, rw)
    out2, _ = _apply(heights, land, tc, rb, rw)
    assert np.array_equal(out1, out2)


def test_different_seed_changes_the_land_pixels():
    heights, land, tc, rb, rw = _island()
    # force a nonzero gain (the default island's HF is already near vanilla's
    # own "plains" target, which would make both seeds add ~0 noise)
    big_target = {"plains": 5000.0}
    out1, _ = _apply(heights, land, tc, rb, rw, seed=1, hf_targets=big_target)
    out2, _ = _apply(heights, land, tc, rb, rw, seed=2, hf_targets=big_target)
    assert not np.array_equal(out1[land], out2[land])
    # the invariant still holds under a different seed
    assert np.array_equal(out1[~land], out2[~land])


# --------------------------------------------------------------------------- #
# detail actually gets added
# --------------------------------------------------------------------------- #
def test_distinct_values_increase():
    """The whole point: fewer than ~160 flat levels in, many more out."""
    heights, land, tc, rb, rw = _island()
    out, stats = _apply(heights, land, tc, rb, rw)
    assert stats["distinct_values_after"] > stats["distinct_values_before"]
    assert stats["distinct_values_before"] == int(np.unique(heights).size)
    assert stats["distinct_values_after"] == int(np.unique(out).size)


def test_stats_report_elapsed_time_and_terrain_gain_rows():
    heights, land, tc, rb, rw = _island()
    _, stats = _apply(heights, land, tc, rb, rw)
    assert stats["elapsed_s"] >= 0
    assert stats["terrain_gain"], "expected at least one terrain-class gain row"
    assert stats["terrain_gain"][0]["terrain"] == "plains"


# --------------------------------------------------------------------------- #
# terrain-aware amplitude: mountains rougher than plains
# --------------------------------------------------------------------------- #
def test_mountains_get_more_detail_than_plains():
    """Same flat starting elevation, split coast-to-coast; only the terrain
    label differs. Vanilla's mountains HF RMS (311.4) is far above plains'
    (86.3, docs/map_fidelity.md §1.2), so the synthesised noise must be too.
    """
    h, w, margin = 300, 300, 30
    land = np.zeros((h, w), dtype=bool)
    land[margin : h - margin, margin : w - margin] = True
    d_land = distance_transform_edt(land)
    taper = np.clip(d_land / 8, 0, 1)
    land_height = WATER + 1 + taper * (20000 - WATER - 1)
    heights = np.clip(np.where(land, land_height, WATER), 0, MAXLVL).astype(np.uint16)

    terrain_code = np.zeros((h, w), dtype=np.uint8)
    terrain_code[:, w // 2 :] = 1  # west = plains (0), east = mountains (1)
    river_body = np.zeros((h, w), dtype=bool)
    river_width_index = np.zeros((h, w), dtype=np.float32)

    out, _ = _apply(
        heights, land, terrain_code, river_body, river_width_index,
        terrain_keys=("plains", "mountains"), seed=7,
    )

    # measured away from the coastal ramp, where both halves started identical
    inner = (d_land > 20) & land
    sigma_px = hd.HF_SIGMA_KM / KM_PER_PX

    def hf_rms(mask: np.ndarray) -> float:
        r = out.astype(np.float64) - gaussian_filter(
            out.astype(np.float64), sigma_px, mode="nearest"
        )
        return float(r[mask].std())

    plains_hf = hf_rms(inner & (terrain_code == 0))
    mountains_hf = hf_rms(inner & (terrain_code == 1))
    assert mountains_hf > 3 * plains_hf


# --------------------------------------------------------------------------- #
# river valleys never raise a pixel
# --------------------------------------------------------------------------- #
def test_river_carving_only_lowers_land_never_raises_it():
    heights, land, tc, rb, rw = _island()
    rb = rb.copy()
    mid = heights.shape[0] // 2
    rb[mid, :] = land[mid, :]
    rw = rw.copy()
    rw[rb] = 5.0

    out_river, _ = _apply(heights, land, tc, rb, rw, seed=99)
    out_no_river, _ = _apply(heights, land, tc, np.zeros_like(rb), rw, seed=99)

    river_land = rb & land
    # the river row must not end up higher than it would with no river at all
    assert (
        out_river[river_land].astype(np.int64) <= out_no_river[river_land].astype(np.int64)
    ).all()


def test_river_stays_above_the_water_level_even_when_carved():
    heights, land, tc, rb, rw = _island()
    rb = rb.copy()
    mid = heights.shape[0] // 2
    rb[mid, :] = land[mid, :]
    rw = rw.copy()
    rw[rb] = 3.0  # widest body colour -> deepest cut

    out, _ = _apply(heights, land, tc, rb, rw, river_depth=900.0)
    assert (out[rb & land].astype(np.int64) > WATER).all()


# --------------------------------------------------------------------------- #
# input validation
# --------------------------------------------------------------------------- #
def test_rejects_non_uint16_heights():
    heights, land, tc, rb, rw = _island()
    with pytest.raises(ValueError, match="uint16"):
        _apply(heights.astype(np.int32), land, tc, rb, rw)


def test_rejects_a_mask_shape_mismatch():
    heights, land, tc, rb, rw = _island()
    with pytest.raises(ValueError, match="does not match"):
        _apply(heights, land[:-1, :], tc, rb, rw)
