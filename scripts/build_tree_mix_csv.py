#!/usr/bin/env python3
"""Turn the vanilla measurement into ``mappings/tree_mix.csv``.

Reads ``docs/evidence/vanilla_tree_mix.csv`` (written by
``scripts/measure_vanilla_tree_mix.py``) and emits the table
``ck2ck3.map.tree_scatter`` samples a tree's mesh from, with the fallback
levels materialised as explicit rows so the sampler never has to re-derive a
marginal at run time:

===== ===================================== ================================
level ``climate`` / ``lat_band`` columns    meaning
===== ===================================== ================================
3     both real                             the full conditional
2     ``lat_band = *``                      marginal over latitude
1     ``climate = *``                       marginal over climate
0     both ``*``                            the terrain's own global mix
===== ===================================== ================================

The sampler tries level 3, then **1**, then 2, then 0, then the terrain's
single row in ``mappings/tree_meshes.csv`` — latitude before climate, because
that is the order vanilla's own data asks for.  This script measures it and
writes ``docs/evidence/vanilla_tree_mix_conditioning.csv``: terrain alone
predicts vanilla's generator 49.8 % of the time (2.056 bits of cross-entropy),
terrain+latitude 58.8 % (1.626 bits), terrain+climate only 50.7 % (2.008
bits).  Vanilla's ``map_data/climate.txt`` names just 635 of its 11,651 land
provinces, so its climate column is mostly ``none`` and carries almost
nothing; ours is far denser, but the table was measured on vanilla, so
vanilla's ordering is the one the table supports.

A level is only emitted when the condition has at least ``--min-count``
vanilla instances behind it, so a species never gets picked for Faerûn off
three instances in a Bavarian valley.

Usage::

    uv run scripts/build_tree_mix_csv.py [--min-count 100]
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEFAULT_IN = REPO / "docs/evidence/vanilla_tree_mix.csv"
DEFAULT_OUT = REPO / "mappings/tree_mix.csv"
WILDCARD = "*"


def _write_conditioning(rows: list[dict[str, str]], out: Path) -> None:
    """How much of vanilla's species choice each conditioning scheme explains.

    Top-1 accuracy (predict each condition's most common generator) and
    cross-entropy in bits, weighted by instances.  This is the evidence for
    the fallback ORDER in ``ck2ck3.map.tree_scatter.resolve_mix``: whichever
    of ``+climate`` / ``+latitude`` explains more goes first.  In-sample, so
    the more granular scheme is flattered — which is why the ``--min-count``
    gate exists — but the two single-variable schemes are compared on equal
    footing.
    """
    schemes = {
        "global": lambda r: ("",),
        "terrain": lambda r: (r["ck3_terrain"],),
        "terrain+climate": lambda r: (r["ck3_terrain"], r["climate"]),
        "terrain+lat_band": lambda r: (r["ck3_terrain"], r["lat_band"]),
        "terrain+climate+lat_band": lambda r: (
            r["ck3_terrain"], r["climate"], r["lat_band"]
        ),
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["scheme", "conditions", "top1_accuracy", "cross_entropy_bits"])
        for name, keyf in schemes.items():
            per: dict[tuple, Counter] = {}
            for r in rows:
                per.setdefault(keyf(r), Counter())[r["file"]] += int(r["count"])
            total = sum(sum(c.values()) for c in per.values())
            hit = sum(max(c.values()) for c in per.values())
            ent = 0.0
            for c in per.values():
                t = sum(c.values())
                for n in c.values():
                    ent -= n * math.log2(n / t)
            w.writerow([name, len(per), round(hit / total, 4),
                        round(ent / total, 4)])
            print(f"  {name:>26}: top-1 {100 * hit / total:5.1f} %, "
                  f"{ent / total:5.3f} bits, {len(per)} conditions")
    print(f"wrote {out}")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--in-csv", type=Path, default=DEFAULT_IN)
    ap.add_argument("--out-csv", type=Path, default=DEFAULT_OUT)
    ap.add_argument(
        "--min-count",
        type=int,
        default=100,
        help="a (terrain, climate, band) level needs this many vanilla "
        "instances before it is trusted over its own marginal",
    )
    ap.add_argument(
        "--min-p",
        type=float,
        default=0.002,
        help="drop a mesh whose share of a condition is below this "
        "(keeps the table readable; the rest is renormalised)",
    )
    ap.add_argument(
        "--conditioning-csv",
        type=Path,
        default=REPO / "docs/evidence/vanilla_tree_mix_conditioning.csv",
        help="where to write the measurement that fixes the fallback order",
    )
    ap.add_argument(
        "--drop-file",
        action="append",
        default=[],
        help="exclude a vanilla generator file from the table entirely "
        "(repeatable); nothing is dropped by default",
    )
    args = ap.parse_args(argv[1:])

    if not args.in_csv.is_file():
        print(
            f"no measurement at {args.in_csv} "
            "(run scripts/measure_vanilla_tree_mix.py first)",
            file=sys.stderr,
        )
        return 1

    with args.in_csv.open("r", encoding="utf-8", newline="") as fh:
        rows = [
            r
            for r in csv.DictReader(
                line for line in fh if not line.lstrip().startswith("#")
            )
            if r["file"] not in args.drop_file
        ]

    _write_conditioning(rows, args.conditioning_csv)

    levels: dict[int, Counter] = {lvl: Counter() for lvl in (3, 2, 1, 0)}
    for r in rows:
        t, c, b, f = r["ck3_terrain"], r["climate"], r["lat_band"], r["file"]
        n = int(r["count"])
        levels[3][(t, c, b, f)] += n
        levels[2][(t, c, WILDCARD, f)] += n
        levels[1][(t, WILDCARD, b, f)] += n
        levels[0][(t, WILDCARD, WILDCARD, f)] += n

    out_rows: list[tuple[str, str, str, str, int, float]] = []
    kept_conditions = 0
    for lvl in (3, 2, 1, 0):
        totals: Counter = Counter()
        for (t, c, b, _f), n in levels[lvl].items():
            totals[(t, c, b)] += n
        for cond, total in sorted(totals.items()):
            if total < args.min_count:
                continue
            files = {
                f: n
                for (t, c, b, f), n in levels[lvl].items()
                if (t, c, b) == cond and n / total >= args.min_p
            }
            kept = sum(files.values())
            if not kept:
                continue
            kept_conditions += 1
            for f, n in sorted(files.items(), key=lambda kv: (-kv[1], kv[0])):
                out_rows.append((*cond, f, n, round(n / kept, 6)))

    args.out_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.out_csv.open("w", encoding="utf-8", newline="") as fh:
        fh.write(
            "# GENERATED by scripts/build_tree_mix_csv.py from\n"
            "# docs/evidence/vanilla_tree_mix.csv "
            "(scripts/measure_vanilla_tree_mix.py over the real CK3 1.19\n"
            "# gfx/map/map_object_data/generated/*.txt). Do not hand-edit: put "
            "human decisions in\n"
            "# overrides/tree_mix.csv, which the converter applies on top. "
            "Method and provenance:\n"
            "# docs/step_map_paint.md section 9.9.\n"
            "#\n"
            "# P(generator file | CK3 terrain key, winter climate zone, "
            "latitude band). `*` is a\n"
            "# wildcard: the sampler tries (terrain, climate, band), then "
            "(terrain, *, band),\n"
            "# then (terrain, climate, *), then (terrain, *, *), then the "
            "terrain's single row in\n"
            "# mappings/tree_meshes.csv -- latitude before climate, measured, "
            "see\n"
            "# docs/evidence/vanilla_tree_mix_conditioning.csv. lat_band 0 is "
            "the northernmost\n"
            "# tenth of the canvas.\n"
            f"# min-count {args.min_count}, min-p {args.min_p}, "
            f"{kept_conditions} conditions, {len(out_rows)} rows.\n"
        )
        w = csv.writer(fh)
        w.writerow(["ck3_terrain", "climate", "lat_band", "file", "count", "p"])
        w.writerows(out_rows)
    print(f"wrote {args.out_csv}: {kept_conditions} conditions, {len(out_rows)} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
