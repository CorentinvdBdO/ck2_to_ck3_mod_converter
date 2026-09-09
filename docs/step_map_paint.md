# Step `map`, terrain-paint half: CK2 `terrain.bmp` → CK3 runtime paint

**Question this answers.** `docs/map_fidelity.md` §1.3/§4.1 found that the
generated mod ships no `gfx/map/terrain` at all, so CK3 samples vanilla's own
115-material paint in UV space across our canvas — Faerûn wears Europe's
terrain textures, and that is the single biggest visual defect the map has.
This step (lane `map-paint-seeds`, Goal B) writes the pair CK3's renderer
actually reads.

**Answer.** `ck2ck3.map.terrain_paint` reuses the CK2-terrain-category code
grid `ck2ck3.map.terrain` already builds for `common/province_terrain`, maps
each pixel's CK2 category to a CK3 terrain key, looks up a (primary,
secondary) vanilla material pair per key from `mappings/terrain_paint.csv`,
resolves those ids to declaration-order ordinals against the vanilla
`materials.settings`, and blends the two with a Gaussian-noise field so CK2's
hard palette edges do not read as pixel art.

| quantity | value (Faerûn) | label |
|---|---|---|
| `detail_index.tga` / `detail_intensity.tga` size | 8320×6784, matches `provinces.png` | `verified` |
| pixel format | RGBA8, uncompressed (TGA image type 2), origin bottom-left | `verified` against the vanilla game folder |
| vanilla materials declared | 115 | `verified` |
| CK3 terrain keys (`common/terrain_types`) | 17 | `verified` |
| keys `mappings/terrain_paint.csv` covers | 17 of 17 | `verified` |
| CK3 terrain classes actually painted on Faerûn | 11 of 17 | `verified` (no `sea`, `coastal_sea`, `oasis`, `terraced_hills`, `desert_mountains` pixels) |
| `missing_material` / `missing_ordinal` on the reference run | 0 / 0 | `verified` |
| file size, each layer | ~226 MB (56.4 Mpx × 4 bytes) | `verified` |
| added runtime, `map` step | ~5 s of the step's ~60 s | `verified` (see §5) |
| two runs → byte-identical TGA pair | yes | `verified`, sha256 match |

Reproduce: `uv run ck2ck3 --config configs/faerun.toml --steps map` (writes
into `[output] mod_dir`), then `uv run python
scripts/render_map_paint_evidence.py` for the before/after crop and the seed
table (`docs/evidence/map_paint/`).

---

## 1. Why `detail_index`/`detail_intensity`, not the 120 mask PNGs

`gfx/map/terrain/materials.settings` looks like the format to write for:
each of its 115 materials names a mask PNG. It is not read at runtime.
`docs/map_fidelity.md` §1.3 verified two things against the vanilla game
folder: the renderer reads `detail_index.tga` (four material ordinals per
pixel, in `materials.settings` **declaration order**) and
`detail_intensity.tga` (their blend weights, summing to exactly 255,
`detail_data.settings: "materials_limit": 4`); and the shipped masks are
*stale* relative to that bake — 49.1% of sampled non-zero-intensity channels
name a material whose own mask is 0 there. So the masks are map-editor input,
not a second copy of the same data, and a converter that writes the TGA pair
directly needs no editor pass, the same conclusion `packed_heightmap` reached
for elevation.

## 2. Pipeline

`ck2ck3.map.terrain_paint.build_layers`, called from `ck2ck3.map.build.run`
right after the flat (paper) map, reusing the terrain-category code grid
`_resize_codes` already built for the majority-terrain vote (no second
resize):

1. **class map.** CK2 terrain category → CK3 terrain key, via
   `ck2ck3.map.terrain.CK2_TO_CK3_TERRAIN` (or `[map.terrain.map]`, the same
   table `common/province_terrain` uses — paint and gameplay terrain never
   disagree). A pixel with no CK2 category (code 0: padding ocean, or a
   colour `terrain.txt` never declared) falls back to `[map.terrain] default`
   (`plains`), same as the majority vote's own fallback.
2. **material choice.** CK3 terrain key → (primary, secondary) vanilla
   material id, from `mappings/terrain_paint.csv`. All 17 rows name existing
   vanilla materials (`verified` against `materials.settings`), so no new
   `.dds` is authored and the colour/tiling match vanilla by construction.
   A key with no row, or a material id the vanilla install this run read does
   not have, falls back to the default key's pair and is logged as a warning
   (`missing_material` / `missing_ordinal` in the run report) — never
   invented silently.
3. **edge treatment.** A Gaussian-filtered (`σ = 1.5 px`) standard-normal
   noise field, seeded (`seed=11`, deterministic), sets the primary/secondary
   blend weight per pixel (clipped to 30–98%, quantised to `[map]
   terrain_paint_quantize` steps, 16 by default). The field ignores class
   boundaries on purpose — it is texture-space dithering, not a class-aware
   blend; erosion-style edges (dilate the higher-priority class along the
   height gradient) are future work, not required (`docs/map_fidelity.md`
   §4.1 calls this "a refinement, not a requirement"). Evidence:
   `docs/evidence/map_paint/sword_coast_zoom_before_after.png` — hard CK2
   edges on the left half, the actual shipped blend on the right.
4. **write.** Channel 0/1 of `detail_index` = primary/secondary ordinal,
   2/3 = 0 (unused, `materials_limit = 4` but this converter never uses more
   than two). Channel 0/1 of `detail_intensity` = the blend weight and its
   complement; an assertion in `build_layers` enforces the sum-to-255
   contract on every pixel before the file is written.

## 3. Format decisions, and what still needs a game test

* **Same size as `provinces.png`, not smaller.** `docs/map_fidelity.md` §4.1
  flagged "whether the pair may be smaller" as an open, game-test-only
  question (the shader samples in UV space, so a half-resolution pair would
  quarter the cost). This step ships the conservative, vanilla-matching
  choice — full canvas resolution — and leaves the smaller-pair experiment
  for later.
* **Uncompressed TGA, not RLE.** `docs/map_fidelity.md` §4.1 also flagged
  "whether CK3 accepts RLE" as untested. Reading the vanilla files directly
  settles it without a game test: both are TGA **image type 2**
  (uncompressed truecolour), not type 10 (RLE) — `xxd` on
  `gfx/map/terrain/detail_index.tga` byte 2 is `0x02`, and the file size
  (169,869,356 bytes) is exactly `9216×4608×4 + 44` (header + footer, no
  compression saving). `terrain_paint.save_tga` writes the same type, so this
  step mirrors vanilla's own format exactly rather than guessing at
  compatibility. Cost: ~226 MB per layer, ~452 MB for the pair, on top of a
  mod that was 143 MB before this lane — `[map] terrain_paint = false` (or
  `skip_images = true`) opts out.
* **Origin bottom-left**, matching vanilla's descriptor byte (`0x08`) exactly.
  `verified` by round-tripping a synthetic RGBA array through
  `Image.fromarray(...).save(path, "TGA")` and back: PIL handles the
  bottom-up row order and BGRA channel swap internally, so this module's
  arrays are ordinary top-down numpy (row 0 = the top of the image, same
  convention as `provinces.png`) and need no manual flip.
* **What was not tested in game**: whether the game actually renders these
  files correctly (only ck3-tiger and format-level checks ran here — no
  `fatal`, no error class this lane's files could plausibly cause, and no
  `detail_index`/`detail_intensity`/`materials.settings` mention anywhere in
  the tiger report at all, `docs/evidence/tiger_map_paint_seeds.txt`), and
  whether ~452 MB extra mod size is acceptable — both are the coordinator's
  calls per `docs/map_fidelity.md` §4.4.

## 4. `mappings/terrain_paint.csv`

`ck3_terrain,primary_material,secondary_material,note` — one row per CK3
terrain key in `common/terrain_types/00_terrains.txt` (17). Seeded from
`scripts/prototype_terrain_masks.py`'s hand-picked table (lane
`map-fidelity`), every id `verified` against the vanilla `materials.settings`
this repo's CK3 install ships. `taiga` carries a note: CK2's `arctic` and
`glacier` categories both fold to `taiga` in `CK2_TO_CK3_TERRAIN` (CK3 has
neither), so `snow` as the secondary material is what reads coldest without
inventing a new class. `terraced_hills` similarly notes there is no
"terraced" vanilla material; `hills_01_rocks_medi` is the nearest visual
match. A CK3 terrain key never used by Faerûn (`sea`, `coastal_sea`, `oasis`,
`terraced_hills`, `desert_mountains`) still gets a row — the table is keyed by
the CK3 vocabulary, not by what one mod happens to paint, so it needs no edit
for the next total conversion.

## 5. Config keys

All under `[map]` in `configs/faerun.toml`:

| key | default | meaning |
|---|---|---|
| `terrain_paint` | `true` | write the pair at all. `false` (or `[map] skip_images = true`) ships neither file, same as before this lane |
| `terrain_paint_csv` | `mappings/terrain_paint.csv` | the material table |
| `terrain_paint_quantize` | `16` | `detail_intensity.tga` blend-weight quantisation step; `1` = no quantisation. Only matters if a future pass adds compression — this step always writes uncompressed TGA (§3) |

## 6. Runtime cost

Reusing the code grid already built for `common/province_terrain` avoids a
second resize of a 56 Mpx array. On the reference machine the terrain-paint
pass (LUT indexing, one Gaussian filter over 56 Mpx, two TGA writes at ~226 MB
each) adds roughly 5 s to the `map` step's ~60 s total — most of that is disk
I/O for the ~452 MB written, not compute. `skip_images = true` skips it
entirely, same as the other three PNGs.

## 7. What lane `map-fidelity` handed off, and what is still open

Taken from `docs/map_fidelity.md` §4.1/§4.4, in scope for this lane:
class map, material choice, edge treatment (noise blend), the format
decisions in §3 above. **Not** in scope (see `docs/evidence/HANDOFF_map_paint_seeds.md`
for the full list): ridged/eroded structure instead of isotropic noise
(a look call, `docs/map_fidelity.md` calls it **L** effort), the heightmap
detail pass (§4.2, a different lane), tree scatter and the `colormap.dds`
resample (§4.3), and the locator/asset placement half of Goal A's sibling
work (`docs/evidence/HANDOFF_map_fidelity.md`, lane `map-ui`).

## 8. Size (lane `paint-size`)

**Question.** GitHub refuses files over 100 MB; the ~226 MB-per-layer TGA
pair from §5/§6 forces the generated mod repo to gitignore both files, so a
clone ships no terrain paint at all. Is there a format under 100 MB/file, or
is none possible?

**Answer: yes, but only at half resolution.** `[map] terrain_paint_scale =
0.5` is *required* — RLE alone does not get the full-resolution pair under
the limit (§8.3). `[map] terrain_paint_format = "tga_rle"` at
`terrain_paint_scale = 0.5` is the recommendation (§8.4); defaults are
unchanged (`"tga"`, `1.0`) pending the coordinator's in-game check.

### 8.1 Does CK3 1.19 accept RLE TGA for this pair?

**Yes, `verified`** — not by a game test (none run in this session, see §8.5),
but by reading two other things:

* **Two installed, published, currently-loadable workshop total conversions
  ship RLE.** Elder Kings 2 (`workshop/content/1158310/2887120253`) and
  Godherja (`.../2326030123`) both ship
  `gfx/map/terrain/detail_index.tga`/`detail_intensity.tga` as TGA **image
  type 10** (RLE) — byte offset 2 is `0x0a` in all four files (`xxd -l 20`,
  `verified`) — at **exactly their own `provinces.png` resolution** (EK2
  8256×5504, Godherja 8192×4096, both `verified` from the PNG IHDR and the
  TGA width/height header fields). Princes of Darkness (`2216659254`) ships
  neither file — it relies on vanilla's own terrain paint, a third data point
  (not every TC overrides this pair). Neither EK2 nor Godherja ships
  half-resolution paint.
* **PIL reads both back correctly** (`Image.open(...).convert("RGBA")` on
  Godherja's `detail_intensity.tga` decodes to a 4096×8192×4 array with the
  expected value ranges per channel, `verified`) — RLE TGA decoding is not
  exotic, standard library support round-trips it.
* This settles the open question §3 above already flagged as untested:
  `terrain_paint.save_tga(..., rle=True)` now writes RLE via PIL's own
  `rle=True` (`verified` to produce the same image-type byte as the two
  shipped mods, `test_save_tga_rle_writes_image_type_10`).

### 8.2 Is DDS viable for these two specific files?

**Unverified, and the evidence leans no.** `strings` on `ck3.exe` finds the
literal names `detail_index.tga` / `detail_intensity.tga` exactly **twice**
in the whole binary, both together, both followed immediately by a bare
`.tga` string, all three from one object file:
`C:\...\jomini\modules\map_editor\source\mapeditor_detail_data.cpp` (the map
editor's own `ProcessMasks` mask-bake step). There is no second occurrence
anywhere else in the binary, and no generic-extension search near it (unlike
the *mask* PNGs, which do have one — `"Failed to load mask texture file: %s
with any of the following formats (png,bmp,tga)."`, a different code path,
`verified` same `strings` dump). One editor-time constant is weak evidence
that the runtime loader uses the same hardcoded filename, but a single
occurrence total, with a literal `.tga` extension right next to it, is the
strongest signal this repo can get without a game test — `detail_index.dds`
may simply never be looked for. Implemented anyway, per spec (§8.4/§8.6), and
it carries no compression benefit even if it did load (§8.3): uncompressed
BGRA8 has the same byte count as plain TGA.

### 8.3 Measured sizes, every format × scale (Faerûn, real run)

`uv run scripts/paint_variants.py <out dir>` on the reference `map`-step
output (`docs/evidence/paint_variants.csv`, `verified`, real 8320×6784 data,
not extrapolated from a tile like §4.1's own sizing table):

| variant | format | scale | size (px) | `detail_index` | `detail_intensity` | total | under 100 MB/file? |
|---|---|---|---|---|---|---|---|
| `tga_full` | `tga` | 1.0 | 8320×6784 | 225.77 MB | 225.77 MB | 451.54 MB | no, no |
| `tga_rle_full` | `tga_rle` | 1.0 | 8320×6784 | **5.57 MB** | 172.55 MB | 178.12 MB | yes, **no** |
| `dds_full` | `dds` | 1.0 | 8320×6784 | 225.77 MB | 225.77 MB | 451.54 MB | no, no |
| `tga_0p5` | `tga` | 0.5 | 4160×3392 | 56.44 MB | 56.44 MB | 112.89 MB | **yes, yes** |
| `tga_rle_0p5` | `tga_rle` | 0.5 | 4160×3392 | **2.33 MB** | **54.55 MB** | **56.88 MB** | **yes, yes** |
| `dds_0p5` | `dds` | 0.5 | 4160×3392 | 56.44 MB | 56.44 MB | 112.89 MB | **yes, yes** |

**Why RLE alone is not enough.** `detail_index`'s ordinals are large flat
runs (one CK2 terrain category covers thousands of contiguous pixels), so RLE
crushes it 40x. `detail_intensity`'s blend weight is the noise-dithered field
from §2 step 3 — a *different* pseudo-random value on nearly every pixel by
design (that is what breaks up CK2's hard palette edges) — so consecutive
bytes rarely repeat and RLE barely helps it (225.77 → 172.55 MB, 24%). This
matches `docs/map_fidelity.md` §4.1's own extrapolated estimate (173 MB at 16
quantisation steps) almost exactly, so that prototype-tile projection holds
up against the real full-canvas run. **No format change alone clears the
100 MB cap for `detail_intensity` at full resolution** — the noise field is
the cost, not the container.

**Why 0.5 clears it comfortably.** Downsampling quarters the pixel count, so
even the *uncompressed* 0.5-scale files (56.44 MB) are under the limit with
room to spare, and RLE on top shrinks the intensity layer further (54.55 MB)
because a box-filtered half-resolution field is smoother — less pixel-to-
pixel noise survives the averaging in `downsample_intensity` — than the
full-resolution one.

### 8.4 Recommendation

**`[map] terrain_paint_format = "tga_rle"`, `[map] terrain_paint_scale =
0.5`.** Reasoning:

1. **Scale is not optional.** Every full-resolution candidate fails the
   100 MB/file cap (§8.3); only `terrain_paint_scale = 0.5` gets under it at
   all, regardless of format.
2. **RLE is the `verified`-safest format at that scale** (§8.1) — real,
   loadable, published mods use exactly this container. Plain `tga` at 0.5 is
   the fallback if RLE somehow does not load in game: still comfortably under
   the cap (56.44 MB/file) and bit-for-bit vanilla's own image type.
3. **`dds` is not recommended**: no compression benefit (§8.3) and the
   weakest load-viability evidence of the three (§8.2).

### 8.5 What the coordinator must check in game

Nothing here was checked against a running CK3 — this lane's own reading of
`ck3.exe` strings and two shipped mods' file headers settles §8.1/§8.2 as far
as static analysis can, but only a game load answers:

* Does `terrain_paint_format = "tga_rle"` actually render (expected: yes,
  §8.1)?
* Does `terrain_paint_scale = 0.5` (a pair *smaller* than `provinces.png`,
  which no installed shipped mod does) still align and render correctly —
  the renderer samples in UV space, so this should just resample, but no
  installed mod tests the smaller-than-province-map case?
* Does `terrain_paint_format = "dds"` load at all, at either scale (expected:
  no, §8.2)?

`scripts/paint_variants.py`/`.sh` build all six combinations as probe mods
under `<out>/../paint_variants/<variant>/` for
`claudespace/scripts/ck3_soak.sh <mod> --extra <dir>` (§8.6).

### 8.6 `scripts/paint_variants.py` / `.sh`

Re-encodes an already-built `detail_index`/`detail_intensity` pair (any
format the run used) into every format × scale combination, without a second
converter run: `load_paint` decodes the master pair once, then for each
variant `downsample_index`/`downsample_intensity` (only if `scale != 1.0`)
and `save_paint` write
`<out>/../paint_variants/<variant>/gfx/map/terrain/detail_index.<ext>` (and
`detail_intensity`) plus a `descriptor.mod`
(`replace_path="gfx/map/terrain"`, no `path=` line — `ck3_soak.sh --extra`
adds that itself). Also writes `docs/evidence/paint_variants.csv` (§8.3's
table, machine-readable). Usage:

```
uv run scripts/paint_variants.py /home/cvdbdo/git/paradox/ck3/wt/_out/paint-size
claudespace/scripts/ck3_soak.sh faerun_ck2_to_ck3_converted \
  --extra /home/cvdbdo/git/paradox/ck3/wt/_out/paint_variants/tga_rle_0p5
```

### 8.7 New `[map]` keys (`configs/faerun.toml`)

| key | default | meaning |
|---|---|---|
| `terrain_paint_format` | `"tga"` | `"tga"` (vanilla's own, uncompressed) / `"tga_rle"` (RLE, `verified` §8.1) / `"dds"` (uncompressed BGRA8, unverified §8.2). Unchanged until the coordinator's in-game check (§8.5) picks one. |
| `terrain_paint_scale` | `1.0` | `1.0` matches `provinces.png` (vanilla's choice); `0.5` halves both dimensions (nearest-neighbour for `detail_index`, box-filter for `detail_intensity` — `ck2ck3.map.terrain_paint.downsample_index`/`downsample_intensity`). Required for any format to clear the 100 MB/file cap (§8.3). |

`ck2ck3.map.terrain_paint.save_paint`/`load_paint`/`paint_ext` dispatch on
`terrain_paint_format`; every writer round-trips through its own reader
(`tests/test_map_terrain_paint.py`, RLE and DDS both, plus the downsample
functions). ck3-tiger has nothing to check here — §6/§7 already established
it raises nothing about this pair (opaque binary files to it either way);
this lane did not re-run it.

### 8.6 In-game check (coordinator, 2026-09-09)

- `verified` Probe `tga_rle_0p5` loaded after the mod (`Paint variant: tga_rle_0p5 ... Enabled` in
  debug.log): the game reached In Game and stayed alive 100 s, zero `detail_index`/`detail_intensity`/
  texture errors in error.log. The first probe run was invalid (its descriptor `replace_path`-ed
  `gfx/map/terrain`, deleting vanilla materials); fixed in `scripts/paint_variants.py`.
- `assumed` Visual quality of half-resolution paint at close zoom. The headless `-test` run sits on the
  character-selection map (political flat map, `claudespace` screenshot), which does not show the paint;
  the player's playtest is the visual check.
- Decision: defaults are now `terrain_paint_format = "tga_rle"`, `terrain_paint_scale = 0.5` (2.3 MB +
  53 MB); the generated mod repo tracks the pair again.

---

## 9. Lane `map-colour`: colormap, trees, the material art pass, and evidence

**Question this answers.** `docs/map_fidelity.md` §4.3/§4.4 flagged three more
things behind "we ship no terrain paint at all": `colormap.dds` (a straight
CK2 asset resample), tree scatter (CK2 `trees.bmp` -> CK3 placed instances),
and an art review of `mappings/terrain_paint.csv`'s two flagged judgement
calls. This lane (`map-colour`) does all three, plus the evidence the
coordinator needs to check them without launching the game itself.

### 9.1 `gfx/map/terrain/colormap.dds`

**Format decision, `verified` against real file headers, not vanilla's own
bake.** Vanilla 1.19 ships `colormap.dds` at full province resolution
(9216x4608), DXT5, 14 mips, 56.6 MB (`xxd`: fourCC `DXT5`,
`dwPitchOrLinearSize = 42,467,328 = 9216*4608`). But two shipped, currently
loadable CK3 total conversions — Elder Kings 2 and Godherja — both ship
`colormap.dds` **uncompressed 32-bit BGRA (A8R8G8B8), at exactly one-quarter
of their own province-map resolution** (EK2 2064x1376 of 8256x5504; Godherja
2048x1024 of 8192x4096; alpha = 255 everywhere, sampled). This lane follows
the two real conversions: `ck2ck3.map.colormap` resamples the CK2 mod's own
`map/terrain/colormap.dds` (pixel-aligned with `provinces.bmp`, `verified`
both 4096x3328 for Faerûn) onto the canvas with the exact crop/scale/offset
`ck2ck3.map.config.plan_canvas` already computed for the province raster,
downsamples to `[map] colormap_scale` (default `0.25`), and writes an
uncompressed BGRA8 DDS byte-for-byte matching the two reference mods'
`ddspf`/`caps` fields. Faerûn's real run: 2080x1696 with a full mip chain,
18.8 MB. Config: `[map] colormap` (default `true`), `colormap_scale` (`0.25`),
`colormap_mips` (`true`). Tests: `tests/test_map_colormap.py` (geometry on a
synthetic image, header bytes against both reference mods, DDS round-trip via
PIL).

`gfx/map/terrain/output_final_colormap.dds` is vanilla's own bake-tool output
and ships **0 bytes** in the real game folder (`verified`); nothing reads it
at runtime and this lane does not write one either.

### 9.2 Trees

`ck2ck3.map.tree_scatter` scatters instances into the 18 vanilla
`gfx/map/map_object_data/generated/*.txt` files the `map-ui` lane emptied
(their coordinates belonged to Europe's canvas). Density: vanilla 1.19 places
549,126 instances over its own 9216x4608 canvas (`verified`,
`scripts/verify_tree_density.py` sums every `count=` in the real files) —
0.012931 instances/px, ~729,900 for our 8320x6784 canvas. Eligibility: any
nonzero CK2 `trees.bmp` pixel (upsampled 8x to province-bitmap resolution,
then resampled onto the canvas the same way the province raster is), minus
water and impassable. Mesh choice: the pixel's own CK3 terrain classification
(the majority-vote result `build.py` already computes) via a new table
`mappings/tree_meshes.csv`, not the CK2 palette colour — §1.4 found no
confirmed index->species mapping, so this is the more grounded signal, and it
means an unpainted terrain class simply gets no trees. Format
`verified` against `gfx/map/map_object_data/generated/tree_pine_01_a_generator_1.txt`
directly: `object={ name= layer= pdxmesh= count=N transform="x y z qx qy qz
qw sx sy sz\n..." }`, scale always `1 1 1`, reusing
`ck2ck3.map.locators.world_position`/`yaw_quaternion` unchanged for the frame.
Faerûn's real run: 711,875 of 729,838 target instances placed (97.5%),
17,963 dropped (desert/mountains/farmlands — no mesh row, by design: bare
sand, above the treeline, cultivated land). Per-file sizes: 66 MB total
across 18 files (vanilla's own is ~52 MB per `docs/map_fidelity.md` §1.6).
Config: `[map] trees` (default `true`), `trees_csv`, `trees_seed` (`4242`,
deterministic), `trees_density_per_px`. Tests:
`tests/test_map_tree_scatter.py` (forest-mask/upsample geometry, scatter
determinism, water/mesh exclusion, `mappings/tree_meshes.csv` completeness
against every `common/terrain_types` key).

### 9.3 `mappings/terrain_paint.csv` art pass

`scripts/verify_terrain_paint_materials.py` reads vanilla's own
`detail_index.tga` primary channel, cross-referenced with
`common/province_terrain` + `map_data/provinces.png`, to find what material
vanilla itself paints for each CK3 terrain key — excluding the `gen_*`/
`central_*` climate-zone material families (dozens of Earth-geography-specific
variants like `gen_tropical_hills`/`gen_steppe_mountain` with no Faerûn
equivalent, which otherwise dilute the vote into meaningless fragments).
**Found one real bug and two genuine improvements, changed 3 of 17 rows:**

* **`forest` was painted with `forest_pine_01`, byte-identical to `taiga`'s
  own primary** — a copy-paste that gave broadleaf forest a conifer texture.
  Vanilla's own non-regional top pick for `forest` is `forest_leaf_01`
  (75.5% share, strongly dominant); `taiga`'s own top pick is `forest_pine_01`
  (78.4%, confirming that one was already right). Changed `forest`'s primary
  to `forest_leaf_01`. This is exactly the "same class of mistake" this lane
  was asked to check every row for, and it was the only instance found.
* **`terraced_hills`** (a flagged judgement call): vanilla's own top pick is
  `farm_paddy_01` at 56.5% share — overwhelmingly dominant, and thematically
  exact (rice-paddy terracing). Changed primary from `hills_01_rocks_medi` to
  `farm_paddy_01`, demoting the old primary to secondary.
* **`desert_mountains`**: vanilla's former primary `mountain_02_desert_c`
  does not appear in vanilla's own top 3 for this key at all; the real top is
  `desert_rocky` (36.9%, near-tied with `hills_01_rocks_medi` at 33.5%).
  Swapped primary/secondary so the material vanilla itself favours leads.
* **`taiga`**'s flagged secondary (`snow`) is kept: vanilla's own real
  secondary there is `forestfloor` (5.9%), not snow, but Faerûn's CK2
  arctic/glacier categories also fold into `taiga` with no vanilla CK3
  equivalent of their own (`ck2ck3.map.terrain`), so `snow` is a deliberate
  style choice for that broader, colder bucket — the note now says so
  explicitly instead of asserting it unverified.
* Every other row's note now records what vanilla itself paints there and why
  it was kept or not (`mappings/terrain_paint.csv`, one note per row).
  Several rows (`plains`, `oasis`, `wetlands`, `steppe`) show a vanilla "top
  pick" driven by real-world geography that does not generalise to Faerûn
  (steppe/mountain overlap in Central Asia, farmland regional variants named
  for India, etc.) and were deliberately kept as-is.

### 9.4 Evidence: `docs/evidence/map_colour/`

`scripts/render_map_colour_evidence.py` composites province outlines (edge
detection on `map_data/provinces.png`) + the resampled `colormap.dds` +
a hillshade of `map_data/heightmap.png`, entirely in Python (no game engine),
for three regions in canvas pixels (8320x6784, top-down y):

| region | box (x, y, w, h) | how found |
|---|---|---|
| Sword Coast (Waterdeep-Baldur's Gate) | 2080, 940, 2048, 2048 | reused from `scripts/render_map_paint_evidence.py` (lane `map-paint-seeds`) |
| Anauroch | 2297, 43, 2048, 2048 | centroid of the largest connected "desert"-terrain blob in the *north* half of the canvas (`scipy.ndimage.label`; several disconnected deserts exist, the northern one matches Anauroch's lore geography) |
| Spine of the World | 1405, 0, 2048, 1024 | the exact province named "Spine of the World" in `docs/evidence/province_id_map.csv` (CK3 id 4056, rgb (161,200,228)), a far-north `impassable_mountains` range |

Each PNG is quantised and resized to stay under 400 KB (`verified`: 328/328/138 KiB).
These are **not** a substitute for an in-game look — no game shader, lighting
or material texture is involved, only the converter's own raster outputs
composited for a sanity check.

### 9.5 What the coordinator should look at in game, and how

The headless `-test` harness reaches `Setting idler 'In Game'`
(`CLAUDE.md` invariant, 54 s vanilla control) but **no input is possible**
(Xwayland aborts on XTEST), so the run otherwise sits wherever the camera
starts. `NCamera.START_LOOK_AT` / `START_ZOOM_STEP` **are real defines**
(`verified`, `game/common/defines/graphic/00_graphics.txt:172-175`), in the
same bottom-up pixel frame as the locators; the `map` step already writes
`START_LOOK_AT` to the bare canvas centre
(`ck2ck3.map.bootstrap.render_camera_defines`, lane `map-ui`), which is not
any of the three regions above.

`scripts/camera_probe.py` writes a tiny probe mod that overrides just
`START_LOOK_AT`/`START_ZOOM_STEP`, loaded *after* the converted mod so its
`NCamera` block's individual keys win (the same "small override file, no
`replace_path`" pattern §8.6 already uses for the paint-format probes):

```
uv run scripts/camera_probe.py <out_dir> <probe_dir> --place waterdeep --zoom 15
claudespace/scripts/ck3_soak.sh <mod-name> --extra <probe_dir> --secs 60
```

which writes `<probe_dir>/common/defines/graphic/zzz_camera_probe_graphics.txt`:

```
NCamera = {
	START_LOOK_AT = { 2351.8 0 5706.6 }
	START_ZOOM_STEP = 15
}
```

(2351.8/5706.6 is Waterdeep's own province centroid, run's canvas; `--place
anauroch` / `--place spine` / `--x .. --y ..` pick a different point; `--zoom`
0 is closest, 34 is furthest, vanilla's own start is 33).

**Not tested in game from this lane** — the hard rule is the coordinator runs
every in-game check, and this repo's own headless soak cannot supply input to
confirm a camera actually moved. What to look at once it does: with the
`ck3_soak.sh` screenshot at `In Game`, the terrain visible around Waterdeep
should show the green/tan colour wash and dithered material blend this
document's §2-§8 describe, not vanilla's flat Europe texture; compare against
`docs/evidence/map_colour/sword_coast.png` for the broad colour/relief
pattern (not a pixel match — that PNG has no game shader in it). If the
define does *not* visibly move the camera (e.g. the frontend/bookmark-select
screen ignores it and only the post-`-test` 3D view honours it), that is
itself useful evidence for `docs/evidence/HANDOFF_map_colour.md` and the next
lane, not a dead end — the fallback stays the user's own playtest.

### 9.6 The CK2 colormap is the wrong kind of texture (coordinator, 2026-09-09 23:40)

In-game check with the camera probe over Waterdeep (`START_ZOOM_STEP = 4`,
`REALM_COLOR_MAP_START_ZOOM_STEP = 0`, screenshot in the session evidence):
terrain paint and trees **render correctly**, but the ground was washed pale
blue-white and the ocean brown.

Cause, `verified` by sampling both files:

| file | over ocean | over land | character |
|---|---|---|---|
| vanilla CK3 `colormap.dds` (9216×4608 DXT5) | 131,129,131 | 148,125,106 (France) | near-neutral **tint**, multiplied over the terrain materials |
| our resample of CK2 `map/terrain/colormap.dds` (4096×3328 DXT1) | 116,142,74 | same green | saturated **satellite image**, no sea/land distinction |

CK2's colormap is a painted land texture that covers the sea too (CK2 draws
water over it), and its content is CK2's own artistic map, not our province
geometry: its arctic patch landed on Waterdeep. Multiplying it over CK3's
terrain materials is wrong twice over — wrong saturation and wrong content.

`[map] colormap` is **false** until the next lane replaces the resample with a
tint derived from our own terrain classes, calibrated against vanilla's own
per-material colormap means (vanilla `detail_index.tga` gives the material per
pixel and `colormap.dds` the tint at the same pixel, so the calibration is a
measurement, not a guess).
