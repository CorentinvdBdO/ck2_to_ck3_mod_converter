#!/usr/bin/env python3
"""Verify that every CK3 key claimed by the mapping tables exists in CK3 1.19.

Checks each `ck3_key` of every `exact`/`approx` row in
`mappings/modifiers.csv` and `mappings/trait_fields.csv`, and each `ck3_trait`
of `mappings/vanilla_traits.csv`, against the local CK3 install:

  1. modifier keys: declared in `game/common/modifier_definition_formats/`
     (the CK3 counterpart of CK2's common/modifier_definitions), or used as
     `<key> = <value>` anywhere under `game/common/`;
  2. trait properties: documented in `game/common/traits/_traits.info` or used
     in `game/common/traits/00_traits.txt`;
  3. trait names: defined as a top-level block in `game/common/traits/00_traits.txt`.

Placeholder keys that contain `<` (e.g. `<ck3_faith>_opinion`) are reported
separately - they are resolved by the culture/religion lanes, not here.

Writes a report to `docs/evidence/verify_ck3_keys.txt` and exits non-zero if
anything is missing.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from collect_ck2_modifier_keys import tokenize, walk  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
GAME_DEFAULT = Path("/home/cvdbdo/.local/share/Steam/steamapps/common/Crusader Kings III/game")


def read(fp: Path) -> str:
    return fp.read_text(encoding="utf-8-sig", errors="replace")


def declared_modifiers(game: Path) -> set[str]:
    keys: set[str] = set()
    for f in sorted((game / "common" / "modifier_definition_formats").glob("*.txt")):
        keys |= {m.group(1) for m in re.finditer(r"(?m)^([A-Za-z_][A-Za-z_0-9]*)\s*=\s*\{", read(f))}
    return keys


def assigned_keys(game: Path) -> set[str]:
    """Every `key =` left-hand side used anywhere under game/common/."""
    keys: set[str] = set()
    pat = re.compile(r"(?m)^[ \t]*([a-z_][a-z_0-9]*)[ \t]*=")
    for f in (game / "common").rglob("*.txt"):
        try:
            keys |= {m.group(1) for m in pat.finditer(read(f))}
        except OSError:
            continue
    return keys


def trait_properties(game: Path) -> set[str]:
    info = read(game / "common" / "traits" / "_traits.info")
    keys = {m.group(1) for m in re.finditer(r"(?m)^[ \t]*([a-z_][a-z_0-9]*)\s*=", info)}
    tr = read(game / "common" / "traits" / "00_traits.txt")
    keys |= {m.group(1) for m in re.finditer(r"(?m)^[ \t]*([a-z_][a-z_0-9]*)\s*=", tr)}
    return keys


def trait_names(game: Path) -> set[str]:
    t = read(game / "common" / "traits" / "00_traits.txt")
    return {k for p, k, v in walk(tokenize(t)) if len(p) == 0 and v is None}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", type=Path, default=GAME_DEFAULT)
    ap.add_argument("--mappings", type=Path, default=REPO / "mappings")
    ap.add_argument("--out", type=Path, default=REPO / "docs" / "evidence" / "verify_ck3_keys.txt")
    args = ap.parse_args()

    if not (args.game / "common").is_dir():
        raise SystemExit(f"no CK3 game/common under {args.game}")

    decl = declared_modifiers(args.game)
    used = assigned_keys(args.game)
    props = trait_properties(args.game)
    names = trait_names(args.game)

    lines: list[str] = [
        f"# verify_ck3_keys.py against {args.game}",
        f"# modifier keys declared in modifier_definition_formats/: {len(decl)}",
        f"# distinct `key =` left-hand sides under common/: {len(used)}",
        f"# trait properties (from _traits.info + 00_traits.txt): {len(props)}",
        f"# trait names in 00_traits.txt: {len(names)}",
        "",
    ]
    misses: list[str] = []
    placeholders: list[str] = []

    usage_only: list[str] = []

    def check(csv_name: str, key_col: str, status_col: str | None, universe: set[str], label: str):
        fp = args.mappings / csv_name
        n_ok = 0
        with fp.open(encoding="utf-8") as fh:
            # `mappings/*.csv` may open with a `#` header block explaining the
            # columns (vanilla_traits.csv does); skip it like every other
            # reader in the repo (`ck2ck3.overrides`, `ck2ck3.traits.tables`).
            lines = [l for l in fh if not l.lstrip().startswith("#")]
            for row in csv.DictReader(lines):
                if status_col and row[status_col] == "none":
                    continue
                key = row[key_col].strip()
                if not key:
                    continue
                if "<" in key:
                    placeholders.append(f"{csv_name}: {row[list(row)[0]]} -> {key}")
                    continue
                if key in universe:
                    n_ok += 1
                    if csv_name == "modifiers.csv" and key not in decl:
                        usage_only.append(key)
                else:
                    misses.append(f"{csv_name}: {row[list(row)[0]]} -> {key} NOT FOUND in {label}")
        lines.append(f"{csv_name}: {n_ok} keys verified against {label}")

    check("modifiers.csv", "ck3_key", "status", decl | used, "modifier_definition_formats/ or any common/ assignment")
    check("trait_fields.csv", "ck3_key", "status", props, "_traits.info or 00_traits.txt")
    check("vanilla_traits.csv", "ck3_trait", "status", names, "00_traits.txt trait names")

    lines += ["",
              f"modifiers.csv keys found only as a common/ assignment and not declared in "
              f"modifier_definition_formats/ ({len(set(usage_only))}) - these are CK3 core "
              f"modifiers/trait fields that need no declaration:"]
    lines += ["  " + k for k in sorted(set(usage_only))]
    lines += ["", f"placeholder keys deferred to the culture/religion lanes: {len(placeholders)}"]
    lines += ["  " + p for p in sorted(set(placeholders))[:5]]
    if len(set(placeholders)) > 5:
        lines.append(f"  ... and {len(set(placeholders)) - 5} more")
    lines += ["", f"MISSES: {len(misses)}"] + ["  " + m for m in misses]

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    if misses:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
