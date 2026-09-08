"""Decode a DXT1 ``.dds`` to a downscaled PNG, to eyeball what we wrote.

The flat map is 8320x6784 and 28 MB of BC1; nothing in this repo can open it
and no image viewer here decodes DDS.  This turns it into something a human (or
a review sheet) can look at.

Usage::

    uv run scripts/preview_dds.py <in.dds> <out.png> [--max-side 1200]
"""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None


def decode_bc1(raw: bytes) -> np.ndarray:
    """``DDS `` bytes -> ``(h, w, 3)`` uint8. DXT1, single surface."""
    if raw[:4] != b"DDS ":
        raise ValueError("not a DDS file")
    height, width = struct.unpack_from("<2I", raw, 12)
    if raw[84:88] != b"DXT1":
        raise ValueError(f"only DXT1 is supported, got {raw[84:88]!r}")

    blocks = np.frombuffer(raw, dtype="<u4", count=(width // 4) * (height // 4) * 2,
                           offset=128).reshape(-1, 2)
    packed, bits = blocks[:, 0], blocks[:, 1]

    def unpack565(v: np.ndarray) -> np.ndarray:
        r, g, b = (v >> 11) & 0x1F, (v >> 5) & 0x3F, v & 0x1F
        return np.stack(
            [(r << 3) | (r >> 2), (g << 2) | (g >> 4), (b << 3) | (b >> 3)], axis=-1
        ).astype(np.float32)

    c0 = unpack565(packed & 0xFFFF)
    c1 = unpack565(packed >> 16)
    palette = np.stack([c0, c1, (2 * c0 + c1) / 3, (c0 + 2 * c1) / 3], axis=1)

    shifts = 2 * np.arange(16, dtype=np.uint32)
    idx = (bits[:, None] >> shifts[None, :]) & 0x3
    texels = np.take_along_axis(palette, idx[:, :, None], axis=1)

    return (
        texels.reshape(height // 4, width // 4, 4, 4, 3)
        .transpose(0, 2, 1, 3, 4)
        .reshape(height, width, 3)
        .round()
        .astype(np.uint8)
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("src", type=Path)
    ap.add_argument("dst", type=Path)
    ap.add_argument("--max-side", type=int, default=1200)
    args = ap.parse_args(argv)

    rgb = decode_bc1(args.src.read_bytes())
    img = Image.fromarray(rgb)
    scale = args.max_side / max(img.size)
    if scale < 1:
        img = img.resize(
            (max(1, int(img.width * scale)), max(1, int(img.height * scale))),
            Image.Resampling.LANCZOS,
        )
    args.dst.parent.mkdir(parents=True, exist_ok=True)
    img.save(args.dst)
    print(f"{args.src} {rgb.shape[1]}x{rgb.shape[0]} -> {args.dst} {img.size}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
