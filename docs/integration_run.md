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

**`--out` does not redirect the evidence, and neither does pytest.** The
`events` and `decisions` steps default their evidence path to the *converter
repo's* `docs/evidence/` (`ck2ck3.steps.events.py:207` and its decisions
sibling), not to the run's output dir. So both a full run with
`--out <throwaway dir>` **and a bare `uv run pytest`** leave three committed
CSVs dirty — `events_convertibility.csv`, `events_unmapped_keys.csv`,
`decisions_convertibility.csv`. `verified` 2026-09-10 (lane `water-border`) by
bisecting the suite: `tests/test_cli.py` is the one that does it; the events,
decisions and provenance test files all override the path correctly. A lane
that never touched those steps must `git checkout --` the three before
committing. Real fix: an `--evidence-dir` flag, or a `test_cli` fixture that
overrides the two paths the way the other three test files already do.

Step 1 is skippable on an unchanged checkout: both outputs are committed, and
`ci/checks.sh` fails if `overrides/loc_keys.csv` has drifted from the
`mappings/loc_key_renames_*.csv` it is built from.

Step 5 needs the **`-test` launch argument** to reach `In Game`: a plain launch
stops at `Setting idler 'Frontend'`, the main menu, and nothing starts a game,
so a run waiting for `Setting idler 'In Game'` can only time out.
`../claudespace/scripts/ck3_test.sh` passes it; a bare
`ck3_launch.sh <mod> --marker ingame` does not.

What the game has actually said about this mod, attempt by attempt, with the
error counts each fix removed: **`docs/evidence/game_load_2026-09-08.md`**.
Read it before touching the `map`, `cultures` or `loc` steps — six of its nine
fixes are things ck3-tiger does not report.

## Running from a git worktree — read this first

`wt/<lane>/.venv` is a **symlink to the main checkout's venv**, and that venv
holds an *editable install* whose `.pth` file names one fixed source tree:

```
$ cat .venv/lib/python3.14/site-packages/_editable_impl_ck2_ck3_mod_converter.pth
/home/cvdbdo/git/paradox/ck3/wt/report-paint/src
```

So in any other worktree `uv run ck2ck3` and `.venv/bin/python -m ck2ck3`
import **someone else's `src/`** and silently convert with the wrong code.
It fails silently: the run succeeds, the output looks plausible, and the
lane's change is simply absent (`verified` 2026-09-10, lane `map-assets`:
a full run produced locator files byte-identical to the previous build).

`pytest` is immune — `pyproject.toml` sets `pythonpath = ["src", "."]`, which
wins over the `.pth` — which is exactly why the tests were green while the
run was wrong.

The fix, in a worktree, for **any** command that imports `ck2ck3`:

```sh
PYTHONPATH=$PWD/src .venv/bin/python -m ck2ck3 --config configs/faerun.toml
```

The `.pth` is a plain path line, not an import hook, so `PYTHONPATH` takes
precedence. Check before a long run:

```sh
PYTHONPATH=$PWD/src .venv/bin/python -c "import ck2ck3; print(ck2ck3.__file__)"
```

A repo script that does `sys.path.insert(0, .../src)` relative to its own
file (e.g. `scripts/check_ck2_locator_slots.py`) is already safe.

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

Four step dependencies are real, and each degrades loudly rather than
silently when the producer did not run in the same pass:

- `cultures` after `dynasties` — CK2 keeps dynasty names globally in
  `common/dynasties` with a `culture` on each; CK3 keeps them per name list, so
  `dynasties` hands over `ctx.data["dynasties"]["names_by_culture"]` and
  `cultures` fills each `dynasty_names` from it. Without it every one of the 419
  name lists is empty there, which is `culture_name_lists.cpp:169` for all of
  them and leaves CK3 with no name to mint a generated character's dynasty from.
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
