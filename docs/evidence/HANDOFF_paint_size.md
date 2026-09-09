# Hand-off: lane `paint-size`

Answers `docs/evidence/HANDOFF_map_paint_seeds.md` open question 1: is there a
`detail_index.tga`/`detail_intensity.tga` format under GitHub's 100 MB/file
cap, or is none possible? Branch `lane/paint-size`, not committed (the
coordinator commits from this hand-off).

## Answer

**Yes, but only at half resolution.** `[map] terrain_paint_scale = 0.5` is
required regardless of format — RLE alone does not clear the cap for
`detail_intensity` at full resolution (172.55 MB, still over). Recommended:
`[map] terrain_paint_format = "tga_rle"`, `[map] terrain_paint_scale = 0.5`
(2.33 MB + 54.55 MB = 56.88 MB total, smallest of all six combinations
measured). Defaults are unchanged (`"tga"`, `1.0`) pending the coordinator's
in-game check — see "What the coordinator must check" below.

## Files changed

New:
- `scripts/paint_variants.py` / `.sh` — re-encodes an already-built
  `detail_index`/`detail_intensity` pair into every format × scale
  combination without a second converter run; writes each as a probe mod
  (`descriptor.mod` + `gfx/map/terrain/*`) plus
  `docs/evidence/paint_variants.csv`.
- `docs/evidence/paint_variants.csv` — the measured table below, from a real
  full-canvas run (not extrapolated from a tile).

Modified:
- `src/ck2ck3/map/terrain_paint.py` — `save_tga(..., rle=True)`; `load_tga`;
  a hand-rolled uncompressed-BGRA8 DDS codec (`save_dds`/`load_dds`,
  `_dds_header`); `save_paint`/`load_paint`/`paint_ext` dispatch on
  `terrain_paint_format`; `downsample_index` (nearest-neighbour, ordinals
  must never interpolate) and `downsample_intensity` (box-filter channel 0,
  re-derive channel 1 as its complement so the sum-to-255 contract survives a
  downsample).
- `src/ck2ck3/map/config.py`, `src/ck2ck3/steps/map.py` —
  `MapConfig.terrain_paint_format`/`terrain_paint_scale` (both the dataclass
  and both `load()` call sites — the CLI's and the standalone entry
  point's), default `"tga"`/`1.0` (unchanged).
- `src/ck2ck3/map/build.py` — applies the downsample (if
  `terrain_paint_scale != 1.0`) before writing, picks the output filename
  extension from `terrain_paint_format` (`ck2ck3.map.terrain_paint.paint_ext`),
  writes via `save_paint`; run report gains `format`/`scale`/`index_size`.
- `tests/test_map_terrain_paint.py` — 19 new tests: RLE TGA round-trip and
  image-type byte, DDS header/round-trip/rejects-garbage, `save_paint`/
  `load_paint`/`paint_ext` for all three formats, `downsample_index`
  (nearest-only, never invents an in-between ordinal),
  `downsample_intensity` (box average, sum-to-255 preserved, rejects
  `scale > 1.0`), and one end-to-end test through `build_layers` →
  downsample → every format.
- `configs/faerun.toml` — documents/sets `terrain_paint_format = "tga"`,
  `terrain_paint_scale = 1.0` (both left at the vanilla-matching default).
- `docs/step_map_paint.md` — new §8 (Size): the RLE/DDS research findings
  with file:line/byte evidence, the measured size table, the recommendation,
  what the coordinator must check in game, the new config keys.

## Commands and results

**Research (goal 1), verified against real files, not guessed:**

```
xxd -l 20 game/gfx/map/terrain/detail_index.tga
# 00000000: 0000 0200 ...  -> image type 2 (uncompressed), matches docs already on file

xxd -l 20 workshop/.../2887120253 (Elder Kings 2) detail_index.tga / detail_intensity.tga
xxd -l 20 workshop/.../2326030123 (Godherja)       detail_index.tga / detail_intensity.tga
# all four: image type 10 (RLE), byte offset 2 = 0x0a
# EK2 8256x5504 == its own provinces.png; Godherja 8192x4096 == its own provinces.png
# (full resolution, not half, in both)

strings ck3.exe | grep -n "detail_index\|detail_intensity"
# exactly 2 hits total, both from mapeditor_detail_data.cpp (map editor's
# own mask-bake step), both followed immediately by a bare ".tga" string —
# no second, generic-extension-search occurrence found anywhere else
```

**Implementation + tests (goals 2/4):**

```
uv run pytest -q
```
→ **1077 passed**, 0 failed (33 in `test_map_terrain_paint.py`, 19 new).
`bash ci/checks.sh` → **checks green**.

```
uv run ck2ck3 --config configs/faerun.toml \
  --out /home/cvdbdo/git/paradox/ck3/wt/_out/paint-size --steps map
```
→ `map 8320x6784 at scale 1.9543 (2.9 -> 1.4839 km/px): 4276 provinces, 3705
baronies in 2125 counties, 152 demoted, 3 lost` in **56.5 s** (defaults —
`tga`, `1.0` — output identical to lane `map-paint-seeds`'s own reference
run, no regression).

**End-to-end config wiring**, a throwaway `configs/_paint_size_smoke.toml`
copy with `terrain_paint_format = "tga_rle"` / `terrain_paint_scale = 0.5`
(deleted after, not committed): same `--steps map` run wrote
`detail_index.tga` as `Targa image data - RGBA - RLE 4160 x 3392 x 32`
(2,333,572 bytes) and `detail_intensity.tga` 54,550,906 bytes — both exactly
matching `paint_variants.py`'s independent re-encode of the same source data
(below), confirming the config keys reach `build.py` correctly.

```
uv run scripts/paint_variants.py /home/cvdbdo/git/paradox/ck3/wt/_out/paint-size
```
→ 6 variants written under `/home/cvdbdo/git/paradox/ck3/wt/_out/paint_variants/`
in 3 s total (re-encode only, no second converter run), table below.

## Variant table (goal 3/4, `docs/evidence/paint_variants.csv`)

| variant | format | scale | size (px) | `detail_index` | `detail_intensity` | total | under 100 MB/file? | expected visual difference |
|---|---|---|---|---|---|---|---|---|
| `tga_full` | `tga` | 1.0 | 8320×6784 | 225.77 MB | 225.77 MB | 451.54 MB | no, no | baseline (current shipped behaviour) |
| `tga_rle_full` | `tga_rle` | 1.0 | 8320×6784 | 5.57 MB | 172.55 MB | 178.12 MB | yes, **no** | none — lossless re-encode of the same pixels |
| `dds_full` | `dds` | 1.0 | 8320×6784 | 225.77 MB | 225.77 MB | 451.54 MB | no, no | none — lossless re-encode; likely does not load at all (§8.2) |
| `tga_0p5` | `tga` | 0.5 | 4160×3392 | 56.44 MB | 56.44 MB | 112.89 MB | **yes, yes** | index unaffected (nearest-neighbour, no new materials); blend edges slightly softer (half the noise-field resolution) |
| **`tga_rle_0p5`** | **`tga_rle`** | **0.5** | 4160×3392 | **2.33 MB** | **54.55 MB** | **56.88 MB** | **yes, yes** | same as `tga_0p5` (RLE is lossless); **recommended** |
| `dds_0p5` | `dds` | 0.5 | 4160×3392 | 56.44 MB | 56.44 MB | 112.89 MB | **yes, yes** | same as `tga_0p5` pixels; likely does not load at all (§8.2) |

## Recommendation and why

`terrain_paint_format = "tga_rle"`, `terrain_paint_scale = 0.5`:

1. Scale is not optional — every full-resolution candidate fails the
   100 MB/file cap; the noise-dithered blend field (the edge treatment lane
   `map-paint-seeds` added) barely compresses under RLE (225.77 → 172.55 MB,
   24%), so no format change alone clears it.
2. RLE is the best-evidenced format at 0.5 scale: two real, loadable,
   published total conversions (Elder Kings 2, Godherja) ship exactly this
   container, full resolution. Fallback if it somehow does not load: plain
   `tga` at 0.5, still comfortably under the cap and bit-for-bit vanilla's
   own image type.
3. `dds` is not recommended: zero compression benefit even if it worked, and
   the weakest load-viability evidence (only 2 occurrences of
   `detail_index`/`detail_intensity` anywhere in `ck3.exe`, both hardcoded
   with a literal `.tga` extension, from the map editor's own bake step).

## What the coordinator must check in game

Nothing here was checked against a running CK3 — everything above is static
analysis (file headers, `strings`, our own round-trip tests). Only a game
load answers:

1. Does `tga_rle` actually render (expected yes, per §8.1's evidence)?
2. Does `terrain_paint_scale = 0.5` — smaller than `provinces.png`, which no
   installed shipped mod tests — still align/render correctly? The shader
   samples in UV space so this should just resample, but it is genuinely
   untested.
3. Does `dds` load at all, at either scale (expected no)?

Probe mods for all six combinations are ready under
`/home/cvdbdo/git/paradox/ck3/wt/_out/paint_variants/<variant>/` (rebuild
any time with `scripts/paint_variants.py <out dir>`). Load one at a time
after the main mod:

```
claudespace/scripts/ck3_soak.sh <mod> --extra /home/cvdbdo/git/paradox/ck3/wt/_out/paint_variants/tga_rle_0p5
```

then a weston screenshot to confirm the terrain paint looks like Faerûn, not
Europe, and does not visibly misalign at the coastline.

## Verify: pytest / full run / sizes / ck3-tiger

- `uv run pytest -q` → **1077 passed**, `bash ci/checks.sh` → **checks
  green**.
- Full `--steps map` run to `/home/cvdbdo/git/paradox/ck3/wt/_out/paint-size`
  → unchanged from lane `map-paint-seeds`'s reference numbers (defaults not
  touched), 56.5 s.
- Every variant's size: `docs/evidence/paint_variants.csv` and the table
  above.
- ck3-tiger: **not run, and not needed** — `detail_index`/`detail_intensity`
  are opaque binary files to it in every format (already established in
  `docs/evidence/tiger_map_paint_seeds.txt` for the `tga` case: no mention of
  these files at all); nothing here changes that.

## Suggested commit message

```
map: RLE/DDS terrain-paint formats + half-resolution downsample, under the 100 MB cap

The detail_index.tga/detail_intensity.tga pair lane map-paint-seeds shipped
is ~226 MB per layer, so GitHub gitignores it and a clone ships no terrain
paint. Behind [map] terrain_paint_format ("tga"/"tga_rle"/"dds", default
unchanged) and [map] terrain_paint_scale (1.0/0.5, default unchanged):

- tga_rle: verified accepted by CK3 1.19 (not by a game test, but by reading
  two installed, loadable, published total conversions -- Elder Kings 2 and
  Godherja both ship exactly this container, full resolution).
- dds: implemented per spec (hand-rolled uncompressed BGRA8, documented
  header) but unverified and likely non-viable -- ck3.exe's only two
  mentions of these filenames are hardcoded with a literal .tga extension,
  from the map editor's own mask-bake code.
- terrain_paint_scale = 0.5 (nearest-neighbour for detail_index, box-filter
  for detail_intensity) is *required*: RLE alone still leaves
  detail_intensity at ~173 MB at full resolution, because the noise-dithered
  blend field barely compresses. At 0.5 every format clears the cap.

Recommended combination (not yet the default, pending an in-game check):
tga_rle + 0.5 -> 2.33 MB + 54.55 MB, smallest of six measured combinations
(docs/evidence/paint_variants.csv, a real full-canvas run).

scripts/paint_variants.py builds all six combinations as probe mods
(descriptor.mod + gfx/map/terrain) for
claudespace/scripts/ck3_soak.sh <mod> --extra <variant dir>.

1077 tests pass (19 new: RLE/DDS codec round-trips, downsample invariants).

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
```
