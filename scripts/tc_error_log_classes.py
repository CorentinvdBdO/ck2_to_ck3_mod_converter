#!/usr/bin/env python3
"""Summarise a CK3 ``error.log`` by class, and say which of it a mod now shadows.

The playtest log is the only evidence that says what the *running* game trips
over, so lane `tc-template` measures itself against it rather than against
ck3-tiger alone (tiger never evaluates a trigger).

Two reports:

* per class — the ``<source>.cpp`` the engine logged from, with the message
  shape, so "before" and "after" runs can be compared line for line;
* per script location for the ``title_links`` class — the vanilla file whose
  trigger named a title that does not exist, with a ``shadowed`` column when a
  mod directory is given, so the projected drop is a fact and not a guess.

    uv run scripts/tc_error_log_classes.py <error.log> [--mod DIR] [--out CSV]

``--mod`` is a generated mod directory; a script location counts as shadowed
when that directory holds a file at the same relative path.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

#: ``[19:22:43][E][title_links.cpp:214]: <message>``
LINE_RE = re.compile(r"^\[\d\d:\d\d:\d\d\]\[E\]\[([A-Za-z0-9_]+)\.cpp:\d+\]: (.*)$")
#: The script location a jomini or title_links error carries.
FILE_RE = re.compile(r"file: (\S+)")
#: Quoted names and bare numbers differ per occurrence, not per class.
SHAPE_QUOTED = re.compile(r"'[^']*'")
SHAPE_DIGITS = re.compile(r"\d+")


def shape(message: str) -> str:
    """Collapse one message to its class: quoted names and numbers blanked."""
    return SHAPE_DIGITS.sub("N", SHAPE_QUOTED.sub("'X'", message))


def read_log(path: Path) -> tuple[Counter[tuple[str, str]], Counter[str]]:
    """``(per-class counts, per-script-file counts for title_links)``."""
    classes: Counter[tuple[str, str]] = Counter()
    title_files: Counter[str] = Counter()
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            match = LINE_RE.match(line.rstrip("\n"))
            if not match:
                continue
            source, message = match.groups()
            classes[(source, shape(message))] += 1
            if source == "title_links":
                where = FILE_RE.search(message)
                if where:
                    title_files[where.group(1)] += 1
    return classes, title_files


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", type=Path)
    parser.add_argument(
        "--mod",
        type=Path,
        default=None,
        help="generated mod directory; a script location it holds counts as shadowed",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=REPO_ROOT / "docs" / "evidence" / "tc_template_error_classes.csv",
    )
    args = parser.parse_args(argv)

    if not args.log.is_file():
        print(f"log not found: {args.log}", file=sys.stderr)
        return 2
    classes, title_files = read_log(args.log)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["source", "count", "message_shape"])
        for (source, message), count in classes.most_common():
            writer.writerow([source, count, message])

    total = sum(classes.values())
    print(f"{total} error lines, {len(classes)} classes -> {args.out}")
    per_source: Counter[str] = Counter()
    for (source, _), count in classes.items():
        per_source[source] += count
    for source, count in per_source.most_common(12):
        print(f"  {count:>8}  {source}.cpp")

    if title_files:
        shadowed = 0
        rows: list[tuple[str, int, str]] = []
        for where, count in title_files.most_common():
            hit = bool(args.mod and (args.mod / where).is_file())
            shadowed += count if hit else 0
            rows.append((where, count, "yes" if hit else "no"))
        title_out = args.out.with_name("tc_template_title_links.csv")
        with title_out.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["script_file", "errors", "shadowed_by_mod"])
            writer.writerows(rows)
        total_title = sum(title_files.values())
        print(
            f"\ntitle_links: {total_title} errors over {len(title_files)} vanilla "
            f"files -> {title_out}"
        )
        if args.mod:
            share = 100.0 * shadowed / total_title if total_title else 0.0
            print(
                f"  {shadowed} of them ({share:.1f} %) come from a file "
                f"{args.mod.name} now shadows"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
