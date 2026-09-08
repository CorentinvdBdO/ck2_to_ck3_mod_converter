# Map fidelity: how far our CK3 map is from a vanilla-looking one

**Question this answers.** Our map loads and plays, and it is ugly
(`docs/playtest_2026-09-08.md` item 13). *Why* is it ugly, in measurable terms,
and what would it cost to fix each cause? Research only — this lane writes no
converter code. Every number below is reproducible from a script in `scripts/`;
the raw tables are in `docs/evidence/map_fidelity/`.

**Answer in one paragraph.** Three separate gaps, in decreasing order of how
much they show. (1) **We ship no terrain paint at all**, so CK3 renders Faerûn
with vanilla *Europe's* material painting stretched over it — that is the single
biggest visual defect and it is a missing file, not a hard problem. (2) Our
heightmap is not flat, it is **terraced**: an 8-bit source through a linear
transfer curve leaves 160 usable land levels 277 apart, which reads as contour
steps and puts *more* high-frequency energy on the map than vanilla has, none of
it terrain. (3) We ship no **map objects**, so every settlement model, army
stack and title icon sits at the vanilla locator for the same province id, far
from our land. All three are converter-writable; none needs the in-game map
editor.

Reproduce:

```
uv run python scripts/map_fidelity_inventory.py
uv run python scripts/map_fidelity_paint.py
uv run python scripts/map_fidelity_locators.py
nohup uv run python scripts/map_fidelity_heightmap.py \
      > docs/evidence/map_fidelity/heightmap_run.log 2>&1 &
nohup uv run python scripts/verify_detail_index.py \
      > docs/evidence/map_fidelity/detail_index.log 2>&1 &
uv run python scripts/barony_seeds_from_ck2_positions.py
uv run python scripts/prototype_heightmap_detail.py
uv run python scripts/prototype_terrain_masks.py
uv run --with matplotlib python scripts/map_fidelity_plots.py   # plots only
```

`matplotlib` is deliberately **not** a repo dependency; the one plotting script
pulls it with `uv run --with` so `pyproject.toml` stays as it is.

---

## 1. How different are CK2 and CK3 map data

### 1.1 The raster inventory

`verified`, `scripts/map_fidelity_inventory.py` →
`docs/evidence/map_fidelity/inventory.csv`.

| layer | CK2 vanilla | CK2 Faerûn | CK3 1.19 vanilla | ours |
|---|---|---|---|---|
| provinces | `provinces.bmp` 3072×2048 RGB | 4096×3328 RGB | `provinces.png` 9216×4608 RGB | 8320×6784 |
| elevation | `topology.bmp` 3072×2048 **8-bit L** | 4096×3328 8-bit L | `heightmap.png` 18432×9216 **16-bit** (2×) | 8320×6784 16-bit (1×) |
| packed elevation | — | — | `packed_heightmap.png` 3185×4061 16-bit + `indirection_heightmap.png` 288×144 RGBA | written by the converter |
| normals | `world_normal_height.bmp` RGB | 3686×2995 RGB | none — derived in-engine | n/a |
| painted terrain | `terrain.bmp` 8-bit palette | same | 115 materials → `detail_index.tga` + `detail_intensity.tga`, both 9216×4608 RGBA | **none** |
| trees | `trees.bmp` 382×293 palette (1/8) | 512×416 (1/8) | 549,126 placed instances in 18 `map_object_data/generated/*.txt` | **none** |
| rivers | `rivers.bmp` 8-bit palette | same | `rivers.png` 8-bit palette, **same palette** | written |
| colour layer | `map/terrain/colormap.dds` 25 MB | same | `gfx/map/terrain/colormap.dds` 9216×4608 DXT5, 56 MB | **none** |
| static objects | `map/statics/00_static.txt`, 1 object (a map frame) | 3 files, **0 objects** | 82,572 id-keyed locators in 8 files | **none** |
| positions | `positions.txt`, 7 slots per province | same, 2660 blocks | `positions.txt` present but disabled in `default.map` | 152-byte stub |

Two things follow immediately. CK2 Faerûn's `map/statics` is **empty**
(`verified`: all three files hold only comments), so there is nothing to port
there — the "CK2 statics are not portable" note in `docs/design_map.md` is moot
for this mod. And `world_normal_height.bmp` has no CK3 counterpart: CK3 derives
normals from the heightmap with `normal_height_scale = 0.8` and
`normal_step_size = 1.6` (`gfx/map/terrain/settings.terrain`), which is one more
reason the heightmap's detail matters.

### 1.2 Elevation: bit depth, distribution, gradient, spectrum

`verified`, `scripts/map_fidelity_heightmap.py` →
`docs/evidence/map_fidelity/heightmap_stats.csv`. All values are in CK3 16-bit
levels; the CK2 maps are pushed through the converter's own transfer curve
(`0 → 0`, `95 → 4883`, `255 → 49205`) first, so the comparison is against what
we would actually write.

| | ck3 vanilla | **ours** | ck2 faerûn | ck2 vanilla |
|---|---|---|---|---|
| km per heightmap pixel | 0.742 | 1.484 | 2.90 | ~4.45 `assumed` |
| **distinct height values** | **31,516** | **212** | 208 | 255 |
| land fraction | 0.559 | 0.469 | 0.509 | 0.715 |
| land p50 / p95 | 9,008 / 26,140 | 9,038 / 23,166 | 9,038 / 23,166 | 8,761 / 35,908 |
| mean \|∇h\| (levels/km) | 140.8 | 131.9 | 120.5 | 47.3 |
| p95 \|∇h\| (levels/km) | 456.0 | 417.4 | 393.8 | 189.3 |
| high-pass RMS (< 6 km) | 282.5 | 319.1 | 326.7 | 116.3 |

**The headline is `distinct_values`: 212 against vanilla's 31,516.** Above the
water level the transfer curve steps by `(49205 − 4883) / 160 = 277` levels per
8-bit source step, so every slope on our map is a staircase of 277-level risers.
Our land percentiles are *identical* to the CK2 source's to four figures, which
confirms the curve and the LANCZOS resize are faithful — the information was
never there to begin with.

**"Flat" is the wrong diagnosis.** Our high-pass RMS is *higher* than vanilla's
(319 vs 283) and our mean gradient is within 7 % of it. The extra energy is the
terrace edges, not terrain: see `docs/evidence/map_fidelity/sword_coast/zoom_before.png`,
where the hillshade is covered in contour "worms".

**The radial power spectrum** (`spectrum.png`, `spectrum.csv`, 512×512 land
patches, n = 6, amplitude vs cycles/km) says the same thing precisely:

* vanilla CK3 land elevation is a **clean power law, amplitude ∝ f^−2.0** over
  0.005–0.6 cycles/km — slope −2.03 fitted on 0.02–0.6, −1.98 on 0.05–0.6,
  −2.08 on 0.005–0.05. Two decades, one exponent. `verified`
* our map tracks vanilla down to about 20 km wavelength (0.05 cycles/km) and
  then **flattens into a quantisation floor** instead of continuing the law;
* our Nyquist is 0.337 cycles/km against vanilla's 0.674, because we ship a 1×
  heightmap. Even with perfect detail we can only carry half of vanilla's
  spatial bandwidth at the current `resolution_factor = 1`.

`hf_by_terrain.csv` / `hf_by_terrain.png` give vanilla's detail amplitude per
CK3 terrain type (RMS of the residual below ~3 km, 300 windows each, land only,
labels from `common/province_terrain`):

| terrain | HF RMS (levels) | | terrain | HF RMS |
|---|---|---|---|---|
| mountains | 311 | | forest | 111 |
| desert_mountains | 323 | | floodplains | 106 |
| terraced_hills | 253 | | drylands | 97 |
| hills | 213 | | steppe | 97 |
| oasis | 122 | | farmlands | 97 |
| jungle | 121 | | desert | 91 |
| plains | 86 | | taiga | 70 |
| wetlands | 70 | | | |

A factor of 4.6 between taiga and desert_mountains — this is the table any
procedural detail pass has to obey, and it is why one global noise amplitude
would be wrong.

### 1.3 Painted terrain

CK2: `terrain.bmp` is an **8-bit palette-indexed** bitmap; the *index* is the
data. `terrain.txt` maps index → CK2 category (`text_<n> = { type = … }`) and
`default.map`'s `tree = { 3 4 7 10 }` promotes tree pixels to forest. Faerûn
declares 21 texture indices over 17 categories — three of them invented
(`glacier`, `subterranean`, `coastal`) — and actually paints **17** indices
resolving to 11 categories; index 19 (49.1 % of the bitmap) is the ocean.
Vanilla CK2 paints 14 indices over 9 categories. Per-index pixel counts:
`docs/evidence/map_fidelity/terrain_classes.csv`. The converter already maps
these to the 17 CK3 keys of `common/terrain_types/00_terrains.txt` and writes
`common/province_terrain` — that is the **gameplay** half and it is done.

CK3's **rendering** half is a different mechanism entirely, and this is the
part we do not ship:

* `gfx/map/terrain/materials.settings` declares **115 materials**, each with a
  diffuse/normal/properties `.dds`, an optional `tile_factor`, and a mask path;
  65 point into `masks/`, 50 into `masks_gen/` (120 mask PNGs exist, all
  9216×4608 8-bit L, 205 MB together).
* the runtime does **not** paint from those masks. It reads
  `gfx/map/terrain/detail_index.tga` and `detail_intensity.tga`, both
  9216×4608 **RGBA8, uncompressed, 170 MB each**: four material ordinals per
  pixel and their weights. `detail_data.settings` caps it at
  `"materials_limit": 4`.
* `verified`, `scripts/verify_detail_index.py`: the index channels are
  ordinals into `materials.settings` **declaration order** (where
  `snow_mask.png` is saturated the index is `mountain_02_snow` = 46, and
  `beach_02` = 6 is the commonest channel-0 value), and the four intensity
  channels sum to **exactly 255** at every one of 165,888 sampled pixels (a 16x16 grid over the whole image).
* also `verified`, and the useful part: **the shipped masks are stale relative
  to the shipped bake.** Of 1,160 sampled channels with non-zero intensity,
  **49.1 %** name a material whose own mask is 0 at that pixel. A runtime that
  painted from the masks could not produce vanilla's own terrain. So the pair
  is the runtime format, the masks are map-editor input, and a converter that
  writes the pair directly never needs the editor — the same conclusion the
  `packed_heightmap` work reached for elevation.

**What we ship today: nothing.** The generated mod has no `gfx/map` at all
(`descriptor.mod` lists 13 `replace_path`s, none under `gfx`), so CK3 samples
vanilla's 9216×4608 Europe paint in UV space across our 8320×6784 canvas.
Faerûn is currently wearing Europe's terrain textures. That, not the heightmap,
is what "ugly map" mostly means.

### 1.4 Trees

CK2 `trees.bmp` is a palette bitmap at **exactly 1/8** of the province bitmap on
each axis (Faerûn 512×416 for 4096×3328; vanilla 382×293 for 3072×2048 —
8.042, i.e. the same rule with rounding). 90.8 % of Faerûn's tree pixels are
index 0 (no trees). The nine used indices fall into three colour triples —
(30,139,109)/(18,100,78)/(8,58,44), (76,156,51)/(47,120,24)/(20,85,0),
(154,156,51)/(118,120,24)/(83,85,0) — i.e. **three species at three densities**
(`assumed`, from the palette structure; CK2 resolves them against the single
`gfx/models/Tree_Diffuse.dds` atlas). Counts:
`docs/evidence/map_fidelity/trees.csv`.

CK3 has no tree bitmap. Trees are **placed instances**: 18 files under
`gfx/map/map_object_data/generated/` holding **549,126** transforms in
`count=` + a flat `transform="…"` matrix list, on the `tree_high_layer` /
`tree_medium_layer` / `tree_low_layer` layers declared in
`map_object_data/layers.txt`. So a CK2→CK3 tree port is a *scatter* problem:
CK2 gives a 1/8-resolution density/species field, CK3 wants ~half a million
positioned meshes. That is arithmetic, not artistry.

### 1.5 Rivers — the one layer that transfers almost unchanged

`verified`, `docs/evidence/map_fidelity/rivers_palette.csv`. CK2 and CK3 use the
**same palette convention**:

| index | RGB | meaning |
|---|---|---|
| 0 | 0,255,0 | river **source** |
| 1 | 255,0,0 | **merge** into an existing river |
| 2 | 255,252,0 | **split** |
| 3…11 | 0,225,255 → 0,0,100 | river **width**, widest (3) to narrowest (11) |
| 254 | 255,0,128 | sea / open water |
| 255 | 255,255,255 | land, no river |

Vanilla CK2 uses indices 0–12, 14, 15, 254, 255; CK3 vanilla uses 0–11, 13, 15,
254, 255. **Faerûn uses only 0, 1, 2, 3, 4, 6, 11 and 255 — it has no 254 at
all**, so a conversion has to paint index 254 over every sea pixel itself or
CK3 will read the ocean as land for river purposes. Faerûn's rivers cover
0.48 % of its bitmap against vanilla CK3's 0.67 %.

### 1.6 Assets and their placement

CK3 `gfx/map/map_object_data/` (`scripts/map_fidelity_locators.py` →
`ck3_map_objects.csv`): 46 files, **82,572** id-keyed locator instances in 8
`game_object_locator` blocks, plus 552,235 generated-content instances.

| locator name | file | instances | layer | clamp to water |
|---|---|---|---|---|
| `buildings` | `building_locators.txt` | 11,297 | building_layer | yes |
| `special_building` | `special_building_locators.txt` | 11,297 | building_layer | yes |
| `siege` | `siege_locators.txt` | 11,297 | unit_layer | no |
| `activities` | `activities.txt` | 11,297 | activities_layer | no |
| `combat` | `combat_locators.txt` | 12,065 | unit_layer | yes |
| `unit_stack_player_owned` | `player_stack_locators.txt` | 12,065 | unit_layer | yes |
| `unit_stack_other_owner` | `other_stack_locators.txt` | 8,906 | unit_layer | yes |
| `unit_stack` | `stack_locators.txt` | 4,348 | unit_layer | yes |

11,297 is the land-province count (`definition.csv` has 14,152 rows, 13,270 of
them active — 882 are commented-out reserves).

**Coordinate frame, `verified` against province centroids over 400 provinces**
(`locator_frame.csv`): `position = { x  height  z }` where `x` is the
`provinces.png` **column** and `z` is measured from the **bottom** of the image.
Median |Δx| from the province centroid is 4.3 px, median |Δz| read
bottom-origin 4.6 px, and read top-origin 2,983 px. Same convention as CK2's
`positions.txt` y. `height` is 0.000000 in all but 78 of the 82,572 instances
(`clamp_to_water_level = yes` does the work) and `scale` is 1 in all but 125.
**Rotation is a quaternion `{ x y z w }` with x = z = 0 in every single one of
the 82,572 instances** — a pure yaw. CK2's one radian per slot therefore
converts exactly: `q = { 0, sin(θ/2), 0, cos(θ/2) }`.

CK2's side is `positions.txt`: 7 (x, y) slots + 7 rotations + 7 heights per
province, y bottom-origin. Measured signature (`ck2_slots.csv`):

| slot | Faerûn: = slot 0 | on water | rotation ≠ 0 | median offset from slot 0 (CK3 px) | what it is |
|---|---|---|---|---|---|
| 0 | 100 % | 9.2 % | 0 % | 0.0 | **capital / city** — the CK2 binary logs `Province %d has illegal capital location` |
| 1 | 0.2 % | 12.0 % | 0 % | 22.8 | unnamed; always distinct, 98.6 % inside its own province in CK2 vanilla |
| 2 | 46.1 % | 12.3 % | 9.6 % | 10.5 | unnamed |
| 3 | 58.1 % | 13.1 % | 0 % | 0.0 | unnamed; `height = 20.000` in **every** block of both maps |
| 4 | 0.0 % | **36.1 %** | 19.1 % | 25.5 | **port** — the binary logs `Invalid port location for province %d, center at …, port location at …` |
| 5 | 21.2 % | 13.8 % | 0.1 % | 28.2 | unnamed; rotation ≠ 0 in 98.8 % of CK2 *vanilla* blocks — an oriented model |
| 6 | 24.7 % | 16.8 % | 1.4 % | 40.1 | unnamed; rotation ≠ 0 in 99.0 % of CK2 vanilla blocks |

Only slots 0 and 4 have names CK2 itself gives them; the community list
("city, unit, port, council, wonder") is `assumed` and this lane found no
evidence in the binary for the other five, so they are described by signature
instead. Faerûn's authors clearly edited slots 0, 1 and 4 and left the rest
near-default, which is why 46–58 % of slots 2 and 3 still equal slot 0 there
while CK2 vanilla's equivalents are 8.5 % and 14 %.

---

## 2. Barony barycentres from the CK2 slots

`scripts/barony_seeds_from_ck2_positions.py` →
`overrides/barony_seeds_ck2positions.csv` (review only, **not wired in**),
`county_slot_spread.csv`, `seed_shift.csv`.

Today the converter uses slot 0 for the county capital barony only (2,110 of
3,694 placed baronies) and farthest-point samples the other 1,584
(`docs/step_map_baronies.md`). The question is whether the other six slots are
worth using.

| measurement (Faerûn, 2,121 counties with slots) | value | label |
|---|---|---|
| median county radius | 45.8 px ≈ **68 km** | `verified` |
| median distinct slot positions per county | 5.0 of 7 | `verified` |
| median distinct slots **inside** the county | 4.0 | `verified` |
| counties with ≥ 2 in-county slots | 2,086 (**98.3 %**) | `verified` |
| counties with ≥ 1 in-county slot per built barony | 2,062 (**97.2 %**) | `verified` |
| in-county slot spread ÷ county radius | median **0.94**, p90 1.49 | `verified` |
| seeds the prototype can place | 3,619 of 3,694 | `verified` |
| median move vs today's barony centre | 15.6 px ≈ **23 km** | `verified` |
| proposed seeds still inside today's barony cell | 2,592 (**71.6 %**) | `verified` |

**Yes, it would change the result materially.** The slots are not clustered:
they span about one county radius, there are enough of them for essentially
every county, and 28.4 % of the proposed seeds land in a *different* barony than
the one they are assigned to today — those borders would move by more than a
barony's width.

**Whether that is an improvement is a separate question, and the honest answer
is: only for two of the seven slots.** Slot 0 is the settlement and slot 4 is
the harbour; both encode something real about where people live. The other five
are rendering anchors for province furniture whose semantics CK2 never
documents, so using them as barony seeds buys *geometric spread with a semantic
veneer* — arguably worse than farthest-point sampling, which at least does not
pretend. The defensible subset is:

* **slot 4 → the coastal `city_holding`** of a county that has one. 36.1 % of
  slot 4s sit on water, i.e. CK2's author placed them on the harbour, so
  snapping them landward gives a genuinely better city position than a sampled
  point. This is the recommendation.
* **slot 0 → capital**, which is already what happens.
* slots 1, 2, 3, 5, 6: use as *spread hints* only if a human reviews the duchy
  sheet, i.e. as pre-filled rows in `overrides/barony_seeds.csv`, never as an
  automatic source.

The prototype CSV is written in exactly `overrides/barony_seeds.csv` format so a
reviewer can copy the rows they like across.

---

## 3. Placing CK3 assets from CK2's

### 3.1 The mapping

| CK2 | CK3 locator | feasible? |
|---|---|---|
| slot 0 (capital/city) | `buildings` (`building_locators.txt`) | **yes** — direct, this is the settlement model |
| slot 0 | `special_building` | yes, same point; vanilla puts them a few px apart |
| slot 4 (port) | no CK3 port locator exists | n/a — CK3 draws harbours from the coastline, not a locator |
| slot 1 | `unit_stack` / `unit_stack_player_owned` / `unit_stack_other_owner` | plausible (slot 1 is the most "inside the province" slot at 98.6 %), `assumed` |
| slot 3 (`height = 20`) | `combat` or `siege` | `assumed`; nothing in the data settles it |
| slots 2, 5, 6 | — | no evidence; use centroids |
| `map/statics` objects | `map_object_data/*.txt` free objects | **nothing to port**: Faerûn ships zero static objects |
| `trees.bmp` | `map_object_data/generated/tree_*_generator_*.txt` | yes, but it is a scatter, see §4.3 |

### 3.2 What is missing, precisely

1. **Per-barony vs per-county.** CK3 needs one locator instance *per province*,
   i.e. per barony: 3,694 of them. CK2 gives 7 slots per *county*: 2,121 sets.
   1,573 baronies have no CK2 anchor of their own; §2's prototype covers 3,619
   of 3,694 by spending the spare slots, and the rest must be centroids.
2. **Rotation** is not missing — CK2's single radian maps exactly onto CK3's
   yaw-only quaternion (§1.6). CK2 Faerûn leaves it at 0.000 in 80–100 % of
   slots anyway, so most CK3 rotations will be 0 whatever we do.
3. **Height** is not missing either: 99.9 % of vanilla instances are
   `position.y = 0` with `clamp_to_water_level = yes`.
4. **Sea provinces.** `combat` and `unit_stack_player_owned` have 12,065
   instances against 11,297 land — they cover water too, so a generator that
   only walks land provinces will leave naval combat unanchored.
5. **The 8th file.** All eight locator sets must exist or the corresponding
   object silently draws at the vanilla province's place — which is exactly
   playtest item 7 ("title icons displaced far to the SW").

---

## 4. Painting a vanilla-style map from CK2 data

### 4.1 Terrain paint — the pipeline

The output is **not** a set of masks; it is the `detail_index.tga` /
`detail_intensity.tga` pair (§1.3). Proposed passes:

1. **Class map.** CK2 `terrain.bmp` index → CK2 category (`terrain.txt`) → CK3
   terrain key, reusing `ck2ck3.map.terrain.CK2_TO_CK3_TERRAIN`, with the
   `trees.bmp` promotion to `forest`. This already exists for
   `common/province_terrain`; the only new part is doing it per **pixel**
   instead of per province.
2. **Material choice.** CK3 terrain key → a primary and a secondary vanilla
   material id. `scripts/prototype_terrain_masks.py` carries a first table
   (`plains → plains_01 / plains_01_noisy`, `mountains → mountain_02 /
   mountain_02_c`, `taiga → forest_pine_01 / snow`, …). Using **existing
   vanilla materials means no new `.dds` has to be authored** and the colour and
   tiling match vanilla by construction, which is most of "colour/texture
   consistency".
3. **Edge treatment.** CK2's palette edges are hard; vanilla's are dithered.
   The prototype blends primary/secondary with a Gaussian-filtered noise field
   (σ = 1.5 px) so class boundaries break up. Erosion-style edges (dilate the
   higher-priority class into the lower along the height gradient) are a
   refinement, not a requirement.
4. **Write the pair.** Channel 0 = primary ordinal, channel 1 = secondary,
   channels 2–3 = 0; intensities must sum to exactly 255 (asserted in the
   prototype).

**Measured cost** (`terrain_paint_sizing.csv`, 2048×2048 Sword Coast tile,
extrapolated to 8320×6784):

| | raw TGA | TGA RLE | PNG (if it were allowed) |
|---|---|---|---|
| `detail_index` from CK2 classes | 226 MB | **8 MB** | 2 MB |
| `detail_intensity`, 256 blend levels | 226 MB | 206 MB | 60 MB |
| `detail_intensity`, 16 levels | 226 MB | **173 MB** | 25 MB |
| `detail_intensity`, 4 levels | 226 MB | **81 MB** | 15 MB |
| vanilla's own pair, same extrapolation | 452 MB | 317 MB | 201 MB |

The index map is nearly free; **the blend weights are the whole cost**, and
quantising them (which is visually invisible at 4–16 steps) is the lever. The
generated mod is 143 MB today, so this is a real decision, not a rounding error.
Two things need a game test before committing: whether CK3 accepts **RLE** TGA
(the loader string only promises `png, bmp, tga` for *masks*), and whether the
pair may be **smaller than `provinces.png`** — vanilla's is exactly province
size but the shader samples it in UV space, so half resolution would quarter the
bill.

### 4.2 Heightmap detail — prototyped on the Sword Coast

`scripts/prototype_heightmap_detail.py`, region Waterdeep (2344, 1098) to
Baldur's Gate (2576, 1676) in canvas pixels, crop 832×896 at (2080, 940).
Four passes, in order:

1. **De-terrace** — Gaussian σ = 1.6 px on land only. Legitimate because the
   real signal is band-limited to the CK2 Nyquist (2.90 km) anyway, so nothing
   true is lost; only the 277-level risers go.
2. **Spectral fill** — fit vanilla's `amplitude ∝ f^−2.0` law to the crop's own
   well-resolved band (0.004–0.03 cycles/km), take the per-frequency shortfall
   against that law, and inject noise shaped to exactly that deficit,
   leaving frequencies below 0.01 cycles/km untouched. Then modulate the
   amplitude per CK3 terrain class so each class hits its `hf_by_terrain.csv`
   figure, with the gain field itself blurred (σ = 6 px) so class borders leave
   no seam.
3. **River valleys** — Gaussian cross-section carved along `rivers.png`
   indices 3–11, depth 900 levels at the centre, width from the CK2 width index.
4. **Coast smoothing** — blend the first 4 px of land toward the water level.

| | before | after | vanilla |
|---|---|---|---|
| distinct height values in the crop | **125** | **17,675** | 31,516 |
| high-pass RMS on land (levels) | 200.9 | 149.7 | ~146 (this crop's terrain mix) |
| mean gradient (levels/km) | 144.3 | 126.5 | 140.8 |
| land p50 / p95 | 8,484 / 15,686 | 8,519 / 15,652 | unchanged by design |

Evidence images (all ≤ 200 KiB, 128-colour hillshades):
`sword_coast/before.png`, `after.png`, `zoom_before.png`, `zoom_after.png`,
`zoom_vanilla_1x.png` (a vanilla Biscay crop halved to our 1.4839 km/px, for a
like-for-like look), and `spectrum_prototype.png`, on which the "after" curve
follows vanilla's dashed line from 0.04 cycles/km to our Nyquist while "before"
sits above it on quantisation noise.

**What the prototype does not fix, and a human should see before we commit.**
Vanilla's detail is *structured* — dendritic valleys, ridge lines, drainage.
Ours is isotropic noise with the right amplitude and the right spectrum. Side by
side (`zoom_after.png` vs `zoom_vanilla_1x.png`) it reads as gravel where
vanilla reads as landscape. Closing that needs ridged-multifractal noise or a
hydraulic-erosion pass, which is a different order of work.

**CK3 constraints that bound all of this** (all already in `CLAUDE.md`, restated
because the prototype has to respect them): the heightmap is 16-bit; the water
level is `WATERLEVEL / WORLD_EXTENTS_Y × 65535` = **4883** for our 3.8/51, and
land must stay strictly above it; vanilla's own maximum is 49,205, which the
config uses as the ceiling; and the game reads `heightmap.heightmap` → the
packed pair, so any detail pass must run *before* `ck2ck3.map.packed_heightmap`
and the pair must be re-packed (the packer is ours, no editor needed). Adding
detail also costs packing efficiency: the packed heightmap dedupes identical
tiles, and 212 distinct values dedupe far better than 17,675 — expect
`packed_heightmap.png` to grow.

### 4.3 Trees and colour

* **Trees.** Scatter instances into `gfx/map/map_object_data/generated/`:
  sample the CK2 `trees.bmp` density (indices 3, 4, 7, 10 are the "is forest"
  set per `default.map:52`; the three colour triples give species) with a
  blue-noise or jittered-grid distribution, at vanilla's own density —
  549,126 instances over 9216×4608, i.e. 1.29e-5 trees per province pixel,
  so ~728 k for our 56.4 Mpx canvas at the same visual density. The file format is
  `object={ name=… count=N transform="x y z qx qy qz sx sy sz …" }` with the
  same bottom-origin frame as the locators.
* **Colour.** `gfx/map/terrain/colormap.dds` (9216×4608 DXT5, 56 MB) is the
  large-scale colour wash. CK2 has the exact analogue at
  `map/terrain/colormap.dds` (25 MB) — so this one is a straight resample of an
  existing CK2 asset, which is the cheapest way to make the map stop looking
  like Europe. `flat_maps/flatmap.dds` (21 MB) is the zoomed-out paper map that
  playtest item 5 complains about; it is one texture, not a pipeline.

### 4.4 Effort

| item | effort | needs a human? |
|---|---|---|
| `detail_index` / `detail_intensity` writer + CK2 class → material table | **M** | the material table wants one art review pass |
| blend-weight quantisation + size decision (RLE? half res?) | **S** | **yes — a game test and a repo-size call** |
| resample CK2 `colormap.dds` → CK3 `colormap.dds` | **S** | no |
| neutral `flatmap.dds` (playtest item 5) | **S** | yes, it is an art asset |
| heightmap de-terrace + spectral fill + per-terrain gain | **M** | no |
| river-valley carving and coast smoothing | **S** | no |
| ridged / eroded structure instead of isotropic noise | **L** | yes, it is a look call |
| tree scatter into `map_object_data/generated/` | **M** | no |
| the 8 locator sets from barony centroids (+ slot 0 / slot 4) | **M** | no — but coordinate with lane `map-ui`, §5 |
| `resolution_factor = 2` to reach vanilla's spatial bandwidth | **S** to switch, **L** in bytes | **yes — a size call** |

---

## 5. Hand-off

`docs/evidence/HANDOFF_map_fidelity.md` — what lane `map-ui` should take from
here (the locator coordinate frame, the quaternion rule, the eight files), what
a future `map-paint` lane inherits, and the three decisions that need a human.
