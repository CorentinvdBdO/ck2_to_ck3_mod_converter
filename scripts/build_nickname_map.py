"""Build/refresh mappings/nicknames.csv (CK2 nickname id -> CK3 nickname id).

CK2 and CK3 both key nicknames by id in `common/nicknames`, so an id present
in both games maps 1:1. Faerûn invents 757 of the 837 ids its characters use;
those get `comment` (the converter emits an in-block comment, never a
made-up CK3 id) until someone ports Faerûn's `common/nicknames` too.

Rows already in the CSV are kept verbatim, so hand-curated semantic matches
survive a refresh. Run: uv run scripts/build_nickname_map.py
"""

from __future__ import annotations

import csv
import sys
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
warnings.simplefilter("ignore")

from ck2ck3.pdx import parse_file  # noqa: E402
from ck2ck3.pdx.nodes import Block, Node  # noqa: E402

CK2 = ROOT / "Faerun" / "Faerun"
CK3 = Path("/home/cvdbdo/.local/share/Steam/steamapps/common/Crusader Kings III/game")
OUT = ROOT / "mappings" / "nicknames.csv"
HEADER = ["ck2_nickname", "ck3_nickname", "status", "uses_in_faerun", "note"]


def ids_of(folder: Path) -> set[str]:
    out: set[str] = set()
    for path in sorted(folder.glob("*.txt")):
        out.update(e.key for e in parse_file(path).entries if isinstance(e, Node))
    return out


def used() -> dict[str, int]:
    counts: dict[str, int] = {}

    def walk(block: Block) -> None:
        for entry in block.entries:
            if not isinstance(entry, Node):
                continue
            if entry.key == "give_nickname" and not isinstance(entry.value, bool):
                counts[str(entry.value)] = counts.get(str(entry.value), 0) + 1
            if isinstance(entry.value, Block):
                walk(entry.value)

    for path in sorted((CK2 / "history" / "characters").glob("*.txt")):
        walk(parse_file(path))
    return counts


def main() -> int:
    ck3 = ids_of(CK3 / "common" / "nicknames")
    ck2 = ids_of(CK2 / "common" / "nicknames")
    counts = used()

    kept: dict[str, dict[str, str]] = {}
    if OUT.exists():
        for row in csv.DictReader(OUT.open(encoding="utf-8")):
            kept[row["ck2_nickname"]] = row

    rows = []
    for nick in sorted(counts):
        if nick in kept and kept[nick]["status"] != "auto":
            row = dict(kept[nick])
            row["uses_in_faerun"] = str(counts[nick])
            rows.append(row)
            continue
        if nick in ck3:
            rows.append({
                "ck2_nickname": nick,
                "ck3_nickname": nick,
                "status": "exact",
                "uses_in_faerun": str(counts[nick]),
                "note": "same id in both games",
            })
        else:
            rows.append({
                "ck2_nickname": nick,
                "ck3_nickname": "",
                "status": "comment",
                "uses_in_faerun": str(counts[nick]),
                "note": (
                    "Faerun-invented nickname"
                    if nick in ck2
                    else "not defined in Faerun common/nicknames either"
                ),
            })

    with OUT.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=HEADER)
        writer.writeheader()
        writer.writerows(rows)

    exact = sum(1 for r in rows if r["status"] == "exact")
    print(f"{OUT.relative_to(ROOT)}: {len(rows)} rows, {exact} exact, "
          f"{len(rows) - exact} commented "
          f"(ck2 defines {len(ck2)}, ck3 defines {len(ck3)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
