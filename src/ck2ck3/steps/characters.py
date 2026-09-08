"""Step ``characters``: CK2 ``history/characters`` -> CK3 ``history/characters``.

All 18124 Faerûn characters, one CK3 file per CK2 file so the mod's id-range
grouping survives. Conversion rules live in :mod:`ck2ck3.port.characters` and
are driven by ``mappings/character_effects.csv``; this module is the I/O and
the reporting.

Runs after ``dynasties``: it reads ``ctx.data["dynasties"]["ck3_ids"]`` for the
referential check. When it runs alone (``--steps characters``) the dynasty set
is read straight from the CK2 files instead, so the check never silently
degrades into a pass.
"""

from __future__ import annotations

from ..context import Context, StepResult
from ..pdx import Block, Node
from ..port import integrity
from ..port.characters import CharacterPort, convert_character_file, output_name
from ..port.evidence import write_csv
from ..port.tables import load_tables

DESCRIPTION = "convert history/characters (18k Faerun characters, field by field)"
OUTPUTS: tuple[str, ...] = ("history/characters",)

DROPPED_EVIDENCE = "docs/evidence/characters_dropped_keys.csv"
INTEGRITY_EVIDENCE = "docs/evidence/characters_integrity.csv"


def run(ctx: Context) -> StepResult:
    source_dir = ctx.ck2("history", "characters")
    files = sorted(source_dir.glob("*.txt"))
    if not files:
        return StepResult(
            summary=f"no CK2 character files under {source_dir}", skipped=True
        )

    tables = load_tables()
    if not tables.trait_id_map_present:
        ctx.info(
            "mappings/trait_id_map.csv absent (traits lane not landed): "
            "trait ids are passed through unchanged"
        )
    port = CharacterPort(tables=tables, prefix=ctx.config.prefix)

    written = []
    for path in files:
        doc = ctx.parse_path(path)
        block = convert_character_file(doc, port, source=path.name)
        rel = f"history/characters/{output_name(path.name, ctx.config.prefix)}"
        ctx.info(f"{path.name}: {len(block)} characters -> {rel}")
        written.append(
            ctx.write_script(rel, block, source=f"history/characters/{path.name}")
        )

    dynasty_ids = _dynasty_ids(ctx)
    result = integrity.check(
        port.facts, dynasty_ids, set(tables.known_traits.values())
    )
    step_warnings = [f"integrity {line}" for line in result.summary_lines()]
    step_warnings += port.report.warnings
    for warning in step_warnings:
        ctx.warn(warning)

    counts = dict(port.report.counts)
    counts["files"] = len(files)
    counts["dynasties_referenced"] = len(
        {f.dynasty for f in port.facts.values() if f.dynasty}
    )
    for kind, n in result.counts.items():
        counts[f"integrity_{kind.replace(' ', '_')}"] = n

    write_csv(
        ctx,
        DROPPED_EVIDENCE,
        ("ck2_key", "level", "reason", "occurrences"),
        sorted(
            ((key, level, reason, n) for (key, level, reason), n in port.report.dropped.items()),
            key=lambda row: (-int(row[3]), row[0]),
        ),
    )
    write_csv(
        ctx,
        INTEGRITY_EVIDENCE,
        ("kind", "occurrences", "examples"),
        sorted(
            (
                (kind, n, "; ".join(i.detail for i in result.issues if i.kind == kind))
                for kind, n in result.counts.items()
            ),
            key=lambda row: -int(row[1]),
        ),
    )

    ctx.data["characters"] = {
        "id_map": dict(port.id_map),
        "integrity": {k: int(v) for k, v in result.counts.items()},
    }

    dropped_total = sum(port.report.dropped.values())
    return StepResult(
        summary=(
            f"{port.report.counts['characters']} characters in {len(files)} files, "
            f"{port.report.counts['dated_blocks']} dated blocks, "
            f"{dropped_total} CK2 entries commented out, "
            f"{sum(result.counts.values())} integrity problems"
        ),
        counts=counts,
        warnings=step_warnings,
        written=written,
    )


def _dynasty_ids(ctx: Context) -> set[str]:
    """The CK3 dynasty ids, from the dynasties step or from CK2 directly."""
    handoff = ctx.data.get("dynasties")
    if handoff and handoff.get("ck3_ids"):
        return set(handoff["ck3_ids"])
    from ..port.common import fae_id

    ids: set[str] = set()
    for path in sorted(ctx.ck2("common", "dynasties").glob("*.txt")):
        doc = ctx.parse_path(path)
        ids.update(
            fae_id(e.key, ctx.config.prefix)
            for e in doc.entries
            if isinstance(e, Node) and isinstance(e.value, Block)
        )
    ctx.info(f"dynasties step did not run; read {len(ids)} dynasty ids from CK2")
    return ids
