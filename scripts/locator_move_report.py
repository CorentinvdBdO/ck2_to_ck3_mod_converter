"""Diff two builds' ``gfx/map/map_object_data`` locator sets, instance by id.

Lane ``map-assets``.  Answers the only question that matters after changing
where locators are placed: **how many instances moved, and by how much**.

Also checks the invariant that costs a build if it breaks: every id present in
the old file must still be present in the new one.  An id left out silently
inherits vanilla's European coordinate (CLAUDE.md invariant), and the engine
fills only gaps, so a shrunken file is worse than no file.

Run::

    uv run scripts/locator_move_report.py --old DIR --new DIR [--csv FILE]

``DIR`` is a directory holding the seven locator files (a mod's
``gfx/map/map_object_data``, or a copy of one).
"""

from __future__ import annotations

import argparse
import csv
import re
import statistics
from pathlib import Path

FILES = (
    "building_locators.txt",
    "special_building_locators.txt",
    "siege_locators.txt",
    "activities.txt",
    "player_stack_locators.txt",
    "other_stack_locators.txt",
    "combat_locators.txt",
)

_INSTANCE = re.compile(
    r"id=(\d+)\s+position=\{ ([-\d.eE]+) ([-\d.eE]+) ([-\d.eE]+) \}"
)


def read_instances(path: Path) -> dict[int, tuple[float, float, float]]:
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    return {
        int(m.group(1)): (float(m.group(2)), float(m.group(3)), float(m.group(4)))
        for m in _INSTANCE.finditer(text)
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--old", required=True, type=Path)
    ap.add_argument("--new", required=True, type=Path)
    ap.add_argument("--csv", type=Path, default=None)
    args = ap.parse_args(argv)

    rows = []
    bad = 0
    for name in FILES:
        old = read_instances(args.old / name)
        new = read_instances(args.new / name)
        lost = sorted(set(old) - set(new))
        gained = sorted(set(new) - set(old))
        moves = [
            ((new[i][0] - old[i][0]) ** 2 + (new[i][2] - old[i][2]) ** 2) ** 0.5
            for i in sorted(set(old) & set(new))
        ]
        moved = [d for d in moves if d > 1e-6]
        row = {
            "file": name,
            "old_instances": len(old),
            "new_instances": len(new),
            "lost_ids": len(lost),
            "gained_ids": len(gained),
            "moved": len(moved),
            "moved_pct": round(100.0 * len(moved) / len(moves), 2) if moves else 0.0,
            "median_move_px": round(statistics.median(moved), 2) if moved else 0.0,
            "p90_move_px": (
                round(sorted(moved)[int(0.9 * (len(moved) - 1))], 2) if moved else 0.0
            ),
            "max_move_px": round(max(moved), 2) if moved else 0.0,
        }
        rows.append(row)
        if lost:
            bad += 1
            print(f"!! {name}: {len(lost)} ids present in --old are MISSING in "
                  f"--new (first: {lost[:5]}) - they will inherit vanilla's "
                  f"coordinate")
        print(
            f"{name:<30} {len(old):>6} -> {len(new):>6} instances, "
            f"{len(moved):>5} moved ({row['moved_pct']:5.2f} %), "
            f"median {row['median_move_px']:>7.2f} px, "
            f"p90 {row['p90_move_px']:>7.2f}, max {row['max_move_px']:>8.2f}"
        )

    if args.csv:
        args.csv.parent.mkdir(parents=True, exist_ok=True)
        with args.csv.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        print(f"-> {args.csv}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
