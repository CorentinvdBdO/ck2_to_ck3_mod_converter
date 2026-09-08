# Regenerating and validating the whole mod

Five commands, from the repository root, with `uv sync --group dev` already
done and `Faerun/` cloned. Nothing here is interactive and nothing needs the
game.

```sh
# 1. the repository-side tables the converter reads (only after a mapping or
#    a trait-classification change; they are committed)
uv run scripts/build_trait_tables.py && uv run scripts/build_loc_key_map.py

# 2. the whole conversion, 62 s, into ../claudespace/mods/faerun_ck2_to_ck3_converted
nohup uv run ck2ck3 --config configs/faerun.toml \
  > docs/evidence/full_run_$(date +%F).log 2>&1 &

# 3. ck3-tiger over the result, then the committable extract of it
#    (the raw report is ~359 MB and gitignored; the extract is ~450 KB)
scripts/validate_output_mod.sh "" docs/evidence/tiger_full_$(date +%F).txt \
  && uv run scripts/tiger_error_extract.py docs/evidence/tiger_full_$(date +%F).txt

# 4. the checks that must be green before /ship
ci/checks.sh

# 5. the scripted tests, in the game, headless (claudespace owns this)
../claudespace/scripts/ck3_test.sh faerun_ck2_to_ck3_converted --headless
```

Step 1 is skippable on an unchanged checkout: both outputs are committed, and
`ci/checks.sh` fails if `overrides/loc_keys.csv` has drifted from the
`mappings/loc_key_renames_*.csv` it is built from.

Step 5 has never been run by this lane — see the open questions in
`docs/evidence/HANDOFF_integration_A.md`.

## What each one is for

| # | command | what it proves |
|---|---|---|
| 1 | `build_trait_tables.py` | `mappings/trait_ck2_to_ck3.csv` matches what the `traits` step writes. It is the **authoritative known-trait set**: the `characters` port comments out a `trait = x` that is not in it, so a stale table silently deletes thousands of traits (`docs/evidence/tiger_full_2026-09-08.md` §3). |
| 1 | `build_loc_key_map.py` | `overrides/loc_keys.csv` = every `mappings/loc_key_renames_*.csv` merged, with the right mode per lane (`rename` drops the CK2 key, `copy` keeps it). Read by the `loc` step as `[loc] key_map`. |
| 2 | `ck2ck3` | 13 steps, 1063 files, 62 s. Per-step seconds, counts and warnings land in `docs/evidence/last_run.md` — read that, not the nohup log. |
| 3 | `validate_output_mod.sh` | ck3-tiger over the mod with the `replace_path` list applied (it reads the `.mod` file it is handed, **not** `descriptor.mod`, which is why the script writes a throwaway copy with `path=`). Appends a by-kind and a by-message summary. |
| 3 | `tiger_error_extract.py` | reduces the 359 MB report to the ~450 KB `*_summary.txt` that is committed: every `error`/`fatal` block verbatim plus that summary tail. |
| 4 | `ci/checks.sh` | pytest, `compileall`, `bash -n`, the docs that must exist, `--list-steps`, and the `loc_keys.csv` freshness check. |
| 5 | `ck3_test.sh` | Runs the `tests/fae_generated_tests.txt` the `tests` step wrote — 107 assertions the mod makes about itself (bookmark characters alive and holding their titles, 50 sampled title holders, 50 sampled land provinces, 1 aggregate over every ruler). Failures go to the user directory's `logs/error.log`; passes are logged nowhere, so the expected count is the number of blocks in the file. |

## Reading the output

| file | what |
|---|---|
| `docs/evidence/last_run.md` | machine-written, every run: steps, seconds, files, counts, warnings. **Gitignored** — the committed record is the dated `full_run_<date>.md`. |
| `docs/evidence/full_run_2026-09-08.md` | the durable per-step record of the reference run |
| `docs/evidence/tiger_full_2026-09-08.md` | every ck3-tiger class with a one-line justification, and the cross-step bugs the report found |
| `docs/evidence/tiger_full_2026-09-08_summary.txt` | the committed extract: every error/fatal block, plus the by-kind counts. The raw report is gitignored |
| `docs/evidence/characters_integrity.csv` | referential problems in `history/characters` (currently one class, 8 rows) |
| `docs/evidence/characters_dropped_keys.csv` | every CK2 key the character port commented out, with the reason and a count |
| `docs/evidence/barony_set.csv` | which counties got a barony — also read by `titles` and `religions` |

## Running one step

```sh
uv run ck2ck3 --config configs/faerun.toml --steps titles,history_titles
uv run ck2ck3 --config configs/faerun.toml --steps tests        # cheap, 1.6 s
uv run ck2ck3 --config configs/faerun.toml --dry-run            # writes nothing
uv run ck2ck3 --list-steps
```

Three step dependencies are real, and each degrades loudly rather than
silently when the producer did not run in the same pass:

- `characters` after `traits` — the known-trait set (falls back to
  `mappings/trait_ck2_to_ck3.csv`, and warns if that is missing too).
- `characters` after `dynasties` — the dynasty id set (falls back to reading
  the CK2 files).
- `tests` **last** — it reads the generated mod back, so with `--steps tests`
  alone it asserts whatever is on disk from the previous run. It skips
  outright, rather than writing an empty file, when there is no bookmark.

`religions` reads `docs/evidence/barony_set.csv` (the `map` step's output) to
avoid a holy site on a county `titles` will drop; with no such file it filters
nothing.
