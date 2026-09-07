"""Minimal brace-block reader for the flat CK2 ``map/`` text files.

TEMPORARY. The ``foundation`` lane is building the real tokenizer/writer in
``ck2ck3.pdx``.  This module only has to cope with the handful of shapes that
appear in ``map/default.map``, ``map/climate.txt``, ``map/island_region.txt``,
``map/geographical_region.txt``, ``map/terrain.txt`` and ``map/positions.txt``:

* ``key = value``
* ``key = "quoted value"``
* ``key = { a b c }``             (flat token list)
* ``key = { sub = { ... } ... }`` (arbitrary nesting)
* duplicate keys at the same level (``sea_zones`` appears 11 times)

It keeps duplicates (children are always lists) and it keeps the trailing
comment of the line that opens *or* closes a block, so callers can recover the
sea-zone / ocean-region names that CK2 only stores as comments.  It is *not* a
round-trip writer.  Replace with ``ck2ck3.pdx`` once that lands.

Gotchas this file exists to remember:
* the last bare token before ``}`` is easy to lose — flush on close;
* CK2 writes the sea-zone name as a trailing comment *after* the closing brace
  (``sea_zones = { 1791 1900 } #Trackless Sea 1``) but the ocean-region name as
  a comment *after the opening brace*.  Both are needed, hence the two-sided
  comment lookup.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

CK2_ENCODING = "cp1252"

_TOKEN = re.compile(
    r"""
      (?P<comment>\#[^\n]*)
    | (?P<string>"[^"\n]*")
    | (?P<open>\{)
    | (?P<close>\})
    | (?P<eq>=)
    | (?P<word>[^\s{}=#"]+)
    """,
    re.VERBOSE,
)


@dataclass
class Block:
    """A ``{ ... }`` block: named children plus positional bare tokens."""

    children: dict[str, list["Block | str"]] = field(default_factory=dict)
    tokens: list[str] = field(default_factory=list)
    #: trailing comment of the opening line, else of the closing line
    comment: str | None = None
    open_line: int = 0
    close_line: int = 0

    def add(self, key: str, value: "Block | str") -> None:
        self.children.setdefault(key, []).append(value)

    def all(self, key: str) -> list["Block | str"]:
        return self.children.get(key, [])

    def blocks(self, key: str) -> list["Block"]:
        return [v for v in self.all(key) if isinstance(v, Block)]

    def first(self, key: str) -> "Block | str | None":
        vals = self.all(key)
        return vals[0] if vals else None

    def str_(self, key: str, default: str | None = None) -> str | None:
        v = self.first(key)
        return v if isinstance(v, str) else default

    def int_(self, key: str, default: int | None = None) -> int | None:
        v = self.first(key)
        try:
            return int(v)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return default

    def ints(self, key: str) -> list[int]:
        """Every integer token in every ``key = { ... }`` block, in file order."""
        return [int(t) for b in self.blocks(key) for t in b.tokens if is_int(t)]


def is_int(tok: str) -> bool:
    return bool(tok) and (tok[1:] if tok[0] in "+-" else tok).isdigit()


def parse(text: str) -> Block:
    """Parse a whole file body into a synthetic root :class:`Block`."""
    # comments by line number, for the two-sided lookup described above
    comments: dict[int, str] = {}
    root = Block()
    stack: list[Block] = [root]
    opened: list[Block] = []
    pending_key: str | None = None
    saw_eq = False
    line = 1
    pos = 0

    def flush_pending() -> None:
        nonlocal pending_key, saw_eq
        if pending_key is not None:
            stack[-1].tokens.append(pending_key)
        pending_key, saw_eq = None, False

    for m in _TOKEN.finditer(text):
        line += text.count("\n", pos, m.start())
        pos = m.start()
        kind = m.lastgroup
        raw = m.group()

        if kind == "comment":
            comments[line] = raw[1:].strip()
            continue
        if kind == "eq":
            saw_eq = True
            continue
        if kind == "open":
            blk = Block(open_line=line)
            top = stack[-1]
            if pending_key is not None and saw_eq:
                top.add(pending_key, blk)
            else:
                flush_pending()
                top.add("", blk)
            pending_key, saw_eq = None, False
            stack.append(blk)
            opened.append(blk)
            continue
        if kind == "close":
            flush_pending()
            if len(stack) > 1:
                blk = stack.pop()
                blk.close_line = line
            continue

        val = raw[1:-1] if kind == "string" else raw
        top = stack[-1]
        if pending_key is not None and saw_eq:
            top.add(pending_key, val)
            pending_key, saw_eq = None, False
        else:
            flush_pending()
            pending_key, saw_eq = val, False

    flush_pending()
    for blk in opened:
        blk.comment = comments.get(blk.open_line) or comments.get(blk.close_line)
    return root


def parse_file(path: str | Path, encoding: str = CK2_ENCODING) -> Block:
    return parse(Path(path).read_text(encoding=encoding, errors="replace"))
