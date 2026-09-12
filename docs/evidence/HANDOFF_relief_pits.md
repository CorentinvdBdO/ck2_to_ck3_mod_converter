# Hand-off — lane `relief-pits` (2026-09-12)

Playtest 4 of build 15 reported two things about the heightmap. The first is
diagnosed and fixed; the second is measured, improved threefold, and **still
short of the target** — §3 is the honest version.

Reference: `docs/step_map_heightmap.md` §2f (the pits and the bound), §2g
(ridged relief), §3 (invariants), §5 (the nine new `[map]` keys). Decisions:
`docs/DECISIONS.md`, 2026-09-12. Evidence: `docs/evidence/relief_pits/`.

## 1. "Thay's pits are even larger"

**The §2d metric measured the wrong thing, and that is the first finding.**
MOAT is cliff-foot undershoot *minus* the same statistic away from a cliff,
so a defect that digs holes everywhere cancels out of it: it read **−116** on
Thay while the pits were real. The replacement is absolute —
`source_local_min − output` over a window of one CK2 source pixel
(`scripts/relief_pits_common.pit_depth`), reported as p95/p99 and the
fraction of land more than one 277-level riser down.

**The cause was pass 4, the coast smoothing — none of the three candidates
the brief named.** Faerûn's CK2 lakes and river provinces sit on high ground
(median such pixel in the Thay crop 14,301), CK3's water level is global, so
each is already a hole punched through a 20,000-level plateau; the old
`_smooth_coast` then pulled the ring of land around it 55 % of the way down
to the water level as well. Thay window, by zone, build 15 → this build:

| zone | share of land | pit p95 / p99 / max |
|---|---|---|
| within 5 px of a water province | 8.4 % | **4086 / 6644 / 8141** → **53 / 191 / 427** |
| within 4 px of a traced river | 6.4 % | 748 / 1217 / 3279 → 427 / 618 / 623 |
| plateau interior | 85.2 % | 290 / 788 / 3044 → 60 / 263 / 829 |

Acquitted, with a whole-canvas ablation (`pits_ablate_before.csv`):
Perona–Malik (pit p99 **76** on its own); the erosion carving the plateau top
— removing the incision makes the pits **worse** (p95 572 → 774) and white
noise in its place changes nothing (564). The spectral fill owns half the p95
and none of the tail.

**The ablation has to run at full canvas size.** On a 768 px crop under
build-15 settings the deficit comes out identically zero and `eroded`,
`isotropic` and `erosion_incision = 0` produce *byte-identical* output — so
`relief_sharp_moat.py --mode isolate` cannot charge the fill or the erosion
with anything. `scripts/relief_pits_ablate_canvas.py` exists for that reason.

## 2. Result, the shipped build (a real `configs/faerun.toml` conversion)

| | Thay pit p95 / p99 / > 1 riser | Spine | bound | `map` step |
|---|---|---|---|---|
| build 15 | 576 / 2612 / **9.34 %** | 514 / 1353 / 8.80 % | 8.81 % of land outside | 143 s |
| this build | **136 / 392 / 1.78 %** | **140 / 393 / 1.73 %** | **0 land px outside**, backstop moves 2.87 % | **142.8 s** |

Four changes, each measured on its own in §2f: `coast_mode = "damp_detail"`
(the whole p99 tail), the erosion slope gate (a correctness fix that costs a
little), the source bound, and `fill_min_cycles_per_km` 0.05 → **0.10**,
which is what makes the bound a backstop rather than a mechanism. The
interior spectrum *improves* at 6.7 and 10 km (1.13 / 1.14 × vanilla against
build 15's 0.65 / 0.92) and returns to the plain rescale at 14–25 km, which
is §2d's own argument carried one octave further.

## 3. "Erosion is still creating smooth mountains instead of sharp ones"

Shape, not spectrum, and **measured on the land mask eroded by 4 px** — one
lake shore is a one-pixel drop of thousands of levels and dominates a fourth
moment: unmasked, build 15's Thaymount crop reads gradient kurtosis **66.1**
against vanilla's 23.2, and **3.0** on its own interior. Against the mean of
vanilla's three mountain crops:

| | grad kurtosis | ridge share | ridge run px |
|---|---|---|---|
| build 15 | 0.29 / **0.13 ×** | 1.10 / 1.06 × | 1.18 / 0.86 × |
| this build | 0.44 / **0.45 ×** | **1.04 / 1.02 ×** | 1.18 / 0.77 × |

* **ridge share hits the ±20 % target**; ridge-line connectivity is 1.18 × on
  the Spine and 0.77 × on Thaymount.
* **gradient kurtosis does not**: tripled, still less than half of vanilla's.
  Two structural reasons, both in §2g — the metric lives at the top of a 1 ×
  sheet's band (Nyquist 0.337 against vanilla's 0.674, §7/§2e), and §2b's
  de-terrace deliberately spends the quantisation risers that give the *plain
  rescale* its 0.42–0.84 ×. `resolution_factor = 2` is the lever; nothing
  inside a 1 × pass got past 0.45 here.

Deliverable figures: `hillshade_{spine,thaymount}_{plain_rescale,build15,after}.png`
against `hillshade_vanilla_mountains.png`, all 512 px = 760 km at 1.4839
km/px.

## 4. Verification

* `uv run pytest` — **1305 passed** (50 in `tests/test_map_heightmap_detail.py`,
  10 of them new: the terraced-plateau bound + ponding + cliff tests with a
  negative control, the erosion gate, the coast crater, the ridged seed).
* `scripts/verify_heightmap_detail_invariants.py` on the lane output
  (`verify_invariants.log`): 3915 land / 361 water provinces, **0** land px
  at or below water, **0** water px above, 39,458 distinct 16-bit values, and
  the §2f bound checked independently from `topology.bmp` + the mod's own
  `common/province_terrain` — **0 land px below the bound, 0 above**, with
  95,581 px excluded because the plain rescale itself put them at or below
  the water level and the land invariant raises those to the pin.
* `ck3-tiger` — **fatal 0, error 58** (41 loc-hash collisions, 14
  wrong-gender, 2 unknown-field, 1 history), `warning(rivers)` 319: every
  total identical to build 15's own run (`tiger_relief_pits_summary.txt`).
* No in-game run, by instruction.

## 5. What the coordinator has to decide

1. **Gradient kurtosis is 0.45 × vanilla, not 0.8–1.2 ×.** Either accept the
   shape as-is and close, or open a `resolution_factor = 2` lane (§2e has
   its cost: 182 MB pair, 348 s, 19.8 GB RSS, and two module-level pixel
   constants to fix first).
2. **The erosion slope gate costs 310 → 337 on the Thay pit p95.** Kept on
   correctness grounds; `heightmap_detail_erosion_slope_gate_steps = 0`
   removes it.
3. **`river_depth = 900` now spends the whole bound tolerance on every river
   pixel** (Thay river band p99 618). Whether a river valley should be inside
   the tolerance is a look call.
4. **The coast pass no longer drags a shore toward the water level**, so a
   real ocean beach is now the CK2 source's own profile rather than a
   synthetic ramp. Nothing measured says that is worse; it has not been seen
   in game.

## 6. What a reader should run

```
uv run python scripts/relief_pits_diagnose.py --mode live  --region both --maps after=<out>/map_data/heightmap.png
uv run python scripts/relief_pits_diagnose.py --mode zones --region both --maps after=<out>/map_data/heightmap.png
uv run python scripts/relief_pits_ablate_canvas.py [--fast]      # ~10 min
uv run python scripts/relief_pits_shape.py    --maps after=<out>/map_data/heightmap.png
uv run python scripts/relief_pits_spectrum.py after=<out>/map_data/heightmap.png
uv run scripts/verify_heightmap_detail_invariants.py <out mod dir>
```

The transect figures need matplotlib: `PYTHONPATH=$PWD/src uv run --with
matplotlib python scripts/relief_pits_diagnose.py --mode live ...`.
