"""Tests for the mapping-table scripts (lane: mappings)."""

from __future__ import annotations

import csv
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from collect_ck2_modifier_keys import classify, parse_leaves, tokenize, walk  # noqa: E402

# A CK2 trait-file fixture: one education trait, one trait with a nested
# command_modifier and an opposites list, and comments in awkward places.
CK2_TRAIT_SNIPPET = """
# a comment with = and { braces }
amateurish_plotter = {
\tattribute = intrigue
\teducation = yes

\tintrigue = 1
\tstewardship = -1
\tcombat_rating = 4 #new value!
}
trained_bard = {
\trandom = no
\tdiplomacy = 1
\tcommand_modifier = {
\t\tcenter = 0.025
\t\tmorale_defence = 0.025
\t}
\topposites = {
\t\tbard
\t\tjourneyman_bard
\t}
\tcaste_tier = 2
}
"""

CK2_BUILDING_SNIPPET = """
castle = {
\tca_wall_1 = {
\t\tdesc = ca_wall_1_desc
\t\ttrigger = { TECH_FORTIFICATIONS_CONSTRUCTION = 0 }
\t\tgold_cost = 50
\t\tbuild_time = 365
\t\tfort_level = 0.5
\t\tlevy_size = 0.025
\t}
}
"""


def test_tokenizer_strips_comments_and_keeps_structure():
    toks = tokenize(CK2_TRAIT_SNIPPET)
    assert "#new" not in toks
    assert toks[:3] == ["amateurish_plotter", "=", "{"]
    assert toks.count("{") == toks.count("}")


def test_walk_reports_paths_and_values():
    leaves = parse_leaves(CK2_TRAIT_SNIPPET)
    by_key = {(p, k): v for p, k, v in leaves}
    assert by_key[(("amateurish_plotter",), "intrigue")] == "1"
    assert by_key[(("amateurish_plotter",), "combat_rating")] == "4"
    assert by_key[(("amateurish_plotter",), "stewardship")] == "-1"
    # nested block: value None, and its children carry the nested path
    assert by_key[(("trained_bard",), "command_modifier")] is None
    assert by_key[(("trained_bard", "command_modifier"), "center")] == "0.025"
    # bare list elements are not leaves
    assert not [k for (p, k), v in by_key.items() if k == "bard"]


def test_walk_is_balanced_on_building_nesting():
    leaves = parse_leaves(CK2_BUILDING_SNIPPET)
    paths = {p for p, _, _ in leaves}
    assert ("castle", "ca_wall_1") in paths
    vals = {k: v for p, k, v in leaves if p == ("castle", "ca_wall_1")}
    assert vals["fort_level"] == "0.5"
    assert vals["levy_size"] == "0.025"


@pytest.mark.parametrize(
    "path,key,kind,expected",
    [
        (("amateurish_plotter",), "intrigue", "trait", "modifier"),
        (("amateurish_plotter",), "education", "trait", "field"),
        (("trained_bard",), "caste_tier", "trait", "field"),
        (("trained_bard", "command_modifier"), "center", "trait", "modifier"),
        (("trained_bard", "opposites"), "bard", "trait", "trigger"),
        (("castle", "ca_wall_1"), "gold_cost", "building", "field"),
        (("castle", "ca_wall_1"), "fort_level", "building", "modifier"),
        (("castle", "ca_wall_1", "trigger"), "TECH_X", "building", "trigger"),
    ],
)
def test_classify(path, key, kind, expected):
    assert classify(path, key, kind) == expected


def test_round_trip_walk_of_a_written_block():
    """parse -> write -> parse gives the same leaves back."""
    leaves = parse_leaves(CK2_TRAIT_SNIPPET)
    lines: list[str] = []
    depth = 0
    for path, key, val in leaves:
        while depth > len(path):
            depth -= 1
            lines.append("\t" * depth + "}")
        indent = "\t" * depth
        if val is None:
            lines.append(f"{indent}{key} = {{")
            depth += 1
        else:
            lines.append(f"{indent}{key} = {val}")
    while depth > 0:
        depth -= 1
        lines.append("\t" * depth + "}")
    again = parse_leaves("\n".join(lines))
    assert again == leaves


# --------------------------------------------------------------------------- #
# mapping-table integrity
# --------------------------------------------------------------------------- #

STATUSES = {"exact", "approx", "none"}


def rows(name: str) -> list[dict[str, str]]:
    with (REPO / "mappings" / name).open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


@pytest.mark.parametrize("name,key_col", [
    ("modifiers.csv", "ck3_key"),
    ("trait_fields.csv", "ck3_key"),
    ("vanilla_traits.csv", "ck3_trait"),
])
def test_status_column_is_valid_and_consistent(name, key_col):
    data = rows(name)
    assert data, f"{name} is empty"
    for r in data:
        assert r["status"] in STATUSES, r
        if r["status"] == "none":
            assert r[key_col] == "", r
        else:
            assert r[key_col], r
        assert r["note"], r


def test_modifiers_csv_columns_and_scales():
    data = rows("modifiers.csv")
    assert list(data[0]) == ["ck2_key", "ck3_key", "scale", "note", "status"]
    for r in data:
        if r["status"] == "none":
            assert r["scale"] == "", r
            assert "comment" in r["note"], r
        else:
            float(r["scale"])  # must parse


def test_no_duplicate_ck2_keys():
    for name, col in [("modifiers.csv", "ck2_key"), ("vanilla_traits.csv", "ck2_trait")]:
        keys = [r[col] for r in rows(name)]
        assert len(keys) == len(set(keys)), name


def test_every_collected_ck2_key_is_mapped():
    """docs/evidence/ck2_modifier_keys.csv and mappings/modifiers.csv agree."""
    ev = REPO / "docs" / "evidence" / "ck2_modifier_keys.csv"
    if not ev.exists():
        pytest.skip("run scripts/collect_ck2_modifier_keys.py first")
    with ev.open(encoding="utf-8") as fh:
        collected = {r["ck2_key"] for r in csv.DictReader(fh)}
    mapped = {r["ck2_key"] for r in rows("modifiers.csv")}
    assert collected - mapped == set()


def test_verify_ck3_keys_script_passes():
    game = Path("/home/cvdbdo/.local/share/Steam/steamapps/common/Crusader Kings III/game")
    if not (game / "common").is_dir():
        pytest.skip("CK3 install not available")
    p = subprocess.run([sys.executable, str(REPO / "scripts" / "verify_ck3_keys.py")],
                       capture_output=True, text=True)
    assert p.returncode == 0, p.stdout + p.stderr
    assert "MISSES: 0" in p.stdout
