# Faerûn CK2 mod survey (2026-09-07, upstream HEAD shallow clone in `Faerun/`)

All numbers `verified` with grep/wc/PIL on the clone unless marked `assumed`.

## 1. Layout (`Faerun/Faerun/`)
- Root files: `Faerun.mod`, `credits.txt`, `changelog.txt`, `ValidatorSettings.txt`, `counters and flags crib.txt`.
- `common/` 57 subfolders. Largest: scripted_effects 47, scripted_triggers 48, cb_types 27, societies 22, buildings 19, traits 17, cultures 13, objectives 13.
- `decisions/` 61 files. `events/` 332 files. `history/` provinces 2125, titles 3422, characters 80 (id-range files + `_unused/`), wars 36, technology 15, offmap_powers 1.
- `gfx/`: characters 3431 files (268 race/sex portrait sets), flags 3455, interface 900, traits 564, event_pictures 246, models 78 (custom unit `.xac`).
- `interface/portraits/` 406 `.gfx` files (one per race/sprite). `localisation/` 120 csv. `map/` 16 files + `statics/`, `terrain/`.
- `Faerun.mod` replaces: landed_titles, scripted_effects/triggers, trade_routes, decisions, events, history/{characters,offmap_powers,provinces,technology,titles,wars}, gfx/loadingscreens.

## 2. Map
- `provinces.bmp` 4096×3328 24-bit; `topology.bmp` 4096×3328 8-bit; `rivers.bmp`, `terrain.bmp` 8-bit; `trees.bmp` 512×416; `world_normal_height.bmp` 3686×2995.
- `definition.csv`: 2697 rows; `max_provinces = 2720`. Sea provinces from `sea_zones`: 369 → ~2328 land (wasteland not excluded).
- `positions.txt`: per province (CK2 has no barony coordinates), 7-slot `position/rotation/height` vectors. First entries Waterdeep(1), Amphail(2), Daggerford(3).
- Present: `adjacencies.csv`, `climate.txt`, `continent.txt`, `geographical_region.txt` (nested `duchies=`/`regions=`), `island_region.txt`, `terrain.txt`, `provinceDef.xls`.
- Ocean regions in `default.map`: Trackless Sea, Lakes, Gbor Nor, Fallen Stars, Yal Tengri.

## 3. Landed titles
- Files: `01_landed_titles.txt` (678 KB, Windows-1252), `01_laerakond.txt`, `landed_titles.txt`, `mercenaries.txt`, `offmap_toril_landed_titles.txt`, `republics.txt`, `titular_titles.txt`.
- Counts: e_ 65, k_ 272, d_ 983, c_ 2132, b_ 15356.
- Commented-out baronies: 1. **Almost all 15k baronies are active definitions**; the "unused" ones are the slots without a holding in `history/provinces` (see `scripts/faerun_barony_stats.py`).
- Baronies per county: min 3, median 7, mean 7.1, max 25.
- Attributes: `color`/`color2`, `capital` (790), `holy_site` (475, several per county), `culture` (7), `title=` custom ruler strings (73, e.g. MARGRAVE, SYLVIZAR), `dignity` (17). Religion comes from province history.
- Empire tier includes faction/organisation titles (`e_army_of_darkness`, `e_black_horde`, `e_emerald_enclave`, `e_pirates`, `e_rebels`, `e_calim_empire`, `e_deep_shanatar`, `e_moradask`…). No explicit "hegemony" keyword.

## 4. History
- Province file sample (`1472 - Talab.txt`): `title=`, `max_settlements=`, `b_x = castle|city|temple`, `culture=`, `religion=`, dated blocks.
- Characters: 18,124 definitions. Dynasties: `Faerun_Dynasties.txt` 12,277 lines.
- Bookmarks: 17, from `bm_before_the_storm` 1357.1.1 to `bm_the_new_era` 1501.1.1 (incl. Bhaalspawn 1368.9.2, Tyranny of Dragons 1481.1.1). Defines: `START_YEAR=1000` learning scenario.
- `Dates.txt` at repo root maps novels/modules to in-game dates.

## 5. Cultures (race system)
- 13 files: human, elves, dwarves, giants, demihuman, dragons, scalykind, littlefolk, monsters, outsiders, animals, province_monster_culture.
- 67 culture groups, ~495 cultures (upper bound). Groups double as races: dwarf, high/dark/sylvan elf, eladrin, gith, orc, goblinoid, giant(kin), gnome, halfling, dragon(kin), undead, fiendish, celestial, planetouched, construct, aberration, slaad, minotaur, centaur, beastfolk, serpent, scaly, plus animals.

## 6. Religions
- `new_faerun_religions.txt` 6518 lines. 15 groups: aberration, atheist, draconic, drow, dwarven, elven, evil/good/wild human pantheons, giant, humanoid, karaturan, pagan, qismaite, unenlightened.
- ~130–184 religions: one per deity inside pantheon groups.

## 7. Traits
- 16 files; core mechanical traits ~700–900, plus 474 per-NPC biography traits, 238 god-patron traits, 112 character-class traits.
- Race traits (`race_traits.txt`, 75): `creature_dwarf/elf/orc/gnome/halfling/drow/tiefling/aasimar/genasi/dragonborn`, `creature_half_elf/half_orc/half_dwarf/half_giant/half_gnoll/half_ogre`, `half_celestial/dragon/fiend/troll`, `creature_dragon` + `dragon_wyrmling/young/adult/ancient`, `lich`, `lich_baelnorn`, `archlich`, `vampire`, `vampire_spawn`, `undead`, sorcerer tiers.
- Race is therefore **double-encoded**: culture group and `creature_*` trait.

## 8. Custom mechanics (inventory for `docs/mechanics_inventory.md`)
- Events: 13,058 ids in 332 files. Decisions: ~101 in 61 files. CBs: ~100 in 27 files.
- Governments: 18 (feudal, democratic_feudal, divine_feudal, theocratic_feudal, theocracy, baron_theocracy, muslim, republic, merchant_republic, tribal, nomadic, nomadic_tribal, semi_nomadic, yikaria, roman_imperial, celestial, order, ordning).
- Societies: ~35 (Harpers, Zhentarim, Emerald Enclave, Cult of the Dragon, Twisted Rune, Kraken Society, Shadow Thieves, Night Masks, Arcane Brotherhood, knightly orders, race warrior lodges).
- Buildings ~345 (19 files), wonders 59, artifacts 546, bloodlines 6 files, laws 9 files (custom succession/council/crown/demesne/obligation), job_titles 498 lines, minor titles 6 files, execution methods 34, offmap powers (Shou Lung, Toril), disease 2 files, objectives 13 files, on_actions 3 files.

## 9. Assets
- 8,857 dds/tga. 268 portrait sets. 3,455 flags. 78 unit models.
- `credits.txt`: Fan Content Policy notice (WotC IP), assets borrowed from Enoofu's FR mod, Better Looking Garbs, Middle Earth Project, Tianxia, Geheimnisnacht, CleanSlate, WTWSMS, ARR, Seven Kingdoms, After the End, Saffron, Elder Kings. **No LICENSE file.** `working-resources/` holds unshipped Warhammer-style portrait sources.

## 10. Localisation
- 120 csv, 113,755 lines, Windows-1252 CRLF, header `#CODE;ENGLISH;FRENCH;GERMAN;;SPANISH;;;;;;;x`, English maintained.

## Implications for the converter
- CK2 portraits are 2D sprite layers: **not reusable** for CK3 3D portraits. Flags (3,455) are reusable as CoA textures or need CoA generation.
- Barony selection must come from `history/provinces` holdings, not from comments.
- Character/dynasty/title history volume is large but regular: good automation target.
- Events (13k) are the long tail; port syntactically, comment what does not map.
