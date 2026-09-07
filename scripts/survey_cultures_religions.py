#!/usr/bin/env python
"""Survey the CK2 culture/religion data and the CK3 vanilla vocabularies.

Reads Faerûn's `common/cultures`, `common/religions` and `common/landed_titles`
plus the CK3 1.19 install, and prints the facts the `cultures` / `religions`
steps need: key inventories, value domains, counts. Everything the generator
hardcodes as a default must appear here first.

    uv run scripts/survey_cultures_religions.py [--config configs/faerun.toml]
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ck2ck3.config import Config  # noqa: E402
from ck2ck3.pdx import Block, Node, parse_file  # noqa: E402
from ck2ck3.pdx.encoding import CK3_ENCODING  # noqa: E402

CULTURE_NON_KEYS = {"graphical_cultures", "alternate_start"}


def culture_groups(ck2_mod: Path):
    """Yield (file, group_id, group_block, {culture_id: block})."""
    folder = ck2_mod / "common" / "cultures"
    for path in sorted(folder.glob("*.txt")):
        if path.stat().st_size == 0:
            continue
        doc = parse_file(path)
        for entry in doc.entries:
            if not isinstance(entry, Node) or not isinstance(entry.value, Block):
                continue
            cultures = {
                e.key: e.value
                for e in entry.value.entries
                if isinstance(e, Node)
                and isinstance(e.value, Block)
                and e.key not in CULTURE_NON_KEYS
            }
            yield path.name, entry.key, entry.value, cultures


def religion_groups(ck2_mod: Path):
    folder = ck2_mod / "common" / "religions"
    for path in sorted(folder.glob("*.txt")):
        doc = parse_file(path)
        for entry in doc.entries:
            if not isinstance(entry, Node) or not isinstance(entry.value, Block):
                continue
            if entry.key == "secret_religion_visibility_trigger":
                continue
            religions = {
                e.key: e.value
                for e in entry.value.entries
                if isinstance(e, Node)
                and isinstance(e.value, Block)
                and e.key
                not in {
                    "male_names",
                    "female_names",
                    "color",
                    "alternate_start",
                    "character_modifier",
                    "unit_modifier",
                    "unit_home_modifier",
                }
            }
            yield path.name, entry.key, entry.value, religions


def holy_sites(ck2_mod: Path) -> Counter:
    """CK2 `holy_site = <religion>` marks, counted per religion."""
    out: Counter = Counter()
    folder = ck2_mod / "common" / "landed_titles"
    for path in sorted(folder.glob("*.txt")):
        doc = parse_file(path, lenient=True)
        stack = [doc]
        while stack:
            block = stack.pop()
            for entry in block.entries:
                if isinstance(entry, Node):
                    if entry.key == "holy_site":
                        out[str(entry.value)] += 1
                    if isinstance(entry.value, Block):
                        stack.append(entry.value)
    return out


def ck3_ids(game: Path, rel: str, depth: int = 0) -> list[str]:
    """Top-level ids defined in every file of a CK3 folder."""
    out: list[str] = []
    folder = game / rel
    for path in sorted(folder.glob("*.txt")):
        if path.name.startswith("_"):
            continue
        doc = parse_file(path, encoding=CK3_ENCODING, lenient=True)
        for entry in doc.entries:
            if isinstance(entry, Node) and not entry.key.startswith("@"):
                out.append(entry.key)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="configs/faerun.toml")
    args = ap.parse_args()
    cfg = Config.load(Path(args.config))
    ck2, game = cfg.ck2_mod, cfg.ck3_game

    print("== CK2 cultures ==")
    groups = list(culture_groups(ck2))
    n_cult = sum(len(c) for *_, c in groups)
    print(f"groups={len(groups)} cultures={n_cult}")
    per_file = Counter(f for f, *_ in groups)
    print("groups per file:", dict(per_file))
    gkeys: Counter = Counter()
    ckeys: Counter = Counter()
    gfx: Counter = Counter()
    unit_gfx: Counter = Counter()
    for _f, _g, gblock, cultures in groups:
        for k in gblock.keys():
            if k in CULTURE_NON_KEYS:
                gkeys[k] += 1
        val = gblock.get("graphical_cultures")
        if isinstance(val, Block):
            for v in val.list_values():
                gfx[str(v)] += 1
        for _cid, cblock in cultures.items():
            for k in cblock.keys():
                ckeys[k] += 1
            uv = cblock.get("unit_graphical_cultures")
            if isinstance(uv, Block):
                for v in uv.list_values():
                    unit_gfx[str(v)] += 1
    print("group keys:", dict(gkeys))
    print("culture keys:", dict(sorted(ckeys.items(), key=lambda kv: -kv[1])))
    print(f"distinct group graphical_cultures values={len(gfx)}")
    print("top graphical_cultures:", gfx.most_common(20))
    print("unit_graphical_cultures:", dict(unit_gfx))

    print("\n== CK2 religions ==")
    rgroups = list(religion_groups(ck2))
    n_rel = sum(len(r) for *_, r in rgroups)
    print(f"groups={len(rgroups)} religions={n_rel}")
    for _f, gid, _gb, rels in rgroups:
        print(f"  {gid}: {len(rels)} -> {sorted(rels)}")
    rgkeys: Counter = Counter()
    rkeys: Counter = Counter()
    for _f, _g, gblock, rels in rgroups:
        for k in gblock.keys():
            if k not in rels:
                rgkeys[k] += 1
        for _rid, rblock in rels.items():
            for k in rblock.keys():
                rkeys[k] += 1
    print("religion-group keys:", dict(sorted(rgkeys.items(), key=lambda kv: -kv[1])))
    print("religion keys:", dict(sorted(rkeys.items(), key=lambda kv: -kv[1])))

    print("\n== CK2 holy sites ==")
    hs = holy_sites(ck2)
    print(f"marks={sum(hs.values())} religions_with_sites={len(hs)}")
    print("top:", hs.most_common(15))
    over = {k: v for k, v in hs.items() if v > 5}
    print(f"religions over the 5-site cap: {len(over)}")

    print("\n== CK3 vocabularies ==")
    for rel in (
        "common/culture/pillars",
        "common/culture/traditions",
        "common/ethnicities",
        "common/religion/doctrine_types",
        "common/religion/religion_family_types",
        "common/named_colors",
        "common/modifier_definition_formats",
    ):
        ids = ck3_ids(game, rel)
        print(f"{rel}: {len(ids)} ids; sample={ids[:6]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
