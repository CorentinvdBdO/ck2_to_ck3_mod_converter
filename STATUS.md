# STATUS — ck2_to_ck3_mod_converter

Rewritten by `/status` and `/ship`. Overwrite, never append.
Updated: 2026-09-08 17:05 by Claude session (coordinator)

## Lanes in flight
| lane | branch | owner | done when | state | checks |
|---|---|---|---|---|---|
| (none in flight) | | | | | |

Shipped 2026-09-08 (game-load): province_mapping entry, test_default bookmark, impassable wasteland, no null land holders, dynasty_houses/credit_portraits shadows, immortal trait, landed-only employers, no employer on rulers. **The generated mod reaches In Game at 1357 headless; 166/173 scripted tests pass.**

Shipped 2026-09-07/08 (all on `main`, pushed): project-kickoff, mappings, mappings-world, foundation, map-physical, traits, localisation, cultures-religions, characters, baronies, titles-history, integration (A+B), dynasty-houses/credit-portraits shadows.

## Repos
| repo | path | base | origin | state |
|---|---|---|---|---|
| converter | `paradox/ck3/ck2_to_ck3_mod_converter` | main d4d2147 | github.com/CorentinvdBdO/ck2_to_ck3_mod_converter (public) | 13 steps (`--list-steps`), full run 62 s, 1063 files; ck3-tiger fatal 0 |
| faerun_ck2_to_ck3_converted (generated) | `paradox/ck3/claudespace/mods/faerun_ck2_to_ck3_converted` | main 82ec406 | github.com/CorentinvdBdO/faerun_ck2_to_ck3_converted (private) | regenerated 2026-09-08 17:00; **reaches In Game** (1357), 166/173 tests pass |
| forgotten_kings (submod) | `paradox/ck3/claudespace/mods/forgotten_kings` | main 3b68112 | github.com/CorentinvdBdO/forgotten_kings (private, GPL-3.0) | skeleton + 2025 roadmap notes |
| ck3_fantasy_assets | `paradox/ck3/ck3_fantasy_assets` | main | none (local by decision) | skeleton |
| claudespace (workspace) | `paradox/ck3/claudespace` | lane/harness (not shipped to master) | none | test harness, headless display, `/fk-push` `/fk-test` `/fk-errors`, `scripts/ck3_bisect.sh` |

## Environment (verified 2026-09-08)
- CK3 1.19.0.6 Windows build under Proton; live user dir inside the Proton prefix; launches via `claudespace/scripts/ck3_launch.sh` (`--headless` = weston + Xwayland on the RTX 5070 Ti).
- CK2 installed at `~/.local/share/Steam/steamapps/common/Crusader Kings II`. Faerûn clone in `Faerun/`.
- ck3-tiger v1.19.0 at `~/.local/bin/ck3-tiger`. Python 3.12, uv, no Rust.
- Git push: token in `../claudespace/tokens` (gitignored), per-repo `credential.helper`; user CorentinvdBdO.

## Blockers and open flags
- 7 scripted tests still fail: 6 bookmark-character checks (`title:X = { holder = root }` scope or the CK2 bookmark title is not actually held at 1357; investigate with the In Game log) and the ruler-holds-capital invariant (2205/2208 rulers pass).
- Ancient non-immortal characters still exist (56 alive ≥150 years without a CK2 immortal marker); ages are accepted by the game but worth a race-lifespan decision.
- Worker agents hang forever at `git commit` (permission prompt nobody answers); coordinator commits. See `~/.claude/harness/NOTES.md`.
- Backlog: `docs/integration_backlog.md` (trait classifier, lifespan overrides, culture gfx chain order, island-region neighbours, TOO LARGE BOX barony, faith icons, bookmark art).
- Open human decisions: `docs/evidence/HANDOFF_integration_B.md` §open questions (8), `docs/step_*.md` open sections.

## Last results
- 2026-09-08 — **first In Game**: headless `-test` run of the converted mod reaches `Setting idler 'In Game'`; 166/173 generated tests pass (`claudespace/docs/evidence/tests_faerun_ck2_to_ck3_converted_2026-09-08_165318.md`).
- 2026-09-08 — crash bisection: 25 launches, root causes in `docs/DECISIONS.md` (empty province_mapping table, missing test_default, employer on rulers); `claudespace/docs/evidence/bisect_*`.
- 2026-09-08 — full run: 13 steps, 61.7 s, 1063 files (`docs/evidence/full_run_2026-09-08.md`); tiger fatal 0 / error 218 accepted classes (`docs/evidence/tiger_full_2026-09-08.md`).
- 2026-09-08 — game loads: map, 419 cultures, 94 faiths, 7130 titles, 18,124 characters; main menu reached without `-test` (`docs/evidence/game_load_2026-09-08.md`).
- 2026-09-08 — vanilla control in the same headless harness: menu 42 s, In Game with `-test` 54 s.

## Next 3
1. Fix the 6 bookmark tests (scope or data) and make `/fk-test faerun_ck2_to_ck3_converted` the standard check; triage the remaining In Game error classes by owning step (`culture trigger [Failed context switch]` in vanilla pool templates, faith icons, heritage audio parameter).
2. Lane `events-decisions` (13k events, syntactic port) and `buildings-wonders`; traits backlog (classifier, lifespan overrides).
3. Ship claudespace `lane/harness` to master (user decision); regenerate + push the generated mod after each converter merge (`docs/integration_run.md`).
