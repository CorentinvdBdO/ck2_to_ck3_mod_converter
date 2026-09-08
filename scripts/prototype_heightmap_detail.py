"""Prototype: add vanilla-matched detail to our 8-bit-sourced CK3 heightmap.

Region: the Sword Coast (Waterdeep -> Baldur's Gate) on the generated map.
Nothing here is wired into the converter; it exists to measure whether the
four proposed passes close the gap to vanilla and what they cost.

Passes, in order:
  1. de-terrace   the CK2 source is 8 bit, so land carries only 160 distinct
                  levels 277 apart after the transfer curve; a small Gaussian
                  removes the staircase without touching real structure, which
                  is band-limited to the CK2 Nyquist anyway.
  2. spectral     vanilla's land heightmap is a clean power law: amplitude
     fill        ~ f^-2.0 over 0.005-0.6 cycles/km (R^2 fit in
                  docs/map_fidelity.md).  The pass fits that law to the crop's
                  own well-resolved low frequencies, and injects noise shaped
                  to exactly the per-frequency deficit, modulated per CK3
                  terrain class by docs/evidence/map_fidelity/hf_by_terrain.csv.
  3. river carve  a smooth valley along map_data/rivers.png, depth by the CK2
                  river width index.
  4. coast smooth blend the first few pixels of land toward the water level.

Outputs under docs/evidence/map_fidelity/sword_coast/:
  before.png after.png (hillshades), zoom_before.png zoom_after.png,
  detail_stats.csv, spectrum_prototype.csv

Run: uv run python scripts/prototype_heightmap_detail.py
"""
from __future__ import annotations

import argparse
import csv
import tomllib
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.ndimage import distance_transform_edt, gaussian_filter

from ck2ck3.map.config import ScaleConfig, plan_canvas

Image.MAX_IMAGE_PIXELS = None

OUT = Path("docs/evidence/map_fidelity/sword_coast")
HF_CSV = Path("docs/evidence/map_fidelity/hf_by_terrain.csv")

WATER = 4883
MAXLVL = 49205
KM_PER_PX = 1.4839
# The per-terrain high-frequency figures were measured on the vanilla 2x
# heightmap with a Gaussian of sigma 4 px = 2.97 km; use the same band here.
HF_SIGMA_KM = 4.0 * (1.4839 / 2)

# Sword Coast crop, canvas pixels. Waterdeep sits at (2344, 1098) and
# Baldur's Gate at (2576, 1676) (CK2 positions.txt slot 0, rescaled).
CROP = (2080, 940, 832, 896)  # x0, y0, w, h
ZOOM = (2240, 1020, 256, 256)


def terrain_map(cfg, canvas, crop) -> np.ndarray:
    """CK3 terrain key per canvas pixel over the crop, as a string array."""
    from ck2ck3.map.terrain import CK2_TO_CK3_TERRAIN
    from ck2ck3.map.ck2read import read_terrain_texture_map

    ck2_map = Path(cfg["input"]["ck2_map_dir"])
    tex = read_terrain_texture_map(ck2_map / "terrain.txt")  # index -> CK2 category
    with Image.open(ck2_map / "terrain.bmp") as im:
        tidx = np.asarray(im)
    with Image.open(ck2_map / "trees.bmp") as im:
        trees = np.asarray(im)
    tree_idx = {3, 4, 7, 10}  # Faerun default.map:52

    x0, y0, w, h = crop
    # canvas pixel -> source pixel (inverse of Canvas.to_target)
    xs = (np.arange(x0, x0 + w) - canvas.offset_x) / canvas.factor + canvas.crop_x0
    ys = (np.arange(y0, y0 + h) - canvas.offset_y) / canvas.factor + canvas.crop_y0
    sx = np.clip(np.round(xs).astype(int), 0, tidx.shape[1] - 1)
    sy = np.clip(np.round(ys).astype(int), 0, tidx.shape[0] - 1)
    idx = tidx[np.ix_(sy, sx)]
    tr = trees[np.ix_(np.clip(sy // 8, 0, trees.shape[0] - 1),
                      np.clip(sx // 8, 0, trees.shape[1] - 1))]

    lut = np.array([CK2_TO_CK3_TERRAIN.get(tex.get(i, "plains"), "plains")
                    for i in range(256)], dtype=object)
    out = lut[idx]
    forest = np.isin(tr, list(tree_idx))
    out = np.where(forest & (out != "mountains"), "forest", out)
    return out.astype("U18")


VANILLA_SLOPE = -2.0   # amplitude ~ f**slope, fitted on vanilla land patches


def radial_profile(P: np.ndarray) -> np.ndarray:
    h, w = P.shape
    yy, xx = np.mgrid[0:h, 0:w]
    r = np.hypot(yy - h // 2, xx - w // 2).astype(int)
    n = min(h, w) // 2
    return np.bincount(r.ravel(), weights=P.ravel())[:n] / np.maximum(
        np.bincount(r.ravel())[:n], 1)


def spectral_fill(h: np.ndarray, land: np.ndarray, km_per_px: float,
                  rng) -> tuple[np.ndarray, dict]:
    """Noise shaped to the per-frequency shortfall against vanilla's power law.

    Returns (unit-scaled noise field, diagnostics).  The field already carries
    the right amplitude at every frequency; the caller only modulates it per
    terrain class.
    """
    H, W = h.shape
    n = min(H, W)
    a = h[:n, :n] - h[:n, :n].mean()
    win = np.hanning(n)
    F = np.fft.fftshift(np.fft.fft2(a * win[:, None] * win[None, :]))
    amp = np.sqrt(radial_profile(np.abs(F) ** 2 / (n * n)))
    k_px = np.arange(len(amp)) / n
    k_km = k_px / km_per_px

    band = (k_km > 0.004) & (k_km < 0.03)
    if not band.any():
        band = (k_km > 0) & (k_km < 0.05)
    c = float(np.median(amp[band] * k_km[band] ** (-VANILLA_SLOPE)))
    with np.errstate(divide="ignore"):
        target = c * np.where(k_km > 0, k_km ** VANILLA_SLOPE, 0.0)
    deficit = np.sqrt(np.clip(target ** 2 - amp ** 2, 0, None))
    deficit[k_km < 0.01] = 0.0                    # keep the real large scales

    yy, xx = np.mgrid[0:H, 0:W]
    r = np.hypot(yy - H / 2, xx - W / 2)
    rr = np.clip((r / max(H, W) * n).astype(int), 0, len(deficit) - 1)
    shape = np.fft.ifftshift(deficit[rr])
    noise = np.fft.irfft2(np.fft.rfft2(rng.standard_normal((H, W))) *
                          shape[:, : W // 2 + 1], s=(H, W))
    s = noise[land].std() if land.any() else noise.std()
    return (noise / max(s, 1e-9)).astype(np.float32), {
        "power_law_c": round(c, 1),
        "fit_band_bins": int(band.sum()),
    }


def hf_targets() -> dict[str, float]:
    return {r["terrain"]: float(r["hf_rms_levels"]) for r in csv.DictReader(HF_CSV.open())}


def hf_rms(a: np.ndarray, mask: np.ndarray) -> float:
    sig = HF_SIGMA_KM / KM_PER_PX
    res = a - gaussian_filter(a, sig)
    return float(res[mask].std()) if mask.any() else 0.0


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
    # 128-colour palette keeps every PNG here well under the 1 MB evidence cap
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
    prof = np.bincount(r.ravel(), weights=P.ravel())[:n // 2] / np.maximum(
        np.bincount(r.ravel())[:n // 2], 1)
    return (np.arange(n // 2)[1:] / n) / km, np.sqrt(prof[1:])


def vanilla_zoom() -> None:
    """A vanilla CK3 coastal crop at OUR km per pixel, for a like-for-like look.

    Vanilla's heightmap is 2x its province map (0.742 km/px), so it is halved
    here to the 1.4839 km/px our map is built at.
    """
    ck3 = Path("/home/cvdbdo/.local/share/Steam/steamapps/common/"
               "Crusader Kings III/game/map_data/heightmap.png")
    if not ck3.exists():
        return
    # west coast of Brittany / Bay of Biscay: province px (3560, 1830) -> 2x
    box = (3560 * 2, 1830 * 2, 3560 * 2 + 1024, 1830 * 2 + 1024)
    with Image.open(ck3) as im:
        a = np.asarray(im.crop(box), dtype=np.uint16).astype(np.float32)
    a = a.reshape(512, 2, 512, 2).mean(axis=(1, 3))       # -> 1.4839 km/px
    water = a <= 3932
    save(hillshade(a, water).resize((512, 512), Image.NEAREST),
         OUT / "zoom_vanilla_1x.png", 512)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="configs/faerun_map.toml")
    ap.add_argument("--mod-dir", default=None)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    cfg = tomllib.loads(Path(args.config).read_text())
    ck2_map = Path(cfg["input"]["ck2_map_dir"])
    mod_dir = Path(args.mod_dir or cfg["output"]["mod_dir"])
    with Image.open(ck2_map / "provinces.bmp") as im:
        sw, sh = im.size
    sc = cfg["scale"]
    canvas = plan_canvas(sw, sh, ScaleConfig(
        vanilla_km_per_px=sc["vanilla_km_per_px"], source_km_per_px=sc["source_km_per_px"],
        sea_margin_px=sc["sea_margin_px"], canvas_multiple=sc["canvas_multiple"],
        max_canvas_px=sc["max_canvas_px"]))

    x0, y0, w, h = CROP
    with Image.open(mod_dir / "map_data/heightmap.png") as im:
        H = np.asarray(im.crop((x0, y0, x0 + w, y0 + h)), dtype=np.uint16).astype(np.float32)
    with Image.open(mod_dir / "map_data/rivers.png") as im:
        riv = np.asarray(im.crop((x0, y0, x0 + w, y0 + h)))

    land = H > WATER
    terr = terrain_map(cfg, canvas, CROP)
    targets = hf_targets()
    print(f"crop {w}x{h} at ({x0},{y0}); land {100 * land.mean():.1f} %; "
          f"distinct levels before {np.unique(H).size}")

    rng = np.random.default_rng(1357)
    out = H.copy()

    # 1. de-terrace ---------------------------------------------------------
    smooth = gaussian_filter(out, 1.6)
    out = np.where(land, smooth, out)

    # 2. spectral fill, amplitude per terrain class -------------------------
    noise, diag = spectral_fill(out, land, KM_PER_PX, rng)
    print(f"  power-law fit C={diag['power_law_c']} over {diag['fit_band_bins']} bins")
    amp = np.zeros_like(noise)
    rows = []
    for key in sorted(set(terr.ravel().tolist())):
        m = (terr == key) & land
        if not m.any():
            continue
        want = targets.get(key, targets.get("plains", 90.0))
        have = hf_rms(out, m)
        unit = hf_rms(noise, m) or 1.0
        need = max(want ** 2 - have ** 2, 0.0) ** 0.5
        amp[m] = need / unit
        rows.append({"terrain": key, "px": int(m.sum()),
                     "vanilla_hf_rms": round(want, 1),
                     "our_hf_rms_before": round(have, 1),
                     "noise_gain_levels": round(need / unit, 1)})
    amp = gaussian_filter(amp, 6.0)      # no seams at terrain borders
    out = out + amp * noise

    # 3. river carving ------------------------------------------------------
    is_river = (riv >= 3) & (riv <= 11)
    if is_river.any():
        dist = distance_transform_edt(~is_river)
        width_px = np.zeros_like(dist)
        width_px[is_river] = 2.0 + (11 - riv[is_river]) * 0.6
        wsp = gaussian_filter(width_px, 3.0) + 2.0
        depth = 900.0 * np.exp(-(dist / wsp) ** 2)
        out = out - depth * land

    # 4. coast smoothing ----------------------------------------------------
    d_sea = distance_transform_edt(land)
    coast = np.clip(d_sea / 4.0, 0, 1)
    out = np.where(land, WATER + (out - WATER) * (0.45 + 0.55 * coast), out)

    out = np.where(land, np.clip(out, WATER + 1, MAXLVL), H)
    after = np.round(out).astype(np.uint16)

    # --- evidence ----------------------------------------------------------
    for name, arr in (("before", H.astype(np.uint16)), ("after", after)):
        save(hillshade(arr.astype(np.float32), ~land), OUT / f"{name}.png", 640)
        zx, zy, zw, zh = ZOOM
        sub = arr[zy - y0:zy - y0 + zh, zx - x0:zx - x0 + zw].astype(np.float32)
        subw = ~land[zy - y0:zy - y0 + zh, zx - x0:zx - x0 + zw]
        save(hillshade(sub, subw).resize((512, 512), Image.NEAREST),
             OUT / f"zoom_{name}.png", 512)

    vanilla_zoom()

    stats = []
    for name, arr in (("before", H), ("after", after.astype(np.float32))):
        g = np.gradient(arr)
        stats.append({
            "stage": name,
            "distinct_levels": int(np.unique(arr).size),
            "land_p50": round(float(np.percentile(arr[land], 50)), 1),
            "land_p95": round(float(np.percentile(arr[land], 95)), 1),
            "hf_rms_land": round(hf_rms(arr, land), 1),
            "grad_mean_levels_per_km": round(
                float(np.hypot(g[0], g[1])[land].mean() / KM_PER_PX), 1),
        })
    stats.append({"stage": "vanilla_reference", "distinct_levels": 31516,
                  "land_p50": 9008.0, "land_p95": 26140.0,
                  "hf_rms_land": "see hf_by_terrain.csv", "grad_mean_levels_per_km": 140.8})
    with (OUT / "detail_stats.csv").open("w", newline="") as f:
        wri = csv.DictWriter(f, fieldnames=list(stats[0].keys()))
        wri.writeheader()
        wri.writerows(stats)
    with (OUT / "per_terrain_gain.csv").open("w", newline="") as f:
        wri = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        wri.writeheader()
        wri.writerows(rows)

    spec = []
    for name, arr in (("before", H), ("after", after.astype(np.float32))):
        k, a = spectrum(arr, KM_PER_PX)
        spec += [{"stage": name, "cycles_per_km": float(kk), "amplitude_levels": float(aa)}
                 for kk, aa in zip(k, a)]
    with (OUT / "spectrum_prototype.csv").open("w", newline="") as f:
        wri = csv.DictWriter(f, fieldnames=["stage", "cycles_per_km", "amplitude_levels"])
        wri.writeheader()
        wri.writerows(spec)

    for s in stats:
        print("  " + "  ".join(f"{k}={v}" for k, v in s.items()))
    for r in rows:
        print("  " + "  ".join(f"{k}={v}" for k, v in r.items()))


if __name__ == "__main__":
    main()
