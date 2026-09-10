#!/usr/bin/env python3
"""Is `[map.heightmap] resolution_factor = 2` worth its bytes?

Playtest 3: "I see the erosion, but still too smooth, not sharp enough."  Two
separable causes (docs/step_map_heightmap.md §7): our 1x sheet has a Nyquist
of 0.337 cycles/km against vanilla's 0.674, and the pass's own content above
0.2 cycles/km.  Only the first is fixed by 2x, and only if the detail pass is
*run* at 2x -- upsampling a finished 1x result adds no frequency at all,
which is why `oursharp_1x_upsampled` is measured here as the control.

Crops only (the goal's instruction): the two study regions, not the canvas.

Usage: uv run python scripts/relief_sharp_2x.py [--regions thay spine]
Writes: docs/evidence/relief_sharp/two_x_spectrum.csv, two_x_summary.csv
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import relief_sharp_common as C  # noqa: E402

Image.MAX_IMAGE_PIXELS = None
PATCH = 256


def plain_rescale_canvas_2x() -> np.ndarray:
    """The plain rescale exactly as `heightmap.build` makes it at factor 2."""
    from ck2ck3.map import heightmap as hm
    from ck2ck3.map.config import HeightmapConfig

    lut = hm.build_curve(HeightmapConfig(
        ck2_sea_level=C.CK2_SEA_LEVEL, ck3_water_level=C.WATER_LEVEL,
        ck3_max_level=C.MAX_LEVEL))
    with Image.open(C.CK2_MAP / "topology.bmp") as im:
        scaled = np.asarray(
            im.convert("L").resize((C.SCALED_W * 2, C.SCALED_H * 2), Image.LANCZOS))
    out8 = np.full((C.CANVAS_H * 2, C.CANVAS_W * 2), C.CK2_SEA_LEVEL, dtype=np.uint8)
    out8[C.OFFSET_Y * 2:C.OFFSET_Y * 2 + C.SCALED_H * 2,
         C.OFFSET_X * 2:C.OFFSET_X * 2 + C.SCALED_W * 2] = scaled
    del scaled
    return lut[out8]


def radial(win: np.ndarray, km_per_px: float):
    """Identical to scripts/report_map_paint_plots.py:radial_spectrum."""
    n = win.shape[0]
    w = np.hanning(n)
    a = (win.astype(np.float64) - win.mean()) * w[:, None] * w[None, :]
    P = (np.abs(np.fft.fftshift(np.fft.fft2(a))) ** 2) / (n * n)
    c = n // 2
    yy, xx = np.mgrid[0:n, 0:n]
    r = np.hypot(yy - c, xx - c).astype(int)
    prof = (np.bincount(r.ravel(), weights=P.ravel())[:c]
            / np.maximum(np.bincount(r.ravel())[:c], 1))
    return (np.arange(c) / n / km_per_px)[1:], np.sqrt(prof[1:])


def mean_spectrum(arr, land, km_per_px, want=24, seed=7):
    rng = np.random.default_rng(seed)
    H, W = arr.shape
    acc, k, n = None, None, 0
    tries = 0
    while n < want and tries < 20000:
        tries += 1
        y = int(rng.integers(0, H - PATCH))
        x = int(rng.integers(0, W - PATCH))
        if not land[y:y + PATCH, x:x + PATCH].all():
            continue
        k, a = radial(arr[y:y + PATCH, x:x + PATCH], km_per_px)
        acc = a if acc is None else acc + a
        n += 1
    return (k, acc / n, n) if n else (None, None, 0)


def sharpness(arr: np.ndarray, km_per_px: float, land: np.ndarray) -> dict:
    """Steepest one-pixel step, expressed per km so 1x and 2x compare."""
    g = []
    for axis in (0, 1):
        d = np.abs(np.diff(arr.astype(np.float64), axis=axis))
        m = (land[1:, :] & land[:-1, :]) if axis == 0 else (land[:, 1:] & land[:, :-1])
        g.append(d[m])
    g = np.concatenate(g) / km_per_px
    return {
        "grad_p99_levels_per_km": round(float(np.percentile(g, 99)), 0),
        "grad_p999_levels_per_km": round(float(np.percentile(g, 99.9)), 0),
        "grad_max_levels_per_km": round(float(g.max()), 0),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--regions", nargs="*", default=["thay", "spine"])
    ap.add_argument("--margin", type=int, default=128)
    args = ap.parse_args()
    from ck2ck3.map import heightmap_detail as hd
    from ck2ck3.map import packed_heightmap as ph
    from ck2ck3.map.config import HeightmapDetailConfig

    cfg = HeightmapDetailConfig(enabled=True)
    one = C.plain_rescale_canvas()
    two = plain_rescale_canvas_2x()
    van = C.load16(C.GAME / "map_data/heightmap.png")
    spec_rows, sum_rows = [], []

    def add_spec(region, name, k, a, n):
        spec_rows.extend({"region": region, "map": name, "patches": n,
                          "cycles_per_km": round(float(kk), 5),
                          "amplitude_levels": round(float(aa), 2)}
                         for kk, aa in zip(k, a))

    # vanilla once, on its own sheet, at its own km/px
    vland = van > C.VANILLA_WATER
    k, a, n = mean_spectrum(van, vland, C.KM_PX_VANILLA, want=48)
    add_spec("-", "ck3_vanilla", k, a, n)
    print(f"vanilla: {n} patches, Nyquist {k[-1]:.3f} c/km", flush=True)
    del van, vland

    for region in args.regions:
        m = args.margin
        cinfo = C.crops()[region]
        y, x, s = cinfo["crop_y"], cinfo["crop_x"], cinfo["crop_side"]
        for factor, canvas in ((1, one), (2, two)):
            mm, yy, xx, ss = m * factor, y * factor, x * factor, s * factor
            base = canvas[yy - mm:yy + ss + mm, xx - mm:xx + ss + mm]
            land = base > C.WATER_LEVEL
            zeros_i = np.zeros(base.shape, dtype=np.int16)
            t0 = time.time()
            out, stats = hd.apply(
                base, land_mask=land, terrain_code=zeros_i,
                terrain_keys=["mountains"],
                river_body=np.zeros(base.shape, dtype=bool),
                river_width_index=np.zeros(base.shape, dtype=np.float32),
                km_per_px=C.KM_PX_OURS / factor,
                water_level=C.WATER_LEVEL, max_level=C.MAX_LEVEL, cfg=cfg,
            )
            elapsed = time.time() - t0
            inner = (slice(mm, mm + ss), slice(mm, mm + ss))
            b_in, o_in, l_in = base[inner], out[inner], land[inner]
            kmpx = C.KM_PX_OURS / factor
            k, a, n = mean_spectrum(o_in, l_in, kmpx)
            if n:
                add_spec(region, f"ours_{factor}x", k, a, n)
            k, a, n = mean_spectrum(b_in, l_in, kmpx)
            if n:
                add_spec(region, f"plain_{factor}x", k, a, n)
            row = {"region": region, "factor": factor,
                   "px": int(o_in.size), "detail_s": round(elapsed, 1),
                   "s_per_megapx": round(elapsed / (base.size / 1e6), 2),
                   "nyquist_c_per_km": round(0.5 / kmpx, 3),
                   **sharpness(o_in, kmpx, l_in),
                   **C.moat_stats(b_in, o_in, l_in, f"ours_{factor}x"),
                   **{f"tr_{kk}": vv for kk, vv in
                      C.monotonic_violation(b_in, o_in, l_in).items()},
                   "packed_bytes_per_px": None}
            # tile-deduped packed size on this crop: a local estimate, the
            # deduper is global on the real canvas
            try:
                import tempfile
                with tempfile.TemporaryDirectory() as td:
                    meta = ph.write_packed(o_in, Path(td), verify=False)
                    tot = sum(f.stat().st_size for f in Path(td).rglob("*")
                              if f.is_file())
                row["packed_bytes_per_px"] = round(tot / o_in.size, 4)
                row["packed_meta"] = str(meta)[:120]
            except Exception as exc:                      # pragma: no cover
                row["packed_bytes_per_px"] = f"n/a ({type(exc).__name__})"
            sum_rows.append(row)
            print({kk: vv for kk, vv in row.items() if kk != "packed_meta"},
                  flush=True)
        # the control: a finished 1x result bicubic-upsampled to 2x adds
        # amplitude nowhere above the 1x Nyquist
        b1 = one[y - m:y + s + m, x - m:x + s + m]
        l1 = b1 > C.WATER_LEVEL
        out1, _ = hd.apply(
            b1, land_mask=l1, terrain_code=np.zeros(b1.shape, dtype=np.int16),
            terrain_keys=["mountains"],
            river_body=np.zeros(b1.shape, dtype=bool),
            river_width_index=np.zeros(b1.shape, dtype=np.float32),
            km_per_px=C.KM_PX_OURS, water_level=C.WATER_LEVEL,
            max_level=C.MAX_LEVEL, cfg=cfg,
        )
        up = np.asarray(Image.fromarray(out1[m:m + s, m:m + s]).resize(
            (s * 2, s * 2), Image.BICUBIC))
        lup = np.asarray(Image.fromarray(l1[m:m + s, m:m + s].astype(np.uint8))
                         .resize((s * 2, s * 2), Image.NEAREST)).astype(bool)
        k, a, n = mean_spectrum(up, lup, C.KM_PX_OURS / 2)
        if n:
            add_spec(region, "ours_1x_upsampled", k, a, n)

    C.OUT.mkdir(parents=True, exist_ok=True)
    for name, rows in (("two_x_spectrum.csv", spec_rows),
                       ("two_x_summary.csv", sum_rows)):
        keys: list[str] = []
        for r in rows:
            for kk in r:
                if kk not in keys:
                    keys.append(kk)
        with (C.OUT / name).open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=keys)
            w.writeheader()
            w.writerows(rows)
        print(f"wrote {C.OUT / name}")


if __name__ == "__main__":
    main()
