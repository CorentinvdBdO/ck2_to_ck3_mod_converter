"""Tokenizer: one test per grammar item."""

from __future__ import annotations

import pytest

from ck2ck3.pdx.errors import PdxSyntaxError
from ck2ck3.pdx.tokens import Date, TokenType, escape, tokenize, unescape


def types(text: str) -> list[TokenType]:
    return [t.type for t in tokenize(text)]


def values(text: str) -> list[object]:
    return [t.value for t in tokenize(text) if t.type is not TokenType.EOF]


def test_simple_assignment():
    assert types("a = b") == [
        TokenType.IDENT,
        TokenType.OP,
        TokenType.IDENT,
        TokenType.EOF,
    ]


@pytest.mark.parametrize("op", ["=", "==", "!=", "<", ">", "<=", ">=", "?="])
def test_every_operator(op):
    toks = list(tokenize(f"a {op} 1"))
    assert toks[1].type is TokenType.OP
    assert toks[1].text == op


def test_numbers():
    assert values("1 -2 3.5 -0.25 .5") == [1, -2, 3.5, -0.25, 0.5]


def test_exponent_float_is_a_float():
    # Written by CK3 itself: common/script_values/00_faction_values.txt.
    assert values("-3e-05") == [-3e-05]


def test_date_is_its_own_type():
    (tok,) = [t for t in tokenize("1066.1.1") if t.type is not TokenType.EOF]
    assert tok.type is TokenType.DATE
    assert tok.value == Date(1066, 1, 1)
    assert str(tok.value) == "1066.1.1"


def test_bools():
    assert values("yes no") == [True, False]


def test_quoted_string_and_empty_string():
    assert values('"hello world" ""') == ["hello world", ""]


def test_escaped_quote_in_string():
    assert values(r'"say \"hi\""') == ['say "hi"']
    assert escape('say "hi"') == r'say \"hi\"'
    assert unescape(r"a\\b") == "a\\b"


def test_hash_inside_string_is_not_a_comment():
    assert values('"a # b"') == ["a # b"]


def test_comment_is_a_token_not_a_skip():
    toks = [t for t in tokenize("# lead\na = b # tail\n") if t.type is TokenType.COMMENT]
    assert [t.text for t in toks] == ["# lead", "# tail"]


def test_variable_reference():
    (tok,) = [t for t in tokenize("@my_var") if t.type is not TokenType.EOF]
    assert tok.type is TokenType.VARREF
    assert tok.value == "my_var"


def test_at_inside_a_word_is_not_a_variable():
    # Faerûn: common/cb_types/pagan_cbs.txt:229
    assert values("won_war@event_target:defender_target") == [
        "won_war@event_target:defender_target"
    ]


def test_blank_line_flag():
    toks = [t for t in tokenize("a = 1\n\nb = 2") if t.type is TokenType.IDENT]
    assert [t.blank_before for t in toks] == [False, True]


def test_line_and_column_are_one_based():
    toks = list(tokenize("a = 1\n\tbb = 2"))
    assert (toks[0].line, toks[0].col) == (1, 1)
    assert (toks[3].line, toks[3].col) == (2, 2)


def test_cr_only_line_endings():
    # Faerûn: history/titles/k_horthgars_horde.txt is CR-terminated, so a
    # comment must stop at the CR or it swallows the whole file.
    toks = [t.type for t in tokenize("a = 1 # c\rb = 2")]
    assert toks.count(TokenType.IDENT) == 2


def test_unknown_character_is_an_error_with_a_location():
    with pytest.raises(PdxSyntaxError) as exc:
        list(tokenize('a = "unterminated\n', "f.txt"))
    assert exc.value.location.line == 1
    assert "f.txt:1:5" in str(exc.value)
