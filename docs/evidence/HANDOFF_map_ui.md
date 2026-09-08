# Hand-off — lane `map-ui`

Branch `lane/map-ui` (worktree `../wt/map-ui`), 2026-09-08. **Nothing is
committed**: the lane brief forbade `git add`/`commit`, so the working tree
holds every change below, grouped here as the commits the coordinator should
make.

`uv run pytest -q` → **953 passed**. `ci/checks.sh` → **checks green**.
Regenerated with `uv run ck2ck3 --config configs/faerun.toml --steps map --out
<scratch>` (58.8 s, 52 files, the real mod untouched).

---

## Proposed commits

### 1. `docs: map UI research — locators, camera, table, flat map`
```
docs/evidence/map_ui_research.md      (new, the whole investigation)
docs/evidence/locator_frame.md        (new, generated evidence table)
docs/evidence/flatmap_preview.png     (new, what the paper map looks like)
docs/evidence/locator_check_mod.log   (new, the validation run)
docs/evidence/locator_frame.log       (new, nohup log)
docs/evidence/map_ui_run.log          (new, nohup log of the scratch regeneration)
docs/formats_map.md                   (new §11 + 8 rows in the fact table)
scripts/check_locator_frame.py        (new)
scripts/preview_dds.py                (new)
CLAUDE.md                             (4 invariants, 2 commands, 1 doc pointer)
```

### 2. `map: write our own gfx/map/map_object_data locators`
```
src/ck2ck3/map/locators.py            (new)
src/ck2ck3/map/build.py               (write them; land vs passable id sets)
src/ck2ck3/steps/map.py               (OUTPUTS gains gfx/map/...)
tests/test_map_locators.py            (new, 15 tests)
```

### 3. `map: camera bounds and the 3D table follow the canvas`
```
src/ck2ck3/map/bootstrap.py           (render_camera_defines)
src/ck2ck3/map/table.py               (new)
src/ck2ck3/map/build.py               (write both)
tests/test_map_table_camera.py        (new, 9 tests)
```

### 4. `map: paint the flat map instead of inheriting vanilla's Earth`
```
src/ck2ck3/map/dxt1.py                (new, BC1 encoder + DDS header)
src/ck2ck3/map/flatmap.py             (new)
src/ck2ck3/map/build.py               (write it)
tests/test_map_flatmap.py             (new, 11 tests)
```

### 5. `map: empty vanilla's foliage generators on a custom canvas`
```
src/ck2ck3/map/locators.py            (render_foliage_stubs)
src/ck2ck3/map/config.py              (strip_vanilla_foliage, default true)
src/ck2ck3/steps/map.py               (read the key)
src/ck2ck3/map/build.py               (write the stubs)
configs/faerun.toml                   (the key, documented)
tests/test_map_locators.py            (2 more tests)
```

(1–5 can also ship as one commit; they touch `build.py` in sequence.)

---

## What the `map` step now writes that it did not before

| path | count | why |
|---|---|---|
| `gfx/map/map_object_data/*_locators.txt` + `activities.txt` | 7 | holdings/CoAs/units/sieges at our provinces, not vanilla's |
| `gfx/map/map_object_data/map_table_*.txt` | 4 | table re-centred and scaled ×1.4722 |
| `gfx/map/map_object_data/generated/*.txt` | 18 | vanilla foliage emptied |
| `gfx/map/terrain/flat_maps/flatmap.dds` | 1 | 8320×6784 DXT1, 28.2 MB |
| `common/defines/graphic/fae_graphics.txt` | 1 | `NCamera` panning + start look-at |

No new `replace_path`: every file is a same-name override, which is what both
reference TCs rely on.  Total added to the generated mod: **32 MB**, of which
28 MB is the flat map.

---

## Findings (detail and file:line in `docs/evidence/map_ui_research.md`)

1. **`positions.txt` is dead.** The string occurs **0** times in the CK3 1.19
   binary. Icon placement is `gfx/map/map_object_data/*.txt`.
2. **Locator frame, measured:** `position = { x y z }` in `provinces.png`
   pixels with **z bottom-up**. Median error over 11 297–12 062 vanilla
   instances: 3–7 px bottom-up, ~1360 px top-down.
3. **The bug behind complaint (a):** `gameobjectlocators.cpp:126` only fills
   *gaps*. 3179 of our 3694 holdings kept a vanilla id's European coordinate
   and drew a median **3040 px** from their own land. The engine's own
   placement for the 515 ids vanilla lacks is the province colour **centroid**
   (1.6 px median) — so centroid is not a guess, it is the engine's answer.
4. **Id sets are not uniform:** `buildings`/`special_building`/`siege`/
   `activities` want land only (3694); `combat`/`unit_stack_*` want everything
   passable plus a constant `id=0` sentinel (4056). Both derived from what the
   engine demanded, both reproduced exactly.
5. **The camera bound is `NCamera.PANNING_WIDTH`/`PANNING_HEIGHT`** — no
   `MAX_ZOOM`, no `MAP_BOUNDS`. Vanilla's 4696 left 2088 px (30.8 %) of our map
   unreachable. Elder Kings 2 sets both to its canvas; we now do the same.
   **This is the defines-only fix, option (i).**
6. **Option (ii) costed:** padding to 2 : 1 means 8320×6784 → **13568×6784**,
   +5248 px of empty ocean, 92.0 Mpx against 56.4 — a 63 % bigger
   `provinces.png`, heightmap, rivers and packed pair. Rejected. Option (iii)
   throws away `docs/map_scale.md`.
7. **The table is data, not a mesh:** four `object={}` per style with a
   `transform` in the locator frame. Neither TC rescales it. We re-centre and
   scale by `max(w/9216, h/4608)` = **1.4722**, i.e. vanilla's `5 5 5` becomes
   `7.361 7.361 7.361`.
8. **The flat map** is `gfx/map/terrain/flat_maps/flatmap.dds`, exactly canvas
   sized, DXT1, mips optional. Ours is parchment shaded by altitude over a
   blue-grey sea; preview `docs/evidence/flatmap_preview.png`.
9. **Vanilla's 51.7 MB of foliage** loads over any custom map. Both TCs stub
   unwanted generators with an empty `instances={ }`; we stub all 18.

## Validation

`uv run scripts/check_locator_frame.py --mod <out> --against <CK3 generated/>`:

* every one of the 7 files, **0 instances further than 1 px** from their own
  province centroid;
* counts match the engine's demand exactly (3694 / 4056);
* against the entries the engine placed itself: **1.58–4.48 px median**
  (worst case 5.06);
* against the entries the engine inherited from vanilla: **3036–3050 px**,
  which is the bug.

---

## Open questions the coordinator must decide

1. **Nothing here has been in the game.** The lane could not launch it. One
   `-test` run plus one eyeball at zoom 21+ settles items 2–4.
2. **Table scale 1.4722 is arithmetic**, not a measured mesh extent (`.mesh`
   is binary and unparsed). If the sheet still overhangs, the number is one
   constant in `ck2ck3.map.table.scale_factor`.
3. **`strip_vanilla_foliage = true` removes all 3-D foliage** until Faerûn
   grows its own. Correct, but visible. `configs/faerun.toml` reverts it.
4. **`FLAT_MAP_ZOOM_STEP` left at vanilla's 21.** EK2 uses 16, which shows the
   paper map sooner and is cheaper on a big sheet — a candidate for the "zoom
   lags" half of the report, one define away.
5. **`PANNING_WIDTH` set to the full 8320.** Godherja deliberately narrows
   theirs. If panning across our 25 % padding ocean (`docs/map_scale.md` §7)
   is annoying, narrow it.
6. **`gfx/map/surround_map/*.dds` untouched** — still vanilla's Earth
   coastline mask beyond the map edge. Cosmetic; GH ships vanilla's unchanged
   on a 2 : 1 map, EK2 re-authored theirs at canvas ÷ 2.
7. **`docs/playtest_2026-09-08.md` is not in the repo.** The playtest facts
   this lane worked from came from the brief; if that file exists elsewhere it
   should be committed so the evidence chain is closed.
8. **The generated mod has not been regenerated.** Output went to a scratch
   `--out`; `docs/integration_run.md` step for the real mod is the
   coordinator's.
