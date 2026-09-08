#!/usr/bin/env python
"""Validate the ``position`` values of a generated ``fae_bookmarks.txt``.

Checks, per bookmark: every character inside the measured vanilla canvas, no
``{ 0 0 }``, and no pair closer than the repulsion floor.  Exit 1 on any
violation, so it can be dropped into a CI run.

Usage: ``uv run scripts/check_bookmark_positions.py <mod dir or file>``
"""

from __future__ import annotations

import math
import re
import sys
from pathlib import Path

from ck2ck3.titles import bookmarks as bm

POS = re.compile(r"position = \{ (-?\d+) (-?\d+) \}")
KEY = re.compile(r"^([A-Za-z_0-9]+)\s*=\s*\{", re.M)


def main() -> int:
    target = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    if target.is_dir():
        hits = sorted(target.glob("common/bookmarks/bookmarks/*.txt"))
        hits = [h for h in hits if h.stat().st_size > 400]
        if not hits:
            print(f"no bookmark file under {target}")
            return 1
        target = hits[0]
    text = target.read_text(encoding="utf-8-sig")
    starts = [(m.start(), m.group(1)) for m in KEY.finditer(text)]
    starts.append((len(text), ""))

    x0, y0, x1, y1 = bm.CANVAS
    bad = 0
    total = 0
    worst: tuple[float, str] | None = None
    for (a, key), (b, _) in zip(starts, starts[1:]):
        pts = [(int(x), int(y)) for x, y in POS.findall(text[a:b])]
        if not pts:
            continue
        total += len(pts)
        floor = bm.effective_min_distance(len(pts))
        for x, y in pts:
            if (x, y) == (0, 0):
                print(f"{key}: character at the origin")
                bad += 1
            if not (x0 <= x <= x1 and y0 <= y <= y1):
                print(f"{key}: ({x} {y}) outside the canvas {bm.CANVAS}")
                bad += 1
        for i in range(len(pts)):
            for j in range(i + 1, len(pts)):
                d = math.dist(pts[i], pts[j])
                if worst is None or d < worst[0]:
                    worst = (d, key)
                if d < floor - 1.0:
                    print(f"{key}: {pts[i]} and {pts[j]} are {d:.1f} px apart "
                          f"(floor {floor:.1f})")
                    bad += 1
        print(f"{key:34s} {len(pts):2d} characters, closest pair "
              f"{min((math.dist(p, q) for i, p in enumerate(pts) for q in pts[i+1:]), default=float('inf')):.1f} px")
    print(f"\n{total} positions in {target}")
    if worst:
        print(f"closest pair overall: {worst[0]:.1f} px in {worst[1]}")
    print(f"violations: {bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
