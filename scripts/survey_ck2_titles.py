#!/usr/bin/env python
"""Tally the CK2 title side with the lane's own reader.

Every count quoted in ``docs/step_titles.md`` and ``docs/formats_titles.md``
comes from here, so a claim can be re-checked after an upstream update:

    uv run scripts/survey_ck2_titles.py [--mod Faerun/Faerun]
"""

from __future__ import annotations

import argparse
import collections
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from ck2ck3.titles import ck2read  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mod", default=str(ROOT / "Faerun" / "Faerun"))
    args = ap.parse_args()
    mod = Path(args.mod)

    roots = ck2read.read_landed_titles_dir(mod / "common" / "landed_titles")
    flat = ck2read.flatten(roots)
    by_tier = collections.Counter(t.prefix for t in flat)
    print("landed_titles: " + ", ".join(f"{k}_={v}" for k, v in sorted(by_tier.items())))
    print(f"  roots={len(roots)} total={len(flat)}")

    kw = collections.Counter()
    for t in flat:
        kw.update(t.keywords.keys())
    print("  keywords: " + ", ".join(f"{k}={v}" for k, v in kw.most_common()))

    blocks = collections.Counter()
    for t in flat:
        blocks.update(t.blocks.keys())
    print("  blocks: " + ", ".join(f"{k}={v}" for k, v in blocks.most_common()))

    cn_lines = sum(len(t.cultural_names) for t in flat)
    cn_keys = collections.Counter()
    for t in flat:
        cn_keys.update(t.cultural_names.keys())
    print(f"  cultural_name lines={cn_lines} distinct keys={len(cn_keys)}")
    markers = collections.Counter()
    for t in flat:
        markers.update(t.group_markers)
    print("  group markers: " + ", ".join(f"{k}={v}" for k, v in markers.most_common()))
    print(f"  titles with color={sum(1 for t in flat if t.color)}")

    groups = ck2read.read_culture_groups(mod / "common" / "cultures")
    cultures = {c for m in groups.values() for c in m}
    print(f"cultures: {len(groups)} groups, {len(cultures)} cultures")
    unknown = sorted(k for k in cn_keys if k not in cultures and k not in groups)
    print(f"  cultural_name keys that are neither culture nor group: {len(unknown)}")
    if unknown:
        print("   " + " ".join(unknown[:40]))
    group_keyed = sorted(k for k in cn_keys if k in groups)
    print(f"  group-keyed cultural names: {len(group_keyed)} {group_keyed}")

    reps = ck2read.republic_titles(
        mod / "common" / "landed_titles" / "republics.txt"
    )
    print(f"republics.txt titles: {len(reps)}")

    hist = ck2read.read_title_histories(mod / "history" / "titles")
    print(f"history/titles: {len(hist)} files")
    tl = sum(len(h.toplevel) for h in hist.values())
    print(f"  top-level (non-dated) keys: {tl}")
    hkeys = collections.Counter()
    for h in hist.values():
        for _, nodes in h.dated:
            hkeys.update(n.key for n in nodes)
        hkeys.update(f"TOPLEVEL:{n.key}" for n in h.toplevel)
    print("  keys: " + ", ".join(f"{k}={v}" for k, v in hkeys.most_common(25)))
    laws = collections.Counter()
    for h in hist.values():
        for _, nodes in h.dated:
            laws.update(str(n.value) for n in nodes if n.key == "law")
    print(f"  distinct laws: {len(laws)}")
    govs = collections.Counter()
    for h in hist.values():
        for _, nodes in h.dated:
            govs.update(str(n.value) for n in nodes if n.key == "government")
    print(f"  explicit governments: {dict(govs)}")

    prov = ck2read.read_province_histories(mod / "history" / "provinces")
    print(f"history/provinces: {len(prov)} files")
    built0 = sum(len(p.holdings) for p in prov.values())
    changes = sum(len(p.holding_changes) for p in prov.values())
    print(f"  holdings at file top={built0} dated holding changes={changes}")
    kinds = collections.Counter()
    for p in prov.values():
        kinds.update(p.holdings.values())
        kinds.update(h for _, _, h in p.holding_changes)
    print("  holding values: " + ", ".join(f"{k}={v}" for k, v in kinds.most_common()))
    print(f"  provinces with a title= {sum(1 for p in prov.values() if p.title)}")
    dated_keys = collections.Counter()
    for p in prov.values():
        dated_keys.update(k for _, k, _ in p.dated)
    print("  dated keys: " + ", ".join(f"{k}={v}" for k, v in dated_keys.most_common(15)))

    bms = ck2read.read_bookmarks_dir(mod / "common" / "bookmarks")
    print(f"bookmarks: {len(bms)}, characters={sum(len(b.characters) for b in bms)}")
    for b in bms:
        print(f"  {b.id} {b.date} era={b.era} chars={len(b.characters)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
