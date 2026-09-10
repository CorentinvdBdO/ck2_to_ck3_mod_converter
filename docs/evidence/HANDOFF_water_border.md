# Hand-off: lane `water-border`

Branch `lane/water-border`, worktree `/home/cvdbdo/git/paradox/ck3/wt/water-border`.
Fixes both build-13 playtest findings. Full account: `docs/step_map_water_border.md`.
**Not committed — the worktree is left dirty by instruction.**

## What was wrong

Two symptoms, one cause: a CK3 map texture sampled at a **whole-map UV** and
shipped by vanilla painted around **Earth**.

1. *"When zooming in the water, the map of Europe appears."* —
   `gfx/map/water/watercolor_rgb_waterspec_a.dds` is the water surface's own
   colour and gloss, read at `jomini_water_default.fxh:505` with the UV built
   at `:42` as `(x / MapSize.x, 1 - z / MapSize.y)`. Vanilla's file is a
   painting of Eurasia and Africa (`verified` by decoding it,
   `docs/evidence/water_border/vanilla/watercolor_rgb_waterspec_a_rgb.png`).
   `foam_map.dds` is the same story: its G channel is a binary picture of
   Earth's landmasses.
2. *"The map border is broken at the top."* —
   `gfx/map/surround_map/surround_mask.dds`, B channel:
   `pdxterrain.shader:777` `SurroundMapAlpha = 1 - mask.b` turns the terrain
   transparent and `pdxborder.shader:115` `clip(1 - mask.b - 0.1)` throws away
   the political borders. Vanilla's mask eats a median 6.5 % and a maximum
   **67 %** of the map height at the top — Arctic there, the Spine of the World
   on ours. `PANNING_HEIGHT` was already correct; the mask hid what the camera
   could reach.

A third leak found by the inventory and fixed here:
`gfx/map/textures/snow_mask.dds`'s R channel (`dynamic_masks.fxh:134`) prints
the Sahara's heat belt at the Sahara's latitude.

## The inventory

`scripts/inventory_map_rasters.py` over vanilla 1.19: **595 rasters, 130
canvas-sized**, of which 121 are the `terrain/masks*` PNGs the runtime never
opens. Nine matter; the converter already owned five (`detail_index`,
`detail_intensity`, `colormap`, `flatmap`, and `flatmap_tgp` deliberately not).
The four it did not are the ones above plus the snow mask —
**and both shipped total conversions override all four** (`verified` by reading
the headers of the live workshop installs: Elder Kings 2 `2887120253`,
Godherja `2326030123`). Table: `docs/step_map_water_border.md` §1.

## Files

New:
- `src/ck2ck3/map/water.py` — `watercolor_rgb_waterspec_a.dds`, `foam_map.dds`, `textures/snow_mask.dds`
- `src/ck2ck3/map/surround.py` — `surround_map/surround_mask.dds`
- `scripts/inventory_map_rasters.py` — every raster under a `gfx/map` tree, from its header
- `scripts/probe_map_raster.py` — decode any map raster to PNG + per-channel statistics
- `scripts/measure_vanilla_water.py` → `mappings/water_profile.csv`, `docs/evidence/vanilla_water_{by_coast,by_depth,summary}.csv`
- `scripts/measure_vanilla_surround.py` → `mappings/surround_profile.csv`, `docs/evidence/vanilla_surround_edges.csv`
- `scripts/measure_vanilla_snow_mask.py` → `docs/evidence/vanilla_snow_mask.csv`, `vanilla_snow_latitude.csv` (evidence for a **rejected** derivation)
- `docs/evidence/vanilla_map_rasters.csv`, `docs/evidence/water_border/` (vanilla vs generated previews and channel stats)
- `docs/step_map_water_border.md`, this file
- `tests/test_map_water.py` (13 tests), `tests/test_map_surround.py` (7 tests)

Edited:
- `src/ck2ck3/map/build.py` — imports, `_write_water_rasters`, `_write_surround_mask`, `_resample_mask`; the water block runs after the colormap block inside `not skip_images`, the surround block after the map-table block
- `src/ck2ck3/map/colormap.py` — `save()` now keeps a supplied 4-channel alpha instead of overwriting it with 255 (the water colour map's alpha is its gloss). RGB input is unchanged.
- `src/ck2ck3/map/config.py` — nine new `[map]` keys + loader
- `src/ck2ck3/steps/map.py` — the **same bug class as `colormap = false` and `trees = false`**: every new key is read here too, or the TOML toggle is a silent no-op. Pinned by `tests/test_map_water.py::test_cli_config_builder_reads_the_keys`.
- `CLAUDE.md` — four new invariant lines (water surface, surround mask, snow mask, the inventory / no `colormap_water.dds`), three new command lines, one docs pointer

## What is written

| file | ours | vanilla | format | scale key |
|---|---|---|---|---|
| `gfx/map/water/watercolor_rgb_waterspec_a.dds` | 4160×3392 | 4608×2304 | A8R8G8B8 | `water_scale = 0.5` |
| `gfx/map/water/foam_map.dds` | 2080×1696 | 4608×2304 | A8R8G8B8 | `water_foam_scale = 0.25` |
| `gfx/map/textures/snow_mask.dds` | 2080×1696 | 4608×2304 | A8R8G8B8 | `snow_mask_scale = 0.25` |
| `gfx/map/surround_map/surround_mask.dds` | 4160×3392 | 4096×2048 | DXT1 | `surround_scale = 0.5` |

Every value is measured, not invented: the colour, gloss and foam ramps are
vanilla's own mean per coast distance (`mappings/water_profile.csv`, in **canvas
pixels** so a scale change cannot rescale the coastline), indexed by *our*
distance to *our* coast; the frame is the thinnest one vanilla itself paints
(`mappings/surround_profile.csv`, 54 texels, B clear by 11 = 22 canvas px, the
whole frame inside our 128 px sea margin).

The snow mask's R is a flat 0 by decision. Both derivations were measured and
both fail — per material the standard deviation exceeds the mean and the ranking
inverts (`desert` 48, `mountains` 198); per latitude the profile is Earth's, and
Faerûn's canvas carries no Earth latitudes. 0, not the raster mean 66, because R
*suppresses* snow: the mean would suppress a quarter of it everywhere.
`dynamic_masks.fxh:110`'s own `_SnowHemisphere` term already fades snow toward
the south of any map.

## Checks

- `uv run pytest -q` → **1264 passed** (was 1244; +20 new), 0 failures.
- `bash ci/checks.sh` → **checks green** (re-run after the `configs/faerun.toml`
  edit).
- Full run → `/home/cvdbdo/git/paradox/ck3/wt/_out/water-border`: 16 steps,
  **1486 files** (was 1482 — the four new rasters), 169.8 s, of which the `map`
  step is 154.8 s and writes 59 files (was 55). The water and surround passes
  are ~10 s of that, all of it the two distance transforms.
- `scripts/validate_output_mod.sh /home/cvdbdo/git/paradox/ck3/wt/_out/water-border`
  → **fatal 0, error 58** — the unchanged baseline (41 `localization-key-collision`,
  14 `wrong-gender`, 2 `unknown-field`, 1 `history`). **Zero diagnostics of any
  severity name `watercolor`, `foam_map`, `snow_mask` or `surround_mask`.**
  Raw report `docs/evidence/tiger_full_water_border.txt` (15 MB, gitignored);
  committable extract `docs/evidence/tiger_full_water_border_summary.txt`.
- Generated rasters decoded and eyeballed against vanilla's:
  `docs/evidence/water_border/{vanilla,generated}/*.png`, channel statistics in
  the two `*_raster_stats.csv` beside them. The generated watercolor shows
  Faerûn's coastline with a teal shelf and no Sahara; the generated surround
  mask is a uniform 54-texel frame with a fully black (visible) interior.

## What the coordinator must look at in game

Coordinates are measured off this build's own `provinces.png` and given in the
locator frame `scripts/camera_probe.py` takes (`--x`/`--z`, z bottom-up), with
the provinces.png row in brackets. Canvas 8320×6784, 52.8 % water, land runs
from row 140 to row 6643.

1. **Open water — the primary probe.**
   `uv run scripts/camera_probe.py <out> <probe> --x 2470 --z 1789`
   (provinces.png x 2470, y 4994) — province **4276 `TRACKLESS_DEEP`**, the
   single point furthest from any coast on the map (1068 px). Zoom in to the
   level the playtest used.
   *Expect:* flat dark teal, RGB near **24, 55, 57**, no structure of any kind,
   no foam.
   *The bug looked like:* a tan Sahara-shaped patch and Mediterranean/Italian
   shorelines drawn in open water, because vanilla's Earth painting was being
   sampled there.
2. **A shelf — proves the ramp follows our coast, not vanilla's.**
   `--x 3405 --z 3488` (provinces.png x 3405, y 3295) — province **3736
   `LAPAL_COAST_2`**, ~50 px off the shore.
   *Expect:* a lighter, greener band (RGB near **35, 74, 76**) hugging the coast
   and fading to the open-water colour by ~120 px out, with foam only inside
   that band. The band must follow **Faerûn's** coastline everywhere it appears.
3. **The north edge — the second finding.** Pan to the top (`PANNING_HEIGHT` is
   already the canvas, so it is reachable) and pull out past
   `NGraphics.FLAT_MAP_ZOOM_STEP = 21` into the paper map. The northernmost land
   pixel is province **4228 `THE_WESTERN_FROST`** at provinces.png x 157,
   y 140 — `--x 157 --z 6643`.
   *Expect:* that province drawn, and an even fade about **22 canvas px** wide
   on all four edges, with political borders stopping at the same distance on
   each. Our whole frame is 108 px, inside the 140 px of sea above the first
   land row, so no land should be touched.
   *The bug looked like:* terrain and realm borders vanishing hundreds of pixels
   early at the top only, and by different amounts across the width — vanilla's
   mask hides a median 6.5 % of the map height there (437 px of ours) and up to
   67 % (**4545 px**) at its worst column.
4. **Secondary — rivers.** `rivers/riverwater.settings:1` points rivers at the
   same water colour texture, so its *land* texels are the colour of our rivers.
   Check one inland river (the Chionthar, or any river in the Dalelands) reads
   as water and not as ink.

## Open

- `terrain/flat_maps/flatmap_tgp.dds` is still vanilla's Earth; `assumed`
  unreachable with our `flat_map_styles` selection. Backlog.
- `gfx/map/environment/environment_terrain_*.dds` are whole-map lighting bakes,
  `assumed` geography-dependent, not measured. Backlog.
- Our watercolor's land half is flat (it only varies with coast distance);
  vanilla's varies with biome. Only rivers sample it, so this is cosmetic.
- The surround frame is a constant-width rectangle; vanilla's varies, which is
  an art call we have no source for.
