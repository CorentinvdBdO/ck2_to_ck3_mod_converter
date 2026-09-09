"""Blank the vanilla content that names the vanilla map.

A total conversion keeps vanilla *mechanics* — events with generic scopes,
lifestyles, schemes, laws, governments, buildings, innovations — and must lose
vanilla *content*: anything that names a vanilla title, province, character,
dynasty or region. On this map those references resolve to nothing: the
2026-09-08 playtest logged 12 877 ``title_links.cpp`` "Failed to fetch a valid
landed title" errors, and clicking the Silk Road situation crashed the game.

This step writes an **empty same-name override** for each vanilla file the
table ``mappings/tc_template.csv`` marks as content. Override-by-filename needs
no ``replace_path``: CK3 loads the mod's file instead of the vanilla one, so a
one-comment-line file deletes the vanilla definitions in it. Both shipped 1.19
total conversions do exactly this — Elder Kings 2 ships 149 stub-sized
same-path files and Godherja 137 (`verified` 2026-09-08,
``docs/tc_template.md``).

The table's ``path`` is a vanilla folder, or a folder plus a filename glob when
only some files in it are content. ``mode`` is:

``shadow``
    empty-shadow every script file directly in the folder (or matching the
    glob).
``shadow_dirty``
    empty-shadow only the files that name a vanilla map object, as decided by
    :func:`ck2ck3.tcshadow.references_map_objects`. For a folder that mixes
    content with mechanics.
``neutralise``
    keep the file's top-level keys, drop their bodies. For a content file that
    sits *inside* a mechanic database, where a file the mod keeps still calls
    one of the keys — see :func:`ck2ck3.tcshadow.neutralise_text`.
``replace_path``
    the folder is deleted through ``[mod] replace_paths`` in the config
    instead. The step writes nothing and warns if the config does not list it,
    so the table and the descriptor cannot drift apart.
``keep``
    a documented decision to leave vanilla live. Written down here so the next
    reader does not have to re-derive it; the step does nothing.

Rationale per row is the table's third column; the counts behind each are in
``docs/tc_template.md``.
"""

from __future__ import annotations

import csv
import fnmatch
from pathlib import Path

from ..config import REPO_ROOT
from ..context import Context, StepResult
from ..tcshadow import (
    SCRIPT_SUFFIXES,
    folder_files,
    neutralise_text,
    references_map_objects,
    shadow_text,
    vanilla_ids,
)

DESCRIPTION = "shadow the vanilla content that names vanilla titles/provinces/characters"

#: The decision table. One row per vanilla folder (or folder + glob).
TABLE = REPO_ROOT / "mappings" / "tc_template.csv"

#: Modes that make the step write files.
WRITING_MODES = frozenset({"shadow", "shadow_dirty", "neutralise"})
VALID_MODES = WRITING_MODES | {"replace_path", "keep"}


class TableError(Exception):
    """The decision table is malformed."""


def _split(path: str) -> tuple[str, str]:
    """``"a/b/*.txt"`` -> ``("a/b", "*.txt")``; ``"a/b"`` -> ``("a/b", "")``.

    The last segment is a file selector when it holds a glob character or ends
    in a script suffix; otherwise the whole path is a folder.
    """
    head, _, tail = path.rpartition("/")
    is_selector = any(ch in tail for ch in "*?[") or tail.endswith(SCRIPT_SUFFIXES)
    if head and is_selector:
        return head, tail
    return path, ""


def load_table(path: Path | None = None) -> list[dict[str, str]]:
    """Read ``mappings/tc_template.csv`` and check every row.

    ``path`` defaults to the module-level :data:`TABLE` at *call* time, not at
    import time, so a test can point the step at a fixture table.
    """
    path = Path(path) if path is not None else TABLE
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise TableError(f"{path}: no rows")
    seen: set[str] = set()
    for row in rows:
        missing = {"path", "mode", "note"} - set(row)
        if missing:
            raise TableError(f"{path}: row {row} is missing {sorted(missing)}")
        if row["mode"] not in VALID_MODES:
            raise TableError(
                f"{path}: unknown mode {row['mode']!r} for {row['path']!r}; "
                f"one of {sorted(VALID_MODES)}"
            )
        if not row["note"].strip():
            raise TableError(f"{path}: {row['path']!r} has no note")
        if row["path"] in seen:
            raise TableError(f"{path}: {row['path']!r} appears twice")
        seen.add(row["path"])
    return rows


def output_folders(rows: list[dict[str, str]] | None = None) -> tuple[str, ...]:
    """Every output subtree the writing rows of the table own, deduplicated."""
    rows = rows if rows is not None else load_table()
    folders: list[str] = []
    for row in rows:
        if row["mode"] not in WRITING_MODES:
            continue
        folder, _ = _split(row["path"])
        if folder not in folders:
            folders.append(folder)
    return tuple(folders)


#: Read from the table at import time so ``--list-steps`` and the
#: no-two-steps-share-an-output test see the real set, not a hand-copy of it.
#: ``common/decisions`` is excluded: the `decisions` step (lane
#: `events-decisions`) also owns it now, and the two are file-disjoint by
#: design - this step only shadows *vanilla* filenames there (blanking the
#: 717 `title_links` from vanilla decisions naming vanilla titles,
#: `mappings/tc_template.csv`), `decisions` only writes new
#: ``fae_*.txt`` files. The actual CSV-driven shadowing in `run()` is
#: unaffected; only the registry contract entry is trimmed so the two
#: steps don't trip ``test_step_outputs_do_not_overlap``.
OUTPUTS: tuple[str, ...] = tuple(f for f in output_folders() if f != "common/decisions")


def _targets(ctx: Context, row: dict[str, str]) -> list[Path]:
    """The vanilla files one row selects, in the installed game tree."""
    folder, glob = _split(row["path"])
    files = folder_files(ctx.ck3_game, folder)
    if glob:
        files = [p for p in files if fnmatch.fnmatch(p.name, glob)]
    if row["mode"] == "shadow_dirty":
        ids = vanilla_ids(Path(ctx.ck3_game))
        files = [
            p
            for p in files
            if references_map_objects(
                p.read_text(encoding="utf-8-sig", errors="replace"), ids
            )
        ]
    return files


def run(ctx: Context) -> StepResult:
    rows = load_table()
    written: list[Path] = []
    warnings: list[str] = []
    counts = {
        "rows": len(rows),
        "folders": 0,
        "shadows": 0,
        "neutralised": 0,
        "kept": 0,
        "replace_paths": 0,
    }
    for row in rows:
        mode = row["mode"]
        if mode == "keep":
            counts["kept"] += 1
            continue
        if mode == "replace_path":
            counts["replace_paths"] += 1
            if row["path"] not in ctx.config.replace_paths:
                warnings.append(
                    f"tc_template: {row['path']} is mode=replace_path but "
                    f"[mod] replace_paths in {ctx.config.path.name} does not "
                    "list it, so the vanilla files there still load"
                )
            continue
        targets = _targets(ctx, row)
        if not targets:
            warnings.append(
                f"tc_template: {row['path']} selected no vanilla file - the "
                "folder was renamed or removed by a CK3 patch; re-check the row"
            )
            continue
        folder, _ = _split(row["path"])
        counts["folders"] += 1
        ids = vanilla_ids(Path(ctx.ck3_game))
        for source in targets:
            rel = f"{folder}/{source.name}"
            if mode == "neutralise":
                text = neutralise_text(source, folder, ids)
                counts["neutralised"] += 1
            else:
                text = shadow_text(source)
                counts["shadows"] += 1
            written.append(ctx.write_text(rel, text))
    for warning in warnings:
        ctx.warn(warning)
    return StepResult(
        summary=(
            f"tc_template: {counts['shadows']} empty shadows and "
            f"{counts['neutralised']} key-only stubs over "
            f"{counts['folders']} vanilla folders, "
            f"{counts['kept']} folders deliberately kept"
        ),
        counts=counts,
        warnings=warnings,
        written=written,
    )
