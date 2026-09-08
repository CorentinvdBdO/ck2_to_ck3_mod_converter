#!/usr/bin/env python
"""Write ``mappings/loc_key_renames_titles.csv`` — this lane's hand-off to `loc`.

The `loc` lane keeps CK2 localisation keys as they are.  Three places in the
title world need a *different* key on the CK3 side, so each becomes a row
``ck2_key,ck3_key``:

1. **title adjectives.**  CK3 reads a title's adjective from
   ``<title id>_adj`` (`verified`, ``localization/english/*`` has
   ``k_england`` and ``k_england_adj``).  Faerun's CK2 localisation has
   **zero** ``*_adj`` keys (`verified`), so every title key has to be copied to
   an ``_adj`` key or the game prints the raw key.
2. **bookmark names.**  CK3 uses the bookmark's own database key as its
   localisation key (``common/bookmarks/groups/_bookmark_groups.info``: "Key of
   the bookmark is used as localization tag as well"), while CK2 names a
   separate key in ``name =`` / ``desc =``.
3. **bookmark character names.**  The converted bookmark character is called
   ``bookmark_<prefix>_<ck2 id>``; CK2 pointed at its own ``ERA_CHAR_NAME_*``
   key.

A CK2 key may appear on several rows: that means "emit the same text under
each CK3 key".  A row whose two columns are equal is never written.

    uv run scripts/build_loc_key_renames_titles.py
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from ck2ck3.config import Config  # noqa: E402
from ck2ck3.titles import model  # noqa: E402

HEADER = ("ck2_key", "ck3_key")


def rows(data: model.TitleModel, prefix: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for title in sorted(data.live_titles):
        out.append((title, f"{title}_adj"))
    for bookmark in data.bookmarks:
        if bookmark.name:
            out.append((bookmark.name.strip('"'), bookmark.id))
        if bookmark.desc:
            out.append((bookmark.desc.strip('"'), f"{bookmark.id}_desc"))
        for character in bookmark.characters:
            if character.name:
                out.append(
                    (
                        character.name.strip('"'),
                        f"bookmark_{prefix}_{character.ck2_id}",
                    )
                )
    return [(a, b) for a, b in out if a and b and a != b]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(ROOT / "configs" / "faerun.toml"))
    ap.add_argument(
        "--out", default=str(ROOT / "mappings" / "loc_key_renames_titles.csv")
    )
    args = ap.parse_args()
    config = Config.load(args.config)
    data = model.build(
        ck2_mod=config.ck2_mod,
        definition_csv=config.out / "map_data" / "definition.csv",
        province_id_map=ROOT / "docs" / "evidence" / "province_id_map.csv",
        government_map_csv=ROOT / "mappings" / "government_map.csv",
        bookmark_date=config.bookmark_date,
        barony_set_csv=ROOT / "docs" / "evidence" / "barony_set.csv",
        prefix=config.prefix,
    )
    table = rows(data, config.prefix)
    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(HEADER)
        writer.writerows(table)
    print(f"{len(table)} rows -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
