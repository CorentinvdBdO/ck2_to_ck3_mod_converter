#!/usr/bin/env python3
"""Verify that every CK3 token claimed by the `mappings/*_fields.csv` and
`mappings/government_map.csv` tables actually exists in the CK3 1.19 game files.

Reads the CK3 column of each mapping table, splits it into tokens, and searches
`game/common/**` and `game/history/**` for each token. A token found only inside
a `*.info` file is reported as `info_only` (documented by Paradox, unused by
vanilla) — that is still evidence, but weaker than a live usage.

Output: docs/evidence/ck3_world_keys.csv  (one row per token)
        docs/evidence/ck3_world_keys_summary.txt

Exit code 1 if any token claimed with status exact/approx is not found at all.

Usage:
    uv run scripts/verify_ck3_world_keys.py [--game <path to CK3 game dir>]
"""
from __future__ import annotations

import argparse
import csv
import os
import re
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEFAULT_GAME = REPO.parent / "claudespace" / "game_files"

# Tables and the column that holds the CK3 tokens.
# table -> the columns whose CK3 tokens must exist in the game files
TABLES = {
    "mappings/culture_fields.csv": ["ck3_key", "default_when_none"],
    "mappings/religion_fields.csv": ["ck3_key", "default_when_none"],
    "mappings/government_map.csv": ["ck3_government", "succession_law_to_emit"],
    "mappings/title_fields.csv": ["ck3_key", "default_when_none"],
    "mappings/character_fields.csv": ["ck3_key", "default_when_none"],
}

VERIFIABLE_STATUS = {"exact", "approx"}

# `<placeholder>` spans and parenthesised prose are notes, not identifiers.
PLACEHOLDER = re.compile(r"<[^>]*>")
PARENS = re.compile(r"\([^)]*\)")
# Tokens that are structural notes rather than script identifiers.
SKIP_TOKEN = re.compile(r"^(?:-|n/a|none|\d+|yes|no)$", re.I)
# English words that appear in prose cells and are not CK3 identifiers.
STOPWORDS = {
    "a", "an", "and", "any", "anyway", "appropriate", "are", "as", "be", "block",
    "bookmark", "but", "by", "do", "each", "emit", "engine", "for", "from", "houses",
    "if", "in", "inherit", "is", "it", "its", "not", "of", "omit", "on", "one",
    "or", "per", "plausible", "see", "set", "the", "then", "to", "was", "when",
    "whenever", "with", "unnamed", "legal", "empty", "absent", "key", "keys",
    "tags", "more_tags",
}
TOKEN_SPLIT = re.compile(r"[\s;,]+")
# A token may be written as `key`, `key = value`, `block.key`, or `file:key`.
CLEAN = re.compile(r"^[\"'`]|[\"'`]$")

SEARCH_DIRS = ("common", "history")
TEXT_EXT = {".txt", ".info"}


def iter_game_files(game: Path):
    for d in SEARCH_DIRS:
        root = game / d
        if not root.is_dir():
            continue
        for dirpath, _dirnames, filenames in os.walk(root):
            for fn in filenames:
                if Path(fn).suffix in TEXT_EXT:
                    yield Path(dirpath) / fn


def build_index(game: Path):
    """token -> list of (relpath, lineno, is_info). Index words once, search many."""
    index: dict[str, list[tuple[str, int, bool]]] = {}
    word = re.compile(r"[A-Za-z_][A-Za-z_0-9]*")
    for path in iter_game_files(game):
        rel = str(path.relative_to(game))
        is_info = path.suffix == ".info"
        try:
            with open(path, encoding="utf-8-sig", errors="replace") as fh:
                for lineno, line in enumerate(fh, 1):
                    for w in set(word.findall(line)):
                        hits = index.setdefault(w, [])
                        if len(hits) < 4096:
                            hits.append((rel, lineno, is_info))
        except OSError as exc:  # pragma: no cover
            print(f"warn: {path}: {exc}", file=sys.stderr)
    return index


def tokens_of(cell: str):
    out = []
    cell = PARENS.sub(" ", PLACEHOLDER.sub(" ", cell or ""))
    for raw in TOKEN_SPLIT.split(cell):
        tok = CLEAN.sub("", raw.strip())
        # `key=value` -> both halves are interesting; keep the bare identifier.
        tok = tok.split("=")[0].strip()
        tok = tok.strip("{}()[]<>.")
        if not tok or SKIP_TOKEN.match(tok) or tok.lower() in STOPWORDS:
            continue
        if not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", tok):
            continue
        # A dangling fragment left behind by removing a <placeholder>, e.g.
        # "heritage_fae_<group>" -> "heritage_fae_", "<faith_id>_adherent" -> "_adherent".
        if tok.startswith("_") or tok.endswith("_"):
            continue
        # Placeholder title/example ids such as c_x, b_y, c_id.
        if re.fullmatch(r"[ekdcbh]_(?:x|y|z|id|name|foo|bar)", tok):
            continue
        out.append(tok)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", default=str(DEFAULT_GAME))
    ap.add_argument("--out", default=str(REPO / "docs" / "evidence"))
    args = ap.parse_args()

    game = Path(args.game).resolve()
    if not (game / "common").is_dir():
        print(f"error: {game} does not look like a CK3 game dir", file=sys.stderr)
        return 2

    print(f"indexing {game} ...", file=sys.stderr)
    index = build_index(game)
    print(f"indexed {len(index)} distinct identifiers", file=sys.stderr)

    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    rows = []
    missing = []
    stats = Counter()

    for table, cols in TABLES.items():
        path = REPO / table
        if not path.exists():
            print(f"warn: {table} missing, skipped", file=sys.stderr)
            continue
        with open(path, encoding="utf-8", newline="") as fh:
            for rec in csv.DictReader(fh):
                status = (rec.get("status") or "").strip().lower()
                stats[f"{Path(table).name}:{status or 'blank'}"] += 1
                toks = []
                for col in cols:
                    if col not in rec:
                        print(f"warn: {table} has no column {col}", file=sys.stderr)
                        continue
                    for t in tokens_of(rec[col]):
                        if t not in toks:
                            toks.append((t, col))
                seen = set()
                for tok, col in [t if isinstance(t, tuple) else (t, cols[0]) for t in toks]:
                    if (tok, col) in seen:
                        continue
                    seen.add((tok, col))
                    hits = index.get(tok, [])
                    live = [h for h in hits if not h[2]]
                    info = [h for h in hits if h[2]]
                    if live:
                        verdict = "found"
                        ev = f"{live[0][0]}:{live[0][1]}"
                    elif info:
                        verdict = "info_only"
                        ev = f"{info[0][0]}:{info[0][1]}"
                    else:
                        verdict = "MISSING"
                        ev = ""
                    rows.append({
                        "table": Path(table).name,
                        "ck2_key": rec.get("ck2_key") or rec.get("ck2_government") or "",
                        "column": col,
                        "status": status,
                        "token": tok,
                        "verdict": verdict,
                        "live_hits": len(live),
                        "info_hits": len(info),
                        "evidence": ev,
                    })
                    if verdict == "MISSING" and status in VERIFIABLE_STATUS:
                        missing.append((Path(table).name, rec.get("ck2_key", ""), tok))

    csv_out = outdir / "ck3_world_keys.csv"
    with open(csv_out, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=[
            "table", "ck2_key", "column", "status", "token", "verdict",
            "live_hits", "info_hits", "evidence"])
        w.writeheader()
        w.writerows(rows)

    verdicts = Counter(r["verdict"] for r in rows)
    lines = [
        f"CK3 game dir: {game}",
        f"tokens checked: {len(rows)}",
        "",
        "verdicts:",
    ]
    for k, v in verdicts.most_common():
        lines.append(f"  {k:10s} {v}")
    lines += ["", "rows per table and status:"]
    for k, v in sorted(stats.items()):
        lines.append(f"  {k:44s} {v}")
    if missing:
        lines += ["", "MISSING tokens on exact/approx rows:"]
        for t, k, tok in missing:
            lines.append(f"  {t}: {k} -> {tok}")
    else:
        lines += ["", "no MISSING tokens on exact/approx rows."]
    summary = "\n".join(lines) + "\n"
    (outdir / "ck3_world_keys_summary.txt").write_text(summary, encoding="utf-8")
    print(summary)
    print(f"wrote {csv_out}")
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
