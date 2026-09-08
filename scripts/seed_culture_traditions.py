#!/usr/bin/env python
"""Seed `overrides/traditions_of_culture_group.csv`, the placeholder traditions.

Why it exists: `derive_traditions()` can only read two CK2 flags (`seafarer`,
`allow_looting`), which in Faerûn cover 97 of 419 cultures. The other 322 got a
CK3 culture with **no** `traditions` block at all — an empty culture screen in
game. CK2 has no tradition concept to convert, so the gap can only be filled by
human input; this script writes the mechanical first draft of that input so
nobody has to type 67 rows.

Every value it writes is `assumed`, keyed on the race from
`overrides/race_of_culture_group.csv` (`docs/design_races.md` item 1) with a
handful of per-group refinements. A submod replaces the file wholesale.

    uv run scripts/seed_culture_traditions.py [--config configs/faerun.toml]

Re-running **overwrites** the file, so edit the CSV after seeding, not before.
Every id must survive `uv run scripts/verify_culture_traditions.py`.
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
from ck2ck3.steps.cultures import MAX_TRADITIONS, read_ck2_cultures  # noqa: E402
from seed_culture_overrides import write_csv  # noqa: E402

#: Races that deliberately get **no** traditions: animal cultures (Faerûn's
#: `99_animals.txt` holds cat/dog/duck/... "cultures" used for beast rulers),
#: the undead, constructs and the province-filler monster culture. None of them
#: is a society with customs to model, and an empty `traditions` block is
#: legal CK3 (`verified`: 1 of 233 vanilla culture blocks defines none).
NO_TRADITION_RACES = frozenset(
    {
        "horse",
        "cat",
        "bear",
        "hedgehog",
        "duck",
        "dog",
        "elephant",
        "panda",
        "undead",
        "construct",
        "monster",
    }
)

#: Race → CK3 traditions. Every id is base game (`common/culture/traditions/
#: 00_*.txt`), never DLC, so the mod loads without any DLC owned.
RACE_TRADITIONS: dict[str, tuple[str, ...]] = {
    "human": ("tradition_hereditary_hierarchy", "tradition_martial_admiration"),
    "elf": ("tradition_forest_folk", "tradition_sacred_groves"),
    "fey": ("tradition_forest_folk", "tradition_sacred_groves"),
    "plant": ("tradition_forest_folk", "tradition_sacred_groves"),
    "dwarf": (
        "tradition_mountain_homes",
        "tradition_ancient_miners",
        "tradition_metal_craftsmanship",
    ),
    "gnome": ("tradition_hidden_cities", "tradition_metal_craftsmanship"),
    "giant": ("tradition_mountain_homes", "tradition_only_the_strong"),
    "halfling": ("tradition_esteemed_hospitality", "tradition_storytellers"),
    "orc": ("tradition_warrior_culture", "tradition_only_the_strong"),
    "goblinoid": ("tradition_warrior_culture", "tradition_strength_in_numbers"),
    "dragon": ("tradition_hereditary_hierarchy", "tradition_isolationist"),
    "beastfolk": ("tradition_hunters", "tradition_tribe_unity"),
    "centaur": ("tradition_horse_lords", "tradition_pastoralists"),
    "minotaur": ("tradition_hidden_cities", "tradition_only_the_strong"),
    "avian": ("tradition_mountaineers", "tradition_hunters"),
    "fish": ("tradition_fishermen", "tradition_seafaring"),
    "serpent": ("tradition_mystical_ancestors", "tradition_ruling_caste"),
    "scaly": ("tradition_jungle_dwellers", "tradition_hunters"),
    "aberration": ("tradition_hidden_cities", "tradition_isolationist"),
    "celestial": (
        "tradition_hereditary_hierarchy",
        "tradition_philosopher_culture",
    ),
    "fiendish": ("tradition_ruling_caste", "tradition_only_the_strong"),
    "gith": ("tradition_warrior_culture", "tradition_isolationist"),
    "planetouched": ("tradition_diasporic", "tradition_astute_diplomats"),
    "genie": ("tradition_ruling_caste", "tradition_hereditary_hierarchy"),
    "outsider": ("tradition_mystical_ancestors", "tradition_isolationist"),
    "outworlder": ("tradition_diasporic", "tradition_xenophilic"),
    "slaad": ("tradition_strength_in_numbers", "tradition_only_the_strong"),
}

#: Per-group refinement, applied instead of the race default. Kept short on
#: purpose: only groups whose Forgotten Realms identity is unmistakable and
#: whose race default would be plainly wrong (four elf groups that are not all
#: woodland, and the human groups with a distinct biome or society).
GROUP_TRADITIONS: dict[str, tuple[str, ...]] = {
    # elves: only the sylvan ones actually live in forests
    "dark_elf_group": (
        "tradition_hidden_cities",
        "tradition_ruling_caste",
        "tradition_only_the_strong",
    ),
    "high_elf_group": (
        "tradition_sacred_groves",
        "tradition_language_scholars",
        "tradition_hereditary_hierarchy",
    ),
    "sylvan_elf_group": (
        "tradition_forest_folk",
        "tradition_sacred_groves",
        "tradition_hunters",
    ),
    "eladrin_group": (
        "tradition_sacred_groves",
        "tradition_mystical_ancestors",
        "tradition_isolationist",
    ),
    # humans with a biome or society the default pair does not describe
    "taan_group": ("tradition_horse_lords", "tradition_pastoralists"),
    "zakharan_group": ("tradition_desert_nomads", "tradition_esteemed_hospitality"),
    "old_zakharan_group": (
        "tradition_desert_nomads",
        "tradition_esteemed_hospitality",
    ),
    "ulutiun_group": ("tradition_hunters", "tradition_esteemed_hospitality"),
    "malatran_group": ("tradition_jungle_dwellers", "tradition_hunters"),
    "maztican_group": ("tradition_jungle_dwellers", "tradition_warrior_culture"),
    "lapal_group": ("tradition_wetlanders", "tradition_jungle_dwellers"),
    "shou_group": (
        "tradition_hereditary_hierarchy",
        "tradition_philosopher_culture",
    ),
    "imaskari_group": ("tradition_hidden_cities", "tradition_philosopher_culture"),
    "netherese_group": (
        "tradition_mystical_ancestors",
        "tradition_hereditary_hierarchy",
    ),
}

PREAMBLE = [
    "CK2 culture group -> CK3 culture `traditions` (space-separated vanilla ids).",
    "ALL VALUES ARE assumed placeholders, submod to replace: CK2 has no tradition",
    "concept, so nothing here is converted from the source mod. Generated by",
    "scripts/seed_culture_traditions.py from overrides/race_of_culture_group.csv",
    "(race) plus a short per-group table; see docs/step_cultures_religions.md",
    "section `Placeholder culture traditions` for the derivation table.",
    "An EMPTY `traditions` cell means deliberately none (animals, undead,",
    "constructs, the monster filler culture) -- not missing input.",
    "A group with NO ROW at all makes the cultures step warn.",
    "The step merges these with the CK2-flag traditions (seafarer ->",
    "tradition_seafaring, allow_looting -> tradition_practiced_pirates), dedupes",
    f"and truncates to DEFAULT_MAX_TRADITIONS = {MAX_TRADITIONS}.",
    "Every id is base game (common/culture/traditions/00_*.txt), no DLC; checked",
    "by scripts/verify_culture_traditions.py.",
]


def traditions_for(group_id: str, race: str) -> tuple[tuple[str, ...], str]:
    """(tradition ids, how it was derived)."""
    if group_id in GROUP_TRADITIONS:
        return GROUP_TRADITIONS[group_id], f"per-group table for {group_id}"
    if race in NO_TRADITION_RACES:
        return (), f"race {race} is on the no-traditions list"
    if race in RACE_TRADITIONS:
        return RACE_TRADITIONS[race], f"race {race}"
    return RACE_TRADITIONS["human"], f"race {race} unknown; fell back to human"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="configs/faerun.toml")
    args = ap.parse_args()
    cfg = Config.load(Path(args.config))
    out = overrides.overrides_dir(cfg)
    groups = read_ck2_cultures(cfg.ck2_mod)
    race_of_group = overrides.read_map(
        cfg, "race_of_culture_group.csv", "ck2_culture_group", "race"
    )

    rows: list[list[str]] = []
    for group in groups:
        race = race_of_group.get(group.id, "unknown")
        traditions, how = traditions_for(group.id, race)
        assert len(traditions) <= MAX_TRADITIONS, group.id
        flags = sorted(
            flag
            for flag in ("seafarer", "allow_looting")
            for culture in group.cultures
            if culture.flag(flag)
        )
        if flags:
            how += f"; {len(set(flags))} CK2 flag(s) add per culture at runtime"
        rows.append([group.id, " ".join(traditions), race, how])

    write_csv(
        out / "traditions_of_culture_group.csv",
        ["ck2_culture_group", "traditions", "race", "derivation"],
        rows,
        PREAMBLE,
    )
    empty = sum(1 for row in rows if not row[1])
    print(f"{len(rows) - empty} groups with traditions, {empty} deliberately empty")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
