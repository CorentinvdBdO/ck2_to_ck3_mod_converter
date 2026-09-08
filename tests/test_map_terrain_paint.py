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
