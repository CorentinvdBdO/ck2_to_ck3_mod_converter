"""Tests for `ck2ck3.traits.conflicts` (docs/step_traits.md rule 3)."""

from __future__ import annotations

from pathlib import Path

from ck2ck3.traits import TraitConflicts, read_trait_conflicts


def test_read_trait_conflicts_reads_opposites_and_group_level(tmp_path: Path) -> None:
    traits = tmp_path / "common" / "traits"
    traits.mkdir(parents=True)
    (traits / "00_traits.txt").write_text(
        "sadistic = { opposites = { compassionate } }\n"
        "compassionate = { opposites = { sadistic } }\n"
        "beauty_bad_1 = { opposites = { beauty_good beauty_bad_2 } "
        "group = beauty_bad level = 1 }\n"
        "beauty_bad_2 = { opposites = { beauty_good beauty_bad_1 } "
        "group = beauty_bad level = 2 }\n"
        "education_intrigue_1 = { group = education_intrigue level = 1 }\n"
        "education_intrigue_2 = { group = education_intrigue level = 2 }\n",
        encoding="utf-8",
    )
    conflicts = read_trait_conflicts(traits)
    assert conflicts.opposites["sadistic"] == frozenset({"compassionate"})
    assert conflicts.group_level["beauty_bad_1"] == ("beauty_bad", 1)
    assert conflicts.group_level["education_intrigue_2"] == ("education_intrigue", 2)


def test_read_trait_conflicts_on_a_missing_dir_is_empty(tmp_path: Path) -> None:
    conflicts = read_trait_conflicts(tmp_path / "no" / "such" / "dir")
    assert conflicts.opposites == {}
    assert conflicts.group_level == {}


def test_conflict_identical_id() -> None:
    conflicts = TraitConflicts()
    assert conflicts.conflict(["sadistic"], "sadistic") == "sadistic"
    assert conflicts.conflict(["sadistic"], "compassionate") is None


def test_conflict_mutual_opposites_either_direction() -> None:
    conflicts = TraitConflicts(opposites={"sadistic": frozenset({"compassionate"})})
    assert conflicts.conflict(["sadistic"], "compassionate") == "sadistic"
    # the reverse direction is not declared explicitly, but must still count
    assert conflicts.conflict(["compassionate"], "sadistic") == "compassionate"


def test_conflict_opposes_a_whole_group_by_bare_token() -> None:
    """`beauty_bad_1` opposes the bare group token `beauty_good`, matching
    ANY trait of that group (CK3's own convention, `verified` 00_traits.txt
    :6824-6830)."""
    conflicts = TraitConflicts(
        opposites={"beauty_bad_1": frozenset({"beauty_good"})},
        group_level={"beauty_good_2": ("beauty_good", 2)},
    )
    assert conflicts.conflict(["beauty_bad_1"], "beauty_good_2") == "beauty_bad_1"


def test_conflict_same_group_different_level() -> None:
    conflicts = TraitConflicts(
        group_level={
            "education_intrigue_1": ("education_intrigue", 1),
            "education_intrigue_2": ("education_intrigue", 2),
        }
    )
    assert (
        conflicts.conflict(["education_intrigue_1"], "education_intrigue_2")
        == "education_intrigue_1"
    )


def test_conflict_first_listed_wins_order() -> None:
    """The first of ``held`` that conflicts is returned; ``held`` is CK2
    declaration order, so the caller keeps the first-listed trait."""
    conflicts = TraitConflicts(opposites={"a": frozenset({"c"})})
    assert conflicts.conflict(["a", "b"], "c") == "a"


def test_no_conflict_for_unrelated_traits() -> None:
    conflicts = TraitConflicts(opposites={"brave": frozenset({"craven"})})
    assert conflicts.conflict(["brave"], "greedy") is None
