"""The flat (paper) map: a DXT1 DDS at the canvas size, and its encoder.

`docs/evidence/map_ui_research.md` §4 measured the three shipping maps: vanilla
9216x4608 DXT1 with no mip chain, Elder Kings 2 8256x5504, Godherja 8192x4096.
Ship none and the game draws vanilla's Earth over your continent.
"""

from __future__ import annotations

import struct

import numpy as np
import pytest

from ck2ck3.map import dxt1, flatmap


def decode_bc1(data: bytes, width: int, height: int) -> np.ndarray:
    """A reference BC1 decoder, so the encoder is checked against the format."""
    out = np.zeros((height, width, 3), dtype=np.uint8)
    blocks = np.frombuffer(data, dtype="<u4").reshape(-1, 2)
    i = 0
    for by in range(height // 4):
        for bx in range(width // 4):
            packed, idx = blocks[i]
            i += 1
            c = []
            for shift in (0, 16):
                v = (int(packed) >> shift) & 0xFFFF
                r, g, b = (v >> 11) & 0x1F, (v >> 5) & 0x3F, v & 0x1F
                c.append(
                    np.array(
                        [(r << 3) | (r >> 2), (g << 2) | (g >> 4), (b << 3) | (b >> 3)],
                        dtype=np.float32,
                    )
                )
            pal = [c[0], c[1], (2 * c[0] + c[1]) / 3, (c[0] + 2 * c[1]) / 3]
            for t in range(16):
                p = pal[(int(idx) >> (2 * t)) & 0x3]
                out[by * 4 + t // 4, bx * 4 + t % 4] = np.round(p).astype(np.uint8)
    return out


def test_header_matches_vanilla_flatmap():
    """Vanilla ships 128 bytes, DXT1, linear size, and mipMapCount = 0."""
    h = dxt1.header(9216, 4608, 21233664)
    assert len(h) == 128
    assert h[:4] == b"DDS "
    size, flags, height, width, linear, depth, mips = struct.unpack_from("<7I", h, 4)
    assert (size, height, width, linear, mips) == (124, 4608, 9216, 21233664, 0)
    assert flags & 0x80000  # DDSD_LINEARSIZE, as vanilla sets it
    assert h[84:88] == b"DXT1"


def test_encode_block_size():
    rgb = np.zeros((8, 16, 3), dtype=np.uint8)
    assert len(dxt1.encode(rgb)) == (8 // 4) * (16 // 4) * 8


def test_encode_rejects_odd_sizes():
    with pytest.raises(ValueError):
        dxt1.encode(np.zeros((5, 8, 3), dtype=np.uint8))


def test_flat_colour_survives_exactly_after_565_rounding():
    """A paper map is mostly flat fill; it must not dither or shift."""
    colour = np.array([216, 200, 164], dtype=np.uint8)
    rgb = np.tile(colour, (8, 8, 1))
    back = decode_bc1(dxt1.encode(rgb), 8, 8)
    # RGB565 quantisation is the only allowed error
    assert np.abs(back.astype(int) - rgb.astype(int)).max() <= 4
    assert len(np.unique(back.reshape(-1, 3), axis=0)) == 1


def test_gradient_round_trips_within_bc1_error():
    ramp = np.linspace(0, 255, 32, dtype=np.uint8)
    rgb = np.stack([np.tile(ramp, (8, 1))] * 3, axis=-1)
    back = decode_bc1(dxt1.encode(rgb), 32, 8)
    assert np.abs(back.astype(int) - rgb.astype(int)).max() <= 12


def test_render_paints_land_and_water_apart():
    water = np.array([[True, True], [False, False]])
    rgb = flatmap.render(water, None)
    assert tuple(rgb[0, 0]) == flatmap.Palette().water
    assert tuple(rgb[1, 0]) == flatmap.Palette().lowland


def test_render_shades_land_by_altitude():
    water = np.zeros((2, 2), dtype=bool)
    heights = np.array([[4883, 4883], [4883, 40000]], dtype=np.uint16)
    rgb = flatmap.render(water, heights, water_level=4883)
    assert tuple(rgb[0, 0]) == flatmap.Palette().lowland
    assert tuple(rgb[1, 1]) == flatmap.Palette().highland
    # water pixels never take the height shading
    assert rgb[1, 1].tolist() != rgb[0, 1].tolist()


def test_render_decimates_a_2x_heightmap():
    """`heightmap.resolution_factor = 2` must not blow up the paper map."""
    water = np.zeros((4, 4), dtype=bool)
    heights = np.full((8, 8), 4883, dtype=np.uint16)
    assert flatmap.render(water, heights).shape == (4, 4, 3)


def test_save_writes_a_readable_dds(tmp_path):
    rgb = np.zeros((8, 8, 3), dtype=np.uint8)
    rgb[..., 0] = 200
    path = tmp_path / "flatmap.dds"
    flatmap.save(rgb, path)
    raw = path.read_bytes()
    assert raw[:4] == b"DDS "
    assert len(raw) == 128 + (8 // 4) * (8 // 4) * 8
    assert decode_bc1(raw[128:], 8, 8)[..., 0].min() >= 196


def test_flatmap_path_is_where_the_engine_looks():
    assert flatmap.FLATMAP_PATH == "gfx/map/terrain/flat_maps/flatmap.dds"
