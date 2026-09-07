#!/usr/bin/env python
"""Seed the three `overrides/*.csv` tables the `cultures` step reads.

The tables are **human input** (`docs/PROJECT.md`): this script only writes the
mechanical first draft so nobody has to type 67 rows, and marks every row a
human should look at with `review = yes`. Re-running it **overwrites** the
files, so edit the CSVs after seeding, not before.

    uv run scripts/seed_culture_overrides.py [--config configs/faerun.toml]
"""

from __future__ import annotations

import argparse
import csv
import io
import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
warnings.simplefilter("ignore")

from ck2ck3 import overrides  # noqa: E402
from ck2ck3.config import Config  # noqa: E402
from ck2ck3.steps.cultures import (  # noqa: E402
    CK2CultureGroup,
    read_ck2_cultures,
)

#: CK2 culture file → the race every one of its groups belongs to, per
#: `docs/design_races.md` item 1. Files that mix races are not listed and fall
#: back to the group's own name.
FILE_RACE = {
    "human.txt": "human",
    "elves.txt": "elf",
    "dwarves.txt": "dwarf",
    "giants.txt": "giant",
    "dragons.txt": "dragon",
    "province_monster_culture.txt": "monster",
}

#: CK2 `graphical_cultures` value → (coa, building, clothing, unit, ethnicity).
#: Only the values with a real-world CK3 analogue are listed; Faerûn's other
#: ~280 fantasy values fall through to the `western_*` defaults, which is what
#: `mappings/culture_fields.csv` prescribes.
REAL_WORLD_GFX: dict[str, tuple[str, str, str, str, str]] = {
    "westerngfx": ("western_coa_gfx", "western_building_gfx", "western_clothing_gfx", "western_unit_gfx", "caucasian"),
    "frankishgfx": ("frankish_group_coa_gfx", "western_building_gfx", "french_clothing_gfx", "western_unit_gfx", "caucasian"),
    "occitangfx": ("occitan_coa_gfx", "mediterranean_building_gfx", "french_clothing_gfx", "western_unit_gfx", "mediterranean"),
    "englishgfx": ("english_coa_gfx", "western_building_gfx", "english_clothing_gfx", "western_unit_gfx", "caucasian"),
    "saxongfx": ("anglo_saxon_coa_gfx", "western_building_gfx", "english_clothing_gfx", "western_unit_gfx", "caucasian"),
    "normangfx": ("norman_coa_gfx", "western_building_gfx", "norman_clothing_gfx", "western_unit_gfx", "caucasian"),
    "germangfx": ("german_group_coa_gfx", "western_building_gfx", "swabian_clothing_gfx", "western_unit_gfx", "caucasian"),
    "celticgfx": ("irish_coa_gfx", "western_building_gfx", "cornish_clothing_gfx", "western_unit_gfx", "caucasian"),
    "norsegfx": ("norse_coa_gfx", "norse_building_gfx", "fp1_norse_clothing_gfx", "norse_unit_gfx", "caucasian_northern_blond"),
    "italiangfx": ("latin_group_coa_gfx", "mediterranean_building_gfx", "western_clothing_gfx", "western_unit_gfx", "mediterranean"),
    "andalusiangfx": ("iberian_group_coa_gfx", "iberian_building_gfx", "iberian_muslim_clothing_gfx", "iberian_muslim_unit_gfx", "mediterranean"),
    "southerngfx": ("latin_group_coa_gfx", "mediterranean_building_gfx", "western_clothing_gfx", "western_unit_gfx", "mediterranean"),
    "byzantinegfx": ("byzantine_group_coa_gfx", "byzantine_building_gfx", "byzantine_clothing_gfx", "eastern_unit_gfx", "mediterranean_byzantine"),
    "orthodoxholygfx": ("byzantine_group_coa_gfx", "byzantine_building_gfx", "byzantine_clothing_gfx", "eastern_unit_gfx", "mediterranean_byzantine"),
    "easterngfx": ("east_slavic_group_coa_gfx", "east_slavic_building_gfx", "east_slavic_clothing_gfx", "eastern_unit_gfx", "slavic"),
    "easternslavicgfx": ("east_slavic_group_coa_gfx", "east_slavic_building_gfx", "east_slavic_clothing_gfx", "eastern_unit_gfx", "slavic"),
    "westernslavicgfx": ("west_slavic_group_coa_gfx", "western_building_gfx", "west_slavic_clothing_gfx", "eastern_unit_gfx", "slavic"),
    "croatsouthslavicgfx": ("south_slavic_group_coa_gfx", "byzantine_building_gfx", "west_slavic_clothing_gfx", "eastern_unit_gfx", "slavic"),
    "serbsouthslavicgfx": ("south_slavic_group_coa_gfx", "byzantine_building_gfx", "west_slavic_clothing_gfx", "eastern_unit_gfx", "slavic"),
    "ugricgfx": ("ugro_permian_group_coa_gfx", "western_building_gfx", "ugro_permian_clothing_gfx", "northern_unit_gfx", "circumpolar"),
    "finnishholygfx": ("balto_finnic_group_coa_gfx", "western_building_gfx", "sami_clothing_gfx", "northern_unit_gfx", "circumpolar"),
    "pagangfx": ("baltic_group_coa_gfx", "western_building_gfx", "northern_clothing_gfx", "northern_unit_gfx", "caucasian"),
    "norseholygfx": ("norse_coa_gfx", "norse_building_gfx", "fp1_norse_clothing_gfx", "norse_unit_gfx", "caucasian_northern_blond"),
    "muslimgfx": ("arabic_group_coa_gfx", "mena_building_gfx", "mena_clothing_gfx", "mena_unit_gfx", "arab"),
    "arabicgfx": ("arabic_group_coa_gfx", "mena_building_gfx", "mena_clothing_gfx", "mena_unit_gfx", "arab"),
    "levantinegfx": ("arabic_group_coa_gfx", "mena_building_gfx", "mena_clothing_gfx", "mena_unit_gfx", "arab"),
    "bektashigfx": ("turkic_group_coa_gfx", "mena_building_gfx", "turkic_clothing_gfx", "mena_unit_gfx", "turkic"),
    "hashshashingfx": ("iranian_group_coa_gfx", "iranian_building_gfx", "iranian_clothing_gfx", "iranian_unit_gfx", "arab"),
    "persiangfx": ("iranian_group_coa_gfx", "iranian_building_gfx", "iranian_clothing_gfx", "iranian_unit_gfx", "arab"),
    "turkishgfx": ("turkic_group_coa_gfx", "mena_building_gfx", "turkic_clothing_gfx", "mena_unit_gfx", "turkic"),
    "cumangfx": ("steppe_coa_gfx", "steppe_building_gfx", "turkic_clothing_gfx", "mongol_unit_gfx", "turkic_west"),
    "egyptiangfx": ("arabic_group_coa_gfx", "mena_building_gfx", "mena_clothing_gfx", "mena_unit_gfx", "arab"),
    "jewishholygfx": ("israelite_group_coa_gfx", "mena_building_gfx", "mena_clothing_gfx", "mena_unit_gfx", "arab"),
    "nehekharangfx": ("arabic_group_coa_gfx", "mena_building_gfx", "mena_clothing_gfx", "mena_unit_gfx", "arab"),
    "berbergfx": ("berber_group_coa_gfx", "berber_group_building_gfx", "afr_berber_clothing_gfx", "mena_unit_gfx", "african"),
    "africangfx": ("central_african_group_coa_gfx", "african_building_gfx", "african_clothing_gfx", "sub_sahran_unit_gfx", "african"),
    "westafricangfx": ("west_african_group_coa_gfx", "african_building_gfx", "african_clothing_gfx", "sub_sahran_unit_gfx", "african"),
    "westafricanholygfx": ("west_african_group_coa_gfx", "african_building_gfx", "african_clothing_gfx", "sub_sahran_unit_gfx", "african"),
    "indiangfx": ("indo_aryan_group_coa_gfx", "indian_building_gfx", "indian_clothing_gfx", "indian_unit_gfx", "indian"),
    "southindiangfx": ("dravidian_group_coa_gfx", "indian_building_gfx", "indian_clothing_gfx", "indian_unit_gfx", "south_indian"),
    "bodpagfx": ("tibetan_group_coa_gfx", "tibetan_building_gfx", "tangut_clothing_gfx", "eastern_unit_gfx", "asian_tibetan"),
    "mongolgfx": ("mongol_coa_gfx", "steppe_building_gfx", "mongol_clothing_gfx", "mongol_unit_gfx", "asian_mongol"),
    "khitangfx": ("steppe_coa_gfx", "steppe_building_gfx", "khitan_clothing_gfx", "mongol_unit_gfx", "asian_mongol"),
    "chinesegfx": ("chinese_group_coa_gfx", "chinese_building_gfx", "chinese_clothing_gfx", "chinese_unit_gfx", "asian_han_chinese"),
    "japanesegfx": ("japanese_coa_gfx", "japanese_building_gfx", "japanese_clothing_gfx", "japanese_unit_gfx", "asian_japanese"),
    "koreangfx": ("chinese_group_coa_gfx", "chinese_building_gfx", "korean_clothing_gfx", "chinese_unit_gfx", "asian_manchu_korean"),
    "khmergfx": ("burman_group_coa_gfx", "southeast_asian_building_gfx", "southeast_asian_clothing_gfx", "southeast_asian_unit_gfx", "asian_malay"),
    "mesoamericangfx": ("western_coa_gfx", "african_building_gfx", "african_clothing_gfx", "sub_sahran_unit_gfx", "east_african"),
    "aztecholygfx": ("western_coa_gfx", "african_building_gfx", "african_clothing_gfx", "sub_sahran_unit_gfx", "east_african"),
}

#: Vanilla ethnicity for the human CK2 culture groups, from the group's own
#: `graphical_cultures` first value (`docs/design_races.md` item 5 tier 2).
ETHNICITY_REVIEW_NOTE = "assumed from the CK2 graphical_cultures value"


def race_of(group: CK2CultureGroup) -> tuple[str, bool, str]:
    """(race, needs_review, how it was derived)."""
    race = FILE_RACE.get(group.source)
    if race is not None:
        review = group.source != "human.txt" and group.slug != race
        return race, review, f"CK2 file {group.source}"
    return group.slug, True, f"CK2 group id {group.id} (file {group.source} mixes races)"


def write_csv(path: Path, header: list[str], rows: list[list[str]], preamble: list[str]) -> None:
    buffer = io.StringIO()
    for line in preamble:
        buffer.write(f"# {line}\n")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(buffer.getvalue(), encoding="utf-8")
    print(f"wrote {path} ({len(rows)} rows)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="configs/faerun.toml")
    args = ap.parse_args()
    cfg = Config.load(Path(args.config))
    out = overrides.overrides_dir(cfg)
    groups = read_ck2_cultures(cfg.ck2_mod)

    race_rows: list[list[str]] = []
    ethnicity_rows: list[list[str]] = []
    for group in groups:
        race, review, how = race_of(group)
        race_rows.append(
            [group.id, race, group.source, "yes" if review else "no", how]
        )
        gfx0 = group.graphical_cultures[0] if group.graphical_cultures else ""
        if race == "human":
            ethnicity = REAL_WORLD_GFX.get(gfx0, (None,) * 5)[4] or "mediterranean"
            note = (
                f"{ETHNICITY_REVIEW_NOTE} {gfx0}"
                if gfx0 in REAL_WORLD_GFX
                else f"no real-world analogue for {gfx0!r}; fell back to mediterranean"
            )
            ethnicity_rows.append(
                [group.id, ethnicity, "no" if gfx0 in REAL_WORLD_GFX else "yes", note]
            )
        else:
            ethnicity_rows.append(
                [
                    group.id,
                    f"fae_placeholder_{race}",
                    "yes",
                    "placeholder until a ck3_fantasy_assets pack ships a real ethnicity",
                ]
            )

    write_csv(
        out / "race_of_culture_group.csv",
        ["ck2_culture_group", "race", "ck2_source_file", "review", "derivation"],
        race_rows,
        [
            "Race of each CK2 culture group -> heritage `parameters = { species_<race> = yes }`.",
            "Seeded by scripts/seed_culture_overrides.py; docs/design_races.md item 1.",
            "review = yes means the value was derived from the group NAME, not from an",
            "unambiguous source file: a human must confirm it (e.g. elves.txt holds four",
            "groups but one race, giants.txt holds giants and giantkin).",
            "Editing `race` changes the emitted species flag and the placeholder ethnicity id.",
        ],
    )
    write_csv(
        out / "ethnicity_of_culture_group.csv",
        ["ck2_culture_group", "ck3_ethnicity", "review", "note"],
        ethnicity_rows,
        [
            "Portrait ethnicity of each CK2 culture group -> culture `ethnicities = { 10 = <x> }`.",
            "Seeded by scripts/seed_culture_overrides.py; docs/design_races.md item 5 tier 2.",
            "Human groups get the nearest vanilla ethnicity, non-human groups a generated",
            "`fae_placeholder_<race>` that inherits a vanilla look with a # TODO comment.",
            "review = yes means a human must confirm: either no real-world analogue existed",
            "for the CK2 graphical_cultures value, or the race needs real art.",
        ],
    )
    write_csv(
        out / "gfx_of_culture_group.csv",
        ["ck2_graphical_culture", "coa_gfx", "building_gfx", "clothing_gfx", "unit_gfx", "review"],
        [[key, *value[:4], "no"] for key, value in sorted(REAL_WORLD_GFX.items())],
        [
            "CK2 `graphical_cultures` value -> the four independent CK3 gfx axes.",
            "Seeded by scripts/seed_culture_overrides.py; mappings/culture_fields.csv.",
            "Only the CK2 values with a real-world CK3 analogue are listed. Faerun uses 320",
            "distinct values; the ~280 fantasy ones (drowgfx, beholdergfx, ...) have no CK3",
            "counterpart and fall through to the western_* defaults. Add a row to override one.",
        ],
    )

    tenets = out / "faith_tenets.csv"
    if not tenets.is_file():
        write_csv(
            tenets,
            ["ck2_religion", "tenet_1", "tenet_2", "tenet_3", "note"],
            [],
            [
                "Per-faith override of the three CK3 core tenets.",
                "Empty file = every faith takes the default set decided in docs/DECISIONS.md",
                "(tenet_ritual_celebrations / tenet_sanctity_of_nature / tenet_ancestor_worship),",
                "except where a CK2 flag justifies a different one (docs/step_cultures_religions.md).",
                "One row per CK2 religion id; all three columns must be filled to take effect.",
            ],
        )
    defaults = out / "culture_defaults.csv"
    if not defaults.is_file():
        write_csv(
            defaults,
            ["ck2_culture", "ethos", "martial_custom", "head_determination", "note"],
            [],
            [
                "Per-culture override of the three CK3 pillar keys CK2 cannot supply.",
                "Empty file = every culture takes the derived value",
                "(docs/step_cultures_religions.md, table `Derived culture keys`).",
                "Blank cells fall back to the derived value, so a row may override just one.",
            ],
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
