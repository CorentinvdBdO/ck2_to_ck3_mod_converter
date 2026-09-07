#!/usr/bin/env python3
"""Generate `mappings/modifiers.csv` from the collected Faerun CK2 modifier keys.

Input : docs/evidence/ck2_modifier_keys.csv (from collect_ck2_modifier_keys.py)
Output: mappings/modifiers.csv  -- columns ck2_key,ck3_key,scale,note,status

The explicit table below is hand-derived (see docs/mapping_modifiers.md for the
evidence and the scale derivations). Dynamic CK2 opinion families
(`<culture_group>_opinion`, `<religion>_opinion`, `<trait>_opinion`,
`opinion_of_<trait>`) are resolved by looking the stem up in the Faerun
culture / religion / trait name sets, so new Faerun content is classified
automatically instead of needing a new table row.

The script fails if any collected key is left unmapped.
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

E, A, N = "exact", "approx", "none"

# ck2_key -> (ck3_key, scale, status, note)
TABLE: dict[str, tuple[str, str, str, str]] = {
    # ---------------- attributes ----------------
    "diplomacy":   ("diplomacy", "1", E, "same additive attribute point"),
    "martial":     ("martial", "1", E, "same additive attribute point"),
    "stewardship": ("stewardship", "1", E, "same additive attribute point"),
    "intrigue":    ("intrigue", "1", E, "same additive attribute point"),
    "learning":    ("learning", "1", E, "same additive attribute point"),
    "diplomacy_penalty":   ("diplomacy", "1", A, "CK2 splits attribute bonus and attribute penalty; CK3 has one additive key - sum both into it"),
    "martial_penalty":     ("martial", "1", A, "CK2 splits attribute bonus and attribute penalty; CK3 has one additive key - sum both into it"),
    "stewardship_penalty": ("stewardship", "1", A, "CK2 splits attribute bonus and attribute penalty; CK3 has one additive key - sum both into it"),
    "intrigue_penalty":    ("intrigue", "1", A, "CK2 splits attribute bonus and attribute penalty; CK3 has one additive key - sum both into it"),
    "learning_penalty":    ("learning", "1", A, "CK2 splits attribute bonus and attribute penalty; CK3 has one additive key - sum both into it"),

    # ---------------- prowess ----------------
    "combat_rating":        ("prowess", "0.1", A, "CK2 2.x rescaled combat_rating x10 (see 00_traits.txt:1728 '#old value: 1'); Faerun range [-100,60] vs CK3 trait prowess range [-10,8]"),
    "hidden_combat_rating": ("prowess_no_portrait", "0.1", A, "same 0.1 scale as combat_rating; CK3 prowess_no_portrait does not change the portrait"),

    # ---------------- health / fertility ----------------
    "health":         ("health", "1", E, "strong 1 -> physique_good_3 1 and weak -1 -> physique_bad_3 -1 both match exactly (CK2 00_traits.txt:1082,1101 vs CK3 00_traits.txt:7649,7507); only ill disagrees (CK2 -2 vs CK3 -1)"),
    "health_penalty": ("health", "1", A, "CK2 separate health-penalty channel (00_traits.txt:434 leper); fold into CK3 health. CK2 illness values run to -7, CK3 illness health stops at -1 - cap or use an override"),
    "fertility":         ("fertility", "1", E, "both are an additive fraction on base fertility; CK2 p90 0.2, CK3 p90 0.2"),
    "fertility_penalty": ("fertility", "1", A, "CK2 separate fertility-penalty channel; fold into CK3 fertility"),
    "disease_defence":   ("epidemic_resistance", "1", A, "CK2 fraction vs CK3 additive resistance points; check magnitude per trait"),

    # ---------------- currencies ----------------
    "monthly_character_prestige": ("monthly_prestige", "1", E, "same units; CK2 absmax 2.0, CK3 absmax 2.0"),
    "monthly_character_piety":    ("monthly_piety", "1", E, "same units; CK2 absmax 1.0, CK3 absmax 2.0"),
    "monthly_character_wealth":   ("monthly_income", "1", E, "flat monthly gold both sides"),
    "liege_prestige": ("monthly_prestige", "1", A, "building grants it to the liege; in CK3 put it in county_holder_character_modifier"),
    "liege_piety":    ("monthly_piety", "1", A, "building grants it to the liege; in CK3 put it in county_holder_character_modifier"),
    "monthly_grace":  ("", "", N, "offmap-power (China) currency; no CK3 equivalent - emit as comment"),

    # ---------------- realm / domain ----------------
    "demesne_size":       ("domain_limit", "1", E, "both are whole holdings; CK2 1..3, CK3 -1..3"),
    "court_size_modifier": ("court_grandeur_baseline_add", "1", A, "CK2 raises the courtier cap; CK3 has no cap, grandeur is the nearest construct"),
    "short_reign_length": ("short_reign_duration_mult", "1", A, "CK2 is months, CK3 is a fraction of the base duration - re-derive per value"),
    "retinuesize":        ("men_at_arms_limit", "1", A, "CK2 retinue cap -> CK3 men-at-arms regiment limit; units differ (troops vs regiments)"),
    "retinuesize_perc":   ("men_at_arms_limit", "1", A, "CK3 has no percentage MAA limit modifier; convert to an absolute men_at_arms_limit"),
    "knights":            ("knight_limit", "1", A, "CK2 building grants flat knight troops; CK3 knight_limit is a knight count"),
    "land_organisation":  ("", "", N, "CK2 levy organisation; no CK3 equivalent - emit as comment"),
    "moved_capital_months_mult": ("", "", N, "CK2 capital-move cooldown; no CK3 equivalent - emit as comment"),

    # ---------------- plots / schemes ----------------
    "plot_power_modifier":           ("owned_hostile_scheme_success_chance_add", "100", A, "CK2 fraction of plot power -> CK3 percentage points of scheme success"),
    "murder_plot_power_modifier":    ("owned_hostile_scheme_success_chance_add", "100", A, "CK3 has no murder-only success modifier; nearest is all hostile schemes"),
    "defensive_plot_power_modifier": ("enemy_hostile_scheme_success_chance_add", "-100", A, "CK2 raises defence, CK3 lowers the enemy's success chance - sign flips"),
    "assassinate_chance_modifier":   ("owned_hostile_scheme_success_chance_add", "100", A, "CK2 assassination plot chance -> CK3 hostile scheme success chance"),
    "plot_discovery_chance":         ("enemy_scheme_secrecy_add", "-100", A, "CK2 raises your chance to discover plots; CK3 lowers the plotter's secrecy - sign flips"),
    "arrest_chance_modifier":        ("", "", N, "CK2 arrest attempt chance; CK3 imprisonment has no chance roll - emit as comment"),

    # ---------------- culture / religion / tech ----------------
    "culture_flex":  ("cultural_acceptance_gain_mult", "1", A, "CK2 conversion flexibility -> CK3 cultural acceptance gain"),
    "religion_flex": ("", "", N, "CK2 willingness to change religion; CK3 has no equivalent - emit as comment"),
    "religious_enemy": ("", "", N, "CK2 flag modifier used by triggers, not a value; emit as comment"),
    "tech_growth_modifier": ("development_growth", "1", A, "CK2 per-province tech growth -> CK3 county development growth"),
    "economy_techpoints":   ("development_growth", "1", A, "CK2 economy tech points; CK3 has no per-category tech - use development growth"),
    "culture_techpoints":   ("development_growth", "1", A, "CK2 culture tech points; CK3 has no per-category tech - use development growth"),
    "military_techpoints":  ("development_growth", "1", A, "CK2 military tech points; CK3 has no per-category tech - use development growth"),

    # ---------------- holding economy ----------------
    "tax_income":          ("monthly_income", "1", E, "flat monthly gold; CK3 buildings put it in province_modifier (00_standard_military_buildings.txt:47)"),
    "global_tax_modifier": ("domain_tax_mult", "1", A, "CK2 realm-wide tax fraction -> CK3 domain tax multiplier"),
    "tradevalue":          ("monthly_income", "1", A, "CK2 trade-post value; CK3 has no trade zones - approximate with flat income"),
    "max_tradeposts":      ("", "", N, "CK2 republic trade posts; no CK3 equivalent - emit as comment"),
    "levy_size":           ("levy_size", "1", E, "both are a fraction of the holding levy; CK3 also has the flat building field `levy`"),
    "global_levy_size":    ("levy_size", "1", A, "CK2 realm-wide; CK3 levy_size is holding/county scope - apply per holding"),
    "levy_reinforce_rate": ("levy_reinforcement_rate", "1", E, "same fraction"),
    "army_reinforce_rate": ("levy_reinforcement_rate", "1", A, "CK2 raised-army reinforcement; CK3 only models levy reinforcement"),
    "garrison_size":       ("garrison_size", "1", E, "both are a fraction of the base garrison"),
    "fort_level":          ("fort_level", "1", E, "CK3 buildings use additional_fort_level in province_modifier (tgp_great_project_buildings.txt:524)"),
    "global_revolt_risk":  ("county_opinion_add", "-100", A, "CK2 revolt risk is a 0..1 fraction; CK3 models unrest as county opinion -100..100, sign flips"),
    "local_revolt_risk":   ("county_opinion_add", "-100", A, "same derivation as global_revolt_risk, applied to one county"),

    # ---------------- construction ----------------
    "build_cost_modifier":        ("holding_build_gold_cost", "1", E, "both are a cost fraction, negative = cheaper"),
    "build_time_modifier":        ("holding_build_speed", "1", E, "CK3 key is prefixed MOD_TIME_PREFIX with color=bad: negative = faster, same sign as CK2"),
    "build_cost_castle_modifier": ("castle_holding_build_gold_cost", "1", E, "CK3 has one key per holding type (00_holding_definitions.txt:8)"),
    "local_build_cost_modifier":  ("holding_build_gold_cost", "1", A, "CK2 province scope; put it in the CK3 building's province_modifier"),
    "local_build_time_modifier":  ("holding_build_speed", "1", A, "CK2 province scope; put it in the CK3 building's province_modifier"),
    "wonder_build_time_modifier": ("great_project_build_speed", "1", A, "CK2 wonders -> CK3 great projects"),
    "wonder_build_cost_modifier": ("", "", N, "CK3 great projects have a build-speed modifier but no cost modifier - emit as comment"),
    "convert_to_castle": ("", "", N, "CK2 tribal upgrade target; CK3 holdings are not converted by buildings - emit as comment"),
    "convert_to_city":   ("", "", N, "CK2 tribal upgrade target; CK3 holdings are not converted by buildings - emit as comment"),
    "ai_republic_modifier": ("", "", N, "CK2 AI build weight; CK3 uses the building's own ai_value block - emit as comment"),
    "ai_feudal_modifier":   ("", "", N, "CK2 AI build weight; CK3 uses the building's own ai_value block - emit as comment"),

    # ---------------- war: command_modifier ----------------
    "damage":         ("army_damage_mult", "1", A, "CK2 commander damage bonus -> CK3 army damage multiplier"),
    "defence":        ("army_toughness_mult", "1", A, "CK2 commander defence bonus -> CK3 army toughness multiplier"),
    "morale_offence": ("", "", N, "CK3 removed army morale - emit as comment"),
    "morale_defence": ("", "", N, "CK3 removed army morale - emit as comment"),
    "land_morale":    ("", "", N, "CK3 removed army morale - emit as comment"),
    "speed":          ("movement_speed", "1", A, "CK2 commander speed -> CK3 movement speed"),
    "siege":          ("siege_phase_time", "-1", A, "CK2 positive = faster siege; CK3 siege_phase_time lower = faster, so the sign flips"),
    "siege_speed":    ("siege_phase_time", "-1", A, "same inversion as `siege`"),
    "siege_defence":  ("defender_holding_advantage", "1", A, "CK2 fraction vs CK3 advantage points - re-derive magnitude"),
    "pursue":         ("army_pursuit_mult", "1", A, "CK2 pursue -> CK3 pursuit multiplier"),
    "retreat":        ("army_screen_mult", "1", A, "CK2 retreat -> CK3 screen multiplier (both cover a withdrawal)"),
    "flank":          ("", "", N, "CK3 battles have no flanks - emit as comment"),
    "narrow_flank":   ("", "", N, "CK3 battles have no flanks - emit as comment"),
    "center":         ("", "", N, "CK3 battles have no centre - emit as comment"),
    "terrain":        ("", "", N, "CK2 leader terrain list; in CK3 use trait_exclusive_if_realm_contains plus <terrain>_advantage - emit as comment"),
    "attrition":      ("", "", N, "CK3 has no character-scope attrition; only <terrain>_attrition_mult (province) and hostile_county_attrition - emit as comment"),
    "winter_combat":  ("winter_advantage", "1", A, "CK2 fraction vs CK3 advantage points - re-derive magnitude"),
    "winter_supply":        ("", "", N, "CK3 has no winter supply channel - emit as comment"),
    "global_winter_supply": ("", "", N, "CK3 has no winter supply channel - emit as comment"),
    "supply_limit":        ("supply_limit", "1", E, "same flat troop-count units"),
    "global_supply_limit": ("supply_limit_mult", "1", A, "CK2 realm-wide fraction -> CK3 supply limit multiplier"),
    "days_of_supply":      ("supply_duration", "1", A, "CK2 days -> CK3 supply duration (months) - divide by 30"),

    # ---------------- troop types ----------------
    "light_infantry":  ("skirmishers_damage_mult", "1", A, "in command_modifier a % bonus -> CK3 MAA damage; in a building a flat troop count -> no CK3 equivalent, emit as comment"),
    "actual_light_infantry": ("skirmishers_damage_mult", "1", A, "Faerun alias of light_infantry"),
    "heavy_infantry":  ("heavy_infantry_damage_mult", "1", A, "in command_modifier a % bonus -> CK3 MAA damage; in a building a flat troop count -> comment"),
    "archers":         ("archers_damage_mult", "1", A, "in command_modifier a % bonus -> CK3 MAA damage; in a building a flat troop count -> comment"),
    "pikemen":         ("pikemen_damage_mult", "1", A, "in command_modifier a % bonus -> CK3 MAA damage; in a building a flat troop count -> comment"),
    "light_cavalry":   ("light_cavalry_damage_mult", "1", A, "in command_modifier a % bonus -> CK3 MAA damage; in a building a flat troop count -> comment"),
    "cavalry":         ("heavy_cavalry_damage_mult", "1", A, "CK2 generic cavalry -> CK3 heavy cavalry"),
    "horse_archers":   ("archer_cavalry_damage_mult", "1", A, "CK2 horse archers -> CK3 archer cavalry"),
    "horse_archers_offensive": ("archer_cavalry_damage_mult", "1", A, "CK2 special-unit offensive -> CK3 damage"),
    "camel_cavalry":   ("camel_cavalry_damage_mult", "1", A, "same unit exists in CK3"),
    "war_elephants":   ("elephant_cavalry_damage_mult", "1", A, "CK2 war elephants -> CK3 elephant cavalry"),
    "galleys":         ("", "", N, "CK3 has no navy - emit as comment"),
    "gunpowder_troops":           ("gunpowder_damage_mult", "1", A, "CK3 gunpowder MAA category (MPO)"),
    "gunpowder_troops_offensive": ("gunpowder_damage_mult", "1", A, "CK2 special-unit offensive -> CK3 damage"),
    "gunpowder_troops_morale":    ("", "", N, "CK3 removed army morale - emit as comment"),
    "giant_troops":           ("", "", N, "Faerun special unit; needs a new CK3 men_at_arms_type - emit as comment"),
    "giant_troops_offensive": ("", "", N, "Faerun special unit; needs a new CK3 men_at_arms_type - emit as comment"),
    "giant_troops_defensive": ("", "", N, "Faerun special unit; needs a new CK3 men_at_arms_type - emit as comment"),
    "mob_troops":     ("", "", N, "Faerun special unit; needs a new CK3 men_at_arms_type - emit as comment"),
    "undead_troops":  ("", "", N, "Faerun special unit; needs a new CK3 men_at_arms_type - emit as comment"),
    "scouting":       ("", "", N, "Faerun custom flag modifier read by events; emit as comment"),

    # ---------------- opinions with a fixed CK3 key ----------------
    "same_opinion":                  ("same_opinion", "1", E, "CK3 trait field (_traits.info:143); CK2 p90 15, CK3 p90 20"),
    "same_opinion_if_same_religion": ("same_opinion_if_same_faith", "1", E, "CK3 trait field (_traits.info:145)"),
    "opposite_opinion":              ("opposite_opinion", "1", E, "CK3 trait field (_traits.info:147)"),
    "sex_appeal_opinion":            ("attraction_opinion", "1", E, "scale 1 verified on three trait pairs: fair 30 -> beauty_good_3 30, ugly -20 -> beauty_bad_2 -20, weak -10 -> physique_bad_3 -10"),
    "vassal_opinion":                ("vassal_opinion", "1", E, "same key and range on both sides"),
    "liege_opinion":                 ("liege_opinion", "1", E, "both mean 'my liege's opinion of me'; CK3 opinion_of_liege is the reverse direction"),
    "general_opinion":               ("general_opinion", "1", E, "same key and range"),
    "same_religion_opinion":         ("same_faith_opinion", "1", E, "CK2 religion -> CK3 faith"),
    "infidel_opinion":               ("different_faith_opinion", "1", E, "CK2 infidel -> CK3 different faith"),
    "church_opinion":                ("clergy_opinion", "1", A, "CK2 church_opinion is the realm clergy's opinion -> CK3 clergy_opinion"),
    "dynasty_opinion":               ("dynasty_opinion", "1", E, "same key and range"),
    "spouse_opinion":                ("spouse_opinion", "1", E, "same key and range"),
    "twin_opinion":                  ("twin_opinion", "1", E, "same key and range"),
    "tribal_opinion":                ("tribal_government_opinion", "1", A, "CK2 tribal vassals -> CK3 tribal-government vassals"),
    "rel_head_opinion":              ("religious_head_opinion", "1", E, "same concept and range"),
    "christian_church_opinion":      ("clergy_opinion", "1", A, "CK2 religion-specific church opinion -> CK3 clergy_opinion; gate it with faith_modifier if it must stay faith-specific"),
    "unreformed_tribal_opinion":     ("tribal_government_opinion", "1", A, "CK2 unreformed-pagan tribal vassals -> CK3 tribal-government vassals"),
    "ambition_opinion":              ("", "", N, "CK2 ambition-target opinion; no CK3 equivalent - emit as comment"),
}

# CK2 dynamic-family fallbacks, resolved against the Faerun name sets.
FAMILY_TRAIT = ("", "", N,
                "CK2 <trait>_opinion / opinion_of_<trait>: CK3 has no per-trait opinion modifier - "
                "emit as a `compatibility = { <trait> = X }` entry in the trait block (_traits.info:160) and a comment")
FAMILY_CULTURE = ("<ck3_culture>_opinion", "1", A,
                  "CK2 <culture|culture_group>_opinion; CK3 supports <culture>_opinion only (no culture-group scope) and the key "
                  "must be declared in common/modifier_definition_formats/ - needs the culture map from the cultures lane")
FAMILY_FAITH = ("<ck3_faith>_opinion", "1", A,
                "CK2 <religion>_opinion -> CK3 <faith>_opinion; the key must be declared in "
                "common/modifier_definition_formats/ (00_religion_definitions.txt) - needs the faith map from the religions lane")
FAMILY_RELIGION_GROUP = ("<ck3_religion>_religion_opinion", "1", A,
                         "CK2 <religion_group>_opinion -> CK3 <religion>_religion_opinion (00_religion_definitions.txt:1); "
                         "must be declared in common/modifier_definition_formats/")
FAMILY_TEXT = ("", "", N,
               "CK2 custom text modifier declared in common/modifier_definitions/ (display only, read back by triggers); "
               "CK3 has no display-only modifier - emit as comment")


def name_sets(faerun: Path) -> dict[str, set[str]]:
    skip = {
        "graphical_cultures", "male_names", "female_names", "pat_grf_name_chance",
        "mat_grf_name_chance", "father_name_chance", "from_dynasty_prefix",
        "dynasty_title_names", "founder_named_dynasties", "bastard_dynasty_prefix",
        "modifier", "character_modifier", "color", "dynasty_name_first",
        "used_for_random", "alternate_start", "pagan_roots", "crusade_cb",
        "allow_looting", "seafarer", "horde", "baron_titles_hidden",
        "count_titles_hidden", "disinherit_from_blinding", "castes",
        "male_patronym", "female_patronym", "prefix", "dukes_called_kings",
    }

    def groups(files):
        gs, ms = set(), set()
        for f in files:
            t = f.read_bytes().decode("cp1252", errors="replace")
            for p, k, v in walk(tokenize(t)):
                if v is not None:
                    continue
                if len(p) == 0:
                    gs.add(k)
                elif len(p) == 1 and k not in skip:
                    ms.add(k)
        return gs, ms

    cg, cu = groups(sorted((faerun / "common" / "cultures").glob("*.txt")))
    rg, rl = groups(sorted((faerun / "common" / "religions").glob("*.txt")))
    traits = set()
    for f in sorted((faerun / "common" / "traits").glob("*.txt")):
        t = f.read_bytes().decode("cp1252", errors="replace")
        traits |= {k for p, k, v in walk(tokenize(t)) if len(p) == 0 and v is None}
    return {"culture_groups": cg, "cultures": cu,
            "religion_groups": rg, "religions": rl, "traits": traits}


def resolve(key: str, sets: dict[str, set[str]]) -> tuple[str, str, str, str] | None:
    if key in TABLE:
        return TABLE[key]
    if key.startswith(("text_effect_", "trait_effect_", "tolerates_")):
        return FAMILY_TEXT
    if key.startswith("opinion_of_"):
        return FAMILY_TRAIT
    if key.endswith("_opinion"):
        stem = key[: -len("_opinion")]
        if stem in sets["traits"]:
            return FAMILY_TRAIT
        if stem in sets["religion_groups"]:
            return FAMILY_RELIGION_GROUP
        if stem in sets["religions"]:
            return FAMILY_FAITH
        if stem in sets["culture_groups"] or stem in sets["cultures"]:
            return FAMILY_CULTURE
        # Faerun declares some pantheon/cult opinion keys in modifier_definitions
        # without a matching culture/religion object of the same name.
        return FAMILY_FAITH
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keys", type=Path, default=REPO / "docs" / "evidence" / "ck2_modifier_keys.csv")
    ap.add_argument("--faerun", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=REPO / "mappings" / "modifiers.csv")
    args = ap.parse_args()
    if args.faerun is None:
        args.faerun = default_faerun()

    sets = name_sets(args.faerun)
    with args.keys.open(encoding="utf-8") as fh:
        keys = [r["ck2_key"] for r in csv.DictReader(fh)]

    rows, missing = [], []
    for k in sorted(keys):
        got = resolve(k, sets)
        if got is None:
            missing.append(k)
            continue
        ck3, scale, status, note = got
        rows.append([k, ck3, scale, note, status])
    if missing:
        raise SystemExit(f"unmapped CK2 modifier keys ({len(missing)}): {missing}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["ck2_key", "ck3_key", "scale", "note", "status"])
        w.writerows(rows)
    from collections import Counter
    c = Counter(r[4] for r in rows)
    print(f"{len(rows)} rows -> {args.out}; " + ", ".join(f"{k}={v}" for k, v in sorted(c.items())))


if __name__ == "__main__":
    main()
