"""Tests for scripts/events_provenance.py (lane: events-provenance).

Fast, fixture-based: writes tiny CK2 `events/`, `decisions/` and
`common/on_actions/` trees to `tmp_path` for a synthetic "vanilla" and
"faerun" pair covering new/kept/modified/deleted, a duplicate id, the
on_actions merge-across-files behaviour, and the mechanic-keyword heuristic.
No dependency on the real Faerûn clone or CK2 install.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from events_provenance import (  # noqa: E402
    classify,
    collect_decisions,
    collect_events,
    collect_on_actions,
    mechanic_hits,
    run,
)


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture()
def trees(tmp_path: Path) -> tuple[Path, Path]:
    vanilla = tmp_path / "vanilla"
    faerun = tmp_path / "faerun"

    _write(
        vanilla,
        "events/x_events.txt",
        """
character_event = {
\tid = 1
\ttrigger = { is_female = yes }
\tdesc = evt_1_desc
\toption = { name = ok }
}
character_event = {
\tid = 2
\ttrigger = { always = yes }
}
letter_event = {
\tid = 3
\tdesc = evt_3_desc
}
character_event = {
\tid = 5
\ttrigger = { always = yes }
}
character_event = {
\tid = 6
\ttrigger = { always = yes }
}
character_event = {
\tid = 6
\ttrigger = { always = no }
}
""",
    )
    _write(
        faerun,
        "events/x_events.txt",
        """
character_event = {
\tid = 1
\ttrigger = { is_female = yes }
\tdesc = evt_1_desc_changed
\toption = { name = ok }
}
character_event = {
\tid = 4
\ttrigger = { always = yes }
\timmediate = { join_society = my_society }
}
character_event = {
\tid = 5
\ttrigger = { always = yes }
}
""",
    )

    _write(
        vanilla,
        "decisions/d.txt",
        """
decisions = {
\tbuild_hospital = {
\t\tpotential = { always = yes }
\t\trevoke_allowed = { always = no }
\t}
\tremove_the_thing = {
\t\tpotential = { always = yes }
\t}
}
""",
    )
    _write(
        faerun,
        "decisions/d.txt",
        """
decisions = {
\tbuild_hospital = {
\t\tpotential = { always = yes }
\t}
\tnew_faerun_decision = {
\t\tpotential = { always = no }
\t}
}
""",
    )

    _write(
        vanilla,
        "common/on_actions/00_on_actions.txt",
        """
on_startup = {
\tevents = {
\t\t1 # first
\t\t2 # second
\t}
}
on_only_vanilla = {
\tevents = { 9 }
}
""",
    )
    _write(
        faerun,
        "common/on_actions/00_on_actions.txt",
        """
on_startup = {
\tevents = {
\t\t1 # first
\t\t2 # second
\t}
}
""",
    )
    _write(
        faerun,
        "common/on_actions/faerun_extra.txt",
        """
on_startup = {
\tevents = {
\t\t42 # faerun addition, same on_action, different file
\t}
}
""",
    )

    return vanilla, faerun


def test_events_classification(trees: tuple[Path, Path]) -> None:
    vanilla, faerun = trees
    v = collect_events(vanilla)
    f = collect_events(faerun)
    rows = {r.id: r for r in classify(v, f)}

    assert rows["1"].status == "modified"
    assert rows["1"].changed_keys == "desc"

    assert rows["2"].status == "deleted"
    assert rows["3"].status == "deleted"

    assert rows["4"].status == "new"
    assert "societies" in rows["4"].uses_faerun_mechanic

    assert rows["5"].status == "kept"
    assert rows["5"].changed_keys == ""

    # duplicate id 6 in vanilla only: recorded, not merged, comparison uses
    # the first occurrence; vanilla_dup_count reflects both.
    assert rows["6"].vanilla_dup_count == 2
    assert rows["6"].status == "deleted"


def test_decisions_classification(trees: tuple[Path, Path]) -> None:
    vanilla, faerun = trees
    v = collect_decisions(vanilla)
    f = collect_decisions(faerun)
    rows = {r.id: r for r in classify(v, f)}

    assert rows["build_hospital"].status == "modified"
    assert rows["build_hospital"].changed_keys == "revoke_allowed"
    assert rows["remove_the_thing"].status == "deleted"
    assert rows["new_faerun_decision"].status == "new"


def test_on_actions_merge_across_files(trees: tuple[Path, Path]) -> None:
    vanilla, faerun = trees
    v = collect_on_actions(vanilla)
    f = collect_on_actions(faerun)
    rows = {r.id: r for r in classify(v, f, merge_multi=True)}

    # Faerûn's on_startup is defined identically to vanilla's in one file,
    # plus an extra `events` block in a second file -- the merge must see
    # that addition and call it modified, not kept.
    assert rows["on_startup"].status == "modified"
    assert "events" in rows["on_startup"].changed_keys.split(";")
    assert rows["on_startup"].faerun_files == "common/on_actions/00_on_actions.txt;common/on_actions/faerun_extra.txt"

    assert rows["on_only_vanilla"].status == "deleted"


def test_mechanic_hits_keyword_match() -> None:
    from ck2ck3.pdx import parse

    block = parse("immediate = { join_society = yes }\n")
    assert "societies" in mechanic_hits(block)

    block2 = parse("trigger = { is_female = yes }\n")
    assert mechanic_hits(block2) == ""


def test_run_end_to_end(trees: tuple[Path, Path]) -> None:
    vanilla, faerun = trees
    results = run(vanilla, faerun)
    assert set(results) == {"events", "decisions", "on_actions"}
    assert len(results["events"]) == 6  # ids 1,2,3,4,5,6
    assert len(results["decisions"]) == 3
    assert len(results["on_actions"]) == 2
