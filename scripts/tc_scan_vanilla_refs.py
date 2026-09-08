#!/usr/bin/env python3
"""Inventory every vanilla CK3 script folder for references to the vanilla map.

For lane `tc-template`. A total conversion deletes vanilla titles, provinces,
characters and regions; any vanilla script still naming one is live content
that resolves to nothing. This script measures, per folder:

* how many files there are, and how many name a vanilla map object;
* how many references of each class (title tag, ``province:N``, ``character:N``,
  ``dynasty:N``, ``geographical_region =``, a vanilla culture/faith/religion id);
* what Atlantis, Elder Kings 2 and Godherja do with that folder
  (``replace_path``, and how many same-name shadow files they ship).

Title/culture/faith ids are not guessed from a regex shape: the id sets are read
out of vanilla itself (``common/landed_titles``, ``common/culture/cultures``,
``common/religion/religions``), so ``k_from_dynasty`` (a real script token that
is not a title) never counts and ``h_india`` (a title whose tier letter is not
in the usual five) does.

Writes ``docs/evidence/tc_template_folders.csv``.

    uv run scripts/tc_scan_vanilla_refs.py [--game DIR] [--out CSV]
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_GAME = Path(
    "/home/cvdbdo/.local/share/Steam/steamapps/common/Crusader Kings III/game"
)
MODS = {
    "ATL": REPO_ROOT.parent
    / ".."  # placeholder, overridden by --atlantis
    ,
    "EK2": Path(
        "/home/cvdbdo/.local/share/Steam/steamapps/workshop/content/1158310/2887120253"
    ),
    "GH": Path(
        "/home/cvdbdo/.local/share/Steam/steamapps/workshop/content/1158310/2326030123"
    ),
}

#: Roots of the vanilla tree this inventory covers.
ROOTS = (
    "common",
    "events",
    "history",
    "gui",
    "gfx/map/map_object_data",
    "gfx/portraits/portrait_modifiers",
    "gfx/court_scene",
    "gfx/interface/illustrations/scripted_illustrations",
    "map_data/geographical_regions",
    "tests",
)

SCRIPT_SUFFIXES = {".txt", ".gui", ".info", ".asset"}

TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
PROVINCE_RE = re.compile(r"\bprovince:\d+")
CHARACTER_RE = re.compile(r"\bcharacter:\d+")
DYNASTY_RE = re.compile(r"\bdynasty:\d+")
GEO_REGION_RE = re.compile(r"\bgeographical_region\s*=")
TITLE_SCOPE_RE = re.compile(r"\btitle:([A-Za-z_][A-Za-z0-9_]*)")
COMMENT_RE = re.compile(r"#.*")


def _ids_from_blocks(root: Path, pattern: str) -> set[str]:
    """Every top-of-block key in ``root``'s files matching ``pattern``."""
    rx = re.compile(pattern, re.MULTILINE)
    found: set[str] = set()
    if not root.is_dir():
        return found
    for path in sorted(root.rglob("*.txt")):
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        found.update(rx.findall(text))
    return found


def vanilla_title_ids(game: Path) -> set[str]:
    return _ids_from_blocks(
        game / "common" / "landed_titles",
        r"^\s*([behkdcb]_[A-Za-z0-9_]+)\s*=\s*\{",
    )


def vanilla_culture_ids(game: Path) -> set[str]:
    return _ids_from_blocks(
        game / "common" / "culture" / "cultures", r"^([a-z][a-z0-9_]*)\s*=\s*\{"
    )


def vanilla_faith_ids(game: Path) -> set[str]:
    """Faith and religion ids, from ``common/religion/religion_types``.

    The 1.19 folder is ``religion_types``; ``common/religion/religions`` (the
    path Atlantis neutralises) has not existed since 1.16 — `verified`.
    """
    root = game / "common" / "religion" / "religion_types"
    found: set[str] = set()
    if not root.is_dir():
        return found
    top = re.compile(r"^([a-z][a-z0-9_]*)\s*=\s*\{", re.MULTILINE)
    faith = re.compile(r"^\t\t([a-z][a-z0-9_]*)\s*=\s*\{", re.MULTILINE)
    for path in sorted(root.rglob("*.txt")):
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        found.update(top.findall(text))
        found.update(faith.findall(text))
    return found


def strip_comments(text: str) -> str:
    return COMMENT_RE.sub("", text)


def scan_file(
    text: str,
    titles: set[str],
    cultures: set[str],
    faiths: set[str],
) -> Counter[str]:
    """Count references of each class in one file's text (comments stripped)."""
    counts: Counter[str] = Counter()
    counts["province"] = len(PROVINCE_RE.findall(text))
    counts["character"] = len(CHARACTER_RE.findall(text))
    counts["dynasty"] = len(DYNASTY_RE.findall(text))
    counts["geo_region"] = len(GEO_REGION_RE.findall(text))
    counts["title_scope"] = sum(
        1 for tag in TITLE_SCOPE_RE.findall(text) if tag in titles
    )
    bare_titles = 0
    culture_refs = 0
    faith_refs = 0
    for token in TOKEN_RE.findall(text):
        if token in titles:
            bare_titles += 1
        elif token in cultures:
            culture_refs += 1
        elif token in faiths:
            faith_refs += 1
    # `title:x` tokens are also counted by the bare pass; report the bare class
    # net of them so the two do not double count.
    counts["title_bare"] = max(0, bare_titles - counts["title_scope"])
    counts["culture"] = culture_refs
    counts["faith"] = faith_refs
    counts["map_refs"] = (
        counts["province"]
        + counts["character"]
        + counts["dynasty"]
        + counts["geo_region"]
        + counts["title_scope"]
        + counts["title_bare"]
    )
    return counts


def folders_of(root: Path, prefix: str) -> dict[str, list[Path]]:
    """Every folder under ``root/prefix`` that directly holds a script file."""
    base = root / prefix
    out: dict[str, list[Path]] = {}
    if not base.is_dir():
        return out
    for path in sorted(base.rglob("*")):
        if not path.is_file() or path.suffix not in SCRIPT_SUFFIXES:
            continue
        rel = path.parent.relative_to(root).as_posix()
        out.setdefault(rel, []).append(path)
    return out


#: A shadow this small is a neutralisation stub, not a reimplementation.
#: Calibrated on the two shipped 1.19 total conversions: their stubs are a BOM
#: plus a comment or a handful of empty ``key = {}`` declarations.
STUB_BYTES = 400


def mod_facts(mod: Path) -> tuple[set[str], set[str], set[str]]:
    """``(replace_paths, script paths, stub-sized script paths)`` of a mod."""
    replaced: set[str] = set()
    files: set[str] = set()
    stubs: set[str] = set()
    if not mod.is_dir():
        return replaced, files, stubs
    descriptor = mod / "descriptor.mod"
    if descriptor.is_file():
        text = descriptor.read_text(encoding="utf-8-sig", errors="replace")
        replaced = set(re.findall(r'replace_path\s*=\s*"([^"]+)"', text))
    for path in mod.rglob("*"):
        if path.is_file() and path.suffix in SCRIPT_SUFFIXES:
            rel = path.relative_to(mod).as_posix()
            files.add(rel)
            if path.stat().st_size < STUB_BYTES:
                stubs.add(rel)
    return replaced, files, stubs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game", type=Path, default=DEFAULT_GAME)
    parser.add_argument("--atlantis", type=Path, default=None)
    parser.add_argument(
        "--out",
        type=Path,
        default=REPO_ROOT / "docs" / "evidence" / "tc_template_folders.csv",
    )
    args = parser.parse_args(argv)

    game = args.game
    if not game.is_dir():
        print(f"game folder not found: {game}", file=sys.stderr)
        return 2

    titles = vanilla_title_ids(game)
    cultures = vanilla_culture_ids(game)
    faiths = vanilla_faith_ids(game)
    print(
        f"vanilla ids: {len(titles)} titles, {len(cultures)} cultures, "
        f"{len(faiths)} faiths/religions",
        file=sys.stderr,
    )

    mods = dict(MODS)
    if args.atlantis:
        mods["ATL"] = args.atlantis
    else:
        mods.pop("ATL", None)
    mod_data = {name: mod_facts(path) for name, path in mods.items()}

    rows: list[dict[str, object]] = []
    for prefix in ROOTS:
        for rel, paths in sorted(folders_of(game, prefix).items()):
            total = Counter()
            hit_files = 0
            for path in paths:
                text = strip_comments(
                    path.read_text(encoding="utf-8-sig", errors="replace")
                )
                counts = scan_file(text, titles, cultures, faiths)
                if counts["map_refs"]:
                    hit_files += 1
                total.update(counts)
            row: dict[str, object] = {
                "folder": rel,
                "files": len(paths),
                "files_with_map_refs": hit_files,
                "title_scope": total["title_scope"],
                "title_bare": total["title_bare"],
                "province": total["province"],
                "character": total["character"],
                "dynasty": total["dynasty"],
                "geo_region": total["geo_region"],
                "culture": total["culture"],
                "faith": total["faith"],
                "map_refs": total["map_refs"],
            }
            names = {p.name for p in paths}
            for name, (replaced, files, stubs) in mod_data.items():
                row[f"{name}_replace_path"] = int(rel in replaced)
                row[f"{name}_shadows"] = sum(
                    1 for n in names if f"{rel}/{n}" in files
                )
                row[f"{name}_stubs"] = sum(1 for n in names if f"{rel}/{n}" in stubs)
            rows.append(row)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    dirty = sum(1 for r in rows if r["map_refs"])
    print(
        f"{len(rows)} folders, {dirty} with at least one vanilla map reference "
        f"-> {args.out}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
