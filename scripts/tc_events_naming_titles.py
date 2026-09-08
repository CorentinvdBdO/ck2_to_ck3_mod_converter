#!/usr/bin/env python3
"""Hand-off to the events lane: every vanilla event file that names a vanilla title.

Lane `tc-template` deliberately leaves ``events/`` alone except for
``events/decisions_events`` and ``events/story_cycles``, whose callers it also
shadows. Blanking any other event file would delete definitions an ``on_action``
entry the mod keeps still lists, which is worse than the dangling title
(``docs/output_bootstrap.md`` §4). So the remainder is written down here instead
of guessed at later.

One row per vanilla event file, with how many vanilla titles it names, how many
of them are county or barony tier (the tiers a landless-title layer cannot
rescue), and the first few tags.

    uv run scripts/tc_events_naming_titles.py [--game DIR] [--mod DIR] [--out CSV]

``--mod`` is a generated mod; a file it already shadows is left out of the list.
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from ck2ck3.tcshadow import (  # noqa: E402
    SCRIPT_SUFFIXES,
    TITLE_SCOPE_RE,
    TOKEN_RE,
    strip_comments,
    vanilla_ids,
)

DEFAULT_GAME = Path(
    "/home/cvdbdo/.local/share/Steam/steamapps/common/Crusader Kings III/game"
)
#: A county or barony needs a province, so no landless-title layer can make one
#: of these resolve; they can only be rewritten or deleted.
UNRESCUABLE_TIERS = ("c_", "b_")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game", type=Path, default=DEFAULT_GAME)
    parser.add_argument("--mod", type=Path, default=None)
    parser.add_argument(
        "--out",
        type=Path,
        default=REPO_ROOT / "docs" / "evidence" / "vanilla_events_naming_titles.csv",
    )
    args = parser.parse_args(argv)
    game = args.game
    if not (game / "events").is_dir():
        print(f"no events/ under {game}", file=sys.stderr)
        return 2
    ids = vanilla_ids(game)

    rows: list[dict[str, object]] = []
    for path in sorted((game / "events").rglob("*")):
        if not path.is_file() or path.suffix not in SCRIPT_SUFFIXES:
            continue
        rel = path.relative_to(game).as_posix()
        if args.mod and (args.mod / rel).is_file():
            continue
        text = strip_comments(path.read_text(encoding="utf-8-sig", errors="replace"))
        tags = Counter(t for t in TOKEN_RE.findall(text) if t in ids.titles)
        if not tags:
            continue
        scoped = sum(1 for t in TITLE_SCOPE_RE.findall(text) if t in ids.titles)
        unrescuable = sum(
            n for tag, n in tags.items() if tag.startswith(UNRESCUABLE_TIERS)
        )
        rows.append(
            {
                "file": rel,
                "title_refs": sum(tags.values()),
                "distinct_tags": len(tags),
                "as_title_scope": scoped,
                "county_or_barony_refs": unrescuable,
                "example_tags": " ".join(tag for tag, _ in tags.most_common(6)),
            }
        )
    rows.sort(key=lambda r: -int(r["title_refs"]))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    total = sum(int(r["title_refs"]) for r in rows)
    hard = sum(int(r["county_or_barony_refs"]) for r in rows)
    print(
        f"{len(rows)} vanilla event files name a vanilla title, "
        f"{total} references, {hard} of them county or barony tier -> {args.out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
