# CK2 → CK3 mod converter — agent guide

Read `STATUS.md` first (state). This file: invariants, commands, pointers. Charter: `docs/PROJECT.md`. House rules: `~/.claude/CLAUDE.md`.

## What this repo is
- Python 3.12 + uv. Converts a CK2 total-conversion mod (test subject: Faerûn, cloned in `Faerun/`, gitignored) into a loadable CK3 1.19 mod.
- Output mod lives in `../claudespace/mods/faerun_ck2_to_ck3_converted` (own git repo, generated, never hand-edited). Submod: `../claudespace/mods/forgotten_kings`. Assets: `../ck3_fantasy_assets`.
- CK3 game files: `../claudespace/game_files` (symlink, read-only). CK3 workspace tooling (push to launcher, error.log, checks): `../claudespace`.

## Commands
- `uv sync --group dev` — env. `uv run pytest` — tests (must be green before `/ship`).
- `uv run scripts/faerun_barony_stats.py` — barony/holding statistics (writes `docs/evidence/barony_stats.csv`).
- `uv run scripts/collect_ck2_modifier_keys.py` → `uv run scripts/build_modifiers_csv.py` → `uv run scripts/classify_faerun_traits.py` → `uv run scripts/verify_ck3_keys.py` — regenerate the mapping tables in `mappings/` and verify every CK3 key against the 1.19 install (must report `MISSES: 0`).
- `ci/checks.sh` — pytest + syntax + docs present. `/ship` runs it. `ck3-tiger <mod>.mod --game ../claudespace/game_files/..` validates generated mods.
- Convert: `uv run ck2ck3 --config configs/faerun.toml [--steps a,b] [--dry-run]` (`uv run -m ck2ck3` works too). `--list-steps` lists the registry. See `docs/cli.md`.
- `uv run scripts/pdx_scan.py [mod_dir] [--roundtrip N]` — parse every script file of a mod, report failures and timings.
- `uv run scripts/survey_faerun_loc.py` → `docs/evidence/loc_quirks.md`; `uv run scripts/collect_ck2_loc_codes.py` → `docs/evidence/ck2_loc_codes.csv` (text-code coverage); `uv run scripts/check_ck3_loc.py <mod>` — validate a generated `localization/` tree (exit 1 on a malformed line).
- `nohup uv run scripts/build_ck3_vanilla_loc_keys.py > docs/evidence/ck3_vanilla_loc_keys.log 2>&1 &` — refresh the 169,096-key vanilla CK3 loc key cache.
- `uv run pytest -m "not slow"` — fast tests only (the slow ones parse the whole Faerûn clone).

## Rules
- Base branch is `main`. Lanes `lane/<name>`. Never commit on main.
- Converter never invents content. No CK3 equivalent → emit a comment next to the nearest construct. Human input → `overrides/*.csv`, read by the converter.
- Every reader/writer gets a pytest with a fixture snippet. Parser changes need a round-trip test (parse → write → parse equal, comments kept).
- CK2 input encoding is Windows-1252; CK3 output is UTF-8 with BOM for localisation, UTF-8 for script.
- Facts about CK2/CK3 formats go to `docs/` in the same commit (`docs/formats_*.md`), with file:line evidence from `Faerun/` or `game_files/`.
- Long runs (full conversion, image work > 2 min) under nohup with a log in `docs/evidence/`.

## Invariants (bite once, write here)
- CK3 1.19 vanilla map is 9216×4608, heightmap 16-bit at 2×. Custom dims allowed (Elder Kings 2: 8256×5504).
- `positions.txt` is optional; `default.map` comments it out in vanilla and major TCs.
- Packed heightmap pair comes from the in-game map editor; the converter writes only `heightmap.png` (16-bit).
- Faerûn defines ~15k baronies but builds ~3.8k holdings; barony set = built holdings, never the defined list.
- CK2 `positions.txt` is per province; there are no barony coordinates to import.
- CK3 localisation has no `FROM` scope; CK2 `From…` codes need a saved scope (`docs/loc_codes.md`).
- CK3 text formats are named in `game/gui/preload/textformatting.gui`; there is no `#Y`, yellow is `#M`.
- The PyPI package `jomini` is unrelated to Paradox parsing (battle simulator). Do not add it.

## Docs
- `docs/PROJECT.md` charter · `docs/DECISIONS.md` · `docs/design_map.md` · `docs/design_races.md` · `docs/mechanics_inventory.md`
- `docs/faerun_ck2_survey.md` · `docs/converter_code_assessment.md` · `docs/races_research.md`
- `docs/formats_loc.md` — CK2 localisation CSV quirks and the CK3 `.yml` rules. `docs/loc_codes.md` — CK2 text code → CK3 data function table, evidence and coverage (94.0 %).
- `docs/mapping_modifiers.md` — CK2→CK3 modifier/trait mapping method, scale derivations, CK3 modifier grammar. Tables: `mappings/modifiers.csv`, `mappings/trait_fields.csv`, `mappings/vanilla_traits.csv`.
- `docs/evidence/` — script outputs, review sheets.
