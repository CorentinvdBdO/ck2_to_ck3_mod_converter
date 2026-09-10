#!/usr/bin/env python3
"""Survey Faerûn's `new` CK2 events: shapes, vocabulary, pictures, namespaces.

Lane `events` (README §5 step 3). Reads `docs/evidence/events_provenance.csv`
(lane `events-provenance`, a fixed snapshot) and every Faerûn event file it
names, and writes four evidence CSVs:

* ``docs/evidence/events_top_level_keys.csv``  — CK2 event top-level key -> uses
* ``docs/evidence/events_vocab_survey.csv``    — trigger/effect key -> uses, by section kind
* ``docs/evidence/events_pictures.csv``        — CK2 `picture`/`border` value -> uses
* ``docs/evidence/events_namespaces.csv``      — CK2 namespace -> events, files

Usage: ``uv run scripts/events_vocab_survey.py`` (~10 s).
"""

from __future__ import annotations

import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from ck2ck3.pdx import Block, Item, Node, parse_file  # noqa: E402

PROVENANCE = REPO / "docs" / "evidence" / "events_provenance.csv"
CK2_MOD = REPO / "Faerun" / "Faerun"
EVIDENCE = REPO / "docs" / "evidence"

#: CK2 event sections and the vocabulary table their body belongs to.
TRIGGER_SECTIONS = {"trigger", "is_triggered_only_trigger", "mean_time_to_happen"}
EFFECT_SECTIONS = {"immediate", "after"}
#: `option = { ... }` bodies are effect-shaped apart from their own
#: `trigger`/`ai_chance`/`name`/`tooltip` fields.
OPTION_TRIGGER_FIELDS = {"trigger", "ai_chance"}

STRUCTURAL = {
    "and", "or", "not", "nor", "nand", "if", "else", "else_if",
    "hidden_tooltip", "custom_tooltip", "random_list", "random",
    "limit", "trigger", "modifier", "factor", "value", "any_",
}


def _walk(block: Block, kind: str, tally: dict[str, Counter]) -> None:
    for entry in block.entries:
        if not isinstance(entry, Node):
            continue
        key = entry.key
        low = key.lower()
        if low in ("limit",):
            child_kind = "trigger"
        elif low in ("modifier", "factor", "value"):
            child_kind = "trigger"
        else:
            child_kind = kind
        if low not in STRUCTURAL and not low.isdigit():
            tally[kind][low] += 1
        if isinstance(entry.value, Block):
            _walk(entry.value, child_kind, tally)


def main() -> int:
    rows = [
        r for r in csv.DictReader(open(PROVENANCE, encoding="utf-8"))
        if r["status"] == "new"
    ]
    by_file: dict[str, list[str]] = defaultdict(list)
    for r in rows:
        by_file[r["faerun_file"]].append(r["id"])

    top_keys: Counter = Counter()
    vocab: dict[str, Counter] = {"trigger": Counter(), "effect": Counter()}
    pictures: Counter = Counter()
    borders: Counter = Counter()
    ns_events: Counter = Counter()
    ns_files: dict[str, set[str]] = defaultdict(set)
    kinds: Counter = Counter()
    mtth = 0
    event_calls: Counter = Counter()
    option_counts: Counter = Counter()
    found = 0

    for rel, ids in sorted(by_file.items()):
        path = CK2_MOD / rel
        doc = parse_file(path, lenient=True, encoding="auto")
        wanted = set(ids)
        namespace = None
        for entry in doc.entries:
            if isinstance(entry, Node) and entry.key == "namespace":
                namespace = str(entry.value)
            if not isinstance(entry, Node) or not isinstance(entry.value, Block):
                continue
            if not entry.key.endswith("_event"):
                continue
            body = entry.value
            eid = None
            for sub in body.entries:
                if isinstance(sub, Node) and sub.key == "id":
                    eid = str(sub.value)
            if eid is None or eid not in wanted:
                continue
            found += 1
            kinds[entry.key] += 1
            ns = eid.split(".")[0] if "." in eid else "<numeric>"
            ns_events[ns] += 1
            ns_files[ns].add(rel)
            nopt = 0
            for sub in body.entries:
                if not isinstance(sub, Node):
                    continue
                k = sub.key.lower()
                top_keys[k] += 1
                if k == "picture":
                    pictures[str(sub.value)] += 1
                elif k == "border":
                    borders[str(sub.value)] += 1
                elif k == "mean_time_to_happen":
                    mtth += 1
                elif k == "option":
                    nopt += 1
                if isinstance(sub.value, Block):
                    if k in TRIGGER_SECTIONS:
                        _walk(sub.value, "trigger", vocab)
                    elif k in EFFECT_SECTIONS:
                        _walk(sub.value, "effect", vocab)
                    elif k == "option":
                        for osub in sub.value.entries:
                            if not isinstance(osub, Node):
                                continue
                            ok = osub.key.lower()
                            if ok in ("name", "tooltip"):
                                continue
                            if isinstance(osub.value, Block):
                                _walk(
                                    osub.value,
                                    "trigger" if ok in OPTION_TRIGGER_FIELDS else "effect",
                                    vocab,
                                )
                            elif ok not in STRUCTURAL:
                                vocab["effect"][ok] += 1
            option_counts[nopt] += 1
            _collect_event_calls(body, event_calls)

    EVIDENCE.mkdir(parents=True, exist_ok=True)
    _write(EVIDENCE / "events_top_level_keys.csv", ["key", "uses"], top_keys.most_common())
    _write(
        EVIDENCE / "events_vocab_survey.csv",
        ["kind", "key", "uses"],
        [(kind, k, n) for kind in ("trigger", "effect") for k, n in vocab[kind].most_common()],
    )
    _write(
        EVIDENCE / "events_pictures.csv",
        ["field", "value", "uses"],
        [("picture", k, n) for k, n in pictures.most_common()]
        + [("border", k, n) for k, n in borders.most_common()],
    )
    _write(
        EVIDENCE / "events_namespaces.csv",
        ["namespace", "events", "files"],
        [(ns, n, ";".join(sorted(ns_files[ns]))) for ns, n in ns_events.most_common()],
    )

    print(f"new events in provenance: {len(rows)}; found in source: {found}")
    print(f"kinds: {dict(kinds)}")
    print(f"namespaces: {len(ns_events)} (bare-numeric ids: {ns_events['<numeric>']})")
    print(f"mean_time_to_happen: {mtth}")
    print(f"distinct trigger keys {len(vocab['trigger'])}, effect keys {len(vocab['effect'])}")
    print(f"options per event: {sorted(option_counts.items())}")
    print(f"event-firing calls: {sum(event_calls.values())} to {len(event_calls)} distinct ids")
    return 0


def _collect_event_calls(block: Block, tally: Counter) -> None:
    for entry in block.entries:
        if not isinstance(entry, Node):
            continue
        if entry.key in (
            "character_event", "letter_event", "narrative_event",
            "long_character_event", "province_event", "society_quest_event",
        ) and isinstance(entry.value, Block):
            for sub in entry.value.entries:
                if isinstance(sub, Node) and sub.key == "id":
                    tally[str(sub.value)] += 1
        if isinstance(entry.value, Block):
            _collect_event_calls(entry.value, tally)


def _write(path: Path, header: list[str], rows) -> None:
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        for row in rows:
            writer.writerow(row)


if __name__ == "__main__":
    raise SystemExit(main())
