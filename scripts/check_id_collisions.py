#!/usr/bin/env python
"""Do Faerûn culture / religion ids collide with CK3 1.19 vanilla ids?

Matters because the generated mod *replaces* `common/culture/cultures`,
`common/culture/name_lists` and the three `common/religion/*_types` folders
(configs/faerun.toml `replace_paths`) but only *adds to*
`common/culture/pillars`, `common/culture/traditions`, `common/ethnicities` and
`common/modifier_definition_formats`. A collision is harmless in a replaced
folder and fatal (duplicate definition) in an additive one.

    uv run scripts/check_id_collisions.py
"""

from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
warnings.simplefilter("ignore")

from ck2ck3.config import Config  # noqa: E402
from ck2ck3.pdx import Block, Node, parse_file  # noqa: E402
from ck2ck3.pdx.encoding import CK3_ENCODING  # noqa: E402
from ck2ck3.steps import cultures as cultures_step  # noqa: E402
from ck2ck3.steps import religions as religions_step  # noqa: E402


def ck3_top_ids(game: Path, rel: str) -> set[str]:
    out: set[str] = set()
    folder = game / rel
    for path in sorted(folder.glob("*.txt")):
        if path.name.startswith("_"):
            continue
        doc = parse_file(path, encoding=CK3_ENCODING, lenient=True)
        for entry in doc.entries:
            if isinstance(entry, Node) and not entry.key.startswith("@"):
                out.add(entry.key)
    return out


def ck3_faith_ids(game: Path) -> set[str]:
    out: set[str] = set()
    folder = game / "common/religion/religion_types"
    for path in sorted(folder.glob("*.txt")):
        if path.name.startswith("_"):
            continue
        doc = parse_file(path, encoding=CK3_ENCODING, lenient=True)
        for entry in doc.entries:
            if not isinstance(entry, Node) or not isinstance(entry.value, Block):
                continue
            out.add(entry.key)
            faiths = entry.value.get("faiths")
            if isinstance(faiths, Block):
                out.update(
                    e.key for e in faiths.entries if isinstance(e, Node)
                )
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="configs/faerun.toml")
    args = ap.parse_args()
    cfg = Config.load(Path(args.config))

    groups = cultures_step.read_ck2_cultures(cfg.ck2_mod)
    ck2_cultures = {c.id for g in groups for c in g.cultures}
    rgroups = religions_step.read_ck2_religions(cfg.ck2_mod)
    ck2_faiths = {r.id for g in rgroups for r in g.religions}

    checks = [
        ("culture ids vs vanilla cultures (REPLACED - ok)",
         ck2_cultures, ck3_top_ids(cfg.ck3_game, "common/culture/cultures")),
        ("faith ids vs vanilla religions+faiths (REPLACED - ok)",
         ck2_faiths, ck3_faith_ids(cfg.ck3_game)),
        ("<culture>_opinion vs vanilla modifier formats (ADDITIVE - skipped by the step)",
         {f"{c}_opinion" for c in ck2_cultures},
         ck3_top_ids(cfg.ck3_game, "common/modifier_definition_formats")),
        ("<faith>_opinion vs vanilla modifier formats (ADDITIVE - skipped by the step)",
         {f"{f}_opinion" for f in ck2_faiths},
         ck3_top_ids(cfg.ck3_game, "common/modifier_definition_formats")),
    ]
    for label, mine, theirs in checks:
        clash = sorted(mine & theirs)
        print(f"{label}: {len(clash)} collisions" + (f" -> {clash}" if clash else ""))
    print(f"\ncultures={len(ck2_cultures)} faiths={len(ck2_faiths)}")
    print(
        "Additive collisions are handled: build_opinion_formats() skips any key "
        "vanilla already declares and leaves a comment in its place "
        "(test_vanilla_declared_opinion_keys_are_skipped)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
