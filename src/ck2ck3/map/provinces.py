"""``provinces.bmp`` (CK2) -> ``provinces.png`` (CK3), with a lost-province report.

The resize is NEAREST on the *id* array by default — any interpolation of the
RGB invents colours that are not province ids.  Upscaling cannot lose a
province, but the converter still runs the survival check because the scale
factor is a config value and someone will eventually point it downwards.

NEAREST has a cost the user saw at close zoom: CK2's bitmap is 2.90 km per
pixel and the canvas is 1.9543x finer, so every border comes out as a 2x2
staircase (`verified`: the mean straight run of a boundary crack is 3.39
canvas px against vanilla's 1.76 — the upsample factor, exactly).
``[map.provinces] smooth_edges`` routes the resize through
:mod:`ck2ck3.map.province_edges` instead: each province's own indicator is
upsampled smoothly and the winner at each pixel takes it.  That is still an
id — the argmax of indicators can only return a label that exists — and it is
bounded to one CK2 source pixel by the same reachability check the paint lane
uses.  Everything below (the survival check, the regrow, the lost report)
then runs on the smoothed array unchanged.

CK3 wants provinces.png as 24-bit RGB (vanilla is; a palette image is rejected,
`assumed`), and every colour in ``definition.csv`` must own at least one pixel or
the game logs a province error.  So the pipeline is:

1. index the CK2 bitmap by colour once (a colour -> id lookup on a 24-bit key);
2. resize the *id* array, not the RGB array, so the survival check is exact
   (NEAREST, or the bounded smooth argmax of ``smooth_edges``);
3. re-grow any province that fell under ``min_pixels`` by dilating it inside its
   own CK2 footprint;
4. anything still missing is dropped from the CK3 output and listed in
   ``docs/evidence/lost_provinces.csv``.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image

from . import paint_edges, province_edges
from .ck2read import Ck2Province
from .config import Canvas

Image.MAX_IMAGE_PIXELS = None

#: sentinel id for "no CK2 province here" (the padding ocean)
PADDING = 0


@dataclass
class ProvinceRaster:
    """Target-resolution CK2-id raster plus the survival bookkeeping."""

    #: (canvas.height, canvas.width) int32 array of CK2 province ids, PADDING outside
    ids: np.ndarray
    #: CK2 id -> pixel count at target resolution (after re-growing)
    pixel_counts: dict[int, int]
    surviving: set[int]
    #: CK2 id -> (source pixel count, target pixel count) for those that died
    lost: dict[int, tuple[int, int]]
    #: CK2 ids rescued by the dilation pass
    regrown: list[int]
    #: CK2 colours found in the bitmap but absent from definition.csv
    undefined_colours: dict[tuple[int, int, int], int]
    #: what the smooth-edge pass did, empty when it is off (docs/step_map_baronies.md §10)
    edges: dict[str, float | int | str] = field(default_factory=dict)


def rgb_key(arr: np.ndarray) -> np.ndarray:
    """Pack an ``(h, w, 3)`` uint8 array into an ``(h, w)`` int32 colour key."""
    a = arr.astype(np.int32)
    return (a[..., 0] << 16) | (a[..., 1] << 8) | a[..., 2]


def build_raster(
    ck2_provinces_bmp: str | Path,
    ck2_provinces: list[Ck2Province],
    canvas: Canvas,
    *,
    min_pixels: int = 16,
    regrow: bool = True,
    smooth_edges: bool = False,
    smooth_sigma_src_px: float = 0.6,
    max_shift_source_px: float = 1.0,
    warp: tuple[np.ndarray, np.ndarray] | None = None,
) -> ProvinceRaster:
    """Rasterise ``provinces.bmp`` onto ``canvas``.

    ``smooth_edges`` replaces the NEAREST resize with
    :func:`ck2ck3.map.province_edges.smooth_resize_ids` and, if ``warp`` is
    given, samples the result through that relief field before bounding the
    whole displacement to ``max_shift_source_px`` CK2 source pixels against
    the NEAREST raster.  ``warp`` is the ``(dy, dx)`` pair from
    :func:`ck2ck3.map.paint_edges.relief_warp`, so the province borders and
    the terrain-paint class edges bend with the same ground.
    """
    with Image.open(ck2_provinces_bmp) as im:
        src_rgb = np.asarray(im.convert("RGB"))

    colour_to_id: dict[int, int] = {}
    for p in ck2_provinces:
        colour_to_id[(p.rgb[0] << 16) | (p.rgb[1] << 8) | p.rgb[2]] = p.id

    keys = rgb_key(src_rgb)
    src_ids, undefined = _keys_to_ids(keys, colour_to_id)
    src_counts = _counts(src_ids)

    tgt = _resize_ids(src_ids, canvas)
    edges: dict[str, float | int | str] = {}
    if smooth_edges:
        tgt, edges = _smooth_edges(
            src_ids,
            tgt,
            canvas,
            sigma_src_px=smooth_sigma_src_px,
            max_shift_source_px=max_shift_source_px,
            warp=warp,
        )
    counts = _counts(tgt)

    regrown: list[int] = []
    if regrow:
        weak = [
            pid
            for pid in src_counts
            if pid != PADDING and counts.get(pid, 0) < min_pixels
        ]
        if weak:
            tgt, regrown = _regrow(tgt, src_ids, canvas, weak, min_pixels)
            counts = _counts(tgt)

    surviving = {
        pid for pid, n in counts.items() if pid != PADDING and n >= min_pixels
    }
    lost = {
        pid: (src_counts[pid], counts.get(pid, 0))
        for pid in src_counts
        if pid != PADDING and pid not in surviving
    }
    # a province defined in CSV but absent from the bitmap is lost too
    for p in ck2_provinces:
        if p.id not in src_counts:
            lost.setdefault(p.id, (0, 0))

    # blank out the pixels of dropped provinces so they read as padding ocean
    if lost:
        tgt = np.where(np.isin(tgt, list(lost)), PADDING, tgt)
        counts = _counts(tgt)

    return ProvinceRaster(
        ids=tgt,
        pixel_counts={k: v for k, v in counts.items() if k != PADDING},
        surviving=surviving,
        lost=lost,
        regrown=regrown,
        undefined_colours=undefined,
        edges=edges,
    )


def _smooth_edges(
    src_ids: np.ndarray,
    nearest: np.ndarray,
    canvas: Canvas,
    *,
    sigma_src_px: float,
    max_shift_source_px: float,
    warp: tuple[np.ndarray, np.ndarray] | None,
) -> tuple[np.ndarray, dict[str, float | int | str]]:
    """Smooth argmax upsample, optional relief warp, bounded against NEAREST.

    The bound is enforced, not hoped for: a pixel keeps its smoothed id only
    if NEAREST already painted that id within ``max_shift_source_px`` CK2
    source pixels of it.  Everything else reverts, so no province can reach
    ground CK2 never gave it — which is what keeps the province *set* and the
    macro geography identical while the outline changes shape.
    """
    smooth = province_edges.smooth_resize_ids(
        src_ids, canvas, sigma_src_px=sigma_src_px
    )
    warped_px = 0
    if warp is not None:
        dy, dx = warp
        if dy.shape != smooth.shape:
            raise ValueError(
                f"relief warp {dy.shape} does not match the canvas {smooth.shape}"
            )
        warped_px = int(((dy != 0) | (dx != 0)).sum())
        smooth = paint_edges.warp_apply(smooth, dy, dx)

    radius = float(max_shift_source_px) * canvas.factor
    ok = paint_edges.within_radius(nearest, smooth, radius)
    reverted = int((~ok).sum())
    out = np.where(ok, smooth, nearest).astype(np.int32)

    stats = paint_edges.class_displacement_stats(
        nearest, out, km_per_px=1.0, max_radius=4
    )
    return out, {
        "smooth": 1,
        "sigma_src_px": float(sigma_src_px),
        "max_shift_source_px": float(max_shift_source_px),
        "bound_px": round(radius, 4),
        "relief_warped_px": warped_px,
        "reverted_px": reverted,
        "changed_px": int(stats["changed_px"]),
        "changed_share": float(stats["changed_share"]),
        "max_shift_px": float(stats["max_px"]),
        "p95_shift_px": float(stats["p95_px"]),
        "beyond_bound_px": float(stats["beyond_radius_px"]),
    }


def _keys_to_ids(
    keys: np.ndarray, colour_to_id: dict[int, int]
) -> tuple[np.ndarray, dict[tuple[int, int, int], int]]:
    """Map a colour-key array to province ids via a sorted-unique lookup."""
    uniq, inverse, counts = np.unique(keys, return_inverse=True, return_counts=True)
    lut = np.zeros(len(uniq), dtype=np.int32)
    undefined: dict[tuple[int, int, int], int] = {}
    for i, k in enumerate(uniq.tolist()):
        pid = colour_to_id.get(k)
        if pid is None:
            # counts comes from the same np.unique pass; recounting per colour
            # would be one full scan of a 13.6 M-pixel array per colour
            undefined[((k >> 16) & 255, (k >> 8) & 255, k & 255)] = int(counts[i])
            lut[i] = PADDING
        else:
            lut[i] = pid
    return lut[inverse].reshape(keys.shape), undefined


def _counts(ids: np.ndarray) -> dict[int, int]:
    uniq, n = np.unique(ids, return_counts=True)
    return {int(u): int(c) for u, c in zip(uniq, n)}


def _resize_ids(src_ids: np.ndarray, canvas: Canvas) -> np.ndarray:
    """NEAREST resize of the id array, pasted on a PADDING canvas.

    Only ``canvas.crop_*`` of the source is used, so unpainted source border
    never becomes padding ocean on the target.
    """
    sh, sw = crop_size(src_ids, canvas)
    rows = (np.arange(canvas.scaled_height) * sh // canvas.scaled_height).clip(0, sh - 1)
    cols = (np.arange(canvas.scaled_width) * sw // canvas.scaled_width).clip(0, sw - 1)
    scaled = src_ids[canvas.crop_y0 + rows[:, None], canvas.crop_x0 + cols[None, :]]

    out = np.full((canvas.height, canvas.width), PADDING, dtype=np.int32)
    y0, x0 = canvas.offset_y, canvas.offset_x
    out[y0 : y0 + canvas.scaled_height, x0 : x0 + canvas.scaled_width] = scaled
    return out


def crop_size(src: np.ndarray, canvas: Canvas) -> tuple[int, int]:
    """``(height, width)`` of the source rectangle the canvas is built from."""
    sh, sw = src.shape[:2]
    ch = canvas.crop_height or sh
    cw = canvas.crop_width or sw
    return ch, cw


def painted_extent(src_ids: np.ndarray) -> tuple[int, int, int, int]:
    """Bounding box ``(x0, y0, x1, y1)`` of pixels CK2 assigned to a province.

    Half-open, so it can be handed straight to
    :func:`ck2ck3.map.config.plan_canvas`.  A bitmap with no painted pixel at
    all is a broken input and raises.

    `verified` on Faerûn 2026-09-07: this returns the whole 4096x3328 bitmap.
    The mod's 21 % of unassigned white pixels are *interior* — the southern and
    western ocean between painted sea provinces — not a border, so the crop
    saves nothing there.  It is still the right pass to run: it costs one
    boolean reduction and it is what stops a mod that *does* have an unpainted
    margin from paying for it in every output file.  See docs/map_scale.md §7.
    """
    rows = np.flatnonzero((src_ids != PADDING).any(axis=1))
    cols = np.flatnonzero((src_ids != PADDING).any(axis=0))
    if rows.size == 0 or cols.size == 0:
        raise ValueError("provinces.bmp has no pixel that definition.csv defines")
    return int(cols[0]), int(rows[0]), int(cols[-1]) + 1, int(rows[-1]) + 1


def _regrow(
    tgt: np.ndarray,
    src_ids: np.ndarray,
    canvas: Canvas,
    weak: list[int],
    min_pixels: int,
) -> tuple[np.ndarray, list[int]]:
    """Rescue each weak province inside its own CK2 footprint.

    The footprint bound is what makes this safe: a province only ever takes
    target pixels that its *own* CK2 pixels project onto, so it can never leak
    into a neighbour's territory or across a coastline.

    Only the handful of weak provinces are touched, so this stays cheap however
    big the canvas is — the naive "build a footprint raster for the whole map"
    version was 31 M Python iterations at Faerûn's target size.

    Ties are resolved in favour of the *weaker* province: pixels are claimed
    from whichever neighbour currently owns them, cheapest-first (padding
    ocean, then provinces that are themselves comfortably above the threshold).
    """
    f = canvas.factor
    regrown: list[int] = []
    for pid in sorted(weak):
        sy, sx = np.nonzero(src_ids == pid)
        if len(sy) == 0:
            continue
        ty = np.clip(
            ((sy - canvas.crop_y0) * f).astype(np.int64) + canvas.offset_y,
            0,
            canvas.height - 1,
        )
        tx = np.clip(
            ((sx - canvas.crop_x0) * f).astype(np.int64) + canvas.offset_x,
            0,
            canvas.width - 1,
        )
        # deduplicate target pixels, keep them in a stable order
        flat = np.unique(ty * canvas.width + tx)
        cand_y, cand_x = flat // canvas.width, flat % canvas.width
        owner = tgt[cand_y, cand_x]

        have = int((tgt == pid).sum())
        need = min_pixels - have
        if need <= 0:
            continue
        # cheapest first: padding, then anything that is not this province
        priority = np.where(owner == PADDING, 0, 1)
        order = np.argsort(priority, kind="stable")
        order = order[owner[order] != pid]
        take = order[:need]
        tgt[cand_y[take], cand_x[take]] = pid
        if int((tgt == pid).sum()) >= min_pixels:
            regrown.append(pid)
    return tgt, regrown


def to_rgb(
    raster: ProvinceRaster,
    id_to_rgb: dict[int, tuple[int, int, int]],
    padding_rgb: tuple[int, int, int],
) -> np.ndarray:
    """The ``provinces.png`` pixel array, 24-bit RGB."""
    max_id = max(id_to_rgb) if id_to_rgb else 0
    lut = np.zeros((max_id + 1, 3), dtype=np.uint8)
    lut[PADDING] = padding_rgb
    for pid, rgb in id_to_rgb.items():
        lut[pid] = rgb
    return lut[np.clip(raster.ids, 0, max_id)]


def save_png(rgb: np.ndarray, path: Path) -> None:
    """Write ``map_data/provinces.png``. CK3 wants 24-bit RGB, not a palette."""
    Image.fromarray(rgb, mode="RGB").save(path, optimize=True)


def render_png(
    raster: ProvinceRaster,
    id_to_rgb: dict[int, tuple[int, int, int]],
    padding_rgb: tuple[int, int, int],
    path: str | Path,
) -> None:
    """Convenience wrapper: build the array and write it in one call."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    save_png(to_rgb(raster, id_to_rgb, padding_rgb), out)


def render_lost_report(raster: ProvinceRaster, names: dict[int, str]) -> str:
    """``docs/evidence/lost_provinces.csv`` content."""
    buf = io.StringIO()
    if True:
        fh = buf
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["ck2_id", "name", "ck2_pixels", "ck3_pixels", "outcome"])
        for pid, (src_n, tgt_n) in sorted(raster.lost.items()):
            w.writerow([pid, names.get(pid, ""), src_n, tgt_n, "dropped"])
        for pid in sorted(raster.regrown):
            w.writerow([pid, names.get(pid, ""), "", raster.pixel_counts.get(pid, 0), "regrown"])
        for rgb, n in sorted(raster.undefined_colours.items(), key=lambda kv: -kv[1]):
            w.writerow(["", f"undefined colour {rgb}", n, 0, "not in definition.csv"])
    return buf.getvalue()


def write_lost_report(
    raster: ProvinceRaster, names: dict[int, str], path: str | Path
) -> None:
    """Convenience wrapper for the standalone entry point."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_lost_report(raster, names), encoding="utf-8", newline="")
