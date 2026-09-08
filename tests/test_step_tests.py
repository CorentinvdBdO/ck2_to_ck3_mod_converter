"""Step ``tests`` — the CK3 scripted-test grammar it writes.

Fixture-driven: a two-file mini output mod is written into ``tmp_path``, the
step reads it back the way it reads the real one, and the emitted text is
compared byte for byte. Grammar reference:
``claudespace/docs/ck3_test_framework.md`` §2.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ck2ck3.config import Config
from ck2ck3.context import Context
from ck2ck3.steps import tests as tests_step

BOOKMARKS = """
bm_low = {
\tstart_date = 1357.1.1
\tweight = { value = 10 }
\tcharacter = {
\t\tname = "bookmark_fae_1"
\t\thistory_id = fae_1
\t\ttitle = k_low
\t}
}

bm_default = {
\tstart_date = 1357.1.1
\tweight = { value = 100 }
\tcharacter = {
\t\tname = "bookmark_fae_2"
\t\thistory_id = fae_2
\t\ttitle = k_high
\t\tcharacter = {
\t\t\tname = "bookmark_fae_3"
\t\t\thistory_id = fae_3
\t\t}
\t}
\tcharacter = {
\t\tname = "bookmark_fae_missing"
\t\thistory_id = fae_404
\t\ttitle = k_high
\t}
}
"""

TITLES = """
k_high = {
\t1200.1.1 = { holder = fae_9 }
\t1300.1.1 = { holder = fae_2 }
\t1400.1.1 = { holder = fae_77 }
}
k_dead = {
\t1300.1.1 = { holder = 0 }
}
k_nohistory = {
\t1300.1.1 = { government = feudal_government }
}
"""

CHARACTERS = """
fae_1 = { name = One }
fae_2 = { name = Two }
fae_3 = { name = Three }
fae_9 = { name = Nine }
"""

PROVINCES = """
1 = { culture = a religion = b holding = castle_holding }
2 = { culture = a religion = b holding = city_holding }
7 = { culture = a religion = b holding = city_holding }
"""

DEFINITION = """\
0;0;0;0;x;x;
1;10;10;10;b_one;x;
2;20;20;20;b_two;x;
3;30;30;30;b_three;x;
7;70;70;70;b_seven;x;
9;90;90;90;SLUG_NO_COUNTY;x;
"""

DEFAULT_MAP = """
sea_zones = RANGE { 100 110 }
lakes = LIST { 7 }
river_provinces = RANGE { 200 202 }
"""


CONFIG = """\
[mod]
name = "Test"
prefix = "tst"
version = "0.1.0"
supported_version = "1.19.*"
tags = []
bookmark_date = "1357.1.1"
replace_paths = ["tests"]

[paths]
ck2_game = "{root}"
ck2_mod = "{root}"
ck3_game = "{root}"
out = "{out}"

[tests]
sample = {sample}
"""


def make_ctx(tmp_path: Path, sample: int = 0, **mod: object) -> Context:
    out = tmp_path / "out"
    out.mkdir()
    (out / "README.md").write_text("keep\n")
    toml = tmp_path / "test.toml"
    toml.write_text(CONFIG.format(root=tmp_path, out=out, sample=sample))
    config = Config.load(toml)
    files = {
        "common/bookmarks/bookmarks/tst_bookmarks.txt": BOOKMARKS,
        "history/titles/tst_titles.txt": TITLES,
        "history/characters/tst_chars.txt": CHARACTERS,
        "history/provinces/tst_provinces.txt": PROVINCES,
        "map_data/definition.csv": DEFINITION,
        "map_data/default.map": DEFAULT_MAP,
    }
    files.update({k: v for k, v in mod.items() if isinstance(v, str)})
    for rel, text in files.items():
        if text is None:
            continue
        path = out / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return Context(config)


# -- reading the generated mod back ---------------------------------------
def test_the_default_bookmark_is_the_highest_weight_one(tmp_path):
    """`-test` starts the default bookmark; a test at another date can only fail."""
    ctx = make_ctx(tmp_path)
    marks = tests_step.read_bookmarks(ctx)
    assert {m.key for m in marks} == {"bm_low", "bm_default"}
    assert tests_step.choose_bookmark(marks, None).key == "bm_default"
    assert tests_step.choose_bookmark(marks, "bm_low").key == "bm_low"
    with pytest.raises(ValueError, match="bm_nope"):
        tests_step.choose_bookmark(marks, "bm_nope")


def test_nested_bookmark_characters_are_collected(tmp_path):
    ctx = make_ctx(tmp_path)
    mark = tests_step.choose_bookmark(tests_step.read_bookmarks(ctx), None)
    assert [c.history_id for c in mark.characters] == ["fae_2", "fae_3", "fae_404"]


def test_the_holder_in_effect_at_the_date_wins(tmp_path):
    """The last dated block at or before the date; `holder = 0` asserts nothing."""
    ctx = make_ctx(tmp_path)
    holders = tests_step.read_title_holders(ctx, (1357, 1, 1))
    assert holders == {"k_high": "fae_2"}


def test_land_provinces_are_history_blocks_that_the_map_paints(tmp_path):
    """Province 3 has no history block, 7 is a lake, 9 has no county."""
    ctx = make_ctx(tmp_path)
    assert tests_step.read_land_provinces(ctx) == [1, 2]


def test_water_declarations_cover_both_range_and_list(tmp_path):
    ctx = make_ctx(tmp_path)
    water = tests_step.read_water_provinces(ctx)
    assert 100 in water and 110 in water and 7 in water and 201 in water
    assert 1 not in water


def test_a_sample_is_spread_not_truncated():
    """A half-converted map must not be tested only at province id 1..n."""
    assert tests_step.spread(list(range(100)), 4) == [0, 25, 50, 75]
    assert tests_step.spread([1, 2], 5) == [1, 2]
    assert tests_step.spread([1, 2], 0) == [1, 2]


# -- the emitted grammar ---------------------------------------------------
def test_the_whole_file_is_the_expected_grammar(tmp_path):
    ctx = make_ctx(tmp_path)
    marks = tests_step.read_bookmarks(ctx)
    text, counts = tests_step.build(
        ctx,
        marks,
        tests_step.read_title_holders(ctx, (1357, 1, 1)),
        tests_step.read_land_provinces(ctx),
        prefix="tst",
        bookmark=tests_step.choose_bookmark(marks, None),
        sample=0,
        declared=tests_step.read_character_ids(ctx),
    )
    body = text.split("\n\n", 1)[1] if "\n\n" in text else text
    assert body == (
        'tst_bookmark_char_fae_2 = {\n'
        '\tname = "bookmark bm_default: bookmark_fae_2 exists and holds k_high"\n'
        '\tcharacter_target = fae_2\n'
        '\n'
        '\texpect = {\n'
        '\t\tis_alive = yes\n'
        '\t\ttitle:k_high = { holder = root }\n'
        '\t}\n'
        '}\n'
        '\n'
        'tst_bookmark_char_fae_3 = {\n'
        '\tname = "bookmark bm_default: bookmark_fae_3 exists"\n'
        '\tcharacter_target = fae_3\n'
        '\n'
        '\texpect = {\n'
        '\t\tis_alive = yes\n'
        '\t}\n'
        '}\n'
        '\n'
        'tst_history_holder_k_high = {\n'
        '\tname = "k_high is held by fae_2 at 1357.1.1"\n'
        '\ttitle_target = k_high\n'
        '\n'
        '\texpect = {\n'
        '\t\tholder = character:fae_2\n'
        '\t}\n'
        '}\n'
        '\n'
        'tst_map_province_1 = {\n'
        '\tname = "province 1 is land with a county, culture and faith"\n'
        '\n'
        '\texpect = {\n'
        '\t\tprovince:1 = {\n'
        '\t\t\tis_sea_province = no\n'
        '\t\t\texists = county\n'
        '\t\t\texists = culture\n'
        '\t\t\texists = faith\n'
        '\t\t}\n'
        '\t}\n'
        '}\n'
        '\n'
        'tst_map_province_2 = {\n'
        '\tname = "province 2 is land with a county, culture and faith"\n'
        '\n'
        '\texpect = {\n'
        '\t\tprovince:2 = {\n'
        '\t\t\tis_sea_province = no\n'
        '\t\t\texists = county\n'
        '\t\t\texists = culture\n'
        '\t\t\texists = faith\n'
        '\t\t}\n'
        '\t}\n'
        '}\n'
        '\n'
        'tst_map_every_ruler_holds_its_capital = {\n'
        '\tname = "every ruler personally holds its capital barony"\n'
        '\n'
        '\texpect = {\n'
        '\t\tany_ruler = {\n'
        '\t\t\tcount = all\n'
        '\t\t\tOR = {\n'
        '\t\t\t\tis_playable_character = no\n'
        '\t\t\t\thighest_held_title_tier < tier_county\n'
        '\t\t\t\tAND = {\n'
        '\t\t\t\t\tcapital_barony.holder = this\n'
        '\t\t\t\t\tcapital_barony = capital_county.capital_vassal\n'
        '\t\t\t\t}\n'
        '\t\t\t}\n'
        '\t\t}\n'
        '\t}\n'
        '}\n'
    )
    assert counts["tests"] == 6  # 2 bookmark + 1 title + 2 province + 1 aggregate
    # fae_404 is in the bookmark but not in history/characters: no test.
    assert counts["bookmark_characters"] == 2
    assert counts["bookmark_characters_skipped"] == 1


def test_every_test_has_a_trigger_and_no_empty_effect(tmp_path):
    """The two parse errors the game reports: `assert`/`expect` with no trigger."""
    ctx = make_ctx(tmp_path)
    result = tests_step.run(ctx)
    text = ctx.out_path("tests", "tst_generated_tests.txt").read_text(
        encoding="utf-8-sig"
    )
    blocks = [b for b in text.split("\n}\n") if " = {" in b]
    assert blocks, "no tests emitted"
    for block in blocks:
        assert "expect = {" in block
        after = block.split("expect = {", 1)[1]
        assert after.strip().splitlines(), "expect is missing trigger"
        assert "effect = {" not in block, "an empty effect is a parse error"
    assert result.counts["tests"] == len(blocks)


def test_the_file_always_carries_a_utf8_bom(tmp_path):
    """All 18 vanilla `game/tests/*.txt` start `ef bb bf`, 17 of them pure ASCII."""
    ctx = make_ctx(tmp_path)
    tests_step.run(ctx)
    raw = ctx.out_path("tests", "tst_generated_tests.txt").read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    assert raw[3:].decode("utf-8").isascii()
    assert b"\xef\xbb\xbf" not in raw[3:], "BOM written twice"


def test_the_sample_size_is_honoured(tmp_path):
    ctx = make_ctx(tmp_path, sample=1)
    result = tests_step.run(ctx)
    assert result.counts["provinces"] == 1
    assert result.counts["provinces_available"] == 2


def test_no_bookmark_means_the_step_skips_rather_than_writes_nothing(tmp_path):
    ctx = make_ctx(tmp_path)
    (ctx.out_path("common", "bookmarks", "bookmarks", "tst_bookmarks.txt")).unlink()
    result = tests_step.run(ctx)
    assert result.skipped
    assert "bookmarks step" in result.summary


def test_a_missing_replace_path_is_warned_about(tmp_path):
    """Vanilla's 18 test files hard-code 1066 ids and fail en masse otherwise."""
    ctx = make_ctx(tmp_path)
    object.__setattr__(ctx.config, "replace_paths", ())
    result = tests_step.run(ctx)
    assert any("replace_paths" in w for w in result.warnings)


def test_outputs_is_the_tests_folder():
    assert tests_step.OUTPUTS == ("tests",)
