# Handoff: lane `events-decisions`

README §5 step 3, restricted to **decisions** (the small, self-contained
first slice of the events port). Branch `lane/events-decisions`.

## Files changed

New:
- `src/ck2ck3/decisions_vocab.py` — `SCOPE_WORDS`, `TITLE_TAG_RE`, `VocabRow`/`read_vocab_csv`.
- `src/ck2ck3/steps/decisions.py` — the step itself (registry name `decisions`).
- `mappings/triggers.csv`, `mappings/effects.csv`, `mappings/event_targets.csv` — the vocabulary tables (goal 1).
- `scripts/decisions_vocab_survey.py` — surveys Faerûn's own decision usage.
- `scripts/ck3_vocab_ground_truth.py` — the CK3 1.19 "used somewhere" key set (also importable).
- `scripts/build_decisions_vocab_tables.py` — curated core + auto-fallback, writes the three tables.
- `scripts/verify_decisions_vocab.py` — fails (lists misses) on any unverifiable `ck3_key`.
- `tests/test_decisions.py` (21 tests), `tests/test_decisions_vocab.py` (6 tests).
- `docs/step_decisions.md`, `docs/mapping_triggers_effects.md`.
- `docs/evidence/decisions_vocab_survey.csv`, `ck3_vocab_ground_truth.txt`,
  `decisions_convertibility.csv`, `tiger_events_decisions_2026-09-09_summary.txt`.

Modified:
- `src/ck2ck3/steps/__init__.py` — registers `decisions` after `loc`/`traits`, before `tests`.
- `configs/faerun.toml` — `[decisions]` section (`provenance`, `min_score = 0.6`).
- `README.md` — §1 table row, §4/§5 status lines.
- `docs/cli.md` — step table row, `[decisions]` config keys.
- `src/ck2ck3/steps/tc_template.py` — **outside this lane's stated scope, done anyway; see below.**

### The `tc_template.py` touch (why)

`tc_template`'s `OUTPUTS` is auto-derived from `mappings/tc_template.csv` and
included `common/decisions` (it shadows *vanilla* decision filenames there,
unrelated to this step's new `fae_*.txt` files — the two are file-disjoint
and both needed). `tests/test_cli.py::test_step_outputs_do_not_overlap`
treats any shared folder string as a hard conflict, so registering
`decisions.OUTPUTS = ("common/decisions",)` broke that generic test. Fixed
with a one-line, commented exclusion of that single folder from
`tc_template`'s declared `OUTPUTS` tuple; `tc_template.run()` and its actual
CSV-driven shadowing behaviour are **unchanged** — only the registry
contract string list lost one entry. Full reasoning: `docs/step_decisions.md` §4.

## Commands run and results

```
uv run scripts/decisions_vocab_survey.py        # 396 decisions, 519 trigger / 692 effect distinct keys
uv run scripts/ck3_vocab_ground_truth.py        # 86,926 keys
uv run scripts/build_decisions_vocab_tables.py  # triggers 449 rows/112 mapped, effects 675/155, event_targets 57/31
uv run scripts/verify_decisions_vocab.py        # "all mapped ck3_key values verified against CK3 1.19 usage"
uv run pytest -q                                # 1079 passed
bash ci/checks.sh                                # checks green
uv run ck2ck3 --config configs/faerun.toml --out /home/cvdbdo/git/paradox/ck3/wt/_out/events-decisions
                                                  # 1379 files, ~64 s, no crash
scripts/validate_output_mod.sh <out dir> docs/evidence/tiger_events_decisions_2026-09-09_summary.txt
                                                  # fatal 0, error 1193 (baseline 58; +2569 findings all
                                                  # inside common/decisions/, condensed evidence file)
```

## Counts

- 959 decisions total (`docs/evidence/decisions_provenance.csv`). 410 `new` + 239 `modified` = 649 in scope
  per README §5; of those, **396 are character-scope** (`decisions`/`society_decisions`/`plot_decisions`
  groups) and emit; 253 are in the other five groups (title/settlement/offmap/targeted/trade-post — CK3 has
  no landing place for any of them) and get an evidence-only row with a reason.
- Of the 396 emitted: **122 ported live** (`is_shown` as converted), **274 below `min_score`**
  (`is_shown = { always = no }`, content stays inspectable). Mean score 0.51, median 0.50.
- 37 `common/decisions/fae_*.txt` files.
- Vocabulary tables: triggers 449 rows (112 mapped, 60% of Faerûn's own usage instances covered),
  effects 675 rows (155 mapped, 57% instance-weighted), event_targets 57 rows (31 mapped, curated only).
- Every table's `ck3_key` verified against real CK3 1.19 script usage; `tests/test_decisions_vocab.py`
  fails the build if any is not (proven non-tautological by a synthetic-fabricated-key test).
- pytest: 1079 passed (21 new in `tests/test_decisions.py`, 6 new in `tests/test_decisions_vocab.py`, no existing test files edited except the `tc_template.py` fix making `test_step_outputs_do_not_overlap` pass again).
- ck3-tiger over the whole mod: **fatal 0**, error 1193 (baseline 58). All 2569 `common/decisions/`-scoped
  findings are catalogued by class in `docs/evidence/tiger_events_decisions_2026-09-09_summary.txt`;
  every class is understood and traced to a documented limitation (`docs/step_decisions.md` §3), not an
  unexplained regression. No other lane's files or error counts changed.

## Debugging log (why the numbers moved during this session)

Three real bugs were found and fixed via the tiger→fix→rebuild→retest loop
(each is a `docs/step_decisions.md` §2/§3 note, not repeated here in full):
1. CK3 decision files are **flat** (no `decisions = {}` wrapper, unlike CK2)
   — the very first draft wrapped output in a CK2-shaped group key, which
   ck3-tiger read as bogus top-level "fields". Fixed before any score/count
   was ever reported.
2. `_lookup`'s cross-table fallback (trigger table if effect table had
   nothing, or vice versa) produced real wrong output for CK3's genuinely
   trigger-only/effect-only shared-name fields (`wealth`/`piety`/
   `prestige`/`opinion`). Removed; several previously "mapped" rows became
   honest `none` rows instead, which is why the emitted-live count dropped
   over the session (234 → 122) as the port got *more correct*, not less
   complete — the content was never valid CK3, it just used to look mapped.
3. `limit`/`trigger` nested inside an `effect` section inherited the
   parent's kind instead of forcing trigger-context; a trait the `traits`
   step commented out (867 of them) fell through every check in
   `TraitInfo` and was passed through as if already a valid CK3 id. Both
   fixed with a regression test each.

## Open questions for the human

Full list with context: `docs/step_decisions.md` §6. Top three:
1. A nested-schema validator (or a "safe to approximate the whole body" list) for keys like
   `create_character`/`spawn_army` whose CK3 inner schema does not match CK2's — currently `none`d out
   entirely rather than half-converted; likely the single biggest remaining quality lever.
2. CK2 value-level translation (`tier = KING` → `tier_kingdom`, government ids via
   `mappings/government_map.csv`) — `convert_block` only ever rewrites keys today, never values (except the
   trait-id special case).
3. Whether `[decisions] min_score = 0.6` is the right bar given the low mean score (0.51) — raising it hides
   more behind `is_shown = never` without changing what is written; lowering it shows more decisions that
   may misfire in-game.

## Suggested commit message

```
Add step `decisions`: port Faerûn's character-scope CK2 decisions to CK3 1.19

Vocabulary tables (mappings/triggers.csv, effects.csv, event_targets.csv)
built from real CK3 1.19 script usage and verified against it; step
ck2ck3.steps.decisions ports the 396 character-scope decisions (of 959),
scoring each by mapped/total keys and hiding (not dropping) anything below
[decisions] min_score. docs/step_decisions.md, docs/mapping_triggers_effects.md.
```
