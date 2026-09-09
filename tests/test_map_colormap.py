"""Tests for gfx/map/terrain/colormap.dds: CK2 colour resample + DDS writer.

Format `verified` against two shipped, loadable CK3 total conversions (Elder
Kings 2, Godherja): uncompressed A8R8G8B8, quarter province-map resolution,
alpha = 255. See ``ck2ck3.map.colormap`` module docstring for the byte-level
evidence.
"""

from __future__ import annotations

import struct

import numpy as np
from PIL import Image

from ck2ck3.map import colormap
from ck2ck3.map.config import Canvas


def _canvas(**kw) -> Canvas:
    base = dict(
        width=16,
        height=16,
        scaled_width=8,
        scaled_height=8,
        offset_x=4,
        offset_y=4,
        factor=2.0,
        crop_x0=0,
        crop_y0=0,
        crop_x1=4,
        crop_y1=4,
    )
    base.update(kw)
    return Canvas(**base)


def _write_ck2_colormap(path, arr: np.ndarray) -> None:
    """A minimal, uncompressed-enough source colormap for PIL to read back.

    Saved as PNG then reopened as if it were the CK2 asset: ``render`` only
    needs ``Image.open(...).convert("RGB")``, so a PNG stand-in exercises the
    same code path without a DXT1 encoder in the test.
    """
    Image.fromarray(arr).save(path)


def test_render_places_source_at_offset_and_fills_margin(tmp_path):
    # 4x4 source, left half red, right half green -> resampled to 8x8, pasted
    # at (4, 4) on a 16x16 canvas filled with a distinct margin colour.
    src = np.zeros((4, 4, 3), dtype=np.uint8)
    src[:, :2] = (255, 0, 0)
    src[:, 2:] = (0, 255, 0)
    p = tmp_path / "colormap.png"
    _write_ck2_colormap(p, src)

    canvas = _canvas()
    out = colormap.render(p, canvas, margin_rgb=(1, 2, 3))
    assert out.shape == (16, 16, 3)

    # corners are untouched margin
    assert tuple(out[0, 0]) == (1, 2, 3)
    assert tuple(out[15, 15]) == (1, 2, 3)
    # inside the pasted region: left half red-ish, right half green-ish
    assert out[8, 5][0] > out[8, 5][1]  # red channel dominant on the left
    assert out[8, 10][1] > out[8, 10][0]  # green channel dominant on the right


def test_render_rescales_crop_when_source_size_differs(tmp_path):
    """A colormap not pixel-aligned with provinces.bmp still resamples right."""
    # source colormap is 8x8 (double the "provinces.bmp" resolution assumed
    # by the canvas' crop box, which is in provinces.bmp pixels)
    src = np.zeros((8, 8, 3), dtype=np.uint8)
    src[:4] = (255, 0, 0)
    src[4:] = (0, 0, 255)
    p = tmp_path / "colormap.png"
    _write_ck2_colormap(p, src)

    canvas = _canvas(crop_x0=0, crop_y0=0, crop_x1=4, crop_y1=4)
    out = colormap.render(p, canvas, source_size=(4, 4))
    assert out.shape == (16, 16, 3)
    # crop should have been rescaled 2x into the 8x8 source's own space,
    # i.e. the whole 8x8 source is used, not just its top-left quadrant
    assert out[5, 8][2] == 0  # top rows: red, no blue
    assert out[10, 8][0] == 0  # bottom rows: blue, no red


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
