# Hand-off — lane `heightmap-2x` (2026-09-24)

User decision: *"Go. Same resolution as vanilla. Erosion patterns to
'enhance' it."* `docs/DECISIONS.md`. Full argument and every table:
`docs/step_map_heightmap.md` §2i (ground-distance audit) and §2j (the
axis-aligned hairline defect, found and fixed).

**Status: shipped, all invariants pass, coordinator's wall-concentration
defect is fixed and verified.**

## 1. What changed

`[map.heightmap] resolution_factor = 2` / `tile_size = 65`
(`configs/faerun.toml`). Every `*_px` window/sigma constant the detail,
erosion and lake-to-land passes use — not already expressed in km via
`km_per_px` — now scales with the resolution factor, so it means the same
ground distance at 1× and 2× (full table: §2i):

* `heightmap_erosion.fractal_seed`/`ridged_seed` octave sigmas
* `heightmap_erosion.eroded_relief`'s `erosion_slope_ceiling_steps` cap
  (divided by `f` — the same physical cliff spans `f`× more output pixels)
* `heightmap_detail._carve_rivers`'s width/blur/margin constants
* `heightmap_detail`'s `wall_spread_window_px`/`wall_spread_sigma_px`,
  `bound_window_px`, `source_adaptive_window_px`
* `heightmap.deepen_sea`'s `sea_shelf_px`
* `lake_to_land.inpaint_heights`'s `sigma_px`,
  `lake_to_land.carve_valleys`'s `ring_px`/`ring_max_px`

Two latent bugs the audit found and fixed, both invisible at `f = 1`:

* `lake_to_land.inpaint_heights`/`carve_valleys` index a `heights`-shaped
  (heightmap resolution) array through `ck3_raster`/`water_mask`
  (province-raster resolution) — a shape mismatch at `f > 1`. Fixed with a
  nearest-neighbour upsample, the same convention `heightmap_detail.apply`'s
  own inputs already use.
* `scripts/verify_heightmap_detail_invariants.py` hard-refused any
  `provinces.png` ≠ `heightmap.png` size — correct at `f = 1`, wrong at
  `f = 2` where vanilla itself ships them at different sizes. Now derives
  `resolution_factor` from the ratio and upsamples the province raster once.
* A THIRD, coordinator-adjacent bug: `ck2ck3/steps/map.py::_map_config` is a
  SECOND, independent `HeightmapConfig` builder (the one the real CLI uses)
  from `ck2ck3/map/config.py`'s own — `ship_heightmap_png` (below) was wired
  into the wrong one first and silently had no effect. Fixed; pinned with
  `tests/test_map_heightmap.py::test_map_config_threads_every_heightmap_key_from_the_cli_config`.

**`map_data/heightmap.png` is dropped from the shipped mod**
(`ship_heightmap_png = false`): ~126–137 MB at 2×, over GitHub's 100 MB
limit, and the engine does not read it (`default.map`'s `topology =
"heightmap.heightmap"` names only the packed pair; every `heightmap.png`
string in `ck3.exe` is namespaced `PdxMapEditor`, the map editor's own
packer). `docs/DECISIONS.md` has the full evidence chain.

**`lake_to_land.inpaint_heights` now solves on the holes' own bounding
box**, not the whole canvas — a performance bug the first `f = 2` run
surfaced (400 whole-canvas Gaussian-blur iterations for 34,560 hole px,
~700 s of the first, 1808 s `map` step). Cut the step to ~611 s.

**The coordinator's own catch, fixed**: dense axis-aligned hairline
stripes on every 2× mountain slope, found by looking at a real render. Root
cause and fix in §2j and summarised in §4 below.

## 2. Measured (final, post-fix)

* `map` step: **610.6–638.4 s** (~10.3 min), down from the first (buggy)
  run's **1808.3 s**. Still dominated by the erosion pass itself
  (**454.4–454.6 s**, unaffected by any fix here, 4× its 1× cost by design —
  §2e's own upsample control adds no sharpness, so the pass has to run at
  2×). Not under the 6 min target in the follow-up brief; see §4.
* Peak RSS: **25.46 GB** (`/usr/bin/time -v`, `--steps map` alone, clean
  isolated measurement, two independent samples agree to 0.05%) — the
  wall-spread gate fix does not change memory usage (same arrays, only two
  threshold constants), not re-measured after it. Slightly over the ~24 GB
  flag in the brief; not tiled (§4).
* File sizes: `packed_heightmap.png` **14.5 MB** (down from 43.9 MB before
  the wall-spread fix — a smoother field with far fewer distinct tiles
  compresses much better), `indirection_heightmap.png` 45 KB,
  `heightmap.heightmap` <1 KB (all well under the 95 MB budget);
  `heightmap.png` **not shipped** (see above — a separate
  `--out .../heightmap-2x-verify` build with `ship_heightmap_png=true` was
  made only to run the evidence scripts below). Every other
  `map_data`/`gfx/map` file unchanged in size class from 1×; the largest,
  `watercolor_rgb_waterspec_a.dds` at 54 MB, predates this lane.
* Invariants (`scripts/verify_heightmap_detail_invariants.py`
  `--no-closed-depression`, see §4 for why): **`invariants hold`, exit 0.**
  land/water pin 0 px violations, source bound 0 px below/above (6 px
  window, 2.0× hf RMS), lake_to_land/river_valleys clean, narrow-canyon 0
  regressions (79 pre-existing elsewhere, informational, unrelated to this
  lane), **wall concentration (check 6) now PASSES**: axis/diag k=2 **0.30**
  against source's own 0.25 (threshold 0.60), k=5 **0.55** against source's
  own 0.66 (threshold 1.01) — the output is now at or below the source's own
  concentration, not above it. `resolution_factor` auto-detected correctly
  (16640×13568 vs provinces 8320×6784).
* ck3-tiger: **fatal 0**, 58 error blocks / 62 raw lines — the same accepted
  baseline STATUS.md already documents (41 loc-hash-collision, 14
  wrong-gender, 2 unknown-field, 1 history). No new error class.
  `docs/evidence/tiger_heightmap_2x_fixed_summary.txt` (33 KB extract of the
  15 MB raw report, gitignore-sized, not committed).
* Spectrum vs vanilla (`scripts/heightmap_2x_spectrum.py`,
  `docs/evidence/heightmap_2x/spectrum_fixed.csv`) — **the fix visibly
  improved this too** (the wall spikes were pure high-frequency energy):

  | c/km | 0.05 | 0.10 | 0.15 | 0.20 | 0.25 | 0.30 | 0.35 | 0.40 | 0.50 | 0.60 |
  |---|---|---|---|---|---|---|---|---|---|---|
  | 1× (build 20) | 0.40 | 0.88 | 0.97 | 0.96 | 0.95 | 0.91 | — (Nyquist) | — | — | — |
  | 2× before the wall-spread fix | 0.72 | 0.96 | — | 1.09 | 1.17 | 1.54 | 2.15 | 2.40 | 2.68 | 2.99 |
  | **2× fixed (shipped)** | 0.69 | 0.93 | 1.08 | 1.13 | 1.19 | 1.24 | **1.26** | **1.25** | **1.28** | **1.27** |

  Reaches vanilla's own 0.6 c/km Nyquist (1× physically stops at 0.337) and
  now sits at **~1.1–1.3× vanilla across the whole 0.15–0.6 c/km band** —
  inside or just outside the brief's own ±30 % target the whole way, a very
  different picture from the pre-fix 1.5–3.0× overshoot.
* Shape vs vanilla (`scripts/measure_relief_shape.py --resolution-factor 2`)
  — also improved: drainage density Thay **0.70×** vanilla (was 0.45×
  broken), Spine **0.52×** (was 0.35×); valley cross-section width75/25
  Thay **2.14** (vanilla 1.94–2.37, now inside the range), Spine 1.88.
* Renders (`docs/evidence/heightmap_2x/renders_fixed/`, Thay/Spine/Sword
  Coast at full canvas resolution — **looked at**): the hairline cross-hatch
  is gone on all three; ridges read as continuous natural slopes with real
  texture, comparable sharpness to the broken build, none of the picket-fence
  pattern. Direct visual confirmation the fix holds outside the crop harness
  it was found and tuned on.

## 3. What a reader should run

```
uv run scripts/verify_heightmap_detail_invariants.py /home/cvdbdo/git/paradox/ck3/wt/_out/heightmap-2x-verify --no-closed-depression
scripts/validate_output_mod.sh /home/cvdbdo/git/paradox/ck3/wt/_out/heightmap-2x docs/evidence/tiger_<tag>.txt
uv run scripts/heightmap_2x_spectrum.py <mod>/map_data/heightmap.png --resolution-factor 2 --tag <tag>
uv run scripts/measure_relief_shape.py <mod>/map_data/heightmap.png --resolution-factor 2 --tag <tag>
uv run python scripts/thay_render.py --region {thay,spine,sword_coast} --skip-3d --no-build15 \
    --extra ours=<mod>/map_data/heightmap.png --extra-resolution-factor 2
uv run --with matplotlib python scripts/heightmap_2x_crop.py --region {thay,spine,sword_coast}
    # the fast (~seconds/variant) crop harness this fix was found and tuned with
ci/checks.sh
```

`<mod>` needs `[map.heightmap] ship_heightmap_png = true` at build time for
the first four (they read `heightmap.png` back, not the packed pair) — the
shipped `configs/faerun.toml` has it `false`; flip it, run `--steps map`
into a throwaway `--out`, flip it back. `heightmap_2x_crop.py` needs no such
build: it constructs its own whole-canvas inputs from `topology.bmp` +
`provinces.png`/`common/province_terrain`/`rivers.png` of any already-shipped
2× output (cached once, ~40 s, then seconds per variant).

## 4. Open — everything real, nothing hidden

**Wall concentration — fixed and verified, not merely patched.** §2j has the
full isolation story: `scripts/heightmap_2x_crop.py` (new, ~1 Mpx real-input
crop, seconds per run instead of ~10.5 minutes) ablated pass by pass and
found only swapping Perona-Malik de-terrace for a blind Gaussian removed the
stripes — ridged relief, erosion diffusion, source-adaptive gain and the
source bound all left the artifact byte-for-byte unchanged when disabled.
Root cause: PM's own known 1× staircase-collapse artifact (already in
CLAUDE.md) gets *more* complete with more diffusion steps, and
`deterrace_iterations` scales with the *square* of the already-`f`-scaled
`deterrace_sigma_px` — 2× gets ~4× the 1× iteration count. Wall-spread's own
`window_px`/`sigma_px` were correctly scaled, but its GATE
(`wall_spread_max_ratio`/`source_margin`, dimensionless, deliberately not
scaled) was tuned against 1×'s baseline, where the source's own
concentration ratio sits near 0.5; at 2× a genuine cliff spans more pixels
so the source's own ratio is naturally lower (0.23–0.29 on the three study
regions), and the 1×-tuned gate never fired on this build's own manufactured
walls. Fix: `wall_spread_max_ratio = 0.20`, `source_margin = 0.05` at
`resolution_factor > 1` — an empirical fit via crop-harness sweep, not
re-derived per-`f` from first principles (only `f ∈ {1, 2}` is used
anywhere). Verified three ways: check 6 passes on the real build, three
full-canvas renders show no hairlines, and both the spectrum and drainage
numbers independently improved as a side effect (the wall spikes were
injecting spurious high-frequency energy and disrupting the flow network).

**The FFT "2-px period power" detector the coordinator asked for was tried
and did not discriminate the artefact cleanly** (§2j): neither a 1-D
Nyquist-bin-power ratio nor a 2-D near-Nyquist axis-vs-diagonal energy ratio
separated the broken build from the fixed one — the *source* itself scored
higher on the 2-D version than either. The artefact is a sparse set of
concentrated single-pixel edges, not a periodic signal a whole-field FFT
resolves well against broadband terrain texture. Check 6
(`edge_step_orientation_counts`, direct axis-vs-diagonal edge counting, no
FFT) is the working detector — it is what caught this defect and what
confirms the fix — so no second, weaker metric was added to the invariants
script.

**Not addressed, and why:**

* Closed-depression-excess (check 5, informational only) needs a
  non-iterative reconstruction algorithm before it is usable at
  `resolution_factor = 2` — `relief_pits_common.closed_depression_depth`'s
  `for _ in range(2*width_px+2)` loop is O(width) full-canvas passes, and
  the width itself is now 2× bigger over a 4×-bigger canvas. Currently run
  with `--no-closed-depression`.
* The erosion pass itself (~455 s, 4× its 1× cost by design) is the
  remaining `map`-step cost; a further lane could shard it or port the inner
  loop to `numba`/Cython. **Not tiled here**: the crop harness proves a
  *stateless* pass (`heightmap_detail.apply` on a padded crop) reproduces
  the canvas faithfully, but the erosion loop's own flow-accumulation state
  is explicitly carried *across* iterations over the *whole* array
  (`eroded_relief`'s `carried` accumulator, §2c) — a naive tile split would
  need to re-derive a safe halo width for a state that grows every
  iteration, which is a correctness question this lane did not have budget
  to answer carefully, not just a mechanical rewrite. Flagged, not attempted.
* Peak RSS 25.46 GB (slightly over ~24 GB) is a consequence of the same
  whole-array erosion state; the same tiling work would address both.
* `relief_pits_common`'s research-only windows (`CLIFF_WIDTH_PX`,
  `relief_sharp_common`'s `MOAT_*` constants) were not threaded through —
  informational diagnostics only, not the invariants script's exit code.
* In-game soak/close-zoom check is the coordinator's, per the lane brief.
