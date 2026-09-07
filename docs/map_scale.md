# Map scale: CK2 Faerûn → CK3 1.19

**Question this answers.** How many CK3 pixels should one CK2 Faerûn pixel
become, so that 10 km in Faerûn covers the same number of pixels as 10 km in
vanilla CK3? Everything downstream — canvas size, barony density, army travel
time, how big Waterdeep looks next to Constantinople — falls out of this one
number.

**Answer.** `factor = 2.90 / 1.4839 = 1.9543`, canvas **8192 × 6656**,
heightmap 1× at 8192 × 6656.

| quantity | value | how | label |
|---|---|---|---|
| vanilla CK3 km per pixel | **1.4839** | latitude fit over 16 core-Europe baronies | `verified` |
| vanilla CK3 km per pixel (whole map) | 1.7426 | same fit over 25 cities worldwide | `verified` |
| CK2 Faerûn km per pixel | **2.90 ± 0.03** | atlas scale bar ÷ registration scale | `verified` |
| CK2 Faerûn km per pixel (canon distances) | 2.545 median, 0.85–3.42 spread | remembered FR distances | `assumed` |
| scale factor | **1.9543** | 2.90 ÷ 1.4839 | `verified` |
| legacy `convert.py` factor | 1.4448 (= 5918/4096) | chosen with no measurement | — |
| legacy factor's implied Faerûn scale | 2.144 km/px | 1.4448 × 1.4839 | `verified` |

The legacy factor was **26 % too small**: it would have squeezed Faerûn to
2.14 km/px, making the continent denser than vanilla Europe.

Reproduce: `uv run python scripts/measure_vanilla_scale.py`,
`uv run python scripts/measure_faerun_scale.py`,
`uv run python scripts/measure_ck2_sea_level.py --ck2-map-dir Faerun/Faerun/map`.

---

## 1. Vanilla CK3 km per pixel — 1.4839 `verified`

**Method.** Compute the pixel centroid of a barony's province colour from
`map_data/provinces.png` + `map_data/definition.csv` (route chosen because
`map_data/positions.txt` is **disabled**: `map_data/default.map:4` reads
`#positions = "positions.txt"`). Match the province to a barony via the
`province = <id>` line in `common/landed_titles/`. Pair each barony with its
city's real-world latitude/longitude, then fit degrees per pixel by least
squares and multiply the latitude figure by 111.19 km/deg.

Latitude, not longitude, because a degree of latitude is a constant 111.19 km
everywhere, while a degree of longitude shrinks with `cos(lat)` and so mixes the
projection's own distortion into the answer.

| fit | deg/px | R² | km/px | n |
|---|---|---|---|---|
| latitude, core Europe | 0.013346 | 0.9962 | **1.4839** | 16 |
| latitude, whole map | 0.015672 | 0.9709 | 1.7426 | 25 |
| longitude, core Europe | 0.019041 | 0.9828 | — | 16 |
| longitude, whole map | 0.019211 | 0.9866 | — | 25 |

Per-pair check over 18 city pairs: median 1.5372 km/px, min 1.2322
(Paris–Venezia), max 2.4682 (Aden–Mogadishu). Split by axis:
`km_per_px_x = 1.565` (8 east-west pairs, sd 0.249),
`km_per_px_y = 1.706` (10 north-south pairs, sd 0.367).

### Why the Europe number and not the global one

**The vanilla CK3 map is not a uniform projection.** `verified`: global
latitude-fit residuals span 653 px — Tunis sits 199 px north of where a linear
fit puts it, Mogadishu 453 px south. Europe is stretched, Arabia and the Horn of
Africa are compressed. No single scalar describes the sheet.

So "the" scale is a choice, and the choice is Europe, for three reasons:

1. Europe is where CK3's province density, barony count and army travel times
   were actually tuned; matching it is what makes Faerûn *play* like CK3.
2. The Europe fit is the tightest (R² 0.9962 against 0.9709), so it is the least
   arbitrary of the available numbers.
3. It is the conservative direction: 1.4839 is smaller than 1.7426, so using it
   makes the Faerûn canvas **larger**, and a map that is slightly too big can be
   cropped later, while one that is too small has thrown away resolution.

Data: `docs/evidence/vanilla_scale.csv` (the centroid cache `.npz` beside it is
gitignored; the script regenerates it).

**Gotcha for whoever re-runs this.** Vanilla barony keys are the transliterated
forms, not the localised ones: `b_constantinople`, `b_cairo`, `b_antiocheia`,
`b_kiev`.

---

## 2. CK2 Faerûn km per pixel — 2.90 `verified`

Two independent sources. The atlas is authoritative; the canon distances are a
sanity check only.

### 2a. Atlas scale bar + registration (authoritative)

The Atlas of Ice and Fire "Nations of the Forgotten Realms" 1371 DR guide map
(`refs/atlas_nations_1371_guide_map.png`, 3000 × 1878, copyrighted, local only)
carries a **miles scale bar**. Note for the next person: it is *not* in the
bottom-left corner of the image — it sits in the bottom-left **ocean**, at
y ≈ 983, x 503–625.

| step | result | label |
|---|---|---|
| scale bar length | 123 px = 250 mi (5 segments of ≈24.6 px, labelled `0 … 250 MILES`) | `verified` |
| atlas km per pixel | 250 × 1.609344 / 123 = **3.2710** | `verified` |
| atlas → CK2 transform | scale **1.1275**, rotation **+0.000°**, translation (514.0, 66.0) | `verified` |
| landmark residual | RMS **1.93 px**, max 2.48 px, 7 island centroids | `verified` |
| independent least-squares refit | scale 1.1264, rotation +0.003°, RMS 1.51 px | `verified` |
| **Faerûn km per pixel** | 3.2710 / 1.1275 = **2.90** | `verified` |

Transform: `ck2_x = 1.1275·atlas_x − 49.75`, `ck2_y = 1.1275·atlas_y + 66.00`.

A rotation of +0.000° and a 1.93 px RMS over 7 landmarks is the interesting
result in its own right: **the CK2 Faerûn mod is drawn on the atlas projection**,
not merely inspired by it. The upstream README's claim (`docs/PROJECT.md`) is
confirmed by measurement.

The division is the right way round: the atlas is the *smaller* image of the
same territory (scale 1.1275 means one atlas pixel becomes 1.1275 CK2 pixels),
so each CK2 pixel covers fewer km than an atlas pixel. Sanity check: 3.2710 /
1.1275 = 2.90 < 3.2710. ✓

Detail, landmark table and method: `docs/evidence/atlas_registration.md`.

A visual check (`docs/evidence/atlas_overlay.png`) draws the warped atlas
coastline over the CK2 land/sea mask; the Sword Coast and the Sea of Fallen
Stars sit on top of each other. That file is **gitignored**: it traces the
copyrighted atlas geometry, so it stays local like `refs/` does. Regenerate it
with `scripts/measure_faerun_scale.py`.

### 2b. Canon distances via `positions.txt` (`assumed`, cross-check only)

Median 2.545 km/px over the pairs in `docs/evidence/faerun_scale_pairs.csv`, but
the spread is 0.85–3.42 km/px, so this source cannot settle the number. It
agrees with 2.90 to within its own noise, which is all that was asked of it.

**Why the spread is so wide, and it is not a measurement error.** `verified`:
the mod's province spacing is not to scale at short range. Waterdeep–Amphail
measures 103 mi on the CK2 map against a canon ~30 mi. Coastlines and
long-range city separations follow the atlas; short hops between neighbouring
provinces are stretched, because a province needs a minimum pixel area to be
playable. This is why the atlas scale bar, which measures the *sheet*, beats
distances between individual settlements.

Two facts about `positions.txt` that the measurement had to establish first, and
that any later lane reading that file needs:

* **y is measured from the bottom of the bitmap.** `verified`: against the
  province colour centroid, the median |Δy| is 3.8 px read as bottom-origin and
  1956.2 px read as top-origin. Convert with `y_top = height − y`.
* **slot 0 of the 7 position pairs is the city.** `verified`: slot 0 is inside
  its own province 91.9 % of the time and on water 9.1 % of the time; slot 4 is
  the port (36 % on water for sea/lake provinces). Slot 3 carries
  `height = 20.000` in all 2660 blocks.

---

## 3. Canvas — 8192 × 6656 `verified` arithmetic, `assumed` requirement

```
4096 × 1.9543 = 8005  →  + 2×64 margin = 8133  →  round up to 64  →  8192
3328 × 1.9543 = 6504  →  + 2×64 margin = 6632  →  round up to 64  →  6656
```

The scaled source is centred in the slack, so every side keeps at least the
64 px sea margin: offsets are (93, 76).

**The multiple-of-64 rule is `assumed`.** No define states it. What is
`verified` is that every shipping map is a multiple of 64 on both axes:

| map | dims | ÷64 |
|---|---|---|
| CK3 vanilla | 9216 × 4608 | 144 × 72 |
| Elder Kings 2 | 8256 × 5504 | 129 × 86 |
| Godherja | 8192 × 4096 | 128 × 64 |
| **ours** | **8192 × 6656** | **128 × 104** |

A multiple of 64 is also what the packed-heightmap tiling wants: `tile_size 33`
means a stride of 32, and 64 is a multiple of both 32 and vanilla's stride of
64. Since the cost of obeying the rule is at most 63 px of extra ocean, the
converter obeys it rather than testing where it breaks.

Our canvas is 54.5 Mpx against Elder Kings 2's 45.4 Mpx — the same order, and
that mod ships and runs, so the size is not a risk.

### `WORLD_EXTENTS` — the define that must follow the canvas

**This is the one that silently ruins a custom-size map.** `verified` in three
places:

| | `WORLD_EXTENTS_X` | `_Y` | `_Z` | `WATERLEVEL` |
|---|---|---|---|---|
| vanilla `common/defines/00_defines.txt:74-77` | 9215 | 50 | 4607 | 3 |
| Elder Kings 2 `common/defines/ek_defines.txt:34-37` | 8255 | 51 | 5503 | 3.8 |
| Godherja `common/defines/00_defines.txt:79-82` | 8191 | 51 | 4095 | 3.8 |
| **ours** | **8191** | **51** | **6655** | **3.8** |

So `WORLD_EXTENTS_X = provinces.png width − 1` and
`WORLD_EXTENTS_Z = provinces.png height − 1`. `_Y` is the vertical world extent
in game units and is *not* derived from the image. Written by
`ck2ck3.map.bootstrap.write_defines` into
`common/defines/fae_defines.txt`, block `NJominiMap`.

---

## 4. Sea level, both ends

### CK3 water level — 4883 `verified`

```
water_16bit = WATERLEVEL / WORLD_EXTENTS_Y × 65535
```

* vanilla: 3 / 50 × 65535 = **3932**
* Elder Kings 2 and Godherja: 3.8 / 51 × 65535 = **4883**
* ours: 3.8 / 51 → **4883**

Both figures were confirmed by measuring the shipped heightmaps rather than
trusting the formula: Godherja's coastal-land pixels are exactly 4883 at the
25th, 50th **and** 75th percentile. Vanilla's ocean floor is 0 across 92.4 % of
its sea-province pixels, and its heightmap maximum is 49205 — which is why
`ck3_max_level = 49205` in the config rather than 65535. Detail:
`docs/formats_map.md` §3.

Adopting the total-conversion values (3.8 / 51) rather than vanilla's (3 / 50)
costs nothing and matches the two mods that are known to work at a custom size.

### CK2 sea level — 95 `verified`, and the map tells us so unambiguously

Classify every pixel as water or land from `definition.csv` + the `sea_zones`
ranges in `default.map`, then compare `topology.bmp` histograms:

| topology value | water px | land px |
|---|---|---|
| 90 | 158,614 | 6 |
| 91 | 112,590 | 23 |
| 92 | 147,450 | 339 |
| **93** | **0** | **0** |
| **94** | **0** | **0** |
| **95** | **0** | **0** |
| **96** | **0** | **0** |
| 97 | 20 | 206,723 |
| 98 | 20 | 125,957 |

There is a **four-value dead band** at 93–96 with zero pixels of either kind.
Water tops out at 92, land starts at 97. So `ck2_sea_level = 95` is correct and
any value in 93…96 produces a byte-identical result. Nothing to tune.

Full histogram: `docs/evidence/ck2_sea_level.md`.

### The transfer curve

Piecewise-linear, pinned at three points: `0 → 0`, `95 → 4883`, `255 → 49205`.
Extra control points can be added in `configs/faerun_map.toml`
(`heightmap.curve`) to compress mountains; it is empty by default because a
straight line keeps relative altitudes honest and there is no evidence yet that
Faerûn's mountains need squashing.

The LANCZOS resize runs on the **8-bit source, before the curve**, so
interpolation happens in the source's own value space and flat water stays a
single exact value instead of rippling around the water level. The ocean margin
is filled at `ck2_sea_level` for the same reason: after the curve it is exactly
4883, so the padding province reads as open sea rather than as a cliff.

---

## 5. Heightmap resolution — 1× `verified` acceptable

`heightmap.heightmap` declares `original_heightmap_size`, and it is the
`heightmap.png` size:

| map | provinces | heightmap | factor |
|---|---|---|---|
| CK3 vanilla | 9216 × 4608 | 18432 × 9216 | 2× |
| Elder Kings 2 | 8256 × 5504 | 8256 × 5504 | **1×** |
| Godherja | 8192 × 4096 | 8192 × 4096 | **1×** |
| ours | 8192 × 6656 | 8192 × 6656 | **1×** |

2× is a vanilla choice, not a requirement — two shipping total conversions prove
1× loads. 1× is chosen because vanilla's `heightmap.png` is a 122 MB file and
ours would be comparable at 2×; at 1× it stays well inside the generated repo's
size budget. `heightmap.resolution_factor = 2` in the config is a one-line
change if terrain detail ever turns out to matter.

**The heightmap is not loaded from `heightmap.png`.** `map_data/default.map:7`
reads `topology = "heightmap.heightmap"`, and that descriptor points at
`packed_heightmap.png` + `indirection_heightmap.png`. All three reference maps
ship that pair. See `docs/formats_packed_heightmap.md`.

---

## 6. What would change these numbers

- A better read of the atlas scale bar. The bar is 123 px for 250 mi; ±1 px is
  ±0.8 %, i.e. ±0.024 km/px, which is where the ±0.03 uncertainty comes from.
- Choosing the whole-map vanilla figure (1.7426) instead of the Europe one. That
  gives `factor = 1.6642` and a canvas of 6976 × 5632 — a 28 % smaller map with
  the same province count, i.e. denser provinces. This is the one open call a
  human might want to overrule; it is a single config line
  (`scale.vanilla_km_per_px`) and the canvas follows.
- Citable canon distances. If a source with real straight-line mileages between
  Faerûnian cities turns up, §2b stops being `assumed` and becomes a second
  authoritative measurement.


---

## 7. Known limitation: the padding ocean is one province over 25% of the canvas

`verified` on the generated map: the colour `(0, 0, 96)` owns **25.3%** of the
8192×6656 canvas as a *single* sea province.

That is not the 64 px margin. It is the CK2 source: 2,949,448 pixels of
`Faerun/Faerun/map/provinces.bmp` — 21% of it — are pure white and appear in no
`definition.csv` row, so CK2 itself never assigned them to a province. They are
the unclaimed water south and west of the continent. The converter cannot
invent provinces there (CLAUDE.md: no invention), so they all fall to the
padding province, along with the margin.

Consequences, none fatal but all worth knowing:

- naval movement across that whole area is **one province hop**;
- it is one sea zone, so it cannot carry distinct names, trade or travel
  modifiers;
- the province's centre of mass is meaningless, so any generated position for
  it will be odd.

Fixes, in increasing effort, for whoever picks this up:

1. **Crop the canvas** to the CK2 map's actual painted extent before scaling.
   Cheapest, loses nothing, and shrinks the images — the 21% white is dead
   weight in every output file too.
2. **Subdivide the padding** into a grid of sea provinces (a Voronoi over the
   existing coastal sea provinces would follow the coast better than a grid).
   Cheap to generate, and gives sane naval movement.
3. **Extend the CK2 map** upstream so the water is assigned there. Correct, but
   not our repository.

Option 1 is the one to do first, and it is a change to `plan_canvas` plus a
"painted extent" pass over the source bitmap, not a redesign.
