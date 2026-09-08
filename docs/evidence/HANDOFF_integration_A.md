# Hand-off — lane `integration`, part A

Branch `lane/integration`, worktree `wt/integration`. **Nothing is committed**:
this run was told not to run `git commit`/`add`/`stash`/`checkout`/`reset`, so
the whole change set is in the working tree and the commit grouping below is a
proposal, not history. `ci/checks.sh` is green (879 tests).

## Done criteria

| brief item | state |
|---|---|
| BOM change finished, pytest green, CLAUDE.md invariant fixed | **done**, and the rule was *wrong*: it is by path, not by content (below) |
| `replace_path` tiger rejects removed from `configs/faerun.toml` | **nothing to remove** — no `history` line was present, and tiger reports no `replace_path` diagnostic. `tests` was **added** |
| "CK2 not installed" comment fixed | done |
| `docs/evidence/last_run.md` gitignored | done — **coordinator must `git rm --cached` it**, it is still in the index |
| loc renames wired (`scripts/build_loc_key_map.py`, `[loc] key_map`) | done, plus a `mode` column the tables needed |
| trait classifier + `lifespan_<N>` → `life_expectancy` | **not done** — left in `docs/integration_backlog.md`; the trait *plumbing* bug (below) was the bigger one and took the budget |
| full run into the real output mod, timings in `docs/evidence/full_run_2026-09-08.md` | done — 13 steps, 61.7 s, 1063 files, exit 0 |
| tiger: `fatal: 0`, every remaining class justified | done — 0 fatal, **218 errors (was 3691)**, `docs/evidence/tiger_full_2026-09-08.md` |
| step `tests` writing `tests/fae_generated_tests.txt`, `replace_path`, last in `DEFAULT_ORDER`, unit-tested | done — 107 assertions, 13 tests |
| `pytest -q` + `ci/checks.sh` green, `docs/integration_run.md` | done |

## Proposed commits

**1. `fix(pdx): BOM on output script is decided by path, not by content`**
`src/ck2ck3/pdx/encoding.py` · `src/ck2ck3/pdx/__init__.py` ·
`src/ck2ck3/pdx/writer.py` · `src/ck2ck3/context.py` ·
`src/ck2ck3/map/writers.py` · `src/ck2ck3/steps/descriptor.py` ·
`tests/test_pdx_writer.py` · `tests/test_cli.py` · `CLAUDE.md` ·
`docs/DECISIONS.md`
> ck3-tiger warns on a BOM-less pure-ASCII file in any `common/`/`history/`
> database (98 generated files did). `encoding_for(rel)` is now the one table
> both `ctx.write_*` and `ck2ck3.map.writers` read; the flat `map_data` files
> and `descriptor.mod` still get none. `warning(encoding)`: 1 → 0.

**2. `feat(ids): one module for every id two steps must agree on`**
`src/ck2ck3/ids.py` (new) · `src/ck2ck3/steps/cultures.py` ·
`src/ck2ck3/titles/model.py` · `src/ck2ck3/titles/bookmarks.py` ·
`tests/test_cross_step_ids.py` (new) · `tests/test_titles_write.py` ·
`CLAUDE.md` · `docs/DECISIONS.md`
> `titles` wrote `name_list_sun_elf` where `cultures` writes
> `name_list_fae_sun_elf` (2848 `error(missing-item)`), and `bookmarks` wrote
> `fae_dyn_7743` where `dynasties` writes `fae_7743` (80 more, plus 77
> `warning(bookmarks)`). Both go through `ck2ck3.ids` now.

**3. `fix(characters): the known-trait set is the traits step's own output`**
`scripts/build_trait_tables.py` · `mappings/trait_ck2_to_ck3.csv` (new,
generated) · `src/ck2ck3/port/tables.py` · `src/ck2ck3/steps/characters.py` ·
`src/ck2ck3/port/characters.py` · `tests/test_port_tables.py` ·
`tests/test_port_characters.py` · `docs/step_traits.md` ·
`docs/step_characters.md` · `CLAUDE.md` · `docs/DECISIONS.md`
> The set was re-derived from `vanilla_traits.csv` +
> `faerun_custom_traits.csv`, which miss the 38 traits the step dedupes by
> exact CK3 id match and the 7 `status = none` ones it ports as new: 8308
> `trait` lines were commented out for traits the mod declares. Preference
> order is now `ctx.data["traits"]` → `mappings/trait_ck2_to_ck3.csv` → the old
> derivation (which now warns). Character integrity mismatches: 8308 → 0.

**4. `fix(characters): CK3 effect names, and the two things 1.19 cannot express`**
`mappings/character_effects.csv` · `src/ck2ck3/port/characters.py` ·
`src/ck2ck3/port/integrity.py` · `src/ck2ck3/steps/characters.py` ·
`tests/test_port_characters.py` · `tests/test_characters_faerun.py` ·
`docs/step_characters.md` · `CLAUDE.md` · `docs/DECISIONS.md`
> `set_dynasty` does not exist (commented; `set_house` needs a house no step
> mints); `add_spouse`/`remove_spouse`/`add_concubine` are dated-history keys,
> so as effects they become `marry`/`divorce`/`make_concubine` with a
> `character:` scope; `change_first_name` takes a loc key, not a literal.
> `add_character_modifier` values are checked against the 6011 ids CK3
> declares. Same-sex marriages become the integrity class `same-sex spouse`
> (8 in Faerûn) instead of a silent `error(wrong-gender)`.
> `error(unknown-field)`: 29 → 0; `error(missing-item)` modifiers: 75 → 0.

**5. `fix(religions): no holy site on a county the map step dropped`**
`src/ck2ck3/steps/religions.py` · `tests/test_step_religions.py`
> `religions` runs before `titles`, so it reads the `map` step's own
> `docs/evidence/barony_set.csv` and drops the mark with a warning.
> 470 → 469 holy-site links; `error(missing-item): title c_barakuir` gone.

**6. `feat(loc): key_map gets a mode, and one script builds it`**
`scripts/build_loc_key_map.py` (new) · `overrides/loc_keys.csv` (new,
generated) · `src/ck2ck3/steps/loc.py` · `configs/faerun.toml` ·
`tests/test_build_loc_key_map.py` (new) · `tests/test_loc_step.py` ·
`ci/checks.sh` · `docs/cli.md` · `docs/DECISIONS.md`
> `rename` drops the CK2 key (the `traits` hand-off), `copy` keeps it (the
> `titles` and `religions` hand-offs — CK3 needs `k_x` *and* `k_x_adj`, so a
> rename would leave every title nameless). 6891 merged rows, +25 676 loc
> lines, english keys 108 986 → 111 323. `loc_key_renames_characters.csv` is
> deliberately excluded (wrong schema; `dynasties` writes those strings).
> `ci/checks.sh` fails if the merged file is stale.

**7. `feat(tests): a step that turns the generated mod's claims into CK3 tests`**
`src/ck2ck3/steps/tests.py` (new) · `src/ck2ck3/steps/__init__.py` ·
`configs/faerun.toml` · `tests/test_step_tests.py` (new) · `docs/cli.md` ·
`CLAUDE.md` · `docs/DECISIONS.md`
> Last in `DEFAULT_ORDER` because it reads the mod back, so no assertion can
> claim something the mod does not say. 107 tests: 6 bookmark characters
> (alive + holding their title), 50 of 2644 title holders, 50 of 3694 land
> provinces, 1 aggregate over every ruler. `replace_path = "tests"` added.
> Logic ported from `../claudespace/scripts/ck3_gen_tests.py`, with three
> corrections it needed on this mod (below).

**8. `docs(integration): the reference run, the tiger triage, how to redo both`**
`docs/integration_run.md` (new) · `docs/evidence/full_run_2026-09-08.md` (new) ·
`docs/evidence/tiger_full_2026-09-08.md` (new) ·
`docs/evidence/tiger_full_2026-09-08_summary.txt` (new) ·
`scripts/tiger_error_extract.py` (new) · `docs/integration_backlog.md` ·
`.gitignore` · regenerated evidence: `docs/evidence/characters_dropped_keys.csv`,
`characters_integrity.csv`, `ck2_flags.csv`, `title_flavorization.csv`,
`title_holy_sites.csv`, `titles_commented_out.csv`
> The raw tiger report is 359 MB, so `.gitignore` takes
> `docs/evidence/tiger_full_*.txt` and `scripts/tiger_error_extract.py` writes
> the 443 KB `*_summary.txt` that *is* committed (every error/fatal block, plus
> the by-kind index). `.gitignore` also takes `last_run.md` and
> `full_run_*.log`.

## Run counts per step (2026-09-08, 61.7 s, 1063 files, 294 warnings)

| step | s | files | headline |
|---|---|---|---|
| `clean` | 0.01 | 0 | removed 6, kept 4 |
| `descriptor` | 0.00 | 1 | 17 `replace_path` |
| `map` | 52.6 | 21 | 8320×6784, 4265 provinces, 3694 baronies in 2125 counties |
| `cultures` | 0.50 | 28 | 67 groups → 134 pillars, 419 cultures + 419 name lists |
| `religions` | 0.25 | 18 | 94 faiths, 469 holy sites over 254 counties |
| `titles` | 2.10 | 3 | 7130 titles, 11 669 commented |
| `history_titles` | 0.09 | 172 | 3236 histories, 3694 province blocks |
| `bookmarks` | 0.00 | 85 | 17 bookmarks, 82 characters + 82 portrait placeholders |
| `traits` | 0.21 | 170 | 407 ported, 143 deduped, 867 commented, 168 icons |
| `dynasties` | 1.18 | 4 | 11 952 dynasties, 11 951 loc keys, 2 hash collisions resolved |
| `characters` | 2.01 | 80 | 18 124 characters, 47 107 dated blocks, 8 integrity problems |
| `loc` | 1.13 | 480 | 111 323 english keys, 93.9 % of 147 711 codes converted |
| `tests` | 1.63 | 1 | 107 scripted tests at 1357.1.1 |

## Tiger, by class (0 fatal, 218 error, 208 389 warning, 16 088 tips/untidy)

Full justification per class: `docs/evidence/tiger_full_2026-09-08.md`.

| n | class | one-line justification |
|---|---|---|
| 174 | `error(choice)` | 27 CK2 faith custom-loc keys have no slot in CK3's fixed 110-key faith list; `[loc] unknown_codes = "custom"` emits `Custom('GetX')` rather than inventing text. Cosmetic in game. **Backlogged to `loc`.** |
| 29 | `error(localization-key-collision)` | 29 of 111 323 keys share a MURMUR3A hash with a vanilla key. `ck2ck3.port.loc_hash` solves this for dynasties; the `loc` step cannot rename a title key without breaking the 1408 CK2 script references that resolve because it kept its CK2 name. **Backlogged to `loc`.** |
| 14 | `error(wrong-gender)` | 8 same-sex marriages CK3 1.19 cannot express; CK2 flags them itself. Reported as an integrity class; rewriting would be invention. **Accepted.** |
| 1 | `error(history)` | `liege = d_highreach` at a date its liege has no living holder — the CK2 source's own inconsistency, 1 title of 3236. **Accepted.** |
| 462 | `warning(missing-file)` | Icons and bookmark art. **Accepted by the brief** (submod job). |
| 143 | `tips(suggest-localization)` | **Accepted by the brief.** |
| 197 097 | `missing-localization` / `missing-item` / `localization` / `datafunctions` / `duplicate-item` | The localisation surface other lanes still owe: 93.9 % of CK2 text codes converted, 37 067 need a saved scope from the event lane, 1265 CK2 keys are defined twice in CK2 itself. **Accepted.** |
| 319 | `warning(rivers)` | Quantified and owned by the `map` step. **Accepted.** |
| 21 | `warning(history)` | CK2 dated blocks after the character's own death. Source data. **Accepted.** |
| 15 | `warning(bookmarks)` | CK2's bookmark file and its character history state different culture/dynasty. Down from 92. **Backlogged to `bookmarks`.** |
| 5 | `markup` / `exact-duplicate-item` | 4 CK2 strings, 1 CK2 duplicate dynasty. **Accepted.** |

## Three corrections `ck3_gen_tests.py` needed on this mod

Worth pushing back to `../claudespace/scripts/ck3_gen_tests.py` (**not touched**
by this run — outside the lane):

1. Its `history_id.isdigit()` filter drops every bookmark character on a mod
   that mints string ids: it produced **0** tests for our 6. The step instead
   validates the id against the generated `history/characters` keys.
2. It takes land provinces from `definition.csv` minus `default.map` water,
   which on this mod is 3904 ids — 210 of them are CK2 provinces that never
   became a barony and have no county, so `exists = county` would fail by
   design. The step intersects with `history/provinces` (3694).
3. It writes the BOM as a literal `﻿` plus `encoding="utf-8"`; going
   through `ctx.write_text` means the path rule decides and a literal one is
   never doubled.

## Open questions for the coordinator

1. **The generated `tests/` file has never been run in the game.** Whether a
   mod can *add* tests at all is unresolved upstream
   (`../claudespace/docs/ck3_test_framework.md` §3) — we replace vanilla's
   folder, which the doc says works, but nobody has seen a `fae_*` test result.
   Command 5 of `docs/integration_run.md` is the check; it needs the headless
   display decision that is still on the backlog.
2. **`git rm --cached docs/evidence/last_run.md`** must be part of the commit
   that lands the `.gitignore` line, or the file keeps churning.
3. **`docs/evidence/tiger_full_2026-09-08.txt` (359 MB) is in the worktree**
   and now gitignored. Delete it or keep it as a local artefact — this run was
   not allowed to `rm`.
4. **`error(localization-key-collision)` needs a policy, not a patch.** Both
   the collision fix and the `error(choice)` fix mean the `loc` lane changing
   key names or emitting `common/customizable_localization`, and one of them
   conflicts with the standing decision that title loc keys keep their CK2
   names. 203 of the 218 remaining errors are these two classes.
5. **The two trait-classifier backlog items were not done** (175 unclassified
   CK2-vanilla traits; 25 non-race rows classified as races; 13
   `lifespan_<N>` → `life_expectancy`). They are content decisions in
   `docs/evidence/faerun_custom_traits.csv`, and now that the known-trait set
   comes from the `traits` step, fixing them changes what `characters` keeps —
   so they should land together, in a `traits` lane, not here.
6. **`same-sex spouse` is a warning-shaped integrity class.** It makes
   `IntegrityResult.clean` false forever, which is why
   `tests/test_characters_faerun.py` now excludes it explicitly. If the
   coordinator wants `clean` to mean "no converter bug", the class needs its
   own severity.
