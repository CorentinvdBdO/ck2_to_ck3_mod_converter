"""Cliff-aware de-terracing and eroded (dendritic) relief for the heightmap.

Two independent pieces, both used by :mod:`ck2ck3.map.heightmap_detail` and
both switchable from the config, because each replaces one step of the
original detail pass with something that produces *landscape* rather than
isotropic noise (``docs/step_map_heightmap.md`` §2b and §2c):

**§2b, :func:`deterrace_cliff_aware`.**  The original pass 1 is a plain
Gaussian, which cannot tell a quantisation riser from a cliff: an 8-bit CK2
source through the converter's transfer curve steps by exactly
``(max_level - water_level) / 160 = 277`` sixteen-bit levels per source
value, so *every* slope is a staircase -- but a real cliff (Thay's terraced
plateaus, the Spine of the World) is several of those steps between adjacent
pixels, and blurring destroys it along with the artefact.  This is
Perona-Malik anisotropic diffusion instead: the flux between two pixels is
weighted by ``exp(-(dh / cliff_step)**2)``, so a one-step riser (277 levels,
weight 0.64 at the default threshold) diffuses away while a three-step cliff
(831 levels, weight 0.02) does not.  In a flat region the scheme is the heat
equation, so ``n`` steps of size ``lambda`` equal a Gaussian of
``sigma = sqrt(2 * lambda * n)`` -- the iteration count is derived from the
same ``deterrace_sigma_px`` the Gaussian used, and the two are therefore
directly comparable.

**§2c, :func:`eroded_relief`.**  The original pass 2 injects white noise
shaped to a radial power law: the right amplitude and the right spectrum,
but no structure -- valleys do not drain and ridges do not connect.  This
seeds the de-terraced macro surface with band-limited fractal noise and runs
a short landscape-evolution model over it: multiple-flow-direction
accumulation (relaxed, not sorted -- see :func:`flow_accumulation`), stream-power
incision ``dz = -K (A/A_ref)^m S`` with the mean incision added back as
uniform uplift so total relief is conserved, and linear hillslope diffusion.
The result is *phase* structure; the caller still equalises its radial
spectrum onto vanilla's law and rescales it per terrain class, so the
amplitude calibration (``hf_by_terrain.csv``) is untouched.

Every function here is pure: same inputs and same ``numpy`` Generator state
in, same array out.
"""

from __future__ import annotations

import numpy as np
from scipy.ndimage import gaussian_filter

#: 8-neighbour offsets ``(dy, dx, distance in pixels)``
NEIGHBOURS: tuple[tuple[int, int, float], ...] = (
    (-1, 0, 1.0), (1, 0, 1.0), (0, -1, 1.0), (0, 1, 1.0),
    (-1, -1, 1.4142135), (-1, 1, 1.4142135),
    (1, -1, 1.4142135), (1, 1, 1.4142135),
)

#: 16-bit levels per 8-bit CK2 source step, for the shipped transfer curve
#: ``0 -> 0``, ``95 -> 4883``, ``255 -> 49205``:  (49205 - 4883) / 160.
QUANTISATION_STEP_LEVELS = 277.0125

#: Perona-Malik explicit step.  0.25 is the stability limit of the 4-point
#: Laplacian; 0.18 keeps a margin and still needs only a handful of steps.
_PM_LAMBDA = 0.18

#: A_ref for the stream-power law is this percentile of the flow
#: accumulation over land, so ``(A / A_ref)**m`` is O(1) in the channels and
#: small on the hillslopes whatever the canvas size or the iteration count.
_ACCUM_REFERENCE_PERCENTILE = 92.0

#: hard cap on one iteration's incision, as a fraction of the local steepest
#: descent: a pixel may never be cut below the neighbour it drains into.
_INCISION_SLOPE_CAP = 0.5

#: Ceiling (16-bit levels per pixel) on the slope the stream-power law is
#: allowed to see, as a multiple of ``QUANTISATION_STEP_LEVELS``.
#:
#: Why it has to exist (docs/step_map_heightmap.md §2d).  ``S`` in
#: ``dz = -K (A/A_ref)^m S`` is the *macro* steepest descent, and on Thay's
#: escarpments that is up to 4,505 levels/px against a land median of 128.
#: The law therefore cut the plateau rim by up to 1,939 levels *per
#: iteration*, sixteen times over, while the uniform uplift added the mean
#: of that back to every land pixel: measured on the Thay crop the returned
#: field averaged **-1,142 levels on cliff pixels and +632 levels twelve
#: pixels away** (`verified`), i.e. a 1,774-level trench around every
#: escarpment before the spectral pass had touched it.  That is the
#: cliff-foot moat playtest 3 reported.
#:
#: 1.0 step = 277 levels/px, one source value per pixel: the steepest
#: gradient the 8-bit source can express without being a *multi*-step cliff,
#: which is macro relief the erosion has no business re-carving.  Measured
#: on the Thay crop the cliff-to-interior trench in the returned field falls
#: 1,773 -> 593 levels at 1.0 and only to 1,153 at 2.0 (`verified`,
#: docs/evidence/relief_sharp/erosion_slope_ceiling.csv).  The
#: "cannot cut below the neighbour it drains into" guard above still uses
#: the *true* slope, so the cap loosens nothing.  0 disables it and
#: reproduces build 13.
DEFAULT_INCISION_SLOPE_CEILING_STEPS = 1.0


def _slices(shape: tuple[int, int], dy: int, dx: int):
    """Source and destination slices for a translation by ``(dy, dx)``."""
    h, w = shape
    return (
        (slice(max(0, dy), h + min(0, dy)), slice(max(0, dx), w + min(0, dx))),
        (slice(max(0, -dy), h + min(0, -dy)), slice(max(0, -dx), w + min(0, -dx))),
    )


def _shift_into(out: np.ndarray, src: np.ndarray, dy: int, dx: int) -> np.ndarray:
    """``out[p] = src[p + (dy, dx)]`` with a zero border, no wrap-around.

    Slice arithmetic rather than ``np.roll``: on an 8320x6784 float32 canvas a
    roll allocates and copies 226 MB per call and the erosion does thousands
    of them.
    """
    src_sl, dst_sl = _slices(src.shape, dy, dx)
    # clear only the strip the copy will not cover: zeroing the whole array
    # first is a second full write pass over 226 MB, and this loop is
    # memory-bandwidth bound
    if dy > 0:
        out[-dy:, :] = 0
    elif dy < 0:
        out[:-dy, :] = 0
    if dx > 0:
        out[:, -dx:] = 0
    elif dx < 0:
        out[:, :-dx] = 0
    out[dst_sl] = src[src_sl]
    return out


def _shift_add(out: np.ndarray, src: np.ndarray, dy: int, dx: int) -> None:
    """``out[p] += src[p + (dy, dx)]`` -- one pass, no temporary."""
    src_sl, dst_sl = _slices(src.shape, dy, dx)
    out[dst_sl] += src[src_sl]


def _clamp_border(buf: np.ndarray, src: np.ndarray, dy: int, dx: int) -> None:
    """Undo ``_shift_into``'s zero border: outside the canvas is level with here.

    A zero border would read as a cliff down to sea level all the way round
    the sheet, which would make the whole rim a channel head.
    """
    if dy == 1:
        buf[-1, :] = src[-1, :]
    elif dy == -1:
        buf[0, :] = src[0, :]
    if dx == 1:
        buf[:, -1] = src[:, -1]
    elif dx == -1:
        buf[:, 0] = src[:, 0]


# --------------------------------------------------------------------------- #
# §2b  cliff-aware de-terrace
# --------------------------------------------------------------------------- #
def deterrace_iterations(sigma_px: float, lam: float = _PM_LAMBDA) -> int:
    """Steps of diffusion whose flat-region blur equals a Gaussian ``sigma_px``."""
    return max(1, int(round(sigma_px * sigma_px / (2.0 * lam))))


def deterrace_cliff_aware(
    heights: np.ndarray,
    sigma_px: float,
    cliff_step_levels: float,
) -> np.ndarray:
    """Perona-Malik de-terrace: kills one-step risers, keeps multi-step cliffs.

    ``heights`` float32, any shape.  ``cliff_step_levels`` is the flux
    half-width in 16-bit levels; ``1.5 * QUANTISATION_STEP_LEVELS`` sits
    between one source step and two, which is exactly the discrimination the
    pass exists to make.
    """
    n = deterrace_iterations(sigma_px)
    lam = sigma_px * sigma_px / (2.0 * n)
    # a real copy, not ascontiguousarray: the loop is in-place and an already
    # contiguous float32 input would otherwise be mutated under the caller
    h = np.array(heights, dtype=np.float32)
    k2 = float(cliff_step_levels) ** 2
    acc = np.empty_like(h)
    d = np.empty_like(h)
    for _ in range(n):
        acc[...] = 0.0
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            _shift_into(d, h, dy, dx)
            _clamp_border(d, h, dy, dx)
            d -= h
            acc += d * np.exp(-(d * d) / k2)
        h += lam * acc
    return h


# --------------------------------------------------------------------------- #
# §2c  eroded relief
# --------------------------------------------------------------------------- #
def fractal_seed(
    shape: tuple[int, int],
    rng: np.random.Generator,
    sigmas_px: tuple[float, ...] = (0.8, 1.6, 3.2, 6.4, 12.0),
    amplitudes: tuple[float, ...] = (0.4, 0.6, 0.8, 0.9, 1.0),
) -> np.ndarray:
    """Unit-variance band-limited fractal noise, the erosion's initial relief.

    One white field filtered at several sigmas rather than several white
    fields: the octaves then share phase the way a real fBm does, and it
    costs one ``standard_normal`` call on the whole canvas instead of five.
    """
    white = rng.standard_normal(shape).astype(np.float32)
    out = np.zeros(shape, dtype=np.float32)
    for sigma, amp in zip(sigmas_px, amplitudes):
        octave = gaussian_filter(white, sigma, mode="nearest")
        out += (amp / max(float(octave.std()), 1e-9)) * octave
    return out / max(float(out.std()), 1e-9)


def _pow_inplace(a: np.ndarray, exponent: float) -> None:
    """``a **= exponent`` -- by repeated squaring for 2 and 4, which are the
    ones the default config uses and which ``np.power`` is ~5x slower at."""
    if exponent == 1.0:
        return
    if exponent == 2.0:
        a *= a
    elif exponent == 4.0:
        a *= a
        a *= a
    elif exponent == 0.5:
        np.sqrt(a, out=a)
    else:
        np.power(a, exponent, out=a)


def _mfd_weights(h: np.ndarray, exponent: float) -> list[np.ndarray]:
    """Multiple-flow-direction weights to the 8 neighbours, rows summing to 1."""
    ws: list[np.ndarray] = []
    total = np.zeros_like(h)
    for dy, dx, dist in NEIGHBOURS:
        w = np.empty_like(h)
        _shift_into(w, h, dy, dx)
        _clamp_border(w, h, dy, dx)
        np.subtract(h, w, out=w)
        np.maximum(w, 0.0, out=w)
        w /= dist
        _pow_inplace(w, exponent)
        ws.append(w)
        total += w
    np.maximum(total, 1e-12, out=total)
    for w in ws:
        w /= total
    return ws


def flow_accumulation(
    weights: list[np.ndarray],
    land: np.ndarray,
    iterations: int,
    start: np.ndarray | None = None,
) -> np.ndarray:
    """``A <- 1 + sum_j w(j->p) A_j``, relaxed ``iterations`` times.

    Relaxation rather than a topological sweep down a sorted elevation list:
    the sweep is inherently sequential and 56 million pixels of it in Python
    is not an option, while one relaxation pass is eight shifted
    multiply-adds.  Each pass propagates the catchment one pixel further
    downstream, so ``iterations`` sets the largest catchment the model can
    see -- which is a feature here, not a compromise: the structure being
    synthesised lives at 1-20 km (2-14 canvas px), and a bounded catchment is
    what keeps the erosion from re-cutting the CK2 source's own macro
    valleys.
    """
    base = land.astype(np.float32)
    acc = base.copy() if start is None else np.array(start, dtype=np.float32)
    term = np.empty_like(base)
    nxt = np.empty_like(base)
    for _ in range(iterations):
        nxt[...] = base
        for (dy, dx, _), w in zip(NEIGHBOURS, weights):
            np.multiply(w, acc, out=term)
            # pixel q sends w_d(q) * A(q) to q + d, so the receiving pixel p
            # takes it from p - d: the shift is by the *opposite* offset
            _shift_add(nxt, term, -dy, -dx)
        acc, nxt = nxt, acc
    return acc


def _steepest_descent(h: np.ndarray) -> np.ndarray:
    s = np.zeros_like(h)
    buf = np.empty_like(h)
    for dy, dx, dist in NEIGHBOURS:
        _shift_into(buf, h, dy, dx)
        _clamp_border(buf, h, dy, dx)
        np.subtract(h, buf, out=buf)
        buf /= dist
        np.maximum(s, buf, out=s)
    return s


def _laplacian(h: np.ndarray) -> np.ndarray:
    out = np.zeros_like(h)
    buf = np.empty_like(h)
    for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        _shift_into(buf, h, dy, dx)
        _clamp_border(buf, h, dy, dx)
        out += buf
    out -= 4.0 * h
    return out


def eroded_relief(
    base: np.ndarray,
    land: np.ndarray,
    rng: np.random.Generator,
    *,
    seed_amplitude: float = 300.0,
    iterations: int = 20,
    accum_iterations: int = 4,
    mfd_exponent: float = 4.0,
    incision: float = 0.5,
    area_exponent: float = 0.5,
    diffusion: float = 0.06,
    slope_ceiling_steps: float = DEFAULT_INCISION_SLOPE_CEILING_STEPS,
) -> tuple[np.ndarray, dict]:
    """Return ``(relief field, diagnostics)`` -- unit-variance over land.

    ``base`` is the de-terraced macro surface, which supplies the drainage
    directions the CK2 source really does carry; the fractal seed supplies
    the relief the 8-bit source never could.  The pair is run through a
    short landscape-evolution model and the *difference* from ``base`` is
    returned, so nothing of the macro survives into the caller's noise field.
    """
    h0 = np.array(base, dtype=np.float32)
    w = h0 + np.float32(seed_amplitude) * fractal_seed(h0.shape, rng)
    ceiling = (
        float(slope_ceiling_steps) * QUANTISATION_STEP_LEVELS
        if slope_ceiling_steps > 0 else 0.0
    )
    landf = land.astype(np.float32)
    n_land = int(land.sum())
    uplift_total = 0.0
    carried: np.ndarray | None = None
    for _ in range(iterations):
        weights = _mfd_weights(w, mfd_exponent)
        acc = flow_accumulation(weights, land, accum_iterations, start=carried)
        del weights
        # carry the catchment across iterations: it changes slowly, so a few
        # relaxation passes per step accumulate to a long propagation
        # distance without paying for a cold start every time.
        carried = acc.copy()
        # the reference percentile is a distribution statistic, so a 1-in-49
        # subsample answers it to well within its own noise -- and does not
        # materialise a 26-million-element gather and sort every iteration
        probe = acc[::7, ::7][land[::7, ::7]]
        a_ref = (
            float(np.percentile(probe, _ACCUM_REFERENCE_PERCENTILE))
            if probe.size else 1.0
        )
        del probe
        slope = _steepest_descent(w)
        acc /= max(a_ref, 1e-6)
        _pow_inplace(acc, area_exponent)
        acc *= incision
        if ceiling > 0.0:
            # the driving slope is capped; the "never below the downstream
            # neighbour" guard below still reads the true one
            acc *= np.minimum(slope, np.float32(ceiling))
        else:
            acc *= slope
        slope *= _INCISION_SLOPE_CAP
        np.minimum(acc, slope, out=acc)
        del slope
        acc *= landf
        uplift = float(acc.sum() / n_land) if n_land else 0.0
        uplift_total += uplift
        # uniform uplift on land, so incision redistributes relief instead of
        # draining it away: without it a short run just lowers everything and
        # the high-pass throws the whole result out
        acc -= uplift * landf
        w -= acc
        del acc
        lap = _laplacian(w)
        lap *= np.float32(diffusion)
        lap *= landf
        w += lap
        del lap
    field = w - h0
    del w
    sd = float(field[land].std()) if land.any() else float(field.std())
    field /= max(sd, 1e-9)
    return field, {
        "erosion_iterations": iterations,
        "erosion_accum_iterations": accum_iterations,
        "erosion_uplift_levels": round(uplift_total, 1),
        "erosion_slope_ceiling_steps": round(float(slope_ceiling_steps), 2),
        "erosion_field_rms_levels": round(sd, 1),
    }
