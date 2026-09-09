#!/usr/bin/env python3
"""Sum every ``count=`` in vanilla's own gfx/map/map_object_data/generated/*.txt.

Verifies the 549,126-instance / 9216x4608-canvas figure ``docs/map_fidelity.md``
§4.3 and this lane's ``ck2ck3.map.tree_scatter`` module quote as vanilla's own
tree/foliage density. Usage::

    uv run scripts/verify_tree_density.py [ck3_game_dir]
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

DEFAULT_GAME = Path(
    "/home/cvdbdo/.local/share/Steam/steamapps/common/Crusader Kings III/game"
)
GENERATED_DIR = "gfx/map/map_object_data/generated"
_COUNT_RE = re.compile(r"count=(\d+)")


def main(argv: list[str]) -> int:
    game_dir = Path(argv[1]) if len(argv) > 1 else DEFAULT_GAME
    src_dir = game_dir / GENERATED_DIR
    if not src_dir.is_dir():
        print(f"no such directory: {src_dir}", file=sys.stderr)
        return 1

    total = 0
    per_file: dict[str, int] = {}
    for p in sorted(src_dir.glob("*.txt")):
        text = p.read_text(encoding="utf-8-sig", errors="replace")
        n = sum(int(m) for m in _COUNT_RE.findall(text))
        per_file[p.name] = n
        total += n

    for name, n in sorted(per_file.items(), key=lambda kv: -kv[1]):
        print(f"{n:>10,}  {name}")
    print(f"{total:>10,}  TOTAL across {len(per_file)} files")

    width, height = 9216, 4608
    density = total / (width * height)
    print(f"density: {density:.6e} instances/px over {width}x{height}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
