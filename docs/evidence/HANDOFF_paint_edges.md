# Hand-off: lane `paint-edges` (soft, relief-aware terrain-class edges)

Read `docs/step_map_paint.md` §10 first — this file is what the *next* lane
and the coordinator need, not the design.

## 1. The user's question, answered

> "Was your hypothesis wrong on just assigning by pixel, or is the map not
> high-def enough?"

Neither hypothesis was wrong and the map was not short of pixels. The paint
was short of *edges*: see §10.5 of `docs/step_map_paint.md` for the split.
Assigning by pixel is right — CK2 has to decide what is where — but the
converter then resampled that assignment NEAREST and blended it with a
class-agnostic noise field, so nothing in the pipeline ever drew a boundary.

## 2. What the coordinator must check in game

- Terrain paint at close zoom, the three places the playtest named: the
  Wealdath (a forest edge), Anauroch (a desert edge), the Sword Coast (a
  coast). The before/after crops are in `docs/evidence/paint_edges/`.
- **Trees against paint.** The scatter's eligibility mask now uses the same
  smooth `trees.bmp` expansion as the paint, so a tree should never stand a
  whole block outside the painted forest any more.
- **The paint pair is now full resolution** (`terrain_paint_scale = 1.0`).
  No installed shipped mod ships a pair *smaller* than its province map, so
  this actually returns us to the shape Elder Kings 2 and Godherja use; if
  anything is misaligned in game it will be obvious at once.

## 3. Decisions the coordinator owns

1. **`terrain_paint_scale = 1.0` is now the shipped default** (was 0.5). It
   is not a size trade any more: the smooth blend compresses so much better
   than the noise field that the full-resolution pair is *smaller* than the
   half-resolution one was. Numbers in `docs/step_map_paint.md` §10.6.
2. **The tree scatter and the `forest` class promotion still use two
   different index sets of `trees.bmp`, and this lane did not unify them.**
   CK2's own `tree = { 3 4 7 10 }` in `default.map` promotes 7,217 tree
   pixels to `forest`; the scatter has always taken *any* non-zero index,
   19,683 pixels — 2.7x more ground. So trees legitimately stand on painted
   plains. Changing it would move ~60 % of the forest area and is a look
   call, not a bug fix. `[map] trees_mask_smooth` smooths both masks the
   same way but leaves the two index sets alone.
3. **The `debug` material.** Vanilla's `materials.settings` declares six
   effect layers first (`drought`, `drought_cracks`, `flood`,
   `summer_grass`, `winter_effect`, `debug`), so ordinals 0-5 are not
   terrain art. This lane stopped writing ordinal 0 into dead channels for
   that reason. Nothing else in the repo knows this; it belongs in
   `docs/formats_map.md` if another lane touches materials.

## 4. What is still open

- **Vanilla's interior richness is not fully matched.** Vanilla paints 3.62
  non-zero channels per pixel more than 50 px from any class boundary
  (`docs/evidence/paint_edges/vanilla_blend_by_distance.csv`); a class here
  paints three. A fourth per-class material would close it, but the fourth
  channel is what carries the neighbouring class at a boundary, so it needs
  a rule for which of the two to drop.
- **The tertiary picks are `assumed` art calls constrained by data.** The
  rule (`scripts/propose_paint_tertiary.py`) is defensible and recorded in
  every row's `note`, but `forest`'s third material is `forest_jungle_01` at
  0.2 % of vanilla's own forest interior — the only same-family candidate
  vanilla's ranking offers. A human look at the Cormanthor is the check.
- **The relief warp is bounded, not tuned.** `terrain_paint_relief_shift_px
  = 1.5` canvas px was chosen to sit inside the one-source-pixel invariant
  with headroom, not because 1.5 looked better than 1.0 or 2.0 in game.
- **`terrain_paint_edge_sigma_px = 2.0`** likewise: vanilla's own
  primary-weight ramp reaches 90 % of its interior value about one
  province-map pixel from the seam, so a wider ramp would *not* be more
  vanilla-like; 2.0 canvas px is a compromise between that measurement and
  killing the visible staircase.

## 5. Reproduce

```
uv run scripts/measure_vanilla_paint_blend.py          # vanilla's own blend
uv run scripts/propose_paint_tertiary.py [--write]     # the tertiary column
scripts/make_paint_edges_before_config.sh              # the build-13 config
nohup uv run ck2ck3 -v --config configs/faerun_paint_edges_before.toml \
  --steps map --no-evidence --out <out>/paint-edges-before &
nohup uv run ck2ck3 -v --config configs/faerun.toml \
  --steps map --out <out>/paint-edges &
uv run --with matplotlib python scripts/paint_edges_report.py \
  --before <out>/paint-edges-before --after <out>/paint-edges
```

## 6. Verification actually run in this lane

- `uv run pytest` green (28 new tests in `tests/test_map_paint_edges.py`).
- `ci/checks.sh` green.
- **ck3-tiger over a full conversion into the lane output: `fatal 0`,
  `error 58`** — the same 58 as the shipped baseline, and tiger names
  `detail_index` / `detail_intensity` / `materials.settings` nowhere at all
  (`docs/evidence/paint_edges/tiger_paint_edges.txt`), as §6/§7 of
  `docs/step_map_paint.md` already established: they are opaque binaries to
  it. The paint cannot be validated statically; the in-game look is the
  coordinator's check.
- Not run: any game launch. `assumed` that a full-resolution pair renders,
  because vanilla and both shipped total conversions use exactly that shape.
