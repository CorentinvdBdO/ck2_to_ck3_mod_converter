# Map UI on a non-vanilla canvas — locators, camera, table, flat map

Lane `map-ui`, 2026-09-08.  Answers the four playtest complaints against the
generated Faerûn mod (canvas **8320 × 6784**, vanilla **9216 × 4608**):

| # | playtest report (`verified` by the user) | root cause | fix |
|---|---|---|---|
| a | title icons / county names / CoAs drawn far SW of their land | vanilla's `gfx/map/map_object_data/*_locators.txt` are inherited, and their ids mean *European* provinces | §1 — write our own |
| b | map too tall for the 3D tabletop; assets collide; zoom lags | `map_table_*.txt` places one fixed-size table entity at vanilla's map centre | §3 |
| c | northern quarter unreachable by the camera | `NCamera.PANNING_HEIGHT = 4696` < our 6784 | §2 |
| d | zoomed out, the flat map is vanilla's real-world paper map | we ship no `gfx/map/terrain/flat_maps/flatmap.dds` | §4 |

Paths below: `V` = `~/.local/share/Steam/steamapps/common/Crusader Kings III/game`,
`EK2` = `…/workshop/content/1158310/2887120253` (Elder Kings 2, 8256 × 5504),
`GH` = `…/workshop/content/1158310/2326030123` (Godherja, 8192 × 4096).

---

## 1. What places holdings, unit stacks, sieges, activities — and the CoAs

### 1.1 `positions.txt` is dead, `map_object_data` is what matters

`verified`: `strings ck3.exe | grep -c positions.txt` → **0**.  CK3 1.19's
binary does not contain the string at all.  `V map_data/default.map:4` comments
the key out, GH ships a 97-byte "FILE REMOVED" stub, EK2 ships no file.  Our
comment-only shadow (`writers.render_positions_stub`) is correct and inert.

The live mechanism is `gfx/map/map_object_data/*.txt`.  Both TCs ship the whole
per-province set:

| file | `name=` | `layer=` | V | EK2 | GH |
|---|---|---|---|---|---|
| `building_locators.txt` | `buildings` | `building_layer` | 1.8 MB | 835 KB | 1.2 MB |
| `special_building_locators.txt` | `special_building` | `building_layer` | 1.9 MB | 838 KB | 1.2 MB |
| `siege_locators.txt` | `siege` | `unit_layer` | 1.8 MB | 832 KB | 1.2 MB |
| `activities.txt` | `activities` | `activities_layer` | 1.8 MB | 835 KB | 1.2 MB |
| `player_stack_locators.txt` | `unit_stack_player_owned` | `unit_layer` | 1.9 MB | 929 KB | 1.3 MB |
| `combat_locators.txt` | `combat` | `unit_layer` | 1.9 MB | 928 KB | 1.3 MB |
| `other_stack_locators.txt` | `unit_stack_other_owner` | `unit_layer` | 1.4 MB | 1.4 MB (vanilla copy) | **empty stub** |
| `stack_locators.txt` | `unit_stack` | `unit_layer` | *not shipped* | 715 KB | empty stub |

`unit_stack` is legacy: vanilla 1.19 ships no `stack_locators.txt`, so there is
nothing to override and the converter does not write one.  GH proves an **empty
`instances={}` block is legal** (`GH gfx/map/map_object_data/other_stack_locators.txt`).

### 1.2 The format, measured not guessed — `scripts/check_locator_frame.py`

```
game_object_locator={
	name="buildings"          render_pass=Map
	clamp_to_water_level=yes  generated_content=no
	layer="building_layer"
	instances={
		{ id=1
		  position={ 271.799835 0.000000 4462.883301 }
		  rotation={ -0.000000 -0.960029 -0.000000 0.279900 }
		  scale={ 1.000000 1.000000 1.000000 } }
```

Cross-checking every vanilla instance against the pixel centroid of its
province colour in `V map_data/provinces.png` + `definition.csv`
(`docs/evidence/locator_frame.md`, 12 750 colours, 9216 × 4608):

| file | n | median \|Δx\| | median \|Δ\| if z is **bottom-up** | median \|Δ\| if z is top-down |
|---|---|---|---|---|
| building_locators | 11 297 | 3.4 | **3.9** | 1360.9 |
| special_building_locators | 11 297 | 4.5 | **3.5** | 1359.4 |
| player_stack_locators | 12 062 | 5.4 | **3.2** | 1383.8 |
| other_stack_locators | 8 904 | 5.8 | **3.1** | 1457.1 |
| siege_locators | 11 297 | 6.1 | **6.4** | 1358.2 |
| combat_locators | 12 062 | 7.1 | **6.2** | 1383.7 |
| activities | 11 297 | 6.5 | **4.6** | 1359.8 |

So, `verified`:

* `position` is `{ x y z }` in **`provinces.png` pixels**, 1 : 1 — not world
  units, not normalised.  This follows from `WORLD_EXTENTS_X = width − 1`.
* **`z` is bottom-up**: `z = image_height − y_top_down`.  Reading it top-down is
  wrong by ~1360 px.  Same convention as CK2 `positions.txt` (`docs/map_scale.md` §2b).
* `y` is height above the water plane and is `0.000000` for essentially every
  per-province instance (1 of 11 297 in `buildings`, 32 in `special_building`,
  40 in `combat` are non-zero hand-tweaks).
* `rotation` is a quaternion `{ qx qy qz qw }`, **yaw only** (`qx = qz = −0`).
  `activities` ships the identity `{ 0 0 0 1 }` for every instance.
* `scale` is `{ 1 1 1 }` throughout.
* the residual 3–7 px is vanilla's artists nudging icons off the centroid; it
  is not a frame error.

### 1.3 The engine generates missing locators — and that is exactly our bug

`ck3.exe` strings, `interface/gameobjectlocators.cpp`:

```
map object locator "{}" is incomplete. A new file with locator data has been generated ({}/{}).
Copy that file (or its contents) to game/gfx/map/map_object_data to fix the error logs.
Failed to get transform for locator type '{}' instance id {}
```

Our own playtest log has it (`…/pfx/…/Crusader Kings III/logs/debug.log`,
`[19:22:50][E][gameobjectlocators.cpp:126]`) for `buildings`,
`special_building`, `unit_stack_player_owned`, `combat`, `siege`, `activities`
— and 744 × `gameobjectlocators.cpp:263 Failed to get transform`.  The engine
wrote replacements to `…/Crusader Kings III/generated/`.

Analysing those generated files against **our** `provinces.png` proves the
mechanism (`verified`):

| | n | median distance to our province centroid |
|---|---|---|
| entries the engine **kept from vanilla** (id also exists in `V building_locators.txt`) | 3179 | **3040 px** |
| entries the engine **generated fresh** (id beyond vanilla's list) | 515 | **1.6 px** (max 2.2) |
| fresh entries in `combat_locators`, land | 202 | 4.5 px |
| fresh entries in `combat_locators`, sea | 6 | 4.6 px |

The engine only *fills gaps*.  3179 of our 3694 land provinces reuse a vanilla
id's European coordinate and land **3 040 px away** from their own territory.
That is complaint (a), quantified.  It also settles the placement rule: the
engine's own answer for a fresh id is **the province colour centroid**, sea
provinces included.

### 1.4 Which ids each file needs

The engine's generated files tell us the required id set exactly.  Against our
`map_data/default.map` classification (3694 land, 180 sea, 86 river, 95 lake,
210 impassable, 4265 total):

| locator | ids the engine demanded | rule |
|---|---|---|
| `buildings`, `special_building`, `siege`, `activities` | 3694 | **land only** (all ids minus sea/river/lake/impassable) |
| `unit_stack_player_owned`, `combat` | 4056 + a sentinel `id=0` | **everything passable** (land + sea + river + lake; impassable excluded) |

`verified`: `building_locators` id set == our land set exactly (0 extra, 0
missing); `combat_locators` extra set == sea ∪ river ∪ lake (361), absent set ==
impassable (210).  `other_stack_locators` was not reported incomplete only
because vanilla happens to cover our id range; it takes the passable set too.

The `id=0` sentinel is a constant, not derived: `V combat_locators` `{ 0 0 509 }`,
`V player_stack/other_stack` `{ 3 0 517 }`, `EK2 other_stack` `{ 3 0 5 }`,
`EK2 stack` `{ 0 0 0 }`.  Any in-canvas point works; the converter copies
vanilla's.

### 1.5 Why not the CK2 `positions.txt` city slot

`docs/map_scale.md` §2b established that CK2 slot 0 is the city and is
bottom-origin, and CLAUDE.md records that **CK2 `positions.txt` is per
province, and there are no barony coordinates**.  One CK2 county becomes many
CK3 baronies here, so a single CK2 city point cannot place 3694 holdings.  The
centroid is used for every locator, which is also what the CK3 engine itself
does.

---

## 2. Camera bounds — `NCamera`, and it is a defines-only fix

`V common/defines/graphic/00_graphics.txt:148` opens `NCamera`.  The bounding
keys:

| key | vanilla | line |
|---|---|---|
| `PANNING_WIDTH` | `9090  #6400` | `:193` |
| `PANNING_HEIGHT` | `4696  #4096` | `:194` |
| `START_LOOK_AT` | `{ 5000.0 0 2300.0 }` | `:171` |
| `START_ZOOM_STEP` | `33` | `:172` |
| `ZOOM_STEPS` | 35 heights, 70 … 6500 | `:159` |
| `MAPTABLE_FLOOR_LEVEL` / `_CEILING_LEVEL` | `-3100` / `3000` | `:178-179` |

There is **no `MAX_ZOOM` and no `MAP_BOUNDS`**; `PANNING_WIDTH`/`PANNING_HEIGHT`
are the camera bound, and they are in the same pixel frame as the locators
(x right, z bottom-up).  `PANNING_HEIGHT = 4696` against our 6784 leaves the
top **2088 px = 30.8 %** of the map unreachable — complaint (c), to the
"northern quarter" the user reported.

How the two TCs handle it (`verified`):

| | canvas | `PANNING_WIDTH` | `PANNING_HEIGHT` | file |
|---|---|---|---|---|
| EK2 (aspect 1.50) | 8256 × 5504 | **8256** | **5504** | `EK2 common/defines/graphic/ek_graphics.txt:12-14` |
| GH (aspect 2.00) | 8192 × 4096 | 6400 | **4096** | `GH common/defines/graphic/00_graphics.txt:193-194` |

EK2 sets both to the canvas exactly.  GH sets the height to the canvas and
keeps vanilla's commented-out `6400` width (their playable area is narrower
than the sheet).  **EK2 is the model**: `PANNING_WIDTH = width`,
`PANNING_HEIGHT = height`.  Neither TC touches `ZOOM_STEPS`, `FOV` or the
`MAPTABLE_*` levels, so a non-2:1 aspect needs no other camera change.

`START_LOOK_AT` is in the same frame and must move too, or the game opens
looking at a point that is off our land; vanilla `{ 5000 0 2300 }` is the map
centre-ish, GH uses `{ 3860 0 1730 }` (`GH …/00_graphics.txt:171`).  The
converter writes the canvas centre.

**Recommendation: option (i), defines only.**  Padding the canvas to the
vanilla 2 : 1 aspect (option ii) would need 8320 × 6784 → **13568 × 6784**, i.e.
+5248 px of empty ocean columns, 92.0 Mpx instead of 56.4 — a 63 % bigger
`provinces.png`, `heightmap.png`, `rivers.png` and packed heightmap for nothing.
Shrinking the scale (option iii) throws away the measurement in
`docs/map_scale.md`.  Two shipping TCs run at 1.50 and 2.00 with defines only.

---

## 3. The 3D map table

The table is **not** a define and not a mesh we have to author: it is four
`object={}` entries in `gfx/map/map_object_data/map_table_<style>.txt`, each
naming a prebuilt entity and one `transform` string.

`V gfx/map/map_object_data/map_table_western.txt`:

```
object={ name="western_tabletop"        entity="tabletop_west_basic_entity"
         render_pass=MapUnderTerrain    layer="map_table_layer_western"
         count=1
         transform="4500.000000 -15.000000 2560.000000 0.000000 0.000000 0.000000 0.000000 5.000000 5.000000 5.000000" }
```

`transform` is `x y z  qx qy qz qw  sx sy sz` — the same pixel frame again.
Styles are declared in `gfx/map/table_styles/table_styles.txt`
(`map_table_style_western` is `default = yes`; `_ce1`, `_ep3`, `_tgp` are DLC-
gated), each with its own `map_table_<style>.txt` and four entities: tabletop,
tablecloth, candles, props.

| | canvas | canvas centre | table `x z` | scale |
|---|---|---|---|---|
| V | 9216 × 4608 | 4608, 2304 | 4500, 2560 | 5 5 5 |
| EK2 | 8256 × 5504 | 4128, 2752 | 3100, 2400 | 5 5 5 |
| GH | 8192 × 4096 | 4096, 2048 | 3100, 2048 | 5 5 5 |

`verified`: **neither TC scales the table mesh**; both only move it, and
neither centres it exactly.  EK2 runs a 5504-tall map (19 % taller than
vanilla) on the unscaled table.  Ours is 6784 — **47 %** taller — which is
complaint (b): the sheet overhangs the table's north edge, so the rim geometry
intersects the map plane and the objects on it.

The converter therefore writes its own `map_table_<style>.txt` for all four
styles: centred on the canvas and uniformly scaled by
`5 × max(width / 9216, height / 4608)` = `5 × 1.472 = 7.36` for us.  Uniform,
because the entity carries candles and props that shear under a non-uniform
scale, and oversize in x is harmless — the table is `render_pass=MapUnderTerrain`,
i.e. always below the sheet.  The y offsets stay vanilla's (`-15` tabletop,
`-20` cloth, `-1` candles/props) so the stacking order is unchanged.

`assumed`, and the one thing here that a game launch has to confirm: that 7.36
is enough and not too much.  The mesh's own extent is inside a binary
`.mesh` (`V gfx/models/tabletop/`) and was not parsed.  The scale is a config
key (`[map.table] scale_headroom`) so the coordinator can retune it without a
code change.

---

## 4. The flat (paper) map

`NGraphics` (`V common/defines/graphic/00_graphics.txt:46-49`):
`FLAT_MAP_HEIGHT = 3.92`, `FLAT_MAP_FADE_SPEED = 2.5`, **`FLAT_MAP_ZOOM_STEP = 21`**
(EK2 sets `16`, `EK2 …/ek_graphics.txt:4`).

The texture is chosen by `gfx/map/flat_map_styles/flat_map_styles.txt`
(`paper_map_style_western` → `texture = "flatmap.dds"`, `default = yes`) and
lives in **`gfx/map/terrain/flat_maps/`**.  `V gfx/map/flat_map_styles/_flat_map_styles.info`
says it outright: *"Be sure to leave a default flatmap.dds file in the folder
anyway, it will be used when loading the game."*

`verified` DDS headers:

| | file | w × h | format | mips | bytes |
|---|---|---|---|---|---|
| V | `flatmap.dds` | 9216 × 4608 | DXT1 (BC1) | 0 | 21 233 792 |
| V | `flatmap_tgp.dds` | 9216 × 4608 | DXT1 | 0 | 21 233 792 |
| EK2 | `flatmap.dds` | 8256 × 5504 | DXT1 | 1 | 22 720 640 |
| GH | `flatmap.dds` | 8192 × 4096 | DXT1 | 1 | 16 777 344 |

So: **the flat map is exactly the canvas size, DXT1, no alpha, no mip chain
needed** (vanilla ships `mipMapCount = 0`).  All three TCs ship one; we ship
none, so the game falls back to vanilla's 9216 × 4608 Earth and stretches it
over Faerûn — complaint (d).  GH's was written by GIMP (`GIMP-DDS` in the
reserved field), so no Paradox tooling is involved.

The converter now writes one: `provinces.png` reduced to the canvas size,
land tinted parchment and water tinted a muted blue-grey, then BC1-encoded.
DXT1 is written by hand (`ck2ck3.map.dxt1`) — a 4 × 4 block is 8 bytes,
`color0`/`color1` in RGB565 plus 16 two-bit indices, which is a 60-line encoder
and avoids depending on Pillow's DDS *save* support (Pillow only gained it
recently and it is not in this project's pinned floor).

Related, not fixed here: `gfx/map/surround_map/` (`surround_mask.dds`,
`surround_fade.dds`, `surround_tile.dds`, `surround_cloud.dds`) is the terrain
*outside* the map edge in 3-D view.  Vanilla's mask is 4096 × 2048, EK2
re-authored theirs at 4128 × 2752 (= canvas ÷ 2), GH kept vanilla's.  Since GH
ships a 2 : 1 map on vanilla's mask and EK2 a 1.5 : 1 map on its own, the mask
is clearly not load-bearing for boot; it is a cosmetic follow-up.

---

## 5. Vanilla's foliage, found while chasing (b)

`gfx/map/map_object_data/generated/` holds 18 files and **51.7 MB** of tree,
reed and rock instances, each an absolute `transform` inside vanilla's own
9216x4608 sheet.  Nothing in the loader ties them to the map they were authored
for: a mod that does not override a file **by name** gets vanilla's forest
loaded over its own map — trees standing in our ocean, props leaning against
the table.  This is the other half of complaint (b), and a plausible cause of
"zoom lags there": the sheet is 22 % bigger than vanilla's and every one of
those instances is still being placed and culled.

Both TCs handle it the same way, and it is the pattern the converter copies:
an **empty `instances={ }` block** with the original
`name`/`layer`/`pdxmesh` header — `EK2` and `GH`
`gfx/map/map_object_data/generated/tree_leaf_low_generator_1.txt` are byte-alike
203-byte stubs.  Neither TC covers *every* vanilla generator (both miss
`tree_sakura_*`, among others), so both still leak some; the converter stubs
all 18.

The cost is that the 3-D map has no foliage at all until Faerûn grows its own.
That is a strict improvement over foliage in the wrong ocean, and it is one
config line: `[map] strip_vanilla_foliage = false`.

---

## Open questions for the coordinator

1. Table scale 7.36 is arithmetic, not measured — the `.mesh` extent is
   unparsed.  Needs one game launch to confirm the sheet no longer overhangs.
2. `PANNING_WIDTH`: EK2 uses the full canvas, GH deliberately narrows it.  We
   use the full canvas; if the padding ocean (25 % of the sheet,
   `docs/map_scale.md` §7) is annoying to pan across, narrowing is one define.
3. `FLAT_MAP_ZOOM_STEP`: left at vanilla's 21.  EK2 lowered it to 16, which
   makes the paper map appear sooner and is cheaper to render on a big sheet —
   possibly relevant to the "zoom lags" half of complaint (b).
4. `surround_map/*.dds` is still vanilla's Earth coastline mask.
5. `[map] strip_vanilla_foliage = true` removes **all** 3-D foliage until
   Faerûn generates its own.  Empty is right, but it is a visible change and a
   one-line revert.
6. `docs/playtest_2026-09-08.md` does not exist in the repo; the playtest facts
   used here came from the lane brief.  If that file exists elsewhere it should
   be committed.
