#!/usr/bin/env python3
"""Propose the `tertiary_material` column of `mappings/terrain_paint.csv`.

Lane `paint-edges`, part A.  The soft-edge blend gives every pixel up to four
material channels; three of them belong to the pixel's own terrain class and
one to its strongest neighbour (`docs/step_map_paint.md` §10.1).  A class
therefore needs a *third* material, and inventing one is not allowed.

Why this script exists rather than taking vanilla's ranking straight.
`scripts/measure_vanilla_paint_blend.py` ranks, per CK3 terrain key, the
materials vanilla itself paints on that key's own interior pixels.  That
ranking is **contaminated by province granularity**: a vanilla province is
one terrain key over thousands of pixels of real, varied ground, so
vanilla's own "plains" pixels lead with `forest_jungle_01` (18.5 %) and its
"steppe" pixels with `mountain_03` (61.4 %).  `mappings/terrain_paint.csv`
already rejected exactly those two picks by hand, with a note each.

So the rule here is narrower and stated up front:

    the tertiary is the highest-ranked material in vanilla's own
    non-regional interior ranking **for that terrain key** that is in the
    same material *family* as our audited primary, is not vanilla's `debug`
    placeholder, and is not already the primary or secondary.  A key whose
    own ranking contains no same-family candidate falls back to the material
    of that family with the largest **overall** vanilla land coverage.

Two filters, two different jobs.  The **family** filter is what defeats the
province-granularity contamination: it throws away vanilla's "plains =
forest_jungle_01" and "steppe = mountain_03" for the same reason
`mappings/terrain_paint.csv` already threw them away by hand.  The **own
ranking first** rule is what keeps the pick specific to the key (taiga gets
`forestfloor`, which vanilla really does paint under its pines, rather than
whichever forest texture is biggest globally).  Family is
`scripts/report_map_paint_plots.py`'s own `MATERIAL_FAMILIES` — the level at
which a geographic argument can be made at all.  A key with no same-family
material left anywhere keeps two materials, never an invented third.

Usage::

    uv run scripts/propose_paint_tertiary.py [--write]

Prints the proposal table; ``--write`` rewrites `mappings/terrain_paint.csv`
in place with the `tertiary_material` and the three `*_weight` columns.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

RANKED = REPO / "docs/evidence/paint_edges/vanilla_materials_by_terrain.csv"
SHARE = REPO / "docs/evidence/report_map_paint/material_share.csv"
TABLE = REPO / "mappings/terrain_paint.csv"

#: interior mix, calibrated on vanilla's own land-wide blend statistics
#: (`docs/evidence/report_map_paint/paint_blend.csv`: primary weight 0.5247,
#: entropy 1.4916 bits).  (0.55, 0.28, 0.17) has entropy 1.42 bits and a
#: primary of 0.55 before any neighbour weight is mixed in at a boundary,
#: which is what lands the land-wide numbers on vanilla's.
MIX_WEIGHTS = (0.55, 0.28, 0.17)
TWO_MATERIAL_WEIGHTS = (0.66, 0.34)

#: copied from scripts/report_map_paint_plots.py (that module imports
#: matplotlib at import time and is deliberately not a repo dependency).
MATERIAL_FAMILIES = [
    ("farmland", ("farm",)),
    ("snow & ice", ("snow", "ice", "glacier")),
    ("mountain", ("mountain",)),
    ("hills", ("hills",)),
    ("forest & jungle", ("forest", "jungle", "woods")),
    ("wetlands", ("wetlands", "mud", "floodplain", "marsh")),
    ("beach & cliff", ("beach", "coastline")),
    ("desert & drylands", ("desert", "dryland", "oasis")),
    ("steppe", ("steppe",)),
    ("plains & lowlands", ("plains", "lowland", "grass", "soil", "dirt")),
]
_REGIONAL_RE = re.compile(r"^(gen_|medi_|northern_|india_|central_|tropical)")
_SKIP = {"debug"}


def family(name: str) -> str:
    for fam, keys in MATERIAL_FAMILIES:
        if any(k in name for k in keys):
            return fam
    return "other"


_TERTIARY_TAG = " | tertiary (lane paint-edges): "


def _note(row: dict, pick: str, why: str) -> str:
    """Keep the audited note and record why the tertiary was picked.

    The shipped table has unquoted commas inside `note`, so `DictReader`
    spills the tail into the restkey; put it back or the rewrite silently
    truncates every audit note.  Re-running the script replaces its own
    previous tag instead of appending a second one.
    """
    text = ",".join([row.get("note") or ""] + list(row.get(None) or []))
    text = text.split(_TERTIARY_TAG)[0]
    if not pick:
        return text
    return f"{text}{_TERTIARY_TAG}{pick}, {why}"


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as fh:
        lines = [ln for ln in fh if not ln.lstrip().startswith("#")]
    return list(csv.DictReader(lines))


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args(argv[1:])

    if not RANKED.exists():
        print(f"missing {RANKED}; run scripts/measure_vanilla_paint_blend.py first")
        return 1
    ranked: dict[str, list[tuple[str, float]]] = {}
    for row in read_rows(RANKED):
        if row.get("regional") == "1" or not row.get("rank_nonregional"):
            continue
        key = row["ck3_terrain"]
        ranked.setdefault(key, []).append(
            (row["material"], float(row["share_nonregional_renormalised"] or 0.0))
        )
    for key in ranked:
        ranked[key].sort(key=lambda t: -t[1])

    coverage: dict[str, float] = {}
    if SHARE.exists():
        for row in read_rows(SHARE):
            coverage[row["material"]] = float(row.get("vanilla_coverage_pct") or 0.0)

    table = read_rows(TABLE)
    out_rows = []
    print(f"{'terrain':<18}{'primary':<22}{'secondary':<24}{'tertiary':<24}why")
    for row in table:
        key = row["ck3_terrain"]
        prim = row["primary_material"]
        sec = row["secondary_material"]
        fam = family(prim)
        own_rank = {m: s for m, s in ranked.get(key, [])}
        cands = [
            (coverage.get(m, 0.0), own_rank.get(m, 0.0), m)
            for m in coverage
            if family(m) == fam
            and m not in _SKIP
            and not _REGIONAL_RE.match(m)
            and m not in (prim, sec)
        ]
        pick = ""
        why = ""
        for mat, share in ranked.get(key, []):
            if mat in _SKIP or _REGIONAL_RE.match(mat) or mat in (prim, sec):
                continue
            if family(mat) != fam:
                continue
            pick = mat
            why = f"{share:.1f} % of this key's own {fam} interior in vanilla"
            break
        if not pick and cands:
            cov, _own, pick = max(cands)
            why = (
                f"not in this key's own ranking; largest {fam} material in "
                f"vanilla overall ({cov:.2f} % of vanilla land)"
            )
        if not pick:
            why = f"no same-family ({fam}) material left; stays 2"
        print(f"{key:<18}{prim:<22}{sec:<24}{pick or '-':<24}{why}")
        weights = MIX_WEIGHTS if pick else TWO_MATERIAL_WEIGHTS
        out_rows.append(
            {
                "ck3_terrain": key,
                "primary_material": prim,
                "secondary_material": sec,
                "tertiary_material": pick,
                "primary_weight": f"{weights[0]}",
                "secondary_weight": f"{weights[1]}",
                "tertiary_weight": f"{weights[2]}" if pick else "",
                # the shipped table has unquoted commas inside `note`, so
                # DictReader spills the tail into the restkey; put it back or
                # the rewrite silently truncates every audit note.
                "note": _note(row, pick, why),
            }
        )

    if args.write:
        fields = [
            "ck3_terrain",
            "primary_material",
            "secondary_material",
            "tertiary_material",
            "primary_weight",
            "secondary_weight",
            "tertiary_weight",
            "note",
        ]
        with TABLE.open("w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=fields)
            w.writeheader()
            w.writerows(out_rows)
        print(f"\nwrote {TABLE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
