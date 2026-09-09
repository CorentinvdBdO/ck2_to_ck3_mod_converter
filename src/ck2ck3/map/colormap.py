"""``gfx/map/terrain/colormap.dds`` — the large-scale colour wash.

`docs/map_fidelity.md` §1.3/§4.3: CK3 samples this texture as a broad colour
tint under the terrain paint; ship none and the game shows vanilla's own
Europe colormap stretched across our canvas.  CK2 has the exact analogue —
Faerûn's `map/terrain/colormap.dds` is **pixel-aligned with `provinces.bmp`**
(`verified`: both are 4096x3328) — so this is a resample of an existing asset,
not new art.

**Format decision, `verified` against two shipped, currently-loadable CK3
total conversions** rather than by guessing at vanilla's own format:

* Vanilla 1.19 ships `colormap.dds` at full province resolution (9216x4608),
  **DXT5** (BC3), 14 mip levels, 56.6 MB (`xxd` on the real game file: fourCC
  `DXT5`, `dwMipMapCount = 14`, `dwPitchOrLinearSize = 42,467,328` = exactly
  `9216*4608` — one byte/pixel average, the DXT5 rate).
* Elder Kings 2 and Godherja — both `verified` loadable total conversions —
  ship `colormap.dds` **uncompressed 32-bit BGRA (A8R8G8B8), at exactly
  one-quarter of their own province-map resolution**: EK2 2064x1376 for its
  8256x5504 canvas, Godherja 2048x1024 for its 8192x4096 canvas, alpha = 255
  everywhere (`verified`, sampled). Neither ships DXT5. Godherja's carries a
  full mip chain (12 levels to 1x1); EK2's does not.

This module follows the two real conversions, not vanilla's own bake: a BC3
(DXT5) encoder is more machinery than this repo has for one texture that is
explicitly "the large-scale colour wash" (`docs/map_fidelity.md` §4.3), not
per-pixel detail, and quarter resolution is what the format is *for*. Writing
uncompressed also sidesteps the one open question a BC3 path would add
(`docs/step_map_paint.md` §8.2 found only weak evidence CK3 loads `.dds` at
all for the sibling `detail_index`/`detail_intensity` pair — this file is a
different, `verified`-safe case because two shipped mods already do exactly
this with `colormap.dds`).
"""

from __future__ import annotations

import struct
from pathlib import Path

import numpy as np
from PIL import Image

#: where the engine looks
COLORMAP_PATH = "gfx/map/terrain/colormap.dds"

# DDSD_CAPS | HEIGHT | WIDTH | PIXELFORMAT | PITCH (uncompressed -> PITCH, not
# LINEARSIZE; `verified` against EK2/Godherja's own header byte 8: 0x0000100f)
_DDSD = 0x1 | 0x2 | 0x4 | 0x1000 | 0x8
_DDSD_MIPMAPCOUNT = 0x20000
_DDPF_ALPHAPIXELS = 0x1
_DDPF_RGB = 0x40
_DDSCAPS_TEXTURE = 0x1000
_DDSCAPS_COMPLEX = 0x8
_DDSCAPS_MIPMAP = 0x400000

#: A8R8G8B8 channel masks, `verified` byte-for-byte against both reference
#: mods' colormap.dds (offsets 92/96/100/104 of the header)
_R_MASK = 0x00FF0000
_G_MASK = 0x0000FF00
_B_MASK = 0x000000FF
_A_MASK = 0xFF000000


def render(
    ck2_colormap: Path,
    canvas,
    *,
    source_size: tuple[int, int] | None = None,
    margin_rgb: tuple[int, int, int] = (74, 90, 110),
) -> np.ndarray:
    """CK2 ``colormap.dds`` resampled onto ``canvas``.

    Reuses the exact crop/scale/offset the province raster was built with
    (``ck2ck3.map.config.plan_canvas``) rather than re-deriving a transform:
    the CK2 colormap ships pixel-aligned with ``provinces.bmp`` in the mods
    checked so far, so the same crop box and resize apply unchanged.

    ``source_size`` is the ``(width, height)`` of the CK2 *province* bitmap
    the canvas geometry was computed from (``build.py`` already has it as
    ``src_w, src_h``); when the colormap's own resolution differs, the crop
    box is rescaled into the colormap's pixel space first, so a mod whose
    colormap is not 1:1 with its provinces.bmp still resamples correctly.
    ``margin_rgb`` fills the sea margin the canvas adds beyond the CK2 map's
    own extent (open ocean the CK2 source never painted).
    """
    with Image.open(ck2_colormap) as im:
        rgb = np.asarray(im.convert("RGB"))
    ch, cw = rgb.shape[:2]
    if source_size and (cw, ch) != tuple(source_size):
        sx, sy = cw / source_size[0], ch / source_size[1]
    else:
        sx = sy = 1.0
    x0, y0 = round(canvas.crop_x0 * sx), round(canvas.crop_y0 * sy)
    x1, y1 = round(canvas.crop_x1 * sx), round(canvas.crop_y1 * sy)
    x1, y1 = max(x1, x0 + 1), max(y1, y0 + 1)
    x1, y1 = min(x1, cw), min(y1, ch)
    crop = rgb[y0:y1, x0:x1]
    resized = Image.fromarray(crop).resize(
        (canvas.scaled_width, canvas.scaled_height), Image.LANCZOS
    )
    out = Image.new("RGB", (canvas.width, canvas.height), margin_rgb)
    out.paste(resized, (canvas.offset_x, canvas.offset_y))
    return np.asarray(out)


def downsample(rgb: np.ndarray, scale: float) -> np.ndarray:
    """Lanczos-resample ``rgb`` (h, w, 3) by ``scale`` (< 1 shrinks)."""
    if scale == 1.0:
        return rgb
    h, w = rgb.shape[:2]
    nw = max(1, round(w * scale))
    nh = max(1, round(h * scale))
    return np.asarray(Image.fromarray(rgb).resize((nw, nh), Image.LANCZOS))


def _mip_chain(rgba: np.ndarray) -> list[np.ndarray]:
    """Full mip chain down to 1x1, matching Godherja's shipped colormap.dds."""
    chain = [rgba]
    h, w = rgba.shape[:2]
    im = Image.fromarray(rgba)
    while h > 1 or w > 1:
        h, w = max(1, h // 2), max(1, w // 2)
        im = im.resize((w, h), Image.LANCZOS)
        chain.append(np.asarray(im))
    return chain


def header(width: int, height: int, *, mips: int = 1) -> bytes:
    """The 128-byte DDS header for uncompressed A8R8G8B8, BGRA byte order.

    Byte-for-byte the same fields as Elder Kings 2's (``mips=1``) or
    Godherja's (``mips>1``) shipped ``colormap.dds`` (`verified`, see module
    docstring); vanilla's own DXT5 header is not used.
    """
    h = bytearray(128)
    h[0:4] = b"DDS "
    flags = _DDSD | (_DDSD_MIPMAPCOUNT if mips > 1 else 0)
    pitch = width * 4
    struct.pack_into(
        "<7I", h, 4,
        124,  # dwSize
        flags,
        height,
        width,
        pitch,  # dwPitchOrLinearSize: row pitch, not a compressed linear size
        0,  # dwDepth
        mips if mips > 1 else 0,  # dwMipMapCount
    )
    struct.pack_into("<2I", h, 76, 32, _DDPF_RGB | _DDPF_ALPHAPIXELS)  # ddspf size, flags
    struct.pack_into("<2I", h, 84, 0, 32)  # fourCC (0 = uncompressed), RGBBitCount
    struct.pack_into("<4I", h, 92, _R_MASK, _G_MASK, _B_MASK, _A_MASK)
    caps = _DDSCAPS_TEXTURE
    if mips > 1:
        caps |= _DDSCAPS_COMPLEX | _DDSCAPS_MIPMAP
    struct.pack_into("<I", h, 108, caps)
    return bytes(h)


def save(rgb: np.ndarray, path: Path, *, mips: bool = True) -> None:
    """Write ``rgb`` (h, w, 3) uint8 as an uncompressed BGRA8 DDS, alpha=255.

    ``mips=True`` (default) writes the full chain to 1x1, Godherja's shape;
    ``False`` writes only the base level, EK2's shape. Both load per the two
    reference mods (module docstring); the chain is kept by default for a
    smoother look at oblique camera angles.
    """
    h, w = rgb.shape[:2]
    alpha = np.full((h, w, 1), 255, dtype=np.uint8)
    rgba = np.concatenate([rgb.astype(np.uint8), alpha], axis=-1)
    levels = _mip_chain(rgba) if mips else [rgba]
    data = bytearray()
    for level in levels:
        bgra = level[..., [2, 1, 0, 3]]
        data += np.ascontiguousarray(bgra, dtype=np.uint8).tobytes()
    path.write_bytes(header(w, h, mips=len(levels)) + bytes(data))
