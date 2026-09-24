# Relief shape: drainage density + valley cross-section, vs vanilla

`scripts/measure_relief_shape.py /home/cvdbdo/git/paradox/ck3/wt/_out/heightmap-2x-verify/map_data/heightmap.png --tag ours_2x_fixed`, 4.4s.

## Cited from docs/step_map_heightmap.md §2g (not re-measured here)
- gradient kurtosis: **0.44-0.45x vanilla** on the interior (8 px high-pass, land mask eroded 4 px), against 1.10-1.14x in build 15 before the ridged seed. `resolution_factor = 2` is the identified lever; nothing inside a 1x pass got past 0.45x.
- ridge_share: **1.02-1.04x vanilla**, inside +-20%.
- ridge_mean_run_px: 1.18x on the Spine, 0.77x on Thaymount (crests break up more than vanilla's there).

## New measurements (this lane)
- **drainage density** (channel px / land px at a fixed absolute flow-accumulation cutoff, vanilla's own pooled 98th percentile 74.6): vanilla mean **0.0200**; spine **0.0103** (0.52x vanilla); thay **0.0139** (0.69x vanilla); 
- **valley cross-section (width at 75% depth / width at 25% depth, higher = more V-shaped)**: vanilla mean **2.1016666666666666**; spine **1.875** (60 transects); thay **2.143** (60 transects); 

## Recommendation
The amplitude and now the crest-vs-dune shape (ridged seed, §2g) are both close to vanilla at 1x resolution; the measured ceiling is gradient kurtosis 0.45x, which the same section already attributes to two structural facts at 1x, not a tunable parameter: the metric's own 8 px high-pass sits at 0.337 cycles/km against vanilla's 0.674 Nyquist (half the frequency resolution to work with), and the cliff-aware de-terrace deliberately spends the quantisation risers that gave the *plain rescale* its higher kurtosis. **Recommendation for the next heightmap lane: `resolution_factor = 2` is necessary to move gradient kurtosis past ~0.45x; nothing paint-side or erosion-parameter-side at 1x can buy more headroom** (measured ceiling, not a guess) — see docs/step_map_heightmap.md §2e for its shipped cost (182 MB pair, 348 s, 19.8 GB peak RSS) before taking that lever. Drainage density and valley shape (this lane's two new numbers) are independent of resolution_factor and should be re-measured once ridged relief or erosion parameters change, against this script's own vanilla baseline.

