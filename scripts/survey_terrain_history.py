#!/usr/bin/env python
"""What the CK2 province-history ``terrain = X`` override says, and where it
disagrees with the ``terrain.bmp`` majority the converter used to trust alone.

Why: in CK2 the history override **is** the province's gameplay terrain; the
bitmap majority is only the fallback (``docs/step_map_terrain.md`` §1).  The
converter derived ``common/province_terrain`` from the bitmap only, so for
every province that carries an override and disagrees with its own pixels we
shipped a terrain the CK2 author did not choose.

This script measures three things, at **CK2 province** (= CK3 county)
resolution, which is cheap (13.6 Mpx, ~20 s) and needs no barony Voronoi:

1. the tally of override categories, and whether any is inside a dated block;
2. for each override category, the distribution of the bitmap majority of the
   same province — the evidence for what Faerûn's invented categories
   (``coastal``, ``subterranean``, ``glacier``, ``arctic``) actually mean;
3. the county-level agreement rate override vs bitmap, in CK3 keys.

The barony-level agreement (county capital vs the other baronies) needs the
real run; it is emitted by the ``map`` step itself as
``docs/evidence/terrain_history_baronies.csv``.

    uv run python scripts/survey_terrain_history.py \
        --ck2-mod-dir Faerun/Faerun \
        --out docs/evidence/terrain_history_survey.md \
        --csv docs/evidence/terrain_history_survey.csv
"""

from __future__ import annotations

import argparse
import csv
import io
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from PIL import Image

from ck2ck3.map import ck2read, holdings, provinces, terrain

Image.MAX_IMAGE_PIXELS = None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ck2-mod-dir", default="Faerun/Faerun")
    ap.add_argument("--out", default="docs/evidence/terrain_history_survey.md")
    ap.add_argument("--csv", default="docs/evidence/terrain_history_survey.csv")
    args = ap.parse_args()

    mod = Path(args.ck2_mod_dir)
    src = mod / "map"

    hist = holdings.read_dir(mod / "history" / "provinces")
    provs = ck2read.read_definitions(src / "definition.csv")
    names = {p.id: p.name for p in provs}
    dm = ck2read.read_default_map(src / "default.map")
    water = dm.sea_ids() | set(dm.major_rivers)
    tex_map = ck2read.read_terrain_texture_map(src / "terrain.txt")
    tree_indices = tuple(ck2read.parse_file(src / "default.map").ints("tree"))

    # -------------------------------------------------- the overrides
    overrides: dict[int, str] = {}
    dated: list[tuple[int, str, str]] = []
    for pid, h in sorted(hist.items()):
        for when, value in h.terrains:
            if when != holdings.EPOCH:
                dated.append((pid, "%d.%d.%d" % when, value))
        latest = h.terrain_at((9999, 1, 1))
        if latest:
            overrides[pid] = latest

    # -------------------------------------------------- bitmap majority
    with Image.open(src / "provinces.bmp") as im:
        rgb = np.asarray(im.convert("RGB"))
    lookup = {(p.rgb[0] << 16) | (p.rgb[1] << 8) | p.rgb[2]: p.id for p in provs}
    ids, _ = provinces._keys_to_ids(provinces.rgb_key(rgb), lookup)
    del rgb

    with Image.open(src / "terrain.bmp") as im:
        terrain_idx = np.asarray(im)
    trees = None
    if (src / "trees.bmp").exists():
        with Image.open(src / "trees.bmp") as im:
            trees = np.asarray(im)
    codes, code_names = terrain.ck2_category_codes(
        terrain_idx, tex_map, trees=trees, tree_indices=tree_indices
    )

    land_ids = {int(i) for i in np.unique(ids) if int(i) > 0} - water
    res = terrain.majority_terrain_codes(
        ids, codes, code_names, land_ids=land_ids, mapping=None, default="plains"
    )

    # -------------------------------------------------- cross-tabulation
    table = terrain.CK2_TO_CK3_TERRAIN
    cat_tally: Counter[str] = Counter()
    cross: dict[str, Counter[str]] = defaultdict(Counter)
    cross_ck3: dict[str, Counter[str]] = defaultdict(Counter)
    agree_ck3 = 0
    rows: list[list[object]] = []
    for pid in sorted(overrides):
        ov = overrides[pid]
        cat_tally[ov] += 1
        bit_cat = res.category.get(pid, "")
        bit_key = res.by_province.get(pid, "")
        ov_key = table.get(ov, "")
        cross[ov][bit_cat or "(no land pixel)"] += 1
        cross_ck3[ov][bit_key or "(none)"] += 1
        same = bool(ov_key) and ov_key == bit_key
        agree_ck3 += same
        rows.append(
            [
                pid,
                names.get(pid, ""),
                hist[pid].county or "",
                "land" if pid in land_ids else "water/absent",
                ov,
                ov_key,
                bit_cat,
                bit_key,
                "yes" if same else "no",
            ]
        )

    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(
        [
            "ck2_province",
            "name",
            "county",
            "kind",
            "history_terrain",
            "history_ck3_key",
            "bitmap_category",
            "bitmap_ck3_key",
            "agree",
        ]
    )
    w.writerows(rows)
    Path(args.csv).parent.mkdir(parents=True, exist_ok=True)
    Path(args.csv).write_text(buf.getvalue(), encoding="utf-8", newline="")

    # -------------------------------------------------- report
    out: list[str] = []
    out.append("# CK2 `history/provinces` `terrain = X` override — survey\n")
    out.append(
        f"Generated by `scripts/survey_terrain_history.py` over `{mod}`.\n"
        f"Province-history files: {len(hist)}. "
        f"Files carrying an override: {len(overrides)} "
        f"({100 * len(overrides) / max(1, len(hist)):.1f} %).\n"
    )
    out.append(
        f"Overrides inside a **dated** block: {len(dated)}"
        + (" — none, so the override is a static property here.\n" if not dated else "\n")
    )
    for pid, when, value in dated[:20]:
        out.append(f"  - province {pid} @ {when} = {value}\n")

    out.append("\n## 1. Override tally\n\n| CK2 category | provinces | CK3 key today |\n|---|---|---|\n")
    for cat, n in cat_tally.most_common():
        out.append(f"| `{cat}` | {n} | `{table.get(cat, '(unmapped)')}` |\n")

    n_land = sum(1 for pid in overrides if pid in land_ids)
    out.append(
        f"\nOf those, {n_land} are land provinces the converter votes terrain "
        f"for; {len(overrides) - n_land} are water or dropped.\n"
    )
    out.append(
        f"\n## 2. County-level agreement (CK3 key)\n\n"
        f"Override's CK3 key == bitmap majority's CK3 key for "
        f"**{agree_ck3} of {len(overrides)}** "
        f"({100 * agree_ck3 / max(1, len(overrides)):.1f} %). "
        f"The other {len(overrides) - agree_ck3} counties ship a terrain the "
        f"CK2 author did not choose.\n"
    )

    out.append("\n## 3. What the bitmap says under each override\n")
    for cat, _ in cat_tally.most_common():
        total = cat_tally[cat]
        out.append(f"\n### `{cat}` ({total} provinces) → `{table.get(cat, '?')}`\n\n")
        out.append("| bitmap CK2 category | n | share | bitmap CK3 key |\n|---|---|---|---|\n")
        for bc, n in cross[cat].most_common():
            key = table.get(bc, "")
            out.append(f"| `{bc}` | {n} | {100 * n / total:.1f} % | `{key}` |\n")

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text("".join(out), encoding="utf-8")
    print("".join(out))
    print(f"\nwrote {args.out} and {args.csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
