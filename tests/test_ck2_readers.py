"""The CK2 readers that were migrated off the regex parser.

Fixture snippets first (CLAUDE.md: every reader gets one), then the real
Faerûn files behind the `slow` marker.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from games.ck2.read.modifiers import read_modifiers_file
from games.ck2.read.traits import read_traits_file
from titles.all_titles import (
    flatten_titles,
    open_definitions,
    read_all_titles,
    read_landed_titles,
    read_province_history,
    read_provinces_climate,
)

REPO = Path(__file__).resolve().parents[1]
FAERUN = REPO / "Faerun" / "Faerun"


def write_cp1252(path: Path, text: str) -> Path:
    path.write_bytes(text.encode("cp1252"))
    return path


# -- province history -------------------------------------------------------
PROVINCE = """\
# c_waterdeep
title = c_waterdeep
max_settlements = 7
b_castle_waterdeep = castle
#b_sea_ward=city
culture = shield_dwarf
religion = dwarven_pantheon
terrain = farmlands

34.1.1 = {
\tculture = monster
\tb_castle_waterdeep = tribal
}
1350.1.1={
\tb_sea_ward = ct_spelljammer_port
}
"""


def test_read_province_history(tmp_path):
    path = write_cp1252(tmp_path / "1 - Waterdeep.txt", PROVINCE)
    province = read_province_history(1, path)
    assert province.title == "c_waterdeep"
    assert province.max_settlements == 7
    assert province.terrain == "farmlands"
    assert province.base_culture == "shield_dwarf"
    assert province.base_religion == "dwarven_pantheon"
    assert province.baronies_history["b_castle_waterdeep"].holding == "castle"
    assert province.history["34.1.1"] == {"culture": "monster"}
    assert province.baronies_history["b_castle_waterdeep"].history["34.1.1"] == {
        "holding": "tribal"
    }
    # A barony that only appears in a dated block is created on the fly.
    assert province.baronies_history["b_sea_ward"].holding == "none"


def test_a_commented_out_barony_has_no_base_holding(tmp_path):
    # `#b_sea_ward=city` is a comment, so the barony only exists from the
    # dated block that grants it a holding.
    path = write_cp1252(tmp_path / "1 - X.txt", PROVINCE)
    baronies = read_province_history(1, path).baronies_history
    assert baronies["b_sea_ward"].holding == "none"
    assert baronies["b_sea_ward"].history["1350.1.1"] == {
        "holding": "ct_spelljammer_port"
    }


# -- climate ----------------------------------------------------------------
def test_read_provinces_climate(tmp_path):
    path = write_cp1252(
        tmp_path / "climate.txt",
        "severe_winter = {\n\t4 10\n}\nnormal_winter = {\n\t1 2\n}\n",
    )
    assert read_provinces_climate(path) == {
        4: "severe_winter",
        10: "severe_winter",
        1: "normal_winter",
        2: "normal_winter",
    }


# -- definition.csv ---------------------------------------------------------
def test_open_definitions_keeps_comments_and_cp1252(tmp_path):
    path = write_cp1252(
        tmp_path / "definition.csv",
        "province;red;green;blue;x;x\n"
        "1;255;0;0;Waterdeep;x\n"
        "# a removed province\n"
        "2;0;255;0;Bj\xf8rn;x#note\n",
    )
    rows, id_to_line = open_definitions(path)
    assert rows[0].id == 1 and rows[0].name == "Waterdeep"
    assert rows[1] == "# a removed province"
    assert rows[2].name == "Bj\xf8rn"
    assert rows[2].comment == "note"
    assert set(id_to_line) == {"1", "2"}


# -- landed titles ----------------------------------------------------------
TITLES = """\
e_north = {
\tcolor={ 10 20 30 }
\tcolor2 = rgb { 1 2 3 }
\tculture = illuskan
\tshort_name = yes
\tgreen_elf = Cormanthor

\tk_waterdeep = {
\t\tcapital = 1 # Waterdeep
\t\tc_waterdeep = {
\t\t\tb_castle_waterdeep = {
\t\t\t\tcolor={ 1 1 1 }
\t\t\t}
\t\t}
\t}
}
"""


def test_read_landed_titles_hierarchy(tmp_path):
    path = write_cp1252(tmp_path / "landed_titles.txt", TITLES)
    (empire,) = read_landed_titles(path)
    assert (empire.title_name, empire.rank) == ("e_north", 1)
    assert empire.color == (10, 20, 30)
    assert empire.color2 == (1, 2, 3)
    assert empire.short_name is True
    assert empire.cultural_names == {"green_elf": "Cormanthor"}
    assert empire.extra["culture"] == "illuskan"
    flat = flatten_titles([empire])
    assert [t.title_name for t in flat] == [
        "e_north",
        "k_waterdeep",
        "c_waterdeep",
        "b_castle_waterdeep",
    ]
    assert [t.rank for t in flat] == [1, 2, 4, 5]


def test_capital_keeps_its_comment(tmp_path):
    path = write_cp1252(tmp_path / "landed_titles.txt", TITLES)
    kingdom = read_landed_titles(path)[0].children[0]
    assert kingdom.capital == 1
    assert kingdom.capital_comment == "# Waterdeep"


# -- traits and modifiers ---------------------------------------------------
def test_read_modifiers_file(tmp_path):
    path = write_cp1252(
        tmp_path / "mods.txt",
        "my_modifier = {\n\tis_good = yes\n\tmax_decimals = 2\n}\n",
    )
    modifiers = read_modifiers_file(path)
    assert modifiers["my_modifier"].is_good is True
    assert modifiers["my_modifier"].max_decimals == 2


def test_read_traits_file_splits_fields_from_modifiers(tmp_path):
    path = write_cp1252(
        tmp_path / "traits.txt",
        "brave = {\n\tpersonality = yes\n\tmartial = 2\n\topposites = { craven }\n}\n",
    )
    traits = read_traits_file(path, check_modifiers=True)
    trait = traits["brave"]
    assert trait.personality is True
    assert trait.opposites == ["craven"]
    assert trait.modifiers == {"martial": 2}


def test_read_traits_file_reports_every_unknown_key(tmp_path):
    path = write_cp1252(
        tmp_path / "traits.txt",
        "odd = {\n\tnot_a_modifier = 1\n\talso_not = 2\n}\n",
    )
    with pytest.raises(ValueError) as exc:
        read_traits_file(path, all_modifiers={}, check_modifiers=True)
    assert "also_not, not_a_modifier" in str(exc.value)


# -- real Faerun files ------------------------------------------------------
@pytest.mark.slow
@pytest.mark.skipif(not FAERUN.is_dir(), reason="Faerun/ clone absent")
def test_faerun_landed_titles():
    titles = read_all_titles(FAERUN / "common" / "landed_titles")
    flat = [t for group in titles.values() for t in flatten_titles(group)]
    by_rank: dict[int, int] = {}
    for title in flat:
        by_rank[title.rank] = by_rank.get(title.rank, 0) + 1
    # 2132 counties is the number scripts/faerun_barony_stats.py reports.
    assert by_rank[4] == 2132
    assert by_rank[5] > 15000
    waterdeep = next(t for t in flat if t.title_name == "c_waterdeep")
    assert waterdeep.color == (131, 206, 243)


@pytest.mark.slow
@pytest.mark.skipif(not FAERUN.is_dir(), reason="Faerun/ clone absent")
def test_faerun_climate_and_definitions():
    climate = read_provinces_climate(FAERUN / "map" / "climate.txt")
    assert climate[4] == "severe_winter"
    assert len(climate) > 1000
    rows, id_to_line = open_definitions(FAERUN / "map" / "definition.csv")
    assert len(id_to_line) > 2000


@pytest.mark.slow
@pytest.mark.skipif(not FAERUN.is_dir(), reason="Faerun/ clone absent")
def test_faerun_province_history():
    province = read_province_history(
        1, FAERUN / "history" / "provinces" / "1 - Waterdeep.txt"
    )
    assert province.title == "c_waterdeep"
    assert province.max_settlements == 7
    assert province.baronies_history["b_castle_waterdeep"].holding == "castle"
