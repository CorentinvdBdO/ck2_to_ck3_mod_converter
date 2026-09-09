#!/usr/bin/env python3
"""Generate ``mappings/colormap_tints.csv`` from measured vanilla tints.

Lane `colormap-fix` step 2: CK3 terrain key -> tint RGB, so
``ck2ck3.map.colormap`` can build a colour raster from the same per-pixel
terrain-key grid ``ck2ck3.map.terrain_paint`` already computes, instead of
resampling CK2's own (wrong-content, wrong-saturation) `colormap.dds`
(`docs/step_map_paint.md` §9.6).

Each CK3 terrain key's tint is vanilla's own measured mean colour for that
key's `mappings/terrain_paint.csv` **primary** material
(`docs/evidence/vanilla_colormap_tints.csv`, `scripts/measure_vanilla_colormap_tints.py`)
- reusing the terrain -> material table that already exists rather than
building a second one. `water` is its own row, vanilla's measured sea/lake
province tint (`material_id == -1`), used for every canvas pixel the map step
already classifies as water (``water_mask``) rather than by terrain key.

The output is a **checked-in, human-editable table**, not regenerated at
convert time: re-run this script after either input table changes, and edit
the CSV by hand for a deliberate art call (matching
`mappings/terrain_paint.csv`'s own convention).

Usage::

    uv run scripts/build_colormap_tints_csv.py
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from ck2ck3.map import terrain_paint  # noqa: E402

VANILLA_CSV = REPO / "docs" / "evidence" / "vanilla_colormap_tints.csv"
TERRAIN_PAINT_CSV = REPO / "mappings" / "terrain_paint.csv"
OUT_CSV = REPO / "mappings" / "colormap_tints.csv"

#: fallback when a terrain key's primary material was not in vanilla's own
#: detail_index primary channel at all (no row measured) - vanilla's overall
#: land mean across every measured material, itself near-neutral.
FALLBACK_NOTE = "no vanilla sample for this material; used the overall land mean"


def read_vanilla_tints(path: Path) -> dict[str, dict]:
    with path.open("r", encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    return {r["material_name"]: r for r in rows}


def main() -> int:
    vanilla = read_vanilla_tints(VANILLA_CSV)
    material_map = terrain_paint.read_material_map(TERRAIN_PAINT_CSV)

    # overall land mean, weighted by sample count, excluding the water row
    land_rows = [r for r in vanilla.values() if r["material_name"] != "water (sea_zones + lakes provinces)"]
    total_n = sum(int(r["sample_count"]) for r in land_rows)
    overall = tuple(
        round(sum(int(r["sample_count"]) * float(r[f"mean_{c}"]) for r in land_rows) / total_n)
        for c in "rgb"
    )

    out_rows = []
    for ck3_key, (primary, _secondary) in sorted(material_map.items()):
        if ck3_key in ("sea", "coastal_sea"):
            continue  # water is its own row below, keyed by water_mask not terrain
        row = vanilla.get(primary)
        if row is None:
            tint = overall
            note = f"primary material '{primary}' {FALLBACK_NOTE}"
            n = 0
        else:
            tint = (round(float(row["mean_r"])), round(float(row["mean_g"])), round(float(row["mean_b"])))
            note = f"vanilla's own mean colormap tint where it paints '{primary}' (material id {row['material_id']})"
            n = int(row["sample_count"])
        out_rows.append(
            {
                "ck3_terrain": ck3_key,
                "tint_r": tint[0],
                "tint_g": tint[1],
                "tint_b": tint[2],
                "sample_count": n,
                "note": note,
            }
        )

    water = vanilla["water (sea_zones + lakes provinces)"]
    out_rows.append(
        {
            "ck3_terrain": "water",
            "tint_r": round(float(water["mean_r"])),
            "tint_g": round(float(water["mean_g"])),
            "tint_b": round(float(water["mean_b"])),
            "sample_count": int(water["sample_count"]),
            "note": "vanilla's own measured sea_zones+lakes colormap tint; applied wherever the map step's own water_mask is true, not by terrain key",
        }
    )

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["ck3_terrain", "tint_r", "tint_g", "tint_b", "sample_count", "note"])
        w.writeheader()
        w.writerows(out_rows)
    print(f"wrote {OUT_CSV} ({len(out_rows)} rows)")
    for r in out_rows:
        print(f"  {r['ck3_terrain']:16s} ({r['tint_r']:>3},{r['tint_g']:>3},{r['tint_b']:>3})  n={r['sample_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
