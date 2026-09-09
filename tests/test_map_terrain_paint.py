"""Tests for CK2 terrain.bmp -> CK3 detail_index/detail_intensity paint."""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import pytest

from ck2ck3.map import terrain_paint
from ck2ck3.map.terrain import CK2_TO_CK3_TERRAIN

REPO = Path(__file__).resolve().parents[1]

MATERIALS_SETTINGS = """﻿materials={
\t{
\t\tname = "plains"
\t\tid = "plains_01"
\t}
\t{
\t\tname = "plains noisy"
\t\tid = "plains_01_noisy"
\t}
\t{
\t\tname = "hills"
\t\tid = "hills_01"
\t}
}
"""


@pytest.fixture
def ordinals(tmp_path):
    p = tmp_path / "materials.settings"
    p.write_text(MATERIALS_SETTINGS, encoding="utf-8")
    return terrain_paint.material_ordinals(p)


def _material_map(tmp_path, rows):
    p = tmp_path / "terrain_paint.csv"
    with p.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["ck3_terrain", "primary_material", "secondary_material", "note"])
        w.writerows(rows)
    return terrain_paint.read_material_map(p)


# --------------------------------------------------------------------------- #
# material_ordinals
# --------------------------------------------------------------------------- #
def test_material_ordinals_are_declaration_order(ordinals):
    assert ordinals == {"plains_01": 0, "plains_01_noisy": 1, "hills_01": 2}


def test_material_ordinals_missing_file_is_not_an_error(tmp_path):
    assert terrain_paint.material_ordinals(tmp_path / "nope.settings") == {}


# --------------------------------------------------------------------------- #
# read_material_map
# --------------------------------------------------------------------------- #
def test_read_material_map_parses_rows(tmp_path):
    m = _material_map(tmp_path, [("plains", "plains_01", "plains_01_noisy", "")])
    assert m == {"plains": ("plains_01", "plains_01_noisy")}


def test_read_material_map_missing_file_is_not_an_error(tmp_path):
    assert terrain_paint.read_material_map(tmp_path / "nope.csv") == {}


def test_the_shipped_terrain_paint_csv_covers_every_ck3_terrain_key():
    """Every CK2_TO_CK3_TERRAIN target key has a material row (Goal B done-criterion)."""
    m = terrain_paint.read_material_map(REPO / "mappings" / "terrain_paint.csv")
    assert m, "mappings/terrain_paint.csv is empty"
    missing = set(CK2_TO_CK3_TERRAIN.values()) - set(m)
    assert not missing, f"no terrain_paint.csv row for {sorted(missing)}"


# --------------------------------------------------------------------------- #
# build_layers
# --------------------------------------------------------------------------- #
def test_intensity_channels_always_sum_to_255(tmp_path, ordinals):
    codes = np.array([[0, 1], [1, 0]], dtype=np.uint16)
    names = ["", "plains"]
    mmap = _material_map(tmp_path, [("plains", "plains_01", "plains_01_noisy", "")])
    layers = terrain_paint.build_layers(
        codes, names, material_map=mmap, ordinals=ordinals
    )
    total = layers.intensity[..., :2].astype(np.uint16).sum(axis=2)
    assert (total == 255).all()
    assert (layers.intensity[..., 2:] == 0).all()


def test_index_channels_use_the_declared_ordinals(tmp_path, ordinals):
    codes = np.array([[1, 2]], dtype=np.uint16)  # plains, hills
    names = ["", "plains", "hills"]
    mmap = _material_map(
        tmp_path,
        [
            ("plains", "plains_01", "plains_01_noisy", ""),
            ("hills", "hills_01", "plains_01", ""),
        ],
    )
    layers = terrain_paint.build_layers(
        codes, names, material_map=mmap, ordinals=ordinals
    )
    assert layers.index[0, 0, 0] == ordinals["plains_01"]
    assert layers.index[0, 0, 1] == ordinals["plains_01_noisy"]
    assert layers.index[0, 1, 0] == ordinals["hills_01"]
    assert layers.index[0, 1, 1] == ordinals["plains_01"]


def test_missing_material_row_falls_back_and_is_reported(tmp_path, ordinals):
    codes = np.array([[1]], dtype=np.uint16)
    names = ["", "jungle"]  # no jungle row in mmap
    mmap = _material_map(tmp_path, [("plains", "plains_01", "plains_01_noisy", "")])
    warnings = []
    layers = terrain_paint.build_layers(
        codes, names, material_map=mmap, ordinals=ordinals,
        default="plains", warn=warnings.append,
    )
    assert layers.missing_material == ["jungle"]
    assert any("jungle" in w for w in warnings)
    assert layers.index[0, 0, 0] == ordinals["plains_01"]  # fell back to default


def test_missing_ordinal_falls_back_to_zero_and_is_reported(tmp_path):
    codes = np.array([[1]], dtype=np.uint16)
    names = ["", "plains"]
    mmap = _material_map(tmp_path, [("plains", "not_a_real_material", "also_fake", "")])
    warnings = []
    layers = terrain_paint.build_layers(
        codes, names, material_map=mmap, ordinals={}, warn=warnings.append,
    )
    assert set(layers.missing_ordinal) == {"not_a_real_material", "also_fake"}
    assert layers.index[0, 0, 0] == 0
    assert any("not_a_real_material" in w for w in warnings)


def test_empty_category_code_falls_back_to_the_default(tmp_path, ordinals):
    """Code 0 (padding / no CK2 category) must not read as an undeclared class."""
    codes = np.array([[0]], dtype=np.uint16)
    names = [""]
    mmap = _material_map(tmp_path, [("plains", "plains_01", "plains_01_noisy", "")])
    layers = terrain_paint.build_layers(
        codes, names, material_map=mmap, ordinals=ordinals, default="plains"
    )
    assert layers.missing_material == []
    assert layers.classes == {"plains": 1}


def test_build_layers_is_deterministic(tmp_path, ordinals):
    codes = np.tile(np.array([0, 1, 1, 0], dtype=np.uint16), (20, 1))
    names = ["", "plains"]
    mmap = _material_map(tmp_path, [("plains", "plains_01", "plains_01_noisy", "")])
    a = terrain_paint.build_layers(codes, names, material_map=mmap, ordinals=ordinals)
    b = terrain_paint.build_layers(codes, names, material_map=mmap, ordinals=ordinals)
    assert np.array_equal(a.index, b.index)
    assert np.array_equal(a.intensity, b.intensity)


def test_classes_histogram_counts_pixels_by_ck3_key(tmp_path, ordinals):
    codes = np.array([[1, 1, 2]], dtype=np.uint16)  # 2x plains, 1x hills
    names = ["", "plains", "hills"]
    mmap = _material_map(
        tmp_path,
        [
            ("plains", "plains_01", "plains_01_noisy", ""),
            ("hills", "hills_01", "plains_01", ""),
        ],
    )
    layers = terrain_paint.build_layers(
        codes, names, material_map=mmap, ordinals=ordinals
    )
    assert layers.classes == {"plains": 2, "hills": 1}


# --------------------------------------------------------------------------- #
# save_tga
# --------------------------------------------------------------------------- #
def test_save_tga_writes_an_uncompressed_true_colour_rgba_file(tmp_path):
    arr = np.zeros((3, 4, 4), dtype=np.uint8)
    arr[..., 0] = 200
    arr[..., 3] = 255
    path = tmp_path / "out.tga"
    terrain_paint.save_tga(arr, path)
    data = path.read_bytes()
    assert data[2] == 2, "must be image type 2 (uncompressed truecolour), not RLE"
    assert data[16] == 32, "must be 32 bits per pixel (RGBA)"
    width = data[12] | (data[13] << 8)
    height = data[14] | (data[15] << 8)
    assert (width, height) == (4, 3)


def test_save_tga_round_trips_through_pil(tmp_path):
    from PIL import Image

    rng = np.random.default_rng(0)
    arr = rng.integers(0, 255, size=(5, 6, 4), dtype=np.uint8)
    arr[..., 3] = 255
    path = tmp_path / "rt.tga"
    terrain_paint.save_tga(arr, path)
    back = np.asarray(Image.open(path).convert("RGBA"))
    assert np.array_equal(arr, back)


# --------------------------------------------------------------------------- #
# save_tga(rle=True) / load_tga — [map] terrain_paint_format = "tga_rle"
# --------------------------------------------------------------------------- #
def test_save_tga_rle_writes_image_type_10(tmp_path):
    arr = np.zeros((3, 4, 4), dtype=np.uint8)
    arr[..., 0] = 200
    arr[..., 3] = 255
    path = tmp_path / "out_rle.tga"
    terrain_paint.save_tga(arr, path, rle=True)
    data = path.read_bytes()
    assert data[2] == 10, "must be image type 10 (RLE), matching Elder Kings 2 / Godherja"


def test_save_tga_rle_round_trips(tmp_path):
    rng = np.random.default_rng(1)
    arr = rng.integers(0, 255, size=(9, 13, 4), dtype=np.uint8)
    arr[..., 3] = 255
    path = tmp_path / "rt_rle.tga"
    terrain_paint.save_tga(arr, path, rle=True)
    back = terrain_paint.load_tga(path)
    assert np.array_equal(arr, back)


def test_plain_and_rle_tga_decode_to_the_same_pixels(tmp_path):
    rng = np.random.default_rng(2)
    arr = rng.integers(0, 255, size=(20, 20, 4), dtype=np.uint8)
    arr[..., 3] = 255
    p1, p2 = tmp_path / "plain.tga", tmp_path / "rle.tga"
    terrain_paint.save_tga(arr, p1, rle=False)
    terrain_paint.save_tga(arr, p2, rle=True)
    assert np.array_equal(terrain_paint.load_tga(p1), terrain_paint.load_tga(p2))


# --------------------------------------------------------------------------- #
# save_dds / load_dds — [map] terrain_paint_format = "dds"
# --------------------------------------------------------------------------- #
def test_save_dds_writes_a_valid_header():
    arr = np.zeros((3, 4, 4), dtype=np.uint8)
    path_bytes = terrain_paint._dds_header(4, 3)
    assert path_bytes[:4] == b"DDS "
    assert len(path_bytes) == 128
    # dwSize == 124, dwHeight == 3, dwWidth == 4 (offsets documented in code)
    import struct

    dw_size = struct.unpack_from("<I", path_bytes, 4)[0]
    dw_height = struct.unpack_from("<I", path_bytes, 12)[0]
    dw_width = struct.unpack_from("<I", path_bytes, 16)[0]
    assert (dw_size, dw_height, dw_width) == (124, 3, 4)
    del arr


def test_save_dds_round_trips(tmp_path):
    rng = np.random.default_rng(3)
    arr = rng.integers(0, 255, size=(7, 11, 4), dtype=np.uint8)
    arr[..., 3] = 255
    path = tmp_path / "rt.dds"
    terrain_paint.save_dds(arr, path)
    back = terrain_paint.load_dds(path)
    assert np.array_equal(arr, back)


def test_load_dds_rejects_a_non_dds_file(tmp_path):
    path = tmp_path / "notdds.bin"
    path.write_bytes(b"not a dds file at all, but long enough" + b"\0" * 100)
    with pytest.raises(ValueError):
        terrain_paint.load_dds(path)


# --------------------------------------------------------------------------- #
# save_paint / load_paint / paint_ext — the [map] terrain_paint_format dispatch
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("fmt,ext", [("tga", "tga"), ("tga_rle", "tga"), ("dds", "dds")])
def test_paint_ext(fmt, ext):
    assert terrain_paint.paint_ext(fmt) == ext


def test_paint_ext_rejects_unknown_format():
    with pytest.raises(ValueError):
        terrain_paint.paint_ext("png")


@pytest.mark.parametrize("fmt", terrain_paint.PAINT_FORMATS)
def test_save_load_paint_round_trips_every_format(tmp_path, fmt):
    rng = np.random.default_rng(4)
    arr = rng.integers(0, 255, size=(6, 8, 4), dtype=np.uint8)
    arr[..., 3] = 255
    path = tmp_path / f"paint.{terrain_paint.paint_ext(fmt)}"
    terrain_paint.save_paint(arr, path, fmt)
    back = terrain_paint.load_paint(path, fmt)
    assert np.array_equal(arr, back)


# --------------------------------------------------------------------------- #
# downsample_index / downsample_intensity — [map] terrain_paint_scale
# --------------------------------------------------------------------------- #
def test_downsample_index_is_nearest_neighbour_never_interpolates():
    """A 2x2 block of two distinct ordinals must downsample to one of the
    two source values, never an average (which could name a bogus material)."""
    arr = np.zeros((4, 4, 4), dtype=np.uint8)
    arr[:2, :2, 0] = 10
    arr[:2, 2:, 0] = 200  # far from 10 -- an average (105) is easy to spot
    arr[2:, :2, 0] = 10
    arr[2:, 2:, 0] = 200
    out = terrain_paint.downsample_index(arr, 0.5)
    assert out.shape == (2, 2, 4)
    assert set(np.unique(out[..., 0]).tolist()) <= {10, 200}


def test_downsample_index_halves_dimensions():
    # even dimensions, same aspect ratio as the shipped 8320x6784 canvas
    arr = np.zeros((416, 338, 4), dtype=np.uint8)
    out = terrain_paint.downsample_index(arr, 0.5)
    assert out.shape[:2] == (arr.shape[0] // 2, arr.shape[1] // 2)


def test_downsample_intensity_preserves_sum_to_255():
    rng = np.random.default_rng(5)
    h, w = 10, 12
    prim = rng.integers(1, 255, size=(h, w), dtype=np.uint8)
    arr = np.zeros((h, w, 4), dtype=np.uint8)
    arr[..., 0] = prim
    arr[..., 1] = 255 - prim
    out = terrain_paint.downsample_intensity(arr, 0.5)
    assert out.shape == (h // 2, w // 2, 4)
    total = out[..., 0].astype(np.uint16) + out[..., 1].astype(np.uint16)
    assert (total == 255).all()
    assert (out[..., 2:] == 0).all()


def test_downsample_intensity_is_a_box_average_not_nearest():
    """A checkerboard of 0/254 should average toward the middle, distinguishing
    box filtering from a nearest-neighbour pick of one corner."""
    arr = np.zeros((2, 2, 4), dtype=np.uint8)
    arr[0, 0, 0], arr[0, 1, 0] = 0, 254
    arr[1, 0, 0], arr[1, 1, 0] = 254, 0
    arr[..., 1] = 255 - arr[..., 0]
    out = terrain_paint.downsample_intensity(arr, 0.5)
    assert out.shape == (1, 1, 4)
    assert 100 < int(out[0, 0, 0]) < 155  # averages to 127, not 0 or 254


def test_downsample_intensity_rejects_scale_above_one():
    arr = np.zeros((4, 4, 4), dtype=np.uint8)
    with pytest.raises(ValueError):
        terrain_paint.downsample_intensity(arr, 2.0)


def test_full_pipeline_downsample_roundtrips_through_every_format(tmp_path, ordinals):
    """End to end at the config default scale (0.5): build a small paint pair,
    downsample, write and read back every format."""
    codes = np.tile(np.array([1, 2], dtype=np.uint16), (40, 20))
    names = ["", "plains", "hills"]
    mmap = _material_map(
        tmp_path,
        [
            ("plains", "plains_01", "plains_01_noisy", ""),
            ("hills", "hills_01", "plains_01", ""),
        ],
    )
    layers = terrain_paint.build_layers(codes, names, material_map=mmap, ordinals=ordinals)
    idx = terrain_paint.downsample_index(layers.index, 0.5)
    inten = terrain_paint.downsample_intensity(layers.intensity, 0.5)
    assert idx.shape[:2] == inten.shape[:2] == (20, 20)
    for fmt in terrain_paint.PAINT_FORMATS:
        ip = tmp_path / f"idx.{terrain_paint.paint_ext(fmt)}"
        terrain_paint.save_paint(idx, ip, fmt)
        assert np.array_equal(terrain_paint.load_paint(ip, fmt), idx)
