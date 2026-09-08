#!/usr/bin/env python3
"""Provenance pass: Faerûn CK2 mod vs vanilla CK2, for events/decisions/on_actions.

Lane `events-provenance`, README §5 step 1. Faerûn `replace_path`s `events` and
`decisions` wholesale (`Faerun/Faerun/Faerun.mod`), so every vanilla CK2 event
or decision id **absent** from Faerûn's own files is truly gone from the game;
`common/on_actions` is **not** `replace_path`d, so a vanilla on_action id
missing from Faerûn's on_action files still fires — see `docs/events_provenance.md`
for why the on_actions table's `deleted` status means something different there.

Keys by id (events: the value of the `id =` field, which already includes the
namespace prefix as CK2 writes it, e.g. ``ADV.1``; decisions: the block's own
key inside a `..._decisions = { }` group; on_actions: the `on_...` block key).
Classifies each id as ``new`` (Faerûn only), ``deleted`` (vanilla only),
``kept`` (same content after stripping comments/formatting) or ``modified``
(changed top-level keys listed). Duplicate ids within one source (an id
defined twice) are recorded, not merged — except on_actions, which the CK2
engine merges additively across files by design, so same-name on_action
blocks from multiple files in one source are concatenated before comparison.

Uses `ck2ck3.pdx` (the tokenizer parser: comment round-trip, cp1252/utf-8
auto-detect) exactly as `ck2ck3.titles.ck2read` does. Writes no mod output —
CSVs only.

Usage:
    uv run scripts/events_provenance.py [--ck2-game DIR] [--ck2-mod DIR] [--out-dir DIR]

Runtime: ~5 s over 249 vanilla + 332 Faerûn event files (`verified` 2026-09-08).
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
import warnings
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from ck2ck3.pdx import Block, Node, parse_file, structurally_equal  # noqa: E402
from ck2ck3.pdx.encoding import EncodingWarning  # noqa: E402

DEFAULT_CK2_GAME = Path(
    "/home/cvdbdo/.local/share/Steam/steamapps/common/Crusader Kings II"
)

#: Every CK2 vanilla event block type (`verified` 2026-09-08: grep of both
#: trees' `events/*.txt` top-level `<x>_event = {` tags).
EVENT_TYPES = frozenset(
    {
        "character_event",
        "province_event",
        "letter_event",
        "long_character_event",
        "narrative_event",
        "diploresponse_event",
        "society_quest_event",
        "unit_event",
    }
)

#: Keys whose change is text/art only, never game logic — used to bucket a
#: `modified` event into "loc/desc only" vs "logic" for the summary doc.
#: `assumed`: CK2's `desc`/`title` are loc-key *references*, not literal text,
#: but a change confined to these plus `picture` never touches trigger/effect
#: flow.
LOC_ONLY_EVENT_KEYS = frozenset(
    {"desc", "title", "picture", "scaled_picture", "sound", "quick_desc", "border"}
)

#: Cheap keyword heuristic for "this event/decision/on_action touches a
#: Faerûn mechanic with no direct CK3 port", per `docs/mechanics_inventory.md`
#: (`assumed`: substring match against the block's own keys/scalar strings,
#: not a real dependency analysis). Matched against a lower-cased token set
#: collected by :func:`_tokens`, so `join_society` matches `society` etc.
MECHANIC_KEYWORDS: dict[str, str] = {
    "society": "societies",
    "offmap": "offmap_powers",
    "bloodline": "bloodlines",
    "wonder": "wonders",
    "trade_route": "trade_routes",
    "trade_post": "trade_routes",
    "execution_method": "execution_methods",
    "disease": "disease",
    "epidemic": "disease",
    "ordning": "governments_custom",
    "celestial": "governments_custom",
    "roman_imperial": "governments_custom",
    "nomad": "governments_custom",
    "spellbook": "sorcerer_tiers",
    "lich": "sorcerer_tiers",
    "vampire": "sorcerer_tiers",
    "job_title": "job_titles",
    "minor_title": "minor_titles",
    "ambition": "objectives",
    "objectives_plot": "objectives",
}


def default_ck2_mod() -> Path:
    """Faerûn clone: repo-local, or a sibling checkout from a worktree."""
    for cand in (
        REPO / "Faerun" / "Faerun",
        REPO.parent / "ck2_to_ck3_mod_converter" / "Faerun" / "Faerun",
        REPO.parent.parent / "ck2_to_ck3_mod_converter" / "Faerun" / "Faerun",
    ):
        if (cand / "events").is_dir():
            return cand
    return REPO / "Faerun" / "Faerun"


@dataclass
class Definition:
    """One occurrence of an id in one file."""

    key: str
    kind: str  # event type / decision group / "on_action"
    block: Block
    file: str  # posix, relative to the tree root
    line: int


@dataclass
class Row:
    """One provenance-CSV row."""

    id: str
    kind: str  # type / group / "on_action"
    faerun_files: str
    vanilla_files: str
    status: str  # new / kept / modified / deleted
    changed_keys: str
    uses_faerun_mechanic: str
    vanilla_dup_count: int = 0
    faerun_dup_count: int = 0


def parse_lenient(path: Path):
    """`parse_file` with encoding sniffing quiet and syntax oddities recorded,
    not raised — a provenance survey over 580+ files must not die on one."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", EncodingWarning)
        return parse_file(path, lenient=True)


def iter_script_files(root: Path):
    return sorted(p for p in root.rglob("*.txt") if p.is_file())


# --------------------------------------------------------------------------- #
# collection
# --------------------------------------------------------------------------- #


def collect_events(root: Path) -> dict[str, list[Definition]]:
    out: dict[str, list[Definition]] = defaultdict(list)
    events_dir = root / "events"
    if not events_dir.is_dir():
        return out
    for path in iter_script_files(events_dir):
        doc = parse_lenient(path)
        rel = path.relative_to(root).as_posix()
        for entry in doc.entries:
            if not (isinstance(entry, Node) and entry.key in EVENT_TYPES):
                continue
            if not isinstance(entry.value, Block):
                continue
            body = entry.value
            id_val = body.get("id")
            if id_val is None:
                continue
            key = str(id_val)
            out[key].append(Definition(key, entry.key, body, rel, entry.line))
    return out


def collect_decisions(root: Path) -> dict[str, list[Definition]]:
    out: dict[str, list[Definition]] = defaultdict(list)
    dec_dir = root / "decisions"
    if not dec_dir.is_dir():
        return out
    for path in iter_script_files(dec_dir):
        doc = parse_lenient(path)
        rel = path.relative_to(root).as_posix()
        for entry in doc.entries:
            # Every vanilla/Faerûn decision group is `<x>decisions = { }`
            # (`decisions`, `targetted_decisions`, `targeted_decisions` — both
            # spellings occur, `title_decisions`, `society_decisions`, …
            # `verified` 2026-09-08 grep of both trees' decisions/*.txt).
            if not (isinstance(entry, Node) and entry.key.endswith("decisions")):
                continue
            if not isinstance(entry.value, Block):
                continue
            group = entry.key
            for sub in entry.value.entries:
                if isinstance(sub, Node) and isinstance(sub.value, Block):
                    out[sub.key].append(
                        Definition(sub.key, group, sub.value, rel, sub.line)
                    )
    return out


def collect_on_actions(root: Path) -> dict[str, list[Definition]]:
    out: dict[str, list[Definition]] = defaultdict(list)
    oa_dir = root / "common" / "on_actions"
    if not oa_dir.is_dir():
        return out
    for path in iter_script_files(oa_dir):
        doc = parse_lenient(path)
        rel = path.relative_to(root).as_posix()
        for entry in doc.entries:
            if not (isinstance(entry, Node) and entry.key.startswith("on_")):
                continue
            if not isinstance(entry.value, Block):
                continue
            out[entry.key].append(
                Definition(entry.key, "on_action", entry.value, rel, entry.line)
            )
    return out


# --------------------------------------------------------------------------- #
# comparison
# --------------------------------------------------------------------------- #


def merged_block(defs: list[Definition]) -> Block:
    """Concatenate every definition's entries into one synthetic block, in
    (file, line) order. Only meaningful for on_actions, whose CK2 engine
    merges same-name blocks across files additively (`verified` 2026-09-08:
    Faerûn's own `on_quest_success` etc. are defined twice, in two files)."""
    if len(defs) == 1:
        return defs[0].block
    merged = Block()
    for d in sorted(defs, key=lambda d: (d.file, d.line)):
        merged.entries.extend(d.block.entries)
    return merged


def changed_top_level_keys(vblock: Block, fblock: Block) -> list[str]:
    """Top-level keys whose value differs (structurally, ignoring comments and
    blank-line layout) or whose entry count differs between the two blocks."""
    all_keys = sorted((set(vblock.keys()) | set(fblock.keys())) - {"id"})
    changed = []
    for k in all_keys:
        vnodes = vblock.nodes(k)
        fnodes = fblock.nodes(k)
        if len(vnodes) != len(fnodes):
            changed.append(k)
            continue
        if any(
            not structurally_equal(vn, fn, comments=False, blanks=False)
            for vn, fn in zip(vnodes, fnodes)
        ):
            changed.append(k)
    return changed


def _tokens(block: Block, limit: int = 4000) -> set[str]:
    """Lower-cased keys and scalar string values, depth-first, capped so one
    huge on_action block cannot blow up the mechanic-heuristic pass."""
    out: set[str] = set()
    stack = [block]
    n = 0
    while stack and n < limit:
        cur = stack.pop()
        for entry in cur.entries:
            n += 1
            if n >= limit:
                break
            if isinstance(entry, Node):
                out.add(entry.key.lower())
                if isinstance(entry.value, str):
                    out.add(entry.value.lower())
                elif isinstance(entry.value, Block):
                    stack.append(entry.value)
            elif isinstance(entry.value, str):
                out.add(entry.value.lower())
    return out


def mechanic_hits(block: Block) -> str:
    tokens = _tokens(block)
    hits = sorted(
        {tag for token in tokens for kw, tag in MECHANIC_KEYWORDS.items() if kw in token}
    )
    return ";".join(hits)


def classify(
    vanilla: dict[str, list[Definition]],
    faerun: dict[str, list[Definition]],
    *,
    merge_multi: bool = False,
) -> list[Row]:
    rows: list[Row] = []
    for key in sorted(set(vanilla) | set(faerun)):
        vdefs = vanilla.get(key, [])
        fdefs = faerun.get(key, [])
        vfiles = ";".join(sorted({d.file for d in vdefs}))
        ffiles = ";".join(sorted({d.file for d in fdefs}))
        if vdefs and not fdefs:
            rows.append(
                Row(key, vdefs[0].kind, "", vfiles, "deleted", "", "", len(vdefs), 0)
            )
            continue
        if fdefs and not vdefs:
            mech = mechanic_hits(merged_block(fdefs) if merge_multi else fdefs[0].block)
            rows.append(
                Row(key, fdefs[0].kind, ffiles, "", "new", "", mech, 0, len(fdefs))
            )
            continue
        # in both
        vblock = merged_block(vdefs) if merge_multi else vdefs[0].block
        fblock = merged_block(fdefs) if merge_multi else fdefs[0].block
        changed = changed_top_level_keys(vblock, fblock)
        if vdefs[0].kind != fdefs[0].kind:
            changed = ["__kind__"] + changed
        mech = mechanic_hits(fblock)
        status = "modified" if changed else "kept"
        rows.append(
            Row(
                key,
                fdefs[0].kind,
                ffiles,
                vfiles,
                status,
                ";".join(changed),
                mech,
                len(vdefs),
                len(fdefs),
            )
        )
    return rows


# --------------------------------------------------------------------------- #
# CSV / CLI
# --------------------------------------------------------------------------- #

CSV_FIELDS = [
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


def write_csv(rows: list[Row], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(CSV_FIELDS)
        for r in rows:
            w.writerow(
                [
                    r.id,
                    r.kind,
                    r.faerun_files,
                    r.vanilla_files,
                    r.status,
                    r.changed_keys,
                    r.uses_faerun_mechanic,
                    r.vanilla_dup_count,
                    r.faerun_dup_count,
                ]
            )


def run(ck2_game: Path, ck2_mod: Path) -> dict[str, list[Row]]:
    v_events = collect_events(ck2_game)
    f_events = collect_events(ck2_mod)
    v_dec = collect_decisions(ck2_game)
    f_dec = collect_decisions(ck2_mod)
    v_oa = collect_on_actions(ck2_game)
    f_oa = collect_on_actions(ck2_mod)
    return {
        "events": classify(v_events, f_events),
        "decisions": classify(v_dec, f_dec),
        "on_actions": classify(v_oa, f_oa, merge_multi=True),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ck2-game", type=Path, default=DEFAULT_CK2_GAME)
    ap.add_argument("--ck2-mod", type=Path, default=None)
    ap.add_argument("--out-dir", type=Path, default=REPO / "docs" / "evidence")
    args = ap.parse_args(argv)

    ck2_mod = args.ck2_mod or default_ck2_mod()
    if not (args.ck2_game / "events").is_dir():
        print(f"no events/ under {args.ck2_game}", file=sys.stderr)
        return 2
    if not (ck2_mod / "events").is_dir():
        print(f"no events/ under {ck2_mod}", file=sys.stderr)
        return 2

    t0 = time.time()
    results = run(args.ck2_game, ck2_mod)
    elapsed = time.time() - t0

    write_csv(results["events"], args.out_dir / "events_provenance.csv")
    write_csv(results["decisions"], args.out_dir / "decisions_provenance.csv")
    write_csv(results["on_actions"], args.out_dir / "on_actions_provenance.csv")

    for kind, rows in results.items():
        counts: dict[str, int] = defaultdict(int)
        for r in rows:
            counts[r.status] += 1
        print(f"{kind}: {len(rows)} ids " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    print(f"elapsed {elapsed:.2f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
