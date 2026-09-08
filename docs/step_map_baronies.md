# Step `map`, barony half: CK2 counties → physical CK3 baronies

**Question this answers.** A CK2 county is one province with up to 7 barony
*slots*; a CK3 county is several provinces, one per barony. Which baronies get
a province, where do their borders go, and how does a human move one that is
wrong?

**Answer.** The baronies are the holdings CK2 actually *built* in
`history/provinces`. Each gets one seed pixel — from a human override, a
gazetteer, the CK2 `positions.txt` city/port slots, or farthest-point sampling
— and the county is then partitioned by multi-source geodesic Voronoi. A
county too small for all its holdings demotes the last ones declared in
`landed_titles`; they stay in `docs/evidence/barony_set.csv` for the
`titles-history` lane to emit as commented-out baronies.

Numbers below are the current (`[map] ck2_position_seeds = true`, lane
`map-paint-seeds`) figures; the row for each superseded by that lane keeps its
pre-lane value in parentheses for comparison.

| quantity | value (Faerûn, 1357.1.1) | label |
|---|---|---|
| CK2 counties in `landed_titles` | 2132 | `verified` |
| counties with province history | 2125 | `verified` |
| **defined** baronies | 15,356 (15,195 inside a county) | `verified` |
| **built** holdings at 1357.1.1 ∪ 1501.1.1 | **3857** | `verified` |
| of those, built only by a later bookmark | 79 | `verified` |
| baronies placed as CK3 provinces | **3705** (was 3694) | `verified` |
| baronies demoted to comments | **152** (was 163), in fewer of 2125 counties | `verified` |
| CK3 provinces total | 4276 = 3705 baronies + county-less land + water (padding ocean included) | `verified` |
| seeds from `positions.txt` **city** slot (capital) | 2112 | `verified` |
| seeds from `positions.txt` **port** slot (§3, new) | 758 | `verified` |
| seeds farthest-point sampled | 835 (was 1584) | `verified` |
| seeds from overrides / gazetteer | 0 (the files ship empty) | `verified` |
| median barony area | 2554 px ≈ 5,600 km² | `verified` |
| smallest placed barony | 128 px (a county whose only holding it is) | `verified` |
| run time, whole `map` step | ~60 s (46 s without the barony split, +5 s for terrain paint — `docs/step_map_paint.md`) | `verified` |
| two runs → identical `provinces.png` sha256 | yes | `verified` |

Reproduce: `uv run ck2ck3 --config configs/faerun.toml --steps map`.
Evidence: `docs/evidence/barony_set.csv`, `docs/evidence/province_id_map.csv`,
`docs/evidence/nonbarony_holdings.csv`, `docs/evidence/baronies/index.md`.

---

## 1. The barony set — built holdings, never the defined list

`ck2ck3.map.holdings`. Facts the reader had to establish, all `verified` on
Faerûn:

* the province id is in the **filename** (`history/provinces/1 - Waterdeep.txt`
  is province 1); nothing inside repeats it. The county is `title = c_x`.
* a holding appears as `b_<key> = <type>`, either at the top of the file
  ("from the start of history", recorded as date `initial`) or inside a dated
  `1010.1.1 = { ... }` block;
* the same barony is re-assigned over time — `b_castle_waterdeep` goes castle →
  tribal → castle → tribal → castle — so a date resolves to the **last
  assignment at or before it**, not the first mention;
* **the right-hand side is not always a holding type.** `b_sea_ward =
  ct_planar_portal` builds a *building*. Reading those as a state change
  silently deleted 79 baronies before the bug was found, so `at()` skips any
  value that is not one of the nine CK2 holding types.

| CK2 holding | CK3 | note |
|---|---|---|
| `castle` | `castle_holding` | |
| `city` | `city_holding` | |
| `temple` | `church_holding` | |
| `tribal` | `tribal_holding` | |
| `nomad` | `tribal_holding` | CK3 dropped nomads; tribal is the nearest tier |
| `fort`, `hospital`, `trade_post`, `family_palace` | **not a barony** | listed in `docs/evidence/nonbarony_holdings.csv`; CK3 models these as buildings |

Faerûn uses only the first four (castle 1905, tribal 1465, city 1280, temple
697 assignments), so `nonbarony_holdings.csv` is header-only for this mod. The
other five are handled anyway because the converter is not Faerûn-specific.

**The set is the union of two dates** (`docs/design_map.md` §B.1): holdings
built at `[map.baronies] bookmark` (which follows `[mod] bookmark_date`) **∪**
anything built by `latest_bookmark`. CK3 cannot create a province mid-game, so
a holding that only appears at a later bookmark still needs its province from
turn one; it just starts with whatever holding it eventually gets. 79 of
Faerûn's 3857 are in the set for that reason alone, flagged
`later_bookmark = yes` in `barony_set.csv`.

## 2. Capacity — which holdings get a province at all

`capacity = max(1, county_pixels // min_barony_pixels)`, applied **before** any
pixel is spent. Holdings beyond it are demoted, lowest priority first, where
priority is the CK2 `landed_titles` declaration order — CK2's own ordering,
which puts the county seat first.

**A county never loses its last barony**, whatever its size: a county with no
province is a hole in the map. 22 placed baronies are therefore under
`min_barony_pixels` (the smallest is 128 px); each is the only holding of a
tiny county.

`min_barony_pixels = 400` is the vanilla figure — a 20×20 blob at 9216×4608 —
and it needs **no rescaling here**, because this canvas is at vanilla's own
km per pixel by construction (`docs/map_scale.md`). Left unset the code derives
326 from the width ratio; `configs/faerun.toml` pins 400 and says why.

## 3. Seeds — four sources, first match wins

`ck2ck3.map.baronies`. Priority order, and what each is for:

1. **`overrides/barony_seeds.csv`** — `barony_id,x,y,note` in canvas pixels.
   The human's answer. Nothing overrides it.
2. **`overrides/gazetteer.csv`** — `place_name,x,y,space,source`, matched on the
   barony's **CK2 localised name** (`ck2ck3.csvloc` over
   `Faerun/Faerun/localisation/*.csv`, English column). Matching folds accents,
   case and punctuation, so `Wyrm's Crossing` matches `wyrmscrossing`. This is
   the file a lore search or an LLM pass fills in. `space = ck2` coordinates are
   put through the map transform, so those rows survive a change of canvas size;
   `space = ck3` rows do not.
3. **the CK2 `positions.txt` city/port slots** (`[map] ck2_position_seeds`,
   default on; `false` reproduces the seed priority before lane
   `map-paint-seeds` — capital only, no slot-4 port seeding):
   * the county **capital** at the **city** slot, slot **0** of the seven pairs
     (`verified`, `docs/map_scale.md` §2b: slot 0 is inside its own province
     91.9 % of the time). The capital is the first barony declared in the
     county (CK2 has no `capital = b_x` inside a county). 2112 of 2125
     counties get a seed this way.
   * the county's **non-capital `city_holding`**, when one exists, at the
     **port** slot, slot **4** (`verified`, `docs/map_fidelity.md` §1.6: the
     CK2 binary itself logs "Invalid port location for province %d" against
     it — 36.1 % of slot 4s sit on water, i.e. the author placed them on the
     harbour). 758 baronies are seeded this way. If the snapped port
     coordinate collides with a seed already taken (a degenerate
     `positions.txt` block where every slot equals slot 0, which is most of
     Faerûn's) the barony falls through to sampling instead of duplicating a
     seed pixel.
   `positions.txt` y is measured from the **bottom** of the CK2 bitmap, so
   `y_top = source_height - y`, for both slots. `[map.baronies] city_slot` /
   `port_slot` (default 0 / 4) pick the indices.
4. **farthest-point sampling**, biased by holding type: a `city_holding` prefers
   coast or river pixels, a `castle_holding` prefers hills/mountains, church and
   tribal prefer neither. A biased pixel's distance counts `1 + bias_gain`
   times, so terrain wins only against a marginally more distant plain pixel.
   The first seed of a county with no pinned seed starts at the pixel nearest
   the county's centre of mass, not in a corner.

Any seed that comes from outside the pipeline (1, 2, 3) is **snapped** to the
nearest pixel of its own county, up to `snap_radius_px` (48). Beyond that the
row is *ignored* and the next source takes over — so a typo degrades to a
sampled seed instead of moving a barony into the wrong county.

## 4. Growth — geodesic, not Euclidean

`ck2ck3.map.growth.geodesic_voronoi`: a 4-connected multi-source BFS over the
whole canvas at once, where a label may only cross into a pixel of **its own
county**. Every pixel enters the frontier exactly once, so the cost is
O(pixels), not O(area × radius): 10 s for Faerûn's 26 M land pixels.

* **Geodesic** because a Euclidean partition lets a barony claim pixels across a
  bay or over a mountain range the county wraps around. Straight-line distance
  is not what an army walks.
* **4-connected** because 8-connected growth leaks across the one-pixel diagonal
  isthmuses the rescale creates on coastlines.
* **Ties go to the lower label, always** — determinism is a requirement
  (`docs/design_map.md` §B.7), and `scipy.ndimage.watershed_ift` does not let us
  choose the tie-break.

### Lloyd relaxation

A farthest-point seed sits in a *corner* of its county by construction, which
makes the partition lopsided and demotes holdings that would have fitted.
`relax_passes` (4) repeats: grow → move each **relaxable** seed to the pixel
of its own region nearest that region's centroid → regrow. Measured on
Faerûn (capital-only seeding, pre lane `map-paint-seeds`):

| relax_passes | demoted |
|---|---|
| 0 | 313 |
| 2 | 176 |
| **4** | **163** |
| 6 | 164 (converged) |

Seeds from an override, the gazetteer or the capital `positions.txt` slot are
**pinned** and never move — the whole point of an override is that it stays
where it was put. The port `positions.txt` slot (§3) is **relaxable**, not
pinned: it is a snapped, clamped coordinate from the source data, not a human
decision, and pinning it exactly like an override measurably demoted *more*
baronies than farthest-point sampling did for the same holdings (`verified`
on Faerûn: 205 demoted with it pinned, 152 with it relaxable, against the 163
baseline above). Lloyd converges to *a* centroidal partition, not an
equal-area one, so a small county can still come out lopsided; that is what
the demotion pass is for.

### Stragglers, and detached county pieces

After relaxation, up to `max_regrow_passes` (3) rounds of "demote the smallest
barony still under `min_barony_pixels` in each county, then regrow". Removing
the worst first usually lifts the others over the line.

79,338 canvas pixels (0.3 % of the land) belong to a county but are unreachable
from any of its seeds — a detached island, or a strip the rescaled coastline cut
off. Leaving them as padding ocean would silently shrink the county, so they are
attached to the nearest seed of their own county. The barony ends up
non-contiguous; the review sheet shows it. **Open item**: seeding the detached
components instead would be better, and needs a rule for which barony gets one.

## 5. Ids and colours

`ck2ck3.map.idmap.build_with_baronies`. Dense `1..N`, in this order:

1. every land barony, in CK2 `landed_titles` **hierarchy order** (empire,
   kingdom, duchy, county, barony), so neighbouring baronies get neighbouring
   ids — 99 % of counties get a fully consecutive id block;
2. every CK2 province that is *not* split — water, wasteland, and land the mod
   gave no county — in ascending CK2 id, which is what keeps the `sea_zones`
   ranges in `default.map` contiguous;
3. the padding ocean, last.

Colours: `blake2b(barony_id)` truncated to 24 bits, then a deterministic upward
probe past anything taken. A hash rather than a counter so adding a barony
upstream does not recolour every barony after it — the `provinces.png` diff
stays local. Python's own `hash()` is salted per process and would make the
output non-reproducible. A barony never takes a colour already used by a CK2
province that survives unchanged, nor black, white or the padding colour.

### The contract with lane `titles-history`

`map_data/definition.csv` column 5 of a **barony row is the CK3 barony title
id**, `b_<ck2 barony name>`, verbatim from CK2 `landed_titles`. One row per
barony province. The titles lane reads province ids straight out of that file.
Sea, lake, river, impassable and county-less land rows keep the uppercase slug
of their CK2 province name, as before. Every value in column 5 gets a
localisation entry, because ck3-tiger reads the column as a localisation key.

`docs/evidence/barony_set.csv` is the second half of the contract: `status` is
`placed` (has a province), `override` (has a province, seeded by a human) or
`demoted` (**no province** — emit it as a commented-out barony).
`docs/evidence/province_id_map.csv` carries `barony`, `county` and `holding`
columns beside every CK3 id.

## 6. What the rest of the pipeline had to learn

* **`common/province_terrain`** — the majority terrain vote moved from CK2 ids
  at CK2 resolution to **CK3 ids at target resolution**, so each barony gets its
  own terrain rather than its county's. It runs as one `np.bincount` over
  `province_id * ncat + terrain_code` (`terrain.majority_terrain_codes`); the
  old sort-and-`np.unique` version would have been a 55 M-element argsort.
  A barony voted `impassable_mountains` is kept passable: it carries a holding.
* **`adjacencies.csv`** — a strait must land on the barony that *faces the
  water*, not on whichever one is the county capital. CK2 stores no coordinates
  (all four columns are `-1` in Faerûn), so the endpoint is derived: the
  crossing goes from → through → to, and each end picks the barony of its county
  whose centroid is nearest the `through` water province's centroid.
* **`climate.txt`, `island_region.txt`, `geographical_regions/`** — a CK2
  province in a region list now expands to **all** of its baronies
  (`IdMap.remap_ids`), or the region loses land.
* **throwaway `common/landed_titles`** — still a flat one-kingdom tree, but the
  county → barony grouping is real, because several provinces now share a
  county and a barony province with no county over it is a hole. The
  `holding =` line in `history/provinces` is real too: it is the CK3 equivalent
  of the CK2 holding that was built.

## 7. Config keys

All under `[map.baronies]` in `configs/faerun.toml` (and `[baronies]` in
`configs/faerun_map.toml` for the standalone entry point), except
`ck2_position_seeds` itself, which is the documented top-level `[map]` flag
(`[map.baronies] ck2_position_seeds` still works too — a value there wins,
since `steps/map.py` merges it under the `[map]` default).

| key | default | meaning |
|---|---|---|
| `bookmark` | `[mod] bookmark_date` | date the barony set is taken at |
| `latest_bookmark` | `1501.1.1` | holdings built by then are baronies too |
| `min_barony_pixels` | `400` (pinned; `0` = derive from width) | smallest barony |
| `capital_weight`, `other_weight` | `1.0`, `1.0` | seed weights (design §B.3) |
| `bias_gain` | `0.5` | how much terrain bias favours a seed pixel |
| `snap_radius_px` | `48` | how far an imported seed may be snapped |
| `relax_passes` | `4` | Lloyd passes on sampled seeds |
| `max_regrow_passes` | `3` | "demote the worst straggler and regrow" rounds |
| `ck2_position_seeds` | `true` | use the `positions.txt` city/port slots as seeds at all |
| `city_slot` | `0` | `positions.txt` slot holding the city coordinate |
| `port_slot` | `4` | `positions.txt` slot holding the port coordinate |
| `seeds_csv` | `overrides/barony_seeds.csv` | human seed overrides |
| `gazetteer_csv` | `overrides/gazetteer.csv` | place-name coordinates |
| `review_sheets` | `false` | write the duchy PNGs during the run |

## 8. Override workflow (for a human, 10 steps)

1. `uv run ck2ck3 --config configs/faerun.toml --steps map` — regenerate the
   map. Read the counts in `docs/evidence/last_run.md`.
2. `nohup uv run scripts/barony_review_sheets.py > docs/evidence/barony_sheets.log 2>&1 &`
   — one PNG per duchy that owns land in `docs/evidence/baronies/`, plus
   `index.md`. 622 sheets, 7.2 MB, ~90 s. (622 and not 979: the rest are
   titular or offmap duchies with no county history.) A duchy smaller than
   512 px is integer-upscaled before the labels are drawn, so they stay
   readable; a bigger one is capped at 1024 px on the long edge.
3. Open `docs/evidence/baronies/index.md`. Its table lists every county that
   lost a holding. Start there.
4. Open the duchy PNG you care about. County borders are white, each barony is
   filled in its `definition.csv` colour, each seed is a black dot labelled with
   the barony id.
5. A seed in the wrong place (a city inland, a castle in a marsh, two seeds on
   top of each other) is the thing to fix.
6. Read the pixel coordinate off `map_data/provinces.png` in the generated mod —
   the sheet is cropped and downscaled, so it is for *finding* the problem, not
   for measuring it.
7. Add a row to `overrides/barony_seeds.csv`: `b_<barony>,x,y,why`. Canvas
   pixels, top-left origin.
8. For a place you know the location of but not the barony id, add a row to
   `overrides/gazetteer.csv` instead: `Name,x,y,ck2,source`. It matches on the
   CK2 localised name and `ck2` coordinates survive a canvas resize.
9. Re-run step 1. Only the counties you touched change: the split is
   deterministic and the colour hash is per barony.
10. A demoted holding you want back needs *space*, not a seed: lower
    `min_barony_pixels`, or accept that the county cannot carry it and let the
    titles lane emit it as a commented barony.

## 9. Known limitations

* **The demoted holdings (152 with `ck2_position_seeds` on, was 163 before
  this lane) are a real loss of content**, not a rendering choice: those CK2
  holdings have no CK3 province. Waterdeep still collapses from 6 built
  holdings to 4, though which two lose out shifted with the port-slot seeding
  (`b_castle_waterdeep`, `b_castle_ward`, `b_north_ward`, `b_the_plinth`
  placed; `b_sea_ward` and `b_trades_ward` demoted, `verified` in
  `docs/evidence/barony_set.csv`) — the county is 2053 canvas pixels, so it
  cannot carry six. That is the collapse `docs/design_map.md` §B.4 predicted
  for Baldur's Gate, arriving on its own. The names survive as comments;
  making them special buildings is submod work. The worst-hit counties are
  `c_menzoberranzan` (4 demoted), `c_undermountain` and `c_sargauth` (3 each)
  — the Underdark, where CK2 packs many holdings into one small cavern
  province; `docs/evidence/barony_set.csv` has the current per-county list.
* **Non-contiguous baronies** where a county has a detached piece with no seed
  (§4).
* **`positions.txt` seeds are per county, not per barony.** CK2 has no barony
  coordinates to import (CLAUDE.md invariant). Slots 0 and 4 (§3) are the only
  two the CK2 binary itself names, so they seed the capital and the
  non-capital port/city holding directly; every other barony in the county is
  still derived (sampled, then relaxed toward its region's centroid).
* **The gazetteer ships empty.** Every named place in Faerûn whose location is
  known from lore is a row nobody has written yet; that is the highest-value
  human input this step can take.
