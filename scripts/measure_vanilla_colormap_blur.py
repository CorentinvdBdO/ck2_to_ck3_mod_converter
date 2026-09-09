#!/usr/bin/env python3
"""Measure the spatial scale vanilla's own `colormap.dds` varies at.

Lane `colormap-fix` step 2 needs a Gaussian blur radius for our own
per-terrain-key tint raster, so terrain-class boundaries do not read as flat
colour blocks the way vanilla's own painted, geography-driven variation never
does. Rather than guess a radius, this measures vanilla's own colour
autocorrelation length directly.

Method:

1. Find the single most "interior" land pixel - the one with the largest
   chessboard (Chebyshev) distance to the nearest water pixel
   (`scipy.ndimage.distance_transform_cdt`, `metric="chessboard"`). A square
   box of half-width `d - 1` centred there is then guaranteed fully on land
   (by the definition of the chessboard distance transform), so the box
   contains no water discontinuity to contaminate the measurement.
2. High-pass that box (subtract a heavily blurred, sigma=32px, copy of
   itself) to isolate texture-scale variation from the large slow gradient
   vanilla's colormap also carries.
3. Compute the 2D autocorrelation of the high-passed box via FFT, radially
   average it, and find the radius where it first drops to 1/e of its
   zero-lag value - the correlation length, in vanilla `colormap.dds` pixels.

Why this radius transfers to our own canvas unchanged (`assumed`, not
re-derived here): `docs/map_scale.md` builds our canvas so its km/px matches
vanilla's own (`vanilla_km_per_px` in `configs/faerun.toml`) - that is the
entire point of the scale-factor fit - so a correlation length measured in
vanilla pixels is already in the right units for a canvas-resolution blur on
our own raster, with no unit conversion. What is `assumed`, not measured: that
an autocorrelation e-folding radius is a reasonable stand-in for a Gaussian
blur sigma (the two are not identical for an arbitrary texture - only exactly
equivalent for blurred white noise), and that a single sample region
generalises to vanilla's whole map.

Usage::

    uv run scripts/measure_vanilla_colormap_blur.py [ck3_game_dir]
"""

from __future__ import annotations

import csv
import re
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.ndimage import distance_transform_cdt, gaussian_filter

Image.MAX_IMAGE_PIXELS = None

REPO = Path(__file__).resolve().parents[1]
DEFAULT_GAME = Path(
    "/home/cvdbdo/.local/share/Steam/steamapps/common/Crusader Kings III/game"
)
OUT_CSV = REPO / "docs" / "evidence" / "vanilla_colormap_blur.csv"

_RANGE_RE = re.compile(r"(?:sea_zones|lakes)\s*=\s*RANGE\s*\{\s*(\d+)\s+(\d+)\s*\}")
_LIST_RE = re.compile(r"(?:sea_zones|lakes)\s*=\s*LIST\s*\{([^}]*)\}")


def read_water_ids(default_map: Path) -> set[int]:
    txt = default_map.read_text(encoding="utf-8-sig", errors="replace")
    ids: set[int] = set()
    for a, b in _RANGE_RE.findall(txt):
        ids.update(range(int(a), int(b) + 1))
    for body in _LIST_RE.findall(txt):
        ids.update(int(x) for x in body.split())
    return ids


def read_definition(path: Path) -> dict[tuple[int, int, int], int]:
    out: dict[tuple[int, int, int], int] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        r = csv.reader(fh, delimiter=";")
        next(r, None)
        for row in r:
            if len(row) < 4:
                continue
            try:
                pid, red, green, blue = (
                    int(row[0]), int(row[1]), int(row[2]), int(row[3]),
                )
            except ValueError:
                continue
            out[(red, green, blue)] = pid
    return out


def province_id_raster(provinces_png: np.ndarray, definition: dict) -> np.ndarray:
    h, w = provinces_png.shape[:2]
    flat = provinces_png.reshape(-1, 3)
    keys = (flat[:, 0].astype(np.int64) << 16) | (flat[:, 1].astype(np.int64) << 8) | flat[:, 2]
    uniq_keys, inverse = np.unique(keys, return_inverse=True)
    lut = np.zeros(len(uniq_keys), dtype=np.int32)
    for i, k in enumerate(uniq_keys.tolist()):
        r, g, b = (k >> 16) & 0xFF, (k >> 8) & 0xFF, k & 0xFF
        lut[i] = definition.get((r, g, b), -1)
    return lut[inverse].reshape(h, w)


def radial_autocorr(patch: np.ndarray) -> np.ndarray:
    """1D radially-averaged autocorrelation of a 2D field, zero-lag = 1."""
    f = np.fft.fft2(patch)
    ac = np.fft.ifft2(f * np.conj(f)).real
    ac = np.fft.fftshift(ac)
    ac /= ac.max()
    cy, cx = ac.shape[0] // 2, ac.shape[1] // 2
    yy, xx = np.indices(ac.shape)
    r = np.sqrt((yy - cy) ** 2 + (xx - cx) ** 2).astype(int)
    total = np.bincount(r.ravel(), ac.ravel())
    count = np.bincount(r.ravel())
    return total / count


def main(argv: list[str]) -> int:
    game_dir = Path(argv[1]) if len(argv) > 1 else DEFAULT_GAME
    t0 = time.time()

    with Image.open(game_dir / "gfx" / "map" / "terrain" / "colormap.dds") as im:
        colormap = np.asarray(im.convert("RGB")).astype(np.float64)
    with Image.open(game_dir / "map_data" / "provinces.png") as im:
        provinces_png = np.asarray(im.convert("RGB"))
    definition = read_definition(game_dir / "map_data" / "definition.csv")
    province_ids = province_id_raster(provinces_png, definition)
    water_ids = read_water_ids(game_dir / "map_data" / "default.map")
    land_mask = ~np.isin(province_ids, list(water_ids)) & (province_ids > 0)
    print(f"loaded in {time.time() - t0:.2f}s, land pixels {int(land_mask.sum())}")

    # scipy's distance transform treats the array boundary as infinitely far,
    # not as background (`verified`: a tiny hand test grows distance right up
    # to a corner with no obstacle nearby) - pad a 1px false border so the
    # canvas edge itself counts as "water" and cannot win the search.
    padded = np.pad(land_mask, 1, constant_values=False)
    cd = distance_transform_cdt(padded, metric="chessboard")[1:-1, 1:-1]
    cy, cx = np.unravel_index(np.argmax(cd), cd.shape)
    d = int(cd[cy, cx])
    half = min(d - 1, 512)
    print(f"most-interior land pixel at ({cx},{cy}), chessboard distance {d}, box half-width {half}")
    box = colormap[cy - half : cy + half, cx - half : cx + half]
    assert land_mask[cy - half : cy + half, cx - half : cx + half].all(), "box touches water"

    gray = box.mean(axis=2)
    low = gaussian_filter(gray, sigma=32)
    hp = gray - low

    radial = radial_autocorr(hp)
    thresh = 1.0 / np.e
    below = np.nonzero(radial < thresh)[0]
    e_fold_radius = int(below[0]) if len(below) else len(radial) - 1

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["radius_px", "autocorrelation"])
        for r_i, v in enumerate(radial[: e_fold_radius + 20]):
            w.writerow([r_i, round(float(v), 4)])

    print(f"box centre ({cx},{cy}), half-width {half}")
    print(f"1/e autocorrelation radius: {e_fold_radius} px (vanilla colormap.dds pixels)")
    print(f"wrote {OUT_CSV}")
    print(f"\nRECOMMENDED colormap blur sigma (our canvas px, same km/px): {e_fold_radius}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
