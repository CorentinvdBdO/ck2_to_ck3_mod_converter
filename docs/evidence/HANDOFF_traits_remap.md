# Handoff — lane `traits-remap`

User correction implemented: vanilla CK2 traits CK3 removed must be **mapped
to an existing CK3 trait**, never ported as a new CK2-named trait. Full
rationale, tables and rules: `docs/step_traits.md` rules 1-3;
`docs/DECISIONS.md` (new 2026-09-08 entry, second one that date, supersedes
the first).

## Files changed

Code:
- `src/ck2ck3/traits/port.py` — `Plan.classify_vanilla` rewritten: `exact`/
  `approx`/`nearest` all dedupe (no live trait); new `Plan.drops` /
  `Plan.sexualities` lists replace `Plan.near_equivalents`.
- `src/ck2ck3/traits/conflicts.py` — **new**: `TraitConflicts` +
  `read_trait_conflicts`, reads `opposites`/`group`/`level` from CK3
  `common/traits/*.txt`.
- `src/ck2ck3/traits/__init__.py`, `src/ck2ck3/traits/convert.py` — export/
  comment updates for the above.
- `src/ck2ck3/steps/traits.py` — header/hand-off/counts updated for the new
  decision kinds (`drop`, `sexuality`), `near_equivalents` removed.
- `src/ck2ck3/port/tables.py` — `Tables.trait_drop_reason` /
  `trait_sexuality` (+ accessors), fallback loader rewritten for the 5
  statuses, `TRAIT_ID_MAP` loader now applies `approx` rows (only
  `drop`/`sexuality` are excluded — the opposite of the old behaviour).
- `src/ck2ck3/port/characters.py` — `CharacterPort.conflicts` field,
  `_convert_trait_key` (sexuality/drop/conflict resolution for the plain
  `trait = x` key; `add_trait`/`remove_trait` unchanged).
- `src/ck2ck3/steps/characters.py` — builds `TraitConflicts` from
  `ctx.ck3("common","traits")` and passes it to `CharacterPort`.
- `scripts/build_trait_tables.py`, `scripts/verify_ck3_keys.py` — updated for
  the new statuses (`verify_ck3_keys.py` skips `sexuality` rows, which hold a
  sexuality value, not a trait id).

Tables:
- `mappings/vanilla_traits.csv` — header rewritten; 13 `none` rows split into
  `nearest` (5), `sexuality` (1, `homosexual`), `drop` (7).
- `mappings/trait_ck2_to_ck3.csv`, `mappings/trait_id_map.csv`,
  `mappings/loc_key_renames_traits.csv`, `docs/evidence/traits_unported.csv`,
  `docs/evidence/traits_groups.csv` — regenerated (`scripts/build_trait_tables.py`).
- `overrides/loc_keys.csv` — regenerated (`scripts/build_loc_key_map.py`).
- `mappings/character_effects.csv` — `trait` row's note updated.

Docs: `docs/step_traits.md` (rules 1-3 rewritten, rules 2-8 renumbered to
4-10, counts/tiger table/open-question refreshed), `docs/DECISIONS.md` (new
entry), `docs/mapping_modifiers.md` (status counts), `README.md` §1 traits
row. `docs/integration_backlog.md` has **no** existing item naming
`homosexual` (searched full history) — nothing to remove there.

Tests: `tests/test_traits.py`, `tests/test_port_characters.py`,
`tests/test_port_tables.py`, `tests/test_mappings.py` updated;
`tests/test_trait_conflicts.py` new (conflicts module unit tests); new
character-port tests for sexuality/drop/conflict resolution (incl. one
against the real CK3 install).

## Verification

- `uv run pytest -q` — **1019 passed**, 0 failed.
- `bash ci/checks.sh` — green.
- Full run: `uv run ck2ck3 --config configs/faerun.toml --out /home/cvdbdo/git/paradox/ck3/wt/_out/traits-remap`
  — 1376 files, 296 warnings, ~71s. `traits` step: 400 ported (117 race), 142
  deduped, 7 dropped, 1 sexuality, 867 commented.
- `grep -lE '^\s*(cruel|envious|kind|proud|wroth|charitable|slothful)\s*=\s*\{' <out>/common/traits/*` → **empty** (pass).
- `trait = sadistic` in `history/characters`: **614**. `trait = compassionate`: **280**.
- `sexuality = homosexual`: **22**.
- `# CK2 trait x: no CK3 counterpart` comments: **140** (122 envious, 8 stressed, 4 experimenter, 3 cavalry_leader, 1 light_foot_leader, 2 more envious in dated blocks).
- Conflicts resolved: **6** (`docs/evidence/tiger_traits_remap.txt` / `characters_dropped_keys.csv`: 3× `absent` dup, 1× `creature_human` dup, 1× `legit_bastard`→`legitimized_bastard` vs already-held `bastard` opposite, 1× a second id deduping to `strategist`).
- ck3-tiger (`scripts/validate_output_mod.sh <out> docs/evidence/tiger_traits_remap.txt`): **fatal 0**, **error 58** (41 `localization-key-collision`, 14 `wrong-gender`, 2 `unknown-field(sexuality)`, 1 `history` — none new from this lane except the 2 `sexuality` ones, see below). Baseline `docs/evidence/tiger_full_2026-09-08.md` had **218** errors under a different `[loc]` config, so this is not a regression.
- Standalone `traits`-step-only ck3-tiger (`docs/evidence/tiger_traits.txt`, regenerated): fatal/error 0, 229 `warning(missing-file)` (was 255), 20 `tips(suggest-localization)` (was 31).

## Open item for the coordinator

- **ck3-tiger 1.19.0 does not know the CK3 `sexuality` history key**
  (`error(unknown-field): unknown token 'sexuality'`), even though vanilla
  itself uses it 20+ times (`game/history/characters/persian.txt:5760`).
  `strings ~/.local/bin/ck3-tiger` has no `sexuality` string at all —
  confirmed tool gap, not a converter bug. Recorded as
  `docs/step_traits.md` open question 10. Nothing to fix on our side.
- `docs/integration_backlog.md` has no `homosexual` item to resolve (checked
  full git history of the file) — the task description may have referred to
  the open question in `docs/step_traits.md`'s old rule 1 downgrade table,
  which this lane's rewrite already superseded.

## Suggested commit message

```
traits: map removed CK2 vanilla traits to existing CK3 traits, not new ones

User correction: approx/nearest dedupe like exact (no CK2-named trait is ever
emitted), homosexual becomes a CK3 sexuality key, the remaining 7 unmappable
vanilla traits are dropped with a specific comment, and a dedupe that would
give a character two conflicting CK3 traits (duplicate/opposite/leveled
sibling) keeps the CK2-first-listed one. 400 live traits (was 429), 142
deduped (was 121), 6 conflicts resolved over 18,124 Faerûn characters.
```
