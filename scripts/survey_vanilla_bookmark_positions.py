#!/usr/bin/env python
"""Measure the CK3 vanilla bookmark-screen canvas from ``common/bookmarks``.

Evidence for ``docs/step_titles.md`` (Bookmarks): the x/y envelope of every
vanilla ``position = { x y }``, the per-bookmark character counts, the minimum
pairwise distance inside one bookmark, and the ``animation`` id histogram.

Usage: ``uv run scripts/survey_vanilla_bookmark_positions.py [config.toml]``
"""

from __future__ import annotations

import collections
import math
import re
import sys
from pathlib import Path

from ck2ck3.config import Config

POS = re.compile(r"position\s*=\s*\{\s*(-?[\d.]+)\s+(-?[\d.]+)\s*\}")
ANIM = re.compile(r"^\s*animation\s*=\s*(\w+)", re.M)
CHAR = re.compile(r"^\tcharacter\s*=\s*\{", re.M)
BOOKMARK = re.compile(r"^(\w+)\s*=\s*\{", re.M)


def main() -> int:
    cfg = Config.load(sys.argv[1] if len(sys.argv) > 1 else "configs/faerun.toml")
    root = Path(cfg.ck3_game) / "common" / "bookmarks" / "bookmarks"
    files = sorted(root.glob("*.txt"))
    if not files:
        print(f"no bookmark files under {root}")
        return 1

    all_pos: list[tuple[float, float]] = []
    anims: collections.Counter[str] = collections.Counter()
    per_bookmark: dict[str, list[tuple[float, float]]] = {}

    for path in files:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        anims.update(ANIM.findall(text))
        # split on top-level bookmark keys (column 0 `key = {`)
        starts = [(m.start(), m.group(1)) for m in BOOKMARK.finditer(text)
                  if m.group(0)[0] not in " \t"]
        starts.append((len(text), ""))
        for (a, key), (b, _) in zip(starts, starts[1:]):
            chunk = text[a:b]
            # Only depth-1 `character = {` blocks carry a position; the nested
            # `relation` alternates do not.  `display = no` blocks are the
            # animation-test dummies, all stacked on one coordinate - they are
            # never drawn, so they must not count toward the envelope.
            pts = []
            cuts = [m.start() for m in CHAR.finditer(chunk)] + [len(chunk)]
            for c0, c1 in zip(cuts, cuts[1:]):
                block = chunk[c0:c1]
                if re.search(r"^\t\tdisplay\s*=\s*no", block, re.M):
                    continue
                found = POS.findall(block)
                if found:
                    pts.append((float(found[0][0]), float(found[0][1])))
            if pts:
                per_bookmark[f"{path.name}:{key}"] = pts
                all_pos.extend(pts)

    xs = [p[0] for p in all_pos]
    ys = [p[1] for p in all_pos]
    print(f"files            : {len(files)} under {root}")
    print(f"positions        : {len(all_pos)}")
    print(f"x range          : {min(xs)} .. {max(xs)}")
    print(f"y range          : {min(ys)} .. {max(ys)}")
    biggest = max(per_bookmark.items(), key=lambda kv: len(kv[1]))
    print(f"max chars in one : {len(biggest[1])} ({biggest[0]})")

    worst = None
    for key, pts in per_bookmark.items():
        for i in range(len(pts)):
            for j in range(i + 1, len(pts)):
                d = math.dist(pts[i], pts[j])
                if worst is None or d < worst[0]:
                    worst = (d, key, pts[i], pts[j])
    if worst:
        print(f"min pair distance: {worst[0]:.1f} in {worst[1]} {worst[2]} {worst[3]}")
    mins = sorted(
        min(math.dist(p, q) for q in pts if q is not p) for pts in per_bookmark.values()
        for p in pts if len(pts) > 1
    )
    if mins:
        print(f"nearest-neighbour: min {mins[0]:.1f} median {mins[len(mins)//2]:.1f}")
    print(f"animation ids    : {len(anims)} distinct")
    for name, n in anims.most_common(12):
        print(f"  {n:4d} {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
