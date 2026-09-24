# Vanilla tree density vs slope
`scripts/measure_vanilla_tree_slope.py`, 549,126 instances, 23,720,182 land px, 3.3s.

## The measured curve
Relative tree density (instances per land px, normalised to the land-wide mean) is **not** a step function of slope: it rises slightly from flat ground to a broad hump around the 25th-70th slope percentile (rel. density up to 1.20 -- gentle slopes actually carry MORE trees than dead-flat ground), then declines smoothly and never quite disappears (0.271 relative density even in the steepest 0.5% of land). This is a real, gradual avoidance of steep ground, not a hard cliff -- vanilla never gates trees off a slope threshold outright.

**Density first sustains below half the land mean at the 95th land-slope percentile.** `[map] trees_slope_gate_percentile` default is set to this value for when the gate is turned on, but because vanilla's own curve is gradual rather than a cutoff, `[map] trees_slope_gate` **defaults to false** — a hard percentile gate is a coarser model than what this measurement actually shows, and the honest recommendation is a future graded density multiplier, not a binary cutoff (`docs/step_map_paint.md` §11).

Full table: `docs/evidence/vanilla_tree_slope.csv`.
