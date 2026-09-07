"""Shared plumbing for the character and dynasty ports.

Three things every rule needs:

* :func:`fae_id` — the one place the ``fae_`` prefix is applied, so no rule
  can accidentally emit a bare CK2 id (see ``docs/DECISIONS.md``).
* :class:`BlockBuilder` — a block under construction that can *drop* an entry
  into a comment. The parse tree has no standalone comment entry (a comment is
  metadata on the entry below it), so a dropped key is held as a pending
  comment and flushed onto the next entry, or into ``end_comments`` when it was
  the last thing in the block. That is what keeps every unconvertible CK2 key
  visible in the output.
* :class:`PortReport` — counts, warnings and the dropped-key rows the run log
  and the evidence CSVs are built from.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Iterable

from ..pdx import Block, Entry, Item, Node
from ..pdx.tokens import Date

DATE_PARTS = 3

#: Paradox's CK2 file-encoding marker. Every Faerûn character and dynasty file
#: opens with the bytes ``###\xc4NSI`` ("###ANSI" with a cp1252 A-umlaut), a
#: CK2-only hint about the file's codepage. CK3 reads UTF-8 and the line is
#: pure noise in 83 generated files, so it is dropped.
CK2_ENCODING_MARKERS = frozenset({"\u00c4NSI", "ANSI", "\ufffdNSI"})


def strip_ck2_markers(comments: Iterable[str]) -> list[str]:
    """Drop the CK2 codepage marker from a comment list, keep everything else.

    The marker reaches us as a comment whose whole body is ``###\u00c4NSI``, so the
    test is "nothing left once the hashes and spaces are gone".

    >>> strip_ck2_markers(["# ###\u00c4NSI", "# real note"])
    ['# real note']
    """
    return [c for c in comments if c.strip("# \t") not in CK2_ENCODING_MARKERS]


def is_date_key(key: str) -> bool:
    """True for a history key like ``1357.1.1``."""
    parts = key.split(".")
    return len(parts) == DATE_PARTS and all(p.isdigit() and p for p in parts)


def fae_id(value: object, prefix: str = "fae") -> str:
    """The CK3 id for a CK2 character or dynasty id.

    Coordinator decision (``docs/DECISIONS.md``): every converted character and
    dynasty id becomes the string ``fae_<ck2_id>``. CK3 accepts string ids
    (33104 of 71124 vanilla history ids are non-numeric) and the prefix makes a
    collision with vanilla's numeric space impossible.

    >>> fae_id(2576)
    'fae_2576'
    >>> fae_id("fae_2576")
    'fae_2576'
    """
    text = str(value)
    return text if text.startswith(f"{prefix}_") else f"{prefix}_{text}"


def shape_of(value: object) -> str:
    """A one-line description of a value, for a dropped-key comment.

    A dropped block must not paste its whole body into a comment (Faerûn's
    ``spawn_unit`` blocks are dozens of lines), so a block is summarised by its
    keys.
    """
    if isinstance(value, Block):
        keys = [e.key for e in value.entries if isinstance(e, Node)]
        if not keys:
            return "{ ... }"
        shown = keys[:6]
        more = "" if len(keys) <= 6 else f" +{len(keys) - 6} more"
        return "{ " + " ".join(shown) + more + " }"
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)


@dataclass
class PortReport:
    """Everything a step needs to report, accumulated across files."""

    counts: Counter = field(default_factory=Counter)
    #: ``(ck2_key, level, reason)`` -> times dropped.
    dropped: Counter = field(default_factory=Counter)
    warnings: list[str] = field(default_factory=list)

    def drop(self, key: str, level: str, reason: str) -> None:
        self.dropped[(key, level, reason)] += 1

    def warn(self, message: str) -> None:
        if message not in self.warnings:
            self.warnings.append(message)

    def dropped_by_key(self) -> Counter:
        out: Counter = Counter()
        for (key, _level, _reason), n in self.dropped.items():
            out[key] += n
        return out


class BlockBuilder:
    """A :class:`~ck2ck3.pdx.Block` being built, with comment carry-over."""

    def __init__(self) -> None:
        self.block = Block()
        self._pending: list[str] = []

    def comment(self, text: str) -> None:
        """Queue a comment line for the next entry (or the block's tail)."""
        self._pending.append(text if text.startswith("#") else f"# {text}")

    def comments(self, texts: Iterable[str]) -> None:
        for text in texts:
            self.comment(text)

    def add(self, entry: Entry) -> Entry:
        """Append an entry, prefixed by whatever comments are pending."""
        if self._pending:
            entry.leading_comments = [*self._pending, *entry.leading_comments]
            self._pending = []
        self.block.append(entry)
        return entry

    def node(self, key: str, value: object, **kwargs: object) -> Node:
        return self.add(Node(key=key, value=value, **kwargs))  # type: ignore[arg-type]

    def item(self, value: object) -> Item:
        return self.add(Item(value=value))

    def finish(self) -> Block:
        """Flush any trailing comments into ``end_comments`` and return."""
        if self._pending:
            self.block.end_comments.extend(self._pending)
            self._pending = []
        return self.block

    def __len__(self) -> int:
        return len(self.block)


def carry_comments(source: Entry, target: Entry) -> Entry:
    """Copy a CK2 entry's own comments and blank-line grouping onto its port."""
    target.leading_comments = [*source.leading_comments, *target.leading_comments]
    target.trailing_comment = source.trailing_comment
    target.blank_before = source.blank_before
    return target


def date_of(key: str) -> Date:
    return Date.parse(key)
