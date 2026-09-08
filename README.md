# ck2_to_ck3_mod_converter

Converts a CK2 total-conversion mod into a CK3 1.19 mod, algorithmically and re-runnably.
Test subject and first customer: the [CK2 Faerûn mod](https://github.com/ProjectFaerun/Faerun) →
[`faerun_ck2_to_ck3_converted`](https://github.com/CorentinvdBdO/faerun_ck2_to_ck3_converted) (generated, never
hand-edited) → [`forgotten_kings`](https://github.com/CorentinvdBdO/forgotten_kings) (the human submod).

**Status 2026-09-08 — first playable raw state.** The generated mod boots, starts the 1357 DR bookmark
and passes 166 of 173 self-generated in-game tests. Map, titles, history, characters, dynasties, cultures,
religions, traits and localisation are converted. No events, decisions, buildings or mechanics yet: vanilla
CK3 rules on a Faerûn map. How to play it: [`docs/playtest.md`](docs/playtest.md).

```
uv sync --group dev
uv run ck2ck3 --config configs/faerun.toml        # 13 steps, ~65 s, 1000+ files into the mod folder
uv run pytest -q                                  # 919 tests
scripts/validate_output_mod.sh "" docs/evidence/tiger_<tag>.txt   # ck3-tiger: fatal 0 is the bar
```
Full regenerate-and-validate loop: [`docs/integration_run.md`](docs/integration_run.md). CLI, config keys and
the step contract: [`docs/cli.md`](docs/cli.md). Charter and non-goals: [`docs/PROJECT.md`](docs/PROJECT.md).
Every decision, with its reason: [`docs/DECISIONS.md`](docs/DECISIONS.md).

---

## 1. What is converted, and how

One CLI, one registry of steps (`ck2ck3.steps.<name>`), each owning its output folders. Numbers are the
Faerûn run of 2026-09-08 (`docs/evidence/full_run_2026-09-08.md`).

| step | CK2 input | CK3 output | how |
|---|---|---|---|
| `map` | `map/provinces.bmp` 4096×3328, `topology.bmp`, `rivers.bmp`, `terrain.bmp`, `definition.csv`, `default.map`, `adjacencies.csv`, `climate.txt`, `geographical_region.txt`, `history/provinces` holdings | `map_data/*` (provinces.png 8320×6784, 16-bit heightmap **and the packed heightmap pair**, rivers, definition, default.map, adjacencies, island regions, geographical regions incl. the seven `graphical_*` ones), `common/province_terrain`, `common/defines` | Scale is measured, not chosen: 2.90 km/px (atlas scale bar) ÷ 1.4839 km/px (vanilla core Europe) = ×1.9543, canvas cropped to the painted extent. Provinces NEAREST-resampled; rivers re-traced as vectors so junctions survive; heightmap curve maps CK2 sea level 95 to CK3 water level 4883. **Baronies**: each county is split into its holdings *built* in CK2 history (3694 of 15,356 defined; 163 demoted as too small) by seeded geodesic Voronoi, capital at the CK2 city position; humans steer it with `overrides/barony_seeds.csv` and `overrides/gazetteer.csv`, review sheets per duchy in `docs/evidence/baronies/`. Details: `docs/design_map.md`, `docs/map_scale.md`, `docs/step_map_baronies.md`, `docs/formats_map.md`, `docs/formats_packed_heightmap.md`. |
| `titles` | `common/landed_titles/*` | `common/landed_titles`, `common/coat_of_arms` | 65 empires, 272 kingdoms, 983 duchies, 2127 counties, 3694 baronies keep their CK2 ids. Field by field through `mappings/title_fields.csv`; unbuilt/demoted baronies and dead titles are emitted **commented**, never dropped. Cultural names → `cultural_names`. CoA = placeholder solid colour from the CK2 `color`. `docs/step_titles.md`. |
| `history_titles` | `history/titles/*`, `history/provinces/*` | `history/titles`, `history/provinces`, `history/province_mapping` | Holders (`fae_<id>` string ids), lieges (dropped when the liege has no living holder, is not a higher tier, or is landless), governments derived from CK2 flags (`mappings/government_map.csv`), succession laws by table, holdings per barony with dated changes. Land titles never get a null holder; county-capital baronies get no history. |
| `bookmarks` | `common/bookmarks` | `common/bookmarks`, `bookmark_portraits` placeholders | 17 bookmarks 1357–1501, 82 characters; the config's `bookmark_date` one is `test_default`. |
| `cultures` | `common/cultures/*` (67 groups, 419 cultures) | `common/culture/{pillars,cultures,name_lists}`, `common/ethnicities`, opinion modifier formats | One heritage + one language pillar per group (heritage carries `species_<race> = yes`, the Elder Kings 2 pattern); name lists are loc keys (ASCII, letter-initial); dynasty names filled from CK2 dynasties; ethnicity per group from `overrides/ethnicity_of_culture_group.csv` (non-humans → placeholder ethnicity). `docs/step_cultures_religions.md`, `docs/design_races.md`. |
| `religions` | `common/religions/*` (15 groups, ~150 religions) | `common/religion/{religion_family_types,religion_types,holy_site_types}` | One family per CK2 group, one faith per CK2 religion, all 23 mandatory doctrine groups filled from a CK2-flag → doctrine table (`mappings/religion_fields.csv`), holy sites from `holy_site = …` (max 5 per faith, one object per county), god names as loc keys. |
| `traits` | `common/traits/*` (1417 traits) | `common/traits`, trait icons | 429 ported (117 race traits get `genetic`, `physical`, `life_expectancy` from `overrides/race_lifespan.csv`), 121 that CK3 already has **exactly** are not redefined (rename map `mappings/trait_id_map.csv`), 867 one-off biography traits emitted commented. Vanilla CK2 content CK3 removed is **replaced**: the 16 near-equivalents and 13 no-equivalents are ported as new traits, never dropped. Modifiers through `mappings/modifiers.csv` with scale factors derived from same-trait pairs. `docs/step_traits.md`, `docs/mapping_modifiers.md`. |
| `dynasties` | `common/dynasties` (11,952) | `common/dynasties`, `dynasty_houses` shadows, dynasty-name yml | `fae_<id>` ids, names become loc keys (hash-collision checked against vanilla), CK2 CoAs dropped with a review sheet. |
| `characters` | `history/characters` (18,124) | `history/characters` | Field by field (`mappings/character_fields.csv`, `character_effects.csv`), death reasons and nicknames by table, traits through the traits hand-off, `immortal_age` → immortal trait + `set_immortal_age`, `employer` kept only while the employer is landed and the character is not a ruler. Integrity report: `docs/evidence/characters_integrity.csv`. |
| `loc` | 120 CSV, 113,755 lines, cp1252 | 480 yml, 4 languages, 111k keys each | Keys keep CK2 names; a `key_map` (built from every lane's rename table) copies/renames where CK3 wants other shapes; text codes converted by table (93.9 % of 147,711; `[From.X]` → saved scope `ck2_from`, unknown `Custom()` marked). `docs/formats_loc.md`, `docs/loc_codes.md`. |
| `tests` | the generated mod itself | `tests/fae_generated_tests.txt` | 107 CK3 scripted-test assertions read back from the mod (bookmark characters alive and holding their title, 50 title holders, 50 provinces' culture/faith, ruler-holds-capital); run with `-test`. |
| `descriptor`, `clean` | — | `descriptor.mod`, `credit_portraits.txt` | `replace_path` only for folders the mod actually fills; vanilla files that name vanilla objects are shadowed by same-name empty files. |

Rules that every step obeys: **no invention** (anything without a CK3 equivalent is emitted as a comment next
to the nearest construct, tagged `# CK2:`), CK2 comments preserved (the parser round-trips them), human input
only through `overrides/*.csv` so a re-run after an upstream Faerûn update keeps the human work, one evidence
file per claim in `docs/evidence/`.

Validation chain: `pytest` (919) → `ck3-tiger` (fatal 0; 218 accepted errors, each class justified in
`docs/evidence/tiger_full_2026-09-08.md`) → headless game launch + generated tests
(`claudespace/scripts/ck3_test.sh <mod> --headless`).

## 2. Hurdles (what actually cost time)

- **The old code did not convert anything.** The regex parser dropped comments and could not write; nothing
  wrote a CK3 file. Replaced by a tokenizer parser with comment round-trip (6437/6437 Faerûn files, 3785/3785
  vanilla CK3 files parse and round-trip), then 13 steps in a day of parallel lanes.
- **CK3 facts that are wrong on the wiki or unwritten.** `replace_path` is not recursive; the packed heightmap
  format (reverse-engineered, byte-identical to vanilla); `WORLD_EXTENTS_X/Z` and `WATERLEVEL` defines move the
  coastline silently; scripts need a BOM on every `common/` and `history/` file, ASCII or not; `positions.txt` is
  not read by 1.19 at all; a bare token starting with a digit breaks the CK3 parser for the rest of the file;
  the 1.19 religion folders are `*_types`. All in `CLAUDE.md` invariants and `docs/formats_*.md`.
- **Three crashes with no message.** 25 bisecting launches and two disassemblies of `ck3.exe`:
  (1) an **empty `history/province_mapping` table** makes the province-history loader dereference null on the
  first block; (2) without a `test_default` bookmark the `-test` game state is generated at date −1.1.1;
  (3) an `employer` on a character who is a ruler at the start date crashes powerful-vassal setup. Godherja's
  single-line `6 = 20` mapping file exists for reason (1). `docs/DECISIONS.md` 2026-09-08.
- **CK2 and CK3 disagree on what a barony is.** CK2 baronies are abstract slots (median 7 per county); CK3
  baronies are map provinces. Solution: built holdings become provinces, the rest stays as comments for the
  submod (`docs/design_map.md` §B).
- **Loose-ends between lanes.** Two id schemes for name lists, two for dynasties, a trait set re-derived
  instead of reused: 8308 traits silently commented. Fixed by a shared `ck2ck3.ids` module and `ctx.data`
  hand-offs between steps; the tiger run went 7707 → 218 errors.
- **Tooling.** The local CK3 is the Windows build under Proton and writes to the Proton prefix, not
  `~/.local/share`; automated runs need a screen, solved with a headless weston + Xwayland on the GPU. Worker
  agents hang at their own `git commit` (a permission prompt nobody can answer), so the coordinator commits.

## 3. Left on the side on purpose (needs a human, or the submod)

- **Art.** CK2 portraits are 2D sprites; nothing is portable. Non-human races get vanilla ethnicities with a
  `# TODO real ethnicity` marker; the race mechanics (heritage `species_*` parameter, genetic race traits,
  lifespans) are in place so a pack from `ck3_fantasy_assets` can be dropped in (`docs/design_races.md`,
  `docs/races_research.md`: no licensed fantasy 3D assets exist today). Faith and trait icons: CK2 files
  copied where they exist (wrong size), missing otherwise. Coats of arms: solid colours; the 3455 CK2 flags are
  listed in `docs/evidence/ck2_flags.csv` for a later pass. Bookmark art and heritage audio: none.
- **Barony geometry.** The Voronoi split is a first placement. Where it is wrong (Baldur's Gate districts,
  Waterdeep wards) the fix is a row in `overrides/barony_seeds.csv`, not code.
- **Design choices CK3 forces.** Default tenets, ethos, traditions, martial customs, doctrine defaults where CK2
  has no concept; all `assumed`, all overridable in `overrides/*.csv`, all listed per step doc.
- **Mechanics with no CK3 home.** Societies (35), offmap Shou Lung, wonders, objectives, laws, custom
  governments beyond the 18 CK3 has: inventory with the best CK3 fit for each in
  `docs/mechanics_inventory.md`. These are submod work, not conversion.
- **Dropped CK2 data.** `dna`, `properties` (2D sprites), CK2 dynasty CoAs, `max_settlements`, hidden titles,
  `immortal` edge cases (56 ancient non-immortals). Each is a comment in the output plus a row in an evidence CSV.

## 4. TODO for the converter

Tracked in `STATUS.md` (Next 3) and `docs/integration_backlog.md`. In order:

1. **Events and decisions** (13,058 events, ~101 decisions, 100 CBs) — see §5.
2. Buildings (345) and wonders (59) → CK3 building chains and special buildings; on_actions; laws table.
3. Traits backlog: 175 unclassified vanilla-origin traits, 25 non-race `race_trait` rows, `lifespan_<N>` as
   `life_expectancy`; culture gfx chain order (1383 cosmetic warnings); island regions (83); one oversized
   barony box; faith icons.
4. The 7 failing generated tests (6 bookmark characters' titles, 1 ruler-capital invariant) and a per-class
   triage of the In Game error log by owning step (`culture trigger [Failed context switch]` in vanilla pool
   templates is the biggest).
5. Second-order fidelity: CK2 `technology` history → innovations; artifacts (546); flags → CoA emblems;
   positions for cities from CK2 `positions.txt`.

## 5. Events: the plan

Faerûn replaces CK2's whole `events/` folder, so every event is one of: **new**, **modified vanilla CK2**,
or **vanilla CK2 kept**; and every vanilla CK2 event absent from Faerûn is **deleted**. That provenance is
computable, since the CK2 base game is installed:

1. **Provenance pass** (`docs/evidence/events_provenance.csv`): parse both event trees, key by event id. Same id
   in both → diff at key level (trigger, MTTH, options, effects) → `modified` with the changed keys listed;
   only in Faerûn → `new`; only in vanilla → `deleted`. The same pass for decisions and on_actions.
2. **Vanilla bridge table** `mappings/events_ck2_ck3_vanilla.csv`: CK2 vanilla event → the CK3 vanilla event or
   system that replaced it (many have none: CK3 restructured lifestyles, schemes, stress). Curated, with
   evidence file:line on both sides. A `modified` Faerûn event whose vanilla ancestor has a CK3 counterpart is
   emitted as **an override of the CK3 event** carrying only the Faerûn delta (the CK3 event copied, the delta
   applied, the CK2 diff attached as comments). `deleted` events with a CK3 counterpart become a list the
   submod can act on (CK3 cannot delete a vanilla event; it can neuter its trigger). `new` events are ported.
3. **Syntactic port** of `new` events: trigger/effect vocabulary through a table
   (`mappings/triggers.csv`, `mappings/effects.csv`, built from both games' `.info` docs and verified like the
   modifier table); scopes `ROOT/FROM/FROMFROM/PREV` → `root`/saved scopes (`ck2_from`, matching what the loc
   step already emits); MTTH → `on_action` pulses with `trigger_event = { days = … }`; character/province/letter
   event types → CK3 event types and `theme`/`left_portrait`. Anything unmapped is a `# CK2:` comment and the
   event gets a **convertibility score** (mapped keys ÷ keys); events below a threshold are emitted with
   `trigger = { always = no }` and a `fae_unported` flag so they exist, are inspectable, and can be re-enabled
   one by one in the submod.
4. **Text**: the loc step already converts 93.9 % of text codes and marks the rest; the events lane must emit the
   `save_scope_as = ck2_from` lines the text expects and define the `Custom()` functions the port can express.
5. **Mechanics**: an event that uses a Faerûn mechanic (society ranks, offmap powers, custom laws, `immortal_age`
   tricks) is classified by `docs/mechanics_inventory.md`; the port keeps the event skeleton and comments the
   mechanic-specific block, so the submod re-implements the mechanic once and the events light up.

Order of work: provenance pass and bridge table first (they decide everything else), then decisions
(small, self-contained), then on_actions, then character events by convertibility score descending.

## 6. Repositories and layout

| what | where |
|---|---|
| this converter | `paradox/ck3/ck2_to_ck3_mod_converter` — `src/ck2ck3/` (pdx parser, steps, map, titles, port), `mappings/` (CK2→CK3 tables), `overrides/` (human input), `configs/faerun.toml`, `tests/`, `docs/`, `scripts/` |
| CK2 input | `Faerun/` (gitignored clone of ProjectFaerun/Faerun), CK2 base game at `~/.local/share/Steam/steamapps/common/Crusader Kings II` |
| generated mod | `paradox/ck3/claudespace/mods/faerun_ck2_to_ck3_converted` (own repo; one commit per regeneration recording converter + upstream shas) |
| submod | `paradox/ck3/claudespace/mods/forgotten_kings` (prefix `fk_`) |
| asset library | `paradox/ck3/ck3_fantasy_assets` (local only; licence-gated packs) |
| CK3 workspace & harness | `paradox/ck3/claudespace` — `scripts/ck3_launch.sh`, `ck3_test.sh`, `ck3_bisect*.sh`, skills `/fk-push` `/fk-test` `/fk-errors`, `docs/ck3_test_framework.md`, `docs/headless_display.md` |

Agent guide: `CLAUDE.md`. State: `STATUS.md`. Surveys: `docs/faerun_ck2_survey.md`,
`docs/converter_code_assessment.md` (the starting point).
