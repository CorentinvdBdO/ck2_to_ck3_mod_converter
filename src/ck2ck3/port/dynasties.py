"""Convert CK2 ``common/dynasties`` to CK3 ``common/dynasties`` plus its loc.

The one shape change: CK2 stores the dynasty name as a literal string
(``name = "Dlardrageth"``), CK3 stores a localisation key
(``name = "dynn_fae_2"``). So this step also owns
``localization/english/fae_dynasties_l_english.yml`` — it is the only place
the literal survives, and no other lane can write it because no other lane
reads ``common/dynasties``.

Dropped, each with a comment in place:

* ``religion`` (4 uses) — CK3 dynasties have no faith; the characters carry it.
* ``used_for_random`` (754 uses) — CK3 has no random world.
* ``coat_of_arms`` (20 uses) — the CK2 block is numeric indices into CK2's own
  flag atlas and cannot be translated. Listed in
  ``docs/evidence/dynasty_coa_dropped.csv`` so a human can redraw them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..pdx import Block, Document, Item, Node, write
from .common import (
    BlockBuilder,
    PortReport,
    carry_comments,
    fae_id,
    shape_of,
    strip_ck2_markers,
)

#: CK3 localisation key prefix for a dynasty name (vanilla: ``dynn_Orsini``).
LOC_PREFIX = "dynn"

DROPPED = {
    "religion": "CK3 dynasties have no faith field; the characters carry the faith",
    "used_for_random": "CK2 random-world flag; CK3 has no random world",
}


@dataclass
class DynastyPort:
    """Converts dynasty blocks; collects the loc pairs and the dropped CoAs."""

    prefix: str = "fae"
    report: PortReport = field(default_factory=PortReport)
    #: ``dynn_fae_<id>`` -> the CK2 literal name.
    loc: dict[str, str] = field(default_factory=dict)
    #: CK2 id -> CK3 id, for the characters step's referential check.
    id_map: dict[str, str] = field(default_factory=dict)
    #: ``(ck3_id, ck2_id, name, culture, coat_of_arms_script)``.
    dropped_coa: list[tuple[str, str, str, str, str]] = field(default_factory=list)
    #: ``dynn_fae_<id>`` -> a renamed key, for the few whose MURMUR3A hash
    #: collides with a vanilla loc key (see :mod:`ck2ck3.port.loc_hash`).
    loc_renames: dict[str, str] = field(default_factory=dict)

    def loc_key(self, ck2_id: str) -> str:
        key = f"{LOC_PREFIX}_{fae_id(ck2_id, self.prefix)}"
        return self.loc_renames.get(key, key)

    def convert_dynasty(self, node: Node) -> Node:
        ck2_id = str(node.key)
        ck3_id = fae_id(ck2_id, self.prefix)
        if ck2_id in self.id_map:
            # `verified`: Faerûn defines dynasty 15817 twice in
            # Faerun_Dynasties.txt ("Zyxenel" then "Phaethoxoris"). CK2 lets the
            # last one win; CK3 loads both and tiger reports a duplicate. Keep
            # both blocks (nothing is invented) but say so loudly.
            self.report.warn(
                f"CK2 dynasty id {ck2_id} is defined more than once; "
                "CK3 will see a duplicate fae_ id"
            )
            self.report.counts["duplicate_ids"] += 1
        self.id_map[ck2_id] = ck3_id
        body = node.value if isinstance(node.value, Block) else Block()
        out = BlockBuilder()

        name = body.get("name")
        culture = body.get("culture")
        key = self.loc_key(ck2_id)

        for entry in body.entries:
            if isinstance(entry, Item):
                out.comment(f"CK2: bare item {shape_of(entry.value)} (not a CK3 shape)")
                continue
            assert isinstance(entry, Node)
            if entry.key == "name":
                # SHAPE CHANGE: literal -> loc key. The literal goes to the yml.
                self.loc[key] = str(entry.value)
                out.add(
                    carry_comments(
                        entry,
                        Node(
                            key="name",
                            value=key,
                            quoted_value=True,
                            leading_comments=[f'# CK2: name = "{entry.value}"'],
                        ),
                    )
                )
                self.report.counts["names"] += 1
            elif entry.key == "culture":
                out.add(
                    carry_comments(
                        entry, Node(key="culture", value=str(entry.value))
                    )
                )
                self.report.counts["cultures"] += 1
            elif entry.key == "coat_of_arms":
                out.comments(strip_ck2_markers(entry.leading_comments))
                out.comment(
                    f"CK2: coat_of_arms = {shape_of(entry.value)} "
                    "(CK2 numeric sprite indices into CK2's own flag atlas; "
                    "not translatable - see docs/evidence/dynasty_coa_dropped.csv)"
                )
                self.report.drop("coat_of_arms", "dynasty", "CK2 flag atlas indices")
                self.dropped_coa.append(
                    (
                        ck3_id,
                        ck2_id,
                        str(name) if name is not None else "",
                        str(culture) if culture is not None else "",
                        write(Block(entries=[entry]), canonical=True).replace("\n", " ").strip(),
                    )
                )
            elif entry.key in DROPPED:
                out.comments(strip_ck2_markers(entry.leading_comments))
                out.comment(
                    f"CK2: {entry.key} = {shape_of(entry.value)} ({DROPPED[entry.key]})"
                )
                self.report.drop(entry.key, "dynasty", DROPPED[entry.key])
            else:
                out.comments(strip_ck2_markers(entry.leading_comments))
                out.comment(
                    f"CK2: {entry.key} = {shape_of(entry.value)} "
                    "(no row for this key; CK3 common/dynasties takes only "
                    "name / prefix / culture / motto)"
                )
                self.report.drop(entry.key, "dynasty", "unknown CK2 dynasty key")
                self.report.warn(
                    f"unmapped CK2 dynasty key {entry.key!r}; commented out"
                )

        if name is None:
            self.report.warn(f"CK2 dynasty {ck2_id} has no name; CK3 requires one")
            self.report.counts["dynasties_without_name"] += 1
        if culture is None:
            self.report.warn(f"CK2 dynasty {ck2_id} has no culture")
            self.report.counts["dynasties_without_culture"] += 1

        result = Node(key=ck3_id, value=out.finish())
        carry_comments(node, result)
        self.report.counts["dynasties"] += 1
        return result


def dynasty_ids(doc: Document) -> list[str]:
    """The CK2 dynasty ids in one file, in source order."""
    return [
        str(e.key)
        for e in doc.entries
        if isinstance(e, Node) and isinstance(e.value, Block)
    ]


def convert_dynasty_file(doc: Document, port: DynastyPort) -> Block:
    """Convert one CK2 dynasty file, keeping its grouping and comments."""
    out = BlockBuilder()
    for entry in doc.entries:
        if isinstance(entry, Item):
            out.comment(f"CK2: bare item {shape_of(entry.value)} (not a CK3 shape)")
            continue
        assert isinstance(entry, Node)
        if not isinstance(entry.value, Block):
            out.comment(f"CK2: {entry.key} = {shape_of(entry.value)} (not a dynasty)")
            port.report.drop(entry.key, "file", "not a dynasty block")
            continue
        entry.leading_comments = strip_ck2_markers(entry.leading_comments)
        out.add(port.convert_dynasty(entry))
    block = out.finish()
    block.end_comments.extend(strip_ck2_markers(doc.end_comments))
    return block


def output_name(ck2_name: str, prefix: str = "fae") -> str:
    """CK2 dynasty file name -> CK3 file name.

    >>> output_name("Faerun_Dynasties.txt")
    'fae_faerun_dynasties.txt'
    """
    stem = Path(ck2_name).stem
    safe = "".join(c if (c.isalnum() or c in "-_") else "_" for c in stem.lower())
    while "__" in safe:
        safe = safe.replace("__", "_")
    return f"{prefix}_{safe.strip('_')}.txt"
