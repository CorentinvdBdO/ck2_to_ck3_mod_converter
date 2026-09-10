# Hand-off — lane `relief-sharp` (2026-09-10)

Playtest 3 of build 13 reported two things about the heightmap. One is fixed
and measured; the other is quantified and deliberately not shipped.

## 1. "Thay has a big issue: plateaux are dipping then coming back up"

**Cause — two, neither of them the one the brief guessed first.** Full
argument and every table: `docs/step_map_heightmap.md` §2d.

* **The stream-power law was handed the escarpment as its slope.**
  `eroded_relief` runs `dz = −K (A/A_ref)^m S` on `base + fractal seed`, and
  `S` on Thay's escarpments is up to **4,505 levels/px against a land median
  of 128**. It planed the plateau rims and the uniform uplift handed the mean
  back to the interior: the returned field averaged **−1,142 levels on cliff
  pixels and +632 twelve pixels away**, a 1,773-level trench around every
  escarpment before the spectral pass ran (`verified`).
* **The fill was filling a band that was never a deficit.** It matched
  vanilla's spectrum down to `KEEP_STRUCTURE_BELOW_KM` = 0.01 cycles/km.
  Vanilla carries 7,100 levels at 47 km and our interior 0.51 × of it, so the
  pass injected ~6,100 levels of 47 km relief on ground the CK2 author drew
  flat. The CK2 source is 4096 × 3328 upscaled 1.9543 ×, its own Nyquist is
  0.172 cycles/km, and a quantiser only *adds* broadband noise — so the
  shortfall down there is Faerûn's relief against Europe's, not a deficit.
  This is the user's "amplified variations way too much", exactly.

**Acquitted, with evidence:** Perona–Malik's 13 % edge overshoot (§2b) — on
its own it leaves *less* undershoot than the plain rescale, and the blind
Gaussian is worse; the coast pass and `deepen_sea` (Thay's crop is 322 km
from water, the coast factor is 1 throughout); the river carve (moves MOAT by
9 levels); `gain_mode = "deficit"` (`hf_target` still leaves +1153).

**Fix.** Two new `[map]` keys, both proved read by
`tests/test_map_heightmap_detail.py` and both named in the `map` step's
summary line in `docs/evidence/last_run.md`:
`heightmap_detail_erosion_slope_ceiling_steps = 0.5` and
`heightmap_detail_fill_min_cycles_per_km = 0.05`. A third,
`heightmap_detail_headroom_fraction = 0.5`, is a bound rather than a fix (it
changes nothing measurable; it makes the clamp floor unreachable by
construction).

**Measured, whole canvas.** Cliff-foot undershoot in excess of the same fill
on flat ground ("MOAT"), Thay / Spine study crops, province land mask:

| | Thay MOAT | Spine MOAT | Δ RMS Thay | land on clamp floor |
|---|---|---|---|---|
| build 13 | **+2927** | **+2350** | 2464 | 0.382 % |
| this build | **−116** | **−72** | 804 | 0.377 % |

Negative means the cliff foot is *flatter* than ordinary ground under the
same fill. Cliffs are kept: Thay's steepest edge is still a 3,878-level
(14-riser) one-pixel step. Interior spectrum 0.05–0.10 cycles/km stays at
0.93–0.97 × vanilla; 0.01–0.03 returns to the plain rescale's 0.51–0.69 ×,
which is Faerûn's own macro relief.

**A measurement trap that cost this lane an afternoon, now in the scripts.**
`plain_rescale > water_level` is **not** the land mask. Faerûn's CK2 lakes
and river provinces sit on high ground (the median such pixel in the Thay
crop is at 14,301), so that test calls 10,020 Thay water pixels land and
reads the water pin under them as a 9,000-level trench — it inflated the
first Thay figure ~2.5 ×. Use `relief_sharp_common.province_land_mask`,
which reads the mask back off a finished map.

## 2. "I see the erosion, but still too smooth, not sharp enough"

`[map.heightmap] resolution_factor = 2` was prototyped on the crops and then
run over the whole canvas. Full numbers: `docs/step_map_heightmap.md` §2e.

* **It is sharper**: Thay's one-pixel gradient p99 **950 → 1888 levels/km**,
  max 2392 → 4618.
* **It needs `tile_size = 65` too.** At the shipped 33 the packer raises
  (8-bit indirection offsets cap a level at 65,536 distinct tiles; a 2×
  canvas is 220,480). 65 gives 55,120 and packs — vanilla's own 2× choice.
* **Cost**: `packed_heightmap.png` 16.3 → 51.1 MB, `heightmap.png` 39.0 →
  130.9 MB (pair 182 MB against 55 MB, over the ~150 MB budget); `map` step
  143 s → 348 s; **19.8 GB peak RSS**.
* **The band it opens is filled 3–4 × too hot**: 3.14/3.42/3.81/4.20 ×
  vanilla at 0.35/0.40/0.50/0.60 cycles/km, and already 1.49 × at 0.20.

**Recommendation: a separate lane, not this one.** `ck2ck3.map.build` now
scales `deterrace_sigma_px`, `gain_blur_px` and `coast_smooth_px` by the
resolution factor (a no-op at 1×), but `fractal_seed`'s octave sigmas and
`_carve_rivers`'s width constants are still module-level canvas-pixel
counts, so at 2× the synthetic relief and the river cross-sections sit at
half their intended ground scale. Fix those, decide the byte budget, and 2×
becomes a config change.

## 3. What a reader should run

```
uv run python scripts/relief_sharp_moat.py --mode live   # the shipped map
uv run python scripts/relief_sharp_moat.py --mode isolate --region thay
uv run python scripts/relief_sharp_slope_ceiling.py      # the field's trench
scripts/relief_sharp_ablate.sh                           # 5 whole-canvas runs
uv run --with matplotlib python scripts/relief_sharp_figures.py --after DIR
uv run python scripts/relief_sharp_2x.py                 # the crop prototype
uv run python scripts/relief_sharp_repack_2x.py <2x heightmap.png>
```

Evidence: `docs/evidence/relief_sharp/` — `moat_live.csv`,
`moat_isolate_{thay,spine}.csv`, `erosion_slope_ceiling.csv`,
`two_x_{spectrum,summary,canvas}.csv`, `transect_{thay,spine}.png`,
`hillshade_{thay,spine}.png`, and one log per run.

## 4. Open

* 0.25–0.30 cycles/km is still 1.48 / 2.11 × vanilla at 1×, unchanged by this
  lane — it is the de-terraced base's own residual riser energy (§2c, §7).
* 0.15 cycles/km fell from 0.96 × (build 13) to 0.66 ×: the fill's roll-on and
  the de-terrace both bite there. Left as it is; a shallower roll-on
  (`fill_min_cycles_per_km = 0.03`) buys it back at the cost of MOAT +331 on
  the Thay crop.
* In-game check is the coordinator's: Thay's escarpments at close zoom, and
  whether the plateau now reads flat.
