# Converter code assessment (2026-09-07, read-only review of `src/` at commit 6e0fc8e)

All items `verified` by reading the code unless marked `assumed`.

## 1. Per-file inventory

- `convert.py` (14 lines) — entry script, not a CLI. Hardcodes `Faerun/Faerun`, `converted_mods`, `faerun_ck2_to_ck3_converted`, dims `(8192,4096)`, scale `5918/4096`, offset `(-146,26)`.
- `src/converter.py` (62) — `initialize_mod()` rmtree's the destination without confirmation and clones the Atlantis template; descriptor rename is commented out. `convert_mod()` has `initialize_mod` and `convert_map` calls **commented out**; only `convert_titles()` runs.
- `src/conversion/ck2_ck3.py` — empty file, unreferenced.
- `src/utils/paradox_file_parser.py` (215) — regex recursive parser: `file_reader`, `compact_lines`, `regex_paradox_parser`. See §2.
- `src/map/convert_map.py` (48) — calls heightmap/provinces/rivers converters. Reads `map/topology.bpm` (**bug**: file is `topology.bmp`; error is caught and printed, step silently no-ops).
- `src/map/heightmap.py` (129) — grayscale, LANCZOS resize, paste on black canvas at offset, hardcoded 12-point GIMP curve → 256 LUT via `np.interp`, saves 8-bit PNG. No 16-bit, no packed heightmap.
- `src/map/province.py` (48) — RGB, NEAREST resize, paste on `(0,0,0)` canvas (invalid province colour). No lost-province detection.
- `src/map/rivers.py` (249) — vector approach: follows rivers from SOURCE pixels, records tributaries with parent index, scales coordinates, re-snaps tributary heads, redraws with Bresenham, stamps special pixels last. Gaps: SPLIT (yellow) not followed, WATER (magenta) treated as river continuation, `deletion_rate` and `end_pixel_color_type` unused, `interp1d`/`random` imports unused.
- `src/titles/all_titles.py` (357) — pydantic models `Definition`, `BaronyHistory`, `CountyProvinceHistory`, `LandedTitle` + rank subclasses (duplicates of `games/ck2/classes.py` with drift). Reads CK2 `definition.csv` (custom parser, keeps `#` lines), `history/provinces/*`, `map/climate.txt`, `landed_titles`. `convert_titles()` ends in `pass`; `new_mod_folder` unused. Writes nothing.
- `src/titles/definitions.py` (17) — `convert_definitions()` stub with a good docstring on county→barony remap. Never called.
- `src/games/ck2/classes.py` (949) — thorough pydantic schema of CK2 (default.map, terrain, titles, histories, characters, cultures, religions, exhaustive `Modifiers` enum, traits, event/opinion modifiers). Only `Trait` and `CustomModifier` are instantiated anywhere.
- `src/games/ck2/read/modifiers.py` (25), `read/traits.py` (46) — the only working readers. Traits reader raises `ValueError` on any unknown key (brittle). `modifiers.py` has a `__main__` block with a hardcoded path from another machine.
- `src/games/ck2/keywords.py`, `src/games/ck3/classes.py` — empty. No CK3 model, reader or writer exists.
- `src/titles/`, `src/utils/` lack `__init__.py` (implicit namespace packages).
- No tests anywhere. `pyproject.toml` lacked `pillow`/`numpy` and `requires-python` (fixed 2026-09-07).

## 2. Parser (`paradox_file_parser.py`)

- Handles: `key = value`, quoted strings (no escapes, no empty string), nested `{}` via manual brace counting on a whitespace-collapsed string, bare lists (`enum` → flattened), dates kept as raw strings, `yes/no` → bool, int/float, duplicate keys coalesced into lists.
- Comments: captured per line then **discarded**; contradicts the README goal "keep the comments". A `#` inside a quoted string is treated as a comment.
- `<`, `>`, `<=`, `>=`: only detected at block start; whole block kept as raw string. `parse_condition` is dead code.
- Not handled: `@variables`, `[[...]]`, `rgb {}`/`hsv {}` disambiguation, escaped quotes, multi-line strings.
- Unmatched characters are silently skipped one at a time (`content = content[1:]`) — parse errors are masked.
- No writer / round-trip. Encoding hardcoded `utf-8-sig`; CK2 files are Windows-1252 (the Faerun clone even failed a UTF-8→cp1252 conversion on one localisation file). `open_definitions` uses platform default encoding.
- Robustness: low-to-medium. Fine for the flat files tested so far, unfit as the foundation of a round-trip converter.

## 3. Map pipeline

- Heightmap: 8-bit output; CK3 1.19 expects 16-bit `heightmap.png` at 2× province resolution plus `packed_heightmap.png` + `indirection_heightmap.png` described by `heightmap.heightmap` (`verified` on vanilla and on Elder Kings 2 / Godherja). Nothing in the repo produces the packed pair.
- Provinces: NEAREST is the right filter; downscaling can delete small provinces with no report; canvas padding is black.
- Rivers: connectivity preserved by construction (vector + re-snap + Bresenham). Fix SPLIT/WATER handling before trusting it.
- Outputs only `heightmap.png`, `provinces.png`, `rivers.png`. Missing: `definition.csv`, `default.map`, `adjacencies.csv`, `climate.txt`, `island_region.txt`, `geographical_regions/`, `province_terrain`, positions (optional; vanilla and both fantasy mods comment `positions` out in `default.map`, Godherja ships a 2-line file → game generates positions, `assumed`).
- `convert_map()` is never reached from `convert.py`.

## 4. Titles / games

- Two divergent model hierarchies (`titles/all_titles.py` vs `games/ck2/classes.py`).
- Everything is read-side, CK2-side. No CK3 schema, no writer, no validation.

## 5. Orchestration

- `convert_mod()` today: computes a path, reads CK2 data, prints, returns. No disk output.
- Atlantis template: cloned as CK3 TC skeleton (placeholders for vanilla titles/characters so the game boots error-free). Clone step currently disabled.

## 6. Top 5 issues before scaling

1. No tests. Parser is the highest-risk component and has none.
2. No CLI/config; mod-specific numbers live in code.
3. Parser cannot round-trip, drops comments, wrong encoding, silent error skipping.
4. Wiring diverged from intent (commented-out pipeline, duplicate models).
5. No CK3 write layer at all; map pipeline writes 3 of ~10 required files.

## 7. Recommendation

- Keep Python 3.12 + uv (Rust absent locally; schema work and river algorithm worth keeping).
- Replace the regex parser with a tokenizer-based parser that keeps comments and can write back (own implementation with tests, or `jomini` if prebuilt Python wheels exist — `assumed`, verify with `uv pip install jomini`).
- Validate output with `ck3-tiger` as an external step (`assumed` prebuilt binaries on GitHub releases).
- Order: parser + tests → CLI/config → fix `topology.bmp`, re-enable map → CK3 write layer (`default.map`, `definition.csv`, landed_titles) → titles/history.
