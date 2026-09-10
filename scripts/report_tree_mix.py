#!/usr/bin/env python3
"""Latitude band x mesh, ours vs vanilla — the evidence for "pines north".

Reads three sets of ``gfx/map/map_object_data/generated/*.txt`` — vanilla's
own, a run with ``[map] trees_regional = false`` (terrain class only) and a
run with it on — and writes, to ``docs/evidence/tree_mix/``:

* ``counts.csv``        instances per generator file, all three
* ``lat_band_mesh.csv`` share of each band's instances per mesh, all three
* ``patch_scale.csv``   stand purity vs cell size, all three (the number
                        ``[map] trees_cell_coherence`` is calibrated against)
* ``fig_lat_band_mesh.png``  the three band x species stacks side by side

Latitude bands are canvas row deciles of each map's own canvas, band 0 =
north — the same fractional-row transfer ``ck2ck3.map.tree_scatter.lat_band``
and ``scripts/measure_vanilla_tree_mix.py`` use.

Usage (matplotlib is deliberately not a repo dependency)::

    uv run --with matplotlib python scripts/report_tree_mix.py \\
        --before ../_out/trees-before --after ../_out/trees-regional
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import numpy as np

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from measure_vanilla_tree_mix import (  # noqa: E402
    PATCH_CELLS,
    band_of_y,
    instances_of_file,
    patch_purity,
)

GENERATED = "gfx/map/map_object_data/generated"
DEFAULT_GAME = Path(
    "/home/cvdbdo/.local/share/Steam/steamapps/common/Crusader Kings III/game"
)
OUT = ROOT / "docs/evidence/tree_mix"
N_BANDS = 10

#: species family per generator file — the figure's categorical dimension.
#: Eight families, so eight fixed categorical slots, assigned by entity and
#: never cycled.
FAMILY_OF = [
    ("tree_pine", "pine"),
    ("tree_leaf", "broadleaf"),
    ("tree_jungle", "jungle"),
    ("tree_palm", "palm"),
    ("tree_cypress", "cypress"),
    ("reeds", "reeds"),
    ("steppe_bush", "steppe bush"),
    ("tree_sakura", "sakura"),
]
FAMILIES = [f for _p, f in FAMILY_OF]
#: validated categorical palette, fixed order (dataviz skill's reference
#: instance; `node scripts/validate_palette.js` reports ALL CHECKS PASS on
#: this order, worst adjacent CVD dE 9.1). Slot i belongs to FAMILIES[i]
#: forever — colour follows the species, never its rank in a chart.
COLORS = [
    "#2a78d6", "#eb6834", "#1baf7a", "#eda100",
    "#e87ba4", "#008300", "#4a3aa7", "#e34948",
]
INK = "#3d3d38"
MUTED = "#8a8a80"


def family(file: str) -> str:
    for prefix, fam in FAMILY_OF:
        if file.startswith(prefix):
            return fam
    return "other"


def read_dir(d: Path) -> dict[str, np.ndarray]:
    """Every generated file's instances as an ``(n, 2)`` (x, z) array."""
    src = d / GENERATED
    if not src.is_dir():
        raise SystemExit(f"no {GENERATED} under {d}")
    return {p.name: instances_of_file(p) for p in sorted(src.glob("*.txt"))}


def canvas_height(d: Path) -> int:
    """Canvas height in pixels, from the run's own provinces.png."""
    from PIL import Image

    with Image.open(d / "map_data/provinces.png") as im:
        return im.size[1]


def band_table(xy: dict[str, np.ndarray], height: int) -> dict[int, dict[str, int]]:
    out: dict[int, dict[str, int]] = {b: {} for b in range(N_BANDS)}
    for f, pts in xy.items():
        if not pts.size:
            continue
        y = np.clip(height - pts[:, 1], 0, height - 1)
        bands = band_of_y(y, height, N_BANDS)
        for b, n in zip(*np.unique(bands, return_counts=True)):
            out[int(b)][f] = out[int(b)].get(f, 0) + int(n)
    return out


def family_shares(table: dict[int, dict[str, int]]) -> np.ndarray:
    """``(N_BANDS, len(FAMILIES))`` share matrix."""
    m = np.zeros((N_BANDS, len(FAMILIES)))
    for b, per_file in table.items():
        total = sum(per_file.values())
        if not total:
            continue
        for f, n in per_file.items():
            fam = family(f)
            if fam in FAMILIES:
                m[b, FAMILIES.index(fam)] += n / total
    return m


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--game", type=Path, default=DEFAULT_GAME)
    ap.add_argument("--before", type=Path, required=True)
    ap.add_argument("--after", type=Path, required=True)
    ap.add_argument("--out-dir", type=Path, default=OUT)
    args = ap.parse_args(argv[1:])

    sets = {
        "vanilla": (read_dir(args.game), 4608),
        "ours_terrain_only": (read_dir(args.before), canvas_height(args.before)),
        "ours_regional": (read_dir(args.after), canvas_height(args.after)),
    }
    args.out_dir.mkdir(parents=True, exist_ok=True)

    files = sorted({f for xy, _h in sets.values() for f in xy})
    with (args.out_dir / "counts.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["file", "family", *sets])
        for f in files:
            w.writerow(
                [f, family(f), *[int(sets[s][0].get(f, np.zeros(0)).shape[0])
                                 for s in sets]]
            )
        w.writerow(
            ["TOTAL", "", *[sum(int(v.shape[0]) for v in sets[s][0].values())
                            for s in sets]]
        )

    tables = {s: band_table(xy, h) for s, (xy, h) in sets.items()}
    with (args.out_dir / "lat_band_mesh.csv").open(
        "w", encoding="utf-8", newline=""
    ) as fh:
        w = csv.writer(fh)
        w.writerow(["set", "lat_band", "file", "family", "count", "share_of_band"])
        for s, t in tables.items():
            for b in range(N_BANDS):
                total = sum(t[b].values())
                for f, n in sorted(t[b].items(), key=lambda kv: -kv[1]):
                    w.writerow(
                        [s, b, f, family(f), n,
                         round(n / total, 6) if total else 0]
                    )

    with (args.out_dir / "patch_scale.csv").open(
        "w", encoding="utf-8", newline=""
    ) as fh:
        w = csv.writer(fh)
        w.writerow(["set", "cell_px", "cells", "instances", "mean_dominant_share"])
        for s, (xy, h) in sets.items():
            for row in patch_purity(xy, h, PATCH_CELLS):
                w.writerow([s, row["cell_px"], row["cells"], row["instances"],
                            row["mean_dominant_share"]])

    # ---------------------------------------------------------------- figure
    titles = {
        "vanilla": "vanilla CK3 1.19",
        "ours_terrain_only": "ours, terrain class only",
        "ours_regional": "ours, regional mix",
    }
    fig, axes = plt.subplots(1, 3, figsize=(13.5, 5.0), sharey=True)
    for ax, s in zip(axes, sets):
        m = family_shares(tables[s])
        bottom = np.zeros(N_BANDS)
        bands = np.arange(N_BANDS)
        for i, fam in enumerate(FAMILIES):
            vals = m[:, i] * 100
            # a 2 px surface gap between stacked segments
            ax.bar(bands, vals, bottom=bottom, width=0.74, color=COLORS[i],
                   label=fam, linewidth=1.4, edgecolor="white")
            # direct-label only the segments big enough to read (relief for
            # the three light-surface hues below 3:1 contrast)
            for b in bands:
                if vals[b] >= 12:
                    ax.text(b, bottom[b] + vals[b] / 2, f"{vals[b]:.0f}",
                            ha="center", va="center", fontsize=7.5,
                            color="white" if fam != "palm" else INK)
            bottom += vals
        ax.set_title(titles[s], fontsize=10, color=INK)
        ax.set_xlabel("latitude band (0 = north)", fontsize=9, color=MUTED)
        ax.set_xticks(bands)
        ax.set_xlim(-0.6, N_BANDS - 0.4)
        ax.set_ylim(0, 100)
        ax.tick_params(labelsize=8, colors=MUTED, length=0)
        for side in ("top", "right", "left"):
            ax.spines[side].set_visible(False)
        ax.spines["bottom"].set_color("#dcdcd6")
        ax.set_axisbelow(True)
        ax.grid(axis="y", color="#ececE6", linewidth=0.8)
    axes[0].set_ylabel("share of the band's instances (%)", fontsize=9, color=MUTED)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=len(FAMILIES),
               frameon=False, fontsize=9, bbox_to_anchor=(0.5, -0.01))
    fig.suptitle(
        "Tree species by latitude band — vanilla's own gradient, ours before "
        "and after the regional mix",
        fontsize=11.5, color=INK,
    )
    fig.tight_layout(rect=(0, 0.06, 1, 0.95))
    png = args.out_dir / "fig_lat_band_mesh.png"
    fig.savefig(png, dpi=140, facecolor="white")
    print(f"wrote {png}")
    for name in ("counts.csv", "lat_band_mesh.csv", "patch_scale.csv"):
        print(f"wrote {args.out_dir / name}")

    # a terminal summary: pine share north, palm+jungle share south
    for s in sets:
        m = family_shares(tables[s])
        pine = m[:, FAMILIES.index("pine")]
        warm = m[:, FAMILIES.index("palm")] + m[:, FAMILIES.index("jungle")]
        print(
            f"{s:>18}: pine bands 0-1 {100 * pine[:2].mean():5.1f} % | "
            f"palm+jungle bands 8-9 {100 * warm[8:].mean():5.1f} %"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
