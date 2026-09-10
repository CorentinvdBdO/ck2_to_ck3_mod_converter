"""The CK2 `history/provinces` `terrain = X` override — reader, table, rule.

Why this exists: in CK2 that line **is** the province's gameplay terrain and
the `terrain.bmp` majority is only the engine's fallback, but the converter
derived `common/province_terrain` from the bitmap alone until lane
`province-terrain`.  1040 of Faerûn's 2125 province files carry an override
and 716 of those disagree with their own bitmap
(`scripts/survey_terrain_history.py`, `docs/step_map_terrain.md`).

The fixture below is a real Faerûn province file's shape (2529 - Wood of Sharp
Teeth) plus a dated block and each of the four invented categories.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from ck2ck3.map import holdings, terrain, terrain_history

REPO = Path(__file__).resolve().parents[1]
TABLE = REPO / "mappings" / "terrain_history_overrides.csv"


# --------------------------------------------------------------------------- #
# 1. the reader
# --------------------------------------------------------------------------- #
FIXTURE = """\
# c_wood_of_sharp_teeth

# County Title
title = c_wood_of_sharp_teeth

# Settlements
max_settlements = 3

b_stepping_stones = tribal
b_deepdelve = castle

# Misc
culture = orc
religion = orc_pantheon
terrain = forest

#History
1375.1.1 = {
\tculture = goblin
}
"""

DATED = """\
title = c_shifting
max_settlements = 2
b_one = castle
terrain = plains

1100.1.1 = {
\tterrain = marsh
}
1400.1.1 = {
\tterrain = desert
}
"""

COMMENTED = """\
title = c_nothing
b_one = castle
#terrain = forest
"""


def write(tmp_path: Path, name: str, text: str) -> Path:
    p = tmp_path / name
    p.write_text(text, encoding="cp1252")
    return p


def test_reads_a_top_level_override(tmp_path: Path):
    h = holdings.read_province_file(
        write(tmp_path, "2529 - Wood of Sharp Teeth.txt", FIXTURE)
    )
    assert h is not None
    assert h.terrains == [(holdings.EPOCH, "forest")]
    assert h.terrain_at((1357, 1, 1)) == "forest"
    # the barony/culture readers must keep working
    assert set(h.at((1357, 1, 1))) == {"b_stepping_stones", "b_deepdelve"}
    assert h.culture_at((1400, 1, 1)) == "goblin"


def test_a_commented_out_override_is_not_one(tmp_path: Path):
    """69 of Faerûn's files carry a bare `#terrain = ` line (`verified`)."""
    h = holdings.read_province_file(write(tmp_path, "7 - Nothing.txt", COMMENTED))
    assert h is not None
    assert h.terrains == []
    assert h.terrain_at((1357, 1, 1)) is None


def test_a_dated_override_resolves_by_date(tmp_path: Path):
    """CK2 allows a dated `terrain =`; Faerûn never uses one, but the reader must."""
    h = holdings.read_province_file(write(tmp_path, "9 - Shifting.txt", DATED))
    assert h is not None
    assert h.terrains == [
        (holdings.EPOCH, "plains"),
        ((1100, 1, 1), "marsh"),
        ((1400, 1, 1), "desert"),
    ]
    assert h.terrain_at((1000, 1, 1)) == "plains"
    assert h.terrain_at((1357, 1, 1)) == "marsh"
    assert h.terrain_at((1500, 1, 1)) == "desert"


@pytest.mark.parametrize(
    "category", ["coastal", "subterranean", "glacier", "arctic"]
)
def test_each_invented_faerun_category_round_trips(tmp_path: Path, category: str):
    text = f"title = c_x\nb_one = castle\nterrain = {category}\n"
    h = holdings.read_province_file(write(tmp_path, f"1 - {category}.txt", text))
    assert h is not None
    assert h.terrain_at((1357, 1, 1)) == category


# --------------------------------------------------------------------------- #
# 2. the decision table
# --------------------------------------------------------------------------- #
def test_the_table_covers_every_category_faerun_uses():
    rules = terrain_history.read_rules(TABLE)
    # the 13 categories `scripts/survey_terrain_history.py` found in Faerûn
    used = {
        "forest", "hills", "coastal", "jungle", "farmlands", "mountain",
        "subterranean", "glacier", "plains", "marsh", "desert", "arctic",
        "steppe",
    }
    assert used <= set(rules), sorted(used - set(rules))


def test_every_invented_category_has_an_explicit_decision_with_a_reason():
    rules = terrain_history.read_rules(TABLE)
    for cat in ("coastal", "subterranean", "glacier", "arctic"):
        rule = rules[cat]
        assert rule.action in (terrain_history.APPLY, terrain_history.KEEP_BITMAP)
        assert len(rule.note) > 80, f"{cat} has no reasoning"


def test_every_applied_key_is_a_real_ck3_terrain_key():
    """No invented terrain id: the value must be one the pixel table also uses."""
    rules = terrain_history.read_rules(TABLE)
    known = set(terrain.CK2_TO_CK3_TERRAIN.values())
    for rule in rules.values():
        if rule.applies:
            assert rule.ck3_terrain in known, rule


def test_no_land_province_can_be_given_a_water_key():
    rules = terrain_history.read_rules(TABLE)
    for rule in rules.values():
        assert not (rule.applies and rule.ck3_terrain in terrain.CK3_WATER_TERRAIN)


def test_coastal_keeps_the_bitmap():
    """The one keep_bitmap decision that changes behaviour; see the row's note."""
    assert not terrain_history.read_rules(TABLE)["coastal"].applies


def test_reader_skips_the_comment_block_and_rejects_a_bad_action(tmp_path: Path):
    p = tmp_path / "t.csv"
    p.write_text(
        "# a comment block, like mappings/vanilla_traits.csv\n"
        "ck2_terrain,action,ck3_terrain,note\n"
        "forest,apply,forest,x\n",
        encoding="utf-8",
    )
    assert terrain_history.read_rules(p)["forest"].ck3_terrain == "forest"

    p.write_text("ck2_terrain,action,ck3_terrain,note\nforest,maybe,forest,x\n")
    with pytest.raises(ValueError, match="action"):
        terrain_history.read_rules(p)

    p.write_text("ck2_terrain,action,ck3_terrain,note\nforest,apply,,x\n")
    with pytest.raises(ValueError, match="no ck3_terrain"):
        terrain_history.read_rules(p)


# --------------------------------------------------------------------------- #
# 3. the application rule, on a synthetic county of three baronies
# --------------------------------------------------------------------------- #
RULES = {
    "farmlands": terrain_history.OverrideRule("farmlands", "apply", "farmlands"),
    "coastal": terrain_history.OverrideRule("coastal", "keep_bitmap", ""),
}


def county(ck2_id: int = 42) -> list[terrain_history.BaronyRef]:
    """One CK2 county -> three CK3 baronies, capital first."""
    return [
        terrain_history.BaronyRef(101, ck2_id, True, "b_cap", "c_x"),
        terrain_history.BaronyRef(102, ck2_id, False, "b_flat", "c_x"),
        terrain_history.BaronyRef(103, ck2_id, False, "b_peak", "c_x"),
    ]


def test_capital_takes_the_override_and_a_strong_non_capital_does_not():
    bitmap = {101: "hills", 102: "plains", 103: "mountains"}
    res = terrain_history.apply_overrides(
        bitmap,
        refs=county(),
        overrides={42: "farmlands"},
        rules=RULES,
    )
    assert res.terrain == {
        101: "farmlands",  # capital: the override always wins
        102: "farmlands",  # non-capital, weak bitmap: the override refines it
        103: "mountains",  # non-capital, strong bitmap: its own pixels win
    }
    assert res.outcomes["applied_capital"] == 1
    assert res.outcomes["applied_weak_bitmap"] == 1
    assert res.outcomes["kept_strong_bitmap"] == 1
    assert res.changed == 2
    assert res.counties_with_override == 1
    # the input is not mutated: the caller diffs the two grids
    assert bitmap[101] == "hills"


def test_a_barony_that_already_agrees_is_not_counted_as_changed():
    res = terrain_history.apply_overrides(
        {101: "farmlands", 102: "plains", 103: "forest"},
        refs=county(),
        overrides={42: "farmlands"},
        rules=RULES,
    )
    assert res.outcomes["already_agreed"] == 1
    assert res.changed == 1


def test_keep_bitmap_changes_nothing_and_is_counted():
    bitmap = {101: "desert", 102: "plains", 103: "hills"}
    res = terrain_history.apply_overrides(
        bitmap, refs=county(), overrides={42: "coastal"}, rules=RULES
    )
    assert res.terrain == bitmap
    assert res.outcomes["kept_rule"] == 3
    assert res.changed == 0
    assert res.counties_with_override == 0


def test_an_unmapped_category_keeps_the_bitmap_and_is_reported():
    bitmap = {101: "desert", 102: "plains", 103: "hills"}
    res = terrain_history.apply_overrides(
        bitmap, refs=county(), overrides={42: "moonscape"}, rules=RULES
    )
    assert res.terrain == bitmap
    assert res.unmapped == {"moonscape": 3}
    assert res.summary()["unmapped_categories"] == {"moonscape": 3}


def test_a_county_with_no_override_is_untouched():
    bitmap = {101: "desert", 102: "plains", 103: "hills"}
    res = terrain_history.apply_overrides(
        bitmap, refs=county(), overrides={}, rules=RULES
    )
    assert res.terrain == bitmap
    assert res.outcomes["no_override"] == 3
    assert res.rows == []


def test_weak_class_set_is_configurable():
    bitmap = {101: "hills", 102: "steppe", 103: "mountains"}
    res = terrain_history.apply_overrides(
        bitmap,
        refs=county(),
        overrides={42: "farmlands"},
        rules=RULES,
        weak_classes=("plains", "farmlands", "steppe"),
    )
    assert res.terrain[102] == "farmlands"
    res2 = terrain_history.apply_overrides(
        bitmap, refs=county(), overrides={42: "farmlands"}, rules=RULES
    )
    assert res2.terrain[102] == "steppe"


def test_empty_weak_set_means_capital_only():
    bitmap = {101: "hills", 102: "plains", 103: "mountains"}
    res = terrain_history.apply_overrides(
        bitmap,
        refs=county(),
        overrides={42: "farmlands"},
        rules=RULES,
        weak_classes=(),
    )
    assert res.terrain == {101: "farmlands", 102: "plains", 103: "mountains"}


def test_evidence_csv_has_one_row_per_affected_province():
    res = terrain_history.apply_overrides(
        {101: "hills", 102: "plains", 103: "mountains"},
        refs=county(),
        overrides={42: "farmlands"},
        rules=RULES,
    )
    text = terrain_history.render_evidence_csv(res)
    lines = text.strip().splitlines()
    assert lines[0].startswith("ck3_id,ck2_province,county,barony,is_capital")
    assert len(lines) == 4
    assert "applied_capital" in lines[1]


# --------------------------------------------------------------------------- #
# 4. the config keys reach MapConfig from the REAL CLI builder
# --------------------------------------------------------------------------- #
def test_cli_config_builder_reads_the_key():
    """A key the CLI builder never reads is a silent no-op whatever the TOML says.

    That is exactly what happened to `[map] colormap` (see the BUG FIXED
    comment in `src/ck2ck3/steps/map.py`), so every new `[map]` key gets this
    test.
    """
    from ck2ck3.steps import map as map_step

    class Cfg:
        raw = {
            "map": {
                "vanilla_km_per_px": 1.0,
                "source_km_per_px": 1.0,
                "province_terrain_history": False,
                "terrain_history_csv": "mappings/other.csv",
                "terrain_history_weak_classes": ["plains"],
            }
        }
        path = Path("configs/x.toml")
        out = Path("/tmp/out")
        prefix = "fae"
        bookmark_date = (1357, 1, 1)
        name = "n"
        version = "0"
        supported_version = "1.19.*"

    class Ctx:
        config = Cfg()

        def ck2(self, *parts):
            return Path("/tmp/ck2").joinpath(*parts)

        def ck3(self, *parts):
            return Path("/tmp/ck3").joinpath(*parts)

    cfg = map_step._map_config(Ctx())
    assert cfg.terrain_history is False
    assert cfg.terrain_history_csv == Path("mappings/other.csv")
    assert cfg.terrain_history_weak == ("plains",)

    Cfg.raw["map"] = {"vanilla_km_per_px": 1.0, "source_km_per_px": 1.0}
    cfg = map_step._map_config(Ctx())
    assert cfg.terrain_history is True
    assert cfg.terrain_history_csv == Path("mappings/terrain_history_overrides.csv")
    assert cfg.terrain_history_weak == ("plains", "farmlands")


def test_faerun_config_turns_it_on_and_names_the_table():
    raw = tomllib.loads((REPO / "configs" / "faerun.toml").read_text())
    m = raw["map"]
    assert m["province_terrain_history"] is True
    assert (REPO / m["terrain_history_csv"]).is_file()
    assert m["terrain_history_weak_classes"] == ["plains", "farmlands"]
