"""Decode a CK3 map raster and say what is in it: preview PNG + channel stats.

`scripts/preview_dds.py` only speaks DXT1 (the flat map we write ourselves).
This one goes through Pillow, which decodes every DDS format shipped in 1.19
except ``B8G8R8A8`` DX10 (``surround_tile.dds``), and prints the per-channel
statistics a "is this texture geography-dependent, and what is its mean value?"
decision needs.

Usage::

    uv run scripts/probe_map_raster.py <raster> [<raster> ...]
        [--png-dir DIR] [--max-side 1200] [--csv OUT.csv]

Prints one row per channel: min, max, mean, median, p05, p95, and the share of
pixels equal to the channel minimum (a flat channel reads 1.00 there).
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None


def load(path: Path) -> np.ndarray:
    """``(h, w, c)`` uint8 for any raster Pillow can open."""
    img = Image.open(path)
    arr = np.asarray(img)
    if arr.ndim == 2:
        arr = arr[:, :, None]
    return arr


def stats(arr: np.ndarray, name: str, channel: int) -> dict[str, object]:
    band = arr[:, :, channel].astype(np.float64)
    lo = band.min()
    return {
        "raster": name,
        "channel": "RGBA"[channel] if arr.shape[2] <= 4 else str(channel),
        "min": int(lo),
        "max": int(band.max()),
        "mean": round(float(band.mean()), 2),
        "median": int(np.median(band)),
        "p05": int(np.percentile(band, 5)),
        "p95": int(np.percentile(band, 95)),
        "frac_at_min": round(float((band == lo).mean()), 4),
        "distinct": int(np.unique(band.astype(np.uint8)).size),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("rasters", nargs="+", type=Path)
    ap.add_argument("--png-dir", type=Path, default=None)
    ap.add_argument("--max-side", type=int, default=1200)
    ap.add_argument("--csv", type=Path, default=None)
    args = ap.parse_args(argv)

    rows: list[dict[str, object]] = []
    for path in args.rasters:
        arr = load(path)
        h, w, c = arr.shape
        print(f"{path}  {w}x{h}  {c} channel(s)")
        for channel in range(c):
            row = stats(arr, path.name, channel)
            rows.append(row)
            print("   {channel}: min {min:>3} max {max:>3} mean {mean:>6} "
                  "median {median:>3} p05 {p05:>3} p95 {p95:>3} "
                  "flat@min {frac_at_min:>6} distinct {distinct}".format(**row))
        if args.png_dir:
            args.png_dir.mkdir(parents=True, exist_ok=True)
            img = Image.fromarray(arr.squeeze() if c == 1 else arr[:, :, :3])
            scale = args.max_side / max(img.size)
            if scale < 1:
                img = img.resize((max(1, int(img.width * scale)),
                                  max(1, int(img.height * scale))),
                                 Image.Resampling.LANCZOS)
            out = args.png_dir / f"{path.stem}_rgb.png"
            img.save(out)
            print(f"   -> {out}")
            if c == 4:
                alpha = Image.fromarray(arr[:, :, 3])
                if scale < 1:
                    alpha = alpha.resize(img.size, Image.Resampling.LANCZOS)
                out_a = args.png_dir / f"{path.stem}_alpha.png"
                alpha.save(out_a)
                print(f"   -> {out_a}")

    if args.csv:
        args.csv.parent.mkdir(parents=True, exist_ok=True)
        with args.csv.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        print(f"{len(rows)} channel rows -> {args.csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
