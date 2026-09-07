# CK2 → CK3 mod converter — agent guide

Read `STATUS.md` first (state). This file: invariants, commands, pointers. Charter: `docs/PROJECT.md`. House rules: `~/.claude/CLAUDE.md`.

## What this repo is
- Python 3.12 + uv. Converts a CK2 total-conversion mod (test subject: Faerûn, cloned in `Faerun/`, gitignored) into a loadable CK3 1.19 mod.
- Output mod lives in `../claudespace/mods/faerun_ck3` (own git repo, generated, never hand-edited). Submod: `../claudespace/mods/forgotten_kings`. Assets: `../ck3_fantasy_assets`.
- CK3 game files: `../claudespace/game_files` (symlink, read-only). CK3 workspace tooling (push to launcher, error.log, checks): `../claudespace`.

## Commands
- `uv sync --group dev` — env. `uv run pytest` — tests (must be green before `/ship`).
- `uv run scripts/faerun_barony_stats.py` — barony/holding statistics (writes `docs/evidence/barony_stats.csv`).
- `ci/checks.sh` — pytest + ruff-free syntax check + docs present. `/ship` runs it.
- Convert: `uv run convert.py` (being replaced by `uv run -m ck2ck3 --config configs/faerun.toml`, lane `foundation`).

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
- The PyPI package `jomini` is unrelated to Paradox parsing (battle simulator). Do not add it.

## Docs
- `docs/PROJECT.md` charter · `docs/DECISIONS.md` · `docs/design_map.md` · `docs/design_races.md` · `docs/mechanics_inventory.md`
- `docs/faerun_ck2_survey.md` · `docs/converter_code_assessment.md` · `docs/races_research.md`
- `docs/evidence/` — script outputs, review sheets.
