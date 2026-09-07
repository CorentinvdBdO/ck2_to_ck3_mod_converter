#!/usr/bin/env python3
"""Survey the CK2 localisation CSVs of a mod and report every quirk found.

Writes ``docs/evidence/loc_quirks.md``: one section per quirk with the first
few ``file:line`` citations, so ``docs/formats_loc.md`` can cite real evidence
instead of a guess. Usage::

    uv run scripts/survey_faerun_loc.py [mod_dir] [-o docs/evidence/loc_quirks.md]
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ck2ck3.csvloc import CK2_COLUMNS  # noqa: E402

HEADER_RE = re.compile(r"^#+CODE;", re.IGNORECASE)
CODE_RE = re.compile(r"\[[^\[\]\n;]{1,120}\]")
VAR_RE = re.compile(r"\$[^$;\n]{1,60}\$")
COLOUR_RE = re.compile("§(.)")
ICON_RE = re.compile("£[^£;\n]{0,20}£?")
EXAMPLES = 4


def check(name: str, hits: dict[str, list[str]], text: str) -> None:
    hits.setdefault(name, [])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mod", nargs="?", default="Faerun/Faerun")
    parser.add_argument("-o", "--out", default="docs/evidence/loc_quirks.md")
    args = parser.parse_args()

    root = Path(args.mod)
    files = sorted((root / "localisation").glob("*.csv"))
    if not files:
        print(f"no csv under {root / 'localisation'}", file=sys.stderr)
        return 1

    hits: dict[str, list[str]] = defaultdict(list)
    counts: Counter[str] = Counter()
    headers: Counter[str] = Counter()
    encodings: Counter[str] = Counter()
    colours: Counter[str] = Counter()
    field_counts: Counter[int] = Counter()
    keys_per_file: dict[str, set[str]] = {}
    no_header: list[str] = []
    lang_share: dict[str, list[int]] = {v: [0, 0] for v in CK2_COLUMNS.values()}
    total_lines = 0

    def note(quirk: str, path: Path, line: int, sample: str) -> None:
        counts[quirk] += 1
        if len(hits[quirk]) < EXAMPLES:
            sample = sample.replace("\t", " ")[:110]
            hits[quirk].append(f"`{path.as_posix()}:{line}` — `{sample}`")

    for path in files:
        raw = path.read_bytes()
        if raw.startswith(b"\xef\xbb\xbf"):
            encodings["utf-8 BOM"] += 1
            note("BOM on a CK2 csv", path, 1, raw[:24].decode("utf-8", "replace"))
        try:
            raw.decode("ascii")
            encodings["ascii"] += 1
        except UnicodeDecodeError:
            try:
                raw.decode("utf-8")
                encodings["utf-8"] += 1
                note("valid UTF-8 (not cp1252)", path, 1, "whole file")
            except UnicodeDecodeError:
                encodings["cp1252"] += 1
        text = raw.decode("cp1252")
        if "\r\n" in text:
            counts["CRLF file"] += 1
        elif "\r" in text:
            note("lone CR line ending", path, 1, "whole file")
        columns = dict(CK2_COLUMNS)
        header_fields = 0
        seen_keys: set[str] = set()
        for number, line in enumerate(text.split("\n"), start=1):
            line = line.rstrip("\r")
            if not line.strip():
                counts["blank line"] += 1
                continue
            total_lines += 1
            if line.startswith("#"):
                if HEADER_RE.match(line):
                    headers[line.strip()] += 1
                    header_fields = len(line.split(";"))
                    labels = {
                        i: f.strip().lower()
                        for i, f in enumerate(line.split(";"))
                        if i and f.strip() and f.strip().lower() != "x"
                    }
                    if labels:
                        columns = labels
                else:
                    note("comment line (# at line start)", path, number, line)
                continue
            fields = line.split(";")
            field_counts[len(fields)] += 1
            key = fields[0].strip()
            if key in seen_keys:
                note("key defined twice in the same file", path, number, line)
            seen_keys.add(key)
            if header_fields and len(fields) > header_fields:
                note("row with more fields than the header", path, number, line)
            last_language = max(columns, default=1)
            if any(
                f.strip() and f.strip() not in {"x", "X"}
                for f in fields[last_language + 1 :]
            ):
                note("semicolon inside the text (columns shift)", path, number, line)
            if not key:
                note("row with an empty key", path, number, line)
            if key != fields[0]:
                note("key padded with spaces", path, number, line)
            if len(fields) <= max(columns, default=1):
                note("row shorter than the header", path, number, line)
            if fields[-1].strip() not in {"x", "X", ""}:
                note("last column is not the x marker", path, number, line)
            if key.startswith("﻿"):
                note("BOM glued to the first key", path, number, line)
            for index, language in columns.items():
                if language not in lang_share:
                    continue
                lang_share[language][1] += 1
                if index < len(fields) and fields[index].strip():
                    lang_share[language][0] += 1
            english = fields[1] if len(fields) > 1 else ""
            if '"' in english:
                note("double quote inside the text", path, number, line)
            if "\\n" in english:
                note("literal \\n line break", path, number, line)
            if "\\" in english.replace("\\n", ""):
                note("backslash other than \\n", path, number, line)
            for match in COLOUR_RE.finditer(line):
                colours["§" + match.group(1)] += 1
                if not match.group(1).isalpha() and match.group(1) != "!":
                    note("malformed colour code (§ + punctuation)", path, number, line)
            for match in ICON_RE.finditer(line):
                note("£ icon code", path, number, match.group(0))
            for match in VAR_RE.finditer(line):
                if "|" in match.group(0):
                    note("$VAR|fmt$ with a format suffix", path, number, match.group(0))
            for match in CODE_RE.finditer(line):
                inner = match.group(0)[1:-1]
                if "(" in inner:
                    note("[code] with arguments", path, number, match.group(0))
                if " " in inner:
                    note("[code] containing a space", path, number, match.group(0))
            if line.count("[") != line.count("]"):
                note("unbalanced square brackets", path, number, line)
        keys_per_file[path.name] = seen_keys
        if not header_fields:
            no_header.append(path.name)
            note("no #CODE header line (column order assumed)", path, 1, "whole file")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# CK2 localisation CSV quirks — survey output",
        "",
        f"Generated by `scripts/survey_faerun_loc.py` over `{root.as_posix()}/localisation`.",
        f"{len(files)} csv, {total_lines} non-blank lines.",
        "",
        "## Headers seen",
        "",
        "| count | header |",
        "|---|---|",
    ]
    lines += [f"| {n} | `{h}` |" for h, n in headers.most_common()]
    lines += ["", "## Field counts per row", "", "| fields | rows |", "|---|---|"]
    lines += [f"| {k} | {v} |" for k, v in sorted(field_counts.items())]
    lines += ["", "## File encodings", "", "| encoding | files |", "|---|---|"]
    lines += [f"| {k} | {v} |" for k, v in encodings.most_common()]
    lines += ["", "## Language column fill rate", "", "| language | filled | rows | share |", "|---|---|---|---|"]
    for language, (filled, rows) in lang_share.items():
        share = filled / rows if rows else 0.0
        lines.append(f"| {language} | {filled} | {rows} | {share:.1%} |")
    lines += ["", "## Colour codes", "", "| code | occurrences |", "|---|---|"]
    lines += [f"| `{k}` | {v} |" for k, v in colours.most_common()]
    cross: Counter[str] = Counter()
    for name, keys in keys_per_file.items():
        for key in keys:
            cross[key] += 1
    shared = sum(1 for n in cross.values() if n > 1)
    lines += [
        "",
        "## Keys",
        "",
        f"- distinct keys: {len(cross)}",
        f"- keys defined in more than one file: {shared}",
        f"- files without a `#CODE` header: {len(no_header)}",
        "",
        "## Quirks",
        "",
    ]
    for quirk, examples in sorted(hits.items(), key=lambda kv: -counts[kv[0]]):
        lines.append(f"### {quirk} — {counts[quirk]}")
        lines.append("")
        lines += [f"- {e}" for e in examples] or ["- (none)"]
        lines.append("")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{out}: {len(files)} files, {total_lines} lines, {len(hits)} quirk kinds")
    for quirk in sorted(hits, key=lambda q: -counts[q]):
        print(f"  {counts[quirk]:7d}  {quirk}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
