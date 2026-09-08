#!/usr/bin/env python
"""Report every CK2 trait key that is in neither `mappings/` trait table.

`ck2ck3.traits.convert` raises `UnmappedKey` on the first uncovered key, which
tells you one key per run. Changing which traits are ported (the 2026-09-08
"replace, never drop" policy did) uncovers a whole batch at once, so this
script converts every live trait independently and lists all of them with the
trait and the block they sit in.

Exit code 0 when every key is covered, 1 otherwise.

Usage: `uv run scripts/check_trait_key_coverage.py [ck2_mod_dir]`
(default: the `[paths] ck2_mod` of `configs/faerun.toml`).
"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from ck2ck3.config import Config  # noqa: E402
from ck2ck3.traits import build_plan, load_tables  # noqa: E402
from ck2ck3.traits.convert import TraitConverter, UnmappedKey, trait_groups  # noqa: E402


def main(argv: list[str]) -> int:
    config = Config.load(ROOT / "configs" / "faerun.toml")
    mod = Path(argv[1]).resolve() if len(argv) > 1 else config.ck2_mod
    tables = load_tables(
        ck3_traits_file=config.ck3_game / "common" / "traits" / "00_traits.txt"
    )
    plan = build_plan(mod, tables)
    live = set(plan.live())
    groups = trait_groups({n: plan.traits[n] for n in plan.traits if n in live})

    missing: dict[str, list[str]] = defaultdict(list)
    for name in plan.traits:
        if name not in live:
            continue
        # One converter per trait: a raise must not stop the next trait.
        converter = TraitConverter(
            tables,
            icons=plan.icon_value,
            live_traits=live,
            groups=groups,
            renames=plan.rename_map,
        )
        try:
            converter.convert(
                name,
                plan.traits[name],
                source_file=plan.source_file[name],
                kind=plan.decision[name],
            )
        except UnmappedKey as exc:
            # "trait <name>: <key> is in neither mapping table"
            key = str(exc).split(": ", 1)[-1].split(" is in neither")[0]
            missing[key].append(name)

    for key in sorted(missing):
        traits = sorted(missing[key])
        print(f"{key}\t{len(traits)}\t{', '.join(traits[:8])}")
    print(f"UNMAPPED KEYS: {len(missing)} over {len(live)} live traits")
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
