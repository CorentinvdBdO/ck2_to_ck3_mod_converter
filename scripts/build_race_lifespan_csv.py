#!/usr/bin/env python
"""Seed `overrides/race_lifespan.csv`: one row per `race_trait`, D&D defaults.

Human-editable input file, so it is generated **once** and then owned by
whoever tunes it; re-running only adds rows for race traits that appeared
upstream (existing rows are kept verbatim). Every number is `assumed` — see the
file header and `docs/step_traits.md`.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from ck2ck3.traits import CK3_BASE_LIFE_EXPECTANCY  # noqa: E402

OUT = ROOT / "overrides" / "race_lifespan.csv"
CLASSIFIED = ROOT / "docs" / "evidence" / "faerun_custom_traits.csv"

HEADER = f"""\
# overrides/race_lifespan.csv - human input for the `traits` step.
#
# STATUS: every number below is `assumed`, not verified. Defaults come from the
# D&D 3.5e Forgotten Realms Campaign Setting maximum ages (the edition that
# matches the 1371 DR start date, docs/PROJECT.md) and are the submod's to tune.
#
# columns
#   ck2_trait        the CK2 trait id the row applies to (race traits only)
#   race             the D&D race the trait stands for, for the reader
#   dnd_max_age      D&D 3.5e maximum age in years, the source datum
#   life_expectancy  the CK3 modifier value, i.e. dnd_max_age - {CK3_BASE_LIFE_EXPECTANCY}
#                    ({CK3_BASE_LIFE_EXPECTANCY} = the CK3 base life expectancy in years, `assumed`:
#                    CK3 1.19 exposes no define for it). Empty = emit none.
#   immortal         yes -> emit `immortal = yes` instead of life_expectancy
#   note             why
#
# A race trait with no row here, or with an empty life_expectancy, gets
# `genetic`/`physical` but no lifespan; the step warns about each one.
"""

# ck2_trait -> (race, dnd_max_age or None, immortal, note)
SEED: dict[str, tuple[str, int | None, bool, str]] = {
    "creature_human": ("human", None, False, "CK3 baseline; no modifier"),
    "creature_elf": ("elf", 700, False, "FRCS elf maximum age"),
    "creature_drow": ("drow", 700, False, "same as elf in 3.5e"),
    "creature_half_elf": ("half_elf", 180, False, "FRCS half-elf maximum age"),
    "creature_dwarf": ("dwarf", 350, False, "FRCS dwarf maximum age"),
    "creature_halfling": ("halfling", 150, False, "FRCS halfling maximum age"),
    "creature_gnome": ("gnome", 350, False, "FRCS gnome maximum age"),
    "creature_orc": ("orc", 45, False, "3.5e orc maximum age; below the CK3 base"),
    "creature_half_orc": ("half_orc", 60, False, "3.5e half-orc maximum age"),
    "creature_tiefling": ("tiefling", 100, False, "planetouched, ~1.2x human"),
    "creature_aasimar": ("aasimar", 100, False, "planetouched, ~1.2x human"),
    "creature_genasi": ("genasi", 100, False, "planetouched, ~1.2x human"),
    "creature_dragonborn": ("dragonborn", 80, False, "dragonborn maximum age"),
    "creature_giant": ("giant", 300, False, "3.5e true giant maximum age"),
    "creature_dragon": ("dragon", 1000, False, "great wyrm; not immortal in CK2"),
    "undead": ("undead", None, True, "CK2 trait has immortal = yes"),
    "lich": ("lich", None, True, "CK2 trait has immortal = yes"),
    "archlich": ("lich", None, True, "CK2 trait has immortal = yes"),
    "lich_baelnorn": ("lich", None, True, "CK2 trait has immortal = yes"),
    "vampire": ("vampire", None, True, "CK2 trait has immortal = yes"),
    "vampire_spawn": ("vampire", None, True, "CK2 trait has immortal = yes"),
    "dhampyr": ("dhampyr", 1000, False, "half-vampire; CK2 trait is not immortal"),
    "creature_celestial": ("celestial", None, True, "outsider, CK2 immortal = yes"),
    "creature_fiend": ("fiend", None, True, "outsider, CK2 immortal = yes"),
    "creature_construct": ("construct", None, True, "CK2 trait has immortal = yes"),
    "longevity": ("longevity", 1000, False, "Faerûn longevity marker"),
}


def race_traits() -> list[str]:
    with CLASSIFIED.open(encoding="utf-8", newline="") as handle:
        return [
            row["ck2_trait"]
            for row in csv.DictReader(handle)
            if row["ck3_treatment"] == "race_trait"
        ]


def main() -> int:
    existing: dict[str, dict[str, str]] = {}
    if OUT.exists():
        with OUT.open(encoding="utf-8", newline="") as handle:
            lines = [ln for ln in handle if not ln.startswith("#")]
        existing = {r["ck2_trait"]: r for r in csv.DictReader(lines)}

    rows: list[dict[str, str]] = []
    for trait in race_traits():
        if trait in existing:
            rows.append(existing[trait])
            continue
        race, max_age, immortal, note = SEED.get(trait, ("", None, False, ""))
        rows.append(
            {
                "ck2_trait": trait,
                "race": race,
                "dnd_max_age": str(max_age) if max_age is not None else "",
                "life_expectancy": (
                    str(max_age - CK3_BASE_LIFE_EXPECTANCY)
                    if max_age is not None
                    else ""
                ),
                "immortal": "yes" if immortal else "no",
                "note": note or "no D&D default; fill in or leave blank",
            }
        )
    fields = ["ck2_trait", "race", "dnd_max_age", "life_expectancy", "immortal", "note"]
    with OUT.open("w", encoding="utf-8", newline="") as handle:
        handle.write(HEADER)
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    filled = sum(1 for r in rows if r["life_expectancy"] or r["immortal"] == "yes")
    print(f"{OUT}: {len(rows)} race traits, {filled} with a lifespan")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
