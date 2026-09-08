"""The mapping tables must be complete and self-consistent.

Fast tests read only the CSVs. The one test that needs the CK3 install shells
out to ``scripts/verify_character_tables.py`` and is skipped without it.
"""

from __future__ import annotations

import csv
import subprocess
import sys
from pathlib import Path

import pytest

from ck2ck3.port.characters import WRAPPED_FORMS, VALUE_REASONS
from ck2ck3.port.tables import (
    CHARACTER_EFFECTS,
    DEATH_REASONS,
    NICKNAMES,
    UNKNOWN_DEATH_REASON,
    load_tables,
)

REPO = Path(__file__).resolve().parents[1]
CK3 = Path("/home/cvdbdo/.local/share/Steam/steamapps/common/Crusader Kings III/game")

#: Every form the port knows how to build. A new form must be added here and
#: to `CharacterPort._shape` in the same commit, or the port raises at runtime.
KNOWN_FORMS = {
    "same", "char_ref", "char_scope", "dynasty_scope", "title_scope",
    "title_scope_effect", "int_effect", "drop_value", "scale_0_1", "trait",
    "nickname", "char_modifier", "death", "effect_block", "comment",
    "char_scope_effect", "nonempty",
}


def rows(rel: str) -> list[dict[str, str]]:
    with (REPO / rel).open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def test_every_form_in_the_table_is_one_the_port_implements() -> None:
    for row in rows(CHARACTER_EFFECTS):
        form = row["form"]
        assert form in KNOWN_FORMS or form.startswith("relation:"), form


def test_every_non_dropping_row_names_a_ck3_key() -> None:
    for row in rows(CHARACTER_EFFECTS):
        if row["form"] == "comment":
            assert row["ck3_key"] == "", row
        else:
            assert row["ck3_key"], row


def test_every_row_has_a_note_saying_why() -> None:
    for row in rows(CHARACTER_EFFECTS):
        assert row["note"].strip() not in ("", "-"), row


def test_levels_are_only_history_dated_or_effect() -> None:
    assert {row["level"] for row in rows(CHARACTER_EFFECTS)} == {
        "history",
        "dated",
        "effect",
    }


def test_every_dated_row_overrides_an_existing_history_row() -> None:
    """A `dated` row exists only to say "CK3 differs inside a dated block"."""
    all_rows = rows(CHARACTER_EFFECTS)
    history = {r["ck2_key"] for r in all_rows if r["level"] == "history"}
    dated = {r["ck2_key"] for r in all_rows if r["level"] == "dated"}
    assert dated <= history, sorted(dated - history)


def test_no_duplicate_key_level_pairs() -> None:
    pairs = [(row["ck2_key"], row["level"]) for row in rows(CHARACTER_EFFECTS)]
    assert len(pairs) == len(set(pairs))


def test_wrapped_forms_are_all_used_by_some_row() -> None:
    forms = {row["form"] for row in rows(CHARACTER_EFFECTS)}
    assert WRAPPED_FORMS <= forms


def test_value_reason_forms_exist_in_the_table() -> None:
    forms = {row["form"] for row in rows(CHARACTER_EFFECTS)}
    assert set(VALUE_REASONS) <= forms


def test_death_reason_statuses_are_from_the_documented_set() -> None:
    statuses = {row["status"] for row in rows(DEATH_REASONS)}
    assert statuses <= {"exact", "approx", "fallback"}


def test_death_reason_fallback_target_exists_in_the_table() -> None:
    targets = {row["ck3_death_reason"] for row in rows(DEATH_REASONS)}
    assert UNKNOWN_DEATH_REASON in targets


def test_no_duplicate_death_reason_rows() -> None:
    keys = [row["ck2_death_reason"] for row in rows(DEATH_REASONS)]
    assert len(keys) == len(set(keys))


def test_nickname_rows_either_map_or_say_comment() -> None:
    for row in rows(NICKNAMES):
        if row["status"] == "comment":
            assert row["ck3_nickname"] == "", row
        else:
            assert row["ck3_nickname"], row


def test_no_duplicate_nickname_rows() -> None:
    keys = [row["ck2_nickname"] for row in rows(NICKNAMES)]
    assert len(keys) == len(set(keys))


def test_the_known_set_comes_from_the_traits_step_output() -> None:
    """`mappings/trait_ck2_to_ck3.csv` is authoritative when it exists."""
    tables = load_tables()
    assert tables.traits_authoritative, "run scripts/build_trait_tables.py"
    assert set(tables.trait_origin.values()) == {"traits_step"}
    assert tables.known_traits, "no traits loaded"
    # A race trait keeps its CK2 id; an `exact` vanilla trait is renamed.
    assert tables.trait("creature_elf") == "creature_elf"
    assert tables.trait("wounded") == "wounded_1"
    assert tables.trait("no_such_trait") is None
    # The 38 traits the step dedupes by exact CK3 id match.
    assert tables.trait("administrator") == "administrator"
    # `approx`/`nearest` now dedupe exactly like `exact` (2026-09-08 second
    # entry, docs/DECISIONS.md): no CK2 trait is ever redefined.
    assert tables.trait("wroth") == "wrathful"
    assert tables.trait("harelip") == "beauty_bad_1"
    # `drop`/`sexuality` never enter the known-trait set at all.
    assert tables.trait("cavalry_leader") is None
    assert tables.trait("homosexual") is None
    assert tables.trait_drop_note("cavalry_leader")
    assert tables.trait_sexuality_value("homosexual") == "homosexual"


def test_approx_and_nearest_rows_of_trait_id_map_are_applied_as_renames() -> None:
    """`mappings/trait_id_map.csv` is now a pure dedupe table (docs/DECISIONS.md
    2026-09-08 second entry): `exact`/`exact_id`/`approx`/`nearest` rows all
    apply the same way. Only `drop`/`sexuality` rows are excluded (no CK3
    trait id to remap onto).
    """
    import csv

    from ck2ck3.port.tables import REPO_ROOT, TRAIT_ID_MAP

    with (REPO_ROOT / TRAIT_ID_MAP).open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    approx = {r["ck2_trait"] for r in rows if r["status"] == "approx"}
    excluded = {r["ck2_trait"] for r in rows if r["status"] in ("drop", "sexuality")}
    assert approx, "no approx pairs: run scripts/build_trait_tables.py"
    assert excluded, "no drop/sexuality pairs: run scripts/build_trait_tables.py"
    tables = load_tables()
    assert approx <= set(tables.trait_id_map)
    assert not excluded & set(tables.trait_id_map)
    assert {r["ck2_trait"] for r in rows} - excluded == set(tables.trait_id_map)


def test_fallback_set_is_read_when_the_traits_output_is_absent(tmp_path) -> None:
    """An old checkout still gets a set, from the two classification tables."""
    import shutil

    from ck2ck3.port import tables as tables_mod

    for rel in (
        tables_mod.CHARACTER_EFFECTS,
        tables_mod.DEATH_REASONS,
        tables_mod.NICKNAMES,
        tables_mod.VANILLA_TRAITS,
        tables_mod.FAERUN_TRAITS,
    ):
        dest = tmp_path / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(tables_mod.REPO_ROOT / rel, dest)
    tables = load_tables(tmp_path)
    assert not tables.traits_authoritative
    assert set(tables.trait_origin.values()) == {
        "exact",
        "approx",
        "nearest",
        "faerun",
        "race",
    }
    # `status = drop`/`sexuality` never enter the known-trait set; they are
    # only in `trait_drop_reason`/`trait_sexuality` (docs/step_traits.md rule 2).
    assert tables.trait("cavalry_leader") is None
    assert tables.trait_drop_note("cavalry_leader")
    assert tables.trait("homosexual") is None
    assert tables.trait_sexuality_value("homosexual") == "homosexual"
    assert tables.trait("wroth") == "wrathful"


def test_adopt_traits_step_is_exactly_what_the_step_wrote() -> None:
    tables = load_tables()
    tables.adopt_traits_step(["a", "b"], {"c": "vanilla_c"})
    assert tables.known_traits == {"a": "a", "b": "b", "c": "vanilla_c"}
    assert tables.trait("creature_elf") is None


def test_trait_id_map_is_optional_and_absent_means_identity() -> None:
    tables = load_tables()
    if not tables.trait_id_map_present:
        assert tables.trait_id_map == {}
        assert tables.trait("creature_elf") == "creature_elf"


@pytest.mark.slow
@pytest.mark.skipif(not CK3.is_dir(), reason="CK3 1.19 install absent")
def test_every_ck3_id_in_the_tables_exists_in_the_game() -> None:
    result = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "verify_character_tables.py")],
        capture_output=True,
        text=True,
        cwd=REPO,
    )
    assert "MISSES: 0" in result.stdout, result.stdout + result.stderr
    assert result.returncode == 0
