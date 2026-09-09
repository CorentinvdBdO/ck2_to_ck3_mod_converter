"""Tests for the decisions-lane vocabulary tables and their verifier.

`mappings/triggers.csv`/`effects.csv`/`event_targets.csv` (goal 1 of lane
`events-decisions`) - shape, and the "must fail on an unknown CK3 key"
guarantee `docs/mapping_triggers_effects.md` describes.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))

from ck2ck3.decisions_vocab import read_vocab_csv  # noqa: E402
from verify_decisions_vocab import check  # noqa: E402

TABLES = ("triggers.csv", "effects.csv", "event_targets.csv")
VALID_STATUS = {"exact", "approx", "none"}
VALID_CONFIDENCE = {"verified", "assumed"}


@pytest.mark.parametrize("name", TABLES)
def test_table_shape(name: str) -> None:
    path = REPO / "mappings" / name
    rows = list(csv.DictReader(open(path, newline="", encoding="utf-8")))
    assert rows, f"{name} is empty"
    seen: set[str] = set()
    for row in rows:
        assert row["ck2_key"], f"{name}: blank ck2_key"
        assert row["ck2_key"] not in seen, f"{name}: duplicate ck2_key {row['ck2_key']!r}"
        seen.add(row["ck2_key"])
        assert row["status"] in VALID_STATUS, f"{name}: {row['ck2_key']} bad status {row['status']!r}"
        assert row["confidence"] in VALID_CONFIDENCE, f"{name}: {row['ck2_key']} bad confidence {row['confidence']!r}"
        if row["status"] == "none":
            assert not row["ck3_key"], f"{name}: {row['ck2_key']} status none but ck3_key set"
            assert row["note"], f"{name}: {row['ck2_key']} status none with no reason"
        else:
            assert row["ck3_key"], f"{name}: {row['ck2_key']} status {row['status']} but no ck3_key"


def test_no_unknown_ck3_key() -> None:
    """The verifier: every non-empty `ck3_key` is real CK3 1.19 vocabulary.

    Fails (with the exact list) if a table row claims a `ck3_key` spelling
    that no vanilla CK3 1.19 script under `common/`/`events/` ever uses -
    the guarantee against inventing a plausible-looking but fictional key.
    """
    from ck3_vocab_ground_truth import ground_truth  # noqa: E402

    misses = check(ground_truth())
    assert misses == [], f"{len(misses)} unverifiable ck3_key value(s): {misses[:10]}"


def test_read_vocab_csv_skips_comments_and_header(tmp_path: Path) -> None:
    path = tmp_path / "t.csv"
    path.write_text(
        "# a comment block\n"
        "ck2_key,ck3_key,status,confidence,note\n"
        "age,age,exact,verified,unchanged\n"
        "wealth,gold,approx,verified,renamed\n"
        "unmappable,,none,verified,no counterpart\n",
        encoding="utf-8",
    )
    rows = read_vocab_csv(path)
    assert rows["age"].ck3_key == "age"
    assert rows["wealth"].ck3_key == "gold"
    assert rows["unmappable"].ck3_key is None
    assert rows["unmappable"].status == "none"


def test_synthetic_unknown_key_is_caught(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The verifier genuinely fails on a fictional key (not a tautology)."""
    from ck3_vocab_ground_truth import ground_truth  # noqa: E402

    bad = tmp_path / "mappings"
    bad.mkdir()
    (bad / "triggers.csv").write_text(
        "ck2_key,ck3_key,status,confidence,note,decision_uses\n"
        "made_up_ck2_key,this_ck3_key_does_not_exist_anywhere,exact,verified,fabricated,1\n",
        encoding="utf-8",
    )
    (bad / "effects.csv").write_text("ck2_key,ck3_key,status,confidence,note,decision_uses\n", encoding="utf-8")
    (bad / "event_targets.csv").write_text("ck2_key,ck3_key,status,confidence,note,decision_uses\n", encoding="utf-8")

    import verify_decisions_vocab as verifier

    monkeypatch.setattr(verifier, "REPO", tmp_path)
    misses = verifier.check(ground_truth())
    assert len(misses) == 1
    assert "this_ck3_key_does_not_exist_anywhere" in misses[0]
