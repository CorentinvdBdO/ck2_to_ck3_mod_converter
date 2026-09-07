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
| `loc.key_map` | path | optional `ck2_key,ck3_key` rename table, applied last |
| `loc.skip_vanilla_collisions` | bool | drop keys that already exist in CK3 vanilla, default `false` |
| `loc.vanilla_keys` | path | the cached vanilla key set, `docs/evidence/ck3_vanilla_loc_keys.txt` |
| `loc.unknown_codes` | str | `custom` (default) or `marker`, see `docs/loc_codes.md` |

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
| `loc` | `localization` | every CK2 localisation CSV → one CK3 `.yml` per language |

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
(`docs/DECISIONS.md`). On Faerûn: 480 files, 108,986 keys per language, 94 % of
147,711 text codes converted, ~1 s. The formats and every CSV quirk are in
`docs/formats_loc.md`, the text-code table and its coverage in
`docs/loc_codes.md`. Its warnings are the lane hand-off: the codes with no CK3
equivalent, and the `save_scope_as = ck2_from` the event port owes it.

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
