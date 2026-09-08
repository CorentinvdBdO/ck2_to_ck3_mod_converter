"""Convert CK2 ``history/characters`` to CK3 ``history/characters``.

Field by field, driven by ``mappings/character_effects.csv``. Three levels of
nesting matter and each has its own key namespace:

1. the character block (``fae_2 = { ... }``) — level ``history``;
2. a dated block (``1240.5.4 = { ... }``) — also level ``history``, because CK2
   and CK3 both accept the same keys there;
3. an ``effect = { ... }`` block — level ``effect``, where the keys are effect
   names rather than history keys.

Anything with no CK3 equivalent becomes an in-block comment
``# CK2: key = value (reason)`` next to where it stood, so the output is a
readable record of what was lost. Nothing is invented.

Verified CK3 shapes (1.19 install, see ``docs/formats_characters.md``):

* ``death = { death_reason = x killer = <id> }`` — ``killer`` is a bare id, not
  a ``character:`` scope.
* ``set_relation_friend = { reason = friend_generic_history target = character:<id> }``
* ``add_pressed_claim = title:<id>``
* ``add_character_modifier = { modifier = x years = n }``
* there is **no** ``effect_even_if_dead`` in CK3; it is ported as ``effect``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..pdx import Block, Document, Item, Node
from ..pdx.tokens import Date
from .common import (
    BlockBuilder,
    PortReport,
    carry_comments,
    fae_id,
    is_date_key,
    shape_of,
    strip_ck2_markers,
)
from .tables import KeyRule, Tables

#: Keys that must sit inside an ``effect = { }`` block in CK3 even though CK2
#: writes them straight into the dated block.
WRAPPED_FORMS = frozenset({"int_effect", "title_scope_effect", "char_scope_effect"})

#: Level name for a key inside a dated block. Most keys behave the same at both
#: levels, so a lookup tries ``dated`` first and falls back to ``history``; a
#: ``dated`` row exists only where CK3 differs (``father`` needs the effect
#: form there, ``fertility`` is a trigger and cannot be used at all).
DATED = "dated"


@dataclass
class CharacterFacts:
    """What the referential-integrity checks need to know about one character."""

    ck3_id: str
    ck2_id: str
    source: str
    dynasty: str | None = None
    father: str | None = None
    mother: str | None = None
    birth: Date | None = None
    death: Date | None = None
    #: ``(kind, target_id)`` for every character this one points at.
    #: ``(kind, target_id)``; ``kind`` is the CK3 key, so a spouse ref is
    #: ``add_spouse`` / ``add_matrilineal_spouse``.
    refs: list[tuple[str, str]] = field(default_factory=list)
    traits: list[str] = field(default_factory=list)
    #: CK2 ``female = yes``. Needed by the integrity check, because CK3 1.19
    #: refuses ``add_spouse`` between two characters of the same gender
    #: (``error(wrong-gender)``) and CK2 allowed it.
    female: bool = False


@dataclass
class CharacterPort:
    """Converts character blocks; accumulates counts, drops and facts."""

    tables: Tables
    prefix: str = "fae"
    report: PortReport = field(default_factory=PortReport)
    facts: dict[str, CharacterFacts] = field(default_factory=dict)
    #: CK2 id -> CK3 id, handed to the titles-history lane through ``ctx.data``.
    id_map: dict[str, str] = field(default_factory=dict)

    # -- helpers -----------------------------------------------------------
    def _ref(self, value: object) -> str:
        return fae_id(value, self.prefix)

    def _drop(self, out: BlockBuilder, node: Node, level: str, reason: str) -> None:
        """Turn an unconvertible CK2 entry into a comment in place."""
        out.comments(strip_ck2_markers(node.leading_comments))
        text = f"CK2: {node.key} {node.op} {shape_of(node.value)} ({reason})"
        if node.trailing_comment:
            text += f" [{node.trailing_comment.lstrip('# ').strip()}]"
        out.comment(text)
        self.report.drop(node.key, level, reason)

    # -- entry point -------------------------------------------------------
    def convert_character(self, node: Node, source: str = "") -> Node:
        """Convert one ``<ck2 id> = { ... }`` block into its CK3 form."""
        ck2_id = str(node.key)
        ck3_id = self._ref(ck2_id)
        if ck2_id in self.id_map:
            self.report.warn(
                f"CK2 character id {ck2_id} is defined more than once; "
                "CK3 will see a duplicate fae_ id"
            )
            self.report.counts["duplicate_ids"] += 1
        self.id_map[ck2_id] = ck3_id
        facts = CharacterFacts(ck3_id=ck3_id, ck2_id=ck2_id, source=source)
        self.facts[ck3_id] = facts

        body = node.value if isinstance(node.value, Block) else Block()
        out = BlockBuilder()
        self._convert_body(body, out, facts, dated=False)
        result = Node(key=ck3_id, value=out.finish())
        carry_comments(node, result)
        self.report.counts["characters"] += 1
        return result

    # -- the three levels --------------------------------------------------
    def _convert_body(
        self,
        body: Block,
        out: BlockBuilder,
        facts: CharacterFacts,
        *,
        dated: bool,
    ) -> None:
        """A character block or a dated block: both use the ``history`` level."""
        wrapped: list[Node] = []
        for entry in body.entries:
            if isinstance(entry, Item):
                out.comment(f"CK2: bare item {shape_of(entry.value)} (not a CK3 shape)")
                self.report.drop("<item>", "history", "bare item")
                continue
            assert isinstance(entry, Node)
            if is_date_key(entry.key):
                if dated:
                    self._drop(out, entry, "history", "nested dated block")
                    continue
                self._convert_dated(entry, out, facts)
                continue
            self._convert_history_key(entry, out, facts, wrapped, dated=dated)
        if wrapped:
            self._append_effect(out, wrapped)
        out.finish()

    def _convert_dated(self, node: Node, out: BlockBuilder, facts: CharacterFacts) -> None:
        body = node.value if isinstance(node.value, Block) else Block()
        inner = BlockBuilder()
        self._convert_body(body, inner, facts, dated=True)
        date = Date.parse(node.key)
        result = Node(key=str(date), value=inner.finish())
        carry_comments(node, result)
        out.add(result)
        self.report.counts["dated_blocks"] += 1
        if "birth" in body:
            facts.birth = date
        if "death" in body:
            facts.death = date

    def _append_effect(self, out: BlockBuilder, wrapped: list[Node]) -> None:
        """Add the one ``effect = { }`` block that carries the wrapped keys."""
        block = Block(entries=list(wrapped))
        out.add(
            Node(
                key="effect",
                value=block,
                leading_comments=[
                    "# CK3 has no history key for the effects below; "
                    "they must sit in an effect block."
                ],
            )
        )
        self.report.counts["effect_blocks_added"] += 1

    # -- one key -----------------------------------------------------------
    def _convert_history_key(
        self,
        node: Node,
        out: BlockBuilder,
        facts: CharacterFacts,
        wrapped: list[Node],
        *,
        dated: bool = False,
    ) -> None:
        level = DATED if dated else "history"
        rule = self.tables.rule(node.key, DATED) if dated else None
        if rule is None:
            rule = self.tables.rule(node.key, "history")
        if rule is None:
            self.report.warn(
                f"unmapped CK2 history key {node.key!r} on a character; commented out"
            )
            self._drop(out, node, level, "no row in mappings/character_effects.csv")
            return
        if rule.drops:
            self._drop(out, node, level, rule.note)
            return

        if rule.form == "effect_block":
            self._convert_effect_block(node, out, rule, facts)
            return
        if rule.form == "death":
            self._convert_death(node, out, facts)
            return
        if rule.form in WRAPPED_FORMS:
            emitted = self._shape(node, rule, facts, level=level)
            if emitted is None:
                self._drop(out, node, level, _value_reason(rule))
                return
            # The CK2 comments belong with the value, which moved.
            wrapped.append(carry_comments(node, emitted))
            self._note_fact(node, rule, facts)
            return

        emitted = self._shape(node, rule, facts, level=level)
        if emitted is None:
            self._drop(out, node, level, _value_reason(rule))
            return
        out.add(carry_comments(node, emitted))
        self._note_fact(node, rule, facts)

    def _convert_effect_block(
        self, node: Node, out: BlockBuilder, rule: KeyRule, facts: CharacterFacts
    ) -> None:
        body = node.value if isinstance(node.value, Block) else Block()
        inner = BlockBuilder()
        if node.key == "effect_even_if_dead":
            inner.comment(
                "CK2: effect_even_if_dead = { ... } "
                "(CK3 has no effect_even_if_dead; ported as effect)"
            )
            self.report.drop("effect_even_if_dead", "history", "renamed to effect")
        for entry in body.entries:
            if isinstance(entry, Item):
                inner.comment(f"CK2: bare item {shape_of(entry.value)} (not a CK3 shape)")
                continue
            assert isinstance(entry, Node)
            self._convert_effect_key(entry, inner, facts)
        result = Node(key=rule.ck3_key, value=inner.finish())
        carry_comments(node, result)
        out.add(result)
        self.report.counts["effect_blocks"] += 1

    def _convert_effect_key(
        self, node: Node, out: BlockBuilder, facts: CharacterFacts
    ) -> None:
        rule = self.tables.rule(node.key, "effect")
        if rule is None:
            reason = (
                "CK2 scope change; CK3 history effects run in the character's scope"
                if _looks_like_scope(node)
                else "no row in mappings/character_effects.csv"
            )
            if not _looks_like_scope(node):
                self.report.warn(
                    f"unmapped CK2 effect {node.key!r} in a character effect block; "
                    "commented out"
                )
            self._drop(out, node, "effect", reason)
            return
        if rule.drops:
            self._drop(out, node, "effect", rule.note)
            return
        emitted = self._shape(node, rule, facts, level="effect")
        if emitted is None:
            self._drop(out, node, "effect", _value_reason(rule))
            return
        out.add(carry_comments(node, emitted))
        self._note_fact(node, rule, facts)

    # -- value shapes ------------------------------------------------------
    def _shape(
        self, node: Node, rule: KeyRule, facts: CharacterFacts, *, level: str
    ) -> Node | None:
        """Build the CK3 node for ``rule``, or ``None`` to comment it out."""
        form = rule.form
        value = node.value
        key = rule.ck3_key

        if form == "same":
            if key == "name" and isinstance(value, str) and not value.strip():
                # 54 Faerûn characters have a blank name: 52 write `name = " "`
                # (the Yikarians) and 2 write `name = ""`. CK3 *requires*
                # `name`, so dropping it turns a tiger warning into a load
                # error; the blank value is kept verbatim and flagged instead.
                self.report.warn(
                    "CK2 character has a blank name; kept verbatim "
                    "because CK3 requires the field (needs a human or an "
                    "overrides row)"
                )
                self.report.counts["empty_names"] += 1
            return Node(key=key, value=value, quoted_value=node.quoted_value)
        if form == "char_ref":
            return Node(key=key, value=self._ref(value))
        if form in ("char_scope", "char_scope_effect"):
            return Node(key=key, value=f"character:{self._ref(value)}")
        if form == "dynasty_scope":
            return Node(key=key, value=f"dynasty:{self._ref(value)}")
        if form == "title_scope":
            return Node(key=key, value=f"title:{value}")
        if form == "title_scope_effect":
            return Node(key=key, value=f"title:{value}")
        if form == "int_effect":
            return Node(key=key, value=value)
        if form == "drop_value":
            return Node(key=key, value=True)
        if form == "scale_0_1":
            return Node(key=key, value=max(1, round(float(value) * 0.1)))
        if form == "trait":
            return self._shape_trait(node, key)
        if form == "nickname":
            return self._shape_nickname(node, key)
        if form == "char_modifier":
            return self._shape_char_modifier(node, key)
        if rule.relation_reason:
            return self._shape_relation(node, key, rule.relation_reason)
        raise AssertionError(f"unknown form {form!r} for CK2 key {node.key!r}")

    def _shape_trait(self, node: Node, key: str) -> Node | None:
        ck2_trait = str(node.value)
        ck3_trait = self.tables.trait(ck2_trait)
        if ck3_trait is None:
            self.report.counts["traits_dropped"] += 1
            return None
        self.report.counts["traits"] += 1
        if ck3_trait != ck2_trait:
            self.report.counts["traits_renamed"] += 1
        return Node(key=key, value=ck3_trait)

    def _shape_nickname(self, node: Node, key: str) -> Node | None:
        if isinstance(node.value, bool):
            return Node(key=key, value=node.value)
        ck3_nick = self.tables.nickname(str(node.value))
        if ck3_nick is None:
            self.report.counts["nicknames_dropped"] += 1
            return None
        self.report.counts["nicknames"] += 1
        return Node(key=key, value=ck3_nick)

    def _shape_relation(self, node: Node, key: str, reason: str) -> Node:
        body = Block(
            entries=[
                Node(key="reason", value=reason),
                Node(key="target", value=f"character:{self._ref(node.value)}"),
            ]
        )
        self.report.counts["relations"] += 1
        return Node(key=key, value=body)

    def _shape_char_modifier(self, node: Node, key: str) -> Node | None:
        if not isinstance(node.value, Block):
            return None
        name = node.value.get("name")
        if name is None:
            return None
        ck3_modifier = self.tables.modifier(str(name))
        if ck3_modifier is None:
            self.report.counts["modifiers_dropped"] += 1
            return None
        self.report.counts["modifiers"] += 1
        entries = [Node(key="modifier", value=ck3_modifier)]
        duration = node.value.get("duration")
        if isinstance(duration, (int, float)) and duration > 0:
            # CK2 duration is in days, CK3 add_character_modifier takes years.
            entries.append(Node(key="years", value=max(1, round(float(duration) / 365))))
        return Node(key=key, value=Block(entries=entries))

    def _convert_death(self, node: Node, out: BlockBuilder, facts: CharacterFacts) -> None:
        if not isinstance(node.value, Block):
            out.add(carry_comments(node, Node(key="death", value=node.value)))
            self.report.counts["deaths"] += 1
            return
        inner = BlockBuilder()
        for entry in node.value.entries:
            if not isinstance(entry, Node):
                continue
            if entry.key == "death_reason":
                ck2_reason = str(entry.value)
                ck3_reason, status = self.tables.death_reason(ck2_reason)
                # Comment whenever the id changed, whatever the table's opinion
                # of how good the match is: the CK2 value must stay readable.
                if ck3_reason != ck2_reason:
                    inner.comment(
                        f"CK2: death_reason = {ck2_reason} ({status} -> {ck3_reason})"
                    )
                    self.report.drop("death_reason", "history", status)
                if status == "unknown":
                    self.report.warn(
                        f"death_reason {ck2_reason!r} has no row in "
                        f"mappings/death_reasons.csv; fell back to {ck3_reason}"
                    )
                inner.add(carry_comments(entry, Node(key="death_reason", value=ck3_reason)))
                self.report.counts[f"death_reason_{status}"] += 1
            elif entry.key == "killer":
                killer = self._ref(entry.value)
                inner.add(carry_comments(entry, Node(key="killer", value=killer)))
                facts.refs.append(("killer", killer))
            else:
                self._drop(inner, entry, "history", "not a CK3 death sub-key")
        result = Node(key="death", value=inner.finish())
        carry_comments(node, result)
        out.add(result)
        self.report.counts["deaths"] += 1

    # -- facts for the integrity checks ------------------------------------
    def _note_fact(self, node: Node, rule: KeyRule, facts: CharacterFacts) -> None:
        key = rule.ck3_key
        if key == "female":
            facts.female = str(node.value).lower() in ("yes", "true")
        elif key == "dynasty":
            facts.dynasty = self._ref(node.value)
        elif key == "father":
            facts.father = self._ref(node.value)
            facts.refs.append(("father", facts.father))
        elif key == "mother":
            facts.mother = self._ref(node.value)
            facts.refs.append(("mother", facts.mother))
        elif rule.form in ("char_ref", "char_scope") or rule.relation_reason:
            facts.refs.append((key, self._ref(node.value)))
        elif rule.form == "trait":
            ck3 = self.tables.trait(str(node.value))
            if ck3:
                facts.traits.append(ck3)


#: Why a value, rather than a key, could not be converted.
VALUE_REASONS = {
    "trait": (
        "the traits step does not declare this trait in the generated mod "
        "(mappings/trait_ck2_to_ck3.csv; the reason per trait is in "
        "docs/evidence/traits_unported.csv)"
    ),
    "char_modifier": (
        "CK3 1.19 declares no such modifier in common/modifiers and no step "
        "converts the CK2 common/event_modifiers it comes from"
    ),
    "nickname": (
        "nickname has no CK3 id in mappings/nicknames.csv; "
        "Faerun defines it in its own common/nicknames"
    ),
    "char_modifier": "CK2 modifier block has no `name`",
}


def _value_reason(rule: KeyRule) -> str:
    return VALUE_REASONS.get(rule.form, rule.note or "value has no CK3 equivalent")


def _looks_like_scope(node: Node) -> bool:
    """True for a CK2 scope-change key such as ``c_bloodstone = { ... }``."""
    return isinstance(node.value, Block) and (
        node.key.startswith(("b_", "c_", "d_", "k_", "e_"))
        or node.key in ("ROOT", "FROM", "PREV", "THIS")
    )


# -- module-level convenience ---------------------------------------------
def convert_character(node: Node, tables: Tables, prefix: str = "fae") -> Node:
    """Convert a single character block with a throwaway port (for tests)."""
    return CharacterPort(tables=tables, prefix=prefix).convert_character(node)


def convert_character_file(
    doc: Document, port: CharacterPort, source: str | Path = ""
) -> Block:
    """Convert every character block of one CK2 file, keeping the file's shape.

    One CK3 file per CK2 file: Faerûn groups its 18124 characters into 80
    id-range files and that grouping is the only index a human has.
    """
    out = BlockBuilder()
    for entry in doc.entries:
        if isinstance(entry, Item):
            out.comment(f"CK2: bare item {shape_of(entry.value)} (not a CK3 shape)")
            continue
        assert isinstance(entry, Node)
        if not isinstance(entry.value, Block):
            out.comment(f"CK2: {entry.key} = {shape_of(entry.value)} (not a character)")
            port.report.drop(entry.key, "file", "not a character block")
            continue
        entry.leading_comments = strip_ck2_markers(entry.leading_comments)
        out.add(port.convert_character(entry, source=str(source)))
    block = out.finish()
    block.end_comments.extend(strip_ck2_markers(doc.end_comments))
    return block


def output_name(ck2_name: str, prefix: str = "fae") -> str:
    """CK2 file name -> CK3 file name, keeping the id range readable.

    >>> output_name("1-1000 Miscellaneous.txt")
    'fae_1-1000_miscellaneous.txt'
    """
    stem = Path(ck2_name).stem
    safe = "".join(c if (c.isalnum() or c in "-_") else "_" for c in stem.lower())
    while "__" in safe:
        safe = safe.replace("__", "_")
    return f"{prefix}_{safe.strip('_')}.txt"
