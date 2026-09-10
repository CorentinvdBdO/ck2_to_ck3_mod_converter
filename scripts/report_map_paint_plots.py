"""Figures for `docs/report_map_paint.md` (lane `report-paint`).

Run: uv run --with matplotlib python scripts/report_map_paint_plots.py [--recompute]
(matplotlib is deliberately not a repo dependency; --with keeps pyproject as is,
same convention as scripts/map_fidelity_plots.py.)

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

  hf_achieved.csv          NOT measured here: transcribed from
                           docs/evidence/HANDOFF_map_heightmap_detail.md
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

#: The reference run of the shipped configuration: lane `seafloor`, 2026-09-10,
#: `[map] heightmap_detail = true` + `[map.heightmap] deepen_sea = true`.  A
#: fixed output directory on purpose -- ../claudespace/mods/... is regenerated
#: by whatever lane is running and is not a stable thing to measure.
MOD = ROOT / "../_out/seafloor"
#: the run one lane earlier: same detail pass, deepen_sea off
MOD_NO_DEEPEN = ROOT / "../_out/colormap-fix"
GAME = ROOT / "../claudespace/game_files"
CK2_MAP = ROOT / "Faerun/Faerun/map"

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
    """
    y, x0, x1 = 1077, 1750, 2450
    now = load_heightmap(MOD / "map_data/heightmap.png")[y, x0:x1]
    before = load_heightmap(
        MOD_NO_DEEPEN / "map_data/heightmap.png")[y, x0:x1]
    return [{"x_px": x0 + i, "ck2_derived": int(b), "deepened": int(n)}
            for i, (b, n) in enumerate(zip(before, now))]


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
              zorder=0, label=r"$f^{-2.0}$ (vanilla's fitted land law)")

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
    for stage, col, lbl in (("before", C_BEFORE, "plain rescale (212 levels map-wide)"),
                            ("now", C_OURS, "shipped, detail pass (44,522)")):
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
    x = np.array([int(r["x_px"]) for r in rows])
    before = np.array([int(r["ck2_derived"]) for r in rows])
    now = np.array([int(r["deepened"]) for r in rows])

    fig, ax = plt.subplots(figsize=(9.0, 4.2), dpi=120)
    ax.plot(x, before, color=C_BEFORE, lw=1.3, label="CK2-derived sea floor (deepen_sea = false)")
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
    ax.set_title("Sea-floor transect, Sword Coast")
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

    keys = sorted(set(ours) | set(ck2) | set(van), key=lambda k: -ours.get(k, 0))
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


def fig_hf_targets() -> str:
    tgt = {r["terrain"]: float(r["hf_rms_levels"]) for r in read_csv(FID / "hf_by_terrain.csv")}
    ach = read_csv(OUT / "hf_achieved.csv")
    keys = [r["terrain"] for r in sorted(ach, key=lambda r: tgt.get(r["terrain"], 0))]
    a = {r["terrain"]: r for r in ach}
    y = np.arange(len(keys))
    fig, ax = plt.subplots(figsize=(8.6, 4.8), dpi=120)
    ax.barh(y + 0.26, [tgt[k] for k in keys], 0.25, color=C_VANILLA,
            label="vanilla target (hf_by_terrain.csv)")
    ax.barh(y, [float(a[k]["achieved_interior"]) for k in keys], 0.25, color=C_OURS,
            label="ours, interior land (> 20 px from any coast)")
    ax.barh(y - 0.26, [float(a[k]["achieved_all_land"]) for k in keys], 0.25,
            color=C_BEFORE, label="ours, all land (coast step inflates this)")
    ax.set_yticks(y)
    ax.set_yticklabels(keys)
    ax.set_xlabel("high-frequency RMS (16-bit levels, detail below ~6 km)")
    ax.set_title("The calibration table the detail pass obeys\n"
                 "(vanilla spans 70 for taiga to 311 for mountains on the classes Faerûn paints —\n"
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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--recompute", action="store_true",
                    help="re-measure the cached CSVs from the shipped rasters")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    made = [
        fig_hf_targets(),                 # figure 1
        fig_spectrum(args.recompute),     # figure 2
        fig_heights(args.recompute),      # figure 3
        fig_seafloor(args.recompute),     # figure 4
        fig_composition(args.recompute),  # figure 5
        fig_colour(),                     # figure 6
        fig_trees(args.recompute),        # figure 7
    ]
    for n in made:
        p = OUT / n
        print(f"wrote {p.relative_to(ROOT)}  ({p.stat().st_size // 1024} KiB)")


if __name__ == "__main__":
    main()
