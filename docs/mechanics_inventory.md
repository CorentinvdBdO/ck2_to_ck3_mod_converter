# Mechanics inventory: Faerûn CK2 → CK3 fit

Source counts: `docs/faerun_ck2_survey.md` (`verified`). CK3 fit column is `assumed` design judgement for the submod; the converter only ports what column "converter" says.

Legend — converter: `port` = syntactic conversion with CK3 equivalents, unknown bits as comments; `stub` = emit commented skeleton + inventory row; `skip` = out of scope.

| Faerûn mechanic | size | CK2 construct | CK3 fit | converter |
|---|---|---|---|---|
| Landed titles all tiers | 65/272/983/2132/15k | `landed_titles` | 1:1 (`landed_titles`), baronies need provinces (design_map §B) | port |
| Faction/organisation empire titles (`e_pirates`, `e_emerald_enclave`…) | ~15 | titular `e_` | landless titles (`landless = yes`) or CK3 1.13+ **landless adventurer/admin** titles; some fit **Legends/Struggles** | port as titular + comment |
| Title history / holders | 3422 files | `history/titles` | 1:1 | port |
| Province history (culture, religion, holdings) | 2125 | `history/provinces` | 1:1 per barony; `max_settlements` → nothing (comment) | port |
| Characters + dynasties | 18k + 12k lines | `history/characters`, `common/dynasties` | 1:1; traits mapped via table; `dna` placeholder per race; CK2 `employer`/`give_nickname` mapped; missing keys commented | port |
| Cultures (67 groups) | ~495 | `cultures` | culture + `heritage` (group) + `language` + ethos/traditions **defaulted**; race → heritage tag + ethnicity (design_races) | port with defaults |
| Religions (15 groups, ~150 deities) | 6.5k lines | `religions` | religion family = group, faith = deity; doctrines defaulted from CK2 flags (`priests_can_marry`, `intermarry`, `feminist`…) ; holy sites from `holy_site` | port with mapping table |
| Traits | ~800 + 474 biography | `traits` | 1:1 where modifier maps; `creature_*` → genetic race traits; biography traits → `flag`/nickname (comment) | port with option table |
| Character classes (112 traits) | 112 | traits | traits (lifestyle-like); or CK3 **lifestyle trees** later | port as traits |
| God patron traits | 238 | traits | faith-specific traits or `religious` traits; or `patron deity` via **court/religion doctrine** | port as traits |
| Sorcerer tiers, lich, vampire, undead | ~15 | traits + events | traits + on_action aging hooks; **immortality** via `immortal = yes` (CK3 supports) | port traits, events stub |
| Governments (18) | 18 | `governments` | CK3 has feudal/clan/tribal/republic(limited)/theocracy/admin/**nomadic (1.14)**/landless. Map table; `ordning` → tribal+comment; `celestial`/`roman_imperial` → administrative | mapping table + comments |
| Laws (succession, council, crown, demesne, obligation) | 9 files | `laws` | CK3 succession laws + crown authority levels + vassal contracts; custom laws mostly unmappable | stub |
| Societies (~35) | 22 files | `societies` | no CK3 equivalent. Nearest: **Legends**, **schemes**, **court positions**, **holy orders** (military orders), **factions**; or reimplement as **struggles**/activities. Needs full re-implementation | stub + inventory |
| Bloodlines | 6 files | `bloodlines` | **dynasty legacies** or **house traditions**; per-character bloodline → trait (`genetic`) | port as traits + comment |
| Offmap powers (Shou Lung, Toril) | 3 | `offmap_powers` | CK3 1.19 has China as a **situation/hegemon** (All Under Heaven); Shou Lung fits that framework; else remove | stub |
| Wonders (59) | 2 files | `wonders` | **special buildings** (`gfx` + `common/buildings` with `type = special`); wonder upgrades → building levels | port as special buildings |
| Buildings (~345) | 19 files | `buildings` | CK3 building chains; modifiers mapped; culture/gov gating via `can_construct` | port with modifier table |
| Artifacts (546) | 6 files | `artifacts` | CK3 artifacts (`history/artifacts`, `common/artifacts/types`) + rarities; quality/wealth defaulted | port |
| Casus belli (~100) | 27 files | `cb_types` | CK3 `casus_belli_types`; effects mostly mappable; CK2 `on_success` specifics commented | port |
| Decisions (~101) | 61 files | `decisions` | CK3 decisions; `potential/allow/effect` → `is_shown/is_valid/effect` | port |
| Events (13,058) | 332 files | `events` | CK3 events; trigger/effect vocabulary mapped by table, unmapped tokens commented; character/province/letter event types → `type = character_event`/`province` scopes; MTTH → `on_action` + `trigger_event` with `days` | port (long tail) |
| Objectives (ambitions, focuses, plots) | 13 files | `objectives` | CK3 **schemes** (plots), **lifestyle focuses**, **hooks**; no ambitions | stub |
| Job titles / council | 498 lines | `job_titles` | CK3 council positions + court positions (1.7+) | mapping table |
| Minor titles (6 files) | 6 | `minor_titles` | court positions | mapping table |
| Execution methods (34) | 2 | `execution_methods` | CK3 has execution + a few flavour variants; extra → events | stub |
| Disease | 2 | `disease` | CK3 **epidemics** (Legends of the Dead) | stub |
| Technology history | 15 files | `history/technology` | CK3 **innovations** per culture; map CK2 tech levels → era/innovations unlocked | mapping table |
| Trade routes | replace_path | `trade_routes` | CK3 has trade... only via situations/China silk road in 1.19; else remove | skip + comment |
| Portraits (268 sets, 2D layers) | 8.8k files | `gfx/characters` | CK3 3D portraits; **not portable**; see design_races | skip |
| Flags (3,455) | 3455 | `gfx/flags` | CK3 coat_of_arms: emblem textures; port as `textured_emblem` fallback per title | port (texture) |
| Unit models (78 `.xac`) | 78 | `gfx/models` | CK3 `.mesh`; not portable | skip |
| Localisation (113k lines) | 120 csv | csv | yml per language, BOM; key renames for changed ids; nested `[Root.GetName]` syntax converted from `[Root.GetBestName]` etc. | port |
| Bookmarks (17) | 1 file | `bookmarks` | CK3 bookmarks + `bookmark_portraits`; start dates kept | port |
| Mercenaries, republics, holy orders | files | landed_titles | CK3 `mercenary_companies`, republics limited (no merchant republic play), holy orders | port with comments |
| Nomads (Tuigan, etc.) | gov | `nomadic_government` | CK3 1.14 nomadic government | mapping |
| Stress, dread, prowess, hooks, schemes, lifestyles, court, travel, legends, struggles, situations | — | n/a | CK3 additions with no CK2 source; leave vanilla defaults; submod decides | skip |

## Scoped-out for the converter, candidate submod projects (ordered by fit)
1. Societies → CK3 secret societies pattern (Legends + schemes + factions) — biggest gap.
2. Race lifespan/aging/hybrids → design_races.
3. Shou Lung / Kara-Tur → 1.19 hegemon situation framework.
4. Wonders/great projects → special buildings + Great Projects if 1.19 offers them for mods.
5. Objectives/ambitions → hooks + schemes.
6. City neighbourhoods (Baldur's Gate, Waterdeep wards) → special buildings in the capital barony.
