"""Recursive-descent parser for Paradox script.

Grammar (EBNF-ish)::

    document := entry*
    block    := "{" entry* "}"
    entry    := key OP value        # node
              | value               # bare list item
              | block               # anonymous block item
    OP       := "=" | "==" | "!=" | "<" | ">" | "<=" | ">=" | "?="
    value    := scalar | block | TAG block | "@" name
    scalar   := string | int | float | date | bool | identifier
    TAG      := "rgb" | "hsv" | "hsv360"

Comments and blank-line groups are attached to entries; see
:mod:`ck2ck3.pdx.nodes`.
"""

from __future__ import annotations

from pathlib import Path

from .encoding import read_text
from .errors import PdxSyntaxError, Problem
from .nodes import Block, Color, Document, Entry, Item, Node, Operator, VarRef
from .tokens import COLOR_TAGS, Token, TokenType, tokenize

_VALUE_TOKENS = frozenset(
    {
        TokenType.STRING,
        TokenType.INT,
        TokenType.FLOAT,
        TokenType.DATE,
        TokenType.BOOL,
        TokenType.IDENT,
        TokenType.VARREF,
    }
)


class Parser:
    """One instance per file. Not reusable."""

    def __init__(self, text: str, source: str = "<string>", lenient: bool = False):
        self.source = source
        self.lenient = lenient
        self.tokens: list[Token] = list(tokenize(text, source))
        self.pos = 0
        self.last_line = 0
        self.problems: list[Problem] = []

    # -- token helpers -----------------------------------------------------
    def peek(self) -> Token:
        return self.tokens[self.pos]

    def advance(self) -> Token:
        tok = self.tokens[self.pos]
        if tok.type is not TokenType.EOF:
            self.pos += 1
        self.last_line = tok.line
        return tok

    def _problem(self, kind: str, message: str, tok: Token) -> None:
        location = tok.location(self.source)
        if not self.lenient:
            raise PdxSyntaxError(f"{kind}: {message}", location)
        self.problems.append(Problem(kind, message, location))

    # -- entry points ------------------------------------------------------
    def parse(self) -> Document:
        block = self._parse_block(inside=False, open_tok=None)
        return Document(
            entries=block.entries,
            end_comments=block.end_comments,
            source=self.source,
            problems=self.problems,
        )

    # -- grammar -----------------------------------------------------------
    def _parse_block(self, inside: bool, open_tok: Token | None) -> Block:
        block = Block()
        pending: list[str] = []
        pending_blank = False
        last_entry_line = -1
        while True:
            tok = self.peek()

            if tok.type is TokenType.COMMENT:
                self.advance()
                if not pending and block.entries and tok.line == last_entry_line:
                    last = block.entries[-1]
                    if last.trailing_comment is None:
                        last.trailing_comment = tok.text
                        continue
                if not pending:
                    pending_blank = tok.blank_before
                elif tok.blank_before:
                    # A blank line inside a comment group: kept as an empty
                    # string so the writer reproduces the grouping.
                    pending.append("")
                pending.append(tok.text)
                continue

            if tok.type is TokenType.RBRACE:
                self.advance()
                if inside:
                    block.end_comments = pending
                    return block
                self._problem(
                    "stray_close_brace", "'}' without a matching '{'", tok
                )
                continue

            if tok.type is TokenType.EOF:
                if inside:
                    assert open_tok is not None
                    raise PdxSyntaxError(
                        "unclosed block, '}' expected before end of file",
                        open_tok.location(self.source),
                    )
                block.end_comments = pending
                return block

            entry = self._parse_entry()
            if entry is None:
                continue
            entry.leading_comments = pending
            entry.blank_before = (
                (pending_blank if pending else tok.blank_before)
                if block.entries
                else False
            )
            pending = []
            pending_blank = False
            block.entries.append(entry)
            last_entry_line = self.last_line

    def _parse_entry(self) -> Entry | None:
        tok = self.peek()

        if tok.type is TokenType.LBRACE:
            self.advance()
            return Item(value=self._parse_block(True, tok), line=tok.line)

        if tok.type is TokenType.OP:
            self.advance()
            self._problem(
                "orphan_operator", f"operator {tok.text!r} with no key", tok
            )
            return None

        if tok.type not in _VALUE_TOKENS:  # pragma: no cover - defensive
            self.advance()
            self._problem("unexpected_token", f"unexpected {tok.type.value}", tok)
            return None

        self.advance()
        nxt = self.peek()
        if nxt.type is not TokenType.OP:
            return Item(
                value=self._scalar(tok),
                quoted=tok.type is TokenType.STRING,
                line=tok.line,
            )

        self.advance()
        key = tok.value if tok.type is TokenType.STRING else tok.text
        node = Node(
            key=str(key),
            op=nxt.text,
            quoted_key=tok.type is TokenType.STRING,
            line=tok.line,
        )
        val_tok = self.peek()
        if val_tok.type in (TokenType.RBRACE, TokenType.EOF):
            self._problem(
                "missing_value",
                f"{node.key!r} {node.op} is followed by no value",
                val_tok,
            )
            return node
        if val_tok.type is TokenType.COMMENT:
            # `key = # comment` then the value on the next line: legal, the
            # comment simply belongs to nothing. Keep it as the node's trailing
            # comment and carry on with the value.
            self.advance()
            node.trailing_comment = val_tok.text
            val_tok = self.peek()
            if val_tok.type in (TokenType.RBRACE, TokenType.EOF):
                self._problem(
                    "missing_value",
                    f"{node.key!r} {node.op} is followed by no value",
                    val_tok,
                )
                return node
        node.value = self._parse_value()
        node.quoted_value = val_tok.type is TokenType.STRING
        return node

    def _parse_value(self) -> object:
        tok = self.advance()
        if tok.type is TokenType.OP:
            # `OPERATOR = <=` (CK3 parametrised triggers).
            return Operator(tok.text)
        if tok.type is TokenType.LBRACE:
            return self._parse_block(True, tok)
        if (
            tok.type is TokenType.IDENT
            and tok.text in COLOR_TAGS
            and self.peek().type is TokenType.LBRACE
        ):
            open_tok = self.advance()
            return Color(tag=tok.text, block=self._parse_block(True, open_tok))
        return self._scalar(tok)

    @staticmethod
    def _scalar(tok: Token) -> object:
        if tok.type is TokenType.VARREF:
            return VarRef(str(tok.value))
        if tok.type is TokenType.IDENT:
            return tok.text
        return tok.value


def parse(text: str, source: str = "<string>", *, lenient: bool = False) -> Document:
    """Parse Paradox script from a string.

    ``lenient=True`` records recoverable oddities (a stray ``}``, a key with no
    value) on :attr:`Document.problems` instead of raising.
    """
    return Parser(text, source, lenient).parse()


def parse_file(
    path: str | Path,
    *,
    encoding: str = "auto",
    lenient: bool = False,
) -> Document:
    """Read and parse a file. See :func:`ck2ck3.pdx.encoding.read_text`."""
    path = Path(path)
    text, used = read_text(path, encoding)
    doc = Parser(text, str(path), lenient).parse()
    doc.encoding = used
    return doc
