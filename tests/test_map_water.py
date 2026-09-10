"""Tests for the whole-map water rasters (``ck2ck3.map.water``).

The bug these files fix is the build-13 playtest's "when zooming in the water,
the map of Europe appears": three textures are sampled at a whole-map UV, so
shipping none leaves vanilla's Earth painted under our sea
(`docs/step_map_water_border.md`).  What the tests pin is that our
replacements are *derived from our own coastline*, in the format both shipped
total conversions use.
"""

from __future__ import annotations

import struct
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from ck2ck3.map import water

REPO = Path(__file__).resolve().parents[1]
PROFILE_CSV = REPO / "mappings" / "water_profile.csv"

FIXTURE_CSV = """\
# a comment block, like every mappings/*.csv may carry
zone,depth_px,n,wc_r,wc_g,wc_b,wc_a,foam_r,foam_g
water,2,10,45,72,73,55,78,31
water,8,10,43,79,81,67,79,82
water,64,10,26,58,60,75,20,252
land,2,10,39,64,65,61,75,5
land,64,10,60,67,63,71,71,0
"""


@pytest.fixture()
def profile(tmp_path):
    p = tmp_path / "water_profile.csv"
    p.write_text(FIXTURE_CSV, encoding="utf-8")
    return water.read_water_profile(p)


def _sea_strip(width=64, height=16, coast=32):
    """Land on the left, sea from column ``coast`` on."""
    mask = np.zeros((height, width), dtype=bool)
    mask[:, coast:] = True
    return mask


def test_read_water_profile_skips_comments_and_sorts(profile):
    assert set(profile) == {"water", "land"}
    assert [r.depth_px for r in profile["water"]] == [2, 8, 64]
    assert profile["water"][0].wc == (45, 72, 73, 55)
    assert profile["water"][0].foam == (78, 31)


def test_read_water_profile_missing_file_is_not_an_error(tmp_path):
    assert water.read_water_profile(tmp_path / "nope.csv") == {}


def test_coast_distance_is_zero_outside_its_own_zone():
    mask = _sea_strip()
    into_water, into_land = water.coast_distance(mask)
    assert into_water[0, 0] == 0
    assert into_land[0, 63] == 0
    assert into_water[0, 32] == pytest.approx(1.0)
    assert into_land[0, 31] == pytest.approx(1.0)


def test_watercolor_follows_our_coast_not_vanillas(profile):
    mask = _sea_strip()
    out = water.build_watercolor(mask, profile=profile, px_per_texel=2.0)
    assert out.shape == (16, 64, 4)
    assert out.dtype == np.uint8
    # the shelf at the shoreline is lighter and less glossy than the deep sea
    shelf = out[0, 32]
    deep = out[0, 63]
    assert shelf[1] > deep[1], "shelf green must exceed open-water green"
    assert shelf[3] < deep[3], "gloss rises with depth in vanilla's own data"
    # land takes the land ramp, not the water one
    assert tuple(out[0, 0])[:3] != tuple(deep)[:3]


def test_watercolor_without_a_table_is_still_blue(tmp_path):
    mask = _sea_strip()
    out = water.build_watercolor(mask, profile={})
    assert tuple(out[0, 63]) == water.FALLBACK_WATER
    assert tuple(out[0, 0]) == water.FALLBACK_LAND


def test_foam_map_channels_match_vanillas_semantics(profile):
    mask = _sea_strip()
    out = water.build_foam_map(mask, profile=profile, px_per_texel=2.0)
    # R is the foam allowance: the shader reads 1 - R, so high R is foam
    assert out[0, 32, 0] > out[0, 63, 0]
    # G is the water mask, feathered at the shore and saturated offshore
    assert out[0, 0, 1] < 20 < out[0, 63, 1]
    # B and A are constant across the whole of vanilla's raster
    assert set(np.unique(out[..., 2])) == {water.FOAM_B_CONST}
    assert set(np.unique(out[..., 3])) == {water.FOAM_A_CONST}


def test_profile_depth_is_in_canvas_pixels_not_texels(profile):
    """Halving the raster scale must not halve the shelf's ground width."""
    mask = _sea_strip(width=128, height=8, coast=64)
    half = water.build_watercolor(mask, profile=profile, px_per_texel=2.0)
    # the same coastline sampled at a coarser raster: one texel is 4 canvas px
    coarse_mask = mask[::2, ::2]
    coarse = water.build_watercolor(coarse_mask, profile=profile,
                                    px_per_texel=4.0)
    # A point ~10 canvas px into the water is the same colour in both, up to
    # the one-texel offset the distance transform starts each zone at (the
    # first water pixel is at distance 1, which is 2 canvas px on one grid and
    # 4 on the other).
    assert np.abs(
        half[0, 64 + 4].astype(int) - coarse[0, 32 + 2].astype(int)
    ).max() <= 2


def test_snow_mask_is_flat_red_with_noise_channels():
    out = water.build_snow_mask((8, 12))
    assert out.shape == (8, 12, 4)
    assert set(np.unique(out[..., 0])) == {0}, "R = 0 hands snow to the engine"
    # G/B/A fall back to vanilla's measured global means with no install
    assert tuple(out[0, 0, 1:]) == water.FALLBACK_SNOW_NOISE


def test_snow_mask_no_snow_is_clamped_to_a_byte():
    assert water.build_snow_mask((4, 4), no_snow=999)[0, 0, 0] == 255
    assert water.build_snow_mask((4, 4), no_snow=-5)[0, 0, 0] == 0


def test_save_keeps_the_alpha_channel(tmp_path):
    """The water colour map's alpha is its gloss, not padding."""
    rgba = np.zeros((4, 4, 4), dtype=np.uint8)
    rgba[..., 0], rgba[..., 3] = 10, 77
    out = tmp_path / "w.dds"
    water.save(rgba, out)
    raw = out.read_bytes()
    assert raw[:4] == b"DDS "
    height, width = struct.unpack_from("<2I", raw, 12)
    assert (width, height) == (4, 4)
    with Image.open(out) as im:
        back = np.asarray(im.convert("RGBA"))
    assert back[0, 0, 0] == 10
    assert back[0, 0, 3] == 77


def test_downsample_shape_and_identity_at_scale_one():
    rgba = np.zeros((16, 32, 4), dtype=np.uint8)
    assert water.downsample(rgba, 1.0) is rgba
    assert water.downsample(rgba, 0.5).shape == (8, 16, 4)


def test_shipped_profile_table_is_readable_and_monotone_in_gloss():
    """The checked-in measurement, not a fixture: vanilla's own numbers."""
    profile = water.read_water_profile(PROFILE_CSV)
    assert len(profile["water"]) > 50
    assert len(profile["land"]) > 20
    shallow = profile["water"][0]
    deep = profile["water"][-1]
    assert shallow.depth_px == 2
    assert shallow.foam[0] > deep.foam[0], "foam is a shore effect"
    assert shallow.foam[1] < deep.foam[1], "the water mask feathers inward"
    assert shallow.wc[3] < deep.wc[3], "gloss rises away from the coast"


def test_cli_config_builder_reads_the_keys():
    """A `[map] water*` key the REAL CLI builder never reads is a silent
    no-op — the `[map] colormap = false` bug, a third time."""
    from ck2ck3.steps import map as map_step

    keys = {
        "water": False,
        "water_scale": 0.25,
        "water_foam_scale": 0.125,
        "snow_mask_scale": 0.5,
        "snow_mask_no_snow": 200,
        "surround_mask": False,
        "surround_scale": 0.25,
        "water_profile_csv": "mappings/other_water.csv",
        "surround_profile_csv": "mappings/other_surround.csv",
    }

    class Cfg:
        raw = {"map": {"vanilla_km_per_px": 1.0, "source_km_per_px": 1.0,
                       **keys}}
        path = Path("configs/x.toml")
        out = Path("/tmp/out")
        prefix = "fae"
        bookmark_date = (1357, 1, 1)
        name = "n"
        version = "0"
        supported_version = "1.19.*"

    class Ctx:
        config = Cfg()

        def ck2(self, *parts):
            return Path("/tmp/ck2").joinpath(*parts)

        def ck3(self, *parts):
            return Path("/tmp/ck3").joinpath(*parts)

    cfg = map_step._map_config(Ctx())
    assert cfg.water is False
    assert cfg.water_scale == 0.25
    assert cfg.water_foam_scale == 0.125
    assert cfg.snow_mask_scale == 0.5
    assert cfg.snow_mask_no_snow == 200
    assert cfg.surround_mask is False
    assert cfg.surround_scale == 0.25
    assert cfg.water_profile_csv == Path("mappings/other_water.csv")
    assert cfg.surround_profile_csv == Path("mappings/other_surround.csv")

    for k in keys:
        Cfg.raw["map"].pop(k)
    cfg = map_step._map_config(Ctx())
    assert cfg.water is True
    assert cfg.surround_mask is True
    assert cfg.water_scale == 0.5
    assert cfg.water_foam_scale == 0.25
    assert cfg.snow_mask_scale == 0.25
    assert cfg.snow_mask_no_snow == 0
    assert cfg.surround_scale == 0.5
    assert cfg.water_profile_csv == Path("mappings/water_profile.csv")
    assert cfg.surround_profile_csv == Path("mappings/surround_profile.csv")
