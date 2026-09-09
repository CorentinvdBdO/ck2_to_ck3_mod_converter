"""The three derived tables: holding type, government, succession laws."""

from __future__ import annotations

from pathlib import Path

import pytest

from ck2ck3.titles import tables

REPO = Path(__file__).resolve().parents[1]
GOV_CSV = REPO / "mappings" / "government_map.csv"


# -- holdings ---------------------------------------------------------------
@pytest.mark.parametrize(
    "ck2,ck3",
    [
        ("castle", "castle_holding"),
        ("city", "city_holding"),
        ("temple", "church_holding"),
        ("tribal", "tribal_holding"),
        ("none", "none"),
    ],
)
def test_map_holding(ck2, ck3):
    assert tables.map_holding(ck2) == (ck3, None)


def test_faerun_invented_holdings_fall_back_with_a_note():
    ck3, note = tables.map_holding("ct_spelljammer_port")
    assert ck3 == "city_holding"
    assert "no CK3 holding type" in note


def test_an_unknown_holding_has_no_target():
    assert tables.map_holding("FORT") == (None, None)


# -- governments ------------------------------------------------------------
def test_government_map_csv_loads_and_skips_the_flag_rows():
    mapping = tables.load_government_map(GOV_CSV)
    assert mapping["feudal_government"] == "feudal_government"
    assert mapping["muslim_government"] == "clan_government"
    assert mapping["roman_imperial_government"] == "administrative_government"
    # Faerun disables nomadic_government entirely; the row has no CK3 target
    assert "nomadic_government" not in mapping


def test_explicit_ck2_government_wins():
    mapping = tables.load_government_map(GOV_CSV)
    choice = tables.derive_government(
        title_id="k_x",
        keywords={"tribe": True},
        explicit_ck2="merchant_republic_government",
        government_map=mapping,
    )
    assert choice.government == "republic_government"
    assert choice.derived is False


@pytest.mark.parametrize(
    "keywords,expected",
    [
        ({"mercenary": True}, "feudal_government"),
        ({"holy_order": True}, "feudal_government"),
        ({"pirate": True}, "landless_adventurer_government"),
        ({"tribe": True}, "tribal_government"),
        ({"controls_religion": True}, "theocracy_government"),
        ({"caliphate": True}, "theocracy_government"),
        ({}, "feudal_government"),
    ],
)
def test_government_from_the_title_flags(keywords, expected):
    assert (
        tables.derive_government(title_id="k_x", keywords=keywords).government
        == expected
    )


def test_flag_order_is_mercenary_before_tribe():
    # e_pirates sets pirate, landless, primary AND tribe; the specific flag has
    # to win over the generic tribal one.
    choice = tables.derive_government(
        title_id="e_pirates", keywords={"pirate": True, "tribe": True}
    )
    assert choice.government == "landless_adventurer_government"


def test_a_republics_txt_title_is_a_republic():
    choice = tables.derive_government(
        title_id="b_baram", keywords={}, is_republic=True
    )
    assert choice.government == "republic_government"
    assert "republics.txt" in choice.reason


def test_an_unmappable_ck2_government_falls_back_and_says_so():
    choice = tables.derive_government(
        title_id="k_x", keywords={}, explicit_ck2="nomadic_government"
    )
    assert choice.government == "feudal_government"
    assert "no CK3 target" in choice.reason


# -- succession laws --------------------------------------------------------
def test_order_and_gender_law_are_both_emitted():
    result = tables.map_succession_laws(
        ["true_cognatic_succession", "succ_primogeniture"]
    )
    assert result.laws == ["single_heir_succession_law", "equal_law"]
    assert result.dropped == []


def test_title_order_and_gender_groups_coexist():
    result = tables.map_succession_laws(
        ["succ_feudal_elective", "agnatic_succession"]
    )
    assert result.laws == ["feudal_elective_succession_law", "male_only_law"]


def test_non_succession_laws_are_dropped_with_a_reason():
    result = tables.map_succession_laws(
        ["war_voting_power_1", "centralization_3", "ze_administration_laws_1"]
    )
    assert result.laws == []
    assert [law for law, _ in result.dropped] == [
        "war_voting_power_1",
        "centralization_3",
        "ze_administration_laws_1",
    ]
    assert all("not a succession law" in why for _, why in result.dropped)


def test_an_unknown_law_is_reported_not_guessed():
    result = tables.map_succession_laws(["succ_made_up"])
    assert result.laws == []
    assert result.dropped == [("succ_made_up", "unknown CK2 law")]


def test_a_lossy_mapping_keeps_a_note():
    result = tables.map_succession_laws(["succ_seniority"])
    assert result.laws == ["single_heir_succession_law"]
    assert "no seniority" in result.notes[0][1]


def test_a_theocratic_law_falls_back_on_a_feudal_holder():
    feudal = tables.map_succession_laws(
        ["succ_divine_cleric"], government="feudal_government"
    )
    assert feudal.laws == ["feudal_elective_succession_law"]
    assert "needs theocracy_government" in feudal.notes[0][1]
    theocratic = tables.map_succession_laws(
        ["succ_divine_cleric"], government="theocracy_government"
    )
    assert theocratic.laws == ["bishop_theocratic_succession_law"]


def test_two_laws_of_one_ck3_group_keep_only_the_first():
    result = tables.map_succession_laws(["succ_gavelkind", "succ_primogeniture"])
    assert result.laws == ["partition_succession_law"]
    assert "already set to" in result.dropped[0][1]


def test_every_faerun_law_is_covered():
    """Every CK2 law that Faerun's history/titles actually uses is mapped.

    The list is the output of scripts/survey_ck2_titles.py, so a CK2 update
    that adds a law makes this test fail rather than silently drop it.
    """
    used = [
        "succ_gavelkind",
        "succ_elective_gavelkind",
        "succ_eldership",
        "succ_seniority",
        "succ_primogeniture",
        "succ_feudal_elective",
        "succ_tanistry",
        "succ_ultimogeniture",
        "succ_turkish_succession",
        "succ_open_elective",
        "succ_patrician_elective",
        "succ_nomad_succession",
        "succ_nomadic_elective",
        "succ_magic_elective",
        "succ_magic_dynastic",
        "succ_magic_wizard",
        "succ_magic_warlock",
        "succ_popular_elective",
        "succ_divine_elective",
        "succ_divine_dynastic",
        "succ_divine_cleric",
        "succ_divine_druid",
        "succ_divine_monk",
        "succ_yikaria",
        "succ_wychlaran",
        "succ_ordning",
        "succ_magister",
        "succ_bahamut",
        "true_cognatic_succession",
        "cognatic_succession",
        "agnatic_succession",
        "enatic_succession",
        "enatic_cognatic_succession",
    ]
    missing = [law for law in used if law not in tables.SUCCESSION_LAWS]
    assert missing == []


def test_history_never_names_an_engine_object_government():
    """mercenary/holy_order governments belong to engine-created companies and orders;
    a landed title carrying them crashed the first tick (docs/DECISIONS.md 2026-09-09)."""
    from ck2ck3.titles import tables
    for _key, government, _why in tables.FLAG_GOVERNMENTS:
        assert government in tables.HISTORY_GOVERNMENTS, government
    for ck3 in tables.load_government_map(GOV_CSV).values():
        assert ck3 in tables.HISTORY_GOVERNMENTS, ck3
