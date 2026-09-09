#!/usr/bin/env python3
"""Verify every `ck3_key` in the decisions-lane vocabulary tables is real.

"Real" = every dot-separated component of the key is found in
`docs/evidence/ck3_vocab_ground_truth.txt` (`scripts/ck3_vocab_ground_truth.py`
- every `key =` left-hand side used anywhere in CK3 1.19's own
`game/common/` + `game/events/`). A chain like `faith.religious_head` is
checked component-wise, since the ground truth only records single keys.

Checks `mappings/triggers.csv`, `mappings/effects.csv`,
`mappings/event_targets.csv`. Exits non-zero (and lists every miss) if any
non-empty `ck3_key` fails - this is the "a test must fail on an unknown CK3
key" guarantee `docs/mapping_triggers_effects.md` describes; wrapped by
`tests/test_decisions_vocab.py`.

Usage: `uv run scripts/verify_decisions_vocab.py`
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from ck3_vocab_ground_truth import ground_truth  # noqa: E402

TABLES = ("triggers.csv", "effects.csv", "event_targets.csv")

#: Prefixes that are a CK3 saved-scope/list-target reference, not a literal
#: script key - never checked against ground truth (`ck2ck3.decisions_vocab`
#: emits these itself, they are not table content).
SCOPE_PREFIXES = ("scope:", "title:", "faith:", "culture:")


def check(gt: frozenset[str]) -> list[str]:
    misses: list[str] = []
    for name in TABLES:
        path = REPO / "mappings" / name
        with open(path, newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                ck3_key = row.get("ck3_key", "").strip()
                if not ck3_key:
                    continue
                for part in ck3_key.split("."):
                    part = part.strip()
                    if not part or part.startswith(SCOPE_PREFIXES):
                        continue
                    if part not in gt:
                        misses.append(f"{name}: {row['ck2_key']} -> {ck3_key} (component {part!r} not in CK3 1.19 usage)")
    return misses


def main() -> int:
    misses = check(ground_truth())
    if misses:
        print(f"{len(misses)} unverifiable ck3_key value(s):")
        for m in misses:
            print(f"  {m}")
        return 1
    print("all mapped ck3_key values verified against CK3 1.19 usage")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
