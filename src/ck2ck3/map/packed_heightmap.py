"""CK3 packed heightmap: reader and writer for the ``*.heightmap`` triple.

``map_data/default.map`` line 7 is ``topology = "heightmap.heightmap"``: CK3
1.19 does **not** load ``heightmap.png`` at runtime, it loads the descriptor
``map_data/heightmap.heightmap`` and through it a *packed pair*

* ``packed_heightmap.png``      -- 16-bit grey atlas of LOD tiles
* ``indirection_heightmap.png`` -- 8-bit RGBA, one pixel per tile

The whole format was reverse-engineered from vanilla 1.19, Elder Kings 2
(workshop 2887120253) and Godherja (2326030123); every claim in this module has
its evidence written down in ``docs/formats_packed_heightmap.md``.  Short
version, because the two traps below cost hours:

1. **All three images are bottom-up** (DDS/OpenGL convention).  Read them with
   ``[::-1]`` and every coordinate in the descriptor becomes trivially
   consistent; read them top-down and the atlas y offsets come out off by one
   and appear to contradict ``level_offsets``.
2. **Tiles overlap by one pixel.**  ``tile_size=65`` means a *stride* of 64, so
   ``18432/64 = 288`` by ``9216/64 = 144`` = the exact size of vanilla's
   indirection image.  The last tile row/column therefore needs one pixel that
   is off the heightmap; vanilla clamps (edge-extend), it does not wrap.

Indirection pixel -> tile:  ``R = r``, ``G = g``, ``B = 2**level``,
``A = level``; the tile lives at ``level_offsets[level] + (r*px, g*px)`` in the
bottom-up atlas, where ``px = ((tile_size-1) >> level) + 1``.

Tile content is *decimation*, not averaging: ``tile[p][i] = height[ty*stride +
p*2**L][tx*stride + i*2**L]``.  The four edge lines are the exception -- they
are resampled at the coarsest level of the two tiles sharing them, which is
what keeps neighbouring LODs crack-free and is the only lossy part of a level-0
tile.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None

#: A tile is stored at the highest level whose bilinear reconstruction stays
#: within this many 16-bit units of the source.  Fitted against Godherja's own
#: choices (99.6% agreement, 1483 tiles); best fit 651-655, and 655 is
#: ``round(0.01 * 65535)``, so 1% of full range is almost certainly the rule
#: Paradox's map editor uses.  See docs/formats_packed_heightmap.md.
LEVEL_MAX_ERROR = 655

#: Indirection ``R``/``G`` are single bytes, so no level may need more than
#: this many tile columns or rows in the atlas.
MAX_ATLAS_TILES_PER_AXIS = 256

_DESCRIPTOR_KEYS = (
    "heightmap_file",
    "indirection_file",
    "original_heightmap_size",
    "tile_size",
    "should_wrap_x",
    "level_offsets",
    "max_compress_level",
    "empty_tile_offset",
)


@dataclass
class HeightmapDescriptor:
    """Parsed ``heightmap.heightmap``.  Field order == vanilla's key order."""

    heightmap_file: str
    indirection_file: str
    original_heightmap_size: tuple[int, int]
    tile_size: int
    should_wrap_x: bool
    level_offsets: list[tuple[int, int]] = field(default_factory=list)
    max_compress_level: int = 4
    empty_tile_offset: tuple[int, int] = (0, 0)

    @property
    def stride(self) -> int:
        return self.tile_size - 1

    @property
    def grid_size(self) -> tuple[int, int]:
        w, h = self.original_heightmap_size
        return w // self.stride, h // self.stride

    def tile_px(self, level: int) -> int:
        return ((self.tile_size - 1) >> level) + 1

    def to_text(self) -> str:
        """Vanilla's exact key order, spacing and LF endings (no BOM)."""
        w, h = self.original_heightmap_size
        offs = " ".join(f"{{ {x} {y} }}" for x, y in self.level_offsets)
        er, eg = self.empty_tile_offset
        return (
            f'heightmap_file="{self.heightmap_file}"\n'
            f'indirection_file="{self.indirection_file}"\n'
            f"original_heightmap_size={{ {w} {h} }}\n"
            f"tile_size={self.tile_size}\n"
            f"should_wrap_x={'yes' if self.should_wrap_x else 'no'}\n"
            f"level_offsets={{ {offs} }}\n"
            f"max_compress_level={self.max_compress_level}\n"
            f"empty_tile_offset={{ {er} {eg} }}\n"
        )

    def write(self, path: Path) -> None:
        """UTF-8 **with BOM** -- vanilla's file starts ``ef bb bf``."""
        path.write_text(self.to_text(), encoding="utf-8-sig", newline="\n")


def parse_descriptor(text: str) -> HeightmapDescriptor:
    """Parse a ``*.heightmap`` body.  Tolerates CRLF (both mods ship CRLF)."""
    values: dict[str, str] = {}
    for raw in text.replace("﻿", "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        values[key.strip()] = val.strip()

    def ints(key: str) -> list[int]:
        return [int(t) for t in values[key].replace("{", " ").replace("}", " ").split()]

    size = ints("original_heightmap_size")
    offs = ints("level_offsets")
    empty = ints("empty_tile_offset")
    return HeightmapDescriptor(
        heightmap_file=values["heightmap_file"].strip('"'),
        indirection_file=values["indirection_file"].strip('"'),
        original_heightmap_size=(size[0], size[1]),
        tile_size=int(values["tile_size"]),
        should_wrap_x=values.get("should_wrap_x", "no") == "yes",
        level_offsets=[(offs[i], offs[i + 1]) for i in range(0, len(offs), 2)],
        max_compress_level=int(values["max_compress_level"]),
        empty_tile_offset=(empty[0], empty[1]),
    )


def read_descriptor(path: Path) -> HeightmapDescriptor:
    return parse_descriptor(Path(path).read_text(encoding="utf-8-sig"))


# --------------------------------------------------------------------------- #
# resampling helpers
# --------------------------------------------------------------------------- #


def _upsample_matrix(px: int, scale: int) -> np.ndarray:
    """``(ts, px)`` bilinear-along-one-axis matrix, ``ts = (px-1)*scale + 1``."""
    ts = (px - 1) * scale + 1
    m = np.zeros((ts, px))
    for i in range(ts):
        k, rem = divmod(i, scale)
        if rem == 0:
            m[i, k] = 1.0
        else:
            f = rem / scale
            m[i, k] = 1.0 - f
            m[i, k + 1] = f
    return m


def _line_resample_matrix(length: int, step: int) -> np.ndarray:
    """``(length, length)`` matrix: keep every ``step``-th sample, interpolate.

    ``step`` must divide ``length - 1`` so the endpoints survive -- that is what
    makes tile *corners* exact even though tile *edges* are resampled.
    """
    if step == 1:
        return np.eye(length)
    m = np.zeros((length, length))
    for i in range(length):
        k, rem = divmod(i, step)
        if rem == 0:
            m[i, i] = 1.0
        else:
            f = rem / step
            m[i, k * step] = 1.0 - f
            m[i, (k + 1) * step] = f
    return m


def _pad_edge(height_bu: np.ndarray, wrap_x: bool) -> np.ndarray:
    """Grow by one row/column so the last tile row/column has its overlap pixel.

    Vanilla clamps in both axes (verified: the outer edge of the right-most and
    top-most tiles equals the last heightmap column/row, and does *not* equal
    column 0).  ``should_wrap_x=yes`` is nowhere in the three maps we have, so
    wrapping x is `assumed`.
    """
    h, w = height_bu.shape
    out = np.empty((h + 1, w + 1), dtype=height_bu.dtype)
    out[:h, :w] = height_bu
    out[:h, w] = height_bu[:, 0] if wrap_x else height_bu[:, -1]
    out[h, :w] = height_bu[-1, :]
    out[h, w] = out[h - 1, w]
    return out


# --------------------------------------------------------------------------- #
# decode
# --------------------------------------------------------------------------- #


def decode_arrays(
    packed_bu: np.ndarray,
    indirection_bu: np.ndarray,
    desc: HeightmapDescriptor,
) -> np.ndarray:
    """Rebuild the top-down ``heightmap.png`` array from bottom-up atlas data."""
    w, h = desc.original_heightmap_size
    stride = desc.stride
    nx, ny = desc.grid_size
    if indirection_bu.shape[:2] != (ny, nx):
        raise ValueError(
            f"indirection is {indirection_bu.shape[1]}x{indirection_bu.shape[0]}, "
            f"but original_heightmap_size/{stride} implies {nx}x{ny}"
        )

    canvas = np.zeros((h + 1, w + 1), dtype=np.uint16)
    ups = {
        lv: _upsample_matrix(desc.tile_px(lv), 1 << lv)
        for lv in range(desc.max_compress_level + 1)
    }
    ah = packed_bu.shape[0]
    for ty in range(ny):
        for tx in range(nx):
            r, g, _b, lv = (int(v) for v in indirection_bu[ty, tx, :4])
            px = desc.tile_px(lv)
            ox, oy = desc.level_offsets[lv]
            y0, x0 = oy + g * px, ox + r * px
            blk = packed_bu[y0 : y0 + px, x0 : x0 + px]
            if blk.shape != (px, px):
                raise ValueError(
                    f"tile ({tx},{ty}) level {lv} points at ({x0},{y0}) which is "
                    f"outside the {packed_bu.shape[1]}x{ah} atlas"
                )
            u = ups[lv]
            tile = u @ blk.astype(np.float64) @ u.T
            canvas[ty * stride : ty * stride + desc.tile_size,
                   tx * stride : tx * stride + desc.tile_size] = (
                np.rint(tile).clip(0, 65535).astype(np.uint16)
            )
    return canvas[:h, :w][::-1].copy()


def decode_packed(map_data_dir: Path, descriptor_name: str = "heightmap.heightmap"):
    """Read the triple in ``map_data_dir`` and return ``(heightmap, descriptor)``."""
    map_data_dir = Path(map_data_dir)
    desc = read_descriptor(map_data_dir / descriptor_name)
    packed = np.array(Image.open(map_data_dir / Path(desc.heightmap_file).name))
    indirection = np.array(Image.open(map_data_dir / Path(desc.indirection_file).name))
    if indirection.ndim != 3 or indirection.shape[2] < 4:
        raise ValueError("indirection_heightmap.png must be 8-bit RGBA")
    return decode_arrays(packed[::-1], indirection[::-1], desc), desc


# --------------------------------------------------------------------------- #
# encode
# --------------------------------------------------------------------------- #


def _choose_levels(
    padded_bu: np.ndarray, tile_size: int, max_level: int, threshold: int
) -> np.ndarray:
    """Highest level per tile whose bilinear reconstruction error <= threshold."""
    stride = tile_size - 1
    ny = (padded_bu.shape[0] - 1) // stride
    nx = (padded_bu.shape[1] - 1) // stride
    levels = np.zeros((ny, nx), dtype=np.uint8)
    windows = np.lib.stride_tricks.sliding_window_view(padded_bu, (tile_size, tile_size))
    mats = {lv: _upsample_matrix(((tile_size - 1) >> lv) + 1, 1 << lv) for lv in range(1, max_level + 1)}
    for ty in range(ny):
        # one tile row at a time: (nx, ts, ts) float64 is a few MB
        row = windows[ty * stride, ::stride][:nx].astype(np.float64)
        best = np.zeros(nx, dtype=np.uint8)
        for lv in range(1, max_level + 1):
            s = 1 << lv
            u = mats[lv]
            rec = np.einsum("ik,nkl,jl->nij", u, row[:, ::s, ::s], u, optimize=True)
            ok = np.abs(rec - row).reshape(nx, -1).max(axis=1) <= threshold
            best[ok] = lv
        levels[ty] = best
    return levels


def _neighbour_levels(levels: np.ndarray, wrap_x: bool) -> dict[str, np.ndarray]:
    """Level of the tile on each side, clamped at the map border (or wrapped in x)."""
    lv = levels.astype(np.int32)
    return {
        "below": np.vstack([lv[:1], lv[:-1]]),
        "above": np.vstack([lv[1:], lv[-1:]]),
        "left": np.hstack([lv[:, -1:], lv[:, :-1]] if wrap_x else [lv[:, :1], lv[:, :-1]]),
        "right": np.hstack([lv[:, 1:], lv[:, :1]] if wrap_x else [lv[:, 1:], lv[:, -1:]]),
    }


def _tile_row_with_fixed_edges(
    padded_bu: np.ndarray,
    ty: int,
    levels: np.ndarray,
    nb: dict[str, np.ndarray],
    tile_size: int,
    mats: dict[int, np.ndarray],
) -> np.ndarray:
    """``(nx, ts, ts)`` float tiles of grid row ``ty``, edges LOD-matched.

    Each of the four edges is resampled at ``2 ** max(own level, neighbour
    level)`` and rounded with ``floor(x + 0.5)``.  That reproduces Godherja's
    stored edge pixels exactly (26384/26384 sampled edge values), and it is
    what keeps neighbouring LODs crack-free: the shared line has to be
    identical on both sides, so it is sampled at the coarser of the two.
    Endpoints survive the resample, so tile *corners* stay exact even when up
    to four different levels meet there.
    """
    stride = tile_size - 1
    nx = levels.shape[1]
    windows = np.lib.stride_tricks.sliding_window_view(padded_bu, (tile_size, tile_size))
    tiles = windows[ty * stride, ::stride][:nx].astype(np.float64)

    def mat(step: int) -> np.ndarray:
        if step not in mats:
            mats[step] = _line_resample_matrix(tile_size, step)
        return mats[step]

    own = levels[ty].astype(np.int32)
    for side, sel in (
        ("below", (slice(None), 0, slice(None))),
        ("above", (slice(None), tile_size - 1, slice(None))),
        ("left", (slice(None), slice(None), 0)),
        ("right", (slice(None), slice(None), tile_size - 1)),
    ):
        lines = tiles[sel]  # (nx, ts)
        step = 1 << np.maximum(own, nb[side][ty])
        for s in np.unique(step):
            if s == 1:
                continue
            m = step == s
            lines[m] = np.floor(lines[m] @ mat(int(s)).T + 0.5)
        tiles[sel] = lines
    return tiles


def _pack_atlas(
    padded_bu: np.ndarray,
    levels: np.ndarray,
    tile_size: int,
    max_level: int,
    wrap_x: bool,
) -> tuple[np.ndarray, np.ndarray, list[tuple[int, int]], tuple[int, int]]:
    """Build, dedupe and lay out every tile; return atlas + indirection (bottom-up).

    Streams one grid row at a time -- a vanilla-sized 18432x9216 heightmap has
    41472 tiles of 65x65 and materialising them all at once is 1.4 GB.
    """
    ny, nx = levels.shape
    nb = _neighbour_levels(levels, wrap_x)
    mats: dict[int, np.ndarray] = {}
    # per level: key -> (block, slot index, reference count)
    per_level: list[dict[bytes, tuple[np.ndarray, int, int]]] = [
        {} for _ in range(max_level + 1)
    ]
    slot_of = np.zeros((ny, nx), dtype=np.int32)
    for ty in range(ny):
        row = _tile_row_with_fixed_edges(padded_bu, ty, levels, nb, tile_size, mats)
        for tx in range(nx):
            lv = int(levels[ty, tx])
            s = 1 << lv
            blk = np.rint(row[tx, ::s, ::s]).clip(0, 65535).astype(np.uint16)
            key = blk.tobytes()
            entry = per_level[lv].get(key)
            if entry is None:
                per_level[lv][key] = (blk, len(per_level[lv]), 1)
                slot_of[ty, tx] = len(per_level[lv]) - 1
            else:
                per_level[lv][key] = (entry[0], entry[1], entry[2] + 1)
                slot_of[ty, tx] = entry[1]

    # atlas width: square-ish for the total occupied area, then widened until
    # every level fits in 256 tile rows (indirection R/G are single bytes).
    area = sum(
        len(per_level[lv]) * (((tile_size - 1) >> lv) + 1) ** 2
        for lv in range(max_level + 1)
    )
    min_w = max(
        (((tile_size - 1) >> lv) + 1) for lv in range(max_level + 1) if per_level[lv]
    )
    atlas_w = max(min_w, math.isqrt(max(area - 1, 0)) + 1)
    while True:
        plan = []
        for lv in range(max_level + 1):
            px = ((tile_size - 1) >> lv) + 1
            cols = min(MAX_ATLAS_TILES_PER_AXIS, max(1, atlas_w // px))
            rows = math.ceil(len(per_level[lv]) / cols) if per_level[lv] else 0
            plan.append((px, cols, rows))
        if all(rows <= MAX_ATLAS_TILES_PER_AXIS for _px, _c, rows in plan):
            break
        if all(cols >= MAX_ATLAS_TILES_PER_AXIS for _px, cols, _r in plan):
            raise ValueError(
                "too many distinct tiles for the 8-bit indirection offsets "
                "(256x256 per level); raise max_compress_level or shrink the heightmap"
            )
        atlas_w *= 2

    level_offsets: list[tuple[int, int]] = []
    y = 0
    for _px, _cols, rows in plan:
        level_offsets.append((0, y))
        y += rows * _px
    atlas_h = max(y, 1)

    atlas = np.zeros((atlas_h, atlas_w), dtype=np.uint16)
    # slot index -> (r, g), per level
    coords: list[np.ndarray] = []
    for lv in range(max_level + 1):
        px, cols, _rows = plan[lv]
        oy = level_offsets[lv][1]
        rg = np.zeros((max(len(per_level[lv]), 1), 2), dtype=np.uint8)
        for blk, i, _count in per_level[lv].values():
            r, g = i % cols, i // cols
            atlas[oy + g * px : oy + g * px + px, r * px : r * px + px] = blk
            rg[i] = (r, g)
        coords.append(rg)

    indirection = np.zeros((ny, nx, 4), dtype=np.uint8)
    for lv in range(max_level + 1):
        m = levels == lv
        if not m.any():
            continue
        indirection[m, :2] = coords[lv][slot_of[m]]
        indirection[m, 2] = 1 << lv
        indirection[m, 3] = lv

    # empty_tile_offset: most-referenced *uniform* tile at max_compress_level.
    # Vanilla, EK2 and Godherja all point at an all-zero tile of that level.
    empty = (0, 0)
    best = -1
    for blk, i, count in per_level[max_level].values():
        if blk.min() == blk.max() and count > best:
            best, empty = count, tuple(int(v) for v in coords[max_level][i])
    if best < 0:
        for _blk, i, count in per_level[max_level].values():
            if count > best:
                best, empty = count, tuple(int(v) for v in coords[max_level][i])
    return atlas, indirection, level_offsets, empty


def write_packed(
    heightmap: np.ndarray,
    out_dir: Path,
    *,
    tile_size: int = 33,
    max_compress_level: int = 4,
    should_wrap_x: bool = False,
    level_threshold: int = LEVEL_MAX_ERROR,
    verify: bool = True,
) -> dict:
    """Write ``packed_heightmap.png`` + ``indirection_heightmap.png`` + descriptor.

    ``heightmap`` is a top-down 2-D ``uint16`` array, exactly as
    ``heightmap.png`` stores it.  Both dimensions must be a multiple of
    ``tile_size - 1`` (a ValueError otherwise -- CK3 derives the tile grid by
    integer division, so a non-multiple would silently drop the last strip).

    Returns the descriptor fields plus atlas statistics; with ``verify`` the
    result also carries the round-trip error of what was just written.
    """
    out_dir = Path(out_dir)
    heightmap = np.asarray(heightmap)
    if heightmap.ndim != 2:
        raise ValueError(f"heightmap must be 2-D, got shape {heightmap.shape}")
    if heightmap.dtype != np.uint16:
        raise ValueError(f"heightmap must be uint16 (16-bit PNG), got {heightmap.dtype}")
    if tile_size < 3 or (tile_size - 1) % (1 << max_compress_level):
        raise ValueError(
            f"tile_size-1 ({tile_size - 1}) must be a multiple of "
            f"2**max_compress_level ({1 << max_compress_level})"
        )
    stride = tile_size - 1
    h, w = heightmap.shape
    if w % stride or h % stride:
        raise ValueError(
            f"heightmap {w}x{h} is not a multiple of the tile stride {stride} "
            f"(tile_size {tile_size}); pad the heightmap first"
        )

    padded = _pad_edge(heightmap[::-1].astype(np.float64), should_wrap_x)
    levels = _choose_levels(padded, tile_size, max_compress_level, level_threshold)
    atlas, indirection, level_offsets, empty = _pack_atlas(
        padded, levels, tile_size, max_compress_level, should_wrap_x
    )

    desc = HeightmapDescriptor(
        heightmap_file="map_data/packed_heightmap.png",
        indirection_file="map_data/indirection_heightmap.png",
        original_heightmap_size=(w, h),
        tile_size=tile_size,
        should_wrap_x=should_wrap_x,
        level_offsets=level_offsets,
        max_compress_level=max_compress_level,
        empty_tile_offset=empty,
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    Image.fromarray(atlas[::-1]).save(out_dir / "packed_heightmap.png", optimize=True)
    Image.fromarray(indirection[::-1], mode="RGBA").save(
        out_dir / "indirection_heightmap.png", optimize=True
    )
    desc.write(out_dir / "heightmap.heightmap")

    ny, nx = levels.shape
    meta = {
        "heightmap_file": desc.heightmap_file,
        "indirection_file": desc.indirection_file,
        "original_heightmap_size": desc.original_heightmap_size,
        "tile_size": tile_size,
        "should_wrap_x": should_wrap_x,
        "level_offsets": level_offsets,
        "max_compress_level": max_compress_level,
        "empty_tile_offset": empty,
        "grid_size": (nx, ny),
        "atlas_size": (atlas.shape[1], atlas.shape[0]),
        "level_histogram": np.bincount(levels.ravel(), minlength=max_compress_level + 1).tolist(),
        "distinct_tiles": int(
            len(np.unique(indirection[:, :, (0, 1, 3)].reshape(-1, 3), axis=0))
        ),
        "packed_bytes": (out_dir / "packed_heightmap.png").stat().st_size,
        "indirection_bytes": (out_dir / "indirection_heightmap.png").stat().st_size,
    }
    if verify:
        back = decode_arrays(atlas, indirection, desc)
        err = np.abs(back.astype(np.int64) - heightmap.astype(np.int64))
        meta["max_abs_error"] = int(err.max())
        meta["mean_abs_error"] = float(err.mean())
        meta["exact_fraction"] = float((err == 0).mean())
    return meta
