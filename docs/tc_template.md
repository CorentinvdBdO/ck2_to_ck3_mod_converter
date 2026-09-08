# The blank total-conversion layer — which vanilla folder goes, and why

Step: `tc_template` (`src/ck2ck3/steps/tc_template.py`).
Table: `mappings/tc_template.csv`. Shared rules: `src/ck2ck3/tcshadow.py`.
Research log with every measurement: `docs/evidence/tc_template_research.md`.

## The problem

A total conversion keeps vanilla **mechanics** — events with generic scopes,
lifestyles, schemes, laws, governments, buildings, innovations — and must lose
vanilla **content**: anything that names a vanilla title, province, character,
dynasty or region. On this map those names resolve to nothing.

Measured on the 2026-09-08 build (`verified`, the live `error.log`):

- **12 877** `title_links.cpp:214 Failed to fetch a valid landed title`, over
  1 400 distinct tags in 418 vanilla files, deterministic at every load;
- 3 433 `history.cpp` "referencing non-existent character in script link",
  2 105 of them `character:<numeric id>` from vanilla portrait modifiers;
- 483 `pdx_persistent_reader.cpp` "Failed to read key reference", mostly
  `common/flavorization` naming `e_japan` and `k_chrysanthemum_throne`;
- 4 411 "Failed to fetch a valid dynasty" out of `common/legends/legend_seeds`;
- and, worst of all, a **crash on click**: the Silk Road situation
  (`common/decisions/dlc_decisions/tgp/tgp_silk_road_decisions.txt` and
  `common/situation/situations/tgp_dynastic_cycle.txt`).

`ck3-tiger` cannot see any of this: it validates the **mod's** files, never
vanilla's, so a full before/after run over the generated mod reports the same
56 errors either way (`verified` 2026-09-08, two throwaway `--out` runs,
`scripts/tc_tiger_before_after.sh`). The game's `error.log` is the only
instrument for this class.

## The two techniques, and when each is right

**Shadow** — write a file with the same relative path as the vanilla one,
holding a BOM and one comment line. CK3 loads the mod's file instead, so the
vanilla definitions in it are gone. No `replace_path` needed. `verified`
2026-09-08: Elder Kings 2 ships 149 such stub-sized same-path files and
Godherja 137, including all 9 of EK2's `tests/` overrides — override-by-filename
is enough to delete a vanilla database, and both shipped 1.19 total conversions
rely on it.

**Neutralise** — keep the file's top-level keys, drop their bodies
(`some_effect = {}`). For a content file that lives *inside* a mechanic
database, where a file we keep still calls one of its keys. `verified`: this is
Elder Kings 2's `common/situation/catalysts/catalysts.txt`, 120 bytes, every
vanilla catalyst key re-declared empty.

Two traps, both hit and both now guarded:

1. `scripts/tc_check_shadow_callers.py` found **534** blanked definitions with
   a live caller in the first draft (accolade character templates called from
   `00_accolades_scripted_effects.txt`, Japanese succession triggers called
   from `common/laws/00_succession_laws.txt`, `setup_tributaries_effect` called
   from `on_action/game_start.txt`). Those 27 rows became `neutralise`. The
   check now reports **0**.
2. **An empty trigger block evaluates true in CK3.** A neutralised
   `scripted_trigger` therefore gets `{ always = no }`, and a `script_value` a
   bare `0`, not `{}` — otherwise
   `can_have_japanese_appointment_succession_law_trigger` would go from broken
   to always allowed.

`replace_path` is used for **none** of this. The repo rule — a `replace_path`
only for a folder we fill — still holds; every row here is pure deletion, so it
is a shadow. The mode exists in the table (and warns when `[mod] replace_paths`
does not list the folder) for the day a lane does fill one.

## The decision table

`vanilla files` is what the row selects, `written` what the step wrote,
`title_links` the errors those files caused in the 2026-09-08 log, `static refs`
the whole folder's title/province/character/dynasty references from
`scripts/tc_scan_vanilla_refs.py`, and the last column how many of the folder's
files Atlantis / Elder Kings 2 / Godherja override at all.

| path | mode | vanilla files | written | title_links | static refs | overridden by ATL/EK2/GH | why |
|---|---|---:|---:|---:|---:|---|---|
| `common/achievements` | shadow | 10 | 10 | 49 | 66 | 9/11/9 (replace_path: GH) | Achievements name vanilla titles and provinces (49 title_links). Godherja replace_paths the folder; Atlantis overrides 9 of the 10 files and EK2 all 11 of its own. |
| `common/coat_of_arms/dynamic_definitions` | shadow | 3 | 3 | 6 | 130 | 3/4/3 | 124 bare vanilla title tags keyed to dynasty/house heraldry. Atlantis ships 3 files here that are a BOM and nothing else; EK2 stubs 2 and Godherja 3. |
| `common/culture/creation_names` | shadow | 2 | 2 | 409 | 437 | 0/3/2 | 409 title_links: the names a created empire/kingdom gets ("k_france" -> Kingdom of France). Pure vanilla-map content. |
| `common/decisions` | shadow | 34 | 34 | 717 | 799 | 14/34/20 (replace_path: GH) | 717 title_links over 23 of 34 files (found kingdoms, restore the Roman Empire). Godherja declares replace_path="common/decisions"; EK2 stubs 7 files. |
| `common/decisions/dlc_decisions` | shadow | 3 | 3 | 208 | 224 | 3/3/3 | 208 title_links. Same class as the parent folder; replace_path is not recursive so every subfolder is its own row. |
| `common/decisions/dlc_decisions/bp3` | shadow | 1 | 1 | 22 | 43 | 1/1/1 | DLC decisions naming vanilla titles (22 title_links). |
| `common/decisions/dlc_decisions/bp_2` | shadow | 1 | 1 |  | 0 | 0/0/1 | DLC decisions folder; shadowed with its siblings so no decision survives that names a vanilla title. |
| `common/decisions/dlc_decisions/ce_1` | shadow | 1 | 1 | 1 | 1 | 1/1/1 | DLC decisions naming vanilla titles (1 title_links). |
| `common/decisions/dlc_decisions/ep_1` | shadow | 2 | 2 | 6 | 6 | 2/2/2 | DLC decisions naming vanilla titles (6 title_links). |
| `common/decisions/dlc_decisions/ep_2` | shadow | 1 | 1 |  | 0 | 0/0/1 | DLC decisions folder; shadowed with its siblings. |
| `common/decisions/dlc_decisions/ep_3` | shadow | 4 | 4 | 6 | 125 | 3/4/4 | DLC decisions naming vanilla titles (6 title_links). |
| `common/decisions/dlc_decisions/fp_1` | shadow | 2 | 2 | 24 | 30 | 1/1/1 | DLC decisions naming vanilla titles (24 title_links). |
| `common/decisions/dlc_decisions/fp_3` | shadow | 5 | 5 | 21 | 28 | 1/3/3 | DLC decisions naming vanilla titles (21 title_links). |
| `common/decisions/dlc_decisions/mpo` | shadow | 5 | 5 | 12 | 34 | 1/4/5 | DLC decisions naming vanilla titles (12 title_links). |
| `common/decisions/dlc_decisions/tgp` | shadow | 10 | 10 | 206 | 258 | 0/8/8 | 206 title_links, including tgp_silk_road_decisions.txt - the Silk Road situation the playtest crashed on. |
| `common/flavorization` | shadow | 8 | 8 |  | 168 | 0/9/7 | 1783 pdx_persistent_reader "Failed to read key reference" at load, all naming vanilla titles (e_japan, k_chrysanthemum_throne). EK2 stubs 6 of 8 files, Godherja 3. |
| `common/great_projects/types` | shadow | 3 | 3 | 341 | 369 | 0/4/3 | 341 title_links: wonders pinned to vanilla counties and provinces. |
| `common/legends/chronicles` | shadow | 1 | 1 | 32 | 64 | 1/1/1 | 32 title_links plus vanilla dynasty references. |
| `common/legends/legend_seeds` | shadow | 1 | 1 | 47 | 106 | 1/1/1 | 4411 "Failed to fetch a valid dynasty" script errors and 47 title_links: seeds are historical legends about vanilla dynasties and titles. |
| `common/on_action/story_cycles` | neutralise | 23 | 23 |  | 0 | 0/3/8 | The on_action hooks of the shadowed story cycles. Neutralised, not blanked: `common/on_action/yearly_on_actions.txt` and three DLC event files call six of these hooks by name. EK2 stubs 2 files here. |
| `common/situation/catalysts` | shadow | 5 | 5 |  | 0 | 0/2/0 | Catalysts exist only to advance the situations shadowed below. |
| `common/situation/situations` | shadow | 10 | 10 | 40 | 51 | 0/10/8 | 40 title_links. tgp_dynastic_cycle.txt and the Silk Road situation crashed the game on click (playtest 2026-09-08). Godherja stubs 5 of 10 files; the brief requires situations fully neutral. |
| `common/story_cycles` | shadow | 52 | 52 | 45 | 60 | 4/22/24 | 45 title_links over 9 of 52 files; the rest are vanilla historical narratives with no place on this map. EK2 stubs 13, Godherja 10. |
| `common/struggle/catalysts` | shadow | 1 | 1 |  | 0 | 0/1/1 | Catalysts of the struggles shadowed below. |
| `common/struggle/struggles` | shadow | 2 | 2 | 3 | 3 | 0/3/2 | history/struggles is already replace_path-ed and empty, so the three vanilla struggles are unreachable content; the brief requires them fully neutral. |
| `common/travel/point_of_interest_types` | shadow | 1 | 1 |  | 51 | 1/1/1 | 51 province: references to vanilla provinces. |
| `common/tutorial_lesson_chains` | shadow | 1 | 1 | 2 | 2 | 0/1/1 | Chains of the tutorial lessons shadowed below. |
| `common/tutorial_lessons` | shadow | 9 | 9 | 27 | 27 | 4/6/4 | 27 title_links: the tutorial walks the player through 1066 Ireland. |
| `events/decisions_events` | shadow | 19 | 19 | 337 | 409 | 6/16/15 | 337 title_links. Fired only by the decisions shadowed above, so shadowing both keeps the set closed. EK2 stubs 5 files, Godherja 9. |
| `events/story_cycles` | shadow | 12 | 12 | 26 | 49 | 5/8/8 | 26 title_links. Fired only by common/story_cycles, shadowed above. Godherja stubs 4. |
| `common/scripted_effects/00_decisions_effects.txt` | neutralise | 1 | 1 | 251 | 5147 | 22/86/94 | 251 title_links; called only from common/decisions. |
| `common/scripted_effects/00_ep3_decision_effects.txt` | neutralise | 1 | 1 | 32 | 5147 | 22/86/94 | 32 title_links; called only from the ep3 decisions. |
| `common/scripted_effects/00_historical_characters_scripted_effects.txt` | neutralise | 1 | 1 | 151 | 5147 | 22/86/94 | 151 title_links; spawns named vanilla historical characters. |
| `common/scripted_effects/00_major_decisions_scripted_effects.txt` | neutralise | 1 | 1 | 933 | 5147 | 22/86/94 | 933 title_links - the single worst vanilla file. Called only from the major decisions. |
| `common/scripted_effects/00_major_decisions_scripted_effects_2.txt` | neutralise | 1 | 1 | 3 | 5147 | 22/86/94 | Continuation of the file above; same callers. |
| `common/scripted_effects/00_major_decisions_scripted_effects_3.txt` | neutralise | 1 | 1 | 50 | 5147 | 22/86/94 | 50 title_links; same callers. |
| `common/scripted_effects/00_mongol_invasion_effects.txt` | neutralise | 1 | 1 | 121 | 5147 | 22/86/94 | 121 title_links: the Mongol invasion scripts vanilla titles and characters directly. |
| `common/scripted_effects/00_tributary_setup_effects.txt` | neutralise | 1 | 1 | 105 | 5147 | 22/86/94 | 105 title_links: sets up the 1066/867 tributary web by title tag. |
| `common/scripted_effects/01_exp1_historical_artifacts_creation_effect.txt` | neutralise | 1 | 1 | 77 | 5147 | 22/86/94 | 77 title_links; creates artefacts owned by vanilla characters. |
| `common/scripted_effects/06_dlc_ce1_legend_effects.txt` | neutralise | 1 | 1 | 146 | 5147 | 22/86/94 | 146 title_links; the legend seeds that call it are shadowed above. |
| `common/scripted_effects/07_frankokratia_scripted_effects.txt` | neutralise | 1 | 1 | 258 | 5147 | 22/86/94 | 258 title_links: the Frankokratia is a Byzantine map event chain. |
| `common/scripted_effects/10_dlc_tgp_scripted_effects.txt` | neutralise | 1 | 1 | 314 | 5147 | 22/86/94 | 314 title_links (East Asia content). |
| `common/scripted_effects/10_dlc_tgp_dynastic_cycle_scripted_effects.txt` | neutralise | 1 | 1 | 107 | 5147 | 22/86/94 | 107 title_links (East Asia content). |
| `common/scripted_effects/tgp_tribute_mission_scripted_effects.txt` | neutralise | 1 | 1 | 66 | 5147 | 22/86/94 | 66 title_links (East Asia content). |
| `common/scripted_triggers/07_frankokratia_triggers.txt` | neutralise | 1 | 1 | 89 | 874 | 10/79/82 | 89 title_links; paired with the Frankokratia effects. |
| `common/scripted_triggers/10_tgp_japan_triggers.txt` | neutralise | 1 | 1 | 2965 | 874 | 10/79/82 | 2965 title_links - the largest single class in the log. Every trigger tests a vanilla Japanese title. |
| `common/scripted_triggers/10_tgp_triggers.txt` | neutralise | 1 | 1 | 45 | 874 | 10/79/82 | 45 title_links (East Asia content). |
| `common/scripted_triggers/10_tgp_dynastic_cycle_triggers.txt` | neutralise | 1 | 1 | 20 | 874 | 10/79/82 | 20 title_links (East Asia content). |
| `common/scripted_triggers/tgp_tribute_mission_triggers.txt` | neutralise | 1 | 1 | 60 | 874 | 10/79/82 | 60 title_links (East Asia content). |
| `common/scripted_modifiers/10_tgp_japan_modifiers.txt` | neutralise | 1 | 1 | 331 | 37 | 2/13/14 | 331 title_links (East Asia content). |
| `common/script_values/10_tgp_japan_values.txt` | neutralise | 1 | 1 | 1 | 573 | 8/48/52 | Values read only by the shadowed Japanese triggers and modifiers. |
| `common/script_values/tgp_japan_values.txt` | neutralise | 1 | 1 | 3 | 573 | 8/48/52 | Values read only by the shadowed Japanese content. |
| `common/script_values/tgp_tribute_mission_values.txt` | neutralise | 1 | 1 | 30 | 573 | 8/48/52 | 30 title_links; read only by the shadowed tribute-mission scripts. |
| `common/script_values/00_decision_values.txt` | neutralise | 1 | 1 | 4 | 573 | 8/48/52 | Read only by common/decisions. |
| `common/script_values/00_mongol_values.txt` | neutralise | 1 | 1 |  | 573 | 8/48/52 | Read only by the Mongol invasion effects shadowed above. |
| `common/script_values/00_invasion_values.txt` | neutralise | 1 | 1 | 1 | 573 | 8/48/52 | Read only by the Mongol invasion effects shadowed above. |
| `gfx/portraits/portrait_modifiers/02_all_developer_characters.txt`, `02_all_historical_characters.txt` | shadow | 2 | 2 | 857 | 857 | 8/25/28 (replace_path: EK2) | Only these two files name vanilla characters in a way that matters. **Was `shadow_dirty` on the folder until 2026-09-08**: 01_clothes_base, 01_headgear_base, 01_beards_base, 00_custom_hair, 05_headgear_situational, 06_clothes_special and 99_special test `title:h_china` / `title:k_chrysanthemum_throne`, so they were emptied and every character was naked and bald in playtest 2. A dangling title in a portrait trigger is one error-log line; a missing base file undresses the world. Rule: load-bearing `gfx/` folders are `keep`, never `shadow_dirty`. |
| `gfx/court_scene/scene_cultures` | keep | 1 | 0 | 18 | 18 | 2/1/1 | 00_default_cultures.txt is the culture-to-court-scene mechanic; was shadow_dirty, now keep (same lesson as portrait_modifiers). Its 18 dangling title triggers only log. |
| `gfx/interface/illustrations/scripted_illustrations` | keep | 7 | 0 | 40 | 206 | 1/1/3 | ingame.txt defines character_view_bg and the in-game window illustrations; shadowing it blanked them. Was shadow_dirty, now keep; 40 dangling title triggers only log. |
| `common/scripted_character_templates/00_mongol_templates.txt` | shadow | 1 | 1 |  | 74 | 1/41/39 | The only pool template that names vanilla titles and is not called by name from a file this mod keeps. 04_ep2_accolade_character_templates.txt also names one, but common/scripted_effects/00_accolades_scripted_effects.txt looks its 30 templates up by id (scripts/tc_check_shadow_callers.py), and a character template with no body cannot generate a character - so it stays. |
| `common/coat_of_arms/template_lists` | keep | 6 | 0 | 7 | 7 | 0/4/5 | 3636 script errors, but all of class "scope:culture Failed context switch", not dangling titles; only 7 title references. Emptying color_lists/colored_emblem_lists would leave dynamic coat-of-arms generation with no palette. EK2 and Godherja both ship full replacements, never stubs. |
| `common/scripted_triggers` | keep | 135 | 5 | 3450 | 874 | 10/79/82 | 3450 title_links, but 00_realm_laws/00_title_triggers/00_war_and_peace_triggers are core mechanics every kept file calls. Only the named DLC files above are shadowed; the rest need per-reference rewriting, not deletion. |
| `common/scripted_effects` | keep | 166 | 14 | 3038 | 5147 | 22/86/94 | 3038 title_links; same reasoning as scripted_triggers. Only the named content files above are shadowed. |
| `common/on_action` | keep | 65 | 0 | 614 | 880 | 10/44/39 | 614 title_links, 427 of them in game_start.txt. on_action is the hook table the whole game runs on; deleting an entry silently disables a mechanic. Needs rewriting, not shadowing. |
| `common/laws` | keep | 5 | 0 | 29 | 29 | 0/5/4 | 29 title_links in 4 of 5 files - 00_realm_laws and 00_succession_laws are load-bearing mechanics. |
| `common/character_interactions` | keep | 57 | 0 | 179 | 195 | 2/38/49 | 179 title_links in 22 of 57 files - grant/revoke title and vassal interactions are core mechanics. |
| `common/casus_belli_types` | keep | 26 | 0 | 177 | 206 | 2/21/24 | 177 title_links in 10 of 26 files - de jure and event wars are core mechanics. |
| `common/council_tasks` | keep | 9 | 0 | 54 | 59 | 7/7/8 | 54 title_links in 6 of 9 files - the council is a core mechanic. |
| `common/customizable_localization` | keep | 149 | 0 | 360 | 2295 | 8/74/87 | 360 title_links, but the folder is read by vanilla localisation everywhere; deleting an entry turns a live string into a raw key. |
| `common/factions` | keep | 6 | 0 | 21 | 21 | 0/7/5 | 21 title_links - factions are a core mechanic. |
| `common/pool_character_selectors` | keep | 6 | 0 |  | 0 | 0/1/1 | 7959 script errors, none of them title_links: the class is "culture trigger [Failed context switch]" on a scope with no culture, which is a characters/cultures data problem, not vanilla map content. |
| `events` | keep | 32 | 0 | 131 | 270 | 10/22/21 | Every events/ folder except decisions_events and story_cycles is left live and listed in docs/evidence/vanilla_events_naming_titles.csv for the events lane; shadowing an event file whose on_action entry survives is worse than a dangling title (docs/output_bootstrap.md §4). |

**Totals over the writing rows: 271 files written. Joining the whole generated tree against the log (`scripts/tc_error_log_classes.py --mod`) gives 8 823 of the 12 877 `title_links` errors (68.5 %) coming from a file this step now shadows or neutralises.**

## What is deliberately left live

The `keep` rows above are the mechanic databases: 4 054 of the 12 877
`title_links` errors survive this step, in `common/on_action` (614),
`common/scripted_effects` (424), `common/customizable_localization` (360),
`events/dlc/ep3` (355), `common/scripted_triggers` (271),
`common/script_values` (222), `common/character_interactions` (179),
`common/casus_belli_types` (177) and `events/factions` (173). Every one of
those files also holds script the game needs, so the fix is a per-reference
rewrite, not a deletion.

Two hand-offs carry the rest:

- `docs/evidence/vanilla_events_naming_titles.csv` — 101 vanilla event files,
  1 424 title references, 642 of them county or barony tier, for the events
  lane. Regenerate with `scripts/tc_events_naming_titles.py`.
- **A landless vanilla-title layer would halve the residual at one file's
  cost.** 7 532 of the 12 877 name an `e_`, `k_`, `d_` or `h_` title (694
  distinct tags), all of which can exist as `landless = yes` with our
  placeholder capital; only the 5 345 `c_`/`b_` references need a province.
  `common/landed_titles` belongs to the `titles` step, so this lane cannot
  write it; `docs/output_bootstrap.md` §5 already specifies the file.

## Folders another step already owns

`common/landed_titles`, `common/coat_of_arms/coat_of_arms` (`titles`) ·
`history/titles`, `history/provinces`, `history/province_mapping`
(`history_titles`) · `history/characters` (`characters`) ·
`common/culture/{pillars,cultures,name_lists}`, `common/ethnicities`
(`cultures`) · `common/religion/*` (`religions`) · `common/dynasties`,
`common/dynasty_houses` (`dynasties`) · `common/bookmarks`,
`common/bookmark_portraits` (`bookmarks`) · `map_data`,
`common/province_terrain`, `common/defines` (`map`) · `tests` (`tests`) ·
`localization` (`loc`). The step contract forbids two steps sharing an output
subtree, so none of them appears in this table.

Two of them are still broken in ways this lane measured but may not fix:
326 `holy_site_type.cpp: No county found for holy site` at every load
(`common/religion/holy_site_types`, `religions`), and 6 191
`coat_of_arms_utilities.cpp: Dynasty had no founder for coat of arms
generation` (`dynasties`).

## Commands

```
uv run ck2ck3 --config configs/faerun.toml --steps tc_template
uv run scripts/tc_scan_vanilla_refs.py [--atlantis DIR]   # docs/evidence/tc_template_folders.csv
uv run scripts/tc_error_log_classes.py <error.log> --mod <mod dir>
uv run scripts/tc_check_shadow_callers.py <mod dir>       # must report 0
uv run scripts/tc_events_naming_titles.py --mod <mod dir>
scripts/tc_tiger_before_after.sh <scratch dir>
```
