"""Tests for the scale maths and the canvas planner."""

from __future__ import annotations

import math

import pytest

from ck2ck3.map.config import Canvas, ScaleConfig, plan_canvas

# the measured numbers this lane runs with (docs/map_scale.md)
VANILLA_KM_PER_PX = 1.4839


def _scale(**kw) -> ScaleConfig:
    base = dict(
        vanilla_km_per_px=VANILLA_KM_PER_PX,
        source_km_per_px=2.90,
        sea_margin_px=64,
        canvas_multiple=64,
    )
    base.update(kw)
    return ScaleConfig(**base)  # type: ignore[arg-type]


def test_factor_is_the_ratio_of_km_per_pixel():
    """The whole point: 10 km must span the same pixels on both maps."""
    s = _scale(vanilla_km_per_px=1.5, source_km_per_px=3.0)
    assert s.factor == pytest.approx(2.0)


def test_ten_km_spans_the_same_pixels_after_scaling():
    s = _scale()
    km = 10.0
    vanilla_px = km / s.vanilla_km_per_px
    source_px = km / s.source_km_per_px
    assert source_px * s.factor == pytest.approx(vanilla_px)


def test_factor_override_wins():
    s = _scale(factor_override=1.4448)  # the legacy convert.py value, 5918/4096
    assert s.factor == pytest.approx(1.4448)


def test_legacy_factor_implies_a_source_scale_we_can_state():
    """5918/4096 was chosen with no measurement; record what it implies."""
    legacy = 5918 / 4096
    assert legacy == pytest.approx(1.4448, abs=1e-4)
    implied_source_km_per_px = legacy * VANILLA_KM_PER_PX
    assert implied_source_km_per_px == pytest.approx(2.144, abs=1e-3)


def test_canvas_fits_the_scaled_source_plus_margin():
    s = _scale()
    c = plan_canvas(4096, 3328, s)
    assert c.scaled_width == math.ceil(4096 * s.factor)
    assert c.scaled_height == math.ceil(3328 * s.factor)
    assert c.width >= c.scaled_width + 2 * s.sea_margin_px
    assert c.height >= c.scaled_height + 2 * s.sea_margin_px


def test_canvas_dims_are_multiples_of_the_configured_step():
    c = plan_canvas(4096, 3328, _scale())
    assert c.width % 64 == 0
    assert c.height % 64 == 0


def test_canvas_is_the_smallest_such_size():
    """One step smaller on either axis must no longer fit."""
    s = _scale()
    c = plan_canvas(4096, 3328, s)
    assert c.width - 64 < c.scaled_width + 2 * s.sea_margin_px
    assert c.height - 64 < c.scaled_height + 2 * s.sea_margin_px


def test_source_is_centred_so_no_side_loses_margin():
    s = _scale()
    c = plan_canvas(4096, 3328, s)
    assert c.offset_x >= s.sea_margin_px - 1
    assert c.offset_y >= s.sea_margin_px - 1
    assert c.width - (c.offset_x + c.scaled_width) >= s.sea_margin_px - 1
    assert c.height - (c.offset_y + c.scaled_height) >= s.sea_margin_px - 1


def test_faerun_canvas_is_the_documented_size():
    """Regression pin: changing the scale must change this test deliberately."""
    c = plan_canvas(4096, 3328, _scale())
    assert (c.width, c.height) == (8192, 6656)


def test_to_target_maps_the_source_corners_inside_the_canvas():
    c = plan_canvas(4096, 3328, _scale())
    assert c.to_target(0, 0) == (c.offset_x, c.offset_y)
    x, y = c.to_target(4095, 3327)
    assert c.offset_x < x < c.width
    assert c.offset_y < y < c.height


def test_non_positive_factor_is_rejected():
    with pytest.raises(ValueError, match="positive"):
        plan_canvas(100, 100, _scale(factor_override=0.0))


def test_absurd_factor_is_rejected_before_allocating_a_huge_image():
    with pytest.raises(ValueError, match="max_canvas_px"):
        plan_canvas(4096, 3328, _scale(factor_override=20.0, max_canvas_px=32768))


def test_bad_canvas_multiple_is_rejected():
    with pytest.raises(ValueError, match="canvas_multiple"):
        plan_canvas(100, 100, _scale(canvas_multiple=0))


def test_downscaling_still_produces_a_valid_canvas():
    c = plan_canvas(4096, 3328, _scale(factor_override=0.5))
    assert (c.scaled_width, c.scaled_height) == (2048, 1664)
    assert c.width % 64 == 0 and c.height % 64 == 0


def test_canvas_to_target_is_monotonic():
    c = Canvas(
        width=1024, height=1024, scaled_width=900, scaled_height=900,
        offset_x=62, offset_y=62, factor=2.0,
    )
    assert c.to_target(0, 0) == (62, 62)
    assert c.to_target(10, 20) == (82, 102)
