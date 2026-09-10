"""Soft, relief-aware terrain-class edges for the CK3 runtime paint.

Why this module exists (playtest of build 13, `docs/step_map_paint.md` §10):
the map reads as pixel art at close zoom.  Two measured causes, both in the
paint pipeline this module replaces:

1. **Nearest-neighbour class edges.**  ``terrain.bmp`` is 2.90 km/px and the
   converter resamples it NEAREST onto a canvas 1.954x finer, so every CK2
   terrain-class boundary is a 2x2-canvas-pixel staircase.  At
   ``terrain_paint_scale = 0.5`` one paint pixel is 2.97 km, so the staircase
   *is* the paint grid.
2. **A noise dither instead of a blend.**  :func:`ck2ck3.map.terrain_paint
   .build_layers` mixed exactly two materials per pixel with a class-agnostic
   Gaussian noise field, so the blend never followed the class boundary at
   all — 2.000 non-zero `detail_intensity` channels per land pixel against
   vanilla's 3.467, entropy 0.73 bits against 1.49, primary weight 0.71
   against 0.52 (`docs/evidence/report_map_paint/paint_blend.csv`).

What this module does instead, in one pass:

* **Distance-field class blend.**  Each CK3 terrain class gets a smooth mask
  (a Gaussian of its own 0/1 indicator, σ = ``sigma_px`` canvas pixels).  The
  two strongest classes at a pixel set the blend, so a class boundary is a
  ramp several pixels wide rather than a step, and the ramp follows the
  boundary's shape instead of a noise field.
* **A material *mix* per class, not a pair.**  ``mappings/terrain_paint.csv``
  may name a third material and explicit weights; the mix is vanilla's own
  measured interior composition for that terrain key, so an interior pixel
  already carries 3 materials at vanilla-like weights and a boundary pixel 4.
  This is the "third material" item `docs/report_map_paint.md` §7.3 left open.
* **Relief-aware boundaries.**  The class map is warped by an integer
  displacement field derived from the heightmap gradient before it is
  blended, so a forest/plains edge wanders with the ground instead of with
  the CK2 pixel grid.  The displacement is bounded by construction
  (``|d| <= relief_shift_px`` canvas pixels), which is the macro invariant:
  a class must never migrate more than one CK2 source pixel (2.90 km = 1.95
  canvas px) from where CK2 painted it.  :func:`class_displacement_stats`
  measures what actually happened.

The class *map* is untouched: CK2 still decides what is where.  Only the
sub-pixel shape of the boundary and the material mix at a pixel change.
"""

from __future__ import annotations

import csv
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.ndimage import distance_transform_edt, gaussian_filter

#: Fallback interior mix when a row of ``mappings/terrain_paint.csv`` names no
#: weights.  Measured against vanilla's own interior bake (see
#: ``docs/evidence/paint_edges/vanilla_blend_measurements.md``); two-material
#: rows fall back to the first two entries, renormalised.
DEFAULT_MIX_WEIGHTS = (0.52, 0.28, 0.20)

#: rows are (material column, weight column) in the extended CSV.
_MIX_COLUMNS = (
    ("primary_material", "primary_weight"),
    ("secondary_material", "secondary_weight"),
    ("tertiary_material", "tertiary_weight"),
)

#: how many `detail_index` / `detail_intensity` channels the format has.
MAX_CHANNELS = 4


# --------------------------------------------------------------------------- #
# the material mix table
# --------------------------------------------------------------------------- #
def read_material_mix(
    path: str | Path,
    *,
    default_weights: Sequence[float] = DEFAULT_MIX_WEIGHTS,
) -> dict[str, list[tuple[str, float]]]:
    """``mappings/terrain_paint.csv`` -> CK3 terrain key -> [(material, weight)].

    Backwards compatible with the two-column table this repo shipped before
    lane `paint-edges`: ``tertiary_material`` and the three ``*_weight``
    columns are optional.  A row with no weights takes ``default_weights``
    truncated to the materials it does name and renormalised, so an old table
    still produces a valid (heavier-primary) mix.  Weights are always
    normalised to sum to 1 and sorted descending, which the blend relies on.
    ``#`` comment lines are skipped like every other reader in this repo.
    """
    p = Path(path)
    if not p.exists():
        return {}
    with p.open("r", encoding="utf-8", newline="") as fh:
        lines = [line for line in fh if not line.lstrip().startswith("#")]
    out: dict[str, list[tuple[str, float]]] = {}
    for row in csv.DictReader(lines):
        key = (row.get("ck3_terrain") or "").strip()
        if not key:
            continue
        mats: list[str] = []
        weights: list[float | None] = []
        for mat_col, w_col in _MIX_COLUMNS:
            mat = (row.get(mat_col) or "").strip()
            if not mat:
                continue
            mats.append(mat)
            raw = (row.get(w_col) or "").strip()
            weights.append(float(raw) if raw else None)
        if not mats:
            continue
        if any(w is None for w in weights):
            weights = [float(w) for w in list(default_weights)[: len(mats)]]
        vals = [max(0.0, float(w)) for w in weights]  # type: ignore[arg-type]
        total = sum(vals)
        if total <= 0:
            vals = [1.0] + [0.0] * (len(mats) - 1)
            total = 1.0
        mix = sorted(
            ((m, v / total) for m, v in zip(mats, vals) if v > 0),
            key=lambda t: -t[1],
        )
        out[key] = mix
    return out


# --------------------------------------------------------------------------- #
# relief-aware displacement field
# --------------------------------------------------------------------------- #
def relief_warp(
    heights: np.ndarray,
    shape: tuple[int, int],
    *,
    shift_px: float,
    sigma_px: float = 8.0,
    land_mask: np.ndarray | None = None,
    gradient_percentile: float = 90.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Integer (dy, dx) per canvas pixel, from the heightmap's own gradient.

    The class map is *sampled through* this field (:func:`warp_apply`) before
    it is blended, so a class boundary follows the ground instead of the CK2
    pixel grid.  Three properties this has to have, and how each is got:

    * **Bounded.**  ``|d| <= shift_px`` by construction (the unit gradient is
      scaled by a saturating factor in ``[0, 1]``, then rounded), so the
      macro invariant — a class never migrates more than one CK2 source pixel
      — is a property of the code, not of the data.
    * **Zero on flat ground.**  The saturating factor is ``|∇h| /
      gradient_ref`` clipped to 1, with ``gradient_ref`` the
      ``gradient_percentile``-th percentile of the land gradient magnitude.
      Where there is no relief there is no displacement, so a plains/steppe
      boundary stays exactly where CK2 put it.
    * **Deterministic.**  No RNG: the field is a function of the heightmap.

    ``heights`` may be at a whole multiple of the canvas resolution (CK3's
    ``resolution_factor``); it is strided down to ``shape``.  Returns two
    ``int8`` arrays, which is the honest precision: the class map is integer
    and is sampled nearest, so a sub-pixel warp would be discarded anyway.
    """
    h, w = shape
    hh, hw = heights.shape[:2]
    fy = max(1, hh // h)
    fx = max(1, hw // w)
    z = heights[: h * fy : fy, : w * fx : fx].astype(np.float32, copy=True)
    if z.shape != (h, w):  # pragma: no cover - defensive, non-integer factors
        z = np.asarray(z, dtype=np.float32)[:h, :w]
    if shift_px <= 0:
        zero = np.zeros((h, w), dtype=np.int8)
        return zero, zero.copy()
    if sigma_px > 0:
        z = gaussian_filter(z, sigma_px, output=z)
    gy, gx = np.gradient(z)
    del z
    mag = np.hypot(gy, gx)
    if land_mask is not None and land_mask.shape == mag.shape:
        sample = mag[land_mask]
    else:
        sample = mag
    ref = float(np.percentile(sample, gradient_percentile)) if sample.size else 0.0
    del sample
    if ref <= 0:
        zero = np.zeros((h, w), dtype=np.int8)
        return zero, zero.copy()
    scale = np.clip(mag / ref, 0.0, 1.0)
    inv = 1.0 / np.maximum(mag, 1e-6)
    del mag
    dyf = shift_px * gy * inv * scale
    dxf = shift_px * gx * inv * scale
    dy = np.rint(dyf)
    dx = np.rint(dxf)
    # rounding each component independently can push the *vector* past the
    # bound ((1.5, 1.5) -> (2, 2) is 2.83 px, not 2); truncating towards zero
    # there can only shorten it, so |d| <= shift_px stays a property of the
    # code rather than of the data.
    over = np.hypot(dy, dx) > shift_px + 1e-9
    if over.any():
        dy = np.where(over, np.trunc(dyf), dy)
        dx = np.where(over, np.trunc(dxf), dx)
    return dy.astype(np.int8), dx.astype(np.int8)


def warp_apply(
    arr: np.ndarray, dy: np.ndarray, dx: np.ndarray, *, chunk_rows: int = 1024
) -> np.ndarray:
    """Sample ``arr`` at ``(y + dy, x + dx)``, clamped at the border.

    Chunked over rows so a 56 Mpx canvas never materialises a 64-bit index
    grid of its own.
    """
    h, w = arr.shape[:2]
    out = np.empty_like(arr)
    cols = np.arange(w, dtype=np.int32)
    for y0 in range(0, h, chunk_rows):
        y1 = min(h, y0 + chunk_rows)
        rows = np.arange(y0, y1, dtype=np.int32)[:, None]
        yy = np.clip(rows + dy[y0:y1], 0, h - 1)
        xx = np.clip(cols[None, :] + dx[y0:y1], 0, w - 1)
        out[y0:y1] = arr[yy, xx]
    return out


# --------------------------------------------------------------------------- #
# the blend
# --------------------------------------------------------------------------- #
@dataclass
class SoftBlend:
    #: HxWx4 uint8 — material ordinals, channel 0 the heaviest
    index: np.ndarray
    #: HxWx4 uint8 — their weights, summing to exactly 255 on every pixel
    intensity: np.ndarray
    #: HxW uint8 — the winning class index per pixel, after the warp+blend
    class_index: np.ndarray
    #: class index -> CK3 terrain key
    class_names: list[str]
    #: HxW uint8 — the class index CK2 painted (no warp, no blend), the
    #: baseline :func:`class_displacement_stats` measures against
    class_index_hard: np.ndarray
    #: blend statistics over ``land_mask`` (or the whole canvas)
    stats: dict[str, float]


def _class_of_code(
    code_names: Sequence[str], table: dict[str, str], default: str
) -> tuple[np.ndarray, list[str]]:
    """CK2 category code -> compact CK3-class index, plus the class names."""
    keys = [table.get(name, default) if name else default for name in code_names]
    names = sorted(set(keys))
    order = {k: i for i, k in enumerate(names)}
    return np.array([order[k] for k in keys], dtype=np.uint8), names


def _mix_arrays(
    class_names: Sequence[str],
    material_mix: dict[str, list[tuple[str, float]]],
    ordinals: dict[str, int],
    *,
    default: str,
    missing_material: set[str],
    missing_ordinal: set[str],
) -> tuple[np.ndarray, np.ndarray]:
    """(nclasses, 4) ordinal + weight tables, weights descending, sum 1."""
    n = len(class_names)
    ords = np.zeros((n, MAX_CHANNELS), dtype=np.uint8)
    ws = np.zeros((n, MAX_CHANNELS), dtype=np.float32)
    fallback = material_mix.get(default) or [("plains_01", 1.0)]
    for i, key in enumerate(class_names):
        mix = material_mix.get(key)
        if not mix:
            missing_material.add(key)
            mix = fallback
        for j, (mat, weight) in enumerate(mix[:MAX_CHANNELS]):
            o = ordinals.get(mat)
            if o is None:
                missing_ordinal.add(mat)
                o = 0
            ords[i, j] = o
            ws[i, j] = weight
        total = float(ws[i].sum())
        if total > 0:
            ws[i] /= total
    return ords, ws


def _quantise_to_255(w: np.ndarray, step: int) -> np.ndarray:
    """(n, 4) float weights summing to ~1 -> uint8 channels summing to 255.

    Quantising each channel independently and letting the residual land on
    the heaviest channel is what keeps the runtime's ``materials_limit``
    sum-to-255 contract exact while still zeroing the tiny fourth channels a
    smooth blend produces (which is what makes the RLE layer compress).
    """
    total = np.maximum(w.sum(axis=1, keepdims=True), 1e-9)
    raw = w / total * 255.0
    if step > 1:
        q = np.rint(raw / step) * step
    else:
        q = np.rint(raw)
    q = np.clip(q, 0.0, 255.0)
    out = q.astype(np.int32)
    lead = np.argmax(out, axis=1)
    rows = np.arange(out.shape[0])
    out[rows, lead] += 255 - out.sum(axis=1)
    np.clip(out, 0, 255, out=out)
    # a clip can only ever have removed weight; give the remainder back to the
    # heaviest channel that still has room (at most one more pass is needed).
    short = 255 - out.sum(axis=1)
    if np.any(short):
        out[rows, lead] += short
        np.clip(out, 0, 255, out=out)
    return out.astype(np.uint8)


def within_radius(
    hard: np.ndarray, soft: np.ndarray, radius: float
) -> np.ndarray:
    """True where ``soft``'s class is present in ``hard`` within ``radius`` px.

    The reachability test behind the macro invariant: a pixel may only take
    a class CK2 actually painted within one source pixel of it.  Class
    agnostic and bounded, so it costs one shifted comparison per offset in
    the disk (13 of them at radius 2) instead of a distance transform per
    class over a 56 Mpx canvas.
    """
    h, w = hard.shape
    ok = hard == soft
    r = int(np.floor(radius))
    for oy in range(-r, r + 1):
        for ox in range(-r, r + 1):
            if (oy == 0 and ox == 0) or np.hypot(oy, ox) > radius:
                continue
            ys = slice(max(0, oy), h + min(0, oy))
            xs = slice(max(0, ox), w + min(0, ox))
            yd = slice(max(0, -oy), h + min(0, -oy))
            xd = slice(max(0, -ox), w + min(0, -ox))
            sub = ok[yd, xd]
            sub |= hard[ys, xs] == soft[yd, xd]
            ok[yd, xd] = sub
    return ok


def build_soft_blend(
    codes: np.ndarray,
    code_names: Sequence[str],
    *,
    material_mix: dict[str, list[tuple[str, float]]],
    ordinals: dict[str, int],
    mapping: dict[str, str] | None = None,
    default: str = "plains",
    quantize: int = 16,
    sigma_px: float = 2.0,
    warp: tuple[np.ndarray, np.ndarray] | None = None,
    max_shift_px: float | None = None,
    land_mask: np.ndarray | None = None,
    chunk_rows: int = 1024,
    warn: Callable[[str], None] = lambda _m: None,
) -> SoftBlend:
    """The `detail_index`/`detail_intensity` pair with soft, relief-aware edges.

    ``codes`` is the CK2 terrain-category code grid at canvas resolution
    (:func:`ck2ck3.map.terrain.ck2_category_codes` + the canvas resize), same
    input :func:`ck2ck3.map.terrain_paint.build_layers` took.  Deterministic:
    there is no RNG anywhere in this path, which is also why the intensity
    layer compresses (a class interior is one constant RGBA value).
    """
    from .terrain import CK2_TO_CK3_TERRAIN

    table = dict(CK2_TO_CK3_TERRAIN if mapping is None else mapping)
    cls_of_code, class_names = _class_of_code(code_names, table, default)

    missing_material: set[str] = set()
    missing_ordinal: set[str] = set()
    mix_ord, mix_w = _mix_arrays(
        class_names,
        material_mix,
        ordinals,
        default=default,
        missing_material=missing_material,
        missing_ordinal=missing_ordinal,
    )
    for name in sorted(missing_material):
        warn(
            f"terrain_paint: CK3 terrain '{name}' has no row in the material "
            "table; using the default mix"
        )
    for name in sorted(missing_ordinal):
        warn(
            f"terrain_paint: material '{name}' is not declared in the vanilla "
            "materials.settings this run read; ordinal 0 used"
        )

    h, w = codes.shape
    cls_hard = cls_of_code[codes]
    cls = warp_apply(cls_hard, warp[0], warp[1]) if warp is not None else cls_hard

    # ---- stage A: the two strongest classes per pixel -------------------- #
    present = np.flatnonzero(np.bincount(cls.reshape(-1), minlength=len(class_names)))
    best1_w = np.zeros((h, w), dtype=np.float32)
    best2_w = np.zeros((h, w), dtype=np.float32)
    best1_c = np.zeros((h, w), dtype=np.uint8)
    best2_c = np.zeros((h, w), dtype=np.uint8)
    for k in present.tolist():
        field = (cls == k).astype(np.float32)
        if sigma_px > 0:
            field = gaussian_filter(field, sigma_px, output=field)
        first = field > best1_w
        second = (~first) & (field > best2_w)
        best2_w = np.where(first, best1_w, np.where(second, field, best2_w))
        best2_c = np.where(first, best1_c, np.where(second, np.uint8(k), best2_c))
        best1_w = np.where(first, field, best1_w)
        best1_c = np.where(first, np.uint8(k), best1_c)
        del field, first, second

    # ---- the macro invariant, enforced rather than hoped for ------------- #
    # The warp is bounded by construction, but the blur rounds corners and
    # can swallow a one-pixel speckle, so the two together can move a class
    # further than either alone. Any pixel whose winning class CK2 did not
    # paint within `max_shift_px` reverts to CK2's own class, unblended.
    # Rare by design; the count is reported.
    reverted = 0
    if max_shift_px is not None and max_shift_px > 0:
        ok = within_radius(cls_hard, best1_c, float(max_shift_px))
        bad = ~ok
        reverted = int(bad.sum())
        if reverted:
            best1_c = np.where(bad, cls_hard, best1_c)
            best1_w = np.where(bad, np.float32(1.0), best1_w)
            best2_w = np.where(bad, np.float32(0.0), best2_w)
        del ok, bad

    # ---- stage B: class weights -> material channels --------------------- #
    idx = np.zeros((h, w, MAX_CHANNELS), dtype=np.uint8)
    inten = np.zeros((h, w, MAX_CHANNELS), dtype=np.uint8)
    step = max(1, int(quantize))
    n_land = 0
    sum_channels = 0.0
    sum_primary = 0.0
    sum_entropy = 0.0
    for y0 in range(0, h, chunk_rows):
        y1 = min(h, y0 + chunk_rows)
        c1 = best1_c[y0:y1].reshape(-1)
        c2 = best2_c[y0:y1].reshape(-1)
        w1 = best1_w[y0:y1].reshape(-1).astype(np.float32)
        w2 = best2_w[y0:y1].reshape(-1).astype(np.float32)
        share = w1 / np.maximum(w1 + w2, 1e-9)
        cand_o = np.concatenate([mix_ord[c1], mix_ord[c2]], axis=1)
        cand_w = np.concatenate(
            [mix_w[c1] * share[:, None], mix_w[c2] * (1.0 - share)[:, None]], axis=1
        )
        # a material both classes name is one material, not two channels
        for i in range(MAX_CHANNELS):
            for j in range(MAX_CHANNELS, 2 * MAX_CHANNELS):
                same = (cand_o[:, i] == cand_o[:, j]) & (cand_w[:, j] > 0)
                if not same.any():
                    continue
                cand_w[same, i] += cand_w[same, j]
                cand_w[same, j] = 0.0
        top = np.argpartition(-cand_w, MAX_CHANNELS - 1, axis=1)[:, :MAX_CHANNELS]
        sel_w = np.take_along_axis(cand_w, top, axis=1)
        sel_o = np.take_along_axis(cand_o, top, axis=1)
        order = np.argsort(-sel_w, axis=1, kind="stable")
        sel_w = np.take_along_axis(sel_w, order, axis=1)
        sel_o = np.take_along_axis(sel_o, order, axis=1)
        qw = _quantise_to_255(sel_w, step)
        # A dead channel repeats the pixel's own primary ordinal rather than
        # taking 0. `verified` on vanilla's own bake (867,903 sampled land
        # pixels): a zero-weight channel never holds ordinal 0, and ordinal 0
        # is not terrain art at all - `materials.settings` declares
        # `drought`, `drought_cracks`, `flood`, `summer_grass`,
        # `winter_effect` and `debug` first, so ordinals 0-5 are seasonal
        # effect layers. Repeating the primary keeps the byte inert, keeps
        # the class interior a constant RGBA quadruple for the RLE, and never
        # names an effect layer.
        sel_o = np.where(qw > 0, sel_o, sel_o[:, :1])
        idx[y0:y1] = sel_o.reshape(y1 - y0, w, MAX_CHANNELS)
        inten[y0:y1] = qw.reshape(y1 - y0, w, MAX_CHANNELS)

        rows = (
            land_mask[y0:y1].reshape(-1)
            if land_mask is not None
            else np.ones(qw.shape[0], dtype=bool)
        )
        if rows.any():
            f = qw[rows].astype(np.float32) / 255.0
            n_land += int(rows.sum())
            sum_channels += float((f > 0).sum())
            sum_primary += float(f[:, 0].sum())
            with np.errstate(divide="ignore", invalid="ignore"):
                lg = np.where(f > 0, np.log2(np.maximum(f, 1e-12)), 0.0)
            sum_entropy += float(-(f * lg).sum())
            del f, lg
        del c1, c2, w1, w2, share, cand_o, cand_w, top, sel_w, sel_o, order, qw

    assert bool(
        (inten.astype(np.uint16).sum(axis=2) == 255).all()
    ), "detail_intensity channels must sum to 255"

    stats = {
        "land_px": float(n_land),
        "mean_nonzero_channels": round(sum_channels / n_land, 4) if n_land else 0.0,
        "mean_primary_weight": round(sum_primary / n_land, 4) if n_land else 0.0,
        "blend_entropy_bits": round(sum_entropy / n_land, 4) if n_land else 0.0,
        "sigma_px": float(sigma_px),
        "max_shift_px": float(max_shift_px or 0.0),
        "reverted_px": float(reverted),
    }
    return SoftBlend(
        index=idx,
        intensity=inten,
        class_index=best1_c,
        class_names=class_names,
        class_index_hard=cls_hard,
        stats=stats,
    )


# --------------------------------------------------------------------------- #
# the macro invariant: how far did a class actually move?
# --------------------------------------------------------------------------- #
def class_displacement_stats(
    baseline: np.ndarray,
    after: np.ndarray,
    *,
    km_per_px: float = 1.0,
    mask: np.ndarray | None = None,
    max_radius: int = 8,
    percentiles: Sequence[float] = (50.0, 95.0, 99.0),
) -> dict[str, float]:
    """How far a class travelled between two class maps, in pixels and km.

    For every pixel whose class changed, the Euclidean distance to the
    nearest pixel that already carried the *new* class in ``baseline`` — i.e.
    how far that class had to migrate to reach here.  This is the right
    metric for the macro invariant (`docs/step_map_paint.md` §10): swallowing
    a one-pixel speckle of class X registers as its neighbour Y moving one
    pixel, not as X moving to infinity, and a boundary that merely bends
    registers as the bend's own amplitude.

    Searched over a disk of ``max_radius`` pixels — the whole point is that
    the answer must be small, so anything beyond the disk is counted in
    ``beyond_radius_px`` and treated as ``max_radius`` in the percentiles
    rather than costing a full distance transform per class (12 classes over
    a 56 Mpx canvas).  ``max_radius = 0`` uses an exact, unbounded
    :func:`scipy.ndimage.distance_transform_edt` per class instead.
    """
    changed = baseline != after
    if mask is not None:
        changed = changed & mask
    n = int(changed.sum())
    out: dict[str, float] = {
        "changed_px": float(n),
        "changed_share": round(float(n) / float(baseline.size), 6),
        "km_per_px": round(float(km_per_px), 6),
        "max_radius_px": float(max_radius),
    }
    if n == 0:
        out.update({"max_px": 0.0, "max_km": 0.0, "mean_px": 0.0,
                    "beyond_radius_px": 0.0})
        for p in percentiles:
            out[f"p{p:g}_px"] = 0.0
            out[f"p{p:g}_km"] = 0.0
        return out

    if max_radius and max_radius > 0:
        dist = np.full(baseline.shape, np.inf, dtype=np.float32)
        offsets = sorted(
            (
                (float(np.hypot(oy, ox)), oy, ox)
                for oy in range(-max_radius, max_radius + 1)
                for ox in range(-max_radius, max_radius + 1)
                if 0 < np.hypot(oy, ox) <= max_radius
            )
        )
        todo = changed.copy()
        h, w = baseline.shape
        for d, oy, ox in offsets:
            if not todo.any():
                break
            ys = slice(max(0, oy), h + min(0, oy))
            xs = slice(max(0, ox), w + min(0, ox))
            yd = slice(max(0, -oy), h + min(0, -oy))
            xd = slice(max(0, -ox), w + min(0, -ox))
            hit = todo[yd, xd] & (baseline[ys, xs] == after[yd, xd])
            if not hit.any():
                continue
            sub = dist[yd, xd]
            sub[hit] = d
            dist[yd, xd] = sub
            todo[yd, xd] &= ~hit
        beyond = int(todo.sum())
        vals = dist[changed]
        vals = np.where(np.isinf(vals), float(max_radius), vals)
        out["beyond_radius_px"] = float(beyond)
    else:
        dist = np.zeros(baseline.shape, dtype=np.float32)
        for k in np.unique(after[changed]).tolist():
            sel = changed & (after == k)
            if not sel.any():
                continue
            edt = distance_transform_edt(baseline != k).astype(np.float32)
            dist[sel] = edt[sel]
            del edt, sel
        vals = dist[changed]
        out["beyond_radius_px"] = 0.0
    out["max_px"] = round(float(vals.max()), 3)
    out["max_km"] = round(float(vals.max()) * km_per_px, 3)
    out["mean_px"] = round(float(vals.mean()), 3)
    out["mean_km"] = round(float(vals.mean()) * km_per_px, 3)
    for p in percentiles:
        v = float(np.percentile(vals, p))
        out[f"p{p:g}_px"] = round(v, 3)
        out[f"p{p:g}_km"] = round(v * km_per_px, 3)
    return out


# --------------------------------------------------------------------------- #
# trees.bmp: a smooth mask instead of a 15.6-pixel Lego block
# --------------------------------------------------------------------------- #
def forest_coverage(
    trees_idx: np.ndarray,
    tree_indices: Sequence[int],
    shape: tuple[int, int],
    *,
    smooth: bool = True,
    blur_px: float = 0.0,
) -> np.ndarray:
    """``trees.bmp`` -> a float coverage field at ``shape``, in [0, 1].

    CK2's ``trees.bmp`` is 1/8 of the province bitmap on each axis — 23.2 km
    per tree pixel on Faerûn — and the converter used to expand it with
    ``np.repeat``, which is why a forest reads as Lego at close zoom.  A
    bilinear expansion of the same indicator (``smooth=True``) puts the 0.5
    contour on the *midpoint* between a forest and a non-forest source pixel
    and rounds every corner, which is what makes the edge organic; the class
    map it feeds is otherwise unchanged.  ``blur_px`` (in *source* pixels of
    ``shape``) adds an extra Gaussian if a softer edge is wanted.
    """
    ind = np.isin(trees_idx, list(tree_indices)).astype(np.float32)
    h, w = shape
    th, tw = ind.shape[:2]
    if not smooth:
        rows = (np.arange(h) * th // h).clip(0, th - 1)
        cols = (np.arange(w) * tw // w).clip(0, tw - 1)
        return ind[rows[:, None], cols[None, :]]
    # pixel-centre aligned bilinear: source centre i maps to (i + 0.5) * s - 0.5
    sy = th / float(h)
    sx = tw / float(w)
    fy = np.clip((np.arange(h) + 0.5) * sy - 0.5, 0, th - 1)
    fx = np.clip((np.arange(w) + 0.5) * sx - 0.5, 0, tw - 1)
    y0 = np.floor(fy).astype(np.int32)
    x0 = np.floor(fx).astype(np.int32)
    y1 = np.minimum(y0 + 1, th - 1)
    x1 = np.minimum(x0 + 1, tw - 1)
    wy = (fy - y0).astype(np.float32)[:, None]
    wx = (fx - x0).astype(np.float32)[None, :]
    top = ind[y0][:, x0] * (1 - wx) + ind[y0][:, x1] * wx
    bot = ind[y1][:, x0] * (1 - wx) + ind[y1][:, x1] * wx
    out = top * (1 - wy) + bot * wy
    if blur_px > 0:
        out = gaussian_filter(out, blur_px, output=out)
    return out
