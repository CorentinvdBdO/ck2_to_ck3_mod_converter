# Hand-off: lane `map-colour`

Branch `lane/map-colour`, worktree `/home/cvdbdo/git/paradox/ck3/wt/map-colour`.
Paint half of "pre-unpause map fidelity" (asset placement and events are
other lanes). Full account and format decisions: `docs/step_map_paint.md` §9.

## Files changed

New:
- `src/ck2ck3/map/colormap.py` — `gfx/map/terrain/colormap.dds` resample/writer
- `src/ck2ck3/map/tree_scatter.py` — tree/foliage scatter into `gfx/map/map_object_data/generated/*.txt`
- `mappings/tree_meshes.csv` — CK3 terrain key -> vanilla generated-file mesh
- `scripts/verify_tree_density.py` — sums vanilla's own `count=` totals (549,126)
- `scripts/verify_terrain_paint_materials.py` — vanilla's own material per terrain key, from its real `detail_index.tga`
- `scripts/render_map_colour_evidence.py` — the three region composites in `docs/evidence/map_colour/`
- `scripts/camera_probe.py` — writes the `NCamera.START_LOOK_AT` probe-mod snippet
- `tests/test_map_colormap.py`, `tests/test_map_tree_scatter.py`, `tests/test_map_camera_probe.py`
- `docs/evidence/map_colour/{sword_coast,anauroch,spine_of_the_world}.png`
- `docs/evidence/tiger_map_colour.txt` (trimmed: head + per-class summary, full report is 15 MB/308k lines, not kept)

Edited:
- `src/ck2ck3/map/build.py` — wires colormap + tree_scatter into the `map` step, replacing the old empty-stub-only foliage path
- `src/ck2ck3/map/config.py` — `colormap`/`colormap_scale`/`colormap_mips`, `trees`/`trees_csv`/`trees_seed`/`trees_density_per_px`
- `src/ck2ck3/steps/map.py` — surfaces `trees_placed`/`trees_dropped`/`colormap_px` in the step's run-log counts
- `configs/faerun.toml` — the new `[map]` keys, all default on
- `mappings/terrain_paint.csv` — 3 of 17 rows changed (see §C below), every row's note rewritten with the verification finding
- `docs/map_fidelity.md` — §4.3 status updated from "research only" to implemented
- `docs/step_map_paint.md` — new §9 (colormap, trees, art pass, evidence, coordinator in-game check)

## Commands and results

- `uv run pytest -q` → **1123 passed** (was 1109 before this lane; +14 new tests, 0 regressions)
- `bash ci/checks.sh` → **checks green**
- Full run: `uv run ck2ck3 --config configs/faerun.toml --out /home/cvdbdo/git/paradox/ck3/wt/_out/map-colour` → 1372 files, 70.1 s total (map step 58.5-58.7 s, unchanged from before this lane within noise; colormap+trees add well under 1 s to that)
- `--steps map` alone: 58.5-58.7 s (colormap ~1 s, trees ~1-2 s of that)
- `bash scripts/validate_output_mod.sh /home/cvdbdo/git/paradox/ck3/wt/_out/map-colour docs/evidence/tiger_map_colour.txt` → **fatal 0**, error 58 (41 loc-key-collision, 14 wrong-gender, 2 unknown-field, 1 history — exactly the known accepted baseline from build 3, `STATUS.md`); nothing in the report mentions colormap/detail_index/detail_intensity/generated-tree files at all (ck3-tiger does not inspect these binary/generated formats, same conclusion the previous lane reached)
- `uv run python scripts/verify_tree_density.py` → 549,126 total, confirms the density figure
- `uv run python scripts/verify_terrain_paint_materials.py` → the per-terrain material histogram behind the CSV changes

## Sizes and counts

- `gfx/map/terrain/colormap.dds`: 2080x1696, uncompressed BGRA8 + full mip chain, **18.8 MB**
- `gfx/map/map_object_data/generated/*.txt`: 18 files, **66 MB total**, 711,875 tree instances placed of a 729,838 target (97.5%), 17,963 dropped (desert/mountains/farmlands, by design)
- Terrain paint (unchanged mechanism, corrected materials): still `tga_rle` at `0.5` scale, 2.3 MB + 53 MB (from the prior lane, this lane only edited the material table, not the format)
- Full generated mod (this out dir): 283 MB, 1372 files

## Goal C: `mappings/terrain_paint.csv` changes (3 of 17 rows)

1. **`forest`**: primary `forest_pine_01` (identical to `taiga`'s own primary — a real bug) -> `forest_leaf_01` (vanilla's own 75.5%-dominant pick)
2. **`terraced_hills`** (flagged): primary `hills_01_rocks_medi` -> `farm_paddy_01` (vanilla's own 56.5%-dominant pick, and thematically exact — rice-paddy terracing)
3. **`desert_mountains`**: primary/secondary swapped (vanilla's real top, `desert_rocky`, was our secondary; the old primary didn't even place top-3)

`taiga`'s flagged secondary (`snow`) kept deliberately — vanilla's own taiga blends with `forestfloor`, not snow, but Faerûn folds CK2 arctic/glacier into the same key with no vanilla equivalent of their own, so `snow` targets that broader bucket, not vanilla's narrower one. Every other row's note now records the vanilla evidence either way (`docs/step_map_paint.md` §9.3 has the full account).

## What is unverified in game

Nothing in this lane was checked against a running CK3 (hard rule: the
coordinator runs every in-game check). Specifically open:

1. Does `colormap.dds` actually render as a colour wash under the terrain paint (format is `verified` byte-for-byte against two loadable reference mods, but never loaded here)?
2. Do the repopulated tree files actually place visible foliage (format `verified` against vanilla's own files, never loaded)?
3. Does the `NCamera.START_LOOK_AT`/`START_ZOOM_STEP` probe (`scripts/camera_probe.py`) actually move the headless `-test` camera, so a screenshot lands on Waterdeep/Anauroch/the Spine instead of the canvas centre? This is the one open question that determines whether the coordinator gets an automated close-up check at all, or falls back to the user's own playtest (`docs/step_map_paint.md` §9.5 has the exact commands).
4. Whether 66 MB of tree data plus 18.8 MB of colormap noticeably changes load time or memory — not measured (no game launch).

## Open questions for the coordinator

- If the camera probe (§9.5) does move the camera in a headless `-test` run, that closes the loop for goals A/B's visual check without a human playtest; if it does not (e.g. the frontend/bookmark screen ignores `NCamera` entirely), say so and the fallback is the user's own playtest per the original brief.
- `mappings/tree_meshes.csv` leaves `plains`/`farmlands`/`floodplains`/`desert`/`drylands`/`mountains`/`desert_mountains`/`terraced_hills`/`sea`/`coastal_sea` without a mesh (no trees). This is a documented, defensible default (bare/cultivated/underwater terrain), not a data gap — extending it is an art call, not something this lane's evidence settles.
- The standalone entry point `python -m ck2ck3.map.build` never sets `ck3_game_dir` (pre-existing gap, not touched by this lane) — `trees`/`terrain_paint`/the map table silently produce nothing under it; only the CLI (`ck2ck3.steps.map`) wires `ck3_game_dir` correctly. Worth a one-line fix in a future lane if the standalone path is still used for anything.

## Suggested commit message

```
map: colormap resample, tree scatter, terrain-paint material art pass (lane map-colour)

Resamples the CK2 mod's own colormap.dds onto the canvas (uncompressed BGRA8
at 1/4 resolution, matching two shipped total conversions rather than
vanilla's own DXT5 bake); repopulates the 18 vanilla
gfx/map/map_object_data/generated/*.txt tree files lane map-ui emptied,
711,875 of a 729,838-instance target placed; fixes a real bug in
mappings/terrain_paint.csv (forest was painted with taiga's own primary
material) and resolves both flagged judgement calls against vanilla's own
detail_index.tga. Adds docs/evidence/map_colour/ (three region composites)
and scripts/camera_probe.py (the coordinator's in-game camera-placement
check). ci/checks.sh green, pytest 1123, ck3-tiger fatal 0 / error 58
(unchanged baseline).
```
