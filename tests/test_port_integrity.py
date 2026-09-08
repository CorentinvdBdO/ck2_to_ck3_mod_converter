"""The referential-integrity checks must actually fire.

Faerûn's own history happens to be clean (0 problems over 18124 characters,
`verified` by ``tests/test_characters_faerun.py``), which is exactly why these
tests build broken input by hand: a check that can never fail is not a check.
"""

from __future__ import annotations

from ck2ck3.pdx import Node, parse
from ck2ck3.pdx.tokens import Date
from ck2ck3.port import integrity
from ck2ck3.port.characters import CharacterFacts, CharacterPort
from ck2ck3.port.tables import load_tables

TABLES = load_tables()


def facts_of(text: str) -> dict[str, CharacterFacts]:
    port = CharacterPort(tables=TABLES)
    for entry in parse(text).entries:
        assert isinstance(entry, Node)
        port.convert_character(entry, source="fixture")
    return port.facts


def test_clean_input_passes() -> None:
    facts = facts_of(
        """
        1 = { name = A 1200.1.1 = { birth = yes } 1250.1.1 = { death = yes } }
        2 = { name = B father = 1 dynasty = 7 1230.1.1 = { birth = yes } }
        """
    )
    result = integrity.check(facts, {"fae_7"}, set())
    assert result.clean, result.summary_lines()


def test_dangling_father_is_reported() -> None:
    facts = facts_of("1 = { name = A father = 404 1200.1.1 = { birth = yes } }")
    result = integrity.check(facts, set(), set())
    assert result.counts["dangling father"] == 1
    assert "fae_404" in result.issues[0].detail


def test_dangling_employer_and_spouse_are_reported() -> None:
    facts = facts_of(
        "1 = { name = A 1200.1.1 = { birth = yes employer = 404 add_spouse = 405 } }"
    )
    result = integrity.check(facts, set(), set())
    assert result.counts["dangling employer"] == 1
    assert result.counts["dangling add_spouse"] == 1


def test_dangling_killer_is_reported() -> None:
    facts = facts_of(
        "1 = { name = A 1200.1.1 = { birth = yes } "
        "1250.1.1 = { death = { death_reason = death_murder killer = 404 } } }"
    )
    result = integrity.check(facts, set(), set())
    assert result.counts["dangling killer"] == 1


def test_unknown_dynasty_is_reported() -> None:
    facts = facts_of("1 = { name = A dynasty = 9 1200.1.1 = { birth = yes } }")
    result = integrity.check(facts, {"fae_8"}, set())
    assert result.counts["unknown dynasty"] == 1


def test_unknown_trait_is_reported() -> None:
    facts = facts_of("1 = { name = A trait = brave 1200.1.1 = { birth = yes } }")
    result = integrity.check(facts, set(), known_traits=set())
    assert result.counts["unknown trait"] == 1
    result = integrity.check(facts, set(), known_traits={"brave"})
    assert "unknown trait" not in result.counts


def test_missing_birth_is_reported() -> None:
    facts = facts_of("1 = { name = A }")
    result = integrity.check(facts, set(), set())
    assert result.counts["no birth date"] == 1


def test_death_before_birth_is_reported() -> None:
    facts = facts_of(
        "1 = { name = A 1250.1.1 = { birth = yes } 1200.1.1 = { death = yes } }"
    )
    result = integrity.check(facts, set(), set())
    assert result.counts["death before birth"] == 1


def test_self_parent_is_reported() -> None:
    facts = facts_of("1 = { name = A father = 1 1200.1.1 = { birth = yes } }")
    result = integrity.check(facts, set(), set())
    assert result.counts["self as father"] == 1


def test_only_a_sample_of_details_is_kept_but_the_count_is_exact() -> None:
    result = integrity.IntegrityResult()
    for i in range(50):
        result.add("dangling father", f"fae_{i}")
    assert result.counts["dangling father"] == 50
    assert len(result.issues) == integrity.SAMPLE
    line = result.summary_lines()[0]
    assert line.startswith("dangling father: 50")
    assert "+45 more" in line


def test_birth_and_death_dates_are_taken_from_the_dated_block() -> None:
    facts = facts_of(
        "1 = { name = A 1200.3.4 = { birth = yes } 1260.5.6 = { death = yes } }"
    )
    char = facts["fae_1"]
    assert char.birth == Date(1200, 3, 4)
    assert char.death == Date(1260, 5, 6)
