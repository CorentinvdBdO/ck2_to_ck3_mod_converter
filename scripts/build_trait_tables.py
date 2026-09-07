#!/usr/bin/env python
"""Regenerate the repository-side tables the `traits` step produces.

Other lanes need these without running the converter:

* `mappings/trait_id_map.csv`          — CK2 trait id -> CK3 trait id (characters, events)
* `mappings/loc_key_renames_traits.csv` — CK2 loc key -> CK3 loc key (localisation)
* `docs/evidence/traits_unported.csv`   — every trait kept only as dead script
* `docs/evidence/traits_groups.csv`     — the group/level families the heuristic found

Usage: `uv run scripts/build_trait_tables.py [ck2_mod_dir]`
(default `Faerun/Faerun`). Reads only; writes only the four files above.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from ck2ck3.config import Config  # noqa: E402
from ck2ck3.traits import (  # noqa: E402
    build_plan,
    convert_plan,
    load_tables,
    loc_key_renames,
    trait_groups,
    unported,
)


def write_csv(path: Path, fields: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f"{path.relative_to(ROOT)}: {len(rows)} rows")


def main(argv: list[str]) -> int:
    config = Config.load(ROOT / "configs" / "faerun.toml")
    mod = Path(argv[1]).resolve() if len(argv) > 1 else config.ck2_mod
    tables = load_tables(
        ck3_traits_file=config.ck3_game / "common" / "traits" / "00_traits.txt"
    )
    plan = build_plan(mod, tables)
    converted, converter = convert_plan(plan, tables)

    write_csv(
        ROOT / "mappings" / "trait_id_map.csv",
        ["ck2_trait", "ck3_trait", "status", "source", "note"],
        [
            {
                "ck2_trait": r.ck2_trait,
                "ck3_trait": r.ck3_trait,
                "status": r.status,
                "source": r.source,
                "note": r.note,
            }
            for r in sorted(plan.renames, key=lambda r: r.ck2_trait)
        ],
    )
    write_csv(
        ROOT / "mappings" / "loc_key_renames_traits.csv",
        ["ck2_key", "ck3_key"],
        [{"ck2_key": a, "ck3_key": b} for a, b in loc_key_renames(plan)],
    )
    write_csv(
        ROOT / "docs" / "evidence" / "traits_unported.csv",
        ["ck2_trait", "source_file", "reason"],
        [
            {"ck2_trait": u.ck2_trait, "source_file": u.source_file, "reason": u.reason}
            for u in sorted(unported(plan), key=lambda u: u.ck2_trait)
        ],
    )
    live = {n: plan.traits[n] for n in plan.traits if n in set(plan.live())}
    groups = trait_groups(live)
    write_csv(
        ROOT / "docs" / "evidence" / "traits_groups.csv",
        ["ck2_trait", "ck3_group", "level"],
        [
            {"ck2_trait": name, "ck3_group": group, "level": level}
            for name, (group, level) in sorted(groups.items(), key=lambda kv: kv[1])
        ],
    )
    print(
        f"ck2 traits {len(plan.traits)}: ported {len(converted)} "
        f"({sum(1 for c in converted if c.kind == 'race_trait')} race), "
        f"deduped {len(plan.renames)}, commented {len(plan.commented())}"
    )
    print("counts: " + ", ".join(f"{k}={v}" for k, v in sorted(converter.counts.items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
