# CK3 1.19 `map_data/` format reference — hard evidence

Purpose: enough verified detail to write a correct CK3 physical map from a converter on the first try.
Every claim carries `path:line` evidence with the line quoted, or is labelled `verified` (measured/read) / `assumed` (not testable here).

Sources (all read-only):

| tag | root |
|---|---|
| `V` | `/home/cvdbdo/.local/share/Steam/steamapps/common/Crusader Kings III/game` (CK3 1.19.0.6) |
| `EK2` | `/home/cvdbdo/.local/share/Steam/steamapps/workshop/content/1158310/2887120253` (Elder Kings 2 0.19.1) |
| `GH` | `/home/cvdbdo/.local/share/Steam/steamapps/workshop/content/1158310/2326030123` (Godherja 0.4.0.5) |

**No `map_data/*.info` file ships with CK3 1.19.** `verified` — `find <game> -name '*.info'` returns 166 files, none under `map_data/`, none named for heightmap/rivers/provinces/adjacencies. The only map-adjacent `.info` files are `common/terrain_types/_terrains.info`, `gfx/map/environment/environment.info`, `gfx/map/province_effects/_province_effects.info`, `gfx/map/flat_map_styles/_flat_map_styles.info`. So the rivers palette and heightmap container semantics below come from the *files themselves* plus the defines, not from Paradox prose.

---

## 1. Dimensions

Read straight out of each PNG's IHDR chunk (bytes 16..28), so no decoder heuristics involved.

| file | V | EK2 | GH |
|---|---|---|---|
| `provinces.png` | **9216×4608**, bitdepth 8, colourtype 2 (RGB) | **8256×5504**, 8, RGB | **8192×4096**, 8, RGB |
| `rivers.png` | **9216×4608**, bitdepth 8, colourtype 3 (palette) | **8256×5504**, 8, palette | **8192×4096**, 8, palette |
| `heightmap.png` | **18432×9216**, bitdepth 16, colourtype 0 (grayscale) | **8256×5504**, 16, gray | **8192×4096**, 16, gray |
| `packed_heightmap.png` | 3185×4061, 16, gray | 1881×3539, 16, gray | 3597×4094, 16, gray |
| `indirection_heightmap.png` | 288×144, 8, RGBA | 258×172, 8, RGBA | 256×128, 8, RGBA |

- **heightmap scale factor: V = 2×, EK2 = 1×, GH = 1×.** `verified` — 18432/9216 = 2 and 9216/4608 = 2; the two mods' heightmaps are byte-for-byte the same dimensions as their `provinces.png`.
- **So the 2× heightmap is a vanilla choice, not a requirement.** `verified` by EK2 and GH shipping 1× and being playable released mods.
- `provinces.png` and `rivers.png` must be the *same* dimensions as each other. `verified` in all three.
- All three heightmaps are 16-bit single-channel grayscale, never 8-bit, never RGB. `verified`.
- `provinces.png` is 24-bit **truecolour RGB**, never palettised, in all three. `verified`.
- `rivers.png` is 8-bit **palette** (`colourtype=3`) in all three. `verified`.

### Multiple-of-N constraint

- **Hard constraint (arithmetic, `verified`): heightmap width and height must be divisible by `tile_size - 1`.** The indirection image is exactly the tile grid:
  - V: `original_heightmap_size={ 18432 9216 }`, `tile_size=65` → 18432/64 = **288**, 9216/64 = **144** = `indirection_heightmap.png` 288×144. ✔
  - EK2: `{ 8256 5504 }`, `tile_size=33` → 8256/32 = **258**, 5504/32 = **172** = 258×172. ✔
  - GH: `{ 8192 4096 }`, `tile_size=33` → 8192/32 = **256**, 4096/32 = **128** = 256×128. ✔
- Empirical common divisor of the six province-map dimensions: **all six are divisible by 64**; `gcd(9216, 8256, 8192) = 64`, `gcd(4608, 5504, 4096) = 128`. `verified`.
- `assumed`: a safe converter rule is *provinces/rivers dimensions divisible by 64, heightmap = 1× or 2× that*. Choosing 1× and `tile_size=33` then only needs divisibility by 32, which 64 already satisfies. There is **no define stating a dimension constraint** — `verified` by grepping `common/defines/` for `map_size`, `scale`, `height`; nothing of the kind exists.
- The world extents defines must be set to `dim - 1`:
  - `V common/defines/00_defines.txt:74` — `	WORLD_EXTENTS_X = 9215`
  - `V common/defines/00_defines.txt:76` — `	WORLD_EXTENTS_Z = 4607`
  - `EK2 common/defines/ek_defines.txt:34` — `    WORLD_EXTENTS_X = 8255`
  - `EK2 common/defines/ek_defines.txt:36` — `    WORLD_EXTENTS_Z = 5503`
  - `GH common/defines/00_defines.txt:79` — `	WORLD_EXTENTS_X = 8191`
  - `GH common/defines/00_defines.txt:81` — `	WORLD_EXTENTS_Z = 4095`
  - i.e. X = provinces width − 1, Z = provinces height − 1. `verified` in all three. Y is the vertical world scale, not a pixel count (§3).

*Reproduce:* `python3 -c "import struct;d=open(P,'rb').read(33);print(struct.unpack('>IIBBBBB',d[16:29]))"` for each PNG.

---

## 2. `map_data/heightmap.heightmap`

Full contents, all three (line numbers as shown; every file starts with a UTF-8 BOM — `V` first three bytes are `ef bb bf`, `verified`).

**Vanilla** (`V map_data/heightmap.heightmap`):
```
1  heightmap_file="map_data/packed_heightmap.png"
2  indirection_file="map_data/indirection_heightmap.png"
3  original_heightmap_size={ 18432 9216 }
4  tile_size=65
5  should_wrap_x=no
6  level_offsets={ { 0 0 } { 0 1397 } { 0 3129 } { 0 3690 } { 0 3861 } }
7  max_compress_level=4
8  empty_tile_offset={ 225 39 }
```

**EK2** (`EK2 map_data/heightmap.heightmap`):
```
1  heightmap_file="map_data/packed_heightmap.png"
2  indirection_file="map_data/indirection_heightmap.png"
3  original_heightmap_size={ 8256 5504 }
4  tile_size=33
5  should_wrap_x=no
6  level_offsets={ { 0 0 } { 0 3184 } { 0 3498 } { 0 3520 } { 0 3530 } }
7  max_compress_level=4
8  empty_tile_offset={ 9 2 }
```

**Godherja** (`GH map_data/heightmap.heightmap`):
```
1  heightmap_file="map_data/packed_heightmap.png"
2  indirection_file="map_data/indirection_heightmap.png"
3  original_heightmap_size={ 8192 4096 }
4  tile_size=33
5  should_wrap_x=no
6  level_offsets={ { 0 0 } { 0 3448 } { 0 3839 } { 0 3947 } { 0 3977 } }
7  max_compress_level=4
8  empty_tile_offset={ 26 38 }
```

Keys:

| key | meaning | evidence / confidence |
|---|---|---|
| `heightmap_file` | mod-root-relative path to the packed 16-bit atlas | `verified` — path resolves to the shipped `packed_heightmap.png` in all three |
| `indirection_file` | mod-root-relative path to the RGBA tile-lookup image | `verified` — resolves, and its dimensions equal the tile grid (§1) |
| `original_heightmap_size` | `{ width height }` of the *unpacked* `heightmap.png` | `verified` — matches `heightmap.png` IHDR exactly in all three |
| `tile_size` | edge length in px of one heightmap tile, **including the shared border row/column**; the stride is `tile_size - 1` | `verified` by the 18432/64 = 288 = indirection width identity in all three |
| `should_wrap_x` | whether the map wraps east–west | `no` in all three; `assumed` that `yes` enables cylindrical wrap |
| `level_offsets` | `{ x y }` origin inside `packed_heightmap.png` for each mip/compression level, level 0 first | `assumed` — the y values are strictly increasing and the last (V: 3861) is < packed height (4061), consistent with vertically stacked level blocks; not otherwise verifiable |
| `max_compress_level` | highest mip level present; `level_offsets` has `max_compress_level + 1` entries | `verified` arithmetically — 4 and 5 entries in all three |
| `empty_tile_offset` | `{ x y }` in tile units of the single all-water tile that every empty tile in the indirection image points at (dedup) | `assumed` — value differs per map and is small, consistent with a single shared tile; not verifiable from files |

### Are the packed pair shipped?

- **V: yes.** `packed_heightmap.png` (16.8 MB) and `indirection_heightmap.png` (40 KB) both present. `verified`.
- **EK2: yes.** 8.9 MB + 15.7 KB. `verified`.
- **GH: yes.** 7.7 MB + 34 KB. `verified`.
- So all three released maps ship the pair. **`assumed`: the game cannot boot a custom map without them** — the format is produced by the in-game map editor's "pack heightmap" step, and there is nothing in `map_data/` or `common/defines/` that describes generating them at load time. A converter that writes only `heightmap.png` must expect to open the map editor once to generate the pair. Not verified: no boot test was run here.
- `nodes.dat` (V 44.7 MB, EK2 11.2 MB, GH 2.8 MB) is also editor-generated and shipped by all three. Not referenced from `default.map`. `assumed` pathfinding/river-node cache.

---

## 3. Water level in `heightmap.png` — **the number**

### The define

`V common/defines/00_defines.txt:73-78`:
```
73  NJominiMap = {
74  	WORLD_EXTENTS_X = 9215
75  	WORLD_EXTENTS_Y = 50
76  	WORLD_EXTENTS_Z = 4607
77  	WATERLEVEL = 3 ### 0.06 in 0-1, 19 in 0-255, use 11% HSB in Photoshop
78  }
```
`EK2 common/defines/ek_defines.txt:35,37`:
```
35      WORLD_EXTENTS_Y = 51
37      WATERLEVEL = 3.8
```
`GH common/defines/00_defines.txt:80,82`:
```
80  	WORLD_EXTENTS_Y = 51
82  	WATERLEVEL = 3.8
```

### The formula

**`water_surface_16bit = WATERLEVEL / WORLD_EXTENTS_Y × 65535`** — `verified` (see measurement).

| map | WATERLEVEL | WORLD_EXTENTS_Y | fraction | predicted 16-bit | measured coastal-land median |
|---|---|---|---|---|---|
| V | 3 | 50 | 0.0600 | **3932** | **3928** |
| EK2 | 3.8 | 51 | 0.0745 | **4883** | **4868** |
| GH | 3.8 | 51 | 0.0745 | **4883** | **4883** (also p25 **and** p75 = 4883) |

Godherja's coastal land is a flat plateau at *exactly* 4883 — p25 = median = p75 = 4883. That is the conclusive proof of the formula: Godherja's map generator clamps shoreline land to the water plane, and the clamp value is the predicted one. `verified`.

The define comment's own "0.06 in 0-1" agrees with 3/50. Its "19 in 0-255" does **not** (0.06 × 255 = 15.3); 19/255 = 0.0745 = 3.8/51, i.e. the comment is stale and describes a 3.8/51 map. Treat the comment's 8-bit figure as wrong; use the formula.

### Measured land/sea separation (vanilla)

Classification: `provinces.png` pixel → colour → id via `definition.csv`; id ∈ (`sea_zones` ∪ `impassable_seas`) = sea, id ∉ (sea ∪ `lakes` ∪ `river_provinces`) = land; heightmap sampled at `[::2, ::2]` (2× scale, top-left of each 2×2 block).

```
heightmap.png global   min=0  max=49205        (max is 75.1% of 65535, not full scale)
SEA province px    n=18,440,815  p50=0  p90=0  p99=2798  p99.9=4178  max=10118   value==0: 92.4%
LAND province px   n=23,814,301  min=0  p0.1=3486  p1=4086  p50=8972  max=49159
LAKE province px   n=   106,208  min=0  p50=2728  max=38469
RIVER-prov px      n=   106,004  min=324 p50=2676 max=4478
coastal LAND px    n=   217,148  min=0  p1=2972  p5=3390  p50=3928
coastal SEA  px    n=   220,378  p50=3184  p95=5378  p99=30544  max=38469
```
Threshold behaviour at the predicted water plane 3932:
```
SEA pixels below 3932 : 99.884 %
LAND pixels ≥   3932 : 99.340 %
best single separating threshold (brute force 2000..6000): 3437, error 58,402 / 42,255,116 px = 0.138 %
```
- **92.4 % of sea-province pixels are exactly 0.** The vanilla ocean floor is a flat 0. `verified`.
- The most common single land value is **4128** (196,307 px of the sampled land) — the flat coastal-land plateau, sitting 196 above the water plane. `verified`.
- Coastal SEA p99 = 30,544 and max = 38,469 look wrong for "sea": that is `lakes`/major-river geometry inside high terrain, plus the 1-px province-border blend. Do not use coastal-sea statistics to set a threshold.
- 1.4 % of sampled heightmap values are odd (37,718 of 2,654,208 at 1/8 subsample). Values are *mostly* even but the format is genuinely 16-bit, not an 8-bit source upscaled. `verified`.

### Converter rules

- Write **water = 0** for open ocean, or anything `< water_surface_16bit`; safest is 0 (vanilla's own choice).
- Write **land ≥ water_surface_16bit + a small margin**. Vanilla's plateau is `+196`; Godherja clamps to exactly the plane. `assumed`: land exactly at the plane renders correctly (Godherja proves it) but `+64` of margin is cheaper than a debugging session.
- Height in world units = `value / 65535 × WORLD_EXTENTS_Y`. `verified` by the formula's three-map agreement.
- Do **not** use the full 0..65535 range: vanilla's max is 49,205 (75 %). `verified`. `assumed`: pushing to 65535 works but produces implausibly tall geometry (EK2 and GH do both hit 65535, so it is legal).

*Reproduce:* load `provinces.png` to a `(H,W)` uint32 colour key, LUT it to province ids via `definition.csv`, build the sea/land masks from `default.map`, sample `heightmap.png[::sy, ::sx]`, then print percentiles and the coastal-land median (`mask & shift(other_mask)` in 4 directions). numpy 2.5.3 + Pillow 12.3.0; peak RSS ~3 GB for the vanilla 18432×9216 heightmap.

---

## 4. `map_data/definition.csv`

Format: `id;r;g;b;name;x;` — **six semicolon-separated fields, no textual header row.**

`V map_data/definition.csv` first four lines (`cat -A`, `^M$` = CRLF):
```
1  0;0;0;0;x;x;^M$
2  1;42;3;128;VESTFIRDIR;x;^M$
3  2;84;6;1;REYKJAVIK;x;^M$
4  3;126;9;129;STOKKSEYRI;x;^M$
```

- **Column 0 = province id** (integer). **1,2,3 = R,G,B** 0..255. **4 = name** (a label only; the game's province name comes from localisation of the barony title, not from here — `assumed`). **5 = `x`**, a dead field in every row of all three maps. `verified`.
- **The `0` row.** Line 1 is literally `0;0;0;0;x;x;` — province id 0 with colour black. It is not a header, it is a reserved row. `verified`. Keep it: colour `(0,0,0)` and id 0 are the "no province" sentinel.
- **Trailing `;` is optional.** `verified` three ways:
  - V: 13,265 numeric rows have 7 `;`-fields (trailing `;` present), **3 rows have 6** and **2 have 8**. Example `V map_data/definition.csv:10889` — `10879;255;130;238;;^M$` (no trailing `;`, empty name). Example `V map_data/definition.csv:10524` — `10514;8;56;79;Naka;;x;^M$` (an extra empty field).
  - GH: **all 8,736 numeric rows have exactly 6 fields, no trailing `;`** — `GH map_data/definition.csv:1` = `0;0;0;0;x;x^M$`. A whole shipped map with no trailing separator. `verified`.
- **Comment lines start with `#`** and are skipped. `V map_data/definition.csv:3501` — `#RESERVED FOR CRACKDTOOTHGRIN;;;;;;`. Vanilla also parks unused ids as commented rows, e.g. `#14141;9;40;248;;x;`. `verified`.
- **Encoding: no BOM.** V first three bytes are `30 3b 30` (`0;0`). `verified`. GH and EK2 likewise start `0;0;0;0`. Line endings **CRLF** in all three. `verified`. File ends with a newline in V. `verified`.

### id density

| map | numeric rows | max id | missing ids in `1..max` |
|---|---|---|---|
| V | 13,270 (ids 0..13269) | 13,269 | **0** |
| EK2 | 5,848 (ids 0..5847) | 5,847 | **0** |
| GH | 8,736 (ids 0..8735) | 8,735 | **0** |

- **ids must be dense `0..N`.** `verified` in the sense that all three shipped maps are perfectly dense with no gaps — vanilla goes so far as to keep ~900 unused ids as *commented* rows rather than leave holes, and `01_province_properties.txt` has an explicit "UNUSED PROVINCES" section (`V common/province_terrain/01_province_properties.txt:11` — `# UNUSED PROVINCES`). `assumed` that a gap is fatal; nothing proves it, but no shipped map risks it. Write dense.
- A province id present in `definition.csv` but with **zero pixels** in `provinces.png` is legal — that is exactly what vanilla's unused ids are. `verified`.
- Conversely, **every colour in `provinces.png` must be in `definition.csv`**: V, EK2 and GH all have **0 pixels** mapping to id 0 (unmapped colour). `verified`.

### duplicate colours

- **No duplicate `r;g;b` triple exists in any of the three maps.** `verified` (`awk`-extract + `sort | uniq -d` → empty for all three, excluding the id-0 row).
- `assumed`: two ids sharing a colour means the second id gets no pixels and the first silently owns the region. Treat duplicate colours as a converter-fatal error and assign colours from a collision-free generator.

*Reproduce:* `awk -F';' '$1 ~ /^[0-9]+$/ && $1+0>0 {print $2";"$3";"$4}' definition.csv | sort | uniq -d` and `awk -F';' '$1 ~ /^[0-9]+$/ {a[$1+0]=1; if($1+0>m)m=$1+0} END{c=0; for(i=1;i<=m;i++) if(!(i in a)) c++; print length(a), m, c}' definition.csv`

---

## 5. `map_data/default.map`

The header block is **byte-identical across V, EK2 and GH** (modulo the BOM: V has none — first bytes `23 6d 61` = `#ma`; EK2 and GH both start with `ef bb bf`). `verified`.

`V map_data/default.map:1-13`:
```
 1  #max_provinces = 1466
 2  definitions = "definition.csv"
 3  provinces = "provinces.png"
 4  #positions = "positions.txt"
 5  rivers = "rivers.png"
 6  #terrain_definition = "terrain.txt"
 7  topology = "heightmap.heightmap"
 8  #tree_definition = "trees.bmp"
 9  continent = "continent.txt"
10  adjacencies = "adjacencies.csv"
11  #climate = "climate.txt"
12  island_region = "island_region.txt"
13  seasons = "seasons.txt"
```

| key | value | notes |
|---|---|---|
| `#max_provinces` | commented out, value `1466` | **dead**. Vanilla has 13,270 provinces while this stale comment says 1466. `verified`. There is **no live province-count define** anywhere in `common/` — grep for `MAX_PROVINCE\|NUM_PROVINCE\|PROVINCE_COUNT` hits only `common/legends/legend_types/00_legends.txt` (`max_provinces = 100/300/500`, a legend-spread parameter, unrelated). `verified`. |
| `definitions` | `"definition.csv"` | path relative to `map_data/`. `verified` (all three) |
| `provinces` | `"provinces.png"` | relative to `map_data/`. `verified` |
| `#positions` | **commented out in all three** | `verified`. Vanilla still ships a 349 KB `positions.txt`; GH ships a 97-byte stub whose entire content is `###############################\n## FILE REMOVED FOR GODHERJA ##\n###############################`; EK2 ships none at all. So `positions.txt` is optional and the commented key is the shipped convention. `verified` |
| `rivers` | `"rivers.png"` | `verified` |
| `#terrain_definition` | commented out, `"terrain.txt"` | dead; terrain comes from `common/province_terrain/` (§7). `verified` — no `terrain.txt` exists in any of the three `map_data/` |
| `topology` | `"heightmap.heightmap"` | `verified` |
| `#tree_definition` | commented out, `"trees.bmp"` | dead. `verified` |
| `continent` | `"continent.txt"` | **the file does not exist** in V, EK2 or GH `map_data/`. `verified` — `ls map_data/continent.txt` → No such file. The key is live (uncommented) and the game ships without the target. So a missing `continent.txt` is harmless. `verified` for vanilla-as-shipped |
| `adjacencies` | `"adjacencies.csv"` | `verified` |
| `#climate` | **commented out in all three**, yet `climate.txt` exists in all three | `verified`. Climate is therefore inert as shipped; §8 |
| `island_region` | `"island_region.txt"` | live in all three. `verified` |
| `seasons` | `"seasons.txt"` | live in V and EK2 (both ship the file). **GH declares it but ships no `seasons.txt`** — `verified` by directory listing. Another live-key-missing-file that boots |

### LIST syntax

Two forms, both used, both on the same key:
- `RANGE { a b }` — inclusive `a..b`. `V map_data/default.map:19` — `sea_zones = RANGE { 632 641 }`
- `LIST { a b c … }` — explicit ids, any count including one. `V map_data/default.map:31` — `sea_zones = LIST { 977 }`

Counts, `verified`:

| map | `RANGE {` | `LIST {` | notes |
|---|---|---|---|
| V | 144 | 78 + 1 lowercase `list {` | `V map_data/default.map:311` — `impassable_mountains = list { 12830 12846 12881 } ` — **lowercase `list` works**, and the line has trailing whitespace |
| EK2 | 48 | 84 + 2 with double space (`LIST  {`) | **extra whitespace before `{` works** |
| GH | 0 | 5 | GH uses only giant single-line `LIST`s (one is 8 KB long) |

So: the keyword is case-insensitive and whitespace-tolerant, and the same key may repeat any number of times — the sets are unions. `verified`.

### The id-set keys

All of these are repeatable `RANGE`/`LIST` keys. Every one of the seven appears in V, EK2 **and** GH — identical key vocabulary. `verified`.

| key | meaning | vanilla count |
|---|---|---|
| `sea_zones` | navigable water provinces | 471 ids |
| `river_provinces` | major-river provinces (navigable, drawn on land) | 224 ids |
| `lakes` | lake provinces | 75 ids |
| `impassable_seas` | water provinces that cannot be sailed | 16 ids |
| `impassable_mountains` | land provinces blocking movement | 1191 ids |

- **`wasteland` is not a key.** `verified` — the distinct top-level keys in all three `default.map` files are exactly `adjacencies continent definitions impassable_mountains impassable_seas island_region lakes provinces river_provinces rivers sea_zones seasons topology`. Vanilla has a `# WASTELAND` section header (`V map_data/default.map:314`) but the section body uses `impassable_mountains`, with a comment admitting it: `V map_data/default.map:316-317` — `# These are actually supposed to be Wasteland:` / `# Cannot be colored. Blocks unit movement, used for things like Sahara desert. ` — and then `V map_data/default.map:319` — `impassable_mountains = LIST { 730 731 8711 }`. **A converter must emit wasteland as `impassable_mountains`.**
- Comments (`#`) are allowed at line start and after a value: `V map_data/default.map:42` — `sea_zones = RANGE { 8613 8617 } #Iceland, Shetlands, Norway`. `verified`.
- The comment at `V map_data/default.map:170-171` documents `impassable_mountains` semantics: `# Can be colored by whoever owns the most of the province's neighbours.` / `# Blocks unit movement.`

*Reproduce:* `grep -oE "^[a-z_]+" default.map | sort -u` and `grep -ioE "(RANGE|LIST) *\{" default.map | sort | uniq -c`

---

## 6. `map_data/rivers.png` palette

Mode must be **8-bit indexed (PNG colourtype 3)**, same dimensions as `provinces.png`, no `tRNS`/transparency chunk (`im.info['transparency']` is `None` in all three). `verified`.

### The palette is identical in V, EK2 and GH

`verified` by dumping `Image.open(p).getpalette()` for each. Only difference: EK2's entry 11 is `(0,0,150)`, a duplicate of entry 10 — an authoring slip that does not break the mod, which is itself weak evidence that entries 11–15 are rarely used.

| idx | RGB | meaning | V px | EK2 px | GH px |
|---|---|---|---|---|---|
| **0** | `(0,255,0)` bright green | **river source** (spring / start of flow) | 631 | 437 | 471 |
| **1** | `(255,0,0)` red | **flow-in / tributary merge** (this river joins another) | 630 | 236 | 369 |
| **2** | `(255,252,0)` yellow | **flow-out / split** (river branches, e.g. a delta) | 31 | 11 | 19 |
| **3** | `(0,225,255)` | width step 1 — **narrowest** | 161,041 | 42,583 | 5,035 |
| 4 | `(0,200,255)` | width step 2 | 20,356 | 15,730 | 24,344 |
| 5 | `(0,150,255)` | width step 3 | 42,533 | 10,043 | 8,105 |
| 6 | `(0,100,255)` | width step 4 | 17,883 | 8,065 | 11,427 |
| 7 | `(0,0,255)` | width step 5 | 5 | 5,142 | 394 |
| 8 | `(0,0,225)` | width step 6 | 1,049 | 3,097 | 120 |
| 9 | `(0,0,200)` | width step 7 | 32,926 | 2,272 | 2,574 |
| 10 | `(0,0,150)` | width step 8 | 1,702 | 2,164 | 1,141 |
| 11 | `(0,0,100)` | width step 9 | 7,349 | 0 | 35,303 |
| 12 | `(0,85,0)` | width step 10 | 0 | 20 | 486 |
| 13 | `(0,125,0)` | width step 11 | 2 | 18 | 123 |
| 14 | `(0,158,0)` | width step 12 | 0 | 0 | 0 |
| **15** | `(24,206,0)` | width step 13 — **widest** | 2 | 0 | 0 |
| … | 16..253 unused | — | 0 | 0 | 0 |
| **254** | `(255,0,128)` magenta | **water / sea — "not a river, and not land either"** | 18,781,357 | 38,913,688 | 13,209,699 |
| **255** | `(255,255,255)` white | **land — "no river here"** | 23,399,831 | 6,437,518 | 20,254,822 |

### What is verified vs inferred

- **Palette RGB values and pixel counts: `verified`** from the files.
- **Indices 3..15 are the 13 river width steps, 3 narrowest → 15 widest: `verified` from a define, not from the wiki.** `V common/defines/jomini/rivers.txt:2-8`:
  ```
  2  NRivers = {
  3  	FADE_IN_DISTANCE = 10.0
  4  	FADE_OUT_DISTANCE = 5.0
  5  	NUM_WIDTH_PIXEL_VALUES = 13 #how many pixels in the river bitmap that are allocated for different river widths
  6  	WIDTH_MIN = 1.0	#how wide the rivers are when using the lowest width in the bitmap
  7  	WIDTH_MAX = 4.0 #how wide the rivers are when using the highest width in the bitmap
  8  	UV_SCALE = 0.8
  9  }
  ```
  13 width values, and indices 3..15 inclusive are exactly 13 entries, with 0/1/2 taken by the topology markers and 254/255 by the background. Rendered width interpolates 1.0 → 4.0 across them. This is why entries 12–15 are *green* despite being widths: the palette colours are only for the human editing the bitmap, the game reads the index.
- **254 = water, 255 = land: `verified` empirically**, by cross-tabbing every vanilla rivers pixel against the sea/lake province mask:
  ```
  idx 254: 18,781,357 px — 98.55 % fall on sea/lake provinces, 1.45 % on land
  idx 255: 23,399,831 px — 99.86 % fall on land provinces,     0.14 % on sea/lake
  ```
  The 1.45 % of magenta on land is the lake/major-river interiors that `default.map` classifies as land-adjacent, plus 1-px borders.
- **0 = source, 1 = merge, 2 = split: `assumed`**, from the CK3/Clausewitz convention plus two corroborating measurements: (a) sources and merges come in near-equal numbers in vanilla (631 vs 630) as a river tree requires, and splits are an order of magnitude rarer (31); (b) 99.2 % of index-1 and 94.9 % of index-0 pixels sit on land provinces, i.e. they are endpoints of land-drawn rivers, not sea markers. **Not** taken from any shipped `.info` file — none exists.

### Converter rules

- Fill the whole image with **255** (land) then **254** over every sea/lake pixel, then draw rivers. `verified` as the vanilla layout.
- Every river must start at exactly one index-0 pixel and be 1 px wide along its path. `assumed`.
- The palette must contain all 256 entries with the exact RGBs above, or at minimum indices 0..15, 254, 255. `assumed` — the game reads indices, but the map editor and every mod author reads colours; matching vanilla costs nothing.
- Never write an RGB/RGBA rivers.png. `verified` — all three are colourtype 3.

*Reproduce:* `python3 -c "from PIL import Image; import numpy as np; Image.MAX_IMAGE_PIXELS=None; im=Image.open('rivers.png'); a=np.asarray(im); p=im.getpalette(); [print(int(v), p[3*int(v):3*int(v)+3], int(c)) for v,c in zip(*np.unique(a,return_counts=True))]"`

---

## 7. `common/province_terrain/`

Two files in all three maps: `00_province_terrain.txt` and `01_province_properties.txt`. `verified`.

### `00_province_terrain.txt`

Flat `key=value`, one per line, **no braces**. `V common/province_terrain/00_province_terrain.txt:1-12` (file begins with a UTF-8 BOM, `verified` — first bytes `ef bb bf`):
```
 1  default_land=plains
 2  default_sea=sea
 3  default_coastal_sea=coastal_sea
 4  1=mountains
 5  2=taiga
 6  3=plains
 7  4=mountains
 8  5=hills
 9  6=hills
10  7=wetlands
11  8=plains
12  9=hills
```
- **Three mandatory default lines first: `default_land`, `default_sea`, `default_coastal_sea`.** `verified` — present as lines 1–3 in V and EK2. `EK2 common/province_terrain/00_province_terrain.txt:1` — `default_land=desert` (a mod may pick any key).
- Then `<province_id>=<terrain_key>`, one per line, no spaces around `=` in vanilla. `verified`.
- **Sea provinces need no entries.** `verified` — spot-checked vanilla sea id 632, 640, 8613 (`sea_zones`), 943 (`lakes`), 1052 (`river_provinces`): **all absent** from the file. They inherit `default_sea` / `default_coastal_sea`.
- **Coverage is not required to be complete even for land.** `verified` — the file has 11,960 `<id>=` lines and the highest id mentioned is 13,159, while there are 12,483 non-water provinces (13,269 − 471 sea − 75 lakes − 224 river − 16 impassable_sea). So ~523 land provinces have no line and fall back to `default_land`.
- Comment lines with `#` are used by GH: `GH common/province_terrain/00_province_terrain.txt:1` — `# THIS IS A GENERATED FILE.` — so leading comments are legal. `verified`.

### `01_province_properties.txt`

Braced blocks, keyed by province id, for winter severity. `V common/province_terrain/01_province_properties.txt:28-51`:
```
28  @himalayan_mountains = 0.90
29  @tibetan_mountains = 0.80
…
45  1527 ={
46  	winter_severity_bias = 0.45
47  }
48  # b_southwark
49  1526 ={
50  	winter_severity_bias = 0.45
51  }
```
- Note the vanilla spacing `1527 ={` — space before `=`, none after. `verified`.
- `@name = value` script-value constants are used. `verified`.
- Water provinces should stay at 0 bias: `V common/province_terrain/01_province_properties.txt:16` — `# Seas & rivers should stay at 0.0 severity bias`. Vanilla simply omits them. `verified`.
- `assumed`: this file is optional for a first boot; it only tunes winter.

### The 17 valid CK3 terrain keys

From `V common/terrain_types/00_terrains.txt` (each is a top-level `key = {` block; **17 total**, `verified` by `grep -cE "^[a-z_]+ *= *\{"`):

| line | key | | line | key |
|---|---|---|---|---|
| 7 | `plains` | | 176 | `oasis` |
| 23 | `sea` | | 198 | `jungle` |
| 35 | `coastal_sea` | | 227 | `forest` |
| 46 | `farmlands` | | 254 | `taiga` |
| 63 | `hills` | | 283 | `wetlands` |
| 92 | `mountains` | | 322 | `steppe` |
| 121 | `desert` | | 342 | `floodplains` |
| 143 | `desert_mountains` | | 364 | `drylands` |
| | | | 384 | `terraced_hills` |

One line: `plains sea coastal_sea farmlands hills mountains desert desert_mountains oasis jungle forest taiga wetlands steppe floodplains drylands terraced_hills`

- Mods add their own by dropping another file in `common/terrain_types/`. `verified` — `EK2 common/terrain_types/ek_terrains.txt` adds `ashlands valenwood tundra black_marsh` (4 more); `GH common/terrain_types/gh_terrains.txt` adds 18 (`marcher_plains marcher_farmlands marcher_hills marcher_mountains marcher_forest marcher_wetlands marcher_floodplains deadlands underworld_expanse mayik_caverns mayik_corridors mayik_chamber redlands_chasms redlands_desert redlands_mountains redlands_drylands archipelagic antimagic_terrain`). Note GH **replaces** `00_terrains.txt` (it ships only `gh_terrains.txt`, no `00_terrains.txt`) — so a total conversion may substitute the whole set.
- Field schema for a terrain block is documented in `V common/terrain_types/_terrains.info:1-16` — `key = {` / `	movement_speed = 1		# Speed on this type of terrain` / … / `	entity = "forest_birds_01" # Environmental graphical asset shown in this terrain.` That file also lists the ~18 auto-generated `KEY + _suffix` modifiers (`_attrition_mult`, `_advantage`, `_supply_limit`, …) at lines 34–52 — relevant because renaming a terrain silently invalidates every script referencing those.

---

## 8. `climate.txt`, `island_region.txt`, `geographical_regions/*.txt`

### `climate.txt` — **inert as shipped**

`default.map` comments the key out in all three maps (`#climate = "climate.txt"`, line 11 everywhere). `verified`. The files still exist. Syntax: three named blocks, each a bare whitespace-separated list of **province ids** (not titles).

`V map_data/climate.txt:1-10`:
```
 1  #Example: Most of Europe north of med.
 2  mild_winter = {
 3  	# Ireland
 4  	8 10 12
 5  	# Ireland
 6  	3 4 5 7 9 11 13 14 15 16
 7  	# British Isles
 8  	33 35 54
 9  	# England & Wales
10  	17 18 19 20 21 22 23 24 25 26 27 28 29 30 31 32 52 53 55 ...
```
Blocks present: `mild_winter` (`:2`), `normal_winter` (`:36`), `severe_winter` (`:66`). `verified`.
- **References province ids**, never titles. `verified`.
- No BOM (V first bytes `23 45 78` = `#Ex`), CRLF. `verified`.
- Mods keep it as a near-empty stub: `EK2 map_data/climate.txt` is 229 bytes with `mild_winter = { 1 2 3 4 5 6 7 8 }` / `normal_winter = { 9 }` / `severe_winter = { 10 }`; `GH map_data/climate.txt` is 58 bytes, entirely `#Example: Most of Europe north of med.\nmild_winter = {\n}` — a single empty block. `verified`. **So a converter can ship an empty-block stub.**
- Note both mod files have **no trailing newline** (`}` is the last byte). `verified`.

### `island_region.txt` — **live** (uncommented in all three)

Self-documenting. `V map_data/island_region.txt:1-21`:
```
 1  # Island regions - no land path from the continent
 2  # The AI needs these to optimize path finding
 3  #
 4  # NOTE: do not add any regions here that are NOT islands
 5  #
 6  # Island regions can be declared with one or more of the following fields:
 7  #	duchies = { }, takes county title names declared in landed_titles.txt
 8  #	counties = { }, takes county title names declared in landed_titles.txt
 9  #	provinces = { }, takes province id numbers declared in /history/provinces
10
11  island_region_iceland = {
12  	duchies = {	d_iceland }
13  }
14
15  island_region_faereyar = {
16  	counties = { c_faereyar }
17  }
18
19  island_region_shetland = {
20  	counties = { c_shetland }
21  }
```
- **Accepts `duchies`, `counties` (title keys) or `provinces` (ids)** — all three forms. `verified`: vanilla uses only `duchies`/`counties`; `EK2 map_data/island_region.txt:20` — `	provinces = { 144 }` proves the id form works.
- Header comment line 7 says `duchies = { }, takes county title names` — that is a **typo in Paradox's own comment**; line 12 shows `duchies = {	d_iceland }`, a duchy key. `verified` by the data.
- UTF-8 BOM in EK2 and GH; V has none (starts `23 20 49` = `# I`). `verified`. So the BOM is optional here.
- Purpose is AI pathfinding only. `assumed` harmless if omitted, but write it: vanilla's warning "the AI needs these" is explicit.

### `geographical_regions/*.txt`

Not referenced from `default.map`; the whole directory is loaded. `verified` — no `region` key exists in any `default.map`.

Declared field vocabulary, from Paradox's own header `V map_data/geographical_regions/geographical_region.txt:1-15`:
```
 1  # Geographical regions
 2  # Regions can be declared with one or more of the following fields:
 3  #	hegemonies = { }, takes de-jure hegemony title names declared in landed_titles.txts
 4  #	empires = { }, takes de-jure empire title names declared in landed_titles.txts
 5  #	kingdoms = { }, takes de-jure kingdom title names declared in landed_titles.txts
 6  #	duchies = { }, takes de-jure duchy title names declared in landed_titles.txt
 7  #	counties = { }, takes de-jure county title names declared in landed_titles.txt
 8  #	provinces = { }, takes province id numbers declared in /history/provinces
 9  #	regions = { }, a region can also include other regions, however the subregions needs to be declared before the parent region.
10  #		E.g. If the region world_europe contains the region world_europe_west then world_europe_west needs to be declared as a region before (i.e. higher up in this file) world_europe.
11
12  # Regions provide the following modifiers:
13  # key + _development_growth
14  # key + _development_growth_factor
15  # This requires "generate_modifiers = yes" in the region
```
Concrete examples, all `verified`:
- Duchy form — `V map_data/geographical_regions/geographical_region.txt:119-124`:
  ```
  119  world_europe_west_britannia = {
  120  	duchies = {
  121  		# England
  122  		d_bedford d_northumberland d_lancaster d_york d_norfolk d_hereford d_gloucester d_canterbury d_somerset
  123  		# Wales
  124  		d_gwynedd d_powys d_deheubarth d_cornwall
  ```
- Nested form + modifier generation — `:719-723`:
  ```
  719  world_steppe = {
  720  	generate_modifiers = yes
  721  	regions = {
  722  		world_steppe_west world_steppe_central world_steppe_east world_steppe_tarim
  ```
- Province-id form — `:1885-1890`:
  ```
  1885  	provinces = {
  1886  		#k_maghreb
  1887  		4758 4730 4732 4722 4714 4712 4711 4708 4707 4697 4698 4696 4748
  1888  		#k_tahert
  1889  		4673 4663 4660 4662 4661 4646 4645
  ```
- Graphical-region form with a colour — `:2115-2121`:
  ```
  2115  graphical_western = {
  2116  	graphical = yes
  2117  	color = { 255 0 0 }
  2118  	regions = {
  2119  		custom_west_francia_minus_mediterranean
  2120  		world_europe_west_germania world_europe_west_britannia world_europe_east world_europe_north
  ```
- **Both ids and titles are referenced**, per region, mixed freely across the file. `verified`. Field frequency across vanilla's `geographical_regions/`: `duchies` 360, `regions` 140, `counties` 101, `kingdoms` 37, `provinces` 25, `color` 7. `verified`.
- **Declaration order matters** for `regions = { }` — subregions must appear earlier in the file (line 9–10 above). `verified` from the comment; a converter must topologically sort.
- Vanilla ships 3 files (`geographical_region.txt`, `10_natural_disaster_regions.txt`, `tgp_chinesenaming_regions.txt`); EK2 4; GH 10. Load order is filename-alphabetical. `assumed`.
- UTF-8 BOM present in `V map_data/geographical_regions/geographical_region.txt` (`ef bb bf`), CRLF. `verified`.

#### What a `replace_path` on this folder costs — three things, all `verified` 2026-09-08 in the game

The folder needs a `replace_path` (vanilla's three files name vanilla duchies),
and that deletes **all 592** vanilla region names. They are not decoration:

1. **Vanilla scripts, GUI and achievements look them up.** 7,992
   `jomini_trigger.cpp:243: PostValidate of trigger 'geographical_region'
   returned false` from vanilla `common/dynasty_legacies`,
   `common/scripted_effects`, `common/scripted_triggers`,
   `common/customizable_localization`, … and one lookup returned a null that
   became an `EXCEPTION_ACCESS_VIOLATION` **one second after the main menu
   appeared**: `databases.h:36: Key
   dlc_fp1_region_core_mainland_scandinavia not found at Database:
   map_data/geographical_regions`, twice, then the crash. So every vanilla
   region name must be re-declared. `<name> = { regions = { } }` is enough,
   and it is the truth: no province of the new map is in it. Elder Kings 2 does
   this by hand for the handful it hit
   (`EK2 map_data/geographical_regions/geographical_region.txt:1896-1954`,
   "Empty right now, but setting this up for vanilla replacement purposes").
2. **Eight of them mint modifiers vanilla content references.** The eight with
   `generate_modifiers = yes` (`world_steppe`, `world_persian_empire`,
   `custom_ireland`, `custom_carthaginian_empire`, `custom_cumbria`,
   `world_innovation_elephants`, `world_innovation_camels`,
   `black_sea_coast_region`) produce `<key>_development_growth[_factor]`, and
   vanilla's `common/traits/00_traits.txt` and `common/culture/innovations/*`
   name them: without the region the game reports `Unexpected token:
   world_innovation_elephants_development_growth_factor`. So the flag has to be
   carried over with the name.
3. **The seven `graphical_*` regions must exist and cover every land province.**
   Every vanilla building asset lists all seven in its `graphical_regions = { }`
   filter (`common/buildings/00_castle_buildings.txt:99`); missing, that is
   2,611 `deferred_database_lookup: '<name>' in field 'geographical region' …
   could not be found in the database`, and a land province in no
   `graphical = yes` region is another 3,904 `geographical_region.cpp: Province
   N b_x has no visual geographical region assigned`. Godherja lists members of
   a graphical region as plain `provinces = { … }`
   (`GH map_data/geographical_regions/gh_biozone_geographical_region.txt:20`),
   which is what a converted map can produce with no duchy layer of its own.
   `RANGE`/`LIST` is `default.map` syntax and does **not** belong here.

#### One thing CK2 tolerates and CK3 rejects

`geographical_region.cpp: Region 'X' have multiple entries for the province
'N'` — a region may not reach one duchy or province through **two** of its
sub-regions. Faerûn's `yehimal_region` (a mountain range) shares 8 duchies with
`tabot_region`, `shou_lung_region` and `katakoro_plateau_region`, and all four
are children of `kara_tur_region`: 130 errors. The fix is to emit such a parent
**flat** — the deduplicated union of its subtree — which leaves membership
unchanged.

---

## 9. `map_data/adjacencies.csv`

Exact header, `V map_data/adjacencies.csv:1`:
```
From;To;Type;Through;start_x;start_y;stop_x;stop_y;Comment
```
`verified` byte-for-byte identical in EK2 (`EK2 map_data/adjacencies.csv:1`, preceded by a UTF-8 BOM) and in GH.

Vanilla body, `V map_data/adjacencies.csv:2-8`:
```
2  #BRITAIN
3  13;1690;sea;1019;655;3608;668;3617;Slemish-Arran
4  14;1684;sea;699;669;3577;698;3584;Carrickfergus-Wigtown
5  35;1691;sea;696;671;3710;674;3715;Mull-Ardnamurchon
6  1504;1515;river_large;628;-1;-1;-1;-1;Rochester-Maldon
7  1527;1526;river_large;629;948;3303;-1;-1;London-Southwark
8  1546;1549;sea;966;877;3242;880;3247;Portsmouth-Carisbrooke
```

### Valid `Type` values

| value | V rows | EK2 rows | GH rows |
|---|---|---|---|
| `sea` | 170 | 158 | 750 |
| `river_large` | 183 | 168 | 26 |
| `river` | 0 | 0 | **10** |
| `mountain` | 0 | 0 | **1** |

`verified` by `awk -F';' 'NR>1{print $3}' adjacencies.csv | sort | uniq -c`.
- **`sea` and `river_large` are `verified` from vanilla.** `river` and `mountain` are `verified` only as *shipped by Godherja* — a released playable mod, so they are almost certainly accepted, but vanilla never uses them. `assumed` that they work in unmodded 1.19.
- A converter should emit only `sea` and `river_large` unless it has a reason not to.

### Column meanings

| col | name | meaning | evidence |
|---|---|---|---|
| 1 | `From` | source land province id | `verified` (13, 14, 35 are Irish/Scottish land baronies) |
| 2 | `To` | destination land province id | `verified` |
| 3 | `Type` | `sea` \| `river_large` (see above) | `verified` |
| 4 | `Through` | the **water province id the crossing passes through** — a `sea_zones` id for `sea`, a `river_provinces` id for `river_large` | `verified`: line 6 `Through=628` and `V map_data/default.map:88` — `river_provinces = RANGE { 628 630 }		#Thames`, on a `river_large` row. Line 3 `Through=1019` and `V map_data/default.map:34` — `sea_zones = RANGE { 999 1011 }` … 1019 falls in `sea_zones = RANGE { 1019 1025 }` (`:36`), on a `sea` row |
| 5–6 | `start_x`, `start_y` | pixel coords **on `provinces.png`** where the adjacency graphic (bridge/strait line) begins | `assumed` from magnitude: max observed y ≈ 3617 < 4608 and x ≈ 1019 < 9216, so they are provinces-space, not heightmap-space |
| 7–8 | `stop_x`, `stop_y` | pixel coords where it ends | `assumed`, same reasoning |
| 9 | `Comment` | free text, human only | `verified` |

### `-1` is allowed

`verified` — count of literal `-1` per column in vanilla's 391 data rows:
```
col 5 (start_x): 131    col 6 (start_y): 132
col 7 (stop_x):  186    col 8 (stop_y):  186
col 9 (Comment):  44
col 1 (From): 1   col 2 (To): 1   col 4 (Through): 1   ← the terminator row only
```
- `-1` in a coordinate means **"let the game place it"**. `verified` that vanilla ships it (line 6 has all four as `-1`) and that a *partial* `-1` works (line 7 gives a start but `-1;-1` for stop).
- `-1` in `Comment` is used as filler. `verified`.
- **Vanilla's last line is a terminator row** — `V map_data/adjacencies.csv:392` — `-1;-1;;-1;-1;-1;-1;-1;` (note the empty `Type`). `assumed` that it is optional; both mods also end with something similar, and no shipped file omits it, so write it.
- Comment lines start with `#`: `V map_data/adjacencies.csv:2` — `#BRITAIN`. `verified`. Blank lines occur too (vanilla's line 390 is empty). `verified`.
- **Line endings: vanilla uses bare LF** (`head -c 4000 | grep -c $'\r'` → 0), **EK2 and GH use CRLF**. `verified`. Both work.
- **BOM: vanilla has none** (first bytes `46 72 6f` = `Fro`); EK2 and GH both have one. `verified`. Both work.

`Through` renders the crossing on `gfx`: `V common/defines/jomini/adjacencies.txt:2` — `	UV_SCALE = 0.125`.

---

## 10. Gotchas — things that will break a converter

Ordered by how much time each costs.

1. **`heightmap.heightmap` + `packed_heightmap.png` + `indirection_heightmap.png` are editor artefacts.** All three shipped maps include them. `assumed`: writing only `heightmap.png` will not boot. Budget one manual pass through the in-game map editor's heightmap-pack step per dimension change, and hard-code the resulting `tile_size`/`level_offsets`/`empty_tile_offset` back into the converter's template. **`original_heightmap_size` must equal `heightmap.png`'s real dimensions and be divisible by `tile_size - 1`** or the indirection grid will not line up (§1, `verified` arithmetic).
2. **Water level is `WATERLEVEL / WORLD_EXTENTS_Y × 65535`, not a constant.** Change `WORLD_EXTENTS_Y` and every land pixel in the heightmap silently becomes sea (or vice versa). Vanilla = 3932, EK2/GH = 4883. `verified` (§3). Set the three `WORLD_EXTENTS_*` defines in the same commit as the map dimensions.
3. **`WORLD_EXTENTS_X`/`_Z` are `dim - 1`, not `dim`.** Off-by-one here misaligns the whole map. `verified` in all three maps (§1).
4. **`provinces.png` must be 24-bit truecolour RGB, `rivers.png` must be 8-bit palette, `heightmap.png` must be 16-bit grayscale.** Pillow will happily write the wrong one; assert `colourtype` after saving. `verified` (§1). Also: **no interlacing** in any shipped map (`interlace=0` everywhere), `verified`.
5. **Colour `(0,0,0)` and province id `0` are reserved.** `definition.csv` line 1 is `0;0;0;0;x;x;` and **zero pixels** in V, EK2 or GH `provinces.png` map to it. `verified`. Never allocate black to a real province. `assumed`: `(255,255,255)` is safe in `provinces.png` (vanilla uses `255;216;0` and `255;130;238`, so bright colours are fine), but white is the "land" index in `rivers.png` — do not confuse the two files' conventions.
6. **`wasteland` is not a `default.map` key.** Emit wasteland provinces as `impassable_mountains`; vanilla's own `# WASTELAND` section does exactly that and says so in a comment. `verified` (§5).
7. **Encoding and line endings are inconsistent *within* vanilla itself.** `verified`: `definition.csv` no BOM + CRLF; `adjacencies.csv` no BOM + **LF**; `heightmap.heightmap` **BOM** + LF; `default.map` no BOM + CRLF; `geographical_regions/*.txt` BOM + CRLF; `00_province_terrain.txt` BOM. The mods flip several of these (EK2's `adjacencies.csv` and `default.map` both gain a BOM). **Conclusion: the parser tolerates BOM/no-BOM and LF/CRLF for all of these.** Safest converter output: UTF-8 **with** BOM + LF for `common/` script and `map_data/*.txt`, UTF-8 **without** BOM for the two CSVs. Do not emit UTF-16 or Windows-1252.
8. **Trailing `;` in `definition.csv` is optional, and rows with 5 or 7 fields are tolerated.** `verified` — Godherja ships 8,736 rows with none, and vanilla itself has 3 rows missing it and 2 with an extra. Do not spend time on this; but do keep the field *order* exact.
9. **Province ids must be dense `0..N` with no gaps.** All three maps are perfectly dense; vanilla keeps ~900 unused ids as commented-out rows rather than leave a hole, and `01_province_properties.txt` has a dedicated `# UNUSED PROVINCES` section. `assumed` fatal, `verified` universally avoided (§4).
10. **`default.map` may declare files that do not exist.** `continent = "continent.txt"` is uncommented in all three maps and the file is absent from all three; GH declares `seasons = "seasons.txt"` and ships none. `verified`. So a missing target is not necessarily the cause of a boot failure — do not chase it.
11. **There is no live max-province define.** `#max_provinces = 1466` in `default.map` is commented out and 9× smaller than vanilla's real 13,270. Grepping `common/` for `MAX_PROVINCE`/`NUM_PROVINCE`/`PROVINCE_COUNT` yields only an unrelated legend parameter. `verified`. Don't look for a cap; there isn't one to set.
12. **`positions.txt` is optional** — commented out in all three `default.map` files; EK2 ships none, GH ships a 97-byte "FILE REMOVED" stub. `verified`. Do not block a first boot on it.
13. **`climate.txt` is inert** — the key is commented out in all three. GH's whole file is one empty `mild_winter = { }` block. `verified`. Ship a stub; do not compute climate.
14. **Sea/lake/river provinces must be absent from `00_province_terrain.txt`, not set to `sea`.** Vanilla omits every water id and relies on `default_sea`/`default_coastal_sea`. `verified` (§7). Writing `632=sea` is `assumed` harmless but diverges from every shipped map.
15. **`rivers.png` indices 12–15 are widths, not "unused greens".** `NUM_WIDTH_PIXEL_VALUES = 13` forces indices 3..15 to be the width ramp. `verified` from the define (§6). A converter that treats 12–15 as land/spare will produce invisible or wrong-width rivers.
16. **`geographical_regions` sub-regions must be declared before their parents in file order.** `verified` from Paradox's comment. Topologically sort before writing.
17. **A total conversion may need to *replace* `common/terrain_types/00_terrains.txt`, not add to it.** Godherja ships only `gh_terrains.txt` — no `00_terrains.txt` at all — so its 18 terrains are the entire set. `verified`. Renaming or dropping a terrain key invalidates the ~18 auto-generated `KEY + _suffix` modifiers listed in `common/terrain_types/_terrains.info:34-52`, which script elsewhere may reference.
18. **`nodes.dat` is large and editor-generated** (V 44.7 MB). Not referenced from `default.map`. Shipped by all three. `verified`. `assumed` needed; treat like the packed heightmap pair.

---

## Final fact table

| fact | value | evidence |
|---|---|---|
| Vanilla water surface, 16-bit | **3932** | `V common/defines/00_defines.txt:75,77` (`WORLD_EXTENTS_Y = 50`, `WATERLEVEL = 3`) → 3/50×65535 = 3932.1; measured coastal-land median **3928** |
| EK2 / GH water surface, 16-bit | **4883** | `EK2 common/defines/ek_defines.txt:35,37`; `GH common/defines/00_defines.txt:80,82` (both 3.8/51) → 4883.0; GH coastal-land p25 = p50 = p75 = **4883** exactly |
| Water-level formula | `WATERLEVEL / WORLD_EXTENTS_Y × 65535` | three-map agreement above, `verified` |
| Vanilla ocean floor value | **0** (92.4 % of sea-province px) | measured |
| Vanilla heightmap max | 49,205 (75 % of range) | measured |
| V provinces / rivers | 9216×4608 | PNG IHDR |
| V heightmap | 18432×9216 = **2×** | PNG IHDR |
| EK2 provinces / rivers / heightmap | 8256×5504 / 8256×5504 = **1×** | PNG IHDR |
| GH provinces / rivers / heightmap | 8192×4096 / 8192×4096 = **1×** | PNG IHDR |
| Heightmap-size constraint | divisible by `tile_size - 1` (64 in V, 32 in mods) | 18432/64=288=indirection width, in all three |
| Common divisor of all six province dims | 64 | `gcd(9216,8256,8192)=64`, `gcd(4608,5504,4096)=128` |
| `provinces.png` format | 8-bit RGB (colourtype 2), non-interlaced | PNG IHDR, all three |
| `rivers.png` format | 8-bit palette (colourtype 3), 256 entries, no tRNS | PNG IHDR + `getpalette()`, all three |
| `heightmap.png` format | 16-bit grayscale (colourtype 0) | PNG IHDR, all three |
| Packed heightmap pair shipped | **yes in V, EK2 and GH** | directory listing |
| `rivers.png` land index | **255** = `(255,255,255)` | 99.86 % of index-255 px on land provinces |
| `rivers.png` water index | **254** = `(255,0,128)` | 98.55 % of index-254 px on sea/lake provinces |
| `rivers.png` width indices | **3..15**, 3 narrowest (width 1.0) → 15 widest (width 4.0) | `V common/defines/jomini/rivers.txt:5-7` (`NUM_WIDTH_PIXEL_VALUES = 13`) |
| `rivers.png` marker indices | 0 source, 1 merge, 2 split (`assumed`) | 631 vs 630 vs 31 px in vanilla; ≥95 % on land |
| Rivers palette source | **not** an `.info` file — no `map_data/*.info` exists | `find <game> -name '*.info'` = 166 hits, none under `map_data/` |
| `definition.csv` columns | `id;r;g;b;name;x;` | `V map_data/definition.csv:1-4` |
| `definition.csv` row 0 | `0;0;0;0;x;x;` — reserved, not a header | `V map_data/definition.csv:1` |
| `definition.csv` trailing `;` | **optional** | GH: 8,736/8,736 rows without it |
| `definition.csv` BOM / EOL | no BOM / CRLF (V, EK2, GH) | first-3-bytes `30 3b 30` |
| Province-id density | dense `0..N`, 0 gaps in V (13,269), EK2 (5,847), GH (8,735) | `awk` gap scan |
| Duplicate colours | none in any of the three | `sort \| uniq -d` empty |
| `default.map` key set | `definitions provinces rivers topology continent adjacencies island_region seasons` + `sea_zones river_provinces lakes impassable_seas impassable_mountains` | `grep -oE "^[a-z_]+"`, identical in all three |
| `default.map` dead keys | `#max_provinces #positions #terrain_definition #tree_definition #climate` | `V map_data/default.map:1,4,6,8,11` |
| `wasteland` key | **does not exist** — use `impassable_mountains` | `V map_data/default.map:314-319` |
| List syntax | `RANGE { a b }` inclusive, `LIST { a b … }`; case- and whitespace-insensitive; keys repeat and union | V 144 RANGE / 78 LIST / 1 `list`; EK2 has `LIST  {` |
| Live province-count cap | **none exists** | grep `MAX_PROVINCE\|NUM_PROVINCE\|PROVINCE_COUNT` over `common/` |
| Terrain keys (vanilla) | **17** | `grep -cE "^[a-z_]+ *= *\{" common/terrain_types/00_terrains.txt` |
| Terrain key list | `plains sea coastal_sea farmlands hills mountains desert desert_mountains oasis jungle forest taiga wetlands steppe floodplains drylands terraced_hills` | same file, lines 7–384 |
| `province_terrain` syntax | `default_land=` / `default_sea=` / `default_coastal_sea=` then `<id>=<key>` | `V common/province_terrain/00_province_terrain.txt:1-4` |
| Sea provinces in `province_terrain` | **absent** — inherit `default_sea` | ids 632, 640, 8613, 943, 1052 all absent |
| `province_terrain` coverage | 11,960 of 12,483 land provinces; rest fall back to `default_land` | line count vs `default.map` water sets |
| `climate.txt` | province **ids**, blocks `mild_winter` / `normal_winter` / `severe_winter`; key commented out in `default.map` | `V map_data/climate.txt:2,36,66`; `V map_data/default.map:11` |
| `island_region.txt` | `duchies` / `counties` (title keys) or `provinces` (ids) | `V map_data/island_region.txt:6-9,12,16`; `EK2 …:20` = `provinces = { 144 }` |
| `geographical_regions` fields | `hegemonies empires kingdoms duchies counties provinces regions` + `generate_modifiers` + `graphical`/`color` | `V map_data/geographical_regions/geographical_region.txt:2-15,720,2116-2117` |
| `geographical_regions` ordering | sub-regions must precede parents | same file, lines 9–10 |
| `adjacencies.csv` header | `From;To;Type;Through;start_x;start_y;stop_x;stop_y;Comment` | `V map_data/adjacencies.csv:1`, identical in EK2 and GH |
| `adjacencies.csv` Types (vanilla) | `sea` (170), `river_large` (183) | `awk` on col 3 |
| `adjacencies.csv` Types (GH extra) | `river` (10), `mountain` (1) | `awk` on col 3 |
| `adjacencies.csv` `-1` | allowed in all four coords and in `Comment`; partial `-1` allowed | 131/132/186/186 occurrences; `V …:6` all-`-1`, `V …:7` half-`-1` |
| `adjacencies.csv` terminator | `-1;-1;;-1;-1;-1;-1;-1;` as last line | `V map_data/adjacencies.csv:392` |
| `adjacencies.csv` BOM / EOL | V: no BOM + **LF**; EK2/GH: BOM + CRLF — both work | `head -c3` + `grep -c $'\r'` |
| `Through` | the water province id the crossing passes through | `V …:6` `Through=628` ∈ `river_provinces RANGE { 628 630 }` (`default.map:88`) |
| `continent.txt` | declared live, **file absent** in all three | `ls map_data/continent.txt` → No such file |
| `positions.txt` | optional; commented out in all three; GH ships a "FILE REMOVED" stub | `V map_data/default.map:4`; `GH map_data/positions.txt` (97 B) |
| `nodes.dat` | editor-generated, unreferenced, shipped by all three (V 44.7 MB) | directory listing |
