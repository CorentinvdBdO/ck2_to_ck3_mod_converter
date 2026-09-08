# Hand-off: lane `map-heightmap-detail`

Wires the `docs/map_fidelity.md` §4.2 prototype into the converter as a
deterministic, seeded detail-synthesis pass on the rescaled heightmap.
Branch `lane/map-heightmap-detail`, all commits by the coordinator from this
worktree's diff.

## Files changed

* `src/ck2ck3/map/heightmap_detail.py` (new) — the four-pass synthesis:
  de-terrace, spectral fill (per-terrain amplitude), river-valley carving,
  coast smoothing. Pure array transform, no I/O.
* `src/ck2ck3/map/config.py` — `HeightmapDetailConfig`, `DEFAULT_HF_TARGETS`
  (baked-in vanilla per-terrain HF RMS table), `heightmap_detail_config()`
  (flat `[map]` keys) and `_heightmap_detail_from_table()` (standalone
  entry point's nested `[heightmap_detail]` table). `MapConfig` gained a
  `heightmap_detail` field.
* `src/ck2ck3/map/build.py` — wires the pass in between `heightmap.build()`
  and the packed-heightmap writer; river tracing moved earlier (computed once,
  reused for both the detail pass and `map_data/rivers.png`, no duplicate
  trace); new helpers `_terrain_code_grid`, `_nn_upsample`.
* `src/ck2ck3/steps/map.py` — one line, wires `heightmap_detail_config(raw)`
  into `_map_config`.
* `configs/faerun.toml` — `[map] heightmap_detail = true` and the seed/
  amplitude keys (flat, defaults = prototype's own numbers).
* `configs/faerun_map.toml` — matching `[heightmap_detail]` table for the
  standalone `ck2ck3.map.build` entry point (off by default there).
* `tests/test_map_heightmap_detail.py` (new) — 16 tests: sea pin, coastline
  (both directions), determinism, distinct-value increase, terrain-aware
  amplitude (mountains > 3x plains on an otherwise-identical synthetic
  island), river valleys never raise a pixel, input validation.
* `scripts/verify_heightmap_detail_invariants.py` (new) — independent
  province-raster-based invariant check on a real generated mod.
* `scripts/check_heightmap_detail_amplitude.py` (new) — global per-terrain
  achieved-vs-target HF RMS, on a real generated mod.
* `scripts/heightmap_detail_evidence.py` (new) — before/after hillshade PNGs
  + spectrum plot from two real converter runs (not the standalone
  prototype).
* `docs/step_map_heightmap.md` (new) — the heightmap step doc (rescale +
  detail pass), invariants, config table, cost.
* `docs/design_map.md` §A step 3, `docs/map_fidelity.md` top status line —
  updated to point at the above.
* `CLAUDE.md` — one-line docs pointer.

Not touched: any barony/Voronoi seeding code, `provinces.py`, `terrain.py`'s
vote logic, or the province raster — lane `map-paint-seeds` owns those and is
running concurrently. `terrain_code` for the per-terrain gain reuses the
*existing* per-province majority-vote result (`terrain.majority_terrain_codes`'s
`by_province`) rather than reclassifying pixels.

## Verification commands and results

```
uv run pytest -q tests/test_map_heightmap_detail.py tests/test_map_heightmap.py
# 40 passed

uv run pytest -q          # whole repo, incl. slow (Faerun/ present)
# 1020 passed

bash ci/checks.sh
# checks green

uv run ck2ck3 --config configs/faerun.toml \
    --out /home/cvdbdo/git/paradox/ck3/wt/_out/map-heightmap-detail
# 15 steps, 1378 files; map step 60.57s (includes the detail pass)

uv run python scripts/verify_heightmap_detail_invariants.py \
    /home/cvdbdo/git/paradox/ck3/wt/_out/map-heightmap-detail
# land provinces checked  3904   water provinces checked 361
# distinct height values  44390
# land px at/below water  0      water px above water    0
# invariants hold

scripts/validate_output_mod.sh /home/cvdbdo/git/paradox/ck3/wt/_out/map-heightmap-detail \
    docs/evidence/tiger_heightmap_detail_summary.txt
# summary: 56 error/fatal, 49922 warning, 10489 tips/untidy (tiger exit 0)
# 0 fatal(); the 56 errors are localization-key-collision / wrong-gender /
# history, pre-existing and owned by other lanes (loc, characters,
# titles-history) -- none mention map_data, heightmap or packed_heightmap.
```

## Numbers, before → after (whole Faerûn map, `[map] heightmap_detail`)

| | before (`= false`) | after (`= true`) |
|---|---|---|
| distinct 16-bit height values | **212** | **44,390** (vanilla 31,516) |
| `map_data/heightmap.png` | 11.6 MB | 40.5 MB |
| `map_data/packed_heightmap.png` | 4.28 MB | 7.44 MB |
| `map_data/indirection_heightmap.png` | 62.3 KB | 62.3 KB (unchanged) |
| `map` step wall time | 58.8 s | 60.6 s (detail pass itself: **10.9 s**, well under the ~2 min budget) |
| coastline invariant | n/a | **holds**, `land px at/below water = 0`, `water px above water = 0` |

Per-terrain HF RMS achieved vs. `DEFAULT_HF_TARGETS`
(`scripts/check_heightmap_detail_amplitude.py`, whole map, land only):

| terrain | target | achieved (all land) | achieved (interior, >20 px / ~30 km from any coast) |
|---|---|---|---|
| desert | 91.2 | 107.3 | 100.8 |
| farmlands | 96.7 | 139.0 | 128.9 |
| forest | 110.7 | 134.2 | 129.9 |
| hills | 213.3 | 258.9 | 235.4 |
| jungle | 120.7 | 130.4 | 100.0 |
| mountains | 311.4 | 360.3 | 344.5 |
| plains | 86.3 | 115.8 | 93.3 |
| steppe | 97.2 | 141.0 | 108.5 |
| taiga | 70.1 | 124.0 | 93.9 |
| wetlands | 70.4 | 105.9 | 85.5 |

**Reading this honestly**: mountains ≫ plains ≫ taiga holds — the
terrain-aware ordering the prototype and the pytest suite both assert is
real. The *whole-map* average overshoots target by roughly 1.1–1.5x; the
*interior* (>20 px from any coastline) average is much closer to 1.0
(0.83–1.34). The gap is the coastline itself: land near a shoreline in the
final PNG carries a real value step down toward `water_level` (land is
clamped strictly above the pin, water can sit far below it), which a Gaussian
high-pass filter reads as extra high-frequency energy — vanilla's own
`hf_by_terrain.csv` measurement deliberately excludes any 64×64 window that
touches water for exactly this reason (`scripts/map_fidelity_heightmap.py`
line ~230), so comparing a naive whole-class average against that number is
not quite apples-to-apples. This is not a broken invariant (coastlines and
the sea pin are separately verified exact) — it is an honest limitation of
how closely the *average* amplitude matches vanilla's, left as-is rather than
hand-tuned against a single measurement method, per the instruction to use
the prototype's own values as defaults.

Sword Coast crop (`docs/evidence/heightmap_detail/`, from real converter
before/after runs, not the standalone prototype):

| | before | after |
|---|---|---|
| distinct values in the crop | 125 | 22,544 |
| land p50 / p95 | 8484 / 15686 | 8382 / 18680 |
| high-pass RMS (crop) | 200.9 | 269.1 |
| mean gradient (levels/km) | 144.3 | 204.4 |

Images: `before.png` / `after.png` (full crop hillshade), `zoom_before.png` /
`zoom_after.png` (tighter zoom), `spectrum.png` (radial power spectrum,
before/after vs. `ck3_vanilla` from `docs/evidence/map_fidelity/spectrum.csv`).

## What stays unverified in game

* Whether the added detail actually *reads* as terrain rather than gravel in
  the real 3D renderer with lighting, fog and the (still-missing) terrain
  paint — `docs/map_fidelity.md` §4.2 already flags that the noise is
  isotropic, not the ridged/dendritic structure vanilla has; this pass does
  not change that.
* Whether the larger `packed_heightmap.png` (+74%) has any load-time or
  memory effect in the actual engine.
* Whether ck3-tiger's `rivers` warnings (248 "tributary not joining",
  identical before/after — pre-existing, not from this pass) look different
  once actually rendered with the new elevation under them.
* The coordinator runs the game; this lane only ran headless ck3-tiger and
  the unit/invariant scripts above.

## Open questions

1. The whole-map average amplitude overshoot (§ above) — worth a follow-up
   that measures "achieved" the same windowed, water-excluded way vanilla's
   own table was measured, so the two numbers are directly comparable? Or is
   the interior-only number (already close to 1.0) the more honest metric to
   report going forward?
2. `packed_heightmap.png` growth (+74%, +3.16 MB) — acceptable, or does the
   repo-size decision in `docs/map_fidelity.md` §4.1 (blend-weight
   quantisation for the terrain-paint pass) need to account for this too?
3. Isotropic-noise-vs-structured-terrain gap (§4.2's own "what this does not
   fix") is unchanged by this lane — still an `L`-effort, human-look-call item
   per the effort table.

## Suggested commit message

```
map: vanilla-matched heightmap detail synthesis

Wire docs/map_fidelity.md §4.2's prototype into the converter as a
deterministic, seeded pass between the plain 8-bit->16-bit rescale and
the packed-heightmap writer: de-terrace, spectral fill to vanilla's
f^-2.0 land spectrum per CK3 terrain class, river-valley carving, coast
smoothing. Faerun: 212 -> 44,390 distinct height values, sea-level pin
and every coastline verified unchanged, pass runtime 10.9s.

[map] heightmap_detail = true (on in configs/faerun.toml), seed and
amplitude parameters default to the prototype's own numbers.
```
