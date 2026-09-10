#!/usr/bin/env python3
"""Build 8 vs build 12: every number `docs/report_map_paint.md` quotes.

Run: uv run --with matplotlib python scripts/report_map_paint_diff.py
(numpy only, but `--with matplotlib` is the same invocation the figures use)

Reads the two measurement sets side by side --
`docs/evidence/report_map_paint/` (build 12, the live mod) against
`docs/evidence/report_map_paint/build8/` (the first edition, `_out/seafloor`)
-- and prints the tables the report's Revision note and §1/§6/§7 quote, so no
number in the prose is typed from memory.
"""
from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
NEW = ROOT / "docs/evidence/report_map_paint"
OLD = NEW / "build8"
#: the frequencies §1 and §6 talk about, cycles per km
SPECTRUM_KM = (0.05, 0.08, 0.1, 0.15, 0.2, 0.3)


def rows(path: Path) -> list[dict]:
    with path.open() as f:
        return [r for r in csv.DictReader(f)
                if not next(iter(r.values())).lstrip().startswith("#")]


def spectrum(path: Path) -> dict[str, np.ndarray]:
    out: dict[str, list] = {}
    for r in rows(path):
        out.setdefault(r["map"], []).append(
            (float(r["cycles_per_km"]), float(r["amplitude_levels"])))
    return {k: np.array(sorted(v)) for k, v in out.items()}


def at(s: np.ndarray, k: float) -> float:
    return float(np.interp(k, s[:, 0], s[:, 1]))


def head(t: str) -> None:
    print(f"\n=== {t}")


def main() -> None:
    n, o = spectrum(NEW / "spectrum.csv"), spectrum(OLD / "spectrum.csv")
    head("radial spectrum, all-land interior patches (amplitude levels)")
    print(f"{'c/km':>6} {'vanilla':>9} {'plain':>9} {'build8':>9} {'build12':>9}"
          f" {'b8/van':>7} {'b12/van':>8}")
    for k in SPECTRUM_KM:
        v = at(n["ck3_vanilla"], k)
        print(f"{k:>6} {v:9.1f} {at(n['ours_before_detail'], k):9.1f}"
              f" {at(o['ours_now'], k):9.1f} {at(n['ours_now'], k):9.1f}"
              f" {at(o['ours_now'], k) / v:7.2f} {at(n['ours_now'], k) / v:8.2f}")

    for name, key in (("land_stats.csv", "stage"), ("clamp_floor.csv", None),
                      ("paint_blend.csv", "map")):
        head(f"{name}: build 8 → build 12")
        a = {(r[key] if key else "-"): r for r in rows(OLD / name)}
        b = {(r[key] if key else "-"): r for r in rows(NEW / name)}
        for k in b:
            for f in b[k]:
                if f == key:
                    continue
                va, vb = a.get(k, {}).get(f, "?"), b[k][f]
                flag = "" if va == vb else "   <-- moved"
                print(f"  {k:<20} {f:<28} {va:>12} → {vb:>12}{flag}")

    head("thay_bands.csv: band-passed RMS over Thay's land, ratio to vanilla")
    a = {r["band_km_lo"]: r for r in rows(OLD / "thay_bands.csv")}
    print(f"{'band km':>14} {'vanilla':>9} {'build8':>9} {'build12':>9}"
          f" {'b8/van':>7} {'b12/van':>8}")
    for r in rows(NEW / "thay_bands.csv"):
        v = float(r["rms_vanilla_norway"])
        ob = float(a[r["band_km_lo"]]["rms_shipped"])
        nb = float(r["rms_shipped"])
        print(f"{float(r['band_km_lo']):6.1f}–{float(r['band_km_hi']):<7.1f}"
              f" {v:9.1f} {ob:9.1f} {nb:9.1f} {ob / v:7.2f} {nb / v:8.2f}")

    head("thay_cliffs.csv: signed drop kept after pass 1 alone (%)")
    a = {(r["cliff_threshold_risers"], r["lag_px"]): r
         for r in rows(OLD / "thay_cliffs.csv")}
    print(f"{'thr':>4} {'baseline km':>12} {'build8 Gaussian':>16}"
          f" {'build12 PM':>11}")
    for r in rows(NEW / "thay_cliffs.csv"):
        k = (r["cliff_threshold_risers"], r["lag_px"])
        print(f"{r['cliff_threshold_risers']:>4} {float(r['baseline_km']):12.2f}"
              f" {float(a[k]['kept_deterrace_pct']):16.1f}"
              f" {float(r['kept_deterrace_pct']):11.1f}")

    head("thay_steps.csv: share of land-to-land pixel edges (%)")
    a = {(r["stage"], r["class"]): r for r in rows(OLD / "thay_steps.csv")}
    for r in rows(NEW / "thay_steps.csv"):
        k = (r["stage"], r["class"])
        print(f"  {r['stage']:<20} {r['class']:<24}"
              f" {float(a[k]['pct']):7.2f} → {float(r['pct']):7.2f}")
    for st in ("after_deterrace", "shipped"):
        ra = next(r for r in rows(OLD / "thay_steps.csv") if r["stage"] == st)
        rb = next(r for r in rows(NEW / "thay_steps.csv") if r["stage"] == st)
        print(f"  {st:<20} {'max_risers':<24}"
              f" {float(ra['max_risers']):7.2f} → {float(rb['max_risers']):7.2f}")

    head("hf_achieved.csv: per-terrain high-frequency RMS (interior land)")
    a = {r["terrain"]: r for r in rows(OLD / "hf_achieved.csv")}
    print(f"{'terrain':<12} {'target':>8} {'b8 (transcribed)':>18}"
          f" {'b12 (measured)':>16} {'b12/target':>11}")
    for r in rows(NEW / "hf_achieved.csv"):
        t = float(r["target"])
        ob = a.get(r["terrain"], {}).get("achieved_interior", "")
        print(f"{r['terrain']:<12} {t:8.1f} {ob:>18}"
              f" {float(r['achieved_interior']):16.1f}"
              f" {float(r['achieved_interior']) / t:11.2f}")

    for name, keyf, valf in (
            ("terrain_area_share.csv", "ck3_terrain", "px"),
            ("tree_counts.csv", "file", "ours")):
        head(f"{name}: build 8 → build 12 (top by build-12 value)")
        def tally(p: Path) -> dict[str, float]:
            d: dict[str, float] = {}
            for r in rows(p):
                if name.startswith("terrain") and r["where"] != "land":
                    continue
                d[r[keyf]] = d.get(r[keyf], 0.0) + float(r[valf])
            return d
        ta, tb = tally(OLD / name), tally(NEW / name)
        sa, sb = sum(ta.values()) or 1.0, sum(tb.values()) or 1.0
        for k in sorted(tb, key=lambda k: -tb[k])[:20]:
            print(f"  {k:<34} {100 * ta.get(k, 0) / sa:7.2f} %"
                  f" → {100 * tb[k] / sb:7.2f} %"
                  f"   ({ta.get(k, 0):>10,.0f} → {tb[k]:>10,.0f})")
        print(f"  {'TOTAL':<34} {sa:>12,.0f} → {sb:>12,.0f}")

    head("material_share.csv: intensity-weighted land coverage by family")
    def fams(p: Path) -> tuple[dict[str, float], dict[str, float]]:
        fo: dict[str, float] = {}
        fv: dict[str, float] = {}
        for r in rows(p):
            fo[r["family"]] = fo.get(r["family"], 0) + float(r["ours_coverage_pct"])
            fv[r["family"]] = fv.get(r["family"], 0) + float(r["vanilla_coverage_pct"])
        return fo, fv
    oa, _ = fams(OLD / "material_share.csv")
    ob2, vb2 = fams(NEW / "material_share.csv")
    print(f"{'family':<22} {'b8 ours':>9} {'b12 ours':>9} {'vanilla':>9} {'diff pp':>9}")
    for f in sorted(vb2, key=lambda f: -vb2[f]):
        print(f"{f:<22} {oa.get(f, 0):9.2f} {ob2.get(f, 0):9.2f}"
              f" {vb2[f]:9.2f} {ob2.get(f, 0) - vb2[f]:+9.2f}")


if __name__ == "__main__":
    main()
