#!/usr/bin/env python3
"""Can the packed pair carry a 2x heightmap, and at what size?

`[map.heightmap] resolution_factor = 2` fails to pack at the shipped
`tile_size = 33`: the indirection map addresses the atlas with 8-bit offsets,
so a level may hold at most 256x256 = 65,536 distinct tiles, and a 2x Faerun
canvas is 520 x 424 = 220,480 of them before any dedupe.  Vanilla's own 2x
sheet uses `tile_size = 65` (18432 x 9216 -> 288 x 144 = 41,472 tiles), which
is the answer; this measures it.

Usage: uv run python scripts/relief_sharp_repack_2x.py <heightmap.png> [--tile 65]
"""

from __future__ import annotations

import argparse
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import relief_sharp_common as C  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("heightmap")
    ap.add_argument("--tiles", type=int, nargs="*", default=[33, 65, 129])
    args = ap.parse_args()
    from ck2ck3.map import packed_heightmap as ph

    a = C.load16(Path(args.heightmap))
    print(f"{args.heightmap}: {a.shape[1]}x{a.shape[0]}", flush=True)
    for tile in args.tiles:
        with tempfile.TemporaryDirectory() as td:
            t0 = time.time()
            try:
                meta = ph.write_packed(a, Path(td), tile_size=tile, verify=False)
            except Exception as exc:
                print(f"  tile_size {tile:4d}: FAILED -- {exc}", flush=True)
                continue
            files = {f.name: f.stat().st_size for f in Path(td).rglob("*")
                     if f.is_file()}
            total = sum(files.values())
            print(f"  tile_size {tile:4d}: {total / 1e6:7.1f} MB in "
                  f"{time.time() - t0:.0f} s  "
                  + " ".join(f"{k} {v / 1e6:.1f}MB" for k, v in sorted(files.items()))
                  + f"  levels={meta.get('level_offsets')}", flush=True)


if __name__ == "__main__":
    main()
