#!/usr/bin/env python3
"""Lane `relief-paint`: does vanilla vary its paint WITHIN a terrain class by
relief, and by how much?

The user's playtest question: "procedural erosion patterns [are] not great
(probably need to edit the paint maps too)". `docs/step_map_heightmap.md`
§2g already measured that our mountains are the right *amplitude* but the
wrong *shape* (gradient kurtosis 0.45x vanilla). This script asks a
different, paint-side question: even where the erosion's shape IS right (on
vanilla's own map, by construction), does the paint ever show it? Or does one
CK3 terrain class always wear one material mix regardless of slope?

Method, reusing existing lane code rather than reinventing it:
  - the per-pixel CK3 terrain-key class grid: `verify_terrain_paint_materials`
    (`read_province_terrain`, `read_definition`), same as
    `scripts/measure_vanilla_paint_blend.py`.
  - `detail_index.tga` primary-channel ordinal -> material id
    (`ck2ck3.map.terrain_paint.material_ordinals`).
  - `map_data/heightmap.png`, vanilla's own 2x-resolution 16-bit elevation,
    downsampled 2x (stride) onto the province/paint pixel grid -- the same
    alignment `measure_vanilla_paint_blend.py:paint_pair` already uses for
    its land mask, extended here to the height *values* themselves.
  - slope: |grad h| (central differences, one paint-pixel spacing).
  - curvature: the 4-neighbour discrete Laplacian, thresholded at the land
    terciles into ridge (concave-down, sum(neighbours) < 4h) / flat / valley
    (concave-up) -- the same sign convention
    `ck2ck3.map.heightmap_erosion._laplacian` uses (read, not imported: that
    module is a sibling lane's, this script only needs the formula).
  - flow accumulation: `ck2ck3.map.heightmap_erosion.flow_accumulation` +
    `_mfd_weights`, imported READ-ONLY (this lane does not edit that file)
    over vanilla's own aligned heightmap, 12 relaxation passes.
  - elevation: land-wide percentile tercile of LOCAL relief (height above its
    own Gaussian-blurred local base, `local_relief_field`) -- NOT raw height
    above sea level. Coordinator review found raw-elevation percentile bins
    are whole-map-relative, so a flat lowland pixel on a map with taller
    mountains overall could still land in a "high" bin and get painted
    snow/rock; local relief is stable across two differently-scaled maps.
  - material -> coarse category (rock / scree_snow / soil_grass / forest /
    other), a name-heuristic over vanilla's own `materials.settings` ids,
    written out as `mappings/paint_material_categories.csv` for audit.

Writes:
    mappings/paint_material_categories.csv   (material id -> category)
    docs/evidence/vanilla_paint_vs_relief.csv     (the conditional table)
    docs/evidence/vanilla_paint_vs_relief_mi.csv  (per-class, per-axis MI/eta^2)
    docs/evidence/vanilla_paint_vs_relief.png     (figure)
    docs/evidence/vanilla_paint_vs_relief.md      (narrative summary)

Usage::

    uv run scripts/measure_vanilla_relief_paint.py [ck3_game_dir]
"""
from __future__ import annotations

import csv
import re
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))

from ck2ck3.map.terrain_paint import material_ordinals  # noqa: E402
from ck2ck3.map.heightmap_erosion import _mfd_weights, flow_accumulation  # noqa: E402
from ck2ck3.map.relief_paint import (  # noqa: E402
    CATEGORY_CODE, CATEGORY_NAMES, classify_material,
)
import verify_terrain_paint_materials as vtpm  # noqa: E402

DEFAULT_GAME = vtpm.DEFAULT_GAME
OUT = REPO / "docs/evidence"
KM_PER_PX = 1.4839  # docs/evidence/report_map_paint/panel_extents.csv
VANILLA_WATER = 3932  # 2x-resolution heightmap.png 16-bit water threshold

#: vanilla materials named for real-world climate zones (gen_*, medi_*,
#: northern_*, india_*, central_*, tropical*) -- `docs/step_map_paint.md`
#: §9.3/§10.4 already found these contaminate any per-terrain-key vote with
#: Earth geography that does not generalise to Faerun (56.1% of vanilla's
#: coverage is these families).  Excluded here for the same reason: without
#: this filter "mountains" at high slope votes `gen_tropical_lowlands_02`
#: top material -- real Earth tropical-mountain provinces, not a slope
#: effect (`verified`, first run of this script, kept as a negative result
#: in docs/evidence/vanilla_paint_vs_relief.md).
_REGIONAL_RE = re.compile(r"^(gen_|medi_|northern_|india_|central_|tropical)")

SLOPE_BINS = ("low", "mid", "high")
CURV_BINS = ("ridge", "flat", "valley")
FLOW_BINS = ("low", "high")
ELEV_BINS = ("low", "mid", "high")

# --------------------------------------------------------------------------- #
# material -> coarse relief family (ck2ck3.map.relief_paint.classify_material)
# --------------------------------------------------------------------------- #
def build_material_categories_csv(ordinals: dict[str, int], out_path: Path) -> dict[str, str]:
    cat_of: dict[str, str] = {}
    rows = []
    for mat_id in sorted(ordinals, key=lambda m: ordinals[m]):
        cat = classify_material(mat_id)
        cat_of[mat_id] = cat
        rows.append({"material": mat_id, "ordinal": ordinals[mat_id], "category": cat})
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["material", "ordinal", "category"])
        w.writeheader()
        w.writerows(rows)
    return cat_of


# --------------------------------------------------------------------------- #
# relief features, aligned to the paint/province pixel grid
# --------------------------------------------------------------------------- #
def load_aligned_height(game_dir: Path, target_shape: tuple[int, int]) -> np.ndarray:
    with Image.open(game_dir / "map_data" / "heightmap.png") as im:
        hm = np.asarray(im.convert("I;16")).astype(np.float32)
    step = hm.shape[0] // target_shape[0]
    aligned = hm[::step, ::step][: target_shape[0], : target_shape[1]]
    return aligned


def slope_field(h: np.ndarray) -> np.ndarray:
    gy, gx = np.gradient(h)
    return np.hypot(gy, gx)


#: local-relief smoothing width, canvas px -- "vanilla's valley width".
#: `docs/step_map_heightmap.md` §2c: the structure the erosion synthesises
#: lives at 1-20 km (2-14 canvas px); 8 px (~12 km at 1.4839 km/px) sits in
#: that band. `assumed`: a judgement call, not itself independently measured
#: -- picked to isolate LOCAL prominence (a peak inside a valley reads high,
#: flat lowland reads ~0) at the same scale the erosion pass already treats
#: as "relief", not a scale separately validated against vanilla.
LOCAL_RELIEF_SIGMA_PX = 24.0


def local_relief_field(h: np.ndarray, sigma_px: float = LOCAL_RELIEF_SIGMA_PX) -> np.ndarray:
    """Height minus its own local (blurred) base -- elevation ABOVE the
    immediate surroundings, not raw height above sea level.

    Coordinator review (`docs/step_map_paint.md` §11): binning raw elevation
    by a WHOLE-MAP percentile put snow/rock on flat lowland forest, because
    "high" was defined by the map's tallest mountains, not by whether a
    given pixel is locally prominent. A flat lowland pixel has local_relief
    ~= 0 regardless of the map's absolute height range, so its bin is stable
    whether measured on vanilla or applied to a differently-scaled Faerun.
    """
    from scipy.ndimage import gaussian_filter
    return h - gaussian_filter(h.astype(np.float32), sigma_px)


def laplacian_field(h: np.ndarray) -> np.ndarray:
    out = -4.0 * h
    out += np.roll(h, 1, axis=0)
    out += np.roll(h, -1, axis=0)
    out += np.roll(h, 1, axis=1)
    out += np.roll(h, -1, axis=1)
    return out


def tercile_bin(values: np.ndarray, land: np.ndarray, *, low_high_only: bool = False) -> np.ndarray:
    """Percentile bin over `land`, applied to the whole array; 0/1(/2)."""
    sample = values[land]
    if low_high_only:
        cuts = [float(np.percentile(sample, 50))]
        out = np.zeros(values.shape, dtype=np.uint8)
        out[values >= cuts[0]] = 1
        return out
    p33, p66 = np.percentile(sample, [33.333, 66.667])
    out = np.zeros(values.shape, dtype=np.uint8)
    out[values >= p33] = 1
    out[values >= p66] = 2
    return out


def curvature_bin(lap: np.ndarray, land: np.ndarray) -> np.ndarray:
    """0 = ridge (concave down), 1 = flat, 2 = valley (concave up)."""
    sample = lap[land]
    p33, p66 = np.percentile(sample, [33.333, 66.667])
    out = np.full(lap.shape, 1, dtype=np.uint8)
    out[lap < p33] = 0
    out[lap > p66] = 2
    return out


def flow_bin_field(h: np.ndarray, land: np.ndarray, *, iterations: int = 12) -> np.ndarray:
    weights = _mfd_weights(h.astype(np.float32), exponent=4.0)
    acc = flow_accumulation(weights, land, iterations)
    log_acc = np.log1p(acc)
    return tercile_bin(log_acc, land, low_high_only=True)


# --------------------------------------------------------------------------- #
# class map (same pattern as measure_vanilla_paint_blend.py)
# --------------------------------------------------------------------------- #
def class_map(game_dir: Path) -> tuple[np.ndarray, list[str]]:
    prov_terrain = vtpm.read_province_terrain(game_dir)
    rgb_to_id = vtpm.read_definition(game_dir / "map_data" / "definition.csv")
    rgbkey_to_tkey: dict[int, str] = {}
    for (r, g, b), pid in rgb_to_id.items():
        rgbkey_to_tkey[(r << 16) | (g << 8) | b] = prov_terrain.get(pid, "")
    with Image.open(game_dir / "map_data" / "provinces.png") as im:
        prov = np.asarray(im.convert("RGB"))
    H, W = prov.shape[:2]
    key = ((prov[:, :, 0].astype(np.uint32) << 16)
           | (prov[:, :, 1].astype(np.uint32) << 8) | prov[:, :, 2])
    del prov
    uniq, inv = np.unique(key, return_inverse=True)
    del key
    tkey_per_uniq = [rgbkey_to_tkey.get(int(u), "") for u in uniq]
    names = sorted(set(tkey_per_uniq))
    code_of = {n: i for i, n in enumerate(names)}
    codes_per_uniq = np.array([code_of[t] for t in tkey_per_uniq], dtype=np.int16)
    codes = codes_per_uniq[inv].reshape(H, W)
    return codes, names


# --------------------------------------------------------------------------- #
# information-theoretic summaries
# --------------------------------------------------------------------------- #
def entropy(counts: np.ndarray) -> float:
    total = counts.sum()
    if total <= 0:
        return 0.0
    p = counts[counts > 0] / total
    return float(-(p * np.log2(p)).sum())


def mutual_information(cat_codes: np.ndarray, bin_codes: np.ndarray,
                        n_cat: int, n_bin: int) -> float:
    """I(category; bin) in bits, over the pixels given."""
    n = cat_codes.size
    if n == 0:
        return 0.0
    joint = np.zeros((n_cat, n_bin), dtype=np.float64)
    np.add.at(joint, (cat_codes, bin_codes), 1.0)
    joint /= n
    pc = joint.sum(axis=1, keepdims=True)
    pb = joint.sum(axis=0, keepdims=True)
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = np.where(joint > 0, joint / np.maximum(pc * pb, 1e-15), 1.0)
        term = np.where(joint > 0, joint * np.log2(np.maximum(ratio, 1e-300)), 0.0)
    return float(term.sum())


def eta_squared(numeric: np.ndarray, bin_codes: np.ndarray, n_bin: int) -> float:
    """ANOVA eta^2 = 1 - SSE/SST: variance of `numeric` explained by the bin."""
    sst = float(np.var(numeric)) * numeric.size
    if sst <= 0:
        return 0.0
    sse = 0.0
    for b in range(n_bin):
        sel = bin_codes == b
        if not sel.any():
            continue
        sse += float(np.var(numeric[sel])) * int(sel.sum())
    return max(0.0, 1.0 - sse / sst)


# a numeric "rockiness" proxy for eta^2 -- ordinal, not a claim of a true
# physical scale, just enough structure for a variance-explained number.
_CATEGORY_SCORE = {"rock": 1.0, "snow": 0.9, "other": 0.5, "forest": 0.3,
                    "grass": 0.1, "soil": 0.2}


def main(argv: list[str]) -> int:
    t0 = time.time()
    game_dir = Path(argv[1]) if len(argv) > 1 else DEFAULT_GAME
    OUT.mkdir(parents=True, exist_ok=True)
    print(f"game dir: {game_dir}")

    print("building terrain-class map...", flush=True)
    codes, names = class_map(game_dir)
    H, W = codes.shape

    print("computing class-boundary distance (interior mask, dist > 5px, "
          "same definition as measure_vanilla_paint_blend.py §10.4)...", flush=True)
    from scipy.ndimage import distance_transform_edt
    bnd = np.zeros(codes.shape, dtype=bool)
    bnd[:, :-1] |= codes[:, :-1] != codes[:, 1:]
    bnd[:, 1:] |= codes[:, :-1] != codes[:, 1:]
    bnd[:-1, :] |= codes[:-1, :] != codes[1:, :]
    bnd[1:, :] |= codes[:-1, :] != codes[1:, :]
    interior_dist = distance_transform_edt(~bnd).astype(np.float32)
    del bnd
    interior = interior_dist > 5
    del interior_dist

    print("reading detail_index.tga primary channel...", flush=True)
    with Image.open(game_dir / "gfx" / "map" / "terrain" / "detail_index.tga") as im:
        idx0 = np.asarray(im.convert("RGBA"))[:, :, 0].astype(np.int32)
    assert idx0.shape == codes.shape, (idx0.shape, codes.shape)

    ords_ = material_ordinals(game_dir / "gfx" / "map" / "terrain" / "materials.settings")
    name_of_ordinal = {v: k for k, v in ords_.items()}
    cat_csv = REPO / "mappings" / "paint_material_categories.csv"
    cat_of_material = build_material_categories_csv(ords_, cat_csv)
    cat_names = list(CATEGORY_NAMES)
    cat_code_of = dict(CATEGORY_CODE)
    cat_of_ordinal = np.zeros(256, dtype=np.uint8)
    for o in range(256):
        mat = name_of_ordinal.get(o)
        cat_of_ordinal[o] = cat_code_of.get(cat_of_material.get(mat, "other"), cat_code_of["other"])
    print(f"  material categories: {cat_names} "
          f"({sum(1 for c in cat_of_material.values() if c != 'other')}/"
          f"{len(cat_of_material)} materials matched a relief category)")

    print("loading + aligning heightmap.png...", flush=True)
    h = load_aligned_height(game_dir, (H, W))
    land_phys = h > VANILLA_WATER
    n_land = int(land_phys.sum())
    print(f"  land px: {n_land:,} / {land_phys.size:,} ({100*land_phys.mean():.2f}%)")

    regional_ordinal = np.array(
        [bool(_REGIONAL_RE.match(name_of_ordinal.get(o, ""))) for o in range(256)]
    )
    nonregional_px = ~regional_ordinal[idx0]
    # `land` (analysis mask): real land AND painted with a non-regional
    # material.  Slope/curvature/flow/elevation percentiles and the flow
    # accumulation itself still use `land_phys` (real geography), so
    # excluding a pixel from the paint analysis never distorts the
    # hydrology; only the paint statistics drop it.
    land = land_phys & nonregional_px
    n_dropped = n_land - int(land.sum())
    n_land = int(land.sum())
    print(f"  dropped {n_dropped:,} px whose primary material is a regional "
          f"(gen_*/medi_*/...) family; {n_land:,} land px remain for the "
          "paint analysis")

    print("computing MESO-SCALE slope/curvature (absolute) + PER-CLASS "
          "elevation bins...", flush=True)
    # lane relief-paint, coordinator review, THIRD pass: even fixed absolute
    # slope/curvature cutoffs on the RAW per-pixel gradient/Laplacian still
    # produced fine-grained speckle on Thay -- the erosion pass deliberately
    # synthesises ridged texture at a 2-14 canvas px scale everywhere on
    # rough classes (docs/step_map_heightmap.md §2c/§2g), so the (slope,
    # curvature) BIN ITSELF flips every few pixels there, and no amount of
    # smoothing the stochastic draw can produce vanilla-sized patches from a
    # condition that already flips at pixel scale. Slope and curvature are
    # now measured on the SAME Gaussian-blurred ("meso-scale") height field
    # elevation already uses (`LOCAL_RELIEF_SIGMA_PX`), not the raw one --
    # still an absolute physical measure (unchanged spirit of "slope in
    # absolute terms"), just read at the scale that decides terrain SHAPE
    # rather than per-pixel erosion noise.
    from scipy.ndimage import gaussian_filter as _gf
    h_meso = _gf(h.astype(np.float32), LOCAL_RELIEF_SIGMA_PX)
    slope = slope_field(h_meso)
    slope_bin = tercile_bin(slope, land_phys)
    lap = laplacian_field(h_meso)
    curv_bin = curvature_bin(lap, land_phys)
    local_relief = h - h_meso
    elev_bin = np.zeros(h.shape, dtype=np.uint8)
    for code, cls_name in enumerate(names):
        if not cls_name:
            continue
        cls_land = land_phys & (codes == code)
        if not cls_land.any():
            continue
        elev_bin[cls_land] = tercile_bin(local_relief, cls_land)[cls_land]
    print(f"  per-class elevation bins filled for "
          f"{sum(1 for n in names if n)} classes")

    slope_cuts = np.percentile(slope[land_phys], [33.333, 66.667])
    lap_cuts = np.percentile(lap[land_phys], [33.333, 66.667])
    print(f"  BAKE INTO relief_paint.py: VANILLA_SLOPE_CUTOFFS = "
          f"({slope_cuts[0]:.4f}, {slope_cuts[1]:.4f})")
    print(f"  BAKE INTO relief_paint.py: VANILLA_CURVATURE_CUTOFFS = "
          f"({lap_cuts[0]:.4f}, {lap_cuts[1]:.4f})")

    print("computing flow accumulation (12 MFD relaxation passes)...", flush=True)
    flow_bin = flow_bin_field(h, land_phys, iterations=12)

    category = cat_of_ordinal[idx0]

    # ---------------------------------------------------------------- table
    print("building the conditional table...", flush=True)
    rows = []
    mi_rows = []
    axis_defs = [("slope", slope_bin, len(SLOPE_BINS), SLOPE_BINS),
                 ("curvature", curv_bin, len(CURV_BINS), CURV_BINS),
                 ("flow", flow_bin, len(FLOW_BINS), FLOW_BINS),
                 ("elevation", elev_bin, len(ELEV_BINS), ELEV_BINS)]
    numeric_score = np.vectorize(lambda o: _CATEGORY_SCORE.get(
        cat_of_material.get(name_of_ordinal.get(int(o), ""), "other"), 0.5
    ))
    score = None  # computed lazily per class (expensive over 8.5M px otherwise)

    for cls_name in names:
        if not cls_name:
            continue
        code = names.index(cls_name)
        cls_mask = land & (codes == code)
        n_cls = int(cls_mask.sum())
        if n_cls < 200:
            continue
        cls_cat = category[cls_mask]
        cls_score = numeric_score(idx0[cls_mask]).astype(np.float64)
        h_cat_given_cls = entropy(np.bincount(cls_cat, minlength=len(cat_names)))

        for axis_name, bin_arr, n_bin, bin_labels in axis_defs:
            cls_bin = bin_arr[cls_mask]
            mi = mutual_information(cls_cat, cls_bin, len(cat_names), n_bin)
            eta2 = eta_squared(cls_score, cls_bin, n_bin)
            frac_explained = (mi / h_cat_given_cls) if h_cat_given_cls > 0 else 0.0
            mi_rows.append({
                "ck3_terrain": cls_name, "axis": axis_name, "n": n_cls,
                "h_category_given_class_bits": round(h_cat_given_cls, 4),
                "mutual_information_bits": round(mi, 4),
                "frac_entropy_explained": round(frac_explained, 4),
                "eta_squared": round(eta2, 4),
            })

        # the applied table: (class, slope_bin, curv_bin, elev_bin) -> category
        # shares + top material. slope/curvature are the two axes
        # docs/step_map_heightmap.md §2g describes physically ("bare rock on
        # steep faces, scree/snow on crests, grass/soil on valley floors");
        # elevation is added as a third axis because it measures as the
        # single strongest predictor of `snow_scree` specifically (mountains:
        # eta^2 0.0515 vs slope's 0.0001, mi_rows below) -- crests read as
        # snow mostly because they are high, not because they are pointy.
        # flow is reported above for the variance-explained question but not
        # applied: mean frac_entropy_explained 0.003-0.005, the weakest of
        # the four everywhere (docs/step_map_paint.md §11).
        s_b = slope_bin[cls_mask]
        c_b = curv_bin[cls_mask]
        e_b = elev_bin[cls_mask]
        ords = idx0[cls_mask]
        for si in range(len(SLOPE_BINS)):
            for ci in range(len(CURV_BINS)):
                for ei in range(len(ELEV_BINS)):
                    sel = (s_b == si) & (c_b == ci) & (e_b == ei)
                    n = int(sel.sum())
                    if n < 30:
                        continue
                    sub_ords = ords[sel]
                    vals, counts = np.unique(sub_ords, return_counts=True)
                    order = np.argsort(-counts)
                    top_o = int(vals[order[0]])
                    top_material = name_of_ordinal.get(top_o, f"ordinal_{top_o}")
                    top_share = round(100.0 * counts[order[0]] / n, 2)
                    second = ""
                    second_share = ""
                    if len(order) > 1:
                        o2 = int(vals[order[1]])
                        second = name_of_ordinal.get(o2, f"ordinal_{o2}")
                        second_share = round(100.0 * counts[order[1]] / n, 2)
                    cat_counts = np.bincount(category[cls_mask][sel], minlength=len(cat_names))
                    cat_shares = {cat_names[i]: round(100.0 * cat_counts[i] / n, 2)
                                  for i in range(len(cat_names)) if cat_counts[i] > 0}
                    rows.append({
                        "ck3_terrain": cls_name,
                        "slope_bin": SLOPE_BINS[si],
                        "curvature_bin": CURV_BINS[ci],
                        "elevation_bin": ELEV_BINS[ei],
                        "n": n,
                        "top_material": top_material,
                        "top_share": top_share,
                        "second_material": second,
                        "second_share": second_share,
                        "category_shares": ";".join(f"{k}={v}" for k, v in
                                                     sorted(cat_shares.items(), key=lambda kv: -kv[1])),
                    })

    with (OUT / "vanilla_paint_vs_relief.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=[
            "ck3_terrain", "slope_bin", "curvature_bin", "elevation_bin", "n",
            "top_material", "top_share", "second_material", "second_share",
            "category_shares"])
        w.writeheader()
        w.writerows(rows)
    with (OUT / "vanilla_paint_vs_relief_mi.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=[
            "ck3_terrain", "axis", "n", "h_category_given_class_bits",
            "mutual_information_bits", "frac_entropy_explained", "eta_squared"])
        w.writeheader()
        w.writerows(mi_rows)
    print(f"wrote {len(rows)} table rows, {len(mi_rows)} MI rows")

    # -------------------------------------------------- per-class palette
    # coordinator review (docs/evidence/HANDOFF_relief_paint.md): reordering
    # a class's existing 2-3 `mappings/terrain_paint.csv` materials cannot
    # produce a visible change when they are all the same family (verified:
    # `mountains` = mountain_02/mountain_02_c/mountain_02_d_valleys, all
    # "rock"). This section measures each class's REAL vanilla palette --
    # not the hand-picked 2-3 rows -- so `relief_paint.py` can substitute a
    # genuinely different material per family, on INTERIOR pixels only
    # (dist > 5px from a class boundary, so a neighbouring class's own
    # material never leaks in as "this class's grass pick").
    print("computing per-class family palette (interior, marginal over "
          "relief bins)...", flush=True)
    family_rows = []
    area_rows = []
    for cls_name in names:
        if not cls_name:
            continue
        code = names.index(cls_name)
        cls_mask = land & interior & (codes == code)
        n_cls = int(cls_mask.sum())
        if n_cls < 200:
            continue
        ords = idx0[cls_mask]
        cats = category[cls_mask]
        cat_counts = np.bincount(cats, minlength=len(cat_names))
        cum = 0.0
        for fi in np.argsort(-cat_counts):
            fam = cat_names[fi]
            share = 100.0 * cat_counts[fi] / n_cls
            area_rows.append({"ck3_terrain": cls_name, "family": fam,
                               "share_pct": round(share, 2), "n": int(cat_counts[fi]),
                               "cumulative_pct": round(min(cum + share, 100.0), 2)})
            cum += share
            if cat_counts[fi] == 0:
                continue
            fam_mask = cats == fi
            fam_ords = ords[fam_mask]
            vals, counts = np.unique(fam_ords, return_counts=True)
            order = np.argsort(-counts)
            top_o = int(vals[order[0]])
            top_mat = name_of_ordinal.get(top_o, f"ordinal_{top_o}")
            family_rows.append({
                "ck3_terrain": cls_name, "family": fam, "material": top_mat,
                "ordinal": top_o,
                "share_within_family_pct": round(100.0 * counts[order[0]] / int(fam_mask.sum()), 2),
                "area_share_pct": round(share, 2), "n": int(fam_mask.sum()),
            })

    fam_csv = REPO / "mappings" / "relief_paint_family_materials.csv"
    with fam_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["# GENERATED by scripts/measure_vanilla_relief_paint.py "
                     "-- do not hand-edit"])
        w.writerow(["ck3_terrain", "family", "material", "ordinal",
                     "share_within_family_pct", "area_share_pct", "n"])
        for r in family_rows:
            w.writerow([r["ck3_terrain"], r["family"], r["material"], r["ordinal"],
                        r["share_within_family_pct"], r["area_share_pct"], r["n"]])
    print(f"wrote {len(family_rows)} rows to {fam_csv}")

    with (OUT / "vanilla_paint_family_area_shares.csv").open(
        "w", newline="", encoding="utf-8"
    ) as f:
        w = csv.DictWriter(f, fieldnames=["ck3_terrain", "family", "share_pct",
                                           "n", "cumulative_pct"])
        w.writeheader()
        w.writerows(area_rows)
    print(f"wrote {len(area_rows)} rows to vanilla_paint_family_area_shares.csv")

    # ------------------------------------------------------ patch scale
    # same recipe as scripts/measure_vanilla_colormap_blur.py (radial
    # autocorrelation e-fold), applied to a numeric family-score field
    # instead of colour, over the same mountain window
    # scripts/relief_pits_shape.py uses (2x heightmap px (4352, 9984) ->
    # province/paint scale //2).
    print("measuring family patch scale (autocorrelation e-fold radius)...",
          flush=True)
    from scipy.ndimage import gaussian_filter as _gf

    def _radial_autocorr(patch: np.ndarray) -> np.ndarray:
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

    numeric_score_arr = np.vectorize(lambda o: _CATEGORY_SCORE.get(
        cat_of_material.get(name_of_ordinal.get(int(o), ""), "other"), 0.5
    ))
    patch_rows = []
    for name, (yh, xh) in (("thay", (4352, 9984)), ("spine", (3584, 9216))):
        y0, x0 = yh // 2, xh // 2
        crop_score = numeric_score_arr(idx0[y0:y0 + 512, x0:x0 + 512]).astype(np.float64)
        low = _gf(crop_score, sigma=32)
        hp = crop_score - low
        radial = _radial_autocorr(hp)
        thresh = 1.0 / np.e
        below = np.nonzero(radial < thresh)[0]
        e_fold = int(below[0]) if len(below) else len(radial) - 1
        patch_rows.append({"crop": name, "e_fold_radius_px": e_fold})
        print(f"  {name}: e-fold radius {e_fold} px")
    with (OUT / "vanilla_paint_family_patch_scale.csv").open(
        "w", newline="", encoding="utf-8"
    ) as f:
        w = csv.DictWriter(f, fieldnames=["crop", "e_fold_radius_px"])
        w.writeheader()
        w.writerows(patch_rows)
    patch_sigma = round(float(np.mean([r["e_fold_radius_px"] for r in patch_rows])), 1)
    print(f"  mean e-fold radius (recommended relief_paint_sigma_px): {patch_sigma}")

    # ---------------------------------------------------------------- figure
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        classes_with_data = sorted({r["ck3_terrain"] for r in mi_rows})
        axes_order = ["slope", "curvature", "flow", "elevation"]
        mat = np.zeros((len(classes_with_data), len(axes_order)))
        for r in mi_rows:
            ci = classes_with_data.index(r["ck3_terrain"])
            ai = axes_order.index(r["axis"])
            mat[ci, ai] = r["frac_entropy_explained"]
        fig, ax = plt.subplots(figsize=(6, max(3, 0.35 * len(classes_with_data))))
        im = ax.imshow(mat, cmap="viridis", vmin=0, vmax=max(0.05, mat.max()), aspect="auto")
        ax.set_xticks(range(len(axes_order)))
        ax.set_xticklabels(axes_order)
        ax.set_yticks(range(len(classes_with_data)))
        ax.set_yticklabels(classes_with_data, fontsize=8)
        ax.set_title("vanilla: fraction of in-class material entropy\n"
                      "explained by each relief axis")
        fig.colorbar(im, ax=ax, label="fraction of H(material|class) explained")
        fig.tight_layout()
        fig.savefig(OUT / "vanilla_paint_vs_relief.png", dpi=140)
        plt.close(fig)
        print("wrote vanilla_paint_vs_relief.png")
    except ImportError:
        print("matplotlib not available, skipping figure "
              "(uv run --with matplotlib python scripts/measure_vanilla_relief_paint.py)")

    # ------------------------------------------------------------- narrative
    lines = ["# Vanilla paint vs relief: in-class material variance\n",
             "`scripts/measure_vanilla_relief_paint.py`, "
             f"{n_land:,} vanilla land px, {time.time()-t0:.1f}s.\n",
             "\n## Fraction of in-class material entropy each relief axis explains "
             "(mean over classes with >= 200 land px)\n"]
    by_axis: dict[str, list[float]] = {}
    for r in mi_rows:
        by_axis.setdefault(r["axis"], []).append(r["frac_entropy_explained"])
    for axis_name in ["slope", "curvature", "flow", "elevation"]:
        vals = by_axis.get(axis_name, [])
        if vals:
            lines.append(f"- **{axis_name}**: mean {np.mean(vals):.3f}, "
                          f"max {np.max(vals):.3f} "
                          f"({len(vals)} classes)\n")
    lines.append("\nPer-class detail: `docs/evidence/vanilla_paint_vs_relief_mi.csv`. "
                  "Applied conditional table (slope x curvature x elevation; flow "
                  "dropped, weakest axis everywhere): "
                  "`docs/evidence/vanilla_paint_vs_relief.csv`.\n")
    lines.append(
        "\n## Per-class family palette (coordinator review finding)\n"
        "Reordering a class's existing 2-3 `mappings/terrain_paint.csv` "
        "materials cannot change what a player sees when they are all one "
        "family (`mountains` = mountain_02/mountain_02_c/"
        "mountain_02_d_valleys, all `rock`, `verified`). "
        f"`mappings/relief_paint_family_materials.csv` ({len(family_rows)} "
        "rows) is each class's own real vanilla top material PER FAMILY, "
        "interior pixels only (dist > 5px from a class boundary); "
        "`docs/evidence/vanilla_paint_family_area_shares.csv` is the target "
        "family area distribution `relief_paint.py`'s output should land "
        "within +-30% of, per class.\n"
    )
    lines.append(
        "\n## Patch scale (spatial coherence)\n"
        f"Radial-autocorrelation e-fold radius of a numeric family-score "
        f"field (`scripts/measure_vanilla_colormap_blur.py`'s own method), "
        f"two mountain crops: "
        + ", ".join(f"{r['crop']} {r['e_fold_radius_px']} px" for r in patch_rows)
        + f". Mean **{patch_sigma} px** is `relief_paint_sigma_px`'s default "
        "-- the Gaussian blur width the family CHOICE is smoothed at before "
        "argmax, so the painted result reads as patches at vanilla's own "
        "scale rather than per-pixel noise.\n"
    )
    (OUT / "vanilla_paint_vs_relief.md").write_text("".join(lines), encoding="utf-8")
    print(f"done in {time.time()-t0:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
