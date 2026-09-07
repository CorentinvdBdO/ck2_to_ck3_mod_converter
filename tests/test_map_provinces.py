"""Tests for the provinces raster, the lost-province report and the re-grow."""

from __future__ import annotations

import csv

import numpy as np
from PIL import Image

from ck2ck3.map import provinces
from ck2ck3.map.ck2read import Ck2Province
from ck2ck3.map.config import Canvas


def canvas(w, h, factor, ox=0, oy=0, sw=None, sh=None) -> Canvas:
    return Canvas(
        width=w, height=h,
        scaled_width=sw if sw is not None else w - 2 * ox,
        scaled_height=sh if sh is not None else h - 2 * oy,
        offset_x=ox, offset_y=oy, factor=factor,
    )


def write_bmp(rgb: np.ndarray, path):
    Image.fromarray(rgb.astype(np.uint8), mode="RGB").save(path)
    return path


def test_rgb_key_packs_and_is_unique():
    arr = np.array([[[1, 2, 3], [255, 255, 255]]], dtype=np.uint8)
    keys = provinces.rgb_key(arr)
    assert keys[0, 0] == (1 << 16) | (2 << 8) | 3
    assert keys[0, 1] == 0xFFFFFF


def test_upscaling_loses_nothing(tmp_path):
    """Every source pixel becomes several, so no colour can disappear."""
    rgb = np.zeros((4, 4, 3), dtype=np.uint8)
    rgb[:, :2] = (10, 0, 0)
    rgb[:, 2:] = (0, 10, 0)
    rgb[0, 0] = (0, 0, 10)  # a single-pixel province
    provs = [
        Ck2Province(1, (10, 0, 0), "A"),
        Ck2Province(2, (0, 10, 0), "B"),
        Ck2Province(3, (0, 0, 10), "C"),
    ]
    c = canvas(16, 16, 2.0, ox=4, oy=4)
    r = provinces.build_raster(
        write_bmp(rgb, tmp_path / "p.bmp"), provs, c, min_pixels=1
    )
    assert r.surviving == {1, 2, 3}
    assert r.lost == {}


def test_undefined_colours_are_reported_and_become_padding(tmp_path):
    rgb = np.full((4, 4, 3), 255, dtype=np.uint8)  # white, not in definition.csv
    rgb[0, 0] = (10, 0, 0)
    provs = [Ck2Province(1, (10, 0, 0), "A")]
    c = canvas(16, 16, 2.0, ox=4, oy=4)
    r = provinces.build_raster(
        write_bmp(rgb, tmp_path / "p.bmp"), provs, c, min_pixels=1
    )
    assert (255, 255, 255) in r.undefined_colours
    assert r.undefined_colours[(255, 255, 255)] == 15
    assert (r.ids[0, 0] == provinces.PADDING)


def test_province_defined_but_absent_from_the_bitmap_is_lost(tmp_path):
    rgb = np.full((4, 4, 3), (10, 0, 0), dtype=np.uint8)
    provs = [Ck2Province(1, (10, 0, 0), "A"), Ck2Province(2, (0, 10, 0), "Filler")]
    c = canvas(16, 16, 2.0, ox=4, oy=4)
    r = provinces.build_raster(
        write_bmp(rgb, tmp_path / "p.bmp"), provs, c, min_pixels=1
    )
    assert 2 in r.lost
    assert r.lost[2] == (0, 0)


def test_downscaling_can_lose_a_tiny_province_and_it_is_reported(tmp_path):
    rgb = np.full((16, 16, 3), (10, 0, 0), dtype=np.uint8)
    rgb[0, 0] = (0, 0, 10)  # 1 source pixel at a 0.25x factor
    provs = [Ck2Province(1, (10, 0, 0), "Big"), Ck2Province(2, (0, 0, 10), "Tiny")]
    c = canvas(8, 8, 0.25, sw=4, sh=4, ox=2, oy=2)
    r = provinces.build_raster(
        write_bmp(rgb, tmp_path / "p.bmp"), provs, c, min_pixels=4, regrow=False
    )
    assert 2 in r.lost
    assert r.lost[2][0] == 1  # one source pixel


def test_regrow_rescues_a_province_inside_its_own_footprint(tmp_path):
    rgb = np.full((16, 16, 3), (10, 0, 0), dtype=np.uint8)
    rgb[0:4, 0:4] = (0, 0, 10)  # 16 source pixels
    provs = [Ck2Province(1, (10, 0, 0), "Big"), Ck2Province(2, (0, 0, 10), "Small")]
    c = canvas(8, 8, 0.25, sw=4, sh=4, ox=2, oy=2)
    r = provinces.build_raster(
        write_bmp(rgb, tmp_path / "p.bmp"), provs, c, min_pixels=1, regrow=True
    )
    assert 2 in r.surviving


def test_regrow_never_takes_a_pixel_outside_the_ck2_footprint(tmp_path):
    """The safety property: a province cannot leak across a coastline."""
    rgb = np.full((16, 16, 3), (10, 0, 0), dtype=np.uint8)
    rgb[0, 0] = (0, 0, 10)
    provs = [Ck2Province(1, (10, 0, 0), "Big"), Ck2Province(2, (0, 0, 10), "Tiny")]
    c = canvas(8, 8, 0.25, sw=4, sh=4, ox=2, oy=2)
    r = provinces.build_raster(
        write_bmp(rgb, tmp_path / "p.bmp"), provs, c, min_pixels=8, regrow=True
    )
    # the footprint is one source pixel, so at most one target pixel: it cannot
    # reach 8 and must not have stolen 8 pixels from its neighbour
    assert int((r.ids == 2).sum()) <= 1


def test_lost_province_pixels_are_blanked_to_padding(tmp_path):
    """A dropped province must not leave pixels of a colour that is not in
    definition.csv, or the game logs an unknown-province error."""
    rgb = np.full((16, 16, 3), (10, 0, 0), dtype=np.uint8)
    rgb[0, 0] = (0, 0, 10)
    provs = [Ck2Province(1, (10, 0, 0), "Big"), Ck2Province(2, (0, 0, 10), "Tiny")]
    c = canvas(8, 8, 0.25, sw=4, sh=4, ox=2, oy=2)
    r = provinces.build_raster(
        write_bmp(rgb, tmp_path / "p.bmp"), provs, c, min_pixels=4, regrow=False
    )
    assert 2 in r.lost
    assert not (r.ids == 2).any()


def test_canvas_outside_the_source_is_padding(tmp_path):
    rgb = np.full((4, 4, 3), (10, 0, 0), dtype=np.uint8)
    provs = [Ck2Province(1, (10, 0, 0), "A")]
    c = canvas(16, 16, 2.0, ox=4, oy=4)
    r = provinces.build_raster(
        write_bmp(rgb, tmp_path / "p.bmp"), provs, c, min_pixels=1
    )
    assert r.ids[0, 0] == provinces.PADDING
    assert r.ids[-1, -1] == provinces.PADDING
    assert r.ids[8, 8] == 1


def test_render_png_is_rgb_and_uses_the_padding_colour(tmp_path):
    rgb = np.full((4, 4, 3), (10, 20, 30), dtype=np.uint8)
    provs = [Ck2Province(1, (10, 20, 30), "A")]
    c = canvas(16, 16, 2.0, ox=4, oy=4)
    r = provinces.build_raster(
        write_bmp(rgb, tmp_path / "p.bmp"), provs, c, min_pixels=1
    )
    out = tmp_path / "provinces.png"
    provinces.render_png(r, {1: (10, 20, 30)}, (0, 0, 96), out)
    with Image.open(out) as im:
        assert im.mode == "RGB"
        arr = np.asarray(im)
    assert tuple(arr[0, 0]) == (0, 0, 96)
    assert tuple(arr[8, 8]) == (10, 20, 30)


def test_lost_report_lists_drops_regrows_and_undefined_colours(tmp_path):
    rgb = np.full((16, 16, 3), (10, 0, 0), dtype=np.uint8)
    rgb[0, 0] = (0, 0, 10)
    rgb[15, 15] = (7, 7, 7)  # undefined
    provs = [Ck2Province(1, (10, 0, 0), "Big"), Ck2Province(2, (0, 0, 10), "Tiny")]
    c = canvas(8, 8, 0.25, sw=4, sh=4, ox=2, oy=2)
    r = provinces.build_raster(
        write_bmp(rgb, tmp_path / "p.bmp"), provs, c, min_pixels=4, regrow=False
    )
    p = tmp_path / "lost_provinces.csv"
    provinces.write_lost_report(r, {1: "Big", 2: "Tiny"}, p)
    rows = list(csv.DictReader(p.open(encoding="utf-8")))
    assert any(r_["ck2_id"] == "2" and r_["outcome"] == "dropped" for r_ in rows)
    assert any("undefined colour" in r_["name"] for r_ in rows)
