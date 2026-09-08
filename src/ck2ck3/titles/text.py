"""A tiny indent-aware line buffer for the generated script files.

The lane writes ``common/landed_titles`` and both history folders as *text*
rather than as a :class:`ck2ck3.pdx.Block` tree, for one reason: most of the
CK2 content that has no CK3 construct has to survive as a **comment inside a
block** (``# b_x = { } # unbuilt in CK2 history``), and a parse tree has no
representation for "a commented-out entry between two live ones".  Keeping the
comments is a repo rule (``CLAUDE.md``: no invention, no silent drop), so the
writer emits text and the round-trip test parses the result back.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

TAB = "\t"


class Lines:
    """Accumulates script lines with an explicit indent level."""

    def __init__(self) -> None:
        self._lines: list[str] = []

    def raw(self, text: str = "") -> None:
        self._lines.append(text)

    def line(self, indent: int, text: str) -> None:
        self._lines.append(f"{TAB * indent}{text}" if text else "")

    def blank(self) -> None:
        if self._lines and self._lines[-1] != "":
            self._lines.append("")

    def comment(self, indent: int, text: str) -> None:
        text = text.lstrip()
        if not text.startswith("#"):
            text = f"# {text}"
        self.line(indent, text)

    def comments(self, indent: int, texts: Iterable[str]) -> None:
        for text in texts:
            self.comment(indent, text)

    def commented_block(self, indent: int, body: Iterable[str]) -> None:
        """Emit ``body`` with every line commented out, indent preserved."""
        for text in body:
            stripped = text.strip()
            self.line(indent, f"# {stripped}" if stripped else "#")

    def extend(self, other: "Lines") -> None:
        self._lines.extend(other._lines)

    def text(self) -> str:
        while self._lines and self._lines[-1] == "":
            self._lines.pop()
        return "\n".join(self._lines) + "\n"

    def __len__(self) -> int:
        return len(self._lines)


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slug(text: str, fallback: str = "x") -> str:
    """A CK3-safe identifier fragment: ASCII, lowercase, ``[a-z0-9_]``.

    CK2 localisation is Windows-1252 and Faerun names carry accents and
    apostrophes (``Ba'ath``, ``Sûzail``); a CK3 localisation *key* may not.
    """
    folded = unicodedata.normalize("NFKD", text)
    folded = "".join(c for c in folded if not unicodedata.combining(c))
    folded = folded.lower().replace("'", "").replace("’", "")
    out = _SLUG_RE.sub("_", folded).strip("_")
    return out or fallback


#: CK3 wants a UTF-8 BOM on a script file that is not pure ASCII: ck3-tiger
#: reports ``warning(encoding): Expected UTF-8 BOM encoding``, and vanilla's
#: own ``common/landed_titles/00_landed_titles.txt`` and
#: ``common/bookmarks/bookmarks/00_bookmarks.txt`` both start with one, while
#: the pure-ASCII ``history/titles/k_england.txt`` does not.
BOM = "\ufeff"


def with_bom(text: str) -> str:
    """Prepend the BOM when the file needs one (i.e. carries non-ASCII)."""
    if text.startswith(BOM) or text.isascii():
        return text
    return BOM + text


def rgb(color: tuple[int, int, int] | None, default: tuple[int, int, int] = (128, 128, 128)) -> str:
    """``color = { r g b }`` body."""
    r, g, b = color if color else default
    return f"{{ {r} {g} {b} }}"


def tail(comment: str | None) -> str:
    """A trailing comment as the writer wants it: exactly one leading ``#``.

    ``pdx`` keeps the ``#`` in :attr:`Node.trailing_comment`, so appending
    ``f" # {comment}"`` would double it.
    """
    if not comment:
        return ""
    return " " + comment.strip() if comment.strip().startswith("#") else f" # {comment.strip()}"


_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def valid_id(value: str) -> bool:
    """True when ``value`` is a legal CK3 database key (title id, loc key)."""
    return bool(_ID_RE.match(value))
