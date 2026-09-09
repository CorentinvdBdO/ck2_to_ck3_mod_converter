"""Tests for scripts/camera_probe.py: the START_LOOK_AT probe-mod writer."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

import camera_probe  # noqa: E402


def test_world_look_at_matches_locator_bottom_up_frame():
    x, z = camera_probe.world_look_at(100.0, 40.0, canvas_height=200)
    assert x == 100.0
    assert z == 160.0  # z = height - y, same as ck2ck3.map.locators.world_position


def test_province_centroid_px_finds_the_right_pixels(tmp_path):
    (tmp_path / "map_data").mkdir()
    arr = np.zeros((10, 10, 3), dtype=np.uint8)
    arr[2:4, 6:8] = (10, 20, 30)
    Image.fromarray(arr).save(tmp_path / "map_data" / "provinces.png")
    x, y = camera_probe.province_centroid_px(tmp_path, (10, 20, 30))
    assert x == 6.5
    assert y == 2.5


def test_render_probe_writes_valid_ncamera_block():
    text = camera_probe.render_probe(1234.5, 6789.0, 12)
    assert "NCamera = {" in text
    assert "START_LOOK_AT = { 1234.5 0 6789.0 }" in text
    assert "START_ZOOM_STEP = 12" in text


def test_write_probe_writes_defines_file_and_descriptor(tmp_path):
    path = camera_probe.write_probe(tmp_path, 1.0, 2.0, 20)
    assert path.is_file()
    assert path.relative_to(tmp_path) == Path(
        "common/defines/graphic/zzz_camera_probe_graphics.txt"
    )
    assert (tmp_path / "descriptor.mod").is_file()
    assert 'version=' in (tmp_path / "descriptor.mod").read_text()
