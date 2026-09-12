# Hand-off — lane `province-edges`

Organic province borders and coastlines at canvas resolution. Full write-up:
`docs/step_map_baronies.md` §10. Evidence:
`docs/evidence/province_edges/`.

## 1. The result in one table

`verified`, `scripts/province_edges_metrics.py`,
`docs/evidence/province_edges/staircase.csv`. Both maps are at 1.4839 km per
pixel, so the numbers compare directly.

| metric (all province borders) | build 15 | this lane | vanilla 1.19 |
|---|---|---|---|
| **mean straight run of a boundary crack** | **3.386 px** | **1.912 px** | **1.763 px** |
| 90°-corner pixels per 100 border px | 18.12 | 36.10 | 40.85 |
| boundary normals within 11.25° of an axis | 0.5305 | 0.4689 | 0.3398 |
| coastline: mean crack run | 3.349 px | 1.788 px | 1.707 px |
| coastline: crack perimeter ÷ σ=2 smoothing | 1.0715 | 1.0622 | 1.2267 |

3.386 / 1.763 = 1.92 ≈ the 1.9543 upsample factor: the staircase was
vanilla-shaped borders stretched, and it is gone. Corner density and length
ratio reward *fine* detail a 2.90 km source cannot carry, so vanilla scores
higher on both; they are the guard rail on over-smoothing, not a target.

## 2. What it cost

`docs/evidence/province_edges/topology_delta.json`, keyed by
`definition.csv` column 5 (never by the numeric id — ids renumber when one
barony changes status).

* 455,890 canvas px (0.81 %) changed province against NEAREST; 20,271 of
  them reverted by the enforced bound; **max total displacement (smoothing +
  warp) 1.414 canvas px, p95 1.0, bound 1.9543 (= 1.0 CK2 source px)**. The relief warp moved
  5,847,180 px (10.4 %) and nothing on flat ground.
* `definition.csv` colours that moved under a surviving name: **0**.
* CK2 provinces dropped as too small: **3 before, 3 after** (the same three).
* Coastline: 149,937 px changed side (0.27 % of canvas), **max displacement
  1.414 canvas px = 2.10 km = 0.72 CK2 source pixels**, p95 1.0, mean 1.0.
* `heightmap.png` pixels disagreeing with the new coastline: **0** — the
  detail pass pins the heightmap to the province land mask.
* 4-connected neighbour pairs 12,557 → 12,565 (+240 / −232).
* `adjacencies.csv`: 320 rows, **0** endpoints without pixels, before and
  after.
* Baronies: all 3857 built holdings still present; **3705 → 3704 placed,
  152 → 153 demoted**, 21 status changes; **71 (1.9 %) changed area by more
  than 20 %** (`barony_area_change.csv`).
* `map` step **128.4 s (`smooth_edges = false`) → 167–200 s** over four runs.
* `smooth_edges = false` reproduces build 15's `provinces.png` **byte for
  byte** (sha256 `7d9a7f78…b0ef60`), via
  `configs/faerun_province_edges_before.toml`.
* ck3-tiger on the lane's full output: **fatal 0, error 58** — the accepted
  baseline, unchanged (41 loc collisions, 14 wrong-gender, 2 unknown-field,
  1 history; `docs/evidence/province_edges/tiger_province_edges.txt`).
* `scripts/verify_heightmap_detail_invariants.py`: **invariants hold** (0 land
  px at/below water, 0 water px above).
* `scripts/check_locator_frame.py --mod`: exit 0, every locator inside its own
  province except the documented concave-centroid ids.

## 3. Open questions for the coordinator

1. **Accept the barony churn?** 21 status changes and a net −1 placed
   barony. The cause is §2's `capacity = county_pixels // 400` threshold, not
   the smoothing; any change of canvas or coastline moves it. The
   alternative is pinning the placed/demoted split from build 15 through an
   override file, which freezes a decision that should follow the map.
2. **`deepen_sea` runs before the detail pass.** It ramps its 24 px shelf
   from the *plain rescale's* shoreline, which disagrees with the province
   shoreline on **159,494 px (0.28 %)** (`verified`). Pre-existing, not
   introduced here, and invisible so far; moving `deepen_sea` after
   `heightmap_detail.apply` would align the shelf with the finished coast but
   changes the sea floor of a shipped build.
3. **The province warp is derived from the base heightmap, the paint warp
   from the detailed one.** Same function, same `[map]
   terrain_paint_relief_sigma_px` / `_percentile`, same bound — but not
   literally the same array, because the detailed heights need a land mask
   made out of the province raster. Making them literally identical means
   computing one warp from the base heights and using it for the paint too,
   which changes build 15's shipped paint.
4. **`smooth_relief_shift_px = 1.0` is a choice**, below the paint lane's
   1.5, because a province border also carries the barony partition and the
   coastline. Nobody has seen the difference in game yet.

## 4. What is still stepped

Inside a county, barony borders come from the 4-connected geodesic BFS
(`docs/step_map_baronies.md` §4), whose equidistant set is an L1 diagonal —
one-pixel steps. That is the remaining structure in the `inland` panel and
the reason the boundary-normal share stops at 0.47 instead of vanilla's 0.34.
Changing it means a different growth metric (8-connected or chamfer BFS, or a
distance-field partition) and reshapes every barony: a lane of its own.

## 5. Not done here

* In-game check at close zoom — the coordinator's.
* `uv run scripts/barony_review_sheets.py` has not been regenerated against
  the new partition.

## 6. Evidence index (`docs/evidence/province_edges/`)

| file | what |
|---|---|
| `staircase.csv` | the three metrics, before / after / vanilla, all borders and coastline |
| `topology_delta.json` | province set, colours, adjacency graph, coast shift, heightmap coast |
| `barony_area_change.csv` | the 71 baronies whose area moved more than 20 % |
| `fig_sword_coast_before_after.png` | Waterdeep's coast at (2345, 1060), ×5 |
| `fig_inland_before_after.png` | the densest water-free county cluster, auto-picked |
| `tiger_province_edges.txt` | ck3-tiger errors + summary (fatal 0, error 58) |
| `heightmap_invariants.log`, `locator_frame.log` | both pass |
| `run_before.log`, `run_after.log`, `full_run.log`, `last_run_after.md` | the runs |
