# Hand-off: lane `integration-b` — getting the converted mod to boot

Branch `lane/integration-b`, worktree `../wt/integration-b`. Nothing is committed:
the coordinator commits. Full attempt-by-attempt record with every error count:
**`docs/evidence/game_load_2026-09-08.md`**.

## Result

| | |
|---|---|
| before | `EXCEPTION_ACCESS_VIOLATION` in `characterhistory.cpp`, ~1 s into history loading. The mod never reached a menu. |
| after fixes a–d | history loaded in full (18,124 characters), `Setting idler 'Frontend'` — **the main menu** — then an access violation 1 s later on a vanilla geographical-region lookup. |
| after fixes e–f | the frontend crash is gone; with `--args "-test"` the game gets past the frontend and dies **in game setup** instead |
| after fixes g–k | **nine error classes gone, ~95,000 log lines.** The mod now loads completely — map, 419 cultures, 94 faiths, 7,130 titles, all histories, 18,124 characters — and the remaining failure is a single `EXCEPTION_ACCESS_VIOLATION` at `0x14207F7B1` in **game setup**, one second after character history. **Not fixed.** |
| control | **vanilla + `-test` reaches `Setting idler 'In Game'` in 54 s** in this harness, so the harness, the marker and the `-test` argument are all sound and the failure is the mod's |
| launches | 8 of 8 used (attempts 3-7, 9, 10, plus the vanilla control) |
| `ci/checks.sh` | green |
| `uv run pytest -q` | 907 passed |
| ck3-tiger over the result | **no `fatal`**; 3 error classes (41 `localization-key-collision`, 14 `wrong-gender`, 1 `history`) out of 39,530 diagnostics. Report: `docs/evidence/tiger_full_2026-09-08b_summary.txt` (raw + by-kind gitignored alongside it) |

## Proposed commits

| # | message | paths |
|---|---|---|
| 1 | `fix(cultures): emit name-list entries as loc keys, not literals` | `src/ck2ck3/nametokens.py`, `src/ck2ck3/steps/cultures.py`, `src/ck2ck3/steps/loc.py`, `tests/test_nametokens.py`, `tests/test_step_cultures.py`, `tests/test_loc_step.py`, `docs/step_cultures_religions.md`, `docs/formats_loc.md`, `CLAUDE.md`, `docs/DECISIONS.md` |
| 2 | `fix(map): declare the seven graphical regions and put every land province in one` | `src/ck2ck3/map/graphical.py`, `src/ck2ck3/map/ck2read.py`, `src/ck2ck3/map/holdings.py`, `src/ck2ck3/map/writers.py`, `src/ck2ck3/map/build.py`, `tests/test_map_graphical.py`, `tests/test_map_ck2read.py`, `tests/test_map_writers.py`, `docs/formats_map.md` |
| 3 | `fix(map): re-declare every vanilla geographical region the replace_path deletes` | `src/ck2ck3/map/ck2read.py`, `src/ck2ck3/map/config.py`, `src/ck2ck3/map/writers.py`, `src/ck2ck3/map/build.py`, `src/ck2ck3/steps/map.py`, `tests/test_map_writers.py`, `tests/test_map_ck2read.py`, `tests/test_map_baronies_faerun.py`, `docs/formats_map.md` |
| 4 | `fix(map): flatten a region whose CK2 sub-regions overlap` | `src/ck2ck3/map/writers.py`, `tests/test_map_writers.py`, `docs/formats_map.md` |
| 5 | `fix(loc): escape a backslash CK3 has no escape for` | `src/ck2ck3/csvloc.py`, `tests/test_csvloc.py`, `docs/formats_loc.md` |
| 6 | `feat(loc): give every culture its _prefix and _collective_noun key` | `scripts/export_opinion_modifier_map.py`, `mappings/loc_key_renames_cultures_religions.csv`, `overrides/loc_keys.csv`, `docs/step_cultures_religions.md` |
| 7 | `fix(loc): do not emit a reference nothing can resolve` — one commit for both policies, `[loc] custom_loc` and `[loc] named_scope`; they share `convert_code`, the `Report`, the config and the docs section | `src/ck2ck3/loc_codes.py`, `src/ck2ck3/steps/loc.py`, `configs/faerun.toml`, `tests/test_loc_codes.py`, `tests/test_loc_step.py`, `docs/loc_codes.md`, `docs/cli.md`, `docs/DECISIONS.md`, `scripts/bisect_strip_custom_loc.py` |
| 8 | `feat(cultures): fill dynasty_names and localise every name list` — also moves `dynasties` before `cultures` in `DEFAULT_ORDER` | `src/ck2ck3/steps/__init__.py`, `src/ck2ck3/steps/cultures.py`, `src/ck2ck3/steps/dynasties.py`, `src/ck2ck3/port/dynasties.py`, `tests/test_step_cultures.py`, `docs/step_cultures_religions.md`, `docs/cli.md`, `docs/integration_run.md`, `CLAUDE.md`, `docs/DECISIONS.md`, `scripts/export_opinion_modifier_map.py`, `mappings/loc_key_renames_cultures_religions.csv`, `overrides/loc_keys.csv` |
| 9 | `docs(evidence): the game-load attempt log` | `docs/evidence/game_load_2026-09-08.md`, `docs/evidence/HANDOFF_integration_B.md`, `docs/evidence/launch*.log`, `docs/evidence/full_run_2026-09-08_intb*.log` |

Commits 2–4 all touch `map/writers.py::render_geographical_regions` and
`map/build.py`; splitting them costs a rebase. Squashing 2+3+4 into one
`fix(map): geographical regions the game actually accepts` is defensible.

## What each fix was worth (error counts, one boot)

| fix | class it removed | count |
|---|---|---|
| a name tokens are loc keys, ASCII, letter-initial | `culture_name_equivalency.cpp: Missing loc X` | 77,736 |
| a (same) | `pdx_persistent_reader` parse failure of `fae_monsters.txt` + 14 dead name lists + the crash | 36 + the crash |
| b graphical regions | `deferred_database_lookup … 'geographical region'` | 2,611 |
| b (same) | `Province N b_x has no visual geographical region assigned` | 3,904 |
| c flatten overlapping sub-regions | `Region 'X' have multiple entries for the province 'N'` | 130 |
| d escape illegal backslashes | `Illegal localization break character` | 2 |
| e ASCII-fold the token | `Invalid character in key name` | 251 |
| f re-declare vanilla region names | `PostValidate of trigger 'geographical_region' returned false` (+ most of `jomini_script_system: Script system error!`) and the frontend crash | 7,992 (+8,517) |
| g culture `_prefix` / `_collective_noun` | `culture_template.cpp:92`/`:97 Missing localization for X` | 832 |
| h `[loc] custom_loc = "marker"` | `jomini_custom_text.h: Object of type 'character' is not valid for 'X'` — 3,829 of the 4,068 generated `Custom()` calls named something CK3 does not know; the 239 left name the six CK3 **vanilla** custom locs | 47 logged, 3,829 latent |
| i `[loc] named_scope = "marker"` | `pdx_data_factory: Failed to find type '<scope>'` + `pdx_data_localize: Data error in loc string '<key>'` — a reference to a CK2 saved scope nothing saves. One of these was the last log line before attempt 5's access violation | 56 logged, 64,803 latent |

## Remaining error classes, with the reason each stays

| class | count (attempt 3) | reason |
|---|---|---|
| `title_links.cpp: Failed to fetch a valid landed title 'X'` | 12,877 | vanilla `common/coat_of_arms/template_lists`, decisions, flavorization and struggles name vanilla titles; `common/landed_titles` is replaced, as it must be. Unavoidable without replacing every vanilla folder that names a title. |
| `pdx_localize.cpp` duplicate localisation key | 15,303 | Faerûn keys shadowing vanilla strings. Deliberate (`[loc] skip_vanilla_collisions = false`): a total conversion replaces the interface text too. |
| `culture_name_lists.cpp:169: … less than MINIMUM_DYNASTY_NAMES` | 838 → **46** | fix (j) fills 396 of 419 name lists from the CK2 dynasties of the culture (or its group). The 23 left are the animal and undead cultures — CK2 defines no dynasty anywhere in those groups, so filling them is human input, not a derivation. The step warns by name. |
| `dynasty_house_template: house 'X': invalid dynasty 'N'` | 558 | vanilla's 558 houses each name a vanilla dynasty id, and `common/dynasties` is replaced. See open question 1. |
| `holy_site_type.cpp: No county found for holy site 'X'` | 326 | vanilla `common/religion/holy_site_types/00_holy_site_types.txt` names vanilla counties; that folder is deliberately **not** replaced (vanilla faiths must keep loading — `configs/faerun.toml`). |
| `coat_of_arms_dynamic_definitions.cpp` | 244 | same cause as `title_links`. |
| `jomini_dynamicdescription` / `pdx_locstring` `trait_fae_*` | 237 | the `traits` step's grouped traits (`fae_lifespan`, `thayan_tattoo_N`) have no loc key. Belongs to lane `traits`. |
| `bookmark.cpp` | 101 | 82 missing bookmark-character location images, 17 missing bookmark backgrounds (`gfx/interface/bookmarks/bm_*.dds`), 2 bookmark characters with no dynasty. Art, not data — lane `bookmarks` / the assets repo. |
| `map.cpp: Province 'X' is neighbouring but not part of island region 'Y'` | 83 | see open question 2. |
| `culture_trait.cpp: Pillar 'X' is a heritage so it should have a audio parameter` | 67 | one per culture group; CK2 has no audio concept and inventing one is invention. 1 more says a language pillar wants a colour, and a CK2 culture group has none (CLAUDE.md invariant). |
| `culture_template.cpp:317: Gfx culture X in <culture> doesn't match existing sequence in <other culture>` | 1,383 | CK3 builds one global order over `building_gfx`/`clothing_gfx`/`unit_gfx`/`coa_gfx` chains and complains when two cultures disagree on the relative order of two entries. Our per-culture chain is `[the mapped gfx, the western default]`, which contradicts vanilla cultures that order the same pair the other way. Needs a single run-wide chain order in the `cultures` step — out of this lane's scope, and cosmetic (it picks a fallback mesh). |
| `culture_template.cpp:87: Culture missing localization for <id>` | 9 | `cat`, `horse`, `lich`, `mouther`, `red_panda`, `undead_dwarf`, `undeadgiant`, `vampire`, `wight` have no CK2 localisation row at all. See open question 3. |
| `map.cpp: Province N has TOO LARGE BOX` | 1 | one barony's pixels are far apart — a Voronoi artefact in the `map` step. |
| `gfx_caps.cpp: Unknown GfxVendor ID '0x5' for 'llvmpipe'` | 6 | the headless harness, not the mod. Note weston fell back to software rendering on this run where an earlier one got the NVIDIA path. |

## Open questions for the coordinator

0. **The game-setup crash is still open, and the next experiment is designed.**
   Fixes (j) and (k) each removed their error class and left the crash
   untouched. Attempt 10 moved the bookmarks aside and got the same crash, but
   that test is **inconclusive** — with no bookmark, `-test` has nothing to
   start either. The clean version is *one* bookmark with *one* known-good
   character (a `[bookmarks] only = <key>` switch in the config, or a
   hand-trimmed `fae_bookmarks.txt`), then the same launch. After that:
   `history/characters` aside, then `common/traits`, then
   `common/landed_titles` + `history/titles`. Read against the vanilla control
   (54 s to `In Game`). Full reasoning, per-attempt error tables and the
   remaining suspects with counts: `docs/evidence/game_load_2026-09-08.md`
   §12-19.
1. **`common/dynasty_houses`** — replacing it would clear the 558
   `invalid dynasty` errors, but the converter writes nothing there and
   `docs/DECISIONS.md` (2026-09-08) forbids a `replace_path` for a folder the
   converter does not fill — that exact mistake crashed the first boot. Options:
   have the `dynasties` step emit a comment-only file there and add the
   `replace_path`, or accept the 558 errors. I left it alone.
2. **Island regions** — CK3 requires an island region to be closed under land
   adjacency (`Province 'X' is neighbouring but not part of island region 'Y'`,
   83 times). Splitting a CK2 island province into baronies breaks that closure.
   The fix is to grow each island region to the connected component of its
   members, which needs a land-neighbour graph the map pipeline does not build
   today. Affects AI pathfinding only.
3. **The nine cultures with no CK2 localisation** — is a title-cased id an
   acceptable mechanical fallback (`red_panda` → "Red Panda"), or is that
   invention that belongs in an `overrides/*.csv`?
4. **Splitting commits 2–4** — they share two files; say whether to squash.
5. **Step 3 of the brief (run the generated tests) was never reached**, because
   the tests only run once the game is `In Game`. `docs/evidence/tests_first_run.md`
   does not exist for that reason. `../claudespace/scripts/ck3_test.sh
   faerun_ck2_to_ck3_converted --headless` is the command, and it will work the
   moment the game-setup crash is gone — the 107 assertions are already written
   into `tests/fae_generated_tests.txt`.
6. **Two converter defects found but left to their owning lanes**:
   `bookmarks` — `bookmark_fae_49669` and `bookmark_fae_26399` have no
   `dynasty`, and CK3 requires a dynasty or dynasty house on a bookmark
   character (`bookmark.cpp:280`); `titles-history` — 28
   `history.cpp:1094: Title history entry contains no valid entries k_X` and 20
   `titlehistory.cpp: … change its defacto liege despite it being a barony` in
   `history/titles/fae_baronies.txt`.
7. **`culture_template.cpp:317`, 1,383 of them** — CK3 keeps one global order
   over the `building_gfx`/`clothing_gfx`/`unit_gfx`/`coa_gfx` chains, and our
   per-culture `[mapped, western default]` chain contradicts vanilla cultures
   that order the same pair the other way. Cosmetic (it picks a fallback mesh),
   but it wants a single run-wide order in the `cultures` step.
