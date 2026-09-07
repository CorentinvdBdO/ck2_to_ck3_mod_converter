# Forgotten Kings — project charter

CK3 total conversion of the Forgotten Realms, built as **a converter first**, a mod second.
Source of truth for scope and non-goals. State lives in `STATUS.md`. Decisions in `docs/DECISIONS.md`.

## Three deliverables (three repos)
| repo | path | role | prefix |
|---|---|---|---|
| converter (this repo) | `paradox/ck3/ck2_to_ck3_mod_converter` · github.com/CorentinvdBdO/ck2_to_ck3_mod_converter | CK2 mod → CK3 mod, algorithmic, re-runnable | — |
| converted mod (generated) | `paradox/ck3/claudespace/mods/faerun_ck2_to_ck3_converted` · github.com/CorentinvdBdO/faerun_ck2_to_ck3_converted | raw converter output, **never hand-edited**, regenerated on every Faerun update | `fae_` (generated) |
| Forgotten Kings submod | `paradox/ck3/claudespace/mods/forgotten_kings` · github.com/CorentinvdBdO/forgotten_kings (GPL-3.0) | human gameplay/flavour work on top of the converted mod | `fk_` |
| asset library | `paradox/ck3/ck3_fantasy_assets` | licensed, reusable CK3 assets (race portraits, clothes, …) the converter pulls from | per pack |

Inputs (gitignored, cloned locally): `Faerun/` = https://github.com/ProjectFaerun/Faerun (CK2 mod, still active upstream).

## What the AI-assisted work is for
- Automate large mechanical tasks: map conversion, barony subdivision, history/title export, localisation port.
- Automate translation work.
- Code search and debugging (converter, CK3 script errors).
- Lore search (canon: Atlas of Ice and Fire, 1371 DR; wiki) to feed gazetteers and placement hints.

## Explicit non-goals of the converter
- No new cultures, religions, events, decisions, mechanics, balance. Zero design.
- Anything that has no CK3 equivalent is emitted **as a comment** next to the nearest CK3 construct, never invented.
- Anything that needs human judgement (barony seeds, race models) takes an **override file** as input; defaults are heuristic.

## Canon and references
- Political/geographic canon: https://atlasoficeandfireblog.wordpress.com/2022/11/11/nations-of-the-forgotten-realms-the-full-guide/ (1371 DR, 39 nations; guide map 3000×1878 saved in `refs/`, copyrighted, not redistributed).
- Faerun CK2 mod already uses the atlas projection (`verified` by upstream README claim; to re-check by overlay).
- CK3 target: 1.19.x. Vanilla map 9216×4608 px, heightmap 18432×9216 16-bit (`verified` 2026-09-07 on local install).

## Roadmap (lanes, in order)
1. `foundation` — parser round-trip with comments, CLI, tests, CK3 target 1.19 dims, output into `claudespace/mods/faerun_ck2_to_ck3_converted`.
2. `map-physical` — provinces/heightmap/rivers rescaled to chosen dims; packed heightmap step; definition.csv; default.map; loads in game with Atlantis placeholders.
3. `baronies` — county → barony subdivision (see `docs/design_map.md`), override CSV, review sheets.
4. `titles-history` — landed_titles (all tiers), history/titles, history/provinces (holdings), positions.
5. `characters` — history/characters + dynasties, id reindexing, DNA placeholders per race.
6. `cultures-religions` — culture/heritage/ethnicity per race, religion families/faiths, holy sites.
7. `traits-modifiers` — trait port with option table (CK2 mechanic → CK3 equivalent or comment).
8. `events-decisions` — syntactic port, unsupported bits as comments; mechanics inventory (`docs/mechanics_inventory.md`).
9. `localisation` — CSV → yml per language, BOM, key rename map.
10. `assets` — asset library packs, ethnicity/gene mapping, placeholders.
