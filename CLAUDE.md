# CK2 → CK3 mod converter — agent guide

Read `STATUS.md` first (state). This file: invariants, commands, pointers. Charter: `docs/PROJECT.md`. House rules: `~/.claude/CLAUDE.md`.

## What this repo is
- Python 3.12 + uv. Converts a CK2 total-conversion mod (test subject: Faerûn, cloned in `Faerun/`, gitignored) into a loadable CK3 1.19 mod.
- Output mod lives in `../claudespace/mods/faerun_ck2_to_ck3_converted` (own git repo, generated, never hand-edited). Submod: `../claudespace/mods/forgotten_kings`. Assets: `../ck3_fantasy_assets`.
- CK3 game files: `../claudespace/game_files` (symlink, read-only). CK3 workspace tooling (push to launcher, error.log, checks): `../claudespace`.

## Commands
- `uv sync --group dev` — env. `uv run pytest` — tests (must be green before `/ship`).
- `uv run scripts/faerun_barony_stats.py` — barony/holding statistics (writes `docs/evidence/barony_stats.csv`).
- `uv run scripts/survey_ck2_titles.py` — CK2 title-side tallies (every count quoted in `docs/step_titles.md`).
- `uv run scripts/tiger_titles_check.py` — ck3-tiger over the titles/history output, per diagnostic class and owning lane (writes `docs/evidence/tiger_titles.txt`).
- `uv run scripts/build_loc_key_renames_titles.py` — regenerate `mappings/loc_key_renames_titles.csv` (the hand-off to lane `loc`).
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
- CK3 1.19 vanilla map is 9216×4608, heightmap 16-bit at 2×. Custom dims allowed, any multiple of 64 (`assumed`); Elder Kings 2 8256×5504 and Godherja 8192×4096 both ship a **1×** heightmap, so 2× is a vanilla choice, not a rule. Ours: 8192×6656 (`docs/map_scale.md`).
- `positions.txt` is optional; `default.map` comments it out in vanilla and major TCs.
- `map_data/default.map` loads the heightmap via `topology = "heightmap.heightmap"`, which points at `packed_heightmap.png` + `indirection_heightmap.png`. **`heightmap.png` alone is not what the game reads.** The converter writes the packed pair itself (`ck2ck3.map.packed_heightmap`, format in `docs/formats_packed_heightmap.md`); no map editor needed.
- Any custom map size needs a `common/defines` override: `WORLD_EXTENTS_X` = width−1, `WORLD_EXTENTS_Z` = height−1. The 16-bit water level is `WATERLEVEL / WORLD_EXTENTS_Y * 65535` (we write 3.8/51 → 4883). Get this wrong and the coastline moves silently.
- `replace_path` is **not** recursive: `history` does nothing for `history/provinces`. `map_data` needs none at all (same-filename override is enough). See `docs/output_bootstrap.md`.
- All three shipped CK3 heightmap/atlas PNGs are stored **bottom-up**.
- Faerûn defines ~15k baronies but builds ~3.8k holdings; barony set = built holdings, never the defined list.
- CK2 `positions.txt` is per province; there are no barony coordinates to import.
- The PyPI package `jomini` is unrelated to Paradox parsing (battle simulator). Do not add it.
- **`common/bookmark_portraits` must not be empty.** A bookmark character with no file there crashes CK3 (ck3-tiger `fatal(crash)`, "This causes a crash in CK3 1.13"). Write a placeholder named after the character's `name` value.
- A CK3 script file with **non-ASCII content needs a UTF-8 BOM** (ck3-tiger `warning(encoding)`); vanilla `common/landed_titles` and `common/bookmarks` files have one, pure-ASCII `history/titles` files do not.
- **`ck3-tiger` reads the `.mod` file you pass it, not `descriptor.mod`** — without the `replace_path` lines in that file every replaced vanilla file loads and you get thousands of phantom "redefined" diagnostics. `--game` wants the install dir, not its `game/` subfolder.
- CK3 `history/titles` allows **no top-level keys**; `liege` must be a strictly higher tier and must have a **living** holder at that date or the line is ignored.
- CK2 `landed_titles` `capital` is a **province id**, not a title. The province→county link is `title = c_x` inside the province-history file.

## Docs
- `docs/PROJECT.md` charter · `docs/DECISIONS.md` · `docs/design_map.md` · `docs/design_races.md` · `docs/mechanics_inventory.md`
- `docs/faerun_ck2_survey.md` · `docs/converter_code_assessment.md` · `docs/races_research.md`
- `docs/map_scale.md` — how the scale factor and canvas were measured · `docs/formats_map.md` — CK3 `map_data/` reference · `docs/formats_packed_heightmap.md` — the packed-heightmap format · `docs/output_bootstrap.md` — what makes a custom map boot
- `docs/step_titles.md` — steps `titles` / `history_titles` / `bookmarks`: rules, derivations, counts, open questions · `docs/formats_titles.md` — CK3 title/history/bookmark facts with file:line · `docs/mapping_world.md` — the field tables (`mappings/title_fields.csv`, `government_map.csv`)
- `docs/mapping_modifiers.md` — CK2→CK3 modifier/trait mapping method, scale derivations, CK3 modifier grammar. Tables: `mappings/modifiers.csv`, `mappings/trait_fields.csv`, `mappings/vanilla_traits.csv`.
- `docs/evidence/` — script outputs, review sheets.
