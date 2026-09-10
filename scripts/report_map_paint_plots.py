"""Figures for `docs/report_map_paint.md` (lane `report-paint`).

Run: uv run --with matplotlib python scripts/report_map_paint_plots.py
         [--mod DIR] [--recompute]
(matplotlib is deliberately not a repo dependency; --with keeps pyproject as is,
same convention as scripts/map_fidelity_plots.py.)

`--mod` is the reference conversion every measurement reads; it defaults to the
live generated mod (`../claudespace/mods/faerun_ck2_to_ck3_converted`).  The
first edition of this report measured `../_out/seafloor`, a build-8 conversion;
those CSVs and PNGs are kept under `docs/evidence/report_map_paint/build8/`.

Writes PNGs to docs/evidence/report_map_paint/.

Where the numbers come from.  Several series already exist as evidence CSVs and
are read as they are: docs/evidence/map_fidelity/hf_by_terrain.csv and
terrain_classes.csv, docs/evidence/vanilla_colormap_blur.csv,
mappings/colormap_tints.csv, mappings/terrain_paint.csv.  The rest are not in
any CSV yet, so this script measures them **once** from the rasters and caches
them beside the PNGs; later runs read the cache and touch no raster at all.
`--recompute` forces the measurement again.

  spectrum.csv             radial power spectrum of all four heightmaps.  Same
                           estimator as scripts/map_fidelity_heightmap.py, but
                           all-land patches (see find_land_patches) and n = 48,
                           so it does NOT reproduce
                           docs/evidence/map_fidelity/spectrum.csv exactly.
  height_hist.csv          land-height histogram, plain rescale vs shipped
  land_stats.csv           distinct values + land percentiles, both stages
  seafloor_transect.csv    one canvas row through the Sword Coast, before and
                           after [map.heightmap] deepen_sea
  terrain_area_share.csv   painted land-area share per CK3 terrain key, read
                           back out of the shipped detail_index.tga
  tree_counts.csv          instances per generator file, ours vs vanilla

  hf_achieved.csv          achieved high-frequency RMS per CK3 terrain key,
                           all land and interior land, measured with vanilla's
                           own estimator (see m_hf_achieved)
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

OUT = ROOT / "docs/evidence/report_map_paint"
FID = ROOT / "docs/evidence/map_fidelity"
EV = ROOT / "docs/evidence"

#: The reference conversion every measurement reads.  `--mod DIR` overrides it;
#: the default is the live generated mod, which is what the report is about
#: (build 12, 2026-09-10).  The first edition measured `../_out/seafloor`, a
#: build-8 conversion, and its CSVs/PNGs are kept under `OUT / "build8"`.
DEFAULT_MOD = ROOT / "../claudespace/mods/faerun_ck2_to_ck3_converted"
MOD = DEFAULT_MOD
GAME = ROOT / "../claudespace/game_files"
CK2_MAP = ROOT / "Faerun/Faerun/map"
CONFIG = ROOT / "configs/faerun.toml"

# --- constants every figure needs, all traceable ----------------------------
# docs/map_scale.md: 2.90 km/px CK2 source, 1.4839 km/px canvas (= vanilla's own)
KM_PX_CK2 = 2.90
KM_PX_OURS = 1.4839
KM_PX_VANILLA = 0.74195
# CLAUDE.md invariant / configs/faerun.toml [map.heightmap]
WATER_LEVEL = 4883
MAX_LEVEL = 49205
CK2_SEA_LEVEL = 95
SEA_SHELF_PX = 24
# docs/step_map_paint.md §9.7
OUR_LAND_SAT, OUR_WATER_SAT = 4.18, 1.02
VANILLA_LAND_SAT, VANILLA_WATER_SAT = 6.97, 0.85
BLUR_SIGMA = 9.0
# docs/step_map_paint.md §9.2
TREE_TARGET = 729838
VANILLA_TREES = 549126

C_VANILLA, C_OURS, C_BEFORE, C_CK2 = "#1b1b1b", "#c44e52", "#4c72b0", "#8172b2"


# ---------------------------------------------------------------- cache glue
def cached(name: str, fields: list[str], compute, recompute: bool) -> list[dict]:
    path = OUT / name
    if path.exists() and not recompute:
        with path.open() as f:
            return [r for r in csv.DictReader(f) if not r[fields[0]].startswith("#")]
    print(f"measuring {name} ...", flush=True)
    rows = compute()
    OUT.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    return rows


def read_csv(path: Path) -> list[dict]:
    with path.open() as f:
        return [r for r in csv.DictReader(f)
                if not next(iter(r.values())).lstrip().startswith("#")]


def _need(path: Path, what: str) -> Path:
    if not path.exists():
        raise SystemExit(
            f"missing {what}: {path}\n"
            f"  delete nothing -- either regenerate the mod "
            f"(docs/integration_run.md) or keep the cached CSV in {OUT}."
        )
    return path


def load_heightmap(path: Path) -> np.ndarray:
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None
    with Image.open(_need(path, "heightmap")) as im:
        return np.asarray(im.convert("I;16")).astype(np.uint16)


# ------------------------------------------------------------- measurements
def radial_spectrum(win: np.ndarray, km_per_px: float):
    """Identical to scripts/map_fidelity_heightmap.py:radial_spectrum."""
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
    k_km = (np.arange(c) / n) / km_per_px
    return k_km[1:], np.sqrt(prof[1:])


def find_land_patches(arrays, size, want, seed=7):
    """`want` (y, x) origins of windows that are **all** land in every array.

    scripts/map_fidelity_heightmap.py allows 2 % water per patch.  That is fine
    for a single map but not across the deepen_sea change: two per cent of a
    patch dropping from 4883 to 0 is a 4883-level step, and a step that big
    dominates the low-frequency end of the very spectrum being compared.  This
    version takes a list of (array, water level) and demands 100 % land in all
    of them, so every curve in figure 1 is measured over the same ground.
    """
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


# canvas geometry of the reference run (configs/faerun.toml [map], and the
# `scale factor 1.954310 -> canvas 8320x6784 (scaled 8005x6504, offset 157,140)`
# line every run logs -- docs/evidence/control_run_nodetail.log:5)
CANVAS_W, CANVAS_H = 8320, 6784
SCALED_W, SCALED_H = 8005, 6504
OFFSET_X, OFFSET_Y = 157, 140
SWORD_COAST = (940, 2080, 832)   # y, x, side -- docs/map_fidelity.md §4.2
#: patch geometry for figure 1.  256 px (380 km on our canvas) rather than the
#: 512 px scripts/map_fidelity_heightmap.py uses: an all-land 512 px window only
#: fits in Faerûn's few largest interiors, so every patch landed in one corner.
PATCH, PATCHES = 256, 48


def plain_rescale_canvas() -> np.ndarray:
    """`ours before the detail pass`, rebuilt exactly as ck2ck3.map.heightmap does.

    LANCZOS-resize the 8-bit CK2 source into the canvas rectangle, pad the sea
    margin at `ck2_sea_level`, then apply the converter's own transfer curve.
    Same code path as the shipped run with `[map] heightmap_detail = false`, so
    the two arrays are pixel-aligned and the same land patches can be used for
    both spectra.
    """
    from PIL import Image
    from ck2ck3.map import heightmap as hm
    from ck2ck3.map.config import HeightmapConfig
    lut = hm.build_curve(HeightmapConfig(
        ck2_sea_level=CK2_SEA_LEVEL, ck3_water_level=WATER_LEVEL,
        ck3_max_level=MAX_LEVEL))
    with Image.open(_need(CK2_MAP / "topology.bmp", "CK2 topology.bmp")) as im:
        scaled = np.asarray(im.convert("L").resize((SCALED_W, SCALED_H),
                                                   Image.LANCZOS))
    out8 = np.full((CANVAS_H, CANVAS_W), CK2_SEA_LEVEL, dtype=np.uint8)
    out8[OFFSET_Y:OFFSET_Y + SCALED_H, OFFSET_X:OFFSET_X + SCALED_W] = scaled
    return lut[out8]


VANILLA_WATER = 3932   # WATERLEVEL 3.0 / WORLD_EXTENTS_Y 50.0 x 65535


def _mean_spectrum(arr, patches, km_per_px):
    acc, k = None, None
    for (y, x) in patches:
        k, a = radial_spectrum(arr[y:y + PATCH, x:x + PATCH], km_per_px)
        acc = a if acc is None else acc + a
    return k, acc / len(patches)


def m_spectrum():
    """All four heightmaps, each on six all-land all-land patches of its own.

    Ours-before and ours-now share one patch set (same canvas, pixel-aligned);
    vanilla and the CK2 source are different sheets and get their own, the same
    way scripts/map_fidelity_heightmap.py does it.
    """
    rows = []

    def emit(name, k, a):
        rows.extend({"map": name, "cycles_per_km": float(kk),
                     "amplitude_levels": float(aa)} for kk, aa in zip(k, a))

    before = plain_rescale_canvas()
    now = load_heightmap(MOD / "map_data/heightmap.png")
    patches = find_land_patches([(before, WATER_LEVEL), (now, WATER_LEVEL)], PATCH, PATCHES)
    print(f"  ours: {len(patches)} patches", flush=True)
    emit("ours_before_detail", *_mean_spectrum(before, patches, KM_PX_OURS))
    emit("ours_now", *_mean_spectrum(now, patches, KM_PX_OURS))
    y, x, s = SWORD_COAST
    k, a = radial_spectrum(now[y:y + s, x:x + s], KM_PX_OURS)
    emit("ours_now_sword_coast", k, a)
    del before, now

    src = plain_rescale_source()
    p2 = find_land_patches([(src, WATER_LEVEL)], PATCH, PATCHES)
    print(f"  ck2_faerun: {len(p2)} patches", flush=True)
    emit("ck2_faerun", *_mean_spectrum(src, p2, KM_PX_CK2))
    del src

    van = load_heightmap(GAME / "map_data/heightmap.png")
    p3 = find_land_patches([(van, VANILLA_WATER)], PATCH, PATCHES)
    print(f"  ck3_vanilla: {len(p3)} patches", flush=True)
    emit("ck3_vanilla", *_mean_spectrum(van, p3, KM_PX_VANILLA))
    del van
    return rows


def plain_rescale_source() -> np.ndarray:
    """The CK2 Faerûn source through the converter's own transfer curve."""
    from PIL import Image
    from ck2ck3.map import heightmap as hm
    from ck2ck3.map.config import HeightmapConfig
    lut = hm.build_curve(HeightmapConfig(
        ck2_sea_level=CK2_SEA_LEVEL, ck3_water_level=WATER_LEVEL,
        ck3_max_level=MAX_LEVEL))
    with Image.open(_need(CK2_MAP / "topology.bmp", "CK2 topology.bmp")) as im:
        return lut[np.asarray(im.convert("L"))]


def m_height_hist():
    lo, hi = 7000, 14000
    rows = []
    for stage, arr in (("before", plain_rescale_canvas()),
                       ("now", load_heightmap(MOD / "map_data/heightmap.png"))):
        land = arr[arr > WATER_LEVEL]
        cnt = np.bincount(land.astype(np.int64), minlength=hi)[lo:hi]
        for i, c in enumerate(cnt):
            if c:
                rows.append({"stage": stage, "level": lo + i, "count": int(c)})
        del land, arr
    return rows


def m_land_stats():
    pcts = [1, 5, 25, 50, 75, 95, 99]
    rows = []
    for stage, arr in (("ours_before_detail", plain_rescale_canvas()),
                       ("ours_now", load_heightmap(MOD / "map_data/heightmap.png"))):
        land = arr[arr > WATER_LEVEL].astype(np.float64)
        r = {"stage": stage, "distinct_values": int(np.unique(arr).size),
             "land_px": int(land.size)}
        for p, v in zip(pcts, np.percentile(land, pcts)):
            r[f"land_p{p:02d}"] = round(float(v), 1)
        rows.append(r)
        del land, arr
    return rows


def m_seafloor_transect():
    """One canvas row west from Waterdeep, out into the Sea of Swords.

    Waterdeep's own province centroid is (2351.8, 5706.6) in the bottom-up
    locator frame (docs/step_map_paint.md §9.5), i.e. canvas row 6784-5707=1077.

    The `before` series is the plain rescale itself, not an older output
    directory.  `deepen_sea` acts on the plain rescale's water, so the plain
    rescale IS the CK2-derived floor, and taking it from here keeps the figure
    independent of which build happens to sit in `../_out` (the first edition
    read a build-8 run with `deepen_sea = false`).
    """
    y, x0, x1 = 1077, 1750, 2450
    now = load_heightmap(MOD / "map_data/heightmap.png")[y, x0:x1]
    before = plain_rescale_canvas()[y, x0:x1]
    return [{"x_px": x0 + i, "ck2_derived": int(b), "deepened": int(n)}
            for i, (b, n) in enumerate(zip(before, now))]


def m_water_stats():
    """Map-wide water-pixel percentiles, plain rescale vs shipped.

    §2's claim ("the water median goes 2981 -> 0") was quoted from
    `docs/step_map_paint.md` §9.6 in the first edition; measuring it here makes
    it a column of a CSV like every other number in the report.
    """
    from scipy.ndimage import distance_transform_edt
    plain = plain_rescale_canvas()
    ship = load_heightmap(MOD / "map_data/heightmap.png")
    water = ship <= WATER_LEVEL
    shelf = distance_transform_edt(water)[water] <= SEA_SHELF_PX
    rows = []
    for stage, arr in (("plain_rescale", plain), ("shipped", ship)):
        w = arr[water].astype(np.float64)
        rows.append({
            "stage": stage, "water_px": int(w.size),
            "p25": round(float(np.percentile(w, 25)), 1),
            "p50": round(float(np.median(w)), 1),
            "p75": round(float(np.percentile(w, 75)), 1),
            "max": round(float(w.max()), 1),
            "on_shelf_pct": round(100.0 * float(shelf.mean()), 1),
        })
    return rows


_WATER_FIELDS = ["stage", "water_px", "p25", "p50", "p75", "max",
                 "on_shelf_pct"]


def m_terrain_area_share():
    """Read the shipped paint back: detail_index channel 0 -> material -> key.

    Land only.  The paint covers the ocean too -- Faerûn's `terrain.bmp` index
    19 is the sea and its declared CK2 category is `coastal_desert`, which the
    class map sends to `drylands`, so counting every pixel would report 45 %
    drylands.  The land mask is the shipped heightmap's own (`deepen_sea` puts
    every province-water pixel at or below the water level), taken at the
    paint's 0.5 scale.
    """
    from PIL import Image
    from ck2ck3.map.terrain_paint import material_ordinals
    Image.MAX_IMAGE_PIXELS = None
    ords_ = material_ordinals(_need(GAME / "gfx/map/terrain/materials.settings",
                                    "vanilla materials.settings"))
    by_ord = {v: k for k, v in ords_.items()}
    prim = {}
    for r in read_csv(ROOT / "mappings/terrain_paint.csv"):
        prim.setdefault(r["primary_material"], []).append(r["ck3_terrain"])
    with Image.open(_need(MOD / "gfx/map/terrain/detail_index.tga",
                          "shipped detail_index.tga")) as im:
        idx = np.asarray(im.convert("RGBA"))[:, :, 0]
    land = load_heightmap(MOD / "map_data/heightmap.png") > WATER_LEVEL
    step = land.shape[0] // idx.shape[0]
    land = land[::step, ::step][:idx.shape[0], :idx.shape[1]]
    rows = []
    for label, mask in (("land", land), ("water", ~land)):
        counts = np.bincount(idx[mask].ravel(), minlength=256)
        for o, n in enumerate(counts):
            if not n:
                continue
            name = by_ord.get(o, f"ordinal_{o}")
            rows.append({"where": label, "material": name,
                         "ck3_terrain": "+".join(prim.get(name, ["(unmapped)"])),
                         "px": int(n)})
    return sorted(rows, key=lambda r: (r["where"], -r["px"]))


def _mod_province_terrain() -> tuple[np.ndarray, list[str]]:
    """Per-canvas-pixel CK3 terrain key of the reference mod, as a code grid.

    Vanilla's own `hf_by_terrain.csv` is measured per **province terrain**
    (scripts/map_fidelity_heightmap.py), not per painted material, so the
    achieved side has to be measured the same way or the comparison is
    between two different class maps.
    """
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None
    terr: dict[int, str] = {}
    for line in _need(MOD / "common/province_terrain/fae_province_terrain.txt",
                      "mod province_terrain").read_text(
                          encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        if k.strip().isdigit():
            terr[int(k.strip())] = v.strip()
    rgb2id: dict[int, int] = {}
    for line in _need(MOD / "map_data/definition.csv",
                      "mod definition.csv").read_text(
                          encoding="utf-8").splitlines():
        p = line.split(";")
        if len(p) >= 4 and p[0].isdigit() and int(p[0]):
            rgb2id[(int(p[1]) << 16) | (int(p[2]) << 8) | int(p[3])] = int(p[0])
    with Image.open(_need(MOD / "map_data/provinces.png",
                          "mod provinces.png")) as im:
        prov = np.asarray(im.convert("RGB"))
    key = ((prov[:, :, 0].astype(np.uint32) << 16)
           | (prov[:, :, 1].astype(np.uint32) << 8) | prov[:, :, 2])
    del prov
    uniq, inv = np.unique(key, return_inverse=True)
    del key
    names = sorted({terr.get(rgb2id.get(int(u), -1), "") for u in uniq})
    code_of = {n: i for i, n in enumerate(names)}
    codes = np.array([code_of[terr.get(rgb2id.get(int(u), -1), "")]
                      for u in uniq], dtype=np.int16)
    return codes[inv].reshape(-1, CANVAS_W), names


#: vanilla's estimator: 64 heightmap px at its 0.742 km/px = 47.5 km, high-pass
#: sigma 4.0 px = 2.97 km.  Ours is a 1x heightmap at 1.4839 km/px, so the same
#: ground is 32 px and the same cut-off is sigma 2.0 px.
HF_WIN_PX = 32
HF_SIGMA_PX = 2.968 / KM_PX_OURS
#: docs/step_map_heightmap.md: "interior" = land more than this far from water
INTERIOR_PX = 20


def m_hf_achieved():
    """Achieved high-frequency RMS per CK3 terrain key, all land and interior.

    Same estimator as vanilla's own `hf_by_terrain.csv`
    (`scripts/map_fidelity_heightmap.py`), transposed to a 1x heightmap: up to
    300 windows per class, each window entirely on land with its **central
    half** entirely inside the class -- vanilla checks a 16 province-px
    neighbourhood inside a 32 province-px window, and copying that exactly is
    what makes the two columns comparable.  The high-pass residual's standard
    deviation, averaged over windows.  The first edition of this report
    transcribed these numbers from
    `docs/evidence/HANDOFF_map_heightmap_detail.md` instead of measuring them.
    """
    from scipy.ndimage import distance_transform_edt, gaussian_filter
    tmap, names = _mod_province_terrain()
    h = load_heightmap(MOD / "map_data/heightmap.png").astype(np.float32)
    land = h > WATER_LEVEL
    hp = h - gaussian_filter(h, HF_SIGMA_PX)
    del h
    interior = distance_transform_edt(land) > INTERIOR_PX
    tgt = {r["terrain"]: float(r["hf_rms_levels"])
           for r in read_csv(FID / "hf_by_terrain.csv")}
    rng = np.random.default_rng(23)
    W = HF_WIN_PX
    rows = []
    for code, name in enumerate(names):
        if not name or name in ("sea", "coastal_sea"):
            continue
        sel = (tmap == code) & land
        ys, xs = np.nonzero(sel)
        if ys.size < 2000:
            continue
        idx = rng.choice(ys.size, size=min(20000, ys.size), replace=False)
        got = {"all_land": [], "interior": []}
        for i in idx:
            if len(got["all_land"]) >= 300 and len(got["interior"]) >= 300:
                break
            py, px = int(ys[i]), int(xs[i])
            y, x = py - W // 2, px - W // 2
            if not (0 <= y and y + W <= tmap.shape[0]
                    and 0 <= x and x + W <= tmap.shape[1]):
                continue
            if not land[y:y + W, x:x + W].all():
                continue
            q = W // 4
            if not (tmap[y + q:y + W - q, x + q:x + W - q] == code).all():
                continue
            v = float(hp[y:y + W, x:x + W].std())
            if len(got["all_land"]) < 300:
                got["all_land"].append(v)
            if interior[py, px] and len(got["interior"]) < 300:
                got["interior"].append(v)
        if len(got["all_land"]) < 20:
            continue
        rows.append({
            "terrain": name,
            "target": round(tgt.get(name, float("nan")), 1),
            "achieved_all_land": round(float(np.mean(got["all_land"])), 1),
            "achieved_interior": (round(float(np.mean(got["interior"])), 1)
                                  if len(got["interior"]) >= 20 else ""),
            "windows_all_land": len(got["all_land"]),
            "windows_interior": len(got["interior"]),
        })
    return sorted(rows, key=lambda r: r["terrain"])


_HF_FIELDS = ["terrain", "target", "achieved_all_land", "achieved_interior",
              "windows_all_land", "windows_interior"]


def m_tree_counts():
    def tally(d: Path) -> dict[str, int]:
        out = {}
        for p in sorted(d.glob("*.txt")):
            n = sum(int(m) for m in re.findall(r"\bcount\s*=\s*(\d+)", p.read_text(
                encoding="utf-8", errors="replace")))
            out[p.name] = n
        return out
    ours = tally(_need(MOD / "gfx/map/map_object_data/generated",
                       "shipped tree generators"))
    van = tally(_need(GAME / "gfx/map/map_object_data/generated",
                      "vanilla tree generators"))
    names = sorted(set(ours) | set(van))
    return [{"file": n, "ours": ours.get(n, 0), "vanilla": van.get(n, 0)}
            for n in names]


# ------------------------------------------------------------------ figures
def fig_spectrum(recompute: bool) -> str:
    series = defaultdict(lambda: ([], []))
    for r in cached("spectrum.csv",
                    ["map", "cycles_per_km", "amplitude_levels"],
                    m_spectrum, recompute):
        k, a = series[r["map"]]
        k.append(float(r["cycles_per_km"]))
        a.append(float(r["amplitude_levels"]))

    style = {
        "ck3_vanilla": ("vanilla CK3 (0.742 km/px)", C_VANILLA, "-", 2.0),
        "ck2_faerun": ("CK2 Faerûn source (2.90 km/px)", C_CK2, ":", 1.6),
        "ours_before_detail": ("ours, plain rescale", C_BEFORE, "--", 1.6),
        "ours_now": ("ours, shipped (same patches)", C_OURS, "-", 1.8),
        "ours_now_sword_coast": ("ours, shipped — Sword Coast crop (has a coastline in it)", C_OURS, "-.", 1.0),
    }
    fig, ax = plt.subplots(figsize=(8.4, 5.2), dpi=120)
    for name in ("ck3_vanilla", "ck2_faerun", "ours_before_detail", "ours_now",
                 "ours_now_sword_coast"):
        lbl, col, ls, lw = style[name]
        k, a = series[name]
        ax.loglog(k, a, ls, color=col, lw=lw, label=lbl)

    # f^-2.0 reference, anchored on vanilla at 0.02 cycles/km
    kv, av = np.array(series["ck3_vanilla"][0]), np.array(series["ck3_vanilla"][1])
    anchor = float(np.interp(0.02, kv, av))
    kk = np.array([0.004, 0.7])
    ax.loglog(kk, anchor * (kk / 0.02) ** -2.0, "-", color="0.55", lw=1.0,
              zorder=0,
              label=r"$f^{-2.0}$ reference slope (build 8's fill target; vanilla's"
                    "\nown fit over 0.02–0.4 c/km is −2.195, and the pass now uses"
                    "\nvanilla's measured curve instead)")

    for f, lbl, ls in ((1 / (2 * KM_PX_CK2), "CK2 source Nyquist\n0.172 c/km", "-"),
                       (1 / (2 * KM_PX_OURS), "our Nyquist\n0.337 c/km", "-."),
                       (1 / (2 * KM_PX_VANILLA), "vanilla Nyquist\n0.674 c/km", ":")):
        ax.axvline(f, color="0.7", lw=1.0, ls=ls, zorder=0)
        ax.text(f, 4.5, " " + lbl, fontsize=7, color="0.35", va="bottom")

    ax.set_xlim(0.004, 0.8)
    ax.set_ylim(3, 3e5)
    ax.set_xlabel("spatial frequency (cycles / km)")
    ax.set_ylabel("amplitude (CK3 16-bit height levels)")
    ax.set_title(f"Radial power spectrum, {PATCH}×{PATCH} all-land patches (n = {PATCHES})")
    ax.grid(True, which="both", alpha=0.22)
    ax.legend(fontsize=8, loc="lower left")
    fig.tight_layout()
    fig.savefig(OUT / "fig2_spectrum.png")
    plt.close(fig)
    return "fig2_spectrum.png"


def fig_heights(recompute: bool) -> str:
    hist = cached("height_hist.csv", ["stage", "level", "count"],
                  m_height_hist, recompute)
    stats = cached("land_stats.csv",
                   ["stage", "distinct_values", "land_px", "land_p01", "land_p05",
                    "land_p25", "land_p50", "land_p75", "land_p95", "land_p99"],
                   m_land_stats, recompute)
    st = {r["stage"]: r for r in stats}
    van = {r["map"]: r for r in read_csv(FID / "heightmap_stats.csv")}

    fig, (ax, bx) = plt.subplots(1, 2, figsize=(10.4, 4.4), dpi=120,
                                 gridspec_kw={"width_ratios": [1.35, 1]})

    lo, hi = 9000, 10400
    grid = np.arange(lo, hi)
    for stage, col, lbl in (
            ("before", C_BEFORE, "plain rescale (%s levels map-wide)"
             % f"{int(st['ours_before_detail']['distinct_values']):,}"),
            ("now", C_OURS, "shipped, detail pass (%s)"
             % f"{int(st['ours_now']['distinct_values']):,}")):
        y = np.full(hi - lo, 0.4)
        for r in hist:
            if r["stage"] == stage and lo <= int(r["level"]) < hi:
                y[int(r["level"]) - lo] = max(int(r["count"]), 0.4)
        ax.fill_between(grid, 0.4, y, step="mid", color=col, alpha=0.85, lw=0,
                        label=lbl)
    ax.set_yscale("log")
    ax.set_ylim(0.4, 3e6)
    ax.set_xlim(lo, hi - 1)
    ax.annotate("", xy=(9315, 1.6e6), xytext=(9038, 1.6e6),
                arrowprops=dict(arrowstyle="<->", color="0.35", lw=0.9))
    ax.text(9176, 1.9e6, "277 levels", fontsize=7.5, color="0.35", ha="center")
    ax.set_xlabel("16-bit height level")
    ax.set_ylabel("land pixels at that exact level (log)")
    ax.set_title("Land-height histogram, a 1400-level window\n"
                 "(the comb teeth are the 8-bit source's 277-level risers)")
    ax.grid(True, alpha=0.22)
    ax.legend(fontsize=8, loc="lower left")

    labels = ["p01", "p05", "p25", "p50", "p75", "p95", "p99"]
    b = np.arange(len(labels))
    ax2 = bx
    ax2.plot(b, [float(van["ck2_faerun"][f"land_{k}"]) for k in labels],
             "o", color=C_CK2, ms=11, mfc="none", mew=1.6,
             label="CK2 Faerûn source (docs/evidence/map_fidelity)")
    ax2.plot(b, [float(st["ours_before_detail"][f"land_{k}"]) for k in labels],
             "o--", color=C_BEFORE, label="ours, plain rescale")
    ax2.plot(b, [float(st["ours_now"][f"land_{k}"]) for k in labels],
             "s-", color=C_OURS, label="ours, shipped")
    ax2.set_xticks(b)
    ax2.set_xticklabels(labels)
    ax2.set_xlabel("land-elevation percentile")
    ax2.set_ylabel("16-bit height level")
    ax2.set_title("Macro: middle holds, tails move\n"
                  "(distinct values %s → %s; vanilla %s)"
                  % (st["ours_before_detail"]["distinct_values"],
                     st["ours_now"]["distinct_values"],
                     van["ck3_vanilla"]["distinct_values"]))
    ax2.grid(True, alpha=0.22)
    ax2.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(OUT / "fig3_heights.png")
    plt.close(fig)
    return "fig3_heights.png"


def fig_seafloor(recompute: bool) -> str:
    rows = cached("seafloor_transect.csv", ["x_px", "ck2_derived", "deepened"],
                  m_seafloor_transect, recompute)
    ws = {r["stage"]: r for r in cached("water_stats.csv", _WATER_FIELDS,
                                        m_water_stats, recompute)}
    x = np.array([int(r["x_px"]) for r in rows])
    before = np.array([int(r["ck2_derived"]) for r in rows])
    now = np.array([int(r["deepened"]) for r in rows])

    fig, ax = plt.subplots(figsize=(9.0, 4.2), dpi=120)
    ax.plot(x, before, color=C_BEFORE, lw=1.3,
            label="CK2-derived sea floor (the plain rescale, before deepen_sea)")
    ax.plot(x, now, color=C_OURS, lw=1.3, label="shipped (deepen_sea = true, 24 px shelf)")
    ax.axhline(WATER_LEVEL, color="#2a6fb0", lw=1.1, ls="--")
    ax.text(x[0] + 5, WATER_LEVEL + 400, f"water level {WATER_LEVEL}  "
            "(WATERLEVEL 3.8 / WORLD_EXTENTS_Y 51 × 65535)",
            fontsize=7.5, color="#2a6fb0")
    ax.axhline(0, color=C_VANILLA, lw=1.1, ls=":")
    ax.text(x[0] + 5, 500, "vanilla's own sea floor: a flat 0 (p25 = p50 = p75)",
            fontsize=7.5, color=C_VANILLA)
    ax.fill_between(x, 0, np.minimum(now, WATER_LEVEL),
                    where=now < WATER_LEVEL, color=C_OURS, alpha=0.10)
    ax.set_xlabel("canvas column (px), row 1077 — west from Waterdeep into the Sea of Swords")
    ax.set_ylabel("16-bit height level")
    ax.set_ylim(-800, 14000)
    ax.set_title("Sea-floor transect, Sword Coast  —  map-wide water median "
                 f"{float(ws['plain_rescale']['p50']):.0f} → "
                 f"{float(ws['shipped']['p50']):.0f}, p75 "
                 f"{float(ws['plain_rescale']['p75']):.0f} → "
                 f"{float(ws['shipped']['p75']):.0f}, "
                 f"{float(ws['shipped']['on_shelf_pct']):.1f} % on the shelf")
    ax.grid(True, alpha=0.22)
    ax.legend(fontsize=8, loc="upper left")
    fig.tight_layout()
    fig.savefig(OUT / "fig4_seafloor.png")
    plt.close(fig)
    return "fig4_seafloor.png"


def fig_colour() -> str:
    tints = [r for r in read_csv(ROOT / "mappings/colormap_tints.csv")]
    land = [r for r in tints if r["ck3_terrain"] != "water"]
    water = next(r for r in tints if r["ck3_terrain"] == "water")

    def sat(r):
        v = [int(r["tint_r"]), int(r["tint_g"]), int(r["tint_b"])]
        return max(v) - min(v)

    land.sort(key=sat)
    fig, (ax, bx) = plt.subplots(1, 2, figsize=(10.4, 4.4), dpi=120)
    cols = [(int(r["tint_r"]) / 255, int(r["tint_g"]) / 255, int(r["tint_b"]) / 255)
            for r in land]
    ax.barh([r["ck3_terrain"] for r in land], [sat(r) for r in land],
            color=cols, edgecolor="0.4", lw=0.5)
    ax.axvline(VANILLA_LAND_SAT, color=C_VANILLA, ls="--", lw=1.2)
    ax.set_ylim(-0.9, len(land) + 2.6)
    ax.text(VANILLA_LAND_SAT + 0.4, len(land) + 1.6,
            f"vanilla's own land mean {VANILLA_LAND_SAT}",
            fontsize=7.5, color=C_VANILLA, va="bottom")
    ax.axvline(OUR_LAND_SAT, color=C_OURS, ls="-", lw=1.2)
    ax.text(OUR_LAND_SAT + 0.4, len(land) + 0.9,
            f"our shipped land mean {OUR_LAND_SAT}",
            fontsize=7.5, color=C_OURS, va="bottom")
    ax.axvline(sat(water), color="#2a6fb0", ls=":", lw=1.2)
    ax.text(sat(water) + 0.4, len(land) + 0.2,
            f"water tint {sat(water)} (ours in game {OUR_WATER_SAT}, vanilla {VANILLA_WATER_SAT})",
            fontsize=7.5, color="#2a6fb0", va="bottom")
    ax.set_xlabel("tint saturation, max − min RGB channel (0–255 units)")
    ax.set_title("Per-terrain colormap tint\n(bar colour is the literal tint; "
                 "every value measured off vanilla)")
    ax.grid(True, axis="x", alpha=0.22)

    blur = read_csv(EV / "vanilla_colormap_blur.csv")
    r = np.array([float(x["radius_px"]) for x in blur])
    a = np.array([float(x["autocorrelation"]) for x in blur])
    bx.plot(r, a, "-o", color=C_VANILLA, ms=3, lw=1.4,
            label="vanilla colormap.dds autocorrelation")
    bx.axhline(1 / np.e, color="0.5", ls="--", lw=1.0)
    bx.text(r[-1], 1 / np.e, "1/e ", fontsize=8, color="0.4", ha="right", va="bottom")
    bx.axvline(BLUR_SIGMA, color=C_OURS, lw=1.2)
    bx.text(BLUR_SIGMA, 0.95, f" our blur σ = {BLUR_SIGMA:.0f} px", fontsize=8,
            color=C_OURS)
    bx.set_xlabel("radius (px; a vanilla colormap pixel and one of our canvas\npixels both cover 1.4839 km — docs/map_scale.md)")
    bx.set_ylabel("radially averaged autocorrelation")
    bx.set_title("Vanilla's own colour correlation length\n"
                 "(1/e crossing at 9 px sets our blur)")
    bx.grid(True, alpha=0.22)
    bx.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(OUT / "fig6_colour.png")
    plt.close(fig)
    return "fig6_colour.png"


CK2_CAT_TO_CK3 = {
    "plains": "plains", "farmlands": "farmlands", "coastal": "farmlands",
    "forest": "forest", "woods": "forest", "hills": "hills",
    "mountain": "mountains", "impassable_mountains": "mountains",
    "steppe": "steppe", "desert": "desert", "coastal_desert": "drylands",
    "jungle": "jungle", "marsh": "wetlands", "arctic": "taiga",
    "glacier": "taiga", "subterranean": "mountains", "pti": "plains",
}


def fig_composition(recompute: bool) -> str:
    share = cached("terrain_area_share.csv",
                   ["where", "material", "ck3_terrain", "px"],
                   m_terrain_area_share, recompute)
    ours = defaultdict(float)
    for r in share:
        if r["where"] != "land":
            continue
        ours[r["ck3_terrain"]] += int(r["px"])
    tot = sum(ours.values())
    ours = {k: 100 * v / tot for k, v in ours.items()}

    ck2 = defaultdict(float)
    for r in read_csv(FID / "terrain_classes.csv"):
        if r["set"] != "ck2_faerun":
            continue
        key = CK2_CAT_TO_CK3.get(r["ck2_type"])
        if key:
            ck2[key] += float(r["land_pct"])

    van = {r["terrain"]: float(r["px_share_pct"]) for r in read_csv(FID / "hf_by_terrain.csv")}
    vtot = sum(van.values())
    van = {k: 100 * v / vtot for k, v in van.items()}

    # the name is the tiebreak: without it the tied-at-zero keys come out in
    # set-iteration order, which PYTHONHASHSEED randomises, and the figure was
    # a different PNG on every run (found by lane `relief-report`).
    keys = sorted(set(ours) | set(ck2) | set(van),
                  key=lambda k: (-ours.get(k, 0), k))
    y = np.arange(len(keys))
    fig, ax = plt.subplots(figsize=(8.6, 5.2), dpi=120)
    ax.barh(y + 0.27, [ck2.get(k, 0) for k in keys], 0.26, color=C_CK2,
            label="CK2 terrain.bmp indices alone (before the trees.bmp → forest promotion)")
    ax.barh(y, [ours.get(k, 0) for k in keys], 0.26, color=C_OURS,
            label="ours, read back out of the shipped detail_index.tga")
    ax.barh(y - 0.27, [van.get(k, 0) for k in keys], 0.26, color=C_VANILLA,
            label="vanilla CK3's own land share")
    ax.set_yticks(y)
    ax.set_yticklabels(keys)
    ax.invert_yaxis()
    ax.set_xlabel("share of painted land area (%)")
    ax.set_title("Terrain-class composition: CK2's, not vanilla's")
    ax.grid(True, axis="x", alpha=0.22)
    ax.legend(fontsize=7.5, loc="lower right")
    fig.tight_layout()
    fig.savefig(OUT / "fig5_composition.png")
    plt.close(fig)
    return "fig5_composition.png"


def fig_hf_targets(recompute: bool) -> str:
    tgt = {r["terrain"]: float(r["hf_rms_levels"]) for r in read_csv(FID / "hf_by_terrain.csv")}
    ach = [r for r in cached("hf_achieved.csv", _HF_FIELDS, m_hf_achieved,
                             recompute)
           if r["terrain"] in tgt and r["achieved_interior"]]
    keys = [r["terrain"] for r in sorted(ach, key=lambda r: tgt.get(r["terrain"], 0))]
    a = {r["terrain"]: r for r in ach}
    y = np.arange(len(keys))
    fig, ax = plt.subplots(figsize=(8.6, 4.8), dpi=120)
    ax.barh(y + 0.26, [tgt[k] for k in keys], 0.25, color=C_VANILLA,
            label="vanilla target (hf_by_terrain.csv)")
    ax.barh(y, [float(a[k]["achieved_interior"]) for k in keys], 0.25, color=C_OURS,
            label="ours, interior land (> 20 px from any coast)")
    ax.barh(y - 0.26, [float(a[k]["achieved_all_land"]) for k in keys], 0.25,
            color=C_BEFORE,
            label="ours, all land (in build 8 the coast step inflated this by up to 1.5×)")
    ax.set_yticks(y)
    ax.set_yticklabels(keys)
    ax.set_xlabel("high-frequency RMS (16-bit levels, detail below ~6 km)")
    lo = min(tgt[k] for k in keys)
    hi = max(tgt[k] for k in keys)
    ax.set_title("The calibration table the detail pass obeys\n"
                 f"(vanilla spans {lo:.0f} to {hi:.0f} on the classes Faerûn paints —\n"
                 "one global noise amplitude would be wrong for all of them)")
    ax.grid(True, axis="x", alpha=0.22)
    ax.legend(fontsize=8, loc="lower right")
    fig.tight_layout()
    fig.savefig(OUT / "fig1_hf_targets.png")
    plt.close(fig)
    return "fig1_hf_targets.png"


def fig_trees(recompute: bool) -> str:
    rows = cached("tree_counts.csv", ["file", "ours", "vanilla"],
                  m_tree_counts, recompute)
    rows = [r for r in rows if int(r["ours"]) or int(r["vanilla"])]
    rows.sort(key=lambda r: -int(r["ours"]))
    names = [r["file"].replace("_generator", "").replace(".txt", "") for r in rows]
    y = np.arange(len(rows))
    ours_total = sum(int(r["ours"]) for r in rows)
    van_total = sum(int(r["vanilla"]) for r in rows)
    fig, ax = plt.subplots(figsize=(8.6, 5.6), dpi=120)
    ax.barh(y + 0.2, [int(r["vanilla"]) for r in rows], 0.38, color=C_VANILLA,
            label=f"vanilla CK3, its own 9216×4608 canvas ({van_total:,})")
    ax.barh(y - 0.2, [int(r["ours"]) for r in rows], 0.38, color=C_OURS,
            label=f"ours, 8320×6784 canvas ({ours_total:,} of a {TREE_TARGET:,} target)")
    ax.set_yticks(y)
    ax.set_yticklabels(names, fontsize=7.5)
    ax.invert_yaxis()
    ax.set_xlabel("placed instances (sum of every count= in the generator file)")
    ax.set_title("Tree scatter: vanilla's density (0.012931 instances/px), "
                 "CK2's forest mask,\nour own terrain classes choosing the mesh")
    ax.grid(True, axis="x", alpha=0.22)
    ax.legend(fontsize=8, loc="lower right")
    fig.tight_layout()
    fig.savefig(OUT / "fig7_trees.png")
    plt.close(fig)
    return "fig7_trees.png"


# ===================================================================== §7
# Side by side: Thay's terraces, multi-scale panels, per-material composition.
# Everything below was added by lane `relief-report`; figures 1-7 above are
# untouched.

#: CK2 px -> canvas px.  The converter logs this triple every run
#: (`scale factor 1.954310 -> canvas 8320x6784 (scaled 8005x6504, offset
#: 157,140)`), and SCALED_W/H, OFFSET_X/Y above are the same line.
CK2_SCALE = SCALED_W / 4096.0
#: one 8-bit source level through the transfer curve, in 16-bit levels.
#: (49205 - 4883) / (255 - 95) = 277.0125.  Every land pixel of the plain
#: rescale is an integer multiple of this above the water pin, so a
#: pixel-to-pixel step of exactly one riser is quantisation and nothing else.
RISER = (MAX_LEVEL - WATER_LEVEL) / (255.0 - CK2_SEA_LEVEL)
#: Pass 1 of `ck2ck3.map.heightmap_detail`, read out of the shipped config
#: rather than hard-coded, because build 9 replaced the Gaussian with a
#: cliff-aware Perona-Malik diffusion (`docs/step_map_heightmap.md` §2b):
#: `heightmap_detail_deterrace_mode = "cliff_aware"`, sigma 2.2 px, flux
#: half-width 415.5 levels.  The build-8 edition of this report measured
#: `"gaussian"` at sigma 1.6.
def _detail_cfg():
    import tomllib
    raw = tomllib.loads(_need(CONFIG, "converter config").read_text("utf-8"))
    from ck2ck3.map.config import heightmap_detail_config
    return heightmap_detail_config(raw.get("map", {}))


def deterrace(plain: np.ndarray, cfg) -> np.ndarray:
    """Pass 1 alone, exactly as `heightmap_detail.apply` runs it."""
    if cfg.deterrace_mode == "cliff_aware":
        from ck2ck3.map.heightmap_erosion import deterrace_cliff_aware
        return deterrace_cliff_aware(plain, cfg.deterrace_sigma_px,
                                     cfg.cliff_step_levels)
    from scipy.ndimage import gaussian_filter
    return gaussian_filter(plain, cfg.deterrace_sigma_px, mode="nearest")

#: common/defines: WORLD_EXTENTS_Y.  A 16-bit level is `level/65535*extents_y`
#: **game units** of height, and one provinces.png pixel is one game unit of
#: ground, so a heightmap at resolution_factor 2 covers half a game unit per
#: pixel.  Hillshading both maps in game units is the only like-for-like
#: comparison: it is the slope the renderer itself sees.
EXTENTS_Y_OURS, EXTENTS_Y_VANILLA = 51.0, 50.0
UNITS_PER_HM_PX_OURS, UNITS_PER_HM_PX_VANILLA = 1.0, 0.5
HILLSHADE_VE = 3.0
HILLSHADE_AZ, HILLSHADE_ALT = 315.0, 35.0

#: The vanilla control region for every side-by-side: the Norwegian coast,
#: heightmap px (2x), i.e. provinces px (1600, 550).  Chosen for the brief's
#: own reason -- coast plus mountains in one frame, the closest vanilla analogue
#: of the Sword Coast and of Thay's scarps.  Recorded in panel_extents.csv.
VANILLA_CTRL_HM = (3200, 1100)
#: Faerûn centres, canvas px.  Waterdeep's own province centroid is
#: (2345, 6784-5724=1060) (docs/step_map_assets.md §5b); the Sword Coast crop
#: is docs/map_fidelity.md §4.2; the continent centre is the painted-extent
#: rectangle's own middle (OFFSET + SCALED/2).
WATERDEEP_CANVAS = (2345, 1060)
SWORD_COAST_CANVAS = (SWORD_COAST[1] + SWORD_COAST[2] // 2,
                      SWORD_COAST[0] + SWORD_COAST[2] // 2)
CONTINENT_CANVAS = (OFFSET_X + SCALED_W // 2, OFFSET_Y + SCALED_H // 2)

LANDED_TITLES = ROOT / "Faerun/Faerun/common/landed_titles/01_landed_titles.txt"


# ------------------------------------------------------- Thay, from CK2 data
def _strip_comment(line: str) -> str:
    i = line.find("#")
    return line if i < 0 else line[:i]


def thay_counties_from_landed_titles() -> list[tuple[str, int]]:
    """`(county title, CK2 province id)` for every county under `k_thay`.

    Faerûn writes the province id as a trailing comment on the county's own
    line (`c_thaymount = { # 1426`), which is also how `capital = 1426 #
    c_thaymount` is read elsewhere in this repo.  The file is Windows-1252
    (CLAUDE.md), so it is decoded as cp1252, not utf-8.
    """
    lines = _need(LANDED_TITLES, "CK2 landed_titles").read_text(
        encoding="cp1252", errors="replace").splitlines()
    start = next(i for i, l in enumerate(lines)
                 if re.match(r"^\s*k_thay\s*=\s*\{", l))
    depth, out = 0, []
    for line in lines[start:]:
        bare = _strip_comment(line)
        m = re.match(r"^\s*(c_\w+)\s*=\s*\{\s*#\s*(\d+)", line)
        if m and depth >= 1:
            out.append((m.group(1), int(m.group(2))))
        depth += bare.count("{") - bare.count("}")
        if depth <= 0:
            break
    if not out:
        raise SystemExit("no counties found under k_thay")
    return out


def read_ck2_definition() -> dict[int, tuple[int, int, int]]:
    rows = {}
    with _need(CK2_MAP / "definition.csv", "CK2 definition.csv").open(
            encoding="cp1252", errors="replace") as f:
        for line in f:
            p = line.strip().split(";")
            if len(p) >= 4 and p[0].isdigit():
                rows[int(p[0])] = (int(p[1]), int(p[2]), int(p[3]))
    return rows


def m_thay_counties():
    """Every Thayan county's pixel footprint on the CK2 `provinces.bmp`."""
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None
    counties = thay_counties_from_landed_titles()
    defs = read_ck2_definition()
    with Image.open(_need(CK2_MAP / "provinces.bmp", "CK2 provinces.bmp")) as im:
        prov = np.asarray(im.convert("RGB"))
    key = ((prov[:, :, 0].astype(np.uint32) << 16)
           | (prov[:, :, 1].astype(np.uint32) << 8) | prov[:, :, 2])
    rows, allmask = [], np.zeros(key.shape, bool)
    for title, pid in counties:
        rgb = defs.get(pid)
        if rgb is None:
            rows.append({"county": title, "province_id": pid, "r": "", "g": "",
                         "b": "", "px": 0, "ck2_x0": "", "ck2_x1": "",
                         "ck2_y0": "", "ck2_y1": ""})
            continue
        m = key == ((rgb[0] << 16) | (rgb[1] << 8) | rgb[2])
        allmask |= m
        ys, xs = np.nonzero(m)
        rows.append({"county": title, "province_id": pid, "r": rgb[0],
                     "g": rgb[1], "b": rgb[2], "px": int(m.sum()),
                     "ck2_x0": int(xs.min()), "ck2_x1": int(xs.max()),
                     "ck2_y0": int(ys.min()), "ck2_y1": int(ys.max())})
    ys, xs = np.nonzero(allmask)
    rows.append({"county": "(all k_thay)", "province_id": -1, "r": "", "g": "",
                 "b": "", "px": int(allmask.sum()),
                 "ck2_x0": int(xs.min()), "ck2_x1": int(xs.max()),
                 "ck2_y0": int(ys.min()), "ck2_y1": int(ys.max())})
    return rows


_THAY_FIELDS = ["county", "province_id", "r", "g", "b", "px",
                "ck2_x0", "ck2_x1", "ck2_y0", "ck2_y1"]


def thay_window(recompute: bool = False, margin_px: int = 40):
    """`(x0, x1, y0, y1)` canvas rectangle covering every Thayan county."""
    rows = cached("thay_counties.csv", _THAY_FIELDS, m_thay_counties, recompute)
    r = next(r for r in rows if r["county"] == "(all k_thay)")
    x0 = int(OFFSET_X + int(r["ck2_x0"]) * CK2_SCALE) - margin_px
    x1 = int(OFFSET_X + int(r["ck2_x1"]) * CK2_SCALE) + margin_px
    y0 = int(OFFSET_Y + int(r["ck2_y0"]) * CK2_SCALE) - margin_px
    y1 = int(OFFSET_Y + int(r["ck2_y1"]) * CK2_SCALE) + margin_px
    return x0, x1, y0, y1


# --------------------------------------------- the four elevation stages
_STAGES: dict[bool, tuple] = {}


def thay_stages(recompute: bool = False):
    """`(ck2_src, plain, deterraced, shipped, land, win)` over the Thay window.

    * `ck2_src`   the CK2 `topology.bmp` bytes themselves, native 2.90 km/px,
                  cropped to the same ground -- the only array here that is
                  not on our canvas.
    * `plain`     `ck2ck3.map.heightmap`'s own output (plain_rescale_canvas).
    * `deterraced` pass 1 of `ck2ck3.map.heightmap_detail` alone, in whatever
                  mode `configs/faerun.toml` selects (build 12: cliff-aware
                  Perona-Malik, sigma 2.2 px), computed on a padded crop so
                  the filter sees the same neighbourhood it would on the full
                  canvas.
    * `shipped`   the reference run's `map_data/heightmap.png`.
    """
    if recompute in _STAGES:
        return _STAGES[recompute]
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None
    print("measuring the Thay window ...", flush=True)
    cfg = _detail_cfg()
    x0, x1, y0, y1 = thay_window(recompute)
    pad = int(np.ceil(6 * cfg.deterrace_sigma_px)) + 4
    plain_full = plain_rescale_canvas()
    P = plain_full[y0 - pad:y1 + pad, x0 - pad:x1 + pad].astype(np.float32)
    del plain_full
    D = deterrace(P, cfg)[pad:-pad, pad:-pad]
    P = P[pad:-pad, pad:-pad]
    S = load_heightmap(MOD / "map_data/heightmap.png")[y0:y1, x0:x1].astype(np.float32)
    land = S > WATER_LEVEL
    with Image.open(_need(CK2_MAP / "topology.bmp", "CK2 topology.bmp")) as im:
        src8 = np.asarray(im.convert("L"))
    cx0, cx1 = int((x0 - OFFSET_X) / CK2_SCALE), int((x1 - OFFSET_X) / CK2_SCALE)
    cy0, cy1 = int((y0 - OFFSET_Y) / CK2_SCALE), int((y1 - OFFSET_Y) / CK2_SCALE)
    from ck2ck3.map import heightmap as hm
    from ck2ck3.map.config import HeightmapConfig
    lut = hm.build_curve(HeightmapConfig(ck2_sea_level=CK2_SEA_LEVEL,
                                         ck3_water_level=WATER_LEVEL,
                                         ck3_max_level=MAX_LEVEL))
    src = lut[src8[max(cy0, 0):cy1, max(cx0, 0):cx1]].astype(np.float32)
    _STAGES[recompute] = (src, P, D, S, land, (x0, x1, y0, y1))
    return _STAGES[recompute]


def _edge_steps(a, land):
    """|Δ| in riser units over every land-to-land 4-neighbour edge."""
    dh = np.abs(np.diff(a, axis=1))[land[:, :-1] & land[:, 1:]]
    dv = np.abs(np.diff(a, axis=0))[land[:-1, :] & land[1:, :]]
    return np.concatenate([dh, dv]) / RISER


_STEP_CLASSES = [(-0.01, 0.01, "flat (0)"), (0.01, 0.5, "sub-riser"),
                 (0.5, 1.5, "1 riser (quantisation)"), (1.5, 2.5, "2 risers"),
                 (2.5, 4.5, "3-4 risers"), (4.5, 1e9, ">=5 risers")]


def m_thay_steps():
    src, P, D, S, land, _ = thay_stages()
    rows = []
    for stage, a in (("ck2_plain_rescale", P), ("after_deterrace", D),
                     ("shipped", S)):
        s = _edge_steps(a, land)
        for lo, hi, lbl in _STEP_CLASSES:
            n = int(((s > lo) & (s <= hi)).sum())
            rows.append({"stage": stage, "class": lbl, "edges": n,
                         "pct": round(100.0 * n / s.size, 3),
                         "n_edges_total": int(s.size),
                         "mean_risers": round(float(s.mean()), 4),
                         "p99_risers": round(float(np.percentile(s, 99)), 3),
                         "max_risers": round(float(s.max()), 3)})
    return rows


_CLIFF_LAGS = (1, 2, 3, 4, 6, 8, 12)


def m_thay_cliffs():
    """How much of a real cliff survives the de-terrace Gaussian.

    A cliff is defined on the **plain rescale**, before anything has touched
    it: a horizontal land-to-land edge whose one-pixel step is at least
    `thr` risers.  One riser is pure quantisation, so >= 2 means the 8-bit
    source itself falls by two or more levels inside 1.48 km -- a real scarp.
    For each such edge the signed drop is measured over a growing baseline
    `2*lag - 1` px wide, oriented by the plain rescale's own sign, so
    zero-mean synthesis noise averages out instead of inflating the number.
    """
    src, P, D, S, land, _ = thay_stages()
    dx = np.diff(P, axis=1)
    ok = land[:, :-1] & land[:, 1:]
    rows = []
    for thr in (2, 4, 6):
        m = (np.abs(dx) >= (thr - 0.5) * RISER) & ok
        ys, xs = np.nonzero(m)
        keep = (xs >= max(_CLIFF_LAGS) + 2) & (xs < P.shape[1] - max(_CLIFF_LAGS) - 2)
        ys, xs = ys[keep], xs[keep]
        sgn = np.sign(dx[ys, xs])
        for lag in _CLIFF_LAGS:
            vals = {}
            for name, a in (("plain", P), ("deterrace", D), ("shipped", S)):
                vals[name] = float((sgn * (a[ys, xs + lag]
                                           - a[ys, xs + 1 - lag])).mean()) / RISER
            rows.append({
                "cliff_threshold_risers": thr, "n_edges": int(ys.size),
                "lag_px": lag, "baseline_km": round((2 * lag - 1) * KM_PX_OURS, 2),
                "drop_plain_risers": round(vals["plain"], 3),
                "drop_deterrace_risers": round(vals["deterrace"], 3),
                "drop_shipped_risers": round(vals["shipped"], 3),
                "kept_deterrace_pct": round(100 * vals["deterrace"] / vals["plain"], 1),
                "kept_shipped_pct": round(100 * vals["shipped"] / vals["plain"], 1),
            })
    return rows


def m_thay_transects():
    """Two canvas rows straight across the Thayan plateau.

    Row A is the row carrying the window's single largest plain-rescale step
    (the western scarp below Thaymount); row B is 120 px south of it.  Both
    are picked by the data, not by eye, so the figure cannot be cherry-picked.
    """
    src, P, D, S, land, (x0, x1, y0, y1) = thay_stages()
    mag = np.abs(np.diff(P, axis=1)) * (land[:, :-1] & land[:, 1:])
    rowA = int(np.argmax(mag.max(axis=1)))
    rowB = min(rowA + 120, P.shape[0] - 1)
    # `src` was cropped at the CK2-grid origin of the same window, so the
    # canvas column has to come back to CK2 coordinates *relative to that
    # origin*, not absolutely.
    cx0 = max(int((x0 - OFFSET_X) / CK2_SCALE), 0)
    cy0 = max(int((y0 - OFFSET_Y) / CK2_SCALE), 0)
    rows = []
    for lbl, r in (("A", rowA), ("B", rowB)):
        cy = int(round(((y0 + r) - OFFSET_Y) / CK2_SCALE)) - cy0
        for i in range(P.shape[1]):
            cx = int(round(((x0 + i) - OFFSET_X) / CK2_SCALE)) - cx0
            rows.append({
                "transect": lbl, "canvas_row": y0 + r, "canvas_col": x0 + i,
                "ck2_source": int(src[np.clip(cy, 0, src.shape[0] - 1),
                                      np.clip(cx, 0, src.shape[1] - 1)]),
                "plain": int(P[r, i]), "deterrace": int(round(D[r, i])),
                "shipped": int(S[r, i]), "land": int(land[r, i]),
            })
    return rows


_BAND_SIGMAS = (0.8, 1.6, 3.2, 6.4, 12.8, 25.6)


def m_thay_bands():
    """Band-passed RMS over Thay's land, plus vanilla's own control region.

    Difference-of-Gaussians bands, so a band's label is the wavelength range
    it passes.  The vanilla column is the Norwegian coast control at the same
    **kilometre** bands (its heightmap is 2x, so its sigmas are doubled), and
    is the only honest yardstick for "is our detail the right size".
    """
    from scipy.ndimage import gaussian_filter
    src, P, D, S, land, _ = thay_stages()
    core = np.zeros_like(land)
    core[40:-40, 40:-40] = True
    m = land & core
    van, vland = _vanilla_control_patch()
    rows = []
    for i in range(len(_BAND_SIGMAS) - 1):
        s1, s2 = _BAND_SIGMAS[i], _BAND_SIGMAS[i + 1]
        row = {"band_km_lo": round(s1 * KM_PX_OURS * 2, 2),
               "band_km_hi": round(s2 * KM_PX_OURS * 2, 2)}
        for name, a in (("plain", P), ("deterrace", D), ("shipped", S)):
            b = gaussian_filter(a, s1) - gaussian_filter(a, s2)
            row[f"rms_{name}"] = round(float(b[m].std()), 1)
        vs1 = s1 * KM_PX_OURS / KM_PX_VANILLA
        vs2 = s2 * KM_PX_OURS / KM_PX_VANILLA
        b = gaussian_filter(van, vs1) - gaussian_filter(van, vs2)
        row["rms_vanilla_norway"] = round(float(b[vland].std()), 1)
        rows.append(row)
    return rows


def m_clamp_floor():
    """Land the detail pass sank below the water level, map-wide.

    `heightmap_detail` guarantees every land pixel ends strictly above
    `water_level`, and it enforces that by clamping.  A pixel sitting at
    exactly `water_level + 1` is therefore a pixel the synthesis pushed under
    and the invariant pulled back -- dead flat, with whatever elevation the
    plain rescale gave it thrown away.  Measured against the plain rescale,
    on the full canvas, not a crop.
    """
    from scipy.ndimage import distance_transform_edt
    plain = plain_rescale_canvas()
    ship = load_heightmap(MOD / "map_data/heightmap.png")
    land = ship > WATER_LEVEL
    clamp = ship == WATER_LEVEL + 1
    n, c = int(land.sum()), int(clamp.sum())
    dist = distance_transform_edt(land)[clamp]
    lost = plain[clamp].astype(np.float64) - (WATER_LEVEL + 1)
    low = land & (plain < 8000)
    return [{
        "land_px": n, "clamp_floor_px": c,
        "clamp_pct_of_land": round(100.0 * c / n, 3),
        "dist_to_water_p50_px": round(float(np.median(dist)), 1),
        "dist_to_water_p90_px": round(float(np.percentile(dist, 90)), 1),
        "dist_to_water_max_px": round(float(dist.max()), 1),
        "within_6px_of_water_pct": round(100.0 * float((dist <= 6).mean()), 1),
        "plain_height_there_p50": round(float(np.median(plain[clamp])), 0),
        "plain_height_there_p90": round(float(np.percentile(plain[clamp], 90)), 0),
        "mean_levels_lost": round(float(lost.mean()), 0),
        "low_land_px_plain_under_8000": int(low.sum()),
        "low_land_clamped_pct": round(100.0 * float((clamp & low).sum()
                                                    / max(int(low.sum()), 1)), 1),
    }]


_CLAMP_FIELDS = ["land_px", "clamp_floor_px", "clamp_pct_of_land",
                 "dist_to_water_p50_px", "dist_to_water_p90_px",
                 "dist_to_water_max_px", "within_6px_of_water_pct",
                 "plain_height_there_p50", "plain_height_there_p90",
                 "mean_levels_lost", "low_land_px_plain_under_8000",
                 "low_land_clamped_pct"]


def _vanilla_control_patch(km: float = 400.0):
    """The Norwegian-coast control crop of vanilla's heightmap, plus its land."""
    cx, cy = VANILLA_CTRL_HM
    half = int(km / KM_PX_VANILLA / 2)
    van = load_heightmap(GAME / "map_data/heightmap.png")[
        cy - half:cy + half, cx - half:cx + half].astype(np.float32)
    return van, van > VANILLA_WATER


# ------------------------------------------------------------- rendering
def hillshade(z, *, units_per_px: float, extents_y: float,
              ve: float = HILLSHADE_VE) -> np.ndarray:
    """Standard hillshade in **game units**, so two maps are comparable.

    A 16-bit level is `level/65535*WORLD_EXTENTS_Y` game units of height and
    one provinces.png pixel is one game unit of ground, so `units_per_px` is
    1.0 for our 1x heightmap and 0.5 for vanilla's 2x one.  Feeding both the
    same vertical exaggeration then compares the slope the renderer sees, not
    an artefact of how many pixels each map spends on a kilometre.
    """
    zu = z.astype(np.float32) / 65535.0 * extents_y * ve
    gy, gx = np.gradient(zu, units_per_px)
    slope = np.arctan(np.hypot(gx, gy))
    aspect = np.arctan2(-gx, gy)
    az, alt = np.radians(HILLSHADE_AZ), np.radians(HILLSHADE_ALT)
    v = (np.sin(alt) * np.cos(slope)
         + np.cos(alt) * np.sin(slope) * np.cos(az - aspect))
    return np.clip(v, 0.0, 1.0)


#: land the detail pass drove below the water level and the invariant clamped
#: back to `water_level + 1` -- dead flat ground, drawn in this colour so it
#: cannot be mistaken for a plain (see `clamp_floor.csv`).
CLAMP_COLOUR = (0.85, 0.30, 0.55)


def shade_rgb(z, land, *, units_per_px, extents_y, clamp=None) -> np.ndarray:
    """Hillshade as RGB with water drawn flat blue, so coastlines read."""
    v = hillshade(z, units_per_px=units_per_px, extents_y=extents_y)
    rgb = np.repeat((0.25 + 0.75 * v)[:, :, None], 3, axis=2)
    rgb[~land] = (0.36, 0.46, 0.58)
    if clamp is not None:
        rgb[clamp] = CLAMP_COLOUR
    return np.clip(rgb, 0, 1)


#: The material tints are vanilla's own measured means and they are nearly
#: neutral by design (R 115-154, G 114-142, B 96-140 -- §4), so a literal
#: rendering of them is 100 shades of grey.  Every paint panel therefore
#: pushes each tint away from the grey point by this factor.  It is a display
#: gain and nothing else: no hue is invented, the ordering and the ratios
#: between materials are vanilla's, and the same gain is applied to all three
#: columns.
TINT_GAIN = 7.0
TINT_GREY = 128.0


def tint_lut() -> np.ndarray:
    """`(256, 3)` float LUT: material ordinal -> boosted vanilla tint.

    `docs/evidence/vanilla_colormap_tints.csv` is keyed by material *name*
    (`scripts/measure_vanilla_colormap_tints.py`); the ordinals are vanilla's
    own declaration order in `materials.settings`, the same numbering both
    `detail_index.tga` files use.
    """
    from ck2ck3.map.terrain_paint import material_ordinals
    ords_ = material_ordinals(_need(GAME / "gfx/map/terrain/materials.settings",
                                    "vanilla materials.settings"))
    lut = np.full((256, 3), TINT_GREY, dtype=np.float32)
    for r in read_csv(EV / "vanilla_colormap_tints.csv"):
        o = ords_.get(r["material_name"])
        if o is not None and 0 <= o < 256:
            lut[o] = (float(r["mean_r"]), float(r["mean_g"]), float(r["mean_b"]))
    return lut


def _boost(rgb: np.ndarray) -> np.ndarray:
    return np.clip((TINT_GREY + (rgb - TINT_GREY) * TINT_GAIN) / 255.0, 0, 1)


def paint_rgb(idx4: np.ndarray, int4: np.ndarray, lut: np.ndarray,
              land: np.ndarray) -> np.ndarray:
    """Blend the four `detail_index` materials by their `detail_intensity`."""
    w = int4.astype(np.float32)
    tot = np.maximum(w.sum(axis=2, keepdims=True), 1e-6)
    mix = (lut[idx4] * w[:, :, :, None]).sum(axis=2) / tot
    rgb = _boost(mix)
    rgb[~land] = (0.36, 0.46, 0.58)
    return rgb


def ck2_paint_rgb(cat_codes: np.ndarray, names: list[str], lut: np.ndarray,
                  land: np.ndarray) -> np.ndarray:
    """The CK2 source's own terrain classes, in the same tint palette.

    CK2 index -> CK2 category (`map/terrain.txt`) -> CK3 terrain key
    (`CK2_TO_CK3_TERRAIN`) -> primary material (`mappings/terrain_paint.csv`)
    -> vanilla's measured tint.  Exactly the chain the converter walks, minus
    every micro pass, which is what "CK2 source, rescaled only" means.
    """
    from ck2ck3.map.terrain import CK2_TO_CK3_TERRAIN
    from ck2ck3.map.terrain_paint import material_ordinals, read_material_map
    ords_ = material_ordinals(GAME / "gfx/map/terrain/materials.settings")
    mats = read_material_map(ROOT / "mappings/terrain_paint.csv")
    per_code = np.full((len(names), 3), TINT_GREY, dtype=np.float32)
    for i, cat in enumerate(names):
        key = CK2_TO_CK3_TERRAIN.get(cat)
        pair = mats.get(key) if key else None
        if pair:
            o = ords_.get(pair[0])
            if o is not None:
                per_code[i] = lut[o]
    rgb = _boost(per_code[cat_codes])
    rgb[~land] = (0.36, 0.46, 0.58)
    return rgb


def ck2_terrain_codes():
    """`(codes, names, land)` on the CK2 source grid, trees promotion included."""
    from PIL import Image
    from ck2ck3.map.ck2read import read_terrain_texture_map
    from ck2ck3.map import terrain as tr
    Image.MAX_IMAGE_PIXELS = None
    tex = read_terrain_texture_map(_need(CK2_MAP / "terrain.txt", "CK2 terrain.txt"))
    with Image.open(_need(CK2_MAP / "terrain.bmp", "CK2 terrain.bmp")) as im:
        idx = np.asarray(im)
    with Image.open(_need(CK2_MAP / "trees.bmp", "CK2 trees.bmp")) as im:
        trees = np.asarray(im)
    cats = tr.ck2_category_grid(idx, tex, trees=trees, tree_indices=tuple(range(1, 256)))
    codes, names = tr.category_codes(cats)
    with Image.open(_need(CK2_MAP / "topology.bmp", "CK2 topology.bmp")) as im:
        land = np.asarray(im.convert("L")) > CK2_SEA_LEVEL
    return codes, names, land


def resize_panel(rgb: np.ndarray, side: int) -> np.ndarray:
    """Fit a panel to `side` px.  Upsample nearest (so the source's own
    resolution stays visible), downsample by area (so it is not aliased)."""
    from PIL import Image
    im = Image.fromarray((np.clip(rgb, 0, 1) * 255).astype(np.uint8))
    mode = Image.NEAREST if im.size[0] < side else Image.BOX
    return np.asarray(im.resize((side, side), mode))


def crop_c(arr, cx, cy, half):
    y0, y1 = max(cy - half, 0), min(cy + half, arr.shape[0])
    x0, x1 = max(cx - half, 0), min(cx + half, arr.shape[1])
    return arr[y0:y1, x0:x1]




# ------------------------------------------------- per-material composition
#: Material families, matched against the material *name* in declaration
#: order (first rule wins).  A family is the level at which a geographic
#: argument can be made at all -- "vanilla has the Sahara" is a statement
#: about arid ground, not about `gen_desert_lowlands` specifically.  Arid
#: **mountains** count as mountains, not as desert: `gen_desert_mountain` is
#: relief that happens to be dry.
MATERIAL_FAMILIES = [
    ("farmland", ("farm",)),
    ("snow & ice", ("snow", "ice", "glacier")),
    ("mountain", ("mountain",)),
    ("hills", ("hills",)),
    ("forest & jungle", ("forest", "jungle", "woods")),
    ("wetlands", ("wetlands", "mud", "floodplain", "marsh")),
    ("beach & cliff", ("beach", "coastline")),
    ("desert & drylands", ("desert", "dryland", "oasis")),
    ("steppe", ("steppe",)),
    ("plains & lowlands", ("plains", "lowland", "grass", "soil", "dirt")),
]
#: vanilla's regional / climate-zone material families.  `terrain_paint.csv`
#: excludes every one of them on purpose (a `gen_*` or `india_*` material is
#: named for a real-world region Faerûn does not have), so their whole share
#: is a mapping choice, not a geographic difference.
_REGIONAL_RE = re.compile(r"^(gen_|medi_|northern_|india_|central_|tropical)")


def material_family(name: str) -> str:
    for fam, keys in MATERIAL_FAMILIES:
        if any(k in name for k in keys):
            return fam
    return "other"


def _paint_pair(base: Path, hm: Path, water: int):
    """`(index, intensity, land)` of one map's paint, land at paint resolution."""
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None
    with Image.open(_need(base / "gfx/map/terrain/detail_index.tga",
                          f"{base.name} detail_index.tga")) as im:
        idx = np.asarray(im.convert("RGBA")).astype(np.int32)
    with Image.open(_need(base / "gfx/map/terrain/detail_intensity.tga",
                          f"{base.name} detail_intensity.tga")) as im:
        itn = np.asarray(im.convert("RGBA")).astype(np.float32)
    land = load_heightmap(hm) > water
    step = land.shape[0] // idx.shape[0]
    land = land[::step, ::step][:idx.shape[0], :idx.shape[1]]
    return idx, itn, land


def _material_stats(idx, itn, land):
    """Coverage / primary / presence / mean-weight per ordinal, plus blend stats."""
    n = int(land.sum())
    w = itn[land] / 255.0
    ii = idx[land]
    cov = np.zeros(256)
    pres = np.zeros(256)
    prim = np.zeros(256)
    for c in range(4):
        np.add.at(cov, ii[:, c], w[:, c])
        np.add.at(pres, ii[:, c], (w[:, c] > 0).astype(float))
    np.add.at(prim, ii[:, 0], 1.0)
    norm = w / np.maximum(w.sum(axis=1, keepdims=True), 1e-9)
    ent = float(-(np.where(norm > 0, norm * np.log2(np.maximum(norm, 1e-12)), 0)
                  ).sum(axis=1).mean())
    blend = {"land_px": n, "blend_entropy_bits": round(ent, 4),
             "mean_nonzero_channels": round(float((w > 0).sum(axis=1).mean()), 4),
             "mean_primary_weight": round(float(norm[:, 0].mean()), 4),
             "materials_used": int((cov > 0).sum())}
    with np.errstate(invalid="ignore", divide="ignore"):
        mean_w = np.where(pres > 0, cov / np.maximum(pres, 1), 0.0)
    return (cov / n * 100, prim / n * 100, pres / n * 100, mean_w), blend


_BLEND: dict[str, dict] = {}


def m_material_share():
    from ck2ck3.map.terrain_paint import material_ordinals
    ords_ = material_ordinals(_need(GAME / "gfx/map/terrain/materials.settings",
                                    "vanilla materials.settings"))
    name = {v: k for k, v in ords_.items()}
    o, ob = _material_stats(*_paint_pair(MOD, MOD / "map_data/heightmap.png",
                                         WATER_LEVEL))
    v, vb = _material_stats(*_paint_pair(GAME, GAME / "map_data/heightmap.png",
                                         VANILLA_WATER))
    _BLEND["ours"], _BLEND["vanilla"] = ob, vb
    rows = []
    for i in range(256):
        if not (o[0][i] or v[0][i]):
            continue
        nm = name.get(i, f"ordinal_{i}")
        rows.append({
            "material": nm, "ordinal": i, "family": material_family(nm),
            "vanilla_regional": int(bool(_REGIONAL_RE.match(nm))),
            "ours_coverage_pct": round(o[0][i], 4),
            "vanilla_coverage_pct": round(v[0][i], 4),
            "ours_primary_pct": round(o[1][i], 4),
            "vanilla_primary_pct": round(v[1][i], 4),
            "ours_presence_pct": round(o[2][i], 4),
            "vanilla_presence_pct": round(v[2][i], 4),
            "ours_mean_weight_where_present": round(o[3][i], 4),
            "vanilla_mean_weight_where_present": round(v[3][i], 4),
        })
    return sorted(rows, key=lambda r: -(r["ours_coverage_pct"]
                                        + r["vanilla_coverage_pct"]))


_MATERIAL_FIELDS = ["material", "ordinal", "family", "vanilla_regional",
                    "ours_coverage_pct", "vanilla_coverage_pct",
                    "ours_primary_pct", "vanilla_primary_pct",
                    "ours_presence_pct", "vanilla_presence_pct",
                    "ours_mean_weight_where_present",
                    "vanilla_mean_weight_where_present"]


def m_paint_blend():
    if not _BLEND:
        m_material_share()
    return [dict(map=k, **v) for k, v in _BLEND.items()]


_BLEND_FIELDS = ["map", "land_px", "materials_used", "blend_entropy_bits",
                 "mean_nonzero_channels", "mean_primary_weight"]

#: The editorial half of figure 13, kept next to the numbers it explains.
#: `expected` is one of `geography` (the difference follows from Faerûn not
#: being Earth, and needs no fix), `mapping` (our own table produced it) or
#: `mixed`.
FAMILY_REASONS = {
    "desert & drylands": ("geography",
        "vanilla's land includes the Sahara, Arabia, Iran and the Thar; "
        "Faerûn's only true desert is Anauroch, with the Calim and Raurin "
        "fringes. A lower arid share is the correct answer, not a defect."),
    "forest & jungle": ("geography",
        "Faerûn is a forested continent (High Forest, Cormanthor, the "
        "Chondalwood) and `trees.bmp` promotes every wooded pixel to forest; "
        "vanilla's Europe/MENA sheet is largely cleared or arid."),
    "steppe": ("geography",
        "the Shaar, the Eastern Shaar and the Endless Wastes are a larger "
        "fraction of Faerûn than the Pontic steppe is of vanilla's map."),
    "plains & lowlands": ("mixed",
        "part geography (the Dalelands, the Vilhon Reach), part mapping: CK2 "
        "`pti` filler and unmapped indices both fall through to plains."),
    "hills": ("mixed",
        "Faerûn's CK2 palette has one hills index and uses it freely; vanilla "
        "splits the same ground between hills and its regional families."),
    "mountain": ("mixed",
        "vanilla carries the Alps, Caucasus, Zagros, Himalaya and Tibet; but "
        "we also fold CK2 `impassable_mountains` and `subterranean` into one "
        "key, so the shortfall is not purely geographic."),
    "snow & ice": ("geography",
        "CK2 `arctic` and `glacier` both fold into taiga, whose secondary is "
        "`snow`; the Spine of the World and the Great Glacier supply it."),
    "wetlands": ("geography",
        "the Marsh of Chelimber and the Farsea Marshes against vanilla's "
        "Pripet, Nile delta and Mesopotamia -- same order, small either way."),
    "farmland": ("geography", "both maps paint about 0.6 % farmland."),
    "beach & cliff": ("mapping",
        "NOT geography. Faerûn has more coastline per unit area than vanilla, "
        "yet we paint 0 % beach on land: `mappings/terrain_paint.csv` gives "
        "`sea`/`coastal_sea` a beach material but those pixels are under "
        "water, and no land key ever picks one. A missing shoreline material."),
    "other": ("mapping",
        "vanilla's leftovers are regional and rock materials our table never "
        "selects from."),
}


# --------------------------------------------------------------- figure 8
def fig_thay_relief(recompute: bool) -> str:
    src, P, D, S, land, (x0, x1, y0, y1) = thay_stages(recompute)
    rows = cached("thay_transects.csv",
                  ["transect", "canvas_row", "canvas_col", "ck2_source",
                   "plain", "deterrace", "shipped", "land"],
                  m_thay_transects, recompute)
    rowA = int(next(r for r in rows if r["transect"] == "A")["canvas_row"]) - y0
    magcol = int(np.argmax(np.abs(np.diff(P, axis=1))[rowA]))

    # the CK2 source panel is on its own 2.90 km/px grid; give it the same
    # ground by resampling nearest to the canvas rectangle (display only).
    from PIL import Image
    src_disp = np.asarray(Image.fromarray(src.astype(np.uint16)).resize(
        (P.shape[1], P.shape[0]), Image.NEAREST)).astype(np.float32)

    cfg = _detail_cfg()
    dt_label = ("Perona–Malik" if cfg.deterrace_mode == "cliff_aware"
                else "Gaussian")
    stages = [("CK2 topology.bmp\n(2.90 km/px, 8-bit)", src_disp),
              ("ours: plain rescale\n(the 277-level terraces)", P),
              (f"+ de-terrace only\n({dt_label} σ = {cfg.deterrace_sigma_px:.1f} px)", D),
              ("ours: shipped\n(all four detail passes)", S)]
    zoom_km = 120.0
    zh = int(zoom_km / KM_PX_OURS / 2)
    zy = int(np.clip(rowA, zh, P.shape[0] - zh))
    zx = int(np.clip(magcol, zh, P.shape[1] - zh))

    fig, axes = plt.subplots(2, 4, figsize=(13.2, 8.2), dpi=120)
    for c, (lbl, a) in enumerate(stages):
        for r, (sub, mask) in enumerate((
                (None, land),
                ((slice(zy - zh, zy + zh), slice(zx - zh, zx + zh)), None))):
            z = a if sub is None else a[sub]
            m = land if sub is None else land[sub]
            rgb = shade_rgb(z, m, units_per_px=UNITS_PER_HM_PX_OURS,
                            extents_y=EXTENTS_Y_OURS)
            ax = axes[r][c]
            ax.imshow(rgb, interpolation="nearest")
            ax.set_xticks([])
            ax.set_yticks([])
            if r == 0:
                ax.set_title(lbl, fontsize=8.5)
                ax.add_patch(plt.Rectangle((zx - zh, zy - zh), 2 * zh, 2 * zh,
                                           fill=False, ec=C_OURS, lw=1.2))
                ax.axhline(rowA, color="#f0c000", lw=0.8, ls="--")
            if c == 0:
                km = (P.shape[1] * KM_PX_OURS if r == 0 else zoom_km)
                ax.set_ylabel(f"{'Thay, all 33 counties' if r == 0 else 'the steepest scarp'}\n"
                              f"{km:.0f} km across", fontsize=8)
    fig.suptitle("Figure 8 — Thay's terraces through the pipeline. Same ground, same hillshade "
                 "(315°/35°, ×3 in game units).\nRow 2 is the red box: the single steepest "
                 "escarpment in the plain rescale. The dashed line is transect A.",
                 fontsize=9.5)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    fig.savefig(OUT / "fig8_thay_relief.png")
    plt.close(fig)
    return "fig8_thay_relief.png"


# --------------------------------------------------------------- figure 9
def fig_thay_transects(recompute: bool) -> str:
    rows = cached("thay_transects.csv",
                  ["transect", "canvas_row", "canvas_col", "ck2_source",
                   "plain", "deterrace", "shipped", "land"],
                  m_thay_transects, recompute)
    by = defaultdict(list)
    for r in rows:
        by[r["transect"]].append(r)

    cfg = _detail_cfg()
    dt = ("Perona–Malik" if cfg.deterrace_mode == "cliff_aware" else "Gaussian")
    series = (("ck2_source", "CK2 source through the transfer curve", C_CK2, ":", 1.3),
              ("plain", "ours, plain rescale", C_BEFORE, "-", 1.1),
              ("deterrace", f"+ de-terrace only ({dt} σ = {cfg.deterrace_sigma_px:.1f} px)",
               "#4f9d5d", "-", 1.3),
              ("shipped", "ours, shipped", C_OURS, "-", 1.0))

    fig = plt.figure(figsize=(11.0, 10.0), dpi=120)
    gs = fig.add_gridspec(3, 2, height_ratios=[1, 1, 1.1], hspace=0.42, wspace=0.2)
    axes = [fig.add_subplot(gs[0, :]), fig.add_subplot(gs[1, :])]

    def water_bands(ax, rs, x):
        wet = np.array([int(r["land"]) == 0 for r in rs])
        d = np.diff(wet.astype(int))
        starts = list(np.nonzero(d == 1)[0] + 1) + ([0] if wet[0] else [])
        ends = list(np.nonzero(d == -1)[0] + 1) + ([len(wet)] if wet[-1] else [])
        for a, b in zip(sorted(starts), sorted(ends)):
            ax.axvspan(x[a], x[min(b, len(x) - 1)], color="#2a6fb0", alpha=0.10, lw=0)

    for i, key in enumerate(("A", "B")):
        rs = by[key]
        x = np.array([int(r["canvas_col"]) for r in rs])
        ax = axes[i]
        water_bands(ax, rs, x)
        for col, lbl, c, ls, lw in series:
            ax.plot(x, [int(r[col]) for r in rs], ls, color=c, lw=lw, label=lbl)
        ax.axhline(WATER_LEVEL, color="#2a6fb0", lw=0.9, ls="--")
        ax.set_ylabel("16-bit height level")
        ax.set_title(f"transect {key} — canvas row {rs[0]['canvas_row']}, west→east "
                     f"across the Thayan plateau ({len(rs) * KM_PX_OURS:.0f} km; "
                     "blue bands are water province pixels)", fontsize=9)
        ax.grid(True, alpha=0.22)
        if i == 0:
            ax.legend(fontsize=8, loc="upper left", ncol=2)

    rs = by["A"]
    x = np.array([int(r["canvas_col"]) for r in rs])
    plain = np.array([int(r["plain"]) for r in rs])
    W = 52

    # left inset: the steepest one-pixel step on this row.
    j = int(np.argmax(np.abs(np.diff(plain))))
    # right inset: the flattest window that still carries at least three
    # risers -- i.e. the staircase itself, picked by the data.
    dry = np.array([int(r["land"]) == 1 for r in rs])
    span = np.array([plain[k:k + W].max() - plain[k:k + W].min()
                     for k in range(len(plain) - W)], dtype=float)
    allland = np.array([dry[k:k + W].all() for k in range(len(plain) - W)])
    ok = (span >= 3 * RISER) & allland
    if not ok.any():
        ok = allland
    k = int(np.argmin(np.where(ok, span, np.inf)))

    drop = abs(int(plain[j + 1]) - int(plain[j]))
    for col_i, (lo, hi, title) in enumerate((
            (max(j - W // 2, 0), min(j + W // 2 + 1, len(rs)),
             f"the steepest pixel step on this row: {drop} levels "
             f"({drop / RISER:.0f} risers) in 1.48 km"),
            (k, k + W,
             "the flattest 77 km of the same row: the staircase itself, "
             "277-level treads"))):
        ax = fig.add_subplot(gs[2, col_i])
        for col, lbl, c, ls, lw in series:
            ax.plot(x[lo:hi], [int(r[col]) for r in rs[lo:hi]], ls, color=c,
                    lw=1.5, marker="." if col != "ck2_source" else None, ms=3)
        ax.set_title(title, fontsize=8.5)
        ax.set_xlabel("canvas column (px)")
        if col_i == 0:
            ax.set_ylabel("16-bit height level")
        ax.grid(True, alpha=0.22)

    keeps = ("keeps the drop and the step"
             if cfg.deterrace_mode == "cliff_aware"
             else "blunts the one-pixel step but keeps the drop")
    fig.suptitle(f"Figure 9 — what the de-terrace pass ({dt} σ = "
                 f"{cfg.deterrace_sigma_px:.1f} px) does to a real cliff "
                 f"(left inset): it {keeps}.\n"
                 "What it does to a quantisation riser (right inset): it removes it "
                 "completely. The red curve's large excursions are the spectral fill — see "
                 "figure 10.", fontsize=9.5)
    # not tight_layout: the two insets live in a nested gridspec and matplotlib
    # warns that it cannot lay those out.  These margins are the same result.
    fig.subplots_adjust(top=0.90, bottom=0.06, left=0.075, right=0.975)
    fig.savefig(OUT / "fig9_thay_transects.png")
    plt.close(fig)
    return "fig9_thay_transects.png"


# -------------------------------------------------------------- figure 10
def fig_thay_steps(recompute: bool) -> str:
    steps = cached("thay_steps.csv",
                   ["stage", "class", "edges", "pct", "n_edges_total",
                    "mean_risers", "p99_risers", "max_risers"],
                   m_thay_steps, recompute)
    cliffs = cached("thay_cliffs.csv",
                    ["cliff_threshold_risers", "n_edges", "lag_px",
                     "baseline_km", "drop_plain_risers", "drop_deterrace_risers",
                     "drop_shipped_risers", "kept_deterrace_pct",
                     "kept_shipped_pct"],
                    m_thay_cliffs, recompute)

    bands = cached("thay_bands.csv",
                   ["band_km_lo", "band_km_hi", "rms_plain", "rms_deterrace",
                    "rms_shipped", "rms_vanilla_norway"],
                   m_thay_bands, recompute)

    classes = [c for _, _, c in _STEP_CLASSES]
    stages = [("ck2_plain_rescale", "plain rescale", C_BEFORE),
              ("after_deterrace", "+ de-terrace", "#4f9d5d"),
              ("shipped", "shipped", C_OURS)]
    fig, (ax, bx, cx) = plt.subplots(1, 3, figsize=(16.6, 5.0), dpi=120,
                                     gridspec_kw={"width_ratios": [1.15, 1, 1]})
    y = np.arange(len(classes))
    for k, (stage, lbl, col) in enumerate(stages):
        vals = [next(float(r["pct"]) for r in steps
                     if r["stage"] == stage and r["class"] == c) for c in classes]
        tot = next(int(r["n_edges_total"]) for r in steps if r["stage"] == stage)
        ax.barh(y + (1 - k) * 0.27, vals, 0.26, color=col,
                label=f"{lbl} (n = {tot:,} edges)")
    ax.set_yticks(y)
    ax.set_yticklabels(classes)
    ax.invert_yaxis()
    ax.set_xlabel("share of land-to-land pixel edges in the Thay window (%)")
    ax.set_title("Step heights across adjacent pixels\n"
                 "one riser = 277 levels = one 8-bit source level", fontsize=9.5)
    ax.grid(True, axis="x", alpha=0.22)
    ax.legend(fontsize=8, loc="lower right")

    for thr, col, mk in ((2, "#7f7f7f", "o"), (4, C_VANILLA, "s"), (6, C_OURS, "^")):
        rs = [r for r in cliffs if int(r["cliff_threshold_risers"]) == thr]
        rs.sort(key=lambda r: float(r["baseline_km"]))
        n = rs[0]["n_edges"]
        bx.plot([float(r["baseline_km"]) for r in rs],
                [float(r["kept_deterrace_pct"]) for r in rs], "-" + mk, color=col,
                ms=4, label=f"≥{thr} risers (n = {int(n):,})")
        bx.plot([float(r["baseline_km"]) for r in rs],
                [float(r["kept_shipped_pct"]) for r in rs], "--" + mk, color=col,
                ms=3, alpha=0.55)
    bx.axhline(100, color="0.4", lw=1.0, ls=":")
    bx.set_ylim(50, 110)
    bx.set_xlabel("baseline the drop is measured over (km)")
    bx.set_ylabel("signed drop kept, % of the plain rescale's own")
    bx.set_title("How much of a real cliff survives\n"
                 "solid = after de-terrace, dashed = shipped map", fontsize=9.5)
    bx.grid(True, alpha=0.22)
    bx.legend(fontsize=8, loc="lower right")
    lab = [f"{float(r['band_km_lo']):.0f}–{float(r['band_km_hi']):.0f}" for r in bands]
    y = np.arange(len(bands))
    for k, (col, lbl, colr) in enumerate((
            ("rms_vanilla_norway", "vanilla CK3, Norwegian coast", C_VANILLA),
            ("rms_shipped", "ours, shipped", C_OURS),
            ("rms_deterrace", "+ de-terrace", "#4f9d5d"),
            ("rms_plain", "plain rescale", C_BEFORE))):
        cx.barh(y + (1.5 - k) * 0.21, [float(r[col]) for r in bands], 0.20,
                color=colr, label=lbl)
    cx.set_yticks(y)
    cx.set_yticklabels(lab)
    cx.invert_yaxis()
    cx.set_ylabel("wavelength band (km)")
    cx.set_xlabel("band-passed RMS over land (16-bit levels)")
    cx.set_title("Where the synthesised detail actually lands\n"
                 "(difference-of-Gaussian bands, Thay land vs vanilla's own coast)",
                 fontsize=9.5)
    cx.grid(True, axis="x", alpha=0.22)
    cx.set_xlim(0, max(float(r["rms_shipped"]) for r in bands) * 1.42)
    cx.legend(fontsize=7.5, loc="lower right", framealpha=0.95)

    # every number in the caption comes out of the two CSVs above
    c4 = [r for r in cliffs if int(r["cliff_threshold_risers"]) == 4]
    near = min(c4, key=lambda r: float(r["baseline_km"]))
    far = max(c4, key=lambda r: float(r["baseline_km"]))
    worst = max(bands, key=lambda r: (float(r["rms_shipped"])
                                      / max(float(r["rms_vanilla_norway"]), 1e-9)))
    ratio = float(worst["rms_shipped"]) / float(worst["rms_vanilla_norway"])
    fig.suptitle(
        "Figure 10 — the de-terrace pass removes the quantisation riser and keeps the cliff: "
        f"{float(near['kept_deterrace_pct']):.0f} % of the one-pixel step and "
        f"{float(far['kept_deterrace_pct']):.0f} % of the drop over "
        f"{float(far['baseline_km']):.0f} km survive (≥ 4 risers).\n"
        f"The fill's largest excess over vanilla is {ratio:.2f}× at "
        f"{float(worst['band_km_lo']):.0f}–{float(worst['band_km_hi']):.0f} km.",
        fontsize=9.5)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(OUT / "fig10_thay_steps.png")
    plt.close(fig)
    return "fig10_thay_steps.png"


# ---------------------------------------------------- figures 11 and 12
#: (label, km across).  Continent is capped at 2000 km on purpose: it is the
#: brief's own figure and it is what a vanilla crop can match.  Faerûn is
#: ~4000 km from Waterdeep to Thay, so this frame is half the continent.
PANEL_SCALES = [("continent", 2000.0), ("region", 400.0), ("local", 80.0)]
#: Faerûn centres, canvas px, nested where the scale allows.
FAERUN_CENTRES = {"continent": (3000, 1500), "region": WATERDEEP_CANVAS,
                  "local": WATERDEEP_CANVAS}
#: vanilla centres, **heightmap** px (2x); the paint is at half of these.
VANILLA_CENTRES = {"continent": (3100, 1500), "region": VANILLA_CTRL_HM,
                   "local": VANILLA_CTRL_HM}
PANEL_PX = 380


def m_panel_extents():
    rows = []
    for name, km in PANEL_SCALES:
        fx, fy = FAERUN_CENTRES[name]
        vx, vy = VANILLA_CENTRES[name]
        rows.append({"scale": name, "km_across": km,
                     "faerun_canvas_x": fx, "faerun_canvas_y": fy,
                     "faerun_km_per_px_height": KM_PX_OURS,
                     "faerun_km_per_px_paint": KM_PX_OURS * 2,
                     "vanilla_heightmap_x": vx, "vanilla_heightmap_y": vy,
                     "vanilla_km_per_px_height": KM_PX_VANILLA,
                     "vanilla_km_per_px_paint": KM_PX_VANILLA * 2,
                     "panel_px": PANEL_PX})
    return rows


_PANEL_FIELDS = ["scale", "km_across", "faerun_canvas_x", "faerun_canvas_y",
                 "faerun_km_per_px_height", "faerun_km_per_px_paint",
                 "vanilla_heightmap_x", "vanilla_heightmap_y",
                 "vanilla_km_per_px_height", "vanilla_km_per_px_paint",
                 "panel_px"]


def _grid(fig, axes, rowlabels, collabels, title, path):
    for r, rl in enumerate(rowlabels):
        for c, cl in enumerate(collabels):
            ax = axes[r][c]
            ax.set_xticks([])
            ax.set_yticks([])
            if r == 0:
                ax.set_title(cl, fontsize=9)
            if c == 0:
                ax.set_ylabel(rl, fontsize=8.5)
    fig.suptitle(title, fontsize=9.5)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(OUT / path)
    plt.close(fig)
    return path


def fig_panels_relief(recompute: bool) -> str:
    cached("panel_extents.csv", _PANEL_FIELDS, m_panel_extents, recompute)
    clamp_stats = cached("clamp_floor.csv", _CLAMP_FIELDS, m_clamp_floor,
                         recompute)[0]
    plain = plain_rescale_canvas()
    ship = load_heightmap(MOD / "map_data/heightmap.png")
    van = load_heightmap(GAME / "map_data/heightmap.png")
    cols = ["CK2 source, rescaled only\n(1.4839 km/px, 8-bit ancestry)",
            "ours, shipped\n(1.4839 km/px, detail pass)",
            "vanilla CK3 — Norwegian coast\n(0.742 km/px, 2× heightmap)"]
    fig, axes = plt.subplots(3, 3, figsize=(11.6, 12.0), dpi=120)
    rowlabels = []
    for r, (name, km) in enumerate(PANEL_SCALES):
        fx, fy = FAERUN_CENTRES[name]
        vx, vy = VANILLA_CENTRES[name]
        ours_half = int(km / KM_PX_OURS / 2)
        van_half = int(km / KM_PX_VANILLA / 2)
        os_ = crop_c(ship, fx, fy, ours_half)
        panels = [
            (crop_c(plain, fx, fy, ours_half), os_ > WATER_LEVEL,
             UNITS_PER_HM_PX_OURS, EXTENTS_Y_OURS, None),
            (os_, os_ > WATER_LEVEL, UNITS_PER_HM_PX_OURS, EXTENTS_Y_OURS,
             os_ == WATER_LEVEL + 1),
            (crop_c(van, vx, vy, van_half), crop_c(van, vx, vy, van_half) > VANILLA_WATER,
             UNITS_PER_HM_PX_VANILLA, EXTENTS_Y_VANILLA, None),
        ]
        for c, (z, m, upp, ey, cl) in enumerate(panels):
            rgb = shade_rgb(z.astype(np.float32), m, units_per_px=upp,
                            extents_y=ey, clamp=cl)
            axes[r][c].imshow(resize_panel(rgb, PANEL_PX), interpolation="nearest")
        rowlabels.append(f"{name} — {km:.0f} km across\n"
                         f"({2 * ours_half} px ours / {2 * van_half} px vanilla)")
    del plain, ship, van
    return _grid(fig, axes, rowlabels, cols,
                 "Figure 11 — elevation at three zooms, the same kilometres in every panel. "
                 "Hillshade 315°/35°, ×3 vertical exaggeration in game units.\n"
                 f"Pink in the middle column is land the detail pass sank below the water "
                 f"level and the clamp pulled back to a dead-flat {WATER_LEVEL + 1}: "
                 f"{clamp_stats['clamp_pct_of_land']} % of all land "
                 f"(clamp_floor.csv).",
                 "fig11_panels_relief.png")


def fig_panels_paint(recompute: bool) -> str:
    cached("panel_extents.csv", _PANEL_FIELDS, m_panel_extents, recompute)
    lut = tint_lut()
    oi, ot, oland = _paint_pair(MOD, MOD / "map_data/heightmap.png", WATER_LEVEL)
    vi, vt, vland = _paint_pair(GAME, GAME / "map_data/heightmap.png", VANILLA_WATER)
    codes, names, cland = ck2_terrain_codes()
    cols = ["CK2 terrain.bmp, class-mapped\n(2.90 km/px, one material per pixel)",
            "ours, shipped detail_index\n(2.97 km/px, two materials blended)",
            "vanilla CK3 detail_index\n(1.4839 km/px, 3.5 materials blended)"]
    fig, axes = plt.subplots(3, 3, figsize=(11.6, 12.0), dpi=120)
    rowlabels = []
    for r, (name, km) in enumerate(PANEL_SCALES):
        fx, fy = FAERUN_CENTRES[name]
        vx, vy = VANILLA_CENTRES[name]
        ck2_c = (int(round((fx - OFFSET_X) / CK2_SCALE)),
                 int(round((fy - OFFSET_Y) / CK2_SCALE)))
        ck2_half = max(int(km / KM_PX_CK2 / 2), 1)
        ours_half = max(int(km / (KM_PX_OURS * 2) / 2), 1)
        van_half = max(int(km / (KM_PX_VANILLA * 2) / 2), 1)
        rgbs = [
            ck2_paint_rgb(crop_c(codes, ck2_c[0], ck2_c[1], ck2_half), names, lut,
                          crop_c(cland, ck2_c[0], ck2_c[1], ck2_half)),
            paint_rgb(crop_c(oi, fx // 2, fy // 2, ours_half),
                      crop_c(ot, fx // 2, fy // 2, ours_half), lut,
                      crop_c(oland, fx // 2, fy // 2, ours_half)),
            paint_rgb(crop_c(vi, vx // 2, vy // 2, van_half),
                      crop_c(vt, vx // 2, vy // 2, van_half), lut,
                      crop_c(vland, vx // 2, vy // 2, van_half)),
        ]
        for c, rgb in enumerate(rgbs):
            axes[r][c].imshow(resize_panel(rgb, PANEL_PX), interpolation="nearest")
        rowlabels.append(f"{name} — {km:.0f} km across\n"
                         f"({2 * ours_half} px ours / {2 * van_half} px vanilla)")
    del oi, ot, vi, vt, codes
    return _grid(fig, axes, rowlabels, cols,
                 "Figure 12 — terrain paint at the same three zooms. Every pixel is its "
                 f"materials' vanilla-measured colormap tint, blended by detail_intensity\n"
                 f"and pushed ×{TINT_GAIN:.0f} from grey so the near-neutral tints are "
                 "visible at all (display gain only, applied identically to all three columns).",
                 "fig12_panels_paint.png")


# -------------------------------------------------------------- figure 13
def fig_materials(recompute: bool) -> str:
    rows = cached("material_share.csv", _MATERIAL_FIELDS, m_material_share,
                  recompute)
    blend = cached("paint_blend.csv", _BLEND_FIELDS, m_paint_blend, recompute)
    bl = {r["map"]: r for r in blend}

    top = sorted(rows, key=lambda r: -(float(r["ours_coverage_pct"])
                                       + float(r["vanilla_coverage_pct"])))[:22]
    fam_o, fam_v = defaultdict(float), defaultdict(float)
    for r in rows:
        fam_o[r["family"]] += float(r["ours_coverage_pct"])
        fam_v[r["family"]] += float(r["vanilla_coverage_pct"])

    fig = plt.figure(figsize=(14.2, 8.6), dpi=120)
    gs = fig.add_gridspec(1, 2, width_ratios=[1.0, 1.25], wspace=0.42)
    ax = fig.add_subplot(gs[0, 0])
    y = np.arange(len(top))
    ax.barh(y + 0.2, [float(r["vanilla_coverage_pct"]) for r in top], 0.38,
            color=C_VANILLA, label="vanilla CK3")
    ax.barh(y - 0.2, [float(r["ours_coverage_pct"]) for r in top], 0.38,
            color=C_OURS, label="ours, shipped")
    ax.set_yticks(y)
    ax.set_yticklabels([(r["material"][:27] + ("…" if len(r["material"]) > 27 else ""))
                        + (" *" if int(r["vanilla_regional"]) else "")
                        for r in top], fontsize=7.0)
    ax.invert_yaxis()
    ax.set_xlabel("share of painted land, intensity-weighted (%)")
    ax.set_title("Per material, the 22 largest\n"
                 "* = a vanilla regional/climate-zone material our table never picks",
                 fontsize=9.5)
    ax.grid(True, axis="x", alpha=0.22)
    ax.legend(fontsize=8, loc="lower right")

    bx = fig.add_subplot(gs[0, 1])
    fams = sorted(set(fam_o) | set(fam_v), key=lambda f: -fam_v.get(f, 0))
    y = np.arange(len(fams))
    bx.barh(y + 0.2, [fam_v.get(f, 0) for f in fams], 0.38, color=C_VANILLA,
            label="vanilla CK3")
    bx.barh(y - 0.2, [fam_o.get(f, 0) for f in fams], 0.38, color=C_OURS,
            label="ours, shipped")
    tone = {"geography": "#4f9d5d", "mixed": "#c8912a", "mapping": "#b4463f"}
    for i, f in enumerate(fams):
        kind, _ = FAMILY_REASONS.get(f, ("mixed", ""))
        d = fam_o.get(f, 0) - fam_v.get(f, 0)
        bx.text(max(fam_v.get(f, 0), fam_o.get(f, 0)) + 0.4, i,
                f"{d:+.1f} pp — {kind}", fontsize=7.5, va="center",
                color=tone.get(kind, "0.3"))
    bx.set_yticks(y)
    bx.set_yticklabels(fams, fontsize=8.5)
    bx.invert_yaxis()
    bx.set_xlim(0, max(max(fam_v.values()), max(fam_o.values())) * 1.55)
    bx.set_xlabel("share of painted land, intensity-weighted (%)")
    bx.set_title("By material family, with the difference and whether geography explains it\n"
                 "green = expected from Faerûn not being Earth · amber = mixed · red = our mapping",
                 fontsize=9.5)
    bx.grid(True, axis="x", alpha=0.22)
    bx.legend(fontsize=8, loc="lower right")
    txt = ("blend density, land pixels — "
           f"materials used: ours {bl['ours']['materials_used']} of vanilla's "
           f"{bl['vanilla']['materials_used']}  ·  "
           f"non-zero channels per pixel: ours {float(bl['ours']['mean_nonzero_channels']):.2f} "
           f"vs {float(bl['vanilla']['mean_nonzero_channels']):.2f}  ·  "
           f"blend entropy: ours {float(bl['ours']['blend_entropy_bits']):.2f} bits "
           f"vs {float(bl['vanilla']['blend_entropy_bits']):.2f}  ·  "
           f"primary weight: ours {float(bl['ours']['mean_primary_weight']):.2f} "
           f"vs {float(bl['vanilla']['mean_primary_weight']):.2f}")
    fig.text(0.5, 0.015, txt, ha="center", fontsize=8.5, color="0.25")
    fig.suptitle("Figure 13 — paint composition per material, not per terrain key. "
                 "Area share alone is the weaker half of the story; the blend line under the "
                 "figure is the stronger one.", fontsize=9.5)
    # see fig_thay_transects: a nested gridspec is not tight_layout's business
    fig.subplots_adjust(top=0.91, bottom=0.09, left=0.135, right=0.985)
    fig.savefig(OUT / "fig13_materials.png")
    plt.close(fig)
    return "fig13_materials.png"


# -------------------------------------------------------------- figure 14
#: The erosion lane's own hillshades, at its own two crops
#: (`docs/evidence/heightmap_erosion/crops.json`): k_thay and
#: k_spine_of_the_world, 512 px square on this canvas.  Reused rather than
#: regenerated so the before/after pair is the same pixels the lane that made
#: the change looked at.
EROSION_EV = EV / "heightmap_erosion"
_BA_COLS = [("plain_rescale", "ours: plain rescale\n(no detail pass)"),
            ("ours_shipped_isotropic", "build 8: Gaussian σ 1.6\n+ isotropic f^−2 fill"),
            ("ours_eroded", "build 12: cliff-aware σ 2.2\n+ eroded relief")]


def fig_before_after() -> str:
    from PIL import Image
    rows = [("thay", "Thay — 512 px, 760 km"),
            ("spine", "Spine of the World — 512 px, 760 km")]
    fig, axes = plt.subplots(2, 4, figsize=(13.4, 7.2), dpi=120)
    with Image.open(_need(EROSION_EV / "hillshade_ck3_vanilla_mountains.png",
                          "vanilla control hillshade")) as im:
        van = np.asarray(im.convert("RGB"))
    for r, (region, rlabel) in enumerate(rows):
        for c, (tag, clabel) in enumerate(_BA_COLS):
            p = _need(EROSION_EV / f"hillshade_{region}_{tag}.png",
                      f"{region} {tag} hillshade")
            with Image.open(p) as im:
                axes[r][c].imshow(np.asarray(im.convert("RGB")),
                                  interpolation="nearest")
            if r == 0:
                axes[r][c].set_title(clabel, fontsize=8.5)
        axes[r][3].imshow(van, interpolation="nearest")
        if r == 0:
            axes[r][3].set_title("vanilla CK3 — mountains\n(the control)",
                                 fontsize=8.5)
        axes[r][0].set_ylabel(rlabel, fontsize=8.5)
        for c in range(4):
            axes[r][c].set_xticks([])
            axes[r][c].set_yticks([])
    fig.suptitle("Figure 14 — before and after the erosion lane, same crops, same hillshade. "
                 "Build 8's fill is isotropic gravel at county scale;\nbuild 12's is a "
                 "drainage network. Panels are the erosion lane's own PNGs "
                 "(docs/evidence/heightmap_erosion/, crops.json).", fontsize=9.5)
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    fig.savefig(OUT / "fig14_before_after.png")
    plt.close(fig)
    return "fig14_before_after.png"


def main() -> None:
    global MOD
    ap = argparse.ArgumentParser()
    ap.add_argument("--mod", type=Path, default=DEFAULT_MOD,
                    help="the reference conversion to measure "
                         f"(default: {DEFAULT_MOD})")
    ap.add_argument("--recompute", action="store_true",
                    help="re-measure the cached CSVs from the shipped rasters")
    args = ap.parse_args()
    MOD = args.mod.resolve()
    print(f"reference conversion: {MOD}", flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    made = [
        fig_hf_targets(args.recompute),   # figure 1
        fig_spectrum(args.recompute),     # figure 2
        fig_heights(args.recompute),      # figure 3
        fig_seafloor(args.recompute),     # figure 4
        fig_composition(args.recompute),  # figure 5
        fig_colour(),                     # figure 6
        fig_trees(args.recompute),        # figure 7
        fig_thay_relief(args.recompute),    # figure 8   -- section 7
        fig_thay_transects(args.recompute), # figure 9
        fig_thay_steps(args.recompute),     # figure 10
        fig_panels_relief(args.recompute),  # figure 11
        fig_panels_paint(args.recompute),   # figure 12
        fig_materials(args.recompute),      # figure 13
        fig_before_after(),                 # figure 14  -- build 8 vs build 12
    ]
    for n in made:
        p = OUT / n
        print(f"wrote {p.relative_to(ROOT)}  ({p.stat().st_size // 1024} KiB)")


if __name__ == "__main__":
    main()
