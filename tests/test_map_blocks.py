"""Tests for the temporary CK2 brace-block reader (``ck2ck3.map.blocks``)."""

from __future__ import annotations

from ck2ck3.map.blocks import parse

DEFAULT_MAP_SNIPPET = """\
max_provinces = 2720
definitions = "definition.csv"
externals = { 2314 2316 }

sea_zones = { 1791 1900 } #Trackless Sea 1
sea_zones = { 1902 1976 } #Lakes 2
sea_zones = { 1977 1986 } #Gbor Nor 3

ocean_region = {\t# Trackless Sea
\tsea_zones = { 1 6 }
}

ocean_region = {\t# Lakes
\tsea_zones = { 2 }
}

tree = { 3 4 7 10 }
"""


def test_scalar_and_quoted_values():
    root = parse(DEFAULT_MAP_SNIPPET)
    assert root.int_("max_provinces") == 2720
    assert root.str_("definitions") == "definition.csv"


def test_last_bare_token_before_close_is_kept():
    """Regression: the token right before ``}`` used to be dropped."""
    root = parse("externals = { 2314 2316 }")
    assert root.ints("externals") == [2314, 2316]
    root = parse("provinces = { 223 }")
    assert root.ints("provinces") == [223]
    root = parse("provinces = { 224 1179 1180 }")
    assert root.ints("provinces") == [224, 1179, 1180]


def test_duplicate_keys_are_kept_in_order():
    root = parse(DEFAULT_MAP_SNIPPET)
    zones = root.blocks("sea_zones")
    assert len(zones) == 3
    assert [z.tokens for z in zones] == [
        ["1791", "1900"],
        ["1902", "1976"],
        ["1977", "1986"],
    ]


def test_comment_after_closing_brace_attaches_to_that_block():
    """CK2 names its sea zones only in a trailing comment after ``}``."""
    root = parse(DEFAULT_MAP_SNIPPET)
    assert [z.comment for z in root.blocks("sea_zones")] == [
        "Trackless Sea 1",
        "Lakes 2",
        "Gbor Nor 3",
    ]


def test_comment_after_opening_brace_attaches_to_that_block():
    """CK2 names its ocean regions in a comment after ``{``."""
    root = parse(DEFAULT_MAP_SNIPPET)
    regions = root.blocks("ocean_region")
    assert [r.comment for r in regions] == ["Trackless Sea", "Lakes"]
    assert regions[0].ints("sea_zones") == [1, 6]


def test_nested_blocks_and_ints_helper():
    root = parse("a = { b = { type = plains color = { 7 } } }")
    a = root.blocks("a")[0]
    b = a.blocks("b")[0]
    assert b.str_("type") == "plains"
    assert b.ints("color") == [7]


def test_missing_keys_return_defaults():
    root = parse("x = 1")
    assert root.int_("nope", 5) == 5
    assert root.str_("nope") is None
    assert root.ints("nope") == []
    assert root.blocks("nope") == []
