#!/usr/bin/env python3
"""Survey the CK2 trigger/effect vocabulary used by Faerûn's emit-eligible decisions.

"Emit-eligible" = ``kind`` in {decisions, society_decisions, plot_decisions}
(character-scope decision groups, see ``docs/step_decisions.md`` §1) and
``status`` in {new, modified}, per ``docs/evidence/decisions_provenance.csv``.

Walks each decision's ``potential``/``from_potential``/``allow``/``ai_will_do``
sections (trigger-shaped) and its ``effect`` section (effect-shaped)
separately, and tallies every block/comparison key seen (excluding logic
operators AND/OR/NOT/NOR/ROOT/FROM/... and bare numeric keys used inside
``random_list``/``ai_will_do`` weighted blocks).

Writes ``docs/evidence/decisions_vocab_survey.csv`` (key,section,count) — the
input to building ``mappings/triggers.csv``/``effects.csv``/``event_targets.csv``.

Usage: ``uv run scripts/decisions_vocab_survey.py``
"""

from __future__ import annotations

import csv
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from ck2ck3.pdx import Block, Node, parse_file  # noqa: E402

DEFAULT_CK2_MOD = REPO / "Faerun" / "Faerun"
PROVENANCE = REPO / "docs" / "evidence" / "decisions_provenance.csv"
OUT = REPO / "docs" / "evidence" / "decisions_vocab_survey.csv"

#: Character-scope decision groups; the only ones the `decisions` step emits.
EMIT_KINDS = frozenset({"decisions", "society_decisions", "plot_decisions"})
STATUSES = frozenset({"new", "modified"})

TRIGGER_SECTIONS = ("potential", "from_potential", "allow", "ai_will_do", "ai_potential")
EFFECT_SECTIONS = ("effect",)

#: Not real trigger/effect keys: scope words, logic blocks, jomini operators.
SKIP_KEYS = frozenset(
    {
        "root", "from", "fromfrom", "fromfromfrom", "prev", "prevprev",
        "prevprevprev", "this", "and", "or", "not", "nor", "if", "else",
        "else_if", "limit", "trigger", "value", "modifier", "factor",
        "weight",
    }
)


def is_number(key: str) -> bool:
    try:
        float(key)
        return True
    except ValueError:
        return False


def walk_keys(value, counter: Counter, *, depth: int = 0) -> None:
    if not isinstance(value, Block):
        return
    for entry in value.entries:
        if isinstance(entry, Node):
            key = entry.key.lower()
            if key not in SKIP_KEYS and not is_number(key):
                counter[entry.key] += 1
            walk_keys(entry.value, counter, depth=depth + 1)


def find_decision_block(doc_block: Block, kind: str, decision_id: str) -> Block | None:
    for entry in doc_block.entries:
        if isinstance(entry, Node) and entry.key == kind and isinstance(entry.value, Block):
            for sub in entry.value.entries:
                if isinstance(sub, Node) and sub.key == decision_id and isinstance(sub.value, Block):
                    return sub.value
    return None


def main() -> None:
    ck2_mod = DEFAULT_CK2_MOD
    trigger_counts: Counter[str] = Counter()
    effect_counts: Counter[str] = Counter()
    parsed_cache: dict[Path, Block] = {}
    n_decisions = 0
    n_missing = 0

    with open(PROVENANCE, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = [
            row
            for row in reader
            if row["kind"] in EMIT_KINDS and row["status"] in STATUSES
        ]

    for row in rows:
        rel = row["faerun_file"]
        path = ck2_mod / rel
        if path not in parsed_cache:
            try:
                parsed_cache[path] = parse_file(path, lenient=True)
            except Exception as exc:  # noqa: BLE001
                print(f"parse error {path}: {exc}", file=sys.stderr)
                parsed_cache[path] = Block()
        block = find_decision_block(parsed_cache[path], row["kind"], row["id"])
        if block is None:
            n_missing += 1
            continue
        n_decisions += 1
        for entry in block.entries:
            if not isinstance(entry, Node):
                continue
            if entry.key in TRIGGER_SECTIONS:
                walk_keys(entry.value, trigger_counts)
            elif entry.key in EFFECT_SECTIONS:
                walk_keys(entry.value, effect_counts)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["key", "section", "count"])
        for key, count in trigger_counts.most_common():
            writer.writerow([key, "trigger", count])
        for key, count in effect_counts.most_common():
            writer.writerow([key, "effect", count])

    print(f"decisions surveyed: {n_decisions} (missing block: {n_missing})")
    print(f"distinct trigger-section keys: {len(trigger_counts)}")
    print(f"distinct effect-section keys: {len(effect_counts)}")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
