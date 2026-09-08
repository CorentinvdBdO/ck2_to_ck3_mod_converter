"""Tests for the CK2 landed_titles hierarchy reader."""

from __future__ import annotations

import pytest

from ck2ck3.map import ck2titles

SAMPLE = """
e_north = {
\tcolor = { 1 2 3 }
\tk_sword = {
\t\tcapital = 5
\t\td_waterdeep = {
\t\t\tc_waterdeep = {
\t\t\t\tb_castle_waterdeep = {}
\t\t\t\tb_sea_ward = {}
\t\t\t}
\t\t\tc_rassalantar = {
\t\t\t\tb_rassalantar = {}
\t\t\t}
\t\t}
\t}
}
e_south = {
\tk_amn = {
\t\td_athkatla = {
\t\t\tc_athkatla = { b_athkatla = {} }
\t\t}
\t}
}
"""


@pytest.fixture
def tree(tmp_path):
    p = tmp_path / "00_landed_titles.txt"
    p.write_text(SAMPLE, encoding="cp1252")
    return ck2titles.read([p])


def test_every_tier_is_read(tree):
    assert {t.tier for t in tree.titles.values()} == {"e", "k", "d", "c", "b"}
    assert len(tree.of_tier("b")) == 4


def test_path_records_the_whole_ancestry(tree):
    t = tree.titles["b_sea_ward"]
    assert t.path == ("e_north", "k_sword", "d_waterdeep", "c_waterdeep", "b_sea_ward")
    assert t.ancestor("d") == "d_waterdeep"
    assert t.parent == "c_waterdeep"


def test_county_capital_is_the_first_barony_declared(tree):
    assert tree.capital_barony("c_waterdeep") == "b_castle_waterdeep"
    assert tree.county_baronies["c_waterdeep"] == ["b_castle_waterdeep", "b_sea_ward"]


def test_walk_order_is_depth_first_file_order(tree):
    """The id order of definition.csv depends on this."""
    keys = sorted(tree.titles, key=lambda k: tree.titles[k].order)
    assert keys == [
        "e_north",
        "k_sword",
        "d_waterdeep",
        "c_waterdeep",
        "b_castle_waterdeep",
        "b_sea_ward",
        "c_rassalantar",
        "b_rassalantar",
        "e_south",
        "k_amn",
        "d_athkatla",
        "c_athkatla",
        "b_athkatla",
    ]


def test_sort_key_puts_a_duchy_s_baronies_together(tree):
    ck = tree.sort_key
    assert ck("b_castle_waterdeep") < ck("b_sea_ward") < ck("b_rassalantar")
    assert ck("b_rassalantar") < ck("b_athkatla")


def test_non_title_keys_are_ignored(tree):
    assert "capital" not in tree.titles
    assert "color" not in tree.titles


def test_tier_of_rejects_non_titles():
    assert ck2titles.tier_of("c_waterdeep") == "c"
    assert ck2titles.tier_of("capital") is None
    assert ck2titles.tier_of("b_") is None
    assert ck2titles.tier_of("x_foo") is None


def test_a_key_declared_twice_is_reported_not_merged(tmp_path):
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    a.write_text("e_x = { c_dup = { b_one = {} } }", encoding="cp1252")
    b.write_text("e_y = { c_dup = { b_two = {} } }", encoding="cp1252")
    tree = ck2titles.read([a, b])
    assert tree.duplicates == ["c_dup"]
    assert tree.county_baronies["c_dup"] == ["b_one"]
