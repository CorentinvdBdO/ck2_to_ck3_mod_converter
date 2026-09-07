#!/usr/bin/env python3
"""Validate a generated CK3 ``localization`` tree.

Checks what CK3 1.19 actually requires of a ``.yml`` (see
``docs/formats_loc.md`` §CK3 side) and reports counts, so the integration test
and a human can use the same rules::

    uv run scripts/check_ck3_loc.py <mod_dir_or_localization_dir>

Exit code 0 when there is no malformed line, 1 otherwise.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

BOM = "﻿"
#: ``' key:0 "text"'`` — one leading space, a version number, a quoted value.
#: CK3 accepts any integer version and ignores it for mod files.
LINE_PREFIX = " "


def check_file(path: Path) -> tuple[list[str], int, str]:
    """Return ``(problems, key_count, language)`` for one ``.yml``."""
    problems: list[str] = []
    raw = path.read_bytes()
    if not raw.startswith(BOM.encode("utf-8")):
        problems.append(f"{path}: no UTF-8 BOM (CK3 will not load the file)")
    text = raw.decode("utf-8-sig")
    if "\n" in text and "\r\n" not in text:
        problems.append(f"{path}: LF line endings, vanilla uses CRLF")
    lines = text.replace("\r\n", "\n").split("\n")
    language = ""
    keys = 0
    seen: set[str] = set()
    for number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        if number == 1 or not language:
            if line.startswith("l_") and line.rstrip().endswith(":"):
                language = line.strip()[2:-1]
                continue
        if line.lstrip().startswith("#"):
            continue
        if not line.startswith(LINE_PREFIX):
            problems.append(f"{path}:{number}: entry does not start with a space")
            continue
        body = line[1:]
        head, sep, value = body.partition(":")
        if not sep:
            problems.append(f"{path}:{number}: no ':' after the key")
            continue
        key = head.strip()
        if not key or any(c.isspace() for c in key):
            problems.append(f"{path}:{number}: bad key {key!r}")
        if key in seen:
            problems.append(f"{path}:{number}: key {key!r} repeated in this file")
        seen.add(key)
        value = value.strip()
        version, _, rest = value.partition(" ")
        if not version.isdigit():
            problems.append(f"{path}:{number}: missing version number after the key")
            continue
        rest = rest.strip()
        if not (rest.startswith('"') and rest.endswith('"') and len(rest) >= 2):
            problems.append(f"{path}:{number}: value is not a quoted string")
            continue
        inner = rest[1:-1]
        # An unescaped quote inside the value ends the string early in CK3.
        index = 0
        while index < len(inner):
            if inner[index] == "\\":
                index += 2
                continue
            if inner[index] == '"':
                problems.append(f"{path}:{number}: unescaped quote in the value")
                break
            index += 1
        if "§" in inner or "£" in inner:
            problems.append(f"{path}:{number}: leftover CK2 markup")
        if "[" in inner and "]" not in inner:
            problems.append(f"{path}:{number}: unbalanced '[' in the value")
        keys += 1
    if not language:
        problems.append(f"{path}: no 'l_<language>:' header")
    return problems, keys, language


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path")
    parser.add_argument("--limit", type=int, default=20, help="problems to print")
    args = parser.parse_args()

    root = Path(args.path)
    if (root / "localization").is_dir():
        root = root / "localization"
    files = sorted(root.rglob("*.yml"))
    if not files:
        print(f"no .yml under {root}", file=sys.stderr)
        return 1

    problems: list[str] = []
    per_language: Counter[str] = Counter()
    files_per_language: Counter[str] = Counter()
    for path in files:
        found, keys, language = check_file(path)
        problems.extend(found)
        per_language[language or "?"] += keys
        files_per_language[language or "?"] += 1

    print(f"{len(files)} files under {root}")
    for language in sorted(per_language):
        print(
            f"  {language:10} {files_per_language[language]:4d} files "
            f"{per_language[language]:7d} keys"
        )
    print(f"malformed lines: {len(problems)}")
    for problem in problems[: args.limit]:
        print(f"  {problem}")
    if len(problems) > args.limit:
        print(f"  ...and {len(problems) - args.limit} more")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
