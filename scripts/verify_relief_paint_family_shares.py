#!/usr/bin/env python3
"""Does the generated mod's own paint reproduce vanilla's measured per-class
family area distribution, within +-30%?

`docs/step_map_paint.md` §11 / coordinator review success criterion #3.
Reuses the same per-class interior definition (dist > 5px from a class
boundary) `scripts/measure_vanilla_relief_paint.py` uses on vanilla, applied
here to OUR generated mod's own `detail_index.tga` + `common/province_terrain`
+ `map_data/provinces.png`.

Usage::

    uv run scripts/verify_relief_paint_family_shares.py <out_mod_dir>
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))

from ck2ck3.map.terrain_paint import material_ordinals  # noqa: E402
from ck2ck3.map.relief_paint import CATEGORY_NAMES, classify_material  # noqa: E402
import verify_terrain_paint_materials as vtpm  # noqa: E402

OUT = REPO / "docs/evidence/relief_paint"


def class_map(mod_dir: Path):
    prov_terrain = vtpm.read_province_terrain(mod_dir)
    rgb_to_id = vtpm.read_definition(mod_dir / "map_data" / "definition.csv")
    rgbkey_to_tkey = {}
    for (r, g, b), pid in rgb_to_id.items():
        rgbkey_to_tkey[(r << 16) | (g << 8) | b] = prov_terrain.get(pid, "")
    with Image.open(mod_dir / "map_data" / "provinces.png") as im:
        prov = np.asarray(im.convert("RGB"))
    H, W = prov.shape[:2]
    key = ((prov[:, :, 0].astype(np.uint32) << 16)
           | (prov[:, :, 1].astype(np.uint32) << 8) | prov[:, :, 2])
    uniq, inv = np.unique(key, return_inverse=True)
    tkey_per_uniq = [rgbkey_to_tkey.get(int(u), "") for u in uniq]
    names = sorted(set(tkey_per_uniq))
    code_of = {n: i for i, n in enumerate(names)}
    codes_per_uniq = np.array([code_of[t] for t in tkey_per_uniq], dtype=np.int16)
    return codes_per_uniq[inv].reshape(H, W), names


def load_paint_primary(mod_dir: Path) -> np.ndarray:
    terrain_dir = mod_dir / "gfx" / "map" / "terrain"
    for ext in ("tga",):
        p = terrain_dir / f"detail_index.{ext}"
        if p.exists():
            from ck2ck3.map.terrain_paint import load_paint
            return load_paint(p, "tga")[..., 0].astype(np.int32)
    raise FileNotFoundError(f"no detail_index.tga under {terrain_dir}")


def main(argv: list[str]) -> int:
    mod_dir = Path(argv[1] if len(argv) > 1 else
                    "/home/cvdbdo/git/paradox/ck3/wt/_out/relief-paint")
    print(f"mod dir: {mod_dir}")

    codes, names = class_map(mod_dir)
    idx0 = load_paint_primary(mod_dir)
    assert idx0.shape == codes.shape, (idx0.shape, codes.shape)

    from scipy.ndimage import distance_transform_edt
    bnd = np.zeros(codes.shape, dtype=bool)
    bnd[:, :-1] |= codes[:, :-1] != codes[:, 1:]
    bnd[:, 1:] |= codes[:, :-1] != codes[:, 1:]
    bnd[:-1, :] |= codes[:-1, :] != codes[1:, :]
    bnd[1:, :] |= codes[:-1, :] != codes[1:, :]
    interior = distance_transform_edt(~bnd) > 5
    del bnd

    # the generated mod never ships materials.settings (that is vanilla's own
    # file, only read at build time to resolve ordinals) -- read vanilla's.
    ordinals = material_ordinals(vtpm.DEFAULT_GAME / "gfx" / "map" / "terrain"
                                  / "materials.settings")
    name_of_ordinal = {v: k for k, v in ordinals.items()}
    cat_code = {c: i for i, c in enumerate(CATEGORY_NAMES)}
    cat_of_ordinal = np.zeros(256, dtype=np.uint8)
    for o in range(256):
        mat = name_of_ordinal.get(o)
        cat_of_ordinal[o] = cat_code.get(classify_material(mat) if mat else "other",
                                          cat_code["other"])
    category = cat_of_ordinal[idx0]

    # vanilla targets
    target: dict[tuple[str, str], float] = {}
    with (OUT.parent / "vanilla_paint_family_area_shares.csv").open(
        newline="", encoding="utf-8"
    ) as f:
        for row in csv.DictReader(f):
            target[(row["ck3_terrain"], row["family"])] = float(row["share_pct"])

    rows = []
    n_ok = n_total = 0
    for cls_name in names:
        if not cls_name:
            continue
        code = names.index(cls_name)
        mask = interior & (codes == code)
        n = int(mask.sum())
        if n < 200:
            continue
        cats = category[mask]
        counts = np.bincount(cats, minlength=len(CATEGORY_NAMES))
        for fi, fam in enumerate(CATEGORY_NAMES):
            ours_pct = 100.0 * counts[fi] / n
            van_pct = target.get((cls_name, fam))
            if van_pct is None or van_pct < 1.0:
                continue  # too rare in vanilla to be a meaningful check
            ratio = ours_pct / van_pct if van_pct else float("nan")
            ok = 0.7 <= ratio <= 1.3
            n_total += 1
            n_ok += int(ok)
            rows.append({
                "ck3_terrain": cls_name, "family": fam,
                "ours_pct": round(ours_pct, 2), "vanilla_pct": round(van_pct, 2),
                "ratio": round(ratio, 3), "within_30pct": ok,
            })

    with (OUT / "relief_paint_family_share_check.csv").open(
        "w", newline="", encoding="utf-8"
    ) as f:
        w = csv.DictWriter(f, fieldnames=["ck3_terrain", "family", "ours_pct",
                                           "vanilla_pct", "ratio", "within_30pct"])
        w.writeheader()
        w.writerows(rows)

    for r in rows:
        flag = "OK" if r["within_30pct"] else "**"
        print(f"  {flag} {r['ck3_terrain']:16s} {r['family']:8s} "
              f"ours {r['ours_pct']:6.2f}%  vanilla {r['vanilla_pct']:6.2f}%  "
              f"ratio {r['ratio']}")
    print(f"\n{n_ok}/{n_total} (class, family >= 1% in vanilla) rows within +-30%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
