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
- `uv run scripts/survey_ck2_titles.py` — CK2 title-side tallies (every count quoted in `docs/step_titles.md`).
- `uv run scripts/tiger_titles_check.py` — ck3-tiger over the titles/history output, per diagnostic class and owning lane (writes `docs/evidence/tiger_titles.txt`).
- `uv run scripts/build_loc_key_renames_titles.py` — regenerate `mappings/loc_key_renames_titles.csv` (the hand-off to lane `loc`).
- `uv run scripts/build_loc_key_map.py [--check]` — merge every `mappings/loc_key_renames_*.csv` into `overrides/loc_keys.csv`, which the `loc` step reads as `[loc] key_map`. `--check` is in `ci/checks.sh`.
- Regenerate + validate the whole mod in five commands: `docs/integration_run.md`.
- `uv run scripts/collect_ck2_modifier_keys.py` → `uv run scripts/build_modifiers_csv.py` → `uv run scripts/classify_faerun_traits.py` → `uv run scripts/verify_ck3_keys.py` — regenerate the mapping tables in `mappings/` and verify every CK3 key against the 1.19 install (must report `MISSES: 0`).
- `ci/checks.sh` — pytest + syntax + docs present. `/ship` runs it. `ck3-tiger <mod>.mod --game ../claudespace/game_files/..` validates generated mods.
- Convert: `uv run ck2ck3 --config configs/faerun.toml [--steps a,b] [--dry-run]` (`uv run -m ck2ck3` works too). `--list-steps` lists the registry. See `docs/cli.md`.
- `uv run scripts/pdx_scan.py [mod_dir] [--roundtrip N]` — parse every script file of a mod, report failures and timings.
- `uv run scripts/bisect_strip_custom_loc.py <mod dir> [--restore]` — bisection only: neutralise every `Custom('X')` call in a generated mod's localisation, to test whether unresolvable custom-loc calls are what kills a game load.
- `uv run scripts/survey_faerun_loc.py` → `docs/evidence/loc_quirks.md`; `uv run scripts/collect_ck2_loc_codes.py` → `docs/evidence/ck2_loc_codes.csv` (text-code coverage); `uv run scripts/check_ck3_loc.py <mod>` — validate a generated `localization/` tree (exit 1 on a malformed line).
- `nohup uv run scripts/build_ck3_vanilla_loc_keys.py > docs/evidence/ck3_vanilla_loc_keys.log 2>&1 &` — refresh the 169,096-key vanilla CK3 loc key cache.
- `uv run pytest -m "not slow"` — fast tests only (the slow ones parse the whole Faerûn clone).
- `uv run scripts/survey_cultures_religions.py` → `uv run scripts/seed_culture_overrides.py` → `uv run scripts/export_opinion_modifier_map.py` → `uv run scripts/check_id_collisions.py` → `uv run scripts/validate_cultures_religions.py` — the `cultures`/`religions` pipeline: source survey, first draft of `overrides/*.csv`, tables for the traits + loc lanes, vanilla-id safety, ck3-tiger evidence.

## Rules
- Base branch is `main`. Lanes `lane/<name>`. Never commit on main.
- Converter never invents content. No CK3 equivalent → emit a comment next to the nearest construct. Human input → `overrides/*.csv`, read by the converter.
- Every reader/writer gets a pytest with a fixture snippet. Parser changes need a round-trip test (parse → write → parse equal, comments kept).
- CK2 input encoding is Windows-1252; CK3 output is UTF-8 **with a BOM, decided by path not by content**: `pdx.encoding.encoding_for(rel)` gives one to everything under `common/`, `history/`, `localization/`, `gfx/`, `tests/` and `map_data/geographical_regions/`, and none to the flat `map_data` files or `descriptor.mod`. `ctx.write_script`/`write_text` apply it; a literal leading `U+FEFF` in the text is consumed rather than written twice.
- Facts about CK2/CK3 formats go to `docs/` in the same commit (`docs/formats_*.md`), with file:line evidence from `Faerun/` or `game_files/`.
- Long runs (full conversion, image work > 2 min) under nohup with a log in `docs/evidence/`.

## Invariants (bite once, write here)
- CK3 1.19 vanilla map is 9216×4608, heightmap 16-bit at 2×. Custom dims allowed, any multiple of 64 (`assumed`); Elder Kings 2 8256×5504 and Godherja 8192×4096 both ship a **1×** heightmap, so 2× is a vanilla choice, not a rule. Ours: 8320×6784 — painted-extent crop plus a 128 px sea margin (`docs/map_scale.md` §7; `sea_margin_px = 64` gives the older 8192×6656).
- `positions.txt` is optional; `default.map` comments it out in vanilla and major TCs.
- `map_data/default.map` loads the heightmap via `topology = "heightmap.heightmap"`, which points at `packed_heightmap.png` + `indirection_heightmap.png`. **`heightmap.png` alone is not what the game reads.** The converter writes the packed pair itself (`ck2ck3.map.packed_heightmap`, format in `docs/formats_packed_heightmap.md`); no map editor needed.
- Any custom map size needs a `common/defines` override: `WORLD_EXTENTS_X` = width−1, `WORLD_EXTENTS_Z` = height−1. The 16-bit water level is `WATERLEVEL / WORLD_EXTENTS_Y * 65535` (we write 3.8/51 → 4883). Get this wrong and the coastline moves silently.
- `replace_path` is **not** recursive: `history` does nothing for `history/provinces`. `map_data` needs none at all (same-filename override is enough). See `docs/output_bootstrap.md`.
- All three shipped CK3 heightmap/atlas PNGs are stored **bottom-up**.
- Faerûn has **67 culture groups / 419 cultures** and **15 religion groups / 94 religions** (`verified`; the survey's "~495 cultures" and "~130–184 religions" were upper bounds).
- A CK2 culture *group* carries only `graphical_cultures` and `alternate_start` — **no colour**. A CK3 language pillar requires one.
- `common/culture/pillars`, `common/culture/traditions`, `common/ethnicities` and `common/modifier_definition_formats` are **not** `replace_path`s: an id emitted there must not collide with vanilla (Faerûn's `gur` and `mari` cultures do).
- ck3-tiger wants a **UTF-8 BOM on every script file under `common/` or `history/`, pure ASCII or not** (`verified` 2026-09-08: 98 generated ASCII files drew `warning(encoding)`). Vanilla agrees everywhere except `history/titles` (56 of 183) and `history/provinces` (91 of 177), which ship BOM-less ASCII files — laxity in two folders, not a rule. All 18 `game/tests/*.txt` have one and 17 are ASCII.
- Faerûn defines 15,356 baronies but builds 3857 holdings at 1357; barony set = built holdings, never the defined list. 3694 become CK3 provinces, 163 are demoted to comments (`docs/step_map_baronies.md`).
- `map_data/definition.csv` column 5 of a barony row **is** the CK3 barony title id `b_<ck2 name>` — the contract lane `titles-history` reads province ids from. Other rows keep the uppercase CK2 province slug.
- CK2 `history/provinces` `b_x = ct_something` builds a *building*, not a holding: resolving a holding type must skip any value that is not one of the nine CK2 holding types, or the barony vanishes.
- CK2 `positions.txt` is per province; there are no barony coordinates to import.
- CK3 localisation has no `FROM` scope; CK2 `From…` codes need a saved scope (`docs/loc_codes.md`).
- CK3 text formats are named in `game/gui/preload/textformatting.gui`; there is no `#Y`, yellow is `#M`.
- The PyPI package `jomini` is unrelated to Paradox parsing (battle simulator). Do not add it.
- **`common/bookmark_portraits` must not be empty.** A bookmark character with no file there crashes CK3 (ck3-tiger `fatal(crash)`, "This causes a crash in CK3 1.13"). Write a placeholder named after the character's `name` value.
- **`ck3-tiger` reads the `.mod` file you pass it, not `descriptor.mod`** — without the `replace_path` lines in that file every replaced vanilla file loads and you get thousands of phantom "redefined" diagnostics. `--game` wants the install dir, not its `game/` subfolder.
- CK3 `history/titles` allows **no top-level keys**; `liege` must be a strictly higher tier and must have a **living** holder at that date or the line is ignored.
- CK2 `landed_titles` `capital` is a **province id**, not a title. The province→county link is `title = c_x` inside the province-history file.
- **Any id two steps derive independently belongs in `ck2ck3.ids`.** Both halves look internally consistent, so the failure only shows up in ck3-tiger or the game: `titles` writing `name_list_sun_elf` while `cultures` writes `name_list_fae_sun_elf` was 2848 `error(missing-item)`, and `bookmarks` writing `fae_dyn_7743` while `dynasties` writes `fae_7743` was another 80.
- The **known-trait set** the `characters` port filters by is `mappings/trait_ck2_to_ck3.csv` — the `traits` step's own output — never a re-derivation from `vanilla_traits.csv` + `faerun_custom_traits.csv`, which miss the 38 traits deduped by exact CK3 id match and the 7 `status = none` ones ported as new (8308 wrongly commented `trait` lines).
- CK3 1.19 has **no `set_dynasty` effect** (`set_house = dynasty_house:<id>` is the runtime form, and CK2 has no cadet houses to mint one from), **no same-gender marriage** (`add_spouse` between two of one gender is `error(wrong-gender)` and ignored), and `change_first_name` takes a **localisation key**, never a literal name. `add_spouse`/`remove_spouse`/`add_concubine` are dated-**history** keys; as effects they are `marry`/`divorce`/`make_concubine`, each taking a `character:<id>` scope.
- `replace_path = "tests"` is **mandatory** for a total conversion: vanilla's 18 `tests/*.txt` hard-code 1066 ids (character `122`, `k_croatia`) and fail en masse otherwise.
- A **bare script token that does not start with a letter breaks the CK3 parser, and it does not recover**: everything after it in the file is lost. Faerûn's `modron` names are serial numbers (`2BD71SF2`), and one of them cost the 14 `name_list_*` blocks that followed it in `fae_monsters.txt` — then an `EXCEPTION_ACCESS_VIOLATION` in `characterhistory.cpp`, because a character of one of those 14 cultures had no name list (`verified` 2026-09-08, `docs/evidence/game_load_2026-09-08.md`).
- A CK3 **name-list entry is a localisation key, not a display string** (`male_names = { Akarakay … }` + ` Akarakay:0 "Akarakay"`), and **a localisation key must be ASCII**: 0 of vanilla's 55,948 name keys hold a non-ASCII byte, and vanilla spells Björn `BjO_rn`, Åke `A__ke`. Letters, digits, `_`, `-` and `'` pass. `ck2ck3.nametokens` does the fold; the literals go to `localization/<lang>/<prefix>_names_l_<lang>.yml`.
- CK3 accepts exactly four localisation escapes — `\n` (47,430 uses in vanilla english), `\t` (224), `\"` (97), `\\` (5). Anything else is `localization_reader.cpp:111: Illegal localization break character` and **truncates the string**.
- CK3 wants **three** localisation keys per culture: `<id>`, `<id>_prefix`, `<id>_collective_noun` (vanilla `localization/english/culture/cultures_l_english.yml:460-462`, all three "Norse"). CK2 supplies only the first.
- `replace_path = "map_data/geographical_regions"` deletes **all 592** vanilla regions, and vanilla scripts, GUI and achievements name them. Every vanilla region name must be re-declared (empty is fine, `generate_modifiers = yes` kept for the 8 that have it — vanilla traits reference the `<region>_development_growth_factor` they mint), and the **seven `graphical_*` regions must exist and cover every land province** or every vanilla building asset's `graphical_regions` filter fails and every province logs "has no visual geographical region assigned". A null from one of these killed the frontend one second after the main menu (`dlc_fp1_region_core_mainland_scandinavia`).
- CK3 rejects a region that reaches one duchy or province through **two** sub-regions (`geographical_region.cpp: Region 'X' have multiple entries for the province 'N'`). CK2 tolerates it — `yehimal_region` shares 8 duchies with `tabot_region` and friends — so such a parent has to be emitted flat.
- A CK3 name list **must** carry `dynasty_names` (`MINIMUM_DYNASTY_NAMES = 2`, `common/defines/00_defines.txt:1145`; the define's own comment says culture-**group** names count toward it). CK2 keeps dynasty names globally in `common/dynasties` with a `culture` each, so step `dynasties` runs before `cultures` and hands them over — with none, all 419 name lists drew `culture_name_lists.cpp:169` and CK3 had no name to mint a generated character's dynasty from.
- `Setting idler 'Frontend'` in `debug.log` is the **main menu**; `Setting idler 'In Game'` needs the game to actually start a bookmark, which headlessly means the `-test` launch argument (`../claudespace/scripts/ck3_launch.sh … --args "-test"`). Without it a run waiting for `In Game` can only time out. **Vanilla with `-test` reaches `In Game` in 54 s** in this harness (`verified` 2026-09-08), so that is the control: a mod that does not is the mod's fault, not the harness's.

- `history/province_mapping` must never be empty when `history/provinces` has any block: the 1.19 loader crashes (null deref) on an empty table. `history_titles` writes one entry (`docs/DECISIONS.md` 2026-09-08). A `replace_path` that leaves a folder empty is only safe when the engine tolerates an empty table; test with a game launch, not just ck3-tiger.

## Docs
- `docs/PROJECT.md` charter · `docs/DECISIONS.md` · `docs/design_map.md` · `docs/design_races.md` · `docs/mechanics_inventory.md`
- `docs/faerun_ck2_survey.md` · `docs/converter_code_assessment.md` · `docs/races_research.md`
- `docs/map_scale.md` — how the scale factor and canvas were measured · `docs/formats_map.md` — CK3 `map_data/` reference · `docs/formats_packed_heightmap.md` — the packed-heightmap format · `docs/output_bootstrap.md` — what makes a custom map boot
- `docs/formats_loc.md` — CK2 localisation CSV quirks and the CK3 `.yml` rules. `docs/loc_codes.md` — CK2 text code → CK3 data function table, evidence and coverage (94.0 %).
- `docs/step_cultures_religions.md` — the `cultures` + `religions` steps: id scheme, every derived default, the CK2-flag→doctrine table, what the neighbouring lanes own. Tables: `mappings/culture_fields.csv`, `mappings/religion_fields.csv`, `mappings/opinion_modifier_map.csv`, `mappings/loc_key_renames_cultures_religions.csv`. Human input: `overrides/*.csv`.
- `docs/step_map_baronies.md` — how CK2 counties become CK3 baronies (seeds, growth, override workflow) · `docs/map_scale.md` — how the scale factor and canvas were measured · `docs/formats_map.md` — CK3 `map_data/` reference · `docs/formats_packed_heightmap.md` — the packed-heightmap format · `docs/output_bootstrap.md` — what makes a custom map boot
- `docs/step_titles.md` — steps `titles` / `history_titles` / `bookmarks`: rules, derivations, counts, open questions · `docs/formats_titles.md` — CK3 title/history/bookmark facts with file:line · `docs/mapping_world.md` — the field tables (`mappings/title_fields.csv`, `government_map.csv`)
- `docs/mapping_modifiers.md` — CK2→CK3 modifier/trait mapping method, scale derivations, CK3 modifier grammar. Tables: `mappings/modifiers.csv`, `mappings/trait_fields.csv`, `mappings/vanilla_traits.csv`.
- `docs/integration_run.md` — regenerate and validate the whole mod in five commands; which steps depend on which.
- `docs/evidence/game_load_2026-09-08.md` — getting the mod to boot in the real game: every launch attempt, what error.log said, what was fixed
- `docs/evidence/full_run_2026-09-08.md` — the reference full run, per step · `docs/evidence/tiger_full_2026-09-08.md` — every ck3-tiger class with its justification, and the cross-step bugs it found
- `docs/evidence/` — script outputs, review sheets.
