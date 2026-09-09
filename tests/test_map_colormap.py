"""Tests for gfx/map/terrain/colormap.dds: measured terrain tint + DDS writer.

Format `verified` against two shipped, loadable CK3 total conversions (Elder
Kings 2, Godherja): uncompressed A8R8G8B8, quarter province-map resolution,
alpha = 255. See ``ck2ck3.map.colormap`` module docstring for the byte-level
evidence, and for why this lane (`colormap-fix`) replaced a CK2-colormap
resample (`docs/step_map_paint.md` §9.6) with a tint measured from vanilla's
own `colormap.dds`/`detail_index.tga` pair.
"""

from __future__ import annotations

import csv
import struct
from pathlib import Path

import numpy as np
from PIL import Image

from ck2ck3.map import colormap

REPO = Path(__file__).resolve().parents[1]


def test_read_tint_map_parses_rows_and_skips_comments(tmp_path):
    p = tmp_path / "tints.csv"
    p.write_text(
        "# a comment line\n"
        "ck3_terrain,tint_r,tint_g,tint_b,sample_count,note\n"
        "plains,127,127,126,13019,some note\n"
        "water,129,130,129,8041139,another note\n",
        encoding="utf-8",
    )
    m = colormap.read_tint_map(p)
    assert m == {"plains": (127, 127, 126), "water": (129, 130, 129)}


def test_read_tint_map_missing_file_is_not_an_error(tmp_path):
    assert colormap.read_tint_map(tmp_path / "nope.csv") == {}


def test_build_from_terrain_paints_by_ck3_key_via_lut():
    # two CK2 categories -> two CK3 keys via an explicit mapping override
    codes = np.array([[0, 1], [1, 0]], dtype=np.uint8)
    code_names = ["plains_cat", "forest_cat"]
    mapping = {"plains_cat": "plains", "forest_cat": "forest"}
    tint_map = {"plains": (10, 20, 30), "forest": (40, 50, 60), "water": (0, 0, 0)}
    water_mask = np.zeros((2, 2), dtype=bool)

    out = colormap.build_from_terrain(
        codes, code_names, tint_map=tint_map, water_mask=water_mask,
        mapping=mapping, blur_sigma=0,
    )
    assert out.dtype == np.uint8
    assert tuple(out[0, 0]) == (10, 20, 30)
    assert tuple(out[1, 1]) == (10, 20, 30)
    assert tuple(out[0, 1]) == (40, 50, 60)
    assert tuple(out[1, 0]) == (40, 50, 60)


def test_build_from_terrain_water_mask_overrides_terrain_key():
    # every pixel maps to "plains", but the whole grid is marked water
    codes = np.zeros((3, 3), dtype=np.uint8)
    code_names = ["plains_cat"]
    mapping = {"plains_cat": "plains"}
    tint_map = {"plains": (200, 10, 10), "water": (1, 2, 3)}
    water_mask = np.ones((3, 3), dtype=bool)

    out = colormap.build_from_terrain(
        codes, code_names, tint_map=tint_map, water_mask=water_mask,
        mapping=mapping, blur_sigma=0,
    )
    assert (out == np.array([1, 2, 3], dtype=np.uint8)).all()


def test_build_from_terrain_missing_key_falls_back_to_default_and_is_reported():
    codes = np.zeros((2, 2), dtype=np.uint8)
    code_names = ["mystery_cat"]
    mapping = {"mystery_cat": "no_such_ck3_key"}
    tint_map = {"plains": (5, 6, 7)}
    warnings: list[str] = []

    out = colormap.build_from_terrain(
        codes, code_names, tint_map=tint_map,
        water_mask=np.zeros((2, 2), dtype=bool),
        mapping=mapping, default="plains", blur_sigma=0, warn=warnings.append,
    )
    assert (out == np.array([5, 6, 7], dtype=np.uint8)).all()
    assert any("no_such_ck3_key" in w for w in warnings)


def test_build_from_terrain_blur_smooths_the_boundary():
    codes = np.zeros((20, 20), dtype=np.uint8)
    codes[:, 10:] = 1
    code_names = ["a", "b"]
    mapping = {"a": "plains", "b": "forest"}
    tint_map = {"plains": (0, 0, 0), "forest": (200, 200, 200)}
    water_mask = np.zeros((20, 20), dtype=bool)

    out = colormap.build_from_terrain(
        codes, code_names, tint_map=tint_map, water_mask=water_mask,
        mapping=mapping, blur_sigma=2.0,
    )
    # a pixel right at the boundary is no longer a pure class colour
    boundary = int(out[10, 10, 0])
    assert 0 < boundary < 200
    # far from the boundary, the blur has not reached and colours stay pure
    assert tuple(out[10, 0]) == (0, 0, 0)
    assert tuple(out[10, 19]) == (200, 200, 200)


def _weighted_mean_saturation(rows: list[dict], r_key: str, g_key: str, b_key: str, n_key: str) -> float:
    total_n = sum(int(row[n_key]) for row in rows)
    total = 0.0
    for row in rows:
        rgb = (float(row[r_key]), float(row[g_key]), float(row[b_key]))
        total += (max(rgb) - min(rgb)) * int(row[n_key])
    return total / total_n


def test_our_land_tints_do_not_exceed_vanillas_own_saturation_by_much():
    """Regression guard: `mappings/colormap_tints.csv` land rows vs. vanilla.

    Every land tint in our table *is* one of vanilla's own measured material
    means (`scripts/build_colormap_tints_csv.py`), so this should already
    hold by construction; this test exists to catch a future edit (a
    hand-picked, more saturated colour; a broken measurement script) rather
    than to prove today's numbers. Margin: 3 (max-min channel units) over
    vanilla's own sample-count-weighted mean saturation across every material
    it actually paints — vanilla's own materials span roughly 0.85 (water) to
    ~19 (its most saturated desert material), so 3 is a small fraction of
    that range, not a rubber stamp.
    """
    with (REPO / "docs" / "evidence" / "vanilla_colormap_tints.csv").open(
        encoding="utf-8", newline=""
    ) as fh:
        vanilla_rows = list(csv.DictReader(fh))
    vanilla_land = [r for r in vanilla_rows if not r["material_name"].startswith("water")]
    vanilla_sat = _weighted_mean_saturation(
        vanilla_land, "mean_r", "mean_g", "mean_b", "sample_count"
    )

    with (REPO / "mappings" / "colormap_tints.csv").open(encoding="utf-8", newline="") as fh:
        our_rows = list(csv.DictReader(fh))
    our_land = [r for r in our_rows if r["ck3_terrain"] != "water"]
    our_sat = _weighted_mean_saturation(our_land, "tint_r", "tint_g", "tint_b", "sample_count")

    margin = 3.0
    assert our_sat <= vanilla_sat + margin, (
        f"our land tints average saturation {our_sat:.2f} exceeds vanilla's "
        f"own {vanilla_sat:.2f} by more than {margin}"
    )


def test_downsample_shape_and_identity_at_scale_one():
    rgb = np.random.default_rng(0).integers(0, 255, (16, 12, 3), dtype=np.uint8)
    assert colormap.downsample(rgb, 1.0) is rgb
    small = colormap.downsample(rgb, 0.25)
    assert small.shape == (4, 3, 3)


def test_header_matches_reference_mod_bytes_no_mips():
    """Byte-for-byte the Elder Kings 2 colormap.dds header (base level only)."""
    h = colormap.header(2064, 1376, mips=1)
    assert len(h) == 128
    assert h[:4] == b"DDS "
    size, flags, height, width, pitch, depth, mips = struct.unpack_from("<7I", h, 4)
    assert (size, height, width, pitch, depth, mips) == (
        124,
        1376,
        2064,
        2064 * 4,
        0,
        0,
    )
    assert flags == 0x0000100F  # verified against the shipped EK2 file
    pf_size, pf_flags = struct.unpack_from("<2I", h, 76)
    assert (pf_size, pf_flags) == (32, 0x41)
    fourcc, bitcount = struct.unpack_from("<2I", h, 84)
    assert (fourcc, bitcount) == (0, 32)
    r, g, b, a = struct.unpack_from("<4I", h, 92)
    assert (r, g, b, a) == (0x00FF0000, 0x0000FF00, 0x000000FF, 0xFF000000)
    (caps,) = struct.unpack_from("<I", h, 108)
    assert caps == 0x1000  # DDSCAPS_TEXTURE, no mip flags


def test_header_sets_mipmap_flags_when_chained():
    """Byte-for-byte the Godherja colormap.dds header's flag/caps fields."""
    h = colormap.header(2048, 1024, mips=12)
    _, flags, _, _, _, _, mips = struct.unpack_from("<7I", h, 4)
    assert flags == 0x0002100F
    assert mips == 12
    (caps,) = struct.unpack_from("<I", h, 108)
    assert caps == 0x00401008  # COMPLEX | TEXTURE | MIPMAP


def test_save_round_trips_base_level_via_pil(tmp_path):
    rgb = np.zeros((8, 8, 3), dtype=np.uint8)
    rgb[:4] = (10, 20, 30)
    rgb[4:] = (200, 150, 100)
    out = tmp_path / "colormap.dds"
    colormap.save(rgb, out, mips=False)

    with Image.open(out) as im:
        assert im.size == (8, 8)
        back = np.asarray(im.convert("RGBA"))
    assert np.array_equal(back[..., :3], rgb)
    assert (back[..., 3] == 255).all()


def test_save_with_mips_writes_full_chain_bytes(tmp_path):
    rgb = np.full((8, 8, 3), 100, dtype=np.uint8)
    out = tmp_path / "colormap.dds"
    colormap.save(rgb, out, mips=True)
    data = out.read_bytes()
    # 8x8 + 4x4 + 2x2 + 1x1 = 64+16+4+1 = 85 pixels, 4 bytes each
    assert len(data) == 128 + 85 * 4
    _, _, _, _, _, _, mips = struct.unpack_from("<7I", data, 4)
    assert mips == 4
