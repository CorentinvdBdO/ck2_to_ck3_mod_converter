# `ck2ck3` — command line, config, step contract

The converter is one CLI over a registry of steps. Each lane adds a step; the
CLI, the config and the context are shared and stable.

```
uv run ck2ck3 --config configs/faerun.toml               # run the default order
uv run ck2ck3 --config configs/faerun.toml --dry-run     # report, write nothing
uv run ck2ck3 --config configs/faerun.toml --steps map,titles
uv run ck2ck3 --list-steps
uv run -m ck2ck3 --help                                  # same thing
```

| flag | meaning |
|---|---|
| `--config PATH` | TOML config, default `configs/faerun.toml` |
| `--steps a,b` | run these steps in this order; `all` means the default order |
| `--dry-run` | every step runs and reports, nothing is written or deleted |
| `--out DIR` | override `[paths] out`, for a throwaway output folder |
| `--list-steps` | list registered steps (`*` = in the default order) |
| `--no-evidence` | do not write `docs/evidence/last_run.md` |
| `-v` / `-vv` | per-file logging / debug |

Exit codes: `0` success, `2` bad config or unknown step, otherwise the
exception of the failing step (the run log still records where it stopped).

Every run overwrites `docs/evidence/last_run.md` in *this* repository (not in
the generated mod): what ran, per-step seconds, files written, counts, and the
warnings, so a review never depends on scrollback.

**`--out` does not redirect `docs/evidence/`.** A step that writes an evidence
table writes it into this repository whatever `--out` says, and `--no-evidence`
only suppresses `last_run.md`. So a *partial* run into a throwaway folder can
still overwrite a committed evidence file with a thinner version:
`--steps traits,characters` rewrote `docs/evidence/characters_dropped_keys.csv`
427 rows shorter, because without the `titles` step there is no landed-title
hand-off (`verified` 2026-09-08). Check `git status docs/evidence` after a
partial run and restore what you did not mean to regenerate.

## Config keys

Reference file: `configs/faerun.toml`. Relative paths resolve against the
converter repository root, so the CLI behaves the same from any directory.

| key | type | meaning |
|---|---|---|
| `mod.name` | str | mod name in `descriptor.mod` and the launcher |
| `mod.prefix` | str | prefix for every generated identifier and filename (`fae`) |
| `mod.version` | str | `descriptor.mod` version |
| `mod.supported_version` | str | CK3 version mask, `1.19.*` |
| `mod.tags` | list[str] | launcher tags |
| `mod.bookmark_date` | str | CK3 bookmark date, `1357.1.1` |
| `mod.replace_paths` | list[str] | vanilla folders the mod replaces instead of extending |
| `paths.ck2_game` | path | CK2 install (not present on this machine, see `STATUS.md`) |
| `paths.ck2_mod` | path | the CK2 mod being converted |
| `paths.ck3_game` | path | CK3 game files, read-only reference |
| `paths.out` | path | the generated mod repository |
| `map.dimensions` | [int, int] | CK3 province-map size in pixels |
| `map.scale` | float | multiplier applied to the CK2 source pixels |
| `map.offset` | [int, int] | where the scaled CK2 map lands on the CK3 canvas |
| `map.source_dimensions` | [int, int] | optional; CK2 source size, filled by lane `map-physical` |
| `loc.languages` | list[str] | languages to write; omit to auto-pick english + every column over `loc.min_share` |
| `loc.min_share` | float | how full a language column must be to earn a file, default `0.05` |
| `loc.key_map` | path | optional `ck2_key,ck3_key[,mode]` table, applied last. `mode` is `rename` (default, the CK2 key is gone) or `copy` (the text is emitted under **both** keys). Built by `scripts/build_loc_key_map.py`; see below |
| `loc.skip_vanilla_collisions` | bool | drop keys that already exist in CK3 vanilla, default `false` |
| `loc.vanilla_keys` | path | the cached vanilla key set, `docs/evidence/ck3_vanilla_loc_keys.txt` |
| `loc.unknown_codes` | str | `custom` (default) or `marker`, see `docs/loc_codes.md` |
| `loc.named_scope` | str | what a reference to a CK2 saved scope becomes: `marker` (default) or `reference` (the chain unchanged). `reference` needs something to run `save_scope_as`, and nothing ports CK2's events yet; an unresolvable scope is a data error in the loc string that crashed game setup (`docs/evidence/game_load_2026-09-08.md`) |
| `loc.custom_loc` | str | what a CK2 customizable-localisation code becomes: `marker` (default, a visible `<!CK2:…!>`) or `call` (`Custom('name')`). `call` needs `common/customizable_localization`, which nothing emits yet, and a call to a name CK3 does not know is an error per evaluation — it crashed game setup (`docs/evidence/game_load_2026-09-08.md`) |
| `decisions.provenance` | path | `docs/evidence/decisions_provenance.csv` (lane `events-provenance`'s per-id classification) |
| `decisions.min_score` | float | a decision's converted keys mapped ÷ total below this get `is_shown = { always = no }`, default `0.6` |
| `decisions.triggers` / `decisions.effects` | path | `mappings/triggers.csv` / `effects.csv`, overridable for tests |
| `decisions.evidence` | path | `docs/evidence/decisions_convertibility.csv`, overridable for tests |
| `events.enabled` | bool | `false` writes no `events/<prefix>_*.txt` at all, default `true` |
| `events.provenance` | path | `docs/evidence/events_provenance.csv`; only `status = new` rows are ported |
| `events.min_score` | float | an event's converted keys mapped ÷ total below this becomes an inert stub, default `1.0` (`docs/step_events.md` §5) |
| `events.themes_csv` | path | `mappings/event_themes.csv`, CK2 `picture`/`border` → CK3 `theme` |
| `events.default_theme` | string | theme for an event whose picture and border are both unlisted, default `default` |
| `events.triggers` / `events.effects` / `events.evidence` | path | as the `decisions` rows above, overridable for tests |
| `tests.sample` | int | history title holders and land provinces the `tests` step asserts, spread evenly. `0` = every one (3694 provinces) |
| `tests.bookmark` | str | bookmark key to anchor the tests to; unset = the highest-weight one, which is what the game's `-test` starts |

The `[map]` values are placeholders carried over from the deleted `convert.py`
(see below). Lane `map-physical` owns them.

## Step contract

A step is a module `ck2ck3.steps.<name>` that defines three things:

```python
DESCRIPTION = "one line, shown by --list-steps"
OUTPUTS = ("common/landed_titles", "history/titles")   # subtrees this step owns

def run(ctx) -> StepResult:      # a plain string or None is also accepted
    ...
```

Rules:

- **One owner per output subtree.** `OUTPUTS` lists the paths, relative to the
  output mod, that the step writes. Two steps must never share one; a test
  (`tests/test_cli.py::test_step_outputs_do_not_overlap`) enforces it. `("*",)`
  means "the whole mod" and is reserved for `clean`.
- **Never touch the filesystem directly.** Read through `ctx.parse_ck2` /
  `ctx.parse_ck3` / `ctx.read_ck2_csv`, write through `ctx.write_script` /
  `ctx.write_loc` / `ctx.write_text`. That is what makes `--dry-run` honest and
  the run log complete.
- **Never print.** `ctx.info(...)` for progress, `ctx.warn(...)` for anything a
  human must look at (warnings land in the run log). The one-line summary is
  the `StepResult.summary` you return.
- **Register it.** Add the module name to `DEFAULT_ORDER` in
  `src/ck2ck3/steps/__init__.py` if it belongs to the standard run; otherwise
  it stays opt-in through `--steps`.

`StepResult(summary, counts={}, warnings=[], written=[], skipped=False)` —
`counts` is a plain `{name: int}` dict and lands in the run-log table.

### What `ctx` provides

| member | what it gives you |
|---|---|
| `ctx.config` | the parsed `Config` (`ctx.config.prefix`, `ctx.config.bookmark`, …) |
| `ctx.ck2(*parts)` / `ctx.ck3(*parts)` / `ctx.out_path(*parts)` | paths in the CK2 mod, the CK3 game, the output mod |
| `ctx.ck2_script_files()` | every CK2 script file (`common/`, `history/`, `decisions/`, `events/`, `map/*.txt`) |
| `ctx.parse_ck2(*parts)` | `pdx.Document`, cp1252 sniffed |
| `ctx.parse_ck3(*parts)` | `pdx.Document`, UTF-8 |
| `ctx.parse_path(path)` | same, for a path you already have |
| `ctx.read_ck2_csv(*parts)` | one CK2 localisation CSV (`csvloc.LocFile`) |
| `ctx.read_ck2_loc(language)` | the whole localisation folder merged, plus overridden keys |
| `ctx.write_script(rel, block)` | UTF-8 script with the generated-by banner (`header=False` to omit it) |
| `ctx.write_loc(rel, {key: text})` | CK3 `.yml`, UTF-8 with BOM, CRLF |
| `ctx.write_text(rel, text)` | anything that is not a parse tree (CSV, `.mod`) |
| `ctx.ids(name, start=1)` | shared `IdAllocator`: `allocate(key)`, `reserve(id)`, `get(key)`, `mapping()` |
| `ctx.data` | dict for handing results to a later step, keyed by producing step |
| `ctx.info` / `ctx.warn` | logging; warnings are collected into the run log |
| `ctx.dry_run` | true when nothing may be written |

Id allocators exist so two steps never mint the same CK3 province or character
id: ask `ctx.ids("province")` rather than keeping a local counter, `reserve()`
the ids you import unchanged from CK2, then `allocate()` the rest.

## Built-in steps

| step | owns | what it does |
|---|---|---|
| `clean` | `*` | deletes every top-level entry of the output mod that is not protected |
| `descriptor` | `descriptor.mod` | writes `descriptor.mod` from the config |
| `tc_template` | 60 vanilla folders, from `mappings/tc_template.csv` | blanks the vanilla content that names vanilla titles/provinces/characters (`docs/tc_template.md`) |
| `loc` | `localization` | every CK2 localisation CSV → one CK3 `.yml` per language |
| `map` | `map_data`, `common/province_terrain`, `common/defines` | the physical map (`docs/design_map.md` §A) |
| `titles` | `common/landed_titles`, `common/coat_of_arms/coat_of_arms` | the Faerûn de jure tree + placeholder coats of arms (`docs/step_titles.md`) |
| `history_titles` | `history/titles`, `history/provinces` | holders, lieges, laws, governments, holdings |
| `bookmarks` | `common/bookmarks`, `common/bookmark_portraits` | bookmarks, their group and their portrait placeholders |
| `traits` | `common/traits`, `gfx/interface/icons/traits` | CK2 traits ported to CK3 (`docs/step_traits.md`) |
| `dynasties` | `common/dynasties`, `common/dynasty_houses`, one loc file | dynasties, and the only place CK2's literal dynasty names survive |
| `characters` | `history/characters` | all 18124 Faerûn characters, field by field (`docs/step_characters.md`) |
| `cultures` | `common/culture/*`, `common/ethnicities`, … | CK2 culture groups/cultures → pillars, cultures, name lists. **Runs after `dynasties`**: a name list's `dynasty_names` comes from `ctx.data["dynasties"]["names_by_culture"]` |
| `religions` | `common/religion/*` | CK2 religion groups/religions → families, religions, faiths, holy sites |
| `decisions` | `common/decisions` | character-scope CK2 decisions ported to CK3 syntax (`docs/step_decisions.md`). **Runs after `loc`/`traits`** |
| `events` | `events` | Faerûn's 1762 `new` CK2 events ported to CK3 syntax (`docs/step_events.md`). **Runs after `decisions`** (shared vocabulary tables and converter), `loc` and `traits` |
| `tests` | `tests` | CK3 scripted tests asserting the generated mod's own claims; **runs last**, see below |

`[map] title_scaffolding = true` re-enables the throwaway one-barony-per-province
title layer the `map` step used to write into `common/landed_titles`,
`history/titles` and `history/provinces`. It is **off** by default because the
`titles` and `history_titles` steps own those folders; turning it on and running
either step in the same pass makes two steps write one subtree.

### `tests` — the mod asserting its own claims

`tests` is the last step in `DEFAULT_ORDER` because it **reads the generated
mod back**: `common/bookmarks`, `history/titles`, `history/provinces`,
`history/characters` and `map_data/`. So every assertion it writes is
something the earlier steps actually said, and a test file can never claim
something the mod does not. On Faerûn: 107 tests in
`tests/fae_generated_tests.txt`, 1.6 s.

| family | source | assertion |
|---|---|---|
| bookmark characters | `common/bookmarks` ∩ `history/characters` | alive at the bookmark date, and `title:<x> = { holder = this }` |
| title holders | `history/titles`, holder in effect at that date | `holder = character:<id>`, `[tests] sample` of them |
| land provinces | `history/provinces` ∩ non-water `definition.csv` | `is_sea_province = no`, `exists = county/culture/faith` |
| one aggregate | — | every playable ruler of county tier or higher holds its capital barony |

`[mod] replace_paths` must list `tests`, or vanilla's 18 test files run
against this map and fail en masse (they hard-code 1066 ids); the step warns
if it is missing. The grammar and how the game runs these files are in
`../claudespace/docs/ck3_test_framework.md`; run them with
`../claudespace/scripts/ck3_test.sh`.

### `tc_template` — the blank total-conversion layer

`tc_template` is the one step whose `OUTPUTS` is not a literal: it is read from
`mappings/tc_template.csv` at import time, so `--list-steps` and the
no-two-steps-share-an-output test see the real set. Each row is a vanilla
folder — or a folder plus a filename glob — and a mode: `shadow` (empty
same-name override of every file), `shadow_dirty` (only the files that name a
vanilla map object), `neutralise` (keep the top-level keys, drop the bodies) or
`keep` (a documented decision to leave vanilla live). A fifth mode,
`replace_path`, writes nothing and warns when `[mod] replace_paths` does not
list the folder, so the table and the descriptor cannot drift apart.

It runs straight after `descriptor` and before every content step: it only
writes empty shadows of vanilla files, and a later step that really fills one
of those folders must win.

### `loc` key map

`[loc] key_map` is one table, built from the per-lane hand-offs by
`uv run scripts/build_loc_key_map.py` (checked for freshness by
`ci/checks.sh`):

| source table | mode | why |
|---|---|---|
| `mappings/loc_key_renames_traits.csv` | `rename` | CK3 reads a trait's text from `trait_<id>` only; the bare CK2 id is never a loc key |
| `mappings/loc_key_renames_titles.csv` | `copy` | CK3 needs **both** `k_neverwinter` and `k_neverwinter_adj`, and CK2 wrote zero `_adj` keys — a rename would leave every title nameless |
| `mappings/loc_key_renames_cultures_religions.csv` | `copy` | same shape: `ADEPT` stays, `ADEPT_plural` is derived from its text |

`mappings/loc_key_renames_characters.csv` is deliberately **not** merged:
despite the name it is a `ck3_loc_key,ck2_source,ck2_value` record of the
literal dynasty names, and the `dynasties` step writes those strings itself.
On Faerûn the merged table is 6891 rows and adds 25 676 loc lines.

`clean` protects `.git`, `.gitattributes`, `.gitignore`, `LICENSE`,
`README.md`, `descriptor.mod`, `docs`, `thumbnail.png`
(`ck2ck3.ck3mod.PROTECTED`), and refuses to run at all on a folder that has
none of `descriptor.mod`, `README.md` or `.git` — a mistyped `[paths] out`
cannot wipe a source tree.

`descriptor` writes the shape Elder Kings 2 uses (`verified` 2026-09-07):
`version`, a multi-line `tags` block, `name`, `supported_version`, then one
`replace_path` line per replaced folder. No comment banner: that file is read
by the launcher, and neither vanilla nor EK2 puts comments in it.

`loc` writes `localization/<language>/<prefix>_<csv stem>_l_<language>.yml`,
one file per source CSV per language, keys keeping their CK2 name
(`docs/DECISIONS.md`), plus `<prefix>_names_l_<language>.yml` — the `cultures`
step's name-list tokens, handed over through `ctx.data["cultures"]["name_loc"]`
because a CK3 name-list entry is a **loc key** and CK2 keeps the literals in
`common/cultures`, not in a CSV. On Faerûn: 484 files, 155,554 keys per
language (44,231 of them name tokens), 91.0 % of 147,711 text codes converted
with the default `[loc] custom_loc = "marker"` (94.0 % with `"call"`), ~2 s.
The formats and every CSV quirk are in `docs/formats_loc.md`, the text-code
table and its coverage in `docs/loc_codes.md`. Its warnings are the lane
hand-off: the codes with no CK3 equivalent, the customizable localisations
nothing ports, and the `save_scope_as = ck2_from` the event port owes it.

## What happened to `convert.py` and `src/converter.py`

Both were deleted, on purpose:

- `convert.py` was a 14-line script with the mod name, the output folder and
  the map geometry hardcoded. Its four numbers now live in `configs/faerun.toml`
  `[map]`: `dimensions = [8192, 4096]` (the CK3 base map size),
  `scale = 1.4448242187` (`5918/4096`, a 1:1 Faerûn) and `offset = [-146, 26]`
  (the chosen placement of Faerûn on the CK3 canvas). Nothing else was in it.
- `src/converter.py` was the pipeline glue and is replaced by the step registry
  plus `runner.run_steps`. Its `initialize_mod()` cloned
  <https://github.com/bombusfrigidus/Atlantis> as a CK3 total-conversion
  skeleton (vanilla title and character placeholders so the game boots without
  errors) after an unconfirmed `shutil.rmtree` of the destination. The clone
  call was already commented out. If a lane wants that skeleton, it becomes a
  step of its own with `--dry-run` support; the destructive rmtree is replaced
  by `clean`, which protects `.git` and never touches a folder that is not the
  generated mod.

No `map_legacy` step was added. `src/map/convert_map.py` still reads
`map/topology.bpm` while the file is `topology.bmp`, so the heightmap converter
silently no-ops (`docs/converter_code_assessment.md` §3); wrapping that in a
step would have registered a step that cannot work. Lane `map-physical` owns
`src/map/` and adds the real `map` step.
