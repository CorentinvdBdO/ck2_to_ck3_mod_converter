# Painting Faerûn: micro-scale similarity with vanilla, macro-scale fidelity to CK2

**Method in one paragraph.** The converter reads five CK2 bitmaps — `topology.bmp`,
`terrain.bmp`, `trees.bmp`, `rivers.bmp`, `provinces.bmp` — and writes the rasters
CK3's renderer actually samples: `map_data/heightmap.png` (through the packed
pair), `gfx/map/terrain/detail_index.tga` and `detail_intensity.tga`,
`gfx/map/terrain/colormap.dds`, and 18 tree-instance files under
`gfx/map/map_object_data/generated/`. Nothing is authored by hand and no map
editor is involved: every output is a pixel-wise function of a CK2 bitmap and a
table of numbers measured off the vanilla CK3 install. This report is about where
those two inputs meet.

## The two axes

Every decision in the paint pipeline answers one of two questions, and only one:

| | CK2 Faerûn supplies | vanilla CK3 supplies |
|---|---|---|
| what | **where** things are | **what a map looks like at 1 km** |
| examples | coastlines, mountain ranges, Anauroch, which pixels are forest, the profile of the Spine of the World | material palette, blend statistics, height spectrum, per-terrain detail amplitude, colour saturation, tree density |
| test | does the continent still have Faerûn's geography? | would this measurement pass for a vanilla screenshot? |

Call these **macro** and **micro**. They are not in tension in principle, but the
CK2 data is far too coarse to carry the micro axis on its own — Faerûn's source
elevation is 8-bit at 2.90 km per pixel — and vanilla's own rasters know nothing
about Faerûn. So each pass either preserves a CK2 macro fact or matches a measured
vanilla micro statistic, and the passes are ordered so a micro pass can never
overwrite a macro one.

The two axes meet at one number. `docs/map_scale.md` fits vanilla CK3's own scale
at **1.4839 km per pixel** (core-Europe latitude fit, R² 0.9962) and Faerûn's at
**2.90 km per pixel** (atlas scale bar), giving a scale factor of **1.9543** and a
canvas of **8320 × 6784**. Choosing to preserve Faerûn's real size is macro
conservation, but it is also what makes every micro measurement transferable: a
vanilla pixel and one of ours now cover the same ground, so sigmas, densities and
correlation lengths measured on vanilla can be used unconverted.

---

## 1. Elevation: rescale for macro, synthesise for micro

The rescale is a piecewise-linear transfer curve pinned at `0 → 0`,
`ck2_sea_level 95 → ck3_water_level 4883`, `255 → ck3_max_level 49205`,
LANCZOS-resized onto the canvas (`ck2ck3.map.heightmap`). It is exact macro
conservation and nothing else: our land percentiles match the CK2 source's to four
figures.

It is also unusable as a finished map. An 8-bit source through that curve leaves
160 usable land steps **277 sixteen-bit levels apart**, and Faerûn measures
**212 distinct height values** map-wide against vanilla's **31,516** (`verified`,
`docs/evidence/map_fidelity/heightmap_stats.csv`). The failure is not flatness —
the plain rescale's high-pass RMS, 319, is *higher* than vanilla's 283 — it is that
all of the extra energy is terrace risers rather than terrain.

`ck2ck3.map.heightmap_detail` fixes the micro axis in four passes: de-terrace
(Gaussian σ = 1.6 canvas px, land only), spectral fill against vanilla's fitted
`amplitude ∝ f^−2.0` land law, river-valley carving, coast smoothing. Two vanilla
measurements drive it. The exponent −2.0 holds over two decades of vanilla's own
spectrum (−2.03 fitted on 0.02–0.6 cycles/km, −1.98 on 0.05–0.6, −2.08 on
0.005–0.05, `verified`). And the amplitude is not global: vanilla's own
high-frequency RMS runs from **70 levels for taiga to 323 for desert_mountains**, a
factor of 4.6, so the injected noise is scaled per pixel by the terrain class the
majority vote has already assigned.

![Per-terrain high-frequency amplitude](evidence/report_map_paint/fig1_hf_targets.png)

*Figure 1 — the calibration table the detail pass obeys, and what it achieved.
Black is vanilla's own measurement (`hf_by_terrain.csv`); red and blue are the
shipped map. The ordering mountains ≫ hills ≫ plains ≫ taiga is reproduced. The
all-land average overshoots by 1.1–1.5×; the interior-only average (> 20 px from
any coast — the like-for-like comparison, since vanilla's own table excludes any
window touching water) sits at 0.83–1.34× of target.
`docs/evidence/report_map_paint/hf_achieved.csv`.*

![Radial power spectrum](evidence/report_map_paint/fig2_spectrum.png)

*Figure 2 — the single best micro-similarity test. 256 × 256 all-land patches,
n = 48 per map, radially averaged, log-log. The CK2 source (purple) is an order of
magnitude short of vanilla everywhere above 0.02 cycles/km. The plain rescale
(blue) rises to meet vanilla near 0.1 c/km, but that rise is the quantisation
floor, not terrain. The shipped map (red) tracks the f^−2.0 law from 0.02 to
0.06 c/km and then falls away — see §6. The thin red curve is the same shipped
array over the Sword Coast crop the prototype was tuned on; it contains a
coastline, whose 4884-level step flatters every frequency.
`docs/evidence/report_map_paint/spectrum.csv`.*

![Height histogram and land percentiles](evidence/report_map_paint/fig3_heights.png)

*Figure 3 — micro detail added without moving macro geography. Left: a 1400-level
window of the land-height histogram. The plain rescale is a comb with teeth 277
levels apart; the shipped map is continuous. Map-wide the distinct-value count goes
**212 → 44,522**, against vanilla's 31,516. Right: land-elevation percentiles. The
plain rescale sits exactly on the CK2 source (open circles) — the rescale invents
nothing. The detail pass holds the middle of the distribution (p50 9038 → 9240,
+2.2 %) but does move the tails (p95 +9.4 %, p99 +20.2 %, and p01/p05 pulled down
to the water level by coast smoothing).
`docs/evidence/report_map_paint/land_stats.csv`.*

Three invariants keep the micro pass off the macro one by construction rather than
by clamping: every water pixel is returned byte-identical to the plain rescale (the
land mask comes from the province raster, not a height threshold); every land pixel
ends strictly above the water level; and frequencies below 0.01 cycles/km are never
touched, so the CK2 source's real mountains and valleys survive. The pass is
deterministic (`heightmap_detail_seed = 1357`) and costs 10.9 s on the full canvas.

## 2. The sea floor: vanilla's shape, not CK2's noise

CK2 carries almost no bathymetry. Rescaled, Faerûn's entire ocean landed in
`[1439, 4883]` — a median only **39 % of the way below the water surface** — and CK3
paints shallow water as sand, so the Sea of Swords came out beach-coloured in the
in-game check (`docs/step_map_paint.md` §9.6).

There was no macro fact to preserve here: the CK2 sea floor is not Faerûn geography,
it is an artefact of a bitmap that only ever had to say "wet". So this pass is pure
micro imitation. Vanilla's own sea floor is a **flat 0** — p25, median and p75 of its
underwater pixels are all 0 (`verified` against `game/map_data/heightmap.png`).
`heightmap.deepen_sea` takes that shape: every water pixel to `sea_floor = 0`, with a
linear ramp over `sea_shelf_px = 24` px of distance from the nearest land, so beaches
and straits keep a gradient instead of dropping off a wall.

![Sea-floor transect](evidence/report_map_paint/fig4_seafloor.png)

*Figure 4 — one canvas row west from Waterdeep into the Sea of Swords. Blue is the
CK2-derived floor, sitting only 700–1900 levels below the surface; red is the
shipped map, at vanilla's 0, with the 24 px shelf visible as the ramp at each shore
and around the shoals near x ≈ 1930–2020. Map-wide the water median goes 2981 → 0
and p75 4420 → 0, with 14.0 % of water pixels left on the shelf. Land is untouched.
`docs/evidence/report_map_paint/seafloor_transect.csv`.*

## 3. Terrain paint: CK2 picks the class, vanilla picks the texture

CK3 does not render terrain from the 120 mask PNGs its `materials.settings` names.
It reads `detail_index.tga` (four material ordinals per pixel, in declaration order)
and `detail_intensity.tga` (their weights, summing to exactly 255). `verified`, and
usefully so: 49.1 % of sampled non-zero channels in vanilla's own bake name a
material whose shipped mask is 0 at that pixel, so the masks are map-editor input,
and a converter that writes the pair directly never needs the editor.

The split is clean. **Macro**: each pixel's CK2 terrain category, through
`CK2_TO_CK3_TERRAIN`, gives a CK3 terrain key — including the `trees.bmp` promotion
to `forest`, without which Faerûn's forests would vanish, since its `terrain.bmp`
forest index has zero pixels. **Micro**: `mappings/terrain_paint.csv` maps each of
the 17 CK3 keys to a (primary, secondary) pair of **existing vanilla materials**, so
colour and tiling match vanilla by construction and no `.dds` is authored. Vanilla's
class edges are dithered where CK2's palette edges are hard, so the
primary/secondary blend weight is a Gaussian-filtered noise field (σ = 1.5 px,
seed 11, 16 quantisation steps).

The material table was audited against vanilla's own bake
(`scripts/verify_terrain_paint_materials.py`, which reads what material vanilla
itself paints for each terrain key). It found one real bug — `forest` was painted
with `forest_pine_01`, byte-identical to `taiga`'s primary, giving broadleaf forest
a conifer texture, where vanilla's own pick is `forest_leaf_01` at 75.5 % share —
and resolved two flagged judgement calls against data (`terraced_hills` →
`farm_paddy_01`, 56.5 % share; `desert_mountains` swapped to lead with
`desert_rocky`, 36.9 %).

![Terrain composition](evidence/report_map_paint/fig5_composition.png)

*Figure 5 — read back out of the shipped `detail_index.tga`, land only. Our
composition is CK2's, not vanilla's, and deliberately so: plains 21.4 %,
hills 15.7 %, steppe 13.9 %, taiga 13.7 %, mountains 13.4 %, desert 9.0 %,
forest 6.7 %, against vanilla's 68.3 % plains. The one large gap between the purple
and red bars is `forest`, which comes from `trees.bmp` rather than `terrain.bmp`.
This is what macro conservation looks like when it works: the micro machinery is
entirely vanilla's, and none of it dragged vanilla's geography along with it.
`docs/evidence/report_map_paint/terrain_area_share.csv`.*

Format was settled by reading vanilla and two shipped total conversions rather than
by guessing: vanilla's pair is TGA image type 2 (uncompressed), Elder Kings 2 and
Godherja both ship type 10 (RLE) at full resolution, and `ck3.exe` names
`detail_index.tga` exactly twice, both times next to a literal `.tga`, so DDS is not
worth the risk. At full resolution the pair is 452 MB and `detail_intensity` cannot
clear GitHub's 100 MB cap in any container — the noise field is the cost, not the
format — so the shipped setting is `tga_rle` at `terrain_paint_scale = 0.5`:
**2.33 MB + 54.55 MB**, loaded in game with no texture error.

## 4. Colour: a measured tint, after a resample that was the wrong idea

The first attempt resampled CK2's own `map/terrain/colormap.dds` onto the canvas.
The in-game check killed it: the ground went pale blue-white and the ocean brown.
The cause is a category error worth recording. Vanilla's `colormap.dds` is a
near-neutral **tint** multiplied over the material textures (131,129,131 over ocean,
148,125,106 over France); CK2's is a saturated **satellite image** of CK2's own
world with no sea/land distinction, and its arctic patch landed on Waterdeep.
Resampling a macro asset does not produce a micro-correct one.

The replacement is a measurement.
`scripts/measure_vanilla_colormap_tints.py` pairs every pixel of vanilla's
`colormap.dds` with the same pixel of its `detail_index.tga` and accumulates a mean
RGB per material over land — 102 rows, every mean inside a tight near-neutral band
(R 115–154, G 114–142, B 96–140). `mappings/colormap_tints.csv` then looks up each
CK3 terrain key's **primary material in the table we already have** and takes that
material's measured mean, so there is no second hand-picked table. Water pixels get
vanilla's own measured sea/lake tint. The blur is measured too: the radially
averaged autocorrelation of a high-passed, guaranteed-all-land crop of vanilla's
colormap first drops to 1/e at **9 px**, used unconverted because our canvas is
built to vanilla's km/px.

![Colour](evidence/report_map_paint/fig6_colour.png)

*Figure 6 — left, the per-terrain tints, each bar drawn in its own literal colour;
they look grey because vanilla's are grey. Right, the autocorrelation curve the blur
sigma comes from. On the shipped map, land saturation (max − min channel) is
**4.18** against vanilla's weighted land mean of **6.97**, and water **1.02**
against vanilla's **0.85** — under vanilla on land, within a point on water.
`mappings/colormap_tints.csv`, `docs/evidence/vanilla_colormap_blur.csv`,
`docs/step_map_paint.md` §9.7.*

## 5. Trees: CK2's mask, vanilla's density, our own classes

CK3 has no tree bitmap; trees are placed instances. Vanilla places **549,126** of
them over its 9216 × 4608 canvas — 0.012931 per pixel — which at the same visual
density is a target of **729,838** for ours. Eligibility is macro (any non-zero
`trees.bmp` pixel, upsampled 8× and resampled onto the canvas, minus water and
impassable); density is micro (vanilla's own figure); mesh choice is neither CK2's
palette nor a guess, but the pixel's own CK3 terrain class through
`mappings/tree_meshes.csv`, because no CK2 index → species mapping was ever
confirmed. **711,875 of 729,838 placed (97.5 %)**; the 17,963 dropped are on desert,
mountains and farmlands, which have no mesh row by design.

![Tree scatter](evidence/report_map_paint/fig7_trees.png)

*Figure 7 — instances per generator file. We use 6 of vanilla's 18 generators and
lean heavily on `tree_leaf_high`, because Faerûn's forests are broadleaf and our
mesh choice follows terrain class rather than vanilla's regional variety. Our total
is 30 % above vanilla's because our canvas is 33 % larger; the per-pixel density is
vanilla's own. `docs/evidence/report_map_paint/tree_counts.csv`.*

**Superseded 2026-09-10 (lane `trees-regional`).** The mesh choice is no longer
terrain class alone: it samples vanilla's own measured
`P(mesh | terrain, climate, latitude band)`. 17 of the 18 generators are now used,
the largest single one falls from 47.7 % to 25.9 % of all instances, and pine's
share of the two northernmost bands goes 14.3 % → 72.1 % against vanilla's own
92.6 %. Same 711,875 instances at the same places — only the mesh changed.
Method, tables and the band × species figure: `docs/step_map_paint.md` §9.9,
`docs/evidence/tree_mix/`.

## 6. What is still not vanilla-like

**Half of vanilla's spatial bandwidth, by construction.** We ship a 1× heightmap, so
our Nyquist is 0.337 cycles/km against vanilla's 0.674 (`verified`). No detail pass
can reach past it. `resolution_factor = 2` is a one-line change and a large one in
bytes.

**And we do not fill the bandwidth we have.** Measured over 48 all-land interior
patches, the shipped map carries **80 levels at 0.1 cycles/km against vanilla's 215,
and 10 against 45 at 0.2** — less, there, than even the plain rescale did (152 and
61). The de-terrace Gaussian is a hard low-pass at about 2.4 km and the spectral
fill puts back roughly an order of magnitude less than vanilla has above
0.08 cycles/km. This is a new measurement from this report (`verified`,
`docs/evidence/report_map_paint/spectrum.csv`), and it does not contradict figure 1:
the 6 km high-pass that amplitude check uses is dominated by the 0.03–0.06 band,
where we do match. Below roughly 12 km wavelength, interior Faerûn is smoother than
vanilla. The earlier lane's evidence crop looked better than this because it is a
coastal crop.

**Isotropic noise, not landscape.** Vanilla's detail is dendritic — valleys, ridge
lines, drainage. Ours has the right amplitude and, in band, the right spectrum, but
the wrong shape; side by side it reads as gravel. Ridged-multifractal noise or a
hydraulic-erosion pass is a different order of work and a human's look call.

**`assumed`, not `verified`.** Equating an autocorrelation e-folding radius with a
Gaussian sigma is exact only for blurred white noise, and one 1024 × 1024 sample
region stands in for the whole vanilla map, so blur σ = 9 px is `assumed`. So is the
visual quality of half-resolution terrain paint at close zoom: it loads without
error and reads correctly at the zoom the camera probe reaches, but nobody has
looked at it from ground level.

**Unreviewed.** 758 counties took a CK2 `positions.txt` port-slot seed for their
coastal city holding, moving barony borders relative to the previous farthest-point
sampling. Nobody has reviewed those duchy sheets, and in the original study 28.4 %
of proposed seeds landed in a different barony than the one they are assigned to
today.

---

Reproduce every figure: `uv run --with matplotlib python
scripts/report_map_paint_plots.py` (add `--recompute` to re-measure from the rasters
instead of the cached CSVs in `docs/evidence/report_map_paint/`). Sources:
`docs/step_map_paint.md`, `docs/step_map_heightmap.md`, `docs/map_fidelity.md`,
`docs/map_scale.md`. In-game screenshots of the shipped paint:
`../claudespace/docs/evidence/waterdeep_terrain.png`, `waterdeep_sea.png`,
`anauroch.png`.
