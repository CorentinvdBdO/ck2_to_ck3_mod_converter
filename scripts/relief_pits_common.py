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
