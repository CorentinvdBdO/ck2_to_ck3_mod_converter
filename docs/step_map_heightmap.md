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

1. **De-terrace** — a small Gaussian (`heightmap_detail_deterrace_sigma_px`,
   default 1.6 canvas px) on land only removes the transfer curve's risers.
   Legitimate because the real signal is band-limited to the CK2 source's own
   Nyquist frequency anyway (`docs/map_scale.md`), so nothing true is lost.
2. **Spectral fill** — vanilla's land elevation is a clean power law,
   amplitude ∝ f^slope (`heightmap_detail_spectral_slope`, default −2.0,
   fitted vanilla exponent). The pass fits that law to the heightmap's own
   well-resolved low frequencies (0.004–0.03 cycles/km), computes the
   per-frequency shortfall against it, and injects noise shaped to exactly
   that deficit. The noise is then scaled **per pixel** so every CK3 terrain
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

## 3. Invariants — what cannot break, and why it cannot

* **Every water pixel is returned byte-identical to the plain rescale.**
  `land_mask` comes from the province raster plus `default.map`'s
  `sea_zones`/lake data (`Ck3Province.is_water`: sea, lake, or river-type
  province, the padding ocean included) — not a topology-value threshold —
  and `apply()` never writes a value at a `land_mask=False` pixel; the sea
  pin and every coastline hold by construction, not by a clamp.
* **Every land pixel ends strictly above `water_level` and at or below
  `max_level`.** The last step of `apply()` is
  `np.clip(land_values, water_level + 1, max_level)`, after all four passes.
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
| `heightmap_detail_deterrace_sigma_px` | `1.6` | pass 1 Gaussian sigma |
| `heightmap_detail_spectral_slope` | `-2.0` | pass 2 power-law exponent |
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

## 6. Cost

* Packing efficiency: the packed-heightmap tile deduper (`docs/formats_packed_heightmap.md`)
  dedupes identical tiles far better with 212 distinct values than with the
  tens of thousands the detail pass adds, so `packed_heightmap.png` grows —
  measured size in `docs/evidence/HANDOFF_map_heightmap_detail.md`.
* Runtime: three whole-canvas FFT2 calls (spectral fit, noise synthesis) plus
  a handful of Gaussian filters and two `distance_transform_edt` calls — all
  vectorised, no per-pixel Python loop. Measured elapsed time is in the same
  hand-off doc; the requirement was to stay under ~2 minutes for the whole
  pass on the 8320×6784 canvas.

## 7. What this pass does not fix

Vanilla's detail is *structured* — dendritic valleys, ridge lines, drainage.
This pass's noise is isotropic with the right amplitude and the right
spectrum, not the right shape: side by side it reads as gravel where vanilla
reads as landscape (`docs/map_fidelity.md` §4.2). Closing that gap needs
ridged-multifractal noise or a hydraulic-erosion pass — a different order of
work, and a look call for a human, not this lane's scope.

**Measured after shipping (report lane, 2026-09-10, `verified`,
`docs/evidence/report_map_paint/spectrum.csv`, `land_stats.csv`).** Two
corrections to the claims above:

* **The band above 0.08 cycles/km is under-filled.** Over 48 all-land interior
  256×256 patches the shipped map carries 80 levels at 0.1 cycles/km against
  vanilla's 215, and 10 against 45 at 0.2 — *less* than the plain rescale
  (152, 61) there. The de-terrace Gaussian (σ = 1.6 px) is a low-pass at about
  2.4 km and pass 2 puts back roughly an order of magnitude less than vanilla
  above 0.08 cycles/km. The earlier evidence crop (`docs/evidence/heightmap_detail/spectrum.png`)
  looked right only because it contains a coastline, whose 4884-level step
  inflates every frequency. Candidate fix: a smaller de-terrace sigma or a
  frequency-dependent gain in pass 2, re-measured on interior patches.
  Tracked in `docs/integration_backlog.md`.
* **The macro tails move.** The pass holds land p50 (9038 → 9240, +2.2 %) but
  raises p95 by 9.4 % and p99 by 20.2 %, and coast smoothing pulls p01/p05
  down to the water level. "Frequencies below 0.01 cycles/km are never
  touched" is true of pass 2 alone; the coast pass and the per-terrain gain
  seams do reshape the extremes. Whether that is acceptable is a look call.

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
