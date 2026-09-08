# STATUS — ck2_to_ck3_mod_converter

Rewritten by `/status` and `/ship`. Overwrite, never append.
Updated: 2026-09-08 22:40 by Claude session (coordinator)

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
- 1 scripted test fails: ruler-holds-capital invariant (2205/2208 rulers). Playtest 2 confirmed table and bookmarks; found nakedness (fixed) and CK2-named traits (fixed). Unverified in game: terrain paint rendering on a non-vanilla canvas, heightmap detail look, CK2 port seeds.
- Terrain paint pair is 2 × 226 MB uncompressed TGA: gitignored in the generated mod repo (GitHub 100 MB limit); RLE / half-res untested. Human call pending.
- Ancient non-immortal characters still exist (56 alive ≥150 years without a CK2 immortal marker); ages are accepted by the game but worth a race-lifespan decision.
- Worker agents hang forever at `git commit` (permission prompt nobody answers); coordinator commits. See `~/.claude/harness/NOTES.md`.
- Backlog: `docs/integration_backlog.md` (trait classifier, lifespan overrides, culture gfx chain order, island-region neighbours, TOO LARGE BOX barony, faith icons, bookmark art).
- Open human decisions: `docs/evidence/HANDOFF_integration_B.md` §open questions (8), `docs/step_*.md` open sections.

## Last results
- 2026-09-08 — build 3: 15 steps, 1368 files; ck3-tiger fatal 0 / error 58 (41 loc hash collisions, 14 wrong-gender, 2 unknown-field, 1 history; `docs/evidence/tiger_build3_2026-09-08.txt`); pytest 1058; headless -test In Game 54 s, 172/173 (only ruler-holds-capital fails).
- 2026-09-08 — playtest-2 build: 15 steps, 1378 files; headless `-test` In Game, 172/173 (`claudespace/docs/evidence/tests_faerun_ck2_to_ck3_converted_2026-09-08_201524.md`); map research `docs/map_fidelity.md`.
- 2026-09-08 — **first In Game**: headless `-test` run of the converted mod reaches `Setting idler 'In Game'`; 166/173 generated tests pass (`claudespace/docs/evidence/tests_faerun_ck2_to_ck3_converted_2026-09-08_165318.md`).
- 2026-09-08 — crash bisection: 25 launches, root causes in `docs/DECISIONS.md` (empty province_mapping table, missing test_default, employer on rulers); `claudespace/docs/evidence/bisect_*`.
- 2026-09-08 — full run: 13 steps, 61.7 s, 1063 files (`docs/evidence/full_run_2026-09-08.md`); tiger fatal 0 / error 218 accepted classes (`docs/evidence/tiger_full_2026-09-08.md`).
- 2026-09-08 — game loads: map, 419 cultures, 94 faiths, 7130 titles, 18,124 characters; main menu reached without `-test` (`docs/evidence/game_load_2026-09-08.md`).
- 2026-09-08 — vanilla control in the same headless harness: menu 42 s, In Game with `-test` 54 s.

## Next 3
1. User playtest 3 of build 483d1d8 (`docs/playtest.md`): clothes, traits, terrain paint, relief, CK2 port seeds.
2. Events §5 step 3: syntactic port of `new` events (1762) — trigger/effect tables, scopes, MTTH → on_action pulses, convertibility score; decisions first (410 new).
3. Map look follow-ups: terrain-paint size call (RLE/half-res test in game), trees/colour map (§4.3), art pass on `mappings/terrain_paint.csv`; characters' looks: per-race ethnicities (`docs/research_dna_races.md` §4).
