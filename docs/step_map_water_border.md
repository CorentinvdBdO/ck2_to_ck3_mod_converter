# The whole-map rasters: water, snow and the surround frame

Lane `water-border`. Two build-13 playtest findings, one cause:

1. *"When zooming in the water, the map of Europe appears."*
2. *"The map border is broken at the top — probably to hide northern Siberia in
   vanilla, but here it hides real content."*

Both are the same failure mode as the flat map (`docs/evidence/map_ui_research.md`
§4) and the colormap (`docs/step_map_paint.md` §9.6): a CK3 texture that is
**sampled at a whole-map UV**, so every texel is pinned to one spot of the map,
and which vanilla ships painted around **Earth**. Ship no override and the
engine stretches vanilla's oceans, shorelines, heat belt and Arctic vignette
over whatever shape your own continent is.

Modules: `ck2ck3.map.water`, `ck2ck3.map.surround`. Config: `[map] water*`,
`snow_mask*`, `surround*`. Tables: `mappings/water_profile.csv`,
`mappings/surround_profile.csv`. Scripts: `scripts/inventory_map_rasters.py`,
`scripts/probe_map_raster.py`, `scripts/measure_vanilla_water.py`,
`scripts/measure_vanilla_snow_mask.py`, `scripts/measure_vanilla_surround.py`.

---

## 1. The inventory

`scripts/inventory_map_rasters.py` reads the header of every raster under a CK3
`gfx/map` tree without decoding it, and flags the ones whose aspect matches the
canvas and whose size is at least a quarter of it. Over vanilla 1.19:
**595 rasters, 130 map-sized** (`docs/evidence/vanilla_map_rasters.csv`,
`verified` 2026-09-10).

121 of those 130 are `terrain/masks*/**.png`, the per-material mask PNGs the
runtime never reads (CLAUDE.md: the renderer reads `detail_index.tga` /
`detail_intensity.tga`). That leaves **nine** whole-map rasters that matter:

| file | vanilla | encodes | geography-dependent? | before this lane | override |
|---|---|---|---|---|---|
| `terrain/detail_index.tga` | 9216×4608 TGA32 | primary/secondary material ordinal per pixel | yes | **ours** (`terrain_paint`) | — |
| `terrain/detail_intensity.tga` | 9216×4608 TGA32 | blend weights per pixel | yes | **ours** (`terrain_paint`) | — |
| `terrain/colormap.dds` | 9216×4608 DXT5, 14 mips | large-scale colour wash | yes | **ours** (`colormap`) | — |
| `terrain/flat_maps/flatmap.dds` | 9216×4608 DXT1 | the zoomed-out paper map | yes | **ours** (`flatmap`) | — |
| `terrain/flat_maps/flatmap_tgp.dds` | 9216×4608 DXT1 | the same, TGP style | yes | *not ours* | `assumed` harmless: the style table selects `paper_map_style_western`, which reads `flatmap.dds`. Backlog. |
| `water/watercolor_rgb_waterspec_a.dds` | 4608×2304 BC7, 13 mips | **RGB = water colour, A = gloss** | **yes — this is the reported bug** | *not ours* | painted from our own coast distance |
| `water/foam_map.dds` | 4608×2304 DXT5, 13 mips | R = shore-foam allowance, G = water mask, B/A constant | **yes** | *not ours* | painted from our own coast distance |
| `textures/snow_mask.dds` | 4608×2304 BC7, 13 mips | R = "snow never falls here"; G/B/A tiled noise | **yes (R only)** | *not ours* | flat R, vanilla's noise resampled |
| `surround_map/surround_mask.dds` | 4096×2048 DXT1, 13 mips | B hides the map, G masks clouds, R is the drop shadow | **yes — this is the border bug** | *not ours* | measured frame on all four edges |

Everything else under `gfx/map/` is a tiling material, a 1×N ramp, a cubemap or
a lighting preset — none of them map-projected. `gfx/map/terrain/colormap_water.dds`
**does not exist in 1.19** (`verified`); the name survives only in older guides.
`gfx/map/environment/environment_terrain_*.dds` are lighting-preset lightmaps,
`assumed` map-projected but selected through a scripted table rather than a
whole-map UV — backlog, not this lane.

Two shipped, loadable total conversions override every one of the four unowned
files (`verified` by reading their headers, `scripts/inventory_map_rasters.py`
over each workshop install):

| file | Elder Kings 2 (8256×5504) | Godherja (8192×4096) |
|---|---|---|
| `watercolor_rgb_waterspec_a.dds` | 4128×2752 **A8R8G8B8**, 1 mip | 4096×2048 **A8R8G8B8**, 13 mips |
| `foam_map.dds` | 4128×2752 DXT3, 13 mips | 1024×512 DXT5, 11 mips |
| `textures/snow_mask.dds` | 2064×1376 DXT5, 12 mips | 2048×1024 BC7, 12 mips |
| `surround_map/surround_mask.dds` | 4128×2752 DXT5, 1 mip | 4096×2048 DXT1 — vanilla's own file, byte-for-byte |

Sizes disagree, formats disagree, mip counts disagree, and both mods load. So
**resolution and compression are free choices; the content is not.**

---

## 2. Why the sea showed Europe

`gfx/FX/jomini/jomini_water_default.fxh:42` builds the water surface's UV
straight from the world position:

```
VertexOut.UV01 = float2( WorldSpacePos.x / MapSize.x,
                         1.0 - WorldSpacePos.z / MapSize.y );
```

No tiling, no offset: texel (0, 0) is the map's north-west corner whatever the
map is. That UV then reaches:

* `:505` `float4 WaterColorAndSpec = PdxTex2D( WaterColorTexture, Input._WorldUV );`
  — RGB is the water's own colour, `.a` its gloss. `gfx/map/water/water.settings:4`
  points `WaterColorTexturePath` at `watercolor_rgb_waterspec_a.dds` and its own
  comment says *"Sampled directly with world UV before any blending."*
* `:346` the refraction pass samples it again at the refracted world position.
* `:289` `float FoamMap = 1.0 - PdxTex2DUpscaleNative( FoamMapTexture, UV01 ).r;`
  — so a **high** R means foam. `:275` reads `.g` to mask the approaching-wave
  pass.

Decoding vanilla's `watercolor_rgb_waterspec_a.dds` (`scripts/probe_map_raster.py`)
shows the file for what it is: a painting of Eurasia and Africa, tan Sahara and
all, with a teal continental shelf around every real coastline
(`docs/evidence/water_border/watercolor_rgb_waterspec_a_rgb.png`). `foam_map`'s
G channel is a straight binary picture of Earth's landmasses
(`.../foam_map_rgb.png`). That is the "map of Europe" the playtest saw: it was
never the terrain, it was the water surface itself.

`gfx/map/rivers/riverwater.settings:1` points rivers at the **same** texture, so
the file's land texels are not dead — they are the colour of our rivers.

### What we write instead

`mappings/water_profile.csv` is vanilla's own mean of all six live channels
against **distance to the nearest coast**, one row per texel of depth, measured
by `scripts/measure_vanilla_water.py` over vanilla's own raster paired with its
`map_data/heightmap.png` (`WATERLEVEL 3 / WORLD_EXTENTS_Y 50 * 65535 = 3932`).
Depth is written in **canvas pixels**, not texels, so changing `[map] water_scale`
cannot silently rescale the coastline.

The measurement (`docs/evidence/vanilla_water_by_coast.csv`):

| coast distance (texels) | wc RGB | wc A (gloss) | foam R | foam G |
|---|---|---|---|---|
| water 1–2 | 45, 72, 73 | 55 | 78 | 31 |
| water 4–8 | 39, 77, 79 | 72 | 74 | 102 |
| water 16–32 | 31, 68, 70 | 75 | 33 | 234 |
| water 64–128 | 24, 54, 57 | 76 | 17 | 255 |
| land 1–2 | 39, 64, 65 | 61 | 75 | 6 |
| land 64–128 | 70, 70, 62 | 78 | 71 | 0 |

Read off: the shelf is lighter and greener than the open sea and *less* glossy;
foam is a shore effect with a measured e-folding length of **31 texels**; the
water mask feathers over ~32 texels rather than being binary; `foam_map`'s B is
**140** and its A **255** across the entire vanilla raster.

`ck2ck3.map.water` interpolates that profile at every pixel's own distance to
**our** coastline — the map step's existing `water_mask`, the same one the
colormap and rivers passes use. Alternatives considered and rejected:

* **Depth-driven instead of coast-driven.** Measured
  (`docs/evidence/vanilla_water_by_depth.csv`): vanilla's colour barely moves
  with depth (0–50 levels: 40, 71, 72; 3000–4000: 27, 61, 63) because 4.4 M of
  its 4.9 M sea texels sit on the same flat abyssal floor. Coast distance is
  what the painting actually varies with, and it is also what our own sea has —
  `deepen_sea` gives a flat floor with a 24 px shelf, so a depth ramp would
  reproduce exactly one ring anyway.
* **Reusing our `colormap.dds` for the land half.** Measured: the correlation
  between vanilla's watercolor and its own colormap over land is 0.42 / 0.04 /
  −0.33 per channel. They are unrelated textures.

Written as uncompressed **A8R8G8B8** — Elder Kings 2's and Godherja's own format
for this file, and the one `ck2ck3.map.colormap` already writes and tests.
`colormap.save` was widened to keep a supplied alpha, because here the alpha is
the gloss map, not padding.

---

## 3. Why the north edge was clipped

`gfx/map/surround_map/surround_mask.dds` is declared in three shaders with the
path hard-coded in the sampler, and read at a whole-map UV with V flipped:

* `gfx/FX/pdxterrain.shader:398-407` declares it; `:777-778`
  ```
  float SurroundMapAlpha = 1 - PdxTex2D( SurroundFlatMapMask,
                                         float2( ColorMapCoords.x, 1.0 - ColorMapCoords.y ) ).b;
  SurroundMapAlpha *= FlatMapLerp;
  ```
  — the **B channel makes the terrain itself transparent** as the camera pulls
  out toward the flat map (`NGraphics.FLAT_MAP_ZOOM_STEP = 21`,
  `common/defines/graphic/00_graphics.txt:49`).
* `gfx/FX/pdxborder.shader:93-104` declares the same sampler; `:115-116`
  `clip( 1.0f - mask.b - 0.1f )` throws away the political borders wherever B is
  high, so realm colours stop before the terrain does.
* `gfx/FX/surroundmap.shader:137` draws the surround plane with `alpha = mask.b`;
  `:230` / `:292` read `mask.g` as the cloud mask (its own comment: *"don't draw
  clouds over map"*); `:352-354` read `mask.r` as the map's drop shadow onto that
  plane.

So one file decides where the map stops being drawn — and vanilla's is painted
around Earth. Measured over vanilla's own 4096×2048 mask
(`scripts/measure_vanilla_surround.py`, `docs/evidence/vanilla_surround_edges.csv`):
the B channel's top margin runs **8 texels at its thinnest, 132 median, 1372 at
its worst — 67 % of the map height**. That worst case is the Arctic. On our
canvas it is the Spine of the World.

`NCamera.PANNING_WIDTH` / `PANNING_HEIGHT` were **not** the cause: the converter
already sets both to the canvas (CLAUDE.md, `bootstrap.render_camera_defines`),
so the camera can reach the north; the mask then hides what it reaches.
`NGraphics.SURROUND_MAP_INNER_RECT` (`{500 1000 500 3700}`) and
`SURROUND_MAP_OUTER_RECT` (`{-10000 -10000 20000 20000}`) exist at
`00_graphics.txt:52,54` in absolute world units, but no moddable file consumes
them and they are `assumed` to size the surround mesh, not to clip the map. They
are left alone.

### What we write instead

Copying vanilla's mask is wrong (it is Earth-shaped) and shipping none is wrong
(vanilla's is what loads). What transfers is the **thinnest frame vanilla itself
uses** — the profile it paints where its own content runs right up to the edge.
`scripts/measure_vanilla_surround.py` takes, per edge, the 5th percentile of
each channel at each inward depth, then the element-wise minimum over the four
edges. Result, `mappings/surround_profile.csv`:

| depth (texels) | R (shadow) | G (clouds) | B (hides map) |
|---|---|---|---|
| 0 | 145 | 244 | 255 |
| 8 | 150 | 243 | 134 |
| 11 | 148 | 227 | **0** |
| 24 | 123 | 65 | 0 |
| 44 | 24 | **0** | 0 |
| 53 | 2 | 0 | 0 |

54 texels total. At half canvas that is **108 canvas pixels** — inside the
128 px sea margin our canvas is built with (`docs/map_scale.md` §7,
`configs/faerun.toml` `sea_margin_px = 128`), so the frame never touches land,
and the terrain is fully visible from 22 canvas pixels in.

`ck2ck3.map.surround` paints that one profile against
`min(distance to any of the four canvas edges)` — a rectangular frame of
constant width, which is the only sane generalisation for a canvas whose content
reaches every edge. Written as **DXT1**, vanilla's own format for this file,
through the BC1 encoder the flat map already uses; alpha is unused by all three
shaders (vanilla's is a constant 255).

Measured against this build's own `provinces.png`: our northernmost land pixel
is at **row 140** of 6784 (province 4228 `THE_WESTERN_FROST`), so there are
140 px of sea above any land. Our frame is 108 px and never reaches it.
Vanilla's mask, applied to the same canvas, would have hidden **437 px** at its
median top margin and **4545 px** at its worst column.

---

## 4. The snow mask: both derivations rejected

`gfx/FX/dynamic_masks.fxh:134` and `:209`:

```
SnowEffectData._NoSnowMask = 1.0f - PdxTex2D( SnowMaskMap,
                                              float2( MapCoords.x, 1.0f - MapCoords.y ) ).r;
```

Only **R** is map-projected. G, B and A are sampled *tiled* (`:105`
`Coords * _SnowNoiseTiling`, `:144` / `:218` `MapCoords * 5.0`) and are noise, so
a resample of vanilla's own carries no geography and is the correct override for
those three. Vanilla's R is a heat belt: 0 over the far north, ~150 over the
Sahara–Arabia–India band (`docs/evidence/vanilla_snow_latitude.csv`).

Two ways to derive our own R were measured, and **both fail**:

* **Per terrain material**, the way `colormap_tints` works
  (`scripts/measure_vanilla_snow_mask.py`, `docs/evidence/vanilla_snow_mask.csv`):
  the per-material standard deviation routinely exceeds the mean (`desert_02`
  mean 48, std 81) and the ranking inverts — `desert` 48 against `mountains`
  198, with only `taiga` unambiguous at 0.01 ± 0.23. Vanilla reuses one material
  at every latitude it occurs at, so material identity carries almost no climate.
* **Per latitude**, which is what R really varies with. But the profile is
  *Earth's*, and Faerûn's canvas carries no Earth latitudes to transfer it onto.
  Applied literally it would also hand Chult a snow-allowed southern tail,
  because vanilla's own southern margin is unpainted.

So the converter ships a **flat R**, and the neutral value is **0, not the mean**:
R is a *suppression* mask, so vanilla's raster mean of 66 would suppress a
quarter of the snow everywhere rather than nowhere. Zero hands the snow line
back to the shader's own hemisphere term (`dynamic_masks.fxh:110`,
`_SnowHemisphere`, which already fades snow toward the south of any map) and to
the game's winter severity. `[map] snow_mask_no_snow` raises it for a map that
wants a hot belt.

---

## 5. What the converter writes

| file | ours | format | mips | scale key |
|---|---|---|---|---|
| `gfx/map/water/watercolor_rgb_waterspec_a.dds` | 4160×3392 | A8R8G8B8 | 1 | `[map] water_scale = 0.5` |
| `gfx/map/water/foam_map.dds` | 2080×1696 | A8R8G8B8 | 1 | `[map] water_foam_scale = 0.25` |
| `gfx/map/textures/snow_mask.dds` | 2080×1696 | A8R8G8B8 | 1 | `[map] snow_mask_scale = 0.25` |
| `gfx/map/surround_map/surround_mask.dds` | 4160×3392 | DXT1 | 1 | `[map] surround_scale = 0.5` |

The water mask is resampled to each raster's own grid **before** the coast
distance is measured, not after: measuring on the canvas and then downsampling
the finished raster would scale the shelf ramp by the downsample factor.

`[map] water = false` and `[map] surround_mask = false` turn each half off. Both
keys, and every scale key, are read in `ck2ck3.steps.map._map_config` as well as
in `ck2ck3.map.config.load` — a key the CLI-facing builder never reads is a
silent no-op, which is how `[map] colormap = false` was ignored for two builds.
`tests/test_map_water.py::test_cli_config_builder_reads_the_keys` pins it.

---

## 6. Open

* `terrain/flat_maps/flatmap_tgp.dds` is still vanilla's Earth. It only shows
  under the TGP paper-map style; `assumed` unreachable with our
  `flat_map_styles` selection. Backlog.
* `gfx/map/environment/environment_terrain_{sunny,shadow}.dds` and
  `environment_mapobjects_*.dds` are whole-map lighting bakes, `assumed`
  geography-dependent. Not measured. Backlog.
* `water/flowmap.dds` (2048×1024) is 2:1 and named like a whole-map texture, but
  is sampled tiled by the flow pass; both TCs override it anyway. Not measured.
* The surround frame is a constant-width rectangle. Vanilla's varies, which is
  an art call we have no source for.
