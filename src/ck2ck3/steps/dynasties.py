"""Step ``dynasties``: CK2 ``common/dynasties`` -> CK3 dynasties + their loc.

Owns three output subtrees:

* ``common/dynasties`` — one CK3 file per CK2 file, ``fae_`` on the filename.
* ``common/dynasty_houses`` — deliberately left empty; CK2 has no cadet houses
  and characters may reference a ``dynasty`` directly. Owned here so no other
  lane can claim it (see ``docs/step_characters.md``).
* ``localization/english/fae_dynasties_l_english.yml`` — the CK2 literal names,
  which only exist inside ``common/dynasties`` and would otherwise be lost.

The step also hands ``ctx.data["dynasties"]`` the CK2->CK3 id map so the
``characters`` step can check every ``dynasty =`` reference.
"""

from __future__ import annotations

from pathlib import Path

from ..context import Context, StepResult
from ..port.dynasties import (
    LOC_PREFIX,
    DynastyPort,
    convert_dynasty_file,
    dynasty_ids,
    output_name,
)
from ..pdx import Document
from ..port.evidence import write_csv
from ..port.loc_hash import keys_in_folder, resolve_collisions

DESCRIPTION = "convert common/dynasties (ids, names -> loc keys, drop CK2 CoAs)"
OUTPUTS: tuple[str, ...] = (
    "common/dynasties",
    "common/dynasty_houses",
    "localization/english/fae_dynasties_l_english.yml",
)

LOC_FILE = "localization/english/fae_dynasties_l_english.yml"
COA_EVIDENCE = "docs/evidence/dynasty_coa_dropped.csv"
RENAME_TABLE = "mappings/loc_key_renames_characters.csv"


def run(ctx: Context) -> StepResult:
    source_dir = ctx.ck2("common", "dynasties")
    files = sorted(source_dir.glob("*.txt"))
    if not files:
        return StepResult(
            summary=f"no CK2 dynasty files under {source_dir}", skipped=True
        )

    # Parse once, then decide the loc keys before writing anything: CK3 hashes
    # localisation keys and a hash collision with a vanilla key silently loses
    # one of them (see ck2ck3.port.loc_hash).
    docs = [(path, ctx.parse_path(path)) for path in files]
    port = DynastyPort(prefix=ctx.config.prefix)
    port.loc_renames = _resolve_loc_collisions(ctx, docs)

    written = []
    for path, doc in docs:
        block = convert_dynasty_file(doc, port)
        rel = f"common/dynasties/{output_name(path.name, ctx.config.prefix)}"
        ctx.info(f"{path.name}: {len(block)} dynasties -> {rel}")
        written.append(
            ctx.write_script(rel, block, source=f"common/dynasties/{path.name}")
        )

    # The one localisation file this step owns: CK3 dynasty names are loc keys.
    written.append(
        ctx.write_loc(
            LOC_FILE,
            sorted(port.loc.items()),
            header_comments=[
                "CK2 common/dynasties stores the dynasty name as a literal string;",
                "CK3 stores a localisation key. These are those literals.",
            ],
        )
    )

    write_csv(
        ctx,
        COA_EVIDENCE,
        ("ck3_dynasty", "ck2_dynasty", "name", "culture", "ck2_coat_of_arms"),
        sorted(port.dropped_coa),
    )
    # The `loc` lane keeps CK2 key names everywhere else; dynasty names are the
    # exception (CK2 has no loc key for them at all), so it needs the new keys.
    write_csv(
        ctx,
        RENAME_TABLE,
        ("ck3_loc_key", "ck2_source", "ck2_value", "note"),
        [
            (key, "common/dynasties name (literal, no CK2 loc key)", value, "new key")
            for key, value in sorted(port.loc.items())
        ],
    )

    for warning in port.report.warnings:
        ctx.warn(warning)

    counts = dict(port.report.counts)
    for (key, _level, _reason), n in port.report.dropped.items():
        counts[f"dropped_{key}"] = counts.get(f"dropped_{key}", 0) + n
    counts["loc_keys"] = len(port.loc)
    counts["loc_key_collisions"] = len(port.loc_renames)

    ctx.data["dynasties"] = {
        "id_map": dict(port.id_map),
        "loc": dict(port.loc),
        "ck3_ids": set(port.id_map.values()),
        # CK2 culture -> its dynasty-name loc keys. The `cultures` step puts
        # these in each name list's `dynasty_names`; without them CK3 logs
        # `culture_name_lists.cpp:169 ... less than MINIMUM_DYNASTY_NAMES` for
        # every one of the 419 name lists and has no name to mint a generated
        # character's dynasty from.
        "names_by_culture": {
            culture: list(keys)
            for culture, keys in port.names_by_culture.items()
        },
    }

    return StepResult(
        summary=(
            f"{port.report.counts['dynasties']} dynasties in {len(files)} files, "
            f"{len(port.loc)} name loc keys, "
            f"{len(port.dropped_coa)} CK2 coats of arms dropped"
        ),
        counts=counts,
        warnings=list(port.report.warnings),
        written=written,
    )


def _resolve_loc_collisions(
    ctx: Context, docs: list[tuple[Path, Document]]
) -> dict[str, str]:
    """Rename the ``dynn_fae_*`` keys that clash with a vanilla key's hash.

    CK3 keys localisation by MURMUR3A and a collision silently drops one of the
    two entries. 11951 mechanically generated keys hit two vanilla keys on the
    first run, so this is checked rather than hoped for.
    """
    vanilla = keys_in_folder(ctx.ck3("localization", "english"))
    if not vanilla:
        ctx.warn(
            "CK3 localisation not readable; dynasty loc keys were not checked "
            "for MURMUR3A collisions with vanilla"
        )
        return {}
    prefix = ctx.config.prefix
    # dict.fromkeys: one key per CK3 id, so a CK2 id defined twice (Faerûn's
    # dynasty 15817) does not look like a collision with itself.
    keys = list(
        dict.fromkeys(
            f"{LOC_PREFIX}_{prefix}_{ck2_id}"
            for _path, doc in docs
            for ck2_id in dynasty_ids(doc)
        )
    )
    renames = resolve_collisions(keys, vanilla)
    for original, replacement in sorted(renames.items()):
        ctx.warn(
            f"loc key {original} collides with a vanilla key's MURMUR3A hash; "
            f"renamed to {replacement}"
        )
    ctx.info(f"checked {len(keys)} loc keys against {len(vanilla)} vanilla keys")
    return renames
