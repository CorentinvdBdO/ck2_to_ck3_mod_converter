"""The CK2 readers of lane ``titles-history``.

Fixture snippets first (CLAUDE.md: every reader gets one), the whole Faerun
clone behind the ``slow`` marker.  These replace the ones that lived in
``tests/test_ck2_readers.py`` against the deleted ``src/titles/all_titles.py``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ck2ck3.pdx import Date
from ck2ck3.titles import ck2read

REPO = Path(__file__).resolve().parents[1]
FAERUN = REPO / "Faerun" / "Faerun"


def write_cp1252(path: Path, text: str) -> Path:
    path.write_bytes(text.encode("cp1252"))
    return path


# -- landed titles ----------------------------------------------------------
TITLES = """\
# the far north
e_north = {
\tcolor={ 10 20 30 }
\tcolor2 = rgb { 1 2 3 }
\tculture = illuskan
\tshort_name = yes
\tgreen_elf = Cormanthor
\tholy_site = triadic
\tholy_site = mercantile
\tallow = { always = no }

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
    (empire,) = ck2read.read_landed_titles(path)
    assert (empire.id, empire.tier, empire.prefix) == ("e_north", 1, "e")
    assert empire.color == (10, 20, 30)
    assert empire.color2 == (1, 2, 3)
    assert empire.flag("short_name") is True
    assert empire.cultural_names == {"green_elf": "Cormanthor"}
    assert empire.keywords["culture"] == "illuskan"
    assert empire.leading_comments == ["# the far north"]
    assert "allow" in empire.blocks
    flat = ck2read.flatten([empire])
    assert [t.id for t in flat] == [
        "e_north",
        "k_waterdeep",
        "c_waterdeep",
        "b_castle_waterdeep",
    ]
    assert [t.tier for t in flat] == [1, 2, 4, 5]
    assert ck2read.index([empire])["c_waterdeep"].parent == "k_waterdeep"


def test_capital_is_a_province_id_and_keeps_its_comment(tmp_path):
    path = write_cp1252(tmp_path / "landed_titles.txt", TITLES)
    kingdom = ck2read.read_landed_titles(path)[0].children[0]
    # CK2 `capital` names a PROVINCE, not a title (verified in Faerun).
    assert kingdom.capital == "1"
    assert kingdom.capital_comment == "# Waterdeep"


def test_float_colours_are_normalised_to_0_255(tmp_path):
    path = write_cp1252(
        tmp_path / "landed_titles.txt", "e_x = {\n\tcolor = { 0.0 0.5 1.0 }\n}\n"
    )
    assert ck2read.read_landed_titles(path)[0].color == (0, 128, 255)


def test_a_group_marker_is_told_from_a_group_cultural_name(tmp_path):
    path = write_cp1252(
        tmp_path / "landed_titles.txt",
        "e_x = {\n\tdwarf_group = yes\n}\ne_y = {\n\tdwarf_group = Hollowbold\n}\n",
    )
    marker, name = ck2read.read_landed_titles(path)
    assert marker.group_markers == ["dwarf_group"]
    assert marker.cultural_names == {}
    assert name.cultural_names == {"dwarf_group": "Hollowbold"}


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
\tremove_settlement = b_castle_waterdeep
}
"""


def test_read_province_history(tmp_path):
    path = write_cp1252(tmp_path / "1 - Waterdeep.txt", PROVINCE)
    province = ck2read.read_province_history(1, path)
    assert province.title == "c_waterdeep"
    assert province.max_settlements == 7
    assert province.terrain == "farmlands"
    assert province.culture == "shield_dwarf"
    assert province.religion == "dwarven_pantheon"
    # a commented-out `#b_sea_ward=city` is a comment, not a holding
    assert province.holdings == {"b_castle_waterdeep": "castle"}
    assert (Date(34, 1, 1), "b_castle_waterdeep", "tribal") in province.holding_changes
    assert (Date(34, 1, 1), "culture", "monster") in province.dated
    assert (
        Date(1350, 1, 1),
        "remove_settlement",
        "b_castle_waterdeep",
    ) in province.dated


def test_read_province_histories_keys_on_the_filename_id(tmp_path):
    write_cp1252(tmp_path / "7 - Amphail.txt", PROVINCE)
    write_cp1252(tmp_path / "not a province.txt", PROVINCE)
    assert list(ck2read.read_province_histories(tmp_path)) == [7]


# -- title history ----------------------------------------------------------
TITLE_HISTORY = """\
# k_cormyr
holder = 20001
26.1.2 = {
\tactive = yes
\tlaw = true_cognatic_succession
\tlaw = succ_primogeniture
\tholder = 20001 # Faerlthann
}
55.1.1 = { holder = 20002 }
"""


def test_read_title_history_separates_toplevel_from_dated(tmp_path):
    path = write_cp1252(tmp_path / "k_cormyr.txt", TITLE_HISTORY)
    history = ck2read.read_title_history(path)
    assert history.id == "k_cormyr"
    assert [n.key for n in history.toplevel] == ["holder"]
    assert [str(d) for d in history.dates()] == ["26.1.2", "55.1.1"]
    first = history.dated[0][1]
    assert [n.key for n in first] == ["active", "law", "law", "holder"]


# -- bookmarks --------------------------------------------------------------
BOOKMARK = """\
bm_test = {
\tname = "BM_TEST"
\tdesc = "BM_TEST_DESC"
\tdate = 1357.1.1
\tera = yes

\tselectable_character = {
\t\tid = 52101
\t\tage = 447
\t\tname = ERA_CHAR_NAME_ZHENGYI
\t\ttitle = k_vaasa

\t\tcharacter = {
\t\t\tdynasty = 7743
\t\t\treligion = abyssal_cult
\t\t\tculture = lich
\t\t\tgovernment = "feudal_government"
\t\t}
\t}
}
"""


def test_read_bookmarks(tmp_path):
    path = write_cp1252(tmp_path / "00_bookmarks.txt", BOOKMARK)
    (bookmark,) = ck2read.read_bookmarks(path)
    assert bookmark.id == "bm_test"
    assert bookmark.date == Date(1357, 1, 1)
    assert bookmark.era is True
    (character,) = bookmark.characters
    assert character.ck2_id == "52101"
    assert character.age == 447
    assert character.title == "k_vaasa"
    assert character.dynasty == "7743"
    assert character.culture == "lich"
    assert character.government == "feudal_government"


# -- cultures ---------------------------------------------------------------
def test_read_culture_groups_skips_group_keywords(tmp_path):
    write_cp1252(
        tmp_path / "human.txt",
        "abeiran_group = {\n"
        "\tgraphical_cultures = { occitangfx }\n"
        "\tgontese = {\n\t\tcolor = { 1 1 1 }\n\t}\n"
        "\tturmishan = {\n\t\tcolor = { 2 2 2 }\n\t}\n"
        "}\n",
    )
    groups = ck2read.read_culture_groups(tmp_path)
    assert groups == {"abeiran_group": ["gontese", "turmishan"]}
    assert ck2read.culture_of_group(groups)["gontese"] == "abeiran_group"


# -- characters -------------------------------------------------------------
def test_read_character_index(tmp_path):
    write_cp1252(
        tmp_path / "chars.txt",
        '2 = {\n\tname = "Bhaal"\n\tfemale = yes\n'
        "\t1240.5.4 = { birth = yes }\n\t1358.9.16 = { death = yes }\n}\n",
    )
    index = ck2read.read_character_index(tmp_path)
    assert index["2"].name == "Bhaal"
    assert index["2"].female is True
    assert index["2"].birth == Date(1240, 5, 4)
    assert index["2"].death == Date(1358, 9, 16)


# -- the real Faerun files --------------------------------------------------
@pytest.mark.slow
@pytest.mark.skipif(not FAERUN.is_dir(), reason="Faerun/ clone absent")
def test_faerun_landed_titles_counts():
    flat = ck2read.flatten(
        ck2read.read_landed_titles_dir(FAERUN / "common" / "landed_titles")
    )
    by_tier: dict[str, int] = {}
    for title in flat:
        by_tier[title.prefix] = by_tier.get(title.prefix, 0) + 1
    # docs/formats_ck2_landed_titles.md, re-measured by
    # scripts/survey_ck2_titles.py
    assert by_tier == {"e": 65, "k": 267, "d": 979, "c": 2132, "b": 15356}
    assert len(flat) == 18799
    waterdeep = ck2read.index(
        ck2read.read_landed_titles_dir(FAERUN / "common" / "landed_titles")
    )["c_waterdeep"]
    assert waterdeep.color == (131, 206, 243)


@pytest.mark.slow
@pytest.mark.skipif(not FAERUN.is_dir(), reason="Faerun/ clone absent")
def test_faerun_every_cultural_name_key_is_a_culture_or_group():
    flat = ck2read.flatten(
        ck2read.read_landed_titles_dir(FAERUN / "common" / "landed_titles")
    )
    groups = ck2read.read_culture_groups(FAERUN / "common" / "cultures")
    cultures = {c for members in groups.values() for c in members}
    keys = {k for t in flat for k in t.cultural_names}
    assert keys - cultures - set(groups) == set()
    # seven of the 226 keys are culture GROUPS, which CK3 cannot key on
    assert len(keys & set(groups)) == 7


@pytest.mark.slow
@pytest.mark.skipif(not FAERUN.is_dir(), reason="Faerun/ clone absent")
def test_faerun_title_history_has_no_toplevel_keys_but_republics_are_baronies():
    histories = ck2read.read_title_histories(FAERUN / "history" / "titles")
    assert len(histories) == 3420
    assert sum(len(h.toplevel) for h in histories.values()) == 0
    patricians = ck2read.republic_titles(
        FAERUN / "common" / "landed_titles" / "republics.txt"
    )
    assert len(patricians) == 161
    assert all(p.startswith("b_") for p in patricians)
