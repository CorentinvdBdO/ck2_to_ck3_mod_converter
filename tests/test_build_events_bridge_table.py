"""Tests for scripts/build_events_bridge_table.py (lane: events-provenance).

Checks the mechanics that matter for correctness: only `kept`/`modified` rows
whose vanilla file is in `FILE_COUNTERPARTS` are emitted, the CK2-side
evidence line is the real line the id was parsed at (not a guess), and a
`none` counterpart carries no CK3 evidence.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from build_events_bridge_table import FILE_COUNTERPARTS, main  # noqa: E402


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_file_counterparts_well_formed() -> None:
    assert len(FILE_COUNTERPARTS) >= 10
    for vfile, (ck3, kind, confidence, reason) in FILE_COUNTERPARTS.items():
        assert vfile.startswith("events/")
        assert kind in ("event_folder", "system", "none")
        assert reason
        if kind == "none":
            assert ck3 == ""
        else:
            assert ck3


def test_build_bridge_table(tmp_path: Path) -> None:
    # A CK2 vanilla tree with one file that IS in FILE_COUNTERPARTS
    # (events/plot_events.txt) and one that is not.
    ck2_game = tmp_path / "ck2"
    covered_file, (ck3, kind, confidence, reason) = next(iter(FILE_COUNTERPARTS.items()))
    _write(
        ck2_game,
        covered_file,
        """
character_event = {
\tid = 424242
\ttrigger = { always = yes }
}
""",
    )
    _write(
        ck2_game,
        "events/uncovered_events.txt",
        """
character_event = {
\tid = 999999
\ttrigger = { always = yes }
}
""",
    )

    evidence_csv = tmp_path / "events_provenance.csv"
    with evidence_csv.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(
            [
                "id",
                "kind",
                "faerun_file",
                "vanilla_file",
                "status",
                "changed_keys",
                "uses_faerun_mechanic",
                "vanilla_dup_count",
                "faerun_dup_count",
            ]
        )
        w.writerow(["424242", "character_event", "events/x.txt", covered_file, "kept", "", "", 1, 1])
        w.writerow(
            ["999999", "character_event", "events/x.txt", "events/uncovered_events.txt", "kept", "", "", 1, 1]
        )
        w.writerow(["1", "character_event", "", covered_file, "deleted", "", "", 1, 0])

    out_csv = tmp_path / "bridge.csv"
    rc = main(
        [
            "--ck2-game",
            str(ck2_game),
            "--evidence-csv",
            str(evidence_csv),
            "--out",
            str(out_csv),
        ]
    )
    assert rc == 0

    rows = list(csv.DictReader(out_csv.open(encoding="utf-8")))
    ids = {r["ck2_id"] for r in rows}
    # only the kept/modified id from the covered file is emitted
    assert ids == {"424242"}
    row = rows[0]
    # Definition.line is the event block's own opening line (`character_event
    # = {`), not the `id =` line one below it -- see collect_events.
    assert row["evidence_ck2"] == f"{covered_file}:2"
    assert row["ck3_counterpart"] == ck3
    assert row["confidence"] == confidence
    if kind == "none":
        assert row["evidence_ck3"] == "n/a"
    else:
        assert row["evidence_ck3"].startswith("game/events/")
