"""Heightmap fidelity: CK2 vs CK3 vs our generated map (lane map-fidelity).

Measures, on land only:
  * value distribution (percentiles) in 16-bit CK3 levels,
  * gradient statistics (levels per km),
  * a radial power spectrum on 512x512 land patches, in cycles/km,
  * vanilla CK3 high-frequency amplitude per CK3 terrain type.

Outputs (docs/evidence/map_fidelity/):
  heightmap_stats.csv, spectrum.csv, spectrum.png, hf_by_terrain.csv

Read-only on both game installs. Run: uv run python scripts/map_fidelity_heightmap.py
"""
from __future__ import annotations

import csv
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter

Image.MAX_IMAGE_PIXELS = None

CK2V = Path("/home/cvdbdo/.local/share/Steam/steamapps/common/Crusader Kings II/map")
FAE = Path("Faerun/Faerun/map")
CK3 = Path("/home/cvdbdo/.local/share/Steam/steamapps/common/Crusader Kings III/game")
GEN = Path("/home/cvdbdo/git/paradox/ck3/claudespace/mods/faerun_ck2_to_ck3_converted")
OUT = Path("docs/evidence/map_fidelity")

# CK2 8-bit -> CK3 16-bit transfer curve used by the converter (docs/map_scale.md §4).
CURVE_X = np.array([0.0, 95.0, 255.0])
CURVE_Y = np.array([0.0, 4883.0, 49205.0])
CK3_WATER = 4883.0
VANILLA_WATER = 3932.0


def ck2_to_ck3_levels(a: np.ndarray) -> np.ndarray:
    return np.interp(a.astype(np.float32), CURVE_X, CURVE_Y).astype(np.float32)


@dataclass
class MapH:
    name: str
    h: np.ndarray          # float32, CK3 16-bit level space
    km_per_px: float
    water: float
    label: str


def load_all() -> list[MapH]:
    maps: list[MapH] = []

    print("loading CK3 vanilla heightmap.png (122 MB) ...", flush=True)
    with Image.open(CK3 / "map_data/heightmap.png") as im:
        v = np.asarray(im, dtype=np.uint16).astype(np.float32)
    maps.append(MapH("ck3_vanilla", v, 1.4839 / 2, VANILLA_WATER, "verified"))

    print("loading our generated heightmap.png ...", flush=True)
    p = GEN / "map_data/heightmap.png"
    if p.exists():
        with Image.open(p) as im:
            g = np.asarray(im, dtype=np.uint16).astype(np.float32)
        maps.append(MapH("ours_generated", g, 1.4839, CK3_WATER, "verified"))

    print("loading CK2 Faerun topology.bmp ...", flush=True)
    with Image.open(FAE / "topology.bmp") as im:
        f = ck2_to_ck3_levels(np.asarray(im))
    maps.append(MapH("ck2_faerun", f, 2.90, CK3_WATER, "verified"))

    print("loading CK2 vanilla topology.bmp ...", flush=True)
    with Image.open(CK2V / "topology.bmp") as im:
        c = ck2_to_ck3_levels(np.asarray(im))
    # 3072 px across roughly the same world CK3 covers in 9216 px.
    maps.append(MapH("ck2_vanilla", c, 1.4839 * 9216 / 3072, CK3_WATER, "assumed"))
    return maps


def find_land_patches(h: np.ndarray, water: float, size: int, want: int, seed: int = 7):
    """Return up to `want` (y, x) origins of windows that are >=98 % above water."""
    rng = np.random.default_rng(seed)
    H, W = h.shape
    out = []
    tries = 0
    while len(out) < want and tries < 20000:
        tries += 1
        y = int(rng.integers(0, H - size))
        x = int(rng.integers(0, W - size))
        win = h[y:y + size, x:x + size]
        if (win > water + 1).mean() >= 0.98:
            out.append((y, x))
    return out


def radial_spectrum(win: np.ndarray, km_per_px: float):
    """1-D radially averaged power spectrum. Returns (cycles_per_km, amplitude)."""
    n = win.shape[0]
    w = np.hanning(n)
    win = (win - win.mean()) * w[:, None] * w[None, :]
    F = np.fft.fftshift(np.fft.fft2(win))
    P = (np.abs(F) ** 2) / (n * n)
    cy, cx = n // 2, n // 2
    yy, xx = np.mgrid[0:n, 0:n]
    r = np.hypot(yy - cy, xx - cx).astype(int)
    nb = np.bincount(r.ravel(), weights=P.ravel())
    cnt = np.bincount(r.ravel())
    prof = nb[:n // 2] / np.maximum(cnt[:n // 2], 1)
    k_px = np.arange(n // 2) / n                    # cycles per pixel
    k_km = k_px / km_per_px                         # cycles per km
    return k_km[1:], np.sqrt(prof[1:])              # amplitude, drop DC


def gradient_stats(h: np.ndarray, water: float, km_per_px: float, rng_seed=3):
    """|grad h| in levels per km, sampled on land."""
    rng = np.random.default_rng(rng_seed)
    H, W = h.shape
    vals = []
    for _ in range(400):
        y = int(rng.integers(1, H - 257))
        x = int(rng.integers(1, W - 257))
        win = h[y:y + 256, x:x + 256]
        m = win > water + 1
        if m.mean() < 0.95:
            continue
        gy, gx = np.gradient(win)
        vals.append(np.hypot(gy, gx)[m].ravel())
    if not vals:
        return {}
    v = np.concatenate(vals) / km_per_px
    return {
        "grad_mean_levels_per_km": float(v.mean()),
        "grad_p50_levels_per_km": float(np.percentile(v, 50)),
        "grad_p95_levels_per_km": float(np.percentile(v, 95)),
        "grad_max_levels_per_km": float(v.max()),
        "grad_n_px": int(v.size),
    }


def hf_rms(h: np.ndarray, water: float, km_per_px: float, sigma_km: float = 6.0, seed=11):
    """RMS of the high-pass residual (detail above `sigma_km`) on land, in levels."""
    rng = np.random.default_rng(seed)
    H, W = h.shape
    sig = max(1.0, sigma_km / km_per_px)
    vals = []
    for _ in range(400):
        y = int(rng.integers(0, H - 128))
        x = int(rng.integers(0, W - 128))
        win = h[y:y + 128, x:x + 128]
        if (win > water + 1).mean() < 0.98:
            continue
        vals.append(float((win - gaussian_filter(win, sig)).std()))
    if not vals:
        return {}
    v = np.array(vals)
    return {"hf_rms_levels_mean": float(v.mean()),
            "hf_rms_levels_p50": float(np.median(v)),
            "hf_rms_levels_p90": float(np.percentile(v, 90)),
            "hf_windows": int(v.size),
            "hf_sigma_km": sigma_km}


def basic_stats(h: np.ndarray, water: float) -> dict:
    land = h[h > water + 1]
    q = np.percentile(land, [1, 5, 25, 50, 75, 95, 99])
    return {
        "px_total": int(h.size),
        "land_frac": float((h > water + 1).mean()),
        "land_p01": float(q[0]), "land_p05": float(q[1]), "land_p25": float(q[2]),
        "land_p50": float(q[3]), "land_p75": float(q[4]), "land_p95": float(q[5]),
        "land_p99": float(q[6]), "land_max": float(h.max()),
        "distinct_values": int(np.unique(h).size),
    }


def per_terrain_hf():
    """Vanilla CK3 high-frequency amplitude per terrain type."""
    print("per-terrain: building province -> terrain map ...", flush=True)
    terr = {}
    default_land = "plains"
    with (CK3 / "common/province_terrain/00_province_terrain.txt").open(encoding="utf-8-sig") as f:
        for line in f:
            line = line.split("#")[0].strip()
            if "=" not in line:
                continue
            k, v = (s.strip() for s in line.split("=", 1))
            if k == "default_land":
                default_land = v
            elif k.isdigit():
                terr[int(k)] = v

    rgb2id = {}
    with (CK3 / "map_data/definition.csv").open(encoding="latin-1") as f:
        for line in f:
            p = line.strip().split(";")
            if len(p) < 5 or not p[0].isdigit():
                continue
            rgb2id[(int(p[1]) << 16) | (int(p[2]) << 8) | int(p[3])] = int(p[0])

    with Image.open(CK3 / "map_data/provinces.png") as im:
        prov = np.asarray(im.convert("RGB"))
    key = (prov[:, :, 0].astype(np.uint32) << 16) | (prov[:, :, 1].astype(np.uint32) << 8) | prov[:, :, 2]
    del prov
    uniq, inv = np.unique(key, return_inverse=True)
    del key
    names = np.array([terr.get(rgb2id.get(int(u), -1), default_land) for u in uniq])
    tmap = names[inv].reshape(4608, 9216)
    del inv, names

    print("per-terrain: loading heightmap ...", flush=True)
    with Image.open(CK3 / "map_data/heightmap.png") as im:
        h = np.asarray(im, dtype=np.uint16).astype(np.float32)

    rng = np.random.default_rng(23)
    rows = []
    for t in sorted(set(tmap.ravel().tolist())):
        if t in ("sea", "coastal_sea"):
            continue
        ys, xs = np.nonzero(tmap == t)
        if ys.size < 2000:
            continue
        hf, grad, amp = [], [], []
        idx = rng.choice(ys.size, size=min(4000, ys.size), replace=False)
        got = 0
        for i in idx:
            if got >= 300:
                break
            py, px = int(ys[i]), int(xs[i])
            if not (16 < py < 4592 and 16 < px < 9200):
                continue
            if not (tmap[py - 8:py + 8, px - 8:px + 8] == t).all():
                continue
            y, x = py * 2 - 32, px * 2 - 32
            win = h[y:y + 64, x:x + 64]
            if win.shape != (64, 64) or (win <= VANILLA_WATER).any():
                continue
            res = win - gaussian_filter(win, 4.0)   # detail below ~6 km
            hf.append(float(res.std()))
            gy, gx = np.gradient(win)
            grad.append(float(np.hypot(gy, gx).mean() / (1.4839 / 2)))
            amp.append(float(win.mean()))
            got += 1
        if got < 20:
            continue
        rows.append({
            "terrain": t, "windows": got,
            "px_share_pct": round(100.0 * float((tmap == t).mean()), 3),
            "hf_rms_levels": round(float(np.mean(hf)), 1),
            "hf_rms_p90": round(float(np.percentile(hf, 90)), 1),
            "grad_mean_levels_per_km": round(float(np.mean(grad)), 1),
            "mean_level": round(float(np.mean(amp)), 1),
        })
        print(f"  {t:<18} n={got:<4} hf_rms={rows[-1]['hf_rms_levels']:>7}", flush=True)
    return rows


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    maps = load_all()

    stat_rows, spec_rows = [], []
    for m in maps:
        print(f"stats {m.name} {m.h.shape} ...", flush=True)
        row = {"map": m.name, "km_per_px": m.km_per_px, "label": m.label,
               "width": m.h.shape[1], "height": m.h.shape[0]}
        row.update(basic_stats(m.h, m.water))
        row.update(gradient_stats(m.h, m.water, m.km_per_px))
        row.update(hf_rms(m.h, m.water, m.km_per_px))
        stat_rows.append(row)

        patches = find_land_patches(m.h, m.water, 512, 6)
        print(f"  {len(patches)} land patches", flush=True)
        acc = None
        for (y, x) in patches:
            k, a = radial_spectrum(m.h[y:y + 512, x:x + 512], m.km_per_px)
            acc = a if acc is None else acc + a
        if acc is not None:
            acc /= len(patches)
            for kk, aa in zip(k, acc):
                spec_rows.append({"map": m.name, "cycles_per_km": float(kk),
                                  "amplitude_levels": float(aa)})

    with (OUT / "heightmap_stats.csv").open("w", newline="") as f:
        keys = sorted({k for r in stat_rows for k in r})
        w = csv.DictWriter(f, fieldnames=["map", "label", "km_per_px", "width", "height"] +
                           [k for k in keys if k not in ("map", "label", "km_per_px", "width", "height")])
        w.writeheader()
        w.writerows(stat_rows)
    with (OUT / "spectrum.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["map", "cycles_per_km", "amplitude_levels"])
        w.writeheader()
        w.writerows(spec_rows)

    for m in maps:
        del m.h
    rows = per_terrain_hf()
    with (OUT / "hf_by_terrain.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print("done", flush=True)


if __name__ == "__main__":
    sys.exit(main())
