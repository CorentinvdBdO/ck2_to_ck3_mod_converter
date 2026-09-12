"""What the organic-border pass did to the map, two builds side by side.

Lane ``province-edges``.  The smoothing is only allowed to change the *shape*
of a border, so everything this script prints has to come out near zero:

* the province set is unchanged — compared by ``definition.csv`` **column 5**
  (the barony title id, or the CK2 province slug), never by the numeric id:
  ids are dense and hierarchy-ordered, so one barony changing status renumbers
  every province after it and an id-keyed diff reads as a rewritten map;
* every barony still exists and none of them changed area by more than
  ``--area-tolerance``;
* the 4-connected neighbour graph gained and lost few pairs, and
  ``adjacencies.csv`` — the hand-written straits and river crossings — still
  names province pairs that exist;
* the coastline moved, but by less than one CK2 source pixel;
* the **heightmap** agrees with the new coastline pixel for pixel
  (``heightmap_coast``): ``heightmap_detail.apply`` pins every land pixel
  above and every water pixel at or below ``water_level`` from the province
  raster's own mask, so a change to ``provinces.png``'s coast is a change to
  ``heightmap.png``'s coast.  ``--ck2-map-dir`` additionally measures how far
  the *plain rescale* of ``topology.bmp`` is from that pinned line, which is
  the coast ``deepen_sea`` sees, because it runs before the detail pass.

Usage::

    uv run scripts/province_edges_report.py \
        --before ../claudespace/mods/faerun_ck2_to_ck3_converted \
        --after  ../wt/_out/province-edges \
        --out-dir docs/evidence/province_edges

``--before``/``--after`` are **mod roots** (the folder holding ``map_data``).
``--barony-set-before`` points at the other build's
``docs/evidence/barony_set.csv`` when it is not next to the mod; without it
the barony comparison is skipped.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from ck2ck3.map import province_edges  # noqa: E402

Image.MAX_IMAGE_PIXELS = None


# --------------------------------------------------------------------------- #
def read_definition(map_data: Path) -> dict[int, tuple[str, tuple[int, int, int]]]:
    """``definition.csv`` -> id -> (column 5 name, rgb)."""
    out: dict[int, tuple[str, tuple[int, int, int]]] = {}
    with (map_data / "definition.csv").open(encoding="utf-8-sig", errors="replace") as fh:
        for row in csv.reader(fh, delimiter=";"):
            if len(row) < 5 or not row[0].strip().isdigit():
                continue
            out[int(row[0])] = (row[4].strip(), (int(row[1]), int(row[2]), int(row[3])))
    return out


def read_name_raster(
    map_data: Path,
    defs: dict[int, tuple[str, tuple[int, int, int]]],
    names: dict[str, int],
) -> np.ndarray:
    """``provinces.png`` as a raster of **shared name indices** (0 = unknown).

    ``names`` is a growing name -> index dict shared by both builds, which is
    what makes the two rasters comparable pixel by pixel even though their
    numeric province ids differ.
    """
    with Image.open(map_data / "provinces.png") as im:
        rgb = np.asarray(im.convert("RGB")).astype(np.int32)
    key = (rgb[..., 0] << 16) | (rgb[..., 1] << 8) | rgb[..., 2]
    lut: dict[int, int] = {}
    for _pid, (name, (r, g, b)) in defs.items():
        lut[(r << 16) | (g << 8) | b] = names.setdefault(name, len(names) + 1)
    uniq, inv = np.unique(key, return_inverse=True)
    table = np.array([lut.get(int(k), 0) for k in uniq.tolist()], dtype=np.int32)
    return table[inv].reshape(key.shape)


def read_adjacencies(map_data: Path) -> list[tuple[int, int, int]]:
    """``adjacencies.csv`` -> the (from, to, through) triples it declares."""
    out: list[tuple[int, int, int]] = []
    path = map_data / "adjacencies.csv"
    if not path.exists():
        return out
    with path.open(encoding="utf-8-sig", errors="replace") as fh:
        for row in csv.reader(fh, delimiter=";"):
            if len(row) < 3 or not row[0].strip().lstrip("-").isdigit():
                continue
            try:
                # From;To;Type;Through;start_x;...  -- `through` is column 3
                out.append((int(row[0]), int(row[1]), int(row[3])))
            except (ValueError, IndexError):
                continue
    return out


def read_barony_set(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8-sig", errors="replace") as fh:
        return {r["barony"]: r for r in csv.DictReader(fh) if r.get("barony")}


# --------------------------------------------------------------------------- #
def compare_definitions(a: dict, b: dict) -> dict:
    """Provinces added/removed by NAME, and the colours that moved under a name.

    A colour is derived from the barony title id (`blake2b`, never a counter),
    so a province that still exists must keep its colour even when its numeric
    id moved.  `recoloured_n` is the number that must be 0.
    """
    ca = {name: rgb for _pid, (name, rgb) in a.items()}
    cb = {name: rgb for _pid, (name, rgb) in b.items()}
    recoloured = sorted(n for n in set(ca) & set(cb) if ca[n] != cb[n])
    return {
        "provinces_before": len(ca),
        "provinces_after": len(cb),
        "added": sorted(set(cb) - set(ca))[:50],
        "added_n": len(set(cb) - set(ca)),
        "removed": sorted(set(ca) - set(cb))[:50],
        "removed_n": len(set(ca) - set(cb)),
        "recoloured": recoloured[:50],
        "recoloured_n": len(recoloured),
        "ids_renumbered": sum(
            1
            for pid in set(a) & set(b)
            if a[pid][0] != b[pid][0]
        ),
    }


def compare_adjacency_file(
    rows: list[tuple[int, int, int]],
    defs: dict,
    names: np.ndarray,
    index: dict[str, int],
) -> dict:
    """Every endpoint of ``adjacencies.csv`` must still own pixels.

    A strait whose `from`, `to` or `through` province has no pixel left is a
    dead crossing; that is the failure mode a border reshape could cause.
    """
    present = set(np.unique(names).tolist())
    def alive(pid: int) -> bool:
        if pid <= 0:
            return True
        name = defs.get(pid, ("", None))[0]
        return index.get(name, -1) in present
    dangling = [r for r in rows if not all(alive(v) for v in r)]
    return {
        "rows": len(rows),
        "endpoints_without_pixels": len(dangling),
        "examples": dangling[:10],
    }


def coast_shift(a_ids: np.ndarray, b_ids: np.ndarray, water: set[int]) -> dict:  # noqa: D401
    """How far the land/water line moved, in canvas pixels."""
    from scipy.ndimage import distance_transform_edt

    wa = np.fromiter(water, dtype=np.int32)
    land_a = ~np.isin(a_ids, wa) & (a_ids > 0)
    land_b = ~np.isin(b_ids, wa) & (b_ids > 0)
    changed = land_a != land_b
    n = int(changed.sum())
    if n == 0:
        return {"changed_px": 0, "max_px": 0.0, "p95_px": 0.0, "mean_px": 0.0}
    # distance from each flipped pixel to the nearest pixel that already had
    # its new state, i.e. how far the line itself travelled
    d = np.zeros(a_ids.shape, dtype=np.float32)
    for state in (True, False):
        sel = changed & (land_b == state)
        if not sel.any():
            continue
        edt = distance_transform_edt(land_a != state).astype(np.float32)
        d[sel] = edt[sel]
        del edt
    v = d[changed]
    return {
        "changed_px": n,
        "changed_share": round(n / float(a_ids.size), 6),
        "max_px": round(float(v.max()), 3),
        "p95_px": round(float(np.percentile(v, 95)), 3),
        "mean_px": round(float(v.mean()), 3),
    }


def heightmap_coast(
    map_data: Path,
    land: np.ndarray,
    water_level: int,
    ck2_map_dir: Path | None,
) -> dict:
    """Does ``heightmap.png`` put the shoreline where ``provinces.png`` does?"""
    with Image.open(map_data / "heightmap.png") as im:
        heights = np.asarray(im)
    f = max(1, heights.shape[0] // land.shape[0])
    hl = heights[::f, ::f][: land.shape[0], : land.shape[1]] > water_level
    out = {
        "water_level": water_level,
        "resolution_factor": f,
        "province_land_px": int(land.sum()),
        "heightmap_land_px": int(hl.sum()),
        "disagreeing_px": int((land != hl).sum()),
        "land_but_under_water": int((land & ~hl).sum()),
        "water_but_above_level": int((~land & hl).sum()),
    }
    if ck2_map_dir is not None:
        out["plain_rescale"] = _plain_rescale_coast(
            map_data, ck2_map_dir, land, water_level
        )
    return out


def _plain_rescale_coast(
    map_data: Path, ck2_map_dir: Path, land: np.ndarray, water_level: int
) -> dict:
    """The coast `deepen_sea` sees: topology.bmp rescaled, before the detail pass.

    `deepen_sea` runs on the plain rescale and ramps its shelf from *that*
    shoreline; the detail pass afterwards moves the shoreline onto the
    province mask.  Where the two disagree the shelf ramp starts a pixel or
    two off the finished coast.  The number here is how often that happens.
    """
    from ck2ck3.map import config as map_config
    from ck2ck3.map import heightmap as hm
    from ck2ck3.map import provinces as pv

    src_ids = pv.rgb_key(
        np.asarray(Image.open(ck2_map_dir / "provinces.bmp").convert("RGB"))
    )
    sh, sw = src_ids.shape
    h, w = land.shape
    cfg = map_config.load(Path("configs/faerun_map.toml"))
    canvas = map_config.plan_canvas(sw, sh, cfg.scale, (0, 0, sw, sh))
    if (canvas.height, canvas.width) != (h, w):
        return {"skipped": f"canvas {canvas.height}x{canvas.width} != map {h}x{w}"}
    plain = hm.build(ck2_map_dir / "topology.bmp", canvas, cfg.heightmap)
    f = cfg.heightmap.resolution_factor
    pl = plain[::f, ::f][:h, :w] > water_level
    return {
        "disagreeing_px": int((land != pl).sum()),
        "disagreeing_share": round(float((land != pl).mean()), 6),
        "land_but_under_water": int((land & ~pl).sum()),
        "water_but_above_level": int((~land & pl).sum()),
    }


def water_name_indices(
    map_data: Path, defs: dict, index: dict[str, int]
) -> set[int]:
    """The shared name indices of every sea/lake/river province of one build."""
    return {
        index[defs[pid][0]]
        for pid in _water_ids(map_data)
        if pid in defs and defs[pid][0] in index
    }


def _water_ids(map_data: Path) -> set[int]:
    text = (map_data / "default.map").read_text(encoding="utf-8-sig", errors="replace")
    ids: set[int] = set()
    for m in re.finditer(
        r"^\s*(sea_zones|river_provinces|lakes)\s*=\s*(RANGE|LIST)\s*\{([^}]*)\}",
        text,
        re.MULTILINE,
    ):
        nums = [int(v) for v in m.group(3).split()]
        if m.group(2) == "RANGE" and len(nums) == 2:
            ids.update(range(nums[0], nums[1] + 1))
        else:
            ids.update(nums)
    return ids


def compare_baronies(a: dict, b: dict, tolerance: float) -> tuple[dict, list[dict]]:
    """Status changes and the baronies whose area moved beyond ``tolerance``."""
    rows: list[dict] = []
    status_changed: list[str] = []
    for key in sorted(set(a) | set(b)):
        ra, rb = a.get(key), b.get(key)
        if ra is None or rb is None:
            status_changed.append(key)
            continue
        if ra.get("status") != rb.get("status"):
            status_changed.append(key)
        try:
            na, nb = int(ra.get("pixels") or 0), int(rb.get("pixels") or 0)
        except ValueError:
            continue
        if na <= 0:
            continue
        rel = (nb - na) / float(na)
        if abs(rel) > tolerance:
            rows.append(
                {
                    "barony": key,
                    "county": rb.get("county", ""),
                    "status_before": ra.get("status", ""),
                    "status_after": rb.get("status", ""),
                    "pixels_before": na,
                    "pixels_after": nb,
                    "rel_change": round(rel, 4),
                }
            )
    rows.sort(key=lambda r: abs(r["rel_change"]), reverse=True)
    summary = {
        "baronies_before": len(a),
        "baronies_after": len(b),
        "only_before": sorted(set(a) - set(b))[:50],
        "only_after": sorted(set(b) - set(a))[:50],
        "status_changed": status_changed[:50],
        "status_changed_n": len(status_changed),
        "tolerance": tolerance,
        "beyond_tolerance_n": len(rows),
    }
    return summary, rows


# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--before", type=Path, required=True, help="mod root")
    ap.add_argument("--after", type=Path, required=True, help="mod root")
    ap.add_argument("--barony-set-before", type=Path)
    ap.add_argument("--barony-set-after", type=Path,
                    default=Path("docs/evidence/barony_set.csv"))
    ap.add_argument("--area-tolerance", type=float, default=0.20)
    ap.add_argument("--water-level", type=int, default=4883,
                    help="[map.heightmap] ck3_water_level of the after build")
    ap.add_argument("--ck2-map-dir", type=Path,
                    help="Faerun/Faerun/map, to measure the plain-rescale coast")
    ap.add_argument("--out-dir", type=Path,
                    default=Path("docs/evidence/province_edges"))
    args = ap.parse_args(argv)

    md_a, md_b = args.before / "map_data", args.after / "map_data"
    defs_a, defs_b = read_definition(md_a), read_definition(md_b)
    index: dict[str, int] = {}
    ids_a = read_name_raster(md_a, defs_a, index)
    ids_b = read_name_raster(md_b, defs_b, index)

    out: dict[str, object] = {
        "before": str(args.before),
        "after": str(args.after),
        "keyed_by": "definition.csv column 5 (province name), not the numeric id",
        "definition": compare_definitions(defs_a, defs_b),
        "adjacency_graph": province_edges.adjacency_delta(ids_a, ids_b),
        "adjacencies_csv_before": compare_adjacency_file(
            read_adjacencies(md_a), defs_a, ids_a, index
        ),
        "adjacencies_csv_after": compare_adjacency_file(
            read_adjacencies(md_b), defs_b, ids_b, index
        ),
        "province_area": province_edges.region_area_delta(
            ids_a, ids_b, tolerance=args.area_tolerance
        ),
        "coast_shift_px": coast_shift(
            ids_a, ids_b, water_name_indices(md_b, defs_b, index)
        ),
    }
    water_b = np.fromiter(water_name_indices(md_b, defs_b, index), dtype=np.int32)
    out["heightmap_coast"] = heightmap_coast(
        md_b,
        ~np.isin(ids_b, water_b) & (ids_b > 0),
        args.water_level,
        args.ck2_map_dir,
    )

    args.out_dir.mkdir(parents=True, exist_ok=True)
    if args.barony_set_before and args.barony_set_before.exists():
        summary, rows = compare_baronies(
            read_barony_set(args.barony_set_before),
            read_barony_set(args.barony_set_after),
            args.area_tolerance,
        )
        out["baronies"] = summary
        path = args.out_dir / "barony_area_change.csv"
        with path.open("w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(
                fh,
                fieldnames=["barony", "county", "status_before", "status_after",
                            "pixels_before", "pixels_after", "rel_change"],
                lineterminator="\n",
            )
            w.writeheader()
            w.writerows(rows)
        print(f"wrote {path} ({len(rows)} rows)")

    text = json.dumps(out, indent=2, sort_keys=True)
    (args.out_dir / "topology_delta.json").write_text(text + "\n", encoding="utf-8")
    print(text)
    print(f"wrote {args.out_dir / 'topology_delta.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
