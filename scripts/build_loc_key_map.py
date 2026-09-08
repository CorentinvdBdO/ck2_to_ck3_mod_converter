#!/usr/bin/env python
"""Concatenate the per-lane loc rename tables into `overrides/loc_keys.csv`.

Every lane that renames a localisation key hands the `loc` lane a table in
`mappings/loc_key_renames_<lane>.csv`. The converter reads exactly one table,
`[loc] key_map` in the config, so this script merges them and stamps the mode
each lane actually meant:

| source table | mode | why |
|---|---|---|
| `loc_key_renames_traits.csv` | `rename` | CK3 reads a trait's text from `trait_<id>` only; the bare CK2 id is never a loc key, so keeping it would emit 1100 dead strings. |
| `loc_key_renames_titles.csv` | `copy` | CK3 needs **both** `k_neverwinter` (name) and `k_neverwinter_adj` (adjective), and CK2 wrote zero `_adj` keys. A rename would leave every title nameless. |
| `loc_key_renames_cultures_religions.csv` | `copy` | Same shape: `ADEPT` stays, `ADEPT_plural` is derived from its text. |

`mappings/loc_key_renames_characters.csv` is **not** merged: despite the name
it is not a `ck2_key,ck3_key` table but a `ck3_loc_key,ck2_source,ck2_value`
record of the literal dynasty names, and the `dynasties` step already writes
those strings itself into `localization/english/fae_dynasties_l_english.yml`
(`docs/DECISIONS.md` 2026-09-07). Feeding it in would map `dynn_fae_1` onto the
prose in column 2.

    uv run scripts/build_loc_key_map.py [--check]

`--check` writes nothing and exits 1 when the committed file is out of date,
which is what `ci/checks.sh` calls.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: `mappings/loc_key_renames_<lane>.csv` stem suffix -> mode, in merge order.
#: A lane not listed here is refused rather than guessed at, so a new hand-off
#: table cannot silently pick the wrong mode.
SOURCES: tuple[tuple[str, str], ...] = (
    ("traits", "rename"),
    ("titles", "copy"),
    ("cultures_religions", "copy"),
)
#: Tables that deliberately do not belong in the key map, with the reason.
EXCLUDED: dict[str, str] = {
    "characters": (
        "not a ck2_key,ck3_key table; the dynasties step writes those strings"
    ),
}

HEADER = ("ck2_key", "ck3_key", "mode", "source")
OUT_REL = Path("overrides") / "loc_keys.csv"


def read_pairs(path: Path) -> list[tuple[str, str]]:
    """`ck2_key,ck3_key` rows, skipping the header and `#` comment lines."""
    pairs: list[tuple[str, str]] = []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.reader(handle):
            if len(row) < 2 or row[0].lstrip().startswith("#"):
                continue
            source, target = row[0].strip(), row[1].strip()
            if not source or not target or source.lower() == "ck2_key":
                continue
            pairs.append((source, target))
    return pairs


def discover(root: Path) -> list[tuple[str, str, Path]]:
    """`(lane, mode, path)` for every table that must be merged.

    Raises when `mappings/` grows a `loc_key_renames_*.csv` that is neither in
    :data:`SOURCES` nor in :data:`EXCLUDED`.
    """
    found = {
        p.stem[len("loc_key_renames_") :]: p
        for p in sorted((root / "mappings").glob("loc_key_renames_*.csv"))
    }
    unknown = sorted(set(found) - {lane for lane, _ in SOURCES} - set(EXCLUDED))
    if unknown:
        raise SystemExit(
            f"scripts/build_loc_key_map.py: unclassified rename table(s) "
            f"{', '.join(unknown)}; add them to SOURCES (with rename|copy) or "
            f"to EXCLUDED with a reason"
        )
    out: list[tuple[str, str, Path]] = []
    for lane, mode in SOURCES:
        if lane in found:
            out.append((lane, mode, found[lane]))
    return out


def build(root: Path) -> tuple[list[tuple[str, str, str, str]], dict[str, int]]:
    """The merged rows plus a per-lane row count.

    A `(ck2_key, ck3_key)` pair seen twice is kept once. Two lanes claiming the
    *same* pair with different modes is an error: `copy` and `rename` disagree
    about whether the CK2 key survives, and silently picking one would lose
    strings in the game with no diagnostic.
    """
    rows: list[tuple[str, str, str, str]] = []
    seen: dict[tuple[str, str], tuple[str, str]] = {}
    counts: dict[str, int] = {}
    for lane, mode, path in discover(root):
        added = 0
        for source, target in read_pairs(path):
            if source == target:
                continue
            key = (source, target)
            if key in seen:
                prev_mode, prev_lane = seen[key]
                if prev_mode != mode:
                    raise SystemExit(
                        f"{source} -> {target}: {prev_lane} wants {prev_mode}, "
                        f"{lane} wants {mode}; resolve in the lane tables"
                    )
                continue
            seen[key] = (mode, lane)
            rows.append((source, target, mode, lane))
            added += 1
        counts[lane] = added
    return rows, counts


def render(rows: list[tuple[str, str, str, str]], counts: dict[str, int]) -> str:
    import io

    buf = io.StringIO()
    buf.write(
        "# GENERATED by scripts/build_loc_key_map.py - do not hand-edit.\n"
        "# Read by the `loc` step as [loc] key_map. `mode`: `rename` drops the\n"
        "# CK2 key, `copy` emits the text under both keys.\n"
    )
    for lane, n in counts.items():
        buf.write(f"#   {lane}: {n} rows\n")
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(HEADER)
    writer.writerows(rows)
    return buf.getvalue()


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=str(ROOT))
    ap.add_argument(
        "--check", action="store_true", help="exit 1 if the file is out of date"
    )
    args = ap.parse_args(argv[1:])
    root = Path(args.root).resolve()
    rows, counts = build(root)
    text = render(rows, counts)
    out = root / OUT_REL
    if args.check:
        current = out.read_text(encoding="utf-8") if out.is_file() else ""
        if current != text:
            print(f"{OUT_REL} is out of date; run scripts/build_loc_key_map.py")
            return 1
        print(f"{OUT_REL} up to date ({len(rows)} rows)")
        return 0
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    detail = ", ".join(f"{lane} {n}" for lane, n in counts.items())
    print(f"{OUT_REL}: {len(rows)} rows ({detail})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
