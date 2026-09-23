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

Added by lane `events` (2026-09-10), coordinator decisions on the hand-off's open questions.
- `events`/`loc`: `[loc] named_scope` stays as is until an event actually runs `save_scope_as` at wire-up time; flip to `"reference"` there, with the events step's `unsaved_scope` gate re-measured. Still open after lane `on-actions` (that lane wired 1 event with no saved scope of its own).
- `events`: `modified` (2911) is the next lane; `docs/evidence/HANDOFF_events.md` §2 is its brief. `common/on_actions` is done (lane `on-actions`, `docs/evidence/HANDOFF_on_actions.md`).

Added by lane `on-actions` (2026-09-23); `docs/evidence/HANDOFF_on_actions.md` is the full brief.
- `on_actions`: extend `mappings/on_actions_ck2_ck3.csv` past its 13/90 mapped `modified` rows — 43 `not researched`, 12 `combat-side scope` (needs a scope hop), 4 `war-ended scope` (needs a scope hop), the rest have no CK3 concept (societies, crusades). `docs/evidence/HANDOFF_on_actions.md` §2.
- `decisions`: same faith/culture value-rewrite gap `events.py` just fixed (`docs/step_decisions.md` §3.3) — `convert_block` still only rewrites keys, never values. Small, mechanical follow-up.


Added by lane `water-border` (2026-09-10).
- `tests/test_cli.py` runs real steps that rewrite other lanes' `docs/evidence/*.csv` on every `pytest` (decisions convertibility, terrain-history baronies, …): point those evidence writes at `tmp_path` in the test, or make the steps write evidence only when the real CLI runs. Own small lane. **Root cause found by lane `on-actions`**: `test_cli_dry_run` (`tests/test_cli.py`) calls `main([..., "--dry-run", "--no-evidence"])` with the default step order and a `config` fixture whose `[events]`/`[on_actions]`/etc. sections are absent, so those steps fall back to the *real* `docs/evidence/*.csv` default paths — and their evidence CSVs are written with a raw `open(path, "w")`, never gated by `ctx.dry_run` the way `ctx.write_script` gates the mod output. Every `uv run pytest -q` (including `ci/checks.sh`) therefore leaves `events_convertibility.csv`/`events_unmapped_keys.csv`/`on_actions_convertibility.csv`/`decisions_convertibility.csv` holding a near-empty fixture result, not real data — a real conversion run (`uv run ck2ck3 --config configs/faerun.toml`) must run *after* the last `pytest` invocation to leave meaningful evidence for a commit. Fix: gate every step's raw evidence `open(..., "w")` behind `if not ctx.dry_run:`, same as `ctx.write_script`.

Added by lane `province-edges` (2026-09-12).
- `map`: `deepen_sea` runs before the detail pass and ramps its shelf from the plain-rescale coast; 159,494 px (0.28 %) of shelf sit off the final (smoothed) coastline. Move the shelf after the coast is final, or feed it the smoothed mask.
- `map`: inside counties the barony borders are still L1 one-pixel steps (4-connected geodesic BFS growth); a smoothed growth front is its own lane (`docs/evidence/HANDOFF_province_edges.md` §4).
- `map`: 21 barony status changes (3705 → 3704 placed, 152 → 153 demoted) trace to `capacity = county_px // 400`, not to the smoothing; review the one demotion in the next barony sheet pass.
