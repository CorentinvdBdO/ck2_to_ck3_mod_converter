# CK3 packed heightmap (`heightmap.heightmap` + `packed_heightmap.png` + `indirection_heightmap.png`)

Reverse-engineered on 2026-09-07 against CK3 **1.19.0.6**, Elder Kings 2
(workshop `2887120253`) and Godherja (`2326030123`).  Code:
`src/ck2ck3/map/packed_heightmap.py`.  Reproduce every number here with

```
uv run scripts/decode_packed_heightmap.py --all --reencode /tmp/reenc
uv run scripts/decode_packed_heightmap.py --size-report 6144x5120 --write /tmp/sz
```

Labels: `verified` = read out of the shipped files or the shipped binary;
`assumed` = inference that no file we have can settle.

---

## 0. Why this file exists

`map_data/default.map:7` is `topology = "heightmap.heightmap"` (`verified`).
CK3 does **not** load `heightmap.png` at runtime — it loads that descriptor and
through it a *packed pair*.  `heightmap.png` is the map editor's source of
truth only.  This corrects the invariant in `CLAUDE.md` ("packed heightmap pair
comes from the in-game map editor; the converter writes only heightmap.png"):
the converter now writes the pair itself.

### Can the game boot with `heightmap.png` alone?

**No** — `assumed`, with strong indirect evidence:

* `strings binaries/ck3.exe` contains `Failed loading packed heightmap '%s'`
  and `Failed loading indirection map '%s'` and no string suggesting a
  `heightmap.png` runtime fallback (`verified`).
* All three maps we have ship `heightmap.png` **and** both packed files
  (`verified`); none ships only `heightmap.png`.
* The experiment that would settle it: rename `packed_heightmap.png` in a test
  mod and launch. Not done — no headless CK3 here.

### The map-editor alternative ("repack heightmap")

`binaries/ck3.exe` contains (`verified`):

```
Map Editor - Repack Window          repack_window       CRepackWindow@PdxMapEditor
[PackHeightmap] Tile size: %d       [PackHeightmap] Compression Levels: %d
[PackHeightmap] Compression level %d: %d tiles
[PackHeightmap] Empty tiles count: %d
[PackHeightmap] Indirection map size: %d x %d (%d tiles total)
[PackHeightmap] Packed heightmap size: %d x %d
Packed heightmap in %.2fs
Failed to pack heightmap on editor setup (did source data change?). Will try repacking...
original_heightmap_size specified in heightmap.heightmap (%d, %d) is not the same
  resolution as the heightmap you are trying to load (%d, %d). Size of the bitmap
  will be used for packing.
Heightmap.LoadMaxError
C:\mnt\gsg\ck3\titus\cw\clausewitz\pdx_utils\pdx_packedheightmap.cpp
```

So: launch CK3 with `-debug_mode`, open the map editor, and its Repack Window
regenerates the pair from `heightmap.png`; the editor also repacks by itself on
setup when it notices the pair is stale.  That is the manual alternative to
this module, and it needs a Windows/Proton run of the game with the mod loaded.
`Heightmap.LoadMaxError` is the compiled-in tolerance the packer uses — it has
no default in any shipped `.settings` file, which is why §5 has to fit it.

---

## 1. The descriptor

`map_data/heightmap.heightmap`, UTF-8 **with BOM** (`ef bb bf`, `verified` in
all three).  Vanilla uses LF and is 293 bytes; both mods use CRLF (the editor
wrote them on Windows).  Eight keys, always in this order:

```
heightmap_file="map_data/packed_heightmap.png"
indirection_file="map_data/indirection_heightmap.png"
original_heightmap_size={ 18432 9216 }
tile_size=65
should_wrap_x=no
level_offsets={ { 0 0 } { 0 1397 } { 0 3129 } { 0 3690 } { 0 3861 } }
max_compress_level=4
empty_tile_offset={ 225 39 }
```

Note the spaces inside every brace pair.  `HeightmapDescriptor.to_text()`
reproduces vanilla's file **byte for byte** (293 B == 293 B) and both mods'
files byte for byte after CRLF→LF (`verified`, `test_descriptor_matches_vanilla_byte_for_byte`).

| | vanilla 1.19 | Elder Kings 2 | Godherja |
|---|---|---|---|
| `original_heightmap_size` | 18432 × 9216 | 8256 × 5504 | 8192 × 4096 |
| `tile_size` | 65 | 33 | 33 |
| `level_offsets` y | 0, 1397, 3129, 3690, 3861 | 0, 3184, 3498, 3520, 3530 | 0, 3448, 3839, 3947, 3977 |
| `max_compress_level` | 4 | 4 | 4 |
| `empty_tile_offset` | 225 39 | 9 2 | 26 38 |
| `should_wrap_x` | no | no | no |

`level_offsets` x is `0` in all 15 entries, so whether the game adds it to the
tile x is `assumed` (this module writes 0 and adds it on decode).

## 2. The three images

`verified` from the PNG IHDR chunks:

| file | vanilla | EK2 | Godherja | PNG |
|---|---|---|---|---|
| `heightmap.png` | 18432×9216 | 8256×5504 | 8192×4096 | 16-bit grey (depth 16, colour type 0) |
| `packed_heightmap.png` | 3185×4061 | 1881×3539 | 3597×4094 | **16-bit grey**, not 8-bit |
| `indirection_heightmap.png` | 288×144 | 258×172 | 256×128 | 8-bit **RGBA** (depth 8, colour type 6) |

**The packed atlas is 16-bit, so nothing is lost to bit depth.**  Vanilla's
atlas values run 0..49145 against the heightmap's 0..49205; the game renders
from the same 16-bit range as `heightmap.png`.  The only losses are the ones in
§4 and §5.

**All three images are bottom-up** (`verified`; DDS/OpenGL convention).  Read
them with PIL (top-down) and every offset in the descriptor comes out off by
one and appears to contradict `level_offsets`; read them as `arr[::-1]` and the
arithmetic below is exact.  The flips of the indirection and the heightmap
cancel, so *tile grid indices need no flip* — only the atlas offsets do.

## 3. Geometry

`stride = tile_size - 1`, i.e. **tiles overlap their neighbour by one pixel**
(`verified`: the shared line, sampled at the coarser of the two levels, is
byte-identical from both sides -- 1000 Godherja seams, 0 mismatches).  Grid size:

```
nx = original_width  / stride       ny = original_height / stride
vanilla   18432/64 = 288   9216/64 = 144   -> indirection is 288x144  ✓
EK2        8256/32 = 258   5504/32 = 172   -> indirection is 258x172  ✓
Godherja   8192/32 = 256   4096/32 = 128   -> indirection is 256x128  ✓
```

Three maps, three tile sizes' worth of arithmetic, three exact hits: the stride
really is `tile_size - 1`, not `tile_size` (`verified`).

The last grid column/row needs one pixel past the heightmap.  Vanilla **clamps**
(edge-extend): the outer column of the right-most tile equals heightmap column
`W-1` and does *not* equal column 0 (`verified` for vanilla and Godherja, both
`should_wrap_x=no`).  What `should_wrap_x=yes` does is `assumed`; this module
wraps in x and always clamps in y.

Indirection pixel → tile, `verified`:

```
R = r   G = g   B = 2**level   A = level
level      in 0..max_compress_level            (A histogram: only 0..4 occur)
B == 2**A  exactly, for every pixel of all three indirection images
px         = ((tile_size - 1) >> level) + 1    (65 -> 65,33,17,9,5)
atlas origin, bottom-up = ( level_offsets[level].x + r*px,
                            level_offsets[level].y + g*px )
```

`B` is redundant with `A`; it is presumably the shader's scale factor
(`assumed`).

Proof that this layout is right and complete: paint every referenced tile's
`px × px` box into an occupancy map of the atlas and count collisions —
**0 overlaps** in all three maps, covering 95.0% / 99.4% / 96.0% of the atlas
(`verified`, and the gaps are the ragged ends of each level's block).  Levels do
share a scanline band: vanilla's level-0 tiles reach y=1430 while
`level_offsets[1].y` is 1397, because the packer drops level-1 tiles into the
free x-space to the right of level 0's short last row.  So `level_offsets` marks
where a level *starts*, it does not fence a level off.

Tile content is **decimation**, not averaging (`verified`):

```
tile[p][i] = heightmap_bottomup[ ty*stride + p*2**level ][ tx*stride + i*2**level ]
```

## 4. The one lossy thing a level-0 tile does: LOD-matched edges

Interiors are byte-exact.  Edges are not, and it is deliberate: two tiles at
different levels share a line, and unless that line is identical on both sides
the mesh cracks.  So each of the four edge lines is resampled at the **coarser**
of the two levels that share it:

```
step = 2 ** max(own level, neighbour level)
edge = floor( 0.5 + linear interpolation of the edge through every step-th sample )
```

`verified` on Godherja: 26384 of 26384 sampled edge values reproduced exactly
with `floor(x+0.5)` (`np.rint` — round-half-even — only gets 97.8%, `floor`
94.3%, `ceil` 98.7%).  Raw decimation of the same edges matches only 91.1% and
is off by up to 643.  Because `step` divides `tile_size - 1`, the *endpoints*
survive, which is why tile **corners** stay exact even where four levels meet.

## 5. How the level is chosen

Highest level whose **bilinear** reconstruction stays within a tolerance:

```
level(tile) = max { L : max| upsample(decimate(tile, 2**L), 2**L) - tile | <= 655 }
```

Fitted, not read out of a file.  Evidence (`verified`), 1483 random Godherja
tiles: best-fitting threshold 651, agreement with the shipped indirection
**99.60%**; at 655 it is 99.53%.  Godherja's own numbers bracket it — over 300
tiles, `max error at the chosen level` never exceeded 654 and `min error at
chosen+1` never dropped below 662.  655 is `round(0.01 * 65535)`, so "1% of full
range" is very likely the actual rule; the constant itself is `assumed`, and
`Heightmap.LoadMaxError` (§0) is what would settle it.

Cross-check by re-encoding each shipped `heightmap.png` with this rule
(`verified`, `--reencode`):

| map | per-tile level agreement | our level histogram | shipped histogram | our packed png | shipped |
|---|---|---|---|---|---|
| Godherja | **99.44%** | 11353 4745 2869 1552 12249 | 11371 4785 2960 1528 12124 | 6.28 MB | 7.74 MB |
| EK2 | 96.71% | 4558 2433 635 396 36354 | 5521 1951 382 321 36201 | 7.28 MB | 8.94 MB |
| vanilla | 87.97% | 1282 3659 6379 4970 25182 | 1063 4948 6100 4838 24523 | 15.47 MB | 16.83 MB |

Godherja agrees best because its pair was generated by the editor from exactly
the `heightmap.png` it ships.  Vanilla agrees worst and its shipped tiles carry
errors far above any threshold (level-2 tiles off by up to 25329, §6), so
vanilla's pair was most likely packed from a source that is no longer identical
to the shipped `heightmap.png` (`assumed`).

## 6. Reconstruction error, per map

`uv run scripts/decode_packed_heightmap.py --all` (`verified`, 16-bit units,
full range 65535):

| map | size | ts | max | mean | exact | interior max | interior exact | edge max | edge exact |
|---|---|---|---|---|---|---|---|---|---|
| vanilla | 18432×9216 | 65 | 25329 | 32.333 | 46.96% | 25329 | 46.82% | 4829 | 51.47% |
| EK2 | 8256×5504 | 33 | 4578 | 3.457 | 94.97% | 4578 | 94.98% | 4551 | 94.72% |
| Godherja | 8192×4096 | 33 | 2351 | 40.237 | 69.11% | 2092 | 68.76% | 2351 | 74.50% |

The number that proves the decode is *correct* rather than merely close is the
level-0 row — tile interiors, per compression level (n tiles / max abs err /
exactly-equal fraction):

```
vanilla   L0 1063/0/1.0000   L1 4948/6260/0.3078  L2 6100/25329/0.1626  L3 4838/7436/0.1101  L4 24523/1263/0.6241
EK2       L0 5521/0/1.0000   L1 1951/3198/0.2810  L2  382/4578/0.1492   L3  321/1654/0.1193  L4 36201/3028/0.9940
Godherja  L0 11371/0/1.0000  L1 4785/1733/0.5187  L2 2960/2092/0.2788   L3 1528/899/0.1400   L4 12124/655/0.6302
```

**Every level-0 tile interior in all three maps round-trips with zero error**
(17 955 tiles, 100.00%).  The format is understood; the residue at L≥1 is
information the packer threw away, not a decode bug.  Godherja's L4 interior max
is exactly **655** — the threshold of §5 showing up in the data.

So the honest answer to "is it lossy": the container is lossless (16-bit atlas,
exact decimation), the *encoder* is lossy above level 0 and on tile edges, and
the loss is bounded by the packer's tolerance except where a tile borders a much
coarser neighbour.

## 7. Worked example: one real vanilla tile, by hand

Bottom-up grid tile `(tx=27, ty=82)` = top-down pixel `(27, 61)` of
`indirection_heightmap.png` (`144-1-82 = 61`).

1. That pixel is RGBA `(10, 10, 1, 0)` → `r=10`, `g=10`, `B=1=2**0`, `level=0`.
2. `px = ((65-1) >> 0) + 1 = 65`.
3. `level_offsets[0] = { 0 0 }`, so the atlas origin (bottom-up) is
   `(0 + 10*65, 0 + 10*65) = (650, 650)`, i.e. top-down rows **3346..3410**,
   columns **650..714** of the 3185×4061 `packed_heightmap.png`.
4. It covers heightmap bottom-up rows `82*64 .. 82*64+64` = **5248..5312**,
   columns `27*64 .. 27*64+64` = **1728..1792**.
5. Interior check: 3969 of 3969 interior pixels identical.  Row 1 starts
   `17822, 18264, 18760, 19228, 19562, 20046` in both the atlas and the
   heightmap.
6. Edges: neighbours are level `0` (below), `2` (above), `0` (left), `0`
   (right).  The bottom/left/right edges therefore use `step=1` and are raw.
   The top edge uses `step = 2**max(0,2) = 4`; the heightmap's row is
   `11136, 11178, 11404, 11550, 11658, ...` but the atlas stores
   `11136, 11267, 11397, 11528, 11658, ...` — exactly
   `floor(0.5 + interp(row[0::4]))`, matching all 65 values, off by up to 150
   from the raw row.  48 of the tile's 4225 pixels differ from the heightmap,
   all of them on that one line.
7. `empty_tile_offset={ 225 39 }` → level 4 (`= max_compress_level`), `px=5`,
   bottom-up `(1125, 4056)` = top-down rows 0..4, columns 1125..1129.  All 25
   values are `0`, and **14314 of vanilla's 41472 tiles** (34.5%) point at that
   one 5×5 block.  Deduplication is not optional for a real map.

## 8. What the encoder does, and why

`write_packed(heightmap, out_dir, *, tile_size=33, max_compress_level=4, should_wrap_x=False)`.

* **Input contract.** Top-down 2-D `uint16`, exactly as `heightmap.png` stores
  it.  Both dimensions must be a multiple of `tile_size - 1`; otherwise
  **`ValueError`** — CK3 derives the grid by integer division, so a non-multiple
  would silently drop the last strip of the map.  Pad the heightmap instead
  (that is the `map-physical` lane's ocean padding).  `tile_size - 1` must also
  be a multiple of `2**max_compress_level`, or the top level's tile is not a
  clean grid.
* **Edge pixel.** Clamp in y always, wrap in x only when `should_wrap_x`
  (§3).
* **Level choice.** §5, threshold `LEVEL_MAX_ERROR = 655`.  Not level-0
  everywhere: an all-level-0 atlas for 6144×5120 is 25.37 MB versus 8.87 MB with
  compression (§9), and vanilla's own shipped atlas is 16.83 MB, so all-level-0
  would be the odd one out.  Set `max_compress_level=0` for a bit-exact,
  larger atlas if a future map needs it — the round-trip is then exactly 0
  (`verified`, §9).
* **Edges.** §4, implemented exactly (`floor(x+0.5)`, coarser neighbour wins).
  We deliberately reproduce vanilla's *lossy* edge instead of storing raw
  values: raw edges would round-trip better but would crack the terrain mesh in
  game, which is the whole reason the rule exists.
* **Dedupe.** Tiles are keyed on their decimated bytes per level, so identical
  ocean tiles collapse to one atlas slot.  On Godherja we emit 24995 distinct
  tiles where the editor emitted 30399 (`verified`) — we dedupe slightly harder.
* **`empty_tile_offset`.** The most-referenced *uniform* tile at
  `max_compress_level`; falls back to the most-referenced tile of that level if
  no uniform one exists, and to `{ 0 0 }` if that level is empty.  All three
  shipped maps point at an all-zero top-level tile, which this rule reproduces.
  What the game *does* with the value is `assumed` (an early-out for empty
  tiles); getting it wrong should at worst cost performance.
* **Atlas layout.** One block per level, level 0 at the bottom, each block laid
  out row-major in `floor(atlas_width / px)` columns; `atlas_width` starts
  square-ish for the total occupied area and doubles until no level needs more
  than 256 tile rows.  **The 256 limit is hard**: indirection `R` and `G` are
  single bytes, so no level may exceed 256 × 256 tiles — `ValueError` if it
  does.  We do *not* copy vanilla's trick of dropping the next level into a
  short last row; the layout is ours, and the game only ever reads
  `level_offsets` + `(r, g)`, which the occupancy test in §3 shows is enough.
* **Streaming.** Tiles are built one grid row at a time: 41472 tiles of 65×65
  as float64 is 1.4 GB, and a vanilla-sized heightmap has exactly that many.
* **Self-check.** `write_packed` decodes what it just wrote and returns
  `max_abs_error`, `mean_abs_error`, `exact_fraction` alongside the descriptor
  fields, so a caller never has to trust the encoder.

## 9. Output size for a 6144×5120 heightmap

`--size-report 6144x5120`, fractal-noise land with a third ocean, `tile_size=33`
(`verified`):

| | packed png | indirection png | levels (L0..L4) | distinct tiles | round-trip |
|---|---|---|---|---|---|
| `max_compress_level=4` | **8.87 MB** (2660×2725) | 27.9 kB (grid 192×160) | 2525 13939 3488 436 10332 | 20545 | max 807, mean 28.2, 53.9% exact |
| `max_compress_level=0` | 25.37 MB (4731×4752) | 1.0 kB | 30720 0 0 0 0 | 20545 | **max 0, exact 100%** |

Raw 16-bit `heightmap.png` for that size is 62.91 MB.  8.87 MB sits inside the
range the shipped maps use (7.7–16.8 MB), so the default settings are safe;
all-level-0 at 25 MB exceeds vanilla's 16.8 MB but is lossless and still opens.

## 10. Still `assumed`

| claim | experiment that would settle it |
|---|---|
| the game cannot boot without the packed pair | rename `packed_heightmap.png` in a test mod and launch |
| `LEVEL_MAX_ERROR` is exactly 655 (1% of range) | read `Heightmap.LoadMaxError`'s default from a debug console |
| `should_wrap_x=yes` wraps the outer tile column | find or build a wrapping map; none of the three wraps |
| `level_offsets[].x` is added to the tile x | a map whose packer chose a non-zero x offset; all 15 entries are 0 |
| indirection `B = 2**level` is the shader's scale | shader source; it is redundant with `A` in every pixel we have |
| vanilla's pair was packed from a different source than its shipped `heightmap.png` | compare against an older/newer patch's `heightmap.png` |
| `empty_tile_offset` is only a rendering early-out | point it at a non-empty tile and look for artefacts |
