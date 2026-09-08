#!/usr/bin/env python3
"""Summary tables for `docs/events_provenance.md`, read back from the CSVs
`scripts/events_provenance.py` writes.

Prints (does not write files):
  * status x kind table for events/decisions/on_actions
  * top 15 event namespaces by modified-count (namespace = the part of the id
    before the first `.`; a bare numeric id has no namespace, bucketed as
    `<numeric>`)
  * how many `modified` events differ only in loc/desc-shaped keys
    (`events_provenance.LOC_ONLY_EVENT_KEYS`) vs touch anything else (logic)
  * duplicate-id counts per source

Usage:
    uv run scripts/events_provenance_summary.py [--evidence-dir DIR]
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from events_provenance import LOC_ONLY_EVENT_KEYS  # noqa: E402


def load(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def namespace_of(event_id: str) -> str:
    return event_id.split(".", 1)[0] if "." in event_id else "<numeric>"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--evidence-dir", type=Path, default=REPO / "docs" / "evidence")
    args = ap.parse_args(argv)

    events = load(args.evidence_dir / "events_provenance.csv")
    decisions = load(args.evidence_dir / "decisions_provenance.csv")
    on_actions = load(args.evidence_dir / "on_actions_provenance.csv")

    for name, rows in (("events", events), ("decisions", decisions), ("on_actions", on_actions)):
        print(f"== {name}: status x kind ==")
        c = Counter((r["status"], r["kind"]) for r in rows)
        for (status, kind), n in sorted(c.items()):
            print(f"  {status:10s} {kind:22s} {n}")
        print()

    print("== events: top 15 namespaces by modified-count ==")
    mod_ns = Counter(namespace_of(r["id"]) for r in events if r["status"] == "modified")
    for ns, n in mod_ns.most_common(15):
        print(f"  {ns:20s} {n}")
    print()

    modified = [r for r in events if r["status"] == "modified"]
    loc_only = sum(
        1
        for r in modified
        if r["changed_keys"]
        and set(r["changed_keys"].split(";")) <= LOC_ONLY_EVENT_KEYS
    )
    logic = len(modified) - loc_only
    print(f"== modified events: {loc_only} loc/desc-only, {logic} touch logic (of {len(modified)}) ==")
    print()

    print("== duplicate ids (dup_count > 1) ==")
    for name, rows in (("events", events), ("decisions", decisions)):
        vdup = sum(1 for r in rows if int(r["vanilla_dup_count"] or 0) > 1)
        fdup = sum(1 for r in rows if int(r["faerun_dup_count"] or 0) > 1)
        print(f"  {name}: {vdup} vanilla ids duplicated, {fdup} faerun ids duplicated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
