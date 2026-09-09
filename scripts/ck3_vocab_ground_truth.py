#!/usr/bin/env python3
"""The CK3 1.19 "ground truth" vocabulary: every script key actually used.

Reusable module + CLI. Scans `key =` / `key = {` left-hand sides across
`game/common/**/*.txt` and `game/events/**/*.txt` — the same
usage-based approach `scripts/verify_ck3_keys.py` already uses for modifier
keys (`assigned_keys`), extended to `events/` because trigger/effect calls
are as dense there as in `common/`. This is deliberately broad: it proves "a
real CK3 1.19 script file uses this exact spelling as a key", not "this is a
hardcoded engine trigger/effect name" (a scripted_trigger/scripted_effect's
own declaration also counts) — the same bar `verify_ck3_keys.py` accepts,
because there is no other ground truth available offline (`effects.log` /
`triggers.log` / `event_targets.log` do not exist anywhere on this machine,
`verified` 2026-09-09 - they are written by the running game's console
`logeffects` et al, which this lane must not launch).

CLI usage: `uv run scripts/ck3_vocab_ground_truth.py` writes
`docs/evidence/ck3_vocab_ground_truth.txt` (one key per line, sorted) and
prints the count.
"""

from __future__ import annotations

import re
import sys
from functools import lru_cache
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
GAME_DEFAULT = Path(
    "/home/cvdbdo/.local/share/Steam/steamapps/common/Crusader Kings III/game"
)
OUT = REPO / "docs" / "evidence" / "ck3_vocab_ground_truth.txt"

_KEY = re.compile(r"(?m)^[ \t]*([A-Za-z_][A-Za-z_0-9]*)[ \t]*[=<>]")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig", errors="replace")


@lru_cache(maxsize=1)
def ground_truth(game: Path = GAME_DEFAULT) -> frozenset[str]:
    """Every key used under `common/` and `events/`. Cached per process."""
    keys: set[str] = set()
    for sub in ("common", "events"):
        base = game / sub
        if not base.is_dir():
            continue
        for f in base.rglob("*.txt"):
            try:
                keys |= {m.group(1) for m in _KEY.finditer(_read(f))}
            except OSError:
                continue
    return frozenset(keys)


def main() -> None:
    game = GAME_DEFAULT
    keys = ground_truth(game)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(sorted(keys)) + "\n", encoding="utf-8")
    print(f"{len(keys)} distinct keys under {game}/common + {game}/events")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
