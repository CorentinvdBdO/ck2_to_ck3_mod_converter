#!/usr/bin/env python3
"""Collect every ``[...]`` text code of a CK2 mod's localisation.

Writes ``docs/evidence/ck2_loc_codes.csv`` — one row per distinct code with its
frequency, the scope chain, the terminal function, whether
``ck2ck3.loc_codes`` converts it, and a ``file:line`` citation. The mapping
table in ``src/ck2ck3/loc_codes.py`` is built from this file, and the
``mapped``/``unmapped`` split is the coverage number quoted in
``docs/loc_codes.md``. Usage::

    uv run scripts/collect_ck2_loc_codes.py [mod_dir] [--language english]
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ck2ck3 import loc_codes  # noqa: E402
from ck2ck3.csvloc import CK2_COLUMNS, read_ck2_csv  # noqa: E402

CODE_RE = re.compile(r"\[[^\[\]\n;]{1,120}\]")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mod", nargs="?", default="Faerun/Faerun")
    parser.add_argument(
        "--language",
        default="all",
        help="one language column, or 'all' (default) for every column",
    )
    parser.add_argument("-o", "--out", default="docs/evidence/ck2_loc_codes.csv")
    parser.add_argument(
        "--unknown",
        default="custom",
        choices=loc_codes.UNKNOWN_POLICIES,
        help="what to do with an unknown Get* function (see loc_codes)",
    )
    args = parser.parse_args()

    languages = (
        list(CK2_COLUMNS.values()) if args.language == "all" else [args.language]
    )
    files = sorted((Path(args.mod) / "localisation").glob("*.csv"))
    if not files:
        print(f"no csv under {args.mod}/localisation", file=sys.stderr)
        return 1

    custom_loc = loc_codes.custom_loc_names(args.mod)
    freq: Counter[str] = Counter()
    where: dict[str, str] = {}
    for path in files:
        loc = read_ck2_csv(path)
        for entry in loc:
            for language in languages:
                for match in CODE_RE.finditer(entry.values.get(language, "")):
                    code = match.group(0)
                    freq[code] += 1
                    where.setdefault(code, f"{path.as_posix()}:{entry.line}")

    total = sum(freq.values())
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    print(f"custom localisation names defined: {len(custom_loc)}")
    mapped_occ = 0
    with open(out, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            ["ck2_code", "occurrences", "scope_chain", "function", "status", "ck3_code", "evidence"]
        )
        for code, count in freq.most_common():
            result = loc_codes.convert_code(code, custom_loc=custom_loc, unknown=args.unknown)
            if result.converted:
                mapped_occ += count
            writer.writerow(
                [
                    code,
                    count,
                    result.scope_chain,
                    result.function,
                    result.status,
                    result.text,
                    where[code],
                ]
            )
    share = mapped_occ / total if total else 0.0
    print(f"{out}: {len(freq)} distinct codes, {total} occurrences")
    print(f"mapped: {mapped_occ} ({share:.1%}), unmapped: {total - mapped_occ}")
    by_status: Counter[str] = Counter()
    for code, count in freq.items():
        by_status[loc_codes.convert_code(code, custom_loc=custom_loc, unknown=args.unknown).status] += count
    for status, count in by_status.most_common():
        print(f"  {count:7d} ({count / total:6.1%})  {status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
