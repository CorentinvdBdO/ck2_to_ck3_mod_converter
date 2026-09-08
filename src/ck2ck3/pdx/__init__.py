"""Tokenizer-based parser and writer for Paradox script (CK2 / CK3 ``.txt``).

Round-trip contract: ``parse(write(parse(text)))`` is structurally equal to
``parse(text)``, comments and blank-line groups included.

    >>> from ck2ck3 import pdx
    >>> doc = pdx.parse('culture = illuskan # base\\n')
    >>> doc.get("culture")
    'illuskan'
    >>> pdx.write(doc)
    'culture = illuskan # base\\n'
"""

from .encoding import (
    CK2_ENCODING,
    CK3_ENCODING,
    BOM_PREFIXES,
    encoding_for,
    needs_bom,
    OUT_ENCODING,
    OUT_PLAIN_ENCODING,
    OUT_LOC_ENCODING,
    EncodingWarning,
    read_text,
    write_text,
)
from .errors import Location, PdxError, PdxSyntaxError, Problem
from .nodes import (
    Block,
    Color,
    Document,
    Entry,
    Item,
    Node,
    Operator,
    VarRef,
    as_dict,
    resolve,
    structurally_equal,
    variables,
    walk,
)
from .parser import Parser, parse, parse_file
from .tokens import Date, Token, TokenType, tokenize
from .writer import (
    Writer,
    format_float,
    format_scalar,
    needs_quotes,
    needs_quotes_key,
    write,
    write_file,
)

__all__ = [
    "Block",
    "CK2_ENCODING",
    "CK3_ENCODING",
    "Color",
    "Date",
    "Document",
    "EncodingWarning",
    "Entry",
    "Item",
    "Location",
    "Node",
    "BOM_PREFIXES",
    "encoding_for",
    "needs_bom",
    "OUT_ENCODING",
    "OUT_PLAIN_ENCODING",
    "Operator",
    "OUT_LOC_ENCODING",
    "Parser",
    "PdxError",
    "PdxSyntaxError",
    "Problem",
    "Token",
    "TokenType",
    "VarRef",
    "Writer",
    "as_dict",
    "format_float",
    "format_scalar",
    "needs_quotes",
    "needs_quotes_key",
    "parse",
    "parse_file",
    "read_text",
    "resolve",
    "structurally_equal",
    "tokenize",
    "variables",
    "walk",
    "write",
    "write_file",
    "write_text",
]
