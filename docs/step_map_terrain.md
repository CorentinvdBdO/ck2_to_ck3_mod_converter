# Step `map`, gameplay-terrain half: the CK2 province-history `terrain = X` override

**Question this answers.** Where does a CK3 province's `common/province_terrain`
entry come from? Until lane `province-terrain` the answer was "the majority CK2
terrain category over its pixels, always" — `ck2ck3.map.terrain`. That is only
CK2's *fallback*. CK2's real rule is:

> A province's gameplay terrain is the `terrain = <category>` line in its
> `history/provinces` file. Only when there is no such line does the engine
> derive it from `terrain.bmp`.

**1040 of Faerûn's 2125 province files carry that line** and **716 of them
disagree with their own bitmap** (`scripts/survey_terrain_history.py`,
`docs/evidence/terrain_history_survey.md`), so half of Faerûn's counties were
shipping a terrain the CK2 author did not choose. The single worst case:
Faerûn's `terrain.bmp` almost never paints farmland, so the map had **16**
farmland provinces where the author declared **123 farmland counties**.

**Answer.** `ck2ck3.map.terrain_history` reads the override, resolves it through
`mappings/terrain_history_overrides.csv` (one explicit decision per CK2
category, with the reasoning in the row), and folds it into the per-barony
bitmap vote with a measured county-capital rule (§3). `[map]
province_terrain_history = true`, default on.

| quantity | value (Faerûn) | label |
|---|---|---|
| CK2 province-history files | 2125 | `verified` |
| files carrying `terrain = X` | 1040 (48.9 %) | `verified` |
| of those, inside a **dated** block | **0** | `verified` |
| commented-out `#terrain =` lines (not overrides) | 69 | `verified` |
| counties whose override's CK3 key ≠ their bitmap's | 716 of 1040 (68.8 %) | `verified` |
| counties whose override the table says to `apply` | 899 | `verified` |
| CK3 provinces changed by the rule | **946** of 3705 baronies (25.5 %) | `verified` |
| `farmlands` provinces, before → after | 16 → 335 | `verified` |
| canvas pixels whose terrain **class** moves | 3,732,425 (6.61 %) | `verified` |
| terrain **paint** pixels changed | **0** — paint is per-pixel, not per-province | `verified` |
| trees placed, before → after | 711,875 → 700,622 (−1.6 %) | `verified` |
| ck3-tiger on the lane output | fatal 0, error 58 — unchanged | `verified` |

Reproduce: `uv run python scripts/survey_terrain_history.py` (the tallies) and
`PYTHONPATH=$PWD/src uv run python scripts/measure_terrain_history_effect.py`
(the before/after, two real `map` runs, ~50 s) →
`docs/evidence/terrain_history_effect.md`.

---

## 1. What the override is, and what shape it takes

`Faerun/Faerun/history/provinces/2529 - Wood of Sharp Teeth.txt`:

```
title = c_wood_of_sharp_teeth
max_settlements = 3
b_stepping_stones = tribal
culture = orc
religion = orc_pantheon
terrain = forest          <-- this line
```

Facts, all `verified` 2026-09-10 on the Faerûn clone:

* **1109 lines match `terrain\s*=` at all**; 1040 are real overrides and 69 are
  a commented-out, empty `#terrain = ` stub. The repo's `grep` is a shell
  function that fails on these Latin-1 files — use `command grep -a`.
* **Exactly one override per file**; no file declares two.
* **None is inside a dated block.** So on Faerûn the override is a static
  property, not a history. The reader
  (`ck2ck3.map.holdings.ProvinceHistory.terrains` /
  `.terrain_at(date)`) still resolves by date the way `culture_at` does,
  because CK2 permits a dated one and the next total conversion may use it.
* Thirteen distinct categories are used. Four of them — `coastal` (141),
  `subterranean` (60), `glacier` (38), `arctic` (10) — are Faerûn inventions
  declared in its own `map/terrain.txt` `categories` block, not CK2 vanilla.

| CK2 category | provinces | | CK2 category | provinces |
|---|---|---|---|---|
| `forest` | 202 | | `subterranean` | 60 |
| `hills` | 169 | | `glacier` | 38 |
| `coastal` | 141 | | `plains` | 36 |
| `jungle` | 125 | | `marsh` | 26 |
| `farmlands` | 123 | | `desert` | 23 |
| `mountain` | 84 | | `arctic` | 10 |
| | | | `steppe` | 3 |

## 2. The decision table, and the four invented categories

`mappings/terrain_history_overrides.csv`. One row per CK2 category:
`action` is `apply` (the override wins, subject to §3) or `keep_bitmap` (the
override is not a landscape statement and the pixels stand); `ck3_terrain` is
the CK3 1.19 key; `note` carries the evidence. A category with **no row** keeps
the bitmap and is counted as `unmapped` in the run report — never guessed.

The evidence used for each decision is the distribution of the *bitmap*
majority under each override, measured at CK2-province resolution
(`docs/evidence/terrain_history_survey.md` §3).

| CK2 category | decision | why, in one line |
|---|---|---|
| `coastal` (141) | **`keep_bitmap`** | see below |
| `subterranean` (60) | `apply` → `mountains` | the Underdark; CK2's harshest habitable category (movement 1.6, supply 1, bottleneck 45), and CK3's `mountains` (supply −0.5, dev −0.25, movement 0.5) is the nearest. Only 24 of 60 vote mountains from pixels — the other 36 are the *surface* painted above the caverns. |
| `glacier` (38) | `apply` → `taiga` | 36 of 38 already vote `taiga`; the override changes 2. Same key the pixel table uses, and paint/gameplay must not disagree about it. |
| `arctic` (10) | `apply` → `taiga` | 9 of 10 already vote `taiga`. |
| the other nine | `apply` → the pixel table's own key | no new decision: `forest`, `hills`, `jungle`, `farmlands`, `mountain`, `plains`, `marsh`, `desert`, `steppe` all already have a CK3 key in `ck2ck3.map.terrain.CK2_TO_CK3_TERRAIN`. |

### 2.1 Why `coastal` keeps the bitmap

Three pieces of evidence, none of them a guess:

1. **CK2 declares `coastal` as farmlands-with-a-chokepoint, not as ground.**
   `Faerun/Faerun/map/terrain.txt`: `coastal` has `movement_cost = 1.1`,
   `max_attrition = -0.01`, `supply_limit = 5` and `color = { 137 104 165 }` —
   character for character the `farmlands` entry, except `bottleneck_chance`
   15 vs 5. It is an economic/naval tag layered on good land.
2. **CK3 already delivers all of it.** CK3 has no coastal terrain because it
   derives coastal-ness from the map: ports, docks and coastal buildings key
   off province adjacency to water, which our `provinces.png` gives them for
   free. There is nothing left for a terrain key to carry.
3. **The bitmap under it is five different landscapes with no winner** —
   plains 63.1 %, desert 18.4 %, hills 9.2 %, arctic 7.1 %, jungle 2.1 % —
   unlike every other category here, and the province names are overwhelmingly
   islands and rocks: Ruathym, Purple Rocks, The Whalebones, Tuern, al-Faraq
   Islands, Maribar Island, Gundarlun, Flamsterd. Mapping it to `farmlands`
   (what the *pixel* table does, harmlessly — `terrain.bmp` has zero `coastal`
   pixels) would hand 141 counties CK3's single strongest terrain (+0.5 supply,
   +0.2 development growth), 36 of them arctic or desert islets whose ground
   texture would still paint snow and sand.

**Reversible in one edit**: set that row to `apply,farmlands`. No code change.

## 3. County override, barony terrain: the application rule

The CK2 override is per *province*, i.e. per CK3 *county*. Our terrain is per
*barony*, because one CK2 county becomes several CK3 provinces
(`docs/step_map_baronies.md`). Two invariants pull against each other: the
author's word, and the only per-barony information we have (its own pixels).

**Measured first** (`docs/evidence/terrain_history_effect.md` §1), over the 899
counties whose override the table applies:

| question | counties | share |
|---|---|---|
| county-**capital** barony's bitmap already equals the override | 333 | 37.0 % |
| **all** the county's baronies already equal it | 277 | 30.8 % |
| at least one barony equals it | 401 | 44.6 % |
| per barony: already equal | 553 of 1681 | 32.9 % |

So the bitmap contradicts the author about two thirds of the time, and it does
so no more reliably at the capital (37.0 %) than county-wide (32.9 %). There is
no reading of the data in which the bitmap is the better source.

**The rule** (`ck2ck3.map.terrain_history.apply_overrides`):

1. The **county-capital** barony always takes the override. It is the barony
   the CK2 province's own history file is about, it inherits the CK2 capital
   position (`docs/step_map_assets.md`), and it is where a player reads the
   county's terrain.
2. A **non-capital** barony takes the override only when its own bitmap
   majority is a *weak* class — `plains` or `farmlands`, `[map]
   terrain_history_weak_classes`. Those are the two CK2 categories that assert
   no relief and no vegetation, and `plains` is also the vote's own no-data
   fallback (`[map.terrain] default`), so "plains" frequently means "nothing
   was painted here" rather than "this is a plain".
3. Otherwise the barony keeps its own bitmap terrain. A mountain barony inside
   an authored `farmlands` county stays mountains.

**What that costs, measured**: 563 capitals take the override, 383 non-capitals
take it on a weak bitmap, 182 non-capitals keep a strong bitmap, 553 already
agreed. Capital-only would have changed 563 provinces; all-baronies 1128; this
rule 946.

The 182 are the whole argument. CK2 had no sub-county terrain at all, so *any*
per-barony answer is information the author never expressed — and where our own
measured pixels make a specific statement (mountains, jungle, desert), CK2's
own fallback ordering is the precedent for trusting them. `[map]
terrain_history_weak_classes = []` reduces the rule to capital-only;
`["plains","farmlands","steppe","taiga","drylands"]` pushes it toward
all-baronies.

## 4. Config keys

`[map]`, `configs/faerun.toml`:

| key | default | meaning |
|---|---|---|
| `province_terrain_history` | `true` | honour the override at all. `false` is exactly the pre-lane behaviour. |
| `terrain_history_csv` | `mappings/terrain_history_overrides.csv` | the decision table |
| `terrain_history_weak_classes` | `["plains","farmlands"]` | §3 step 2 |

All three are read in **both** config front doors —
`ck2ck3.map.config.load` (the standalone TOML) and
`ck2ck3.steps.map._map_config` (the real CLI) — and
`tests/test_map_terrain_history.py::test_cli_config_builder_reads_the_key` pins
that. A `[map]` key the CLI builder never reads is a silent no-op whatever the
TOML says; that is how `[map] colormap = false` was ignored for two builds.

Run report, `report["terrain_history"]`: `overrides_in_ck2_history`,
`counties_with_override`, `provinces_changed`, one count per outcome
(`already_agreed`, `applied_capital`, `applied_weak_bitmap`,
`kept_strong_bitmap`, `kept_rule`, `kept_unmapped`, `no_override`),
`unmapped_categories`, and the class-grid pixel shift of §5. Evidence:
`docs/evidence/terrain_history_baronies.csv`, one row per affected CK3 province.

## 5. What else moves — and what does not

The override is applied **after** impassability is decided, on purpose:
`impassable_ck3` in `ck2ck3.map.build` stays a pure `terrain.bmp` property
(the CK2 category vote), exactly as before this lane. Faerûn declares
`impassable_mountains` in no history file anyway.

| consumer | reads | moved by this lane |
|---|---|---|
| `common/province_terrain` | per province | **yes** — this is the point. §3 histogram. |
| terrain paint `detail_index.tga` / `detail_intensity.tga` | **per pixel** (`ck2ck3.map.terrain_paint` maps each pixel's CK2 category) | **no**, zero pixels |
| `gfx/map/terrain/colormap.dds` | per pixel, same grid | **no** |
| heightmap detail pass (`heightmap_detail.apply`, per-terrain HF amplitude) | **per province**, via `build._terrain_code_grid(ck3_raster, terrain_ck3, …)` | **yes** — 3,732,425 canvas px (6.61 %) change class |
| tree scatter mesh choice (`tree_scatter`, `mappings/tree_meshes.csv`) | **per province**, same grid | **yes** — same 6.61 % |

Two consequences worth naming:

* **Heightmap amplitude.** The moved pixels mostly go `plains` → `farmlands`
  (317 provinces; HF target 86.3 → 96.7 levels, +12 %), `plains` → `forest`
  (187; 86.3 → 110.7, +28 %), `plains` → `hills` (110; 86.3 → 213.3, ×2.5) and
  `hills` → `mountains` (63; 213.3 → 311.4, +46 %). Net: the detail pass gets
  *rougher* over the overridden counties, which is the direction
  `docs/step_map_heightmap.md` §7 says our interior land is short in.
* **Trees, measured**: **711,875 → 700,622 placed, −11,253 (−1.6 %)**, and
  `dropped_no_mesh` 17,963 → 29,216 by exactly the same 11,253.
  `mappings/tree_meshes.csv` gives `farmlands` **no mesh** ("cultivated land;
  no canopy") while `plains` has one, and 317 provinces move `plains` →
  `farmlands`, so their canopy goes. This is *correct* — the author said
  farmland — but it is a visible change and lane `trees-regional` should know.

**`docs/report_map_paint.md` figure 5 does not move.** It is read back out of
the shipped `detail_index.tga`, which is per-pixel paint, and this lane changes
zero paint pixels. What *has* changed is a claim in
`docs/step_map_paint.md` §2 step 1 — "paint and gameplay terrain never
disagree". They now disagree for 946 provinces, deliberately and exactly the
way CK2 itself disagrees (the bitmap is the texture, the history line is the
gameplay terrain). §1b of that file records it.

## 6. Open

* **`coastal` → `keep_bitmap` is the one reversible judgement call** (§2.1).
  141 counties. The coordinator should decide whether Faerûn's seafaring
  islands ought to be CK3 `farmlands`.
* **Paint now disagrees with gameplay terrain for 946 provinces.** A follow-up
  lane could repaint an overridden county's pixels to the override's material
  pair, which would make the ground match the tooltip. Not done here: the paint
  grid belongs to lane `map-paint`, and repainting would also move figure 5 and
  the colormap.
* **`glacier` and `arctic` both fold to `taiga`**, which is mild for polar
  ground (HF 70.1, the lowest of all keys; supply −0.2). CK3 has no arctic key.
  Changing it would move the paint too, so it is a `map-paint` decision.
* **`subterranean` is still not the Underdark.** 60 counties get `mountains`.
  A real Underdark needs a terrain type, and inventing one is the submod's job
  (`forgotten_kings`), not the converter's.
