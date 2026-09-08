# STATUS — ck2_to_ck3_mod_converter

Rewritten by `/status` and `/ship`. Overwrite, never append.
Updated: 2026-09-08 20:25 by Claude session (coordinator)

## Lanes in flight
| lane | branch | owner | done when | state | checks |
|---|---|---|---|---|---|
| (none in flight) | | | | | |

Shipped 2026-09-08 (playtest-1 fixes): tc_template (blank-TC shadows, 271 files), map locators/camera/table/flatmap/foliage, ported removed traits (429), placeholder traditions (392 cultures), bookmark positions, launcher path (claudespace), map-fidelity research. Build 2980004: **In Game, 172/173 tests**.

Shipped 2026-09-08 (game-load): province_mapping entry, test_default bookmark, impassable wasteland, no null land holders, dynasty_houses/credit_portraits shadows, immortal trait, landed-only employers, no employer on rulers. **The generated mod reaches In Game at 1357 headless; 166/173 scripted tests pass.**

Shipped 2026-09-07/08 (all on `main`, pushed): project-kickoff, mappings, mappings-world, foundation, map-physical, traits, localisation, cultures-religions, characters, baronies, titles-history, integration (A+B), dynasty-houses/credit-portraits shadows.

## Repos
| repo | path | base | origin | state |
|---|---|---|---|---|
| converter | `paradox/ck3/ck2_to_ck3_mod_converter` | main daf6ab1 | github.com/CorentinvdBdO/ck2_to_ck3_mod_converter (public) | 13 steps (`--list-steps`), full run 62 s, 1063 files; ck3-tiger fatal 0 |
| faerun_ck2_to_ck3_converted (generated) | `paradox/ck3/claudespace/mods/faerun_ck2_to_ck3_converted` | main 2980004 | github.com/CorentinvdBdO/faerun_ck2_to_ck3_converted (private) | playtest-2 build 2026-09-08 20:20; In Game, 172/173 tests |
| forgotten_kings (submod) | `paradox/ck3/claudespace/mods/forgotten_kings` | main 3b68112 | github.com/CorentinvdBdO/forgotten_kings (private, GPL-3.0) | skeleton + 2025 roadmap notes |
| ck3_fantasy_assets | `paradox/ck3/ck3_fantasy_assets` | main | none (local by decision) | skeleton |
| claudespace (workspace) | `paradox/ck3/claudespace` | master 17a247a | none | test harness, headless display, `/fk-push` `/fk-test` `/fk-errors`, `scripts/ck3_bisect.sh` |

## Environment (verified 2026-09-08)
- CK3 1.19.0.6 Windows build under Proton; live user dir inside the Proton prefix; launches via `claudespace/scripts/ck3_launch.sh` (`--headless` = weston + Xwayland on the RTX 5070 Ti).
- CK2 installed at `~/.local/share/Steam/steamapps/common/Crusader Kings II`. Faerûn clone in `Faerun/`.
- ck3-tiger v1.19.0 at `~/.local/bin/ck3-tiger`. Python 3.12, uv, no Rust.
- Git push: token in `../claudespace/tokens` (gitignored), per-repo `credential.helper`; user CorentinvdBdO.

## Blockers and open flags
- 1 scripted test fails: ruler-holds-capital invariant (2205/2208 rulers). Playtest-1 findings and owners: `docs/playtest_2026-09-08.md`; unverified in-game: table scale ×1.4722, camera height, foliage removal, flatmap look.
- Ancient non-immortal characters still exist (56 alive ≥150 years without a CK2 immortal marker); ages are accepted by the game but worth a race-lifespan decision.
- Worker agents hang forever at `git commit` (permission prompt nobody answers); coordinator commits. See `~/.claude/harness/NOTES.md`.
- Backlog: `docs/integration_backlog.md` (trait classifier, lifespan overrides, culture gfx chain order, island-region neighbours, TOO LARGE BOX barony, faith icons, bookmark art).
- Open human decisions: `docs/evidence/HANDOFF_integration_B.md` §open questions (8), `docs/step_*.md` open sections.

## Last results
- 2026-09-08 — playtest-2 build: 15 steps, 1378 files; headless `-test` In Game, 172/173 (`claudespace/docs/evidence/tests_faerun_ck2_to_ck3_converted_2026-09-08_201524.md`); map research `docs/map_fidelity.md`.
- 2026-09-08 — **first In Game**: headless `-test` run of the converted mod reaches `Setting idler 'In Game'`; 166/173 generated tests pass (`claudespace/docs/evidence/tests_faerun_ck2_to_ck3_converted_2026-09-08_165318.md`).
- 2026-09-08 — crash bisection: 25 launches, root causes in `docs/DECISIONS.md` (empty province_mapping table, missing test_default, employer on rulers); `claudespace/docs/evidence/bisect_*`.
- 2026-09-08 — full run: 13 steps, 61.7 s, 1063 files (`docs/evidence/full_run_2026-09-08.md`); tiger fatal 0 / error 218 accepted classes (`docs/evidence/tiger_full_2026-09-08.md`).
- 2026-09-08 — game loads: map, 419 cultures, 94 faiths, 7130 titles, 18,124 characters; main menu reached without `-test` (`docs/evidence/game_load_2026-09-08.md`).
- 2026-09-08 — vanilla control in the same headless harness: menu 42 s, In Game with `-test` 54 s.

## Next 3
1. User playtest 2 (`docs/playtest.md`): launcher path, bookmarks clickable, icons on land, table/camera, flatmap, traditions, Silk Road no longer present.
2. Map fidelity lane from `docs/map_fidelity.md`: CK2 slot 0/4 barony seeds (28 % of seeds move), 16-bit heightmap detail synthesis, `detail_index/intensity` paint from CK2 terrain — one prototype region in game first.
3. Events: provenance pass + CK2→CK3 vanilla bridge table (README §5); `docs/evidence/vanilla_events_naming_titles.csv` (101 vanilla event files) is the first input.
