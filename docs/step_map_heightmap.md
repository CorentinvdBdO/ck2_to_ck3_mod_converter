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

## 2d. The cliff-foot moat (`heightmap_detail_fill_min_cycles_per_km`, `heightmap_detail_erosion_slope_ceiling_steps`)

**What the playtest saw.** Build 13, Thay: *"plateaux are dipping then coming
back up"* — a trench just inside and outside every escarpment, the plateau
top and the ground beyond it both higher than the strip between them. The
user's read was *"your method amplified variations way too much"*, and that
turned out to be exactly right.

**How it is measured.** `scripts/relief_sharp_moat.py`, two numbers, both on
the two study crops of §2b (`docs/evidence/relief_sharp/moat_live.csv`,
`moat_isolate_thay.csv`, `moat_isolate_spine.csv`):

* **undershoot** — for every adjacent pair the *plain rescale* jumps ≥ 2
  quantisation risers over, walk 12 px into the low side and take the
  deepest dip below the foot's own level. Transects whose source profile
  keeps descending are dropped, so the foot really is flat in the source.
* **control** — the same statistic on pairs that jump *one* riser: the same
  fill on ground the source drew equally flat, but with no escarpment
  beside it. Any fill dips a couple of hundred levels below a flat foot and
  that is terrain; **`MOAT = undershoot − control`** is the part that only
  happens next to a cliff, and that is the number to drive to zero.

The land mask for all of this is the **province** mask read back off a
finished map, never `plain_rescale > water_level`: Faerûn's CK2 lakes and
river provinces sit on high ground (the median such pixel in the Thay crop is
at 14,301 in the rescale), so a threshold on the rescale calls 10,020 Thay
water pixels land and then reads the water pin under them as a 9,000-level
trench. That mistake inflated the first measurement of this lane by ~2.5×.

### The three candidates, each toggled on its own

Build-13 settings on the Thay crop, one switch at a time
(`docs/evidence/relief_sharp/moat_isolate_thay.csv`, `verified`):

| variant | undershoot | control | **MOAT** |
|---|---|---|---|
| plain rescale | 12 | 56 | −44 |
| de-terrace (Perona–Malik) **alone** | −47 | 80 | **−126** |
| build 13, all passes | 1838 | 343 | **1494** |
| …with the Gaussian de-terrace instead | 2071 | 364 | 1707 |
| …with `erosion_incision = 0` | 199 | 309 | **−111** |
| …with `relief_mode = "isotropic"` | 33 | 340 | **−308** |
| …with `gain_mode = "hf_target"` | 1412 | 259 | 1153 |
| …with `river_depth = 0` | 1802 | 300 | 1503 |
| …with `coast_smooth_px = 0` | 1836 | 342 | 1494 |

**Perona–Malik is not the cause** (`verified`). Its overshoot is real — §2b
measures 1.13 × cliff survival — but it is bounded by the step: on the whole
Thay crop the de-terrace moves land by 184 levels RMS and 805 levels at
most, and on its own it leaves *less* undershoot than the plain rescale. The
blind Gaussian is **worse**, which settles it: a sharpening filter cannot be
what a blurring filter also does.

**Neither is the coast pass, `deepen_sea`, or the river carve** (`verified`).
Thay's crop is 322 km from the nearest water, so `_smooth_coast`'s factor is
1 everywhere in it, and turning the coast pass and the river carve off moves
MOAT by 0 and 9 levels.

**Neither is the deficit-mode gain.** `gain_mode = "hf_target"` still leaves
MOAT at 1153.

### Cause 1 — the stream-power law was handed the escarpment as its slope

`eroded_relief` evolves `w = base + fractal seed` and returns `w − base`, on
the argument that "nothing of the macro survives into the caller's noise
field". That is false as soon as the model *erodes* the macro. `S` in
`dz = −K (A/A_ref)^m S` is the steepest descent of `w`, which on Thay's
escarpments is up to **4,505 levels/px against a land median of 128**
(`verified`). Capped at `_INCISION_SLOPE_CAP = 0.5` of it, that is still
1,939 levels cut from the plateau rim *per iteration*, sixteen times over —
and the uniform uplift then hands the mean of that back to every land pixel.
Measured on the Thay crop, the returned field averages **−1,142 levels on
cliff pixels and +632 levels twelve pixels away**: a 1,773-level trench
around every escarpment before the spectral pass has touched it
(`docs/evidence/relief_sharp/erosion_slope_ceiling.csv`, `verified`).

**The fix.** `heightmap_detail_erosion_slope_ceiling_steps` caps the slope
the *stream-power term* may see, in 277-level source steps per pixel. The
"never below the neighbour it drains into" guard still reads the true slope,
so nothing is loosened. The default is **0.5** = 138 levels/px, which is the
fractal seed's own 93rd-percentile gradient (p50 47, p90 115, p99 183,
`verified`): the model then incises the relief it is *synthesising* and not
the escarpment it was handed. Trench in the returned field, Thay crop:

| `slope_ceiling_steps` | 0 (build 13) | 4.0 | 2.0 | 1.0 | **0.5** |
|---|---|---|---|---|---|
| field RMS, levels | 931 | 875 | 674 | 487 | **390** |
| cliff→interior trench, levels | 1773 | 1654 | 1153 | 593 | **246** |

### Cause 2 — the fill was filling a band that was never a deficit

§2c aims the fill at vanilla's own measured land spectrum and fills the
shortfall from `KEEP_STRUCTURE_BELOW_KM` = 0.01 cycles/km up. Vanilla's
amplitude at 0.021 cycles/km (47 km) is **7,100 levels**, and our interior
carries 0.51 × of it, so the pass was injecting ~6,100 levels of relief at
47 km wavelength — on top of the CK2 author's own macro relief. Measured on
48 all-land interior patches of the build-13 map, that is what the numbers
say happened (`verified`, ratio to vanilla):

| cycles/km | km | plain rescale | build 13 | **this build** |
|---|---|---|---|---|
| 0.0105 | 95 | 0.69 | 0.88 | **0.69** |
| 0.0158 | 63 | 0.62 | 1.08 | **0.62** |
| 0.0211 | 47 | 0.51 | 1.13 | **0.51** |
| 0.0290 | 34 | 0.40 | 1.23 | **0.44** |
| 0.0395 | 25 | 0.39 | 1.12 | **0.80** |
| 0.0500 | 20 | 0.41 | 1.03 | **0.93** |
| 0.0711 | 14 | 0.46 | 1.03 | **0.95** |
| 0.1000 | 10 | 0.70 | 1.13 | **0.95** |
| 0.1500 | 6.7 | 1.20 | 0.96 | **0.65** |
| 0.2001 | 5.0 | 1.31 | 0.90 | **0.85** |
| 0.3001 | 3.3 | 1.50 | 2.06 | **2.10** |

Build 13 matched vanilla from 95 km to 10 km, which is exactly the problem.
**A shortfall at 47 km is not a deficit the pass is entitled to fill.** The
CK2 source raster is 4096 × 3328 upscaled 1.9543 × onto the canvas, so one
source pixel is 2.90 km and its own Nyquist is **0.172 cycles/km**
(`verified`, `docs/map_scale.md`): below that the author's terrain is fully
*resolved* and only *quantised*, and a quantiser only ever **adds**
broadband noise (step / √12 = 80 levels, white) — it cannot remove 7,100
levels at 47 km. What the shortfall down there measures is the difference
between Faerûn's macro relief and Europe's, and filling it fabricates
mountain-scale terrain on ground the CK2 author drew flat. On Thay's
plateaus that was ±20,000 levels of 35–60 km undulation, which is the moat
the playtest saw and, word for word, "variations amplified way too much".

**The fix.** `heightmap_detail_fill_min_cycles_per_km` is where the fill
reaches full strength, with a one-octave raised-cosine roll-on below it
(`heightmap_detail.fill_band_weight`; a brick wall would ring, and a sinc
beside an escarpment is another moat). Default **0.05 cycles/km = 20 km**:
below it the source is resolved and untouched, above it the deficit is
genuinely ours — the de-terrace alone (a σ 2.2 px = 3.3 km diffusion)
attenuates there, and past 0.172 cycles/km there is no source content at
all. 0 restores build 13.

### What it costs

The 0.05–0.2 cycles/km band §2c bought stays bought (0.93/0.95/0.95/0.65/0.85
against vanilla at 0.05/0.07/0.10/0.15/0.20); 0.01–0.03 goes back to the
plain rescale's own 0.51–0.69 ×, which is Faerûn's relief rather than
Europe's. `0.15` at 0.65 × is the one point that got worse — the fill's
roll-on and the de-terrace both bite there — and it is left as it is.

### Measured, finished maps

Both study crops, plain rescale / build 13 / this build, province land mask
(`docs/evidence/relief_sharp/moat_live.csv`, `verified`):

| crop | map | undershoot | control | **MOAT** | delta RMS vs rescale | land on clamp floor |
|---|---|---|---|---|---|---|
| Thay | build 13 | 3478 | 551 | **+2927** | 2464 | 0.034 % |
| Thay | this build | 169 | 285 | **−116** | 804 | 0.006 % |
| Spine | build 13 | 2678 | 328 | **+2350** | 1695 | 0.038 % |
| Spine | this build | 95 | 168 | **−72** | 405 | 0.031 % |

The cliff-foot profile is now *flatter* than the same fill leaves ordinary
ground: MOAT is negative on both crops, and the absolute undershoot is under
200 levels, against a 3,878-level (14-riser) cliff on Thay's steepest edge
that §2b still keeps. Whole-canvas land on the clamp floor 0.382 % → 0.377 %.

### The ablation — one full `map` run per default this lane moved

`scripts/relief_sharp_ablate.sh` (five whole-canvas runs, ~2 min each),
measured by `scripts/relief_sharp_moat.py --mode live`
(`docs/evidence/relief_sharp/moat_live.csv`, `verified`). MOAT is the
cliff-foot excess defined above; `Δ RMS` is the finished map against the
plain rescale, on land, inside the crop.

| run | Thay MOAT | Thay Δ RMS | Spine MOAT | Spine Δ RMS |
|---|---|---|---|---|
| plain rescale | −46 | 0 | −46 | 0 |
| **build 13** (`no_fix`, byte-identical to the shipped map) | **+2927** | 2464 | **+2350** | 1695 |
| fill band only (slope ceiling off) | +861 | 1061 | +705 | 629 |
| slope ceiling only (fill from 0.01 c/km) | −46 | **1569** | −130 | **1083** |
| **both, ceiling 0.5** (shipped) | **−116** | **804** | **−72** | **405** |
| both, ceiling 1.0 | +15 | 818 | +9 | 415 |
| both, `headroom_fraction = 1.0` | −116 | 808 | −74 | 410 |

Read it as two separate defects with two separate fixes. **The slope ceiling
is what removes the cliff *correlation*** — on its own it takes MOAT to zero.
**The fill band is what removes the *amplitude*** — on its own it halves the
map's departure from the source but leaves MOAT at +861/+705. Only the pair
gives both, and only at ceiling **0.5**: at 1.0 the trench comes back
(+15/+9 rather than −116/−72). `headroom_fraction` changes nothing
measurable, as stated above.

**A third default moved, and it is a bound rather than a fix.**
`heightmap_detail_headroom_fraction` (0.5) is the fraction of a pixel's own
headroom `_limit_excursion` may saturate into. At 1.0 `tanh` still reaches
`water_level + 1` exactly, so a pixel whose fill is several times its
headroom clips flat and a run of them prints a trench. On the finished
Faerûn map it changes nothing measurable (`verified`, the ablation below) —
the limiter binds on 0.19 % of land — so it is here as a guarantee, not as
part of the moat fix.

---

## 2e. `resolution_factor = 2`, measured (not shipped)

Playtest 3's second finding: *"I see the erosion, but still too smooth, not
sharp enough."* Half of that is §7's standing limit — a 1× sheet has a
Nyquist of 0.337 cycles/km against vanilla's 0.674, and no pass reaches past
it. `[map.heightmap] resolution_factor = 2` was prototyped on the two study
crops and then run over the whole canvas
(`scripts/relief_sharp_2x.py`, `relief_sharp_2x_full.py`,
`relief_sharp_repack_2x.py`; `docs/evidence/relief_sharp/two_x_*.csv`,
`run_map_2x.log`, `repack_2x.log`). All `verified`.

**It works, and it is sharper.** Thay's steepest one-pixel step, expressed
per km so the two grids compare: gradient p99 **950 → 1888** levels/km, p99.9
1598 → 2650, max 2392 → 4618. The cliff is not just kept, it is twice as
steep on the ground.

**Three costs, one of them a blocker until it is configured.**

1. **The packer refuses the default tile size.** The indirection map
   addresses the atlas with 8-bit offsets, so one compression level holds at
   most 256 × 256 = 65,536 distinct tiles. At `tile_size = 33` (stride 32) a
   2× Faerûn canvas is 520 × 424 = **220,480** tiles before any dedupe and
   `write_packed` raises. `tile_size = 65` (stride 64) gives 260 × 212 =
   55,120 and packs — which is exactly what vanilla's own 2× sheet does
   (18432 × 9216 at `tile_size = 65`). So 2× is a **two**-key change.
2. **Bytes.** `packed_heightmap.png` 16.3 → **51.1 MB** at `tile_size = 65`
   (72.1 MB at 129), and `heightmap.png` 39.0 → **130.9 MB**. The pair is
   182 MB against the 1× 55 MB, over the ~150 MB the lane was given.
3. **Runtime and memory.** The `map` step goes 143 s → **348 s** (5:48, plus
   ~20 s for the pack it did not reach), **19.8 GB peak RSS**. Inside the
   6-minute budget, not inside a small machine.

**And the sharpness it adds is not vanilla's.** Interior spectrum, 48
all-land 256 px patches, the report's own estimator, ratio to vanilla
(`docs/evidence/relief_sharp/two_x_canvas.csv`):

| cycles/km | 0.05 | 0.07 | 0.10 | 0.15 | 0.20 | 0.25 | 0.30 | 0.35 | 0.40 | 0.50 | 0.60 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ours 1× | 0.97 | 0.99 | 0.93 | 0.66 | 0.86 | 1.48 | 2.11 | — | — | — | — |
| ours 2× | 1.09 | 1.09 | 1.14 | 1.26 | 1.49 | 1.94 | 2.33 | **3.14** | **3.42** | **3.81** | **4.20** |

The new band is filled 3–4 × too hot. Two reasons, both known: the transfer
curve's risers are a *sharper* edge on the finer grid (the plain 2× rescale
alone measures 3.3–4.9 × vanilla at 0.4–0.6), and every `*_px` key of the
pass is a **canvas**-pixel length. `ck2ck3.map.build` now multiplies
`deterrace_sigma_px`, `gain_blur_px` and `coast_smooth_px` by the resolution
factor — a no-op at 1× — but `fractal_seed`'s octave sigmas and
`_carve_rivers`'s width constants are still module-level pixel counts, so at
2× the synthetic relief and the river cross-sections sit at half their
intended ground scale. **That is the work a 2× lane has to do**, and it is
why `resolution_factor` stays at 1 here.

**The control that proves the point.** A finished 1× map bicubic-upsampled
to 2× measures 0.29–0.36 × vanilla at 0.6 cycles/km — an interpolator adds
no frequency. If sharpness is wanted, the pass has to *run* at 2×; there is
no cheap version.

---

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
| `heightmap_detail_erosion_slope_ceiling_steps` | `0.5` | pass 2 ceiling on the slope the stream-power law sees, in 277-level source steps per px; `0` reproduces build 13 (§2d) |
| `heightmap_detail_target_mode` | `"vanilla_curve"` | pass 2 fill target: vanilla's measured curve (§2c) or `"power_law"` |
| `heightmap_detail_target_gain` | `1.0` | multiplier on that curve before the shortfall is taken |
| `heightmap_detail_gain_mode` | `"deficit"` | pass 2 amplitude authority: the measured shortfall with the terrain table as a relative modulation (§2c e), or `"hf_target"`, the original per-class `sqrt(want² − have²)` |
| `heightmap_detail_spectral_slope` | `-2.0` | pass 2 power-law exponent — only read by `"power_law"` |
| `heightmap_detail_fill_min_cycles_per_km` | `0.05` | pass 2: where the fill reaches full strength, one-octave cosine roll-on below; `0` reproduces build 13 (§2d) |
| `heightmap_detail_headroom_fraction` | `0.5` | pass 2: the fraction of a pixel's own headroom the offset may saturate into, so `tanh` cannot reach the clamp floor exactly (§2d) |
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
(`verified`). No detail pass reaches past it. `[map.heightmap]
resolution_factor = 2` is measured in **§2e** — it is affordable, it does
add sharpness, and it is not a one-line change after all.

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
