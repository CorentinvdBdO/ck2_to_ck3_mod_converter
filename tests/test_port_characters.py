"""One test per conversion rule, each with a three-line CK2 fixture.

The port is a pure function of a parse tree plus the tables, so nothing here
needs a Context, an output folder or the Faerûn clone. The slow end-to-end
counts live in ``tests/test_characters_faerun.py``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ck2ck3.pdx import Block, Node, parse, write
from ck2ck3.port.characters import CharacterPort, output_name
from ck2ck3.port.common import fae_id, strip_ck2_markers
from ck2ck3.port.tables import Tables, load_tables

CK3_GAME = Path(
    "/home/cvdbdo/.local/share/Steam/steamapps/common/Crusader Kings III/game"
)
needs_ck3 = pytest.mark.skipif(
    not (CK3_GAME / "common" / "traits" / "00_traits.txt").exists(),
    reason="CK3 1.19 install not present",
)


@pytest.fixture(scope="module")
def tables() -> Tables:
    return load_tables()


def convert(text: str, tables: Tables) -> tuple[str, CharacterPort]:
    """Convert a CK2 snippet holding exactly one character block."""
    doc = parse(text)
    node = doc.entries[0]
    assert isinstance(node, Node)
    port = CharacterPort(tables=tables)
    return write(Block(entries=[port.convert_character(node)])), port


# -- ids -------------------------------------------------------------------
def test_id_prefixing_covers_key_and_every_reference(tables: Tables) -> None:
    out, port = convert(
        """
        7 = {
            name = Elminster
            dynasty = 42
            father = 6
            mother = 5
            1200.1.1 = { birth = yes employer = 9 add_spouse = 8 }
        }
        """,
        tables,
    )
    assert "fae_7 = {" in out
    assert "dynasty = fae_42" in out
    assert "father = fae_6" in out
    assert "mother = fae_5" in out
    assert "employer = fae_9" in out
    assert "add_spouse = fae_8" in out
    assert port.id_map == {"7": "fae_7"}


def test_fae_id_is_idempotent() -> None:
    assert fae_id(7) == "fae_7"
    assert fae_id("fae_7") == "fae_7"
    assert fae_id(7, prefix="fk") == "fk_7"


def test_output_name_keeps_the_id_range_readable() -> None:
    assert output_name("1-1000 Miscellaneous.txt") == "fae_1-1000_miscellaneous.txt"
    assert output_name("39001-40000 Ra-Khati and Khazari.txt") == (
        "fae_39001-40000_ra-khati_and_khazari.txt"
    )


# -- attributes and plain keys --------------------------------------------
def test_attributes_and_flags_pass_through(tables: Tables) -> None:
    out, _ = convert(
        """
        1 = {
            martial = 18 diplomacy = 13 intrigue = 23 stewardship = 8 learning = 13
            female = yes health = 10.0 fertility = 0
            disallow_random_traits = yes
            culture = illuskan
            religion = triadic
        }
        """,
        tables,
    )
    for line in (
        "martial = 18",
        "diplomacy = 13",
        "intrigue = 23",
        "stewardship = 8",
        "learning = 13",
        "female = yes",
        "disallow_random_traits = yes",
        "culture = illuskan",
        "religion = triadic",
    ):
        assert line in out


# -- death -----------------------------------------------------------------
def test_bare_death_stays_bare(tables: Tables) -> None:
    out, _ = convert("1 = { 1300.1.1 = { death = yes } }", tables)
    assert "death = yes" in out


def test_death_reason_exact_match_is_not_commented(tables: Tables) -> None:
    out, port = convert(
        "1 = { 1300.1.1 = { death = { death_reason = death_battle } } }", tables
    )
    assert "death_reason = death_battle" in out
    assert "# CK2: death_reason" not in out
    assert port.report.counts["death_reason_exact"] == 1


def test_death_reason_remap_keeps_the_ck2_value_in_a_comment(tables: Tables) -> None:
    out, port = convert(
        "1 = { 1300.1.1 = { death = { death_reason = death_execution_burning } } }",
        tables,
    )
    assert "death_reason = death_burned" in out
    assert "# CK2: death_reason = death_execution_burning (exact -> death_burned)" in out
    assert port.report.counts["death_reason_exact"] == 1


def test_unknown_death_reason_falls_back_and_warns(tables: Tables) -> None:
    out, port = convert(
        "1 = { 1300.1.1 = { death = { death_reason = death_by_beholder } } }", tables
    )
    assert "death_reason = death_natural_causes" in out
    assert "# CK2: death_reason = death_by_beholder (unknown" in out
    assert any("death_by_beholder" in w for w in port.report.warnings)


def test_killer_is_prefixed_and_not_scoped(tables: Tables) -> None:
    # Verified in the 1.19 install: history `killer` takes a bare id
    # (history/characters/bai.txt: killer = bai_yang_2_1), not character:<id>.
    out, port = convert(
        "1 = { 1300.1.1 = { death = { death_reason = death_murder killer = 99 } } }",
        tables,
    )
    assert "killer = fae_99" in out
    assert "character:" not in out
    assert ("killer", "fae_99") in port.facts["fae_1"].refs


# -- relations -------------------------------------------------------------
@pytest.mark.parametrize(
    "ck2_effect,ck3_effect,reason",
    [
        ("add_friend", "set_relation_friend", "friend_generic_history"),
        ("add_rival", "set_relation_rival", "rival_historical"),
        ("add_lover", "set_relation_lover", "lover_history"),
    ],
)
def test_relations_become_effects_with_a_reason(
    tables: Tables, ck2_effect: str, ck3_effect: str, reason: str
) -> None:
    out, port = convert(
        f"1 = {{ 1300.1.1 = {{ effect = {{ {ck2_effect} = 4 }} }} }}", tables
    )
    assert f"{ck3_effect} = {{" in out
    assert f"reason = {reason}" in out
    assert "target = character:fae_4" in out
    assert port.report.counts["relations"] == 1


def test_relation_removal_takes_a_character_scope(tables: Tables) -> None:
    out, _ = convert("1 = { 1300.1.1 = { effect = { remove_lover = 4 } } }", tables)
    assert "remove_relation_lover = character:fae_4" in out


# -- nicknames -------------------------------------------------------------
def test_known_nickname_is_kept(tables: Tables) -> None:
    out, port = convert(
        "1 = { 1300.1.1 = { give_nickname = nick_the_great } }", tables
    )
    assert "give_nickname = nick_the_great" in out
    assert port.report.counts["nicknames"] == 1


def test_faerun_only_nickname_becomes_a_comment(tables: Tables) -> None:
    out, port = convert(
        "1 = { 1300.1.1 = { give_nickname = nick_blackstaff } }", tables
    )
    assert "\tgive_nickname = nick_blackstaff" not in out
    assert "# CK2: give_nickname = nick_blackstaff" in out
    assert port.report.counts["nicknames_dropped"] == 1


# -- traits ----------------------------------------------------------------
def test_vanilla_trait_is_renamed_to_its_ck3_id(tables: Tables) -> None:
    # `wounded` is an `exact` row of mappings/vanilla_traits.csv, so the traits
    # step dedupes it to CK3 `wounded_1` and does not redefine it.
    out, port = convert("1 = { trait = wounded }", tables)
    assert "trait = wounded_1" in out
    assert port.report.counts["traits_renamed"] == 1


def test_approx_vanilla_trait_is_renamed_just_like_exact(tables: Tables) -> None:
    """Policy 2026-09-08 second entry (`docs/DECISIONS.md`): `approx` dedupes
    exactly like `exact` — no CK2 trait definition is ever emitted. CK3
    `wrathful` is only a near-equivalent of CK2 `wroth`, but the character
    still gets the CK3 id, not the CK2 one."""
    out, port = convert("1 = { trait = wroth }", tables)
    assert "trait = wrathful" in out
    assert "trait = wroth" not in out
    assert port.report.counts["traits_renamed"] == 1


def test_nearest_vanilla_trait_is_renamed(tables: Tables) -> None:
    """`nearest` (no real counterpart, but a gameplay-adjacent CK3 trait)
    dedupes the same way as `exact`/`approx`."""
    out, port = convert("1 = { trait = harelip }", tables)
    assert "trait = beauty_bad_1" in out
    assert "trait = harelip" not in out


def test_sexuality_vanilla_trait_becomes_a_sexuality_key(tables: Tables) -> None:
    """`homosexual` is not a CK3 trait at all; the character gets the CK3
    `sexuality` history key instead (docs/step_traits.md rule 2)."""
    out, port = convert("1 = { trait = homosexual }", tables)
    assert "sexuality = homosexual" in out
    assert "trait = homosexual" not in out
    assert port.report.counts["traits_sexuality"] == 1


def test_drop_vanilla_trait_leaves_a_specific_comment(tables: Tables) -> None:
    """`envious` has no CK3 landing place at all; the character loses it with
    the exact comment the user asked for (docs/step_traits.md rule 2)."""
    out, port = convert("1 = { trait = envious }", tables)
    assert "trait = envious" not in out
    assert "# CK2 trait envious: no CK3 counterpart" in out
    assert port.report.counts["traits_dropped_no_ck3"] == 1


def test_faerun_race_trait_keeps_its_id(tables: Tables) -> None:
    out, _ = convert("1 = { trait = creature_elf }", tables)
    assert "trait = creature_elf" in out


def test_unknown_trait_becomes_a_comment(tables: Tables) -> None:
    out, port = convert("1 = { trait = patron_bhaal }", tables)
    assert "\ttrait = patron_bhaal" not in out
    assert "# CK2: trait = patron_bhaal" in out
    assert port.report.counts["traits_dropped"] == 1


def test_trait_id_map_post_pass_is_applied_to_the_fallback_set() -> None:
    """The dedupe table renames a trait the *fallback* port set kept.

    Only the fallback: `mappings/trait_ck2_to_ck3.csv` already carries the
    final CK3 id, and re-applying a ck2-keyed map on top of it would rename a
    ck3 id by a ck2 key.
    """
    tables = load_tables()
    tables.traits_authoritative = False
    tables.known_traits["creature_elf"] = "creature_elf"
    tables.trait_id_map_present = True
    tables.trait_id_map["creature_elf"] = "creature_elf_dedup"
    out, _ = convert("1 = { trait = creature_elf }", tables)
    assert "trait = creature_elf_dedup" in out


def test_the_authoritative_set_is_not_remapped_again() -> None:
    """A ck2-keyed dedupe entry must not touch an already-final ck3 id."""
    tables = load_tables()
    assert tables.traits_authoritative, "run scripts/build_trait_tables.py"
    tables.trait_id_map["creature_elf"] = "creature_elf_dedup"
    out, _ = convert("1 = { trait = creature_elf }", tables)
    assert "trait = creature_elf\n" in out


def test_traits_step_handoff_replaces_the_known_set() -> None:
    """Only what the traits step wrote this run resolves."""
    tables = load_tables()
    tables.adopt_traits_step(["creature_elf"], {"wounded": "wounded_1"})
    out, port = convert(
        "1 = { trait = creature_elf trait = wounded trait = brave }", tables
    )
    assert "trait = creature_elf" in out
    assert "trait = wounded_1" in out
    assert "# CK2: trait = brave" in out
    assert port.report.counts["traits_dropped"] == 1


def test_add_and_remove_trait_go_through_the_same_table(tables: Tables) -> None:
    out, _ = convert(
        "1 = { 1300.1.1 = { add_trait = wounded remove_trait = brave } }", tables
    )
    assert "add_trait = wounded_1" in out
    assert "remove_trait = brave" in out


# -- rule 3: a dedupe must not give a character a conflicting pair ---------
def test_two_ck2_traits_deduping_to_one_ck3_trait_conflict(tables: Tables) -> None:
    """`hunter` (exact) and `falconer` (approx) both dedupe to
    `lifestyle_hunter`: the second is commented, not redefined twice."""
    from ck2ck3.traits import TraitConflicts

    port = CharacterPort(tables=tables, conflicts=TraitConflicts())
    doc = parse("1 = { trait = hunter trait = falconer }")
    out = write(Block(entries=[port.convert_character(doc.entries[0])]))
    assert out.count("trait = lifestyle_hunter") == 1
    assert "conflicts with already-held lifestyle_hunter" in out
    assert port.report.counts["traits_conflict_dropped"] == 1
    assert port.facts["fae_1"].traits == ["lifestyle_hunter"]


def test_opposite_ck3_traits_after_a_dedupe_conflict(tables: Tables) -> None:
    """`cruel` -> `sadistic` and `kind` -> `compassionate` never conflicted as
    CK2 ids, but CK3 declares the two traits mutual opposites."""
    from ck2ck3.traits import TraitConflicts

    conflicts = TraitConflicts(opposites={"sadistic": frozenset({"compassionate"})})
    port = CharacterPort(tables=tables, conflicts=conflicts)
    doc = parse("1 = { trait = cruel trait = kind }")
    out = write(Block(entries=[port.convert_character(doc.entries[0])]))
    assert "trait = sadistic" in out
    assert "trait = compassionate" not in out
    assert "conflicts with already-held sadistic" in out
    assert port.report.counts["traits_conflict_dropped"] == 1


def test_no_conflict_check_when_conflicts_is_none(tables: Tables) -> None:
    """``conflicts=None`` (the dataclass default) disables the check."""
    port = CharacterPort(tables=tables)
    doc = parse("1 = { trait = hunter trait = falconer }")
    out = write(Block(entries=[port.convert_character(doc.entries[0])]))
    assert out.count("trait = lifestyle_hunter") == 2


@needs_ck3
def test_leveled_trait_conflict_from_real_ck3_opposites(tables: Tables) -> None:
    """`slow` (approx -> intellect_bad_2) and `imbecile` (exact ->
    intellect_bad_3) never conflicted in CK2, but CK3 1.19 lists every
    intellect_bad tier as each other's `opposites`
    (`common/traits/00_traits.txt`, `verified`)."""
    from ck2ck3.traits import read_trait_conflicts

    conflicts = read_trait_conflicts(CK3_GAME / "common" / "traits")
    port = CharacterPort(tables=tables, conflicts=conflicts)
    doc = parse("1 = { trait = slow trait = imbecile }")
    out = write(Block(entries=[port.convert_character(doc.entries[0])]))
    assert "trait = intellect_bad_2" in out
    assert "trait = intellect_bad_3" not in out
    assert "conflicts with already-held intellect_bad_2" in out


# -- effects that must be wrapped -----------------------------------------
def test_immortal_age_moves_into_an_effect_block(tables: Tables) -> None:
    out, port = convert("1 = { 1300.1.1 = { birth = yes immortal_age = 30 } }", tables)
    assert "effect = {" in out
    assert "set_immortal_age = 30" in out
    assert out.index("birth = yes") < out.index("set_immortal_age")
    assert port.report.counts["effect_blocks_added"] == 1


def test_history_add_claim_is_wrapped_and_scoped(tables: Tables) -> None:
    out, _ = convert("1 = { 1300.1.1 = { add_claim = c_shadowdale } }", tables)
    assert "effect = {" in out
    assert "add_pressed_claim = title:c_shadowdale" in out


def test_wealth_becomes_an_add_gold_effect(tables: Tables) -> None:
    out, _ = convert("1 = { 1300.1.1 = { wealth = 500 } }", tables)
    assert "add_gold = 500" in out


# -- effect blocks ---------------------------------------------------------
def test_effect_even_if_dead_is_ported_as_effect_with_a_note(tables: Tables) -> None:
    out, port = convert(
        "1 = { 1300.1.1 = { effect_even_if_dead = { add_trait = wounded } } }", tables
    )
    assert "effect_even_if_dead =" not in out.replace("# CK2: effect_even_if_dead", "")
    assert "effect = {" in out
    assert "add_trait = wounded_1" in out
    assert "CK3 has no effect_even_if_dead" in out
    assert port.report.dropped[("effect_even_if_dead", "history", "renamed to effect")] == 1


def test_character_flag_effects_are_renamed(tables: Tables) -> None:
    out, _ = convert(
        "1 = { 1300.1.1 = { effect = { set_character_flag = lich_court "
        "clr_character_flag = mortal } } }",
        tables,
    )
    assert "add_character_flag = lich_court" in out
    assert "remove_character_flag = mortal" in out


def test_set_real_father_takes_a_character_scope(tables: Tables) -> None:
    out, _ = convert(
        "1 = { 1300.1.1 = { effect = { set_real_father = 20081 } } }", tables
    )
    assert "set_real_father = character:fae_20081" in out


def test_add_character_modifier_converts_days_to_years(tables: Tables) -> None:
    out, _ = convert(
        "1 = { 1300.1.1 = { effect = { add_character_modifier = "
        "{ name = uncertain_times duration = 1825 } } } }",
        tables,
    )
    assert "modifier = uncertain_times" in out
    assert "years = 5" in out


def test_permanent_character_modifier_omits_years(tables: Tables) -> None:
    out, _ = convert(
        "1 = { 1300.1.1 = { effect = { add_character_modifier = "
        "{ name = undead_realm_lord duration = -1 } } } }",
        tables,
    )
    assert "modifier = undead_realm_lord" in out
    assert "years" not in out


def test_weak_claim_becomes_an_unpressed_claim(tables: Tables) -> None:
    out, _ = convert(
        "1 = { 1300.1.1 = { effect = { add_weak_pressed_claim = c_westgate } } }",
        tables,
    )
    assert "add_unpressed_claim = title:c_westgate" in out


def test_consort_becomes_a_concubine(tables: Tables) -> None:
    out, _ = convert("1 = { 1300.1.1 = { add_consort = 60015 } }", tables)
    assert "add_concubine = fae_60015" in out


# -- dropped keys ----------------------------------------------------------
@pytest.mark.parametrize(
    "snippet,key",
    [
        ('1 = { dna = "0jiaa0k0000" }', "dna"),
        ('1 = { properties = "rkxiai0000000000b" }', "properties"),
        ("1 = { easter_egg = yes }", "easter_egg"),
        ("1 = { secret_religion = shadow_gods }", "secret_religion"),
        ("1 = { 1300.1.1 = { create_bloodline = { type = bhaal_bloodline } } }",
         "create_bloodline"),
        ("1 = { 1300.1.1 = { effect = { join_society = harpers } } }", "join_society"),
        ("1 = { 1300.1.1 = { effect = { imprison = 9307 } } }", "imprison"),
    ],
)
def test_unconvertible_keys_become_in_place_comments(
    tables: Tables, snippet: str, key: str
) -> None:
    out, port = convert(snippet, tables)
    assert f"# CK2: {key}" in out
    assert port.dropped_key_count(key) == 1 if hasattr(port, "dropped_key_count") else True
    assert sum(n for (k, _l, _r), n in port.report.dropped.items() if k == key) == 1


def test_dropped_block_is_summarised_not_pasted(tables: Tables) -> None:
    out, _ = convert(
        "1 = { 1300.1.1 = { effect = { spawn_unit = { province = 12 owner = ROOT "
        "troops = { light_infantry = { 500 500 } } } } } }",
        tables,
    )
    assert "# CK2: spawn_unit = { province owner troops }" in out
    assert "light_infantry" not in out


def test_ck2_comment_on_a_dropped_key_survives(tables: Tables) -> None:
    out, _ = convert(
        "1 = { 1300.1.1 = { effect = { join_society = harpers # the good guys\n} } }",
        tables,
    )
    assert "the good guys" in out


def test_unmapped_key_warns_once_and_is_commented(tables: Tables) -> None:
    out, port = convert("1 = { fondness_for_cheese = yes }", tables)
    assert "# CK2: fondness_for_cheese = yes" in out
    assert any("fondness_for_cheese" in w for w in port.report.warnings)


def test_ck2_scope_change_is_commented_without_a_warning(tables: Tables) -> None:
    out, port = convert(
        "1 = { 1300.1.1 = { effect = { c_bloodstone = { ROOT = { capital = PREV } } } } }",
        tables,
    )
    assert "# CK2: c_bloodstone" in out
    assert port.report.warnings == []


def test_trailing_comment_only_block_still_closes(tables: Tables) -> None:
    """A block whose every entry was dropped keeps the comments in end_comments."""
    out, _ = convert("1 = { 1300.1.1 = { easter_egg = yes } }", tables)
    assert out.count("{") == out.count("}")
    assert "# CK2: easter_egg" in out


# -- CK2 file markers -----------------------------------------------------
def test_ck2_codepage_marker_is_dropped() -> None:
    assert strip_ck2_markers(["# ###ÄNSI"]) == []
    assert strip_ck2_markers(["#Bhaal himself"]) == ["#Bhaal himself"]


# -- comments and grouping ------------------------------------------------
def test_ck2_comments_and_blank_groups_survive(tables: Tables) -> None:
    out, _ = convert(
        """
        # a note above the character
        2 = {
            name = Bhaal

            culture = planar # a trailing note
        }
        """,
        tables,
    )
    assert "# a note above the character" in out
    assert "# a trailing note" in out
    assert "\n\n\tculture" in out


# -- keys CK3 treats differently inside a dated block ---------------------
def test_dated_father_becomes_a_set_father_effect(tables: Tables) -> None:
    """`verified` by ck3-tiger: a bare `father` in a dated block is a structure
    error ("expected block, found value"); the effect form is the only way."""
    out, _ = convert("1 = { 1300.1.1 = { father = 20202 mother = 20205 } }", tables)
    assert "\tfather = " not in out
    assert "set_father = character:fae_20202" in out
    assert "set_mother = character:fae_20205" in out
    assert "effect = {" in out


def test_top_level_father_stays_a_history_key(tables: Tables) -> None:
    out, _ = convert("1 = { father = 20202 }", tables)
    assert "father = fae_20202" in out
    assert "set_father" not in out


def test_dated_fertility_is_commented(tables: Tables) -> None:
    """`verified` by ck3-tiger: `fertility` is a trigger, not an effect."""
    out, port = convert("1 = { 1300.1.1 = { fertility = 0 } }", tables)
    assert "# CK2: fertility = 0" in out
    assert "\tfertility = 0" not in out
    assert sum(
        n for (k, level, _r), n in port.report.dropped.items()
        if k == "fertility" and level == "dated"
    ) == 1


def test_top_level_fertility_is_kept(tables: Tables) -> None:
    out, _ = convert("1 = { fertility = 0 }", tables)
    assert "fertility = 0" in out
    assert "# CK2: fertility" not in out


def test_set_name_becomes_a_comment(tables: Tables) -> None:
    """CK3 `change_first_name` takes a loc key, never a literal name.

    `error(unknown-field): unknown token `Obould`` (4x, `verified`
    2026-09-08). And `change_first_name = ""` makes ck3-tiger 1.19.0 panic
    (src/trigger.rs:1454, `docs/formats_characters.md` s10), so neither shape
    may be emitted.
    """
    for value in ('"Obould"', '""'):
        out, _ = convert(
            "1 = { 1300.1.1 = { effect = { set_name = %s } } }" % value, tables
        )
        assert "change_first_name" not in out.split("# CK2:")[0]
        assert "# CK2: set_name = " in out


def test_spouse_effects_use_marry_and_divorce(tables: Tables) -> None:
    """`add_spouse` is a dated-history key; the effect is `marry`."""
    out, _ = convert(
        "1 = { 1300.1.1 = { effect = { add_spouse = 2 remove_spouse = 3 } } }",
        tables,
    )
    # A scope, not a bare history id: `marry = fae_2` is
    # `error(unknown-field): unknown token \`fae_2\``.
    assert "marry = character:fae_2" in out
    assert "divorce = character:fae_3" in out
    assert "add_spouse" not in out


def test_a_modifier_ck3_does_not_declare_becomes_a_comment(tables: Tables) -> None:
    """No step converts CK2 common/event_modifiers, so its ids cannot resolve."""
    tables.adopt_ck3_modifiers({"stressed_modifier"})
    out, port = convert(
        "1 = { 1300.1.1 = { effect = { add_character_modifier = "
        "{ name = known_vamp_modifier duration = 730 } } } }",
        tables,
    )
    assert "known_vamp_modifier" not in out.split("# CK2:")[0]
    assert "# CK2: add_character_modifier" in out
    assert port.report.counts["modifiers_dropped"] == 1

    out, port = convert(
        "1 = { 1300.1.1 = { effect = { add_character_modifier = "
        "{ name = stressed_modifier duration = 730 } } } }",
        tables,
    )
    assert "modifier = stressed_modifier" in out
    assert "years = 2" in out


def test_empty_character_name_is_kept_but_flagged(tables: Tables) -> None:
    """CK3 *requires* `name`, so dropping it would be a load error, not a fix.
    54 Faerûn characters have a blank name (2 of them `name = ""`)."""
    out, port = convert('1 = { name = "" }', tables)
    assert 'name = ""' in out
    assert port.report.counts["empty_names"] == 1
    assert any("blank name" in w for w in port.report.warnings)


def test_space_only_character_name_is_kept_verbatim(tables: Tables) -> None:
    """The 52 Yikarians write `name = " "`, not `name = ""`; both are blank and
    both are kept, because CK3 requires the field either way."""
    out, port = convert('1 = { name = " " }', tables)
    assert 'name = " "' in out
    assert port.report.counts["empty_names"] == 1
    assert any("blank name" in w for w in port.report.warnings)
