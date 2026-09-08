"""CK2 text codes, colours and icons → CK3 data functions."""

from __future__ import annotations

from pathlib import Path

import pytest

from ck2ck3 import loc_codes
from ck2ck3.loc_codes import (
    MARKER,
    Report,
    convert_code,
    convert_text,
    custom_loc_names,
    is_language_helper,
)

REPO = Path(__file__).resolve().parents[1]
FAERUN = REPO / "Faerun" / "Faerun"


def text(code: str, **kwargs) -> str:
    return convert_code(code, **kwargs).text


# -- scope chains ----------------------------------------------------------
@pytest.mark.parametrize(
    "ck2,ck3",
    [
        # CK3 1.19 english loc: [ROOT.Char.GetSheHe], [THIS.Char.GetCulture…]
        ("[Root.GetFirstName]", "[ROOT.Char.GetFirstName]"),
        ("[This.GetTitledFirstName]", "[THIS.Char.GetTitledFirstName]"),
        ("[Prev.GetName]", "[PREV.Char.GetName]"),
        ("[Player.GetName]", "[GetPlayer.GetName]"),
        # a bare code is CK2's Root
        ("[GetHerHis]", "[ROOT.Char.GetHerHis]"),
        # chain steps
        ("[This.Liege.GetName]", "[THIS.Char.GetLiege.GetName]"),
        ("[Root.Capital.GetName]", "[ROOT.Char.GetCapitalLocation.GetName]"),
        ("[Root.Religion.GetName]", "[ROOT.Char.GetFaith.GetName]"),
        ("[Root.Culture.GetName]", "[ROOT.Char.GetCulture.GetName]"),
        ("[Root.PrimaryTitle.GetName]", "[ROOT.Char.GetPrimaryTitle.GetName]"),
        ("[Root.Spouse.GetFirstName]", "[ROOT.Char.GetPrimarySpouse.GetFirstName]"),
        ("[Root.Father.GetName]", "[ROOT.Char.GetFather.GetName]"),
        ("[Root.Owner.GetName]", "[ROOT.Char.GetHolder.GetName]"),
        # a function CK3 folds into a chain step
        ("[Root.Religion.GetHighGodName]", "[ROOT.Char.GetFaith.HighGodName]"),
        ("[Root.GetHighGodName]", "[ROOT.Char.GetFaith.HighGodName]"),
        ("[Root.Religion.GetGroupName]", "[ROOT.Char.GetFaith.GetReligion.GetName]"),
        ("[Root.RelHead.GetName]", "[ROOT.Char.GetFaith.GetReligiousHead.GetName]"),
        # CK2 spells capitalisation with Cap, CK3 with |U
        ("[Root.GetSheHeCap]", "[ROOT.Char.GetSheHe|U]"),
        # gendered words: CK3 only ships the female-first form
        ("[Root.GetManWoman]", "[ROOT.Char.GetWomanMan]"),
        ("[Root.GetLordLady]", "[ROOT.Char.GetLadyLord]"),
        ("[Root.GetHerselfHimself]", "[ROOT.Char.GetHerselfHimself]"),
        # CK3 ships the gendered relatives as vanilla custom localisations
        ("[Root.GetSonDaughter]", "[ROOT.Char.Custom('DaughterSon')]"),
        ("[Root.GetSisterBrother]", "[ROOT.Char.Custom('SisterBrother')]"),
        # a CK2 dynasty shows as a CK3 house name
        ("[Root.GetDynName]", "[ROOT.Char.GetHouse.GetBaseName]"),
    ],
)
def test_maps_the_frequent_codes(ck2, ck3):
    assert text(ck2) == ck3


def test_from_becomes_a_saved_scope_and_says_so():
    result = convert_code("[From.GetFirstName]", named_scope_policy="reference")
    assert result.text == "[ck2_from.GetFirstName]"
    assert result.status == "mapped"
    assert "saved scope" in result.note


@pytest.mark.parametrize(
    "ck2,ck3",
    [
        ("[FromFrom.GetName]", "[ck2_fromfrom.GetName]"),
        ("[FromFromFrom.GetName]", "[ck2_fromfromfrom.GetName]"),
        ("[From.GetHerHisCap]", "[ck2_from.GetHerHis|U]"),
    ],
)
def test_from_chains_get_their_own_scope_name(ck2, ck3):
    assert text(ck2, named_scope_policy="reference") == ck3


def test_a_from_code_is_a_marker_under_the_default_policy():
    """`[ck2_from.…]` is a saved scope too: nothing runs
    `save_scope_as = ck2_from` until the event port ships, and an unresolvable
    scope is a data error in the loc string, not a blank."""
    result = convert_code("[From.GetFirstName]")
    assert result.text == MARKER.format("From.GetFirstName")
    assert "saved scope" in result.note


def test_a_ck2_event_target_is_kept_as_a_ck3_saved_scope():
    result = convert_code(
        "[relic_hunter.GetTitledFirstName]", named_scope_policy="reference"
    )
    assert result.text == "[relic_hunter.GetTitledFirstName]"
    assert result.status == "named_scope"


def test_a_saved_scope_is_a_marker_until_something_saves_it():
    """CK3 references saved scopes the same way CK2 does, but only an event,
    decision or on_action that ran `save_scope_as` puts the scope there, and
    nothing ports CK2's events yet. `verified` 2026-09-08:
    `pdx_data_factory.cpp: Failed to find type 'christian' in
    'christian.GetReligion.GetName'` + `pdx_data_localize.cpp: Data error in
    loc string '<key>'` were the last log lines before an access violation in
    game setup (docs/evidence/game_load_2026-09-08.md)."""
    result = convert_code("[relic_hunter.GetTitledFirstName]")
    assert result.text == MARKER.format("relic_hunter.GetTitledFirstName")
    assert result.status == "named_scope"
    assert "saved scope" in result.note


# -- what has no CK3 equivalent -------------------------------------------
@pytest.mark.parametrize(
    "ck2",
    [
        "[Root.Society.GetName]",          # societies removed in CK3
        "[Root.PlotTarget.GetName]",       # plots removed
        "[From.Offmap.Ruler.GetName]",     # offmap powers removed
        "[Root.job_marshal.GetName]",      # council jobs are court positions
        "[Root.Job_marshal.GetName]",      # CK2 vanilla spells it upper case
        "[From.OriginalOwner.GetName]",    # CK3 keeps no previous holder
        "[Root.GetEmperorEmpress]",        # no CK3 gendered emperor word
    ],
)
def test_dead_ck2_mechanics_are_marked_not_guessed(ck2):
    result = convert_code(ck2)
    assert result.status == "unmapped"
    assert result.text == MARKER.format(ck2[1:-1])
    assert result.note


def test_the_marker_carries_no_square_brackets():
    # CK3 parses [...] anywhere in a value, so a leftover would break.
    marked = text("[Root.Society.GetName]")
    assert "[" not in marked and "]" not in marked


def test_language_helpers_are_marked():
    result = convert_code("[From.Get_le_TitledFirstName]")
    assert result.status == "language_helper"
    assert is_language_helper("Get_E")
    assert not is_language_helper("GetFirstName")


# -- customizable localisation --------------------------------------------
def test_a_mod_custom_loc_becomes_a_ck3_custom_call():
    result = convert_code(
        "[Root.TalosLoc]", custom_loc={"TalosLoc"}, custom_loc_policy="call"
    )
    assert result.text == "[ROOT.Char.Custom('TalosLoc')]"
    assert result.status == "custom"


def test_a_custom_call_is_a_marker_until_the_custom_loc_port_ships():
    """`Custom('X')` for an X CK3 does not know is not inert: `verified`
    2026-09-08, 795 such names produced `jomini_custom_text.h:94: Object of
    type 'character' is not valid for 'VampName'` and the game died in game
    setup. Nothing emits common/customizable_localization yet, so `marker` is
    the default (docs/evidence/game_load_2026-09-08.md)."""
    result = convert_code("[Root.TalosLoc]", custom_loc={"TalosLoc"})
    assert result.text == MARKER.format("Root.TalosLoc")
    assert result.status == "custom"
    assert "Custom(" not in result.text


def test_an_unknown_getter_is_a_custom_call_only_under_the_call_policy():
    result = convert_code("[Root.GetChancellorName]", custom_loc_policy="call")
    assert result.text == "[ROOT.Char.Custom('GetChancellorName')]"
    assert result.status == "custom_unverified"
    # default policy: no call to a name nothing defines
    assert "Custom(" not in convert_code("[Root.GetChancellorName]").text


def test_the_marker_policy_switches_it_off():
    result = convert_code("[Root.GetChancellorName]", unknown="marker")
    assert result.status == "unmapped"
    assert result.text == MARKER.format("Root.GetChancellorName")


# -- colours, icons, variables --------------------------------------------
def test_colours_become_ck3_text_formats():
    # textformatting.gui: M = mixed_value = color_yellow, N = negative_value
    assert convert_text("§YHi§!") == "#M Hi#!"
    assert convert_text("§Rbad§!") == "#N bad#!"
    assert convert_text("§Ggood§!") == "#P good#!"


def test_a_stray_paragraph_sign_is_dropped():
    report = Report()
    assert convert_text("plain§", report=report) == "plain"
    assert report.stray_colour_marks == 1


def test_icons_are_marked():
    report = Report()
    assert convert_text("cost £1£", report=report) == "cost <!CK2:icon_1!>"
    assert report.icons == 1


def test_variables_pass_through_unchanged():
    assert convert_text("gain $VALUE|R$ of $LIST$") == "gain $VALUE|R$ of $LIST$"


def test_an_unbalanced_bracket_is_removed():
    report = Report()
    out = convert_text("I support [From.GetTitledName", report=report)
    assert "[" not in out and "]" not in out
    assert report.stray_brackets == 1


def test_a_literal_newline_escape_survives():
    assert convert_text("one\\ntwo") == "one\\ntwo"


# -- the report ------------------------------------------------------------
def test_the_report_counts_every_status():
    report = Report()
    convert_text("[Root.GetFirstName] [Root.Society.GetName] [x.GetName]", report=report)
    assert report.total == 3
    assert report.converted == 2
    assert report.coverage() == pytest.approx(2 / 3)
    assert "[Root.Society.GetName]" in report.unconverted


# -- the real mod ----------------------------------------------------------
@pytest.mark.slow
@pytest.mark.skipif(not FAERUN.is_dir(), reason="Faerun/ not cloned")
def test_faerun_defines_its_customizable_localisations():
    names = custom_loc_names(FAERUN)
    assert len(names) > 1000
    assert "TalosLoc" in names


def test_every_table_entry_has_a_ck3_form_or_a_reason():
    for name, entry in loc_codes.FUNCTIONS.items():
        assert entry.ck3 or entry.note, f"{name} has neither a mapping nor a reason"
