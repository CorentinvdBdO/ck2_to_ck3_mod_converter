"""Inventory every key used in Faerûn's history/characters and common/dynasties.

Writes docs/evidence/characters_key_tally.csv (key, level, uses) and prints the
CK3-side vocabularies (death reasons, nicknames) so the mapping tables in
`ck2ck3/steps/characters/` can be checked against the real game files.

Run: uv run scripts/survey_characters.py
"""

from __future__ import annotations

import csv
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ck2ck3.pdx import parse_file  # noqa: E402
from ck2ck3.pdx.nodes import Block, Node  # noqa: E402
from ck2ck3.pdx.tokens import Date  # noqa: E402

CK2 = ROOT / "Faerun" / "Faerun"
CK3 = Path("/home/cvdbdo/.local/share/Steam/steamapps/common/Crusader Kings III/game")


def walk(block: Block, path: str, tally: Counter, values: dict[str, Counter]) -> None:
    for entry in block.entries:
        if not isinstance(entry, Node):
            tally[f"{path}/<item>"] += 1
            continue
        key = "<date>" if isinstance(entry.key, Date) or _is_date(entry.key) else entry.key
        here = f"{path}/{key}" if path else key
        tally[here] += 1
        if isinstance(entry.value, Block):
            walk(entry.value, here, tally, values)
        else:
            values.setdefault(here, Counter())[str(entry.value)] += 1


def _is_date(text: str) -> bool:
    parts = str(text).split(".")
    return len(parts) == 3 and all(p.isdigit() for p in parts)


def main() -> int:
    tally: Counter = Counter()
    values: dict[str, Counter] = {}
    chars = 0
    for path in sorted((CK2 / "history" / "characters").glob("*.txt")):
        doc = parse_file(path)
        for entry in doc.entries:
            if isinstance(entry, Node) and isinstance(entry.value, Block):
                chars += 1
                walk(entry.value, "", tally, values)
    dyn = 0
    dtally: Counter = Counter()
    dvalues: dict[str, Counter] = {}
    for path in sorted((CK2 / "common" / "dynasties").glob("*.txt")):
        doc = parse_file(path)
        for entry in doc.entries:
            if isinstance(entry, Node) and isinstance(entry.value, Block):
                dyn += 1
                walk(entry.value, "", dtally, dvalues)

    out = ROOT / "docs" / "evidence" / "characters_key_tally.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["scope", "key_path", "uses", "distinct_values", "sample_values"])
        for key, n in sorted(tally.items(), key=lambda kv: -kv[1]):
            vs = values.get(key, Counter())
            w.writerow([
                "characters", key, n, len(vs),
                " | ".join(v for v, _ in vs.most_common(6)),
            ])
        for key, n in sorted(dtally.items(), key=lambda kv: -kv[1]):
            vs = dvalues.get(key, Counter())
            w.writerow([
                "dynasties", key, n, len(vs),
                " | ".join(v for v, _ in vs.most_common(6)),
            ])
    print(f"characters={chars} dynasties={dyn} -> {out}")

    # CK3 vocabularies
    for name, sub in (("death reasons", "common/deathreasons"), ("nicknames", "common/nicknames")):
        ids: set[str] = set()
        for path in sorted((CK3 / sub).glob("*.txt")):
            doc = parse_file(path)
            ids.update(e.key for e in doc.entries if isinstance(e, Node))
        print(f"ck3 {name}: {len(ids)}")
        (ROOT / "docs" / "evidence" / f"ck3_{sub.split('/')[-1]}.txt").write_text(
            "\n".join(sorted(ids)) + "\n", encoding="utf-8"
        )
    for name, sub in (("death reasons", "common/death"), ("nicknames", "common/nicknames")):
        ids = set()
        for path in sorted((CK2 / sub).glob("*.txt")):
            doc = parse_file(path)
            ids.update(e.key for e in doc.entries if isinstance(e, Node))
        print(f"ck2 {name}: {len(ids)}")
        (ROOT / "docs" / "evidence" / f"ck2_{sub.split('/')[-1]}.txt").write_text(
            "\n".join(sorted(ids)) + "\n", encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
