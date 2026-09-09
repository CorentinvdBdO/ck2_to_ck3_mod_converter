"""Build terrain-paint format/scale variants as loadable probe mods.

Reads the `detail_index`/`detail_intensity` pair a converter run already
wrote (any `[map] terrain_paint_format`), re-encodes it into every candidate
in `docs/step_map_paint.md` §size, and writes each into its own sibling
folder as a self-contained probe mod:

    <out>/../paint_variants/<variant>/gfx/map/terrain/detail_index.<ext>
    <out>/../paint_variants/<variant>/gfx/map/terrain/detail_intensity.<ext>
    <out>/../paint_variants/<variant>/descriptor.mod

The coordinator loads one at a time after the main mod:

    claudespace/scripts/ck3_soak.sh <mod> --extra <out>/../paint_variants/<variant>

`ck3_soak.sh --extra DIR` requires `DIR/descriptor.mod` to exist and strips
any `path=` line from it before pointing the launcher at `DIR` — see its
source, `claudespace/scripts/ck3_soak.sh`. The probe overrides by same
path only: NO `replace_path="gfx/map/terrain"` - that would also delete
vanilla's colormap, material textures and materials.settings and the test
would show a broken map for a reason unrelated to the paint format
(2026-09-09 first probe run). Consequence: a `dds` variant cannot hide the
main mod's `.tga` pair, so the dds probes only show whether the engine picks
up a .dds *in addition* - moot anyway, ck3.exe names the pair with a literal
`.tga` (docs/step_map_paint.md §8.2).

Usage::

    uv run scripts/paint_variants.py <converter out dir> [--variants-dir DIR]

Reports each variant's byte size on stdout, and writes
`docs/evidence/paint_variants.csv` with the same table.
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ck2ck3.map import terrain_paint  # noqa: E402

REPO = Path(__file__).resolve().parents[1]

#: (format, scale) -> variant id. Order matters only for the printed report.
VARIANTS: list[tuple[str, float]] = [
    ("tga", 1.0),
    ("tga_rle", 1.0),
    ("dds", 1.0),
    ("tga", 0.5),
    ("tga_rle", 0.5),
    ("dds", 0.5),
]


def _variant_id(fmt: str, scale: float) -> str:
    size = "full" if scale == 1.0 else f"{scale:g}".replace(".", "p")
    return f"{fmt}_{size}"


def _find_master_pair(out_dir: Path) -> tuple[Path, Path, str]:
    """Locate the pair a converter run already wrote, whatever its format."""
    terrain_dir = out_dir / "gfx" / "map" / "terrain"
    for fmt in terrain_paint.PAINT_FORMATS:
        ext = terrain_paint.paint_ext(fmt)
        idx = terrain_dir / f"detail_index.{ext}"
        inten = terrain_dir / f"detail_intensity.{ext}"
        if idx.exists() and inten.exists():
            return idx, inten, fmt
    raise SystemExit(
        f"no detail_index/detail_intensity pair found under {terrain_dir} "
        f"(looked for extensions {sorted({terrain_paint.paint_ext(f) for f in terrain_paint.PAINT_FORMATS})})"
    )


_DESCRIPTOR_TEMPLATE = """version="0.1.0-probe"
tags={{
\t"Graphics"
}}
name="Paint variant: {variant}"
supported_version="1.19.*"
"""


def _write_descriptor(variant_dir: Path, variant: str) -> None:
    (variant_dir / "descriptor.mod").write_text(
        _DESCRIPTOR_TEMPLATE.format(variant=variant), encoding="utf-8"
    )


def build_variants(out_dir: Path, variants_dir: Path) -> list[dict]:
    idx_path, inten_path, master_fmt = _find_master_pair(out_dir)
    print(f"master pair: format={master_fmt} "
          f"index={idx_path.stat().st_size} bytes "
          f"intensity={inten_path.stat().st_size} bytes")
    index = terrain_paint.load_paint(idx_path, master_fmt)
    intensity = terrain_paint.load_paint(inten_path, master_fmt)
    print(f"decoded shape: index={index.shape} intensity={intensity.shape}")

    rows = []
    for fmt, scale in VARIANTS:
        variant = _variant_id(fmt, scale)
        t0 = time.time()
        idx_out, inten_out = index, intensity
        if scale != 1.0:
            idx_out = terrain_paint.downsample_index(index, scale)
            inten_out = terrain_paint.downsample_intensity(intensity, scale)
        ext = terrain_paint.paint_ext(fmt)
        variant_dir = variants_dir / variant
        terrain_dir = variant_dir / "gfx" / "map" / "terrain"
        terrain_dir.mkdir(parents=True, exist_ok=True)
        idx_p = terrain_dir / f"detail_index.{ext}"
        inten_p = terrain_dir / f"detail_intensity.{ext}"
        terrain_paint.save_paint(idx_out, idx_p, fmt)
        terrain_paint.save_paint(inten_out, inten_p, fmt)
        _write_descriptor(variant_dir, variant)
        dt = time.time() - t0
        row = {
            "variant": variant,
            "format": fmt,
            "scale": scale,
            "width": int(idx_out.shape[1]),
            "height": int(idx_out.shape[0]),
            "index_bytes": idx_p.stat().st_size,
            "intensity_bytes": inten_p.stat().st_size,
            "total_bytes": idx_p.stat().st_size + inten_p.stat().st_size,
            "seconds": round(dt, 2),
        }
        rows.append(row)
        print(
            f"{variant:16s} {row['width']}x{row['height']}  "
            f"index={row['index_bytes']/1e6:8.2f} MB  "
            f"intensity={row['intensity_bytes']/1e6:8.2f} MB  "
            f"total={row['total_bytes']/1e6:8.2f} MB  ({dt:.1f}s)"
        )
    return rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("out_dir", type=Path, help="converter output dir (contains gfx/map/terrain)")
    ap.add_argument(
        "--variants-dir",
        type=Path,
        default=None,
        help="default: <out_dir>/../paint_variants",
    )
    ap.add_argument(
        "--csv",
        type=Path,
        default=REPO / "docs" / "evidence" / "paint_variants.csv",
    )
    args = ap.parse_args(argv)

    out_dir = args.out_dir.resolve()
    variants_dir = (args.variants_dir or (out_dir.parent / "paint_variants")).resolve()
    variants_dir.mkdir(parents=True, exist_ok=True)

    rows = build_variants(out_dir, variants_dir)

    args.csv.parent.mkdir(parents=True, exist_ok=True)
    with args.csv.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"\nwrote {args.csv}")
    print(f"variant probe mods under {variants_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
