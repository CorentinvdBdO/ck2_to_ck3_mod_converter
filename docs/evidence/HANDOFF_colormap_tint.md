# Hand-off: lane `colormap-fix`

Branch `lane/colormap-fix`, worktree `/home/cvdbdo/git/paradox/ck3/wt/colormap-fix`.
Replaces lane `map-colour`'s CK2-colormap resample (found wrong in-game,
`docs/step_map_paint.md` §9.6) with a tint measured from vanilla's own
`colormap.dds`. Full account: `docs/step_map_paint.md` §9.7.

## Files changed

New:
- `scripts/measure_vanilla_colormap_tints.py` — per-material vanilla tint measurement -> `docs/evidence/vanilla_colormap_tints.csv`
- `scripts/measure_vanilla_colormap_blur.py` — vanilla colour autocorrelation length -> `docs/evidence/vanilla_colormap_blur.csv`
- `scripts/build_colormap_tints_csv.py` — generates `mappings/colormap_tints.csv` from the two tables above
- `scripts/verify_colormap_land_water.py` — land/water mean+stddev+saturation of a generated `colormap.dds`, vs. vanilla
- `docs/evidence/vanilla_colormap_tints.csv`, `docs/evidence/vanilla_colormap_blur.csv`
- `mappings/colormap_tints.csv` — CK3 terrain key -> measured tint RGB

Edited:
- `src/ck2ck3/map/colormap.py` — removed `render()` (CK2 resample); added `read_tint_map`, `build_from_terrain` (paints from the same CK2 code grid `terrain_paint` uses, water-mask override, measured-sigma blur). `downsample`/`header`/`save` unchanged.
- `src/ck2ck3/map/build.py` — colormap block now calls `build_from_terrain` on `codes_tgt`/`code_names`/`water_mask` instead of resampling a CK2 file; `keep_codes_tgt` now also fires for `[map] colormap` (previously only `terrain_paint`), and the colormap report gains land/water mean+std.
- `src/ck2ck3/map/config.py` — new `colormap_tints_csv`, `colormap_blur_sigma` fields + loader.
- `src/ck2ck3/steps/map.py` — **bug fix**: `_map_config` never read `colormap`/`colormap_scale`/`colormap_mips` at all, so `configs/faerun.toml`'s toggle was a no-op through the real CLI since lane `map-colour` shipped it. Added those plus the two new keys.
- `configs/faerun.toml` — `[map] colormap = true` (re-enabled), new `colormap_tints_csv`/`colormap_blur_sigma` keys documented.
- `tests/test_map_colormap.py` — removed the two `render()` tests; added tint-map/build-from-terrain/regression-guard tests (12 tests total, was 7).
- `docs/step_map_paint.md` — §9.1 trimmed to point at §9.7 (kept §9.6 as-is); new §9.7.
- `docs/map_fidelity.md` — §4.3's "Colour" bullet marked superseded; new status paragraph.

## Commands and results

- `uv run pytest -q` → **1128 passed**, 0 failures, 0 regressions.
- `bash ci/checks.sh` → **checks green**.
- Full run (`--steps map`, `configs/faerun.toml` with `colormap = true`):
  `uv run ck2ck3 --config configs/faerun.toml --out /home/cvdbdo/git/paradox/ck3/wt/_out/colormap-fix` →
  55 files, 67.0 s (`colormap = false` gives 54 files, ~58-68 s — the colormap
  pass itself is under 1 s of that either way).
- `uv run scripts/verify_colormap_land_water.py /home/cvdbdo/git/paradox/ck3/wt/_out/colormap-fix`:

  | | land | water |
  |---|---|---|
  | mean RGB | 126.7, 125.9, 122.5 | 128.8, 129.8, 128.7 |
  | stddev RGB | 1.2, 2.0, 3.8 | 0.4, 0.5, 0.7 |
  | saturation (max-min) | 4.18 | 1.02 |

  vs. vanilla: land weighted-mean saturation **6.97**, water saturation
  **0.85** — ours is under vanilla on land, within a point on water.
- `colormap.dds`: 2080x1696, 18.81 MB (unchanged size from the old resample; same format).
- ck3-tiger, real run against the fresh map-only output: **fatal 0**, error
  1320 (all `missing-item`, expected noise from a map-only partial mod with
  no `common`/`history`), 0 mentions of `colormap`/`dds` anywhere in the
  report. Tiger's own binary embeds a `tiger_lib::dds` DDS-header reader
  (unlike the TGA pair, which has none), so this is a real "tiger looked and
  found nothing", not "tiger can't look" — noted in §9.7.

## Measurement headlines (`docs/evidence/vanilla_colormap_tints.csv`, 102 rows)

| material | mean RGB | n | note |
|---|---|---|---|
| water (sea_zones+lakes) | 129,130,129 | 8.04M | matches §9.6's own 131,129,131 ocean sample |
| beach_02 | 129,130,129 | 10.55M | coastal transition; near-identical to open water |
| plains_01 | 127,127,126 | 13.0K | our `plains` primary |
| forest_leaf_01 | 128,128,125 | 649K | our `forest` primary |
| desert_rocky | 138,128,115 | 363K | our `desert_mountains` primary |
| desert_wavy_01_larger | 154,138,116 | 406K | most saturated material vanilla paints anywhere |

Blur: vanilla's own 1/e colour-autocorrelation radius is **9 px**
(`docs/evidence/vanilla_colormap_blur.csv`), used directly as the canvas-pixel
Gaussian sigma (our canvas matches vanilla's own km/px by construction).

## What is unverified in game

- Nothing here was checked against a running CK3 — same limitation as lane
  `map-colour` (`docs/step_map_paint.md` §9.5): the headless `-test` harness
  cannot supply input to move the camera, so a screenshot at `In Game` is the
  only way to see whether the tint actually reads correctly over Waterdeep
  now (no green ocean, no washed-out land).
- The camera-probe workflow from §9.5/`scripts/camera_probe.py` is unchanged
  and still the tool to use for that check.
- The blur-sigma equivalence (autocorrelation e-folding radius = Gaussian
  blur sigma) is `assumed`, not proven equal — see §9.7's own caveat.

## Open questions for the coordinator

1. Does the tint read correctly over Waterdeep/Sword Coast in a real
   playtest or camera-probe screenshot (no green ocean, no washed land)?
2. Is a blur sigma of 9 canvas px the right visual scale, or does it need a
   human eye once it's actually on screen (the measurement is grounded, but
   the ACF-to-sigma equivalence is approximate)?
3. `mappings/colormap_tints.csv` is now a second hand-off surface next to
   `mappings/terrain_paint.csv` — worth a note in `CLAUDE.md`'s invariants
   list if a future lane edits terrain keys, so both tables get regenerated
   together (`scripts/build_colormap_tints_csv.py`).

## Suggested commit message(s)

One concern per commit, in order:

1. `map: measure vanilla's own colormap tint per material and blur scale`
   (the two `scripts/measure_*` + their `docs/evidence/*.csv` outputs)
2. `map: build mappings/colormap_tints.csv from the measured tints`
   (`scripts/build_colormap_tints_csv.py` + `mappings/colormap_tints.csv`)
3. `map: replace the CK2-colormap resample with the measured tint`
   (`src/ck2ck3/map/colormap.py`, `build.py`, `config.py`, tests)
4. `map: fix [map] colormap toggle being ignored by the CLI pipeline`
   (`src/ck2ck3/steps/map.py`)
5. `map: re-enable [map] colormap now the tint is within vanilla's range`
   (`configs/faerun.toml`, `scripts/verify_colormap_land_water.py`)
6. `docs: rewrite step_map_paint.md §9 colormap around the tint approach`
   (`docs/step_map_paint.md`, `docs/map_fidelity.md`, this hand-off)

(The coordinator may prefer to squash 1-5 into fewer commits; listed
separately here so each is independently reviewable.)
