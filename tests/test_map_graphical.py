"""Every land province needs exactly one CK3 ``graphical_*`` region."""

from __future__ import annotations

from ck2ck3.map import graphical
from ck2ck3.map.holdings import ProvinceHistory
from ck2ck3.map.idmap import Ck3Province, IdMap


def make_idmap(pairs: list[tuple[int, int]]) -> IdMap:
    """``[(ck3 id, ck2 id)]`` -> an IdMap where several CK3 ids share a CK2 one."""
    provinces = [
        Ck3Province(id=ck3, rgb=(1, 2, 3), name=f"P{ck3}", ck2_id=ck2)
        for ck3, ck2 in pairs
    ]
    ck2_to_all: dict[int, list[int]] = {}
    for ck3, ck2 in pairs:
        ck2_to_all.setdefault(ck2, []).append(ck3)
    return IdMap(
        provinces=provinces,
        ck2_to_ck3={ck2: ids[0] for ck2, ids in ck2_to_all.items()},
        dropped=[],
        padding=provinces[-1],
        ck2_to_all=ck2_to_all,
    )


def history(province_id: int, cultures: list[tuple[tuple[int, int, int], str]]):
    return ProvinceHistory(
        province_id=province_id,
        county=f"c_{province_id}",
        name=str(province_id),
        source=f"{province_id}.txt",
        cultures=list(cultures),
    )


def test_region_of_ck2_gfx_reads_through_the_building_gfx_column():
    """The join is CK2 graphical culture -> overrides/gfx_of_culture_group.csv
    building_gfx -> the vanilla region shipping that building set."""
    table = graphical.region_of_ck2_gfx(
        {
            "chinesegfx": "chinese_building_gfx",
            "arabicgfx": "mena_building_gfx",
            "drowgfx": "western_building_gfx",
            "beholdergfx": "no_such_building_gfx",
        }
    )
    assert table["chinesegfx"] == "graphical_east_asia"
    assert table["arabicgfx"] == "graphical_mena"
    assert table["drowgfx"] == "graphical_western"
    assert "beholdergfx" not in table  # falls through to the caller's default


def test_every_land_province_is_placed_exactly_once():
    """Both errors this fixes are per-province: "has no visual geographical
    region assigned" (3904) and "multiple entries for the province" (130)."""
    idmap = make_idmap([(10, 1), (11, 1), (20, 2), (30, 3)])
    buckets = graphical.assign(
        history={
            1: history(1, [((1, 1, 1), "shou")]),
            2: history(2, [((1, 1, 1), "calishite")]),
            # province 3 has no history file at all
        },
        idmap=idmap,
        land_ck3={10, 11, 20, 30},
        graphical_culture_of_culture={"shou": "chinesegfx", "calishite": "arabicgfx"},
        region_of_gfx={
            "chinesegfx": "graphical_east_asia",
            "arabicgfx": "graphical_mena",
        },
        bookmark=(1357, 1, 1),
    )
    placed = [i for ids in buckets.values() for i in ids]
    assert sorted(placed) == [10, 11, 20, 30]
    assert len(placed) == len(set(placed))
    assert buckets["graphical_east_asia"] == [10, 11]
    assert buckets["graphical_mena"] == [20]
    assert 30 in buckets[graphical.DEFAULT_GRAPHICAL_REGION]


def test_water_provinces_are_left_out():
    idmap = make_idmap([(10, 1), (11, 1)])
    buckets = graphical.assign(
        history={1: history(1, [((1, 1, 1), "shou")])},
        idmap=idmap,
        land_ck3={10},
        graphical_culture_of_culture={"shou": "chinesegfx"},
        region_of_gfx={"chinesegfx": "graphical_east_asia"},
        bookmark=(1357, 1, 1),
    )
    assert [i for ids in buckets.values() for i in ids] == [10]


def test_the_culture_in_effect_at_the_bookmark_wins():
    """CK2 lets a province change culture; a graphical region has to follow the
    bookmark, not the first line of the file."""
    hist = history(1, [((1, 1, 1), "shou"), ((1300, 1, 1), "calishite")])
    assert hist.culture_at((1357, 1, 1)) == "calishite"
    assert hist.culture_at((1200, 1, 1)) == "shou"
    assert hist.culture_at((0, 1, 1)) is None


def test_all_seven_buckets_exist_even_when_empty():
    buckets = graphical.assign(
        history={},
        idmap=make_idmap([(10, 1)]),
        land_ck3=set(),
        graphical_culture_of_culture={},
        region_of_gfx={},
        bookmark=(1357, 1, 1),
    )
    assert sorted(buckets) == sorted(name for name, _ in graphical.GRAPHICAL_REGIONS)
