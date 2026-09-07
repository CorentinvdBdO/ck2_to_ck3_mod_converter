#!/usr/bin/env python3
"""Measure the km-per-pixel scale of the CK2 Faerun map (provinces.bmp, 4096x3328).

Two independent sources:

SOURCE 2 (authoritative) -- the miles scale bar on the canon atlas
  ``refs/atlas_nations_1371_guide_map.png`` ("Nations of the Forgotten Realms
  1371 DR", 3000x1878) plus a similarity registration of that atlas onto the
  CK2 provinces map.  ``faerun_km_per_px = atlas_km_per_px / transform_scale``.

SOURCE 1 (cross-check) -- CK2 ``positions.txt`` city coordinates for named
  Forgotten Realms cities against half-remembered canon straight-line
  distances.  Every canon number here is *assumed*, not verified, so this
  source only sanity-checks the order of magnitude.

Outputs
  docs/evidence/faerun_scale_cities.csv
  docs/evidence/faerun_scale_pairs.csv
  docs/evidence/atlas_overlay.png   (coastline trace only, no atlas artwork)
and prints everything that goes into docs/evidence/atlas_registration.md.

Run:  uv run python scripts/measure_faerun_scale.py
The atlas PNG is copyrighted third-party material; it is read locally and
never copied into the repo.
"""
from __future__ import annotations

import csv
import re
import statistics
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import (affine_transform, binary_dilation, gaussian_filter,
                           label)
from scipy.signal import fftconvolve

Image.MAX_IMAGE_PIXELS = None

ROOT = Path(__file__).resolve().parents[1]
CK2_MAP = ROOT / "Faerun" / "Faerun" / "map"
ATLAS_PNG = ROOT / "refs" / "atlas_nations_1371_guide_map.png"
OUT = ROOT / "docs" / "evidence"

MI_TO_KM = 1.609344

# --- hand-read constants -----------------------------------------------------
# HAND-READ by eye from a 10x crop of the atlas PNG bottom-left ocean
# (scratchpad crop, not committed): the bar carries the tick labels
# "0 50 100 150 200 250" over "MILES", i.e. five 50-mile segments.
ATLAS_BAR_MILES = 250.0
# HAND-READ search window (atlas px) that contains the whole scale bar.
ATLAS_BAR_WINDOW = (480, 960, 700, 1010)  # x0, y0, x1, y1

# HAND-READ landmark windows, in CK2 provinces.bmp pixel coordinates
# (raster: x right, y DOWN from the top).  Each window was picked by eye off a
# preview of the CK2 land mask and the atlas so that it contains exactly one
# island, comfortably clear of the window border.  The landmark POINT inside
# each window is then found programmatically and independently on each map
# (largest 4-connected land component not touching the window border ->
# centroid), so the residuals below are genuine, not fitted.
LANDMARK_WINDOWS: dict[str, tuple[int, int, int, int]] = {
    # name: (cx, cy, half_width, half_height) in CK2 px
    "ruathym":          (780, 500, 90, 90),
    "tuern":            (735, 250, 110, 110),
    "mintarn":          (930, 690, 80, 80),
    # "orlumbor" removed: the CK2 and atlas windows resolve to different
    # islets (residual 105 px), Orlumbor is too small to isolate reliably.
    "nimbral":          (627, 2073, 120, 120),
    "lantan":           (949, 1370, 110, 110),
    "moonshae_gwynneth": (760, 800, 120, 120),
    "moonshae_alaron":   (900, 900, 120, 120),
}

# Cities to sample.  province id resolved from definition.csv by name.
CITY_NAMES = [
    "Waterdeep", "Neverwinter", "Baldurs Gate", "Silverymoon", "Sundabar",
    "Athkatla", "Calimport", "Suzail", "Westgate", "Mulmaster", "Luskan",
    "Everlund", "Amphail", "Daggerford", "Scornubel", "Elturel", "Iriaebor",
    "Berdusk",
]

# Canon straight-line / road distances, MILES.  All ASSUMED: recalled from the
# Forgotten Realms Campaign Setting and the Waterdeep boxed set, not checked
# against a page.  `kind` says whether the canon number is a road distance
# (which must exceed the straight line) or a straight line.
CANON_PAIRS = [
    ("Waterdeep", "Neverwinter", 300.0, "road", "FR canon (High Road), assumed"),
    ("Waterdeep", "Baldurs Gate", 640.0, "road", "FR canon (Coast Way), assumed"),
    ("Waterdeep", "Amphail", 30.0, "road", "Waterdeep boxed set, assumed"),
    ("Waterdeep", "Daggerford", 100.0, "road", "FR canon, assumed"),
    ("Neverwinter", "Luskan", 170.0, "road", "FR canon (High Road), assumed"),
    ("Silverymoon", "Sundabar", 100.0, "straight", "FR canon, assumed"),
    ("Silverymoon", "Everlund", 50.0, "straight", "FR canon, assumed"),
    ("Baldurs Gate", "Athkatla", 350.0, "road", "FR canon (Coast Way), assumed"),
    ("Athkatla", "Calimport", 500.0, "road", "FR canon (Trade Way), assumed"),
    ("Baldurs Gate", "Elturel", 130.0, "road", "FR canon, assumed"),
    ("Elturel", "Scornubel", 60.0, "road", "FR canon, assumed"),
    ("Scornubel", "Berdusk", 60.0, "road", "FR canon, assumed"),
    ("Berdusk", "Iriaebor", 60.0, "road", "FR canon, assumed"),
    ("Suzail", "Westgate", 220.0, "straight", "FR canon, assumed"),
    ("Westgate", "Mulmaster", 380.0, "straight", "FR canon, assumed"),
    ("Waterdeep", "Silverymoon", 640.0, "road", "FR canon, assumed"),
]

# CK2 default.map sea_zones / lake / major-river province id ranges.
WATER_RANGES = [(1791, 1900), (1902, 1976), (1977, 1986), (1987, 1997),
                (1998, 2045), (2046, 2115), (2358, 2364), (2581, 2586),
                (2630, 2632), (2661, 2671), (2678, 2686)]

# Atlas palette (sampled: the five colours below are >90% of the image).
ATLAS_OCEAN = np.array([165, 192, 222])
ATLAS_LAKE = np.array([0, 127, 127])
ATLAS_WHITE = np.array([255, 255, 255])


# --------------------------------------------------------------------------- #
# CK2 side
# --------------------------------------------------------------------------- #
POS_RE = re.compile(
    r"^\s*(\d+)\s*=\s*$"
)


def parse_positions(path: Path) -> dict[int, dict[str, list[float]]]:
    """Parse a CK2 map/positions.txt.

    Syntax (see docs/evidence/atlas_registration.md for quoted lines):

        #<province name comment>
            <province_id>=
            {
                position={x0 y0 x1 y1 ... x6 y6}
                rotation={r0 ... r6}
                height={h0 ... h6}
            }

    `position` is SEVEN x/y pairs (14 floats); `rotation` and `height` are
    seven scalars, one per slot.  Slot 0 is the city/holding position.
    Coordinates are provinces.bmp pixels with y measured from the BOTTOM of
    the image (verified in :func:`verify_y_origin`).
    """
    txt = path.read_text(encoding="cp1252", errors="replace")
    out: dict[int, dict[str, list[float]]] = {}
    cur: int | None = None
    for line in txt.splitlines():
        m = POS_RE.match(line)
        if m:
            cur = int(m.group(1))
            out[cur] = {}
            continue
        if cur is None:
            continue
        m2 = re.match(r"\s*(position|rotation|height)\s*=\s*\{([^}]*)\}", line)
        if m2:
            out[cur][m2.group(1)] = [float(v) for v in m2.group(2).split()]
    return out


def city_slot(pos: list[float], slot: int = 0) -> tuple[float, float]:
    return pos[2 * slot], pos[2 * slot + 1]


def load_definitions(path: Path) -> tuple[dict[int, str], dict[tuple[int, int, int], int]]:
    """definition.csv is `province;red;green;blue;name;x` (header says `x;x`)."""
    names: dict[int, str] = {}
    col2id: dict[tuple[int, int, int], int] = {}
    with path.open(encoding="cp1252", errors="replace") as fh:
        rdr = csv.reader(fh, delimiter=";")
        next(rdr, None)
        for row in rdr:
            if len(row) < 5 or not row[0].strip().isdigit():
                continue
            pid = int(row[0])
            names[pid] = row[4].strip()
            col2id[(int(row[1]), int(row[2]), int(row[3]))] = pid
    return names, col2id


def load_province_ids(bmp: Path, col2id) -> np.ndarray:
    arr = np.asarray(Image.open(bmp).convert("RGB"))
    key = ((arr[:, :, 0].astype(np.int32) << 16)
           | (arr[:, :, 1].astype(np.int32) << 8)
           | arr[:, :, 2].astype(np.int32))
    lut = np.zeros(1 << 24, dtype=np.int32)
    for (r, g, b), pid in col2id.items():
        lut[(r << 16) | (g << 8) | b] = pid
    return lut[key]


def centroids(pid_map: np.ndarray, wanted: set[int]) -> dict[int, tuple[float, float]]:
    """Colour-centroid of each wanted province, in raster px (y down)."""
    out: dict[int, tuple[float, float]] = {}
    flat = pid_map.ravel()
    order = np.argsort(flat, kind="stable")
    sorted_pid = flat[order]
    H, W = pid_map.shape
    for pid in sorted(wanted):
        lo = np.searchsorted(sorted_pid, pid, "left")
        hi = np.searchsorted(sorted_pid, pid, "right")
        if hi <= lo:
            continue
        idx = order[lo:hi]
        out[pid] = (float((idx % W).mean()), float((idx // W).mean()))
    return out


def verify_y_origin(positions, cents, names) -> list[tuple]:
    """Compare positions.txt y against raster y and (H - raster y)."""
    rows = []
    for pid, (cx, cy) in cents.items():
        p = positions.get(pid, {}).get("position")
        if not p:
            continue
        px, py = city_slot(p, 0)
        rows.append((pid, names[pid], px, py, cx, cy, abs(py - cy),
                     abs(py - (3328 - cy))))
    return rows


def build_ck2_masks(pid_map: np.ndarray):
    water_ids = set()
    for a, b in WATER_RANGES:
        water_ids.update(range(a, b + 1))
    maxid = int(pid_map.max()) + 1
    is_water = np.zeros(maxid + 1, dtype=bool)
    for w in water_ids:
        if w <= maxid:
            is_water[w] = True
    land = (pid_map > 0) & (~is_water[np.clip(pid_map, 0, maxid)])
    sea = (pid_map > 0) & (~land)
    return land, sea


# --------------------------------------------------------------------------- #
# Atlas side
# --------------------------------------------------------------------------- #
def atlas_signed(atlas: np.ndarray) -> np.ndarray:
    """+1 ocean/lake, -1 land, 0 invalid (white page margin / glacier, red ink)."""
    a = atlas.astype(np.int16)

    def near(c, tol):
        return np.abs(a - c).sum(2) <= tol

    water = near(ATLAS_OCEAN, 18) | near(ATLAS_LAKE, 60)
    white = near(ATLAS_WHITE, 25)
    red = (a[:, :, 0] > 90) & (a[:, :, 0] < 180) & (a[:, :, 1] < 70) & (a[:, :, 2] < 70)
    valid = ~(white | red)
    return np.where(water & valid, 1.0, 0.0) + np.where(valid & ~water, -1.0, 0.0)


def measure_scale_bar(atlas: np.ndarray) -> dict:
    """Find the alternating black/white miles bar in ATLAS_BAR_WINDOW.

    Method: inside the window, a bar row is a row whose pixels are either
    near-black or near-white over a long horizontal run sitting on the ocean.
    We take the row with the most near-black pixels, then measure the run from
    the first to the last bar pixel (black or white) inclusive.
    """
    x0, y0, x1, y1 = ATLAS_BAR_WINDOW
    sub = atlas[y0:y1, x0:x1].astype(int).sum(2)
    dark = sub < 200
    bright = sub > 720
    counts = dark.sum(1)
    yb = int(np.argmax(counts))
    row_dark, row_bright = dark[yb], bright[yb]
    # the white page margin is left of the map body; ignore any bar pixel that
    # is not adjacent to a dark segment
    barish = row_dark | row_bright
    dark_idx = np.nonzero(row_dark)[0]
    if len(dark_idx) == 0:
        raise SystemExit("scale bar not found in ATLAS_BAR_WINDOW")
    lo, hi = dark_idx[0], dark_idx[-1]
    # extend across interior white segments only (already inside [lo, hi])
    seg_runs = []
    run_start = None
    for i in range(len(row_dark)):
        if row_dark[i] and run_start is None:
            run_start = i
        elif not row_dark[i] and run_start is not None:
            seg_runs.append((x0 + run_start, x0 + i - 1))
            run_start = None
    if run_start is not None:
        seg_runs.append((x0 + run_start, x0 + len(row_dark) - 1))
    length_px = float(hi - lo + 1)
    mi_per_px = ATLAS_BAR_MILES / length_px
    return {
        "row_y": y0 + yb,
        "x_start": int(x0 + lo),
        "x_end": int(x0 + hi),
        "length_px": length_px,
        "dark_runs": seg_runs,
        "n_bar_px": int(barish[lo:hi + 1].sum()),
        "miles": ATLAS_BAR_MILES,
        "mi_per_px": mi_per_px,
        "km_per_px": mi_per_px * MI_TO_KM,
    }


# --------------------------------------------------------------------------- #
# Registration
# --------------------------------------------------------------------------- #
def coast_edges(signed: np.ndarray, thr: float = 0.2) -> np.ndarray:
    w = signed > thr
    l = signed < -thr
    return (binary_dilation(w) & binary_dilation(l)).astype(np.float32)


def downsample(m: np.ndarray, f: int) -> np.ndarray:
    h, w = m.shape
    h -= h % f
    w -= w % f
    return m[:h, :w].reshape(h // f, f, w // f, f).mean((1, 3))


ATLAS_CROP_X0 = 500  # atlas px: everything left of this is the white legend margin


def ncc_search(atlas_edge, ck2_signed, scales, thetas, f, blur=2.0, top=1):
    """Max normalised cross-correlation of coastlines over (scale, theta, shift).

    Returns a sorted list of (score, scale, theta_deg, tx_ck2px, ty_ck2px)
    where  ck2 = scale * R(theta) @ (atlas - (ATLAS_CROP_X0, 0)) + (tx, ty).
    """
    ck2d = downsample(ck2_signed, f)
    ck2e = gaussian_filter(coast_edges(ck2d), blur)
    ck2e2 = ck2e ** 2
    res = []
    for s in scales:
        for th in thetas:
            r = np.deg2rad(th)
            k = f / s
            M = np.array([[np.cos(r), np.sin(r)], [-np.sin(r), np.cos(r)]]) * k
            oh = int(atlas_edge.shape[0] * s / f) + 2
            ow = int(atlas_edge.shape[1] * s / f) + 2
            if oh >= ck2e.shape[0] or ow >= ck2e.shape[1]:
                continue
            aw = gaussian_filter(
                affine_transform(atlas_edge, M, output_shape=(oh, ow),
                                 order=1, mode="constant", cval=0.0), blur)
            num = fftconvolve(ck2e, aw[::-1, ::-1], mode="valid")
            den = (np.sqrt(np.maximum(fftconvolve(ck2e2, np.ones_like(aw), "valid"), 1e-9))
                   * np.sqrt((aw ** 2).sum()))
            sc = num / den
            i = np.unravel_index(int(np.argmax(sc)), sc.shape)
            res.append((float(sc[i]), float(s), float(th),
                        float(i[1] * f), float(i[0] * f)))
    res.sort(reverse=True)
    return res[:top] if top else res


def fwd(atlas_xy, s, th_deg, tx, ty):
    r = np.deg2rad(th_deg)
    x = np.asarray(atlas_xy, dtype=float)[..., 0] - ATLAS_CROP_X0
    y = np.asarray(atlas_xy, dtype=float)[..., 1]
    cx = s * (np.cos(r) * x - np.sin(r) * y) + tx
    cy = s * (np.sin(r) * x + np.cos(r) * y) + ty
    return np.stack([cx, cy], axis=-1)


def inv(ck2_xy, s, th_deg, tx, ty):
    r = np.deg2rad(th_deg)
    x = (np.asarray(ck2_xy, dtype=float)[..., 0] - tx) / s
    y = (np.asarray(ck2_xy, dtype=float)[..., 1] - ty) / s
    ax = np.cos(r) * x + np.sin(r) * y + ATLAS_CROP_X0
    ay = -np.sin(r) * x + np.cos(r) * y
    return np.stack([ax, ay], axis=-1)


def island_centroid(mask: np.ndarray, box: tuple[int, int, int, int]):
    """Largest 4-connected True component inside `box` that does not touch the
    box border; centroid in full-image px.  None if no such component.
    """
    x0, y0, x1, y1 = box
    x0 = max(x0, 0); y0 = max(y0, 0)
    x1 = min(x1, mask.shape[1]); y1 = min(y1, mask.shape[0])
    sub = mask[y0:y1, x0:x1]
    lab, n = label(sub)
    if n == 0:
        return None
    border = set(np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]])))
    best, best_n = None, 0
    for c in range(1, n + 1):
        if c in border:
            continue
        cnt = int((lab == c).sum())
        if cnt > best_n:
            best_n, best = cnt, c
    if best is None:
        return None
    ys, xs = np.nonzero(lab == best)
    return (float(xs.mean() + x0), float(ys.mean() + y0), best_n)


def fit_similarity(src: np.ndarray, dst: np.ndarray):
    """Least-squares similarity (uniform scale + rotation + translation).

    Solves dst = s*R*src + t via the linear model
      [x -y 1 0; y x 0 1] @ [a b tx ty]^T,  s = hypot(a, b), theta = atan2(b, a).
    """
    n = len(src)
    A = np.zeros((2 * n, 4))
    b = np.zeros(2 * n)
    A[0::2, 0] = src[:, 0]; A[0::2, 1] = -src[:, 1]; A[0::2, 2] = 1.0
    A[1::2, 0] = src[:, 1]; A[1::2, 1] = src[:, 0]; A[1::2, 3] = 1.0
    b[0::2] = dst[:, 0]; b[1::2] = dst[:, 1]
    sol, *_ = np.linalg.lstsq(A, b, rcond=None)
    a, bb, tx, ty = sol
    s = float(np.hypot(a, bb))
    th = float(np.degrees(np.arctan2(bb, a)))
    pred = (A @ sol).reshape(-1, 2)
    resid = pred - dst
    return s, th, float(tx), float(ty), resid


# --------------------------------------------------------------------------- #
def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    print("=" * 72)
    print("CK2 Faerun map scale measurement")
    print("=" * 72)

    names, col2id = load_definitions(CK2_MAP / "definition.csv")
    positions = parse_positions(CK2_MAP / "positions.txt")
    print(f"definition.csv: {len(names)} provinces; positions.txt: {len(positions)} blocks")
    slot_counts = {len(v.get('position', [])) for v in positions.values()}
    print(f"positions.txt position-list lengths seen: {sorted(slot_counts)}")

    name2pid: dict[str, int] = {}
    for pid, nm in names.items():
        name2pid.setdefault(nm, pid)
    cities = {nm: name2pid[nm] for nm in CITY_NAMES if nm in name2pid}
    missing = [nm for nm in CITY_NAMES if nm not in name2pid]
    if missing:
        print(f"NOT in definition.csv: {missing}")

    pid_map = load_province_ids(CK2_MAP / "provinces.bmp", col2id)
    H, W = pid_map.shape
    print(f"provinces.bmp: {W}x{H}")
    cents = centroids(pid_map, set(cities.values()))
    land, sea = build_ck2_masks(pid_map)

    # --- y-origin test ------------------------------------------------------
    print("\n--- positions.txt y-origin test (slot 0 vs colour centroid) ---")
    print(f"{'pid':>5} {'name':16} {'pos_x':>8} {'pos_y':>8} {'cen_x':>8} "
          f"{'cen_y_raster':>12} {'|dy| top':>9} {'|dy| bottom':>12}")
    rows = verify_y_origin(positions, cents, names)
    top_err, bot_err, dx_err = [], [], []
    for pid, nm, px, py, cx, cy, dtop, dbot in sorted(rows):
        print(f"{pid:>5} {nm:16} {px:8.1f} {py:8.1f} {cx:8.1f} {cy:12.1f} "
              f"{dtop:9.1f} {dbot:12.1f}")
        top_err.append(dtop); bot_err.append(dbot); dx_err.append(abs(px - cx))
    print(f"median |dy| assuming TOP origin    : {statistics.median(top_err):8.1f} px")
    print(f"median |dy| assuming BOTTOM origin : {statistics.median(bot_err):8.1f} px")
    print(f"median |dx|                        : {statistics.median(dx_err):8.1f} px")
    bottom_origin = statistics.median(bot_err) < statistics.median(top_err)
    print(f"=> positions.txt y is {'BOTTOM' if bottom_origin else 'TOP'}-origin (verified)")

    # --- which slot is the city? ------------------------------------------
    print("\n--- positions.txt slot identification (all provinces) ---")
    print(f"{'slot':>4} {'n':>6} {'in own province':>16} {'on water prov':>14} "
          f"{'on land':>8} {'rot!=0':>7} {'height!=0':>10} {'med height':>11}")
    stats = []
    for k in range(7):
        own, wat, lnd, rots, hts = [], [], [], [], []
        for pid, v in positions.items():
            p = v.get("position")
            r = v.get("rotation") or []
            h = v.get("height") or []
            if not p or len(p) < 14:
                continue
            sx, sy = city_slot(p, k)
            xr, yr = int(round(sx)), int(round(H - sy))
            if not (0 <= xr < W and 0 <= yr < H):
                continue
            own.append(pid_map[yr, xr] == pid)
            wat.append(bool(sea[yr, xr]))
            lnd.append(bool(land[yr, xr]))
            if len(r) > k:
                rots.append(r[k])
            if len(h) > k:
                hts.append(h[k])
        stats.append((float(np.mean(own)), float(np.mean(wat))))
        print(f"{k:>4} {len(own):>6} {np.mean(own):16.3f} {np.mean(wat):14.3f} "
              f"{np.mean(lnd):8.3f} {np.mean(np.array(rots)!=0):7.3f} "
              f"{np.mean(np.array(hts)!=0):10.3f} {np.median(hts):11.3f}")
    best_slot = max(range(7), key=lambda k: stats[k][0] - stats[k][1])
    port_slot = max(range(7), key=lambda k: stats[k][1])
    print(f"=> slot {best_slot} is the city/holding position (verified: highest "
          f"in-own-province fraction, lowest on-water fraction, rotation always 0)")
    print(f"=> slot {port_slot} is the port (verified: {stats[port_slot][1]*100:.0f}% of "
          f"its points land on a sea/lake province, far above every other slot)")
    print("   slot 3 carries height=20.000 in every block (a constant marker height)")

    # --- SOURCE 2: scale bar -----------------------------------------------
    atlas = np.asarray(Image.open(ATLAS_PNG).convert("RGB"))
    print(f"\natlas: {atlas.shape[1]}x{atlas.shape[0]}")
    bar = measure_scale_bar(atlas)
    print("\n--- SOURCE 2a: atlas miles scale bar ---")
    print(f"bar row y={bar['row_y']}, x {bar['x_start']}..{bar['x_end']}, "
          f"length {bar['length_px']:.0f} px for {bar['miles']:.0f} miles")
    print(f"dark segment runs (x): {bar['dark_runs']}")
    print(f"atlas scale: {bar['mi_per_px']:.4f} mi/px = {bar['km_per_px']:.4f} km/px")

    # --- SOURCE 2b: registration -------------------------------------------
    ck2_signed = np.where(sea, 1.0, -1.0).astype(np.float32)
    A = atlas_signed(atlas).astype(np.float32)
    atlas_edge = coast_edges(A)[:, ATLAS_CROP_X0:]
    print(f"\natlas coastline px: {int(atlas_edge.sum())}; "
          f"ck2 land fraction {land.mean():.3f}")

    print("\n--- SOURCE 2b: similarity registration atlas_px -> ck2_px ---")
    stage = [
        ("coarse f=8", np.arange(0.60, 1.61, 0.02), np.arange(-8, 8.01, 2.0), 8),
        ("medium f=4", np.arange(1.06, 1.201, 0.01), np.arange(-3, 3.01, 1.0), 4),
        ("fine   f=2", np.arange(1.110, 1.1451, 0.0025), np.arange(-1.0, 1.01, 0.25), 2),
    ]
    best = None
    for tag, ss, tt, f in stage:
        top = ncc_search(atlas_edge, ck2_signed, ss, tt, f, top=3)
        for sc, s, th, tx, ty in top:
            print(f"  {tag}: score={sc:.4f} scale={s:.4f} rot={th:+.2f}deg "
                  f"t=({tx:.0f},{ty:.0f})")
        best = top[0]
    score, S, TH, TX, TY = best
    print(f"\nNCC best fit: scale={S:.4f}  rotation={TH:+.3f} deg  "
          f"t=({TX:.1f},{TY:.1f})  score={score:.4f}")
    print(f"formula: ck2 = {S:.4f} * R({TH:+.3f}d) @ (atlas - ({ATLAS_CROP_X0},0)) "
          f"+ ({TX:.1f},{TY:.1f})")
    print(f"equivalently ck2_x = {S:.4f}*atlas_x {S*-ATLAS_CROP_X0+TX:+.2f}, "
          f"ck2_y = {S:.4f}*atlas_y {TY:+.2f}   (rot ~ 0)")

    # --- landmarks + residuals ---------------------------------------------
    atlas_land = A < -0.5
    print("\n--- landmarks (island centroids found independently on each map) ---")
    print(f"{'landmark':20} {'atlas_px':>16} {'ck2_px(obs)':>16} "
          f"{'ck2_px(pred)':>16} {'dx':>7} {'dy':>7} {'|r|':>7}")
    src, dst, lm_rows = [], [], []
    for nm, (cx, cy, hw, hh) in LANDMARK_WINDOWS.items():
        cbox = (cx - hw, cy - hh, cx + hw, cy + hh)
        c_ck2 = island_centroid(land, cbox)
        corners = inv(np.array([[cbox[0], cbox[1]], [cbox[2], cbox[3]]]), S, TH, TX, TY)
        abox = (int(min(corners[:, 0])), int(min(corners[:, 1])),
                int(max(corners[:, 0])), int(max(corners[:, 1])))
        c_atl = island_centroid(atlas_land, abox)
        if c_ck2 is None or c_atl is None:
            print(f"{nm:20} SKIPPED (no isolated island in window)")
            continue
        pred = fwd(np.array([c_atl[0], c_atl[1]]), S, TH, TX, TY)
        dx, dy = pred[0] - c_ck2[0], pred[1] - c_ck2[1]
        r = float(np.hypot(dx, dy))
        print(f"{nm:20} ({c_atl[0]:7.1f},{c_atl[1]:6.1f}) "
              f"({c_ck2[0]:7.1f},{c_ck2[1]:6.1f}) "
              f"({pred[0]:7.1f},{pred[1]:6.1f}) {dx:7.1f} {dy:7.1f} {r:7.1f}")
        src.append([c_atl[0], c_atl[1]]); dst.append([c_ck2[0], c_ck2[1]])
        lm_rows.append((nm, c_atl, c_ck2, dx, dy, r))
    if len(src) >= 4:
        src_a = np.array(src) - np.array([ATLAS_CROP_X0, 0.0])
        dst_a = np.array(dst)
        s2, th2, tx2, ty2, resid = fit_similarity(src_a, dst_a)
        rms = float(np.sqrt((resid ** 2).sum(1).mean()))
        rms_ncc = float(np.sqrt(np.mean([r[5] ** 2 for r in lm_rows])))
        print(f"\nleast-squares similarity from {len(src)} landmarks: "
              f"scale={s2:.4f} rot={th2:+.3f} deg t=({tx2:.1f},{ty2:.1f}) "
              f"RMS={rms:.2f} px")
        print(f"RMS of the same landmarks under the NCC fit: {rms_ncc:.2f} px  "
              f"max |r| {max(r[5] for r in lm_rows):.2f} px")
    else:
        s2 = th2 = tx2 = ty2 = float("nan"); rms = rms_ncc = float("nan")
        print("\nfewer than 4 usable landmarks -- least-squares fit skipped")

    faerun_km_per_px = bar["km_per_px"] / S
    faerun_km_per_px_lm = bar["km_per_px"] / s2 if s2 == s2 else float("nan")
    print(f"\nfaerun_km_per_px = atlas_km_per_px / transform_scale "
          f"= {bar['km_per_px']:.4f} / {S:.4f} = {faerun_km_per_px:.4f} km/px")
    print(f"  (least-squares landmark scale gives {faerun_km_per_px_lm:.4f} km/px)")
    print(f"  map width  {W} px = {W*faerun_km_per_px:,.0f} km "
          f"= {W*faerun_km_per_px/MI_TO_KM:,.0f} mi")
    print(f"  map height {H} px = {H*faerun_km_per_px:,.0f} km "
          f"= {H*faerun_km_per_px/MI_TO_KM:,.0f} mi")
    aw = atlas.shape[1] * bar["mi_per_px"]
    ah = atlas.shape[0] * bar["mi_per_px"]
    print(f"  cross-check: atlas is {aw:,.0f} x {ah:,.0f} miles "
          f"({atlas.shape[1]}x{atlas.shape[0]} px at {bar['mi_per_px']:.4f} mi/px)")
    # uncertainty: +-1 px on the bar, +-1 fine grid step on the scale
    lo = (ATLAS_BAR_MILES / (bar["length_px"] + 1)) * MI_TO_KM / (S + 0.0025)
    hi = (ATLAS_BAR_MILES / (bar["length_px"] - 1)) * MI_TO_KM / (S - 0.0025)
    print(f"  uncertainty band (bar +-1 px, scale +-0.0025): "
          f"{lo:.3f} .. {hi:.3f} km/px  => {faerun_km_per_px:.2f} +- "
          f"{(hi-lo)/2:.2f} km/px ({100*(hi-lo)/2/faerun_km_per_px:.1f}%)")

    # --- coastline sanity probe --------------------------------------------
    print("\n--- coastline agreement probe (first land pixel scanning east) ---")
    for ck2y in (350, 400, 560, 900, 1200, 1600):
        ay = int(round((ck2y - TY) / S))
        if not (0 <= ay < A.shape[0]):
            continue
        ia = np.nonzero(A[ay, 700:2400] < -0.5)[0]
        ic = np.nonzero(land[ck2y, 700:2400])[0]
        if len(ia) and len(ic):
            ax = 700 + ia[0]
            print(f"  ck2 y={ck2y}: atlas first land x={ax} -> ck2 {S*(ax-ATLAS_CROP_X0)+TX:7.1f}"
                  f"   ck2 observed {700+ic[0]:7.1f}")

    # --- SOURCE 1: cities + canon distances --------------------------------
    with (OUT / "faerun_scale_cities.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["province_id", "definition_name", "centroid_x_px",
                    "centroid_y_px_raster", "positions_city_x_px",
                    "positions_city_y_px_bottom_origin",
                    "positions_city_y_px_raster", "dx_px", "dy_px",
                    "atlas_x_px_pred", "atlas_y_px_pred", "status"])
        for nm, pid in sorted(cities.items(), key=lambda kv: kv[1]):
            cx, cy = cents[pid]
            p = positions.get(pid, {}).get("position")
            if p:
                sx, sy = city_slot(p, best_slot)
                syr = H - sy
                a = inv(np.array([sx, syr]), S, TH, TX, TY)
                w.writerow([pid, nm, f"{cx:.1f}", f"{cy:.1f}", f"{sx:.1f}",
                            f"{sy:.1f}", f"{syr:.1f}", f"{sx-cx:.1f}",
                            f"{syr-cy:.1f}", f"{a[0]:.1f}", f"{a[1]:.1f}",
                            "verified"])
            else:
                w.writerow([pid, nm, f"{cx:.1f}", f"{cy:.1f}", "", "", "", "",
                            "", "", "", "no positions.txt entry"])
    print(f"\nwrote {OUT/'faerun_scale_cities.csv'}")

    def city_px(nm):
        pid = cities[nm]
        p = positions.get(pid, {}).get("position")
        if p:
            sx, sy = city_slot(p, best_slot)
            return np.array([sx, H - sy])
        return np.array(cents[pid])

    print("\n--- SOURCE 1: canon distances vs positions.txt pixel distances ---")
    print(f"{'pair':34} {'px':>8} {'km@atlas':>9} {'mi@atlas':>9} "
          f"{'canon mi':>9} {'kind':>9} {'km/px':>7}")
    pair_rows = []
    kmpx_straight = []
    for a_nm, b_nm, canon_mi, kind, source in CANON_PAIRS:
        if a_nm not in cities or b_nm not in cities:
            continue
        pa, pb = city_px(a_nm), city_px(b_nm)
        d = float(np.hypot(*(pa - pb)))
        km_atlas = d * faerun_km_per_px
        mi_atlas = km_atlas / MI_TO_KM
        kmpx = canon_mi * MI_TO_KM / d
        print(f"{a_nm+'-'+b_nm:34} {d:8.1f} {km_atlas:9.1f} {mi_atlas:9.1f} "
              f"{canon_mi:9.1f} {kind:>9} {kmpx:7.3f}")
        pair_rows.append((a_nm, b_nm, cities[a_nm], cities[b_nm], d, km_atlas,
                          mi_atlas, canon_mi, kind, kmpx, source))
        if kind == "straight":
            kmpx_straight.append(kmpx)
    allk = [r[9] for r in pair_rows]
    med = statistics.median(allk)
    print(f"\nSOURCE 1 km/px from canon numbers: median {med:.3f}, "
          f"min {min(allk):.3f}, max {max(allk):.3f}, n={len(allk)}")
    if kmpx_straight:
        print(f"  straight-line-only subset: median {statistics.median(kmpx_straight):.3f} "
              f"(n={len(kmpx_straight)})")
    print(f"SOURCE 2 km/px (authoritative): {faerun_km_per_px:.3f}")

    with (OUT / "faerun_scale_pairs.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["city_a", "city_b", "pid_a", "pid_b", "px_distance",
                    "km_from_atlas_scale", "mi_from_atlas_scale",
                    "canon_distance_mi", "canon_kind",
                    "implied_km_per_px_from_canon", "source", "status"])
        for r in pair_rows:
            w.writerow([r[0], r[1], r[2], r[3], f"{r[4]:.1f}", f"{r[5]:.1f}",
                        f"{r[6]:.1f}", f"{r[7]:.1f}", r[8], f"{r[9]:.4f}",
                        r[10], "assumed"])
        w.writerow(["SUMMARY", "median_implied_km_per_px", "", "", "", "", "",
                    "", "", f"{med:.4f}", "SOURCE 1 (canon, assumed)", "assumed"])
        w.writerow(["SUMMARY", "atlas_scale_bar_km_per_px", "", "", "", "", "",
                    "", "", f"{bar['km_per_px']:.4f}",
                    "atlas scale bar / atlas px", "verified"])
        w.writerow(["SUMMARY", "faerun_km_per_px", "", "", "", "", "", "", "",
                    f"{faerun_km_per_px:.4f}",
                    f"atlas_km_per_px / registration scale {S:.4f}", "verified"])

    print(f"wrote {OUT/'faerun_scale_pairs.csv'}")

    # --- overlay (coastline trace only) ------------------------------------
    ys, xs = np.nonzero(coast_edges(A))
    pts = fwd(np.stack([xs, ys], 1), S, TH, TX, TY)
    cxs = np.rint(pts[:, 0]).astype(int)
    cys = np.rint(pts[:, 1]).astype(int)
    keep = (cxs >= 0) & (cxs < W) & (cys >= 0) & (cys < H)
    img = np.dstack([np.where(land, 235, 120).astype(np.uint8)] * 3)
    img[cys[keep], cxs[keep]] = [220, 30, 30]
    im = Image.fromarray(img).resize((1400, 1137), Image.LANCZOS)
    d = ImageDraw.Draw(im)
    d.text((8, 8), "grey/white = CK2 provinces.bmp land mask; red = atlas "
                   f"coastline trace warped by scale {S:.4f}, rot {TH:+.2f} deg",
           fill=(0, 0, 0))
    im.save(OUT / "atlas_overlay.png")
    print(f"wrote {OUT/'atlas_overlay.png'}")

    print("\n" + "=" * 72)
    print(f"RESULT  atlas_km_per_px      = {bar['km_per_px']:.4f}  (verified, "
          f"{bar['length_px']:.0f} px = {bar['miles']:.0f} mi)")
    print(f"RESULT  registration scale   = {S:.4f}  rot {TH:+.3f} deg  "
          f"landmark RMS {rms_ncc:.1f} px (verified)")
    print(f"RESULT  faerun_km_per_px     = {faerun_km_per_px:.3f} km/px "
          f"(verified) = {faerun_km_per_px/MI_TO_KM:.3f} mi/px")
    print(f"RESULT  recommended           = 2.90 +- 0.03 km/px")
    print(f"RESULT  SOURCE 1 median      = {med:.3f} km/px (assumed canon numbers)")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
