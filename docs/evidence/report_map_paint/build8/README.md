# `docs/report_map_paint.md`, first edition — build 8 numbers

Every CSV and PNG here was measured on `/home/cvdbdo/git/paradox/ck3/wt/_out/seafloor`,
a **build-8** conversion (2026-09-10, lane `seafloor`): Gaussian de-terrace
σ 1.6 px, isotropic `f^−2.0` spectral fill, terrain-class tree meshes, no
province-history terrain override.

They are kept so the report can quote both editions. The current edition's
numbers, measured on build 12 (the live mod, converter `main` c9bc250), are one
directory up. Regenerate either with:

```
uv run --with matplotlib python scripts/report_map_paint_plots.py \
    --mod <conversion dir> --recompute
```

`hf_achieved.csv` here is the odd one out: it was transcribed from
`docs/evidence/HANDOFF_map_heightmap_detail.md`, not measured by the plot
script. The build-12 edition measures it.
