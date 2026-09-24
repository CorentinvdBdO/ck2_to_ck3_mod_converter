# Hand-off: lane `relief-paint`

Full writeup: `docs/step_map_paint.md` §11. This file is the checklist a
reviewer/coordinator needs without reading the whole doc.

## What this lane found (measured first, per the brief)

1. **Vanilla does vary paint within a terrain class by relief, but only a
   little at the individual-material level.** `scripts/measure_vanilla_relief_paint.py`
   against vanilla's own `detail_index.tga` + `heightmap.png`:
   slope/curvature/flow/elevation together explain 2-10% of a class's own
   material entropy (mean 2.1%/0.8%/0.4%/3.7% respectively,
   `docs/evidence/vanilla_paint_vs_relief.md`, `verified`). The direction is
   right (`mountains` at high elevation+ridge is 30.8% `snow` against
   9.7-22.0% at lower elevation), the magnitude is small. Vanilla's
   real-world regional material families (`gen_*`/`medi_*`/etc) were
   excluded from the analysis — the first run without that filter was
   contaminated (kept as a documented negative result).
2. **Two applied designs were built, measured, and rejected before the one
   that ships** — see "What was built and rejected" below. This is the
   important part of the hand-off: both failures were caught by measuring
   the actual output, not assumed away.
3. **Vanilla's tree density declines with slope gradually, never a hard
   cutoff.** `scripts/measure_vanilla_tree_slope.py`: relative density peaks
   at 1.20x on gentle slopes, falls to 0.271x on the steepest 0.5% of land,
   never zero. `trees_slope_gate` therefore defaults **off** even though the
   mechanism is implemented and tested.
4. **The heightmap's own shape ceiling is already measured** (cited from
   `docs/step_map_heightmap.md` §2g, not re-derived): gradient kurtosis
   0.44-0.45x vanilla at 1x resolution, ridge share met (1.02-1.04x).
   `resolution_factor = 2` is the identified lever for more; this lane adds
   drainage density (0.38-0.40x vanilla, a new independent finding) and
   valley V/U shape (already close, 0.94-1.0x) as two new,
   resolution-independent numbers (`scripts/measure_relief_shape.py`,
   `docs/evidence/relief_paint/relief_shape.csv`/`.md`).

## What was built and rejected (read this before touching the module)

**v1 — reorder a class's existing 2-3 materials.** Never introduced a new
material, only permuted which weight slot an already-configured material
occupied. **Coordinator review of the renders found it invisible**:
`paintshade_spine_ours.png` differed from the pre-lane render by a mean
absolute pixel value of 0.51/255. Cause: `mappings/terrain_paint.csv`'s
`mountains` row is `mountain_02`/`mountain_02_c`/`mountain_02_d_valleys` —
three bare-rock variants of ONE family — so no permutation of them can ever
paint a green valley or a white crest.

**v2 first cut — substitute a real material per family, chosen
deterministically (argmax of a spatially-smoothed rank).** Fixed the
palette problem (a class can now show any of its 6 measured families) but
introduced a new one: **measured 93% rock on `mountains`** against
vanilla's own real area share of 36% (`scripts/verify_relief_paint_family_shares.py`,
first run). A real vanilla bin is a MIX (e.g. 31% snow / 29% rock / 18%
grass), and an argmax can only ever reproduce the single largest member.

**v2 shipped — stochastic sampling from the measured mix.** Same family
substitution, but the winning family per pixel is drawn by inverse-CDF
against a spatially-coherent uniform field (a Gaussian-blurred
standard-normal noise field pushed through the normal CDF — a Gaussian
copula: exact uniform marginal, spatial correlation length = `sigma_px`),
independently for the primary and secondary channel. Reproduces the whole
measured mix in expectation. **Result: 28/48 (class, family) pairs with
>= 1% vanilla share land within +-30% of vanilla's own measured share**,
up from 8/48 for the argmax cut; `mountains` itself is 5/6 within
tolerance.

**A third measured-and-rejected design decision**: `interior_weight` (a
gate meant to skip active class-boundary blends) was tried at 0.7 and
measured to fire on **0% of the canvas** — §10's own per-class mix caps
primary `detail_intensity` weight at 0.55-0.56 EVERYWHERE, including deep
class interiors, so weight cannot distinguish "near a boundary" from "this
class's own 3-material split". Default is now `0.0` (apply everywhere).

**Round 2 — coordinator flagged snow/rock on flat lowland forest, fixed by
per-class relative relief + a physical gate (`docs/step_map_paint.md`
§11.3d).** The v2-shipped design above still binned `elevation`,
`slope` and `curvature` on **whole-map** terciles/percentiles, so a
lowland-forest class's own rare "high" pixels (relative to itself) were
mislabelled "high" by the WHOLE MAP's scale, and vanilla's measured
conditional has a small non-zero rock/snow share there — sampled onto
genuinely flat, low ground. Fixed by (1) `elevation_bin` from
`local_relief = height - gaussian_filter(height, 24px)`, binned per-CLASS,
never whole-map; (2) `slope`/`curvature` on a meso-scale (`sigma=24px`)
height field against FIXED, vanilla-measured absolute cutoffs (not a
per-map percentile, so a rougher map can't call its own average "steep");
(3) `apply_physical_family_gate` forces rock/snow probability to exactly 0
when `slope_bin==0 AND elev_bin==0`, renormalising the rest. Verified
directly on the regenerated `paintshade_spine_ours.png`: no grey/white on
the flat lowland, mountains unchanged. Cost: the whole-map area-share
check moved from 28/48 to **21/48** within +-30% — the gate trades some
aggregate-share agreement (which the check can't break down by bin) for
correctness on the specific flagged failure mode.

**Round 3 — coordinator flagged speckle on flat `taiga` AND "camouflage"
on `sword_coast`'s flat plains/forest, fixed by restricting relief paint
to classes/pixels where relief actually carries signal
(`docs/step_map_paint.md` §11.3e).** Round 2 fixed the specific flat-
lowland-forest defect it targeted, but the render still showed the same
underlying problem on OTHER flat classes it hadn't touched: `taiga` kept
white/grey speckle, and `sword_coast` (flat plains/forest) turned into
independent-per-pixel grass/forest/soil/other noise — worse than build
17/19's uniform lowland. Root cause: this module's own first measurement
says relief explains only 2-8% of a class's in-class material entropy —
an average dominated by wide-relief-range classes (`mountains`, `hills`);
on a genuinely flat class the measured conditional is close to that
class's own unconditional mix, so sampling from it per pixel is close to
sampling noise. Fixed by a new config allow-list, `[map]
relief_paint_classes` (default `mountains`/`desert_mountains`/`hills`),
plus `ck2ck3.map.relief_paint.build_class_eligible_mask` requiring
`slope_bin > 0 OR elev_bin > 0` even inside those classes — every other
class/pixel is now left **byte-identical** to §10's own output, asserted
by a dedicated test
(`test_apply_relief_family_paint_leaves_excluded_classes_byte_identical`).
Verified on all three regenerated renders: `sword_coast`'s and Thay's/
Spine's flat ground is clean, mountains/hills unchanged. Cost: relief
paint now touches 25.9% of land (was 76.6%), `detail_index.tga` dropped to
29 MB (was 46 MB), and the whole-map area-share check dropped to 10/48 —
expected, since 12 of 15 painted classes are now untouched by design; see
§11.3e for why that specific number is no longer the right instrument for
those classes.

## What was built (final)

- `src/ck2ck3/map/relief_paint.py`: `apply_relief_family_paint` -- per
  pixel, samples a material family from the class's measured
  relief-conditioned mix (spatially coherent), then substitutes that
  class's own measured top material for that family into
  `detail_index` primary/secondary. Never changes a weight value.
- `mappings/relief_paint.csv` (per-bin family MIX, not just rank —
  `scripts/build_relief_paint_csv.py`), `mappings/relief_paint_family_materials.csv`
  (per-class, per-family top material, interior pixels only),
  `mappings/paint_material_categories.csv` (material -> family) —
  all three from `scripts/measure_vanilla_relief_paint.py`.
- `relief_paint.py` module constants (not config, baked from measurement):
  `LOCAL_RELIEF_SIGMA_PX = 24`, `VANILLA_SLOPE_CUTOFFS = (21.13, 58.62)`,
  `VANILLA_CURVATURE_CUTOFFS = (-0.676, 0.407)` — vanilla's own meso-scale
  slope/curvature tercile cutoffs, printed by
  `scripts/measure_vanilla_relief_paint.py`, re-run and re-baked if the
  measurement crops or heightmap scale ever change.
- `[map] relief_paint` (default **true**), `relief_paint_csv`,
  `relief_paint_family_csv`, `relief_paint_categories_csv`,
  `relief_paint_sigma_px` (default `4.5`, vanilla's own measured patch
  scale), `relief_paint_interior_weight` (default `0.0`),
  `relief_paint_classes` (default `("mountains", "desert_mountains",
  "hills")`, round 3 — §11.3e), `trees_slope_gate`
  (default `false`), `trees_slope_gate_percentile` (default `95.0`) — read
  by BOTH `ck2ck3.map.config.load` and `ck2ck3.steps.map._map_config`
  (`tests/test_map_relief_paint.py`, the silent-no-op bug check).
- `relief_paint.py::build_class_eligible_mask` (round 3, new): class
  allow-list + `slope_bin > 0 OR elev_bin > 0` within-class threshold,
  ANDed into `apply_relief_family_paint`'s `eligible_mask` parameter — a
  pixel outside it is left completely untouched, index AND intensity.
- Tree scatter eligibility gated on land slope when `trees_slope_gate` is on
  (`ck2ck3.map.relief_paint.compute_slope_percentile_mask`, `build.py`).
- `scripts/relief_paint_render.py` (copied from sibling lane `thay-relief`'s branch,
  which had not merged when this lane started — the coordinator reconciles
  the two copies on merge): added `--paint-mod DIR` / `--categories-csv`, a
  paint-colour hillshade drape (`save_paintshade`).
- `scripts/verify_relief_paint_family_shares.py` (new): the per-class,
  per-family area-share check against vanilla, +-30% tolerance.
- Tests: `tests/test_map_relief_paint.py` (20 cases: readers for both the
  rank and shares tables, bin computation including the per-class-not-
  whole-map elevation test, the physical-gate veto test, the
  stochastic-sampling invariants including a reproduces-the-mix-in-
  expectation test and a sigma-controls-patch-size test, both
  config-builder silent-no-op checks, the round-3 class-eligible-mask test
  and the byte-identical-on-excluded-classes test).

## Bug found and fixed during verification

`build.py`'s new `relief_slope_bin`/`trees_steep_mask` locals were only
initialised inside the `if not skip_images:` block, but the tree-scatter
code that reads `trees_steep_mask` runs regardless of `skip_images`
(text-only output) — `UnboundLocalError` on the `skip_images=True` path,
caught by `tests/test_map_baronies_faerun.py` (7 errors). Fixed by moving
the `None` defaults above the `if not skip_images:` guard.

## Verification

- **Visual, checked directly, from the FINAL build** (coordinator
  instruction: look at the renders before reporting, and regenerate every
  render from the final output — done, all three regions): mountains/hills
  everywhere still show grey rock on escarpment/cliff faces, green
  grass/forest patches, tan/beige on plateaus, small white patches at the
  highest points, unchanged from round 2. **Round 3's own fix, verified**:
  `sword_coast`'s flat plains/forest is now clean and uniform (the
  "camouflage" is gone), Thay's crater floor and Spine's lowland forest are
  clean (no speckle on `taiga` or any other flat class) — all three now
  read like build 17/19's own lowland paint, exactly as asked.
- `uv run pytest`: **1370 passed**, 0 failed.
- `ci/checks.sh`: **green** (syntax, compileall, pytest, `ck2ck3
  --list-steps`, `overrides/loc_keys.csv` fresh, docs present).
- ck3-tiger (`docs/evidence/tiger_relief_paint.txt`, map-only descriptor,
  re-run on the final build): **fatal 0**, 1326 error/fatal (all `title
  d_x not defined` — expected, no `titles` step run in this map-only
  build), 322 `warning(rivers)` (pre-existing). Nothing about
  `detail_index`, `detail_intensity`, `relief_paint` or
  `materials.settings`.
- paint sizes (final build): `detail_index.tga` **29 MB** (down from round
  2's 46 MB), `detail_intensity.tga` **24 MB** — both well under the
  100 MB limit.
- final real run, `[map] relief_paint = true`, `trees_slope_gate = true`
  (`docs/evidence/relief_paint_build.log`): relief paint changed
  **6,842,018 land px (25.9%)** primary material (down from round 2's
  20,262,569 px, 76.6% — the intended effect of the class/threshold
  restriction), of **7,836,769 px (29.6% of land) eligible**; trees slope
  gate excluded **55,465 px**.
- `docs/evidence/relief_paint/relief_paint_family_share_check.csv`: the
  per-(class,family) area-share numbers behind the **10/48** headline
  (down from 21/48 pre-round-3 — see the round-3 note above: 12 of 15
  painted classes are now, by design, untouched by relief paint, so their
  aggregate area-share necessarily disagrees with vanilla's much richer
  real palette; `mountains` (3/6) and `hills` (2/6) are the numbers that
  still mean what they used to).

## Open, for the coordinator

- `relief_paint` now defaults **true** (was off pending this exact check).
  `trees_slope_gate` still defaults **off** — vanilla's own density decline
  is gradual, not a cutoff, so a hard percentile gate is a coarser model
  than the measurement supports; the mechanism is there for a future graded
  multiplier.
- 38/48 (class, family) pairs are outside +-30% post-round-3, but 12 of the
  15 painted classes are now, by design, entirely untouched by relief
  paint (`relief_paint_classes` excludes them) — their disagreement with
  vanilla's real richer palette is expected and not actionable from inside
  this module; §10's own `mappings/terrain_paint.csv` mix is what would
  need to change for those classes, out of this lane's scope. Within the
  three still-eligible classes, `mountains` is 3/6 and `hills` 2/6 within
  tolerance — the only rows this check still says anything useful about.
- `desert_mountains` never appears in the family-share check output at
  all (no rows >= 1% vanilla area share) — `assumed`: either Faerun has
  very little land of that class, or its own configured mix already
  concentrates on one family; not investigated further, flagged for
  whoever picks this back up.
- `resolution_factor = 2` is now recommended by TWO independent lines of
  evidence (gradient kurtosis §2g, this lane's citation) as the only lever
  past the measured 1x heightmap-shape ceiling; its cost (182 MB pair,
  348 s, 19.8 GB RSS) is unchanged from §2e. This lane's own new finding —
  drainage density 0.38-0.40x vanilla — is a SEPARATE, resolution-independent
  lead for lane `thay-relief` (erosion catchment size, not resolution).
