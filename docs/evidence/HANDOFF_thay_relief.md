# Hand-off — lane `thay-relief` (2026-09-23)

Playtest verdict after build 17: **"Thay was still broken."** No more detail
than that. Two prior lanes (`relief-sharp`, `relief-pits`) each fixed a
measured cause and each time the user still saw the problem, so the brief's
premise was explicit: the metrics had already been wrong twice, so this lane
starts from a render, not a table.

Reference: `docs/step_map_heightmap.md` §2h (the render, the defect list,
which metric sees each). Decisions: `docs/DECISIONS.md`, 2026-09-23.
Evidence: `docs/evidence/thay_relief/`.

## 1. What the render showed

`scripts/thay_render.py` hillshades and oblique-3D-renders the Thay window
(canvas x 4752-5311, y 1583-2222, +100 px margin) at the engine's own
vertical scale (`world_height = level / 65535 * WORLD_EXTENTS_Y`, unit pixel
spacing) and its own low sun (`sun_direction` in
`gfx/map/environment/environment.txt`, elevation 33.1 deg), camera pitch
from `ZOOM_STEPS_TILT[0]` = 50 deg
(`common/defines/graphic/00_graphics.txt`), for CK2's own `topology.bmp`,
the plain rescale, a reconstruction of build 15, and the actual shipped
build-17 `heightmap.png`.

CK2 source and the plain rescale both show an ordinary rounded massif.
Build 15 and build 17 both show, in the same place, a **closed escarpment
loop** ~500x600 canvas px (740x890 km) around a domed interior, serrated
along its southern arc, with a lake sitting just outside it rendered as a
dead-flat plane meeting jagged terrain at a vertical wall.

## 2. Three defect classes

**(a) The closed-loop rampart — verified, partially fixed.** The CK2 source
itself already carries a 7,480-9,521-level closed depression there
(`closed_depression_depth` on the *plain rescale*, new metric
`closed_depression_excess` isolates what is added on top: p99 378-467 / max
1,837-2,072 levels at 9-45 px before this lane, a minority of the total).
Cause: `_relative_terrain_gain` gives one amplitude scalar per terrain class
(mountains x2.317) applied uniformly regardless of local source roughness,
so a gentle CK2 rim gets the same full ridged texture as a real cliff,
reinforced coherently all the way around a closed contour — a defect no
single-source-pixel bound (§2f) can see, since every pixel individually
stays inside its own tolerance. Fix: `heightmap_detail_source_adaptive_gain`
(new default true) scales amplitude down, never up, by local source
roughness. Measured: excess -18 % to -22 % at every window, whole-canvas
mean amplitude -31 %, a synthetic 9-step cliff keeps > 85 % of its
amplitude, Spine of the World window unchanged. **Not closed**: the
after-fix render still shows the same ring, thinner — most of the depth is
the CK2 author's own relief sharpened by pass 1 (Perona-Malik, §2b), which
this fix does not touch.

**(b) Serrated / stair-step escarpment faces — observed, not fixed.** 38-109
canvas px from any water province (ruled out: not the province-edges
coast/lake mask). Plausible mechanism, `assumed`: `deterrace_cliff_aware`'s
Perona-Malik flux is 4-connected (`heightmap_erosion.py:199`,
`verified`), which under-smooths a curved/diagonal boundary asymmetrically.
Not isolated by a dedicated ablation in the time available; not fixed, since
a flux change touches §2b's own extensively-measured cliff-survival ratios.

**(c) Lakes as vertical-walled holes — verified intrinsic.** `build17`'s
Thay crop reads level [0, 39865]: `sea_floor = 0` beside 13,000-40,000-level
land. CK2 draws the same lake bed as one continuous, gently-sloping surface
with no water pin at all (direct render comparison, `verified`) — this is
CK3's single global `WATERLEVEL`, not a CK2 authoring choice. Two least-bad
treatments **proposed, not implemented**: a wider shore ramp for
high-altitude water provinces specifically, or an `overrides/` entry
converting the highest such provinces to marsh/land — a per-province
gameplay call, not the converter's to make unattended.

## 3. What changed

* `src/ck2ck3/map/config.py` — three new `HeightmapDetailConfig` fields
  (`source_adaptive_gain`, `source_adaptive_window_px`,
  `source_adaptive_floor`), wired into both TOML readers.
* `src/ck2ck3/map/heightmap_detail.py` — `_source_roughness_factor` (new),
  applied to the per-terrain amplitude before `delta = amp * noise`.
* `configs/faerun.toml` — the three new flat keys, default on.
* `scripts/thay_render.py` — new: the render this lane is built on.
* `scripts/relief_pits_common.py` — `closed_depression_excess`/`_stats`
  (new), `EXCESS_WINDOWS_PX = (3, 9, 27)`.
* `scripts/verify_heightmap_detail_invariants.py` — reports the new metric
  on a finished mod (informational, not a hard gate: the fix is partial by
  design, see §2 above).
* `tests/test_map_heightmap_detail.py` — 3 new tests on a combined
  flat-top/lake-hole/multi-step-cliff fixture
  (`_thay_like_fixture`/`_run_thay_like`), plus the 3 new keys added to the
  existing key-reaches-config and defaults tests.

## 4. Verification

* `uv run pytest` — **1327 passed** (53 in `test_map_heightmap_detail.py`).
* `ci/checks.sh` — green.
* `scripts/verify_heightmap_detail_invariants.py` on a real
  `configs/faerun.toml` `--steps map` run into `wt/_out/thay-relief`: land
  0 px at/below water, water 0 px above, source bound (2sigma/3px) **0 land
  px below, 0 above** — the fix does not weaken the existing §2f bound.
  Whole-canvas closed-depression excess: p95 0-57, p99 17-270, max
  1,115-2,158 at 3/9/27 px — Thay is the extreme case, not the norm.
* Runtime: `map` step **190.9 s** (heightmap detail 67 s, ~+12 s over the
  §2f-documented baseline for the roughness field's two morphological
  filters and one Gaussian blur; the rest of the difference against the
  142.8 s §2f baseline is the `province-edges` lane's own cost, which
  postdates that figure).
* ck3-tiger: run on a full conversion into `wt/_out/thay-relief`
  (`docs/evidence/thay_relief_full_run.log`, `docs/evidence/thay_relief_tiger.txt`) —
  this lane touches only heightmap raster synthesis and three new `[map]`
  TOML keys, no generated script/history/loc content, so no tiger-visible
  file changed; see the log for the actual run.
* No in-game run, by instruction.

## 5. What the coordinator has to decide

1. **The rampart is thinner, not gone.** Accept it as the CK2 author's own
   geography, sharpened but honestly rendered for the first time — or open
   a lane to soften pass 1's Perona-Malik response specifically on a
   *closed, low-total-drop* contour (needs its own metric: §2b's flux has
   no notion of "this edge closes a loop").
2. **The serration mechanism is a hypothesis** (4-connected diffusion flux),
   not isolated by ablation. A follow-up lane would re-derive pass 1's flux
   over 8 neighbours or a true gradient-magnitude stopping function and
   re-validate against §2b's cliff-survival ratios.
3. **Thay's lakes as shafts is an engine limit, not a bug** — two proposed
   treatments in §2c above, neither implemented; pick one, both, or accept
   the shaft.
4. **The closed-depression excess check is informational, not a hard gate**
   in `verify_heightmap_detail_invariants.py` (the fix is partial by
   design). A future "is Thay actually fixed" claim should re-run
   `scripts/thay_render.py` and look, not just read a percentile.

## 6. What a reader should run

```
uv run python scripts/thay_render.py [--out-dir DIR] [--skip-3d]
uv run scripts/verify_heightmap_detail_invariants.py <out mod dir>
```

Figures: `docs/evidence/thay_relief/{hillshade,oblique}_{ck2_source,plain_rescale,build15,build17,after_fix}.png`.
