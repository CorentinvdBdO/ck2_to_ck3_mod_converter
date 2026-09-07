#!/usr/bin/env python3
"""Classify the Faerun-specific CK2 traits by the file they are defined in.

Writes `docs/evidence/faerun_custom_traits.csv` with columns
`ck2_trait,source_file,ck3_treatment,note`.

`ck3_treatment` is a *classification*, not a design decision:
  port       - a plain character trait; the trait lane can port it mechanically
  race_trait - belongs to the race/creature system, owned by the races lane
  comment    - part of a CK2-only subsystem (classes, god patrons, biography
               markers); the converter emits it as a comment

CK2 vanilla traits are excluded - those live in `mappings/vanilla_traits.csv`.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from collect_ck2_modifier_keys import tokenize, walk  # noqa: E402

REPO = Path(__file__).resolve().parents[1]


def default_faerun() -> Path:
    """Faerun clone lives in the main checkout; a git worktree sees it as a sibling."""
    for cand in (
        REPO / "Faerun" / "Faerun",
        REPO.parent / "ck2_to_ck3_mod_converter" / "Faerun" / "Faerun",
        REPO.parent.parent / "ck2_to_ck3_mod_converter" / "Faerun" / "Faerun",
    ):
        if (cand / "common" / "traits").is_dir():
            return cand
    return REPO / "Faerun" / "Faerun"
CK2_DEFAULT = Path("/home/cvdbdo/.local/share/Steam/steamapps/common/Crusader Kings II")

# source file -> (treatment, note)
TREATMENT: dict[str, tuple[str, str]] = {
    "00_traits.txt":  ("port", "Faerun addition to the vanilla trait file"),
    "01_traits.txt":  ("port", "Faerun addition to the vanilla trait file"),
    "02_traits.txt":  ("port", "Faerun addition to the vanilla trait file"),
    "03_traits.txt":  ("port", "Faerun addition to the vanilla trait file"),
    "04_battle_scars_and_tattoos_traits.txt": ("port", "battle scar / tattoo trait; CK3 has scarred plus one_eyed/one_legged"),
    "05_LT_traits.txt": ("port", "Faerun addition to the vanilla trait file"),
    "Congenital_Traits.txt": ("port", "congenital trait; CK3 target is genetic = yes plus a group/level tier"),
    "acquired_traits.txt":   ("port", "acquired character trait"),
    "misc_traits.txt":       ("port", "misc character trait"),
    "race_traits.txt":       ("race_trait", "creature/race trait; owned by the races lane (docs/design_races.md)"),
    "template_traits.txt":   ("race_trait", "creature template (lycanthrope, feytouched, ...); owned by the races lane"),
    "character_class_traits.txt": ("comment", "D&D class/level system; no CK3 equivalent"),
    "god_patron_traits.txt":      ("comment", "god-patron trait, drives CK2 <trait>_opinion modifiers; no CK3 equivalent"),
    "religious_traits.txt":       ("comment", "chosen-of-deity trait tied to the CK2 religion system"),
    "roleplaying_traits.txt":     ("comment", "roleplaying marker read by Faerun events"),
    "z_biography_traits.txt":     ("comment", "hidden biography/flavour marker read by Faerun events"),
}


def top_level_traits(directory: Path) -> dict[str, str]:
    """trait name -> file it is defined in (first definition wins)."""
    out: dict[str, str] = {}
    for f in sorted(directory.glob("*.txt")):
        t = f.read_bytes().decode("cp1252", errors="replace")
        for p, k, v in walk(tokenize(t)):
            if len(p) == 0 and v is None:
                out.setdefault(k, f.name)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--faerun", type=Path, default=None)
    ap.add_argument("--ck2", type=Path, default=CK2_DEFAULT)
    ap.add_argument("--out", type=Path, default=REPO / "docs" / "evidence" / "faerun_custom_traits.csv")
    args = ap.parse_args()
    if args.faerun is None:
        args.faerun = default_faerun()

    fae = top_level_traits(args.faerun / "common" / "traits")
    vanilla = set(top_level_traits(args.ck2 / "common" / "traits"))

    rows = []
    unknown_files = set()
    for name, src in sorted(fae.items()):
        if name in vanilla:
            continue
        if src not in TREATMENT:
            unknown_files.add(src)
            continue
        treatment, note = TREATMENT[src]
        rows.append([name, src, treatment, note])
    if unknown_files:
        raise SystemExit(f"no treatment rule for source file(s): {sorted(unknown_files)}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["ck2_trait", "source_file", "ck3_treatment", "note"])
        w.writerows(rows)
    from collections import Counter
    c = Counter(r[2] for r in rows)
    print(f"{len(rows)} Faerun-specific traits -> {args.out}; "
          + ", ".join(f"{k}={v}" for k, v in sorted(c.items())))


if __name__ == "__main__":
    main()
