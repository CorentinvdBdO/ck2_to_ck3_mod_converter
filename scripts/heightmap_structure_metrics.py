#!/usr/bin/env python3
"""Structure metrics for a heightmap crop: is the detail *landscape* or gravel?

Two numbers, both computed on the **high-passed** field (so macro relief does
not decide the answer) and both dimensionless, so a vanilla crop at 0.742
km/px and one of ours at 1.4839 km/px can be compared after the vanilla crop
is halved to our pixel size:

* ``coherence`` -- mean structure-tensor coherence
  ``(l1 - l2) / (l1 + l2)`` of the gradient field over a small window.
  Isotropic noise has no preferred direction, so l1 ~ l2 and coherence -> 0;
  ridge lines and valley walls are locally one-dimensional, so it -> 1.
* ``drain_top1_share`` / ``accum_tail_exponent`` -- drainage statistics of an
  MFD flow accumulation on the crop.  A dendritic network concentrates flow:
  a few channel pixels carry most of the catchment, so the top 1 % of pixels
  by accumulation hold a large share of the total, and the exceedance
  distribution ``P(A > a)`` follows a power law (Hack / Horton), fitted here
  over the middle two decades.  Gravel drains nowhere: every pixel is a local
  pit or a local peak, the share collapses toward 1 % and the tail is steep.

Usage:  uv run scripts/heightmap_structure_metrics.py --help
"""
from __future__ import annotations

import numpy as np
from scipy.ndimage import gaussian_filter

#: 8-neighbour offsets and their pixel distances
NB = [(-1, 0, 1.0), (1, 0, 1.0), (0, -1, 1.0), (0, 1, 1.0),
      (-1, -1, 1.41421356), (-1, 1, 1.41421356),
      (1, -1, 1.41421356), (1, 1, 1.41421356)]


def shift(a: np.ndarray, dy: int, dx: int, fill: float = 0.0) -> np.ndarray:
    """``a`` translated by ``(dy, dx)``, edges filled with ``fill`` (no wrap)."""
    out = np.full_like(a, fill)
    ys = slice(max(0, dy), a.shape[0] + min(0, dy))
    yd = slice(max(0, -dy), a.shape[0] + min(0, -dy))
    xs = slice(max(0, dx), a.shape[1] + min(0, dx))
    xd = slice(max(0, -dx), a.shape[1] + min(0, -dx))
    out[yd, xd] = a[ys, xs]
    return out


def high_pass(a: np.ndarray, sigma_px: float) -> np.ndarray:
    return a.astype(np.float32) - gaussian_filter(a.astype(np.float32), sigma_px,
                                                  mode="nearest")


def coherence(a: np.ndarray, mask: np.ndarray, hp_sigma_px: float = 8.0,
              win_sigma_px: float = 3.0) -> float:
    """Mean structure-tensor coherence of the high-passed field over ``mask``."""
    d = high_pass(a, hp_sigma_px)
    gy, gx = np.gradient(d)
    jxx = gaussian_filter(gx * gx, win_sigma_px, mode="nearest")
    jyy = gaussian_filter(gy * gy, win_sigma_px, mode="nearest")
    jxy = gaussian_filter(gx * gy, win_sigma_px, mode="nearest")
    tr = jxx + jyy
    root = np.sqrt(np.maximum((jxx - jyy) ** 2 + 4 * jxy ** 2, 0.0))
    with np.errstate(invalid="ignore", divide="ignore"):
        c = np.where(tr > 1e-9, root / tr, 0.0)
    return float(np.clip(c, 0, 1)[mask].mean())


def flow_accumulation(a: np.ndarray, mask: np.ndarray, iters: int = 64,
                      p: float = 1.1) -> np.ndarray:
    """Multiple-flow-direction accumulation, relaxed ``iters`` times.

    Relaxation rather than a topological sweep: ``A <- 1 + sum_j w_(j->p) A_j``
    propagates one pixel downstream per pass, is pure array arithmetic, and
    ``iters`` sets the largest catchment the metric can see -- which is what we
    want, since the structure under test lives at 1-20 km (2-14 px).
    """
    h = a.astype(np.float32)
    ws, tot = [], np.zeros_like(h)
    for dy, dx, dist in NB:
        s = np.maximum(h - shift(h, dy, dx, fill=np.inf), 0.0) / dist
        w = np.where(np.isfinite(s), s, 0.0) ** p
        ws.append(w)
        tot += w
    ws = [w / np.maximum(tot, 1e-12) for w in ws]
    acc = mask.astype(np.float32)
    for _ in range(iters):
        nxt = mask.astype(np.float32).copy()
        for (dy, dx, _), w in zip(NB, ws):
            # pixel q sends w_d(q)*A(q) to q+d, so p receives it from p-d
            nxt += shift(w * acc, -dy, -dx)
        acc = nxt
    return acc


def drainage_stats(a: np.ndarray, mask: np.ndarray, hp_sigma_px: float = 8.0,
                   iters: int = 64) -> dict:
    """Share of total accumulation held by the top 1 %, and the tail exponent."""
    acc = flow_accumulation(high_pass(a, hp_sigma_px), mask, iters=iters)
    v = np.sort(acc[mask])[::-1]
    if v.size == 0 or v.sum() <= 0:
        return {"drain_top1_share": 0.0, "accum_tail_exponent": 0.0}
    k = max(1, int(0.01 * v.size))
    share = float(v[:k].sum() / v.sum())
    # exceedance power law over the middle of the range
    ranks = np.arange(1, v.size + 1) / v.size
    lo, hi = int(0.002 * v.size), int(0.2 * v.size)
    lo = max(lo, 1)
    x, y = np.log(v[lo:hi]), np.log(ranks[lo:hi])
    ok = np.isfinite(x) & np.isfinite(y)
    beta = float(-np.polyfit(x[ok], y[ok], 1)[0]) if ok.sum() > 8 else 0.0
    return {"drain_top1_share": share, "accum_tail_exponent": beta}


def all_metrics(a: np.ndarray, mask: np.ndarray, hp_sigma_px: float = 8.0) -> dict:
    out = {"coherence": coherence(a, mask, hp_sigma_px)}
    out.update(drainage_stats(a, mask, hp_sigma_px))
    return out


def hillshade(a: np.ndarray, km_per_px: float, azimuth: float = 315.0,
              altitude: float = 35.0, z_scale: float = 1.0) -> np.ndarray:
    """8-bit hillshade, levels -> metres assumed 1:1 (relative look only)."""
    gy, gx = np.gradient(a.astype(np.float32), km_per_px * 1000.0)
    gy, gx = gy * z_scale, gx * z_scale
    slope = np.arctan(np.hypot(gx, gy))
    aspect = np.arctan2(-gx, gy)
    az, al = np.radians(360.0 - azimuth + 90.0), np.radians(altitude)
    shade = (np.sin(al) * np.cos(slope)
             + np.cos(al) * np.sin(slope) * np.cos(az - aspect))
    return np.clip(shade * 255.0, 0, 255).astype(np.uint8)


def channel_alignment(a: np.ndarray, mask: np.ndarray, coarse_sigma_px: float = 6.0,
                      fine_sigma_px: float = 2.5, top_fraction: float = 0.02,
                      iters: int = 48) -> float:
    """How far the *fine* detail sits below the *coarse* drainage network.

    The discriminator the other two metrics turned out not to be.  Coherence
    and drainage concentration are properties of any smooth random field --
    measured on the shipped isotropic map they already match vanilla -- because
    a band-limited Gaussian field does have locally 1-D structure and does
    drain somewhere.  What it does *not* have is self-similarity across scale:
    detail generated independently of the surface it is added to knows nothing
    about where the larger valleys are.

    So: route flow on the surface smoothed at ``coarse_sigma_px``, take the top
    ``top_fraction`` of pixels by accumulation as the coarse channel network,
    and report the mean of the ``fine_sigma_px`` high-pass over those pixels in
    units of its own standard deviation.  A real landscape's fine gullies run
    down inside its big valleys, so the number is strongly negative; noise
    bolted onto a smooth base gives ~0.
    """
    f = a.astype(np.float32)
    coarse = gaussian_filter(f, coarse_sigma_px, mode="nearest")
    acc = flow_accumulation(coarse, mask, iters=iters)
    fine = f - gaussian_filter(f, fine_sigma_px, mode="nearest")
    sd = float(fine[mask].std())
    if sd <= 0:
        return 0.0
    vals = acc[mask]
    if vals.size == 0:
        return 0.0
    cut = float(np.quantile(vals, 1.0 - top_fraction))
    sel = mask & (acc >= cut)
    if not sel.any():
        return 0.0
    return float(fine[sel].mean() / sd)
