"""Is CK3's detail_index.tga the baked form of gfx/map/terrain/masks/*.png?

If it is, a converter can write the pair itself and never open the map editor —
the same trick `ck2ck3.map.packed_heightmap` already pulls for the heightmap.

Method: sample land pixels, read every material mask at those pixels, and check
that the four material ids in detail_index.tga are the four masks with the
largest value there, and that detail_intensity.tga holds their weights.

Writes docs/evidence/map_fidelity/detail_index_check.csv.
Run: nohup uv run python scripts/verify_detail_index.py > docs/evidence/map_fidelity/detail_index.log 2>&1 &
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None

CK3 = Path("/home/cvdbdo/.local/share/Steam/steamapps/common/Crusader Kings III/game")
TER = CK3 / "gfx/map/terrain"
OUT = Path("docs/evidence/map_fidelity")
N = 400


def material_order() -> list[tuple[str, str]]:
    """(id, mask path) in materials.settings declaration order."""
    txt = (TER / "materials.settings").read_text(encoding="utf-8-sig", errors="replace")
    out = []
    for blk in re.finditer(r"\{([^{}]*)\}", txt):
        b = blk.group(1)
        mid = re.search(r'\bid\s*=\s*"([^"]+)"', b)
        msk = re.search(r'\bmask\s*=\s*"([^"]+)"', b)
        if mid and msk:
            out.append((mid.group(1), msk.group(1)))
    return out


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    mats = material_order()
    print(f"{len(mats)} materials with a mask", flush=True)

    with Image.open(TER / "detail_index.tga") as im:
        idx = np.asarray(im)
    with Image.open(TER / "detail_intensity.tga") as im:
        inten = np.asarray(im)
    print(f"detail_index {idx.shape} {idx.dtype}; intensity {inten.shape}", flush=True)

    rng = np.random.default_rng(5)
    H, W = idx.shape[:2]
    ys = rng.integers(0, H, N * 4)
    xs = rng.integers(0, W, N * 4)
    keep = inten[ys, xs, 0] > 0
    ys, xs = ys[keep][:N], xs[keep][:N]
    print(f"sampled {len(ys)} pixels with non-zero first intensity", flush=True)

    vals = np.zeros((len(mats), len(ys)), dtype=np.uint8)
    for i, (mid, rel) in enumerate(mats):
        p = TER / rel
        if not p.exists():
            print(f"  MISSING {rel}", flush=True)
            continue
        with Image.open(p) as im:
            a = np.asarray(im.convert("L"))
        vals[i] = a[ys, xs]
        if i % 20 == 0:
            print(f"  read {i}/{len(mats)}", flush=True)

    rows, exact_top4, exact_all = [], 0, 0
    for j in range(len(ys)):
        col = vals[:, j].astype(int)
        top = np.argsort(-col)[:4]
        got = [int(v) for v in idx[ys[j], xs[j]][:4]]
        wgt = [int(v) for v in inten[ys[j], xs[j]][:4]]
        hit = sum(1 for g in got if g < len(mats) and g in set(top.tolist()))
        exact_top4 += hit == 4
        mask_of_got = [int(col[g]) if g < len(mats) else -1 for g in got]
        exact_all += mask_of_got == wgt
        rows.append({
            "y": int(ys[j]), "x": int(xs[j]),
            "index_rgba": "/".join(map(str, got)),
            "intensity_rgba": "/".join(map(str, wgt)),
            "material_ids": "/".join(mats[g][0] if g < len(mats) else "?" for g in got),
            "mask_values_at_those_ids": "/".join(map(str, mask_of_got)),
            "top4_by_mask": "/".join(mats[int(t)][0] for t in top),
            "in_top4": hit,
        })

    with (OUT / "detail_index_check.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    n = len(rows)
    print(f"\nsamples                          {n}")
    print(f"all four index channels in top-4 {exact_top4} ({100*exact_top4/n:.1f} %)")
    print(f"intensity == mask value exactly  {exact_all} ({100*exact_all/n:.1f} %)")
    print(f"mean channels in top-4           {np.mean([r['in_top4'] for r in rows]):.2f} / 4")


if __name__ == "__main__":
    main()
