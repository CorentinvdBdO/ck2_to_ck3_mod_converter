"""How staircased is a ``provinces.png``?  Three numbers, ours against vanilla.

Lane ``province-edges``.  CK2's province bitmap is 2.90 km per pixel and the
CK3 canvas is 1.9543x finer, so the NEAREST upsample in
``ck2ck3.map.provinces._resize_ids`` turns every province border and every
coastline into a staircase of 2x2 canvas pixels.  Vanilla draws the same kind
of border at the same 1.4839 km per pixel with organic curves.  "Organic"
needs a target before it can be a goal, so this script measures both.

Three metrics, each computed on the *label* image (no definition.csv needed
except to say which ids are water):

``axis_step_frac``
    Fraction of border pixels whose local boundary normal points within
    ``--axis-tol`` degrees of an axis.  The normal is a 3x3 Sobel of the
    "same label as me" indicator, which is exactly the boundary's own
    orientation at pixel scale.  A NEAREST upsample can only produce
    horizontal and vertical boundary segments, so this goes to ~1; an organic
    contour spreads its normals over every direction and lands near the
    fraction of a smooth curve that happens to be axis-aligned.

``corner_per_100px``
    Border pixels that have a differing 4-neighbour both vertically and
    horizontally, per 100 border pixels.  This is the 90-degree corner
    density: a 2x2 staircase turns a corner every two pixels, an organic
    contour only where the coast really turns.

``mean_crack_run_px``
    Mean length of a maximal straight run of boundary cracks (the unit edges
    between two differing pixels), averaged over the horizontal and the
    vertical family.  This is the staircase's own period: a NEAREST upsample
    by 1.9543 stretches every straight source segment by that factor, so the
    runs come out about twice as long as the source drew them.  It is the
    metric that separates "the border was drawn coarse and blown up" from
    "the border was drawn at this resolution", which neither of the two below
    can do.

``length_ratio`` (coastline only)
    Crack perimeter of the land mask divided by the crack perimeter of the
    same mask Gaussian-smoothed at ``--smooth-sigma`` and re-thresholded at
    0.5.  **Read this one and ``corner_per_100px`` the other way round**: both
    reward *fine* detail, and a staircase has none — it is coarse, not noisy.
    Vanilla scores higher on both (`verified`, 2026-09-12: 40.9 corners/100 px
    and 1.23 against our 18.1 and 1.07) because a hand-drawn vanilla border
    wiggles at single-pixel scale, which a 2.90 km source simply cannot carry.
    They are here as a guard rail: smoothing our borders pushes both *down*,
    away from vanilla, so they bound how much smoothing is honest.

Both maps here happen to be at the same 1.4839 km per pixel
(``docs/map_scale.md``), so the numbers compare directly.

Usage::

    uv run scripts/province_edges_metrics.py \
        --map before=../claudespace/mods/faerun_ck2_to_ck3_converted/map_data \
        --map vanilla=../claudespace/game_files/map_data \
        --out docs/evidence/province_edges/staircase.csv

``--crop NAME=x0,y0,x1,y1`` restricts one map to a window (the vanilla
Norwegian-coast panel, say).  A map may be given more than once under
different names.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter

Image.MAX_IMAGE_PIXELS = None

# CK2/CK3 province maps that are known to be at this scale; recorded in the
# CSV so a reader never compares two maps at different km per pixel by mistake
KM_PER_PX = 1.4839


# --------------------------------------------------------------------------- #
# inputs
# --------------------------------------------------------------------------- #
def read_labels(map_data: Path) -> np.ndarray:
    """``provinces.png`` -> an int32 label per pixel (the packed 24-bit colour)."""
    with Image.open(map_data / "provinces.png") as im:
        rgb = np.asarray(im.convert("RGB")).astype(np.int32)
    return (rgb[..., 0] << 16) | (rgb[..., 1] << 8) | rgb[..., 2]


def read_water_colours(map_data: Path) -> set[int]:
    """Packed colours of every sea/lake/river province, from default.map + CSV."""
    ids = _water_ids(map_data / "default.map")
    out: set[int] = set()
    with (map_data / "definition.csv").open(encoding="utf-8-sig", errors="replace") as fh:
        for row in csv.reader(fh, delimiter=";"):
            if len(row) < 4 or not row[0].strip().isdigit():
                continue
            pid = int(row[0])
            if pid in ids:
                try:
                    r, g, b = (int(row[1]), int(row[2]), int(row[3]))
                except ValueError:
                    continue
                out.add((r << 16) | (g << 8) | b)
    return out


def _water_ids(default_map: Path) -> set[int]:
    """`sea_zones`, `river_provinces` and `lakes` as a flat id set."""
    text = default_map.read_text(encoding="utf-8-sig", errors="replace")
    ids: set[int] = set()
    keys = ("sea_zones", "river_provinces", "lakes")
    for m in re.finditer(
        r"^\s*(" + "|".join(keys) + r")\s*=\s*(RANGE|LIST)\s*\{([^}]*)\}",
        text,
        re.MULTILINE,
    ):
        nums = [int(v) for v in m.group(3).split()]
        if m.group(2) == "RANGE" and len(nums) == 2:
            ids.update(range(nums[0], nums[1] + 1))
        else:
            ids.update(nums)
    return ids


# --------------------------------------------------------------------------- #
# the metrics
# --------------------------------------------------------------------------- #
#: 3x3 Sobel taps as (dy, dx, gx weight, gy weight), centre excluded
_SOBEL = (
    (-1, -1, 1.0, 1.0), (-1, 0, 0.0, 2.0), (-1, 1, -1.0, 1.0),
    (0, -1, 2.0, 0.0), (0, 1, -2.0, 0.0),
    (1, -1, 1.0, -1.0), (1, 0, 0.0, -2.0), (1, 1, -1.0, -1.0),
)


def _shift_eq(labels: np.ndarray, dy: int, dx: int) -> np.ndarray:
    """``labels`` shifted by (dy, dx) equals ``labels``; edge-clamped."""
    h, w = labels.shape
    ys = np.clip(np.arange(h) + dy, 0, h - 1)
    xs = np.clip(np.arange(w) + dx, 0, w - 1)
    return labels[ys[:, None], xs[None, :]] == labels


def border_mask(labels: np.ndarray) -> np.ndarray:
    """Pixels with at least one 4-neighbour carrying a different label."""
    out = np.zeros(labels.shape, dtype=bool)
    for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        out |= ~_shift_eq(labels, dy, dx)
    return out


def axis_step_frac(labels: np.ndarray, sel: np.ndarray, tol_deg: float) -> float:
    """Share of ``sel`` border pixels whose boundary normal is axis-aligned."""
    gx = np.zeros(labels.shape, dtype=np.float32)
    gy = np.zeros(labels.shape, dtype=np.float32)
    for dy, dx, wx, wy in _SOBEL:
        eq = _shift_eq(labels, dy, dx).astype(np.float32)
        if wx:
            gx += wx * eq
        if wy:
            gy += wy * eq
    g = np.hypot(gx, gy)
    live = sel & (g > 1e-6)
    n = int(live.sum())
    if n == 0:
        return float("nan")
    ang = np.degrees(np.arctan2(gy[live], gx[live]))
    # distance to the nearest multiple of 90 degrees
    d = np.abs(((ang + 45.0) % 90.0) - 45.0)
    return float((d <= tol_deg).sum()) / n


def corner_per_100px(labels: np.ndarray, sel: np.ndarray) -> float:
    """90-degree corners per 100 border pixels of ``sel``."""
    vert = ~_shift_eq(labels, -1, 0) | ~_shift_eq(labels, 1, 0)
    horz = ~_shift_eq(labels, 0, -1) | ~_shift_eq(labels, 0, 1)
    n = int(sel.sum())
    if n == 0:
        return float("nan")
    return 100.0 * float((sel & vert & horz).sum()) / n


def mean_crack_run_px(labels: np.ndarray) -> float:
    """Mean straight-run length of the boundary cracks, both families averaged.

    A *crack* is a unit edge between two 4-adjacent pixels with different
    labels.  The horizontal cracks (between a pixel and the one below it) form
    runs along x; the vertical cracks form runs along y.  A border drawn at
    this resolution turns often and its runs are short; a border drawn at
    2.90 km and blown up 1.9543x keeps the source's own run lengths multiplied
    by that factor, which is the staircase.
    """
    below = labels[:-1, :] != labels[1:, :]   # horizontal cracks, run along x
    right = labels[:, :-1] != labels[:, 1:]   # vertical cracks, run along y
    lens = np.concatenate([_run_lengths(below), _run_lengths(right.T)])
    return float(lens.mean()) if lens.size else float("nan")


def _run_lengths(mask: np.ndarray) -> np.ndarray:
    """Lengths of the maximal True runs along axis 1, over every row."""
    pad = np.zeros((mask.shape[0], 1), dtype=np.int8)
    flat = np.concatenate([pad, mask.astype(np.int8), pad], axis=1).ravel()
    d = np.diff(flat)
    return np.flatnonzero(d == -1) - np.flatnonzero(d == 1)


def crack_perimeter(mask: np.ndarray) -> int:
    """Unit edges between a True and a False pixel (4-connected)."""
    return int((mask[:, :-1] != mask[:, 1:]).sum() + (mask[:-1, :] != mask[1:, :]).sum())


def length_ratio(mask: np.ndarray, sigma: float) -> float:
    """Crack perimeter over that of the same mask smoothed and re-thresholded."""
    smooth = gaussian_filter(mask.astype(np.float32), sigma) >= 0.5
    den = crack_perimeter(smooth)
    if den == 0:
        return float("nan")
    return crack_perimeter(mask) / den


def measure(
    labels: np.ndarray,
    water: set[int],
    *,
    axis_tol: float,
    smooth_sigma: float,
) -> list[dict]:
    """One row per boundary set (``all`` province borders, then ``coast``)."""
    rows: list[dict] = []
    b_all = border_mask(labels)
    rows.append(
        {
            "boundary": "all",
            "border_px": int(b_all.sum()),
            "axis_step_frac": round(axis_step_frac(labels, b_all, axis_tol), 4),
            "corner_per_100px": round(corner_per_100px(labels, b_all), 2),
            "mean_crack_run_px": round(mean_crack_run_px(labels), 3),
            "length_ratio": "",
        }
    )
    if water:
        land = ~np.isin(labels, np.fromiter(water, dtype=np.int32))
        wl = land.astype(np.int32)  # a 2-label map: the coastline only
        b_coast = border_mask(wl)
        rows.append(
            {
                "boundary": "coast",
                "border_px": int(b_coast.sum()),
                "axis_step_frac": round(axis_step_frac(wl, b_coast, axis_tol), 4),
                "corner_per_100px": round(corner_per_100px(wl, b_coast), 2),
                "mean_crack_run_px": round(mean_crack_run_px(wl), 3),
                "length_ratio": round(length_ratio(land, smooth_sigma), 4),
            }
        )
    return rows


# --------------------------------------------------------------------------- #
def _parse_kv(values: list[str], what: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for v in values or ():
        if "=" not in v:
            raise SystemExit(f"--{what} wants NAME=VALUE, got {v!r}")
        k, _, rest = v.partition("=")
        out[k] = rest
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--map", action="append", required=True,
                    help="NAME=path/to/map_data (repeatable)")
    ap.add_argument("--crop", action="append", default=[],
                    help="NAME=x0,y0,x1,y1 window for that map")
    ap.add_argument("--axis-tol", type=float, default=11.25,
                    help="degrees from an axis that still counts as axis-aligned")
    ap.add_argument("--smooth-sigma", type=float, default=2.0,
                    help="Gaussian sigma of the length_ratio reference")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)

    maps = _parse_kv(args.map, "map")
    crops = _parse_kv(args.crop, "crop")

    rows: list[dict] = []
    for name, path in maps.items():
        md = Path(path)
        labels = read_labels(md)
        water = read_water_colours(md)
        box = ""
        if name in crops:
            x0, y0, x1, y1 = (int(v) for v in crops[name].split(","))
            labels = labels[y0:y1, x0:x1]
            box = crops[name]
        for row in measure(labels, water, axis_tol=args.axis_tol,
                           smooth_sigma=args.smooth_sigma):
            rows.append({"map": name, "crop": box, "km_per_px": KM_PER_PX,
                         "width": labels.shape[1], "height": labels.shape[0],
                         **row})
            print(f"{name:14s} {box:22s} {row['boundary']:6s} "
                  f"border_px={row['border_px']:>9d} "
                  f"axis={row['axis_step_frac']} "
                  f"corners/100={row['corner_per_100px']} "
                  f"run={row['mean_crack_run_px']} "
                  f"len_ratio={row['length_ratio']}", flush=True)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
