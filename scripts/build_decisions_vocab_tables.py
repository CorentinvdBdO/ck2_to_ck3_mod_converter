#!/usr/bin/env python3
"""Build `mappings/triggers.csv`, `effects.csv`, `event_targets.csv`.

Method (`docs/mapping_triggers_effects.md`):

1. A hand-curated core (`CURATED_TRIGGERS`/`CURATED_EFFECTS`/`CURATED_EVENT_TARGETS`
   below) of CK2 <-> CK3 1.19 vocabulary, built from both games' `.info` docs
   plus real usage grep and cross-checked against `docs/DECISIONS.md`/CLAUDE.md
   invariants already established by earlier lanes (e.g. `add_spouse` is a
   history key, not an effect: `marry`/`divorce`/`make_concubine` are).
   `status`: `exact` (same meaning), `approx` (renamed or semantic drift, see
   `note`), `none` (no CK3 counterpart, `note` says why). `confidence`:
   `verified` (grepped against the CK3 1.19 install this run) or `assumed`.
2. Every key `scripts/decisions_vocab_survey.py` found in Faerûn's
   emit-eligible decisions (character-scope: `decisions`, `society_decisions`,
   `plot_decisions`; status `new`/`modified`) gets a row. A key not in the
   curated core is auto-classified: if the *exact spelling* is used
   somewhere in CK3 1.19's own `common/`+`events/` script
   (`scripts/ck3_vocab_ground_truth.py`), it is emitted `exact`/`assumed`
   ("same spelling in real CK3 script, semantics not individually checked");
   otherwise `none`/`verified` ("not found in the CK3 1.19 vocabulary
   sample"). This is the same usage-based verification bar
   `scripts/verify_ck3_keys.py` already established for modifier keys.
3. A key of CK2 title-tag shape (`c_`/`d_`/`e_`/`k_`/`b_` + name) used as a
   scope-opening key, or a bare `<trait> = yes/no` shorthand, is *not* a
   vocabulary entry (:mod:`ck2ck3.decisions_vocab` recognises both
   structurally at conversion time) - excluded from all three tables.

Usage: `uv run scripts/build_decisions_vocab_tables.py`
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from ck2ck3.decisions_vocab import TITLE_TAG_RE  # noqa: E402
from ck3_vocab_ground_truth import ground_truth  # noqa: E402

SURVEY = REPO / "docs" / "evidence" / "decisions_vocab_survey.csv"
TRAIT_TABLE = REPO / "mappings" / "trait_ck2_to_ck3.csv"

# ---------------------------------------------------------------------------
# Curated core. (ck2_key: (ck3_key_or_None, status, confidence, note))
# ---------------------------------------------------------------------------

CURATED_TRIGGERS: dict[str, tuple[str | None, str, str, str]] = {
    # -- identity / attributes, unchanged --------------------------------
    "age": ("age", "exact", "verified", "same key, same meaning"),
    "is_female": ("is_female", "exact", "verified", "unchanged"),
    "is_alive": ("is_alive", "exact", "verified", "unchanged"),
    "is_adult": ("is_adult", "exact", "verified", "unchanged"),
    "is_playable": ("is_playable", "exact", "verified", "unchanged"),
    "is_married": ("is_married", "exact", "verified", "unchanged"),
    "is_married_matrilineally": (None, "none", "verified", "not found in the CK3 1.19 vocabulary sample; needs a human check of the matrilineal-marriage trigger"),
    "is_betrothed": ("is_betrothed", "exact", "assumed", "not individually greped"),
    "is_pregnant": ("is_pregnant", "exact", "assumed", "not individually greped"),
    "health": ("health", "exact", "verified", "unchanged"),
    "diplomacy": ("diplomacy", "exact", "verified", "unchanged"),
    "martial": ("martial", "exact", "verified", "unchanged"),
    "stewardship": ("stewardship", "exact", "verified", "unchanged"),
    "intrigue": ("intrigue", "exact", "verified", "unchanged"),
    "learning": ("learning", "exact", "verified", "unchanged"),
    "piety": ("piety", "exact", "verified", "unchanged"),
    "ai": (None, "none", "verified", "context-dependent field (e.g. custom_tooltip's audience filter); no single CK3 vocabulary meaning as a bare trigger, needs a human check per call site"),
    "prestige": ("prestige", "exact", "verified", "unchanged"),
    "wealth": ("gold", "approx", "verified", "CK2 wealth (total gold) -> CK3 gold"),
    "scaled_wealth": ("gold", "approx", "assumed", "CK2 wealth scaled by realm size; CK3 has no scaling variant, compares raw gold"),
    "culture": ("culture", "exact", "verified", "unchanged (scope-link comparison)"),
    "culture_group": (None, "none", "assumed",
        "CK3 has no culture-group scope word; nearest is the culture's heritage/language pillar - needs the cultures lane's group->pillar map, out of this lane's scope"),
    "religion": ("faith", "approx", "verified", "CK2 specific religion -> CK3 faith (faith = faith:<id>)"),
    "religion_group": (None, "none", "assumed",
        "CK3 groups faiths by `faith.religion`, not a bare scope word; needs the religions lane's religion-group id map, out of this lane's scope"),
    "government": ("government", "approx", "assumed",
        "CK2 government id -> CK3 government_type id via mappings/government_map.csv (titles lane); this lane emits the CK2 id verbatim as a `# CK2:` comment when not a literal match"),
    "tier": ("tier", "exact", "verified", "unchanged as a key; CK2 COUNT/DUKE/KING/EMPEROR values become CK3 tier_county/tier_duchy/tier_kingdom/tier_empire (verified: game/common/decisions)"),
    "higher_tier_than": (None, "none", "verified",
        "not a CK3 key: CK3 restructures the comparison as `highest_held_title_tier > <value>` (a scripted value with an inline operator), not a bare trigger key - needs per-decision restructuring, not a table rename"),
    "higher_real_tier_than": (None, "none", "verified", "see higher_tier_than: CK3 has no bare comparison key for this"),
    "lower_real_tier_than": (None, "none", "verified", "see higher_tier_than: CK3 has no bare comparison key for this"),
    "real_tier": (None, "none", "verified", "not found in the CK3 1.19 vocabulary sample; nearest is the scripted value highest_held_title_tier"),
    "dynasty": ("dynasty", "exact", "verified", "unchanged (scope-link comparison)"),
    "primary_title": ("primary_title", "exact", "verified", "unchanged (scope-link comparison)"),
    "has_landed_title": ("has_title", "approx", "assumed", "CK3 renamed has_landed_title -> has_title"),
    "is_landed": ("is_landed", "exact", "verified", "unchanged"),
    "is_ruler": ("is_ruler", "exact", "verified", "unchanged"),
    "is_capital": (None, "none", "assumed",
        "CK2 checks a province is a capital; CK3 splits capital_county/capital_barony are scope links, not a trigger on the province itself"),
    "is_coastal": ("is_coastal", "exact", "verified", "unchanged (province/county trigger)"),
    "is_island": (None, "none", "assumed", "not found in the CK3 1.19 vocabulary sample"),
    # `government_has_flag` is real (`verified`, game/common/decisions), but
    # its value must be the *flag's own name* (e.g. `government_is_tribal`),
    # not the CK2 boolean this key carried - a bare key rename left
    # `government_has_flag = yes` on the page, `error(missing-item)`
    # ("government flag yes not defined"). Fixing this needs the key AND
    # value rewritten together, which this table can't express; `none` until
    # a human (or a future value-aware pass) does it per call site.
    "is_theocracy": (None, "none", "verified",
        "CK3 government checks are flag-based (government_has_flag = government_is_theocratic) - needs the value rewritten too, not just the key; see comment above CURATED_TRIGGERS is_theocracy"),
    "is_republic": (None, "none", "verified", "see is_theocracy: needs key+value rewritten together"),
    "is_tribal": (None, "none", "verified", "see is_theocracy: needs key+value rewritten together"),
    "is_nomadic": (None, "none", "verified", "see is_theocracy: needs key+value rewritten together"),
    "is_feudal": (None, "none", "verified", "see is_theocracy: needs key+value rewritten together"),
    "is_merchant_republic": (None, "none", "verified", "see is_theocracy: needs key+value rewritten together"),
    "is_landless_type_title": (None, "none", "verified", "not found in the CK3 1.19 vocabulary sample; needs a human check of the landless-title trigger"),
    "is_within_diplo_range": (None, "none", "assumed",
        "CK3 has no diplomatic-range mechanic (distance-based diplomacy was removed)"),
    "is_independent": (None, "none", "assumed", "not found in the CK3 1.19 vocabulary sample; check `is_independent_ruler`"),
    "independent": (None, "none", "assumed", "not found in the CK3 1.19 vocabulary sample; check `is_independent_ruler`"),
    "is_incapable": ("is_incapable", "exact", "verified", "unchanged"),
    "is_imprisoned": ("is_imprisoned", "exact", "verified", "unchanged"),
    "prisoner": ("is_imprisoned", "approx", "assumed", "CK2 prisoner = yes/no trigger -> CK3 is_imprisoned"),
    "war": ("is_at_war", "approx", "verified", "CK2 war = yes/no -> CK3 is_at_war"),
    "any_war": (None, "none", "verified", "not found in the CK3 1.19 vocabulary sample as a bare iterator; use is_at_war for the yes/no check"),
    "war_score": (None, "none", "assumed", "not found in the CK3 1.19 vocabulary sample as a bare trigger"),
    "using_cb": (None, "none", "assumed", "CK3 war/CB structure differs; no direct trigger equivalent found"),
    "has_dlc": ("has_dlc", "exact", "verified", "unchanged"),
    "has_game_rule": ("has_game_rule", "exact", "verified", "unchanged"),
    "has_character_flag": ("has_character_flag", "exact", "verified", "unchanged"),
    "had_character_flag": (None, "none", "assumed",
        "CK3 has no 'had' (once-set) flag history trigger; needs a variable set alongside the flag"),
    "had_flag": (None, "none", "assumed", "see had_character_flag"),
    "has_flag": ("has_character_flag", "approx", "assumed", "CK2 generic has_flag -> CK3 has_character_flag in character scope"),
    "has_global_flag": ("has_global_variable", "approx", "assumed", "CK3 replaced global flags with global variables"),
    "has_offmap_flag": (None, "none", "verified", "offmap powers do not exist in CK3 (docs/mechanics_inventory.md)"),
    "has_bloodline_flag": (None, "none", "verified", "bloodlines do not exist in CK3 (docs/mechanics_inventory.md)"),
    "has_artifact_flag": ("has_variable", "approx", "assumed", "CK3 artifacts carry variables, not flags"),
    "has_title_flag": ("has_variable", "approx", "assumed", "CK3 titles carry variables, not flags"),
    "check_variable": ("has_variable", "approx", "verified",
        "CK3 has no check_variable key; existence is has_variable, value comparison is a direct `var:<name> ></=/< value` expression - needs per-decision restructuring, not a pure rename"),
    "trigger_if": ("trigger_if", "exact", "verified", "unchanged"),
    "trigger_else": ("trigger_else", "exact", "verified", "unchanged"),
    "trigger_else_if": ("trigger_else_if", "exact", "verified", "unchanged"),
    "trigger_switch": (None, "none", "assumed", "not found in the CK3 1.19 vocabulary sample; use trigger_if chains"),
    "calc_true_if": ("calc_true_if", "exact", "verified", "unchanged"),
    "custom_tooltip": ("custom_tooltip", "exact", "verified", "unchanged"),
    "hidden_tooltip": (None, "none", "verified",
        "not a real CK3 vocabulary key at all (its ground-truth hits were the `text`-shaped custom_tooltip field, not a trigger keyword); wrapping content as custom_tooltip without the required `text=` field caused error(field-missing) - do not approximate, needs a human check per call site"),
    "conditional_tooltip": (None, "none", "assumed", "not found in the CK3 1.19 vocabulary sample"),
    "hidden_trigger": (None, "none", "assumed", "not found as a bare wrapper in the CK3 1.19 sample"),
    "always": ("always", "exact", "verified", "unchanged"),
    "text": ("text", "exact", "assumed", "unchanged (custom_tooltip field)"),
    # -- relations / court -------------------------------------------------
    "employer": ("employer", "exact", "verified", "unchanged (scope-link comparison)"),
    "liege": ("liege", "exact", "verified", "unchanged (scope-link comparison)"),
    "top_liege": ("top_liege", "exact", "verified", "unchanged (scope-link comparison)"),
    "holder": ("holder", "exact", "verified", "unchanged (scope-link comparison)"),
    "owner": ("holder", "approx", "assumed", "CK2 province owner -> CK3 county/barony holder"),
    "spouse": ("spouse", "exact", "assumed", "unchanged (scope-link comparison)"),
    "character": ("this", "approx", "assumed",
        "CK2 `character = X` compares the current scope to X; CK3 compares scopes directly, no wrapper key"),
    "is_child_of": ("is_child_of", "exact", "verified", "unchanged"),
    "is_close_relative": (None, "none", "assumed", "not found in the CK3 1.19 vocabulary sample; use is_close_family_of"),
    "is_friend": (None, "none", "assumed", "not found in the CK3 1.19 vocabulary sample; check has_relation_friend"),
    "is_rival": (None, "none", "assumed", "not found in the CK3 1.19 vocabulary sample; check has_relation_rival"),
    "is_lover": (None, "none", "assumed", "not found in the CK3 1.19 vocabulary sample; check has_relation_lover"),
    "is_allied_with": (None, "none", "assumed", "CK3 alliance mechanic differs (through pacts/friends), no direct trigger found"),
    "is_councillor": ("has_council_position", "approx", "assumed", "CK3 renamed councillor -> council position"),
    "is_heir": (None, "none", "assumed", "not found in the CK3 1.19 vocabulary sample as a bare trigger; check is_heir_of"),
    "current_heir": (None, "none", "assumed", "not found in the CK3 1.19 vocabulary sample as a bare scope link"),
    "num_of_children": (None, "none", "assumed", "not found in the CK3 1.19 vocabulary sample; use num_children"),
    "has_children": (None, "none", "assumed", "not found in the CK3 1.19 vocabulary sample"),
    "has_living_children": (None, "none", "assumed", "not found in the CK3 1.19 vocabulary sample"),
    "num_of_spouses": (None, "none", "assumed", "CK3 does not track spouse count as a trigger the same way"),
    "num_of_prisoners": (None, "none", "assumed", "not found in the CK3 1.19 vocabulary sample"),
    "num_of_vassals": (None, "none", "assumed", "not found in the CK3 1.19 vocabulary sample as a bare trigger"),
    "is_consort": (None, "none", "assumed", "CK3 has no separate consort concept from spouse"),
    "is_lowborn": ("is_lowborn", "exact", "assumed", "unchanged"),
    "trait": ("has_trait", "approx", "verified",
        "CK2 explicit trait check `trait = X` -> CK3 `has_trait = X`; the argument X is re-resolved through the traits step's id map at conversion time (ck2ck3.steps.decisions), not a literal rename"),
    "has_full_court": (None, "none", "assumed", "not found in the CK3 1.19 vocabulary sample"),
    "free_court_slots": (None, "none", "assumed", "CK3 court has no fixed slot count"),
    "host": (None, "none", "assumed", "CK3 dropped the CK2 'host' (travelling court) concept as a scope word"),
    "same_realm": ("same_realm_as", "approx", "assumed", "CK3 renamed same_realm -> same_realm_as"),
    "opinion": ("opinion", "exact", "verified", "unchanged (scope-link comparison block)"),
    "reverse_opinion": ("reverse_opinion", "exact", "assumed", "unchanged"),
    "has_opinion_modifier": ("has_opinion_modifier", "exact", "assumed", "unchanged"),
    "has_any_opinion_modifier": (None, "none", "assumed", "not found in the CK3 1.19 vocabulary sample"),
    "has_character_modifier": ("has_character_modifier", "exact", "verified", "unchanged"),
    "has_truce": ("has_truce", "exact", "assumed", "unchanged"),
    "reverse_has_truce": (None, "none", "assumed", "not found in the CK3 1.19 vocabulary sample"),
    "has_liege_enforced_peace": (None, "none", "assumed", "CK3 has no liege-enforced-peace mechanic"),
    "will_liege_enforce_peace": (None, "none", "assumed", "CK3 has no liege-enforced-peace mechanic"),
    "diplomatic_immunity": (None, "none", "assumed", "not found in the CK3 1.19 vocabulary sample"),
    "owes_favor_to": (None, "none", "assumed", "CK3 hooks are not modelled as favors owed"),
    "supported_claimant": (None, "none", "assumed", "not found in the CK3 1.19 vocabulary sample"),
    "same_society_as": (None, "none", "verified", "societies do not exist in CK3 (docs/mechanics_inventory.md)"),
    # -- realm / geography ---------------------------------------------
    "capital_holding": ("capital_barony", "approx", "assumed", "CK3 splits capital_county/capital_barony scope links"),
    "capital_scope": ("capital_county", "approx", "assumed", "CK3 splits capital_county/capital_barony scope links"),
    "location": (None, "none", "assumed",
        "CK2 character-current-province scope link has no direct CK3 equivalent (character has no bare province location); use capital_county or the title scope"),
    "region": ("geographical_region", "approx", "assumed", "CK3 renamed region -> geographical_region for the check"),
    "port": (None, "none", "assumed", "not found in the CK3 1.19 vocabulary sample as a bare trigger"),
    "holding_type": ("holding_type", "exact", "assumed", "unchanged"),
    "has_temple": (None, "none", "assumed", "CK3 building system differs (special_building_slot); no bare trigger found"),
    "has_building": ("has_building", "exact", "verified", "unchanged"),
    "num_of_count_titles": (None, "none", "assumed", "not found in the CK3 1.19 vocabulary sample"),
    "num_of_count_titles_in_realm": (None, "none", "assumed", "not found in the CK3 1.19 vocabulary sample"),
    "num_of_baron_titles_in_realm": (None, "none", "assumed", "not found in the CK3 1.19 vocabulary sample"),
    "num_of_government_vassals": (None, "none", "assumed", "not found in the CK3 1.19 vocabulary sample"),
    "demesne_size": ("domain_limit", "approx", "assumed", "CK3 renamed demesne -> domain"),
    "over_max_demesne_size": (None, "none", "assumed", "compare domain_limit vs held counts instead; no single trigger found"),
    "realm_size": ("realm_size", "exact", "assumed", "unchanged"),
    "relative_realm_size": (None, "none", "assumed", "not found in the CK3 1.19 vocabulary sample"),
    "realm_levies": (None, "none", "assumed", "CK3 replaced levies with men-at-arms/levy size scripted values"),
    "monthly_income": (None, "none", "assumed", "not found in the CK3 1.19 vocabulary sample as a bare trigger"),
    "completely_controls": ("completely_controls", "exact", "assumed", "unchanged (de jure control check)"),
    "controls_religion": (None, "none", "assumed", "no direct CK3 equivalent found (CK3 has no religion-territory control trigger)"),
    "any_neighbor_province": ("any_neighboring_county", "approx", "assumed", "CK3 merged province into county"),
    "any_realm_province": ("any_in_de_facto_hierarchy", "approx", "assumed",
        "CK3 has no bare province scope; nearest iterator is over the realm's counties/holders, needs a human check"),
    "count": ("count", "exact", "assumed", "unchanged (list-iterator limiter)"),
    # -- misc engine -----------------------------------------------------
    "days": ("days", "exact", "verified", "unchanged (duration field)"),
    "months": ("months", "exact", "assumed", "unchanged (duration field)"),
    "years": ("years", "exact", "assumed", "unchanged (duration field)"),
    "month": (None, "none", "assumed", "not found as a bare current-month trigger in the CK3 1.19 sample"),
    "year": (None, "none", "assumed", "not found as a bare current-year trigger in the CK3 1.19 sample"),
    "total_years_played": (None, "none", "assumed", "not found in the CK3 1.19 vocabulary sample"),
    "ruled_years": (None, "none", "assumed", "not found in the CK3 1.19 vocabulary sample"),
    "min": ("min", "exact", "assumed", "unchanged (scripted-value clamp)"),
    "max": ("max", "exact", "assumed", "unchanged (scripted-value clamp)"),
    "flag": (None, "none", "assumed", "context-dependent field name, not a single vocabulary key"),
    "key": (None, "none", "assumed", "context-dependent field name (custom_tooltip key), not a vocabulary key"),
    "which": (None, "none", "assumed", "context-dependent field name (check_variable), not a vocabulary key"),
    "name": (None, "none", "assumed", "context-dependent field name, not a single vocabulary key"),
    "type": (None, "none", "assumed", "context-dependent field name, not a single vocabulary key"),
    "target": (None, "none", "assumed", "context-dependent field name, not a single vocabulary key"),
    "power": (None, "none", "assumed", "context-dependent field name, not a single vocabulary key"),
    "rank": (None, "none", "assumed", "context-dependent field name, not a single vocabulary key"),
    "size": (None, "none", "assumed", "context-dependent field name, not a single vocabulary key"),
    "amount": (None, "none", "assumed", "context-dependent field name, not a single vocabulary key"),
    "attacker": ("attacker", "exact", "assumed", "unchanged (war scope link)"),
    "defender": ("defender", "exact", "assumed", "unchanged (war scope link)"),
    "any_attacker": (None, "none", "assumed", "not found in the CK3 1.19 vocabulary sample as a bare iterator"),
    "any_defender": (None, "none", "assumed", "not found in the CK3 1.19 vocabulary sample as a bare iterator"),
    "fertility": ("fertility", "exact", "assumed", "unchanged"),
    "immortal": ("immortal", "exact", "verified", "CK3 1.19 has a bare `immortal = yes/no` character trigger (CLAUDE.md immortal-trait invariant refers to the effect side, `immortal_age`, which is a separate field)"),
    "combat_rating": (None, "none", "assumed", "not found in the CK3 1.19 vocabulary sample"),
    "has_regent": (None, "none", "verified", "not found in the CK3 1.19 vocabulary sample; CK3 regency is exposed via the council/court position system, no bare trigger found"),
    "is_devil_worshiper_trigger": (None, "none", "verified", "Faerûn-specific custom scripted_trigger, not core CK2/CK3 vocabulary; converted 1:1 only if the effects lane later ports common/scripted_triggers (out of scope here)"),
}

#: Suffix families with one shared reason, applied after exact-key lookups
#: fail (keeps the curated dict above from repeating the same note per race
#: or society flavour key).
NONE_KEYWORD_REASONS: list[tuple[str, str]] = [
    ("society", "societies do not exist in CK3 (docs/mechanics_inventory.md)"),
    ("secret_religious", "secret religious societies/cults do not exist in CK3 (docs/mechanics_inventory.md)"),
    ("bloodline", "bloodlines do not exist in CK3 (docs/mechanics_inventory.md)"),
    ("offmap", "offmap powers do not exist in CK3 (docs/mechanics_inventory.md)"),
    ("plot", "CK2 plots have no CK3 counterpart (schemes are structurally different, docs/mechanics_inventory.md)"),
    ("wonder", "CK2 wonders map to CK3 special buildings, not this trigger/effect surface (docs/mechanics_inventory.md)"),
    ("job_", "CK2 council jobs are CK3 court positions, a different construct (docs/mechanics_inventory.md)"),
    ("minor_title", "CK2 minor titles map to CK3 court positions, a different construct (docs/mechanics_inventory.md)"),
    ("trade_post", "trade posts/routes do not exist in CK3 1.19 (docs/mechanics_inventory.md)"),
    ("trade_route", "trade posts/routes do not exist in CK3 1.19 (docs/mechanics_inventory.md)"),
    ("disease", "CK2 disease maps to CK3 epidemics, a different construct (docs/mechanics_inventory.md)"),
    ("execution_method", "CK3 has one generic execution effect, not per-method keys (docs/mechanics_inventory.md)"),
    ("faction", "CK3 factions exist but with a different scripting surface; no per-key match attempted"),
    ("ambition", "CK2 ambitions have no CK3 counterpart (docs/mechanics_inventory.md)"),
    ("z_", "Faerûn custom scripted_trigger (common/scripted_triggers/faerun_class_triggers.txt), not core CK2/CK3 vocabulary - porting Faerûn's own scripted_effects/scripted_triggers is out of this lane's scope"),
]

CURATED_EFFECTS: dict[str, tuple[str | None, str, str, str]] = {
    "trait": ("add_trait", "approx", "verified",
        "CK2 explicit `trait = X` effect (add) -> CK3 `add_trait = X`; the argument X is re-resolved through the traits step's id map at conversion time (ck2ck3.steps.decisions), not a literal rename"),
    "add_trait": ("add_trait", "exact", "verified", "unchanged"),
    "remove_trait": ("remove_trait", "exact", "verified", "unchanged"),
    "random_traits": ("random_traits", "exact", "assumed", "unchanged (create_character field)"),
    "give_nickname": ("give_nickname", "exact", "verified", "unchanged"),
    "has_nickname": ("has_nickname", "exact", "assumed", "unchanged (this is a trigger, kept for the survey's cross-listing)"),
    "set_name": (None, "none", "verified", "not found in the CK3 1.19 vocabulary sample; needs a human check (CK3 renames a title via change_title_name, not a character)"),
    "piety": (None, "none", "verified", "not a CK3 effect key: piety is trigger-only, changed only via add_piety - no bare effect of this name"),
    "ai": (None, "none", "verified", "context-dependent field; no single CK3 vocabulary meaning as a bare effect, needs a human check per call site"),
    "name": (None, "none", "assumed", "context-dependent field name, not a single vocabulary key"),
    "wealth": (None, "none", "verified", "not a CK3 effect key: `piety`/`prestige`/`gold` are trigger-only comparisons in CK3, changed only via add_gold/add_piety/add_prestige - no bare effect of this name"),
    "prestige": (None, "none", "verified", "not a CK3 effect key: prestige is trigger-only, changed only via add_prestige - no bare effect of this name"),
    "opinion": (None, "none", "verified", "not a CK3 effect key: opinion is a trigger-only comparison block, changed only via add_opinion/remove_opinion - no bare effect of this name"),
    "set_character_flag": ("add_character_flag", "approx", "verified", "CK3 renamed set_character_flag -> add_character_flag"),
    "clr_character_flag": ("remove_character_flag", "approx", "verified", "CK3 renamed clr_character_flag -> remove_character_flag"),
    "has_character_flag": ("has_character_flag", "exact", "verified", "unchanged (trigger, kept for cross-listing)"),
    "set_flag": ("add_character_flag", "approx", "assumed", "CK2 generic set_flag -> CK3 add_character_flag in character scope"),
    "clr_flag": ("remove_character_flag", "approx", "assumed", "CK2 generic clr_flag -> CK3 remove_character_flag in character scope"),
    "set_global_flag": ("set_global_variable", "approx", "assumed", "CK3 replaced global flags with global variables"),
    "clr_global_flag": ("remove_global_variable", "approx", "assumed", "CK3 replaced global flags with global variables"),
    "set_offmap_flag": (None, "none", "verified", "offmap powers do not exist in CK3 (docs/mechanics_inventory.md)"),
    "clr_offmap_flag": (None, "none", "verified", "offmap powers do not exist in CK3 (docs/mechanics_inventory.md)"),
    "set_artifact_flag": ("add_artifact_history", "approx", "assumed", "CK3 artifacts track history entries/variables, not flags"),
    "set_title_flag": ("set_variable", "approx", "assumed", "CK3 titles carry variables, not flags"),
    "set_dynasty_flag": ("set_variable", "approx", "assumed", "CK3 dynasties carry variables, not flags"),
    "set_variable": ("set_variable", "exact", "verified", "unchanged"),
    "change_variable": ("change_variable", "exact", "verified", "unchanged"),
    "check_variable": ("has_variable", "approx", "verified", "see triggers table: no check_variable key in CK3, needs restructuring"),
    "multiply_variable": (None, "none", "assumed", "not found in the CK3 1.19 vocabulary sample; use change_variable multiply="),
    "divide_variable": (None, "none", "assumed", "not found in the CK3 1.19 vocabulary sample; use change_variable divide="),
    "export_to_variable": (None, "none", "assumed", "CK3 has no direct localisation-export effect of this shape"),
    "clr_quest": (None, "none", "assumed", "CK3 quest system differs; no direct effect found"),
    "has_quest": (None, "none", "assumed", "CK3 quest system differs; no direct trigger found"),
    "character_event": ("trigger_event", "approx", "verified", "CK2 character_event (inline event trigger) -> CK3 trigger_event"),
    "letter_event": ("trigger_event", "approx", "assumed", "CK3 has no letter-event type; ported as a regular trigger_event"),
    "narrative_event": ("trigger_event", "approx", "assumed", "CK3 has no narrative-event type; ported as a regular trigger_event"),
    "province_event": (None, "none", "assumed", "CK2 province events have no direct CK3 scope-typed equivalent; a decision cannot fire one from character scope without a scope change"),
    "long_character_event": ("trigger_event", "approx", "assumed", "ported as a regular trigger_event"),
    "repeat_event": (None, "none", "assumed", "not found in the CK3 1.19 vocabulary sample; use an on_action pulse"),
    "id": ("id", "exact", "assumed", "unchanged (trigger_event field)"),
    "save_event_target_as": ("save_scope_as", "approx", "verified", "CK3 unified saved targets into scopes"),
    "save_persistent_event_target": (None, "none", "assumed", "CK3 has no persistent (cross-session) saved scope; nearest is a global variable"),
    "clear_persistent_event_target": (None, "none", "assumed", "see save_persistent_event_target"),
    "event_target": ("scope", "approx", "verified", "CK2 `event_target:X` reference -> CK3 `scope:X` (prefix rewrite, see ck2ck3.decisions_vocab)"),
    "persistent_event_target": (None, "none", "assumed", "CK3 has no persistent saved-scope equivalent; nearest is a global_var: reference"),
    "opinion_effect": (None, "none", "assumed", "not found in the CK3 1.19 vocabulary sample; use add_opinion"),
    "add_opinion": ("add_opinion", "exact", "verified", "unchanged"),
    "remove_opinion": ("remove_opinion", "exact", "verified", "unchanged"),
    "reverse_religion": (None, "none", "assumed", "not found in the CK3 1.19 vocabulary sample"),
    "convert_to": ("set_character_faith", "approx", "assumed", "CK2 religion-convert effect -> CK3 set_character_faith"),
    "convert_to_secret_religion": (None, "none", "verified", "secret religions do not exist in CK3 (docs/mechanics_inventory.md)"),
    "set_secret_religion": (None, "none", "verified", "secret religions do not exist in CK3 (docs/mechanics_inventory.md)"),
    "set_religion_head": (None, "none", "assumed", "CK3 assigns the religious head via the faith's clergy/doctrine system, not a bare effect"),
    "add_character_modifier": ("add_character_modifier", "exact", "verified", "unchanged"),
    "remove_character_modifier": ("remove_character_modifier", "exact", "verified", "unchanged"),
    "add_province_modifier": ("add_county_modifier", "approx", "assumed", "CK3 merged province into county"),
    "remove_province_modifier": ("remove_county_modifier", "approx", "assumed", "CK3 merged province into county"),
    "has_province_modifier": ("has_county_modifier", "approx", "assumed", "CK3 merged province into county (trigger, kept for cross-listing)"),
    "add_gold": ("add_gold", "exact", "verified", "unchanged"),
    "add_piety": ("add_piety", "exact", "verified", "unchanged"),
    "add_prestige": ("add_prestige", "exact", "verified", "unchanged"),
    "add_dread": ("add_dread", "exact", "verified", "unchanged"),
    "scaled_prestige": (None, "none", "assumed", "not found as a bare effect; use add_prestige with a scripted value"),
    "transfer_scaled_wealth": (None, "none", "assumed", "not found in the CK3 1.19 vocabulary sample"),
    "employer": ("employer", "exact", "assumed", "unchanged (scope-link, kept for cross-listing)"),
    "set_relation_rival": ("set_relation_rival", "exact", "verified", "unchanged"),
    "remove_friend": ("remove_relation_friend", "approx", "assumed", "CK3 relations are typed via set/remove_relation_<type>"),
    "remove_guardian": (None, "none", "assumed", "not found in the CK3 1.19 vocabulary sample"),
    "has_guardian": (None, "none", "assumed", "not found in the CK3 1.19 vocabulary sample"),
    "add_hook": ("add_hook", "exact", "verified", "unchanged"),
    "remove_hook": ("remove_hook", "exact", "verified", "unchanged"),
    "add_claim": ("add_pressed_claim", "approx", "verified", "CK2 add_claim (weak claim) has no exact CK3 counterpart; nearest is add_pressed_claim (strong claim)"),
    "add_pressed_claim": ("add_pressed_claim", "exact", "verified", "unchanged"),
    "banish": ("banish", "exact", "verified", "unchanged"),
    "exile": ("banish", "approx", "verified", "CK3 has no separate exile effect; banish is the nearest"),
    "imprison": ("imprison", "exact", "verified", "unchanged"),
    "execute_character": (None, "none", "verified", "not found in the CK3 1.19 vocabulary sample as a bare effect; nearest is a scheme/death effect, needs a human check"),
    "death": ("death", "exact", "verified", "unchanged"),
    "set_death_reason": ("set_death_reason", "exact", "verified", "unchanged"),
    "marry": ("marry", "exact", "verified", "unchanged (CLAUDE.md invariant)"),
    "divorce": ("divorce", "exact", "verified", "unchanged (CLAUDE.md invariant)"),
    "make_concubine": ("make_concubine", "exact", "verified", "unchanged (CLAUDE.md invariant)"),
    "remove_spouse": ("divorce", "approx", "assumed", "CK2 remove_spouse effect -> CK3 divorce (CLAUDE.md invariant on add/remove_spouse being history keys)"),
    "add_spouse": (None, "none", "verified", "CK2 add_spouse as an *effect* has no CK3 equivalent; marry is the effect, add_spouse is history-only (CLAUDE.md invariant)"),
    "genetic_father": ("father", "approx", "assumed", "CK3 has one father scope link, no separate genetic/social split as an effect target"),
    "genetic_mother": ("mother", "approx", "assumed", "CK3 has one mother scope link"),
    "set_father": ("set_father", "exact", "assumed", "unchanged"),
    "set_mother": ("set_mother", "exact", "assumed", "unchanged"),
    "set_gender": (None, "none", "assumed", "not found in the CK3 1.19 vocabulary sample as a runtime effect (gender is set at create_character time)"),
    "female": ("gender", "approx", "assumed", "CK2 create_character field `female = yes/no` -> CK3 `gender = female/male`"),
    "give_minor_title": (None, "none", "verified", "CK2 minor titles map to CK3 court positions, a different construct (docs/mechanics_inventory.md)"),
    "give_council_position": ("assign_council_task", "approx", "assumed", "CK3 renamed the council-position grant effect"),
    "grant_title": ("change_title_holder", "approx", "verified", "CK3 title transfer effect is change_title_holder"),
    "grant_title_no_opinion": ("change_title_holder", "approx", "assumed", "same effect, CK3 has no separate opinion-free variant found"),
    "create_title": (None, "none", "verified", "CK3 titles are a static database, not creatable at runtime (docs/mechanics_inventory.md)"),
    "activate_title": (None, "none", "assumed", "not found in the CK3 1.19 vocabulary sample; CK3 titles that exist in the database are always active"),
    "destroy_landed_title": ("destroy_title", "approx", "verified", "CK3 renamed the destroy-title effect"),
    "remove_title": ("change_title_holder", "approx", "assumed", "CK2 generic remove_title -> CK3 change_title_holder (to no one) / destroy_title depending on target, needs a human check"),
    "usurp_title": (None, "none", "assumed", "not found in the CK3 1.19 vocabulary sample as a bare effect"),
    "change_title_holder": ("change_title_holder", "exact", "verified", "unchanged"),
    "copy_title_history": (None, "none", "assumed", "not found in the CK3 1.19 vocabulary sample"),
    "copy_title_laws": (None, "none", "assumed", "not found in the CK3 1.19 vocabulary sample"),
    "abdicate": (None, "none", "verified", "not found in the CK3 1.19 vocabulary sample as a bare effect; needs a human check"),
    "abdicate_to": (None, "none", "assumed", "not found in the CK3 1.19 vocabulary sample as a bare effect"),
    "make_tributary": (None, "none", "assumed", "CK3 tributaries use a different (situation-based) mechanic; no direct effect found"),
    "remove_tributary": (None, "none", "assumed", "see make_tributary"),
    "set_defacto_liege": (None, "none", "assumed", "not found in the CK3 1.19 vocabulary sample"),
    "recalc_succession": (None, "none", "assumed", "not found in the CK3 1.19 vocabulary sample; CK3 recalculates automatically"),
    "add_law": (None, "none", "verified", "not found in the CK3 1.19 vocabulary sample as a bare effect; CK3 law-grant effects are per-law-group, needs a human check per decision"),
    "has_law": (None, "none", "verified", "not found in the CK3 1.19 vocabulary sample; CK3 checks a specific law group's value, not a bare has_law(trigger, kept for cross-listing)"),
    "add_building": ("add_building", "exact", "verified", "unchanged"),
    "build_holding": (None, "none", "assumed", "not found in the CK3 1.19 vocabulary sample as a bare effect"),
    "add_holding_slot": (None, "none", "assumed", "CK3 has no dynamic holding-slot effect"),
    "make_capital_holding": ("set_capital_county", "approx", "assumed", "CK3 capital is set at county level"),
    "num_of_empty_holdings": (None, "none", "assumed", "not found in the CK3 1.19 vocabulary sample"),
    "num_of_max_settlements": (None, "none", "verified", "CK3 has no settlement-count cap mechanic"),
    "spawn_unit": (None, "none", "verified",
        "spawn_army exists in CK3 (verified) but its inner schema is fixed (location=/name=/army_composition=...) and does not match CK2 spawn_unit's body (province=/owner=/leader=/troops={}) field-by-field - approximating the outer key alone left the CK2 body inside it, error(unknown-field)/error(missing-item) per field; needs a human rewrite per call site, same limitation as create_character"),
    "spawn_fleet": (None, "none", "assumed", "CK3 has no separate fleet-spawn effect (ships are part of army composition)"),
    "reinforces": (None, "none", "assumed", "not found in the CK3 1.19 vocabulary sample"),
    "disband_on_peace": (None, "none", "assumed", "not found in the CK3 1.19 vocabulary sample"),
    "can_toggle_looting": (None, "none", "assumed", "not found in the CK3 1.19 vocabulary sample"),
    "is_looter": (None, "none", "assumed", "not found in the CK3 1.19 vocabulary sample"),
    "attrition": (None, "none", "assumed", "not found in the CK3 1.19 vocabulary sample as a bare effect"),
    "troops": (None, "none", "assumed", "context-dependent field name (spawn_army composition), not a single vocabulary key"),
    "maintenance_multiplier": (None, "none", "assumed", "not found in the CK3 1.19 vocabulary sample"),
    "earmark": (None, "none", "assumed", "CK3 regiments have no earmark mechanic"),
    "has_earmarked_regiments": (None, "none", "assumed", "see earmark"),
    "cannot_inherit": (None, "none", "assumed", "not found in the CK3 1.19 vocabulary sample"),
    "set_graphical_culture": (None, "none", "verified", "not found in the CK3 1.19 vocabulary sample; CK3 graphical culture is a culture-definition field, not a runtime effect (out of this lane's scope - the cultures lane)"),
    "graphical_culture": (None, "none", "verified", "not found in the CK3 1.19 vocabulary sample as a bare trigger/effect key"),
    "set_government_type": ("change_government", "approx", "assumed", "CK3 government-change effect is change_government"),
    "government": ("government", "approx", "assumed", "context-dependent; see mappings/government_map.csv from the titles lane"),
    "gfx_culture_scope": (None, "none", "assumed", "not found in the CK3 1.19 vocabulary sample"),
    "trigger_event": ("trigger_event", "exact", "verified", "unchanged"),
    "random": ("random", "exact", "verified", "unchanged"),
    "random_list": ("random_list", "exact", "verified", "unchanged"),
    "chance": ("chance", "exact", "assumed", "unchanged (random_list weight field)"),
    "hidden_effect": ("hidden_effect", "exact", "assumed", "unchanged"),
    "hidden": (None, "none", "assumed", "context-dependent field name, not a single vocabulary key"),
    "custom_tooltip": ("custom_tooltip", "exact", "verified", "unchanged"),
    "hidden_tooltip": (None, "none", "verified", "see triggers table: not real CK3 vocabulary, approximating it broke custom_tooltip's required text field"),
    "tooltip": (None, "none", "assumed", "context-dependent field name, not a single vocabulary key"),
    "create_character": (None, "none", "verified",
        "the key exists in CK3 but its inner schema is a fixed template (template=/faith=/culture=/gender=/age=/random_traits=), not an open effect body like CK2's - CK2's body (remove_trait=, attributes={}, flag=...) does not port field-by-field without a human rewrite; approximating it as a pass-through produced error(unknown-field)/error(wrong-use) inside it"),
    "new_character": (None, "none", "assumed", "CK2 alias of create_character - see create_character"),
    "new_bloodline": (None, "none", "verified", "bloodlines do not exist in CK3 (docs/mechanics_inventory.md)"),
    "create_bloodline": (None, "none", "verified", "bloodlines do not exist in CK3 (docs/mechanics_inventory.md)"),
    "join_society": (None, "none", "verified", "societies do not exist in CK3 (docs/mechanics_inventory.md)"),
    "leave_society": (None, "none", "verified", "societies do not exist in CK3 (docs/mechanics_inventory.md)"),
    "activate_plot": (None, "none", "verified", "CK2 plots have no CK3 counterpart (docs/mechanics_inventory.md)"),
    "in_faction": (None, "none", "assumed", "not found in the CK3 1.19 vocabulary sample as a bare trigger"),
    "leads_faction": (None, "none", "assumed", "not found in the CK3 1.19 vocabulary sample"),
    "faction_power": (None, "none", "assumed", "not found in the CK3 1.19 vocabulary sample"),
    "artifact": (None, "none", "assumed", "context-dependent field name (add_artifact_title_history etc.), not a single vocabulary key"),
    "add_artifact": ("add_artifact_title_history", "approx", "assumed", "CK3 artifact-grant effects differ by source; needs a human check"),
    "destroy_artifact": ("destroy_artifact", "exact", "assumed", "unchanged"),
    "unsafe_destroy_artifact": ("destroy_artifact", "approx", "assumed", "CK3 has one destroy_artifact effect"),
    "transfer_artifact": (None, "none", "assumed", "not found in the CK3 1.19 vocabulary sample as a bare effect"),
    "has_artifact": ("has_artifact", "exact", "assumed", "unchanged (trigger, kept for cross-listing)"),
    "is_artifact_active": (None, "none", "assumed", "not found in the CK3 1.19 vocabulary sample"),
    "is_artifact_equipped": (None, "none", "assumed", "not found in the CK3 1.19 vocabulary sample"),
    "artifact_type": (None, "none", "assumed", "context-dependent field name, not a single vocabulary key"),
    "has_wonder_upgrade": (None, "none", "verified", "CK2 wonders map to CK3 special buildings, a different construct (docs/mechanics_inventory.md)"),
    "has_wonder_upgrade_flag": (None, "none", "verified", "see has_wonder_upgrade"),
    "is_building_wonder_upgrade": (None, "none", "verified", "see has_wonder_upgrade"),
    "any_realm_wonder_upgrade": (None, "none", "verified", "see has_wonder_upgrade"),
    "destroy_wonder_upgrade": (None, "none", "verified", "see has_wonder_upgrade"),
    "wonder": (None, "none", "verified", "see has_wonder_upgrade"),
    "wonder_owner": (None, "none", "verified", "see has_wonder_upgrade"),
    "move": (None, "none", "assumed", "context-dependent field name (army movement), not a single vocabulary key"),
    "move_character": (None, "none", "assumed", "not found in the CK3 1.19 vocabulary sample as a bare effect"),
    "force_host": (None, "none", "assumed", "CK3 has no travelling-court host mechanic"),
}

CURATED_EVENT_TARGETS: dict[str, tuple[str | None, str, str, str]] = {
    "liege": ("liege", "exact", "verified", "scope link, unchanged"),
    "top_liege": ("top_liege", "exact", "verified", "scope link, unchanged"),
    "employer": ("employer", "exact", "verified", "scope link, unchanged"),
    "spouse": ("primary_spouse", "approx", "assumed", "CK2 spouse (first spouse) -> CK3 primary_spouse; every_spouse for the full list"),
    "capital_scope": ("capital_county", "approx", "assumed", "CK3 splits capital_county/capital_barony"),
    "capital_holding": ("capital_barony", "approx", "assumed", "CK3 splits capital_county/capital_barony"),
    "location": (None, "none", "assumed", "no CK3 character->province scope link (character has no bare location)"),
    "primary_title": ("primary_title", "exact", "verified", "scope link, unchanged"),
    "holder": ("holder", "exact", "verified", "title -> holder character, unchanged"),
    "owner": ("holder", "approx", "assumed", "CK2 province owner -> CK3 county/barony holder"),
    "religion_head": ("faith.religious_head", "approx", "assumed", "guessed chain, needs a human check against 1.19 event_targets"),
    "any_vassal": ("every_vassal", "approx", "verified", "CK3 spells the any/every pair every_/any_ the same way; any_ used inside triggers, every_ inside effects"),
    "any_liege": (None, "none", "assumed", "CK3 has a single liege scope link, not a de jure chain iterator; use liege directly or de_jure_liege"),
    "any_de_jure_vassal_title": ("any_in_de_jure_hierarchy", "approx", "assumed", "guessed rename, needs a human check"),
    "any_demesne_title": ("any_held_title", "approx", "assumed", "guessed rename, needs a human check"),
    "any_demesne_province": ("any_held_title", "approx", "assumed", "CK3 merged province into county/barony titles"),
    "any_realm_province": ("any_in_de_facto_hierarchy", "approx", "assumed", "no bare province iterator; needs a human check"),
    "any_realm_title": ("any_in_de_facto_hierarchy", "approx", "assumed", "guessed rename, needs a human check"),
    "any_realm_character": ("any_in_de_facto_hierarchy", "approx", "assumed", "guessed rename, needs a human check"),
    "any_realm_lord": (None, "none", "assumed", "not found in the CK3 1.19 vocabulary sample"),
    "any_courtier": ("any_courtier", "exact", "verified", "list iterator, unchanged"),
    "any_courtier_or_vassal": ("any_courtier_or_guest", "approx", "verified", "CK3 renamed the courtier iterator family to courtier_or_guest"),
    "any_child": ("any_child", "exact", "verified", "list iterator, unchanged"),
    "any_consort": (None, "none", "assumed", "CK3 has no separate consort iterator from spouse"),
    "any_dynasty_member": ("any_dynasty_member", "exact", "verified", "unchanged"),
    "any_friend": (None, "none", "assumed", "not found in the CK3 1.19 vocabulary sample; use any relation-typed iterator"),
    "any_neighbor_province": ("any_neighboring_county", "approx", "verified", "CK3 merged province into county"),
    "any_neighbor_independent_ruler": (None, "none", "assumed", "not found in the CK3 1.19 vocabulary sample"),
    "random_courtier": ("random_courtier", "exact", "assumed", "unchanged"),
    "random_courtier_or_vassal": ("random_courtier_or_guest", "approx", "verified", "CK3 renamed the courtier iterator family to courtier_or_guest"),
    "random_vassal": ("random_vassal", "exact", "assumed", "unchanged"),
    "random_demesne_title": ("random_held_title", "approx", "assumed", "guessed rename, needs a human check"),
    "random_demesne_province": ("random_held_title", "approx", "assumed", "CK3 merged province into county/barony titles"),
    "random_landed_title": (None, "none", "assumed", "not found in the CK3 1.19 vocabulary sample"),
    "random_province_holding": (None, "none", "assumed", "not found in the CK3 1.19 vocabulary sample"),
    "random_society_member": (None, "none", "verified", "societies do not exist in CK3 (docs/mechanics_inventory.md)"),
    "random_realm_wonder_upgrade": (None, "none", "verified", "wonders do not exist in this form in CK3 (docs/mechanics_inventory.md)"),
    "de_jure_liege": ("de_jure_liege", "exact", "verified", "scope link, unchanged (title scope)"),
    "de_jure_liege_or_above": (None, "none", "verified", "not found in the CK3 1.19 vocabulary sample; needs a human check (chain de_jure_liege repeatedly, or a scripted list)"),
    "dejure_liege_title": ("de_jure_liege", "approx", "assumed", "same construct, different CK2 alias"),
    "base_title": (None, "none", "assumed", "not found in the CK3 1.19 vocabulary sample"),
    "thirdparty_title_scope": (None, "none", "verified", "third-party/targeted decisions map to CK3 character interactions, out of this lane's scope"),
    "plot_target_char": (None, "none", "verified", "CK2 plots have no CK3 counterpart (docs/mechanics_inventory.md)"),
    "governor": (None, "none", "verified", "offmap powers do not exist in CK3 (docs/mechanics_inventory.md)"),
    "offmap_ruler": (None, "none", "verified", "offmap powers do not exist in CK3 (docs/mechanics_inventory.md)"),
    "host": (None, "none", "assumed", "CK3 dropped the CK2 'host' (travelling court) concept as a scope word"),
    "current_heir": (None, "none", "assumed", "not found in the CK3 1.19 vocabulary sample as a bare scope link"),
    "player_heir": (None, "none", "assumed", "not found in the CK3 1.19 vocabulary sample"),
    "suzerain": (None, "none", "assumed", "not found in the CK3 1.19 vocabulary sample; use liege"),
    "genetic_father": ("father", "approx", "assumed", "CK3 has one father scope link"),
    "genetic_mother": ("mother", "approx", "assumed", "CK3 has one mother scope link"),
    "any_owned_bloodline": (None, "none", "verified", "bloodlines do not exist in CK3 (docs/mechanics_inventory.md)"),
    "any_bloodline": (None, "none", "verified", "bloodlines do not exist in CK3 (docs/mechanics_inventory.md)"),
    "society": (None, "none", "verified", "societies do not exist in CK3 (docs/mechanics_inventory.md)"),
    "any_society_member": (None, "none", "verified", "societies do not exist in CK3 (docs/mechanics_inventory.md)"),
    "job_chancellor": (None, "none", "verified", "CK2 council jobs are CK3 court positions, a different construct (docs/mechanics_inventory.md)"),
    "job_spymaster": (None, "none", "verified", "CK2 council jobs are CK3 court positions, a different construct (docs/mechanics_inventory.md)"),
}


def classify_from_ground_truth(key: str, gt: frozenset[str]) -> tuple[str | None, str, str, str]:
    for needle, reason in NONE_KEYWORD_REASONS:
        if needle in key.lower():
            return (None, "none", "verified" if needle not in ("z_",) else "assumed", reason)
    if key in gt:
        return (key, "exact", "assumed",
                "auto: identical spelling found in CK3 1.19 script usage (semantics not individually checked)")
    return (None, "none", "verified", "not found in the CK3 1.19 vocabulary sample (auto-classified)")


def build_table(
    keys: list[tuple[str, int]],
    curated: dict[str, tuple[str | None, str, str, str]],
    gt: frozenset[str],
) -> list[tuple[str, str, str, str, str, int]]:
    rows = []
    seen = set()
    for key, count in keys:
        if key in seen or TITLE_TAG_RE.match(key):
            continue
        seen.add(key)
        ck3_key, status, confidence, note = curated.get(key) or classify_from_ground_truth(key, gt)
        rows.append((key, ck3_key or "", status, confidence, note, count))
    rows.sort(key=lambda r: (-r[5], r[0]))
    return rows


def write_csv(path: Path, rows: list[tuple[str, str, str, str, str, int]]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["ck2_key", "ck3_key", "status", "confidence", "note", "decision_uses"])
        for row in rows:
            writer.writerow(row)


def main() -> None:
    gt = ground_truth()
    trigger_survey: list[tuple[str, int]] = []
    effect_survey: list[tuple[str, int]] = []
    with open(SURVEY, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            target = trigger_survey if row["section"] == "trigger" else effect_survey
            target.append((row["key"], int(row["count"])))

    trigger_rows = build_table(trigger_survey, CURATED_TRIGGERS, gt)
    effect_rows = build_table(effect_survey, CURATED_EFFECTS, gt)
    # event_targets.csv is curated-only (it documents scope words, not every
    # survey key) plus any survey key explicitly curated above that a human
    # would expect to find there.
    target_rows = []
    for key, (ck3_key, status, confidence, note) in sorted(CURATED_EVENT_TARGETS.items()):
        target_rows.append((key, ck3_key or "", status, confidence, note, 0))

    write_csv(REPO / "mappings" / "triggers.csv", trigger_rows)
    write_csv(REPO / "mappings" / "effects.csv", effect_rows)
    write_csv(REPO / "mappings" / "event_targets.csv", target_rows)

    for name, rows in (("triggers", trigger_rows), ("effects", effect_rows), ("event_targets", target_rows)):
        total = len(rows)
        mapped = sum(1 for r in rows if r[1])
        print(f"{name}: {total} rows, {mapped} mapped ({mapped / total:.0%})" if total else f"{name}: 0 rows")


if __name__ == "__main__":
    main()
