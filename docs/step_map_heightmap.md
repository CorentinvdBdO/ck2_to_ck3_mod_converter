# Step `map`, heightmap half: CK2 topology → CK3 16-bit terrain

**Question this answers.** `heightmap.png` is a faithful rescale of CK2's
8-bit `topology.bmp`, but faithful is not enough: it reads as terraced
contour lines instead of terrain. What does the converter do about it, and
what does it guarantee stays true no matter what?

**Answer.** Two stages, always in this order:

1. **Rescale** (`ck2ck3.map.heightmap`) — CK2's 8-bit `topology.bmp` through a
   piecewise-linear curve pinned at `0 → 0`, `ck2_sea_level → ck3_water_level`,
   `255 → ck3_max_level`, LANCZOS-resized onto the canvas. This alone is
   enough to boot a coastline-correct, playable map (`docs/map_scale.md` §4).
2. **Detail synthesis**, optional, `[map] heightmap_detail = true`
   (`ck2ck3.map.heightmap_detail`) — a deterministic, seeded pass that adds
   vanilla-matched high-frequency detail on top of the rescale, without ever
   moving a coastline or a sea pixel. Off by default; `configs/faerun.toml`
   turns it on.

Then the packed pair (`ck2ck3.map.packed_heightmap`,
`docs/formats_packed_heightmap.md`) is (re-)built from whichever heights array
came out of step 2, since that is what the game actually loads.

Full method and the vanilla numbers this is matched against:
`docs/map_fidelity.md` §1.2 (why the plain rescale is flat) and §4.2 (the
prototype this module implements, Sword Coast evidence).

Reproduce: `uv run ck2ck3 --config configs/faerun.toml --steps map`.
Unit tests: `tests/test_map_heightmap.py` (the rescale),
`tests/test_map_heightmap_detail.py` (the detail pass, synthetic islands).

---

## 1. Why the plain rescale is not enough

CK2's `topology.bmp` is 8-bit: 256 possible source values. After the transfer
curve, land only spans ~160 of them, 277 sixteen-bit levels apart. On Faerûn
that measures as **212 distinct height values** on the whole map, against
vanilla's **31,516** (`docs/map_fidelity.md` §1.2, `verified`,
`scripts/map_fidelity_heightmap.py`). It is not simply "flat": the terrace
risers themselves are extra high-frequency energy the real terrain never had,
so the plain rescale's high-pass RMS (319) is actually *higher* than
vanilla's (283) — it is the wrong kind of detail, not too little of it.

## 2. The detail pass — four steps, `ck2ck3.map.heightmap_detail.apply`

Same four passes as the prototype (`scripts/prototype_heightmap_detail.py`,
`docs/map_fidelity.md` §4.2), vectorised over the whole canvas rather than a
crop:

1. **De-terrace** — removes the transfer curve's risers on land only.
   Two modes, `heightmap_detail_deterrace_mode`: the original blind Gaussian
   (`"gaussian"`) and the cliff-aware diffusion that is now the default
   (`"cliff_aware"`, **§2b**). Legitimate either way because the real signal
   is band-limited to the CK2 source's own Nyquist frequency
   (`docs/map_scale.md`), so nothing true is lost — but only the cliff-aware
   one keeps a *real* cliff, which is a jump of several risers at once.
2. **Spectral fill** — the shortfall of our own radial land spectrum against
   vanilla's, injected as noise shaped to exactly that deficit. Two targets,
   `heightmap_detail_target_mode`: a single fitted power law
   (`"power_law"`, amplitude ∝ f^`heightmap_detail_spectral_slope`) and
   vanilla's own measured curve (`"vanilla_curve"`, the default, **§2c**).
   The noise itself is either white (`heightmap_detail_relief_mode =
   "isotropic"`) or an eroded, dendritic field (`"eroded"`, the default,
   **§2c**). The noise is then scaled **per pixel** so every CK3 terrain
   class (mountains, plains, taiga, …) reaches its own measured vanilla
   high-frequency amplitude — `DEFAULT_HF_TARGETS` in
   `ck2ck3/map/config.py`, baked in from
   `docs/evidence/map_fidelity/hf_by_terrain.csv` so a normal run has no
   dependency on a research-evidence file at conversion time. Frequencies
   below `KEEP_STRUCTURE_BELOW_KM` (0.01 cycles/km) are never touched, so the
   CK2 source's own real mountains and valleys survive untouched — this pass
   only ever *adds* detail the source never had the bit depth to carry.
3. **River valleys** — a Gaussian cross-section is carved along the traced
   `rivers.png` body pixels (indices 3–11), depth `heightmap_detail_river_depth`
   (default 900 sixteen-bit levels) at the centreline, width from the CK2
   river-width index. Subtracted on **land only**, so a river valley can only
   ever cut a pixel lower than what passes 1–2 already built — it never
   raises one above its neighbours.
4. **Coast smoothing** — land within `heightmap_detail_coast_smooth_px`
   (default 4 canvas px) of the shoreline is blended toward the water level,
   so beaches stay flat instead of gaining mountain-scale noise right at the
   waterline.

---

## 2b. Cliff-aware de-terrace (`heightmap_detail_deterrace_mode`)

**The problem.** An 8-bit source through the transfer curve steps by exactly
`(49205 − 4883) / 160 = 277.0125` sixteen-bit levels per source value, so
*every* slope on the rescaled map is a staircase. A Gaussian cannot tell that
staircase from a real escarpment, because it does not look at the size of the
step it is smoothing. Thay's terraced plateaus and the Spine of the World are
where the difference shows: over the two study crops (located by
`scripts/heightmap_erosion_crops.py` from `k_thay` and
`k_spine_of_the_world`), **15.4 %** and **10.3 %** of adjacent land pixel
pairs jump ≥ 1.5 quantisation steps, and the largest is **14 steps**
(`verified`).

**The pass.** Perona–Malik anisotropic diffusion. The flux between two
neighbouring pixels is weighted `exp(−(Δh / cliff_step)²)` with
`heightmap_detail_cliff_step_levels` = 415.5 (1.5 × 277.0125): a one-step
riser diffuses at 64 % rate, a two-step at 17 %, a three-step at 2 %. In a
flat region the scheme *is* the heat equation, so *n* steps of size λ equal a
Gaussian of σ = √(2λn) — the iteration count is derived from
`heightmap_detail_deterrace_sigma_px`, which is why the two modes are
comparable at all. λ = 0.18 (the 4-point Laplacian is stable to 0.25); at
σ = 2.2 that is 13 steps, 3.7 s on the full canvas.

**Measured** (`docs/evidence/heightmap_erosion/cliff_survival.csv`,
`scripts/heightmap_erosion_evidence.py`, `verified`). Pass 1 **in
isolation** — both filters against the same plain rescale, fraction of
adjacent-pair step amplitude surviving:

| crop | | Gaussian σ 1.6 (shipped) | cliff-aware σ 2.2 |
|---|---|---|---|
| Thay | ≥ 2-step cliff kept | 0.692 | **1.133** |
| Thay | 1-step riser removed | 0.431 | **0.640** |
| Spine of the World | ≥ 2-step cliff kept | 0.703 | **1.122** |
| Spine of the World | 1-step riser removed | 0.507 | **0.648** |

The cliff-aware mode is better on *both* axes: it keeps 1.6 × as much of the
cliff and removes half again as much of the artefact. Slightly over 1.0 is
real and expected — Perona–Malik sharpens an edge it decides not to cross
(the classic backward-diffusion term), and the tests bound it at 1.25 so a
future sigma change cannot turn that into a cartoon.

The same CSV also carries the two *finished* maps (0.87 / 0.97 for this
build, 0.84 / 0.83 for the shipped one). Those columns are the weaker
measurement and are only there for continuity: the synthesised detail lands
on the very pixel pairs the metric reads, so a bigger fill lowers the
apparent survival whatever pass 1 did. The isolated columns are what §2b
claims.

**Scope, honestly.** Lane `relief-report` measured the same thing a different
way and found the Gaussian costs *sharpness*, not amplitude: it keeps 67 % of
the one-pixel step on Thay's steepest edges and 98 % of the drop over 34 km
(`docs/evidence/report_map_paint/thay_cliffs.csv`, `thay_steps.csv`,
`verified`). Both are true — the 34 km drop is a macro fact no local filter
touches, and the one-pixel step is what a player sees at close zoom. This
pass is a cheap win on the second, not a rescue of the first. **A smaller
sigma is not the fix for anything**: at σ = 1.6 the cliff-aware mode keeps
1.079 of the cliff but removes only 0.570 of the riser on Thay, against 0.640
at 2.2 and 0.691 at 3.0, and a smaller sigma leaves *more* terrace energy in
the band §2c is trying to fill.

## 2c. Structured relief and the fill target (`heightmap_detail_relief_mode`, `heightmap_detail_target_mode`)

Three defects of the shipped fill, all `verified`, all fixed here:

**(a) The target was an extrapolated law.** Vanilla's land spectrum is *not*
a clean f^−2.0 over the whole range: fitted over 0.02–0.4 cycles/km its
exponent is **−2.195**, and it flattens near its own Nyquist. Fitting f^−2.0
to our well-resolved 0.004–0.03 band and extrapolating over-fills 0.03–0.1
and starves everything above. `target_mode = "vanilla_curve"` replaces it
with vanilla's own measured radial land spectrum, `VANILLA_LAND_SPECTRUM` in
`heightmap_detail.py`, baked in from
`docs/evidence/report_map_paint/spectrum.csv` (48 all-land 256×256 patches of
`game/map_data/heightmap.png`) for the same reason `DEFAULT_HF_TARGETS` is
baked in: a conversion run must not read a research evidence file. It is
anchored to *our* map by the median ratio over 0.015–0.03 cycles/km, the band
where the two already agree (0.99× at 0.02), so the pass imports vanilla's
*shape*, never Europe's relief.

**(b) The shortfall was measured on the wrong thing.** The whole-canvas FFT
is dominated by coastlines (a 4884-level step) and by the padding ocean, so
it reported 0.05 cycles/km as already full for a map whose *interior*
carried 42 % of vanilla there. `_interior_patch_spectrum` now measures
`have` on 48 all-land 256 px patches — the same geometry
`scripts/report_map_paint_plots.py` and `scripts/heightmap_erosion_evidence.py`
measure with, so the number the pass aims at and the number the evidence
reports are one measurement. With no all-land patch (every synthetic
fixture, any map with no interior) it falls back to the canvas spectrum.

**(c) The noise had no shape.** `relief_mode = "eroded"`
(`ck2ck3.map.heightmap_erosion.eroded_relief`) seeds the de-terraced surface
with band-limited fractal noise and runs a short landscape-evolution model
over the pair, so the drainage the CK2 source really does carry directs the
result:

* **flow accumulation** by relaxation, not by a sorted topological sweep —
  `A ← 1 + Σⱼ w(j→p)·Aⱼ`, eight shifted multiply-adds per pass, multiple-flow
  weights ∝ slope^4. The catchment is carried between steps, so
  `erosion_iterations × erosion_accum_iterations` = 16 × 3 propagates 48 px
  ≈ 71 km. Bounded on purpose: the structure being synthesised lives at
  1–20 km (2–14 canvas px), and a bounded catchment is what stops the erosion
  re-cutting the CK2 source's own macro valleys;
* **stream-power incision** `dz = −K·(A/A_ref)^0.5·S`, `A_ref` the 92nd
  percentile of accumulation over land so the law is scale-free, capped at
  half the local steepest descent so a pixel can never be cut below the
  neighbour it drains into;
* **uniform uplift** equal to the mean incision, added back every step, so
  incision *redistributes* relief instead of draining it — without it a short
  run just lowers everything and the high-pass throws the result away;
* **hillslope diffusion**, one linear Laplacian step per iteration.

The field is then high-passed and handed to the spectral pass as the *phase*
source. The deficit is imposed on it as a radial **equaliser** (its own radial
amplitude divided out, the target multiplied in, capped at 8× the median gain
so an empty bin cannot ring): a radial filter changes no phase, so the valleys
and ridges survive while the spectrum lands exactly where the isotropic
version put it. The per-terrain gain (`DEFAULT_HF_TARGETS`) is untouched, so
the amplitude calibration is the same one figure 1 of `docs/report_map_paint.md`
checks.

**(e) The two calibrations were cancelling each other out.** The original
amplitude rule is one scalar per terrain class,
`need = sqrt(want² − have²)`, where `have` is the class's own RMS under a
~3 km high-pass of the de-terraced base. That rule reads *any* residual
broadband energy as "detail already present" — and §2b's whole purpose is to
keep broadband edge energy. Measured on Faerûn the two halves of this lane
therefore fought: with the cliff-aware de-terrace in front of it the rule
decided almost no fill was needed and the interior band came out
0.40/0.53/0.87/1.11/2.08 × vanilla at 0.05/0.1/0.15/0.2/0.3 cycles/km —
i.e. still the *base's* shape, tilted, with the fill contributing little.
`gain_mode = "deficit"` (default) breaks the tie: the absolute level comes
from the per-frequency shortfall, matched by measuring the shaped field's own
interior-patch spectrum against `deficit_rad` over 0.05–0.3 cycles/km (the
same operator on both sides, so no FFT-normalisation algebra to get wrong),
and `DEFAULT_HF_TARGETS` is applied as a modulation whose land mean is 1 —
keeping desert_mountains at 4.6 × taiga, which is what that table is for.
With no all-land interior patch (a synthetic fixture, a small map, an
archipelago) there is nothing to match against and the pass falls back to
the old per-class rule.

**(d) The fill has to fit in the headroom.** Lane `relief-report` measured
that the shipped fill pushed **8.193 % of all land** (2,166,924 px, mean 3485
levels destroyed, median 113 km from any water) below the water level, where
the closing `np.clip` put it back on `water_level + 1`
(`docs/evidence/report_map_paint/clamp_floor.csv`). A clamp is not a bound.
`_limit_excursion` now saturates the synthesised offset into the headroom the
pixel actually has — `tanh(|δ| / room)·room`, downward against
`water_level + 1` and upward against `max_level` — before the clip ever runs.
`tanh` rather than `min` because a hard bound prints the shape of the floor
into the map as a plateau, which is the artefact being removed; where |δ| is
small against the headroom it is the identity to first order.

### §2c measured

Radial amplitude on 48 all-land 256 × 256 interior patches, the same patch
geometry and the same estimator `scripts/report_map_paint_plots.py` uses, all
maps on the same patches (`docs/evidence/heightmap_erosion/spectrum_bands.csv`,
`verified`). The figure is the ratio to vanilla CK3's own land spectrum:

| cycles/km | km | plain rescale | shipped (Gaussian + isotropic) | **this build** |
|---|---|---|---|---|
| 0.05 | 20 | 0.42 | 0.54 | **1.13** |
| 0.10 | 10 | 0.70 | 0.37 | **1.16** |
| 0.15 | 6.7 | 1.23 | 0.26 | **1.00** |
| 0.20 | 5.0 | 1.35 | 0.23 | **0.91** |
| 0.30 | 3.3 | 1.50 | 0.21 | **2.05** |

Four of the five points are inside ±30 % of vanilla; **0.3 cycles/km is
not** — it is 2.05 ×, and the plain rescale is already 1.50 × there, so this
is the de-terraced base's own residual, not the fill (the deficit at
0.3 cycles/km is zero, because `have` exceeds the target). 0.3 cycles/km is
3.3 km, i.e. 2.2 canvas pixels: it is where the cliffs §2b deliberately
keeps live, and cutting it means giving them back. Left as it is, flagged.

**The rivers pass and the erosion agree.** They could have fought: pass 3
carves `rivers.png` where CK2 says a river is, and the erosion routes water
where *our* surface says it flows. Measured on the finished maps
(`docs/evidence/heightmap_erosion/river_alignment.csv`, `verified`), over all
87,854 traced river-body land pixels, the eroded build puts **90.5 %** of
them below their own 9 km surroundings against the shipped build's 89.5 %,
and river pixels are **7.4 ×** over-represented in the top 1 % of flow
accumulation against 5.5 %. The erosion pulls drainage toward the rivers
rather than away from them. ck3-tiger's own `warning(rivers)` count is
unchanged at 319, the same figure every build since 2026-09-07 reports.

Other measured effects of the pass, on the whole map:

* **land on the `water_level + 1` clamp floor: 8.193 % → 0.349 %**
  (`verified`, the `map` step's own summary line in
  `docs/evidence/last_run.md`; the target was < 0.5 %);
* land p95 25,340 → 23,010 and p99 37,827 → 31,883, against the plain
  rescale's own 23,166 — the macro tails move far less than the shipped
  build moved them;
* distinct 16-bit values 44,522 → ~42,000 (vanilla 31,516);
* the detail pass costs **10.9 s → ≈52 s**, and the whole `map` step
  61 s → 103 s.

## 3. Invariants — what cannot break, and why it cannot

* **Every water pixel is returned byte-identical to the plain rescale.**
  `land_mask` comes from the province raster plus `default.map`'s
  `sea_zones`/lake data (`Ck3Province.is_water`: sea, lake, or river-type
  province, the padding ocean included) — not a topology-value threshold —
  and `apply()` never writes a value at a `land_mask=False` pixel; the sea
  pin and every coastline hold by construction, not by a clamp.
* **Every land pixel ends strictly above `water_level` and at or below
  `max_level`.** The last step of `apply()` is
  `np.clip(land_values, water_level + 1, max_level)`, after all four passes —
  but that clip is now a *backstop*, not the mechanism: §2c(d) saturates the
  synthesised offset into the headroom each pixel has, so the clip catches
  0.349 % of land rather than 8.193 %. `land_pct_on_clamp_floor` is in the
  stats dict and in the `map` step's summary for exactly this reason: if it
  climbs, the fill is writing terrain the map has no room for.
* **Rivers stay in valleys.** Pass 3 only subtracts, and only on land: a
  river pixel can end lower than the plain rescale gave it, never higher.
* **Deterministic.** The same inputs and the same
  `heightmap_detail_seed` always produce the same output array
  (`numpy.random.default_rng(seed)`, no other source of randomness).

## 4. Wiring into `ck2ck3.map.build`

`terrain_code` (per-pixel CK3 terrain key, for the per-terrain gain) is built
from the **existing** per-province majority-vote result
(`terrain.majority_terrain_codes`'s `by_province`, the same table
`common/province_terrain` is written from) indexed through the province
raster — no second pixel-level terrain classification, and no dependency on
the terrain-paint lane's own work. `river_body`/`river_width_index` reuse the
same traced `rivers.png` array the `map_data/rivers.png` writer produces (the
trace is computed once, before the heightmap, and reused for both). At
`[map.heightmap] resolution_factor > 1` these canvas-resolution arrays are
nearest-neighbour upsampled to the heightmap's own resolution first
(`ck2ck3.map.build._nn_upsample`).

## 5. Config (`[map]`, flat keys — see `configs/faerun.toml`)

| key | default | meaning |
|---|---|---|
| `heightmap_detail` | `false` | turn the pass on |
| `heightmap_detail_seed` | `1357` | deterministic RNG seed |
| `heightmap_detail_deterrace_mode` | `"cliff_aware"` | pass 1 filter: `"cliff_aware"` (§2b) or `"gaussian"` (the shipped blur) |
| `heightmap_detail_deterrace_sigma_px` | `2.2` | pass 1 blur, in the flat-region sense for both modes (`1.6` with `"gaussian"` reproduces the shipped build) |
| `heightmap_detail_cliff_step_levels` | `415.5` | pass 1 flux half-width, 1.5 × the 277-level quantisation step |
| `heightmap_detail_relief_mode` | `"eroded"` | pass 2 phase source: `"eroded"` (§2c) or `"isotropic"` (white noise) |
| `heightmap_detail_erosion_iterations` | `16` | pass 2 landscape-evolution steps |
| `heightmap_detail_erosion_accum_iterations` | `3` | pass 2 flow-accumulation relaxations per step (carried between steps) |
| `heightmap_detail_erosion_seed_amplitude` | `300.0` | pass 2 initial fractal relief RMS |
| `heightmap_detail_erosion_mfd_exponent` | `4.0` | pass 2 multiple-flow-direction slope exponent |
| `heightmap_detail_erosion_incision` | `0.5` | pass 2 stream-power K |
| `heightmap_detail_erosion_diffusion` | `0.06` | pass 2 hillslope diffusion per step |
| `heightmap_detail_target_mode` | `"vanilla_curve"` | pass 2 fill target: vanilla's measured curve (§2c) or `"power_law"` |
| `heightmap_detail_target_gain` | `1.0` | multiplier on that curve before the shortfall is taken |
| `heightmap_detail_gain_mode` | `"deficit"` | pass 2 amplitude authority: the measured shortfall with the terrain table as a relative modulation (§2c e), or `"hf_target"`, the original per-class `sqrt(want² − have²)` |
| `heightmap_detail_spectral_slope` | `-2.0` | pass 2 power-law exponent — only read by `"power_law"` |
| `heightmap_detail_gain_blur_px` | `6.0` | pass 2 amplitude-seam blur |
| `heightmap_detail_river_depth` | `900.0` | pass 3 valley depth |
| `heightmap_detail_coast_smooth_px` | `4.0` | pass 4 beach-flattening distance |
| `heightmap_detail_hf_targets` | (baked-in table) | inline TOML table to override the per-terrain HF RMS targets |

A `[map] heightmap_detail_*` sub-**table** of that name is not used — it
would collide with the boolean flag, the same reason the `scale` keys are
flat (see the comment in `configs/faerun.toml`). The standalone
`ck2ck3.map.build` entry point (`configs/faerun_map.toml`) instead nests a
real `[heightmap_detail]` table, since it has no `[map]` wrapper to collide
with.

**Every key here is proved read, not assumed read.** A key under the wrong
header is silently ignored (it has happened), so two things guard it:
`tests/test_map_heightmap_detail.py::test_every_new_flat_map_key_reaches_the_config`
sets each one to a non-default value and asserts it arrives (and the same for
the nested table the standalone entry point uses), and the `map` step now
names the switched modes and the clamp-floor figure in its own summary line,
so `docs/evidence/last_run.md` records what the run actually used.

## 6. Cost

* Packing efficiency: the packed-heightmap tile deduper (`docs/formats_packed_heightmap.md`)
  dedupes identical tiles far better with 212 distinct values than with the
  tens of thousands the detail pass adds, so `packed_heightmap.png` grows —
  measured size in `docs/evidence/HANDOFF_map_heightmap_detail.md`.
* Runtime: three whole-canvas FFT2 calls (spectral fit, noise synthesis) plus
  48 patch FFTs for the interior spectrum, a handful of Gaussian filters and
  two `distance_transform_edt` calls — all vectorised, no per-pixel Python
  loop. The erosion adds a loop of 16 iterations, each eight shifted
  multiply-adds per flow-accumulation pass; it is memory-bandwidth bound on a
  226 MB float32 canvas, which is why the shifts are slice arithmetic rather
  than `np.roll` and why `A**4` is two multiplications rather than
  `np.power`. Measured on Faerûn: the pass went from **10.9 s** (Gaussian +
  isotropic) to **≈55 s**, inside the ~2.5 min budget. The whole `map` step
  is 61 s → 107 s.

## 7. What this pass does not fix

**Half of vanilla's spatial bandwidth, by construction.** We ship a 1×
heightmap, so our Nyquist is 0.337 cycles/km against vanilla's 0.674
(`verified`). No detail pass reaches past it; `[map.heightmap]
resolution_factor = 2` is a one-line change and a large one in bytes.

**The macro tails still move, and the reason was misdiagnosed.** The 2026-09-10
note in this section said coast smoothing pulled land p01/p05 down to the
water level. That was wrong: it was the **closing clamp**. The fill wrote
below sea level over 8.193 % of all land — median 113 km from any water, so
nothing to do with the coast pass — and `np.clip` put every one of those
pixels on `water_level + 1` (`docs/evidence/report_map_paint/clamp_floor.csv`,
lane `relief-report`, `verified`). §2c(d) bounds the excursion instead, and
the figure is now **0.392 %** of land on the floor. The upper tail is also
much closer to the source than the shipped build's: land p95 25,340 → 23,010
against the plain rescale's 23,166, p99 37,827 → 31,883.

**0.3 cycles/km is still 2.05 × vanilla.** Everything from 0.05 to 0.2 is
inside ±30 % (§2c measured); the top of the band is not, and the fill is not
what put it there — the de-terraced base alone is 1.5 × vanilla at
3.3 km wavelength. Removing it means a stronger de-terrace, which is
precisely the cliff amplitude §2b exists to keep. That trade is a look call,
not a measurement.

**`fill_gain = 0.70` is measured, not derived.** The absolute amplitude is
matched on the shaped field, but the per-terrain envelope (a spatial
multiply, so a convolution in frequency), the river carve and the headroom
`tanh` all touch it afterwards and together leave the finished map above the
target. 0.70 is the number that brings 0.05–0.2 cycles/km inside ±30 %.
Which of the three dominates is `assumed`, not isolated.

**The structure metrics do not settle the "dendritic" claim, and that is a
finding.** Gradient-field coherence and drainage concentration were the two
candidate measures. Both were computed on vanilla mountain crops (halved to
our pixel size), on the plain rescale, on the shipped isotropic build and on
this one (`docs/evidence/heightmap_erosion/structure_metrics.csv`,
`scripts/heightmap_structure_metrics.py`). They do separate *terrain* from
*quantisation* — the plain rescale is far below vanilla on both — but they do
**not** separate isotropic noise from landscape: the shipped build already
matched or exceeded vanilla on both, because any smooth band-limited random
field is locally one-dimensional and does drain somewhere. A third metric,
`channel_alignment` (how far the fine detail sits below the *coarse*
drainage network, i.e. cross-scale self-similarity), discriminates better in
principle and still does not give a clean win here. The honest position: the
hillshades in `docs/evidence/heightmap_erosion/` are the evidence for the
shape claim, and they are a human's look call — which is what
`docs/map_fidelity.md` §4.4 said this item would be.

## Sea floor (2026-09-10)

CK2's `topology.bmp` carries almost no bathymetry. Rescaled, Faerûn's whole
ocean landed in `[1439, 4883]` — a median only **39 %** of the way below the
water surface — and CK3 paints shallow water as sand, so the ocean west of
Waterdeep came out beach-coloured in the in-game check (camera probe,
`docs/step_map_paint.md` §9.5/§9.8).

Vanilla's own sea floor is a **flat 0**: p25, median and p75 of vanilla's
underwater pixels are all 0 (`verified` against `game/map_data/heightmap.png`,
water level 3932 = `WATERLEVEL 3.0 / WORLD_EXTENTS_Y 50.0 × 65535`). So
`ck2ck3.map.heightmap.deepen_sea` takes vanilla's shape rather than rescaling
CK2's noise: every water pixel goes to `[map.heightmap] sea_floor` (0), with a
linear ramp over `sea_shelf_px` (24) pixels of distance from the nearest land,
so beaches and straits keep a gradient instead of dropping off a wall. Land
pixels are untouched; the pass runs before the detail synthesis and the packer.

Measured on Faerûn: water median 2981 → **0**, p75 4420 → **0**, 14.0 % of
water pixels remain on the shelf between 0 and the water level, land minimum
4884 (one level above the surface, as before).

`deepen_sea = false` restores the old behaviour.
