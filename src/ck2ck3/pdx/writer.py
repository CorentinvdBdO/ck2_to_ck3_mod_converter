"""Writer for Paradox script: turns a parse tree back into text.

Two modes:

* default — tabs, comments, blank-line groups, item-only blocks on one line;
  ``parse(write(parse(x)))`` is structurally equal to ``parse(x)``.
* ``canonical=True`` — no comments, no blank lines, one entry per line. Used to
  diff two files for meaning rather than for layout.
"""

from __future__ import annotations

import re
from pathlib import Path

from .encoding import OUT_ENCODING, write_text
from .nodes import Block, Color, Item, Node, Operator, VarRef
from .tokens import Date, TokenType, classify_word, escape

_WORD_RE = re.compile(r"[^\s{}\#\"=<>!?]+\Z")


def needs_quotes(text: str) -> bool:
    """True when ``text`` cannot be written as a bare word without changing.

    Anything that would come back as a number, a date, a bool or a variable
    reference must stay quoted, otherwise the round trip changes the type.
    """
    if not text or _WORD_RE.match(text) is None:
        return True
    return classify_word(text)[0] is not TokenType.IDENT


def needs_quotes_key(text: str) -> bool:
    """True when a *key* must be quoted.

    Weaker than :func:`needs_quotes`: a key is always a string, so a key that
    looks like a date (``1066.1.1 = { ... }``) stays bare.
    """
    return not text or _WORD_RE.match(text) is None


def format_float(value: float) -> str:
    """Render a float in plain decimal notation.

    Paradox script has no exponent syntax, so ``repr(-3e-05)`` would produce a
    token the game reads as an identifier. Seen in CK3
    ``common/script_values/00_faction_values.txt``.
    """
    text = repr(value)
    if "e" in text or "E" in text:
        text = f"{value:.20f}".rstrip("0")
        if text.endswith("."):
            text += "0"
    if "." not in text:
        text += ".0"
    return text


def format_scalar(value: object, *, quoted: bool = False) -> str:
    """Render a scalar value as script text."""
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, Date):
        return str(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return format_float(value)
    if isinstance(value, VarRef):
        return f"@{value.name}"
    if isinstance(value, Operator):
        return value.text
    if isinstance(value, str):
        if quoted or needs_quotes(value):
            return f'"{escape(value)}"'
        return value
    raise TypeError(f"cannot write value of type {type(value).__name__}")


class Writer:
    def __init__(
        self,
        *,
        indent: str = "\t",
        newline: str = "\n",
        canonical: bool = False,
    ) -> None:
        self.indent = indent
        self.newline = newline
        self.canonical = canonical

    # -- public ------------------------------------------------------------
    def write(self, block: Block) -> str:
        lines: list[str] = []
        self._emit_entries(block, 0, lines)
        if not self.canonical:
            lines.extend(self._comment_lines(block.end_comments, ""))
        text = self.newline.join(lines)
        return text + self.newline if text else ""

    # -- internals ---------------------------------------------------------
    def _emit_entries(self, block: Block, depth: int, lines: list[str]) -> None:
        pad = self.indent * depth
        for entry in block.entries:
            if not self.canonical:
                if entry.blank_before and lines:
                    lines.append("")
                lines.extend(self._comment_lines(entry.leading_comments, pad))
            head = self._entry_head(entry)
            tail = (
                f" {entry.trailing_comment}"
                if entry.trailing_comment and not self.canonical
                else ""
            )
            value = entry.value
            if value is None:
                # `key =` with no value (a Faerûn typo); keep it as it was.
                lines.append(f"{pad}{head}{tail}")
                continue
            if not isinstance(value, (Block, Color)):
                text = format_scalar(value, quoted=self._quoted(entry))
                lines.append(f"{pad}{head}{text}{tail}")
                continue
            inner = value.block if isinstance(value, Color) else value
            tag = f"{value.tag} " if isinstance(value, Color) else ""
            opener, closer = self._container(inner, tag)
            if opener is None:
                lines.append(f"{pad}{head}{closer}{tail}")
                continue
            lines.append(f"{pad}{head}{opener}")
            self._emit_entries(inner, depth + 1, lines)
            if not self.canonical:
                lines.extend(
                    self._comment_lines(
                        inner.end_comments, self.indent * (depth + 1)
                    )
                )
            # A trailing comment of a multi-line block sat after its closing
            # brace in the source; a comment on the opening line belongs to the
            # first inner entry instead.
            lines.append(f"{pad}}}{tail}")

    @staticmethod
    def _comment_lines(comments: list[str], pad: str) -> list[str]:
        """Render a comment group; an empty entry is a preserved blank line."""
        return [f"{pad}{c}" if c else "" for c in comments]

    def _entry_head(self, entry) -> str:
        if isinstance(entry, Node):
            key = (
                f'"{escape(entry.key)}"'
                if entry.quoted_key or needs_quotes_key(entry.key)
                else entry.key
            )
            if entry.value is None:
                return f"{key} {entry.op}"
            return f"{key} {entry.op} "
        return ""

    @staticmethod
    def _quoted(entry) -> bool:
        if isinstance(entry, Node):
            return entry.quoted_value
        return isinstance(entry, Item) and entry.quoted

    def _container(self, block: Block, tag: str = "") -> tuple[str | None, str]:
        """Return ``(opener, closer)``; ``opener is None`` means write inline."""
        if self._inline(block):
            values = " ".join(
                format_scalar(e.value, quoted=self._quoted(e)) for e in block.entries
            )
            body = f"{{ {values} }}" if values else "{ }"
            return None, f"{tag}{body}"
        return f"{tag}{{", "}"

    def _inline(self, block: Block) -> bool:
        """An item-only block with no comments and no blank groups fits a line."""
        if block.end_comments and not self.canonical:
            return False
        for entry in block.entries:
            if not isinstance(entry, Item) or isinstance(entry.value, (Block, Color)):
                return False
            if not self.canonical and (
                entry.leading_comments or entry.trailing_comment or entry.blank_before
            ):
                return False
        return True


def write(
    block: Block,
    *,
    indent: str = "\t",
    newline: str = "\n",
    canonical: bool = False,
) -> str:
    """Render a parse tree as Paradox script text."""
    return Writer(indent=indent, newline=newline, canonical=canonical).write(block)


def write_file(
    block: Block,
    path: str | Path,
    *,
    encoding: str = OUT_ENCODING,
    header: str | None = None,
    **kwargs: object,
) -> None:
    """Write a parse tree to ``path`` as UTF-8 (no BOM) with LF endings.

    ``header`` is prepended verbatim; use it for the "generated by" banner.
    """
    text = write(block, **kwargs)  # type: ignore[arg-type]
    if header:
        prefix = header if header.endswith("\n") else header + "\n"
        text = prefix + text
    write_text(path, text, encoding)
