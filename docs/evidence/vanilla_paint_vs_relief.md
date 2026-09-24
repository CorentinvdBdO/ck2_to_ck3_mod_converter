# Vanilla paint vs relief: in-class material variance
`scripts/measure_vanilla_relief_paint.py`, 11,998,972 vanilla land px, 18.5s.

## Fraction of in-class material entropy each relief axis explains (mean over classes with >= 200 land px)
- **slope**: mean 0.018, max 0.036 (15 classes)
- **curvature**: mean 0.015, max 0.034 (15 classes)
- **flow**: mean 0.004, max 0.015 (15 classes)
- **elevation**: mean 0.023, max 0.059 (15 classes)

Per-class detail: `docs/evidence/vanilla_paint_vs_relief_mi.csv`. Applied conditional table (slope x curvature x elevation; flow dropped, weakest axis everywhere): `docs/evidence/vanilla_paint_vs_relief.csv`.

## Per-class family palette (coordinator review finding)
Reordering a class's existing 2-3 `mappings/terrain_paint.csv` materials cannot change what a player sees when they are all one family (`mountains` = mountain_02/mountain_02_c/mountain_02_d_valleys, all `rock`, `verified`). `mappings/relief_paint_family_materials.csv` (89 rows) is each class's own real vanilla top material PER FAMILY, interior pixels only (dist > 5px from a class boundary); `docs/evidence/vanilla_paint_family_area_shares.csv` is the target family area distribution `relief_paint.py`'s output should land within +-30% of, per class.

## Patch scale (spatial coherence)
Radial-autocorrelation e-fold radius of a numeric family-score field (`scripts/measure_vanilla_colormap_blur.py`'s own method), two mountain crops: thay 4 px, spine 5 px. Mean **4.5 px** is `relief_paint_sigma_px`'s default -- the Gaussian blur width the family CHOICE is smoothed at before argmax, so the painted result reads as patches at vanilla's own scale rather than per-pixel noise.
