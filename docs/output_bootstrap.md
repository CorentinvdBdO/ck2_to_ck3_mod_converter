# Output bootstrap: the minimum layer that makes a custom CK3 1.19 map boot

Scope: what the converter must emit into `mods/faerun_ck2_to_ck3_converted` so that a
**physical-map-only** mod loads and a bookmark starts, before any real titles, history,
cultures or religions exist.

Evidence paths (short names used throughout):
- `VANILLA` = `/home/cvdbdo/.local/share/Steam/steamapps/common/Crusader Kings III/game` (1.19)
- `ATL` = Atlantis TC clone, `github.com/bombusfrigidus/Atlantis`
- `EK2` = `steamapps/workshop/content/1158310/2887120253` (Elder Kings 2 0.19.1)
- `GH` = `steamapps/workshop/content/1158310/2326030123` (Godherja 0.4.0.5)

Every claim below is `verified` (read from the file cited) unless labelled `assumed`.

---

## 0. Two facts that shape everything

| # | Fact | Evidence |
|---|---|---|
| 1 | `replace_path` is **not recursive**. Replacing a parent does nothing for its subdirectories. | `verified` — ck3-tiger v1.19.0 binary diagnostic strings: `"replace_path only replaces the specific directory, not any directories below it"` and `"So replace_path = history is not useful, you should replace the paths under it."` (`/home/cvdbdo/.local/share/ck3-tiger/ck3-tiger-linux-v1.19.0/ck3-tiger`) |
| 2 | **Override-by-filename** is an alternative to `replace_path`: a mod file at the same relative path as a vanilla file replaces it wholesale. Use it when vanilla has few files in the dir; use `replace_path` when vanilla has many you cannot enumerate. | `verified` — `EK2/common/bookmarks/bookmarks/00_bookmarks.txt` and `GH/common/religion/holy_site_types/00_holy_site_types.txt` shadow the identically named vanilla files with **no** matching `replace_path` line. |

Corollary: `map_data` does **not** need `replace_path` at all. Neither EK2 nor GH declares it;
both simply ship `definition.csv`, `provinces.png`, `heightmap.png`, … under the vanilla names.
`ATL/descriptor.mod:15` declares `replace_path="map_data"` and then ships an incomplete
`map_data` — see §3.

---

## 1. descriptor.mod / metadata.json comparison

### 1.1 Which manifest do they use?

| mod | `descriptor.mod` | `.metadata/metadata.json` | `supported_version` | notes |
|---|---|---|---|---|
| Atlantis | yes, 16 lines | **absent** (`ls .metadata` → no such file) | `"1.16.*"` (`ATL/descriptor.mod:16`) | also ships a launcher-side `Atlantis.mod` with `path=` (`ATL/Atlantis.mod:17`) |
| Elder Kings 2 | yes, 29 lines | **absent** | `"1.19.0.6"` (`EK2/descriptor.mod:28`) | `remote_file_id="2887120253"` (`:29`) |
| Godherja | yes, 38 lines | **absent** | `"1.19.*"` (`GH/descriptor.mod:36`) | `path=` (`:37`) + `remote_file_id=` (`:38`) |

- `verified`: no mod in `steamapps/workshop/content/1158310/` (4 mods) contains a `.metadata` directory;
  the only `*metadata*` entries are `dlc_metadata/`.
- `verified`: `ck3-tiger` v1.19.0 — our CI validator per `docs/DECISIONS.md` — takes a
  `descriptor.mod` path as its argument (`ck3-tiger-linux-v1.19.0/README.md:49`,
  `ck3-tiger --help`: `<MODPATH>  Path to .mod file of mod to check`). Grepping the binary for
  `metadata.json` returns nothing: **tiger cannot read a metadata.json-only mod**.
- **The task premise "1.19 prefers .metadata/metadata.json" is not supported on this install.**
  `.metadata/metadata.json` is the *Paradox Mods* (paradoxmods.com) upload manifest that the
  launcher generates; `descriptor.mod` remains the format the game and the tooling read (`assumed`
  for the "launcher generates it" half).
- **Decision: emit `descriptor.mod` only.** Add `.metadata/metadata.json` later only if we publish
  to Paradox Mods.
- `verified` bonus from the tiger strings: `"Steam ignores picture= and always uses thumbnail.png."`
  → ship `thumbnail.png`, not `picture=`.

### 1.2 replace_path lines, side by side (exact quoted lines)

`ATL/descriptor.mod:6-15` (12 paths):
```
replace_path="common/bookmarks"
replace_path="common/dynasties"
replace_path="common/dynasty_houses"
replace_path="history/artifacts"
replace_path="history/characters"
replace_path="history/provinces"
replace_path="history/titles"
replace_path="history/wars"
replace_path="tests"
replace_path="map_data"
```
(10 lines; `common/bookmarks` and `map_data` are both dead ends given fact 0.1 — Atlantis's real
bookmark content lives in `common/bookmarks/bookmarks/`, `groups/`, `challenge_characters/`, which
`replace_path="common/bookmarks"` does **not** cover.)

`EK2/descriptor.mod:6-27` (22 paths):
```
replace_path="common/bookmark_portraits"
replace_path="common/dna_data"
replace_path="common/culture/cultures"
replace_path="common/culture/name_lists"
replace_path="common/dynasties"
replace_path="common/landed_titles"
replace_path="common/province_terrain"
replace_path="common/terrain_types"
replace_path="common/religion/doctrine_types"
replace_path="common/religion/holy_site_types"
replace_path="common/religion/religion_family_types"
replace_path="common/religion/religion_types"
replace_path="gfx/interface/illustrations/loading_screens"
replace_path="gfx/portraits/portrait_modifiers"
replace_path="history"
replace_path="history/artifacts"
replace_path="history/characters"
replace_path="history/cultures"
replace_path="history/provinces"
replace_path="history/titles"
replace_path="history/wars"
replace_path="history/struggles"
```
(`replace_path="history"` at `:20` is the exact no-op tiger warns about.)

`GH/descriptor.mod:15-35` (21 paths):
```
replace_path="common/achievements"
replace_path="common/bookmark_portraits"
replace_path="common/coat_of_arms/coat_of_arms"
replace_path="common/culture/cultures"
replace_path="common/culture/name_lists"
replace_path="common/decisions"
replace_path="common/dynasties"
replace_path="common/dna_data"
replace_path="common/game_concepts"
replace_path="common/landed_titles"
replace_path="common/religion/doctrines"
replace_path="common/religion/religion_family_types"
replace_path="common/religion/religion_types"
replace_path="gfx/map/terrain"
replace_path="history/characters"
replace_path="history/cultures"
replace_path="history/province_mapping"
replace_path="history/provinces"
replace_path="history/titles"
replace_path="history/struggles"
replace_path="map_data/geographical_regions"
```
(`replace_path="common/religion/doctrines"` is stale: the 1.19 dir is
`common/religion/doctrine_types` — `verified`, `ls VANILLA/common/religion/` has no `doctrines`.)

### 1.3 Union / intersection

| path | ATL | EK2 | GH | needed for map-only boot? |
|---|---|---|---|---|
| `common/landed_titles` | – | ✔ | ✔ | **yes** |
| `history/provinces` | ✔ | ✔ | ✔ | **yes** |
| `history/titles` | ✔ | ✔ | ✔ | **yes** |
| `history/characters` | ✔ | ✔ | ✔ | **yes** |
| `history/wars` | ✔ | ✔ | – (GH ships 2 files by name) | **yes** (1 vanilla file, 293 lines, hardcodes `location = 1596`) |
| `history/cultures` | – | ✔ | ✔ | yes (134 vanilla files keyed by province id) |
| `history/province_mapping` | – | – | ✔ | **yes** (6 vanilla files, `6254 = 6131` province→province) |
| `history/struggles` | – | ✔ | ✔ | optional |
| `history/artifacts` | ✔ | ✔ | – | no — vanilla file is 3 bytes (BOM only) |
| `map_data/geographical_regions` | – | – | ✔ | **yes** |
| `map_data` | ✔ | – | – | **no** (override by filename instead) |
| `common/bookmark_portraits` | – | ✔ | ✔ | optional |
| `common/religion/holy_site_types` | – | ✔ | – (GH overrides by name) | **yes**, one way or the other |
| `common/religion/religion_types` | – | ✔ | ✔ | no, if holy_site_types is fixed |
| `common/culture/cultures`, `name_lists` | – | ✔ | ✔ | **no** (see §4, cultures are map-clean) |
| `common/dynasties`, `dynasty_houses` | ✔ | ✔ (dynasties) | ✔ (dynasties) | **no** (map-clean) |
| `common/province_terrain` | – | ✔ | – | no (2 files, override by name) |
| `common/decisions`, `achievements`, `coat_of_arms/coat_of_arms` | – | – | ✔ | optional, see §4 tier B |
| `tests` | ✔ | – | – | optional |

---

## 2. Atlantis neutralisation inventory

Atlantis's own statement of intent (`ATL/README.md`):
> "Atlantis replaces or otherwise masks all provinces, titles, regions, cultures, religions, and characters in CK3. […] All duchies, kingdoms, and empires are preserved as landless titles with a shared placeholder capital. All cultures and religions are left untouched but hidden through GUI changes. All holy sites are set to a shared placeholder county. […] The placeholder province is 1, corresponding to b_atlantis. The placeholder county is c_atlantis. The placeholder character is 1, 'Atlas.'"
> "It's worth mentioning that Atlantis replaces whole files, not objects within files."

### 2.1 Shape of the tree

- `verified`: 282 files total. Of the 263 `.txt`/`.gui`/`.yml` files, **238 sit at a path that also
  exists in vanilla 1.19** (i.e. they are whole-file overrides) and **25 are new**.
- `verified`: placeholder token occurrences across the mod — `c_atlantis` 2195, `character:1` 1489,
  `b_atlantis` 471, `d_atlantis` 8. It is a search-and-replace layer, not a stub layer.
- **There is no "ship an empty file" pattern anywhere in Atlantis.** Only three files are
  effectively empty, and they are unrelated dumps: `credits.txt`, `credit_portraits.txt` and the
  three `common/coat_of_arms/dynamic_definitions/*.txt` (3 bytes = BOM only). Everything else is a
  full vanilla copy with vanilla ids rewritten, or a new placeholder definition.

### 2.2 Per-directory, what it ships and why

| path | files | empty / stub / rewritten vanilla | why |
|---|---|---|---|
| `common/landed_titles/00_landed_titles.txt` | 1, 63 KB | **rewritten vanilla**: 1109 title blocks, `verified` 0 `province =` lines, `verified` all 1109 `capital = c_atlantis`, each `landless = yes` (`ATL/common/landed_titles/00_landed_titles.txt:16-19`) | keeps every vanilla e/k/d tag *resolvable* so `title:k_france`-style script references do not dangle, while owning no land |
| `common/landed_titles/atlantis_landed_titles.txt` | 1, 1.1 KB | **new stub**: `e_atlantis > k_atlantis > d_atlantis > {c_atlantis, c_atlantis_b, c_atlantis_c}` with 9 baronies `province = 1..9` | the entire playable world |
| `common/religion/holy_sites/00_holy_sites.txt` | 1, 39 KB | **rewritten vanilla**: 380 blocks, `verified` 194 `county = c_atlantis`, `barony = b_atlantis` where vanilla had one | holy sites are mandatory per faith; repointing the county keeps all vanilla faiths valid. **Path is dead in 1.19** — see §2.3 |
| `common/religion/religions/atlantis_atlantite.txt` | 1, 8 KB | **new**: one religion + one faith | a faith for the placeholder character. **Path is dead in 1.19** |
| `common/bookmarks/bookmarks/00_bookmarks.txt` | 1, 479 B | **stub, one bookmark** — full text in §5 | a bookmark is required to start; it needs a live `history_id` and `title` |
| `common/bookmarks/groups/00_bookmark_groups.txt` | 1, 55 B | **stub**: `bm_group_atlantis = { default_start_date = 1.1.1 }` | this is where `default_start_date` lives; `verified` vanilla has it only at `VANILLA/common/bookmarks/groups/00_bookmark_groups.txt:2,6,10` (867/1066/1178) — **not** in `common/defines` |
| `common/bookmarks/challenge_characters/00_challenge_characters.txt` | 1, 383 B | **stub**, same character as HARD | vanilla's file names vanilla characters |
| `common/bookmark_portraits/` | 2, ~9 KB each | **new**: `# Auto generated file … Created using console command dump_bookmark_portraits` + a `genes={}` block | cosmetic; `verified` vanilla's 332 files are pure gene data with zero title/province refs |
| `history/provinces/k_atlantis.txt` | 1, 543 B | **stub**: provinces 1-9, three with `culture/religion/holding = castle_holding`, six `holding = none` | province history keyed by numeric id |
| `history/titles/k_atlantis.txt` | 1, 216 B | **stub**: `d_atlantis`/`c_atlantis`(+b/c) `1.1.1 = { holder = 1 }`, duchy also `government = feudal_government` | someone must hold the land at start |
| `history/characters/` | 3 | `atlantis.txt` **new** (13 lines, char `1` "Atlas"); `eastereggs.txt` + `easteregg_non_developers.txt` are **trimmed vanilla copies** (114 KB vs 143 KB, 3.1 KB vs 9.2 KB) | the easter-egg characters are referenced by `gfx/portraits/portrait_modifiers/02_all_developer_characters.txt`, so they are kept and pruned rather than deleted |
| `common/dynasties/` | 2 | `atlantis_dynasties.txt` **new** (`1 = { name = "dynn_atlas" culture = "greek" }`); `01_vanity_dynasties.txt` a vanilla copy re-added after `replace_path` dropped all 8 vanilla files | the ruler designer needs vanity dynasties |
| `common/dynasty_houses/` | **0 files** | `replace_path` with nothing shipped = pure delete | — |
| `history/wars/`, `history/artifacts/`, `tests/` | **0 files** | pure delete via `replace_path` | vanilla `history/wars/00_wars.txt` hardcodes `targeted_titles={ k_england }` and `location = 1596` |
| `common/province_terrain/` | 2 | `00_province_terrain.txt` **stub** (`default_land=plains` + `1..9=plains`); `01_province_properties.txt` **stub** (1.7 KB) | overridden by filename, not `replace_path` |
| `map_data/geographical_regions/geographical_region.txt` | 1, 15 KB | **rewritten vanilla**: same region keys, `verified` only 2 `duchies=`, 1 `counties=`, 2 `provinces=`, 16 `regions=` blocks left, all pointing at `d_atlantis` | 328 `duchies=` blocks in vanilla; regions must resolve or de-jure/AI/disaster code breaks |
| `common/culture/` | 3 | **new only**: 1 heritage pillar, 1 culture, 1 traditions file. Vanilla cultures are left loaded and hidden in `gui/window_faith.gui` + `common/on_action/game_start.txt` (`religion:x = { set_variable = religion_invisible }`) | vanilla cultures are map-clean; masking is cosmetic |
| ~200 further files under `common/{decisions,scripted_effects,scripted_triggers,on_action,story_cycles,achievements,casus_belli_types,activities,council_positions,council_tasks,script_values,customizable_localization,...}` and `events/` | 238 overrides total | **rewritten vanilla copies** with `c_<vanilla>` → `c_atlantis`, `title:x` → placeholder, `character:<id>` → `character:1` | this is the bulk of the work and the reason the template exists |

### 2.3 Atlantis is stale against 1.19

| break | evidence |
|---|---|
| Declares `supported_version="1.16.*"` | `ATL/descriptor.mod:16` |
| `common/religion/holy_sites/` **does not exist in 1.19**; the dir is `common/religion/holy_site_types/` | `verified` `ls VANILLA/common/religion/` → `doctrine_group_types doctrine_types holy_site_types religion_family_types religion_types` only. Atlantis's 39 KB holy-site neutralisation therefore loads nowhere, and vanilla's real `00_holy_site_types.txt` (322 blocks, 326 `county =` lines) stays live and broken |
| `common/religion/religions/` also does not exist in 1.19 → the Atlantite faith never loads | same `ls` |
| Its `00_landed_titles.txt` neutralises 1109 titles. Vanilla 1.19 ships **11 files** in `common/landed_titles/` (`00_landed_titles.txt`, `01_japan.txt`, `01_japan_noble_family.txt`, `01_korea_noble_family.txt`, `01_other_noble_family.txt`, `02_china.txt`, `03_seasia.txt`, `04_china_noble_families.txt`, `05_goryeo.txt`, `06_philippines.txt`, `_landed_titles.info`) totalling **11 298 `province = ` lines**, 10 042 baronies, 4 417 counties, 1 036 duchies, 268 kingdoms, 88 empires. Atlantis covers `00_landed_titles.txt` only; the other 10 files load in full and point at 2 140+ nonexistent provinces | `verified` counts over `VANILLA/common/landed_titles/` |
| It declares `replace_path="map_data"` but ships **no** `rivers.png`, `heightmap.png`, `packed_heightmap.png`, `indirection_heightmap.png`, `heightmap.heightmap` or `seasons.txt`, all of which its own `default.map` requires (`ATL/map_data/default.map:5,7,13`). **As cloned it cannot boot.** | `verified` `ls ATL/map_data/` = `adjacencies.csv climate.txt default.map definition.csv island_region.txt provinces.png geographical_regions/` |
| Its two `replace_path` lines for `common/bookmarks` and `map_data` are no-ops for the subdirs that matter (fact 0.1) | — |
| **No LICENSE, COPYING or licence statement anywhere in the repo** | `verified` `find ATL -maxdepth 2 -iname '*licen*' -o -iname '*copying*'` → empty; `README.md`/`README.txt` contain no grant. Default: all rights reserved. Take-it-or-leave-it wording ("So, take it or leave it") is not a licence |

---

## 3. Recommendation

**Build our own bootstrap layer, generated by the converter from the installed vanilla 1.19 tree at
build time. Use the Atlantis *technique*, vendor none of its files.**

Reasons:

1. **Licence.** `verified`: Atlantis ships no LICENCE file, so it is all-rights-reserved by
   default. `docs/DECISIONS.md` (2026-09-07) already rules that we accept only packs with an
   explicit licence or written permission, and `forgotten_kings` is GPL-3.0. Vendoring 238 files of
   modified Paradox script from an unlicensed third-party repo into a public repo is out.
2. **It is stale and silently so.** `verified`: two of its neutralisation paths
   (`common/religion/holy_sites/`, `common/religion/religions/`) no longer exist in 1.19, and its
   `landed_titles` neutralisation covers 1 of vanilla's 11 files. The failures are *silent* — the
   files just never load.
3. **238 vendored vanilla-1.16 file copies would shadow their 1.19 counterparts**, reverting three
   patches' worth of Paradox script and re-breaking on every future patch. That is the exact
   maintenance trap `docs/PROJECT.md` avoids with "converted mod is never hand-edited".
4. **The neutralisation is mechanical, so the converter should do it.** Every one of the 238
   overrides is "copy vanilla file, rewrite `c_x`/`b_x`/`character:<id>` to a placeholder". Reading
   `$CK3_GAME/…` at build time and emitting the rewritten copies is a ~200-line converter step,
   is re-runnable per patch, has no licence question about *our* repo (the output is a derived
   Paradox file, same as any mod), and needs no upstream to track.
5. **It cannot boot as cloned** (missing heightmap/rivers/seasons, §2.3) so "Atlantis as base layer"
   is not even a working starting point; we would be reimplementing `map_data` anyway — which lane
   `map-physical` already does (`docs/design_map.md` §A).

Keep from Atlantis (ideas, not files):
- one placeholder province / barony / county / character / dynasty, everything repointed at it;
- vanilla e/k/d titles preserved as `landless = yes` with the placeholder capital, so ~700 of the
  1 408 script title references resolve for free with one generated file;
- masking vanilla cultures/faiths with a `religion_invisible` variable rather than deleting them.

---

## 4. Scale of the neutralisation problem (measured on 1.19)

`verified` — distinct title tags referenced as `title:<tag>` across `VANILLA/common`, `events`, `gui`:

| tier | distinct tags | fixable by shipping a landless title? |
|---|---|---|
| `e_` | 78 | yes |
| `k_` | 167 | yes |
| `d_` | 459 | yes |
| `c_` | 422 | **no** — a county needs ≥1 barony, a barony needs a province |
| `b_` | 282 | **no** — same |
| total | **1408** | 704 free, 704 need file edits |

`verified`: **151 vanilla files** contain a `title:c_…` or `title:b_…` reference. All three surveyed
TCs neutralise **100 %** of them — EK2 overrides all 151 by filename; Godherja overrides 143 and
deletes the remaining 8 via `replace_path="common/decisions"`; Atlantis rewrites them. **No shipped
1.19 TC leaves a county- or barony-tier vanilla title reference dangling.** Treat that as the
strong prior; `assumed` that some subset is merely error.log noise rather than fatal, and the first
boot plus `ck3-tiger` will tell us which.

Distribution of the 151 (`verified` hit-file counts per dir): `events/` 112 of 536 ·
`common/decisions` 42 of 69 · `common/scripted_effects` 40 of 166 · `common/scripted_triggers` 31 of
135 · `common/activities` 16 of 62 · `common/on_action` 15 of 165 · `common/casus_belli_types` 10 of
26 · `common/achievements` 7 of 10 · `common/story_cycles` 7 of 52 · `common/important_actions` 2 of
33 · `common/council_positions` 1 of 2.

`verified` **map-clean** — no province id or title tag anywhere, leave vanilla alone:
`common/culture/cultures` (56 files), `common/culture/pillars`, `common/culture/name_lists` (53),
`common/dynasties` (8), `common/dynasty_houses` (5), `common/defines` (no province id, no start
title, no map dimensions), `common/court_positions` (45), `common/game_rules`, `common/travel`,
`common/bookmark_portraits` (332, pure `genes={}`).
`common/coat_of_arms/coat_of_arms` is title-**keyed** (1 878 blocks) but lookup-only: an entry for a
title that no longer exists is inert (`assumed`, consistent with EK2 not replacing it).

`verified` **not** in `common/`: geographical regions live at `map_data/geographical_regions/`
(3 vanilla files; the main one has 328 `duchies={}`, 39 `counties={}`, 26 `provinces={}` numeric-id
blocks, 7 `kingdoms={}`, 1 `empires={}`).

---

## 5. The minimal file set the converter must emit

Placeholder names used below (converter constants, `fae_` prefix per `docs/PROJECT.md`):

| constant | value |
|---|---|
| placeholder province id | `1` (first land row of `definition.csv`) |
| placeholder barony | `b_fae_void` |
| placeholder county | `c_fae_void` |
| placeholder duchy / kingdom / empire | `d_fae_void` / `k_fae_void` / `e_fae_void` |
| placeholder character id | `1` |
| placeholder dynasty key | `fae_void` (string key, avoids collision with vanilla numeric ids) |
| placeholder culture / faith | vanilla `greek` / `catholic` (both map-clean, §4) |
| start date | `1368.9.2` (Faerûn CK2 start, `docs/design_map.md` §B) |

### Tier A — boot blockers (must ship)

- [ ] **`descriptor.mod`** — stub, verbatim:
  ```
  version="0.0.0"
  tags={
  	"Total Conversion"
  }
  name="Faerun (CK2 conversion, raw)"
  replace_path="common/landed_titles"
  replace_path="history/characters"
  replace_path="history/cultures"
  replace_path="history/province_mapping"
  replace_path="history/provinces"
  replace_path="history/struggles"
  replace_path="history/titles"
  replace_path="history/wars"
  replace_path="map_data/geographical_regions"
  supported_version="1.19.*"
  ```
  No `path=` (that belongs in the launcher-side `.mod` file, not the descriptor).
  No `picture=` — `verified` Steam ignores it and uses `thumbnail.png`.
- [ ] **`.metadata/metadata.json`** — **do not emit.** `verified`: none of ATL/EK2/GH has one;
  `ck3-tiger` v1.19.0 cannot read one. Revisit only for a Paradox Mods upload.
- [ ] **`thumbnail.png`** — any image. `assumed` non-fatal if missing (launcher shows a blank tile).
- [ ] **`map_data/`** — override by filename, **no `replace_path`**. Required set, `verified` from
  `VANILLA/map_data/default.map:2-13` + `VANILLA/map_data/heightmap.heightmap`:
  `default.map`, `definition.csv`, `provinces.png`, `rivers.png`, `heightmap.png`,
  `packed_heightmap.png`, `indirection_heightmap.png`, `heightmap.heightmap`, `seasons.txt`,
  `island_region.txt`, `adjacencies.csv`. `climate.txt` and `positions.txt` are commented out in
  vanilla's own `default.map` → optional. `continent.txt` is *referenced* by vanilla's `default.map:9`
  and **does not exist in vanilla** → `verified` a dangling `continent =` line is tolerated.
  `nodes.dat` is a generated pathfinding cache; EK2 and GH ship one, `assumed` not required.
  Content of these files is lane `map-physical` tasks 1-5 (`docs/design_map.md`), not this doc.
- [ ] **`map_data/geographical_regions/`** — `replace_path`. Minimum: one file re-declaring every
  vanilla region key with our placeholder, so nothing dangles. Stub shape:
  ```
  world_europe = { duchies = { d_fae_void } }
  # … one line per vanilla region key, all pointing at d_fae_void
  ```
  Generate the key list from `VANILLA/map_data/geographical_regions/*.txt` (3 files) at build time.
  Alternative, cheaper: emit only the regions our own script needs and accept "region not found"
  errors — `assumed` non-fatal, but Atlantis chose to keep every key.
- [ ] **`common/landed_titles/`** — `replace_path`. Two generated files:
  - `00_vanilla_landless.txt` — every vanilla `e_`/`k_`/`d_` tag (1 392 of them,
    `verified` 88 + 268 + 1 036) as:
    ```
    k_france = {
    	capital = c_fae_void
    	landless = yes
    }
    ```
    Generate the tag list from `VANILLA/common/landed_titles/*.txt` — all 11 files, not just
    `00_landed_titles.txt`. This resolves 704 of the 1 408 script title references (§4).
  - `10_fae_titles.txt` — the real Faerûn tree from the converter, containing `c_fae_void` /
    `b_fae_void` on the placeholder province plus the converted counties/baronies.
- [ ] **`common/landed_titles/` must cover every land province** in `definition.csv` with exactly
  one barony; sea/lake/impassable ids go in `default.map` instead. `assumed`: a land province with
  no barony is the "passable land, but not part of any title" case that vanilla's own `default.map`
  comment calls out (`VANILLA/map_data/default.map`, `# UNUSED PROVINCES` block).
- [ ] **`history/provinces/`** — `replace_path`. One generated file per de-jure kingdom. Stub shape
  (from `ATL/history/provinces/k_atlantis.txt:6-14`):
  ```
  1 = {
  	culture = greek
  	religion = catholic
  	holding = castle_holding
  }
  2 = {
  	holding = none
  }
  ```
  Every land province id must appear; `holding = none` is the valid "empty" value.
- [ ] **`history/titles/`** — `replace_path`. Stub, one file, verbatim shape from
  `ATL/history/titles/k_atlantis.txt`:
  ```
  d_fae_void = {
  	1368.9.2 = {
  		holder = 1
  		government = feudal_government
  	}
  }
  c_fae_void = {
  	1368.9.2 = {
  		holder = 1
  	}
  }
  ```
  Plus one `holder = 1` block per converted county so no county is unheld.
- [ ] **`history/characters/`** — `replace_path`. Stub, one file, verbatim:
  ```
  1 = {
  	name = "Placeholder"
  	dynasty = fae_void
  	religion = "catholic"
  	culture = "greek"
  	1330.1.1 = {
  		birth = yes
  	}
  }
  ```
  Do **not** re-add vanilla's easter-egg files unless `gfx/portraits/portrait_modifiers` errors
  matter (`assumed` they are warnings; Atlantis kept them, EK2/GH did not).
- [ ] **`history/cultures/`** — `replace_path`, ship nothing. `verified` 134 vanilla files keyed by
  province id.
- [ ] **`history/province_mapping/`** — `replace_path`, ship nothing. `verified` 6 vanilla files of
  `<province id> = <province id>`.
- [ ] **`history/wars/`** — `replace_path`, ship nothing. `verified` 1 vanilla file, 293 lines,
  `targeted_titles={ k_england }` and `location = 1596`.
- [ ] **`history/struggles/`** — `replace_path`, ship nothing. 5 vanilla files.
- [ ] **`common/dynasties/fae_void_dynasties.txt`** — new file, no `replace_path` (vanilla dynasties
  are map-clean, §4). Stub, verbatim:
  ```
  fae_void = {
  	name = "dynn_fae_void"
  	culture = "greek"
  }
  ```
- [ ] **`common/religion/holy_site_types/00_holy_site_types.txt`** — override by filename (the file
  name must match vanilla's exactly, `verified`; this is Godherja's pattern). Re-emit **all 322
  vanilla keys** with the county repointed:
  ```
  jerusalem = {
  	county = c_fae_void
  }
  rome = {
  	county = c_fae_void
  }
  # … 320 more, key list generated from VANILLA/common/religion/holy_site_types/00_holy_site_types.txt
  ```
  Drop the `barony =` and `character_modifier` blocks; keep `parameters` blocks if any faith
  doctrine reads them (`assumed` needed — vanilla has flags like `jerusalem_conversion_bonus`).
  **How to avoid needing this:** you cannot, unless you also `replace_path` all of
  `common/religion/religion_types` (49 files) — `verified` those hold 718 `holy_site = <key>` lines
  that must resolve. Repointing 322 counties in one generated file is far cheaper than authoring
  49 faith files, so keep vanilla faiths for the map-only boot.
- [ ] **`common/province_terrain/00_province_terrain.txt`** — override by filename. Stub:
  ```
  default_land=plains
  default_sea=sea
  default_coastal_sea=coastal_sea
  1=plains
  ```
  plus one `<id>=<terrain>` line per land province from the converter's terrain step.
- [ ] **`common/province_terrain/01_province_properties.txt`** — override by filename; a header-only
  file is enough for boot (`assumed`; `ATL`'s is 1.7 KB of comments plus filler).
- [ ] **`common/bookmarks/groups/00_bookmark_groups.txt`** — override by filename. Stub, verbatim:
  ```
  bm_group_fae = {
  	default_start_date = 1368.9.2
  }
  ```
  `verified`: this is the only place `default_start_date` exists in vanilla
  (`VANILLA/common/bookmarks/groups/00_bookmark_groups.txt:2,6,10`); it is **not** in
  `common/defines`.
- [ ] **`common/bookmarks/bookmarks/00_bookmarks.txt`** — override by filename (do **not** use
  `replace_path="common/bookmarks"`, fact 0.1). Stub, verbatim shape from
  `ATL/common/bookmarks/bookmarks/00_bookmarks.txt`:
  ```
  bm_fae_void = {
  	start_date = 1368.9.2
  	is_playable = yes
  	group = bm_group_fae

  	weight = {
  		value = 0
  	}

  	character = {
  		name = "bookmark_fae_void"
  		dynasty = fae_void
  		dynasty_splendor_level = 1
  		type = male
  		birth = 1330.1.1
  		title = d_fae_void
  		government = feudal_government
  		culture = greek
  		religion = catholic
  		difficulty = "BOOKMARK_CHARACTER_DIFFICULTY_MEDIUM"
  		history_id = 1
  		position = { 200 400 }
  		animation = personality_bold
  	}
  }
  ```
  Constraints, `verified` from `VANILLA/common/bookmarks/bookmarks/_bookmarks.info`: `history_id`
  must name a character that exists in `history/characters`, `title` must be a title that character
  holds at `start_date`, `group` must name a declared bookmark group. `position` is map pixels for
  the selection UI — cosmetically wrong is not fatal (`assumed`).
- [ ] **`common/bookmarks/challenge_characters/00_challenge_characters.txt`** — override by filename.
  Same character block, `BOOKMARK_CHARACTER_DIFFICULTY_HARD`, no `position`. Needed because
  vanilla's file names vanilla characters (`assumed` non-fatal, cheap to do).
- [ ] **`localization/english/fae_bootstrap_l_english.yml`** — UTF-8 **with BOM**, `l_english:`
  header. Keys: `bookmark_fae_void`, `bookmark_fae_void_desc`, `dynn_fae_void`, plus the title names
  (`d_fae_void`, `c_fae_void`, `b_fae_void`, `k_fae_void`, `e_fae_void`) and every generated county.
  Missing loc renders the raw key — `assumed` non-fatal.

### Tier B — error.log hygiene (do it, but it does not block first boot)

- [ ] **`common/bookmark_portraits/`** — `replace_path`, ship nothing, or one file per bookmark
  character. Missing entry → the portrait is derived from the character's DNA (`assumed`).
  `verified` vanilla's 332 files are gene data only, so leaving them is harmless but noisy.
- [ ] **The 151 vanilla files carrying `title:c_…` / `title:b_…`** — the converter reads each from
  `$CK3_GAME`, rewrites every county/barony tag to `c_fae_void` / `b_fae_void` and every
  `character:<numeric id>` to `character:1`, and writes it to the same relative path. §4 has the
  per-directory hit counts. **This is the single biggest item and the one Atlantis exists to do.**
  Cheaper shortcuts, in increasing risk: `replace_path="common/decisions"` (kills 42),
  `replace_path="common/achievements"` (7), `replace_path="common/story_cycles"` (7),
  `replace_path="common/casus_belli_types"` (10) — all shipping nothing. Do **not** `replace_path`
  `events/` or `common/on_action/`: `assumed` deleting event definitions that `on_action` entries
  still list is worse than dangling title refs.
- [ ] **`tests/`** — `replace_path`, ship nothing. `verified` vanilla ships 18 QA test files; the
  hardcoded title refs in them are commented out, so this is optional.
- [ ] **`common/on_action/game_start.txt`** + **`gui/window_faith.gui`** — only if we want to *hide*
  vanilla cultures/faiths rather than leave them selectable. Cosmetic; skip for a map-only boot.

### Explicitly NOT needed for a map-only boot (`verified` map-clean, §4)

`common/culture/**` · `common/dynasties` (beyond adding one file) · `common/dynasty_houses` ·
`common/defines` (no province id, no start title, no map-dimension define exists there — map size
comes from `map_data/heightmap.heightmap`'s `original_heightmap_size={ 18432 9216 }` and the image
dimensions, `verified`) · `common/coat_of_arms/**` · `common/court_positions` · `common/game_rules` ·
`common/travel` · `history/artifacts` (vanilla file is 3 bytes) · `map_data` as a `replace_path`.

---

## 6. DECISIONS.md line

`docs/DECISIONS.md` uses `- YYYY-MM-DD — <decision>. Reason: <reason>` (em dash, not pipes) —
`verified`, all 9 existing entries. The line to append, in that format:

```
- 2026-09-07 — Map bootstrap layer is generated by the converter from the installed vanilla 1.19 tree, not vendored from Atlantis: 9 `replace_path` entries, vanilla e/k/d titles re-emitted as `landless = yes` with a `c_fae_void` capital, all 322 `holy_site_types` counties repointed, one placeholder province/county/barony/character/dynasty/bookmark. Reason: Atlantis is unlicensed, targets 1.16.*, two of its neutralisation paths no longer exist in 1.19, it covers 1 of vanilla's 11 landed_titles files, and it cannot boot as cloned (`docs/output_bootstrap.md`).
```

If the pipe format from the task brief is wanted instead:

```
2026-09-07 | map bootstrap | converter generates its own neutralisation layer from vanilla 1.19; Atlantis used as reference only | unlicensed, 1.16-era, two dead paths in 1.19, covers 1 of 11 landed_titles files, cannot boot as cloned
```

---

## 7. Known failure modes

Verified anchors first, then the error.log shapes.

`verified` from mod sources:
- `ATL/README.md` states the intended end state and the debugging loop: run with `-debug_mode
  -develop`, "error.log should have a lot of errors involving your provinces, but none should cause
  crashes" after `map_data` alone, then fewer after `landed_titles`/`province_terrain`/
  `geographical_regions`, then "Clean up any bookmark-related crashes or substantial errors" after
  bookmarks. **So: province errors are non-fatal, bookmark errors can crash.**
- `ATL/map_data/island_region.txt:7-9` documents the accepted keys: `duchies = { }` "takes county
  title names declared in landed_titles.txt", `counties = { }`, `provinces = { }` "takes province id
  numbers declared in /history/provinces".
- `VANILLA/map_data/default.map` `# UNUSED PROVINCES` comment: "These provinces cause issues because
  they are passable land, but not part of any title."

`assumed` — error.log shapes when each piece is missing (from knowledge, to be replaced with real
lines after the first boot; log at `~/.local/share/Paradox Interactive/Crusader Kings III/logs/error.log`):

| missing / wrong | error.log shape | fatal? |
|---|---|---|
| `landed_titles` barony names a province id absent from `definition.csv` | `Province <id> in title b_x does not exist` / `[titles] Unknown province` | error, sometimes crash on map init |
| land province in `definition.csv` with no barony | `Province <id> is not part of any title` | error only; province is unclickable |
| `definition.csv` row count vs `provinces.png` colour set mismatch | `Province <id> has no pixels on the province map` / `Unknown color (r,g,b) in provinces.png` | error per province; a colour with no row is fatal |
| `default.map` sea/lake/impassable ranges not matching `definition.csv` | `Province <id> is defined as sea zone but has a land title` | error |
| `heightmap.heightmap` / `packed_heightmap.png` / `indirection_heightmap.png` missing or size-inconsistent | `Failed to load heightmap` / `Heightmap size mismatch` | **crash at load** |
| `rivers.png` missing or not 8-bit palette | `rivers.png is not an indexed image` | **crash / black map** |
| `history/provinces` entry for a province id that does not exist | `Invalid province id <id> in history/provinces/<file>` | error |
| `history/titles` block for a title tag not in `landed_titles` | `Unknown title <tag> in history` | error |
| `history/titles` holder id not in `history/characters` | `Character <id> does not exist` | error, and the title starts unheld |
| county with no holder at start date | `Title c_x has no holder` | error; AI/de-jure oddities |
| `holy_site_types` entry whose `county` does not exist | `Holy site <key> refers to unknown county c_x` | error, and GHW/holy-war code can crash on use |
| faith `holy_site = <key>` where the key is undeclared | `Faith x refers to unknown holy site <key>` | error |
| `geographical_regions` naming an absent duchy/county/province | `Region <key>: unknown duchy d_x` | error; `assumed` de-jure hegemony and disaster code degrade, do not crash |
| bookmark `history_id` naming a nonexistent character | `Bookmark bm_x: character <id> not found` | **crash / empty bookmark screen** — the one Atlantis's README warns about |
| bookmark `title` the character does not hold at `start_date` | `Bookmark character has no title` | **crash on start / unplayable bookmark** |
| no bookmark group, or `group` naming an undeclared group | `Unknown bookmark group bm_group_x` | **crash / no start date offered** |
| no playable bookmark at all | bookmark list empty | **cannot start a game** |
| `title:<tag>` in script where the tag is undeclared | `Unknown title title:c_x` at file:line, once per reference at load | error spam; `assumed` non-fatal, but §4 shows no shipped TC relies on that |
| `character:<id>` in script where the id is gone | `Character <id> not found` | error |
| `province_terrain` entry for an absent province | `Unknown province <id> in province_terrain` | error; `default_land` covers the reverse case |
| `descriptor.mod` `supported_version` below the running patch | launcher marks the mod "not compatible"; game still loads it | warning |

Verification plan (lane `map-physical`, before shipping): run
`ck3-tiger --game "$CK3_GAME" mods/faerun_ck2_to_ck3_converted/descriptor.mod` and boot once with
`-debug_mode -develop`, then replace every `assumed` row above with the real line.
