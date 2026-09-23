# Hand-off from lane `on-actions` to the `modified`-events lane (and beyond)

Lane `on-actions` did the events hand-off's §3 job (`docs/evidence/HANDOFF_events.md`):
orphan hygiene, the `missing_loc` gate, the CK2->CK3 on_action mapping table,
the on_action wiring step, the faith/culture value rewrite, and the MTTH
pulse formula (not wired — nothing currently qualifies). Rules and counts:
`docs/step_events.md` §on_actions. This doc is what the **next** lanes need,
named the same way `HANDOFF_events.md` named this one.

## 1. Contracts the next lanes must reuse, not re-derive

| thing | where | why |
|---|---|---|
| CK2 on_action name -> CK3 counterpart | `mappings/on_actions_ck2_ck3.csv` (`scripts/build_on_actions_map.py`) | 13 of 90 `modified` rows are mapped and individually verified; extending `CURATED` is the single biggest lever left (§2). |
| which live events an on_action reaches | `ctx.data["events"]["reachable_ids"]` after `on_actions` runs, or `docs/evidence/on_actions_convertibility.csv` (`wired = yes`) | Re-deriving reachability independently risks the same drift CLAUDE.md's id-collision invariant warns about — always read it, don't recompute from the raw on_action files by hand. |
| the orphan mechanism | `ck2ck3.steps.events.write_events`/`render_event`/`event_calls_within_live` | A step that adds more reachability (this hand-off's own next lane will) must call `events.write_events(ctx, events_data["prefix"], events_data["by_file"], full_reachable_ids)` again, not hand-roll an `orphan` patch — it is idempotent and needs no re-parsing. |
| faith/culture value rewrite | `ck2ck3.steps.events.make_faith_culture_hook`, `FAITH_CULTURE_KEYS` | `religion`/`religion_group`/`set_religion`/`culture`/`set_culture` are now resolved through `ctx.data["religions"]`/`["cultures"]`, keyed by context (trigger vs effect) - `docs/step_events.md` §1a has the full table with vanilla file:line evidence. `docs/step_decisions.md` §3.3 is the same gap in `decisions.py`, still open. |
| `missing_loc` gate | `ck2ck3.steps.events.GATE_REASONS["missing_loc"]` | Generalised, not special-cased - any future event whose loc key is not ported gets it automatically. |

## 2. Extending `mappings/on_actions_ck2_ck3.csv` (biggest lever)

77 of the 90 `modified` on_actions are still `confidence = none`:

- **43 `not researched this pass`** — the same per-name check as the 13
  curated rows (exact/near name match in
  `../claudespace/game_files/common/on_action/*.txt`, then read the file's
  own leading comment for the root scope, then cross-check a real usage
  line). Ordered by nothing in particular; `docs/evidence/on_actions_provenance.csv`
  has the full 90-row `modified` list with `changed_keys` per row if a
  frequency order is wanted.
- **12 `combat-side scope`** (`on_battle_won`/`_lost`/`_leader` families,
  `on_siege_*_leader`, `on_siege_over_*`) — CK3's `on_combat_end_winner`/
  `_loser` root is the *combat side*, not a character
  (`game/common/on_action/combat_on_actions.txt:14`). A real fix needs a
  scope hop (`side_primary_participant` or similar) this pass does not
  synthesize - worth a dedicated look, since "someone won/lost a battle" is
  common flavour-event material.
- **4 `war-ended scope`** (`on_war_ended_victory`/`_defeat`/`_whitepeace`/
  `_invalid`) — `on_war_won_attacker`/`_defender`/`_white_peace`/
  `_invalidated` document no character root at all in
  `game/common/on_action/war_on_actions.txt`; only `scope:attacker`/
  `scope:defender`/`scope:war`. Needs the same kind of scope hop.
- **9 `society`** (`on_character_*_society*`) — CK3 has no societies. Only
  revisit if a submod reimplements them (same call `docs/step_events.md` §2
  already made for `society_quest_event`).
- **9 `crusade`** (`on_crusade_*`, `on_p(un)ledge_crusade_participation`) —
  CK3 replaced crusades with great holy wars; no per-event counterpart was
  matched. `game/common/on_action/religion_on_actions.txt:987-1016`
  (`on_great_holy_war_*`) is the nearest system, not researched further.

Regenerate with `uv run scripts/build_on_actions_map.py` after editing
`CURATED`/`BUCKETS` in that script - it is the single source, never hand-edit
`mappings/on_actions_ck2_ck3.csv` itself (a comment at its own header, if you
add one, should say so).

## 3. Why only 1 event wired this run, and what changes that

`docs/evidence/on_actions_convertibility.csv`: of 185 hookups the 13 mapped
on_actions carry, 137 name a vanilla CK2 event (`kept`/`modified` status —
out of this lane's `new`-only scope) and 47 name a `new` event that is
itself still a stub. Both numbers shrink as other lanes progress:

- **The `modified`-events lane** (`docs/evidence/HANDOFF_events.md` §2) is
  what turns the 137 "not a `new` event" rows into real hookups - most of
  Faerûn's on_action content references *vanilla* CK2 events it modified,
  not new ones.
- **Raising the events step's own live count** (better vocabulary-table
  coverage, `docs/step_events.md` §11.2; resolving `unsaved_scope`/
  `from_scope`, §11 items about `FROM` binding) turns some of the 47 stub
  rows live automatically - re-run `on_actions` after any such change, no
  code change needed here.

## 4. MTTH pulse: formula ready, nothing wired

`docs/step_events.md` §on_actions "MTTH pulse" has the formula
(`weight = round(12000 / mean_months)` on `yearly_playable_pulse`'s
`random_events`, `quarterly_playable_pulse` for `mean_months` < ~4) and the
evidence for both on_action names. **0 of the 3 `mean_time_to_happen` events
are otherwise live** (all score 0.32-0.35), so nothing was wired - wiring a
pulse hookup for a body this unmapped is exactly what
`docs/step_decisions.md` §3b's stabilisation policy forbids. If the
`modified`-events lane brings more MTTH events across `min_score`, implement
the formula as a small addition to `on_actions.py` (a dedicated
`MTTH_KEYS`/hook similar to `FAITH_CULTURE_KEYS`, gated the same "only a
live event" way `make_event_hook` already is).

## 5. In-game soak (coordinator's job)

Not run from this worktree (`claudespace/scripts/ck3_soak.sh` needs the mod
registered under `claudespace/mods/`, outside this worktree's write scope).
Before soaking:

- ck3-tiger over `wt/_out/on-actions`: **fatal 0, error 58** (unchanged from
  the events-lane baseline), zero findings under `common/on_action/`
  (`docs/evidence/tiger_on_actions_2026-09-23.txt`,
  `..._summary.txt`).
- The one live wire: `fae_frmaint.20` (CK2 `frmaint.20`, a
  `has_character_flag = reverting_religion_change` character_event) now
  fires from `on_character_faith_change` (root = the character whose faith
  changed) — a low-risk single event, safe to soak alongside the events-lane
  baseline (`docs/evidence/on_actions_convertibility.csv`).
- Re-run `scripts/tiger_on_actions_check.py` after any change to confirm the
  `common/on_action/` finding count stays 0 and `events/` does not grow past
  its current 3.

## 6. Loose end this lane found but did not fix

`docs/step_decisions.md` §3.3's `government`/tier-constant value rewrite and
the faith/culture rewrite are the same *class* of gap (`convert_block` only
ever rewrote keys, never values) but live in two different converters
(`decisions.py` vs `events.py`). `decisions.py` does not yet take the
`religions`/`cultures` maps `events.py` now does - wiring it through would
be a small, mechanical follow-up, not owned by this lane (`decisions` is a
different step with its own `min_score`/stabilisation history).
