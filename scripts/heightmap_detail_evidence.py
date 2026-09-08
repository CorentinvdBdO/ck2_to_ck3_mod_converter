#!/usr/bin/env python3
"""Evidence for the wired-in heightmap detail pass (lane map-heightmap-detail).

Unlike `scripts/prototype_heightmap_detail.py` (a standalone crop-only
experiment), this reads the **real converter output**: a "before" run
(`[map] heightmap_detail = false`) and an "after" run (`= true`) of the same
config, both `--steps clean,map`. It writes, under
`docs/evidence/heightmap_detail/`:

  before.png / after.png       Sword Coast crop hillshade, full view
  zoom_before.png / zoom_after.png   a tighter zoom of the same crop
  spectrum.png                 radial power spectrum, before/after vs vanilla
  stats.csv                    distinct-value counts, gradient, HF RMS

Run:
  uv run --with matplotlib python scripts/heightmap_detail_evidence.py \\
      <before_out_dir> <after_out_dir>
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter

Image.MAX_IMAGE_PIXELS = None

OUT = Path("docs/evidence/heightmap_detail")
VANILLA_SPECTRUM_CSV = Path("docs/evidence/map_fidelity/spectrum.csv")

WATER = 4883
MAXLVL = 49205
KM_PER_PX = 1.4839
HF_SIGMA_PX = 4.0 * (1.4839 / 2) / KM_PER_PX

# same Sword Coast crop as scripts/prototype_heightmap_detail.py, canvas px
CROP = (2080, 940, 832, 896)
ZOOM = (2240, 1020, 256, 256)


def hillshade(h: np.ndarray, water: np.ndarray, az=315.0, alt=45.0, z=6.0) -> Image.Image:
    gy, gx = np.gradient(h.astype(np.float32) * z / 65535.0 * 200.0)
    slope = np.arctan(np.hypot(gx, gy))
    aspect = np.arctan2(-gx, gy)
    a, e = np.radians(az), np.radians(alt)
    shade = (np.sin(e) * np.cos(slope)
             + np.cos(e) * np.sin(slope) * np.cos(a - aspect))
    img = np.clip(shade, 0, 1)
    tint = np.clip((h - WATER) / (MAXLVL - WATER), 0, 1)
    rgb = np.empty(h.shape + (3,), dtype=np.uint8)
    rgb[..., 0] = np.clip(img * (110 + 130 * tint), 0, 255)
    rgb[..., 1] = np.clip(img * (140 + 90 * tint), 0, 255)
    rgb[..., 2] = np.clip(img * (105 + 120 * tint), 0, 255)
    rgb[water] = (36, 62, 104)
    return Image.fromarray(rgb)


def save(img: Image.Image, path: Path, max_w: int) -> None:
    if img.width > max_w:
        img = img.resize((max_w, round(img.height * max_w / img.width)), Image.LANCZOS)
    img = img.quantize(colors=128, method=Image.MEDIANCUT, dither=Image.Dither.NONE)
    img.save(path, optimize=True)
    print(f"  {path}  {img.size}  {path.stat().st_size / 1024:.0f} KiB")


def spectrum(a: np.ndarray, km: float):
    n = min(a.shape)
    a = a[:n, :n].astype(np.float64)
    w = np.hanning(n)
    a = (a - a.mean()) * w[:, None] * w[None, :]
    P = np.abs(np.fft.fftshift(np.fft.fft2(a))) ** 2 / (n * n)
    yy, xx = np.mgrid[0:n, 0:n]
    r = np.hypot(yy - n // 2, xx - n // 2).astype(int)
    prof = np.bincount(r.ravel(), weights=P.ravel())[: n // 2] / np.maximum(
        np.bincount(r.ravel())[: n // 2], 1
    )
    return (np.arange(n // 2)[1:] / n) / km, np.sqrt(prof[1:])


def hf_rms(a: np.ndarray, mask: np.ndarray) -> float:
    res = a - gaussian_filter(a, HF_SIGMA_PX)
    return float(res[mask].std()) if mask.any() else 0.0


def crop_heightmap(mod_dir: Path, box: tuple[int, int, int, int]) -> np.ndarray:
    x0, y0, w, h = box
    with Image.open(mod_dir / "map_data/heightmap.png") as im:
        return np.asarray(im.crop((x0, y0, x0 + w, y0 + h)), dtype=np.uint16).astype(np.float32)


def main() -> None:
    if len(sys.argv) != 3:
        print(__doc__.strip())
        raise SystemExit(2)
    before_dir, after_dir = Path(sys.argv[1]), Path(sys.argv[2])
    OUT.mkdir(parents=True, exist_ok=True)

    before = crop_heightmap(before_dir, CROP)
    after = crop_heightmap(after_dir, CROP)
    land = before > WATER  # identical land/water mask before and after (§3 invariant)

    print(f"crop {CROP[2]}x{CROP[3]} at ({CROP[0]},{CROP[1]}); land {100 * land.mean():.1f}%")
    print(f"distinct values in the crop: before={np.unique(before).size} after={np.unique(after).size}")

    x0, y0, _, _ = CROP
    for name, arr in (("before", before), ("after", after)):
        save(hillshade(arr, ~land), OUT / f"{name}.png", 640)
        zx, zy, zw, zh = ZOOM
        sub = arr[zy - y0 : zy - y0 + zh, zx - x0 : zx - x0 + zw]
        subw = ~land[zy - y0 : zy - y0 + zh, zx - x0 : zx - x0 + zw]
        save(hillshade(sub, subw).resize((512, 512), Image.NEAREST), OUT / f"zoom_{name}.png", 512)

    stats = []
    for name, arr in (("before", before), ("after", after)):
        g = np.gradient(arr)
        stats.append({
            "stage": name,
            "distinct_levels": int(np.unique(arr).size),
            "land_p50": round(float(np.percentile(arr[land], 50)), 1),
            "land_p95": round(float(np.percentile(arr[land], 95)), 1),
            "hf_rms_land": round(hf_rms(arr, land), 1),
            "grad_mean_levels_per_km": round(
                float(np.hypot(g[0], g[1])[land].mean() / KM_PER_PX), 1
            ),
        })
    with (OUT / "stats.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(stats[0].keys()))
        w.writeheader()
        w.writerows(stats)
    for s in stats:
        print("  " + "  ".join(f"{k}={v}" for k, v in s.items()))

    # --- spectrum plot: before/after (this crop) vs vanilla's own curve ---
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(7.2, 4.4), dpi=110)
    for name, arr, style in (("before", before, "--"), ("after", after, "-")):
        k, amp = spectrum(arr, KM_PER_PX)
        ax.loglog(k, amp, style, label=f"ours, {name}", lw=1.6)
    if VANILLA_SPECTRUM_CSV.exists():
        ks, amps = [], []
        with VANILLA_SPECTRUM_CSV.open() as f:
            for r in csv.DictReader(f):
                if r["map"] == "ck3_vanilla":
                    ks.append(float(r["cycles_per_km"]))
                    amps.append(float(r["amplitude_levels"]))
        ax.loglog(ks, amps, ":", label="ck3_vanilla", lw=1.4, color="0.3")
    for wl, lbl in ((10, "10 km"), (5, "5 km"), (2, "2 km"), (1, "1 km")):
        ax.axvline(1.0 / wl, color="0.85", lw=0.8, zorder=0)
    ax.set_xlabel("spatial frequency (cycles / km)")
    ax.set_ylabel("amplitude (CK3 16-bit height levels)")
    ax.set_title("Sword Coast crop, converter output before/after vs vanilla")
    ax.grid(True, which="both", alpha=0.25)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(OUT / "spectrum.png")
    plt.close(fig)
    print(f"  {OUT / 'spectrum.png'}  {(OUT / 'spectrum.png').stat().st_size / 1024:.0f} KiB")


if __name__ == "__main__":
    main()
