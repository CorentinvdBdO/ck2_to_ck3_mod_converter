#!/usr/bin/env python3
"""Every number and every picture lane `erosion` claims, from the rasters.

Three measurements, one command:

1. **Cliff survival** (docs/step_map_heightmap.md §2b).  Over the Thay and
   Spine of the World study crops, the fraction of *multi-step* adjacent
   height difference (>= 2 x 277 levels in the plain rescale -- a real cliff)
   that is still there afterwards, and the fraction of *single-step* riser
   (the quantisation artefact) that is gone.  Both maps are measured against
   the same plain-rescale baseline, so the two de-terrace modes are directly
   comparable.
2. **Radial spectrum** on 256x256 all-land patches, exactly
   `scripts/report_map_paint_plots.py`'s method and patch geometry, so the
   0.05-0.3 cycles/km band can be read against `spectrum.csv`'s vanilla
   column.  Never a coastal crop: a 4884-level coastline step flatters every
   frequency (docs/report_map_paint.md §6).
3. **Structure metrics** (`scripts/heightmap_structure_metrics.py`) on the
   study crops and on vanilla mountain crops halved to our pixel size.

Plus side-by-side hillshades of every crop.

Usage:
  uv run --with matplotlib python scripts/heightmap_erosion_evidence.py \
      [--before-mod DIR] [--after-mod DIR] [--skip-spectrum]
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import heightmap_structure_metrics as M  # noqa: E402

Image.MAX_IMAGE_PIXELS = None

OUT = ROOT / "docs/evidence/heightmap_erosion"
CK2_MAP = ROOT / "Faerun/Faerun/map"
GAME = ROOT / "../claudespace/game_files"

# canvas geometry and levels -- configs/faerun.toml [map] / [map.heightmap]
CANVAS_W, CANVAS_H = 8320, 6784
SCALED_W, SCALED_H = 8005, 6504
OFFSET_X, OFFSET_Y = 157, 140
WATER_LEVEL, MAX_LEVEL, CK2_SEA_LEVEL = 4883, 49205, 95
KM_PX_OURS, KM_PX_VANILLA = 1.4839, 0.74195
VANILLA_WATER = 3932
QUANT = (MAX_LEVEL - WATER_LEVEL) / 160.0
PATCH, PATCHES = 256, 48

#: vanilla mountain crops (heightmap px, 2x sheet), the three highest-relief
#: all-land 1024 px windows found by a stride-256 sweep of
#: game/map_data/heightmap.png -- halved here to our 1.4839 km/px
VANILLA_CROPS = ((4352, 9984), (3584, 9216), (3840, 9728))


def plain_rescale_canvas() -> np.ndarray:
    """`ours before any detail pass`, exactly as ck2ck3.map.heightmap builds it."""
    from ck2ck3.map import heightmap as hm
    from ck2ck3.map.config import HeightmapConfig
    lut = hm.build_curve(HeightmapConfig(
        ck2_sea_level=CK2_SEA_LEVEL, ck3_water_level=WATER_LEVEL,
        ck3_max_level=MAX_LEVEL))
    with Image.open(CK2_MAP / "topology.bmp") as im:
        scaled = np.asarray(im.convert("L").resize((SCALED_W, SCALED_H), Image.LANCZOS))
    out8 = np.full((CANVAS_H, CANVAS_W), CK2_SEA_LEVEL, dtype=np.uint8)
    out8[OFFSET_Y:OFFSET_Y + SCALED_H, OFFSET_X:OFFSET_X + SCALED_W] = scaled
    return lut[out8]


def load(path: Path) -> np.ndarray:
    with Image.open(path) as im:
        return np.asarray(im.convert("I;16")).astype(np.uint16)


def halve(a: np.ndarray) -> np.ndarray:
    return np.asarray(Image.fromarray(a).resize(
        (a.shape[1] // 2, a.shape[0] // 2), Image.LANCZOS))


# ------------------------------------------------------------------ 1. cliffs
def step_fraction(before: np.ndarray, after: np.ndarray, mask: np.ndarray,
                  lo: float, hi: float) -> float:
    """Fraction of the adjacent-pair step amplitude in ``[lo, hi)`` still present.

    ``lo``/``hi`` in quantisation steps, classified on ``before``; both axes,
    only pairs whose two pixels are both in ``mask``.
    """
    tot_b = tot_a = 0.0
    for axis in (0, 1):
        db = np.diff(before.astype(np.float64), axis=axis)
        da = np.diff(after.astype(np.float64), axis=axis)
        m = (mask[1:, :] & mask[:-1, :]) if axis == 0 else (mask[:, 1:] & mask[:, :-1])
        sel = m & (np.abs(db) >= lo * QUANT) & (np.abs(db) < hi * QUANT)
        tot_b += float(np.abs(db[sel]).sum())
        tot_a += float(np.abs(da[sel]).sum())
    return tot_a / tot_b if tot_b > 0 else float("nan")


def deterrace_only(before, crops, margin: int = 32) -> dict:
    """Pass 1 in isolation, both modes, on each crop.

    The finished-map columns below are contaminated by the fill: synthesised
    detail lands on the same adjacent pixel pairs the cliff metric reads, so
    a bigger fill lowers the apparent survival whatever pass 1 did.  These
    columns are the de-terrace measured on its own, which is what §2b claims.
    A margin is taken around the crop so the filter's own boundary handling
    is not what is being measured.
    """
    from scipy.ndimage import gaussian_filter
    from ck2ck3.map import heightmap_erosion as he
    out = {}
    for region, c in crops.items():
        y, x, s = c["crop_y"], c["crop_x"], c["crop_side"]
        wide = before[y - margin:y + s + margin,
                      x - margin:x + s + margin].astype(np.float32)
        sl = (slice(margin, margin + s), slice(margin, margin + s))
        out[region] = {
            "deterrace_gaussian_1.6": gaussian_filter(wide, 1.6, mode="nearest")[sl],
            "deterrace_cliff_aware_2.2": he.deterrace_cliff_aware(
                wide, 2.2, he.QUANTISATION_STEP_LEVELS * 1.5)[sl],
        }
    return out


def measure_cliffs(before, maps, crops) -> list[dict]:
    rows = []
    isolated = deterrace_only(before, crops)
    for region, c in crops.items():
        y, x, s = c["crop_y"], c["crop_x"], c["crop_side"]
        b = before[y:y + s, x:x + s]
        land = b > WATER_LEVEL
        for name, arr in list(isolated[region].items()) + [
                (k, v[y:y + s, x:x + s]) for k, v in maps.items()]:
            a = arr
            rows.append({
                "region": region,
                "map": name,
                "cliff_survival_ge2_steps": round(step_fraction(b, a, land, 2.0, 99.0), 4),
                "cliff_survival_ge3_steps": round(step_fraction(b, a, land, 3.0, 99.0), 4),
                "riser_removed_1_step": round(
                    1.0 - step_fraction(b, a, land, 0.5, 1.5), 4),
                "land_px": int(land.sum()),
            })
    return rows


# ---------------------------------------------------------------- 2. spectrum
def radial_spectrum(win: np.ndarray, km_per_px: float):
    """Identical to scripts/report_map_paint_plots.py:radial_spectrum."""
    n = win.shape[0]
    w = np.hanning(n)
    win = (win.astype(np.float64) - win.mean()) * w[:, None] * w[None, :]
    F = np.fft.fftshift(np.fft.fft2(win))
    P = (np.abs(F) ** 2) / (n * n)
    c = n // 2
    yy, xx = np.mgrid[0:n, 0:n]
    r = np.hypot(yy - c, xx - c).astype(int)
    prof = (np.bincount(r.ravel(), weights=P.ravel())[:c]
            / np.maximum(np.bincount(r.ravel())[:c], 1))
    return (np.arange(c) / n / km_per_px)[1:], np.sqrt(prof[1:])


def find_land_patches(arrays, size, want, seed=7):
    """`want` origins of windows that are 100 % land in every (array, level)."""
    rng = np.random.default_rng(seed)
    H, W = arrays[0][0].shape
    out, tries = [], 0
    while len(out) < want and tries < 40000:
        tries += 1
        y = int(rng.integers(0, H - size))
        x = int(rng.integers(0, W - size))
        if all((a[y:y + size, x:x + size] > w).all() for a, w in arrays):
            out.append((y, x))
    return out


def mean_spectrum(arr, patches, km_per_px):
    acc, k = None, None
    for (y, x) in patches:
        k, a = radial_spectrum(arr[y:y + PATCH, x:x + PATCH], km_per_px)
        acc = a if acc is None else acc + a
    return k, acc / len(patches)


def measure_spectrum(before, maps) -> list[dict]:
    rows = []

    def emit(name, k, a):
        rows.extend({"map": name, "cycles_per_km": float(kk),
                     "amplitude_levels": float(aa)} for kk, aa in zip(k, a))

    stack = [(before, WATER_LEVEL)] + [(m, WATER_LEVEL) for m in maps.values()]
    patches = find_land_patches(stack, PATCH, PATCHES)
    print(f"  spectrum: {len(patches)} all-land patches shared by every map",
          flush=True)
    emit("ours_plain_rescale", *mean_spectrum(before, patches, KM_PX_OURS))
    for name, arr in maps.items():
        emit(name, *mean_spectrum(arr, patches, KM_PX_OURS))
    van = load(GAME / "map_data/heightmap.png")
    p = find_land_patches([(van, VANILLA_WATER)], PATCH, PATCHES)
    emit("ck3_vanilla", *mean_spectrum(van, p, KM_PX_VANILLA))
    del van
    return rows


def band_table(spectrum_rows: list[dict]) -> list[dict]:
    """Amplitude at the frequencies docs/report_map_paint.md §6 quotes."""
    by_map: dict[str, list[tuple[float, float]]] = {}
    for r in spectrum_rows:
        by_map.setdefault(r["map"], []).append(
            (float(r["cycles_per_km"]), float(r["amplitude_levels"])))
    wanted = (0.05, 0.1, 0.15, 0.2, 0.3)
    out = []
    van = {}
    for name, pts in by_map.items():
        pts.sort()
        ks = np.array([p[0] for p in pts])
        vs = np.array([p[1] for p in pts])
        for f in wanted:
            if f > ks.max():
                continue
            val = float(np.interp(f, ks, vs))
            if name == "ck3_vanilla":
                van[f] = val
            out.append({"map": name, "cycles_per_km": f,
                        "amplitude_levels": round(val, 1)})
    for row in out:
        v = van.get(row["cycles_per_km"])
        row["vs_vanilla"] = round(row["amplitude_levels"] / v, 3) if v else ""
    return out


# --------------------------------------------------------------- 3. structure
def measure_structure(before, maps, crops) -> list[dict]:
    rows = []
    van = load(GAME / "map_data/heightmap.png")
    for i, (y, x) in enumerate(VANILLA_CROPS):
        c = halve(van[y:y + 1024, x:x + 1024])
        m = np.ones(c.shape, dtype=bool)
        rows.append({"region": f"ck3_vanilla_mountains_{i}", "map": "ck3_vanilla",
                     "coherence": round(M.coherence(c, m), 4),
                     "drain_top1_share": round(M.drainage_stats(c, m)["drain_top1_share"], 4),
                     "channel_alignment": round(M.channel_alignment(c, m), 4)})
    del van
    for region, c in crops.items():
        y, x, s = c["crop_y"], c["crop_x"], c["crop_side"]
        land = before[y:y + s, x:x + s] > WATER_LEVEL
        for name, arr in [("ours_plain_rescale", before)] + list(maps.items()):
            w = arr[y:y + s, x:x + s].astype(np.float32)
            rows.append({"region": region, "map": name,
                         "coherence": round(M.coherence(w, land), 4),
                         "drain_top1_share": round(
                             M.drainage_stats(w, land)["drain_top1_share"], 4),
                         "channel_alignment": round(M.channel_alignment(w, land), 4)})
    return rows


# --------------------------------------------------------------- hillshades
def write_hillshades(before, maps, crops) -> None:
    van = load(GAME / "map_data/heightmap.png")
    for i, (y, x) in enumerate(VANILLA_CROPS[:1]):
        c = halve(van[y:y + 1024, x:x + 1024]).astype(np.float32)
        Image.fromarray(M.hillshade(c, KM_PX_OURS)).save(
            OUT / "hillshade_ck3_vanilla_mountains.png")
    del van
    for region, c in crops.items():
        y, x, s = c["crop_y"], c["crop_x"], c["crop_side"]
        for name, arr in [("plain_rescale", before)] + list(maps.items()):
            img = M.hillshade(arr[y:y + s, x:x + s].astype(np.float32), KM_PX_OURS)
            Image.fromarray(img).save(OUT / f"hillshade_{region}_{name}.png")


def write_csv(name: str, rows: list[dict]) -> None:
    if not rows:
        return
    path = OUT / name
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"  wrote {path.relative_to(ROOT)} ({len(rows)} rows)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--before-mod", default=str(ROOT / "../_out/seafloor"),
                    help="the shipped build: gaussian de-terrace + isotropic fill")
    ap.add_argument("--after-mod", default=str(ROOT / "../_out/erosion"),
                    help="this lane's build: cliff-aware de-terrace + eroded relief")
    ap.add_argument("--skip-spectrum", action="store_true")
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    crops = json.loads((OUT / "crops.json").read_text())
    t0 = time.time()
    print("building the plain rescale", flush=True)
    before = plain_rescale_canvas()
    maps = {
        "ours_shipped_isotropic": load(Path(args.before_mod) / "map_data/heightmap.png"),
        "ours_eroded": load(Path(args.after_mod) / "map_data/heightmap.png"),
    }

    print("1. cliff survival", flush=True)
    write_csv("cliff_survival.csv", measure_cliffs(before, maps, crops))
    print("3. structure metrics", flush=True)
    write_csv("structure_metrics.csv", measure_structure(before, maps, crops))
    print("hillshades", flush=True)
    write_hillshades(before, maps, crops)
    if not args.skip_spectrum:
        print("2. radial spectrum", flush=True)
        rows = measure_spectrum(before, maps)
        write_csv("spectrum.csv", rows)
        write_csv("spectrum_bands.csv", band_table(rows))
    print(f"done in {time.time() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
