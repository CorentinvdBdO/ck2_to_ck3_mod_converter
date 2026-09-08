#!/usr/bin/env python
"""Check every tradition id the `cultures` step can emit against CK3 1.19.

Sources checked:

* `overrides/traditions_of_culture_group.csv` — the human-input placeholder
  table (`scripts/seed_culture_traditions.py`).
* `ck2ck3.steps.cultures.TRADITION_OF_FLAG` — the two CK2-flag traditions.

Target: every `<id> = { ... }` at the top level of
`<ck3_game>/common/culture/traditions/*.txt`, minus the `_traditions.info`
documentation file. A miss is a CK3 `error(missing-item)` and an empty slot in
the culture screen, so this exits **1** on any miss and on any row that would
exceed `DEFAULT_MAX_TRADITIONS`.

    uv run scripts/verify_culture_traditions.py [--config configs/faerun.toml]
        [--out docs/evidence/culture_traditions_check.txt]
"""

from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
warnings.simplefilter("ignore")

from ck2ck3 import overrides  # noqa: E402
from ck2ck3.config import Config  # noqa: E402
from ck2ck3.pdx import Node, parse_file  # noqa: E402
from ck2ck3.pdx.encoding import CK3_ENCODING  # noqa: E402
from ck2ck3.steps.cultures import (  # noqa: E402
    MAX_TRADITIONS,
    TRADITION_OF_FLAG,
    TRADITIONS_OVERRIDE,
    read_traditions_of_group,
)

#: Tradition files whose ids only exist when the DLC is owned. An id from one
#: of these loads for us (the game files are on disk) but not for a player
#: without the DLC, so the seed table stays inside `00_*.txt`.
BASE_GAME_PREFIX = "00_"


def game_traditions(game: Path) -> dict[str, str]:
    """{tradition id: the file that defines it}."""
    out: dict[str, str] = {}
    folder = game / "common" / "culture" / "traditions"
    for path in sorted(folder.glob("*.txt")):
        if path.name.startswith("_"):
            continue
        doc = parse_file(path, encoding=CK3_ENCODING, lenient=True)
        for entry in doc.entries:
            if isinstance(entry, Node) and not entry.key.startswith("@"):
                out.setdefault(entry.key, path.name)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="configs/faerun.toml")
    ap.add_argument("--out", default="docs/evidence/culture_traditions_check.txt")
    args = ap.parse_args()
    cfg = Config.load(Path(args.config))
    lines: list[str] = []

    def say(text: str = "") -> None:
        lines.append(text)
        print(text)

    game = cfg.ck3_game
    if not game.is_dir():
        print(f"CK3 game files not found at {game}", file=sys.stderr)
        return 2
    known = game_traditions(game)
    say(f"CK3 install: {game}")
    say(f"{len(known)} tradition ids in common/culture/traditions/*.txt")

    table = read_traditions_of_group(cfg)
    used: dict[str, list[str]] = {}
    for group_id, traditions in sorted(table.items()):
        for tradition in traditions:
            used.setdefault(tradition, []).append(group_id)
    for flag, tradition in TRADITION_OF_FLAG.items():
        used.setdefault(tradition, []).append(f"CK2 flag {flag}")

    say()
    say(f"overrides/{TRADITIONS_OVERRIDE}: {len(table)} rows, "
        f"{sum(1 for v in table.values() if not v)} deliberately empty")
    say(f"{len(used)} distinct tradition ids used")

    misses = sorted(t for t in used if t not in known)
    say()
    for tradition in sorted(used):
        where = known.get(tradition)
        mark = "OK  " if where else "MISS"
        say(f"{mark} {tradition:<40} {where or '(not in CK3 1.19)'}"
            f"  <- {len(used[tradition])} source(s)")

    dlc = sorted(
        t
        for t in used
        if t in known and not known[t].startswith(BASE_GAME_PREFIX)
    )
    oversize = sorted(g for g, v in table.items() if len(v) > MAX_TRADITIONS)

    say()
    say(f"MISSES: {len(misses)}" + (f" -> {', '.join(misses)}" if misses else ""))
    say(f"DLC-ONLY: {len(dlc)}" + (f" -> {', '.join(dlc)}" if dlc else ""))
    say(f"ROWS OVER MAX_TRADITIONS={MAX_TRADITIONS}: {len(oversize)}"
        + (f" -> {', '.join(oversize)}" if oversize else ""))

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {out}")
    return 1 if (misses or dlc or oversize) else 0


if __name__ == "__main__":
    raise SystemExit(main())
