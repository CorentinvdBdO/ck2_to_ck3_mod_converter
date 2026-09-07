# STATUS — ck2_to_ck3_mod_converter

Rewritten by `/status` and `/ship`. Overwrite, never append.
Updated: 2026-09-07 by Claude session (ship project-kickoff)

## Lanes in flight
| lane | branch | owner | done when | state | checks |
|---|---|---|---|---|---|
| project-kickoff | lane/project-kickoff | Claude 2026-09-07 | charter, decisions, surveys, map/races designs, mechanics inventory, CLAUDE/STATUS, ci/checks.sh green; submod + asset-lib skeletons exist | merged 2026-09-07 | green |

## Repos
| repo | path | base | origin | state |
|---|---|---|---|---|
| converter | `paradox/ck3/ck2_to_ck3_mod_converter` | main | github.com/CorentinvdBdO/ck2_to_ck3_mod_converter (public) | code reads CK2, writes nothing (see docs/converter_code_assessment.md) |
| faerun_ck2_to_ck3_converted (generated) | `paradox/ck3/claudespace/mods/faerun_ck2_to_ck3_converted` | main | github.com/CorentinvdBdO/faerun_ck2_to_ck3_converted (private) | README + descriptor placeholder; content comes from lane `foundation` |
| forgotten_kings (submod) | `paradox/ck3/claudespace/mods/forgotten_kings` | main | github.com/CorentinvdBdO/forgotten_kings (private, GPL-3.0) | skeleton + 2025 roadmap notes in docs/ |
| ck3_fantasy_assets | `paradox/ck3/ck3_fantasy_assets` | main | none (no GitHub repo yet) | skeleton |

## Environment (verified 2026-09-07)
- CK3 1.19.0.6 installed; CK2 **not** installed (no vanilla CK2 files locally; Faerûn clone is the only CK2 source).
- Faerûn upstream HEAD shallow-cloned in `Faerun/` (1.5 GB). Elder Kings 2 and Godherja installed via Workshop (race references).
- Git push: token in `../claudespace/tokens` (gitignored), wired as a per-repo `credential.helper`; user CorentinvdBdO.
- Python 3.12, uv, no Rust. ck3-tiger v1.19.0 at `~/.local/bin/ck3-tiger` (installed 2026-09-07).

## Blockers and open flags
- Open decisions in `docs/design_map.md` §C (target dims, bookmark date) and `docs/design_races.md` (asset licensing).
- Faerûn has no LICENSE; conversion output inherits WotC Fan Content Policy constraints.

## Last results
- 2026-09-07 — races research: no CK3 FR mod exists, no reusable race assets; EK2 pattern adopted (`docs/races_research.md`, `docs/design_races.md`).
- 2026-09-07 — `scripts/faerun_barony_stats.py`: 2132 counties, 15,195 defined baronies, 3,786 built @1368.9.2 (median 1/county). `docs/evidence/barony_stats.csv`.

## Next 3
1. Lane `foundation`: tokenizer parser with comment round-trip + tests; CLI with `configs/faerun.toml`; output to `claudespace/mods/faerun_ck2_to_ck3_converted`.
2. Lane `map-physical`: 16-bit heightmap, ocean padding, lost-province report, default.map/definition.csv writers; load in game with Atlantis placeholders.
3. Lane `baronies`: built-holding barony set, seeded geodesic Voronoi, override CSV, review PNGs.
