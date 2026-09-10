#!/usr/bin/env python3
"""Shared ground for lane `relief-sharp`: crops, the plain-rescale baseline,
the moat metric and transects.

Every number this lane reports is measured with the functions here, so the
moat figure in `docs/step_map_heightmap.md` §2d, the per-candidate isolation
table and the finished-map check are one measurement.

The canvas geometry, levels and km/px are the same constants
`scripts/heightmap_erosion_evidence.py` uses (configs/faerun.toml
`[map]` / `[map.heightmap]`).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.ndimage import distance_transform_edt, grey_closing

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

Image.MAX_IMAGE_PIXELS = None

CK2_MAP = ROOT / "Faerun/Faerun/map"
GAME = ROOT / "../claudespace/game_files"
LIVE_MOD = ROOT / "../claudespace/mods/faerun_ck2_to_ck3_converted"
OUT = ROOT / "docs/evidence/relief_sharp"
CROPS_JSON = ROOT / "docs/evidence/heightmap_erosion/crops.json"

CANVAS_W, CANVAS_H = 8320, 6784
SCALED_W, SCALED_H = 8005, 6504
OFFSET_X, OFFSET_Y = 157, 140
WATER_LEVEL, MAX_LEVEL, CK2_SEA_LEVEL = 4883, 49205, 95
KM_PX_OURS, KM_PX_VANILLA = 1.4839, 0.74195
VANILLA_WATER = 3932
QUANT = (MAX_LEVEL - WATER_LEVEL) / 160.0

#: a moat is a trench narrower than this (canvas px) beside an escarpment.
#: 9 px = 13 km: wider than the 2-14 px band the fill synthesises, narrow
#: enough that a real CK2 valley is not closed by it.
MOAT_CLOSING_PX = 9
#: "beside the cliff" and "away from any cliff", in px of distance from the
#: nearest >= 2-quantisation-step adjacent pair of the plain rescale
MOAT_NEAR_PX = 5.0
MOAT_FAR_PX = 15.0


def crops() -> dict:
    return json.loads(CROPS_JSON.read_text())


def load16(path: Path) -> np.ndarray:
    with Image.open(path) as im:
        return np.asarray(im.convert("I;16")).astype(np.uint16)


def plain_rescale_canvas() -> np.ndarray:
    """`ours before any detail pass`, exactly as ck2ck3.map.heightmap builds it."""
    from ck2ck3.map import heightmap as hm
    from ck2ck3.map.config import HeightmapConfig

    lut = hm.build_curve(
        HeightmapConfig(
            ck2_sea_level=CK2_SEA_LEVEL,
            ck3_water_level=WATER_LEVEL,
            ck3_max_level=MAX_LEVEL,
        )
    )
    with Image.open(CK2_MAP / "topology.bmp") as im:
        scaled = np.asarray(im.convert("L").resize((SCALED_W, SCALED_H), Image.LANCZOS))
    out8 = np.full((CANVAS_H, CANVAS_W), CK2_SEA_LEVEL, dtype=np.uint8)
    out8[OFFSET_Y:OFFSET_Y + SCALED_H, OFFSET_X:OFFSET_X + SCALED_W] = scaled
    return lut[out8]


def province_land_mask(finished: np.ndarray) -> np.ndarray:
    """The province raster's own land mask, read back off a finished map.

    `heightmap_detail.apply` guarantees every water pixel ends at or below
    `water_level` and every land pixel strictly above it, so a finished map
    *is* the land mask.  Thresholding the plain rescale instead is wrong and
    was wrong here: Faerun's CK2 lakes and river provinces sit on high
    ground (Thay's median such pixel is at 14,301 in the rescale), so a
    `> water_level` test on the rescale calls 10,020 Thay water pixels land
    and then reads the water pin under them as a 9,000-level trench.
    """
    return finished > WATER_LEVEL


def crop_box(region: str, margin: int = 0) -> tuple[slice, slice]:
    c = crops()[region]
    y, x, s = c["crop_y"], c["crop_x"], c["crop_side"]
    return (slice(y - margin, y + s + margin), slice(x - margin, x + s + margin))


# --------------------------------------------------------------------------- #
# the moat metric
# --------------------------------------------------------------------------- #
def cliff_mask(base: np.ndarray, land: np.ndarray, steps: float = 2.0) -> np.ndarray:
    """Pixels on either side of an adjacent pair jumping >= `steps` risers.

    Classified on the *plain rescale*, never on the finished map: the thing
    being asked is "what happened next to a real escarpment", and the
    escarpment is a property of the source.
    """
    m = np.zeros(base.shape, dtype=bool)
    b = base.astype(np.float64)
    thr = steps * QUANT
    d0 = np.abs(np.diff(b, axis=0)) >= thr
    d0 &= land[1:, :] & land[:-1, :]
    m[1:, :] |= d0
    m[:-1, :] |= d0
    d1 = np.abs(np.diff(b, axis=1)) >= thr
    d1 &= land[:, 1:] & land[:, :-1]
    m[:, 1:] |= d1
    m[:, :-1] |= d1
    return m


def depression_depth(a: np.ndarray, size: int = MOAT_CLOSING_PX) -> np.ndarray:
    """How far each pixel sits below the surface that spans over it.

    Grey-scale morphological closing (dilate then erode) with a `size` px
    square fills any trench narrower than `size` and leaves everything wider
    alone, so `closing - a` is exactly the depth of a narrow depression and
    zero on an open slope.  This is the shape the user reported: "plateaux
    are dipping then coming back up".
    """
    return grey_closing(a.astype(np.float32), size=size) - a.astype(np.float32)


def moat_stats(
    base: np.ndarray, final: np.ndarray, land: np.ndarray, label: str
) -> dict:
    """Trench depth beside the plain rescale's own escarpments, and away from them."""
    cliffs = cliff_mask(base, land)
    if not cliffs.any():
        return {"map": label, "cliff_px": 0}
    dist = distance_transform_edt(~cliffs).astype(np.float32)
    dep = depression_depth(final)
    near = land & (dist <= MOAT_NEAR_PX) & ~cliffs
    far = land & (dist > MOAT_FAR_PX)
    base_dep = depression_depth(base)
    row = {
        "map": label,
        "cliff_px": int(cliffs.sum()),
        "near_px": int(near.sum()),
        "far_px": int(far.sum()),
        # the headline: how deep the trench beside a cliff is
        "moat_mean_near": round(float(dep[near].mean()), 1) if near.any() else 0.0,
        "moat_p95_near": round(float(np.percentile(dep[near], 95)), 1) if near.any() else 0.0,
        "moat_p99_near": round(float(np.percentile(dep[near], 99)), 1) if near.any() else 0.0,
        "moat_max_near": round(float(dep[near].max()), 1) if near.any() else 0.0,
        # control: the same statistic where there is no escarpment
        "moat_p95_far": round(float(np.percentile(dep[far], 95)), 1) if far.any() else 0.0,
        # and what the source itself already had beside the same cliffs
        "source_moat_p95_near": round(float(np.percentile(base_dep[near], 95)), 1)
        if near.any() else 0.0,
    }
    row["moat_excess_p95"] = round(row["moat_p95_near"] - row["moat_p95_far"], 1)
    return row


def _undershoot(
    base: np.ndarray, final: np.ndarray, land: np.ndarray,
    lo_steps: float, hi_steps: float, span: int,
) -> np.ndarray:
    """Deepest dip below the foot level, `span` px into the low side.

    For every adjacent pair whose plain-rescale jump is in
    ``[lo_steps, hi_steps)`` risers, walk `span` px away from the step on
    the low side.  Transects whose *source* profile keeps descending are
    dropped, so what is left is a foot the source drew flat: any dip below
    it in the finished map is synthetic.
    """
    b = base.astype(np.float64)
    f = final.astype(np.float64)
    worst = []
    for axis in (0, 1):
        db = np.diff(b, axis=axis)
        m = (land[1:, :] & land[:-1, :]) if axis == 0 else (land[:, 1:] & land[:, :-1])
        sel = m & (np.abs(db) >= lo_steps * QUANT) & (np.abs(db) < hi_steps * QUANT)
        ys, xs = np.nonzero(sel)
        for y, x in zip(ys, xs):
            # low side of the pair, and the direction that walks away from it
            if axis == 0:
                lo_y, lo_x = (y + 1, x) if db[y, x] > 0 else (y, x)
                step = (1, 0) if db[y, x] > 0 else (-1, 0)
            else:
                lo_y, lo_x = (y, x + 1) if db[y, x] > 0 else (y, x)
                step = (0, 1) if db[y, x] > 0 else (0, -1)
            ys2 = lo_y + step[0] * np.arange(span + 1)
            xs2 = lo_x + step[1] * np.arange(span + 1)
            ok = (
                (ys2 >= 0) & (ys2 < b.shape[0]) & (xs2 >= 0) & (xs2 < b.shape[1])
            )
            ys2, xs2 = ys2[ok], xs2[ok]
            if ys2.size < 4 or not land[ys2, xs2].all():
                continue
            foot = b[lo_y, lo_x]
            # only count a transect whose source profile really is flat-ish
            # beyond the cliff: a genuine downhill slope is not a moat
            if b[ys2, xs2].min() < foot - 1.5 * QUANT:
                continue
            worst.append(foot - f[ys2, xs2].min())
    return np.asarray(worst) if worst else np.empty(0)


def monotonic_violation(
    base: np.ndarray, final: np.ndarray, land: np.ndarray, span: int = 12
) -> dict:
    """Cliff-foot undershoot, and the same statistic where there is no cliff.

    The control matters: *any* synthesised detail dips a couple of hundred
    levels below a flat foot, and that is terrain, not a moat.  What the
    playtest saw is a dip that only happens **beside an escarpment**, so the
    number to drive to zero is the *excess* over the control -- undershoot
    beyond a one-step riser, which is the same fill on ground the source
    drew equally flat.
    """
    cliff = _undershoot(base, final, land, 2.0, 99.0, span)
    ctrl = _undershoot(base, final, land, 0.5, 1.5, span)
    if cliff.size == 0:
        return {"transects": 0}
    out = {
        "transects": int(cliff.size),
        "undershoot_mean": round(float(cliff.mean()), 1),
        "undershoot_p95": round(float(np.percentile(cliff, 95)), 1),
        "undershoot_max": round(float(cliff.max()), 1),
        "frac_undershoot_gt_200": round(float((cliff > 200).mean()), 4),
        "control_transects": int(ctrl.size),
        "control_undershoot_mean": round(float(ctrl.mean()), 1) if ctrl.size else 0.0,
    }
    out["moat_excess_mean"] = round(
        out["undershoot_mean"] - out["control_undershoot_mean"], 1)
    return out
