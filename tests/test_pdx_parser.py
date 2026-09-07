"""Parser: one test per grammar item, plus the accessor helpers."""

from __future__ import annotations

import warnings

import pytest

from ck2ck3 import pdx
from ck2ck3.pdx import (
    Block,
    Color,
    Date,
    EncodingWarning,
    Item,
    Node,
    Operator,
    PdxSyntaxError,
    VarRef,
    parse,
    parse_file,
)


def test_key_value():
    doc = parse("culture = illuskan")
    assert doc.get("culture") == "illuskan"
    assert doc["culture"] == "illuskan"
    assert "culture" in doc
    with pytest.raises(KeyError):
        doc["religion"]


@pytest.mark.parametrize("op", ["=", "==", "!=", "<", ">", "<=", ">=", "?="])
def test_every_operator_is_kept(op):
    (node,) = parse(f"age {op} 6").nodes()
    assert (node.key, node.op, node.value) == ("age", op, 6)


def test_comparison_block():
    # `limit = { ROOT = { society_rank == 3 } }`
    doc = parse("limit = { ROOT = { society_rank == 3 } }")
    inner = doc["limit"]["ROOT"]
    (node,) = inner.nodes()
    assert (node.key, node.op, node.value) == ("society_rank", "==", 3)


def test_nested_blocks():
    doc = parse("a = { b = { c = 1 } }")
    assert doc["a"]["b"]["c"] == 1


def test_bare_value_list():
    doc = parse("severe_winter = { 4 10 17 }")
    assert doc["severe_winter"].list_values() == [4, 10, 17]


def test_bare_identifier_list():
    doc = parse("allow = { a b }")
    assert doc["allow"].list_values() == ["a", "b"]


def test_mixed_block():
    doc = parse("x = { 1 2 key = v 3 }")
    block = doc["x"]
    assert block.list_values() == [1, 2, 3]
    assert block.get("key") == "v"


def test_anonymous_block_item():
    doc = parse("x = { { a = 1 } { a = 2 } }")
    items = doc["x"].items()
    assert [i.value["a"] for i in items] == [1, 2]


def test_duplicate_keys_kept_in_order():
    doc = parse("law = a\nlaw = b")
    assert doc.get_all("law") == ["a", "b"]
    assert doc.get("law") == "a"
    assert doc.keys() == ["law", "law"]


def test_quoted_string_value_and_empty_string():
    doc = parse('a = "hello world"\nb = ""')
    assert doc["a"] == "hello world"
    assert doc["b"] == ""


def test_numbers_and_negatives():
    doc = parse("a = 1\nb = -2\nc = 3.5\nd = -0.25")
    assert [doc["a"], doc["b"], doc["c"], doc["d"]] == [1, -2, 3.5, -0.25]
    assert isinstance(doc["a"], int)
    assert isinstance(doc["c"], float)


def test_date_value_and_date_key():
    doc = parse("birth = 1066.1.1\n1355.07.28 = { holder = 1 }")
    assert doc["birth"] == Date(1066, 1, 1)
    assert doc.get("1355.07.28")["holder"] == 1


def test_bool():
    doc = parse("a = yes\nb = no")
    assert doc["a"] is True
    assert doc["b"] is False


def test_variable_definition_and_reference():
    doc = parse("@cost = 5\nprice = @cost")
    assert doc.get("@cost") == 5
    assert doc["price"] == VarRef("cost")
    assert pdx.variables(doc) == {"cost": 5}
    assert pdx.resolve(doc)["price"] == 5


def test_unknown_variable_stays_symbolic():
    doc = parse("price = @nope")
    assert pdx.resolve(doc)["price"] == VarRef("nope")
    with pytest.raises(KeyError):
        pdx.resolve(doc, strict=True)


@pytest.mark.parametrize("tag", ["rgb", "hsv", "hsv360"])
def test_tagged_colors(tag):
    doc = parse(f"color = {tag} {{ 20 30 40 }}")
    value = doc["color"]
    assert isinstance(value, Color)
    assert value.tag == tag
    assert value.components == [20, 30, 40]


def test_untagged_color_is_a_plain_block():
    doc = parse("color = { 255 0 0 }")
    assert isinstance(doc["color"], Block)
    assert doc["color"].list_values() == [255, 0, 0]


def test_operator_as_value():
    # CK3: events/diarchy_events/vizierate_events.txt:109
    doc = parse("OPERATOR = <=")
    assert doc["OPERATOR"] == Operator("<=")


def test_leading_comments_attach_to_the_next_node():
    doc = parse("# one\n# two\ntitle = c_waterdeep")
    (node,) = doc.nodes()
    assert node.leading_comments == ["# one", "# two"]


def test_blank_line_inside_a_comment_group_is_kept():
    doc = parse("# one\n\n# two\ntitle = x")
    (node,) = doc.nodes()
    assert node.leading_comments == ["# one", "", "# two"]


def test_trailing_comment_attaches_to_the_same_line():
    doc = parse("title = x # here\nother = y")
    first, second = doc.nodes()
    assert first.trailing_comment == "# here"
    assert second.trailing_comment is None


def test_trailing_comment_after_a_closing_brace():
    # Faerûn: history/titles/c_thingulphar.txt:9
    doc = parse("1324.1.1={holder=30928} #Owol[5405]")
    (node,) = doc.nodes()
    assert node.trailing_comment == "#Owol[5405]"


def test_comment_on_the_opening_brace_line_leads_the_first_inner_entry():
    doc = parse("x = { # why\n\ta = 1\n}")
    (inner,) = doc["x"].nodes()
    assert inner.leading_comments == ["# why"]


def test_comments_at_the_end_of_a_block_are_kept():
    doc = parse("x = {\n\ta = 1\n\t# last word\n}")
    assert doc["x"].end_comments == ["# last word"]


def test_comments_at_the_end_of_a_file_are_kept():
    doc = parse("a = 1\n# bye\n")
    assert doc.end_comments == ["# bye"]


def test_blank_group_flag():
    doc = parse("a = 1\n\nb = 2\nc = 3")
    assert [n.blank_before for n in doc.nodes()] == [False, True, False]


def test_first_entry_never_carries_a_blank_flag():
    doc = parse("\n\na = 1")
    assert doc.nodes()[0].blank_before is False


def test_node_delegates_dict_access_to_a_block_value():
    doc = parse("x = { a = 1\na = 2 }")
    node = doc.get_node("x")
    assert node.get("a") == 1
    assert node.get_all("a") == [1, 2]
    assert node["a"] == 1
    assert "a" in node


def test_walk_visits_every_entry():
    doc = parse("a = { b = { c = 1 } }")
    keys = [e.key for _, e in pdx.walk(doc) if isinstance(e, Node)]
    assert sorted(keys) == ["a", "b", "c"]


def test_errors_carry_file_line_col():
    with pytest.raises(PdxSyntaxError) as exc:
        parse("a = {\n\tb = 1\n", "f.txt")
    assert str(exc.value).startswith("f.txt:1:5")


def test_stray_close_brace_is_an_error_by_default():
    with pytest.raises(PdxSyntaxError) as exc:
        parse("a = 1\n}\n", "f.txt")
    assert "stray_close_brace" in str(exc.value)


def test_stray_close_brace_is_recorded_in_lenient_mode():
    doc = parse("a = 1\n}\nb = 2\n", "f.txt", lenient=True)
    assert doc.keys() == ["a", "b"]
    assert [p.kind for p in doc.problems] == ["stray_close_brace"]
    assert doc.problems[0].location.line == 2


def test_key_without_a_value_is_recorded_in_lenient_mode():
    doc = parse("x = { a = }\n", lenient=True)
    (node,) = doc["x"].nodes()
    assert node.value is None
    assert [p.kind for p in doc.problems] == ["missing_value"]


def test_parse_file_reads_cp1252(tmp_path):
    path = tmp_path / "ck2.txt"
    path.write_bytes("name = \"Bj\xf8rn\"\n".encode("cp1252"))
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        doc = parse_file(path)
    assert doc["name"] == "Bj\xf8rn"
    assert doc.encoding == "cp1252"
    assert any(w.category is EncodingWarning for w in caught)


def test_parse_file_reads_utf8_with_bom(tmp_path):
    path = tmp_path / "ck3.txt"
    path.write_bytes("name = \"Bjørn\"\n".encode("utf-8-sig"))
    doc = parse_file(path)
    assert doc["name"] == "Bjørn"
    assert doc.encoding == "utf-8-sig"


def test_parse_file_with_an_explicit_encoding(tmp_path):
    path = tmp_path / "ck2.txt"
    path.write_bytes("name = \"Bj\xf8rn\"\n".encode("cp1252"))
    doc = parse_file(path, encoding=pdx.CK2_ENCODING)
    assert doc["name"] == "Bj\xf8rn"


def test_item_and_node_are_distinguishable():
    doc = parse("x = { 1 a = 2 }")
    entries = doc["x"].entries
    assert isinstance(entries[0], Item)
    assert isinstance(entries[1], Node)
