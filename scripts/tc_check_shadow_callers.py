#!/usr/bin/env python3
"""Did shadowing a vanilla file orphan a caller that is still live?

The one real risk of lane `tc-template`: an empty shadow deletes the vanilla
definitions in a file, and a vanilla file the mod *keeps* still calls one of
them. CK3 answers with "unknown effect/trigger/script value", which is a
mechanic quietly not running — worse than the dangling title the shadow fixed.

So, for every file the mod shadows:

1. read the vanilla original and take its top-level keys (``some_effect = {``);
2. scan every vanilla script file the mod does **not** shadow for that key;
3. report each key that still has a live caller, with the callers.

Exit code 1 when anything is orphaned, so ``ci/checks.sh`` and a lane review
both notice.

    uv run scripts/tc_check_shadow_callers.py <mod dir> [--game DIR] [--out CSV]
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from ck2ck3.tcshadow import SCRIPT_SUFFIXES, strip_comments  # noqa: E402

DEFAULT_GAME = Path(
    "/home/cvdbdo/.local/share/Steam/steamapps/common/Crusader Kings III/game"
)
#: A definition at column 0 of a vanilla database file.
TOP_KEY_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=", re.MULTILINE)
TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

#: Folders whose keys are never called by name from elsewhere: a decision, an
#: event, an achievement or a story cycle is run by the engine or by an
#: on_action, and both of those are shadowed alongside it. Scanning them would
#: report every decision id as "orphaned" by its own localisation.
SELF_CONTAINED = (
    "common/achievements",
    "common/coat_of_arms/dynamic_definitions",
    "common/culture/creation_names",
    "common/decisions",
    "common/flavorization",
    "common/great_projects",
    "common/legends",
    "common/situation",
    "common/story_cycles",
    "common/struggle",
    "common/travel",
    "common/tutorial_lesson_chains",
    "common/tutorial_lessons",
    "events",
    "gfx",
)


def shadowed_paths(mod: Path, game: Path) -> list[str]:
    """Relative paths where the mod holds a file that vanilla also holds."""
    out: list[str] = []
    for path in sorted(mod.rglob("*")):
        if not path.is_file() or path.suffix not in SCRIPT_SUFFIXES:
            continue
        rel = path.relative_to(mod).as_posix()
        if (game / rel).is_file():
            out.append(rel)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mod", type=Path)
    parser.add_argument("--game", type=Path, default=DEFAULT_GAME)
    parser.add_argument(
        "--out",
        type=Path,
        default=REPO_ROOT / "docs" / "evidence" / "tc_template_orphaned_callers.csv",
    )
    args = parser.parse_args(argv)
    game, mod = args.game, args.mod
    if not game.is_dir() or not mod.is_dir():
        print("game or mod folder not found", file=sys.stderr)
        return 2

    shadowed = shadowed_paths(mod, game)
    checked = [
        rel for rel in shadowed if not rel.startswith(SELF_CONTAINED)
    ]
    keys: dict[str, str] = {}
    for rel in checked:
        vanilla = strip_comments(
            (game / rel).read_text(encoding="utf-8-sig", errors="replace")
        )
        # A `neutralise`d override keeps the keys and drops the bodies, so its
        # definitions are still there; only what the override *lost* can orphan
        # a caller.
        kept = set(
            TOP_KEY_RE.findall(
                strip_comments(
                    (mod / rel).read_text(encoding="utf-8-sig", errors="replace")
                )
            )
        )
        for key in TOP_KEY_RE.findall(vanilla):
            if key not in kept:
                keys.setdefault(key, rel)
    print(
        f"{len(shadowed)} shadowed files, {len(checked)} of them callable, "
        f"{len(keys)} definitions blanked",
        file=sys.stderr,
    )
    if not keys:
        return 0

    shadow_set = set(shadowed)
    callers: dict[str, set[str]] = defaultdict(set)
    for path in game.rglob("*"):
        if not path.is_file() or path.suffix not in SCRIPT_SUFFIXES:
            continue
        rel = path.relative_to(game).as_posix()
        if rel in shadow_set:
            continue
        text = strip_comments(path.read_text(encoding="utf-8-sig", errors="replace"))
        for token in set(TOKEN_RE.findall(text)):
            if token in keys:
                callers[token].add(rel)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["key", "shadowed_file", "live_callers", "example_caller"])
        for key in sorted(callers):
            live = sorted(callers[key])
            writer.writerow([key, keys[key], len(live), live[0]])
    print(f"{len(callers)} blanked definitions still have a live caller -> {args.out}")
    for key in sorted(callers)[:15]:
        print(f"  {key}  ({keys[key]})  <- {sorted(callers[key])[0]}")
    return 1 if callers else 0


if __name__ == "__main__":
    raise SystemExit(main())
