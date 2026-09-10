"""Measure every CK2 ``positions.txt`` slot against the generated map.

Lane ``map-assets``.  The converter anchors the county-capital barony's
locators on CK2 slot 0 (``[map] ck2_locator_positions``,
``docs/step_map_assets.md``).  This script is the evidence behind that choice
and the regression check on it: it puts **all seven** slots through exactly
the same transform and the same validity gate the converter uses
(:func:`ck2ck3.map.locators.ck2_capital_anchors`) and reports, per slot,

* how many county capitals had that slot at all,
* how many landed **inside their own barony** in the generated
  ``map_data/provinces.png`` — the accept rate,
* how many fell outside the canvas or in another province,
* the median distance from the centroid the locator would otherwise use,
* the distance from slot 0, in canvas pixels.

That last column is what rules slot 1 out for the unit stacks: vanilla keeps
a unit stack ~7 px from the settlement (``mappings/locator_offsets.csv``) and
CK2's slot 1 is three times that away (``docs/step_map_assets.md`` §4).

Run::

    uv run scripts/check_ck2_locator_slots.py            # uses configs/faerun.toml
    uv run scripts/check_ck2_locator_slots.py --mod DIR --config configs/faerun.toml

Writes ``docs/evidence/map_fidelity/locator_slots.csv``.
"""

from __future__ import annotations

import argparse
import csv
import sys
import tomllib
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ck2ck3.map import ck2read, locators  # noqa: E402
from ck2ck3.map.config import ScaleConfig, plan_canvas  # noqa: E402
from ck2ck3.map.provinces import painted_extent  # noqa: E402

Image.MAX_IMAGE_PIXELS = None

OUT = Path("docs/evidence/map_fidelity/locator_slots.csv")

#: the slot the converter actually anchors on
ADOPTED_SLOT = locators.CK2_ANCHOR_SLOT


def load_canvas(cfg_path: Path):
    """The canvas the converter plans, from the same TOML the converter reads.

    The crop matters: ``crop_to_painted`` moves every transformed coordinate,
    so re-deriving the canvas by hand would measure a different map.
    """
    cfg = tomllib.loads(cfg_path.read_text())
    repo = cfg_path.resolve().parent.parent
    m = cfg["map"]
    ck2_map = (repo / cfg["paths"]["ck2_mod"] / "map").resolve()
    scale = ScaleConfig(
        vanilla_km_per_px=float(m["vanilla_km_per_px"]),
        source_km_per_px=float(m["source_km_per_px"]),
        sea_margin_px=int(m.get("sea_margin_px", 64)),
        canvas_multiple=int(m.get("canvas_multiple", 64)),
        max_canvas_px=int(m.get("max_canvas_px", 32768)),
    )
    return cfg, repo, ck2_map, scale


def source_id_raster(bmp: Path, definitions) -> np.ndarray:
    rgb2id = {p.rgb: p.id for p in definitions}
    with Image.open(bmp) as im:
        a = np.asarray(im.convert("RGB"))
    key = (
        (a[:, :, 0].astype(np.uint32) << 16)
        | (a[:, :, 1].astype(np.uint32) << 8)
        | a[:, :, 2]
    )
    uniq, inv = np.unique(key, return_inverse=True)
    lut = np.array(
        [rgb2id.get(((int(u) >> 16) & 255, (int(u) >> 8) & 255, int(u) & 255), 0)
         for u in uniq],
        dtype=np.int32,
    )
    return lut[inv].reshape(a.shape[:2])


def ck3_id_raster(mod_dir: Path, idmap_csv: Path) -> np.ndarray:
    rgb2id = {}
    for r in csv.DictReader(idmap_csv.open()):
        if r["ck3_id"] and r["r"]:
            rgb2id[(int(r["r"]) << 16) | (int(r["g"]) << 8) | int(r["b"])] = int(
                r["ck3_id"]
            )
    with Image.open(mod_dir / "map_data/provinces.png") as im:
        a = np.asarray(im.convert("RGB"))
    key = (
        (a[:, :, 0].astype(np.uint32) << 16)
        | (a[:, :, 1].astype(np.uint32) << 8)
        | a[:, :, 2]
    )
    uniq, inv = np.unique(key, return_inverse=True)
    lut = np.array([rgb2id.get(int(u), 0) for u in uniq], dtype=np.int32)
    return lut[inv].reshape(a.shape[:2])


def centroids(raster: np.ndarray) -> dict[int, tuple[float, float]]:
    flat = raster.reshape(-1)
    w = raster.shape[1]
    n = int(flat.max()) + 1
    cnt = np.bincount(flat, minlength=n).astype(np.float64)
    idx = np.arange(flat.size, dtype=np.int64)
    sy = np.bincount(flat, weights=idx // w, minlength=n)
    sx = np.bincount(flat, weights=idx % w, minlength=n)
    return {
        int(i): (float(sx[i] / cnt[i]), float(sy[i] / cnt[i]))
        for i in np.nonzero(cnt)[0]
        if i
    }


def capital_ids(barony_set: Path, idmap_csv: Path) -> dict[int, int]:
    """CK2 province id -> CK3 province id of its county-capital barony."""
    by_key = {
        r["barony"]: int(r["ck3_id"])
        for r in csv.DictReader(idmap_csv.open())
        if r["kind"] == "barony" and r["ck3_id"]
    }
    out: dict[int, int] = {}
    for r in csv.DictReader(barony_set.open()):
        if r["status"] != "placed" or r["capital"] != "yes":
            continue
        pid = by_key.get(r["barony"])
        if pid is not None:
            out[int(r["ck2_province"])] = pid
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="configs/faerun.toml")
    ap.add_argument("--mod", default=None, help="generated mod root")
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args(argv)

    cfg, repo, ck2_map, scale = load_canvas(Path(args.config))
    mod_dir = Path(args.mod or cfg["paths"]["out"])

    defs = ck2read.read_definitions(ck2_map / "definition.csv")
    src_ids = source_id_raster(ck2_map / "provinces.bmp", defs)
    src_h, src_w = src_ids.shape
    crop = painted_extent(src_ids) if cfg["map"].get("provinces", {}).get(
        "crop_to_painted", True
    ) else None
    canvas = plan_canvas(src_w, src_h, scale, crop)
    print(
        f"source {src_w}x{src_h} -> canvas {canvas.width}x{canvas.height} "
        f"factor {canvas.factor:.6f} offset ({canvas.offset_x},{canvas.offset_y}) "
        f"crop {crop}"
    )

    positions = ck2read.read_positions(ck2_map / "positions.txt")
    raster = ck3_id_raster(mod_dir, repo / "docs/evidence/province_id_map.csv")
    cent = centroids(raster)
    caps = capital_ids(
        repo / "docs/evidence/barony_set.csv",
        repo / "docs/evidence/province_id_map.csv",
    )
    print(f"{len(caps)} county-capital baronies, {len(positions)} CK2 position blocks")

    rows = []
    for slot in range(7):
        _anchors, st = locators.ck2_capital_anchors(
            positions=positions,
            capital_ids=caps,
            canvas=canvas,
            source_height=src_h,
            raster=raster,
            centroids=cent,
            slot=slot,
        )
        d = st.as_dict()
        d["adopted"] = "anchor" if slot == ADOPTED_SLOT else "-"
        d["p90_move_px"] = (
            round(float(np.percentile(st.moves_px, 90)), 2) if st.moves_px else 0.0
        )
        rows.append(d)
        print(
            f"  slot {slot}: {st.accepted:>5}/{st.candidates} "
            f"({100 * st.accept_rate:5.1f} %) inside own barony, "
            f"{st.outside_province:>5} elsewhere, {st.off_canvas:>3} off canvas, "
            f"median move {st.median_move_px:6.1f} px  -> {d['adopted']}"
        )

    # slot 0 -> slot N distance, the number that rules slot 1 out for the unit
    # stacks: vanilla's own stack offset is ~7 px (mappings/
    # locator_offsets.csv), so a 20+ px CK2 spread is a different look.
    print("  distance from slot 0, canvas px (median / p95):")
    for slot in range(7):
        d = []
        for ck2_id in caps:
            s = positions.get(ck2_id)
            if not s or len(s) <= slot:
                continue
            a = canvas.to_target(s[0][0], src_h - s[0][1])
            b = canvas.to_target(s[slot][0], src_h - s[slot][1])
            d.append(float(np.hypot(a[0] - b[0], a[1] - b[1])))
        rows[slot]["dist_from_slot0_px"] = round(float(np.median(d)), 2) if d else 0.0
        rows[slot]["dist_from_slot0_p95_px"] = (
            round(float(np.percentile(d, 95)), 2) if d else 0.0
        )
        if slot:
            print(f"    slot {slot}: {np.median(d):6.1f} / "
                  f"{np.percentile(d, 95):6.1f}")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"-> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
