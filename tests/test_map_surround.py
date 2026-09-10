"""Tests for ``gfx/map/surround_map/surround_mask.dds`` (``ck2ck3.map.surround``).

The build-13 playtest: "the map border is broken at the top — probably to hide
northern Siberia in vanilla, but here it hides real content."  Vanilla's mask
is painted around Earth and its B channel makes the terrain transparent
(``pdxterrain.shader:777``) and clips the political borders
(``pdxborder.shader:115``).  These tests pin that our replacement frames all
four edges evenly and leaves the whole map visible.
"""

from __future__ import annotations

import struct
from pathlib import Path

import numpy as np

from ck2ck3.map import surround

REPO = Path(__file__).resolve().parents[1]
PROFILE_CSV = REPO / "mappings" / "surround_profile.csv"

FIXTURE_CSV = """\
# a comment block, like every mappings/*.csv may carry
depth,r,g,b
0,145,244,255
1,150,240,200
2,150,200,0
3,120,80,0
4,0,0,0
"""


def _fixture_profile(tmp_path):
    p = tmp_path / "surround_profile.csv"
    p.write_text(FIXTURE_CSV, encoding="utf-8")
    return surround.read_profile(p)


def test_read_profile_skips_comments_and_indexes_by_depth(tmp_path):
    profile = _fixture_profile(tmp_path)
    assert profile.shape == (5, 3)
    assert tuple(profile[0]) == (145, 244, 255)
    assert tuple(profile[2]) == (150, 200, 0)


def test_read_profile_missing_file_leaves_the_map_visible(tmp_path):
    """A missing table must not silently hide the map — that is the bug."""
    profile = surround.read_profile(tmp_path / "nope.csv")
    mask = surround.build(16, 12, profile)
    assert mask.max() == 0


def test_edge_depth_is_the_distance_to_the_nearest_of_four_edges():
    depth = surround.edge_depth(9, 7)
    assert depth[0, 0] == 0
    assert depth[3, 4] == 3  # centre of a 9x7 grid
    assert depth[0, 4] == 0
    assert depth[3, 0] == 0
    assert depth[1, 1] == 1
    assert depth[6, 8] == 0


def test_build_frames_all_four_edges_and_clears_the_middle(tmp_path):
    profile = _fixture_profile(tmp_path)
    mask = surround.build(32, 24, profile)
    assert mask.shape == (24, 32, 3)
    for y, x in ((0, 0), (0, 31), (23, 0), (23, 31), (0, 16), (12, 0)):
        assert tuple(mask[y, x]) == (145, 244, 255)
    # B, the channel that hides the terrain, is clear from depth 2 in
    assert mask[2, 16, 2] == 0
    assert mask[12, 16, 2] == 0
    # and past the profile everything is clear
    assert tuple(mask[12, 16]) == (0, 0, 0)


def test_build_is_symmetric_top_to_bottom(tmp_path):
    """Vanilla's own mask is not — that asymmetry is the reported bug."""
    mask = surround.build(40, 30, _fixture_profile(tmp_path))
    assert np.array_equal(mask[0], mask[-1])
    assert np.array_equal(mask[:, 0], mask[:, -1])


def test_save_writes_a_dxt1_dds_at_the_asked_size(tmp_path):
    mask = surround.build(16, 8, _fixture_profile(tmp_path))
    out = tmp_path / "surround_mask.dds"
    surround.save(mask, out)
    raw = out.read_bytes()
    assert raw[:4] == b"DDS "
    height, width = struct.unpack_from("<2I", raw, 12)
    assert (width, height) == (16, 8)
    assert raw[84:88] == b"DXT1", "vanilla's own format for this file"


def test_shipped_profile_fits_inside_the_sea_margin():
    """The frame must not reach land: our canvas has a 128 px sea margin.

    The profile is in texels of a half-canvas raster, so 128 canvas px is 64
    texels (`docs/map_scale.md` §7, `configs/faerun.toml` sea_margin_px).
    """
    profile = surround.read_profile(PROFILE_CSV)
    assert 1 < len(profile) <= 64
    # B, the channel that hides terrain and clips borders, must clear first
    b_zero = int(np.argmax(profile[:, 2] == 0))
    assert 0 < b_zero <= 16, f"terrain hidden {b_zero} texels in"
    assert tuple(profile[-1]) != (0, 0, 0) or len(profile) == 1
    assert profile[0, 2] == 255, "the outermost texel is fully framed"
