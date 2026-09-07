"""``provinces.bmp`` (CK2) -> ``provinces.png`` (CK3), with a lost-province report.

The resize is NEAREST — any interpolation invents colours that are not province
ids.  Upscaling cannot lose a province, but the converter still runs the
survival check because the scale factor is a config value and someone will
eventually point it downwards.

CK3 wants provinces.png as 24-bit RGB (vanilla is; a palette image is rejected,
`assumed`), and every colour in ``definition.csv`` must own at least one pixel or
the game logs a province error.  So the pipeline is:

1. index the CK2 bitmap by colour once (a colour -> id lookup on a 24-bit key);
2. resize the *id* array, not the RGB array, so the survival check is exact;
3. re-grow any province that fell under ``min_pixels`` by dilating it inside its
   own CK2 footprint;
4. anything still missing is dropped from the CK3 output and listed in
   ``docs/evidence/lost_provinces.csv``.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

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
) -> ProvinceRaster:
    with Image.open(ck2_provinces_bmp) as im:
        src_rgb = np.asarray(im.convert("RGB"))

    colour_to_id: dict[int, int] = {}
    for p in ck2_provinces:
        colour_to_id[(p.rgb[0] << 16) | (p.rgb[1] << 8) | p.rgb[2]] = p.id

    keys = rgb_key(src_rgb)
    src_ids, undefined = _keys_to_ids(keys, colour_to_id)
    src_counts = _counts(src_ids)

    tgt = _resize_ids(src_ids, canvas)
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
    )


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
    """NEAREST resize of the id array, pasted on a PADDING canvas."""
    sh, sw = src_ids.shape
    rows = (np.arange(canvas.scaled_height) * sh // canvas.scaled_height).clip(0, sh - 1)
    cols = (np.arange(canvas.scaled_width) * sw // canvas.scaled_width).clip(0, sw - 1)
    scaled = src_ids[rows[:, None], cols[None, :]]

    out = np.full((canvas.height, canvas.width), PADDING, dtype=np.int32)
    y0, x0 = canvas.offset_y, canvas.offset_x
    out[y0 : y0 + canvas.scaled_height, x0 : x0 + canvas.scaled_width] = scaled
    return out


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
    sh, sw = src_ids.shape
    f = canvas.factor
    regrown: list[int] = []
    for pid in sorted(weak):
        sy, sx = np.nonzero(src_ids == pid)
        if len(sy) == 0:
            continue
        ty = np.clip((sy * f).astype(np.int64) + canvas.offset_y, 0, canvas.height - 1)
        tx = np.clip((sx * f).astype(np.int64) + canvas.offset_x, 0, canvas.width - 1)
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
