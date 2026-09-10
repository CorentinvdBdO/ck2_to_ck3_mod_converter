# Vanilla terrain-paint blend: edge or interior? (lane `paint-edges`)

Command: `uv run scripts/measure_vanilla_paint_blend.py`
Wall time: 11.0s total (distance transform: 2.4s), CK3 1.19 vanilla install, `23,720,182` land px of `42,467,328` (55.86%). `verified`.

## Q1 -- edge effect or interior property?

- `verified`: mean non-zero channels is `3.2311` at 0-2 px from a class boundary and `3.6227` at >50 px (interior). The invariant 3.467 (`CLAUDE.md`) is the **land-wide** mean, not an interior one.
- `verified`: full trend is in `docs/evidence/paint_edges/vanilla_blend_by_distance.csv` -- one row per bin (0-2, 2-5, 5-10, 10-20, 20-50, >50 px), each with land_px, mean_nonzero_channels, blend_entropy_bits, mean_primary_weight and the share of 1/2/3/4-channel pixels.
- `verified`: verdict -- **both**: the far-interior bin (>50 px) still averages well above 2 non-zero channels, so soft edges alone (blending two neighbouring classes' existing materials across the seam) cannot reach 3.47 on their own -- some of vanilla's blend is a genuine interior property of each terrain class (it paints 3+ materials of its own even far from any other class), not just edge bleed. Reaching 3.47 needs **both** softer edges **and** a 3rd/4th material per class.

## Q2 -- blend width

- `verified`: primary-material weight reaches ~90% of its interior value (interior mean over dist>=50px = 0.557, threshold 0.501) at **d = 1 province-map px** (integer-px curve, 3-px moving average, min 500 samples/px; not itself written to a CSV -- derived from the same per-pixel arrays as `vanilla_blend_by_distance.csv`).
- `verified`: at 1.4839 km/px (province-map / paint resolution, `docs/evidence/report_map_paint/panel_extents.csv` `vanilla_km_per_px_paint`), that is **1.5 km**.
- `verified`: the crossing is this low because the curve is not a simple edge-to-plateau ramp -- mean_primary_weight is already `0.5224` at 0-2px, *dips* to `0.5099`-`0.5099` through the 10-50px bins, then rises to `0.5567` only past 50px. Vanilla's primary-weight edge softening is nearly immediate; the wide, far-interior rise is a separate effect (large uniform interiors, e.g. big mountain ranges, painting with less texture variety than small or boundary-adjacent patches of the same class), not boundary blending.
- `assumed`: class-boundary definition includes land/water seams (vanilla's own `common/province_terrain` gives water provinces a real key, `sea`/`coastal_sea`), so this width mixes class-class and coastal blending; see the script's module docstring.

## Q3 -- material mix per terrain key

- `verified`: full ranked table (top 24 overall + top 24 non-regional, interior pixels only, dist>5px) is `docs/evidence/paint_edges/vanilla_materials_by_terrain.csv`.
- `verified`: non-regional interior top-3 for the terrains this lane asked about by name:
  - **plains**: primary=forest_jungle_01 (18.5%), secondary=desert_wavy_01 (15.0%), tertiary=mountain_02_desert_c (14.1%)
  - **forest**: primary=forest_leaf_01 (73.6%), secondary=mountain_02_c_snow (8.5%), tertiary=mountain_02_d_snow (4.5%)
  - **taiga**: primary=forest_pine_01 (71.2%), secondary=forestfloor (7.3%), tertiary=mountain_02_d (6.3%)
  - **mountains**: primary=mountain_02_snow (18.2%), secondary=desert_rocky (13.3%), tertiary=debug [vanilla placeholder, not real art] (6.8%)
  - **desert**: primary=desert_wavy_01 (23.2%), secondary=drylands_01 (15.1%), tertiary=desert_rocky (12.0%)
  - **steppe**: primary=mountain_03 (61.4%), secondary=drylands_01_grassy (14.6%), tertiary=mountain_02_desert_c (5.4%)
  - **hills**: primary=hills_01 (19.0%), secondary=drylands_01_grassy (16.3%), tertiary=hills_01_rocks (7.6%)
  - **jungle**: primary=forest_jungle_01 (56.5%), secondary=steppe_bushes (16.1%), tertiary=steppe_grass (8.7%)

### Proposed (primary, secondary, tertiary) triple per CK3 terrain key

Non-regional interior ranking's top 3, for `mappings/terrain_paint.csv` to gain a `tertiary_material` column from (`assumed` as a *proposal* -- these are vanilla's own choices, not yet cross-checked against Faerun's own geography the way the existing primary/secondary picks were). Vanilla's own `debug` placeholder material (materials.settings id `debug`, a literal dev/debug texture, not terrain art) is skipped when picking these three, even where it outranks the material shown (flagged below); the raw measurement including `debug` is in `vanilla_materials_by_terrain.csv`.

| ck3_terrain | primary | secondary | tertiary | note |
|---|---|---|---|---|
| desert | desert_wavy_01 (23.2%) | drylands_01 (15.1%) | desert_rocky (12.0%) |  |
| desert_mountains | desert_rocky (36.4%) | hills_01_rocks_medi (32.5%) | coastline_cliff_desert (4.5%) | vanilla's own top-3 non-regional pick includes `debug`, skipped here |
| drylands | drylands_01_grassy (60.9%) | drylands_01 (22.7%) | mountain_02_d_valleys (4.6%) |  |
| farmlands | farmland_01 (50.7%) | steppe_grass (10.9%) | mountain_02_c_snow (6.7%) |  |
| floodplains | floodplains_01 (46.7%) | drylands_01_grassy (13.2%) | oasis (9.3%) |  |
| forest | forest_leaf_01 (73.6%) | mountain_02_c_snow (8.5%) | mountain_02_d_snow (4.5%) |  |
| hills | hills_01 (19.0%) | drylands_01_grassy (16.3%) | hills_01_rocks (7.6%) |  |
| jungle | forest_jungle_01 (56.5%) | steppe_bushes (16.1%) | steppe_grass (8.7%) |  |
| mountains | mountain_02_snow (18.2%) | desert_rocky (13.3%) | wetlands_02 (6.3%) | vanilla's own top-3 non-regional pick includes `debug`, skipped here |
| oasis | drylands_01_grassy (32.4%) | mountain_02_c (28.3%) | drylands_01 (20.4%) |  |
| plains | forest_jungle_01 (18.5%) | desert_wavy_01 (15.0%) | mountain_02_desert_c (14.1%) |  |
| steppe | mountain_03 (61.4%) | drylands_01_grassy (14.6%) | mountain_02_desert_c (5.4%) |  |
| taiga | forest_pine_01 (71.2%) | forestfloor (7.3%) | mountain_02_d (6.3%) |  |
| terraced_hills | farm_paddy_01 (55.5%) | steppe_bushes (8.3%) | steppe_rocks (7.0%) |  |
| wetlands | oasis (44.3%) | steppe_bushes (9.4%) | steppe_grass (7.6%) |  |

