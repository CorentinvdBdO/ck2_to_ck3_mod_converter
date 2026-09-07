#!/usr/bin/env python3
"""Cache the set of localisation keys CK3 vanilla already defines.

``[loc] skip_vanilla_collisions`` needs to know which CK2 keys would shadow a
vanilla CK3 string. Scanning ``game/localization`` costs a 273 MB read, so it
is done once here and the result is committed as
``docs/evidence/ck3_vanilla_loc_keys.txt`` (one key per line, sorted, with a
provenance header). Long enough to want a log::

    nohup uv run scripts/build_ck3_vanilla_loc_keys.py \
        > docs/evidence/ck3_vanilla_loc_keys.log 2>&1 &

Only the key half of each line is read (``^ key:<version>``), never the text,
so the output holds no CK3 content.
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ck2ck3.config import REPO_ROOT  # noqa: E402

DEFAULT_GAME = Path(
    "/home/cvdbdo/.local/share/Steam/steamapps/common/Crusader Kings III/game"
)
#: ``' key:0 "text"'`` — the shape every vanilla line has.
KEY_RE = re.compile(r"^[ \t]+([A-Za-z0-9_.\-]+):\d")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("game", nargs="?", default=str(DEFAULT_GAME))
    parser.add_argument(
        "-o", "--out", default="docs/evidence/ck3_vanilla_loc_keys.txt"
    )
    parser.add_argument(
        "--language",
        default="english",
        help="which localization subfolder to scan (keys are language-independent)",
    )
    args = parser.parse_args()

    root = Path(args.game) / "localization" / args.language
    if not root.is_dir():
        print(f"not a folder: {root}", file=sys.stderr)
        return 1

    started = time.time()
    keys: set[str] = set()
    files = 0
    for path in sorted(root.rglob("*.yml")):
        files += 1
        with open(path, encoding="utf-8-sig", errors="replace") as handle:
            for line in handle:
                match = KEY_RE.match(line)
                if match:
                    keys.add(match.group(1))
        if files % 200 == 0:
            print(f"{files} files, {len(keys)} keys, {time.time() - started:.0f}s")

    out = Path(args.out)
    if not out.is_absolute():
        out = REPO_ROOT / out
    out.parent.mkdir(parents=True, exist_ok=True)
    header = [
        "# CK3 vanilla localisation keys, one per line, sorted.",
        f"# Built by scripts/build_ck3_vanilla_loc_keys.py from {root}",
        f"# {files} files, {len(keys)} keys.",
    ]
    out.write_text("\n".join(header + sorted(keys)) + "\n", encoding="utf-8")
    print(
        f"{out}: {len(keys)} keys from {files} files in {time.time() - started:.0f}s"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
