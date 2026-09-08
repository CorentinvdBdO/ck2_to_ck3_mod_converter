# CK2 → CK3 mod converter — agent guide

Read `STATUS.md` first (state). This file: invariants, commands, pointers. Charter: `docs/PROJECT.md`. House rules: `~/.claude/CLAUDE.md`.

## What this repo is
- Python 3.12 + uv. Converts a CK2 total-conversion mod (test subject: Faerûn, cloned in `Faerun/`, gitignored) into a loadable CK3 1.19 mod.
- Output mod lives in `../claudespace/mods/faerun_ck2_to_ck3_converted` (own git repo, generated, never hand-edited). Submod: `../claudespace/mods/forgotten_kings`. Assets: `../ck3_fantasy_assets`.
- CK3 game files: `../claudespace/game_files` (symlink, read-only). CK3 workspace tooling (push to launcher, error.log, checks): `../claudespace`.

## Commands
- `uv sync --group dev` — env. `uv run pytest` — tests (must be green before `/ship`).
- `uv run scripts/faerun_barony_stats.py` — barony/holding statistics (writes `docs/evidence/barony_stats.csv`).
- `nohup uv run scripts/barony_review_sheets.py > docs/evidence/barony_sheets.log 2>&1 &` — per-duchy barony review PNGs (`docs/evidence/baronies/`, 622 sheets, ~90 s).
- `scripts/validate_output_mod.sh "" docs/evidence/tiger_<tag>.txt` — ck3-tiger over the generated mod, with a by-kind summary appended.
- `uv run scripts/collect_ck2_modifier_keys.py` → `uv run scripts/build_modifiers_csv.py` → `uv run scripts/classify_faerun_traits.py` → `uv run scripts/verify_ck3_keys.py` — regenerate the mapping tables in `mappings/` and verify every CK3 key against the 1.19 install (must report `MISSES: 0`).
- `ci/checks.sh` — pytest + syntax + docs present. `/ship` runs it. `ck3-tiger <mod>.mod --game ../claudespace/game_files/..` validates generated mods.
- Convert: `uv run ck2ck3 --config configs/faerun.toml [--steps a,b] [--dry-run]` (`uv run -m ck2ck3` works too). `--list-steps` lists the registry. See `docs/cli.md`.
- `uv run scripts/pdx_scan.py [mod_dir] [--roundtrip N]` — parse every script file of a mod, report failures and timings.
- `uv run pytest -m "not slow"` — fast tests only (the slow ones parse the whole Faerûn clone).

## Rules
- Base branch is `main`. Lanes `lane/<name>`. Never commit on main.
- Converter never invents content. No CK3 equivalent → emit a comment next to the nearest construct. Human input → `overrides/*.csv`, read by the converter.
- Every reader/writer gets a pytest with a fixture snippet. Parser changes need a round-trip test (parse → write → parse equal, comments kept).
- CK2 input encoding is Windows-1252; CK3 output is UTF-8 with BOM for localisation, UTF-8 for script.
- Facts about CK2/CK3 formats go to `docs/` in the same commit (`docs/formats_*.md`), with file:line evidence from `Faerun/` or `game_files/`.
- Long runs (full conversion, image work > 2 min) under nohup with a log in `docs/evidence/`.

## Invariants (bite once, write here)
- CK3 1.19 vanilla map is 9216×4608, heightmap 16-bit at 2×. Custom dims allowed, any multiple of 64 (`assumed`); Elder Kings 2 8256×5504 and Godherja 8192×4096 both ship a **1×** heightmap, so 2× is a vanilla choice, not a rule. Ours: 8320×6784 — painted-extent crop plus a 128 px sea margin (`docs/map_scale.md` §7; `sea_margin_px = 64` gives the older 8192×6656).
- `positions.txt` is optional; `default.map` comments it out in vanilla and major TCs.
- `map_data/default.map` loads the heightmap via `topology = "heightmap.heightmap"`, which points at `packed_heightmap.png` + `indirection_heightmap.png`. **`heightmap.png` alone is not what the game reads.** The converter writes the packed pair itself (`ck2ck3.map.packed_heightmap`, format in `docs/formats_packed_heightmap.md`); no map editor needed.
- Any custom map size needs a `common/defines` override: `WORLD_EXTENTS_X` = width−1, `WORLD_EXTENTS_Z` = height−1. The 16-bit water level is `WATERLEVEL / WORLD_EXTENTS_Y * 65535` (we write 3.8/51 → 4883). Get this wrong and the coastline moves silently.
- `replace_path` is **not** recursive: `history` does nothing for `history/provinces`. `map_data` needs none at all (same-filename override is enough). See `docs/output_bootstrap.md`.
- All three shipped CK3 heightmap/atlas PNGs are stored **bottom-up**.
- Faerûn defines 15,356 baronies but builds 3857 holdings at 1357; barony set = built holdings, never the defined list. 3694 become CK3 provinces, 163 are demoted to comments (`docs/step_map_baronies.md`).
- `map_data/definition.csv` column 5 of a barony row **is** the CK3 barony title id `b_<ck2 name>` — the contract lane `titles-history` reads province ids from. Other rows keep the uppercase CK2 province slug.
- CK2 `history/provinces` `b_x = ct_something` builds a *building*, not a holding: resolving a holding type must skip any value that is not one of the nine CK2 holding types, or the barony vanishes.
- CK2 `positions.txt` is per province; there are no barony coordinates to import.
- The PyPI package `jomini` is unrelated to Paradox parsing (battle simulator). Do not add it.

## Docs
- `docs/PROJECT.md` charter · `docs/DECISIONS.md` · `docs/design_map.md` · `docs/design_races.md` · `docs/mechanics_inventory.md`
- `docs/faerun_ck2_survey.md` · `docs/converter_code_assessment.md` · `docs/races_research.md`
- `docs/step_map_baronies.md` — how CK2 counties become CK3 baronies (seeds, growth, override workflow) · `docs/map_scale.md` — how the scale factor and canvas were measured · `docs/formats_map.md` — CK3 `map_data/` reference · `docs/formats_packed_heightmap.md` — the packed-heightmap format · `docs/output_bootstrap.md` — what makes a custom map boot
- `docs/mapping_modifiers.md` — CK2→CK3 modifier/trait mapping method, scale derivations, CK3 modifier grammar. Tables: `mappings/modifiers.csv`, `mappings/trait_fields.csv`, `mappings/vanilla_traits.csv`.
- `docs/evidence/` — script outputs, review sheets.
