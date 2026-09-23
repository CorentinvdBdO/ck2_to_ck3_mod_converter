#!/usr/bin/env python3
"""Lane `thay-relief`: turn `docs/evidence/lake_to_land_candidates.csv`
(`scripts/measure_high_lakes.py`) into the human override file plus a
proposals list for everywhere else.

* `overrides/lake_to_land.csv` -- pre-filled with the Thay-window lakes only
  (the ones this lane's renders show as shafts), action `marsh`. This file
  is meant to be **hand-edited** from here; re-running this script does not
  overwrite an existing row (matched by `ck2_id`), only adds new Thay rows
  that are missing.
* `docs/evidence/lake_to_land_proposed.csv` -- every other candidate
  (`region != thay`) at or above the measured threshold, a *proposal*
  (suggested action `marsh`) the human has not accepted yet, not read by the
  converter.

Usage:
  uv run python scripts/propose_lake_to_land_csv.py
      [--candidates docs/evidence/lake_to_land_candidates.csv]
      [--overrides overrides/lake_to_land.csv]
      [--proposed docs/evidence/lake_to_land_proposed.csv]
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

OVERRIDES_HEADER = """\
# overrides/lake_to_land.csv -- human input, hand-edited from here.
#
# A CK2 lake province drawn on high ground: CK3's single global water level
# turns it into a hole down to the pin, and CK2 itself draws a lake's own
# topology.bmp pixels near sea level regardless of the plateau under it, so
# the shore's own elevation carries the only real signal
# (`scripts/measure_high_lakes.py`, `docs/step_map_heightmap.md` \xa72h iii).
#
# Columns:
#   ck2_id  - the CK2 province numeric id (docs/evidence/province_id_map.csv
#             has the CK2<->CK3 mapping; lake_to_land_candidates.csv has the
#             measurement every row here was proposed from)
#   action  - marsh (CK3 terrain forced to `wetlands`, both gameplay and
#             paint) or land (terrain code becomes the mode of the
#             surrounding land's own paint codes)
#   reason  - why, free text
#
# Pre-filled with the Thay-window lakes this lane's renders show as vertical
# shafts (`docs/evidence/thay_relief/`). Every other measured candidate,
# whole canvas, is a *proposal* in docs/evidence/lake_to_land_proposed.csv --
# add a row here yourself to accept one.
ck2_id,action,reason
"""

PROPOSED_HEADER_EXTRA = "suggested_action"


def read_candidates(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def read_existing_override_ids(path: Path) -> set[int]:
    if not path.exists():
        return set()
    text = path.read_text(encoding="utf-8-sig")
    lines = [ln for ln in text.splitlines() if not ln.lstrip().startswith("#")]
    ids = set()
    for row in csv.DictReader(lines):
        raw = (row.get("ck2_id") or "").strip()
        if raw.isdigit():
            ids.add(int(raw))
    return ids


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidates", default=str(ROOT / "docs/evidence/lake_to_land_candidates.csv"))
    ap.add_argument("--overrides", default=str(ROOT / "overrides/lake_to_land.csv"))
    ap.add_argument("--proposed", default=str(ROOT / "docs/evidence/lake_to_land_proposed.csv"))
    args = ap.parse_args()

    rows = read_candidates(Path(args.candidates))
    thay_rows = [r for r in rows if r["region"] == "thay"]
    other_rows = [r for r in rows if r["region"] != "thay"]

    overrides_path = Path(args.overrides)
    existing = read_existing_override_ids(overrides_path)
    new_thay = [r for r in thay_rows if int(r["ck2_id"]) not in existing]

    overrides_path.parent.mkdir(parents=True, exist_ok=True)
    if not overrides_path.exists():
        overrides_path.write_text(OVERRIDES_HEADER, encoding="utf-8")
        added_header = True
    else:
        added_header = False
    if new_thay:
        with overrides_path.open("a", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            for r in new_thay:
                reason = (
                    f"{r['name']}: measured {r['risers_above_water']} risers "
                    f"above the water level ({r['shore_median_level']} vs 4883), "
                    "renders as a shaft in docs/evidence/thay_relief/"
                )
                w.writerow([r["ck2_id"], "marsh", reason])
    print(
        f"{overrides_path}: {'created, ' if added_header else ''}"
        f"{len(new_thay)} new Thay row(s) added "
        f"({len(thay_rows) - len(new_thay)} already present)"
    )

    proposed_path = Path(args.proposed)
    proposed_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(other_rows[0].keys()) + [PROPOSED_HEADER_EXTRA] if other_rows else [
        "ck2_id", "name", "pixel_count", "ring_px", "ring_land_pixel_count",
        "shore_median_level", "risers_above_water", "canvas_centroid_y",
        "canvas_centroid_x", "region", PROPOSED_HEADER_EXTRA,
    ]
    with proposed_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        for r in other_rows:
            row = dict(r)
            row[PROPOSED_HEADER_EXTRA] = "marsh"
            w.writerow(row)
    print(f"{proposed_path}: {len(other_rows)} proposed row(s), not read by the converter")


if __name__ == "__main__":
    main()
