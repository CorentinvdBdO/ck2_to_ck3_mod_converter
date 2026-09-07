# Map design: CK2 Faerûn → CK3

Decisions here are converter defaults. Everything human-judged enters through override files so re-runs keep the work.

## A. Physical map

### Facts (`verified` 2026-09-07)
| | CK2 Faerûn | CK3 vanilla 1.19 | Elder Kings 2 | Godherja |
|---|---|---|---|---|
| provinces | 4096×3328 bmp | 9216×4608 png | 8256×5504 | 8192×4096 |
| heightmap | 8-bit `topology.bmp` same size | 16-bit `heightmap.png` **2×** (18432×9216) | 16-bit, 1× | 16-bit, 1× |
| packed heightmap | — | `packed_heightmap.png` + `indirection_heightmap.png`, `heightmap.heightmap` (tile 65) | tile 33 | tile 33 |
| positions | per province, 7 slots | `positions` commented out in `default.map` | commented out | 2-line file |
| rivers | 8-bit palette bmp | 8-bit palette png | same | same |
| province count | 2697 (369 sea) | 14152 rows | 5846 | 8734 |

- Custom map dimensions are allowed (EK2 proves it). Aspect ratio is free.
- Atlas guide map (1371 DR) is 3000×1878 (aspect 1.60); Faerûn CK2 map aspect 1.23 (includes more north/south). Overlay check is lane `map-physical` task 1.
- CK3 heightmap must be 16-bit; the packed pair is produced by the in-game map editor ("repack heightmap"), `assumed`; implementing the packer in Python is an option later (format: tiles of `tile_size`, indirection image indexes tiles, `level_offsets` per mip).

### Pipeline (converter)
1. `provinces.bmp` → NEAREST resize by `scale`, paste at `offset` on a canvas of `dims`; padding = a dedicated "ocean" colour registered in `definition.csv`, never black.
2. Lost-province detection: every CK2 colour must survive with ≥ `min_pixels` (default 64) or be reported; tiny ones are re-grown by one dilation pass inside their county, else listed in `docs/evidence/lost_provinces.csv`.
3. `topology.bmp` → 16-bit, LANCZOS resize to 2×dims, curve remap: CK2 sea level 95/255 → CK3 water level (measure from vanilla `heightmap.png` at coast pixels, task), mountains compressed by a configurable curve (`heightmap_curve` in the config, default = current 12-point curve).
4. Rivers: keep the vector follow/redraw approach; fix SPLIT (yellow) and WATER (magenta) handling; add a unit test on a synthetic river.
5. Write `default.map` (sea_zones from CK2 `sea_zones`, lakes from `ocean_region` "Lakes", impassable from CK2 wasteland), `definition.csv` (barony-keyed, see B), `adjacencies.csv` (straits from CK2 file, ids remapped), `climate.txt` (CK2 winter → CK3 `mild_winter/normal_winter/severe_winter` lists), `island_region.txt`, `geographical_regions/` (from CK2 `geographical_region.txt`, duchy lists remapped), `common/province_terrain/` (CK2 `terrain.bmp` majority colour per barony → CK3 terrain key via a mapping table).
6. `positions.txt`: omit; let the game generate. Optional later: centroid-based generation for cities at CK2 city position (rescaled), `assumed` acceptable since Godherja ships an empty file.

### Assets placement (answer to "can they be imported and rescaled")
- CK2 `positions.txt` gives per-province city/unit/port/council/etc. coordinates → yes, rescale with the same `scale`/`offset` and assign them to the **county capital barony**. Other baronies get centroids. This is enough for a loading map; fine placement is human/map-editor work.
- Unit models, trees, static objects: CK2 `map/statics` are not portable. Leave to the CK3 map editor.

## B. Barony subdivision

### Facts (`verified`, `scripts/faerun_barony_stats.py`, date 1368.9.2)
- 2132 counties, 15,195 defined baronies (median 7 per county), but only **3,786 built holdings** (median 1, mean 1.78, max 7). 1,088 counties have a single built holding.
- `max_settlements` median 3.
- Commented-out baronies are irrelevant (1 in the whole mod). "Unused" = defined but never built in history.

### Recommended method: "built holdings as physical baronies, seeded Voronoi, override CSV"
Better than pizza slices or one-per-county, and scales with human input:
1. **Barony set per county** = holdings built at the chosen bookmark date (default: earliest bookmark 1357.1.1 ∪ any holding built by the latest bookmark, so later bookmarks still have their provinces). Unbuilt defined baronies are emitted **as comments** in `landed_titles` (kept for the submod to promote). Result: ~3.8–4.5k land baronies, comparable to Godherja.
2. **Seeds**. Priority order, first match wins:
   - override file `overrides/barony_seeds.csv` (`barony_id, x, y` in CK3 pixel space) — human or LLM-gazetteer supplied;
   - gazetteer `overrides/gazetteer.csv` (`place_name, x, y, source`) matched on the barony's localised name (lore search feeds this: Wyrm's Crossing, Amphail…);
   - county capital barony → CK2 city position from `positions.txt`, rescaled;
   - remaining baronies → farthest-point sampling inside the county mask, biased by holding type: `city` toward coast/river pixels, `castle` toward hills/mountain terrain, `temple` neutral, `tribal` neutral.
3. **Growth**: multi-source geodesic Voronoi (BFS on the county pixel mask, so baronies never leak across water or impassable). Optional weight per seed so the capital gets the largest share (default 1.0 all).
4. **Size guard**: `min_barony_pixels` (default 400 at 9216×4608, ≈ a 20×20 blob). If the county area cannot host k baronies, the smallest holdings beyond capacity are demoted to comments and logged. This is where Baldur's Gate collapses to Inner City / Outer City / Wyrm's Crossing automatically; the neighbourhoods stay as comments for a later "special building" treatment by the submod.
5. **Colours**: each barony gets a unique colour derived from a hash of its id (deterministic across runs). `definition.csv` is barony-keyed; ids assigned by (kingdom, duchy, county, barony) order so nearby ids are nearby on the map.
6. **Review sheet**: per duchy, one PNG (`docs/evidence/baronies/<d_id>.png`) with the county outline, barony fills, seed dots, labels; plus the CSV the human edits. Editing = move a seed or add a row, rerun the lane script. This is the "faster human work" loop.
7. **Determinism**: given the same inputs and overrides, the output pixel map is identical (seeded hash, stable sort), so reconversions after upstream updates produce minimal diffs in the generated mod repo.

### Alternatives considered
- Pizza slices: ugly, ignores coast/terrain, no human loop. Rejected.
- One barony per county: loses the CK2 holdings (cities/temples) that carry the economy; only acceptable as a `--baronies=capital-only` debug flag. Kept as a flag.
- All 7 defined baronies as physical: 15k baronies of ~8×8 px, unreadable. Rejected.

## C. Open items (human decisions, not blocking the converter)
1. Target dimensions: keep 1:1 with vanilla scale (Faerûn ≈ 5918×4808 after scaling, i.e. bigger than vanilla) or fit into 9216×4608 with borders. Default in config: 1:1 scale, canvas 6144×5120 (multiples of 64 `assumed` required).
2. Bookmark date driving the barony set (default 1357.1.1 ∪ later).
3. How far to align the CK2 political map to the atlas 1371 canon: converter only reports diffs (county → atlas nation colour sampled at centroid) in `docs/evidence/canon_diff.csv`; edits are submod work.
