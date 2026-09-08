# Hand-off — lane `tc-template`, 2026-09-08

Branch `lane/tc-template`, worktree `wt/tc-template`. Nothing committed: the
lane brief forbids `git commit`/`add`, so the coordinator commits.

## What shipped

- **Step `tc_template`** (`src/ck2ck3/steps/tc_template.py`), 3rd in
  `DEFAULT_ORDER`, right after `descriptor`. Writes **271 files in 0.08 s**:
  222 empty shadows and 49 key-only stubs over **60 vanilla folders**;
  12 folders are `keep` with the reason recorded.
- **`mappings/tc_template.csv`** — 73 rows, `path,mode,note`. `path` is a
  vanilla folder or a folder plus a filename glob. Modes: `shadow`,
  `shadow_dirty`, `neutralise`, `keep`, `replace_path`.
- **`src/ck2ck3/tcshadow.py`** — the one owner of "does this file name a
  vanilla map object" and of the two override shapes; the step and the four
  scripts all go through it.
- **`docs/tc_template.md`** — per row: mode, files, written, `title_links`
  errors covered, static references, what Atlantis / EK2 / Godherja do, and why.
- Scripts: `tc_scan_vanilla_refs.py`, `tc_error_log_classes.py`,
  `tc_check_shadow_callers.py`, `tc_events_naming_titles.py`,
  `tc_tiger_before_after.sh`. Evidence CSVs under `docs/evidence/`.
- 21 new tests (`tests/test_tc_template.py`). `uv run pytest -q`: **940 passed**.
  `ci/checks.sh`: **green**.

## Numbers

| | before | after |
|---|---:|---:|
| `title_links.cpp` errors, whole log | 12 877 | 4 054 projected (**−68.5 %**) |
| … from a file the step now blanks | — | 8 823 |
| blanked definitions with a live caller | 534 (first draft) | **0** |
| ck3-tiger `error`/`fatal` over the whole mod | 56 | 56 |
| ck3-tiger by-kind table | identical | identical |

`title_links` is deterministic at load and was measured twice at 12 877. The
projection is a join of the log against the generated tree, not an estimate:
`scripts/tc_error_log_classes.py <error.log> --mod <mod>`.

## Two findings that change how this project measures itself

1. **ck3-tiger never validates vanilla's own files.** A full conversion with
   and without this step gives byte-identical by-kind tables, so the entire
   12 877-error class is invisible to it. Only the game's `error.log` sees it.
   Both facts are now CLAUDE.md invariants.
2. **An empty script block is not neutral.** An empty `scripted_trigger` body
   evaluates **true** in CK3. A neutralised trigger gets `{ always = no }`, a
   neutralised `script_value` a bare `0`.

## Corrections to the brief

- `docs/playtest_2026-09-08.md` **does not exist** anywhere in the repo or in
  the four lane worktrees. Facts were re-derived from the live `error.log`.
- The **13 698 `culture trigger [Failed context switch]` errors are not this
  lane's**. Root cause, `verified`: a scope with no culture, in
  `common/pool_character_selectors/00_clergy.txt:42,46,50`
  (`culture = { has_same_culture_heritage = scope:base.culture }`), alongside
  3 564 `scriptedcharacterdata.cpp:191 No culture had a fulfilled trigger in
  HandleCulture` and 3 564 `:421 Failed to select ethnicity via 'default'`.
  `pool_character_selectors` names zero vanilla titles. This is a
  `cultures`/`characters` data problem — a culture with no ethnicities, or a
  character with no culture.
- No new `replace_path` was added. Every row is pure deletion, so the repo rule
  (a `replace_path` only for a folder we fill) makes it a shadow. The
  `replace_path` mode exists in the table and warns when `[mod] replace_paths`
  disagrees, for the day a lane fills one.

## Also changed outside the lane's own files

`src/ck2ck3/pdx/encoding.py`: `events/` added to `BOM_PREFIXES`. All 536 vanilla
event files carry a UTF-8 BOM and tiger warned about the ones this step writes.
One line, one test, CLAUDE.md updated.

## For the coordinator to decide

1. **A landless vanilla-title layer in the `titles` step would halve the
   residual for one generated file.** 7 532 of the 12 877 name an `e_`, `k_`,
   `d_` or `h_` title — 694 distinct tags, all declarable as
   `landless = yes` with our placeholder capital. Only the 5 345 `c_`/`b_`
   references need a province. `docs/output_bootstrap.md` §5 already specifies
   the file; `common/landed_titles` belongs to `titles`, so this lane could not
   write it.
2. **Should the events lane blank or rewrite?**
   `docs/evidence/vanilla_events_naming_titles.csv`: 101 vanilla event files,
   1 424 title references, 642 county or barony tier. This lane left `events/`
   alone except `events/decisions_events` and `events/story_cycles`, whose
   callers it also blanked.
3. **Two error classes measured here belong to other lanes and are unfixed**:
   326 `holy_site_type.cpp: No county found for holy site` every load
   (`religions`), and 6 191 `coat_of_arms_utilities.cpp: Dynasty had no founder
   for coat of arms generation` (`dynasties`).
4. **A game launch is the only remaining proof.** The lane brief forbade
   launching, so the −68.5 % is a projection from a deterministic load-time
   class, not an observed run. One `-test` launch settles it, and would also
   confirm the Silk Road crash is gone.
5. `scripts/tc_check_shadow_callers.py` is the regression guard for this lane
   but needs a built mod, so it is not in `ci/checks.sh`. Worth adding to
   `docs/integration_run.md` as a post-conversion check.

## What is left

- Nothing in the lane's own scope. 4 054 `title_links` errors remain by
  decision, each attributed to a `keep` row in `docs/tc_template.md`.
