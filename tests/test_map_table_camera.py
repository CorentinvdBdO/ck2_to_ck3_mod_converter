"""The 3D map table and the camera bound — both pure data on a custom canvas.

Fixtures are verbatim vanilla CK3 1.19:
`game/gfx/map/map_object_data/map_table_western.txt` and the `NCamera` keys of
`game/common/defines/graphic/00_graphics.txt`.
"""

from __future__ import annotations

import re

import pytest

from ck2ck3.map import bootstrap, table

VANILLA_WESTERN = """\
object={
\tname="western_tabletop"
\trender_pass=MapUnderTerrain
\tclamp_to_water_level=yes
\tgenerated_content=no
\tlayer="map_table_layer_western"
\tentity="tabletop_west_basic_entity"
\tcount=1
\ttransform="4500.000000 -15.000000 2560.000000 0.000000 0.000000 0.000000 0.000000 5.000000 5.000000 5.000000
"}
object={
\tname="western_tabletop_cloth"
\trender_pass=MapUnderTerrain
\tclamp_to_water_level=yes
\tgenerated_content=no
\tlayer="map_table_layer_western"
\tentity="tabletop_west_basic_tablecloth_entity"
\tcount=1
\ttransform="4500.000000 -20.000000 2560.000000 0.000000 0.000000 0.000000 0.000000 5.000000 5.000000 5.000000
"}
"""


def transforms(text: str) -> list[list[float]]:
    return [
        [float(v) for v in m.group(1).split()]
        for m in re.finditer(r'transform="([^"]*)"', text, re.S)
    ]


# ------------------------------------------------------------------- table
def test_scale_factor_is_the_larger_axis_ratio():
    assert table.scale_factor(9216, 4608) == 1.0
    assert table.scale_factor(8320, 6784) == pytest.approx(6784 / 4608)
    assert table.scale_factor(8192, 4096) == pytest.approx(8192 / 9216)


def test_vanilla_canvas_is_a_no_op():
    out = table.render_table_file(VANILLA_WESTERN, width=9216, height=4608)
    assert transforms(out) == transforms(VANILLA_WESTERN)


def test_table_is_recentred_and_grown_for_a_tall_canvas():
    out = table.render_table_file(VANILLA_WESTERN, width=8320, height=6784)
    k = 6784 / 4608
    first = transforms(out)[0]
    assert first[0] == pytest.approx(8320 / 2 + (4500 - 4608) * k)
    assert first[2] == pytest.approx(6784 / 2 + (2560 - 2304) * k)
    assert first[7:] == pytest.approx([5 * k] * 3)


def test_y_offsets_and_rotation_are_untouched():
    """They set the stacking order of table, cloth, candles and props."""
    out = transforms(table.render_table_file(VANILLA_WESTERN, width=8320, height=6784))
    assert [t[1] for t in out] == [-15.0, -20.0]
    assert all(t[3:7] == [0.0, 0.0, 0.0, 0.0] for t in out)


def test_everything_but_the_transform_is_passed_through():
    out = table.render_table_file(VANILLA_WESTERN, width=8320, height=6784)
    for line in ('entity="tabletop_west_basic_entity"', "render_pass=MapUnderTerrain",
                 'layer="map_table_layer_western"', "count=1"):
        assert line in out
    assert out.count("object={") == 2


def test_no_game_dir_means_no_table_files():
    """A run without the CK3 install must not crash; the caller warns."""
    assert table.render_all(None, width=8320, height=6784) == {}


# ------------------------------------------------------------------ camera
def test_camera_defines_follow_the_canvas():
    text = bootstrap.render_camera_defines(width=8320, height=6784)
    assert "NCamera = {" in text
    assert "PANNING_WIDTH = 8320" in text
    assert "PANNING_HEIGHT = 6784" in text


def test_start_look_at_is_the_canvas_centre():
    text = bootstrap.render_camera_defines(width=8320, height=6784)
    assert "START_LOOK_AT = { 4160.0 0 3392.0 }" in text


def test_world_extents_and_camera_stay_in_separate_blocks():
    """Vanilla keeps NJominiMap and NCamera apart; so do both reference TCs."""
    extents = bootstrap.render_defines(width=8320, height=6784)
    assert "NJominiMap = {" in extents
    assert "NCamera" not in extents
