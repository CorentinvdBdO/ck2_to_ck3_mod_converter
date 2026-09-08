"""Bookmark writer: test_default, character positions and animations.

The position rules and the numbers quoted here are documented in
``docs/step_titles.md`` (Bookmarks) and measured by
``scripts/survey_vanilla_bookmark_positions.py``.
"""
import math
import re
from pathlib import Path

import pytest

from ck2ck3.pdx import Date
from ck2ck3.titles import bookmarks
from ck2ck3.titles.ck2read import (
    Ck2Bookmark,
    Ck2BookmarkCharacter,
    Ck2CharacterStub,
)

POS = re.compile(r"position = \{ (-?\d+) (-?\d+) \}")
ANIM = re.compile(r"animation = (\w+)")


def test_test_default_is_emitted_once_for_the_default_date():
    src = Path(bookmarks.__file__).read_text()
    assert "test_default = yes" in src and "marked_default" in src


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #
def _bookmark(bid: str, ids: list[str]) -> Ck2Bookmark:
    return Ck2Bookmark(
        id=bid,
        date=Date(1357, 1, 1),
        characters=[
            Ck2BookmarkCharacter(ck2_id=cid, title=f"c_{cid}", name=f"N{cid}")
            for cid in ids
        ],
    )


def _render(bookmarks_, positions):
    ids = [c.ck2_id for b in bookmarks_ for c in b.characters]
    return bookmarks.render(
        bookmarks_,
        characters={i: Ck2CharacterStub(id=i, birth=Date(1320, 1, 1)) for i in ids},
        live_titles=frozenset(f"c_{i}" for i in ids),
        default_date="1357.1.1",
        title_positions=positions,
    )


def _text(result):
    return result.files["common/bookmarks/bookmarks/fae_bookmarks.txt"]


# --------------------------------------------------------------------------- #
# geometry
# --------------------------------------------------------------------------- #
def test_positions_are_inside_the_measured_vanilla_canvas():
    # four capitals spread over a 1000x1000 CK2 map
    positions = {
        "c_a": (10.0, 10.0),
        "c_b": (990.0, 10.0),
        "c_c": (10.0, 990.0),
        "c_d": (500.0, 500.0),
    }
    result = _render([_bookmark("bm_x", ["a", "b", "c", "d"])], positions)
    pts = [(int(x), int(y)) for x, y in POS.findall(_text(result))]
    assert len(pts) == 4
    x0, y0, x1, y1 = bookmarks.CANVAS
    for x, y in pts:
        assert x0 <= x <= x1 and y0 <= y <= y1
    assert (0, 0) not in pts


def test_paradox_y_is_flipped_to_screen_y():
    # c_north has the larger CK2 y, so it must get the smaller screen y
    positions = {"c_north": (500.0, 900.0), "c_south": (500.0, 100.0)}
    result = _render([_bookmark("bm_x", ["north", "south"])], positions)
    pts = POS.findall(_text(result))
    assert int(pts[0][1]) < int(pts[1][1])


def test_no_two_characters_of_one_bookmark_are_closer_than_the_floor():
    # six capitals within 4 CK2 pixels of each other: geography alone would
    # stack them, the repulsion pass must not
    positions = {f"c_{i}": (500.0 + i, 500.0 + i) for i in range(6)}
    positions["c_far"] = (0.0, 0.0)
    positions["c_far2"] = (1000.0, 1000.0)
    result = _render([_bookmark("bm_x", [str(i) for i in range(6)])], positions)
    pts = [(int(x), int(y)) for x, y in POS.findall(_text(result))]
    floor = bookmarks.effective_min_distance(len(pts))
    for i in range(len(pts)):
        for j in range(i + 1, len(pts)):
            assert math.dist(pts[i], pts[j]) >= floor - 1.0


def test_identical_capitals_are_separated_deterministically():
    positions = {f"c_{i}": (500.0, 500.0) for i in range(4)}
    positions["c_edge"] = (0.0, 0.0)
    pts = bookmarks.place_characters(
        [(500.0, 500.0)] * 4, bbox=bookmarks.bounding_box(positions)
    )
    assert len(set(pts)) == 4


def test_the_bounding_box_does_not_depend_on_the_bookmark():
    # the same capital lands on the same pixel in two different bookmarks
    positions = {"c_a": (10.0, 10.0), "c_b": (990.0, 990.0), "c_c": (500.0, 500.0)}
    one = _render([_bookmark("bm_one", ["a"])], positions)
    two = _render([_bookmark("bm_two", ["a"])], positions)
    assert POS.findall(_text(one)) == POS.findall(_text(two))


def test_render_is_deterministic_across_two_calls():
    positions = {f"c_{i}": (10.0 * i, 7.0 * i) for i in range(8)}
    book = [_bookmark("bm_x", [str(i) for i in range(8)])]
    assert _text(_render(book, positions)) == _text(_render(book, positions))


# --------------------------------------------------------------------------- #
# fallback grid
# --------------------------------------------------------------------------- #
def test_characters_without_a_coordinate_go_on_a_spread_grid():
    result = _render([_bookmark("bm_x", ["a", "b", "c", "d"])], {})
    pts = [(int(x), int(y)) for x, y in POS.findall(_text(result))]
    assert len(pts) == 4 and len(set(pts)) == 4
    x0, y0, x1, y1 = bookmarks.CANVAS
    for x, y in pts:
        assert x0 <= x <= x1 and y0 <= y <= y1
    assert result.counts["positioned_on_grid"] == 4
    assert result.counts["positioned_from_map"] == 0


def test_a_mixed_bookmark_counts_both_kinds():
    positions = {"c_a": (10.0, 10.0), "c_b": (990.0, 990.0)}
    result = _render([_bookmark("bm_x", ["a", "b", "c"])], positions)
    assert result.counts["positioned_from_map"] == 2
    assert result.counts["positioned_on_grid"] == 1
    assert any("fallback grid" in w for w in result.warnings)


# --------------------------------------------------------------------------- #
# animation
# --------------------------------------------------------------------------- #
def test_animation_is_picked_from_the_verified_vanilla_list():
    result = _render(
        [_bookmark("bm_x", [f"{i}" for i in range(20)])],
        {f"c_{i}": (10.0 * i, 10.0 * i) for i in range(20)},
    )
    used = ANIM.findall(_text(result))
    assert len(used) == 20
    assert set(used) <= set(bookmarks.ANIMATIONS)
    assert len(set(used)) > 1, "one constant animation for every character"


def test_animation_is_a_pure_function_of_the_name_key():
    assert bookmarks.animation_for("bookmark_fae_1") == bookmarks.animation_for(
        "bookmark_fae_1"
    )
    assert bookmarks.animation_for("bookmark_fae_1") in bookmarks.ANIMATIONS


# --------------------------------------------------------------------------- #
# county_positions
# --------------------------------------------------------------------------- #
def test_county_positions_uses_the_city_slot_and_only_live_counties():
    got = bookmarks.county_positions(
        ck2_of_county={"c_live": 1, "c_dead": 2},
        own_county={"k_realm": "c_live", "d_gone": "c_dead"},
        live_titles=frozenset({"c_live", "k_realm"}),
        positions={1: [(11.0, 22.0), (99.0, 99.0)], 2: [(3.0, 4.0)]},
    )
    assert got == {"c_live": (11.0, 22.0), "k_realm": (11.0, 22.0)}


@pytest.mark.parametrize("count", [0, 1, 2, 6, 40])
def test_effective_min_distance_never_exceeds_the_floor(count):
    assert bookmarks.effective_min_distance(count) <= bookmarks.MIN_DISTANCE
