"""Tests for the river trace-and-redraw conversion.

The regressions these pin down are the two bugs in the previous implementation
(``docs/converter_code_assessment.md`` §3): SPLIT (index 2) was not followed,
and WATER (index 254) was walked into as if it were river.
"""

from __future__ import annotations

import numpy as np
from PIL import Image

from ck2ck3.map import rivers
from ck2ck3.map.config import Canvas


def canvas(w=40, h=40, factor=2.0, ox=2, oy=2) -> Canvas:
    return Canvas(
        width=w, height=h,
        scaled_width=int(w - 2 * ox), scaled_height=int(h - 2 * oy),
        offset_x=ox, offset_y=oy, factor=factor,
    )


def write_bmp(arr: np.ndarray, path) -> str:
    """Write an 8-bit palette BMP with the CK2/CK3 rivers palette."""
    im = Image.fromarray(arr.astype(np.uint8), mode="P")
    flat = [0] * 768
    for i, (r, g, b) in rivers.PALETTE.items():
        flat[i * 3 : i * 3 + 3] = [r, g, b]
    im.putpalette(flat)
    im.save(path)
    return str(path)


# --------------------------------------------------------------------------- #
# palette semantics
# --------------------------------------------------------------------------- #
def test_is_river_covers_specials_and_widths_but_not_water_or_land():
    assert rivers.is_river(rivers.SOURCE)
    assert rivers.is_river(rivers.MERGE)
    assert rivers.is_river(rivers.SPLIT)
    assert all(rivers.is_river(i) for i in range(3, 12))
    assert not rivers.is_river(rivers.WATER)
    assert not rivers.is_river(rivers.LAND)
    assert not rivers.is_river(12)


def test_palette_matches_the_ck3_values():
    """Byte-identical to vanilla map_data/rivers.png's palette."""
    assert rivers.PALETTE[0] == (0, 255, 0)
    assert rivers.PALETTE[1] == (255, 0, 0)
    assert rivers.PALETTE[2] == (255, 252, 0)
    assert rivers.PALETTE[254] == (255, 0, 128)
    assert rivers.PALETTE[255] == (255, 255, 255)


# --------------------------------------------------------------------------- #
# bresenham
# --------------------------------------------------------------------------- #
def test_bresenham_endpoints_are_inclusive():
    pts = rivers.bresenham(0, 0, 0, 3)
    assert pts[0] == (0, 0) and pts[-1] == (0, 3)


def test_bresenham_is_eight_connected_with_no_gaps():
    pts = rivers.bresenham(0, 0, 7, 3)
    for (y0, x0), (y1, x1) in zip(pts, pts[1:]):
        assert max(abs(y1 - y0), abs(x1 - x0)) == 1


def test_bresenham_single_pixel():
    assert rivers.bresenham(5, 5, 5, 5) == [(5, 5)]


# --------------------------------------------------------------------------- #
# tracing
# --------------------------------------------------------------------------- #
def test_trace_walks_a_straight_river_from_its_source():
    src = np.full((5, 8), rivers.LAND, dtype=np.int16)
    src[2, 1] = rivers.SOURCE
    src[2, 2:7] = 3
    paths = rivers.trace(src)
    assert len(paths) == 1
    assert paths[0].points[0] == (2, 1)
    assert len(paths[0].points) == 6


def test_trace_does_not_walk_into_water():
    """Regression: index 254 was treated as river continuation."""
    src = np.full((5, 10), rivers.LAND, dtype=np.int16)
    src[2, 1] = rivers.SOURCE
    src[2, 2:5] = 3
    src[2, 5:] = rivers.WATER  # open sea
    paths = rivers.trace(src)
    assert len(paths) == 1
    assert all(src[p] != rivers.WATER for p in paths[0].points)
    assert len(paths[0].points) == 4


def test_trace_follows_a_split_branch():
    """Regression: index 2 (yellow) started no path, so the branch was lost."""
    src = np.full((7, 10), rivers.LAND, dtype=np.int16)
    src[3, 1] = rivers.SOURCE
    src[3, 2:8] = 3  # main stem
    src[4, 4] = rivers.SPLIT  # distributary leaves here
    src[5, 4] = 4
    src[6, 4] = 4
    paths = rivers.trace(src)
    traced = {p for path in paths for p in path.points}
    assert (4, 4) in traced, "the SPLIT pixel itself must be traced"
    assert (5, 4) in traced and (6, 4) in traced, "the split branch must be traced"


def test_trace_covers_every_river_pixel_exactly_once():
    src = np.full((9, 9), rivers.LAND, dtype=np.int16)
    src[4, 1] = rivers.SOURCE
    src[4, 2:8] = 3
    src[1, 4] = rivers.SOURCE
    src[2, 4] = 5
    src[3, 4] = rivers.MERGE
    river_pixels = {
        (int(y), int(x)) for y, x in zip(*np.nonzero(np.isin(src, [0, 1, 2, 3, 5])))
    }
    seen: list[tuple[int, int]] = []
    for path in rivers.trace(src):
        seen.extend(path.points)
    # every river pixel appears; junction pixels may repeat as path endpoints
    assert set(seen) == river_pixels


def test_trace_handles_a_ring_with_no_endpoint():
    src = np.full((6, 6), rivers.LAND, dtype=np.int16)
    src[1:5, 1] = 3
    src[1:5, 4] = 3
    src[1, 1:5] = 3
    src[4, 1:5] = 3
    paths = rivers.trace(src)
    assert paths, "a closed loop must still be traced, not skipped forever"


def test_width_index_is_the_modal_body_value():
    src = np.full((3, 8), rivers.LAND, dtype=np.int16)
    src[1, 1] = rivers.SOURCE
    src[1, 2:6] = 6
    src[1, 6] = 3
    path = rivers.trace(src)[0]
    assert path.width_index == 6


# --------------------------------------------------------------------------- #
# render
# --------------------------------------------------------------------------- #
def test_render_paints_water_from_the_mask_not_from_the_source(tmp_path):
    """CK2 Faerûn writes no 254 at all; CK3 needs its sea marked 254."""
    src = np.full((16, 16), rivers.LAND, dtype=np.int16)
    bmp = write_bmp(src, tmp_path / "rivers.bmp")
    c = canvas()
    mask = np.zeros((c.height, c.width), dtype=bool)
    mask[:, :5] = True
    out = rivers.render(bmp, c, mask)
    assert (out[:, :5] == rivers.WATER).all()
    assert (out[:, 5:] == rivers.LAND).all()


def test_render_upscales_a_river_and_keeps_it_connected(tmp_path):
    src = np.full((16, 16), rivers.LAND, dtype=np.int16)
    src[8, 2] = rivers.SOURCE
    src[8, 3:14] = 3
    bmp = write_bmp(src, tmp_path / "rivers.bmp")
    c = canvas(w=64, h=64, factor=2.0, ox=8, oy=8)
    out = rivers.render(bmp, c, np.zeros((c.height, c.width), dtype=bool))

    ys, xs = np.nonzero(np.isin(out, [0, 1, 2] + list(range(3, 12))))
    assert len(ys) > 0
    # one connected run per row: check the drawn xs form an unbroken span
    row = int(np.bincount(ys).argmax())
    span = np.sort(xs[ys == row])
    assert (np.diff(span) == 1).all(), "the redrawn river has a gap"


def test_render_keeps_the_source_pixel_as_index_zero(tmp_path):
    src = np.full((16, 16), rivers.LAND, dtype=np.int16)
    src[8, 2] = rivers.SOURCE
    src[8, 3:10] = 3
    bmp = write_bmp(src, tmp_path / "rivers.bmp")
    c = canvas(w=64, h=64, factor=2.0, ox=8, oy=8)
    out = rivers.render(bmp, c, np.zeros((c.height, c.width), dtype=bool))
    assert (out == rivers.SOURCE).sum() == 1, "exactly one source pixel survives"


def test_render_never_draws_a_river_over_water(tmp_path):
    src = np.full((16, 16), rivers.LAND, dtype=np.int16)
    src[8, 2] = rivers.SOURCE
    src[8, 3:14] = 3
    bmp = write_bmp(src, tmp_path / "rivers.bmp")
    c = canvas(w=64, h=64, factor=2.0, ox=8, oy=8)
    mask = np.zeros((c.height, c.width), dtype=bool)
    mask[:, 40:] = True
    out = rivers.render(bmp, c, mask)
    assert (out[:, 40:] == rivers.WATER).all()


def test_render_rejects_a_mask_of_the_wrong_shape(tmp_path):
    bmp = write_bmp(np.full((8, 8), rivers.LAND, dtype=np.int16), tmp_path / "r.bmp")
    c = canvas()
    try:
        rivers.render(bmp, c, np.zeros((3, 3), dtype=bool))
    except ValueError as exc:
        assert "water_mask" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected a ValueError")


def test_render_rejects_a_non_palette_source(tmp_path):
    p = tmp_path / "rgb.png"
    Image.fromarray(np.zeros((8, 8, 3), dtype=np.uint8), mode="RGB").save(p)
    c = canvas()
    try:
        rivers.render(p, c, np.zeros((c.height, c.width), dtype=bool))
    except ValueError as exc:
        assert "palette" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected a ValueError")


# --------------------------------------------------------------------------- #
# write / stats
# --------------------------------------------------------------------------- #
def test_write_png_round_trips_indices_and_palette(tmp_path):
    idx = np.full((8, 8), rivers.LAND, dtype=np.uint8)
    idx[4, 2] = rivers.SOURCE
    idx[4, 3:6] = 3
    idx[0, 0] = rivers.WATER
    p = tmp_path / "rivers.png"
    rivers.write_png(idx, p)
    with Image.open(p) as im:
        assert im.mode == "P"
        back = np.asarray(im)
        pal = im.getpalette()
    assert (back == idx).all()
    assert tuple(pal[0:3]) == (0, 255, 0)
    assert tuple(pal[254 * 3 : 254 * 3 + 3]) == (255, 0, 128)


def test_stats_counts_each_class():
    idx = np.full((4, 4), rivers.LAND, dtype=np.uint8)
    idx[0, 0] = rivers.SOURCE
    idx[0, 1] = rivers.MERGE
    idx[0, 2] = rivers.SPLIT
    idx[1, :] = 3
    idx[2, :] = rivers.WATER
    s = rivers.stats(idx)
    assert s["sources"] == 1 and s["merges"] == 1 and s["splits"] == 1
    assert s["body"] == 4 and s["water"] == 4
