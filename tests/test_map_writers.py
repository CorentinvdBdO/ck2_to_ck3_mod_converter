"""Tests for the CK3 ``map_data`` / ``common`` writers."""

from __future__ import annotations

import pytest

from ck2ck3.map import writers
from ck2ck3.map.ck2read import Ck2Adjacency, Ck2GeoRegion
from ck2ck3.map.idmap import Ck3Province, IdMap


def prov(i, rgb=(1, 2, 3), name="P", **kw) -> Ck3Province:
    return Ck3Province(id=i, rgb=rgb, name=name, ck2_id=i, **kw)


def make_idmap(provinces: list[Ck3Province]) -> IdMap:
    return IdMap(
        provinces=provinces,
        ck2_to_ck3={p.ck2_id: p.id for p in provinces if p.ck2_id is not None},
        dropped=[],
        padding=provinces[-1],
    )


# --------------------------------------------------------------------------- #
# id list formatting
# --------------------------------------------------------------------------- #
def test_to_ranges_collapses_runs():
    assert writers.to_ranges([1, 2, 3, 5, 7, 8]) == [(1, 3), (5, 5), (7, 8)]


def test_to_ranges_sorts_and_dedupes():
    assert writers.to_ranges([3, 1, 2, 2]) == [(1, 3)]


def test_format_id_lists_uses_range_for_runs_and_list_for_the_rest():
    lines = writers.format_id_lists("sea_zones", [1, 2, 3, 4, 10, 20, 21])
    assert "sea_zones = RANGE { 1 4 }" in lines
    # a run of 2 (20 21) and a single (10) are cheaper as one LIST
    assert any(line.startswith("sea_zones = LIST {") for line in lines)
    listed = [ln for ln in lines if "LIST" in ln][0]
    assert "10" in listed and "20" in listed and "21" in listed


def test_format_id_lists_wraps_long_lists():
    lines = writers.format_id_lists(
        "lakes", [i for i in range(0, 100, 2)], per_line=5
    )
    assert all(len(ln.split("{")[1].split("}")[0].split()) <= 5 for ln in lines)


def test_format_id_lists_is_empty_for_no_ids():
    assert writers.format_id_lists("lakes", []) == []


# --------------------------------------------------------------------------- #
# definition.csv
# --------------------------------------------------------------------------- #
def test_definition_csv_starts_with_the_zero_row(tmp_path):
    p = tmp_path / "definition.csv"
    writers.write_definition_csv([prov(1, (10, 20, 30), "Waterdeep")], p)
    lines = p.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "0;0;0;0;x;x;"


def test_definition_csv_row_format_has_a_trailing_semicolon(tmp_path):
    p = tmp_path / "definition.csv"
    writers.write_definition_csv([prov(1, (10, 20, 30), "Waterdeep")], p)
    assert p.read_text(encoding="utf-8").splitlines()[1] == "1;10;20;30;Waterdeep;x;"


def test_definition_csv_has_no_bom(tmp_path):
    p = tmp_path / "definition.csv"
    writers.write_definition_csv([prov(1)], p)
    assert not p.read_bytes().startswith(b"\xef\xbb\xbf")


def test_definition_csv_replaces_semicolons_in_names(tmp_path):
    p = tmp_path / "definition.csv"
    writers.write_definition_csv([prov(1, name="A;B")], p)
    assert "A,B" in p.read_text(encoding="utf-8")


def test_definition_csv_names_an_unnamed_province(tmp_path):
    p = tmp_path / "definition.csv"
    writers.write_definition_csv([prov(4, name="")], p)
    assert "province_4" in p.read_text(encoding="utf-8")


def test_definition_csv_rejects_duplicate_colours(tmp_path):
    with pytest.raises(ValueError, match="share colour"):
        writers.write_definition_csv(
            [prov(1, (5, 5, 5)), prov(2, (5, 5, 5))], tmp_path / "d.csv"
        )


def test_definition_csv_rejects_duplicate_ids(tmp_path):
    with pytest.raises(ValueError, match="duplicate CK3 province id"):
        writers.write_definition_csv(
            [prov(1, (5, 5, 5)), prov(1, (6, 6, 6))], tmp_path / "d.csv"
        )


# --------------------------------------------------------------------------- #
# default.map
# --------------------------------------------------------------------------- #
def _default_map(tmp_path, **kw) -> str:
    m = make_idmap(
        [
            prov(1),
            prov(2, is_sea=True),
            prov(3, is_sea=True),
            prov(4, is_sea=True),
            prov(5, is_lake=True),
            prov(6, is_river=True),
            prov(7, is_impassable=True),
            Ck3Province(id=8, rgb=(0, 0, 96), name="Pad", ck2_id=None, is_sea=True),
        ]
    )
    p = tmp_path / "default.map"
    writers.write_default_map(m, p, **kw)
    return p.read_text(encoding="utf-8")


def test_default_map_loads_the_heightmap_through_the_descriptor(tmp_path):
    """CK3 reads heightmap.heightmap, never heightmap.png directly."""
    text = _default_map(tmp_path)
    assert 'topology = "heightmap.heightmap"' in text
    assert "heightmap.png" not in text


def test_default_map_leaves_the_vanilla_commented_keys_commented(tmp_path):
    text = _default_map(tmp_path)
    for line in (
        "#max_provinces",
        '#positions = "positions.txt"',
        '#climate = "climate.txt"',
        '#terrain_definition = "terrain.txt"',
    ):
        assert line in text


def test_default_map_separates_seas_lakes_rivers_and_impassable(tmp_path):
    text = _default_map(tmp_path)
    assert "sea_zones = RANGE { 2 4 }" in text
    assert "lakes = LIST { 5 }" in text
    assert "river_provinces = LIST { 6 }" in text
    assert "impassable_mountains = LIST { 7 }" in text


def test_default_map_never_lists_a_river_province_as_a_sea_zone(tmp_path):
    text = _default_map(tmp_path)
    sea_lines = [ln for ln in text.splitlines() if ln.startswith("sea_zones")]
    assert not any(" 6 " in f" {ln} " for ln in sea_lines)


def test_default_map_keeps_the_ck2_sea_zone_names_as_comments(tmp_path):
    text = _default_map(tmp_path, sea_zone_names={2: "Trackless Sea", 3: "Trackless Sea"})
    assert "# Trackless Sea" in text


def test_default_map_says_none_rather_than_emitting_an_empty_key(tmp_path):
    m = make_idmap([prov(1), Ck3Province(id=2, rgb=(0, 0, 96), name="Pad", ck2_id=None, is_sea=True)])
    p = tmp_path / "default.map"
    writers.write_default_map(m, p)
    text = p.read_text(encoding="utf-8")
    assert "lakes = " not in text
    assert "# none" in text


# --------------------------------------------------------------------------- #
# adjacencies.csv
# --------------------------------------------------------------------------- #
def test_adjacencies_header_matches_ck3(tmp_path):
    m = make_idmap([prov(1), prov(2), prov(3)])
    p = tmp_path / "adjacencies.csv"
    writers.write_adjacencies_csv([], m, p)
    assert p.read_text(encoding="utf-8").splitlines()[0] == (
        "From;To;Type;Through;start_x;start_y;stop_x;stop_y;Comment"
    )


def test_adjacencies_remaps_ids_and_maps_the_type(tmp_path):
    m = make_idmap([prov(10), prov(20), prov(30)])
    m.ck2_to_ck3 = {10: 1, 20: 2, 30: 3}
    p = tmp_path / "adjacencies.csv"
    n = writers.write_adjacencies_csv(
        [Ck2Adjacency(10, 20, "sea", 30, "strait")], m, p
    )
    assert n == 1
    assert p.read_text(encoding="utf-8").splitlines()[1] == (
        "1;2;sea;3;-1;-1;-1;-1;strait"
    )


def test_adjacencies_ck2_major_river_becomes_river_large(tmp_path):
    """CK3 accepts only `sea` and `river_large` as adjacency types."""
    m = make_idmap([prov(1), prov(2)])
    p = tmp_path / "adjacencies.csv"
    writers.write_adjacencies_csv([Ck2Adjacency(1, 2, "major_river", -1, "")], m, p)
    assert ";river_large;" in p.read_text(encoding="utf-8")


def test_adjacencies_drops_rows_whose_endpoint_was_lost(tmp_path):
    m = make_idmap([prov(1), prov(2)])
    log: list[str] = []
    p = tmp_path / "adjacencies.csv"
    n = writers.write_adjacencies_csv(
        [Ck2Adjacency(1, 99, "sea", -1, "gone")], m, p, dropped_log=log
    )
    assert n == 0
    assert log and "endpoint lost" in log[0]


def test_adjacencies_keeps_the_row_but_blanks_a_lost_through(tmp_path):
    m = make_idmap([prov(1), prov(2)])
    log: list[str] = []
    p = tmp_path / "adjacencies.csv"
    writers.write_adjacencies_csv(
        [Ck2Adjacency(1, 2, "sea", 99, "c")], m, p, dropped_log=log
    )
    assert ";sea;-1;" in p.read_text(encoding="utf-8")
    assert log and "set -1" in log[0]


# --------------------------------------------------------------------------- #
# climate / island_region / geographical_regions
# --------------------------------------------------------------------------- #
def test_climate_remaps_ids_and_emits_all_three_keys(tmp_path):
    m = make_idmap([prov(1), prov(2), prov(3)])
    m.ck2_to_ck3 = {10: 1, 20: 2, 30: 3}
    p = tmp_path / "climate.txt"
    writers.write_climate({"severe_winter": [10, 99], "mild_winter": [30]}, m, p)
    text = p.read_text(encoding="utf-8")
    assert "mild_winter = {" in text and "normal_winter = {" in text
    assert "severe_winter = {" in text
    assert "\t1\n" in text and "99" not in text


def test_island_region_uses_provinces_not_duchies(tmp_path):
    m = make_idmap([prov(1), prov(2)])
    m.ck2_to_ck3 = {223: 1, 224: 2}
    p = tmp_path / "island_region.txt"
    writers.write_island_region({"region_mintarn": [223, 224]}, m, p)
    text = p.read_text(encoding="utf-8")
    assert "region_mintarn = {" in text
    assert "provinces = { 1 2 }" in text


def test_island_region_comments_out_a_region_that_lost_everything(tmp_path):
    m = make_idmap([prov(1)])
    m.ck2_to_ck3 = {}
    p = tmp_path / "island_region.txt"
    writers.write_island_region({"region_gone": [999]}, m, p)
    assert "# region_gone: every province lost" in p.read_text(encoding="utf-8")


def test_geographical_regions_declare_children_before_parents(tmp_path):
    """CK3 requires a sub-region to be declared before the region using it."""
    m = make_idmap([prov(1)])
    regions = [
        Ck2GeoRegion(name="parent", regions=["child"]),
        Ck2GeoRegion(name="child", duchies=["d_waterdeep"]),
    ]
    p = tmp_path / "regions.txt"
    writers.write_geographical_regions(regions, m, p)
    text = p.read_text(encoding="utf-8")
    assert text.index("child = {") < text.index("parent = {")


def test_geographical_regions_pass_duchy_keys_through_unchanged(tmp_path):
    m = make_idmap([prov(1)])
    p = tmp_path / "regions.txt"
    writers.write_geographical_regions(
        [Ck2GeoRegion(name="r", duchies=["d_waterdeep", "d_leilon"])], m, p
    )
    assert "duchies = { d_waterdeep d_leilon }" in p.read_text(encoding="utf-8")


def test_geographical_regions_survive_a_reference_cycle(tmp_path):
    m = make_idmap([prov(1)])
    regions = [
        Ck2GeoRegion(name="a", regions=["b"]),
        Ck2GeoRegion(name="b", regions=["a"]),
    ]
    p = tmp_path / "regions.txt"
    writers.write_geographical_regions(regions, m, p)
    text = p.read_text(encoding="utf-8")
    assert "a = {" in text and "b = {" in text


# --------------------------------------------------------------------------- #
# province_terrain
# --------------------------------------------------------------------------- #
def test_province_terrain_has_a_bom_and_the_three_default_lines(tmp_path):
    p = tmp_path / "terrain.txt"
    writers.write_province_terrain({5: "hills"}, p, default="plains")
    assert p.read_bytes().startswith(b"\xef\xbb\xbf")
    text = p.read_text(encoding="utf-8-sig")
    assert "default_land=plains" in text
    assert "default_sea=sea" in text
    assert "default_coastal_sea=coastal_sea" in text


def test_province_terrain_rows_are_id_equals_key_sorted(tmp_path):
    p = tmp_path / "terrain.txt"
    writers.write_province_terrain({10: "forest", 2: "hills"}, p)
    lines = [
        ln for ln in p.read_text(encoding="utf-8-sig").splitlines() if "=" in ln
    ]
    assert lines[-2:] == ["2=hills", "10=forest"]


# --------------------------------------------------------------------------- #
# small files
# --------------------------------------------------------------------------- #
def test_continent_lists_the_land_provinces(tmp_path):
    p = tmp_path / "continent.txt"
    writers.write_continent(p, name="fae_continent", province_ids=[3, 1, 2])
    text = p.read_text(encoding="utf-8")
    assert "fae_continent = {" in text and "id = 1" in text
    assert "1 2 3" in text
