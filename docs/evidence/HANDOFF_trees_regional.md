# Hand-off — lane `trees-regional` (2026-09-10)

Procedural regional tree species: the mesh a tree gets is now sampled from
vanilla CK3's own measured `P(mesh | terrain, climate, latitude band)` instead
of from the province's terrain class alone. Method, provenance, counts and
open questions: `docs/step_map_paint.md` §9.9.

## The headline, as a measurement

Species family as a share of each latitude band's instances, vanilla / ours
(`docs/evidence/tree_mix/lat_band_mesh.csv`, figure
`docs/evidence/tree_mix/fig_lat_band_mesh.png`):

| | pine, bands 0–1 (north) | jungle+palm, bands 8–9 (south) | cypress, band 4 |
|---|---|---|---|
| vanilla CK3 1.19 | 92.6 % | 63.8 % | 11.8 % |
| ours, before (terrain class only) | 14.3 % | 52.3 % | 0 % |
| **ours, after** | **72.1 %** | **75.4 %** | **10.2 %** |

17 of vanilla's 18 generators are now used (was 6); the largest single
generator falls from 47.7 % to 25.9 % of all instances.

## What did not change

- **711,875 of 729,838 instances placed, 17,963 dropped — identical before and
  after.** `tree_scatter.pick_points` is shared by both paths, so the same
  seed picks the same points; `mappings/tree_meshes.csv` is still the
  eligibility gate (an empty `file` column = no trees on that terrain).
- All 18 vanilla generator files are still overridden; the one the mix never
  reaches (`tree_sakura_02_generator.txt`) is written as an empty stub.
- Format, density, seed and the locator coordinate frame: untouched.

## Bug found on the way

`src/ck2ck3/steps/map.py::_map_config` — the CLI-facing config builder — never
read **any** of the four existing `[map] trees*` keys (`trees`, `trees_csv`,
`trees_seed`, `trees_density_per_px`). `[map] trees = false` in
`configs/faerun.toml` would have been silently ignored, exactly as
`[map] colormap = false` was for two builds (§9.7). All nine tree keys are now
read there and pinned by a test.

## For the coordinator

1. **In-game check (this lane did none).** Camera probe recipe in
   `docs/step_map_paint.md` §9.8. Worth looking at: the Spine of the World /
   far north (`--place spine`) should now read as conifer, the Sword Coast
   (`--place waterdeep`) as broadleaf, Chult as jungle canopy.
2. **Decision — palm.** We place 2,048 palms; vanilla places 12,739. Vanilla
   plants them on `drylands` (30 %), `floodplains` (67 %) and `oasis` (48 %),
   and `mappings/tree_meshes.csv` gives `drylands`, `floodplains` and `desert`
   an empty row on the art grounds §9.2 recorded. Enabling `drylands` would
   turn several thousand *dropped* instances into palms in Calimshan and the
   Shaar — it changes the drop count, so it is a call, not a fix.
3. **Decision — sakura.** Vanilla's four `tree_sakura_*` generators are 730
   instances (0.13 %), a Japan-only curiosity. The measurement carries them
   through at the same negligible weight (1,105 for us, in band 3). Nothing
   was hand-deleted; `--drop-file tree_sakura_01_generator.txt` (repeatable)
   on `scripts/build_tree_mix_csv.py` removes them from the table if Faerûn
   should not have cherry blossom.
4. **Open, not blocking.** Above the 24 px calibration cell our stands are
   more mixed than vanilla's (0.559 vs 0.657 dominant share at 64 px); a
   second, coarser coherence scale would close it.
5. **The human hook is `overrides/tree_mix.csv`** (ships empty): rows replace
   the measured distribution for an exact `(terrain, climate, lat_band)` key.

## Verification

- `uv run pytest` — **1170 passed** (20 of them new, `tests/test_map_tree_mix.py`).
- `ci/checks.sh` — **checks green**.
- `scripts/validate_output_mod.sh ../_out/trees-regional` over a full 1372-file
  run — **fatal 0, error 58**, the same 41 loc-hash-collision / 14
  wrong-gender / 2 unknown-field / 1 history mix as build 3, and no
  diagnostic of any kind mentioning `map_object_data`
  (`docs/evidence/tiger_trees_regional_2026-09-10_summary.txt`).
- **Not** checked in game — the coordinator runs every in-game check.

## Reproduce

```
uv run scripts/measure_vanilla_tree_mix.py      # -> docs/evidence/vanilla_tree_mix.csv (+2 more)
uv run scripts/build_tree_mix_csv.py            # -> mappings/tree_mix.csv, conditioning.csv
PYTHONPATH=$PWD/src uv run ck2ck3 --config configs/faerun.toml --steps map --out ../_out/trees-regional
uv run --with matplotlib python scripts/report_tree_mix.py \
    --before ../_out/trees-before --after ../_out/trees-regional
```

`../_out/trees-before` is the same run with `trees_regional = false`, kept as
the before/after control.

## Files

- `src/ck2ck3/map/tree_scatter.py` — `read_mix_table`, `apply_mix_overrides`,
  `resolve_mix`, `lat_band`, `cell_uniform`, `assign_regional_meshes`,
  `scatter_regional`, `pick_points` (extracted, shared)
- `src/ck2ck3/map/build.py` — `_climate_code_grid`, the regional call
- `src/ck2ck3/map/config.py`, `src/ck2ck3/steps/map.py` — five new keys plus
  the four that were dead
- `mappings/tree_mix.csv` (generated), `overrides/tree_mix.csv` (human)
- `scripts/measure_vanilla_tree_mix.py`, `scripts/build_tree_mix_csv.py`,
  `scripts/report_tree_mix.py`
- `tests/test_map_tree_mix.py` (20 tests)
- `docs/evidence/tree_mix/`, `docs/evidence/vanilla_tree_mix*.csv`
