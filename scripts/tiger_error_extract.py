#!/usr/bin/env python
"""Reduce a whole-mod ck3-tiger report to the part worth committing.

A ck3-tiger run over the generated Faerûn mod is **359 MB**: one indented
block per diagnostic, and 208 000 of the 224 000 diagnostics are localisation
the converter is not the owner of. That is unreviewable and unstorable, so the
raw report is gitignored (`docs/evidence/tiger_full_*.txt`) and this writes the
committed extract next to it:

* the three header lines the validator puts on top (when, which mod, which game),
* **every** `error(...)` and `fatal(...)` block, verbatim, with its source
  excerpt — those are the ones that have to be justified one by one in
  `docs/evidence/tiger_full_<date>.md`,
* the `--- by kind` / `--- by message` tail `scripts/validate_output_mod.sh`
  appends, which is the index to everything left out.

On the 2026-09-08 run that is 444 KB, 1280 lines.

    uv run scripts/tiger_error_extract.py docs/evidence/tiger_full_2026-09-08.txt

Output path: the input with `_summary` before the suffix, unless `-o` says
otherwise. Regenerate it whenever you regenerate the report; the raw file is
gitignored and the summary is not (`.gitignore` has the negation).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

#: A diagnostic starts at column 0 with `severity(kind):`. Everything indented
#: under it, up to the next one or a blank line, is its excerpt.
SEVERITIES = ("error(", "fatal(", "warning(", "tips(", "untidy(", "advice(")
KEPT = ("error(", "fatal(")
#: The line `validate_output_mod.sh` writes before its own summary.
TAIL_MARKER = "--- by kind"
PREAMBLE = (
    "# Committed extract of a ck3-tiger whole-mod report, written by\n"
    "# scripts/tiger_error_extract.py. The raw report is gitignored (359 MB on\n"
    "# Faerun: one block per diagnostic, 208k of them localisation warnings).\n"
    "# Kept here: every error/fatal block verbatim, and the by-kind /\n"
    "# by-message summary that indexes what is not here. Regenerate with\n"
    "# scripts/validate_output_mod.sh, then re-run this.\n"
)


def extract(lines: list[str]) -> tuple[list[str], dict[str, int]]:
    """The extract, plus `{kept, total_diagnostics, lines_in, lines_out}`."""
    out: list[str] = []
    for line in lines[:8]:
        out.append(line)
        if line.startswith("---"):
            break
    out += ["\n", PREAMBLE, "\n=== every error/fatal block ===\n\n"]

    kept = total = 0
    i, n = 0, len(lines)
    while i < n:
        line = lines[i]
        if not line.startswith(SEVERITIES):
            i += 1
            continue
        total += 1
        if not line.startswith(KEPT):
            i += 1
            continue
        kept += 1
        out.append(line)
        j = i + 1
        while j < n and lines[j].strip() and not lines[j].startswith(
            SEVERITIES + ("---",)
        ):
            out.append(lines[j])
            j += 1
        out.append("\n")
        i = j

    tail = next(
        (k for k, l in enumerate(lines) if l.startswith(TAIL_MARKER)), None
    )
    if tail is not None:
        out.append("\n")
        # Three lines back picks up the validator's `summary:` line.
        out += lines[max(0, tail - 3) :]
    counts = {
        "kept": kept,
        "total_diagnostics": total,
        "lines_in": n,
        "lines_out": len(out),
    }
    return out, counts


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("report", help="the raw ck3-tiger report")
    ap.add_argument("-o", "--out", help="default: <report>_summary<suffix>")
    args = ap.parse_args(argv[1:])

    src = Path(args.report)
    if not src.is_file():
        print(f"no such report: {src}", file=sys.stderr)
        return 1
    dst = (
        Path(args.out)
        if args.out
        else src.with_name(f"{src.stem}_summary{src.suffix}")
    )
    lines = src.read_text(encoding="utf-8", errors="replace").splitlines(True)
    out, counts = extract(lines)
    dst.write_text("".join(out), encoding="utf-8")
    print(
        f"{dst}: {counts['kept']} error/fatal blocks of "
        f"{counts['total_diagnostics']} diagnostics, "
        f"{counts['lines_out']} lines from {counts['lines_in']} "
        f"({src.stat().st_size // 1024} KB -> {dst.stat().st_size // 1024} KB)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
