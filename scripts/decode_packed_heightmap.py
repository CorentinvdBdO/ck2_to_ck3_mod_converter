#!/usr/bin/env python
"""Rebuild heightmap.png from the packed pair and score it against the shipped file.

    uv run scripts/decode_packed_heightmap.py <map_data dir> [<map_data dir> ...]
    uv run scripts/decode_packed_heightmap.py --all          # vanilla + EK2 + Godherja

For each directory it reads ``heightmap.heightmap`` +
``packed_heightmap.png`` + ``indirection_heightmap.png``, reconstructs the
heightmap, and prints max/mean absolute error and the exactly-equal fraction
against the shipped ``heightmap.png`` -- overall, on tile interiors, and on the
one-pixel tile borders, because the borders are lossy *by design* (see
``docs/formats_packed_heightmap.md``).

``--write DIR`` also dumps the reconstruction as a 16-bit PNG.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ck2ck3.map.packed_heightmap import (  # noqa: E402
    decode_packed,
    read_descriptor,
    write_packed,
)

Image.MAX_IMAGE_PIXELS = None

KNOWN = {
    "vanilla": Path(
        "~/.local/share/Steam/steamapps/common/Crusader Kings III/game/map_data"
    ).expanduser(),
    "ek2": Path(
        "~/.local/share/Steam/steamapps/workshop/content/1158310/2887120253/map_data"
    ).expanduser(),
    "godherja": Path(
        "~/.local/share/Steam/steamapps/workshop/content/1158310/2326030123/map_data"
    ).expanduser(),
}


def border_mask(shape: tuple[int, int], stride: int) -> np.ndarray:
    """True on the one-pixel lines shared between neighbouring tiles (bottom-up)."""
    mask = np.zeros(shape, dtype=bool)
    mask[::stride, :] = True
    mask[:, ::stride] = True
    mask[-1, :] = True
    mask[:, -1] = True
    return mask


def score(name: str, map_data: Path, write_dir: Path | None) -> dict | None:
    if not (map_data / "heightmap.heightmap").exists():
        print(f"{name}: no heightmap.heightmap in {map_data}", file=sys.stderr)
        return None
    recon, desc = decode_packed(map_data)
    shipped = np.array(Image.open(map_data / "heightmap.png"))
    if shipped.shape != recon.shape:
        print(f"{name}: shipped heightmap.png is {shipped.shape}, decoded {recon.shape}")
        return None
    if write_dir is not None:
        write_dir.mkdir(parents=True, exist_ok=True)
        Image.fromarray(recon).save(write_dir / f"{name}_reconstructed_heightmap.png")

    # everything below is in bottom-up space, the format's own orientation
    err = np.abs(recon.astype(np.int64) - shipped.astype(np.int64))[::-1]
    edges = border_mask(err.shape, desc.stride)
    inner = ~edges
    row = {
        "name": name,
        "size": f"{recon.shape[1]}x{recon.shape[0]}",
        "tile": desc.tile_size,
        "max": int(err.max()),
        "mean": float(err.mean()),
        "exact": float((err == 0).mean()),
        "in_max": int(err[inner].max()),
        "in_exact": float((err[inner] == 0).mean()),
        "ed_max": int(err[edges].max()),
        "ed_exact": float((err[edges] == 0).mean()),
    }

    # per compression level, tile interiors only
    levels = np.array(Image.open(map_data / Path(desc.indirection_file).name))[::-1][:, :, 3]
    stride = desc.stride
    per_level = []
    for lv in range(desc.max_compress_level + 1):
        tys, txs = np.where(levels == lv)
        if len(tys) == 0:
            per_level.append(None)
            continue
        mx = 0
        exact = 0
        total = 0
        for ty, tx in zip(tys, txs):
            e = err[ty * stride + 1 : (ty + 1) * stride, tx * stride + 1 : (tx + 1) * stride]
            mx = max(mx, int(e.max()))
            exact += int((e == 0).sum())
            total += e.size
        per_level.append((len(tys), mx, exact / max(total, 1)))
    row["per_level"] = per_level
    return row


def reencode(name: str, map_data: Path, out_root: Path) -> None:
    """Re-pack the shipped heightmap.png and compare with the shipped pair.

    This is the encoder's only real-world check: the numbers it prints
    (compression-level histogram, atlas size, file size) are what
    docs/formats_packed_heightmap.md quotes as evidence that
    ``LEVEL_MAX_ERROR`` reproduces the map editor's own choices.
    """
    desc = read_descriptor(map_data / "heightmap.heightmap")
    shipped = np.array(Image.open(map_data / "heightmap.png"))
    ind = np.array(Image.open(map_data / Path(desc.indirection_file).name))[::-1]
    out = out_root / name
    meta = write_packed(
        shipped,
        out,
        tile_size=desc.tile_size,
        max_compress_level=desc.max_compress_level,
        should_wrap_x=desc.should_wrap_x,
    )
    theirs = np.bincount(ind[:, :, 3].ravel(), minlength=desc.max_compress_level + 1)
    agree = float((ind[:, :, 3] == np.array(Image.open(out / "indirection_heightmap.png"))[::-1][:, :, 3]).mean())
    packed = Image.open(map_data / Path(desc.heightmap_file).name)
    print(f"{name}: re-encoded {shipped.shape[1]}x{shipped.shape[0]} tile_size={desc.tile_size}")
    print(f"   level histogram  ours {meta['level_histogram']}  theirs {theirs.tolist()}")
    print(f"   per-tile level agreement with the shipped indirection: {agree:.4f}")
    print(f"   atlas ours {meta['atlas_size'][0]}x{meta['atlas_size'][1]}"
          f"  theirs {packed.size[0]}x{packed.size[1]}")
    print(f"   packed png ours {meta['packed_bytes'] / 1e6:.2f} MB"
          f"  theirs {(map_data / Path(desc.heightmap_file).name).stat().st_size / 1e6:.2f} MB")
    print(f"   round-trip max={meta['max_abs_error']} mean={meta['mean_abs_error']:.3f}"
          f" exact={meta['exact_fraction']:.4f}  distinct_tiles={meta['distinct_tiles']}")


def size_report(dims: str, tile_size: int, out_root: Path) -> None:
    """Encode a synthetic heightmap of the given size and report file sizes."""
    w, h = (int(v) for v in dims.lower().split("x"))
    rng = np.random.default_rng(0)
    # fractal noise, so tile detail (and therefore the level mix) is realistic
    land = np.zeros((h, w))
    for step in (128, 64, 32, 16, 8, 4):
        small = rng.normal(0.0, 1.0, (h // step + 2, w // step + 2))
        land += np.kron(small, np.ones((step, step)))[:h, :w] * step
    # real heightmaps are smooth at the pixel level (they come out of a
    # sculpting tool at 1x or 2x and get blurred); without this the noise is
    # per-pixel and *every* tile ends up incompressible, which no map is.
    for _ in range(3):
        land = (
            land
            + np.roll(land, 1, 0)
            + np.roll(land, -1, 0)
            + np.roll(land, 1, 1)
            + np.roll(land, -1, 1)
        ) / 5.0
    land = 20000 + land * (14000 / max(np.abs(land).max(), 1e-9))
    land[: h // 3, :] = 0.0  # a third ocean, like a real map
    hm = np.rint(land).clip(0, 65535).astype(np.uint16)
    print(f"synthetic {w}x{h} tile_size={tile_size}:")
    print(f"   heightmap.png raw         {w * h * 2 / 1e6:.2f} MB (16-bit, uncompressed)")
    for mcl in (4, 0):
        meta = write_packed(
            hm, out_root / f"synthetic_{w}x{h}_mcl{mcl}", tile_size=tile_size,
            max_compress_level=mcl,
        )
        tag = f"max_compress_level={mcl}" + (" (all level 0)" if mcl == 0 else "")
        print(f"   {tag}")
        print(f"     packed_heightmap.png      {meta['packed_bytes'] / 1e6:.2f} MB"
              f"  ({meta['atlas_size'][0]}x{meta['atlas_size'][1]})")
        print(f"     indirection_heightmap.png {meta['indirection_bytes'] / 1e3:.1f} kB"
              f"  (grid {meta['grid_size'][0]}x{meta['grid_size'][1]})")
        print(f"     levels {meta['level_histogram']}  distinct_tiles={meta['distinct_tiles']}")
        print(f"     round-trip max={meta['max_abs_error']} mean={meta['mean_abs_error']:.3f}"
              f" exact={meta['exact_fraction']:.4f}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("dirs", nargs="*", type=Path)
    ap.add_argument("--all", action="store_true", help="score vanilla, EK2 and Godherja")
    ap.add_argument("--write", type=Path, default=None, help="dump reconstructions here")
    ap.add_argument("--reencode", type=Path, default=None, metavar="OUT",
                    help="also re-pack each shipped heightmap.png into OUT and compare")
    ap.add_argument("--size-report", metavar="WxH", default=None,
                    help="encode a synthetic heightmap of this size and report file sizes")
    ap.add_argument("--tile-size", type=int, default=33, help="tile_size for --size-report")
    args = ap.parse_args()

    if args.size_report:
        size_report(args.size_report, args.tile_size, args.write or Path("/tmp"))
        if not args.dirs and not args.all and not args.reencode:
            return 0

    targets: list[tuple[str, Path]] = [(d.parent.name or d.name, d) for d in args.dirs]
    if args.all or not targets:
        targets = list(KNOWN.items())

    rows = [r for name, d in targets if (r := score(name, d, args.write))]
    if not rows:
        return 1
    hdr = (
        f"{'mod':10s} {'size':11s} {'ts':>3s} {'maxerr':>7s} {'meanerr':>8s} "
        f"{'exact':>7s} {'in_max':>7s} {'in_exact':>9s} {'edge_max':>9s} {'edge_exact':>11s}"
    )
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        print(
            f"{r['name']:10s} {r['size']:11s} {r['tile']:3d} {r['max']:7d} {r['mean']:8.3f} "
            f"{r['exact']:7.4f} {r['in_max']:7d} {r['in_exact']:9.4f} "
            f"{r['ed_max']:9d} {r['ed_exact']:11.4f}"
        )
    print()
    print("tile interiors by compression level (n tiles / max abs err / exactly-equal)")
    for r in rows:
        cells = " ".join(
            "L%d -/-/-" % lv if s is None else f"L{lv} {s[0]}/{s[1]}/{s[2]:.4f}"
            for lv, s in enumerate(r["per_level"])
        )
        print(f"  {r['name']:10s} {cells}")
    if args.reencode:
        print()
        for name, d in targets:
            if (d / "heightmap.heightmap").exists():
                reencode(name, d, args.reencode)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
