"""Integration: convert the real Faerûn characters and dynasties, check counts.

Marked ``slow``; skipped when the Faerûn clone is absent (it is gitignored,
see CLAUDE.md). Asserts the totals the lane promised, that everything the port
writes re-parses, and that the referential-integrity checks come back clean on
the real data — the unit tests in ``test_port_integrity.py`` prove the same
checks fire on broken input.
"""

from __future__ import annotations

import time
import warnings
from pathlib import Path

import pytest

from ck2ck3.pdx import Block, Node, parse, parse_file, write
from ck2ck3.port import integrity
from ck2ck3.port.characters import CharacterPort, convert_character_file
from ck2ck3.port.common import CK2_ENCODING_MARKERS
from ck2ck3.port.dynasties import DynastyPort, convert_dynasty_file
from ck2ck3.port.tables import load_tables

REPO = Path(__file__).resolve().parents[1]
FAERUN = REPO / "Faerun" / "Faerun"

#: `verified` 2026-09-07 by scripts/survey_characters.py against the clone.
FAERUN_CHARACTERS = 18124
FAERUN_CHARACTER_FILES = 80
FAERUN_DYNASTIES = 11952
FAERUN_DYNASTY_FILES = 3
FAERUN_DATED_BLOCKS = 47107
FAERUN_COA = 20
#: The whole port must stay well inside the lane's two-minute budget.
BUDGET_SECONDS = 60

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(not FAERUN.is_dir(), reason="Faerun/ clone absent"),
]


@pytest.fixture(scope="module")
def dynasties() -> tuple[DynastyPort, list[Block]]:
    port = DynastyPort()
    blocks = []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for path in sorted((FAERUN / "common" / "dynasties").glob("*.txt")):
            blocks.append(convert_dynasty_file(parse_file(path), port))
    return port, blocks


@pytest.fixture(scope="module")
def characters() -> tuple[CharacterPort, list[Block], float]:
    port = CharacterPort(tables=load_tables())
    blocks = []
    started = time.monotonic()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for path in sorted((FAERUN / "history" / "characters").glob("*.txt")):
            blocks.append(convert_character_file(parse_file(path), port, source=path.name))
    return port, blocks, time.monotonic() - started


# -- counts ----------------------------------------------------------------
def test_every_character_is_converted(characters) -> None:
    port, blocks, _ = characters
    assert port.report.counts["characters"] == FAERUN_CHARACTERS
    assert len(blocks) == FAERUN_CHARACTER_FILES
    assert sum(len(b) for b in blocks) == FAERUN_CHARACTERS


def test_every_dated_block_is_converted(characters) -> None:
    port, _, _ = characters
    assert port.report.counts["dated_blocks"] == FAERUN_DATED_BLOCKS


def test_every_dynasty_is_converted(dynasties) -> None:
    port, blocks = dynasties
    assert port.report.counts["dynasties"] == FAERUN_DYNASTIES
    assert len(blocks) == FAERUN_DYNASTY_FILES
    assert sum(len(b) for b in blocks) == FAERUN_DYNASTIES


def test_every_dynasty_gets_a_name_but_one_id_is_duplicated(dynasties) -> None:
    """`verified`: Faerûn defines dynasty 15817 twice, and 644 has no culture."""
    port, _ = dynasties
    assert port.report.counts["names"] == FAERUN_DYNASTIES
    assert len(port.loc) == FAERUN_DYNASTIES - 1  # 15817 collapses to one key
    assert port.report.counts["duplicate_ids"] == 1
    assert port.report.counts["dynasties_without_culture"] == 1
    assert any("15817" in w for w in port.report.warnings)


def test_the_twenty_ck2_coats_of_arms_are_recorded(dynasties) -> None:
    port, _ = dynasties
    assert len(port.dropped_coa) == FAERUN_COA


# -- ids -------------------------------------------------------------------
def test_every_character_id_is_prefixed_and_unique(characters) -> None:
    port, blocks, _ = characters
    ids = [e.key for b in blocks for e in b.entries if isinstance(e, Node)]
    assert len(ids) == len(set(ids)) == FAERUN_CHARACTERS
    assert all(i.startswith("fae_") for i in ids)


def test_no_bare_ck2_id_survives_in_a_reference(characters) -> None:
    """Every emitted father/mother/employer/spouse value carries the prefix."""
    port, blocks, _ = characters
    checked = 0
    for block in blocks:
        for node in _walk_nodes(block):
            if node.key in ("father", "mother", "employer", "dynasty", "killer",
                            "add_spouse", "add_matrilineal_spouse", "remove_spouse",
                            "add_concubine"):
                assert str(node.value).startswith("fae_"), f"{node.key} = {node.value}"
                checked += 1
    assert checked > 30_000


# -- integrity -------------------------------------------------------------
def test_faerun_history_has_no_dangling_references(characters, dynasties) -> None:
    port, _, _ = characters
    dyn_port, _ = dynasties
    tables = port.tables
    result = integrity.check(
        port.facts, set(dyn_port.id_map.values()), set(tables.known_traits.values())
    )
    assert result.clean, "\n".join(result.summary_lines())


def test_every_character_has_a_birth_date(characters) -> None:
    port, _, _ = characters
    assert all(f.birth is not None for f in port.facts.values())


# -- output is valid script ------------------------------------------------
def test_every_written_file_reparses_with_the_same_character_count(characters) -> None:
    port, blocks, _ = characters
    for block in blocks:
        text = write(block)
        reparsed = parse(text)
        assert not reparsed.problems, reparsed.problems[:3]
        assert len(reparsed) == len(block)


def test_every_written_dynasty_file_reparses(dynasties) -> None:
    _, blocks = dynasties
    for block in blocks:
        reparsed = parse(write(block))
        assert not reparsed.problems, reparsed.problems[:3]
        assert len(reparsed) == len(block)


def test_no_ck2_codepage_marker_reaches_the_output(characters, dynasties) -> None:
    _, char_blocks, _ = characters
    _, dyn_blocks = dynasties
    for block in [*char_blocks, *dyn_blocks]:
        for line in write(block).splitlines():
            assert line.strip("# \t") not in CK2_ENCODING_MARKERS


# -- budget ----------------------------------------------------------------
def test_the_character_port_is_fast_enough(characters) -> None:
    _, _, seconds = characters
    assert seconds < BUDGET_SECONDS, f"{seconds:.1f}s for {FAERUN_CHARACTERS} characters"


# -- losses are bounded and reported --------------------------------------
def test_dropped_keys_are_all_accounted_for_by_the_tables(characters) -> None:
    """No drop may carry the 'no row in the table' reason: the table is complete."""
    port, _, _ = characters
    unmapped = {
        (key, level)
        for (key, level, reason), _n in port.report.dropped.items()
        if reason.startswith("no row in")
    }
    assert not unmapped, sorted(unmapped)


def test_no_unmapped_key_warnings_on_the_real_mod(characters) -> None:
    port, _, _ = characters
    assert [w for w in port.report.warnings if "unmapped" in w] == []


def _walk_nodes(block: Block):
    for entry in block.entries:
        if isinstance(entry, Node):
            yield entry
            if isinstance(entry.value, Block):
                yield from _walk_nodes(entry.value)
