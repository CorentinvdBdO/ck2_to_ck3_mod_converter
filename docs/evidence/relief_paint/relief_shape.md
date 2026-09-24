# Relief shape: drainage density + valley cross-section, vs vanilla

`scripts/measure_relief_shape.py /home/cvdbdo/git/paradox/ck3/wt/_out/relief-paint/map_data/heightmap.png --tag relief-paint`, 2.5s.

## Cited from docs/step_map_heightmap.md §2g (not re-measured here)
- gradient kurtosis: **0.44-0.45x vanilla** on the interior (8 px high-pass, land mask eroded 4 px), against 1.10-1.14x in build 15 before the ridged seed. `resolution_factor = 2` is the identified lever; nothing inside a 1x pass got past 0.45x.
- ridge_share: **1.02-1.04x vanilla**, inside +-20%.
- ridge_mean_run_px: 1.18x on the Spine, 0.77x on Thaymount (crests break up more than vanilla's there).

## New measurements (this lane)
- **drainage density** (channel px / land px at a fixed absolute flow-accumulation cutoff, vanilla's own pooled 98th percentile 87.4): vanilla mean **0.0200**; spine **0.0076** (0.38x vanilla); thay **0.0079** (0.40x vanilla); 
- **valley cross-section (width at 75% depth / width at 25% depth, higher = more V-shaped)**: vanilla mean **2.0**; spine **2.0** (60 transects); thay **1.875** (60 transects); 

## Recommendation
The amplitude and now the crest-vs-dune shape (ridged seed, §2g) are both close to vanilla at 1x resolution; the measured ceiling is gradient kurtosis 0.45x, which the same section already attributes to two structural facts at 1x, not a tunable parameter: the metric's own 8 px high-pass sits at 0.337 cycles/km against vanilla's 0.674 Nyquist (half the frequency resolution to work with), and the cliff-aware de-terrace deliberately spends the quantisation risers that gave the *plain rescale* its higher kurtosis. **Recommendation for the next heightmap lane: `resolution_factor = 2` is necessary to move gradient kurtosis past ~0.45x; nothing paint-side or erosion-parameter-side at 1x can buy more headroom** (measured ceiling, not a guess) — see docs/step_map_heightmap.md §2e for its shipped cost (182 MB pair, 348 s, 19.8 GB peak RSS) before taking that lever. Drainage density and valley shape (this lane's two new numbers) are independent of resolution_factor and should be re-measured once ridged relief or erosion parameters change, against this script's own vanilla baseline.

**New finding this run: drainage density is 0.38-0.40x vanilla** at the same absolute accumulation cutoff — fewer well-defined channels than vanilla carries at the same crop scale, even though valley cross-section shape (V vs U) already matches vanilla closely. This is independent of the ridged-seed / gradient-kurtosis finding above and is a candidate for the erosion's own `erosion_accum_iterations`/`erosion_iterations` (catchment size) rather than `resolution_factor` — flagged for the thay-relief lane, not fixed here (heightmap modules out of scope for this lane).
