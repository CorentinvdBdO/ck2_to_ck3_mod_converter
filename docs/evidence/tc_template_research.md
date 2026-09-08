# Lane `tc-template` — research log, 2026-09-08

What was measured, in the order it was measured, with the command that produced
it. Conclusions and the resulting decision table are in `docs/tc_template.md`;
the hand-off is `docs/evidence/HANDOFF_tc_template.md`.

Short names: `VANILLA` = `/home/cvdbdo/.local/share/Steam/steamapps/common/Crusader Kings III/game`
(1.19) · `ATL` = Atlantis (`github.com/bombusfrigidus/Atlantis`, cloned to the
session scratchpad) · `EK2` = workshop `2887120253` (0.19.1) · `GH` = workshop
`2326030123` (0.4.0.5) · `LOG` = the live error.log inside the Proton prefix
(`docs/playtest.md` names the path).

Everything below is `verified` unless labelled `assumed`.

---

## 0. Two corrections to the brief

1. **`docs/playtest_2026-09-08.md` does not exist**, in `main` or in any of the
   four lane worktrees (`find … -name '*playtest*'`). The playtest facts used
   here were re-derived from `LOG` directly. `docs/playtest.md` (the tutorial)
   is a different file.
2. **The 13 698 `culture trigger [Failed context switch]` errors are not caused
   by vanilla content naming vanilla titles**, so this lane cannot fix them.
   Measured on the In Game run (`LOG` before it rotated at 19:53): 24 641
   `Failed context switch` lines, 16 773 of them on a bare `culture` scope, and
   the script locations are `common/pool_character_selectors/00_clergy.txt`
   (7959), `common/scripted_effects/00_pool_effects.txt` (5349),
   `common/coat_of_arms/template_lists/color_lists.txt` (3154),
   `common/scripted_triggers/00_coa_triggers.txt` (3105). The failing lines are
   `culture = { has_same_culture_heritage = scope:base.culture }`
   (`00_clergy.txt:42,46,50`) — a scope with **no culture**, next to 3564
   `scriptedcharacterdata.cpp:191 No culture had a fulfilled trigger in
   HandleCulture` and 3564 `:421 Failed to select ethnicity via 'default'`.
   That is a `cultures`/`characters` data problem (a culture with no
   ethnicities, or a character with no culture), not vanilla map content.
   `common/pool_character_selectors` names **zero** vanilla titles, provinces or
   characters. Handed off, not fixed here.

---

## 1. What the running game actually trips over

`LOG`, load of the 2026-09-08 build, `uv run scripts/tc_error_log_classes.py`:

| n | class |
|---|---|
| 15 293 | `pdx_localize.cpp` duplicate localisation key (lane `loc`) |
| **12 877** | **`title_links.cpp:214` Failed to fetch a valid landed title** |
| 3 433 | `history.cpp` referencing non-existent character in script link |
| 1 398 | `culture_template.cpp` missing culture localisation |
| 483 | `pdx_persistent_reader.cpp` failed to read key reference |
| 326 | `holy_site_type.cpp` no county found for holy site |
| 244 | `coat_of_arms_dynamic_definitions.cpp` |

Plus, only on the run that reached In Game (a later launch truncated the log):
33 061 `jomini_script_system.cpp` script errors, 9 386 `culture_trait.cpp`,
8 440 `characterhistory.cpp`, 6 191 `coat_of_arms_utilities.cpp` ("Dynasty had
no founder for coat of arms generation").

`title_links` is the class this lane owns, and it is **deterministic at load**:
the same 12 877 in two separate runs.

### 1.1 The 12 877, by tier

| tier | occurrences | distinct tags | can a landless title fix it? |
|---|---|---|---|
| `c_` | 4 583 | 421 | no — a county needs a barony, a barony needs a province |
| `e_` | 2 909 | 78 | yes |
| `k_` | 1 939 | 167 | yes |
| `d_` | 1 687 | 449 | yes |
| `h_` | 997 | 5 | yes — `h_` is a real above-empire tier in 1.19 |
| `b_` | 762 | 280 | no |
| total | 12 877 | 1 400 | 7 532 (58.5 %) rescuable, 5 345 not |

`h_china`, `h_dar_al_islam`, `h_eastern_roman_empire`, `h_india`,
`h_roman_empire` are declared in `VANILLA/common/landed_titles/`; a tier regex
of `[ekdcb]_` misses all five, which is why `ck2ck3.tcshadow` reads the id set
out of vanilla instead of guessing at the shape.

### 1.2 The 12 877, by owning folder (top rows)

`common/scripted_triggers` 3450 · `common/scripted_effects` 3038 ·
`common/decisions` 717 · `common/on_action` 614 · `common/scripted_modifiers`
426 · `common/culture/creation_names` 409 · `common/customizable_localization`
360 · `events/dlc/ep3` 355 · `common/great_projects/types` 341 ·
`events/decisions_events` 337 · `common/script_values` 261 ·
`common/decisions/dlc_decisions` 208 (+206 in its `tgp/` subfolder) ·
`common/character_interactions` 179 · `common/casus_belli_types` 177 ·
`events/factions` 173. Full list:
`docs/evidence/tc_template_title_links.csv` (418 files).

**Folder is the wrong granularity.** The single worst file is
`common/scripted_triggers/10_tgp_japan_triggers.txt` (2965 of the folder's
3450) and the second is `common/scripted_effects/00_major_decisions_scripted_effects.txt`
(933 of 3038) — both pure regional content inside a folder whose other files are
core mechanics (`00_realm_laws`, `00_title_triggers`, `00_war_and_peace_triggers`).
So the decision table addresses files as well as folders.

---

## 2. Static inventory of the vanilla tree

`uv run scripts/tc_scan_vanilla_refs.py --atlantis <clone>` →
`docs/evidence/tc_template_folders.csv`, 321 folders, **137 with at least one
vanilla map reference**. Id sets read out of vanilla: 17 081 titles, 244
cultures, 191 faiths/religions.

Biggest offenders by static reference count (folders another step already owns
marked *owned*):

| folder | files | dirty | refs | note |
|---|---|---|---|---|
| `common/landed_titles` | 11 | 11 | 19 795 | *owned* (`titles`), `replace_path`ed |
| `history/titles` | 183 | 183 | 17 338 | *owned* (`history_titles`), `replace_path`ed |
| `map_data/geographical_regions` | 3 | 3 | 7 020 | *owned* (`map`), `replace_path`ed |
| `common/scripted_effects` | 166 | 44 | 5 147 | mechanic + content mixed |
| `common/customizable_localization` | 150 | 14 | 2 295 | read by vanilla loc everywhere |
| `common/coat_of_arms/coat_of_arms` | 10 | 4 | 2 025 | *owned* (`titles`) |
| `history/characters` | 207 | 84 | 1 354 | *owned* (`characters`) |
| `common/on_action` | 66 | 14 | 880 | hook table |
| `common/scripted_triggers` | 135 | 32 | 874 | mechanic + content mixed |
| `common/decisions` | 35 | 23 | 799 | content |
| `common/script_values` | 114 | 25 | 573 | mechanic + content mixed |
| `gfx/portraits/portrait_modifiers` | 33 | 8 | 522 | 507 `character:` links to developer easter eggs |
| `common/culture/creation_names` | 3 | 2 | 437 | content |
| `common/religion/holy_site_types` | 2 | 1 | 398 | *owned* (`religions`), **still broken** — see §6 |

Caveat on two columns: the CSV's `culture` and `faith` counts are token
matches against the vanilla culture and faith id sets, so a common word that is
also an id inflates them. They are indicative, not exact. The title, province,
character and dynasty columns are exact.

---

## 3. What the three reference total conversions do

`replace_path` lines: `ATL` 10, `EK2` 22, `GH` 21 — quoted in full in
`docs/output_bootstrap.md` §1.2, unchanged since.

The finding this lane turns on is not the `replace_path` lists but the
**empty-shadow pattern**, which `docs/output_bootstrap.md` §2.1 explicitly said
Atlantis does not use:

* `EK2` ships **149** script files under 400 bytes that sit at a vanilla path;
  `GH` ships **137**. Atlantis ships 5.
* Their folders are almost exactly the ones this lane wants:
  `gfx/portraits/portrait_modifiers` (EK2 15), `common/story_cycles` (13 / 10),
  `tests` (9 / 12), `common/decisions` (7), `common/flavorization` (6 / 3),
  `events/decisions_events` (5 / 9), `common/scripted_character_templates`
  (4 / 4), `common/situation/situations` (GH 5),
  `common/customizable_localization` (3 / 10), `common/scripted_effects` (3 / 5),
  `common/scripted_triggers` (2 / 6), `common/coat_of_arms/dynamic_definitions`
  (2 / 3), `gfx/map/map_object_data` (3 / 5).
* `EK2/tests/*` is shadowed **file by file**, not by `replace_path` — a second
  witness that override-by-filename is enough to delete a vanilla database.

`EK2/common/situation/catalysts/catalysts.txt` (120 bytes) is the other shape,
and the one that made this lane safe: it keeps every vanilla catalyst **key**
and empties the body (`catalyst_win_any_war_within_the_region = {}`). That is
the `neutralise` mode.

Atlantis stays a reference only, for the reasons already recorded in
`docs/output_bootstrap.md` §3 (no licence, `supported_version="1.16.*"`, two
neutralisation paths that no longer exist in 1.19, covers 1 of 11
`landed_titles` files, cannot boot as cloned). Re-checked 2026-09-08: still
true, still no LICENSE file.

---

## 4. The failure mode that shaped the design

First implementation blanked 272 vanilla files outright.
`uv run scripts/tc_check_shadow_callers.py <mod>` — take the top-level keys of
every blanked file, then scan every vanilla file the mod **keeps** for those
keys — found **534 blanked definitions with a live caller**, e.g.

* `accolade_archer_character` … 30 templates in
  `common/scripted_character_templates/04_ep2_accolade_character_templates.txt`,
  called by `common/scripted_effects/00_accolades_scripted_effects.txt`;
* `can_have_japanese_appointment_succession_law_trigger` in
  `10_tgp_japan_triggers.txt`, called by `common/laws/00_succession_laws.txt`;
* `setup_tributaries_effect`, `hre_elector_list_save_effect`,
  `spawn_historical_characters_effect`, all called by
  `common/on_action/game_start.txt` or `yearly_on_actions.txt`.

Blanking those would swap 12 877 dangling-title errors for a set of silently
disabled mechanics — a worse trade. Fixes applied:

1. **`neutralise` instead of `shadow`** for every content file inside a
   mechanic database (27 rows). Keys kept, bodies dropped.
2. **An empty trigger body evaluates TRUE in CK3**, so a neutralised
   `scripted_trigger` gets `{ always = no }` and a `script_value` gets a bare
   `0`, not `{}`. Without that,
   `can_have_japanese_appointment_succession_law_trigger` would have gone from
   "broken" to "always allowed".
3. **`04_ep2_accolade_character_templates.txt` reverted to kept**: a character
   template with no body cannot generate a character, and neutralising it would
   not have helped.

After: **0 blanked definitions with a live caller**
(`docs/evidence/tc_template_orphaned_callers.csv`, empty).

---

## 5. Result

`uv run ck2ck3 --config configs/faerun.toml --out <scratch> --steps tc_template`
writes **271 files** in 0.08 s: 222 empty shadows and 49 key-only stubs over 60
vanilla folders, 12 folders deliberately kept.

Projected `title_links` drop, measured by joining the log against the generated
tree (`scripts/tc_error_log_classes.py --mod <scratch>`):
**8 823 of 12 877 (68.5 %)** come from a file the step now shadows or
neutralises. The residual 4 054 sits in kept mechanic folders —
`common/on_action` 614, `common/scripted_effects` 424,
`common/customizable_localization` 360, `events/dlc/ep3` 355,
`common/scripted_triggers` 271, `common/script_values` 222,
`common/character_interactions` 179, `common/casus_belli_types` 177,
`events/factions` 173 — and in `events/`, which is handed to the events lane
(`docs/evidence/vanilla_events_naming_titles.csv`: 101 files, 1 424 references,
642 of them county or barony tier).

---

## 6. Left for someone else

* **A landless vanilla-title layer** would resolve the other half at one file's
  cost: 7 532 of the 12 877 name an `e_`/`k_`/`d_`/`h_` title, all of which can
  exist as `landless = yes` with our placeholder capital. `common/landed_titles`
  belongs to the `titles` step, so this lane cannot write it. See
  `docs/output_bootstrap.md` §5, which already specifies the file.
* **`common/religion/holy_site_types`**: 326 `holy_site_type.cpp: No county
  found for holy site` at every load. `docs/output_bootstrap.md` §5 specifies
  the fix (re-emit all vanilla keys with the county repointed) and the
  `religions` step owns the folder; it is not done.
* **`coat_of_arms_utilities.cpp`, 6 191** "Dynasty had no founder for coat of
  arms generation" — the `dynasties` step.
* **The culture/ethnicity context failures** of §0.2 — `cultures` /
  `characters`.
