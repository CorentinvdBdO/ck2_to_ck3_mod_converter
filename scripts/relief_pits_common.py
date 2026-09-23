#!/usr/bin/env python3
"""Lane `relief-pits`: the pit metric, the source bound and the shape metrics.

Three families of measurement, all importable and side-effect free, so the
numbers in `docs/step_map_heightmap.md` §2f/§2g, the invariant script and the
unit tests are one implementation.

**Why a new pit metric at all.** §2d's "cliff-foot excess" (MOAT) is the
*difference* between the trench beside an escarpment and the same statistic
far from one. It went to -116 on Thay while playtest 4 reported the pits had
grown, and both are true: a defect that digs holes *everywhere* raises the
control as fast as it raises the near-cliff number, so their difference says
nothing. The metric here is absolute and has a physical zero -- how far a
finished pixel sits below the lowest value the CK2 source itself carries
within one source pixel.

**The bound.** One CK2 source pixel is 1.9543 canvas px (`docs/map_scale.md`),
so the source's own local minimum over a 3 px square is the lowest height the
author drew anywhere that pixel could have come from. Synthesised detail is
entitled to the per-terrain-class texture amplitude vanilla itself carries
(`docs/evidence/map_fidelity/hf_by_terrain.csv`, ~2x the levels RMS) and no
more: anything deeper is a closed depression the source has no basis for.
"""

from __future__ import annotations

import numpy as np
from scipy.ndimage import (
    gaussian_filter,
    grey_dilation,
    grey_erosion,
    label,
    maximum_filter,
)

#: canvas px per CK2 source px (8005/4096 = 6504/3328, docs/map_scale.md §7)
SOURCE_PX_CANVAS = 1.9543
#: square side, canvas px, that covers one CK2 source pixel in every direction
LOCAL_WINDOW_PX = 3
#: one quantisation riser of the transfer curve, 16-bit levels
QUANT_LEVELS = 277.0125

#: the per-terrain HF texture amplitude the map-fidelity report measured on
#: vanilla (`hf_rms_levels` of docs/evidence/map_fidelity/hf_by_terrain.csv).
#: The bound uses `BOUND_TOLERANCE_SIGMAS` x this.
VANILLA_HF_RMS: dict[str, float] = {
    "desert": 91.2, "desert_mountains": 322.6, "drylands": 96.9,
    "farmlands": 96.7, "floodplains": 106.0, "forest": 110.7, "hills": 213.3,
    "jungle": 120.7, "mountains": 311.4, "oasis": 121.8, "plains": 86.3,
    "steppe": 97.2, "taiga": 70.1, "terraced_hills": 253.2, "wetlands": 70.4,
}
BOUND_TOLERANCE_SIGMAS = 2.0


# --------------------------------------------------------------------------- #
# the pit metric
# --------------------------------------------------------------------------- #
def local_min(a: np.ndarray, size: int = LOCAL_WINDOW_PX) -> np.ndarray:
    return grey_erosion(a.astype(np.float32), size=size, mode="nearest")


def local_max(a: np.ndarray, size: int = LOCAL_WINDOW_PX) -> np.ndarray:
    return grey_dilation(a.astype(np.float32), size=size, mode="nearest")


def pit_depth(source: np.ndarray, output: np.ndarray,
              size: int = LOCAL_WINDOW_PX) -> np.ndarray:
    """``source_local_min - output``: positive where the output dug a hole.

    Measured against the *minimum* over one source pixel rather than the
    source value itself, so a genuine escarpment (where the window spans both
    sides) costs nothing: at the top of a cliff the local minimum is already
    the bottom of it.
    """
    return local_min(source, size) - output.astype(np.float32)


def bump_height(source: np.ndarray, output: np.ndarray,
                size: int = LOCAL_WINDOW_PX) -> np.ndarray:
    """``output - source_local_max``: the pit metric's mirror image."""
    return output.astype(np.float32) - local_max(source, size)


def _tail(v: np.ndarray, prefix: str, riser: float = QUANT_LEVELS) -> dict:
    if v.size == 0:
        return {f"{prefix}_px": 0}
    return {
        f"{prefix}_px": int(v.size),
        f"{prefix}_mean": round(float(v.mean()), 1),
        f"{prefix}_p95": round(float(np.percentile(v, 95)), 1),
        f"{prefix}_p99": round(float(np.percentile(v, 99)), 1),
        f"{prefix}_max": round(float(v.max()), 1),
        f"{prefix}_frac_gt_riser": round(float((v > riser).mean()), 5),
    }


def pit_stats(source: np.ndarray, output: np.ndarray, land: np.ndarray,
              label_: str = "", size: int = LOCAL_WINDOW_PX) -> dict:
    """p95/p99/max of the pit depth and of its mirror, over ``land``."""
    row: dict = {"map": label_} if label_ else {}
    row.update(_tail(pit_depth(source, output, size)[land], "pit"))
    row.update(_tail(bump_height(source, output, size)[land], "bump"))
    return row


#: how wide a closed depression the sink metric is allowed to see, px.
#: 9 px = 13 km: wider than the 2-14 px band the detail pass synthesises,
#: narrower than any real CK2 valley.  Unbounded, the metric reports the
#: depth of the window's own macro basin and says nothing about the detail
#: pass (the plain rescale scores 34,351 on Thay that way, `verified`).
SINK_WIDTH_PX = 9


def closed_depression_depth(a: np.ndarray, land: np.ndarray,
                            width_px: int = SINK_WIDTH_PX) -> np.ndarray:
    """Depth of each pixel's own closed depression, basins up to ``width_px``.

    Morphological reconstruction by erosion: the marker is ``a`` dilated over
    a ``width_px`` window (so it sits at the rim level over any pit narrower
    than that and on ``a`` itself elsewhere), then relaxed down with
    ``f <- max(a, min f over the 4 neighbours)`` until it stops moving. The
    result is the surface water would pond to, and ``f - a`` is the pond's
    depth -- exactly "dipping then coming back up".
    """
    a32 = a.astype(np.float32)
    f = grey_dilation(a32, size=width_px, mode="nearest")
    for _ in range(2 * width_px + 2):
        nb = np.full_like(f, np.inf)
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            s = np.roll(np.roll(f, dy, axis=0), dx, axis=1)
            if dy == 1:
                s[0, :] = f[0, :]
            elif dy == -1:
                s[-1, :] = f[-1, :]
            if dx == 1:
                s[:, 0] = f[:, 0]
            elif dx == -1:
                s[:, -1] = f[:, -1]
            np.minimum(nb, s, out=nb)
        new = np.maximum(a32, nb)
        if np.allclose(new, f, atol=1e-3):
            f = new
            break
        f = new
    return np.where(land, f - a32, 0.0).astype(np.float32)


#: widths (canvas px) the closed-depression *excess* is checked at.  3 is one
#: CK2 source pixel (the §2f bound's own window); 9 and 27 catch a basin the
#: 3 px window cannot, since a 20 km bowl (27 px) or a 13 km one (9 px) both
#: pass a 3 px local-min/max test at every individual pixel while still
#: being, as a whole, a closed loop far deeper than anything the CK2 source
#: draws there (docs/step_map_heightmap.md §2h).
EXCESS_WINDOWS_PX = (3, 9, 27)


def closed_depression_excess(
    source: np.ndarray, output: np.ndarray, land: np.ndarray,
    width_px: int,
) -> np.ndarray:
    """``closed_depression_depth(output) - closed_depression_depth(source)``.

    Elevation alone is not enough to tell "the CK2 author already drew a
    gentle macro basin here" from "the detail pass invented a rampart": a
    genuine 40-90 px CK2 basin can be 7,000+ levels deep in the plain
    rescale too (`verified`, Thaymount). What must not happen is the
    *output*'s own closed-depression reading exceeding the *source*'s own,
    at the same window -- that is depth the pass added on top of what the
    author drew, whatever the total depth already was.
    """
    dep_out = closed_depression_depth(output, land, width_px=width_px)
    dep_src = closed_depression_depth(source, land, width_px=width_px)
    return dep_out - dep_src


def closed_depression_excess_stats(
    source: np.ndarray, output: np.ndarray, land: np.ndarray,
    widths: tuple[int, ...] = EXCESS_WINDOWS_PX,
) -> dict:
    """p95/p99/max/frac>1-riser of the excess, one row of keys per width."""
    row: dict = {}
    for w in widths:
        excess = closed_depression_excess(source, output, land, w)[land]
        if excess.size == 0:
            continue
        row[f"cd_excess_{w}px_p95"] = round(float(np.percentile(excess, 95)), 1)
        row[f"cd_excess_{w}px_p99"] = round(float(np.percentile(excess, 99)), 1)
        row[f"cd_excess_{w}px_max"] = round(float(excess.max()), 1)
        row[f"cd_excess_{w}px_frac_gt_riser"] = round(
            float((excess > QUANT_LEVELS).mean()), 5)
    return row


# --------------------------------------------------------------------------- #
# "vertical black slabs" -- a cliff rendered as a 1-px wall (docs §2h ii)
# --------------------------------------------------------------------------- #
#: the 8 neighbour offsets, axis-aligned first (the coordinator's split)
_AXIS_OFFSETS = ((1, 0), (0, 1))
_DIAG_OFFSETS = ((1, 1), (1, -1))


def _shift(a: np.ndarray, dy: int, dx: int) -> np.ndarray:
    """``a`` shifted by ``(dy, dx)``, edge-padded (never wraps)."""
    return np.pad(a, ((max(dy, 0), max(-dy, 0)), (max(dx, 0), max(-dx, 0))),
                  mode="edge")[
        max(-dy, 0): max(-dy, 0) + a.shape[0],
        max(-dx, 0): max(-dx, 0) + a.shape[1],
    ]


def edge_steps(h: np.ndarray, land: np.ndarray,
               offsets: tuple[tuple[int, int], ...]) -> np.ndarray:
    """Max ``|h[p] - h[neighbour]|`` over ``offsets``, land-to-land pairs only."""
    h = h.astype(np.float64)
    out = np.zeros(h.shape, dtype=np.float64)
    for dy, dx in offsets:
        nb = _shift(h, dy, dx)
        nb_land = _shift(land.astype(np.float64), dy, dx) > 0.5
        d = np.abs(h - nb)
        d[~(land & nb_land)] = 0.0
        np.maximum(out, d, out=out)
        # the other direction of the same offset (pixel on the low side)
        nb2 = _shift(h, -dy, -dx)
        nb2_land = _shift(land.astype(np.float64), -dy, -dx) > 0.5
        d2 = np.abs(h - nb2)
        d2[~(land & nb2_land)] = 0.0
        np.maximum(out, d2, out=out)
    return out


def edge_step_orientation_counts(h: np.ndarray, land: np.ndarray,
                                 k_risers: float,
                                 quant: float = QUANT_LEVELS) -> dict:
    """Land pixels touching a >= ``k_risers`` step, split axis-aligned vs
    diagonal (`_AXIS_OFFSETS` / `_DIAG_OFFSETS`).

    A "vertical black slab" in an oblique render is a near-vertical wall
    face over one pixel of horizontal run -- an *axis-aligned* giant edge,
    counted once whichever of the two axes it runs along, since either one
    reads as a slab from an oblique camera. A real escarpment 2-3 canvas px
    wide (the CK2 source's own cliff width) should split its drop over
    several *diagonal-inclusive* steps, not concentrate it on one
    axis-aligned pair.
    """
    thr = k_risers * quant
    axis = edge_steps(h, land, _AXIS_OFFSETS) >= thr
    diag = edge_steps(h, land, _DIAG_OFFSETS) >= thr
    n_land = max(int(land.sum()), 1)
    return {
        "k_risers": k_risers,
        "axis_aligned_px": int(axis.sum()),
        "diagonal_px": int(diag.sum()),
        "axis_aligned_frac_of_land": round(float(axis.sum()) / n_land, 5),
        "diagonal_frac_of_land": round(float(diag.sum()) / n_land, 5),
        # the ratio the brief asks for: how much more common an axis-aligned
        # giant step is than a diagonal one, at the same threshold
        "axis_over_diag": round(
            float(axis.sum()) / max(float(diag.sum()), 1.0), 2),
    }


#: window (canvas px) the "local relief" a cliff's drop is measured over --
#: the CK2 source's own cliff width after the 1.9543x LANCZOS upsample
#: (2-3 canvas px, docs/step_map_heightmap.md §2h) plus a pixel of margin
CLIFF_WIDTH_PX = 5


def cliff_drop_concentration(source: np.ndarray, output: np.ndarray,
                             land: np.ndarray,
                             cliff_steps: float = 2.0,
                             window: int = CLIFF_WIDTH_PX) -> np.ndarray:
    """Per source-cliff pixel: the output's single biggest neighbour step,
    as a fraction of the output's own local relief over ``window`` px.

    1.0 means the *entire* visible drop at that pixel happens in one
    pixel-to-pixel edge -- a wall, not a slope. A drop spread continuously
    over the source's own ~3 px cliff width reads close to
    ``1 / (pixels along the profile)``, well under 1.

    ``source`` locates *where* a cliff is (so the same set of pixels is
    compared across maps); the ratio itself is read off ``output``, so this
    is comparable between the plain rescale (source, where it is close to 1
    by construction -- a rescaled 8-bit riser lands on exactly one canvas
    pixel pair before any de-terrace), build 17 and any candidate fix.
    """
    cliff = (edge_steps(source, land, _AXIS_OFFSETS + _DIAG_OFFSETS)
             >= cliff_steps * QUANT_LEVELS) & land
    max_step = edge_steps(output, land, _AXIS_OFFSETS + _DIAG_OFFSETS)
    relief = (maximum_filter(output.astype(np.float32), size=window, mode="nearest")
              - grey_erosion(output.astype(np.float32), size=window, mode="nearest"))
    ratio = np.divide(max_step, relief, out=np.zeros_like(max_step),
                      where=relief > 1e-6)
    return np.clip(ratio, 0.0, 1.0)[cliff]


def wall_stats(source: np.ndarray, output: np.ndarray, land: np.ndarray,
              k_list: tuple[float, ...] = (2.0, 3.0, 5.0)) -> dict:
    """One row: orientation counts at each ``k_risers``, plus the drop
    concentration ratio's p50/p95/max on the source's own cliff pixels."""
    row: dict = {}
    for k in k_list:
        oc = edge_step_orientation_counts(output, land, k)
        row[f"axis_over_diag_k{k:g}"] = oc["axis_over_diag"]
        row[f"axis_frac_k{k:g}"] = oc["axis_aligned_frac_of_land"]
        row[f"diag_frac_k{k:g}"] = oc["diagonal_frac_of_land"]
    conc = cliff_drop_concentration(source, output, land)
    if conc.size:
        row["drop_concentration_px"] = int(conc.size)
        row["drop_concentration_p50"] = round(float(np.percentile(conc, 50)), 3)
        row["drop_concentration_p95"] = round(float(np.percentile(conc, 95)), 3)
        row["drop_concentration_max"] = round(float(conc.max()), 3)
    return row


# --------------------------------------------------------------------------- #
# the bound (docs §2f)
# --------------------------------------------------------------------------- #
def tolerance_field(terrain_code: np.ndarray, terrain_keys: list[str],
                    hf_rms: dict[str, float] | None = None,
                    sigmas: float = BOUND_TOLERANCE_SIGMAS) -> np.ndarray:
    """Per-pixel bound tolerance, 16-bit levels, from the terrain class."""
    table = VANILLA_HF_RMS if hf_rms is None else hf_rms
    fallback = float(table.get("plains", 86.3))
    lut = np.array(
        [float(table.get(k, fallback)) * sigmas for k in terrain_keys],
        dtype=np.float32,
    )
    if lut.size == 0:
        return np.full(terrain_code.shape, fallback * sigmas, dtype=np.float32)
    idx = np.clip(terrain_code.astype(np.int32), 0, lut.size - 1)
    return lut[idx]


#: levels of slack the bound check allows for integer rounding: the pass
#: bounds a float array and then rounds it to uint16, so a pixel sitting
#: exactly on the bound can land half a level outside it.
BOUND_ROUNDING_SLACK = 1.0


def bound_violation(source: np.ndarray, output: np.ndarray, land: np.ndarray,
                    tol: np.ndarray | float,
                    size: int = LOCAL_WINDOW_PX,
                    slack: float = BOUND_ROUNDING_SLACK) -> dict:
    """How far the output leaves ``[src_local_min - tol, src_local_max + tol]``."""
    lo = local_min(source, size) - tol - slack
    hi = local_max(source, size) + tol + slack
    o = output.astype(np.float32)
    under = np.maximum(lo - o, 0.0)[land]
    over = np.maximum(o - hi, 0.0)[land]
    n = max(int(land.sum()), 1)
    return {
        "bound_under_frac": round(float((under > 0).sum()) / n, 5),
        "bound_over_frac": round(float((over > 0).sum()) / n, 5),
        "bound_under_p99": round(float(np.percentile(under, 99)), 1)
        if under.size else 0.0,
        "bound_under_max": round(float(under.max()), 1) if under.size else 0.0,
        "bound_over_max": round(float(over.max()), 1) if over.size else 0.0,
    }


# --------------------------------------------------------------------------- #
# shape metrics (docs §2g) -- all dimensionless, all amplitude-free
# --------------------------------------------------------------------------- #
def _hessian(a: np.ndarray, sigma_px: float) -> tuple[np.ndarray, ...]:
    f = gaussian_filter(a.astype(np.float32), sigma_px, mode="nearest")
    gy, gx = np.gradient(f)
    hyy, hyx = np.gradient(gy)
    hxy, hxx = np.gradient(gx)
    return hxx, 0.5 * (hxy + hyx), hyy, gy, gx


def gradient_shape(a: np.ndarray, mask: np.ndarray, km_per_px: float) -> dict:
    """Kurtosis and peakedness of |grad h| -- is the slope spiky or rolling?

    Both are ratios of moments, so they do not move when the whole field is
    scaled: they answer "what shape", not "how tall".
    """
    gy, gx = np.gradient(a.astype(np.float32), km_per_px)
    g = np.hypot(gx, gy)[mask]
    if g.size < 16:
        return {"grad_kurtosis": 0.0, "grad_p99_over_rms": 0.0}
    m, sd = float(g.mean()), float(g.std())
    rms = float(np.sqrt((g ** 2).mean()))
    kurt = float((((g - m) / max(sd, 1e-9)) ** 4).mean()) - 3.0
    return {
        "grad_kurtosis": round(kurt, 3),
        "grad_p99_over_rms": round(float(np.percentile(g, 99)) / max(rms, 1e-9), 3),
        "grad_rms_levels_per_km": round(rms, 1),
    }


def ridge_mask(a: np.ndarray, mask: np.ndarray, sigma_px: float = 1.2,
               curvature_quantile: float = 0.0) -> np.ndarray:
    """Pixels that are crests: a local maximum *across* the ridge direction.

    Pure shape, no amplitude threshold. Take the Hessian's most negative
    eigenvalue and its eigenvector ``v`` (the direction of strongest downward
    curvature, i.e. across the ridge); a crest is a pixel that is at least as
    high as the surface one pixel away in both ``+v`` and ``-v``, with that
    eigenvalue negative. A rolling, smoothly filled surface has few such
    pixels and they do not join up; a ridged field has many and they form
    lines.
    """
    hxx, hxy, hyy, _, _ = _hessian(a, sigma_px)
    tr = hxx + hyy
    root = np.sqrt(np.maximum((hxx - hyy) ** 2 + 4.0 * hxy ** 2, 0.0))
    lam_min = 0.5 * (tr - root)
    # eigenvector of lam_min: (hxy, lam_min - hxx) normalised (fall back to the
    # other form when hxy vanishes)
    vx = np.where(np.abs(hxy) > 1e-12, hxy, lam_min - hyy)
    vy = np.where(np.abs(hxy) > 1e-12, lam_min - hxx, hxy)
    n = np.hypot(vx, vy)
    vx = np.divide(vx, n, out=np.zeros_like(vx), where=n > 1e-12)
    vy = np.divide(vy, n, out=np.zeros_like(vy), where=n > 1e-12)
    f = gaussian_filter(a.astype(np.float32), sigma_px, mode="nearest")
    ys, xs = np.indices(f.shape)
    crest = lam_min < 0
    if curvature_quantile > 0:
        cut = np.quantile(lam_min[mask], curvature_quantile)
        crest &= lam_min <= cut
    for sign in (1.0, -1.0):
        yy = np.clip(ys + sign * vy, 0, f.shape[0] - 1)
        xx = np.clip(xs + sign * vx, 0, f.shape[1] - 1)
        crest &= f >= _bilinear(f, yy, xx) - 1e-6
    return crest & mask


def _bilinear(f: np.ndarray, yy: np.ndarray, xx: np.ndarray) -> np.ndarray:
    y0 = np.floor(yy).astype(np.int32)
    x0 = np.floor(xx).astype(np.int32)
    y1 = np.clip(y0 + 1, 0, f.shape[0] - 1)
    x1 = np.clip(x0 + 1, 0, f.shape[1] - 1)
    ty, tx = yy - y0, xx - x0
    return (f[y0, x0] * (1 - ty) * (1 - tx) + f[y1, x0] * ty * (1 - tx)
            + f[y0, x1] * (1 - ty) * tx + f[y1, x1] * ty * tx)


_EIGHT = np.ones((3, 3), dtype=bool)


def ridge_stats(a: np.ndarray, mask: np.ndarray, sigma_px: float = 1.2) -> dict:
    """Crest share and how long the crest lines run before they break."""
    crest = ridge_mask(a, mask, sigma_px)
    n_land = max(int(mask.sum()), 1)
    lab, count = label(crest, structure=_EIGHT)
    if count == 0:
        return {"ridge_share": 0.0, "ridge_mean_run_px": 0.0,
                "ridge_p90_run_px": 0.0}
    sizes = np.bincount(lab.ravel())[1:]
    return {
        "ridge_share": round(float(crest.sum()) / n_land, 4),
        # mean over *pixels*, not over components: what fraction of a crest
        # pixel's own line is connected to it, which is what "the ridges join
        # up" means visually
        "ridge_mean_run_px": round(
            float((sizes.astype(np.float64) ** 2).sum() / max(sizes.sum(), 1)), 2),
        "ridge_p90_run_px": round(float(np.percentile(sizes, 90)), 2),
    }


#: how far from a water province the shape metrics stay away, px.  A land
#: pixel on a lake shore has a several-thousand-level drop on one side, and
#: that single edge dominates a fourth moment: measured on the Thaymount crop,
#: not eroding the mask reports gradient kurtosis 101 where the interior
#: carries 22 (`verified`).  CLAUDE.md's own rule, applied to shape as well as
#: to spectrum: measure on all-land interior, never across a coastline.
SHAPE_MASK_ERODE_PX = 4


def shape_metrics(a: np.ndarray, mask: np.ndarray, km_per_px: float,
                  hp_sigma_px: float = 8.0,
                  erode_px: int = SHAPE_MASK_ERODE_PX) -> dict:
    """Every shape number this lane reports, on the high-passed field.

    High-passed for the same reason the structure metrics are: the question
    is the shape of the *texture*, and a crop's macro tilt would otherwise
    dominate both the gradient moments and the curvature sign.  Measured on
    the mask eroded by ``erode_px``, so a water-province edge -- which is a
    one-pixel drop of thousands of levels, by the engine's own rule -- does
    not stand in for mountain texture.
    """
    from scipy.ndimage import binary_erosion

    f = a.astype(np.float32)
    hp = f - gaussian_filter(f, hp_sigma_px, mode="nearest")
    m = mask
    if erode_px > 0 and not mask.all():
        m = binary_erosion(mask, np.ones((3, 3), bool), iterations=erode_px)
        if m.sum() < 0.05 * max(mask.sum(), 1):
            m = mask
    out = gradient_shape(hp, m, km_per_px)
    out.update(ridge_stats(hp, m))
    out["shape_px"] = int(m.sum())
    return out


def local_relief(a: np.ndarray, mask: np.ndarray, size: int = 5) -> dict:
    """p95 of (local max - local min) -- the amplitude the shape sits on."""
    r = (maximum_filter(a.astype(np.float32), size=size, mode="nearest")
         - grey_erosion(a.astype(np.float32), size=size, mode="nearest"))[mask]
    if r.size == 0:
        return {"local_relief_p95": 0.0}
    return {"local_relief_p95": round(float(np.percentile(r, 95)), 1)}


# --------------------------------------------------------------------------- #
# per-pixel terrain class, read back off a generated mod
# --------------------------------------------------------------------------- #
def terrain_codes_from_mod(mod_dir, ys: slice, xs: slice):
    """``(code array, keys)`` for a crop, from a generated mod's own files.

    `common/province_terrain/*.txt` (`<province id>=<terrain key>`) indexed
    through `map_data/definition.csv` and `provinces.png` -- the same table
    `ck2ck3.map.build` hands the detail pass, but readable without running a
    conversion, so the study scripts and the pass agree on the class of every
    pixel.
    """
    from pathlib import Path

    from PIL import Image

    mod = Path(mod_dir)
    terr: dict[int, str] = {}
    default_land = "plains"
    for txt in sorted((mod / "common/province_terrain").glob("*.txt")):
        for line in txt.read_text(encoding="utf-8-sig").splitlines():
            line = line.split("#", 1)[0].strip()
            if "=" not in line:
                continue
            k, _, v = line.partition("=")
            k, v = k.strip(), v.strip()
            if k == "default_land":
                default_land = v
            elif k.isdigit():
                terr[int(k)] = v
    rgb_to_id: dict[int, int] = {}
    for line in (mod / "map_data/definition.csv").read_text(
            encoding="utf-8", errors="replace").splitlines():
        p = line.split(";")
        if len(p) < 5 or not p[0].isdigit():
            continue
        pid = int(p[0])
        if pid:
            rgb_to_id[(int(p[1]) << 16) | (int(p[2]) << 8) | int(p[3])] = pid
    with Image.open(mod / "map_data/provinces.png") as im:
        prov = np.asarray(im.convert("RGB"))[ys, xs]
    key = ((prov[..., 0].astype(np.int64) << 16)
           | (prov[..., 1].astype(np.int64) << 8) | prov[..., 2])
    keys = sorted({default_land} | set(terr.values()))
    index = {k: i for i, k in enumerate(keys)}
    code = np.full(key.shape, index[default_land], dtype=np.int16)
    for rgb, pid in rgb_to_id.items():
        t = terr.get(pid)
        if t is None or t == default_land:
            continue
        code[key == rgb] = index[t]
    return code, keys


# --------------------------------------------------------------------------- #
# where the pits are: the three zones the passes own
# --------------------------------------------------------------------------- #
def pit_by_zone(source: np.ndarray, output: np.ndarray, land: np.ndarray,
                river_body: np.ndarray | None = None,
                coast_px: float = 5.0, river_px: float = 4.0,
                size: int = LOCAL_WINDOW_PX) -> list[dict]:
    """The pit metric split into coast band / river band / plateau interior.

    Two of the four passes are *allowed* to sit below the source: pass 4
    blends the first few land pixels toward the water level (beaches), and
    pass 3 carves a river valley.  Both are deliberate and both look like a
    pit to an absolute metric, so a diagnosis has to separate them from the
    interior -- which is where a flat CK2 plateau has no excuse for a hole.
    """
    from scipy.ndimage import distance_transform_edt

    d_water = distance_transform_edt(land).astype(np.float32)
    zones = {"coast_band": land & (d_water <= coast_px)}
    if river_body is not None and river_body.any():
        d_river = distance_transform_edt(~river_body).astype(np.float32)
        zones["river_band"] = land & (d_water > coast_px) & (d_river <= river_px)
        rest = land & (d_water > coast_px) & (d_river > river_px)
    else:
        rest = land & (d_water > coast_px)
    zones["interior"] = rest
    depth = pit_depth(source, output, size)
    rows = []
    n_land = max(int(land.sum()), 1)
    for name, m in zones.items():
        row = {"zone": name, "share_of_land": round(float(m.sum()) / n_land, 4)}
        row.update(_tail(depth[m], "pit"))
        rows.append(row)
    return rows
