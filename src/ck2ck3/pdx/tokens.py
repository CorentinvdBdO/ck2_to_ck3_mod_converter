"""Tokenizer for Paradox script (CK2 and CK3 ``.txt`` files).

Pure stdlib. One master regular expression, one pass, no backtracking over the
input: the whole file is scanned with ``re.Pattern.match`` at an explicit
position so that an unknown character is an error with a location instead of a
silently skipped byte.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Iterator

from .errors import Location, PdxSyntaxError

#: Comparison / assignment operators, longest first so ``<=`` wins over ``<``.
OPERATORS = ("<=", ">=", "==", "!=", "?=", "=", "<", ">")

#: Tagged colour prefixes: ``color = rgb { 20 30 40 }``.
COLOR_TAGS = ("rgb", "hsv360", "hsv")


class TokenType(Enum):
    LBRACE = "lbrace"
    RBRACE = "rbrace"
    OP = "op"
    STRING = "string"
    INT = "int"
    FLOAT = "float"
    DATE = "date"
    BOOL = "bool"
    IDENT = "ident"
    VARREF = "varref"
    COMMENT = "comment"
    EOF = "eof"


@dataclass
class Token:
    type: TokenType
    #: Source text, verbatim, minus the quotes of a string.
    text: str
    #: Decoded python value for scalar tokens, ``None`` otherwise.
    value: object
    line: int
    col: int
    #: True when at least one entirely blank line precedes this token.
    blank_before: bool = False

    def location(self, source: str) -> Location:
        return Location(source, self.line, self.col)


_TOKEN_RE = re.compile(
    r"""
      (?P<ws>[ \t\f\v]+)
    | (?P<nl>\r\n|[\n\r])
    | (?P<comment>\#[^\n\r]*)
    | (?P<lbrace>\{)
    | (?P<rbrace>\})
    | (?P<op><=|>=|==|!=|\?=|=|<|>)
    | (?P<string>"(?:[^"\\\n\r]|\\.)*")
    | (?P<word>[^\s{}\#"=<>!?]+)
    """,
    re.VERBOSE,
)

_DATE_RE = re.compile(r"^-?\d+\.\d+\.\d+$")
_INT_RE = re.compile(r"^[+-]?\d+$")
_FLOAT_RE = re.compile(r"^[+-]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][+-]?\d+)?$")

_STRING_ESCAPES = {'"': '"', "\\": "\\", "n": "\n", "t": "\t"}


def unescape(raw: str) -> str:
    """Decode the body of a quoted string (quotes already stripped)."""
    if "\\" not in raw:
        return raw
    out: list[str] = []
    i = 0
    while i < len(raw):
        ch = raw[i]
        if ch == "\\" and i + 1 < len(raw):
            nxt = raw[i + 1]
            out.append(_STRING_ESCAPES.get(nxt, "\\" + nxt))
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def escape(text: str) -> str:
    """Encode a string body for writing back inside double quotes."""
    return text.replace("\\", "\\\\").replace('"', '\\"')


@dataclass(frozen=True, order=True)
class Date:
    """A Paradox date literal such as ``1066.1.1``.

    Kept as its own type so a date never collides with a float.
    """

    year: int
    month: int
    day: int

    @classmethod
    def parse(cls, text: str) -> "Date":
        year, month, day = text.split(".")
        return cls(int(year), int(month), int(day))

    def __str__(self) -> str:
        return f"{self.year}.{self.month}.{self.day}"


def classify_word(word: str) -> tuple[TokenType, object]:
    """Map a bare word to a token type and a python value."""
    if _DATE_RE.match(word):
        return TokenType.DATE, Date.parse(word)
    if _INT_RE.match(word):
        return TokenType.INT, int(word)
    if _FLOAT_RE.match(word):
        return TokenType.FLOAT, float(word)
    if word == "yes":
        return TokenType.BOOL, True
    if word == "no":
        return TokenType.BOOL, False
    if word.startswith("@") and len(word) > 1:
        return TokenType.VARREF, word[1:]
    return TokenType.IDENT, word


def tokenize(text: str, source: str = "<string>") -> Iterator[Token]:
    """Yield every token of ``text``, ending with a single ``EOF`` token.

    ``COMMENT`` tokens are emitted (never dropped) so the parser can attach
    them to the node they document.
    """
    pos = 0
    end = len(text)
    line = 1
    line_start = 0
    newlines = 0
    first = True
    while pos < end:
        match = _TOKEN_RE.match(text, pos)
        if match is None:
            raise PdxSyntaxError(
                f"unexpected character {text[pos]!r}",
                Location(source, line, pos - line_start + 1),
            )
        kind = match.lastgroup
        start = pos
        pos = match.end()
        if kind == "ws":
            continue
        if kind == "nl":
            line += 1
            line_start = pos
            newlines += 1
            continue
        col = start - line_start + 1
        blank_before = newlines >= 2 and not first
        newlines = 0
        first = False
        raw = match.group()
        if kind == "comment":
            yield Token(TokenType.COMMENT, raw, None, line, col, blank_before)
        elif kind == "lbrace":
            yield Token(TokenType.LBRACE, raw, None, line, col, blank_before)
        elif kind == "rbrace":
            yield Token(TokenType.RBRACE, raw, None, line, col, blank_before)
        elif kind == "op":
            yield Token(TokenType.OP, raw, raw, line, col, blank_before)
        elif kind == "string":
            body = raw[1:-1]
            yield Token(TokenType.STRING, body, unescape(body), line, col, blank_before)
        else:
            ttype, value = classify_word(raw)
            yield Token(ttype, raw, value, line, col, blank_before)
    yield Token(TokenType.EOF, "", None, line, end - line_start + 1, False)
