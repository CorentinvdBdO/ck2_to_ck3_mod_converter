#!/usr/bin/env python
"""Bisection helper: neutralise every ``Custom('X')`` call in a generated mod.

The `loc` step converts a CK2 text code it cannot map to a CK3 built-in into
``[ROOT.Char.Custom('GetFoo')]``, because that is what the code *is* in CK2 — a
customizable localisation. Nothing ports `localisation/customizable_localisation`
yet, so all 795 of those names are dangling, and CK3 answers with
``jomini_custom_text.h:94: Object of type 'character' is not valid for 'GetFoo'``.

This script rewrites the generated `localization/` in place so each such call
becomes the plain custom-loc name in angle brackets — no data function, nothing
for CK3 to resolve — so a launch can say whether those calls are what kills the
game. It is a **bisection tool**, not part of the conversion: run it on the
generated mod, launch, then regenerate to undo.

    uv run scripts/bisect_strip_custom_loc.py <mod dir> [--restore]

`--restore` puts back the `.bisect-backup` copies it made.
"""

from __future__ import annotations

import argparse
import re
import shutil
from pathlib import Path

#: `[Some.Chain.Custom('Name')]`, including a trailing format suffix
#: (`|E`, `|U`), which the loc step may append.
CALL = re.compile(r"\[[^\[\]]*Custom\('([^']+)'\)[^\[\]]*\]")

BACKUP_SUFFIX = ".bisect-backup"


def strip(path: Path) -> int:
    text = path.read_text(encoding="utf-8-sig")
    new, n = CALL.subn(lambda m: f"<{m.group(1)}>", text)
    if n:
        backup = path.with_suffix(path.suffix + BACKUP_SUFFIX)
        if not backup.exists():
            shutil.copy2(path, backup)
        path.write_text("﻿" + new, encoding="utf-8", newline="")
    return n


def restore(root: Path) -> int:
    n = 0
    for backup in sorted(root.rglob("*" + BACKUP_SUFFIX)):
        target = backup.with_name(backup.name[: -len(BACKUP_SUFFIX)])
        shutil.move(str(backup), str(target))
        n += 1
    return n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("mod", type=Path)
    ap.add_argument("--restore", action="store_true")
    args = ap.parse_args()
    loc = args.mod / "localization"
    if not loc.is_dir():
        print(f"no localization/ under {args.mod}")
        return 1
    if args.restore:
        print(f"restored {restore(loc)} files")
        return 0
    files = calls = 0
    for path in sorted(loc.rglob("*.yml")):
        n = strip(path)
        if n:
            files += 1
            calls += n
    print(f"neutralised {calls} Custom() calls in {files} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
