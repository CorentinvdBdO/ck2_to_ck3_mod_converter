"""Prototype: barony seeds from the CK2 positions.txt slots (lane map-fidelity).

CK2 ``map/positions.txt`` carries seven (x, y) slots per **province**, and a
CK2 province is a CK3 county.  The converter uses slot 0 (the capital/city
location) for the county capital barony only; every other barony is
farthest-point sampled inside the county mask.  This script asks whether the
other six slots are distinct enough, and inside the county often enough, to be
worth using as anchors for the non-capital baronies, and how much the answer
would move the borders we ship today.

Only slots 0 and 4 are named by CK2 itself — the binary logs "has illegal
capital location" and "Invalid port location for province" — so the other five
are described here by their measured signature, not by a guessed name.

Writes, for review only (nothing is wired into the converter):
  overrides/barony_seeds_ck2positions.csv            candidate seeds
  docs/evidence/map_fidelity/ck2_slots.csv           per-slot signature
  docs/evidence/map_fidelity/county_slot_spread.csv  per-county geometry
  docs/evidence/map_fidelity/seed_shift.csv          per-barony move vs today

Run: uv run python scripts/barony_seeds_from_ck2_positions.py
"""
from __future__ import annotations

import argparse
import csv
import re
import tomllib
from collections import defaultdict
from pathlib import Path

import numpy as np
from PIL import Image

from ck2ck3.map.config import ScaleConfig, plan_canvas

Image.MAX_IMAGE_PIXELS = None

OUT = Path("docs/evidence/map_fidelity")
SEED_OUT = Path("overrides/barony_seeds_ck2positions.csv")

SLOT_NOTES = {
    0: "capital/city (named by the CK2 binary)",
    1: "unnamed; always distinct from slot 0 and almost always inside the province",
    2: "unnamed; equal to slot 0 in 46 % of Faerun blocks",
    3: "unnamed; height = 20.000 in every block of both maps",
    4: "port (named by the CK2 binary); most often on water",
    5: "unnamed; rotation non-zero in 99 % of vanilla blocks (an oriented model)",
    6: "unnamed; rotation non-zero in 99 % of vanilla blocks (an oriented model)",
}

BLOCK_RE = re.compile(r"(\d+)\s*=\s*\{(.*?)\n\t\}", re.S)
FIELD_RE = {k: re.compile(rf"{k}=\{{([^}}]*)\}}") for k in ("position", "rotation", "height")}


def read_positions(path: Path):
    """province id -> (7 (x, y) pairs, rotations, heights). y is bottom-origin."""
    txt = path.read_text(encoding="latin-1")
    out = {}
    for m in BLOCK_RE.finditer(txt):
        body = m.group(2)
        pm = FIELD_RE["position"].search(body)
        if not pm:
            continue
        v = [float(x) for x in pm.group(1).split()]
        rm = FIELD_RE["rotation"].search(body)
        hm = FIELD_RE["height"].search(body)
        out[int(m.group(1))] = (
            list(zip(v[0::2], v[1::2])),
            [float(x) for x in rm.group(1).split()] if rm else [],
            [float(x) for x in hm.group(1).split()] if hm else [],
        )
    return out


def load_canvas(cfg_path: Path):
    cfg = tomllib.loads(cfg_path.read_text())
    ck2_map = Path(cfg["input"]["ck2_map_dir"])
    with Image.open(ck2_map / "provinces.bmp") as im:
        sw, sh = im.size
    sc = cfg["scale"]
    scale = ScaleConfig(
        vanilla_km_per_px=sc["vanilla_km_per_px"],
        source_km_per_px=sc["source_km_per_px"],
        sea_margin_px=sc["sea_margin_px"],
        canvas_multiple=sc["canvas_multiple"],
        max_canvas_px=sc["max_canvas_px"],
    )
    return cfg, ck2_map, sh, plan_canvas(sw, sh, scale)


def label_maps(mod_dir: Path, idmap_csv: Path):
    """(county keys, county->barony->ck3 id, county label image, province id image).

    Both images are built once from a lookup table: a per-county ``np.isin``
    over 56 Mpx would take hours.
    """
    rows = list(csv.DictReader(idmap_csv.open()))
    by_county: dict[str, dict[str, int]] = defaultdict(dict)
    for r in rows:
        if r["kind"] == "barony" and r["county"] and r["ck3_id"]:
            by_county[r["county"]][r["barony"]] = int(r["ck3_id"])
    keys = sorted(by_county)
    cidx = {k: i for i, k in enumerate(keys)}
    id2county = {pid: cidx[k] for k, bs in by_county.items() for pid in bs.values()}

    rgb2county, rgb2id = {}, {}
    for r in rows:
        if not r["ck3_id"] or not r["r"]:
            continue
        pid = int(r["ck3_id"])
        packed = (int(r["r"]) << 16) | (int(r["g"]) << 8) | int(r["b"])
        rgb2id[packed] = pid
        if pid in id2county:
            rgb2county[packed] = id2county[pid]

    with Image.open(mod_dir / "map_data/provinces.png") as im:
        a = np.asarray(im.convert("RGB"))
    key = (a[:, :, 0].astype(np.uint32) << 16) | (a[:, :, 1].astype(np.uint32) << 8) | a[:, :, 2]
    uniq, inv = np.unique(key, return_inverse=True)
    clut = np.array([rgb2county.get(int(u), -1) for u in uniq], dtype=np.int32)
    plut = np.array([rgb2id.get(int(u), 0) for u in uniq], dtype=np.int32)
    shape = a.shape[:2]
    return keys, by_county, clut[inv].reshape(shape), plut[inv].reshape(shape)


def centroids(pmap: np.ndarray) -> dict[int, tuple[float, float]]:
    flat = pmap.ravel()
    n = int(flat.max()) + 1
    cnt = np.bincount(flat, minlength=n).astype(float)
    ys = np.repeat(np.arange(pmap.shape[0], dtype=np.float64), pmap.shape[1])
    xs = np.tile(np.arange(pmap.shape[1], dtype=np.float64), pmap.shape[0])
    sy = np.bincount(flat, weights=ys, minlength=n)
    sx = np.bincount(flat, weights=xs, minlength=n)
    ok = cnt > 0
    out = {}
    for i in np.nonzero(ok)[0]:
        out[int(i)] = (sx[i] / cnt[i], sy[i] / cnt[i])
    return out


def slot_signature(pos, topo, src_h, factor) -> list[dict]:
    sig = []
    for s in range(7):
        d0, water, same0, rotnz = [], 0, 0, 0
        for pts, rot, _hei in pos.values():
            if len(pts) < 7:
                continue
            x, y = pts[s]
            x0, y0 = pts[0]
            d0.append(float(np.hypot(x - x0, y - y0)))
            same0 += (x, y) == (x0, y0)
            rotnz += s < len(rot) and abs(rot[s]) > 1e-6
            yy, xx = int(round(src_h - y)), int(round(x))
            if 0 <= yy < topo.shape[0] and 0 <= xx < topo.shape[1] and topo[yy, xx] <= 95:
                water += 1
        n = max(len(d0), 1)
        sig.append({
            "slot": s, "note": SLOT_NOTES[s], "blocks": len(d0),
            "pct_equal_to_slot0": round(100.0 * same0 / n, 1),
            "pct_rotation_nonzero": round(100.0 * rotnz / n, 1),
            "pct_on_water": round(100.0 * water / n, 1),
            "median_dist_from_slot0_ck2px": round(float(np.median(d0)), 2),
            "median_dist_from_slot0_ck3px": round(float(np.median(d0)) * factor, 1),
        })
    return sig


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="configs/faerun_map.toml")
    ap.add_argument("--mod-dir", default=None,
                    help="generated mod root; default = [output] mod_dir of the config")
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    cfg, ck2_map, src_h, canvas = load_canvas(Path(args.config))
    mod_dir = Path(args.mod_dir or cfg["output"]["mod_dir"])
    print(f"canvas {canvas.width}x{canvas.height} factor {canvas.factor:.4f} "
          f"offset ({canvas.offset_x},{canvas.offset_y})")

    pos = read_positions(ck2_map / "positions.txt")
    with Image.open(ck2_map / "topology.bmp") as im:
        topo = np.asarray(im)
    sig = slot_signature(pos, topo, src_h, canvas.factor)
    with (OUT / "ck2_slots.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(sig[0].keys()))
        w.writeheader()
        w.writerows(sig)
    for r in sig:
        print(f"  slot{r['slot']}  d0={r['median_dist_from_slot0_ck3px']:>6} ck3px  "
              f"=slot0 {r['pct_equal_to_slot0']:>5}%  water {r['pct_on_water']:>5}%  "
              f"rot {r['pct_rotation_nonzero']:>5}%")

    baronies = list(csv.DictReader(Path("docs/evidence/barony_set.csv").open()))
    keys, by_county, clab, pmap = label_maps(
        mod_dir, Path("docs/evidence/province_id_map.csv"))
    cidx = {k: i for i, k in enumerate(keys)}
    areas = np.bincount(clab[clab >= 0].ravel(), minlength=len(keys))
    cent = centroids(pmap)

    counties = defaultdict(list)
    for b in baronies:
        if b["status"] == "placed":
            counties[b["county"]].append(b)

    rows, seeds, shifts = [], [], []
    n_any = n_enough = 0
    for county, bs in sorted(counties.items()):
        ck2_prov = int(bs[0]["ck2_province"])
        slots = pos.get(ck2_prov)
        ci = cidx.get(county)
        if not slots or ci is None or areas[ci] == 0:
            continue
        radius = float(np.sqrt(int(areas[ci]) / np.pi))

        pts3 = [canvas.to_target(x, src_h - y) for (x, y) in slots[0][:7]]
        uniq_pts = sorted(set(pts3))
        inside = [p for p in uniq_pts
                  if 0 <= p[1] < clab.shape[0] and 0 <= p[0] < clab.shape[1]
                  and clab[p[1], p[0]] == ci]

        def spread(points):
            if len(points) < 2:
                return 0.0
            a = np.array(points, dtype=float)
            d = np.hypot(a[:, None, 0] - a[None, :, 0], a[:, None, 1] - a[None, :, 1])
            return float(d.max())

        sp_in = spread(inside)
        rows.append({
            "county": county, "ck2_province": ck2_prov, "baronies": len(bs),
            "county_px": int(areas[ci]), "county_radius_px": round(radius, 1),
            "distinct_slots": len(uniq_pts),
            "distinct_slots_inside_county": len(inside),
            "spread_all_slots_px": round(spread(uniq_pts), 1),
            "spread_inside_px": round(sp_in, 1),
            "spread_inside_over_radius": round(sp_in / radius, 3) if radius else 0.0,
        })
        n_any += len(inside) >= 2
        n_enough += len(inside) >= len(bs)

        used: list[tuple[int, int]] = []
        order = sorted(bs, key=lambda b: (b["capital"] != "yes", b["barony"]))
        for b in order:
            pick = why = None
            if b["capital"] == "yes" and pts3[0] in inside and pts3[0] not in used:
                pick, why = pts3[0], "slot0 capital/city"
            elif b["holding"] == "city_holding" and pts3[4] in inside and pts3[4] not in used:
                pick, why = pts3[4], "slot4 port"
            else:
                free = [p for p in inside if p not in used]
                if free:
                    if used:
                        u = np.array(used, dtype=float)
                        fa = np.array(free, dtype=float)
                        dd = np.hypot(fa[:, None, 0] - u[None, :, 0],
                                      fa[:, None, 1] - u[None, :, 1]).min(axis=1)
                        pick = free[int(dd.argmax())]
                    else:
                        pick = free[0]
                    why = f"slot{pts3.index(pick)} (farthest free in-county slot)"
            if pick is None:
                continue
            used.append(pick)
            seeds.append({"barony_id": b["barony"], "x": pick[0], "y": pick[1],
                          "note": f"{county} {b['holding']} <- {why}"})
            pid = by_county[county].get(b["barony"])
            cx, cy = cent.get(pid, (float("nan"), float("nan")))
            shifts.append({
                "barony": b["barony"], "county": county, "ck3_province": pid,
                "seed_x": pick[0], "seed_y": pick[1],
                "current_centroid_x": round(cx, 1), "current_centroid_y": round(cy, 1),
                "dist_px": round(float(np.hypot(pick[0] - cx, pick[1] - cy)), 1),
                "seed_in_current_cell": "yes" if (pid and pmap[pick[1], pick[0]] == pid) else "no",
                "current_seed_source": b["seed_source"],
            })

    for name, data in (("county_slot_spread.csv", rows), ("seed_shift.csv", shifts)):
        with (OUT / name).open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(data[0].keys()))
            w.writeheader()
            w.writerows(data)

    hdr = ("# barony_id,x,y,note\n"
           "# PROTOTYPE, NOT WIRED IN. Candidate barony seeds derived from the CK2\n"
           "# positions.txt slots; same format as overrides/barony_seeds.csv, so a\n"
           "# reviewer can copy rows across.  x,y are canvas pixels of the generated\n"
           "# map_data/provinces.png, top-left origin.\n"
           "# Generated by scripts/barony_seeds_from_ck2_positions.py.\n"
           "# Only the slot-0 (capital/city) and slot-4 (port) rows carry a meaning\n"
           "# CK2 itself gives the slot; the rest are geometry, not semantics.\n"
           "# See docs/map_fidelity.md.\n")
    with SEED_OUT.open("w", newline="") as f:
        f.write(hdr)
        csv.DictWriter(f, fieldnames=["barony_id", "x", "y", "note"]).writerows(seeds)

    ds = np.array([r["distinct_slots"] for r in rows])
    dsi = np.array([r["distinct_slots_inside_county"] for r in rows])
    spr = np.array([r["spread_inside_over_radius"] for r in rows])
    rad = np.array([r["county_radius_px"] for r in rows])
    dist = np.array([s["dist_px"] for s in shifts])
    inc = sum(s["seed_in_current_cell"] == "yes" for s in shifts)
    print(f"\ncounties measured                   {len(rows)}")
    print(f"median county radius                {np.median(rad):.1f} px "
          f"({np.median(rad) * 1.4839:.0f} km)")
    print(f"median distinct slots               {np.median(ds):.1f} of 7")
    print(f"median distinct slots inside county {np.median(dsi):.1f}")
    print(f"counties with >=2 in-county slots   {n_any} ({100 * n_any / len(rows):.1f} %)")
    print(f"counties with >= 1 slot per barony  {n_enough} ({100 * n_enough / len(rows):.1f} %)")
    print(f"in-county slot spread / radius      median {np.median(spr):.2f}, "
          f"p90 {np.percentile(spr, 90):.2f}")
    print(f"seed rows                           {len(seeds)} -> {SEED_OUT}")
    print(f"median move vs today's cell centre  {np.median(dist):.1f} px "
          f"({np.median(dist) * 1.4839:.0f} km)")
    print(f"seeds still inside today's cell     {inc} ({100 * inc / len(shifts):.1f} %)")


if __name__ == "__main__":
    main()
