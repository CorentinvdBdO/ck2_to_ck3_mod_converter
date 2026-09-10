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

## 1b. Gameplay terrain is NOT this file's business (lane `province-terrain`)

`common/province_terrain` and the paint pair are two different answers to two
different questions, and since lane `province-terrain` they are allowed to
disagree — because in CK2 they already do.

* **Paint** is per **pixel**: each pixel's CK2 terrain category (from
  `terrain.bmp` + `trees.bmp`) picks a material pair. That is what §2 below
  describes and it is unchanged.
* **Gameplay terrain** is per **province**, and its first source is the CK2
  `history/provinces` `terrain = X` line, not the bitmap — CK2's own rule, see
  `docs/step_map_terrain.md`. 1040 of Faerûn's 2125 province files carry that
  line; the override moved 946 CK3 provinces.

So the sentence in §2 step 1 — "paint and gameplay terrain never disagree" —
is now true only of the *table* (both still resolve a CK2 category through
`ck2ck3.map.terrain.CK2_TO_CK3_TERRAIN`), not of the *result*. **946 provinces
are painted one class and played as another**, most of them painted plains and
played farmlands/forest. This is faithful to CK2, where the bitmap is the
texture and the history line is the terrain, but it is a visible mismatch
between the ground and the province tooltip.

Zero paint pixels changed, so **figure 5 in `docs/report_map_paint.md` does not
move** — it is read back out of the shipped `detail_index.tga`. What did move,
because it reads the per-province class grid, is the heightmap detail pass and
the tree scatter: 6.61 % of canvas pixels change class
(`docs/step_map_terrain.md` §5).

Open, for whoever owns this file next: repaint an overridden county's pixels to
its override's material pair, so the ground matches the tooltip. That would
also move figure 5 and the colormap, so it is a paint-lane decision, not a
terrain-lane one.

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

### 9.1 `gfx/map/terrain/colormap.dds` (superseded by §9.7)

This lane (`map-colour`) originally shipped a resample of the CK2 mod's own
`map/terrain/colormap.dds` onto the canvas, in the same uncompressed BGRA8
DDS format two reference mods (Elder Kings 2, Godherja) use. **§9.6 found
this wrong**: CK2's colormap is a saturated, geography-specific land painting
with no sea/land distinction of its own, not a neutral tint, and resampling
it put CK2's arctic patch on Waterdeep. `[map] colormap` shipped `false`
until lane `colormap-fix` replaced the resample with a **measured tint**;
see §9.7 for the current approach, config keys and numbers. The DDS format
decision itself (uncompressed BGRA8, quarter province-map resolution,
matching the two reference mods' header fields) is unchanged — only the
pixel content changed.

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
deterministic), `trees_density_per_px`. **Superseded in part by §9.9**: the
mesh choice is now vanilla's own measured
`P(mesh | terrain, climate, latitude band)` (`[map] trees_regional`, default
`true`); the density, eligibility and format decisions in this section are
unchanged. Deterministic across *processes* only since
2026-09-10: the per-mesh yaw salt was `hash(file)`, which Python randomises
per process, so every regeneration rewrote all 711,875 yaws (1.4 M diff lines
in the generated mod); it is `zlib.crc32(file)` now (`tree_scatter.mesh_seed`). Tests:
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

### 9.7 Lane `colormap-fix`: measured tint replaces the resample

**Measurement 1 — vanilla's own per-material tint.**
`scripts/measure_vanilla_colormap_tints.py` pairs every pixel of vanilla's
`gfx/map/terrain/colormap.dds` with the same pixel of `detail_index.tga`
(both `verified` 9216x4608, pixel-aligned) and accumulates mean/stddev RGB
per material ordinal, over land only. Decode method, `verified`: Pillow 12.3
decodes the DXT5 `colormap.dds` to a full per-pixel RGB array natively in
~0.15 s — a **full BC3 decode**, not the 4x4-block colour-endpoint
approximation the lane brief allowed for as a fallback. Water definition,
`verified`: vanilla's own `sea_zones`+`lakes` province ids from
`map_data/default.map`, rasterised via `provinces.png` + `definition.csv` —
not "pixels whose material is a sea material", because vanilla's own
`materials.settings` has no material named for water at all. Output:
`docs/evidence/vanilla_colormap_tints.csv` (102 rows: 101 materials + a
synthetic `water` row). Interesting rows (mean RGB, sample count):

| material | mean RGB | n | note |
|---|---|---|---|
| water (sea_zones+lakes) | 129,130,129 | 8.04M | matches §9.6's own 131,129,131 ocean sample |
| beach_02 | 129,130,129 | 10.55M | coastal transition strip; near-identical to open water |
| plains_01 | 127,127,126 | 13.0K | our own `plains` primary |
| forest_leaf_01 | 128,128,125 | 649K | our own `forest` primary (§9.3's bug fix) |
| desert_rocky | 138,128,115 | 363K | our own `desert_mountains` primary, most saturated common land material |
| desert_wavy_01_larger | 154,138,116 | 406K | the single most saturated material vanilla paints anywhere (R-B=38) |

Every material's mean sits in a tight near-neutral band (R 115-154, G
114-142, B 96-140); nothing approaches CK2's saturated 116,142,74 green.

**Measurement 2 — vanilla's own colour blur scale.**
`scripts/measure_vanilla_colormap_blur.py` finds the single most-interior
land pixel (largest chessboard distance to water, `scipy.ndimage
.distance_transform_cdt`, a 1px false border added first so the canvas edge
cannot itself win the search — `verified` by a hand test that the transform
otherwise treats the array boundary as infinitely far, not as background),
crops a guaranteed-all-land 1024x1024 box around it (landed in west/central
Africa, `chessboard distance 606`), high-passes it (subtract a sigma=32
blur) and finds where its radially-averaged 2D autocorrelation first drops
to 1/e: **9 px**, in vanilla `colormap.dds` pixels
(`docs/evidence/vanilla_colormap_blur.csv`). Used unconverted as our own
canvas-pixel blur sigma because our canvas is built to match vanilla's own
km/px (`docs/map_scale.md`) — the entire point of the scale-factor fit — so
a vanilla pixel and a canvas pixel already cover the same ground distance.
`assumed`: equating an autocorrelation e-folding radius with a Gaussian blur
sigma is exact only for blurred white noise, not vanilla's actual texture,
and one sample region stands in for the whole map.

**Building our own colormap.** `scripts/build_colormap_tints_csv.py` turns
measurement 1 into `mappings/colormap_tints.csv` — CK3 terrain key -> tint
RGB — by looking up each key's **primary** material in the existing
`mappings/terrain_paint.csv` (no second hand-picked table) and taking that
material's measured mean. All 16 rows (15 land keys + `water`) resolved to a
real vanilla sample, no fallback needed. `ck2ck3.map.colormap
.build_from_terrain` paints this straight from `ck2ck3.map.terrain_paint`'s
own per-pixel CK2-code grid (`codes_tgt`/`code_names`, `build.py` — no second
resize), overrides every `water_mask` pixel with the measured water tint,
then blurs with the measured sigma. `build.py` also had to start keeping
`codes_tgt` alive when `[map] colormap` is on and `[map] terrain_paint` is
off (`keep_codes_tgt`), since both passes now share it.

**Bug found and fixed: the `[map] colormap` toggle was dead.**
`src/ck2ck3/steps/map.py::_map_config` — the function that turns
`configs/faerun.toml`'s `[map]` table into a `MapConfig` for the real CLI
pipeline — never read `colormap`/`colormap_scale`/`colormap_mips` at all, so
`configs/faerun.toml`'s `colormap = false` (set by the coordinator after
§9.6) was **silently ignored**: every real run kept using the `MapConfig`
dataclass default (`colormap: bool = True`) and painted the broken CK2
resample regardless of the toml. `ck2ck3.map.config.load` (the
standalone-TOML entry point, `python -m ck2ck3.map.build`) already read it
correctly — only the CLI-facing builder was missing it. `verified` by
toggling `[map] colormap` in `configs/faerun.toml` before and after the fix
and checking whether `gfx/map/terrain/colormap.dds` appeared in a real run's
output: before the fix it appeared regardless of the toml value; after,
`false` correctly skips it (54 files instead of 55) and `true` writes it.
Fixed alongside adding the two new keys (`colormap_tints_csv`,
`colormap_blur_sigma`) so they are not born with the same bug.

**Numbers, real Faerûn run** (`uv run ck2ck3 --config configs/faerun.toml
--out <dir> --steps map`, `scripts/verify_colormap_land_water.py <out
dir>`):

| | land | water | vanilla land (weighted) | vanilla water |
|---|---|---|---|---|
| mean RGB | 126.7, 125.9, 122.5 | 128.8, 129.8, 128.7 | (varies by material) | 129,130,129 |
| stddev RGB | 1.2, 2.0, 3.8 | 0.4, 0.5, 0.7 | up to ~20 per material | 2.8 |
| saturation (max-min) | **4.18** | **1.02** | **6.97** | **0.85** |

Our land saturation (4.18) is comfortably under vanilla's own weighted mean
(6.97) — the blur and Faerûn's own terrain-class mix pull it toward neutral,
never past it — and our water tint (1.02) sits within a point of vanilla's
own (0.85), close enough that the small gap is squarely inside vanilla's
own material-to-material variation. **`[map] colormap` is re-enabled
(`true`)** on this basis. File: 2080x1696, 18.81 MB, unchanged from the old
resample's size (same format/resolution, only the pixel content changed).

**Regression guards** (`tests/test_map_colormap.py`):
`test_our_land_tints_do_not_exceed_vanillas_own_saturation_by_much` fails if
`mappings/colormap_tints.csv`'s land rows exceed vanilla's own weighted mean
saturation by more than 3 (max-min channel units) —
`test_build_from_terrain_water_mask_overrides_terrain_key` checks a
water-masked pixel gets the water tint regardless of its terrain-key colour.
Existing DDS geometry/header/round-trip tests (from the original resample
lane) are kept green.

**ck3-tiger**: `verified` — a real `ck3-tiger` run against a fresh map-only
output (`fatal: 0`, `error: 1320` all `missing-item`/`duplicate-item`/
`rivers`, none mentioning `colormap` or `dds`) found nothing about this file.
Note this is a *stronger* check than the `detail_index.tga`/
`detail_intensity.tga` pair's own precedent (§8.7: "opaque binary files to it
either way"): `ck3-tiger`'s own binary embeds a `tiger_lib::dds` module that
decodes a DDS header via the `image` crate (unlike the TGA pair, which has no
comparable module in the binary at all) — so tiger *can* look inside a DDS
file. It simply produced no diagnostic of any kind about
`gfx/map/terrain/colormap.dds` in this run.

Config: `[map] colormap` (default `true`), `colormap_tints_csv` (default
`mappings/colormap_tints.csv`), `colormap_blur_sigma` (default `9.0`),
`colormap_scale` (`0.25`, unchanged), `colormap_mips` (`true`, unchanged).
Hand-off: `docs/evidence/HANDOFF_colormap_tint.md`.

### 9.8 The camera probe works (coordinator, 2026-09-09 23:37)

`scripts/camera_probe.py` was tried in game and does what it claims:
`START_LOOK_AT { 2351.8 0 5706.6 }` opened the map on Waterdeep and the Sword
Coast (Faerûn county names, our coastline), and adding
`REALM_COLOR_MAP_START_ZOOM_STEP = 0` with `START_ZOOM_STEP = 4` removed the
political colour wash so the **terrain, its paint and the trees are visible**
in a headless screenshot. Recipe:

```
uv run scripts/camera_probe.py <mod dir> <probe dir> --place waterdeep --zoom 4
# then add REALM_COLOR_MAP_START_ZOOM_STEP = 0 to the probe's NCamera block
claudespace/scripts/ck3_soak.sh <mod> --extra <probe dir> --secs 120
# screenshot ~60 s after "Setting idler 'In Game'":
#   WAYLAND_DISPLAY=ck3-headless weston-screenshooter
```

Two waits matter: the In Game marker fires while the loading screen is still
up, so a screenshot taken 20 s after it catches the loading art; 60 s is
enough. Any visual claim about the map can now be checked without the user.

### 9.9 Lane `trees-regional`: procedural regional species mix

**Question this answers.** §9.2 picked a tree's mesh from its province's CK3
terrain class alone. That used **6 of vanilla's 18 generators** and leaned on
`tree_leaf_high_generator_1` for 48 % of all instances
(`docs/report_map_paint.md` fig 7): no pine belt in the north, no cypress, no
palm anywhere. Vanilla's own placement is regional, and this lane measures
that and reproduces it.

**Measurement 1 — vanilla's own mix.**
`scripts/measure_vanilla_tree_mix.py` walks all 549,126 instances in vanilla's
own 18 `gfx/map/map_object_data/generated/*.txt`, converts each
`transform=`'s `x`/`z` back to a canvas pixel (`y = 4608 − z`, the same frame
`ck2ck3.map.locators` uses), and looks up three things at that pixel:

| variable | source | note |
|---|---|---|
| CK3 terrain key | `common/province_terrain` via `provinces.png` + `definition.csv` | 11,651 rows, `default_land = plains` |
| winter climate zone | `map_data/climate.txt` | `mild`/`normal`/`severe`, else `none` — vanilla names only **635** of its 11,651 land provinces |
| latitude band | canvas row decile, band 0 = north | `assumed`: fractional north-south position transfers between a real-world map and a fantasy one |

Output `docs/evidence/vanilla_tree_mix.csv` (967 rows,
`P(file | terrain, climate, band)` with counts). Vanilla's own gradient, as
share of each band's instances:

| band | pine | broadleaf | jungle | palm | cypress | reeds |
|---|---|---|---|---|---|---|
| 0 (N) | **93.6** | 6.4 | 0 | 0 | 0 | 0 |
| 1 | **91.7** | 2.6 | 0 | 0 | 0 | 5.7 |
| 2 | 26.7 | 57.9 | 0 | 0 | 0 | 15.4 |
| 3 | 0.3 | 83.2 | 0 | 0 | 0.1 | 8.9 |
| 4 | 1.4 | 82.6 | 0.3 | 0 | **11.8** | 3.5 |
| 5 | 0.1 | 66.8 | 16.2 | 10.0 | 4.8 | 2.0 |
| 6 | 0 | 38.0 | 47.3 | 11.0 | 0 | 3.7 |
| 7 | 0 | 46.4 | 21.3 | **23.1** | 0.1 | 9.1 |
| 8 | 0 | 54.2 | 39.0 | 1.8 | 0 | 4.9 |
| 9 (S) | 0 | 13.2 | **85.1** | 1.7 | 0 | 0 |

So "pines north, cypress and palm south" is vanilla's own behaviour, not a
style preference — and the four `tree_sakura_*` generators are 730 instances
in total (0.13 %), a Japan-only curiosity that survives in the table at that
same negligible weight rather than being hand-deleted.

**Measurement 2 — which conditioning variable actually carries the signal.**
`scripts/build_tree_mix_csv.py` scores every scheme by top-1 accuracy and
cross-entropy over vanilla's own instances
(`docs/evidence/vanilla_tree_mix_conditioning.csv`):

| scheme | conditions | top-1 | cross-entropy |
|---|---|---|---|
| global | 1 | 25.2 % | 3.188 bits |
| terrain | 15 | 49.8 % | 2.056 bits |
| terrain + climate | 44 | 50.7 % | 2.008 bits |
| **terrain + latitude** | 104 | **58.8 %** | **1.626 bits** |
| terrain + climate + latitude | 188 | 59.4 % | 1.588 bits |

Latitude is worth ten times what climate is worth *on vanilla's data*, because
vanilla's `climate.txt` covers 5 % of its provinces. That measurement, not a
prior, fixes the fallback order in `tree_scatter.resolve_mix`. (In-sample, so
the finest scheme is flattered — hence the `--min-count 100` gate; the two
single-variable schemes are compared on equal footing.)

**The table.** `mappings/tree_mix.csv` (`# GENERATED`, 277 conditions,
1632 rows) materialises the full conditional *and* its marginals as explicit
rows, `*` being the wildcard. The sampler's chain, most specific first:

1. `(terrain, climate, band)`
2. `(terrain, *, band)`
3. `(terrain, *, band∓1)` — bands are ordinal and species vary smoothly with
   latitude. Not cosmetic: vanilla has **no forest-classified province in its
   own band 0 at all** (Iceland and northern Norway are taiga and mountains),
   while Faerûn's band 0 is 79,028 tree instances of mostly forest-classified
   land. Without this step the entire far north fell through to the
   Europe-wide severe-winter forest marginal and came out 65 % broadleaf; band
   1 next door is 70 % pine. Pine share in bands 0–1 went 28 % → 72 % when
   this rung was added.
4. `(terrain, climate, *)`
5. `(terrain, *, *)`
6. the terrain's single row in `mappings/tree_meshes.csv`

**Faerûn's own conditioning variables.** The terrain class is the existing
per-province majority vote; the climate zone is `_climate_code_grid` in
`ck2ck3.map.build`, which remaps Faerûn's own CK2 `map/climate.txt` through
the same `IdMap` that writes `map_data/climate.txt` itself, so a tree is
sampled under the zone the game will read for that province; the band is
`tree_scatter.lat_band`, a canvas row decile of our own 6784-px canvas.

**Coherence.** Species form stands. `[map] trees_cell_coherence` (0.55) of the
trees take one shared uniform per `[map] trees_cell_px` (24) square cell,
hashed by cell position with `zlib.crc32` — never `hash()`, which Python salts
per process and which already cost this module a 1.4 M-line diff of pure yaw
churn (§9.2). The rest draw independently, because **vanilla's own stands are
not pure**: `docs/evidence/vanilla_tree_patch_scale.csv` measures the
instance-weighted share of a cell's dominant generator and vanilla is only
0.775 at 8 px, 0.724 at 24 px, 0.541 at 256 px. Calibrated result
(`docs/evidence/tree_mix/patch_scale.csv`), `verified` on the real run:

| cell | vanilla | ours, terrain only | ours, regional |
|---|---|---|---|
| 8 px | 0.775 | 0.987 | 0.745 |
| 24 px | 0.724 | 0.962 | **0.727** |
| 64 px | 0.657 | 0.910 | 0.559 |
| 256 px | 0.541 | 0.773 | 0.474 |

The terrain-only pass was far *too* pure (a whole province is one species);
ours now matches vanilla at the calibration scale and is somewhat more mixed
than vanilla above it — see the open questions.

**The density contract is untouched.** `tree_scatter.pick_points` is shared by
both paths, so the same seed picks the same points either way, and
`mappings/tree_meshes.csv` stays the eligibility gate — a terrain key with an
empty `file` column gets no trees whatever the mix table says. `verified` on
the real Faerûn run at the time (build 9, before `[map] province_terrain_history`): **711,875 of 729,838 placed, 17,963 dropped, identical
before and after**. All 18 vanilla generator files are still overridden; the
one the mix never uses (`tree_sakura_02_generator.txt`) is written as an
empty stub.

**Result, real Faerûn run** (`--out ../_out/trees-regional`,
`scripts/report_tree_mix.py`). **17 of 18 generators used, up from 6**, and
the share of the largest single generator falls from 47.7 % to 25.9 %:

| generator | vanilla | ours, terrain only | ours, regional |
|---|---|---|---|
| `tree_pine_01_b_generator_1` | 87,196 | 46,370 | 122,941 |
| `tree_pine_01_a_generator_1` | 51,997 | 0 | 41,695 |
| `tree_pine_impassable_01_a_generator_1` | 30,406 | 0 | 887 |
| `tree_leaf_high_generator_1` | 138,645 | 339,829 | 184,190 |
| `tree_leaf_high_generator_2` | 36,248 | 0 | 53,852 |
| `tree_leaf_high_generator_3` | 74,170 | 0 | 111,056 |
| `tree_leaf_2_high_generator_1` | 14,831 | 0 | 34,086 |
| `tree_leaf_01_single_generator_1` | 3,954 | 179,733 | 5,680 |
| `tree_jungle_01_d_generator_1` | 38,113 | 104,334 | 102,756 |
| `tree_jungle_01_c_generator_1` | 1,227 | 0 | 3,443 |
| `tree_cypress_01_generator_1` | 7,138 | 0 | 13,637 |
| `tree_palm_generator_1` | 12,739 | 0 | 2,048 |
| `reeds_01_generator_1` | 47,085 | 23,898 | 33,565 |
| `steppe_bush_01_generator` | 4,647 | 17,711 | 934 |
| four `tree_sakura_*` | 730 | 0 | 1,105 |
| **total** | **549,126** | **711,875** | **711,875** |

Since build 10 the province-history terrain override retags 946 provinces (335 to `farmlands`, which has no mesh row), so the live count is **700,622 placed / 29,216 dropped** (`docs/evidence/last_run.md`, `docs/report_map_paint.md` §5); the mix shares above shift by under a point.

And the claim as a measurement — species family as a share of each latitude
band, vanilla / ours (`docs/evidence/tree_mix/lat_band_mesh.csv`, figure
`docs/evidence/tree_mix/fig_lat_band_mesh.png`):

| band | pine | broadleaf | jungle | palm | cypress | reeds | ours n |
|---|---|---|---|---|---|---|---|
| 0 (N) | 93.6 / **66.8** | 6.4 / 19.4 | – | – | – | 0 / 13.8 | 79,028 |
| 1 | 91.7 / **77.4** | 2.6 / 21.5 | – | – | – | 5.7 / 1.1 | 112,886 |
| 2 | 26.7 / 9.5 | 57.9 / 77.2 | – | – | – | 15.4 / 13.2 | 73,057 |
| 3 | 0.3 / 1.0 | 83.2 / 90.2 | – | – | 0.1 / 0 | 8.9 / 6.5 | 91,205 |
| 4 | 1.4 / 1.0 | 82.6 / 69.8 | 0.3 / 17.6 | 0 / 0.2 | 11.8 / **10.2** | 3.5 / 1.3 | 87,238 |
| 5 | 0.1 / 5.3 | 66.8 / 59.3 | 16.2 / 30.5 | 10.0 / 0.3 | 4.8 / 3.6 | 2.0 / 1.0 | 129,712 |
| 6 | 0 / 21.5 | 38.0 / 58.3 | 47.3 / 18.5 | 11.0 / 0.4 | – | 3.7 / 1.4 | 45,235 |
| 7 | 0 / 0 | 46.4 / 65.7 | 21.3 / 29.4 | 23.1 / 1.1 | – | 9.1 / 3.8 | 57,623 |
| 8 | 0 / 0 | 54.2 / 26.1 | 39.0 / **70.7** | 1.8 / 0.6 | – | 4.9 / 2.6 | 21,809 |
| 9 (S) | 0 / 0 | 13.2 / 20.4 | 85.1 / **75.2** | 1.7 / 4.3 | – | – | 14,082 |

Pine in the two northernmost bands: **14.3 % → 72.1 %** (vanilla 92.6 %).
Jungle + palm in the two southernmost: **52.3 % → 75.4 %** (vanilla 63.8 %).
Cypress appears at all, and peaks in band 4 at 10.2 % against vanilla's own
11.8 %.

**Config.** `[map] trees_regional` (default `true`), `trees_mix_csv`
(`mappings/tree_mix.csv`), `trees_mix_overrides_csv` (`overrides/tree_mix.csv`),
`trees_cell_px` (24), `trees_cell_coherence` (0.55). Read in **both**
`ck2ck3.map.config.load` and `ck2ck3.steps.map._map_config` — and while adding
them, **the four existing `[map] trees*` keys turned out to have the
`colormap = false` bug too**: `_map_config` never read `trees`, `trees_csv`,
`trees_seed` or `trees_density_per_px` at all, so `[map] trees = false` in
`configs/faerun.toml` would have been a silent no-op. All nine keys are now
read there and pinned by
`tests/test_map_tree_mix.py::test_cli_config_builder_reads_the_tree_keys`.

**Human hook.** `overrides/tree_mix.csv` (ships empty) replaces the measured
distribution for an exact `(terrain, climate, lat_band)` key — not blended, so
forcing a region's species is one obvious edit.

**Reproduce.**

```
uv run scripts/measure_vanilla_tree_mix.py          # -> docs/evidence/vanilla_tree_mix.csv
uv run scripts/build_tree_mix_csv.py                # -> mappings/tree_mix.csv
PYTHONPATH=$PWD/src uv run ck2ck3 --config configs/faerun.toml --steps map --out <dir>
uv run --with matplotlib python scripts/report_tree_mix.py --before <dir off> --after <dir on>
```

**Open questions.**

1. **Palm is still 2,048 instances against vanilla's 12,739.** Vanilla plants
   palms on `drylands` (30 %), `floodplains` (67 %) and `oasis` (48 %);
   `mappings/tree_meshes.csv` gives `drylands`, `floodplains` and `desert`
   an empty row, so Faerûn's Calimshan and the Shaar drop their trees
   instead. Enabling `drylands` alone would move a few thousand instances
   from `dropped` to `palm` — a real change to the drop count, so it is a
   decision, not a bug fix.
2. **Band 6 is 21.5 % pine where vanilla is 0.** That is Faerûn geography,
   not a table error: CK2 arctic/glacier folds to CK3 `taiga`
   (`ck2ck3.map.terrain`) and Faerûn has cold uplands at mid-canvas.
   `assumed` to be correct; the coordinator's in-game look is the check.
3. **Above the calibration scale our stands are more mixed than vanilla's**
   (0.559 vs 0.657 at 64 px). Vanilla's long-range correlation comes from its
   province geometry, which one square cell size cannot reproduce; a second,
   coarser coherence scale would.
4. The latitude-band transfer is `assumed` — a canvas row decile of a
   real-world map standing in for a canvas row decile of Faerûn. It is the
   whole reason band 6 and band 9 read as they do.
5. `tree_pine_impassable_01_a_generator_1` is 887 instances for us and 30,406
   for vanilla, because our eligibility excludes impassable provinces and
   vanilla's own use of that mesh is almost entirely on them.

---

## 10. Lane `paint-edges`: soft, relief-aware class edges

**Question.** The user's playtest of build 13: *the map is very pixelated*.
And the question behind it — "was the hypothesis wrong on just assigning by
pixel, or is the map not high-def enough?"

**Answer, measured: it is the edges, not the resolution.** Both halves of
the answer are in §10.5, but the short version is that at build 13 the paint
had two defects that are independent of how many pixels the file has, and
fixing them shrank `detail_intensity.tga` by 7x, which then made the
resolution question moot — the full-resolution pair now fits under the size
cap that forced `terrain_paint_scale = 0.5` in the first place (§8).

### 10.1 What was wrong, in the pipeline's own terms

1. **The class edges were nearest-neighbour.** `terrain.bmp` is 2.90 km/px
   and the canvas is 1.9543x finer (`docs/map_scale.md`), so
   `_resize_codes`'s NEAREST resample turned every CK2 terrain-class
   boundary into a staircase of 2x2 canvas pixels. At
   `terrain_paint_scale = 0.5` one paint pixel is 2.97 km, so the staircase
   *was* the paint grid: the class edge could not be anything but a step.
2. **The blend was a noise dither, not a blend.** §2 step 3 mixed exactly
   two materials per pixel with a Gaussian noise field that "ignores class
   boundaries on purpose". It broke up flat texture, but it never softened a
   class edge, and it cost 2.000 non-zero `detail_intensity` channels per
   land pixel against vanilla's 3.467 (`docs/report_map_paint.md` §7.3).
3. **`trees.bmp` is 1/8 resolution** — 23.2 km per tree pixel — and
   `expand_trees` / `tree_scatter.upsample_to_source` expanded it with
   `np.repeat`, so a forest boundary was a 15.6-canvas-pixel block. That is
   the Wealdath Lego shape in the playtest screenshot.

### 10.2 What replaces it (`ck2ck3.map.paint_edges`)

`[map] terrain_paint_soft_edges = true` routes the paint through
`build_soft_blend` instead of `terrain_paint.build_layers`:

1. **A distance-field mask per class.** Each CK3 terrain class's 0/1
   indicator is Gaussian-blurred at `terrain_paint_edge_sigma_px` canvas
   pixels. The two strongest classes at a pixel set the blend, so a boundary
   is a ramp whose shape follows the boundary and not a noise field.
2. **A material *mix* per class, not a pair.** `mappings/terrain_paint.csv`
   gained `tertiary_material` plus `primary_weight` / `secondary_weight` /
   `tertiary_weight` (§10.4). Three of the four channels are the pixel's own
   class, the fourth its strongest neighbour; a material both classes name is
   merged into one channel rather than listed twice.
3. **A relief-aware boundary.** `relief_warp` derives an integer (dy, dx)
   per canvas pixel from the smoothed heightmap gradient, and the class map
   is sampled through it *before* it is blended, so a forest/plains edge
   wanders with the ground. Three properties by construction: the
   displacement is bounded (`|d| <= terrain_paint_relief_shift_px`, and
   rounding a vector component-wise can only shorten it — see the
   `np.trunc` fallback in `relief_warp`), it is exactly zero on flat ground
   (the saturating factor is `|grad h| / gradient_ref` clipped to 1), and it
   is deterministic (no RNG anywhere in this path).
4. **The same treatment for `trees.bmp`.** `forest_coverage` expands the
   tree indicator bilinearly, pixel-centre aligned, and thresholds it at
   `trees_mask_threshold`; the 0.5 contour sits on the midpoint between a
   forest and a non-forest source pixel, which is the area-preserving
   choice, and every corner is rounded. The same mask feeds the `forest`
   class promotion (`terrain.ck2_category_codes(forest_mask=...)`) and the
   tree scatter's eligibility, and the scatter mask is warped by the same
   relief field, so the trees stand where the forest is painted.

**The macro invariant.** CK2 still decides what is where. Only the sub-pixel
shape of a boundary and the material mix at a pixel change; a class must
never migrate more than one CK2 source pixel (2.90 km = 1.9543 canvas px)
from where CK2 painted it. `class_displacement_stats` measures it on every
run and the number is in the run log: for each pixel whose class changed,
the distance to the nearest pixel that already carried the new class. That
metric is the right one because swallowing a one-pixel speckle of class X
registers as its neighbour Y moving one pixel, not as X moving to infinity.

### 10.3 Config keys (all flat under `[map]`, read by `steps/map.py`)

| key | default | meaning |
|---|---|---|
| `terrain_paint_soft_edges` | `true` | use the distance-field blend. `false` restores build 13's `build_layers` exactly |
| `terrain_paint_edge_sigma_px` | `2.0` | Gaussian sigma, canvas px, of each class indicator mask: the width of the ramp. `0` = hard edges |
| `terrain_paint_relief_shift_px` | `1.5` | maximum relief warp, canvas px (2.23 km, inside the 2.90 km bound). `0` disables the warp |
| `terrain_paint_relief_sigma_px` | `8.0` | Gaussian on the heightmap before its gradient drives the warp |
| `terrain_paint_relief_percentile` | `90.0` | land-gradient percentile at which the warp saturates at the full shift |
| `trees_mask_smooth` | `true` | bilinear + threshold expansion of `trees.bmp` instead of `np.repeat` |
| `trees_mask_threshold` | `0.5` | coverage level that counts as forest |
| `trees_mask_blur_px` | `0.0` | extra Gaussian (source px) on the interpolated tree field |

`_map_config` in `src/ck2ck3/steps/map.py` is the only reader of the `[map]`
table; a key added to `MapConfig` alone is silently ignored, which is exactly
the bug build 11 shipped with the `[map] trees*` keys. All eight are read
there (`grep -n terrain_paint_soft_edges src/ck2ck3/steps/map.py`).

### 10.4 Why a third material, and where it comes from

`scripts/measure_vanilla_paint_blend.py` (this lane) settles whether
vanilla's 3.467 channels per pixel is an edge effect or a property of the
class itself, by binning vanilla's own land pixels by distance to the
nearest terrain-class boundary
(`docs/evidence/paint_edges/vanilla_blend_by_distance.csv`, `verified`):

| distance to a class boundary | 0-2 px | 2-5 | 5-10 | 10-20 | 20-50 | >50 |
|---|---|---|---|---|---|---|
| non-zero channels / px | 3.231 | 3.338 | 3.404 | 3.465 | 3.527 | **3.623** |
| mean primary weight | 0.522 | 0.518 | 0.516 | 0.510 | 0.510 | 0.557 |

It goes **up** with distance from the boundary. So vanilla's blend is not
edge bleed: a vanilla terrain class paints 3-4 materials of its own deep in
its own interior, and soft edges alone could never reach 3.47. Each class
needs its own third material — which is also the "third material" item
`docs/report_map_paint.md` §7.3 left open.

The same script's second output ranks, per CK3 terrain key, the materials
vanilla paints on that key's own *interior* pixels
(`docs/evidence/paint_edges/vanilla_materials_by_terrain.csv`). That ranking
cannot be used raw: it is contaminated by province granularity — a vanilla
province is one terrain key over thousands of pixels of real, varied ground,
so vanilla's own "plains" pixels lead with `forest_jungle_01` (18.5 %) and
its "steppe" pixels with `mountain_03` (61.4 %), two picks
`mappings/terrain_paint.csv` had already rejected by hand with a note each.
`scripts/propose_paint_tertiary.py` therefore applies a narrower rule, and
records it in each row's `note`:

> the tertiary is the highest-ranked material in vanilla's own non-regional
> interior ranking **for that terrain key** that is in the same material
> *family* as our audited primary, is not vanilla's `debug` placeholder, and
> is not already the primary or the secondary. A key whose own ranking has no
> same-family candidate falls back to the largest material of that family by
> overall vanilla land coverage (only `steppe`, `sea` and `coastal_sea` do).

Weights are `0.55 / 0.28 / 0.17` for every three-material row and
`0.66 / 0.34` for a two-material one. They are not an art choice: 0.55/0.28/
0.17 has a blend entropy of 1.42 bits and a primary weight of 0.55 before
any neighbour is mixed in at a boundary, which is what lands the land-wide
numbers on vanilla's measured 1.4916 bits and 0.5247.

### 10.5 Resolution or edges? The measurement

The user asked which of the two it was. Both builds below are at
`terrain_paint_scale = 1.0` — **the same resolution** — so the comparison
isolates the edges (`docs/evidence/paint_edges/paint_blend_before_after.csv`,
`verified`, measured off the shipped TGA pairs, land only):

| | build 13 (before) | soft edges (after) | vanilla (target) |
|---|---|---|---|
| non-zero channels / px | 2.000 | **3.23** | 3.467 |
| mean primary weight | 0.712 | **0.538** | 0.525 |
| blend entropy | 0.714 bits | **1.505 bits** | 1.492 bits |
| materials used over land | 20 | 27 | 101 |

**It was the edges, and here is why resolution could not have been the
cause.** At build 13's `terrain_paint_scale = 0.5` one paint pixel was
2.97 km and one CK2 source pixel is 2.90 km: the paint file already resolved
its own input almost exactly. No class detail was being lost to the file's
resolution — there was none left to lose. Every visible step was the NEAREST
resample of that input and the noise dither over it, both of which look
identical at any resolution. The before/after crops
(`docs/evidence/paint_edges/fig_sword_coast_before_after.png`,
`fig_wealdath_before_after.png`, `fig_anauroch_before_after.png`) show the
same pixels of ground with and without the staircase.

Resolution matters *after* the fix, not before it: a boundary ramp needs
pixels to be drawn in, and at 1.48 km/px there are twice as many of them
across each ramp as at 2.97. Which is why §10.6 ships full resolution — and
it turned out to cost nothing.

Two other measured results from the same pair of runs:

* **The relief warp moved 24.1 % of the canvas** by at least one pixel, and
  nothing on flat ground.
* **The macro invariant held**: 1.4 % of land pixels changed class,
  **max displacement 2.099 km (0.72 CK2 source pixels), p95 1.484 km
  (0.51)** — inside the one-source-pixel bound, which is enforced rather
  than hoped for (`terrain_paint_max_shift_source_px`, §10.3). Before the
  enforcement was added the same configuration measured max 4.452 km: the
  warp is bounded by construction but the blend's corner rounding can
  swallow a one-pixel speckle, and the two together exceeded the bound.
  34,361 canvas pixels (0.06 % of the canvas) revert to CK2's own
  class because of the check.
* **The smooth tree mask is area-preserving**, as the 0.5 threshold
  promises: 456,344 source pixels become `forest` against the block
  expansion's 461,888 (−1.2 %), and the scatter's eligible area is
  1,234,566 against 1,259,712 (−2.0 %). The forests are the same size; only
  their outlines changed.

### 10.6 Size: full resolution is now free (part D)

`docs/evidence/paint_edges/paint_sizes.csv`, `verified`, both layers
re-encoded from the shipped full-resolution pair:

| layer | scale | `tga` | `tga_rle` |
|---|---|---|---|
| `detail_index` | 1.0 (8320×6784) | 225.77 MB | **20.42 MB** |
| `detail_intensity` | 1.0 | 225.77 MB | **24.41 MB** |
| `detail_index` | 0.5 (4160×3392) | 56.44 MB | 7.14 MB |
| `detail_intensity` | 0.5 | 56.44 MB | 9.20 MB |

Against §8.3's build-13 numbers at the same scale and format: `tga_rle` at
1.0 was 5.57 MB + **172.55 MB**. The intensity layer is **7.1x smaller**,
and the whole pair at *full* resolution (44.8 MB) is now **smaller than the
half-resolution pair was** (56.9 MB). §8.3's diagnosis was exactly right —
"the noise field is the cost, not the container" — and removing the noise
field removed the cost: a class interior is now one constant RGBA quadruple,
which is what RLE is for. `detail_index` grew (5.57 → 20.40 MB) because it
now carries three or four material ordinals per pixel instead of two, and
that is a bargain.

**So `[map] terrain_paint_scale = 1.0` is the new default** — the value
vanilla, Elder Kings 2 and Godherja all use, and the one no installed mod
tests a smaller alternative to (§8.5). The 100 MB/file constraint that
forced 0.5 in §8.4 no longer binds, with 70 MB of headroom on the larger
layer.
