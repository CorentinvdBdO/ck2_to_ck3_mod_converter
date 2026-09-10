"""Inventory every raster under a CK3 ``gfx/map`` tree, from the file header.

Answers the question "which of vanilla's map textures are canvas-sized, i.e.
encode the shape of vanilla's Earth, and would therefore leak vanilla geography
into a custom map that does not override them?".

Reads DDS (DX9 ``DDPIXELFORMAT`` and DX10 ``DXGI_FORMAT``), PNG, TGA and BMP
headers without decoding the payload, so it is cheap over a whole install.

Usage::

    uv run scripts/inventory_map_rasters.py [--root DIR] [--csv OUT.csv]
                                            [--canvas WxH] [--ratio-tol 0.02]

``--canvas`` (default vanilla ``9216x4608``) marks every raster whose width and
height are within ``--ratio-tol`` of that aspect *and* at least a quarter of the
canvas in each axis as ``map_sized`` — the set a custom map has to think about.
"""

from __future__ import annotations

import argparse
import csv
import struct
import sys
from pathlib import Path

DDPF_FOURCC = 0x4
DDPF_RGB = 0x40
DDPF_LUMINANCE = 0x20000
DDPF_ALPHAPIXELS = 0x1
DDSD_MIPMAPCOUNT = 0x20000

# DXGI_FORMAT values we can hit in a CK3 install.
DXGI = {
    2: "R32G32B32A32_FLOAT",
    10: "R16G16B16A16_FLOAT",
    24: "R10G10B10A2_UNORM",
    28: "R8G8B8A8_UNORM",
    29: "R8G8B8A8_UNORM_SRGB",
    34: "R16G16_UNORM",
    41: "R32_FLOAT",
    49: "R8G8_UNORM",
    56: "R16_UNORM",
    61: "R8_UNORM",
    71: "BC1_UNORM",
    72: "BC1_UNORM_SRGB",
    74: "BC2_UNORM",
    77: "BC3_UNORM",
    78: "BC3_UNORM_SRGB",
    80: "BC4_UNORM",
    83: "BC5_UNORM",
    87: "B8G8R8A8_UNORM",
    88: "B8G8R8X8_UNORM",
    95: "BC6H_UF16",
    98: "BC7_UNORM",
    99: "BC7_UNORM_SRGB",
}

BLOCK_BYTES = {
    "DXT1": 8, "BC1_UNORM": 8, "BC1_UNORM_SRGB": 8, "BC4_UNORM": 8,
    "DXT3": 16, "DXT5": 16, "BC2_UNORM": 16, "BC3_UNORM": 16,
    "BC3_UNORM_SRGB": 16, "BC5_UNORM": 16, "BC7_UNORM": 16,
    "BC7_UNORM_SRGB": 16, "BC6H_UF16": 16, "ATI2": 16, "ATI1": 8,
}


def _dds(raw: bytes) -> dict[str, object]:
    height, width = struct.unpack_from("<2I", raw, 12)
    flags = struct.unpack_from("<I", raw, 8)[0]
    mips = struct.unpack_from("<I", raw, 28)[0] if flags & DDSD_MIPMAPCOUNT else 1
    pf_flags = struct.unpack_from("<I", raw, 80)[0]
    fourcc = raw[84:88]
    bit_count = struct.unpack_from("<I", raw, 88)[0]

    if pf_flags & DDPF_FOURCC:
        if fourcc == b"DX10":
            dxgi = struct.unpack_from("<I", raw, 128)[0]
            fmt = DXGI.get(dxgi, f"DXGI_{dxgi}")
        else:
            fmt = fourcc.decode("ascii", "replace")
    elif pf_flags & DDPF_LUMINANCE:
        fmt = f"L{bit_count}" + ("A" if pf_flags & DDPF_ALPHAPIXELS else "")
    elif pf_flags & DDPF_RGB:
        fmt = f"RGB{bit_count}" + ("A" if pf_flags & DDPF_ALPHAPIXELS else "")
    else:
        fmt = f"pf_flags_0x{pf_flags:x}"
    return {"width": width, "height": height, "format": fmt, "mips": max(1, mips)}


def _png(raw: bytes) -> dict[str, object]:
    width, height = struct.unpack_from(">2I", raw, 16)
    depth, colour = raw[24], raw[25]
    kinds = {0: "GRAY", 2: "RGB", 3: "PALETTE", 4: "GRAY_A", 6: "RGBA"}
    return {"width": width, "height": height,
            "format": f"{kinds.get(colour, colour)}{depth}", "mips": 1}


def _tga(raw: bytes) -> dict[str, object]:
    width, height = struct.unpack_from("<2H", raw, 12)
    image_type, depth = raw[2], raw[16]
    rle = "RLE_" if image_type >= 9 else ""
    return {"width": width, "height": height,
            "format": f"TGA_{rle}{depth}bpp_type{image_type}", "mips": 1}


def _bmp(raw: bytes) -> dict[str, object]:
    width, height = struct.unpack_from("<2i", raw, 18)
    depth = struct.unpack_from("<H", raw, 28)[0]
    return {"width": width, "height": abs(height),
            "format": f"BMP{depth}", "mips": 1}


READERS = {".dds": _dds, ".png": _png, ".tga": _tga, ".bmp": _bmp}


def read_header(path: Path) -> dict[str, object] | None:
    """Header facts for one raster, or ``None`` if the suffix is not one."""
    reader = READERS.get(path.suffix.lower())
    if reader is None:
        return None
    with path.open("rb") as fh:
        raw = fh.read(256)
    try:
        info = reader(raw)
    except (struct.error, IndexError):
        return None
    info["bytes"] = path.stat().st_size
    return info


def surface_bytes(width: int, height: int, fmt: str) -> int:
    """Bytes of the top mip, for a sanity check against the file size."""
    block = BLOCK_BYTES.get(fmt)
    if block is not None:
        return max(1, (width + 3) // 4) * max(1, (height + 3) // 4) * block
    digits = "".join(c for c in fmt if c.isdigit())
    bits = int(digits) if digits else 32
    return width * height * bits // 8


def scan(root: Path, canvas: tuple[int, int], ratio_tol: float) -> list[dict]:
    canvas_w, canvas_h = canvas
    canvas_ratio = canvas_w / canvas_h
    rows: list[dict] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        info = read_header(path)
        if info is None:
            continue
        w, h = int(info["width"]), int(info["height"])
        ratio_ok = h > 0 and abs(w / h - canvas_ratio) / canvas_ratio <= ratio_tol
        big_enough = w >= canvas_w // 4 and h >= canvas_h // 4
        rows.append({
            "path": str(path.relative_to(root)),
            "width": w,
            "height": h,
            "format": info["format"],
            "mips": info["mips"],
            "bytes": info["bytes"],
            "top_mip_bytes": surface_bytes(w, h, str(info["format"])),
            "canvas_fraction": round(w / canvas_w, 4) if canvas_w else "",
            "map_sized": "yes" if (ratio_ok and big_enough) else "no",
        })
    return rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", type=Path,
                    default=Path("../claudespace/game_files/gfx/map"))
    ap.add_argument("--csv", type=Path, default=None)
    ap.add_argument("--canvas", default="9216x4608")
    ap.add_argument("--ratio-tol", type=float, default=0.02)
    args = ap.parse_args(argv)

    cw, ch = (int(v) for v in args.canvas.lower().split("x"))
    rows = scan(args.root, (cw, ch), args.ratio_tol)
    if not rows:
        print(f"no rasters under {args.root}", file=sys.stderr)
        return 1

    fields = list(rows[0])
    if args.csv:
        args.csv.parent.mkdir(parents=True, exist_ok=True)
        with args.csv.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        print(f"{len(rows)} rasters -> {args.csv}")

    width = max(len(r["path"]) for r in rows)
    for row in rows:
        mark = "*" if row["map_sized"] == "yes" else " "
        print(f"{mark} {row['path']:<{width}}  {row['width']:>5}x{row['height']:<5}"
              f"  {row['format']:<18} mips={row['mips']:<2} {row['bytes']:>10}")
    print(f"\n{sum(r['map_sized'] == 'yes' for r in rows)} map-sized "
          f"of {len(rows)} rasters (canvas {cw}x{ch})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
