"""Tests for the CK3 packed-heightmap codec (``ck2ck3.map.packed_heightmap``).

Pure numpy, no game files, no images larger than a few hundred pixels.  The
error bounds asserted here are the ones documented in
``docs/formats_packed_heightmap.md``:

* a level-0 tile's **interior** round-trips exactly (verified on all three real
  maps: 1063/5521/11371 level-0 tiles, 100% of interior pixels exact);
* everything else is bounded by the encoder's level threshold
  ``LEVEL_MAX_ERROR`` plus one rounding unit, except the one-pixel lines shared
  with a *coarser* neighbour, which the format deliberately resamples at the
  neighbour's level.
"""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from ck2ck3.map.packed_heightmap import (
    LEVEL_MAX_ERROR,
    decode_arrays,
    decode_packed,
    parse_descriptor,
    read_descriptor,
    write_packed,
)

VANILLA_DESCRIPTOR = (
    'heightmap_file="map_data/packed_heightmap.png"\n'
    'indirection_file="map_data/indirection_heightmap.png"\n'
    "original_heightmap_size={ 18432 9216 }\n"
    "tile_size=65\n"
    "should_wrap_x=no\n"
    "level_offsets={ { 0 0 } { 0 1397 } { 0 3129 } { 0 3690 } { 0 3861 } }\n"
    "max_compress_level=4\n"
    "empty_tile_offset={ 225 39 }\n"
)


def synthetic_heightmap(h: int = 256, w: int = 320) -> np.ndarray:
    """Gradient + flat ocean block + noisy mountain block, like a real map."""
    yy, xx = np.mgrid[0:h, 0:w]
    hm = (2000 + yy * 40 + xx * 30).astype(np.int64)
    hm[0:64, 0:96] = 0  # flat ocean -> should compress to the top level
    rng = np.random.default_rng(1234)
    hm[128:192, 160:288] = 30000 + rng.integers(0, 9000, (64, 128))  # mountains
    return hm.clip(0, 65535).astype(np.uint16)


def border_mask(shape: tuple[int, int], stride: int) -> np.ndarray:
    """Bottom-up mask of the one-pixel lines shared between tiles."""
    mask = np.zeros(shape, dtype=bool)
    mask[::stride, :] = True
    mask[:, ::stride] = True
    mask[-1, :] = True
    mask[:, -1] = True
    return mask


# --------------------------------------------------------------------------- #
# round-trip
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("tile_size", [33, 65])
def test_round_trip_bounded(tmp_path, tile_size):
    hm = synthetic_heightmap()
    meta = write_packed(hm, tmp_path, tile_size=tile_size)
    back, desc = decode_packed(tmp_path)

    assert back.shape == hm.shape
    assert back.dtype == np.uint16
    assert desc.tile_size == tile_size
    assert desc.original_heightmap_size == (hm.shape[1], hm.shape[0])

    err = np.abs(back.astype(np.int64) - hm.astype(np.int64))
    # write_packed's self-check must agree with an independent decode
    assert meta["max_abs_error"] == int(err.max())
    assert meta["exact_fraction"] == pytest.approx(float((err == 0).mean()))

    levels = np.array(Image.open(tmp_path / "indirection_heightmap.png"))[::-1][:, :, 3]
    err_bu = err[::-1]
    stride = desc.stride
    inner = ~border_mask(err_bu.shape, stride)

    # level-0 tile interiors are exact; other levels stay inside the threshold
    for ty in range(levels.shape[0]):
        for tx in range(levels.shape[1]):
            box = (slice(ty * stride, (ty + 1) * stride + 1),
                   slice(tx * stride, (tx + 1) * stride + 1))
            tile_err = np.where(inner[box], err_bu[box], 0)
            if levels[ty, tx] == 0:
                assert tile_err.max() == 0, f"level-0 tile ({tx},{ty}) is not exact"
            else:
                assert tile_err.max() <= LEVEL_MAX_ERROR + 1


def test_noisy_block_stays_level_zero(tmp_path):
    """The mountain block is incompressible, the ocean block is level 4."""
    hm = synthetic_heightmap()
    write_packed(hm, tmp_path, tile_size=33)
    ind = np.array(Image.open(tmp_path / "indirection_heightmap.png"))[::-1]
    levels = ind[:, :, 3]
    assert levels[0, 0] == 4, "smooth gradient corner should use the top level"
    assert levels[7, 0] == 4, "flat ocean block should use the top level"
    # hm[128:192, 160:288] bottom-up is rows 64..127, cols 160..287 = grid
    # rows 2-3, columns 5-8
    assert (levels[2:4, 5:9] == 0).all(), "noisy mountain tiles must not compress"
    assert np.array_equal(ind[:, :, 2], (1 << levels).astype(np.uint8))


def test_flat_heightmap_has_one_tile(tmp_path):
    hm = np.full((128, 128), 4242, dtype=np.uint16)
    meta = write_packed(hm, tmp_path, tile_size=33)
    assert meta["distinct_tiles"] == 1
    assert meta["level_histogram"] == [0, 0, 0, 0, 16]
    assert meta["max_abs_error"] == 0
    # the single tile is the empty tile, and it sits at the atlas origin
    assert meta["empty_tile_offset"] == (0, 0)
    atlas = np.array(Image.open(tmp_path / "packed_heightmap.png"))
    assert atlas.shape == (3, 3) and (atlas == 4242).all()
    back, _ = decode_packed(tmp_path)
    assert np.array_equal(back, hm)


# --------------------------------------------------------------------------- #
# descriptor
# --------------------------------------------------------------------------- #


def test_descriptor_matches_vanilla_byte_for_byte():
    desc = parse_descriptor(VANILLA_DESCRIPTOR)
    assert desc.to_text() == VANILLA_DESCRIPTOR
    assert desc.grid_size == (288, 144)
    assert desc.tile_px(0) == 65 and desc.tile_px(4) == 5


def test_written_descriptor_has_bom_and_vanilla_key_order(tmp_path):
    hm = synthetic_heightmap()
    write_packed(hm, tmp_path, tile_size=33)
    raw = (tmp_path / "heightmap.heightmap").read_bytes()
    assert raw[:3] == b"\xef\xbb\xbf", "CK3 wants the descriptor UTF-8 with BOM"
    text = raw.decode("utf-8-sig")
    assert b"\r\n" not in raw
    keys = [line.split("=", 1)[0] for line in text.splitlines()]
    assert keys == [
        "heightmap_file",
        "indirection_file",
        "original_heightmap_size",
        "tile_size",
        "should_wrap_x",
        "level_offsets",
        "max_compress_level",
        "empty_tile_offset",
    ]
    assert "original_heightmap_size={ 320 256 }" in text
    assert "should_wrap_x=no" in text
    # five level offsets for max_compress_level=4, x always 0
    desc = read_descriptor(tmp_path / "heightmap.heightmap")
    assert len(desc.level_offsets) == 5
    assert all(x == 0 for x, _y in desc.level_offsets)
    assert [y for _x, y in desc.level_offsets] == sorted(y for _x, y in desc.level_offsets)


def test_descriptor_parses_crlf_and_bom():
    desc = parse_descriptor("﻿" + VANILLA_DESCRIPTOR.replace("\n", "\r\n"))
    assert desc.original_heightmap_size == (18432, 9216)
    assert desc.empty_tile_offset == (225, 39)
    assert desc.should_wrap_x is False


# --------------------------------------------------------------------------- #
# input validation
# --------------------------------------------------------------------------- #


def test_dims_not_multiple_of_stride_raises(tmp_path):
    """Documented choice: raise, never silently drop the last strip."""
    hm = np.zeros((100, 320), dtype=np.uint16)  # 100 % 32 != 0
    with pytest.raises(ValueError, match="multiple of the tile stride 32"):
        write_packed(hm, tmp_path, tile_size=33)


def test_wrong_dtype_and_rank_raise(tmp_path):
    with pytest.raises(ValueError, match="uint16"):
        write_packed(np.zeros((64, 64), dtype=np.uint8), tmp_path, tile_size=33)
    with pytest.raises(ValueError, match="2-D"):
        write_packed(np.zeros((4, 64, 64), dtype=np.uint16), tmp_path, tile_size=33)


def test_tile_size_must_suit_max_compress_level(tmp_path):
    hm = np.zeros((64, 64), dtype=np.uint16)
    with pytest.raises(ValueError, match="max_compress_level"):
        write_packed(hm, tmp_path, tile_size=25, max_compress_level=4)


def test_decode_rejects_mismatched_indirection():
    desc = parse_descriptor(VANILLA_DESCRIPTOR)
    with pytest.raises(ValueError, match="implies 288x144"):
        decode_arrays(
            np.zeros((10, 10), np.uint16), np.zeros((2, 2, 4), np.uint8), desc
        )
