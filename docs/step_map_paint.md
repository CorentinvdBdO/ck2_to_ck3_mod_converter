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
