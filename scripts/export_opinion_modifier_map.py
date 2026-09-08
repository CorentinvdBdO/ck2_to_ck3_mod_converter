#!/usr/bin/env python
"""Resolve the placeholder rows of `mappings/modifiers.csv` and hand two tables
to the neighbouring lanes.

`mappings/modifiers.csv` carries rows whose CK3 side is still a placeholder
(`<ck3_culture>_opinion`, `<ck3_faith>_opinion`,
`<ck3_religion>_religion_opinion`) because the culture and faith ids only exist
once the `cultures` / `religions` steps have run. This script runs those steps'
pure readers and writes:

* `mappings/opinion_modifier_map.csv` — `ck2_modifier_key,ck3_modifier_key,...`
  for the **traits** lane, one row per CK3 key (a CK2 culture-*group* key fans
  out to one row per culture, because CK3 has no culture-group opinion scope).
* `mappings/loc_key_renames_cultures_religions.csv` — `ck2_key,ck3_key` for the
  **localisation** lane: the extra key shapes CK3 wants (a possessive, a plural)
  that CK2 stores only once.

    uv run scripts/export_opinion_modifier_map.py [--config configs/faerun.toml]
"""

from __future__ import annotations

import argparse
import csv
import io
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

MAPPINGS = Path(__file__).resolve().parents[1] / "mappings"


def vanilla_modifier_formats(game: Path) -> set[str]:
    """Every key already declared in vanilla `common/modifier_definition_formats`.

    `common/modifier_definition_formats` is **not** in `replace_paths`, so a
    generated declaration that collides with a vanilla one is a duplicate.
    """
    out: set[str] = set()
    folder = game / "common" / "modifier_definition_formats"
    for path in sorted(folder.glob("*.txt")):
        if path.name.startswith("_"):
            continue
        doc = parse_file(path, encoding=CK3_ENCODING, lenient=True)
        out.update(e.key for e in doc.entries if isinstance(e, Node))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="configs/faerun.toml")
    args = ap.parse_args()
    cfg = Config.load(Path(args.config))
    prefix = cfg.prefix

    groups = cultures_step.read_ck2_cultures(cfg.ck2_mod)
    culture_of_group = {g.id: [c.id for c in g.cultures] for g in groups}
    rgroups = religions_step.read_ck2_religions(cfg.ck2_mod)
    faiths = {r.id for g in rgroups for r in g.religions}
    religion_of_group = {
        g.id: religions_step.religion_id(prefix, g) for g in rgroups
    }
    family_of_group = {g.id: religions_step.family_id(prefix, g) for g in rgroups}
    vanilla = vanilla_modifier_formats(cfg.ck3_game)

    rows: list[list[str]] = []
    unresolved: list[str] = []
    #: CK2 opinion keys that name a religion/culture Faerûn never defines:
    #: three CK2-base leftovers plus one typo (the religion is `thasmudyanic`).
    #: `verified` by grep: 0 definitions in Faerûn common/religions.
    DANGLING_NOTE = (
        "CK2 dangling reference: Faerun defines no religion or culture of this "
        "name (CK2-base leftover or typo), so there is nothing to map"
    )
    with (MAPPINGS / "modifiers.csv").open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            ck2 = row["ck2_key"]
            ck3 = row["ck3_key"]
            if not ck2.endswith("_opinion") or "<" not in ck3:
                continue
            stem = ck2[: -len("_opinion")]
            if ck3 == "<ck3_culture>_opinion":
                if stem in culture_of_group:
                    for culture in culture_of_group[stem]:
                        rows.append(
                            [
                                ck2,
                                f"{culture}_opinion",
                                "culture",
                                "approx",
                                f"CK2 culture group {stem}: CK3 has no culture-group "
                                "opinion scope, so the CK2 key fans out to every "
                                "culture of the group",
                            ]
                        )
                elif any(stem in c for c in culture_of_group.values()):
                    rows.append([ck2, f"{stem}_opinion", "culture", "exact", ""])
                else:
                    unresolved.append(ck2)
            elif ck3 == "<ck3_faith>_opinion":
                if stem in faiths:
                    rows.append([ck2, f"{stem}_opinion", "faith", "exact", ""])
                else:
                    unresolved.append(ck2)
            elif ck3 == "<ck3_religion>_religion_opinion":
                if stem in religion_of_group:
                    rows.append(
                        [
                            ck2,
                            f"{religion_of_group[stem]}_opinion",
                            "religion",
                            "approx",
                            "CK2 religion group -> CK3 religion; the sibling "
                            f"family key is {family_of_group[stem]}_opinion",
                        ]
                    )
                else:
                    unresolved.append(ck2)
            else:
                unresolved.append(ck2)

    for key in sorted(set(unresolved)):
        rows.append([key, "", "", "none", DANGLING_NOTE])

    clashes = sorted({r[1] for r in rows if r[1]} & vanilla)
    buffer = io.StringIO()
    for line in (
        "CK2 opinion modifier key -> CK3 opinion modifier key, resolved against the",
        "culture and faith ids the `cultures` / `religions` steps emit.",
        "Written by scripts/export_opinion_modifier_map.py; consumed by the traits lane.",
        "A CK2 culture-GROUP key produces one row per culture of the group: CK3 has no",
        "culture-group opinion scope (verified: 0 heritage_*_opinion keys in 1.19).",
        "Every ck3_modifier_key here is declared in the generated",
        "common/modifier_definition_formats/fae_{culture,faith}_opinions.txt.",
        f"Vanilla-key collisions: {len(clashes)}"
        + (f" -> {', '.join(clashes)}" if clashes else " (none)"),
    ):
        buffer.write(f"# {line}\n")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["ck2_modifier_key", "ck3_modifier_key", "scope", "status", "note"])
    writer.writerows(sorted(rows))
    (MAPPINGS / "opinion_modifier_map.csv").write_text(
        buffer.getvalue(), encoding="utf-8"
    )
    print(
        f"opinion_modifier_map.csv: {len(rows)} rows, "
        f"{len(set(unresolved))} dangling CK2 keys"
    )
    for key in sorted(set(unresolved)):
        print(f"  dangling: {key}")

    renames: list[tuple[str, str]] = []
    for group in rgroups:
        for religion in group.religions:
            _, rows_ = religions_step.faith_localization(religion)
            renames += rows_
    # CK3 asks a culture for three localisation keys, CK2 supplies one.
    # `verified` 2026-09-08: vanilla
    # localization/english/culture/cultures_l_english.yml:460-462 has
    # `norse`, `norse_prefix` and `norse_collective_noun`, all three "Norse",
    # and without the latter two the game logs
    # `culture_template.cpp: Missing localization for <culture>_prefix` — 832
    # of them on Faerun. `copy` mode emits both from the CK2 key's own text.
    for cgroup in groups:
        for culture in cgroup.cultures:
            key = cultures_step.culture_id(culture)
            renames.append((key, f"{key}_prefix"))
            renames.append((key, f"{key}_collective_noun"))
            # A name list needs its own loc key too: vanilla
            # localization/english/culture/culture_name_lists_l_english.yml:4
            # has ` name_list_ainu: "Ainu"`, 221 of them, and without it CK3
            # logs `culture_name_lists.cpp: Missing loc for name_list_X` — 419
            # of them on Faerun (`verified` 2026-09-08).
            renames.append((key, cultures_step.name_list_id(prefix, culture)))
    seen: set[tuple[str, str]] = set()
    unique = [r for r in sorted(renames) if not (r in seen or seen.add(r))]
    buffer = io.StringIO()
    for line in (
        "Extra localisation key shapes the CK3 religion UI needs, which CK2 stores",
        "only once. Written by scripts/export_opinion_modifier_map.py for the",
        "localisation lane; the generated faiths already reference the ck3_key.",
        "`_possessive` is needed for HighGodNamePossessive / DevilNamePossessive,",
        "`_plural` for Priest*Plural / Bishop*Plural / AltPriestTermPlural / GHWNamePlural.",
        "The ck2_key's own text is the input; the ck3_key is a NEW key to derive from it.",
        "Faith / religion / family base keys (<faith_id>, _adj, _adherent,",
        "_adherent_plural, _desc and holy_site_<id>_name) keep the CK2 names and are",
        "not listed: nothing renames.",
        "<culture>_prefix and <culture>_collective_noun are here too: CK3 wants three",
        "keys per culture (vanilla norse/norse_prefix/norse_collective_noun, all",
        '"Norse") and CK2 has only the first. So is name_list_<prefix>_<culture>:',
        'vanilla has ` name_list_ainu: "Ainu"` for every one of its 221 name lists.',
    ):
        buffer.write(f"# {line}\n")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["ck2_key", "ck3_key"])
    writer.writerows(unique)
    (MAPPINGS / "loc_key_renames_cultures_religions.csv").write_text(
        buffer.getvalue(), encoding="utf-8"
    )
    print(f"loc_key_renames_cultures_religions.csv: {len(unique)} rows")
    return 1 if clashes else 0


if __name__ == "__main__":
    raise SystemExit(main())
