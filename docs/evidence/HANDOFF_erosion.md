# Hand-off — lane `erosion`: cliff-aware de-terrace and eroded relief

**What it is.** Passes 1 and 2 of `ck2ck3.map.heightmap_detail` replaced,
behind six new `[map]` keys, plus a new module
`ck2ck3.map.heightmap_erosion`. The reference is `docs/step_map_heightmap.md`
§2b (cliff-aware de-terrace) and §2c (structured relief, the fill target, the
amplitude authority, the headroom bound). This file is the reproduction
recipe, the evidence index and what is left.

## Reproduce

```
cd /home/cvdbdo/git/paradox/ck3/wt/erosion
PYTHONPATH=$PWD/src uv run ck2ck3 --config configs/faerun.toml \
    --out /home/cvdbdo/git/paradox/ck3/wt/_out/erosion            # ~2.5 min
uv run scripts/heightmap_erosion_crops.py                          # study crops
PYTHONPATH=$PWD/src uv run python scripts/heightmap_erosion_evidence.py
uv run scripts/verify_heightmap_detail_invariants.py \
    /home/cvdbdo/git/paradox/ck3/wt/_out/erosion
scripts/validate_output_mod.sh /home/cvdbdo/git/paradox/ck3/wt/_out/erosion \
    docs/evidence/tiger_erosion.txt
```

`PYTHONPATH=$PWD/src` is not optional (CLAUDE.md: the worktree `.venv`
editable path). Long runs go under `nohup` with the log in
`docs/evidence/heightmap_erosion/`.

## Evidence index — `docs/evidence/heightmap_erosion/`

| file | what |
|---|---|
| `crops.json` | the two study regions as canvas boxes, derived from `k_thay` and `k_spine_of_the_world` |
| `cliff_survival.csv` | §2b: multi-step cliff kept / one-step riser removed, per crop, per build |
| `spectrum.csv`, `spectrum_bands.csv` | §2c: radial amplitude on 48 all-land 256 px patches, and the 0.05–0.3 cycles/km table against vanilla |
| `structure_metrics.csv` | coherence, drainage concentration, cross-scale channel alignment; vanilla mountain crops as the reference |
| `river_alignment.csv` | do the traced rivers still sit in the drainage the erosion built |
| `tiger_erosion_summary.txt` | ck3-tiger by kind and by message: **fatal 0 / error 58**, byte-identical totals to the shipped build |
| `hillshade_*.png` | vanilla mountains / plain rescale / shipped isotropic / this build, both crops |
| `run_map_iter.log`, `run_full_after.log` | the runs the numbers come from |

## Scripts

* `scripts/heightmap_erosion_crops.py` — CK2 kingdom title → CK3 province ids
  → canvas box. The `grep` shell function chokes on the Latin-1
  `landed_titles`; the script decodes cp1252 itself.
* `scripts/heightmap_structure_metrics.py` — the three structure measures and
  the hillshade. Importable; no side effects.
* `scripts/heightmap_erosion_evidence.py` — every CSV and PNG above.
* `scripts/prototype_heightmap_erosion.py` — the crop-sized bench the
  constants were swept on (seconds per configuration, not minutes).

## The numbers, in one place (`verified`, 2026-09-10)

| | shipped (Gaussian + isotropic) | this build |
|---|---|---|
| multi-step cliff kept, Thay / Spine (pass 1 alone) | 0.692 / 0.703 | **1.133 / 1.122** |
| one-step riser removed, Thay / Spine (pass 1 alone) | 0.431 / 0.507 | **0.640 / 0.648** |
| interior band vs vanilla, 0.05 / 0.1 / 0.15 / 0.2 / 0.3 c/km | 0.54 / 0.37 / 0.26 / 0.23 / 0.21 | **1.13 / 1.16 / 1.00 / 0.91 / 2.05** |
| land on the `water_level + 1` clamp floor | 8.193 % | **0.349 %** (92,183 px) |
| land p95 / p99 (plain rescale 23,166 / —) | 25,340 / 37,827 | **23,010 / 31,883** |
| structure: coherence, Thay / Spine (vanilla 0.54–0.56) | 0.61 / 0.59 | 0.50 / 0.48 |
| structure: drainage top-1 % share (vanilla 0.199–0.203) | 0.207 / 0.204 | 0.187 / 0.191 |
| detail pass runtime, 8320 × 6784 | 10.9 s | **50 s** (whole `map` step 61 s → 102 s) |

ck3-tiger on the new output: **fatal 0, error 58, warning 50,079, untidy
10,336, tips 142** — every total identical to the shipped build's own run
(`docs/evidence/tiger_map_assets_2026-09-10_summary.txt`), `warning(rivers)`
included at 319.

`verify_heightmap_detail_invariants.py` on the new output: 3915 land
provinces, 361 water provinces, **0** land pixels at or below the water
level, **0** water pixels above it, 44,394 distinct 16-bit values.

## What the coordinator has to decide

1. **The look.** Two structure metrics turned out not to separate isotropic
   noise from landscape (`docs/step_map_heightmap.md` §7), so the hillshades
   are the evidence and this is a human's call, as `docs/map_fidelity.md`
   §4.4 predicted. Compare `hillshade_thay_ours_shipped_isotropic.png` with
   `hillshade_thay_ours_eroded.png` against
   `hillshade_ck3_vanilla_mountains.png`.
2. **Perona–Malik sharpens what it keeps.** Multi-step cliff amplitude comes
   out slightly *above* the source (see §2b). It is bounded by test at 1.25×
   and it is a real property of the filter, not a bug — but whether a 14 %
   crisper escarpment reads as "cliff" or as "drawn-on contour" is a look
   call at close zoom.
3. **In-game verification** was out of this lane's scope by instruction. The
   output mod is left in place at `/home/cvdbdo/git/paradox/ck3/wt/_out/erosion`.
