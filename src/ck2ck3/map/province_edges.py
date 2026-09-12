"""Organic province borders: a smooth upsample of the CK2 label map.

Lane ``province-edges``.  ``provinces.build_raster`` resizes the CK2 *id*
array with NEAREST, which is the only safe choice on an id array — an
interpolated colour is not a province.  But CK2's ``provinces.bmp`` is
2.90 km per pixel and the CK3 canvas is 1.9543x finer
(``docs/map_scale.md``), so NEAREST turns every province border and every
coastline into a staircase of 2x2 canvas pixels.  That staircase is what the
user sees at close zoom, and it is *upstream* of almost everything else: the
coastline it draws is the water mask the colormap, the water rasters, the
tree eligibility and the heightmap detail pass all read.

The fix is the one interpolation that *is* safe on a label array: upsample
each province's own 0/1 indicator smoothly and give every canvas pixel to
whichever indicator is largest there.  An argmax of indicators is still a
label — no colour is invented, no pixel is left unassigned, and a province
that owned any source pixel still wins somewhere near it.  The boundary
between two provinces becomes the level set where their two blurred
indicators cross, which is a curve.

Three properties this has to have, and how each is got:

* **Bounded.**  A pixel may only take a province that the NEAREST raster
  already painted within ``max_shift_source_px`` CK2 source pixels of it
  (:func:`ck2ck3.map.paint_edges.within_radius`, the same check the paint
  lane uses for terrain classes, ``docs/step_map_paint.md`` §10.2).  Anything
  further reverts to NEAREST, so the invariant is a property of the code.
* **Topology-preserving.**  The province *set* does not change here: the
  weak-province regrow and the lost-province report in
  :mod:`ck2ck3.map.provinces` run after this, on the smoothed array, exactly
  as they ran on the NEAREST one.  :func:`adjacency_pairs` counts what the
  smoothing did to the neighbour graph so the change is reported rather than
  assumed.
* **Deterministic.**  No RNG.  The labels are walked in ``np.unique`` order
  and a tie is decided with a strict ``>``, so the **lowest CK2 id** wins —
  the same tie-break rule the barony growth uses
  (``docs/step_map_baronies.md`` §4), and not whatever order a hash or a
  scan happened to produce.

Pixel-centre alignment, and a bonus.  The smooth sample point for target
pixel ``t`` is ``(t + 0.5) / factor - 0.5`` in source coordinates — the
area-preserving convention, the one ``paint_edges.forest_coverage`` already
uses, and the one ``PIL.Image.resize`` uses for the heightmap.  The NEAREST
path used ``t / factor`` floored instead, which sits about a quarter of a
source pixel off it.  So the smoothed province map is *better* registered
against the LANCZOS heightmap than the NEAREST one was, not worse.

Cost.  Done naively — one blurred indicator plane per province over the whole
canvas — this is 2132 passes over 55 Mpx.  It is tiled instead: inside a
1024-pixel canvas tile only a handful of provinces exist, and only those are
built.  The halo around each tile is wide enough that a tile boundary is
never visible in the result (``_halo_px``).
"""

from __future__ import annotations

import numpy as np
from scipy.ndimage import gaussian_filter

from .config import Canvas

#: sentinel id for "no CK2 province here"; mirrors ``provinces.PADDING``
PADDING = 0


def source_coords(n_target: int, factor: float) -> np.ndarray:
    """Source coordinate of each target pixel centre (float, may be negative).

    The area-preserving convention: target pixel ``t`` samples the source at
    ``(t + 0.5) / factor - 0.5``.  ``PIL.Image.resize`` uses the same one for
    the heightmap, so the two rasters land on the same grid.  Values outside
    ``[0, n_source - 1]`` are legitimate at the border; the caller clamps when
    it gathers.
    """
    return (np.arange(n_target, dtype=np.float64) + 0.5) / factor - 0.5


def _halo_px(sigma_src_px: float) -> int:
    """Source pixels of context a tile needs so its edge is seam-free."""
    return max(2, int(np.ceil(3.0 * max(sigma_src_px, 0.0))) + 2)


def smooth_resize_ids(
    src_ids: np.ndarray,
    canvas: Canvas,
    *,
    sigma_src_px: float = 0.6,
    tile_px: int = 1024,
) -> np.ndarray:
    """NEAREST's replacement: per-province smooth upsample, then argmax.

    ``src_ids`` is the full-size CK2 id array; only ``canvas.crop_*`` of it is
    used, exactly as in :func:`ck2ck3.map.provinces._resize_ids`.  Returns a
    ``(canvas.height, canvas.width)`` int32 array with ``PADDING`` outside the
    scaled region.

    ``sigma_src_px`` is the Gaussian width of each indicator, **in CK2 source
    pixels**, so the shape of a border does not change when the canvas does.
    0 means "bilinear only" — still smooth, because the indicator is
    interpolated, but with the tightest possible ramp.
    """
    if sigma_src_px < 0:
        raise ValueError(f"sigma_src_px must be >= 0, got {sigma_src_px}")
    sh = canvas.crop_height or src_ids.shape[0]
    sw = canvas.crop_width or src_ids.shape[1]
    src = src_ids[
        canvas.crop_y0 : canvas.crop_y0 + sh, canvas.crop_x0 : canvas.crop_x0 + sw
    ]

    th, tw = canvas.scaled_height, canvas.scaled_width
    fy = th / sh
    fx = tw / sw
    ry = source_coords(th, fy)
    rx = source_coords(tw, fx)
    halo = _halo_px(sigma_src_px)

    scaled = np.empty((th, tw), dtype=np.int32)
    for ty0 in range(0, th, tile_px):
        ty1 = min(th, ty0 + tile_px)
        for tx0 in range(0, tw, tile_px):
            tx1 = min(tw, tx0 + tile_px)
            scaled[ty0:ty1, tx0:tx1] = _tile(
                src, ry[ty0:ty1], rx[tx0:tx1], sigma_src_px, halo
            )

    out = np.full((canvas.height, canvas.width), PADDING, dtype=np.int32)
    y0, x0 = canvas.offset_y, canvas.offset_x
    out[y0 : y0 + th, x0 : x0 + tw] = scaled
    return out


def _tile(
    src: np.ndarray,
    ry: np.ndarray,
    rx: np.ndarray,
    sigma_src_px: float,
    halo: int,
) -> np.ndarray:
    """The argmax for one target tile, built from a haloed source window."""
    sh, sw = src.shape
    y0 = max(0, int(np.floor(ry[0])) - halo)
    y1 = min(sh, int(np.ceil(ry[-1])) + halo + 2)
    x0 = max(0, int(np.floor(rx[0])) - halo)
    x1 = min(sw, int(np.ceil(rx[-1])) + halo + 2)
    win = src[y0:y1, x0:x1]

    labels = np.unique(win)
    if labels.size == 1:
        return np.full((ry.size, rx.size), labels[0], dtype=np.int32)

    # bilinear gather weights, shared by every indicator plane of this tile
    wy = np.clip(ry - y0, 0, win.shape[0] - 1)
    wx = np.clip(rx - x0, 0, win.shape[1] - 1)
    iy = np.floor(wy).astype(np.intp)
    ix = np.floor(wx).astype(np.intp)
    iy1 = np.minimum(iy + 1, win.shape[0] - 1)
    ix1 = np.minimum(ix + 1, win.shape[1] - 1)
    ay = (wy - iy).astype(np.float32)[:, None]
    ax = (wx - ix).astype(np.float32)[None, :]

    best = np.zeros((ry.size, rx.size), dtype=np.float32)
    who = np.full((ry.size, rx.size), int(labels[0]), dtype=np.int32)
    for lab in labels.tolist():
        plane = (win == lab).astype(np.float32)
        if sigma_src_px > 0:
            plane = gaussian_filter(plane, sigma_src_px, mode="nearest")
        v = (
            plane[np.ix_(iy, ix)] * ((1 - ay) * (1 - ax))
            + plane[np.ix_(iy1, ix)] * (ay * (1 - ax))
            + plane[np.ix_(iy, ix1)] * ((1 - ay) * ax)
            + plane[np.ix_(iy1, ix1)] * (ay * ax)
        )
        # strict >: the first (lowest) label wins a tie, so the result does
        # not depend on the order numpy happens to return uniques in
        take = v > best
        best = np.where(take, v, best)
        who = np.where(take, np.int32(lab), who)
    return who


# --------------------------------------------------------------------------- #
# the neighbour graph, so a topology change is counted rather than assumed
# --------------------------------------------------------------------------- #
def adjacency_pairs(ids: np.ndarray) -> set[tuple[int, int]]:
    """Unordered pairs of ids that touch 4-connected anywhere on the raster."""
    pairs: set[tuple[int, int]] = set()
    m = int(ids.max()) + 1
    for a, b in (
        (ids[:-1, :], ids[1:, :]),
        (ids[:, :-1], ids[:, 1:]),
    ):
        diff = a != b
        lo = np.minimum(a[diff], b[diff]).astype(np.int64)
        hi = np.maximum(a[diff], b[diff]).astype(np.int64)
        pairs.update(
            (int(k // m), int(k % m)) for k in np.unique(lo * m + hi).tolist()
        )
    return pairs


def adjacency_delta(before: np.ndarray, after: np.ndarray) -> dict[str, int]:
    """How the 4-connected neighbour graph changed between two rasters."""
    a = adjacency_pairs(before)
    b = adjacency_pairs(after)
    return {
        "pairs_before": len(a),
        "pairs_after": len(b),
        "pairs_added": len(b - a),
        "pairs_removed": len(a - b),
    }


def region_area_delta(
    before: np.ndarray, after: np.ndarray, *, tolerance: float = 0.20
) -> dict[str, object]:
    """Ids whose pixel count moved more than ``tolerance``, and by how much.

    Used on the barony raster (``docs/step_map_baronies.md``): the smoothing
    is allowed to reshape a barony, not to halve it.
    """
    ub, cb = np.unique(before, return_counts=True)
    ua, ca = np.unique(after, return_counts=True)
    cnt_b = dict(zip(ub.tolist(), cb.tolist()))
    cnt_a = dict(zip(ua.tolist(), ca.tolist()))
    worst: list[tuple[int, int, int, float]] = []
    for pid, n0 in cnt_b.items():
        if pid == PADDING or n0 == 0:
            continue
        n1 = cnt_a.get(pid, 0)
        rel = (n1 - n0) / float(n0)
        if abs(rel) > tolerance:
            worst.append((int(pid), int(n0), int(n1), round(rel, 4)))
    worst.sort(key=lambda r: abs(r[3]), reverse=True)
    return {
        "ids_before": len([k for k in cnt_b if k != PADDING]),
        "ids_after": len([k for k in cnt_a if k != PADDING]),
        "vanished": sorted(k for k in cnt_b if k != PADDING and k not in cnt_a),
        "tolerance": tolerance,
        "beyond_tolerance": len(worst),
        "worst": worst[:50],
    }
