# Faerûn map scale — atlas registration and `positions.txt` geometry

Produced by `scripts/measure_faerun_scale.py` (`uv run python scripts/measure_faerun_scale.py`,
~2 min). Outputs alongside this file: `faerun_scale_cities.csv`,
`faerun_scale_pairs.csv`, `atlas_overlay.png`.

**Headline (verified):** the CK2 Faerûn `provinces.bmp` (4096×3328) is
**2.90 ± 0.03 km per pixel** (1.80 miles/px). The whole map is therefore
≈ 11,880 × 9,655 km (7,384 × 5,999 miles).

Source used: the miles scale bar on the canon atlas
`refs/atlas_nations_1371_guide_map.png` ("Nations of the Forgotten Realms
1371 DR", 3000×1878), transferred onto the CK2 map by a similarity
registration of the two coastlines. That atlas is copyrighted third-party
material; it is read locally and never copied into the repo. `atlas_overlay.png`
contains only a one-pixel coastline trace over our own province mask, no
atlas artwork.

---

## 1. `positions.txt` syntax

`Faerun/Faerun/map/positions.txt`, 717 KB, Windows-1252, tab-indented,
**2660 province blocks**. First ten lines verbatim (lines 1–10):

```
#Waterdeep
	1=
	{
		position={1119.000 2838.000 1116.000 2844.000 1112.000 2849.000 1117.000 2844.000 1113.000 2833.000 1111.000 2826.000 1118.000 2832.000}
		rotation={0.000 0.000 0.785 0.000 0.785 0.000 0.785}
		height={0.000 0.000 0.000 20.000 0.000 0.000 0.000}
	}
#Amphail
	2=
	{
```

Verified facts:

- The province name appears only as a `#` **comment** on the line *before* the
  id. It is not parseable data; the id line is `\t<province_id>=` with the
  brace on the next line (so a naive `id={` regex finds nothing).
- `position` is **seven x/y pairs = 14 floats**. Every one of the 2660 blocks
  has exactly 14 (verified: the set of observed list lengths is `{14}`).
- `rotation` and `height` are **seven scalars**, one per slot — not per axis.
- Rotations are radians and quantised to multiples of π/4 (`0.785`, `1.571`,
  `2.356`). `height` is `20.000` in slot 3 of **every** block and `0.000`
  everywhere else.
- Only 3 blocks have a zeroed (`0.000 0.000`) slot, all in slot 3. The mod
  fills every other slot for every province, so "unused slot" is not a usable
  discriminator here.
- The file is listed (not commented out) in `default.map`:
  `positions = "positions.txt"`.

### 1.1 Coordinate origin — y is measured from the BOTTOM (verified)

Test: compute each province's colour centroid from `provinces.bmp` (raster
coordinates, y down from the top) and compare against the slot-0 y from
`positions.txt`, both as-is and mirrored (`3328 − y`).

| assumption | median \|Δy\| over 18 named cities |
|---|---|
| y from the TOP (raster) | **1956.2 px** |
| y from the BOTTOM | **3.8 px** |

Median \|Δx\| is 3.8 px, i.e. the same magnitude. So `positions.txt` is in
`provinces.bmp` **pixel** units with the y axis flipped:
`raster_y = 3328 − positions_y`. Examples: Waterdeep `position` y = 2838.0,
centroid raster y = 480.7 (3328 − 480.7 = 2847.3, Δ 9.3);
Neverwinter 3017.0 vs 3019.5 (Δ 2.5).

### 1.2 Which slot is the city (verified by statistics, all 2660 blocks)

| slot | in its own province | on a sea/lake province | on land | rotation ≠ 0 | height ≠ 0 |
|---|---|---|---|---|---|
| **0** | **0.919** | **0.091** | **0.909** | 0.000 | 0.000 |
| 1 | 0.896 | 0.121 | 0.878 | 0.000 | 0.000 |
| 2 | 0.859 | 0.121 | 0.878 | 0.096 | 0.000 |
| 3 | 0.730 | 0.129 | 0.870 | 0.000 | 1.000 (=20.0) |
| 4 | 0.618 | **0.360** | 0.638 | 0.191 | 0.001 |
| 5 | 0.695 | 0.136 | 0.862 | 0.001 | 0.000 |
| 6 | 0.592 | 0.167 | 0.830 | 0.014 | 0.000 |

- **Slot 0 is the city / holding position.** It has the highest
  in-own-province rate and the lowest on-water rate, and its rotation is
  always 0 — a holding graphic is never rotated and never in the sea. This
  also matches the CK2 convention that the first pair is the city.
- **Slot 4 is the port** (assumed label, verified behaviour): 36 % of its
  points land on a sea or lake province, four times any other slot, and 19 %
  carry a rotation — a quay is oriented and sits in the water.
- Slot 3 is the one slot with a constant `height=20.000`; its label is
  unknown (no CK2 install available to check against vanilla).
- Caution: a "nearest to the province centroid" test does **not** identify the
  city. On the 18-city sample all seven slots sit within 16 px of the centroid
  and slot 3 wins that test (3.5 px vs slot 0's 7.8 px) — the slots are all
  within one province of each other, so the discriminator has to be
  in-province/on-land, not distance.

---

## 2. Atlas scale bar (verified)

The bar is in the bottom-left **ocean** of the atlas, not on the white page
margin, at atlas y = 983–985. Measurement method, all programmatic
(`measure_scale_bar`):

1. Restrict to the hand-read window atlas x ∈ [480, 700), y ∈ [960, 1010) —
   read off a 10× scratchpad crop, which also confirmed by eye that the tick
   labels are `0 50 100 150 200 250` over the word `MILES` (five 50-mile
   segments).
2. Classify pixels as near-black (RGB sum < 200) or near-white (sum > 720).
3. Take the row with the most near-black pixels → y = 983.
4. Measure from the first to the last black pixel on that row, inclusive.

Result: **x = 503 … 625, length 123 px for 250 miles**. The three dark runs
are x = 503–526, 552–576, 602–625, alternating with two white runs — five
even segments of ~24.6 px, consistent with 50 miles each.

```
atlas_mi_per_px = 250 / 123      = 2.0325 mi/px
atlas_km_per_px = 2.0325 × 1.609344 = 3.2710 km/px
```

Cross-check: at that scale the atlas sheet is 6,098 × 3,817 miles, plausible
for a Faerûn sheet that runs from west of the Moonshaes to Semphar and
Murghôm with ocean margins.

Uncertainty: ±1 px on a 123 px bar is ±0.8 %.

---

## 3. Registration atlas px → CK2 px

### 3.1 Method

Both maps are reduced to a **coastline mask** and matched by normalised
cross-correlation over (uniform scale, rotation, translation):

- CK2: `provinces.bmp` → province ids via `definition.csv`; water = the
  `sea_zones` / lake / major-river id ranges listed in `default.map`
  (1791–1900, 1902–1976, 1977–1986, 1987–1997, 1998–2045, 2046–2115,
  2358–2364, 2581–2586, 2630–2632, 2661–2671, 2678–2686). Land fraction 0.508.
- Atlas: water = the ocean blue `(165,192,222)` and the lake teal
  `(0,127,127)`; land = anything else except the white page margin/glacier
  and the dark-red ink of the nation boxes (those are marked *invalid* and
  contribute nothing). Atlas x < 500 is the legend margin and is cropped off.
  79,305 atlas coastline pixels.
- Coastline = pixels where a dilated water mask meets a dilated land mask;
  Gaussian-blurred (σ = 2 at the working resolution) so the fit tolerates the
  CK2 mask's province-granular jaggedness.
- Three passes, each an exhaustive FFT translation search per (scale, rotation):
  coarse at ⅛ resolution (scale 0.60–1.60 step 0.02, rotation ±8° step 2°),
  medium at ¼ (1.06–1.20 step 0.01, ±3° step 1°), fine at ½
  (1.110–1.145 step 0.0025, ±1° step 0.25°). The optimum is interior in every
  pass and lands on rotation exactly 0 at every resolution.

### 3.2 Fitted transform (verified)

```
ck2 = 1.1275 · R(+0.000°) · (atlas − (500, 0)) + (514.0, 66.0)

i.e.  ck2_x = 1.1275 · atlas_x − 49.75
      ck2_y = 1.1275 · atlas_y + 66.00
```

| | scale | rotation | translation | RMS over landmarks |
|---|---|---|---|---|
| coastline NCC (primary) | **1.1275** | **+0.000°** | (514.0, 66.0) | 1.93 px |
| least squares on 7 landmarks | 1.1264 | +0.003° | (513.8, 67.7) | **1.51 px** |

The two independent fits agree to 0.1 % in scale and 0.003° in rotation. The
CK2 map is an unrotated, uniformly scaled copy of this atlas's projection.

### 3.3 Landmarks and residuals

Landmarks are **island centroids**, located *independently on each map* by the
same rule: inside a hand-read window, take the largest 4-connected land
component that does not touch the window border, then its centroid. The
windows were read by eye off previews and are listed in `LANDMARK_WINDOWS` at
the top of the script; the landmark points themselves are not hand-placed, so
these residuals are real and not fitted.

| landmark | atlas px | CK2 px observed | CK2 px predicted | dx | dy | \|r\| |
|---|---|---|---|---|---|---|
| Ruathym | (751.3, 386.0) | (795.5, 502.9) | (797.3, 501.2) | +1.8 | −1.7 | 2.48 |
| Tuern | (757.9, 208.5) | (803.7, 300.1) | (804.8, 301.0) | +1.1 | +1.0 | 1.49 |
| Mintarn | (823.3, 597.0) | (878.8, 741.4) | (878.5, 739.1) | −0.3 | −2.3 | 2.32 |
| Nimbral | (559.7, 1808.0) | (580.3, 2103.1) | (581.3, 2104.5) | +1.0 | +1.4 | 1.72 |
| Lantan | (837.7, 1210.6) | (895.2, 1431.6) | (894.8, 1431.0) | −0.4 | −0.6 | 0.72 |
| Moonshae — Gwynneth | (778.1, 630.9) | (827.7, 779.5) | (827.5, 777.4) | −0.2 | −2.2 | 2.21 |
| Moonshae — Alaron | (903.7, 668.6) | (968.2, 821.6) | (969.1, 819.8) | +1.0 | −1.8 | 2.06 |

**RMS 1.93 px, max 2.48 px** (≈ 5.6 km) under the NCC fit; 1.51 px under the
least-squares fit. Orlumbor was dropped: it is small enough that the CK2 and
atlas windows resolve to different islets (residual 105 px) — the window, not
the registration, is at fault.

Independent probe, coastline crossings (first land pixel scanning east from
x = 700 on a given CK2 row, computed separately on each map):

| CK2 row | atlas coast mapped to CK2 x | CK2 coast observed |
|---|---|---|
| 350 | 1043.9 | 1044 |
| 400 | 1050.7 | 1052 |
| 560 | 960.5 | 961 |
| 900 | 1214.2 | 1215 |
| 1200 | 1092.4 | 1242 |
| 1600 | 855.6 | 857 |

Five of six agree to 1–2 px. Row 1200 is a scan-line artefact, not a
registration error: at that latitude the two maps' first landfall east of
x = 700 is a different island (the atlas hits an islet the CK2 mask does not
carry as land).

### 3.4 Result

```
faerun_km_per_px = atlas_km_per_px / transform_scale
                 = 3.2710 / 1.1275
                 = 2.9011 km/px          (verified)
```

Direction check: `ck2 = 1.1275 · atlas`, so one CK2 pixel is 1/1.1275 = 0.887
atlas pixels, i.e. 0.887 × 3.2710 = 2.90 km. The CK2 map is *larger* in pixels
than the atlas for the same ground, so its km/px must be *smaller* than the
atlas's — it is. Using the least-squares landmark scale instead gives 2.9040
km/px (0.1 % apart).

Uncertainty: ±1 px on the bar (±0.8 %) and ±0.0025 on the fitted scale
(±0.2 %) give a band of **2.871 … 2.931 km/px**, i.e.

> **recommended: `faerun_km_per_px = 2.90 ± 0.03 km/px` (1.80 ± 0.02 mi/px)**

---

## 4. Cross-check against canon distances (SOURCE 1 — weak)

`faerun_scale_pairs.csv`. 18 named cities were resolved in `definition.csv`
(all of the requested list except that Baldur's Gate is spelled
`Baldurs Gate`, province 13); their slot-0 city positions give the pixel
distances. Every canon mileage in that CSV is marked **assumed** — recalled
from the Forgotten Realms Campaign Setting and the Waterdeep boxed set, not
checked against a page — and most published FR figures are *road* distances,
which must exceed a straight line. So this source can only test the order of
magnitude.

- median implied scale over 16 pairs: **2.545 km/px** (min 0.847, max 3.417)
- straight-line-only subset (4 pairs): 2.466 km/px
- atlas-derived value: 2.901 km/px

Selected pairs at the atlas scale vs the recalled canon number:

| pair | px | miles at 2.901 km/px | canon (assumed) | kind |
|---|---|---|---|---|
| Waterdeep–Baldur's Gate | 319.0 | 575 | 640 | road |
| Baldur's Gate–Athkatla | 193.4 | 349 | 350 | road |
| Suzail–Westgate | 118.1 | 213 | 220 | straight |
| Waterdeep–Neverwinter | 198.2 | 357 | 300 | road |
| Waterdeep–Silverymoon | 301.4 | 543 | 640 | road |
| Waterdeep–Amphail | 57.0 | 103 | 30 | road |

Reconciliation. The two sources are consistent where they can be: the atlas
scale reproduces Baldur's Gate–Athkatla and Suzail–Westgate to within 3 %, and
puts Waterdeep–Baldur's Gate at 575 straight-line miles against 640 road
miles, which is the right relationship. The ±25 % scatter in the canon column
is the recalled numbers, not the map — coastline registration RMS is 1.9 px
(5.6 km), so `provinces.bmp` *is* a faithful uniform copy of the atlas
projection and no single km/px value can be wrong by more than ~1 %.

The one real finding on the CK2 side is that the mod's **province placement is
not to scale at short range**: Waterdeep–Amphail is 57 px = 103 miles on this
map against a canon ~30 miles, so the Waterdeep hinterland is stretched ~3×.
Silverymoon–Sundabar (130 vs 100 mi) and Scornubel–Berdusk (154 vs 60 mi) show
the same inflation. Coastlines are to scale; the density of inland provinces
near a hub is not. Consequence for the converter: derive distances and
travel-time-like values from pixel geometry, never from canon city mileages,
and expect inland province spacing near Waterdeep, the Silver Marches and the
Chionthar valley to over-represent real ground.

Therefore **SOURCE 2 (atlas scale bar + registration) is authoritative** and
SOURCE 1 is retained only as an order-of-magnitude check.

---

## 5. Reproducing / files

- `scripts/measure_faerun_scale.py` — prints everything above; hand-read
  constants (`ATLAS_BAR_MILES`, `ATLAS_BAR_WINDOW`, `LANDMARK_WINDOWS`) are at
  the top of the file with comments saying they were read by eye.
- `docs/evidence/faerun_scale_cities.csv` — per city: province id,
  `definition.csv` name, colour centroid (raster px), slot-0 city position in
  both `positions.txt` (bottom-origin) and raster coordinates, the centroid
  offset, and the predicted atlas pixel.
- `docs/evidence/faerun_scale_pairs.csv` — per city pair: pixel distance, km
  and miles at the atlas scale, the assumed canon mileage and its source, and
  the km/px that canon number would imply. Three `SUMMARY` rows carry
  `atlas_scale_bar_km_per_px` (verified), `faerun_km_per_px` (verified) and
  the SOURCE 1 median (assumed).
- `docs/evidence/atlas_overlay.png` — CK2 land mask with the atlas coastline
  trace warped by the fitted transform. Coastline linework only.
