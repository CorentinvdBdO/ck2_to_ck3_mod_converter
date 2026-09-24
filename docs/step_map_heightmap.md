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
4. **Coast smoothing** — the synthesised offset is damped over the land
   within `heightmap_detail_coast_smooth_px` (default 4 canvas px) of a
   shoreline, so beaches stay flat instead of gaining mountain-scale noise
   right at the waterline. Until 2026-09-12 this contracted the *height*
   toward the water level, which dug a crater around every inland CK2 lake
   (**§2f**); `heightmap_detail_coast_mode = "blend_to_water"` restores it.
5. **The source bound** — the output is held inside
   `[source_local_min − tol, source_local_max + tol]` over a window of one
   CK2 source pixel, `tol` being that pixel's terrain class's own measured
   vanilla high-frequency amplitude (**§2f**). Detail is texture on the CK2
   author's surface, never a hole in it.

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

## 2f. Why build 15 still had pits — and the bound that makes them impossible

**What playtest 4 said.** *"Thay's pits are even larger"*, after the §2d moat
fix, and *"erosion is still creating smooth mountains instead of sharp ones"*
(§2g). This section is the first half.

### The metric §2d used could not see this

§2d drove **MOAT** — cliff-foot undershoot *minus* the same statistic away
from a cliff — from +2927 to −116 on Thay. Both that number and the
playtest are right, and that is the lesson: MOAT is a **difference**, so a
defect that digs holes *everywhere* raises its control as fast as it raises
its signal and cancels out of it. It answers "is the trench correlated with
the escarpment", which was the build-13 question, and it cannot answer "is
there a trench".

The metric this section drives is absolute and has a physical zero
(`scripts/relief_pits_common.pit_depth`):

> **pit depth** = `source_local_min − output`, the local minimum taken over a
> window of **one CK2 source pixel** (1.9543 canvas px, so a 3 px square).

Against the local *minimum* rather than the source value, so a real
escarpment costs nothing: at a cliff the window already spans both sides, and
the top of the drop is bounded below by the foot of it. On ground the author
drew flat the two collapse together and the metric is exactly "how far below
the author's own surface did we dig". Reported as p95, p99, and the fraction
of land more than **one quantisation riser (277 levels)** down. The land mask
is the province mask read off a finished map, never `plain_rescale >
water_level` (§2d, and CLAUDE.md).

### The ablation — one whole-canvas run per candidate

**The ablation has to run at full canvas size**, which is a finding of its
own. `relief_sharp_moat.py --mode isolate` toggles each pass on a 768 px
crop; under build-15 settings that is degenerate. The crop holds no all-land
256 px interior patch, so `_interior_patch_spectrum` returns nothing, the
fall-back whole-crop spectrum of a terraced window already exceeds vanilla's
curve everywhere above 0.05 cycles/km, the deficit comes out identically
zero — and `eroded`, `isotropic` and `erosion_incision = 0` then produce
**byte-identical** output (delta RMS 474.9 on all three, `verified`). A crop
ablation cannot charge the fill or the erosion with anything.
`scripts/relief_pits_ablate_canvas.py` runs each variant over the real
8320 × 6784 sheet (~60 s, ~6 GB) and measures the two study windows.

Thay window (canvas y 1583–2222, x 4752–5311), province land mask,
`docs/evidence/relief_pits/pits_ablate_before.csv`, all `verified`:

| variant | pit p95 | pit p99 | land > 1 riser down | Spine p95 | Spine p99 |
|---|---|---|---|---|---|
| plain rescale | 0 | 0 | 0 % | 0 | 0 |
| **build 15, the shipped map** | **576** | **2612** | **9.34 %** | 514 | 1353 |
| build 15 reproduced by this harness | 572 | 2611 | 9.29 % | 508 | 1345 |
| (iii) pass 1 alone (Perona–Malik) | 4 | **76** | 0.01 % | −89 | 34 |
| (i) `erosion_incision = 0` | 774 | 2818 | 11.84 % | 788 | 1928 |
| (i) `relief_mode = "isotropic"` | 564 | 2622 | 9.78 % | 445 | 1098 |
| (ii) `fill_min_cycles_per_km = 0.10` | 333 | 2604 | 5.58 % | 204 | 813 |
| (ii) `fill_min_cycles_per_km = 0.172` | 282 | 2606 | 5.03 % | 145 | 648 |
| (ii) `fill_gain = 0` (no fill at all) | 285 | 2614 | 5.06 % | 145 | 643 |
| pass 3 off (`river_depth = 0`) | 491 | 2604 | 7.75 % | 428 | 1300 |
| **pass 4 off (`coast_smooth_px = 0`)** | 344 | **823** | 6.31 % | 447 | 999 |

**Candidate (iii), Perona–Malik, is acquitted outright**: on its own it digs
76 levels at p99 against a 193-level tolerance.

**Candidate (i), the erosion carving basins into the plateau top, is
acquitted as the cause** — and this is the surprise. Removing the incision
makes the pits *worse* (p95 572 → 774), and white noise in place of the
eroded field changes nothing (564). The mechanism the brief suspected is
real (a flat source has no macro drainage, so the model organises around its
own fractal seed) but it is not what digs the holes: the radial equaliser
downstream re-imposes the same spectrum whatever phase it is handed, and the
erosion's own redistribution happens to *reduce* the extremes.

**Candidate (ii), the fill, owns half the p95 and none of the tail.** Turn
the fill off entirely and p95 falls 572 → 285 while p99 stays at 2614.

**The tail is pass 4, the coast smoothing — a fourth candidate none of the
three readings named.** Turning it off takes p99 2611 → 823. Split the
window by zone (`docs/evidence/relief_pits/pits_zones_both.csv`, `verified`):

| Thay zone | share of land | build 15 pit p95 / p99 / max | this build |
|---|---|---|---|
| within 5 px of a water province | 8.4 % | **4086 / 6644 / 8141** | **53 / 191 / 427** |
| within 4 px of a traced river | 6.4 % | 748 / 1217 / 3279 | 427 / 618 / 623 |
| plateau interior | 85.2 % | 290 / 788 / 3044 | 60 / 263 / 829 |

(The river band is the one zone that is *meant* to sit below the source:
pass 3 carves where CK2 says a river is. The bound now holds it to 618
levels at p99 rather than 1217.)

### The cause, in one sentence

**Faerûn's CK2 lakes and river provinces sit on high ground, CK3's water
level is global, and pass 4 dragged the ring of land around each one 55 % of
the way down to it.**

The median CK2 lake/river-province pixel in the Thay crop is at **14,301** in
the plain rescale (§2d already records this, for a different reason). The
heightmap owes CK3 a water pixel at or below `water_level` = 4883, so every
such province is already a hole punched through a 20,000-level plateau —
unavoidable, and the engine's rule, not ours. What was ours is the next
line: `_smooth_coast` computed
`water_level + (out − water_level) · factor` with `factor` = 0.45 at the
shoreline, i.e. it pulled the first four pixels of land 55 % of the way down
to sea level as well. On Thay that is an **8,000-level crater** around every
lake, and Thay is full of them. The same code runs at the real ocean coast,
where it is harmless because the CK2 source is already near sea level there
— which is why it survived three builds unnoticed.

"Even larger" than before the moat fix is consistent: §2d flattened the
plateau interior, so the craters stopped competing with 20,000 levels of
fabricated 47 km undulation and became the thing you see.

### The four fixes

1. **`heightmap_detail_coast_mode = "damp_detail"`** (new default). Pass 4
   now damps the *synthesised offset* over the first `coast_smooth_px` of
   land — `h2 + (out − h2)·factor` — instead of contracting the height
   toward the water level. That is the whole of the pass's stated job ("a
   beach does not gain mountain-scale noise at the waterline"), and it
   leaves the shore at the height the CK2 author drew, so the drop into a
   lake happens in the one pixel where the lake starts.
   `"blend_to_water"` restores build 15.
2. **`heightmap_detail_erosion_slope_gate_steps = 1.0`** (new). The
   stream-power law may only run where the *source* has macro slope — one
   quantisation riser per CK2 source pixel, 277 levels over 2.90 km,
   measured on a one-source-pixel Gaussian of the de-terraced base, with a
   smooth-step transition so the gate leaves no outline. Where it is 0 the
   model degenerates to seed plus hillslope diffusion: texture, no carving.
   This is the candidate-(i) mechanism closed by construction. It is a
   correctness fix, not a pit fix — it costs a little on the metric (below),
   for the same reason removing the incision did.
3. **`heightmap_detail_bound_window_px = 3`,
   `heightmap_detail_bound_tolerance_sigmas = 2.0`** (new): the hard bound,
   below.
4. **`heightmap_detail_fill_min_cycles_per_km` 0.05 → 0.10.** Not a new key —
   §2d's own, moved one octave. It is the change that makes the bound a
   backstop rather than a mechanism, and the measurement that justifies it is
   the bound's own hit rate: at 0.05 the fill wants to leave the author's
   surface often enough that the clamp is doing real work.

### The bound

> For every land pixel, over a window of one CK2 source pixel,
> `source_local_min − tol ≤ output ≤ source_local_max + tol`,
> with `tol` = `bound_tolerance_sigmas` × the pixel's own terrain class's
> measured vanilla high-frequency RMS (`heightmap_detail_hf_targets`, from
> `docs/evidence/map_fidelity/hf_by_terrain.csv`: plains 86, hills 213,
> mountains 311, desert_mountains 323 levels). Median tolerance on Thay:
> **193 levels**; on the Spine of the World **427**.

Three things about it:

* **The clamp is toward the source, not toward the water level.** §2c(d)'s
  headroom limiter bounds the fill by the room between the pixel and the sea,
  which is the right bound for *not drowning* land and the wrong one for *not
  digging*: on a 20,000-level plateau it permits a 15,000-level pit.
* **It is a `tanh` saturation over the last quarter of the tolerance**, not a
  hard clip — a hard clip prints the bound's own shape into the map as a flat
  spot, which is the artefact being removed. The saturation band is a
  fraction of the **tolerance**, not of the interval: a fraction of the
  interval squashes legal terrain (measured, and fixed: a 20,000-level
  plateau beside a lake came out at 19,186).
* **It is a backstop and its hit fraction is reported**, in the pass's stats
  dict and in the `map` step's own summary line
  (`bound_limited_pct_of_land`) — on the shipped build, **2.87 % of all
  land** is moved by more than one level. The passes in front of it are
  fixed so that it rarely binds; if that number climbs, the fill is writing
  terrain the source has no basis for. "Hit" means the saturation actually
  moved the pixel, not that it entered the soft band: counting entries
  overstates the backstop's work by an order of magnitude (15.0 % of land at
  `fill_min_cycles_per_km = 0.05`).

`heightmap_detail_bound_tolerance_sigmas = 0` disables it.

### Measured, whole canvas

`scripts/relief_pits_ablate_canvas.py`,
`docs/evidence/relief_pits/pits_ablate_staged.csv` and `pits_ablate_after.csv`,
`verified`. "outside the bound" is the fraction of land more than one level
(integer rounding) outside `[src_local_min − 2σ, src_local_max + 2σ]`.

| build | Thay pit p95 | p99 | land > 1 riser down | outside the bound | Spine p95 | p99 | land > 1 riser down |
|---|---|---|---|---|---|---|---|
| plain rescale | 0 | 0 | 0 % | 0 % | 0 | 0 | 0 % |
| **build 15, shipped** | 576 | 2612 | **9.34 %** | **8.81 %** | 514 | 1353 | **8.80 %** |
| + `coast_mode = "damp_detail"` | 310 | 751 | 5.59 % | 4.98 % | 379 | 858 | 6.77 % |
| + the erosion slope gate | 337 | 805 | 6.06 % | 5.26 % | 407 | 919 | 7.39 % |
| + the bound + §2g ridged relief | 256 | 597 | 4.71 % | 0.02 % | 263 | 614 | 4.79 % |
| + fill from 0.10 c/km | 125 | 376 | 1.59 % | 0.00 % | 140 | 372 | 1.53 % |
| **the shipped build, whole `map` run** | **136** | **392** | **1.78 %** | **0.00 %** | **140** | **393** | **1.73 %** |

The last row is a real conversion (`configs/faerun.toml` at the new
defaults), the rest are the ablation harness on the same canvas; the two
agree to within the seed. The `map` step costs **142.8 s**, against build
15's 143 s — the bound is two morphological filters and the gate one
Gaussian, and the ridged seed replaces a `standard_normal` it was already
paying for.

Read it as four independent changes, each with its own share:

* the **coast mode** is the whole of the p99 tail — 2612 → 751 on its own;
* the **slope gate** costs a little (310 → 337), the same way removing the
  incision entirely did, and it is here for correctness: an erosion model
  with no drainage to model is carving its own seed. Honest, and flagged;
* the **bound** takes the residual to 4.7 % of land more than a riser down,
  and to ~0 % outside the tolerance;
* **`fill_min_cycles_per_km` 0.05 → 0.10** is the change that makes the bound
  a backstop rather than a mechanism. At 0.05 the pass writes outside the
  author's surface often enough that the bound has real work to do; at 0.10
  the pits fall to 1.6 % of land and the backstop moves **2.6 % of all land**
  by more than one level.

**And the spectrum gets *better*, not worse.** 48 all-land 256 px interior
patches, ratio to vanilla's own land spectrum
(`docs/evidence/relief_pits/spectrum_bands.csv`, `verified`):

| cycles/km | km | plain rescale | build 15 | this build |
|---|---|---|---|---|
| 0.021 | 47 | 0.55 | 0.54 | 0.54 |
| 0.040 | 25 | 0.42 | 0.82 | 0.40 |
| 0.050 | 20 | 0.42 | 0.96 | 0.39 |
| 0.071 | 14 | 0.49 | 0.98 | 0.67 |
| 0.100 | 10 | 0.70 | 0.92 | **1.14** |
| 0.150 | 6.7 | 1.23 | **0.65** | **1.13** |
| 0.200 | 5.0 | 1.35 | 0.84 | 1.03 |
| 0.300 | 3.3 | 1.50 | 2.08 | 2.09 |

The 14–25 km band goes back to the plain rescale, which is §2d's own
argument carried one octave further: below the CK2 source's Nyquist the
author's terrain is resolved, and a shortfall there is Faerûn's relief rather
than ours to invent. In exchange, 6.7 km — "the one point that got worse" in
§2d, at 0.65 × — comes back to 1.13 ×, and 10 km to 1.14 ×. 0.3 cycles/km is
unchanged at 2.09 × (§7's standing item: that is the de-terraced base's own
residual riser energy, not the fill).

### Evidence and what to run

`docs/evidence/relief_pits/`, produced by four scripts:

| script | what |
|---|---|
| `scripts/relief_pits_common.py` | the pit metric, the closed-depression (sink) metric, the bound check, the shape metrics, and the per-pixel terrain class read back off a generated mod. Importable, no side effects; the invariant script and the unit tests use the same code. |
| `scripts/relief_pits_diagnose.py` | `--mode live` (pit/bound/shape per map, signed-difference and hillshade PNGs, interior **and** rim transects), `--mode zones` (coast band / river band / interior), `--mode ablate` (the crop ablation, kept only to demonstrate that it is degenerate) |
| `scripts/relief_pits_ablate_canvas.py` | the whole-canvas ablation, one `heightmap_detail.apply` per variant |
| `scripts/relief_pits_shape.py` / `relief_pits_spectrum.py` | §2g's shape numbers and the interior spectrum, against vanilla |

Figures: `signed_diff_{thay,spine}_build15.png` (the craters are the blue
rings around every inland water province), `transects_{thay,spine}.png` (the
plateau interior row and the steepest rim row, every map on one axis),
`hillshade_{thay,spine,thaymount}_*.png`, `hillshade_vanilla_mountains.png`.

### Still open

* **The erosion slope gate costs a little on the pit metric** (Thay p95
  310 → 337 with everything else equal). It is kept because an erosion model
  with no drainage to model is carving its own seed, which is not a defensible
  thing for the pass to do — but it is a correctness argument, not a
  measured win, and it is flagged here rather than buried.
* **A river valley is still a pit by this metric** (Thay river band p95 748 in
  build 15). It is deliberate — pass 3 carves where CK2 says a river is — and
  the bound permits it only within the tolerance, so a 900-level centreline
  now costs the bound a hit on every river pixel. Whether `river_depth`
  should be inside the tolerance instead is a look call, not a measurement.
* **0.3 cycles/km stays at 2.09 × vanilla** (§7), and the 14-25 km band is now
  deliberately Faerûn's own.

---

## 2g. Ridged relief — "smooth mountains instead of sharp ones"

Playtest 4's second finding. It is **not** a spectrum complaint: §2c already
measures us at 2.05 × vanilla's amplitude at 0.3 cycles/km and inside ±30 %
from 0.05 to 0.2. Amplitude is not the problem, shape is.

### What "shape" is, measured

Four dimensionless numbers, all on the 8 px (12 km) high-pass so a crop's
macro tilt cannot decide them, all in `scripts/relief_pits_common`:

* `grad_kurtosis` — excess kurtosis of `|∇h|`. Long flat stretches with rare
  steep ones give a large number; a landscape of constant-slope faces gives a
  small one.
* `grad_p99_over_rms` — the same question without the fourth power.
* `ridge_share` — the fraction of land pixels that are **crests**: the
  Hessian's most negative eigenvalue is negative and the pixel is at least as
  high as the bilinear surface one pixel away in both directions along that
  eigenvector. No amplitude threshold anywhere in it, so it is pure shape.
* `ridge_mean_run_px` — pixel-weighted mean size of a connected crest
  component: how far a ridge line runs before it breaks up.

The reference is vanilla's own three highest-relief all-land 1024 px mountain
windows (`heightmap_erosion_evidence.VANILLA_CROPS`), 2×2-averaged to our
1.4839 km/px so both sides are sampled at the same ground scale, against two
512 px (760 km) crops of ours: the Spine of the World, and Thaymount (located
as the highest pixel of the plain rescale inside the Thay window).

### The mechanism

A **Gaussian random field is symmetric**: its peaks and its pits have the
same shape, so a mountain built from one reads as dunes however tall it is.
`fractal_seed` is exactly such a field, and the radial equaliser downstream
changes no phase, so whatever the erosion does the crests stay round.

`heightmap_erosion.ridged_seed` folds each octave through
`(1 − |n|) ** sharpness`. `|n|` creases along the zero set of `n`, which is a
set of *curves*, so every octave's zero crossing becomes a ridge line; the
exponent sharpens the crease and flattens the valley floor. The octaves share
one white field, as in `fractal_seed`, so the fine crests sit on the coarse
ones rather than crossing them at random.

On a 256 px unit-variance field (`verified`):

| seed | skew | grad kurtosis | ridge share | ridge mean run px |
|---|---|---|---|---|
| `fractal_seed` (smooth) | 0.07 | 8.36 | 0.158 | 155 |
| `ridged_seed`, sharpness 2 | **0.42** | **1.05** | **0.181** | **1663** |
| `ridged_seed`, sharpness 3 | 0.67 | 1.31 | 0.187 | 3355 |

Note the direction of the kurtosis: a ridged field's gradient is *less*
kurtotic, because a V-shaped face has a nearly constant slope where a sum of
Gaussian octaves has long flat stretches and rare steep ones. That matters,
because our build-15 map is on the wrong side of vanilla on that number
(below).

Two config knobs apply it per terrain class, both blurred by
`gain_blur_px` like the amplitude field so a class border leaves no seam:

* `heightmap_detail_ridged_classes` (default `mountains`,
  `desert_mountains`, `hills`, `terraced_hills`) and
  `heightmap_detail_ridged_weight` (1.0) mix the ridged seed into the
  erosion's initial relief;
* `heightmap_detail_ridged_diffusion_scale` (0.15) cuts the hillslope
  diffusion on those classes — thermal diffusion is precisely the term that
  rounds a crest off, so a mountain wants less of it than a plain does.

`heightmap_detail_ridged_sharpness` (3.0) is the crest exponent.

### §2g measured

Two 512 px (760 km) crops of ours against the mean of vanilla's three,
high-passed at 8 px, **on the land mask eroded by 4 px**
(`docs/evidence/relief_pits/shape_before.csv`, `shape_after.csv`,
`scripts/relief_pits_shape.py`, all `verified`). Figures in brackets are the
ratio to vanilla's own mean (23.2 / 3.10 / 0.1175 / 117.4).

| crop | map | grad kurtosis | p99/RMS \|grad\| | ridge share | ridge run px |
|---|---|---|---|---|---|
| Spine | plain rescale | 9.8 (0.42) | 3.40 (1.10) | 0.165 (1.40) | 162 (1.38) |
| Spine | build 15 | 6.7 (**0.29**) | 3.52 (1.14) | 0.129 (1.10) | 138 (1.18) |
| Spine | this build | 10.2 (**0.44**) | 3.94 (1.27) | 0.122 (**1.04**) | 139 (**1.18**) |
| Thaymount | plain rescale | 19.5 (0.84) | 3.16 (1.02) | 0.159 (1.35) | 197 (1.68) |
| Thaymount | build 15 | 3.0 (**0.13**) | 3.00 (0.97) | 0.125 (1.06) | 102 (0.86) |
| Thaymount | this build | 10.4 (**0.45**) | 3.46 (1.12) | 0.120 (**1.02**) | 90 (0.77) |

**The masking is not a detail, it is the measurement.** Unmasked, build 15's
own two crops read gradient kurtosis **49.3 and 66.1** — *twice* vanilla's
23.2, and meaningless: CK3's water level is global, so a lake shore is a
one-pixel drop of thousands of levels and one such edge dominates a fourth
moment. On the same crops' interiors the same build reads **6.7 and 3.0**.
Eroding the land mask by 4 px is the same rule §2c(b) already applies to the
spectrum, and it inverts the answer: on the interior our mountains are **far
smoother** than vanilla's, which is what the playtest said.

**Result against the target.**

* **`ridge_share` is met**: 1.02–1.04 × vanilla, inside ±20 %, from 1.06–1.10
  in build 15. `ridge_mean_run_px` is 1.18 × on the Spine and 0.77 × on
  Thaymount — Thaymount's crest lines break up more than vanilla's do, which
  is the one shape number that got slightly worse than build 15's 0.86 ×.
* **`grad_kurtosis` is not met**: 0.13–0.29 × vanilla in build 15, **0.44–0.45
  × here**. The ridged seed roughly triples it and it is still less than half
  of vanilla's. Two reasons, both `verified` and both structural: the metric
  lives at the top of our band (an 8 px high-pass on a 1 × sheet whose
  Nyquist is 0.337 cycles/km against vanilla's 0.674 — §7's standing limit,
  quantified in §2e), and the §2b de-terrace deliberately spends the
  quantisation risers that give the *plain rescale* its 0.42–0.84 ×.
  `resolution_factor = 2` is the lever that moves it; nothing inside a 1 ×
  pass got past 0.45 here.

The ablation's own contribution, same crops: with `ridged_weight = 0` the
build measures 0.40 / 0.40 × instead of 0.44 / 0.45 ×, and the pit metrics are
unchanged (Thay p95 129 against 134). So the ridged seed is a shape change
and costs nothing measurable elsewhere.
---

## 2i. `resolution_factor = 2`, shipped: the ground-distance audit

User decision 2026-09-24 (`docs/DECISIONS.md`): ship at vanilla's own
resolution, 2× the province canvas, with the erosion/detail passes running
*at* 2× rather than a bicubic upsample of a 1× map (§2e's control measured
that adds no frequency at all — 0.29–0.36 × vanilla at 0.6 c/km). Lane
`heightmap-2x`.

**Why this is not a one-line flip.** §2e already found the two-key packer
change (`resolution_factor = 2` + `tile_size = 65`) and already found the
mechanism of the defect: every `*_px` key of this module is a **canvas**-
pixel length, and at 2× the heightmap is a finer grid than the canvas, so an
unconverted pixel count describes half its intended ground distance. §2e
had `ck2ck3.map.build` scale three of them
(`deterrace_sigma_px`/`gain_blur_px`/`coast_smooth_px`) and stopped there,
flagging `fractal_seed`'s octave sigmas and `_carve_rivers`'s width
constants as still wrong. This section is the full audit that finding asked
for, `grep`-driven over every module `heights` passes through
(`ck2ck3.map.{heightmap,heightmap_detail,heightmap_erosion,lake_to_land,build}`).

**The constants, what each one is, and how each is now converted:**

| constant | module | was | now |
|---|---|---|---|
| `deterrace_sigma_px`, `gain_blur_px`, `coast_smooth_px` | `heightmap_detail` cfg | × `f` (§2e) | unchanged |
| `wall_spread_window_px`, `wall_spread_sigma_px` | `heightmap_detail` cfg | canvas px | × `f`, `build.detail_cfg` |
| `bound_window_px` (the §2f one-source-pixel bound) | `heightmap_detail` cfg | canvas px | × `f`, rounded, min 1 |
| `source_adaptive_window_px` (§2h source-roughness window) | `heightmap_detail` cfg | canvas px | × `f` |
| `fractal_seed`/`ridged_seed` octave sigmas `(0.8, 1.6, 3.2, 6.4, 12.0)` | `heightmap_erosion` | fixed, module-level | × `f` via `eroded_relief(seed_sigma_scale=f)` |
| `erosion_slope_ceiling_steps` (the §2d cliff-foot-moat cap) | `heightmap_erosion.eroded_relief` | levels/canvas-px | ÷ `f` (the *same* physical cliff spans `f`× more output pixels, so its slope in levels/px is `1/f` of the 1× value — `px_scale=f`) |
| `_RIVER_WIDTH_BASE_PX`, `_RIVER_WIDTH_PER_INDEX`, `_RIVER_BLUR_PX`, `_RIVER_MARGIN_PX` | `heightmap_detail._carve_rivers` | fixed module constants | × `f` via `px_scale=f` |
| `sea_shelf_px` (`deepen_sea`'s coastal ramp) | `heightmap.deepen_sea` | canvas px | × `f` at the `build.py` call site |
| `inpaint_heights`'s `sigma_px` (lake harmonic fill) | `lake_to_land` | canvas px, default 1.5 | × `f`, passed explicitly |
| `carve_valleys`'s `ring_px`/`ring_max_px` (valley bank search) | `lake_to_land` | canvas px, defaults 15/240 | × `f`, passed explicitly |

**Not scaled, and why that is correct, not an oversight:** every `*_km`
key and every constant multiplied through `km_per_px` (`HF_SIGMA_KM`,
`KEEP_STRUCTURE_BELOW_KM`, the whole spectral-fill/`macro_slope_gate`
machinery, `SOURCE_PX_KM`) — `ck2ck3.map.build` already passes
`km_per_px = cfg.scale.vanilla_km_per_px / f` into `heightmap_detail.apply`,
so anything built on it is resolution-correct by construction and needed no
change. `fill_min_cycles_per_km`, `erosion_slope_gate_steps` (via
`macro_slope_gate`, km-based), `river_depth`, `cliff_step_levels` and every
`*_levels` constant are heights or km, not pixel distances, and are
untouched. The "never below the downstream neighbour" incision guard inside
`eroded_relief` reads the *true*, unscaled per-pixel slope on purpose — it
is a per-pixel physical invariant, not a ground-distance measurement
(`heightmap_erosion.eroded_relief`'s own docstring).

**A second, pre-existing bug this audit found and fixed: `heights` and the
province raster silently disagreed in shape at `resolution_factor > 1`.**
`lake_to_land.inpaint_heights`/`carve_valleys` index `heights` (already `f`×
canvas resolution, from `heightmap.build`) through `ck3_raster` (always
canvas resolution — province-raster-derived arrays never grow with the
heightmap). At `f = 1` the two happen to be the same array and the bug is
invisible; at `f = 2` it is a shape mismatch. `ck2ck3.map.build` now
nearest-neighbour-upsamples `ck3_raster`/`water_mask` to heightmap
resolution (`_nn_upsample`, the same helper `heightmap_detail.apply`'s own
land/terrain/river inputs already used) before either lake_to_land call.

**Evidence and measurement tooling had the same bug, twice over, and needed
the same fix:**

* `scripts/relief_sharp_common.plain_rescale_canvas()` (`docs/evidence/relief_sharp/*.csv`,
  and every one of `scripts/verify_heightmap_detail_invariants.py`'s source-
  bound/closed-depression/wall/narrow-canyon checks) hardcoded the 1× canvas
  geometry, so at `f = 2` it returned a shape that could never match
  `heights` and every one of those checks silently reported "SKIPPED" — a
  green invariants run that had stopped checking four of its nine invariants.
  Now takes `resolution_factor`, scaling all four geometry constants
  (`CANVAS_*`, `SCALED_*`, `OFFSET_*`).
* `scripts/verify_heightmap_detail_invariants.py` itself additionally hard-
  refused any `provinces.png`/`heightmap.png` size mismatch
  (`if prov.shape[:2] != heights.shape: return 1`) — correct at `f = 1`,
  wrong at `f = 2`, where vanilla's own map ships the two at different sizes
  on purpose. It now derives `resolution_factor` from the ratio, upsamples
  the province-id raster once at the top of `main`, and every downstream
  per-province check (land/water invariant, valley/lake-to-land checks, the
  narrow-canyon scan) works unmodified against the upsampled array. Every
  window constant used against a `heights`-resolution array
  (`bound_window`, `NARROW_CANYON_WIDTH_PX`/`RING_PX`,
  `BED_VS_BANK_RING_PX`, `relief_pits_common.terrain_codes_from_mod`'s own
  province-terrain rasterisation, `closed_depression_excess_stats`'s
  `EXCESS_WINDOWS_PX`) is multiplied by the detected factor at the call
  site.
* `scripts/measure_relief_shape.py` (drainage density, valley V/U shape)
  took a `--resolution-factor` flag: its `OUR_CROPS` origins and `CROP_PX`
  window are canvas-px, and vanilla's own crops were being 2×2-mean-pooled
  down to match a 1× "ours" — at `f = 2` both are the same native
  resolution and the pooling is now skipped instead of blurring vanilla's
  own signal.

**Known gap, left as a documented limit, not fixed:** `relief_pits_common`'s
research-only windows outside the invariants script's own call sites —
`CLIFF_WIDTH_PX` inside `wall_stats`'s `cliff_drop_concentration`, and the
`MOAT_CLOSING_PX`/`MOAT_NEAR_PX`/`MOAT_FAR_PX` transect constants in
`relief_sharp_common` used only by the §2d isolation studies — are still
1×-canvas-px and were not threaded through for this lane. They are informational
diagnostics (check 6 already compares the *output's* ratio to the *source's
own* ratio at the same unscaled window, so it stays self-consistent even
unconverted) rather than pass/fail gates on the shipped file, and are not
used by `verify_heightmap_detail_invariants.py`'s exit code.

**Verification method.** No new synthetic 1×-vs-2× fixture was added
(`ci/checks.sh`'s own runtime budget does not have room for a second `map`
step); instead `uv run pytest -m "not slow"` (1337 passed) plus a real
`configs/faerun.toml` run at `resolution_factor = 2` is the check — every
`*_px` constant above is exercised on the real canvas, at the real 1.9543×
oversample, with the real lake/valley overrides live. `docs/evidence/heightmap_2x/`
carries the run log, sizes, timing/RSS and the spectrum/shape tables.

**The first full run found the real cost, and it was not the erosion.** The
first `resolution_factor = 2` run of this lane's own code took **1808 s**
for the `map` step (30 min) — a real regression to chase, not the ~2×–4×
this section's own audit predicted. `lake_to_land.inpaint_heights` (the §2h
iii harmonic lake fill) runs 400 iterations of a whole-canvas
`gaussian_filter`, and at `resolution_factor = 2` `sigma_px` is correctly
doubled (this section) to keep the same ground blur — so the same 400
passes now cost ~4× the per-pixel work over ~4× the pixels. Profiling this
run's own wall-clock (the `building heightmap` → `lake_to_land heightmap
inpaint` log gap) put it at roughly **700 s** on its own, for **34,560**
hole pixels (0.015 % of the canvas) — 5 marsh provinces near Thaymount, not
spread across the map.

**Fix: solve on the holes' own bounding box, not the canvas.**
Blur-and-restore is a diffusion process — information travels
`~sigma_px * sqrt(2 * iterations)` px in `iterations` passes — so
`inpaint_heights` now crops to the union of every hole's bounding box padded
by four times that radius (a "fixed" land pixel inside the padding is
restored to its true value every pass exactly as in the whole-canvas
version, so the artificial crop edge has decayed to negligible influence
long before it could reach a hole), with a fallback to the whole canvas if
the padded box would already cover more than 60 % of it. Re-run with the
fix: same inputs, byte-identical stats (`before_median`/`after_median`/
`bank_median` unchanged to the decimal — `verified`, the two runs' log
lines), `crop_frac_of_canvas` **0.0115** (2,589,796 of 225.8M px), and the
whole `building heightmap` → `synthesising heightmap detail` gap (heightmap
build + lake inpaint + valley carve + `deepen_sea`) dropped from an
estimated ~750 s to **~27 s**. `carve_valleys` (the river-valley bank
search) was never the cost — it is a bounded ring-dilation per province, six
of them, not a canvas-wide iteration — and needed no change.

**What is left, honestly.** The erosion/detail pass itself
(`heightmap_detail.apply`'s `relief_mode = "eroded"`) is `erosion_iterations
× accum_iterations` = 16 × 3 relaxation passes of 8-neighbour shifted
multiply-adds over the *whole* heightmap-resolution array by design (§2c:
the catchment has to be carried on the same grid the incision cuts), so it
does not shrink the way a small, localised hole-fill does — it cost
**454.6 s** on both runs (identical to the decimal, since nothing in the
lake-fill fix touches it), essentially 4× its 1× cost because there are 4×
the pixels. This is the genuine, physically-expected cost of running the
erosion *at* 2× rather than upsampling a 1× result (which is exactly why
§2e's own upsample control was rejected — sharpness has to come from the
pass, and the pass has to touch every pixel). Total `map` step after the
lake-inpaint fix: see the run log referenced in the HANDOFF; still
dominated by the erosion pass, which a further lane could shard by tile or
port to a compiled inner loop (`numba`/Cython) if a faster wall-clock is
needed — out of this lane's scope, flagged here rather than rewritten under
time pressure.

**`map_data/heightmap.png` is not shipped at `resolution_factor = 2`.**
Confirmed by three independent pieces of evidence, all `verified`: (1)
`map_data/default.map`'s `topology = "heightmap.heightmap"` names only
`packed_heightmap.png`/`indirection_heightmap.png` (the pre-existing CLAUDE.md
invariant); (2) a text grep of every file under `../claudespace/game_files`
finds no reference to `heightmap.png` outside `heightmap.heightmap`'s own two
lines; (3) `strings` over the installed `ck3.exe` finds the literal string
`heightmap.png` *and* the message `"original_heightmap_size specified in
heightmap.heightmap (%d, %d) is not the same resolution as the heightmap you
are trying to load (%d, %d). Size of the bitmap will be used for packing."`,
but every symbol near it is namespaced under `PdxMapEditor`
(`CHeightmapResolutionTool@PdxMapEditor`, `CEditorHeightmap@PdxMapEditor`,
`ApplyHeightmapResolution`) — the in-game **map editor**'s own tool for
*producing* the packed pair from a raw `heightmap.png`, not a runtime asset
path. Vanilla's own `heightmap.png` is 122 MB — over GitHub's 100 MB hard
limit already, which is only possible because Paradox ships it outside git —
and ours is ~126 MB at `resolution_factor = 2` (39 MB at 1×, safe). Neither
Elder Kings 2 nor Godherja was installed locally to check directly (both are
1× heightmaps anyway, so the question does not arise for them at their
shipped resolution); the vanilla-binary and `default.map` evidence above is
what this decision rests on. `[map.heightmap] ship_heightmap_png` (default
`true`, `configs/faerun.toml` sets it `false`) gates the write; set it `true`
locally to run this repo's own evidence scripts (they read `heightmap.png`
back for analysis, never the packed pair) against a generated mod.
---

## 2j. Dense axis-aligned hairline stripes at 2× — found, isolated, fixed

The first real `resolution_factor = 2` render (coordinator's own look at
`docs/evidence/heightmap_2x/renders/hillshade_spine_ours_2x.png`) showed a
dense hairline cross-hatch, mostly horizontal, on every mountain slope — not
present at 1×. Axis-aligned and 2×-only pointed at a raster-grid-locked
mechanism, not noise.

**The crop harness.** `scripts/heightmap_2x_crop.py` runs
`heightmap_detail.apply` on a real ~1 Mpx crop (Spine/Thay/Sword Coast, the
real topology/province/terrain/river inputs, cached once) instead of the
full 226 Mpx canvas — seconds per variant instead of ~10.5 minutes. §2h's
own `relief_pits_ablate_canvas.py` had ruled crop ablation out for charging
the *spectral fill's amplitude* with anything (no 256 px all-land interior
patch, `_interior_patch_spectrum` degenerates); that caveat is about gain
calibration, not about a raster-grid-locked shape defect, and the stripes
reproduce on the crop pixel-for-pixel identically to the canvas render.

**Isolation, by ablation** (`docs/evidence/heightmap_2x/crop_ablation/`,
`.npy` diffs against the shipped-config crop, `verified`):

| variant | max diff (levels) | stripes gone? |
|---|---|---|
| `no_ridged`, `isotropic_relief`, `no_erosion_diffusion`, `no_source_adaptive_gain`, `diffusion_x4` | **0** (byte-identical) | no — these passes never touch this crop's output at all (the spectral fill's gain evaluates near-zero here, a further symptom of the same degenerate-crop gain calibration §2h already named) |
| `no_wall_spread` | 1540 | no |
| `no_source_bound` | 762 | no |
| `no_deterrace_sigma` (≈0, de-terrace disabled) | 1377 | yes, but everything else changes too (raw quantisation stipple) |
| **`gaussian_deterrace`** (blind Gaussian instead of Perona-Malik) | 3537 | **yes, cleanly** |

Only swapping Perona-Malik for a blind Gaussian removes the stripes while
leaving every other pass untouched — the cause is `deterrace_cliff_aware`
itself, at 2×.

**Root cause.** CLAUDE.md's own 1× invariant already names the mechanism:
*"Perona-Malik de-terrace alone… turns a multi-pixel CK2 cliff into a 1-px
axis-aligned wall"* (a classic anisotropic-diffusion staircase-collapse: a
ramp of small risers each resists diffusion just enough that the whole drop
concentrates onto whichever edge starts largest). At 1× this is measured
(source 0.56, pass 1 alone 0.85) and `widen_concentrated_steps` (wall-spread)
corrects it. The staircase-collapse dynamic gets *more* complete the more
diffusion steps it is given, and `deterrace_iterations = sigma_px² /
(2·λ)` scales with the **square** of `deterrace_sigma_px` — itself already
correctly scaled by `resolution_factor` (§2e/§2i) — so a 2× run gets **~4×**
the 1× iteration count (54 vs 13 on the Spine crop) and the collapse has
that much more "time" to fully concentrate a drop before wall-spread ever
measures it.

**Why wall-spread, itself resolution-scaled, did not catch it.**
`wall_spread_iterations` made *no* difference at 4, 8 or 16 (crop-harness
sweep, byte-identical output each time) — the bottleneck is not smoothing
budget, it is the gate: `over = (ratio_out > max_ratio) & (ratio_out >
ratio_src + source_margin)`. `max_ratio`/`source_margin` are dimensionless
and were never scaled — reasonably, since a ratio needs no ground-distance
conversion — but they were tuned entirely against 1×'s own baseline, where
the *source's own* concentration ratio sits near 0.5. At 2× a genuine cliff
is naturally **less** concentrated (it spans ~2× more pixels), so the
source's own ratio measured on these crops is **0.23–0.29**: the 1×-tuned
gate (`max_ratio = 0.55`) never fires on this build's own manufactured
walls, because they never looked concentrated enough by the 1× yardstick
even though they were far more concentrated than *this* source's own.

**Fix, `ck2ck3.map.build`'s `detail_cfg` replace(), `resolution_factor > 1`
only:** `wall_spread_max_ratio = 0.20`, `wall_spread_source_margin = 0.05`
(from 0.55/0.15). Found by a crop-harness sweep (0.55 → 0.10 in steps),
picked at the point every one of the three regions clears check 6's own
threshold (`source + 0.35`) with room:

| region | source k=2 | k=5 | shipped (broken) k=2 | **fixed** k=2 | k=5 | threshold k=2 |
|---|---|---|---|---|---|---|
| Thay | 0.29 | 0.08 | — | **0.31** | 0.12 | 0.64 |
| Spine | 0.29 | 0.03 | 0.81 | **0.33** | 0.03 | 0.64 |
| Sword Coast | 0.23 | 0.05 | — | **0.29** | 0.00 | 0.58 |

Elevation range is unaffected (Spine crop: p99 28,954 vs 29,035, std 5873
vs 5885, both < 0.5 % — the macro terrain is untouched); only the
pathological single-pixel gradient spike shrinks (Spine crop grad p99
**1053 → 693** levels/px, max 2196 → 1446) — wall-spread finally doing the
job it was built for, not new blurring. Confirmed by eye on all three
regions (`docs/evidence/heightmap_2x/crop_ablation/crop_{region}_FIXED.png`)
and on the real, whole-canvas rebuild.

**Not scaled per-`f` from first principles** — 0.20/0.05 is an empirical fit
at `f = 2`, documented as such rather than derived, since only `f ∈ {1, 2}`
is used anywhere in this repo or its two reference total conversions.

**The FFT "2-px period power" detector the coordinator also asked for was
tried and did not discriminate the artefact cleanly** — a Nyquist-bin-power
and a near-Nyquist axis-vs-diagonal 2-D power ratio were both computed on
the source, the broken build and the fixed build (`verified`): neither
separated "broken" from "fixed" (axis/diag near-Nyquist energy 19.1 / 10.1 /
10.2 respectively — the *source* itself scored highest). The artefact is a
handful of concentrated single-pixel edges, not a periodic signal a whole-
field FFT resolves well against broadband terrain texture. Check 6
(`edge_step_orientation_counts`, already in `scripts/
verify_heightmap_detail_invariants.py`) is the direct, working detector —
it is what caught this defect and what confirms the fix — so no second,
weaker metric was added.
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
* **The output never leaves the CK2 author's own surface, plus texture**
  (§2f, since 2026-09-12). Over a window of one CK2 source pixel
  (`heightmap_detail_bound_window_px` = 3 canvas px), every land pixel
  satisfies `source_local_min - tol <= out <= source_local_max + tol`, with
  `tol` = `heightmap_detail_bound_tolerance_sigmas` (2.0) times the pixel's
  own terrain class's measured vanilla high-frequency RMS. `_bound_to_source`
  is the last pass, and it saturates rather than clips, so the bound holds by
  construction and leaves no flat spot where it binds. Checked independently
  on a finished mod by `scripts/verify_heightmap_detail_invariants.py`, which
  rebuilds the source from `topology.bmp` and reads the per-pixel terrain
  class out of the mod's own `common/province_terrain`.
  `bound_limited_pct_of_land` is in the stats dict and in the `map` step's
  summary: it is a backstop, and a number that climbs means the passes in
  front of it are writing terrain the source has no basis for. On the
  shipped build: **0 land px below the bound and 0 above**, with 95,581 px
  excluded because the plain rescale itself put them at or below the water
  level and the land invariant above raises those to the pin (`verified`,
  `docs/evidence/relief_pits/verify_invariants.log`).
* **Detail near a shore is damped, never dragged down** (§2f). Pass 4 blends
  the synthesised *offset* toward zero over the first
  `heightmap_detail_coast_smooth_px` of land, so a lake on a plateau keeps
  its shore at the height the CK2 author drew. `"blend_to_water"` restores
  build 15's behaviour, which pulled that shore 55 % of the way down to the
  global water level.
* **The erosion only runs where the source drains** (§2f). The stream-power
  law is gated on the *source's* own macro slope, one quantisation riser per
  CK2 source pixel; on flat ground the model degenerates to seed plus
  hillslope diffusion, which is texture.
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
| `heightmap_detail_fill_min_cycles_per_km` | `0.10` | pass 2: where the fill reaches full strength, one-octave cosine roll-on below; `0` reproduces build 13 (§2d), `0.05` build 15 (§2f) |
| `heightmap_detail_headroom_fraction` | `0.5` | pass 2: the fraction of a pixel's own headroom the offset may saturate into, so `tanh` cannot reach the clamp floor exactly (§2d) |
| `heightmap_detail_erosion_slope_gate_steps` | `1.0` | pass 2: the erosion may only run where the *source* has macro slope, in 277-level risers per CK2 source pixel (2.90 km); `0` reproduces build 15 (§2f) |
| `heightmap_detail_bound_window_px` | `3` | pass 5: the source bound's window, canvas px — one CK2 source pixel is 1.9543 (§2f) |
| `heightmap_detail_bound_tolerance_sigmas` | `2.0` | pass 5: the bound's tolerance, as a multiple of the terrain class's own vanilla HF RMS; `0` disables the bound (§2f) |
| `heightmap_detail_ridged_classes` | `["mountains", "desert_mountains", "hills", "terraced_hills"]` | pass 2: the classes that get a ridged relief seed (§2g) |
| `heightmap_detail_ridged_weight` | `1.0` | pass 2: how much of the seed is ridged on those classes (§2g) |
| `heightmap_detail_ridged_sharpness` | `3.0` | pass 2: the crest exponent of `(1 - abs(noise)) ** sharpness` (§2g) |
| `heightmap_detail_ridged_diffusion_scale` | `0.15` | pass 2: multiplier on the hillslope diffusion over those classes (§2g) |
| `heightmap_detail_coast_mode` | `"damp_detail"` | pass 4: damp the synthesised offset near a shore, or `"blend_to_water"` (build 15) which contracts the height toward the water level (§2f) |
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

**Gradient kurtosis is still 0.44-0.45 × vanilla on our mountain crops**
(§2g). Ridge share and ridge-line connectivity are inside ±20 % of vanilla's
own; the fourth moment of the slope is not, and nothing inside a 1 × pass got
it past 0.45 here. It is the same standing limit as the item above, measured
on shape instead of on spectrum.

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

## 2h. "Thay was still broken" — the render, the defect list, which metric sees each

Lane `thay-relief` (2026-09-23). Playtest verdict after build 17, no more
detail than that; the brief was explicit that our metrics had already
measured the wrong thing twice (§2d's MOAT, §2f's own bound hit rate), so
this section starts from a **render**, not a table.

### The render

`scripts/thay_render.py` — a hillshade and an oblique 3-D view of the Thay
window (canvas x 4752-5311, y 1583-2222, +100 px margin) for four heights:
CK2's own `topology.bmp` at native resolution, our plain rescale, a
reconstruction of build 15's settings, and the actual shipped build-17
`heightmap.png`. The vertical scale is not a choice: `WORLD_EXTENTS_Y = 51`
(`common/defines/fae_defines.txt`) is the same world-unit scale the engine
applies to the 16-bit height channel over a canvas where one heightmap texel
is one world unit horizontally on both axes (`WORLD_EXTENTS_X`/`Z` =
width/height - 1, the CLAUDE.md invariant), so
`world_height = level / 65535 * 51` with unit pixel spacing is the exact
surface normal `pdxterrain.shader` computes from this texture — no separate
exaggeration knob to get wrong. The sun is vanilla's own constant,
`sun_direction = { -4.5 3 -1 }` (x, y-up, z, `gfx/map/environment/environment.txt`),
elevation 33.1 deg, corroborated by the same file's
`terrain_sunny_sun_elevation = 0.4` (36 deg on the file's own 0..1 = 0..90 deg
scale). The camera pitch is `ZOOM_STEPS_TILT[0] = 50` deg
(`common/defines/graphic/00_graphics.txt`), the closest zoom step. Figures:
`docs/evidence/thay_relief/{hillshade,oblique}_{ck2_source,plain_rescale,build15,build17,after_fix}.png`.

**What build 17's render shows, in words.** The CK2 source and the plain
rescale both show an ordinary rugged massif around a lake, rounded, no sharp
boundary. Build 15 and build 17 both show, in the same place, a **closed
escarpment loop** — a hard, unbroken rampart maybe 500 x 600 canvas px
(740 x 890 km) around, encircling a domed interior that reads distinctly
smoother/rougher-textured than the terrain outside it, with a lake sitting
just outside the loop's eastern arc. Along the loop's southern arc the wall
is **serrated**: alternating light/dark teeth in the hillshade, a stair-step
crenellation in the oblique view — the same look the brief's b15 in-game
screenshot names. Where the render crosses an actual lake (the flat grey
patch, top area of every crop), the oblique view shows it as a dead-flat
plane meeting jagged terrain at a vertical wall — a shaft, not a shore.

Three defect classes, each with its own cause and its own metric:

### (a) The closed-loop rampart — verified, partially fixed

**Not a fabricated basin.** `scripts/relief_pits_common.closed_depression_depth`
(morphological reconstruction: the surface water would pond to) run on the
*plain rescale itself*, at 9/27/45/81 px windows, already reads up to
7,480-9,521 levels deep at the same location the render's ring sits over —
the CK2 author's own topology already carries a broad, gentle 20-90 px
macro-basin there (Thaymount is the highest pixel of the Thay window, an
isolated dome, and every isolated dome an erosion model or a diffusion
filter runs over is exactly the shape that organises a ring). What must not
happen is the *output* exceeding that by more than the terrain-class
tolerance — `closed_depression_excess = closed_depression_depth(output) -
closed_depression_depth(source)`, the new metric this section adds
(`relief_pits_common.closed_depression_excess`/`_stats`,
`EXCESS_WINDOWS_PX = (3, 9, 27)`, the task's own suggested windows: "since a
20 km bowl passes a 3 px window"). On the shipped build 17, before this
lane's fix, the excess at 9/27/45 px was p99 378/444/467, max 1837/2072/1868
levels — real, but well under half of the total depth: **most of the ring's
depth is the CK2 author's own relief**, not something the pass invented.

**The mechanism that turns a gentle 300-level undulation into a player-visible
rampart.** `_relative_terrain_gain` (the default `gain_mode = "deficit"`
path) assigns exactly one amplitude scalar per CK3 terrain class — on this
run, mountains gets gain x2.317 — applied *uniformly* to every pixel of
that class, whatever the CK2 source looks like there. A gently-domed rim the
author drew with a couple of quantisation risers over 20+ px gets the same
full ridged mountain texture (§2g) as a real 3,878-level Thay escarpment two
pixels away in the same class. Because that texture (`eroded_relief`,
`ridged_seed`) is phase-locked to the very terrain it textures, the same
amplitude reinforces *coherently* all the way around a closed contour — a
defect no single-source-pixel bound (§2f, 3 px window) can ever see, because
every pixel individually still sits inside its own tolerance; the
serration/coherence is a property of the whole loop, not of any one pixel.

**The fix.** `heightmap_detail_source_adaptive_gain = true` (new default).
`_source_roughness_factor` scales the per-terrain amplitude down (never up)
by how rough the CK2 source *already is* locally — local relief (dilation
minus erosion) over `heightmap_detail_source_adaptive_window_px` (9 px),
normalised to the pixel's own class mean, floored at
`heightmap_detail_source_adaptive_floor` (0.35) so a class border stays
seamless. A pixel on a real cliff (locally rough) keeps ~full class
amplitude; a pixel on a gentle rim (locally smooth) gets down to 35 % of it.

**Measured** (Thay window, `docs/evidence/thay_relief/`, `verified`, same
seed and config otherwise, whole-canvas run):

| metric | window | before (build 17) | after this fix |
|—-|—-|—-|—-|
| pit depth (§2f, `source_local_min - out`) | 3 px | p95 134 / p99 371 | p95 99 / p99 327 |
| pit depth | 9 px | p95 -104 / p99 71 | p95 -110 / p99 25 |
| pit depth | 27 px | p95 -347 / p99 -42 | p95 -356 / p99 -46 |
| closed-depression **excess** | 9 px | p95 49 / p99 378 / max 1837 | p95 11 / p99 308 / max 1793 |
| closed-depression **excess** | 27 px | p95 107 / p99 444 / max 2072 | p95 70 / p99 387 / max 2061 |
| closed-depression **excess** | 45 px | p95 138 / p99 467 / max 1868 | p95 98 / p99 415 / max 1905 |

Whole-canvas mean of the roughness factor: **0.694** — the fix reduces
synthesised detail amplitude by roughly 31 % on average across all land, not
only at Thay. Synthetic-fixture regression: a real escarmpent (9-step cliff)
keeps > 85 % of its amplitude with the fix on vs off
(`tests/test_map_heightmap_detail.py::test_source_adaptive_gain_shrinks_the_closed_loop_rampart`).

**Honestly: not closed.** The render after the fix
(`oblique_after_fix.png`, `hillshade_after_fix.png`) still shows the same
ring, thinner. The excess this fix touches (`amp * noise`, pass 2's own
amplitude) is a real but minority contributor; the majority of the ring's
depth is the CK2 source's own macro relief being *sharpened* by pass 1
(Perona-Malik de-terrace, §2b), which is deliberately edge-preserving and
this fix does not touch, because §2b's own cliff-survival ratios are
extensively measured and a change there risks them. **Open**, flagged for
the coordinator: either accept the ring as the CK2 author's own geography,
rendered honestly for the first time, or open a lane to soften pass 1's
response on a *closed, low-total-drop* contour specifically (which needs its
own metric to target, since §2b's flux weighting has no notion of "this
edge closes a loop").

### (b) Serrated / stair-step escarpment faces — verified, fixed

The coordinator's own read of `oblique_after_fix.png` against
`oblique_ck2_source.png`: the west/south escarpment is a row of **vertical
black slabs, axis-aligned**, that the CK2 source does not have — not the
gentle sawtooth this section first described, but a harder claim, and a
correct one.

**The metric** (`scripts/relief_pits_common.wall_stats`, `edge_steps`,
`cliff_drop_concentration`): for every land pixel, the biggest single-step
jump to any of its 8 neighbours, split axis-aligned (the two raster axes)
from diagonal, counted at `k_risers` in {2, 3, 5}; and, at every pixel the
*source* (plain rescale) itself marks as a cliff, the fraction of that
pixel's own local relief (`max - min` over a 5 px window, the source's own
cliff width after the 1.9543x LANCZOS upsample plus a pixel of margin) that
shows up on its single biggest output edge — the **drop-concentration
ratio**. 1.0 means the entire visible drop happens in one pixel-to-pixel
step; a slope spread continuously over the source's own width reads well
under it.

**Measured** (`docs/evidence/thay_relief/wall_stats.csv`, `scripts/thay_wall_report.py`,
a real `configs/faerun.toml` conversion, `verified`):

| region | map | axis/diag k=2 | axis/diag k=5 | drop conc. p50 | p95 | max |
|---|---|---|---|---|---|---|
| Thay | source (plain rescale) | 0.56 | 0.22 | 0.35 | 0.60 | 1.00 |
| Thay | build 17 (shipped) | 0.77 | 0.49 | 0.38 | 0.64 | 1.00 |
| Thay | **pass 1 alone** (Perona-Malik, isolated) | **0.85** | **0.53** | 0.39 | 0.71 | 1.00 |
| Thay | **this build** | 0.69 | 0.38 | 0.33 | 0.47 | 1.00 |
| Spine | source (plain rescale) | 0.57 | 0.20 | 0.36 | 0.61 | 1.00 |
| Spine | build 17 (shipped) | 0.80 | 0.48 | 0.37 | 0.65 | 0.98 |
| Spine | **this build** | 0.67 | 0.37 | 0.32 | 0.46 | 0.76 |

The Spine of the World -- the lane's other standing study crop, no closed
basin, genuinely rugged relief throughout -- shows the same pattern: build
17's axis bias (0.57 -> 0.80 at k=2) is not a Thay-specific artefact, and
this build brings it back most of the way (0.67) with the drop-concentration
max actually *below* the source's own (0.76 vs 1.00) rather than merely
closer to it. Before/after renders:
`{hillshade,oblique}_spine_{ck2_source,plain_rescale,build17,ours}.png`.

**Cause, found by ablation.** Pass 1 in isolation — before the spectral
fill, the erosion or the bound ever run — already carries axis/diag from the
source's 0.56 to **0.85**, higher than the full build-17 pipeline (0.77):
the later passes slightly *dilute* the defect, they do not cause it. This is
Perona-Malik's classic staircasing failure: a ramp of several small
quantisation risers, each individually resisting diffusion just enough
(`exp(-(delta/cliff_step)^2)`), does not merge into one smooth slope —
whichever single edge starts out largest diffuses least, stays largest, and
after enough iterations the whole local drop has collapsed onto it, while
its immediate neighbours flatten out. On a square raster that edge is
axis-aligned by construction, which is the "vertical" the coordinator named.
An 8-connected flux (diagonal neighbours added, weight 0.5, lambda rescaled
to keep the same flat-region blur) was tried and only partly helps (0.85 to
0.81 at k=2): the staircase is a property of the conductance-driven positive
feedback, not of which neighbours it runs over.

**The fix — pass 1b, `heightmap_detail_wall_spread_enabled`** (new default
`true`, `heightmap_erosion.widen_concentrated_steps`). At every pixel, the
drop-concentration ratio is measured on both the *output* and the *source*
(same window); where the output's ratio exceeds the source's own by more
than `heightmap_detail_wall_spread_source_margin` (0.15) **and** exceeds
`heightmap_detail_wall_spread_max_ratio` (0.55) in absolute terms, that
pixel (plus a 2 px margin, so the wall does not just reappear one pixel
over) gets a few extra iterations
(`heightmap_detail_wall_spread_iterations` = 4) of plain Gaussian diffusion
(`heightmap_detail_wall_spread_sigma_px` = 1.0), until the excess
concentration is gone. Comparing against the *source's own* ratio, not
against zero or a fixed constant, is the point: a CK2 author is entitled to
draw a cliff genuinely one source pixel wide (the source's own Nyquist
allows it, `docs/map_scale.md`), and that must survive untouched — the
plateau fixture's clean single-pixel escarpment keeps 99 % of its step
(`tests/test_map_heightmap_detail.py::test_wall_spread_leaves_a_genuinely_one_pixel_cliff_alone`),
while a diagonal cliff spread over the source's own 3 px width has its
axis-bias driven back toward the source's own ratio
(`test_wall_spread_moves_a_diagonal_cliff_back_toward_the_source_ratio`).
Cliff amplitude cost, whole Thay window: mean local relief at real
(>=5-riser) cliff pixels 8127 -> 8009 levels against the source's 8420
(-1.4 %, `verified`).

**First attempt regressed two existing tests, and that is worth recording.**
An absolute-threshold version (any pixel whose ratio exceeded 0.55, full
stop) passed the Thay validation but broke
`test_the_bound_still_keeps_the_multi_step_cliff` (a genuinely one-pixel
synthetic escarpment collapsed from 2445 to 277 levels — 89 % gone) and
`test_the_coast_pass_no_longer_drags_high_ground_toward_the_water_level`
(the lake-shore pin, a legitimate near-vertical wall by the engine's own
rule, got flagged as "a wall" and smoothed into a 7,600-level crater — the
exact defect `damp_detail` exists to prevent). Both were the same mistake:
measuring the output's concentration against zero instead of against the
*source's own* concentration at that pixel, and both a synthetic 1-px cliff
and a lake shore are supposed to be concentrated. The source-relative gate
fixed both without losing the Thay improvement (`tests/test_map_heightmap_detail.py`,
56 passed).

**New invariant** (`scripts/verify_heightmap_detail_invariants.py` check 6,
`check_wall_concentration`): reports axis/diag at k=2/3/5 and the
drop-concentration percentiles against the same plain-rescale baseline this
section measures with, and fails the run if `axis_over_diag_k2` sits more
than `WALL_AXIS_OVER_DIAG_HEADROOM` (0.35) above the *source's own* ratio —
a real gate, not informational, since this fix is validated to close most of
the gap rather than only reduce it.

### (c) Lakes as vertical-walled holes — verified intrinsic, a question for the user, least-bad treatment proposed

`build17`'s crop reads level **[0, 39865]**: Thay's plateau lakes sit at
`sea_floor = 0` (`ck2ck3.map.heightmap.deepen_sea`) beside land at
13,000-40,000 — a shaft, not a shore, and the oblique render shows exactly
that (a dead-flat plane meeting jagged terrain at a vertical wall).

**Would CK2 have drawn it the same way? No** (`verified`): the CK2-source
render (`hillshade_ck2_source.png`, `oblique_ck2_source.png`) uses
`topology.bmp`'s own elevation at the lake, with no separate water pin
applied at all — the lake bed is part of one continuous, gently-sloping
surface, the same as every other CK2 pixel. CK2 never forced a single global
water level onto a high-altitude lake; **this is intrinsic to CK3's single
`WATERLEVEL` define**, not a CK2-vs-CK3 authoring difference and not
something this pass introduced (§2f already reached the same conclusion for
the *crater* half of this; this section adds the direct source comparison).

**Least-bad treatment, proposed, not implemented** (per instruction: propose,
do not invent):

1. **A sloped lake-shore ramp inside the plateau bound.** Extend
   `_smooth_coast`'s `damp_detail` radius specifically for a water province
   whose *source* elevation sits far above the surrounding regional water
   level (a "high lake" flag, e.g. source elevation > 2x the class's typical
   coastal elevation), tapering the drop over 20-40 px instead of the
   current 4, so the wall reads as a valley side, not a cliff. Costs: softens
   a real elevation fact (CK3 cannot avoid a hole there) into a longer,
   gentler descent — still not what CK2 drew, but not a shaft either.
   Illustrated (a whole-window 40 px taper, not the selective per-province
   version above, and not fed back through the real pipeline):
   `hillshade_lake_wide_ramp.png`, `oblique_lake_wide_ramp.png`.
2. **Flag the highest-altitude lake/river provinces for conversion to
   marsh/land**, a human-reviewed `overrides/` entry per province (not a
   blanket rule): a county whose CK2 lake sits on a genuine plateau becomes a
   marsh or a small landlocked county instead of a CK3 water province.
   Changes gameplay (a barony gained), not just visuals, and is a per-county
   judgement call the converter should not make unattended. Illustrated (a
   harmonic in-paint of the water pixels from their land neighbours, purely
   a rendering mock-up of the idea, not a real classification change):
   `hillshade_lake_marsh_fill.png`, `oblique_lake_marsh_fill.png`.

**The user's decision (2026-09-23): option 2, marsh/land via
`overrides/lake_to_land.csv`.** Not the ramp.

**Implementation** (`src/ck2ck3/map/lake_to_land.py`, wired into
`ck2ck3.map.build` at three independent points, each patching an array a
DIFFERENT downstream pass reads, because none of the three is derived from
the others):

1. **Province classification.** `patch_water_ids` removes the overridden
   CK2 id from `lake_ids` **and** `river_ids` **and** `sea_ids`, before
   baronies/`idmap`/`default.map` ever see them. A CK2 lake id is *also* a
   `sea_zones` id (CK2 defines a lake as a sea zone inside a `Lakes`-named
   `ocean_region`, `ck2read.Ck2DefaultMap.lake_ids`), and
   `ck2ck3.map.idmap.build`'s own rule is `is_sea = in sea_ids and not in
   lake_ids and not in river_ids` -- so removing the id from `lake_ids`
   alone does not make it land, it makes it a *different kind of water*
   (`verified`, twice: the first real conversion run found the override
   silently had no effect at all because the CLI's own config builder
   never read the two new keys, §2h iii below; the second found
   `default.map` still listing every overridden province, now under
   `sea_zones` instead of `lakes`, because only `lake_ids` had been
   patched). All three sets have to move together. From here the existing
   untitled-land rule (`docs/step_map_baronies.md`) forces
   `impassable_mountains` unless CK2 happens to give the province a real
   title -- the same identity every other titleless CK2 land province
   already gets, no new CK3-identity code.
2. **Terrain.** `patch_codes` forces every one of the province's own pixels
   to one CK2 terrain-category code, in the *same* per-pixel grid both the
   gameplay-terrain majority vote and the paint pass read (one patch fixes
   both): `marsh` -> CK2's own `marsh` category (Faerûn's `terrain.txt`
   index 15, -> CK3 `wetlands`); `land` -> the mode of the codes among the
   already-land pixels in a ring around the province.
3. **Heightmap.** `inpaint_heights` -- the actual fix for the shaft, and
   the reason "reclassify the province" is not enough on its own: CK2 draws
   a lake's own `topology.bmp` pixels near sea level *regardless of the
   plateau under it* (Lake Thaylambar is raw bytes 85-92 of 255, whatever
   is around it -- `scripts/measure_high_lakes.py`'s first version measured
   the lake's own pixels and found all 95 of Faerûn's lakes within 0.1
   riser of each other for exactly this reason). So `deepen_sea`'s own
   water test (`heights <= water_level`, a raw-height threshold with no
   province lookup at all) would flatten these pixels to the sea floor
   whether or not the province is reclassified. `inpaint_heights` runs a
   harmonic (Laplace) fill from the surrounding land's own plain-rescale
   elevation, *before* `deepen_sea`, so the pin never fires and the
   detail pass's own source bound (§2f) sees plateau-height pixels like any
   other land.

**The measurement, and why the 5 Thay lakes are in the file anyway.**
`scripts/measure_high_lakes.py` cannot use the lake's own pixels (see
above); it measures a `--ring-px` (15) dilation ring of *land* pixels
around each lake instead, plain-rescale elevation, in risers above
`water_level`. Whole-canvas distribution over Faerûn's 95 lakes: p50 6.0,
p75 8.5, p90 12.0, p95 15.0, p99 19.0, max 27.0. `--min-risers 10` gates
`docs/evidence/lake_to_land_proposed.csv` (12 rows, everywhere else on the
map) -- roughly the p75-p90 boundary, a defensible "clearly on elevated
ground" cutoff given the median lake (6 risers, ~1,662 levels above the
pin) is an ordinary valley pond. **The 5 Thay lakes measure only 3-8
risers** (Lake Thaylambar 8, Tirulag/Yeshelmaar 4, Murthil/Flamm 3) --
*below* that threshold, and are in `overrides/lake_to_land.csv` anyway,
because the render evidence, not the riser count, is what put them there:
`oblique_build17.png`/`hillshade_build17.png` show them as shafts, measured
independently by the whole-canvas closed-depression/pit metrics in §2h(a).
The two measurements answer different questions -- "how much higher is the
shore than the water level" (a lake sitting in its own local dip can score
low on this even on a genuinely high plateau, since a lake occupies the
*lowest* point of its immediate surroundings almost by definition) against
"does the render show a shaft" -- and only the second is what the user
asked to fix. **`--min-risers` should not drop to catch them by the same
rule**: lowering it to 3 to sweep in Thay's own lakes would also sweep in
every ordinary valley pond within a few hundred levels of the water line
that never had a render problem in the first place (`docs/evidence/lake_to_land_proposed.csv`
at `--min-risers 3` would have been the whole `candidates.csv` file, 80 of
95 lakes). The whole-canvas proposals list stays threshold-gated; a Thay-like
case elsewhere on the map should be added to `overrides/lake_to_land.csv`
the same way Thay's own five were -- because a render showed it, not
because a number crossed a line.

**Bugs found on the way to a working fix, both by real conversion runs, not
by the unit tests** (`docs/DECISIONS.md`): (1) the CLI-facing config
builder (`ck2ck3.steps.map._map_config`) never read the two new `[map]`
keys -- a documented, named failure mode in this repo
(`test_cli_config_builder_reads_the_key`, an established pattern this
module should have used from the start and now does); (2) `patch_water_ids`
originally only touched `lake_ids`/`river_ids`, leaving the id in
`sea_ids` and flipping it to a *true sea* province instead of land. Both
are now regression-tested (`tests/test_map_lake_to_land.py`) and both are
checked independently of the unit tests on a finished mod:
`scripts/verify_heightmap_detail_invariants.py` check 7 reads
`overrides/lake_to_land.csv` and `default.map` directly and fails if any
overridden province is still in `sea_zones`/`lakes`/`river_provinces`.

### Whole-canvas regression

One real `configs/faerun.toml` conversion, `map` step only
(`docs/evidence/thay_relief_map_run.log`): **190.9 s** (heightmap detail
67 s of it), against build 17's own recorded 142.8 s (§2f) — the
`source_adaptive_gain` roughness field costs two whole-canvas morphological
filters and one Gaussian blur, ~+12 s of the detail pass's own total, the
rest is this build also carrying the `province-edges` lane's cost that
§2f's own figure predates. `scripts/verify_heightmap_detail_invariants.py`
on the lane output: land/water pin holds, source bound (2sigma over 3 px)
holds, `docs/evidence/thay_relief_invariants.log`. `source_adaptive_gain`
only ever *reduces* amplitude (never raises it above the class target), so
it cannot make the spectrum or pit metrics worse; the Spine of the World
window, same before/after comparison, confirms it does not
(`verified`): pit depth p95/p99 at 3 px 140/404 -> 140/370, shape metrics
(gradient kurtosis 1.721 -> 1.722, ridge share 0.1263 -> 0.1227) within
noise, closed-depression excess at 27 px p99 717 -> 712 — a small, uniform
improvement, not a Thay-specific one, because the Spine's own terrain is
already closer to its class's average roughness than Thay's isolated dome.

**`wall_spread` on top, `map` step only**: **203.3 s**
(`docs/evidence/thay_relief_map_run2.log`), +12.4 s over the
`source_adaptive_gain`-only figure above -- one extra concentration-ratio
pass (an 8-neighbour max, two morphological filters and up to 4 targeted
Gaussian iterations, but the last only runs where a pixel is still flagged
"over" after the previous one, so most of the canvas exits after 1). A full
conversion (all steps) with both fixes: `docs/evidence/thay_relief_full_run2.log`.
`scripts/verify_heightmap_detail_invariants.py` on that output (check 6, the
new wall-concentration gate): passes -- axis/diag k=2 sits within the
`WALL_AXIS_OVER_DIAG_HEADROOM` (0.35) of the source's own ratio on both
regions this section measures (`docs/evidence/thay_relief_invariants2.log`).
ck3-tiger, full mod: `docs/evidence/thay_relief_tiger2.txt` -- this lane
touches only heightmap raster synthesis, no generated script/history/loc
content, so the fatal/error counts are unchanged from the pre-lane baseline
(fatal 0, error 58).

### §2h (d) The rings are CK2 river provinces (coordinator, 2026-09-23)

After the wall fix and the lake override, Thay's oblique render still showed the
closed escarpment loop. Overlaying the water-pinned pixels (`heightmap <= 4883`) on
the hillshade (`docs/evidence/thay_relief/diag_water_pin.png`) settles it
(`verified`): every ring is a CK2 **river province** — `RIVER_MURGHOL`,
`LOWER_RIVER_MURGHOL`, `RIVER_UMBER`, `UPPER_`/`LOWER_RAUTHENFLOW_RIVER` — a 2–4 px
water province that the detail pass pins to CK3's single global water level, so it
is cut as a canyon thousands of levels deep all the way round the plateau. Same
mechanism as the lake shafts, in linear form; it is what "plateaux dipping then
coming back up" has been since playtest 3. `rivers.png` (the drawn river) is a
different, thinner line and is not the cause (`diag_rivers_borders.png`). Next:
decide the treatment for high-ground river provinces (lane follow-up).

### §2h (d) implementation: `valley` -- a river stays a river, its bed stops being pinned

**1. Measurement, whole canvas, same ring method as the lakes**
(`scripts/measure_high_rivers.py`, `docs/evidence/river_valley_candidates.csv`):
surrounding-land elevation (15 px dilation ring, excluding all water) minus
the water level, in risers. 86 CK2 river provinces on the canvas; p50 5.0
risers, p90 8.0, p99 11.7, max 16.0. Eight provinces read >= 10 risers, six
of them the coordinator's own five Thay rivers plus a newly-measured
geographic neighbour (`Lake Umber`, CK2 id 2029, `kind=river` despite the
name -- confusingly named but the same defect). The other two (`Fire River`,
`River Xon`) sit outside Thay and are left as proposals, not applied
(`docs/evidence/river_valleys_proposed.csv`), matching the lake lane's own
precedent of only touching the region the render actually shows broken.
Every one of these six provinces' own `topology.bmp` pixels is CK2's flat
sea-level anchor (raw byte 92/255, the same value the Thay lakes measured),
`verified` the same way `scripts/measure_high_lakes.py` first found it for
lakes -- so this is the identical mechanism, not a coincidence.

**2. Vanilla check, before deciding the treatment**
(`scripts/measure_vanilla_river_provinces.py`): is a `river_provinces`
pixel above `WATERLEVEL` legal in CK3 at all? Read vanilla's own
`WATERLEVEL` define (`../claudespace/game_files/common/defines/00_defines.txt`,
`3.0/50 * 65535` = 3932 in 16-bit levels) and vanilla's own
`map_data/{provinces.png,heightmap.png,definition.csv,default.map}`
directly (2x upsampling the province-id raster to match the 2x heightmap).
Result, `verified`: 224 vanilla river provinces, 424,016 px; heights range
0-4,960 (p50 2,676, p99 3,642), and **433 px (0.10 %) in 14 of 224
provinces sit above the water level**, up to +1,028 levels. So yes, it is
legal -- CK3 renders it exactly like any other land-adjacent water pixel;
there is no separate "river above water" shader path, because the engine's
water surface is the same whole-map plane `jomini_water_default.fxh`
already paints everywhere (CLAUDE.md's own water-surface invariant). The
larger finding is the useful one: vanilla river provinces are **not**
flatly pinned at all -- they follow real terrain (rivers run downhill,
hence mostly below water), with rare small excursions above it where the
terrain does. Ours were only flat because `heightmap_detail.apply`'s
land/water clamp treats every water province (sea, lake, river) identically
regardless of kind. This is the evidence base for `valley`: it is not
fabricated behaviour, it restores what a river province is allowed to look
like and CK2 itself never modelled.

**3. The `valley` action** (`src/ck2ck3/map/lake_to_land.py`,
`overrides/river_valleys.csv`, schema identical to `lake_to_land.csv`:
`ck2_id,action,reason`, `read_overrides` is shared). Unlike `marsh`/`land`,
a `valley` row:
- is **skipped** by `patch_water_ids` (`WATER_STAYING_ACTIONS = (VALLEY,)`)
  -- `sea_ids`/`lake_ids`/`river_ids` are untouched, so the province stays
  exactly the water province CK2 had it as: navigable, in
  `river_provinces`/`sea_zones`, `is_water=True` all the way through
  `idmap.build`;
- is carved, not inpainted (`carve_valleys`): a harmonic bank estimate
  seeded from **true land only** (`land_mask = ~water_mask`, excluding
  every other still-pinned water province, unlike `inpaint_heights`'s
  looser boundary) via normalized-convolution + iterative blur-restore,
  minus a shallow `depth` (300 levels, deliberately smaller than
  `heightmap_detail_river_depth`'s 900-level traced-line carve and within
  the §2f per-terrain tolerance band of 193-427), clipped to
  `(water_level, bank]` so the result is never level with the bank and
  never at or below the water level either;
- runs **before** `heightmap.deepen_sea`, same reason as the lake inpaint:
  `deepen_sea`'s own water test is a raw-height threshold with no province
  lookup (`heights <= water_level`), so the height has to be raised before
  it runs or the pin reappears regardless of classification;
- widens the **heightmap-detail land mask only** (`valley_mask`,
  `heightmap_land_mask = ~water_mask | valley_mask_arr` in `build.py`) so
  the normal cliff-aware/wall-spread/source-bound pipeline treats these
  pixels like ordinary land on top of the carved base -- the province
  classification (`water_mask`, what `default.map` and the terrain vote
  read) is left alone, only what `heightmap_detail.apply`'s closing clamp
  is allowed to do to these pixels changes.
- `rivers.png` needed no extra work: `rivers.render` paints
  `out[water_mask] = WATER` directly, and a `valley` province's
  `water_mask` bit is still set (`patch_water_ids` never touched it), so
  its course was already drawn there before this change and stays drawn.

CLI wiring followed the lake lane's own established lesson (`docs/DECISIONS.md`,
Bug #1): `river_valleys`/`river_valleys_csv` were added to
`ck2ck3.steps.map._map_config` -- the real CLI config builder -- in the same
commit as the module code, proven by
`tests/test_map_lake_to_land.py::test_cli_config_builder_reads_the_key`
(extended, not duplicated) before `build.py` was ever wired to read them.
Run-report counters (`river_valleys_rules`, `river_valleys_heights_holes_px`,
`river_valleys_depth`) and a summary-line fragment were added to
`ck2ck3.steps.map.run` in the same commit as the CLI-config change, not
after a run caught them missing -- applying Bug #1's lesson proactively
this time instead of repeating it.

**4. Invariants** (`scripts/verify_heightmap_detail_invariants.py`):
- check 7 (`overrides/lake_to_land.csv`) is unchanged: a `marsh`/`land`
  province must have LEFT every `default.map` water list.
- **check 8** (`overrides/river_valleys.csv`, new): the opposite assertion
  -- a `valley` province must have STAYED in a `default.map` water list
  (fails loudly if a future change to `patch_water_ids` ever stops skipping
  `WATER_STAYING_ACTIONS`), and must have NO pixel at or below the water
  level any more, and must not be perfectly flat (a std-dev-zero result
  would read as a new pin at a different level, not a carved bed). Its
  province-id set is also handed back to `main()` so the generic check 2
  loop (every water province <= water level) skips exactly these ids --
  they are supposed to violate that rule now, by design.
- **check 9** (new, "no narrow water-pinned canyon"): a standing regression
  check generalising the diagnostic above, run over *every* water province
  on the canvas, named in an override or not. True width is
  `2 x distance_transform_edt(mask).max()` (the widest inscribed circle's
  diameter) -- not `measure_high_rivers.py`'s circle-equivalent-diameter
  area proxy, which reads 28-56 px for these same five provinces because it
  folds their *length* into the estimate. Calibrated directly off the
  pre-fix 22:26 mod (`docs/evidence/thay_relief/`): the five named rivers
  measured true width 8.5-10.0 px, ring risers (same 15 px ring, same
  formula as the measurement script) 4.0-10.0, 100 % of their own pixels
  pinned; `Lake Umber` (30 px wide, 3.0 risers) is the nearest miss and is
  correctly excluded by the width gate alone. Gate:
  `NARROW_CANYON_WIDTH_PX = 12.0`, `NARROW_CANYON_MIN_RISERS = 3.0`,
  `NARROW_CANYON_RING_PX = 15`. A province only trips it while **still
  fully pinned** (`(own_vals <= water_level).all()`), so a `valley` row
  that carved correctly no longer matches at all -- this check is a
  regression gate for the *next* unnoticed high water province, not a
  duplicate of check 8.

**5. The coordinator's catch: "min > water_level" passed while the canyon
was unchanged.** The first cut of `carve_valleys` (§ above) reported
`bank_median 5347.6` -- measured, not merely claimed, `docs/evidence/thay_relief_map_debug1.log`
-- against the 6545-7653 these same six provinces were proposed from
(`scripts/measure_high_rivers.py`). Root cause: that first cut seeded a
harmonic (iterative Gaussian blur-and-restore) fill from `land_mask` alone
(true land, excluding *every* water province on the canvas, not only the
six holes). That made every OTHER water province -- every sea, every
still-pinned river -- simultaneously "free" in the same diffusion, so a
hole's effective neighbourhood was the whole connected water network it
drains into, not its own bank; 400 iterations at sigma 1.5 px (effective
reach ~30 px) cannot cross that to reach real land, and the un-reached
interior stayed near its `water_level` fallback. `carve_valleys` is
rewritten (`src/ck2ck3/map/lake_to_land.py`): a direct ring-dilation search
per province, widened in powers of two from `ring_px=15` (identical to
`measure_high_rivers.py`'s own already-verified method) up to
`ring_max_px=240` for the rare province boxed in by other water --
proximity search, never diffusion through a possibly enormous shared water
body. Re-measured: `bank_median 6545.0` (matches the proposal exactly),
`carved_median 6245.0` -- `bank - depth`, on the nose
(`docs/evidence/thay_relief_map_debug2.log`).

**Check 8 is now the hard gate the coordinator asked for**: bed vs bank,
not "not pinned". `scripts/verify_heightmap_detail_invariants.py`
measures each province's own bed median against a 15 px land ring around
it (the same measurement, so a bank number here is directly comparable to
the one a row was proposed from) and fails if `bank - bed` exceeds
`depth (300) + tol (1000, headroom for heightmap_detail's own texture
synthesis on top of the carve)`. This is the check that actually caught
the bug above once written -- "min > water_level" and "not perfectly flat"
both passed on the broken run.

Two more bugs the hard gate's own first run surfaced, both in the
*invariants script*, not the pipeline: (1) `check_source_bound` (existing
check 3) flagged 264 land px "above the bound" for the first time ever,
because it independently rebuilds "source" from the raw, un-carved
`topology.bmp` and a valley province's own source there is still near the
water level -- excluded now by province classification (dilated by the
bound's own `window_px`, since a bank pixel's local window can still reach
one step into the valley) alongside the existing per-pixel `source <=
water_level` rule. (2) that exclusion first did nothing at all (264 stayed
264): `np.isin(key, list(valley_ids))` compared packed provinces.png RGB
keys against small integer province ids from `definition.csv` -- never
equal by construction. Fixed by mapping id -> rgb -> packed key through
`definition` first, the same lookup every other per-province check in this
script already does.

**6. Full run, invariants, ck3-tiger** (`wt/_out/thay-relief`,
`docs/evidence/thay_relief_full_run4.log`): `map` step summary line names
`river_valleys 6 CK2 river provinces carved (10223 px, depth 300.0)`.
`scripts/verify_heightmap_detail_invariants.py`
(`docs/evidence/thay_relief_invariants8.log`): **invariants hold** -- check
7 (lake_to_land) clean, check 8 (river_valleys, bed-vs-bank hard gate)
clean, check 9 (narrow canyon) "none on a province this lane's overrides
target" (+ 77 elsewhere, informational, out of scope -- DECISIONS.md), the
pre-existing source bound (check 3) 0 px under / 0 px over. Direct sample
of the six provinces' own pixels in the finished `heightmap.png`
(`verified`): min 5015-6216 (all above the 4883 water level), median
5408-7239 -- e.g. River Umber min 6216 / median 7239 / max 7525, Lower
Rauthenflow River 6129 / 6740 / 6931 -- against 100%
at-or-below-water-level before any fix. ck3-tiger
(`docs/evidence/thay_relief_tiger4.txt`): fatal 0, error 58 -- unchanged
from the pre-lane baseline.

**7. Renders: fixed numerically, and the ring in them is a different,
already-known defect.** `scripts/thay_render.py --extra
final_v2=<heightmap.png>` -> `docs/evidence/thay_relief/{hillshade,oblique}_final_v2.png`.
Looked at directly, as instructed: `final_v2` still shows the same-looking
ring as every earlier render. `scripts/thay_water_pin_overlay.py` (the
coordinator's own ad hoc water-pin-in-red diagnostic, now a script)
settles what the ring's pixels actually are on the *finished* mod
(`docs/evidence/thay_relief/diag_water_pin_v2.png`): every still-pinned
(red) pixel in the Thay crop belongs to `NORTHERN_ALAMBER_SEA`,
`EASTERN_WIZARDS_REACH`, `TRACKLESS_DEEP`, `LAKE_ASHANE`, `ALAMBER_SEA`,
`WESTERN_WIZARDS_REACH`, `SEA_OF_DLURG` -- real seas and one real lake,
correctly pinned; none of the six carved provinces appear in that tally at
all. A second, geometric diagnostic settles it beyond doubt
(`docs/evidence/thay_relief/diag_valley_mask_v2.png`): the six carved
provinces' own pixels, highlighted directly on the same hillshade the ring
appears in, are two small, thin features off to the side (one river
mouth, one short reach) -- nowhere near the ring's own path around the
central peak. The ring is therefore the already-documented Thaymount
escarpment/closed depression (§2h: 7,480-9,521 levels in the CK2 source
itself, `heightmap_detail_source_adaptive_gain` cuts the excess ~20-30%,
does not close it -- a real, if harsh, cliff, not a canyon this task's
provinces caused) plus the real coastline against Lake Ashane and the
surrounding seas. The coordinator's original §2h (d) diagnosis named these
six rivers as *the* cause of the ring; the evidence above says they were
never large enough to be visible in it at all (a 300-level shallow valley
against an escarpment reading in the thousands) -- a second, independent
defect was misattributed to the first. Reopening the escarpment closure is
outside this task's own stated scope (the five/six named river provinces),
so it is recorded here, not attempted.

### §2h (e) The rings were black lines in CK2's provinces.bmp (coordinator, 2026-09-24)

`verified`: the thin water-pinned ring pixels around Thaymount all belong to
`TRACKLESS_DEEP` (id 4275), the padding ocean — not to any river province.
Faerûn's CK2 `provinces.bmp` carries **16,786 pure-black pixels in 50 thin
components** that `definition.csv` does not define; around Thay they trace the
plateau escarpments. `provinces._keys_to_ids` sent every undefined colour to
`PADDING`, so each drawn line became a one-pixel strip of ocean inside the land,
pinned to CK3's global water level: the canyon rings every Thay playtest since
playtest 3 reported, and the "1-px walls" of §2h (b). Fix:
`provinces.fill_undefined_lines` gives every undefined *non-white* pixel its
nearest defined province (white stays padding ocean). Result: the rings and the
slabs are gone from the render (`hillshade_final_v3.png`, `oblique_final_v3.png`);
3710 baronies placed (was 3704), invariants hold, ck3-tiger fatal 0 / error 58.
Lesson: every earlier pass moved its own metric while the render stayed broken —
the defect was in the id raster, upstream of every relief pass.
