"""Binary-search the character block that makes ck3-tiger panic.

ck3-tiger 1.19.0 aborts with ``index out of bounds`` in ``src/trigger.rs:1454``
on the generated ``history/characters``, but only when the mod also ships a
``localization/`` folder; either subtree alone validates fine. This halves the
file until one block is left, so the report can name the construct instead of
guessing.

Each probe is a full tiger run (~10 s), so the search is ~log2(blocks) runs.

Usage: uv run python scripts/bisect_tiger_panic.py <converted file> [scratch dir]
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys

GAME = os.environ.get(
    "CK3_GAME",
    os.path.expanduser("~/.local/share/Steam/steamapps/common/Crusader Kings III"),
)


def split_blocks(text: str) -> list[str]:
    """Top-level ``id = { ... }`` blocks, brace-counted, comments attached."""
    blocks: list[str] = []
    current: list[str] = []
    depth = 0
    for line in text.splitlines(True):
        current.append(line)
        depth += line.count("{") - line.count("}")
        if depth == 0 and line.strip().startswith("}"):
            blocks.append("".join(current))
            current = []
    if current:
        blocks.append("".join(current))
    return blocks


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    source = pathlib.Path(sys.argv[1])
    scratch = pathlib.Path(sys.argv[2] if len(sys.argv) > 2 else "/tmp/tiger-bisect")
    mod = scratch / "mod"
    (mod / "history" / "characters").mkdir(parents=True, exist_ok=True)
    (mod / "localization" / "english").mkdir(parents=True, exist_ok=True)
    (mod / "localization" / "english" / "t_l_english.yml").write_text(
        '﻿l_english:\n my_key:0 "x"\n', encoding="utf-8"
    )
    modfile = scratch / "mod.mod"
    modfile.write_text(
        'version="0.1"\ntags={\n\t"T"\n}\nname="bisect"\n'
        f'supported_version="1.19.*"\npath="{mod}"\n',
        encoding="utf-8",
    )
    target = mod / "history" / "characters" / "x.txt"
    probes = 0

    def panics(blocks: list[str]) -> bool:
        nonlocal probes
        probes += 1
        target.write_text("".join(blocks), encoding="utf-8")
        result = subprocess.run(
            ["ck3-tiger", "--game", GAME, str(modfile)],
            capture_output=True,
            text=True,
        )
        return "panicked" in result.stdout + result.stderr

    blocks = split_blocks(source.read_text(encoding="utf-8"))
    print(f"{len(blocks)} blocks in {source.name}", flush=True)
    if not panics(blocks):
        print("no panic on the whole file; nothing to bisect")
        return 0

    while len(blocks) > 1:
        half = len(blocks) // 2
        if panics(blocks[:half]):
            blocks = blocks[:half]
        elif panics(blocks[half:]):
            blocks = blocks[half:]
        else:
            print(f"panic needs more than one of these {len(blocks)} blocks")
            break
        print(f"  narrowed to {len(blocks)} (probe {probes})", flush=True)

    print(f"--- minimal panicking input ({probes} tiger runs) ---")
    print("".join(blocks))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
