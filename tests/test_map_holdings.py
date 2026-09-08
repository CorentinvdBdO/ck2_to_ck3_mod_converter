"""Tests for the barony set: which CK2 holdings exist at a date."""

from __future__ import annotations

import pytest

from ck2ck3.map import holdings

WATERDEEP = """
# c_waterdeep
title = c_waterdeep
max_settlements = 7

b_castle_waterdeep = castle
#b_castle_ward=castle

culture = shield_dwarf
terrain = farmlands

952.1.1 = {
\tb_the_plinth = temple # the Spires of the Morning
}
974.1.1 = {
\tb_castle_ward = castle
}
1010.1.1 = {
\tb_sea_ward = city
}
1060.1.1 = {
\tb_sea_ward = ct_planar_portal
}
1400.1.1 = {
\tb_late_ward = city
}
"""


@pytest.fixture
def hist(tmp_path):
    p = tmp_path / "1 - Waterdeep.txt"
    p.write_text(WATERDEEP, encoding="cp1252")
    return holdings.read_province_file(p)


def test_province_id_and_county_come_from_the_file(hist):
    assert hist.province_id == 1
    assert hist.county == "c_waterdeep"
    assert hist.name == "Waterdeep"
    assert hist.max_settlements == 7


def test_commented_out_holdings_are_not_read(hist):
    """`#b_castle_ward=castle` at the top must not count as built at 0.0.0."""
    assert hist.assignments["b_castle_ward"] == [((974, 1, 1), "castle")]


def test_top_level_assignment_is_dated_at_the_epoch(hist):
    assert hist.assignments["b_castle_waterdeep"] == [(holdings.EPOCH, "castle")]


def test_state_at_a_date_uses_the_last_assignment_before_it(hist):
    assert hist.at((900, 1, 1)) == {"b_castle_waterdeep": "castle"}
    assert hist.at((960, 1, 1)) == {
        "b_castle_waterdeep": "castle",
        "b_the_plinth": "temple",
    }


def test_a_building_does_not_replace_the_holding_type(hist):
    """`b_sea_ward = ct_planar_portal` builds a building, not a holding."""
    assert hist.at((1357, 1, 1))["b_sea_ward"] == "city"


def test_selection_at_the_bookmark_plus_anything_built_later(hist):
    tree_order = ["b_castle_waterdeep", "b_the_plinth", "b_castle_ward", "b_sea_ward"]
    sel = holdings.select(
        hist, bookmark=(1357, 1, 1), latest=(1501, 1, 1), order=tree_order
    )
    assert list(sel.baronies) == tree_order + ["b_late_ward"]
    assert sel.baronies["b_the_plinth"] == "church_holding"
    assert sel.baronies["b_sea_ward"] == "city_holding"
    assert sel.later == frozenset({"b_late_ward"})
    assert sel.built["b_late_ward"] == (1400, 1, 1)
    assert sel.built["b_castle_waterdeep"] == holdings.EPOCH


def test_selection_before_a_holding_exists_leaves_it_out(hist):
    sel = holdings.select(hist, bookmark=(900, 1, 1), latest=(900, 1, 1))
    assert list(sel.baronies) == ["b_castle_waterdeep"]


def test_order_puts_the_capital_first(hist):
    sel = holdings.select(
        hist,
        bookmark=(1357, 1, 1),
        latest=(1357, 1, 1),
        order=["b_the_plinth", "b_castle_waterdeep"],
    )
    assert list(sel.baronies)[:2] == ["b_the_plinth", "b_castle_waterdeep"]


def test_ck2_holding_types_map_to_the_four_ck3_ones():
    assert holdings.CK2_TO_CK3_HOLDING["castle"] == "castle_holding"
    assert holdings.CK2_TO_CK3_HOLDING["city"] == "city_holding"
    assert holdings.CK2_TO_CK3_HOLDING["temple"] == "church_holding"
    assert holdings.CK2_TO_CK3_HOLDING["tribal"] == "tribal_holding"
    assert holdings.CK2_TO_CK3_HOLDING["nomad"] == "tribal_holding"
    assert set(holdings.CK2_TO_CK3_HOLDING.values()) == {
        "castle_holding",
        "city_holding",
        "church_holding",
        "tribal_holding",
    }


def test_non_barony_holdings_are_separated_not_dropped(tmp_path):
    p = tmp_path / "9 - Fortville.txt"
    p.write_text(
        "title = c_fortville\nb_fortville = castle\n"
        "1200.1.1 = { b_the_fort = fort b_the_shop = trade_post }\n",
        encoding="cp1252",
    )
    hist = holdings.read_province_file(p)
    sel = holdings.select(hist, bookmark=(1357, 1, 1), latest=(1501, 1, 1))
    assert list(sel.baronies) == ["b_fortville"]
    assert sorted(sel.non_barony) == [("b_the_fort", "fort"), ("b_the_shop", "trade_post")]
    csv = holdings.render_nonbarony_csv({9: sel}, names={9: "Fortville"})
    assert "b_the_fort,fort" in csv
    assert "no CK3 holding tier" in csv


def test_a_file_with_no_numeric_prefix_is_skipped(tmp_path):
    p = tmp_path / "readme.txt"
    p.write_text("title = c_nowhere\n", encoding="cp1252")
    assert holdings.read_province_file(p) is None


def test_read_dir_keys_by_province_id(tmp_path):
    (tmp_path / "3 - Athkatla.txt").write_text(
        "title = c_athkatla\nb_athkatla = city\n", encoding="cp1252"
    )
    (tmp_path / "10 - Amn.txt").write_text(
        "title = c_amn\nb_amn = tribal\n", encoding="cp1252"
    )
    got = holdings.read_dir(tmp_path)
    assert sorted(got) == [3, 10]
    assert got[10].county == "c_amn"
