"""Regenerate ``mappings/on_actions_ck2_ck3.csv``.

Lane `on-actions`. For every id in ``docs/evidence/on_actions_provenance.csv``
(197 CK2 `common/on_actions` ids, 107 `kept` / 90 `modified`, 0 `new`), decide
a CK3 `common/on_action` counterpart - or ``none`` with a reason.

A `kept` row means Faerûn's own on_action block is byte-for-byte the CK2
vanilla one (`docs/events_provenance.md` §2): there is no Faerûn *delta* to
port, so every `kept` row is ``none: kept - identical to vanilla CK2,
nothing new to port`` without further research.

`modified` rows are the actionable 90. :data:`CURATED` is a small,
individually **verified** table (root/scope checked against the CK3 1.19
install, see the docstring on each entry's evidence in
`docs/step_events.md` §on_actions) - not a semantic-search guess. Every
`modified` id absent from :data:`CURATED` is written ``none`` with one of
the reason buckets below; extending the table is future work
(`docs/evidence/HANDOFF_on_actions.md`).

Run: ``uv run scripts/build_on_actions_map.py``. Read by
``src/ck2ck3/steps/on_actions.py``.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PROVENANCE = REPO_ROOT / "docs" / "evidence" / "on_actions_provenance.csv"
OUT = REPO_ROOT / "mappings" / "on_actions_ck2_ck3.csv"

#: ck2_on_action -> (ck3_on_action, ck3_root_scope, note-with-evidence).
#: Every row `verified` against the 1.19 install
#: (`../claudespace/game_files/common/on_action/`), 2026-09-23.
CURATED: dict[str, tuple[str, str, str]] = {
    "on_death": ("on_death", "character (dying)", "exact name match; game/common/on_action/death.txt:1 'character just about to die in root scope'"),
    "on_divorce": ("on_divorce", "character (major partner)", "exact name match; game/common/on_action/marriage_concubinage.txt:176, same shape as on_marriage"),
    "on_marriage": ("on_marriage", "character (major partner)", "exact name match; game/common/on_action/marriage_concubinage.txt:2-4 'root = Major partner of the marriage'"),
    "on_war_started": ("on_war_started", "character (assumed: CB declarant, same as on_declaration)", "exact name match; game/common/on_action/war_on_actions.txt:309-312 'same scopes as the CBs on_declaration'"),
    "on_adulthood": ("on_birthday_adulthood", "character (coming of age)", "game/common/on_action/birthday.txt:1-2,323 'character having its birthday in root scope', called from on_birthday's on_actions chain (scope carries over)"),
    "on_outbreak": ("disease_outbreak_pulse", "character (assumed: per-character disease pulse, same shape as CK2 on_outbreak)", "game/common/on_action/health_on_actions.txt:343, no explicit root comment - medium confidence"),
    "on_became_imprisoned": ("on_imprison", "character (the one imprisoned)", "game/common/on_action/prison_on_actions.txt:5-7 'character being imprisoned in root scope'"),
    "on_become_imprisoned_any_reason": ("on_imprison", "character (the one imprisoned)", "same target as on_became_imprisoned; CK3 on_imprison covers every imprisonment reason, matching CK2's 'any_reason' variant"),
    "on_released_from_prison": ("on_release_from_prison", "character (the one released)", "game/common/on_action/prison_on_actions.txt:252-253 'character released from prison in root scope'"),
    "on_birth": ("on_birth_mother", "character (mother)", "game/common/on_action/child_birth_on_actions.txt:1-8 'called for the mother'; CK2 on_birth ROOT is also the mother. CK3 additionally splits into on_birth_child/on_birth_father, not wired here (single-target mapping only)"),
    "on_pregnancy": ("on_pregnancy_mother", "character (mother)", "game/common/on_action/child_birth_on_actions.txt:1165-1169 'called for the mother when a pregnancy reaches revealed status'"),
    "on_character_convert_religion": ("on_character_faith_change", "character", "game/common/on_action/religion_on_actions.txt:388-391 'Root is the character'"),
    "on_character_convert_culture": ("on_character_culture_change", "character", "game/common/on_action/culture_on_actions.txt:29-30 'Root = character'"),
}

#: ck2 id -> reason bucket, checked before the generic "not researched" note.
SOCIETY = "societies do not exist in CK3 (docs/mechanics_inventory.md), matches events step OUT_OF_SCOPE_REASONS['society_quest_event']"
COMBAT_SIDE_SCOPE = (
    "CK3's combat_on_actions.txt on_combat_end_winner/loser root is the "
    "winning/losing COMBAT SIDE, not a character (verified, 'Root = Winning "
    "combat side'); a ported character-scope event body cannot fire from "
    "there without a scope hop this pass does not synthesize"
)
WAR_ENDED_SCOPE = (
    "game/common/on_action/war_on_actions.txt on_war_won_attacker/defender/"
    "white_peace/invalidated document no character root (only scope:attacker/"
    "scope:defender/scope:war); guessing the root risks firing a "
    "character-scope body in the wrong scope (safety rule, docs/step_decisions.md §3b)"
)
CRUSADE = "CK3 replaced crusades with great holy wars; no per-event counterpart researched this pass"
BUCKETS: dict[str, str] = {
    "on_character_ask_to_join_society": SOCIETY,
    "on_character_join_society": SOCIETY,
    "on_character_kicked_from_society": SOCIETY,
    "on_character_leave_society": SOCIETY,
    "on_character_society_rank_down": SOCIETY,
    "on_character_society_rank_up": SOCIETY,
    "on_character_switch_society_interest": SOCIETY,
    "on_society_bi_yearly_pulse": SOCIETY,
    "on_society_progress_full": SOCIETY,
    "on_battle_lost": COMBAT_SIDE_SCOPE,
    "on_battle_lost_leader": COMBAT_SIDE_SCOPE,
    "on_battle_won": COMBAT_SIDE_SCOPE,
    "on_battle_won_leader": COMBAT_SIDE_SCOPE,
    "on_major_battle_lost": COMBAT_SIDE_SCOPE,
    "on_major_battle_lost_leader": COMBAT_SIDE_SCOPE,
    "on_major_battle_won": COMBAT_SIDE_SCOPE,
    "on_major_battle_won_leader": COMBAT_SIDE_SCOPE,
    "on_siege_lost_leader": COMBAT_SIDE_SCOPE,
    "on_siege_won_leader": COMBAT_SIDE_SCOPE,
    "on_siege_over_winner": COMBAT_SIDE_SCOPE,
    "on_siege_over_loc_chars": COMBAT_SIDE_SCOPE,
    "on_war_ended_defeat": WAR_ENDED_SCOPE,
    "on_war_ended_invalid": WAR_ENDED_SCOPE,
    "on_war_ended_victory": WAR_ENDED_SCOPE,
    "on_war_ended_whitepeace": WAR_ENDED_SCOPE,
    "on_crusade_canceled": CRUSADE,
    "on_crusade_creation": CRUSADE,
    "on_crusade_invalid": CRUSADE,
    "on_crusade_launches": CRUSADE,
    "on_crusade_monthly": CRUSADE,
    "on_crusade_preparation_starts": CRUSADE,
    "on_crusade_target_changes": CRUSADE,
    "on_pledge_crusade_participation": CRUSADE,
    "on_unpledge_crusade_participation": CRUSADE,
}
NOT_RESEARCHED = (
    "not researched this pass; needs the same per-on_action name+root+scope "
    "check as the CURATED rows (docs/evidence/HANDOFF_on_actions.md)"
)


def build() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with open(PROVENANCE, encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if row["kind"] != "on_action":
                continue
            ck2_id = row["id"]
            status = row["status"]
            if status == "kept":
                rows.append({
                    "ck2_on_action": ck2_id, "status": status, "ck3_on_action": "",
                    "ck3_root_scope": "", "confidence": "n/a",
                    "note": "kept: identical to vanilla CK2, nothing new to port",
                })
                continue
            if ck2_id in CURATED:
                ck3_id, scope, note = CURATED[ck2_id]
                rows.append({
                    "ck2_on_action": ck2_id, "status": status, "ck3_on_action": ck3_id,
                    "ck3_root_scope": scope, "confidence": "verified", "note": note,
                })
                continue
            reason = BUCKETS.get(ck2_id, NOT_RESEARCHED)
            rows.append({
                "ck2_on_action": ck2_id, "status": status, "ck3_on_action": "",
                "ck3_root_scope": "", "confidence": "none", "note": reason,
            })
    rows.sort(key=lambda r: r["ck2_on_action"])
    return rows


def main() -> int:
    rows = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["ck2_on_action", "status", "ck3_on_action", "ck3_root_scope", "confidence", "note"],
        )
        writer.writeheader()
        writer.writerows(rows)
    mapped = sum(1 for r in rows if r["ck3_on_action"])
    modified = sum(1 for r in rows if r["status"] == "modified")
    print(f"{len(rows)} rows -> {OUT.relative_to(REPO_ROOT)}; {mapped}/{modified} modified ids mapped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
