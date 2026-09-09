"""Tests for the 8-bit CK2 topology -> 16-bit CK3 heightmap conversion."""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from ck2ck3.map import bootstrap, heightmap
from ck2ck3.map.config import Canvas, HeightmapConfig


def cfg(**kw) -> HeightmapConfig:
    base = dict(
        resolution_factor=1,
        ck2_sea_level=95,
        ck3_water_level=4883,
        ck3_max_level=49205,
        curve=[],
        tile_size=33,
    )
    base.update(kw)
    return HeightmapConfig(**base)  # type: ignore[arg-type]


def canvas(w=64, h=64, factor=2.0, ox=8, oy=8) -> Canvas:
    return Canvas(
        width=w, height=h,
        scaled_width=w - 2 * ox, scaled_height=h - 2 * oy,
        offset_x=ox, offset_y=oy, factor=factor,
    )


# --------------------------------------------------------------------------- #
# the water level
# --------------------------------------------------------------------------- #
def test_water_level_formula_reproduces_vanilla():
    """3 / 50 * 65535 = 3932, the value measured off vanilla's coastline."""
    assert bootstrap.water_level_16bit(waterlevel=3, extents_y=50) == 3932


def test_water_level_formula_reproduces_both_reference_total_conversions():
    """Elder Kings 2 and Godherja both write 3.8 / 51 -> 4883."""
    assert bootstrap.water_level_16bit(waterlevel=3.8, extents_y=51) == 4883


def test_our_defines_and_our_curve_agree_on_the_water_level():
    """The one number that must not drift between two files."""
    assert cfg().ck3_water_level == bootstrap.water_level_16bit()


# --------------------------------------------------------------------------- #
# the curve
# --------------------------------------------------------------------------- #
def test_curve_pins_sea_level_to_the_ck3_water_level():
    lut = heightmap.build_curve(cfg())
    assert lut[95] == 4883


def test_curve_pins_the_endpoints():
    lut = heightmap.build_curve(cfg())
    assert lut[0] == 0
    assert lut[255] == 49205


def test_curve_is_monotonic_so_altitudes_keep_their_order():
    lut = heightmap.build_curve(cfg())
    assert (np.diff(lut.astype(np.int32)) >= 0).all()


def test_curve_is_uint16():
    assert heightmap.build_curve(cfg()).dtype == np.uint16


def test_curve_is_linear_between_the_pinned_points():
    lut = heightmap.build_curve(cfg())
    # halfway between 0 and the sea level
    assert lut[47] == pytest.approx(4883 * 47 / 95, abs=2)


def test_extra_control_points_bend_the_curve():
    plain = heightmap.build_curve(cfg())
    bent = heightmap.build_curve(cfg(curve=[(175, 10000)]))
    assert bent[175] == 10000
    assert bent[175] < plain[175], "the control point should compress mountains"


def test_a_decreasing_curve_is_rejected():
    with pytest.raises(ValueError, match="non-decreasing"):
        heightmap.build_curve(cfg(curve=[(200, 100)]))


def test_every_land_value_is_above_the_water_level():
    lut = heightmap.build_curve(cfg())
    assert (lut[96:] > 4883).all()


def test_every_sea_value_is_at_or_below_the_water_level():
    lut = heightmap.build_curve(cfg())
    assert (lut[:96] <= 4883).all()


# --------------------------------------------------------------------------- #
# target size
# --------------------------------------------------------------------------- #
def test_resolution_factor_one_matches_the_provinces_size():
    """The Elder Kings 2 / Godherja choice."""
    assert heightmap.target_size(canvas(w=8192, h=6656), cfg()) == (8192, 6656)


def test_resolution_factor_two_matches_vanilla():
    assert heightmap.target_size(canvas(w=9216, h=4608), cfg(resolution_factor=2)) == (
        18432, 9216,
    )


def test_resolution_factor_below_one_is_rejected():
    with pytest.raises(ValueError, match="resolution_factor"):
        heightmap.target_size(canvas(), cfg(resolution_factor=0))


# --------------------------------------------------------------------------- #
# build
# --------------------------------------------------------------------------- #
def _topology(tmp_path, arr: np.ndarray):
    p = tmp_path / "topology.bmp"
    Image.fromarray(arr.astype(np.uint8), mode="L").save(p)
    return p


def test_build_returns_uint16_of_the_target_size(tmp_path):
    src = np.full((16, 16), 120, dtype=np.uint8)
    c = canvas()
    out = heightmap.build(_topology(tmp_path, src), c, cfg())
    assert out.dtype == np.uint16
    assert out.shape == (c.height, c.width)


def test_build_fills_the_ocean_margin_at_exactly_the_water_level(tmp_path):
    """The padding province must read as open sea, not as a cliff."""
    src = np.full((16, 16), 200, dtype=np.uint8)
    c = canvas()
    out = heightmap.build(_topology(tmp_path, src), c, cfg())
    assert out[0, 0] == 4883
    assert out[-1, -1] == 4883


def test_build_puts_the_source_inside_the_margin(tmp_path):
    src = np.full((16, 16), 200, dtype=np.uint8)
    c = canvas()
    out = heightmap.build(_topology(tmp_path, src), c, cfg())
    assert out[c.height // 2, c.width // 2] > 4883


def test_build_scales_by_the_resolution_factor(tmp_path):
    src = np.full((16, 16), 120, dtype=np.uint8)
    c = canvas()
    out = heightmap.build(_topology(tmp_path, src), c, cfg(resolution_factor=2))
    assert out.shape == (c.height * 2, c.width * 2)


def test_flat_sea_stays_a_single_value_through_the_resize(tmp_path):
    """LANCZOS runs on the 8-bit source, so flat water does not ripple."""
    src = np.full((16, 16), 95, dtype=np.uint8)
    c = canvas()
    out = heightmap.build(_topology(tmp_path, src), c, cfg())
    assert (out == 4883).all()


# --------------------------------------------------------------------------- #
# write
# --------------------------------------------------------------------------- #
def test_write_png_is_16_bit_and_round_trips(tmp_path):
    arr = np.array([[0, 4883], [30000, 49205]], dtype=np.uint16)
    p = tmp_path / "heightmap.png"
    heightmap.write_png(arr, p)
    with Image.open(p) as im:
        assert im.mode == "I;16"
        assert (np.asarray(im) == arr).all()


def test_write_png_rejects_an_8_bit_array(tmp_path):
    with pytest.raises(ValueError, match="uint16"):
        heightmap.write_png(np.zeros((4, 4), dtype=np.uint8), tmp_path / "h.png")


# --------------------------------------------------------------------------- #
# measuring the source sea level
# --------------------------------------------------------------------------- #
def test_measure_sea_level_finds_the_boundary_between_water_and_land():
    topo = np.array([[30, 30, 40], [100, 110, 120]], dtype=np.uint8)
    ids = np.array([[7, 7, 7], [1, 1, 1]], dtype=np.int32)
    m = heightmap.measure_sea_level(topo, ids, water_ids={7})
    assert m["water_median"] == 30
    assert m["land_median"] == 110
    assert 40 <= m["suggested_sea_level"] <= 100


def test_measure_sea_level_needs_both_land_and_water():
    topo = np.array([[30]], dtype=np.uint8)
    ids = np.array([[7]], dtype=np.int32)
    with pytest.raises(ValueError, match="both water and land"):
        heightmap.measure_sea_level(topo, ids, water_ids={7})


def test_deepen_sea_flattens_the_open_sea_and_keeps_a_shelf():
    """CK2 has no bathymetry and CK3 paints shallow water as sand; vanilla's own
    sea floor is a flat 0 (docs/step_map_heightmap.md)."""
    import numpy as np
    from ck2ck3.map import heightmap

    wl = 4883
    # a 1-pixel island at the centre of a 121x121 sea, all of it just under the surface
    h = np.full((121, 121), wl - 100, dtype=np.uint16)
    h[60, 60] = wl + 5000
    out = heightmap.deepen_sea(h, wl, shelf_px=10, floor=0)

    assert out[60, 60] == wl + 5000, "land must not move"
    assert out[60, 61] < wl, "the pixel next to land stays under water"
    assert out[60, 61] > out[60, 66] > out[0, 0], "depth increases away from the coast"
    assert out[0, 0] == 0, "the open sea sits on the floor"
    assert out.max() == wl + 5000 and out.dtype == h.dtype


def test_deepen_sea_is_a_no_op_without_water():
    import numpy as np
    from ck2ck3.map import heightmap

    h = np.full((8, 8), 20000, dtype=np.uint16)
    assert (heightmap.deepen_sea(h, 4883) == h).all()
