#!/usr/bin/env python
"""Measure km-per-pixel of the vanilla CK3 1.19 map.

Method (read-only against the CK3 game dir):
  1. For a hand-picked set of baronies whose real-world city is unambiguous,
     read `province = <id>` out of common/landed_titles/00_landed_titles.txt.
  2. Look the province id up in map_data/definition.csv to get its RGB.
  3. Compute the pixel centroid of that colour in map_data/provinces.png.
     map_data/default.map has `positions = "positions.txt"` COMMENTED OUT in
     vanilla, so the provinces bitmap is the authoritative source of geometry.
  4. Compare great-circle distances between city pairs with pixel distances,
     split into mostly-east-west and mostly-north-south pairs, and fit
     degrees-per-pixel by least squares over all cities.

Run:  uv run python scripts/measure_vanilla_scale.py
Writes docs/evidence/vanilla_scale.csv (+ a centroid cache npz next to it).
"""

from __future__ import annotations

import csv
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None  # provinces.png is 9216x4608 = 42 Mpx

REPO = Path(__file__).resolve().parents[1]
GAME = Path(
    "/home/cvdbdo/.local/share/Steam/steamapps/common/Crusader Kings III/game"
)
LANDED_TITLES = GAME / "common" / "landed_titles" / "00_landed_titles.txt"
DEFINITION = GAME / "map_data" / "definition.csv"
PROVINCES = GAME / "map_data" / "provinces.png"

OUT_DIR = REPO / "docs" / "evidence"
OUT_CSV = OUT_DIR / "vanilla_scale.csv"
CACHE = OUT_DIR / "vanilla_scale_centroids.npz"

R_EARTH_KM = 6371.0
KM_PER_DEG_LAT = 111.19  # mean meridian degree, R=6371 -> pi*R/180

# barony key -> (real-world city, lat, lon).
# Coordinates are well-known city-centre values (assumed, from public
# gazetteer knowledge); they are the only non-measured input here.
CITIES: dict[str, tuple[str, float, float]] = {
    "b_reykjavik":      ("Reykjavik",              64.1466, -21.9426),
    "b_dublin":         ("Dublin",                 53.3498,  -6.2603),
    "b_uppsala":        ("Uppsala",                59.8586,  17.6389),
    "b_novgorod":       ("Veliky Novgorod",        58.5213,  31.2710),
    "b_london":         ("London",                 51.5072,  -0.1276),
    "b_moskva":         ("Moscow",                 55.7558,  37.6173),
    "b_kiev":           ("Kyiv",                   50.4501,  30.5234),
    "b_praha":          ("Prague",                 50.0755,  14.4378),
    "b_paris":          ("Paris",                  48.8566,   2.3522),
    "b_venezia":        ("Venice",                 45.4408,  12.3155),
    "b_roma":           ("Rome",                   41.9028,  12.4964),
    "b_constantinople": ("Istanbul",               41.0082,  28.9784),
    "b_toledo":         ("Toledo",                 39.8628,  -4.0273),
    "b_lisboa":         ("Lisbon",                 38.7223,  -9.1393),
    "b_athens":         ("Athens",                 37.9838,  23.7275),
    "b_tunis":          ("Tunis",                  36.8065,  10.1815),
    "b_antiocheia":     ("Antakya (Antioch)",      36.2023,  36.1613),
    "b_samarkand":      ("Samarkand",              39.6270,  66.9750),
    "b_baghdad":        ("Baghdad",                33.3152,  44.3661),
    "b_isfahan":        ("Isfahan",                32.6539,  51.6660),
    "b_jerusalem":      ("Jerusalem",              31.7683,  35.2137),
    "b_marrakesh":      ("Marrakesh",              31.6295,  -7.9811),
    "b_cairo":          ("Cairo",                  30.0444,  31.2357),
    "b_aden":           ("Aden",                   12.7855,  45.0187),
    "b_mogadishu":      ("Mogadishu",               2.0469,  45.3182),
}


def barony_province_ids(keys: list[str]) -> dict[str, int]:
    """province = <id> is the first such line inside each `b_x = { ... }` block."""
    text = LANDED_TITLES.read_text(encoding="utf-8-sig", errors="replace")
    lines = text.splitlines()
    want = set(keys)
    out: dict[str, int] = {}
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped.endswith("= {"):
            continue
        key = stripped.split("=")[0].strip()
        if key not in want or key in out:
            continue
        for probe in lines[i + 1 : i + 12]:
            probe = probe.strip()
            if probe.startswith("province"):
                out[key] = int(probe.split("=")[1].split("#")[0].strip())
                break
    missing = want - out.keys()
    if missing:
        sys.exit(f"barony keys not found or without province: {sorted(missing)}")
    return out


def province_rgb(ids: set[int]) -> dict[int, tuple[int, int, int]]:
    out: dict[int, tuple[int, int, int]] = {}
    with DEFINITION.open(encoding="utf-8-sig", errors="replace") as fh:
        for row in fh:
            parts = row.split(";")
            if len(parts) < 4 or not parts[0].strip().isdigit():
                continue
            pid = int(parts[0])
            if pid in ids:
                out[pid] = (int(parts[1]), int(parts[2]), int(parts[3]))
    missing = ids - out.keys()
    if missing:
        sys.exit(f"province ids absent from definition.csv: {sorted(missing)}")
    return out


def centroids(
    rgbs: dict[int, tuple[int, int, int]],
) -> tuple[dict[int, tuple[float, float, int]], tuple[int, int]]:
    """Pixel centroid + pixel count per province colour. Cached (42 Mpx scan)."""
    signature = ",".join(f"{p}:{r}-{g}-{b}" for p, (r, g, b) in sorted(rgbs.items()))
    if CACHE.exists():
        z = np.load(CACHE, allow_pickle=False)
        if str(z["signature"]) == signature:
            data = z["data"]
            size = (int(z["width"]), int(z["height"]))
            print(f"centroid cache hit: {CACHE}")
            return {int(r[0]): (float(r[1]), float(r[2]), int(r[3])) for r in data}, size

    print(f"scanning {PROVINCES} ...")
    with Image.open(PROVINCES) as im:
        size = im.size
        arr = np.asarray(im.convert("RGB"), dtype=np.uint8)
    height, width = arr.shape[:2]
    packed = (
        arr[:, :, 0].astype(np.int32) << 16
        | arr[:, :, 1].astype(np.int32) << 8
        | arr[:, :, 2].astype(np.int32)
    )

    rows = []
    for pid, (r, g, b) in sorted(rgbs.items()):
        ys, xs = np.nonzero(packed == (r << 16 | g << 8 | b))
        if xs.size == 0:
            sys.exit(f"province {pid} colour {(r, g, b)} not present in provinces.png")
        rows.append((pid, float(xs.mean()), float(ys.mean()), int(xs.size)))

    data = np.array(rows, dtype=np.float64)
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        CACHE, data=data, signature=signature, width=width, height=height
    )
    return {int(r[0]): (r[1], r[2], int(r[3])) for r in rows}, size


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R_EARTH_KM * math.asin(math.sqrt(a))


def linfit(x: np.ndarray, y: np.ndarray) -> tuple[float, float, float]:
    """slope, intercept, R^2 for y = slope*x + intercept."""
    slope, intercept = np.polyfit(x, y, 1)
    pred = slope * x + intercept
    ss_res = float(((y - pred) ** 2).sum())
    ss_tot = float(((y - y.mean()) ** 2).sum())
    return float(slope), float(intercept), 1.0 - ss_res / ss_tot


# Pairs chosen so both axes are covered at several latitudes.
PAIRS = [
    ("b_lisboa", "b_samarkand"),
    ("b_london", "b_moskva"),
    ("b_toledo", "b_constantinople"),
    ("b_cairo", "b_baghdad"),
    ("b_tunis", "b_antiocheia"),
    ("b_dublin", "b_kiev"),
    ("b_marrakesh", "b_jerusalem"),
    ("b_paris", "b_venezia"),
    ("b_uppsala", "b_roma"),
    ("b_novgorod", "b_jerusalem"),
    ("b_london", "b_marrakesh"),
    ("b_praha", "b_tunis"),
    ("b_moskva", "b_baghdad"),
    ("b_dublin", "b_lisboa"),
    ("b_isfahan", "b_aden"),
    ("b_aden", "b_mogadishu"),
    ("b_reykjavik", "b_roma"),
    ("b_athens", "b_cairo"),
]


# The vanilla map is deliberately NOT a uniform projection: Europe is enlarged
# and Arabia / the Horn of Africa are compressed. This subset is the linear
# "core" (western Eurasia + Mediterranean) where a single scale actually holds.
CORE_EUROPE = (
    "b_dublin b_uppsala b_novgorod b_london b_moskva b_kiev b_praha b_paris "
    "b_venezia b_roma b_constantinople b_toledo b_lisboa b_athens b_tunis "
    "b_antiocheia"
).split()


def main() -> None:
    keys = list(CITIES)
    pids = barony_province_ids(keys)
    rgbs = province_rgb(set(pids.values()))
    cents, (width, height) = centroids(rgbs)

    print(f"provinces.png = {width}x{height}")

    city_rows = []
    for key in keys:
        name, lat, lon = CITIES[key]
        pid = pids[key]
        r, g, b = rgbs[pid]
        cx, cy, px = cents[pid]
        city_rows.append(
            dict(
                key=key, city=name, province_id=pid, r=r, g=g, b=b,
                cx=round(cx, 2), cy=round(cy, 2), lat=lat, lon=lon, pixels=px,
            )
        )

    print("\n== cities ==")
    print(f"{'barony':<18}{'prov':>6}{'cx':>10}{'cy':>10}{'lat':>9}{'lon':>9}{'px':>8}")
    for c in city_rows:
        print(
            f"{c['key']:<18}{c['province_id']:>6}{c['cx']:>10.1f}{c['cy']:>10.1f}"
            f"{c['lat']:>9.3f}{c['lon']:>9.3f}{c['pixels']:>8}"
        )

    by_key = {c["key"]: c for c in city_rows}

    # ---- least-squares degrees per pixel -------------------------------------
    xs = np.array([c["cx"] for c in city_rows])
    ys = np.array([c["cy"] for c in city_rows])
    lons = np.array([c["lon"] for c in city_rows])
    lats = np.array([c["lat"] for c in city_rows])
    lon_slope, lon_int, lon_r2 = linfit(xs, lons)
    lat_slope, lat_int, lat_r2 = linfit(ys, lats)

    print("\n== least-squares fit over all cities ==")
    print(f"lon = {lon_slope:.8f} * x + {lon_int:.4f}   R^2 = {lon_r2:.6f}")
    print(f"lat = {lat_slope:.8f} * y + {lat_int:.4f}   R^2 = {lat_r2:.6f}")
    print(f"deg/px lon = {lon_slope:.6f}  ({1/lon_slope:.2f} px per deg lon)")
    print(f"deg/px lat = {-lat_slope:.6f}  ({-1/lat_slope:.2f} px per deg lat)")
    print(f"implied full-globe width  = {360/lon_slope:,.0f} px")
    print(f"implied full-globe height = {180/-lat_slope:,.0f} px")
    fit_km_px_y = -lat_slope * KM_PER_DEG_LAT
    print(f"km/px from lat fit = {fit_km_px_y:.5f}")

    # ---- residuals: is the projection linear? --------------------------------
    lon_res = lons - (lon_slope * xs + lon_int)
    lat_res = lats - (lat_slope * ys + lat_int)
    print("\n== residuals of the global fit (deg, and px of map error) ==")
    print(f"{'barony':<18}{'d_lon':>9}{'px':>8}{'d_lat':>9}{'px':>8}")
    order = np.argsort(lat_res)
    for j in order:
        print(
            f"{city_rows[j]['key']:<18}{lon_res[j]:>9.2f}"
            f"{lon_res[j] / lon_slope:>8.0f}{lat_res[j]:>9.2f}"
            f"{lat_res[j] / lat_slope:>8.0f}"
        )
    print(
        f"lat residual spread = {lat_res.max() - lat_res.min():.2f} deg "
        f"({abs((lat_res.max() - lat_res.min()) / lat_slope):.0f} px) -- "
        "a single global scale cannot be exact"
    )

    # ---- core-Europe subset (where the projection is close to linear) --------
    sel = [j for j, c in enumerate(city_rows) if c["key"] in CORE_EUROPE]
    eu_lon_slope, _, eu_lon_r2 = linfit(xs[sel], lons[sel])
    eu_lat_slope, _, eu_lat_r2 = linfit(ys[sel], lats[sel])
    eu_km_px_y = -eu_lat_slope * KM_PER_DEG_LAT
    print(f"\n== core-Europe subset (n={len(sel)}) ==")
    print(f"deg/px lon = {eu_lon_slope:.6f}   R^2 = {eu_lon_r2:.6f}")
    print(f"deg/px lat = {-eu_lat_slope:.6f}   R^2 = {eu_lat_r2:.6f}")
    print(f"km/px from core lat fit = {eu_km_px_y:.5f}")

    # ---- pair measurements ----------------------------------------------------
    pair_rows = []
    for a, b in PAIRS:
        ca, cb = by_key[a], by_key[b]
        dx = cb["cx"] - ca["cx"]
        dy = cb["cy"] - ca["cy"]
        px_dist = math.hypot(dx, dy)
        gc = haversine_km(ca["lat"], ca["lon"], cb["lat"], cb["lon"])
        mean_lat = math.radians((ca["lat"] + cb["lat"]) / 2)
        ew_km = abs(cb["lon"] - ca["lon"]) * KM_PER_DEG_LAT * math.cos(mean_lat)
        ns_km = abs(cb["lat"] - ca["lat"]) * KM_PER_DEG_LAT
        axis = "EW" if ew_km >= ns_km else "NS"
        pair_rows.append(
            dict(
                a=a, b=b, axis=axis,
                gc_km=round(gc, 2), px_dist=round(px_dist, 2),
                km_per_px=round(gc / px_dist, 5),
                dx=round(dx, 2), dy=round(dy, 2),
                ew_km=round(ew_km, 2), ns_km=round(ns_km, 2),
                km_per_px_axis=round((ew_km / abs(dx)) if axis == "EW"
                                     else (ns_km / abs(dy)), 5),
            )
        )

    print("\n== pairs ==")
    hdr = f"{'a':<16}{'b':<16}{'ax':>4}{'gc_km':>10}{'px':>9}{'km/px':>9}{'km/px axis':>12}"
    print(hdr)
    for p in pair_rows:
        print(
            f"{p['a']:<16}{p['b']:<16}{p['axis']:>4}{p['gc_km']:>10.1f}"
            f"{p['px_dist']:>9.1f}{p['km_per_px']:>9.4f}{p['km_per_px_axis']:>12.4f}"
        )

    allv = np.array([p["km_per_px"] for p in pair_rows])
    ew = np.array([p["km_per_px_axis"] for p in pair_rows if p["axis"] == "EW"])
    ns = np.array([p["km_per_px_axis"] for p in pair_rows if p["axis"] == "NS"])
    km_per_px_x = float(ew.mean())
    km_per_px_y = float(ns.mean())

    print("\n== summary ==")
    print(
        f"combined km/px : n={allv.size} min={allv.min():.4f} "
        f"median={np.median(allv):.4f} max={allv.max():.4f} mean={allv.mean():.4f} "
        f"sd={allv.std(ddof=1):.4f}"
    )
    print(
        f"km_per_px_x (EW pairs, n={ew.size}) = {km_per_px_x:.5f} "
        f"(sd {ew.std(ddof=1):.5f}, min {ew.min():.4f}, max {ew.max():.4f})"
    )
    print(
        f"km_per_px_y (NS pairs, n={ns.size}) = {km_per_px_y:.5f} "
        f"(sd {ns.std(ddof=1):.5f}, min {ns.min():.4f}, max {ns.max():.4f})"
    )
    print(f"anisotropy x/y = {km_per_px_x / km_per_px_y:.4f}")
    print(f"\nRECOMMENDED vanilla_km_per_px = {eu_km_px_y:.4f}")
    print(
        "  = core-Europe latitude fit slope x 111.19 km/deg (R^2 "
        f"{eu_lat_r2:.4f})."
    )
    print(f"  whole-map latitude fit gives {fit_km_px_y:.4f} km/px (R^2 "
          f"{lat_r2:.4f}) -- use that for a globe-spanning map.")
    print(
        "Rationale: y is monotonic in latitude and free of the cos(lat)\n"
        "  shrinkage that makes x scale-dependent, so the lat fit is the least\n"
        "  noisy estimator. The subset matters because vanilla is not one\n"
        "  projection: Europe is enlarged and Arabia/Horn of Africa compressed,\n"
        "  so no single scalar fits the whole sheet (see residuals above)."
    )

    # ---- CSV -----------------------------------------------------------------
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["# vanilla CK3 1.19 map scale measurement"])
        w.writerow([f"# provinces.png {width}x{height}; R={R_EARTH_KM} km;"
                    f" {KM_PER_DEG_LAT} km/deg lat"])
        w.writerow(["# lat/lon are well-known real-world city centres (assumed);"
                    " cx/cy are measured province-colour centroids"])
        w.writerow([])
        w.writerow(["section", "key", "city", "province_id", "r", "g", "b",
                    "cx", "cy", "lat", "lon", "pixels"])
        for c in city_rows:
            w.writerow(["city", c["key"], c["city"], c["province_id"], c["r"],
                        c["g"], c["b"], c["cx"], c["cy"], c["lat"], c["lon"],
                        c["pixels"]])
        w.writerow([])
        w.writerow(["section", "a", "b", "axis", "gc_km", "px_dist", "km_per_px",
                    "dx", "dy", "ew_km", "ns_km", "km_per_px_axis"])
        for p in pair_rows:
            w.writerow(["pair", p["a"], p["b"], p["axis"], p["gc_km"],
                        p["px_dist"], p["km_per_px"], p["dx"], p["dy"],
                        p["ew_km"], p["ns_km"], p["km_per_px_axis"]])
        w.writerow([])
        w.writerow(["section", "metric", "value", "unit", "note"])
        for name, val, unit, note in [
            ("deg_per_px_lon", round(lon_slope, 8), "deg/px",
             f"least squares lon~x, R2={lon_r2:.6f}"),
            ("deg_per_px_lat", round(-lat_slope, 8), "deg/px",
             f"least squares lat~y, R2={lat_r2:.6f}"),
            ("r2_lon", round(lon_r2, 6), "", "goodness of lon~x fit"),
            ("r2_lat", round(lat_r2, 6), "", "goodness of lat~y fit"),
            ("px_per_deg_lon", round(1 / lon_slope, 4), "px/deg", ""),
            ("px_per_deg_lat", round(-1 / lat_slope, 4), "px/deg", ""),
            ("implied_globe_width_px", round(360 / lon_slope, 1), "px",
             "if the projection were extended to 360 deg"),
            ("implied_globe_height_px", round(180 / -lat_slope, 1), "px",
             "if extended to 180 deg"),
            ("km_per_px_x", round(km_per_px_x, 5), "km/px",
             f"mean of {ew.size} EW pairs, along mean parallel"),
            ("km_per_px_y", round(km_per_px_y, 5), "km/px",
             f"mean of {ns.size} NS pairs"),
            ("km_per_px_combined_median", round(float(np.median(allv)), 5),
             "km/px", f"median of {allv.size} great-circle pairs"),
            ("anisotropy_x_over_y", round(km_per_px_x / km_per_px_y, 5), "",
             ">1 means x is stretched relative to y"),
            ("deg_per_px_lon_core_europe", round(eu_lon_slope, 8), "deg/px",
             f"core-Europe subset (n={len(sel)}), R2={eu_lon_r2:.6f}"),
            ("deg_per_px_lat_core_europe", round(-eu_lat_slope, 8), "deg/px",
             f"core-Europe subset (n={len(sel)}), R2={eu_lat_r2:.6f}"),
            ("r2_lat_core_europe", round(eu_lat_r2, 6), "", ""),
            ("km_per_px_lat_fit_global", round(fit_km_px_y, 4), "km/px",
             f"all {len(city_rows)} cities, R2={lat_r2:.4f}"),
            ("lat_residual_spread_px",
             round(abs((lat_res.max() - lat_res.min()) / lat_slope), 1), "px",
             "global fit error range; proof the projection is non-uniform"),
            ("vanilla_km_per_px", round(eu_km_px_y, 4), "km/px",
             "RECOMMENDED: core-Europe lat fit x 111.19 km/deg"),
        ]:
            w.writerow(["metric", name, val, unit, note])

    print(f"\nwrote {OUT_CSV}")
    print(f"cache {CACHE}")


if __name__ == "__main__":
    main()
