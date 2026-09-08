"""Multi-source geodesic Voronoi on a pixel mask.

This is the "growth" half of the barony method (``docs/design_map.md`` §B.3).
Given one seed pixel per barony and a raster that says which CK2 county each
pixel belongs to, it grows every barony outwards one pixel at a time, so a
barony can only ever take pixels that are **connected to its seed through its
own county**.

Why geodesic and not a plain Euclidean Voronoi: a Euclidean partition would let
a barony on one side of a bay claim pixels on the other side, or jump a
mountain range that the county wraps around.  Straight-line distance is not
what an army walks.

Why a frontier BFS and not ``scipy.ndimage.watershed_ift``: every pixel enters
the frontier exactly once, so the cost is O(pixels) rather than
O(area x radius), it needs no cost image, and — the reason that decided it —
the tie-break is ours and therefore deterministic.  Two baronies that reach a
pixel on the same step: the lower label wins, always.  Determinism is a
requirement of the whole converter (``docs/design_map.md`` §B.7).

The BFS is 4-connected.  8-connected growth would leak across a one-pixel
diagonal isthmus, which is exactly the coastline artefact the rescale creates.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np


def geodesic_voronoi(
    groups: np.ndarray,
    seeds: Sequence[tuple[int, int, int]],
) -> np.ndarray:
    """Grow ``seeds`` over ``groups``; returns a label array of the same shape.

    ``groups`` is the parent id per pixel (0 = not assignable, e.g. water or
    another county's land).  ``seeds`` is ``(y, x, label)`` with ``label >= 1``.
    A seed on a pixel whose group is 0 is ignored — the caller is expected to
    have snapped it onto the mask first.

    Labels never cross a group boundary, so two counties can be grown in the
    same call without interfering, which is how the whole map is done in one
    pass.
    """
    if groups.ndim != 2:
        raise ValueError(f"groups must be 2-D, got shape {groups.shape}")
    h, w = groups.shape
    g = groups.reshape(-1)
    labels = np.zeros(h * w, dtype=np.int32)

    starts: list[int] = []
    start_labels: list[int] = []
    for y, x, label in seeds:
        if label < 1:
            raise ValueError(f"seed label must be >= 1, got {label}")
        if not (0 <= y < h and 0 <= x < w):
            continue
        flat = y * w + x
        if g[flat] == 0:
            continue
        starts.append(flat)
        start_labels.append(label)
    if not starts:
        return labels.reshape(h, w)

    frontier = np.asarray(starts, dtype=np.int64)
    front_labels = np.asarray(start_labels, dtype=np.int32)
    frontier, front_labels = _first_wins(frontier, front_labels)
    labels[frontier] = front_labels

    while frontier.size:
        cand_list: list[np.ndarray] = []
        lab_list: list[np.ndarray] = []
        col = frontier % w
        for shift, keep in (
            (-w, frontier >= w),
            (w, frontier < (h - 1) * w),
            (-1, col > 0),
            (1, col < w - 1),
        ):
            src = frontier[keep]
            if src.size == 0:
                continue
            nb = src + shift
            # unclaimed, and inside the same group as the pixel it came from
            ok = (labels[nb] == 0) & (g[nb] == g[src])
            if not ok.any():
                continue
            cand_list.append(nb[ok])
            lab_list.append(front_labels[keep][ok])
        if not cand_list:
            break
        cand = np.concatenate(cand_list)
        cand_labels = np.concatenate(lab_list)
        cand, cand_labels = _first_wins(cand, cand_labels)
        labels[cand] = cand_labels
        frontier, front_labels = cand, cand_labels
    return labels.reshape(h, w)


def _first_wins(
    flat: np.ndarray, labels: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Deduplicate ``flat``, keeping the lowest label for each pixel."""
    order = np.lexsort((labels, flat))
    flat, labels = flat[order], labels[order]
    keep = np.empty(flat.size, dtype=bool)
    keep[0] = True
    np.not_equal(flat[1:], flat[:-1], out=keep[1:])
    return flat[keep], labels[keep]


def farthest_point(
    pixels: np.ndarray,
    width: int,
    chosen: Sequence[int],
    *,
    bias: np.ndarray | None = None,
    bias_gain: float = 0.5,
) -> int:
    """Pick the pixel of ``pixels`` farthest from every already-``chosen`` one.

    ``pixels`` and ``chosen`` are flat indices into an array of row length
    ``width``.  ``bias`` is a boolean array parallel to ``pixels``; a biased
    pixel's distance is multiplied by ``1 + bias_gain``, so a hill or a stretch
    of coast wins over a marginally more distant field.  Distance is Euclidean
    here on purpose: this only has to *place* the seed, and the growth step
    afterwards is what has to respect the geography.

    Ties go to the lowest flat index, so the result never depends on the order
    numpy happens to scan in.
    """
    if pixels.size == 0:
        raise ValueError("cannot sample a seed from an empty pixel set")
    py, px = pixels // width, pixels % width
    if chosen:
        c = np.asarray(chosen, dtype=np.int64)
        cy, cx = c // width, c % width
        d2 = np.full(pixels.size, np.inf)
        for y, x in zip(cy.tolist(), cx.tolist()):
            np.minimum(d2, (py - y) ** 2 + (px - x) ** 2, out=d2)
        score = np.sqrt(d2)
    else:
        # no seed yet: start from the pixel nearest the county's centre of mass,
        # so a one-barony county gets a sane capital instead of a corner pixel
        cy, cx = py.mean(), px.mean()
        score = -np.sqrt((py - cy) ** 2 + (px - cx) ** 2)
    if bias is not None and bias.any():
        score = np.where(bias, score * (1.0 + bias_gain), score)
    return int(pixels[int(np.argmax(score))])


def snap_to_mask(
    flat: int, mask_pixels: np.ndarray, width: int, *, max_distance: int
) -> int | None:
    """Nearest pixel of ``mask_pixels`` to ``flat``, or ``None`` if too far.

    Used for seeds that come from outside the pipeline (an override row, a
    gazetteer entry, a rescaled CK2 ``positions.txt`` coordinate): they are
    given in canvas pixels and may land a few pixels off the county, on a
    coastline that moved in the rescale.  Snapping is honest as long as the
    distance is bounded and the bound is reported.
    """
    if mask_pixels.size == 0:
        return None
    y, x = flat // width, flat % width
    my, mx = mask_pixels // width, mask_pixels % width
    d2 = (my - y) ** 2 + (mx - x) ** 2
    i = int(np.argmin(d2))
    if d2[i] > max_distance * max_distance:
        return None
    return int(mask_pixels[i])
