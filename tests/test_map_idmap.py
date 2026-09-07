"""Tests for the CK2 -> CK3 province id remap."""

from __future__ import annotations

import csv

import pytest

from ck2ck3.map import idmap
from ck2ck3.map.ck2read import Ck2Province

PAD = (0, 0, 96)


def provs(*specs: tuple[int, tuple[int, int, int], str]) -> list[Ck2Province]:
    return [Ck2Province(id=i, rgb=c, name=n) for i, c, n in specs]


FIVE = provs(
    (1, (10, 0, 0), "Waterdeep"),
    (3, (0, 10, 0), "Daggerford"),   # id 2 does not exist in CK2
    (7, (0, 0, 10), "Trackless Sea"),
    (8, (0, 0, 11), "Lake Ashaba"),
    (9, (0, 0, 12), "River Chionthar"),
)


def build(surviving=None, **kw):
    return idmap.build(
        FIVE,
        surviving if surviving is not None else {1, 3, 7, 8, 9},
        sea_ids=kw.pop("sea_ids", {7, 8, 9}),
        lake_ids=kw.pop("lake_ids", {8}),
        river_ids=kw.pop("river_ids", {9}),
        padding_rgb=PAD,
        padding_name="Padding",
        **kw,
    )


def test_ids_are_dense_and_start_at_one():
    m = build()
    assert [p.id for p in m.provinces] == [1, 2, 3, 4, 5, 6]  # 5 CK2 + padding


def test_sparse_ck2_ids_are_compacted_in_ascending_order():
    m = build()
    assert m.ck2_to_ck3 == {1: 1, 3: 2, 7: 3, 8: 4, 9: 5}


def test_padding_ocean_is_appended_last_as_a_sea_province():
    m = build()
    assert m.padding.id == 6
    assert m.padding.ck2_id is None
    assert m.padding.is_sea and m.padding.is_water


def test_dropped_provinces_are_reported_and_leave_no_gap():
    m = build(surviving={1, 7})
    assert m.dropped == [3, 8, 9]
    assert m.ck2_to_ck3 == {1: 1, 7: 2}
    assert [p.id for p in m.provinces] == [1, 2, 3]


def test_remap_ids_silently_drops_lost_ids():
    m = build(surviving={1, 7})
    assert m.remap_ids([1, 3, 7, 99]) == [1, 2]


def test_sea_lake_and_river_are_mutually_exclusive():
    """CK3 rejects an id that is in both river_provinces and sea_zones."""
    m = build()
    by_ck2 = {p.ck2_id: p for p in m.provinces if p.ck2_id is not None}
    sea, lake, river = by_ck2[7], by_ck2[8], by_ck2[9]
    assert (sea.is_sea, sea.is_lake, sea.is_river) == (True, False, False)
    assert (lake.is_sea, lake.is_lake, lake.is_river) == (False, True, False)
    assert (river.is_sea, river.is_lake, river.is_river) == (False, False, True)
    assert all(p.is_water for p in (sea, lake, river))


def test_land_is_not_water():
    m = build()
    land = next(p for p in m.provinces if p.ck2_id == 1)
    assert not land.is_water and not land.is_impassable


def test_impassable_is_carried_through():
    m = build(impassable_ids={1})
    assert next(p for p in m.provinces if p.ck2_id == 1).is_impassable


def test_padding_colour_colliding_with_a_province_is_rejected():
    with pytest.raises(ValueError, match="collides"):
        idmap.build(
            FIVE,
            {1},
            sea_ids=set(),
            lake_ids=set(),
            padding_rgb=(10, 0, 0),
            padding_name="Padding",
        )


@pytest.mark.parametrize("reserved", [(0, 0, 0), (255, 255, 255)])
def test_black_and_white_are_rejected_as_padding(reserved):
    with pytest.raises(ValueError, match="must not be"):
        idmap.build(
            FIVE,
            {1},
            sea_ids=set(),
            lake_ids=set(),
            padding_rgb=reserved,
            padding_name="Padding",
        )


def test_id_map_csv_records_survivors_and_losses(tmp_path):
    m = build(surviving={1, 7})
    p = tmp_path / "province_id_map.csv"
    idmap.write_id_map_csv(m, p)
    rows = list(csv.DictReader(p.open(encoding="utf-8")))
    assert rows[0]["ck2_id"] == "1" and rows[0]["ck3_id"] == "1"
    assert rows[0]["kind"] == "land"
    assert rows[1]["kind"] == "sea"
    assert rows[2]["ck2_id"] == "" and rows[2]["name"] == "Padding"
    dropped = [r for r in rows if r["kind"] == "dropped"]
    assert {r["ck2_id"] for r in dropped} == {"3", "8", "9"}
