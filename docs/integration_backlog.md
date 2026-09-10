# Integration backlog (coordinator; cleared by lane `integration` after all steps land)

Collected from lane reports 2026-09-07. One line each; delete when done.

- `mappings/modifiers.csv:36` `culture_flex → cultural_acceptance_gain_mult` is culture-scope, illegal in a trait; reclassify.
- Trait classifier: 175 CK2-vanilla traits lack a classification row; 25 of 117 `race_trait` rows are not races (`wiz_*`, `warlock_*`, `origin_*`) yet get `genetic`/`physical`. Fix `docs/evidence/faerun_custom_traits.csv` and rerun.
- 13 `lifespan_<N>` traits currently `immortal = yes`; add `life_expectancy` override rows instead.

Added by lane `integration` (part A, 2026-09-08); each is a named ck3-tiger
class in `docs/evidence/tiger_full_2026-09-08.md` with its count.
- `loc`: 29 `error(localization-key-collision)` — run `ck2ck3.port.loc_hash` over the loc step's keys the way `dynasties` already does, but a title key cannot simply be renamed (1408 CK2 script references resolve because it kept its CK2 name).
- `loc`: 174 `error(choice)` — 27 CK2 faith custom-loc keys (`GetPietyName`, `GetLordSpiritualName`, …) have no slot in CK3's fixed 110-key faith list; map each onto a real key or a `common/customizable_localization` entry.
- `bookmarks`: 15 `warning(bookmarks)` — the bookmark block's `culture`/`dynasty` disagrees with the character's own history at the bookmark date (CK2 states both, in two files, and they differ). Prefer history and warn.
- `characters`: no step converts CK2 `common/event_modifiers`, so 75 `add_character_modifier` values are commented out. Either a `modifiers` step or an `overrides/` mapping onto CK3 ids.
- `characters`: `set_name` is commented out — CK3 `change_first_name` takes a localisation key, and no lane owns minting one for 4 literal names.
- Missing art: 462 `warning(missing-file)` — 133 bookmark illustrations/icons and 329 trait/faith icons. Submod job (`../ck3_fantasy_assets`).
- `git rm --cached docs/evidence/last_run.md` when landing the `.gitignore` line: the file is still in the index.
- Claudespace: unify `ck3_mod_prefix()` (scripts/ck3_paths.sh) with `prefix_for()` (ci/checks.sh).
- Headless display for automated game runs (weston headless + Xwayland) — user decision.
- git-guard hook reads the session cwd, so worker threads in worktrees get blocked; fix hook to honour `cd`/`-C` in the command (see ~/.claude/harness/NOTES.md).

Added by lane `report-paint` (2026-09-10), from `docs/report_map_paint.md` §6.
- `map` heightmap detail: interior land is under-filled above 0.08 cycles/km (80 vs vanilla 215 levels at 0.1 c/km; 10 vs 45 at 0.2), below even the plain rescale there. Try `heightmap_detail_deterrace_sigma_px` < 1.6 and/or a frequency-dependent pass-2 gain; measure on all-land interior patches, never on a coastal crop (`scripts/report_map_paint_plots.py --recompute`).
- `map` heightmap detail: the pass moves land p95 +9.4 % / p99 +20.2 %; decide whether the tails should be clamped to the CK2 source's.
