"""A small BC1 (DXT1) DDS writer, because CK3's flat map has to be one.

``gfx/map/terrain/flat_maps/flatmap.dds`` is DXT1 in all three reference maps
(`docs/evidence/map_ui_research.md` §4): vanilla 9216x4608 with **no** mip
chain, Elder Kings 2 8256x5504 and Godherja 8192x4096 with one level.  Godherja's
was written by GIMP, so no Paradox tool is involved and any BC1 encoder will do.

Pillow can *read* DDS but only gained a DXT1 *save* path recently, and this repo
pins no floor that guarantees it, so the 8-byte block is written here instead.

BC1 block layout, 4x4 texels in 8 bytes, little-endian:

===========  =====================================================
bytes 0-1    ``color0`` as RGB565
bytes 2-3    ``color1`` as RGB565
bytes 4-7    16 two-bit indices, texel ``(x, y)`` at bit ``2*(4*y + x)``
===========  =====================================================

With ``color0 > color1`` the palette is ``c0, c1, (2*c0+c1)/3, (c0+2*c1)/3``
(indices 0, 1, 2, 3) and there is no transparency, which is what the flat map
wants.  Encoding is a bounding-box fit: endpoints are the per-channel min and
max of the block, each texel takes the nearest of the four palette entries
along that axis.  For a paper map — large flat areas and slow gradients — that
is visually lossless and it vectorises, which a 56 Mpx sheet needs.
"""

from __future__ import annotations

import struct
from pathlib import Path

import numpy as np

#: DDS header constants.  ``DDSD_CAPS|HEIGHT|WIDTH|PIXELFORMAT|LINEARSIZE``
_DDSD = 0x1 | 0x2 | 0x4 | 0x1000 | 0x80000
_DDPF_FOURCC = 0x4
_DDSCAPS_TEXTURE = 0x1000

#: blocks per encode chunk; 1e6 blocks is ~200 MB of float32 scratch
_CHUNK = 1_000_000


def _to_565(rgb: np.ndarray) -> np.ndarray:
    """(..., 3) uint8 -> uint16 RGB565, **rounded** rather than truncated.

    Truncating (``r >> 3``) biases every channel downward by up to 7/255 and a
    flat parchment fill comes back visibly darker; rounding to the nearest
    representable level halves the worst case and keeps flat areas flat.
    """
    v = rgb.astype(np.uint32)
    r = (v[..., 0] * 31 + 127) // 255
    g = (v[..., 1] * 63 + 127) // 255
    b = (v[..., 2] * 31 + 127) // 255
    return ((r << 11) | (g << 5) | b).astype(np.uint16)


def _from_565(packed: np.ndarray) -> np.ndarray:
    """uint16 RGB565 -> (..., 3) float32, the colour the decoder will see."""
    r = (packed >> 11) & 0x1F
    g = (packed >> 5) & 0x3F
    b = packed & 0x1F
    out = np.empty(packed.shape + (3,), dtype=np.float32)
    out[..., 0] = (r << 3) | (r >> 2)
    out[..., 1] = (g << 2) | (g >> 4)
    out[..., 2] = (b << 3) | (b >> 3)
    return out


def encode(rgb: np.ndarray) -> bytes:
    """Compress an ``(h, w, 3)`` uint8 image to BC1. Both sides must be /4."""
    h, w = rgb.shape[:2]
    if h % 4 or w % 4:
        raise ValueError(f"BC1 needs both sides divisible by 4, got {w}x{h}")

    # (h, w, 3) -> (nblocks, 16, 3) in raster block order
    blocks = (
        rgb.reshape(h // 4, 4, w // 4, 4, 3)
        .transpose(0, 2, 1, 3, 4)
        .reshape(-1, 16, 3)
    )
    n = blocks.shape[0]
    out = np.empty((n, 2), dtype=np.uint32)

    for start in range(0, n, _CHUNK):
        chunk = blocks[start : start + _CHUNK]
        lo = chunk.min(axis=1)
        hi = chunk.max(axis=1)
        p0 = _to_565(hi)
        p1 = _to_565(lo)
        # BC1 reads the opaque 4-colour palette only when color0 > color1.
        # Equal endpoints are the 3-colour mode, but then every index 0 still
        # decodes to exactly that colour, so a flat block is safe either way.
        swap = p0 < p1
        p0, p1 = np.where(swap, p1, p0), np.where(swap, p0, p1)

        c0 = _from_565(p0)
        c1 = _from_565(p1)
        axis = c0 - c1
        len2 = (axis * axis).sum(axis=1)
        # t = 0 at c1, 1 at c0; palette sits at t = 0, 1/3, 2/3, 1
        t = np.einsum(
            "bij,bj->bi", chunk.astype(np.float32) - c1[:, None, :], axis
        ) / np.where(len2 == 0, 1.0, len2)[:, None]
        # nearest palette entry -> its BC1 index (0 = c0, 1 = c1, 2, 3)
        idx = np.select(
            [t < 1 / 6, t < 1 / 2, t < 5 / 6],
            [np.uint32(1), np.uint32(3), np.uint32(2)],
            default=np.uint32(0),
        ).astype(np.uint32)
        idx[len2 == 0] = 0

        shifts = (2 * np.arange(16, dtype=np.uint32))[None, :]
        out[start : start + chunk.shape[0], 0] = p0.astype(np.uint32) | (
            p1.astype(np.uint32) << 16
        )
        out[start : start + chunk.shape[0], 1] = (idx << shifts).sum(
            axis=1, dtype=np.uint32
        )
    return out.astype("<u4").tobytes()


def header(width: int, height: int, linear_size: int) -> bytes:
    """The 128-byte DDS header vanilla's ``flatmap.dds`` carries."""
    h = bytearray(128)
    h[0:4] = b"DDS "
    struct.pack_into(
        "<7I",
        h,
        4,
        124,  # dwSize
        _DDSD,  # dwFlags
        height,
        width,
        linear_size,  # dwPitchOrLinearSize
        0,  # dwDepth
        0,  # dwMipMapCount - vanilla flatmap.dds ships none
    )
    struct.pack_into("<2I", h, 76, 32, _DDPF_FOURCC)  # pixel format size, flags
    h[84:88] = b"DXT1"
    struct.pack_into("<I", h, 108, _DDSCAPS_TEXTURE)
    return bytes(h)


def save(rgb: np.ndarray, path: Path) -> None:
    """Write ``rgb`` as a single-surface, mip-less DXT1 ``.dds``."""
    data = encode(rgb)
    path.write_bytes(header(rgb.shape[1], rgb.shape[0], len(data)) + data)
