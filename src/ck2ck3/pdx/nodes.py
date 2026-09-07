"""The parse tree for Paradox script.

Design constraints that drive the shape of these classes:

* **Duplicate keys are normal** in Paradox script, so a block is an *ordered
  list of entries*, never a dict. Dict-like reads are available through
  :meth:`Block.get`, :meth:`Block.get_all` and ``block["key"]``.
* **Comments are content.** Comments on the lines above an entry become its
  :attr:`Entry.leading_comments`; a comment on the same line becomes its
  :attr:`Entry.trailing_comment`; comments after the last entry of a block are
  kept in :attr:`Block.end_comments`.
* **Blank lines are layout, not content**, so only the fact that a blank line
  group preceded an entry is kept (:attr:`Entry.blank_before`); the writer uses
  it to reproduce the original grouping.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterator, Sequence

from .errors import Problem
from .tokens import Date

Scalar = str | int | float | bool | Date
Value = "Scalar | Block | VarRef | Color | Operator"


@dataclass
class VarRef:
    """A reference to a script variable: ``@my_var``. Kept symbolic."""

    name: str


@dataclass
class Operator:
    """A comparison operator used as a *value*.

    CK3 does this for parametrised triggers: ``OPERATOR = <=`` in
    ``events/diarchy_events/vizierate_events.txt:109``. Kept as its own type so
    the writer emits it bare instead of quoting it.
    """

    text: str


@dataclass
class Color:
    """A tagged colour: ``rgb { 20 30 40 }``, ``hsv { 0.5 1 1 }``.

    The body is kept as a :class:`Block` so an unusual body (a comment between
    two components) survives a round trip; :attr:`components` is the common
    read path.
    """

    tag: str
    block: "Block" = field(default_factory=lambda: Block())

    @property
    def components(self) -> list[object]:
        return self.block.list_values()


@dataclass
class Entry:
    """Base class of the two things a block can contain."""

    leading_comments: list[str] = field(default_factory=list)
    trailing_comment: str | None = None
    blank_before: bool = False
    line: int = 0


@dataclass
class Node(Entry):
    """A ``key OP value`` entry, e.g. ``culture = illuskan`` or ``age > 6``."""

    key: str = ""
    op: str = "="
    value: "Value" = None
    #: True when the key was quoted in the source.
    quoted_key: bool = False
    #: True when a string value was quoted in the source.
    quoted_value: bool = False

    # -- dict-like reads delegated to a block value ------------------------
    @property
    def block(self) -> "Block":
        if not isinstance(self.value, Block):
            raise TypeError(f"value of {self.key!r} is not a block")
        return self.value

    def get(self, key: str, default: object = None) -> object:
        return self.block.get(key, default)

    def get_all(self, key: str) -> list[object]:
        return self.block.get_all(key)

    def __getitem__(self, key: str) -> object:
        return self.block[key]

    def __contains__(self, key: str) -> bool:
        return key in self.block


@dataclass
class Item(Entry):
    """A bare value inside a list block, e.g. each number of ``{ 1 2 3 }``."""

    value: "Value" = None
    #: True when the item was quoted in the source.
    quoted: bool = False


@dataclass
class Block:
    """An ordered sequence of entries, i.e. the body of ``{ ... }``.

    A block may mix :class:`Node` and :class:`Item` entries; Faerûn does it in
    ``common/`` (``holding_types``) and CK3 does it in gene definitions.
    """

    entries: list[Entry] = field(default_factory=list)
    #: Comments sitting after the last entry, before the closing brace.
    end_comments: list[str] = field(default_factory=list)
    #: Force one entry per line even when the block would fit on one. Set by a
    #: writer that must match a vanilla file's layout (``descriptor.mod``);
    #: never set by the parser and never part of structural equality.
    multiline: bool = field(default=False, compare=False)

    # -- sequence protocol -------------------------------------------------
    def __iter__(self) -> Iterator[Entry]:
        return iter(self.entries)

    def __len__(self) -> int:
        return len(self.entries)

    def append(self, entry: Entry) -> None:
        self.entries.append(entry)

    # -- dict-like reads ---------------------------------------------------
    def nodes(self, key: str | None = None) -> list[Node]:
        """Every :class:`Node` entry, optionally filtered by key."""
        return [
            e
            for e in self.entries
            if isinstance(e, Node) and (key is None or e.key == key)
        ]

    def items(self) -> list[Item]:
        """Every bare :class:`Item` entry (the list part of the block)."""
        return [e for e in self.entries if isinstance(e, Item)]

    def list_values(self) -> list[object]:
        """The values of the bare items, e.g. ``[1, 2, 3]`` for ``{ 1 2 3 }``."""
        return [e.value for e in self.entries if isinstance(e, Item)]

    def keys(self) -> list[str]:
        """Keys in source order, duplicates included."""
        return [e.key for e in self.entries if isinstance(e, Node)]

    def get(self, key: str, default: object = None) -> object:
        for entry in self.entries:
            if isinstance(entry, Node) and entry.key == key:
                return entry.value
        return default

    def get_all(self, key: str) -> list[object]:
        return [
            entry.value
            for entry in self.entries
            if isinstance(entry, Node) and entry.key == key
        ]

    def get_node(self, key: str) -> Node | None:
        for entry in self.entries:
            if isinstance(entry, Node) and entry.key == key:
                return entry
        return None

    def __getitem__(self, key: str) -> object:
        for entry in self.entries:
            if isinstance(entry, Node) and entry.key == key:
                return entry.value
        raise KeyError(key)

    def __contains__(self, key: str) -> bool:
        return any(isinstance(e, Node) and e.key == key for e in self.entries)

    def pairs(self) -> Iterator[tuple[str, object]]:
        """Iterate ``(key, value)`` for node entries, duplicates included."""
        for entry in self.entries:
            if isinstance(entry, Node):
                yield entry.key, entry.value


@dataclass
class Document(Block):
    """A parsed file. ``source`` and ``encoding`` never take part in equality."""

    source: str = field(default="<string>", compare=False)
    encoding: str | None = field(default=None, compare=False)
    problems: list[Problem] = field(default_factory=list, compare=False)


def structurally_equal(
    left: object,
    right: object,
    *,
    comments: bool = True,
    blanks: bool = True,
) -> bool:
    """Compare two trees, optionally ignoring comments and blank-line flags.

    Used by the round-trip tests: ``parse(write(parse(x)))`` must be
    structurally equal to ``parse(x)``, comments and blank groups included.
    """
    if isinstance(left, Block) and isinstance(right, Block):
        if len(left.entries) != len(right.entries):
            return False
        if comments and list(left.end_comments) != list(right.end_comments):
            return False
        return all(
            structurally_equal(a, b, comments=comments, blanks=blanks)
            for a, b in zip(left.entries, right.entries)
        )
    if isinstance(left, Entry) and isinstance(right, Entry):
        if type(left) is not type(right):
            return False
        if comments and (
            list(left.leading_comments) != list(right.leading_comments)
            or left.trailing_comment != right.trailing_comment
        ):
            return False
        if blanks and left.blank_before != right.blank_before:
            return False
        if isinstance(left, Node):
            if left.key != right.key or left.op != right.op:
                return False
        return structurally_equal(
            left.value, right.value, comments=comments, blanks=blanks
        )
    if isinstance(left, Color) and isinstance(right, Color):
        return left.tag == right.tag and structurally_equal(
            left.block, right.block, comments=comments, blanks=blanks
        )
    if isinstance(left, bool) or isinstance(right, bool):
        # bool is an int subclass; keep 1 and yes distinct.
        return left is right
    return left == right


def variables(block: Block) -> dict[str, object]:
    """Collect ``@name = value`` definitions of a block, in source order."""
    out: dict[str, object] = {}
    for entry in block.entries:
        if isinstance(entry, Node) and entry.key.startswith("@"):
            out[entry.key[1:]] = entry.value
    return out


def resolve(
    value: object,
    table: dict[str, object] | None = None,
    *,
    strict: bool = False,
) -> object:
    """Replace :class:`VarRef` values by their definition, recursively.

    Returns a new tree; the input is left untouched so the writer can still
    emit the symbolic form. Unknown references stay symbolic unless ``strict``.
    """
    if isinstance(value, Document):
        table = {**variables(value), **(table or {})}
    elif isinstance(value, Block) and table is None:
        table = variables(value)
    table = table or {}
    return _resolve(value, table, strict)


def _resolve(value: object, table: dict[str, object], strict: bool) -> object:
    if isinstance(value, VarRef):
        if value.name in table:
            return _resolve(table[value.name], table, strict)
        if strict:
            raise KeyError(f"undefined script variable @{value.name}")
        return VarRef(value.name)
    if isinstance(value, Document):
        return Document(
            entries=[_resolve_entry(e, table, strict) for e in value.entries],
            end_comments=list(value.end_comments),
            source=value.source,
            encoding=value.encoding,
            problems=list(value.problems),
        )
    if isinstance(value, Block):
        return Block(
            entries=[_resolve_entry(e, table, strict) for e in value.entries],
            end_comments=list(value.end_comments),
        )
    return value


def _resolve_entry(entry: Entry, table: dict[str, object], strict: bool) -> Entry:
    resolved = _resolve(entry.value, table, strict)
    if isinstance(entry, Node):
        return Node(
            leading_comments=list(entry.leading_comments),
            trailing_comment=entry.trailing_comment,
            blank_before=entry.blank_before,
            line=entry.line,
            key=entry.key,
            op=entry.op,
            value=resolved,
            quoted_key=entry.quoted_key,
            quoted_value=entry.quoted_value,
        )
    assert isinstance(entry, Item)
    return Item(
        leading_comments=list(entry.leading_comments),
        trailing_comment=entry.trailing_comment,
        blank_before=entry.blank_before,
        line=entry.line,
        value=resolved,
        quoted=entry.quoted,
    )


def walk(block: Block) -> Iterator[tuple[Sequence[str], Entry]]:
    """Depth-first walk yielding ``(path, entry)`` for every entry."""
    stack: list[tuple[tuple[str, ...], Block]] = [((), block)]
    while stack:
        path, current = stack.pop()
        for entry in current.entries:
            yield path, entry
            if isinstance(entry, Block):  # pragma: no cover - defensive
                continue
            if isinstance(entry.value, Block):
                key = entry.key if isinstance(entry, Node) else "[]"
                stack.append((path + (key,), entry.value))
