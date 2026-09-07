#!/usr/bin/env python
"""Survey the Faerûn CK2 trait corpus: counts, key usage, opposites cliques.

Read-only. Writes nothing; prints a report used to size the `traits` step and
to derive the group/level heuristic. See docs/step_traits.md.
"""

from __future__ import annotations

import collections
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from ck2ck3 import pdx  # noqa: E402

TRAITS_DIR = ROOT / "Faerun" / "Faerun" / "common" / "traits"


def load_csv(rel: str, key: str) -> dict[str, dict[str, str]]:
    with (ROOT / rel).open(encoding="utf-8", newline="") as handle:
        return {row[key]: row for row in csv.DictReader(handle)}


def main() -> int:
    vanilla = load_csv("mappings/vanilla_traits.csv", "ck2_trait")
    custom = load_csv("docs/evidence/faerun_custom_traits.csv", "ck2_trait")
    fields = load_csv("mappings/trait_fields.csv", "ck2_key")
    modifiers = load_csv("mappings/modifiers.csv", "ck2_key")

    order: list[str] = []
    per_file: dict[str, list[str]] = {}
    keys = collections.Counter()
    opposites: dict[str, set[str]] = {}
    for path in sorted(TRAITS_DIR.glob("*.txt")):
        doc = pdx.parse_file(path)
        names = [n.key for n in doc.nodes()]
        per_file[path.name] = names
        order.extend(names)
        for node in doc.nodes():
            if not isinstance(node.value, pdx.Block):
                continue
            for key in node.value.keys():
                keys[key] += 1
            opp = node.value.get("opposites")
            if isinstance(opp, pdx.Block):
                opposites[node.key] = {str(v) for v in opp.list_values()}

    print(f"trait blocks: {len(order)} in {len(per_file)} files, distinct {len(set(order))}")
    dupes = [n for n, c in collections.Counter(order).items() if c > 1]
    print(f"redefined within Faerun: {len(dupes)} {sorted(dupes)[:10]}")
    print(f"in vanilla_traits.csv: {sum(1 for n in set(order) if n in vanilla)}")
    print(f"in faerun_custom_traits.csv: {sum(1 for n in set(order) if n in custom)}")
    print(f"in neither: {sorted(set(order) - set(vanilla) - set(custom))}")
    for name, rows in (("files", per_file),):
        for f, names in rows.items():
            print(f"  {f}: {len(names)}")

    print(f"\ndistinct keys used: {len(keys)}")
    unmapped = [k for k in keys if k not in fields and k not in modifiers]
    print(f"keys in neither mapping table: {len(unmapped)}")
    for k in sorted(unmapped):
        print(f"  {k}  x{keys[k]}")

    print("\n-- opposites cliques (mutual, size>=3) --")
    for name, opp in sorted(opposites.items()):
        clique = {name} | opp
        if len(clique) < 3:
            continue
        if all(clique - {m} == opposites.get(m, set()) for m in clique):
            if name == min(clique, key=order.index):
                ranked = sorted(clique, key=order.index)
                print(f"  {len(ranked)}: {ranked}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
