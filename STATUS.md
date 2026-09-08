# STATUS — ck2_to_ck3_mod_converter

Rewritten by `/status` and `/ship`. Overwrite, never append.
Updated: 2026-09-08 07:05 by Claude session (coordinator)

## Lanes in flight
| lane | branch | owner | done when | state | checks |
|---|---|---|---|---|---|
| game-load | (coordinator, main) | Claude 2026-09-08 | converted mod reaches `Setting idler 'In Game'` with `-test`; generated tests run | bisecting an access violation in game setup (see Blockers) | pytest 910 green |

Shipped 2026-09-07/08 (all on `main`, pushed): project-kickoff, mappings, mappings-world, foundation, map-physical, traits, localisation, cultures-religions, characters, baronies, titles-history, integration (A+B), dynasty-houses/credit-portraits shadows.

## Repos
| repo | path | base | origin | state |
|---|---|---|---|---|
| converter | `paradox/ck3/ck2_to_ck3_mod_converter` | main 9287307 | github.com/CorentinvdBdO/ck2_to_ck3_mod_converter (public) | 13 steps (`--list-steps`), full run 62 s, 1063 files; ck3-tiger fatal 0 |
| faerun_ck2_to_ck3_converted (generated) | `paradox/ck3/claudespace/mods/faerun_ck2_to_ck3_converted` | main 43d8d20 | github.com/CorentinvdBdO/faerun_ck2_to_ck3_converted (private) | regenerated 2026-09-08; loads to main menu; crashes in game setup with `-test` |
| forgotten_kings (submod) | `paradox/ck3/claudespace/mods/forgotten_kings` | main 3b68112 | github.com/CorentinvdBdO/forgotten_kings (private, GPL-3.0) | skeleton + 2025 roadmap notes |
| ck3_fantasy_assets | `paradox/ck3/ck3_fantasy_assets` | main | none (local by decision) | skeleton |
| claudespace (workspace) | `paradox/ck3/claudespace` | lane/harness (not shipped to master) | none | test harness, headless display, `/fk-push` `/fk-test` `/fk-errors`, `scripts/ck3_bisect.sh` |

## Environment (verified 2026-09-08)
- CK3 1.19.0.6 Windows build under Proton; live user dir inside the Proton prefix; launches via `claudespace/scripts/ck3_launch.sh` (`--headless` = weston + Xwayland on the RTX 5070 Ti).
- CK2 installed at `~/.local/share/Steam/steamapps/common/Crusader Kings II`. Faerûn clone in `Faerun/`.
- ck3-tiger v1.19.0 at `~/.local/bin/ck3-tiger`. Python 3.12, uv, no Rust.
- Git push: token in `../claudespace/tokens` (gitignored), per-repo `credential.helper`; user CorentinvdBdO.

## Blockers and open flags
- **Game setup crash**: `EXCEPTION_ACCESS_VIOLATION 0x14207F7B1` ~1 s after `characterhistory.cpp` token listing, only with `-test` (menu is reached without it). Not caused by history/characters, history/titles, common/traits, common/culture, common/religion or localization (each removed alone still crashes; `docs/evidence/bisect_*`). Second bisect round running over tests, bookmarks, history/provinces, defines, province_terrain, geographical_regions, coat_of_arms, bookmark_portraits, gfx, landed_titles.
- Worker agents hang forever at `git commit` (permission prompt nobody answers); coordinator commits. See `~/.claude/harness/NOTES.md`.
- Backlog: `docs/integration_backlog.md` (trait classifier, lifespan overrides, culture gfx chain order, island-region neighbours, TOO LARGE BOX barony, faith icons, bookmark art).
- Open human decisions: `docs/evidence/HANDOFF_integration_B.md` §open questions (8), `docs/step_*.md` open sections.

## Last results
- 2026-09-08 — full run: 13 steps, 61.7 s, 1063 files (`docs/evidence/full_run_2026-09-08.md`); tiger fatal 0 / error 218 accepted classes (`docs/evidence/tiger_full_2026-09-08.md`).
- 2026-09-08 — game loads: map, 419 cultures, 94 faiths, 7130 titles, 18,124 characters; main menu reached without `-test` (`docs/evidence/game_load_2026-09-08.md`).
- 2026-09-08 — vanilla control in the same headless harness: menu 42 s, In Game with `-test` 54 s.

## Next 3
1. Find the game-setup crash (bisect round 2), fix in the converter, regenerate, reach In Game, run `tests/fae_generated_tests.txt`.
2. Ship claudespace `lane/harness` to master (user decision), then `/fk-test faerun_ck2_to_ck3_converted` becomes the standard check.
3. Lanes `events-decisions` (13k events, syntactic port), `buildings-wonders`, `traits` follow-ups from the backlog.
