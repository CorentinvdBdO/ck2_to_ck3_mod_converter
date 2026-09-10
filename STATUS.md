# STATUS — ck2_to_ck3_mod_converter

Rewritten by `/status` and `/ship`. Overwrite, never append.
Updated: 2026-09-10 13:00 by Claude session (coordinator)

## Lanes in flight
| lane | branch | owner | done when | state | checks |
|---|---|---|---|---|---|
| (none in flight) | | | | | |

Shipped 2026-09-08 (playtest-2 fixes, build 3): naked-fix (portrait_modifiers keep), traits-remap (removed CK2 vanilla traits mapped to CK3 traits: 400 live, 142 deduped, 7 dropped, 1 sexuality), map-paint-seeds (CK2 port-slot seeds, demoted 163→152; terrain paint TGA pair), map-heightmap-detail (212→44,390 levels, coast invariants clamped), events-provenance (13,457 ids classified, bridge table 56 %), research-dna (`docs/research_dna_races.md`). Mod build 483d1d8: **ck3-tiger fatal 0 / error 58; headless -test In Game in 54 s, 172/173 tests** (`claudespace/docs/evidence/tests_faerun_ck2_to_ck3_converted_2026-09-08_224531.md`).

Shipped 2026-09-08 (playtest-1 fixes): tc_template (blank-TC shadows, 271 files), map locators/camera/table/flatmap/foliage, ported removed traits (429), placeholder traditions (392 cultures), bookmark positions, launcher path (claudespace), map-fidelity research. Build 2980004: **In Game, 172/173 tests**.

Shipped 2026-09-08 (game-load): province_mapping entry, test_default bookmark, impassable wasteland, no null land holders, dynasty_houses/credit_portraits shadows, immortal trait, landed-only employers, no employer on rulers. **The generated mod reaches In Game at 1357 headless; 166/173 scripted tests pass.**

Shipped 2026-09-07/08 (all on `main`, pushed): project-kickoff, mappings, mappings-world, foundation, map-physical, traits, localisation, cultures-religions, characters, baronies, titles-history, integration (A+B), dynasty-houses/credit-portraits shadows.

## Repos
| repo | path | base | origin | state |
|---|---|---|---|---|
| converter | `paradox/ck3/ck2_to_ck3_mod_converter` | main 09cf7b2+ | github.com/CorentinvdBdO/ck2_to_ck3_mod_converter (public) | 15 steps (`--list-steps`), full run 72 s, 1368 files + 2 gitignored TGA; ck3-tiger fatal 0; pytest 1058 |
| faerun_ck2_to_ck3_converted (generated) | `paradox/ck3/claudespace/mods/faerun_ck2_to_ck3_converted` | main 483d1d8 | github.com/CorentinvdBdO/faerun_ck2_to_ck3_converted (private) | build 3 2026-09-08 22:30; tiger fatal 0; In Game, 172/173 tests |
| forgotten_kings (submod) | `paradox/ck3/claudespace/mods/forgotten_kings` | main 3812924 | github.com/CorentinvdBdO/forgotten_kings (private, GPL-3.0) | skeleton + roadmap notes + `docs/design_dlc_gating.md` |
| ck3_fantasy_assets | `paradox/ck3/ck3_fantasy_assets` | main | none (local by decision) | skeleton |
| claudespace (workspace) | `paradox/ck3/claudespace` | master 17a247a | none | test harness, headless display, `/fk-push` `/fk-test` `/fk-errors`, `scripts/ck3_bisect.sh` |

## Environment (verified 2026-09-08)
- CK3 1.19.0.6 Windows build under Proton; live user dir inside the Proton prefix; launches via `claudespace/scripts/ck3_launch.sh` (`--headless` = weston + Xwayland on the RTX 5070 Ti).
- CK2 installed at `~/.local/share/Steam/steamapps/common/Crusader Kings II`. Faerûn clone in `Faerun/`.
- ck3-tiger v1.19.0 at `~/.local/bin/ck3-tiger`. Python 3.12, uv, no Rust.
- Git push: token in `../claudespace/tokens` (gitignored), per-repo `credential.helper`; user CorentinvdBdO.

## Blockers and open flags
- ~~Intermittent post-test crash~~ **fixed 2026-09-09 evening**: root cause was the blank `common/flavorization` shadow (no ruler title names → first-tick crash 0x141972299, the user's 18:33 crash). Vanilla flavorization kept: 10/10 launches alive vs 7/10. Landed mercenary/holy-order governments also normalised to feudal (`docs/DECISIONS.md`).
- 1 scripted test fails: ruler-holds-capital invariant (2205/2208 rulers). Playtest 2 confirmed table and bookmarks; found nakedness (fixed), CK2-named traits (fixed), fresh-game crash on unpause (fixed 2026-09-09). Seen in game headless (camera probe): terrain paint, colormap tint, sea floor, trees, settlement positions (builds 8–9). Not yet seen: heightmap detail at close zoom, CK2 port seeds.
- Terrain paint: RLE TGA at half resolution (2.3 + 53 MB) since 2026-09-09; loads and renders in game (headless probe, zoom step 4); close-zoom quality pending the user playtest.
- Ancient non-immortal characters still exist (56 alive ≥150 years without a CK2 immortal marker); ages are accepted by the game but worth a race-lifespan decision.
- Worker agents hang forever at `git commit` (permission prompt nobody answers); coordinator commits. See `~/.claude/harness/NOTES.md`.
- Backlog: `docs/integration_backlog.md` (trait classifier, lifespan overrides, culture gfx chain order, island-region neighbours, TOO LARGE BOX barony, faith icons, bookmark art).
- Open human decisions: `docs/evidence/HANDOFF_integration_B.md` §open questions (8), `docs/step_*.md` open sections.

## Last results
- 2026-09-10 — **asset placement done and seen in game (build 9)**: map-object locators anchor on CK2 `positions.txt` slot 0 for the county-capital barony (2108/2116 accepted by the inside-own-pixels gate), centroid otherwise, with vanilla's measured per-type offset at vanilla's median distance (`median_radius`: siege 9.98 px, stacks 7.10/7.69, combat 13.63 — ours equals vanilla row by row). Headless probe over Waterdeep: the castle and its CoA stand at the CK2 author's town (`b_castle_ward`, X 2345 Y 5724), 240 s soak alive, tiger fatal 0 / error 58 unchanged (`claudespace/docs/evidence/b9_waterdeep_locators.png`, `docs/step_map_assets.md` §5b). Two side fixes: the tree yaw seed was `hash(file)` (per-process random → 1.4 M diff lines per regen; now `crc32`), and the `tests` step now emits the `fae_canary_must_fail` canary the soak looks for.
- 2026-09-10 — `docs/report_map_paint.md`: the paint pipeline as one argument (macro from CK2, micro from vanilla), seven figures. New measurements: interior land under-filled above 0.08 cycles/km (80 vs vanilla 215 levels at 0.1 c/km, below the plain rescale); the detail pass moves land p95 +9.4 % / p99 +20.2 % (`docs/step_map_heightmap.md` §7, backlog).
- 2026-09-10 — **paint half of pre-unpause fidelity done and verified in game** (mod ad8402f): terrain paint and 711,875 trees render; the colormap is rebuilt as a tint measured off vanilla (125-130 per channel, replacing a saturated CK2 satellite image); the sea has vanilla's flat-0 floor with a 24 px shelf (CK2 ships no bathymetry and CK3 painted our shallow sea as sand). Anauroch reads as desert, the Sword Coast as snowy January forest. The camera probe (`scripts/camera_probe.py` plus `REALM_COLOR_MAP_START_ZOOM_STEP = 0`) makes any visual claim checkable headless.
- 2026-09-09 — **first-tick crash fixed** (build 4): 26 neutralised script files → keep; headless soak 300 s alive, 172/173 tests (`claudespace/docs/evidence/tests_faerun_ck2_to_ck3_converted_2026-09-09_101703.md`). Root cause and bisection: `docs/DECISIONS.md`, `docs/tc_template.md`.
- 2026-09-08 — build 3: 15 steps, 1368 files; ck3-tiger fatal 0 / error 58 (41 loc hash collisions, 14 wrong-gender, 2 unknown-field, 1 history; `docs/evidence/tiger_build3_2026-09-08.txt`); pytest 1058; headless -test In Game 54 s, 172/173 (only ruler-holds-capital fails).
- 2026-09-08 — playtest-2 build: 15 steps, 1378 files; headless `-test` In Game, 172/173 (`claudespace/docs/evidence/tests_faerun_ck2_to_ck3_converted_2026-09-08_201524.md`); map research `docs/map_fidelity.md`.
- 2026-09-08 — **first In Game**: headless `-test` run of the converted mod reaches `Setting idler 'In Game'`; 166/173 generated tests pass (`claudespace/docs/evidence/tests_faerun_ck2_to_ck3_converted_2026-09-08_165318.md`).
- 2026-09-08 — crash bisection: 25 launches, root causes in `docs/DECISIONS.md` (empty province_mapping table, missing test_default, employer on rulers); `claudespace/docs/evidence/bisect_*`.
- 2026-09-08 — full run: 13 steps, 61.7 s, 1063 files (`docs/evidence/full_run_2026-09-08.md`); tiger fatal 0 / error 218 accepted classes (`docs/evidence/tiger_full_2026-09-08.md`).
- 2026-09-08 — game loads: map, 419 cultures, 94 faiths, 7130 titles, 18,124 characters; main menu reached without `-test` (`docs/evidence/game_load_2026-09-08.md`).
- 2026-09-08 — vanilla control in the same headless harness: menu 42 s, In Game with `-test` 54 s.

## Next 3
1. **Events** (README §5 step 3): syntactic port of the 1762 `new` events with the decisions lessons — never emit half-converted script live, stub with `# draft:` comments, canary in every test run, distinct mod `name` for test copies. Pre-unpause fidelity (paint + asset placement) is closed.
2. User playtest 3 of build 9 (`docs/playtest.md`): unpause and play; clothes, traits, terrain paint at close zoom, relief, settlement positions, ruler titles.
3. Heightmap detail follow-up (from the report): fill the 0.08–0.3 cycles/km band (de-terrace sigma / frequency-dependent gain) and decide whether the land tails should be clamped to the CK2 source; measure on interior patches only.
