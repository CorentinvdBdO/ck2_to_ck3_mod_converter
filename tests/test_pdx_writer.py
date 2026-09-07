"""Writer: exact output for each grammar item, then the round-trip contract."""

from __future__ import annotations

import pytest

from ck2ck3 import pdx
from ck2ck3.pdx import parse, structurally_equal, write

SAMPLES = {
    "key_value": "culture = illuskan\n",
    "operators": "age > 6\nrank <= 3\nvalue != 2\nx ?= 1\n",
    "nested": "a = {\n\tb = {\n\t\tc = 1\n\t}\n}\n",
    "value_list": "severe_winter = { 4 10 17 }\n",
    "ident_list": "allow = { a b }\n",
    "empty_block": "x = { }\n",
    "mixed": "x = {\n\t1\n\tkey = v\n}\n",
    "quoted": 'name = "hello world"\nempty = ""\n',
    "escaped": 'name = "say \\"hi\\""\n',
    "numbers": "a = 1\nb = -2\nc = 3.5\nd = -0.25\n",
    "date": "birth = 1066.1.1\n1355.7.28 = {\n\tholder = 1\n}\n",
    "bools": "a = yes\nb = no\n",
    "variables": "@cost = 5\nprice = @cost\n",
    "colors": "color = rgb { 20 30 40 }\ncolor2 = hsv { 0.5 1.0 1.0 }\n",
    "operator_value": "OPERATOR = <=\n",
    "leading_comment": "# one\n# two\ntitle = x\n",
    "trailing_comment": "title = x # here\n",
    "block_trailing_comment": "x = {\n\ta = 1\n} # after\n",
    "end_comment": "x = {\n\ta = 1\n\t# last\n}\n",
    "file_end_comment": "a = 1\n# bye\n",
    "blank_group": "a = 1\n\nb = 2\n",
    "blank_in_comment_group": "# one\n\n# two\na = 1\n",
    "duplicate_keys": "law = a\nlaw = b\n",
    "anonymous_blocks": "x = {\n\t{\n\t\ta = 1\n\t}\n\t{\n\t\ta = 2\n\t}\n}\n",
}


@pytest.mark.parametrize("name", sorted(SAMPLES))
def test_writer_reproduces_the_canonical_layout(name):
    text = SAMPLES[name]
    assert write(parse(text, name)) == text


@pytest.mark.parametrize("name", sorted(SAMPLES))
def test_round_trip_is_structurally_equal(name):
    first = parse(SAMPLES[name], name)
    second = parse(write(first), name)
    assert structurally_equal(first, second)


def test_writer_keeps_a_date_key_bare():
    # A key is a string, kept verbatim: no quotes, no zero-padding change.
    written = write(parse("1355.07.28 = { holder = 1 }"))
    assert written == "1355.07.28 = {\n\tholder = 1\n}\n"


def test_writer_quotes_a_string_that_would_change_type():
    doc = pdx.Document(entries=[pdx.Node(key="a", value="5"), pdx.Node(key="b", value="yes")])
    assert write(doc) == 'a = "5"\nb = "yes"\n'
    again = parse(write(doc))
    assert again["a"] == "5" and again["b"] == "yes"


def test_writer_never_uses_exponent_notation():
    # CK3 script has no exponent syntax; -3e-05 must round-trip as a float.
    doc = parse("mult = -0.00003")
    assert write(doc) == "mult = -0.00003\n"
    assert parse(write(doc))["mult"] == -3e-05


def test_writer_keeps_an_empty_key_value():
    doc = parse("x = { a = }", lenient=True)
    assert write(doc) == "x = {\n\ta =\n}\n"


def test_canonical_mode_drops_comments_and_blanks():
    text = "# lead\na = 1 # tail\n\nb = { 1 2 }\n"
    assert write(parse(text), canonical=True) == "a = 1\nb = { 1 2 }\n"


def test_canonical_mode_compares_meaning_not_layout():
    left = parse("a=1 b={2 3}")
    right = parse("# c\na = 1\n\nb = {\n\t2\n\t3\n}\n")
    assert write(left, canonical=True) == write(right, canonical=True)


def test_indent_can_be_spaces():
    assert write(parse("a = { b = 1 }"), indent="    ") == "a = {\n    b = 1\n}\n"


def test_write_file_is_utf8_without_bom(tmp_path):
    path = tmp_path / "out.txt"
    pdx.write_file(parse('name = "Bjørn"'), path)
    assert path.read_bytes() == 'name = "Bjørn"\n'.encode("utf-8")


def test_write_file_header(tmp_path):
    path = tmp_path / "out.txt"
    pdx.write_file(parse("a = 1"), path, header="# generated")
    assert path.read_text(encoding="utf-8") == "# generated\na = 1\n"


def test_structurally_equal_can_ignore_comments():
    left = parse("a = 1\n")
    right = parse("# note\na = 1\n")
    assert not structurally_equal(left, right)
    assert structurally_equal(left, right, comments=False)


def test_structurally_equal_keeps_bool_and_int_apart():
    assert not structurally_equal(parse("a = yes"), parse("a = 1"))


# -- comment mode (added by lane `traits`) ---------------------------------
def test_commented_mode_prefixes_every_line():
    """`commented=True` turns a tree into dead script the game ignores."""
    text = (
        "creature_elf = {\n"
        "\tdiplomacy = 1 # ears\n"
        "\n"
        "\topposites = { creature_orc }\n"
        "}\n"
    )
    out = pdx.write(pdx.parse(text), commented=True)
    assert all(line.startswith("#") for line in out.splitlines())
    # a preserved blank line stays a bare `#`, not `# `
    assert "#\n" in out
    # nothing is left for the parser to see
    assert pdx.parse(out).nodes() == []


def test_commented_mode_is_reversible():
    """Stripping the prefix gives back exactly the default rendering."""
    text = (
        "# lead\n"
        "t = {\n"
        "\ta = 1 # trail\n"
        "\tb = { 1 2 3 }\n"
        "\t# end\n"
        "}\n"
    )
    doc = pdx.parse(text)
    plain = pdx.write(doc)
    commented = pdx.write(doc, commented=True)
    revived = "\n".join(
        line[2:] if line.startswith("# ") else line[1:]
        for line in commented.splitlines()
    )
    assert revived + "\n" == plain
    assert pdx.structurally_equal(pdx.parse(revived), doc)
