#!/usr/bin/env python3
"""Lane `relief-pits` part C: is our mountain relief the *shape* vanilla's is?

"Smooth" is not a spectrum complaint -- we already exceed vanilla at
0.3 cycles/km (`docs/step_map_heightmap.md` §2c). It is a shape complaint, so
this measures shape and nothing else, on crops of the same ground extent:

* `grad_kurtosis` -- fourth moment of |grad h|. A field of smooth bumps has a
  near-Gaussian gradient (kurtosis ~ 0); sharp crests separated by smooth
  valleys put weight in the tail.
* `grad_p99_over_rms` -- the same question without the fourth power.
* `ridge_share` -- the fraction of land pixels that are crests: a local
  maximum across the direction of strongest downward curvature. No amplitude
  threshold anywhere in it.
* `ridge_mean_run_px` -- pixel-weighted mean size of a connected crest
  component, i.e. how far a ridge line runs before it breaks up.

The vanilla reference is the three highest-relief all-land 1024 px windows of
`game/map_data/heightmap.png` (`heightmap_erosion_evidence.VANILLA_CROPS`),
halved to our 1.4839 km/px, so a vanilla crop and one of ours cover the same
760 km and are sampled at the same ground scale.

Usage:
  uv run python scripts/relief_pits_shape.py [--maps name=heightmap.png ...]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import heightmap_structure_metrics as M  # noqa: E402
import relief_pits_common as P  # noqa: E402
import relief_sharp_common as C  # noqa: E402
from relief_pits_diagnose import write_csv  # noqa: E402

OUT = C.ROOT / "docs/evidence/relief_pits"
GAME = C.ROOT / "../claudespace/game_files"
#: the same three vanilla mountain windows lane `erosion` measured against
VANILLA_CROPS = ((4352, 9984), (3584, 9216), (3840, 9728))
CROP_PX = 512  # 760 km at our 1.4839 km/px


def halve(a: np.ndarray) -> np.ndarray:
    """A 2x vanilla sheet resampled to our pixel size by 2x2 mean."""
    h, w = a.shape[0] // 2 * 2, a.shape[1] // 2 * 2
    return a[:h, :w].astype(np.float32).reshape(h // 2, 2, w // 2, 2).mean((1, 3))


def our_crops() -> dict[str, tuple[int, int]]:
    """`{name: (y, x)}` -- the Spine of the World and Thaymount, 512 px each.

    Thaymount is located rather than hard-coded: the highest pixel of the
    plain rescale inside the Thay window, which is what that mountain is.
    """
    c = C.crops()
    spine = (c["spine"]["crop_y"], c["spine"]["crop_x"])
    base = C.plain_rescale_canvas()
    y0, x0, y1, x1 = 1583, 4752, 2222, 5311
    win = base[y0:y1, x0:x1]
    iy, ix = np.unravel_index(int(np.argmax(win)), win.shape)
    ty = int(np.clip(y0 + iy - CROP_PX // 2, 0, base.shape[0] - CROP_PX))
    tx = int(np.clip(x0 + ix - CROP_PX // 2, 0, base.shape[1] - CROP_PX))
    return {"spine": spine, "thaymount": (ty, tx)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--maps", nargs="*", default=[])
    ap.add_argument("--out-csv", default="shape_metrics.csv")
    ap.add_argument("--tag", default="")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    rows: list[dict] = []
    van = C.load16(GAME / "map_data/heightmap.png")
    for i, (y, x) in enumerate(VANILLA_CROPS):
        c = halve(van[y:y + 2 * CROP_PX, x:x + 2 * CROP_PX])
        m = np.ones(c.shape, dtype=bool)
        r = {"crop": f"vanilla_mountains_{i}", "map": "ck3_vanilla"}
        r.update(P.shape_metrics(c, m, C.KM_PX_OURS))
        r.update(P.local_relief(c, m))
        rows.append(r)
        if i == 0:
            Image.fromarray(M.hillshade(c, C.KM_PX_OURS)).save(
                OUT / "hillshade_vanilla_mountains.png")
    del van

    maps: dict[str, Path] = {"plain_rescale": None,
                             "build15": C.LIVE_MOD / "map_data/heightmap.png"}
    for spec in args.maps:
        name, _, path = spec.partition("=")
        maps[name] = Path(path)
    base = C.plain_rescale_canvas()
    crops = our_crops()
    (OUT / "shape_crops.json").write_text(json.dumps(
        {k: {"y": v[0], "x": v[1], "side": CROP_PX} for k, v in crops.items()},
        indent=2))
    live_land = C.province_land_mask(C.load16(C.LIVE_MOD / "map_data/heightmap.png"))
    for name, path in maps.items():
        if path is None:
            arr = base
        elif not path.exists():
            print(f"skip {name}: {path} missing")
            continue
        else:
            arr = C.load16(path)
        for crop, (y, x) in crops.items():
            ys, xs = slice(y, y + CROP_PX), slice(x, x + CROP_PX)
            a = arr[ys, xs].astype(np.float32)
            m = live_land[ys, xs]
            r = {"crop": crop, "map": name}
            r.update(P.shape_metrics(a, m, C.KM_PX_OURS))
            r.update(P.local_relief(a, m))
            rows.append(r)
            tag = f"_{args.tag}" if args.tag else ""
            Image.fromarray(M.hillshade(a, C.KM_PX_OURS)).save(
                OUT / f"hillshade_{crop}_{name}{tag}.png")
        del arr

    van_rows = [r for r in rows if r["map"] == "ck3_vanilla"]
    for key in ("grad_kurtosis", "grad_p99_over_rms", "ridge_share",
                "ridge_mean_run_px"):
        v = float(np.mean([r[key] for r in van_rows]))
        for r in rows:
            r[f"{key}_vs_vanilla"] = round(r[key] / v, 3) if v else ""
    write_csv(OUT / args.out_csv, rows)
    for r in rows:
        print(f"  {r['crop']:22s} {r['map']:16s} kurt {r['grad_kurtosis']:7.2f}"
              f" ({r['grad_kurtosis_vs_vanilla']:5.2f}x)"
              f"  p99/rms {r['grad_p99_over_rms']:5.2f}"
              f" ({r['grad_p99_over_rms_vs_vanilla']:5.2f}x)"
              f"  ridge {r['ridge_share']:.4f}"
              f" ({r['ridge_share_vs_vanilla']:5.2f}x)"
              f"  run {r['ridge_mean_run_px']:7.2f}"
              f" ({r['ridge_mean_run_px_vs_vanilla']:5.2f}x)")


if __name__ == "__main__":
    main()
