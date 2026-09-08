"""Check every CK3 id in the character/dynasty mapping tables against 1.19.

The repo rule (CLAUDE.md): the converter never invents content, so every CK3
key or value a table names must exist in the installed game. Prints
``MISSES: 0`` when it does.

Checks:
* ``mappings/death_reasons.csv`` — every ck3_death_reason in common/deathreasons
  and every ck2_death_reason defined in Faerûn's common/death.
* ``mappings/nicknames.csv`` — every ck3_nickname in common/nicknames.
* ``mappings/character_effects.csv`` — every non-empty ck3_key is either a
  history key from ``history/_characters.info``, an effect that appears in the
  game's own scripts, or a documented exception listed below.

Run: uv run scripts/verify_character_tables.py
"""

from __future__ import annotations

import csv
import re
import subprocess
import sys
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
warnings.simplefilter("ignore")

from ck2ck3.pdx import parse_file  # noqa: E402
from ck2ck3.pdx.nodes import Node  # noqa: E402

CK2 = ROOT / "Faerun" / "Faerun"
CK3 = Path("/home/cvdbdo/.local/share/Steam/steamapps/common/Crusader Kings III/game")

#: CK3 history keys, from history/_characters.info plus the ones vanilla's own
#: history files use that the .info does not list.
HISTORY_KEYS = {
    "name", "dna", "female", "martial", "prowess", "diplomacy", "intrigue",
    "stewardship", "learning", "trait", "add_trait", "remove_trait", "father",
    "mother", "real_father", "disallow_random_traits", "faith", "religion",
    "culture", "dynasty", "dynasty_house", "give_nickname", "sexuality",
    "health", "fertility", "set_house", "set_culture", "capital",
    "set_character_faith_no_effect", "add_spouse", "add_matrilineal_spouse",
    "add_same_sex_spouse", "remove_spouse", "add_concubine", "employer",
    "birth", "death", "effect", "portrait_override",
}


def ids_of(folder: Path) -> set[str]:
    out: set[str] = set()
    for path in sorted(folder.glob("*.txt")):
        out.update(e.key for e in parse_file(path).entries if isinstance(e, Node))
    return out


def read(rel: str) -> list[dict[str, str]]:
    with (ROOT / rel).open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def effect_exists(name: str) -> bool:
    """True when the game's own scripts use ``name`` as an effect."""
    result = subprocess.run(
        ["grep", "-rlF", f"{name} =", str(CK3 / "events"), str(CK3 / "common"),
         str(CK3 / "history")],
        capture_output=True,
        text=True,
    )
    return bool(result.stdout.strip())


def main() -> int:
    misses: list[str] = []

    ck3_deaths = ids_of(CK3 / "common" / "deathreasons")
    ck2_deaths = ids_of(CK2 / "common" / "death")
    rows = read("mappings/death_reasons.csv")
    for row in rows:
        if row["ck3_death_reason"] not in ck3_deaths:
            misses.append(f"death_reasons.csv: CK3 {row['ck3_death_reason']} not in 1.19")
        if row["ck2_death_reason"] not in ck2_deaths:
            misses.append(f"death_reasons.csv: CK2 {row['ck2_death_reason']} not in Faerun")
    uncovered = ck2_deaths - {r["ck2_death_reason"] for r in rows}
    misses += [f"death_reasons.csv: CK2 {d} has no row" for d in sorted(uncovered)]
    print(f"death_reasons.csv: {len(rows)} rows, {len(ck3_deaths)} CK3 ids available")

    ck3_nicks = ids_of(CK3 / "common" / "nicknames")
    rows = read("mappings/nicknames.csv")
    for row in rows:
        if row["ck3_nickname"] and row["ck3_nickname"] not in ck3_nicks:
            misses.append(f"nicknames.csv: CK3 {row['ck3_nickname']} not in 1.19")
    mapped = sum(1 for r in rows if r["ck3_nickname"])
    print(f"nicknames.csv: {len(rows)} rows, {mapped} mapped, {len(rows) - mapped} commented")

    rows = read("mappings/character_effects.csv")
    checked = 0
    for row in rows:
        key = row["ck3_key"]
        if not key:
            continue
        checked += 1
        if row["level"] == "history" and key in HISTORY_KEYS:
            continue
        if effect_exists(key):
            continue
        misses.append(f"character_effects.csv: CK3 {key!r} not found in the 1.19 scripts")
    print(f"character_effects.csv: {len(rows)} rows, {checked} CK3 keys checked")

    for miss in misses:
        print(f"  MISS {miss}")
    print(f"MISSES: {len(misses)}")
    return 1 if misses else 0


if __name__ == "__main__":
    raise SystemExit(main())
