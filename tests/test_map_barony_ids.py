"""Tests for barony-keyed CK3 ids, colours, definition.csv and strait remap."""

from __future__ import annotations

import pytest

from ck2ck3.map import bootstrap, idmap, writers
from ck2ck3.map.baronies import Barony, BaronyPlan
from ck2ck3.map.ck2read import Ck2Adjacency, Ck2Province

# CK2: 1 and 2 are counties, 3 is a wasteland, 50 and 51 are sea
CK2 = [
    Ck2Province(1, (10, 10, 10), "Waterdeep"),
    Ck2Province(2, (20, 20, 20), "Rassalantar"),
    Ck2Province(3, (30, 30, 30), "Trollcrag Mountains"),
    Ck2Province(50, (40, 40, 40), "Trackless Sea"),
    Ck2Province(51, (50, 50, 50), "Sword Coast"),
]
SURVIVING = {1, 2, 3, 50, 51}


def _barony(key, county, pid, order, rank=0, holding="castle_holding"):
    return Barony(
        key=key,
        county=county,
        ck2_province=pid,
        holding=holding,
        built=(1000, 1, 1),
        is_capital=(rank == 0),
        order=order,
        rank=rank,
        pixels=1000,
        seed_source="sampled",
        seed_y=1,
        seed_x=1,
    )


def _plan(*baronies):
    p = BaronyPlan(placed=list(baronies))
    for i, b in enumerate(p.placed):
        p.by_province.setdefault(b.ck2_province, []).append(b)
    return p


@pytest.fixture
def ids():
    # hierarchy order deliberately NOT the CK2 province order: province 2's
    # barony is declared before province 1's second barony
    plan = _plan(
        _barony("b_castle_waterdeep", "c_waterdeep", 1, order=10, rank=0),
        _barony("b_sea_ward", "c_waterdeep", 1, order=11, rank=1, holding="city_holding"),
        _barony("b_rassalantar", "c_rassalantar", 2, order=12, rank=0),
    )
    return idmap.build_with_baronies(
        CK2,
        SURVIVING,
        plan,
        sea_ids={50, 51},
        lake_ids=set(),
        river_ids=set(),
        padding_rgb=(0, 0, 96),
        padding_name="Trackless Deep",
    )


def test_land_baronies_come_first_in_hierarchy_order(ids):
    first = [p for p in ids.provinces if p.is_barony]
    assert [p.id for p in first] == [1, 2, 3]
    assert [p.barony for p in first] == [
        "b_castle_waterdeep",
        "b_sea_ward",
        "b_rassalantar",
    ]


def test_unsplit_provinces_follow_in_ascending_ck2_order(ids):
    rest = [p for p in ids.provinces if not p.is_barony and p.ck2_id is not None]
    assert [(p.ck2_id, p.id) for p in rest] == [(3, 4), (50, 5), (51, 6)]


def test_the_padding_ocean_is_last(ids):
    assert ids.padding.id == 7
    assert ids.provinces[-1] is ids.padding


def test_sea_ids_stay_contiguous_so_default_map_uses_a_range(ids):
    seas = [p.id for p in ids.provinces if p.is_sea and p.ck2_id is not None]
    assert seas == [5, 6]
    assert writers.to_ranges(seas) == [(5, 6)]


def test_one_ck2_county_maps_to_all_of_its_baronies(ids):
    assert ids.all_ck3(1) == [1, 2]
    assert ids.all_ck3(2) == [3]
    assert ids.all_ck3(50) == [5]


def test_the_primary_id_of_a_county_is_its_capital_barony(ids):
    assert ids.ck3(1) == 1
    assert ids.by_id()[1].barony == "b_castle_waterdeep"


def test_remap_ids_expands_a_region_to_every_barony(ids):
    """A CK2 region that named a county must name all of its baronies."""
    assert ids.remap_ids([1, 2, 999]) == [1, 2, 3]


def test_labels_map_back_to_ck3_ids(ids):
    assert ids.label_to_id == {1: 1, 2: 2, 3: 3}


# ------------------------------------------------------------------ colours
def test_every_colour_is_unique(ids):
    colours = [p.rgb for p in ids.provinces]
    assert len(set(colours)) == len(colours)


def test_a_barony_never_takes_a_ck2_or_reserved_colour(ids):
    ck2_colours = {p.rgb for p in CK2}
    for p in ids.provinces:
        if p.is_barony:
            assert p.rgb not in ck2_colours
            assert p.rgb not in {(0, 0, 0), (255, 255, 255), (0, 0, 96)}


def test_colour_is_a_stable_function_of_the_barony_id():
    a = idmap.barony_colour("b_castle_waterdeep", set())
    b = idmap.barony_colour("b_castle_waterdeep", set())
    assert a == b
    assert a != idmap.barony_colour("b_sea_ward", set())


def test_a_taken_colour_is_probed_past_deterministically():
    want = idmap.barony_colour("b_x", set())
    second = idmap.barony_colour("b_x", {want})
    assert second != want
    assert second == idmap.barony_colour("b_x", {want})


def test_reserved_colours_are_never_returned():
    black = idmap.barony_colour("b_x", set())
    assert idmap.barony_colour("b_x", {black} | idmap.RESERVED_COLOURS) not in (
        (0, 0, 0),
        (255, 255, 255),
    )


# ----------------------------------------------------------- definition.csv
def test_definition_csv_name_column_is_the_barony_title_id(ids):
    keys = bootstrap.unique_keys(ids.provinces)
    names = bootstrap.definition_names(ids.provinces, keys)
    text = writers.render_definition_csv(ids.provinces, names)
    rows = [line.split(";") for line in text.splitlines()]
    assert rows[0][:5] == ["0", "0", "0", "0", "x"]
    assert rows[1][4] == "b_castle_waterdeep"
    assert rows[2][4] == "b_sea_ward"
    assert rows[3][4] == "b_rassalantar"


def test_definition_csv_keeps_descriptive_names_for_water_and_wasteland(ids):
    keys = bootstrap.unique_keys(ids.provinces)
    names = bootstrap.definition_names(ids.provinces, keys)
    assert names[4] == "TROLLCRAG_MOUNTAINS"
    assert names[5] == "TRACKLESS_SEA"


def test_every_definition_name_has_a_localisation_key(ids):
    keys = bootstrap.unique_keys(ids.provinces)
    names = bootstrap.definition_names(ids.provinces, keys)
    loc = bootstrap.localisation_entries(ids.provinces, keys)
    for name in names.values():
        assert name in loc, name


def test_a_barony_keeps_its_ck2_localised_name(ids):
    keys = bootstrap.unique_keys(ids.provinces)
    loc = bootstrap.localisation_entries(
        ids.provinces, keys, loc_names={"b_castle_waterdeep": "Castle Waterdeep"}
    )
    assert loc["b_castle_waterdeep"] == "Castle Waterdeep"
    assert loc["b_sea_ward"] == bootstrap.humanise("b_sea_ward") == "Sea Ward"


def test_landed_titles_groups_baronies_under_their_ck2_county(ids):
    keys = bootstrap.unique_keys(ids.provinces)
    text, n = bootstrap.render_landed_titles(ids.provinces, keys)
    assert n == 4  # three baronies plus the wasteland's own county
    county = text.split("c_waterdeep = {")[1].split("c_rassalantar")[0]
    assert "b_castle_waterdeep = {" in county
    assert "b_sea_ward = {" in county
    assert text.count("c_waterdeep = {") == 1


def test_province_history_carries_the_real_ck3_holding_type(ids):
    text, _ = bootstrap.render_province_history(ids.provinces)
    blocks = text.split("= {")
    assert "holding = castle_holding" in text
    assert "holding = city_holding" in text
    assert len(blocks) == 5  # 4 land provinces + the split marker


# ------------------------------------------------------- strait endpoint remap
def test_a_strait_attaches_to_the_barony_facing_the_water(ids):
    """CK2 gives no coordinates, so the endpoint is derived from the centroids."""
    centroids = {
        1: (0.0, 0.0),   # b_castle_waterdeep, inland
        2: (0.0, 100.0),  # b_sea_ward, on the sea side
        3: (50.0, 50.0),  # b_rassalantar
        5: (0.0, 200.0),  # the sea being crossed
    }
    from ck2ck3.map.build import _endpoint_picker

    pick = _endpoint_picker(ids, centroids)
    assert pick(1, 50) == 2  # the sea ward, not the capital
    assert pick(2, 50) == 3  # one barony only: no choice to make


def test_adjacencies_use_the_endpoint_picker(ids):
    centroids = {1: (0.0, 0.0), 2: (0.0, 100.0), 3: (50.0, 50.0), 5: (0.0, 200.0)}
    from ck2ck3.map.build import _endpoint_picker

    adj = [Ck2Adjacency(from_id=1, to_id=2, type="sea", through=50, comment="strait")]
    text, kept = writers.render_adjacencies_csv(
        adj, ids, endpoint=_endpoint_picker(ids, centroids)
    )
    assert kept == 1
    row = text.splitlines()[1].split(";")
    assert row[:4] == ["2", "3", "sea", "5"]


def test_without_a_picker_the_capital_barony_is_used(ids):
    adj = [Ck2Adjacency(from_id=1, to_id=2, type="sea", through=50, comment="")]
    text, kept = writers.render_adjacencies_csv(adj, ids)
    assert text.splitlines()[1].split(";")[:2] == ["1", "3"]
