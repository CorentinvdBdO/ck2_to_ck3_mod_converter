"""`overrides/lake_to_land.csv` -- a CK2 plateau lake becomes CK3 land/marsh.

Why this exists: CK3 has one global water level, and CK2 draws a lake's own
`topology.bmp` pixels near sea level regardless of the plateau under it
(Lake Thaylambar's raw bytes are 85-92 of 255, `scripts/measure_high_lakes.py`),
so reclassifying the province is not enough -- the elevation has to be
replaced too (`docs/step_map_heightmap.md` §2h iii).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from ck2ck3.map import lake_to_land as l2l

# --------------------------------------------------------------------------- #
# 1. the reader
# --------------------------------------------------------------------------- #
CSV_TEXT = """\
# comment header, must be skipped
ck2_id,action,reason
101,marsh,"Thay plateau lake"
202,land,"tiny pond, no title"
"""


def test_read_overrides(tmp_path: Path):
    p = tmp_path / "lake_to_land.csv"
    p.write_text(CSV_TEXT, encoding="utf-8")
    rules = l2l.read_overrides(p)
    assert set(rules) == {101, 202}
    assert rules[101].action == "marsh"
    assert rules[101].reason == "Thay plateau lake"
    assert rules[202].action == "land"


def test_read_overrides_missing_file_is_empty(tmp_path: Path):
    assert l2l.read_overrides(tmp_path / "nope.csv") == {}


def test_read_overrides_rejects_bad_action(tmp_path: Path):
    p = tmp_path / "bad.csv"
    p.write_text("ck2_id,action,reason\n1,ocean,x\n", encoding="utf-8")
    with pytest.raises(ValueError, match="ocean"):
        l2l.read_overrides(p)


# --------------------------------------------------------------------------- #
# 2. patch_water_ids
# --------------------------------------------------------------------------- #
def test_patch_water_ids_removes_overridden_ids_from_all_three_sets():
    rules = {101: l2l.LakeToLandRule(101, "marsh"), 202: l2l.LakeToLandRule(202, "land")}
    sea_ids, lake_ids, river_ids = l2l.patch_water_ids(
        rules, sea_ids={9, 101, 202}, lake_ids={101, 105}, river_ids={202, 9},
    )
    assert lake_ids == {105}
    assert river_ids == {9}  # 202 removed; 9 stays (only 101/202 targeted)
    assert sea_ids == {9}    # 101/202 removed; 9 (never targeted) stays


def test_patch_water_ids_refuses_a_true_sea_id():
    warnings = []
    rules = {9: l2l.LakeToLandRule(9, "marsh")}
    sea_ids, lake_ids, river_ids = l2l.patch_water_ids(
        rules, sea_ids={9}, lake_ids={101}, river_ids=set(),
        warn=warnings.append,
    )
    assert sea_ids == {9}    # unchanged: a true sea zone is refused
    assert lake_ids == {101}  # unchanged: 9 was never a lake anyway
    assert warnings and "sea zone" in warnings[0]


def test_patch_water_ids_accepts_a_lake_id_that_is_also_in_sea_ids():
    """The bug a real conversion run caught: CK2 defines a lake as a sea
    zone inside a `Lakes`-named ocean_region, so every real lake id is *also*
    in `sea_ids` -- refusing on `in sea_ids` alone rejected every lake this
    module exists for. `ck2ck3.map.idmap.build`'s own `is_sea` rule
    (`in sea_ids and not in lake_ids and not in river_ids`) is the one to
    match."""
    warnings = []
    rules = {101: l2l.LakeToLandRule(101, "marsh")}
    sea_ids, lake_ids, river_ids = l2l.patch_water_ids(
        rules, sea_ids={101, 202}, lake_ids={101}, river_ids=set(),
        warn=warnings.append,
    )
    assert lake_ids == set()
    assert warnings == []


def test_patch_water_ids_a_lake_dropped_from_sea_ids_is_not_is_sea_anymore():
    """The second bug a real conversion run caught: dropping an id from
    `lake_ids` alone leaves it in `sea_ids`, so `idmap.build`'s own rule
    (`in sea_ids and not in lake_ids and not in river_ids`) makes it a *true
    sea* province instead of land -- `default.map` kept listing it, just
    under `sea_zones` instead of `lakes` (`sea` count +5, `lakes` -5 on the
    coordinator's second run). This mirrors `idmap.build`'s own `is_sea`
    formula directly, so a future change to one cannot silently diverge from
    the other."""
    rules = {101: l2l.LakeToLandRule(101, "marsh")}
    sea_ids, lake_ids, river_ids = l2l.patch_water_ids(
        rules, sea_ids={101}, lake_ids={101}, river_ids=set(),
    )
    is_sea = 101 in sea_ids and 101 not in lake_ids and 101 not in river_ids
    assert is_sea is False


# --------------------------------------------------------------------------- #
# fixture: a 40x40 canvas, land at 20000, a 6x6 "lake" hole at 4700 in the
# middle (CK3 id 2), ordinary land is CK3 id 1
# --------------------------------------------------------------------------- #
def _fixture():
    h, w = 40, 40
    ck3_raster = np.ones((h, w), dtype=np.int32)
    ck3_raster[17:23, 17:23] = 2  # the lake province, ck2 id 101 -> ck3 id 2
    heights = np.full((h, w), 20000, dtype=np.uint16)
    heights[17:23, 17:23] = 4700  # CK2's own near-water-level pixels
    codes_tgt = np.full((h, w), 3, dtype=np.uint16)  # 3 = "plains" in code_names below
    codes_tgt[17:23, 17:23] = 5  # whatever CK2 categorised the water pixels as
    code_names = ["", "farmlands", "mountains", "plains", "hills", "ocean", "marsh"]
    ck2_to_ck3 = {101: 2}
    water_mask = np.zeros((h, w), dtype=bool)  # already patched: nothing is water now
    return ck3_raster, heights, codes_tgt, code_names, ck2_to_ck3, water_mask


# --------------------------------------------------------------------------- #
# 3. patch_codes
# --------------------------------------------------------------------------- #
def test_patch_codes_marsh_forces_the_marsh_category():
    ck3_raster, _, codes_tgt, code_names, ck2_to_ck3, water_mask = _fixture()
    rules = {101: l2l.LakeToLandRule(101, "marsh")}
    out, stats = l2l.patch_codes(
        codes_tgt, ck3_raster, ck2_to_ck3, rules, code_names, water_mask,
    )
    marsh_code = code_names.index("marsh")
    assert (out[17:23, 17:23] == marsh_code).all()
    assert stats["marsh"] == 1


def test_patch_codes_land_takes_the_neighbour_majority():
    ck3_raster, _, codes_tgt, code_names, ck2_to_ck3, water_mask = _fixture()
    rules = {101: l2l.LakeToLandRule(101, "land")}
    out, stats = l2l.patch_codes(
        codes_tgt, ck3_raster, ck2_to_ck3, rules, code_names, water_mask,
    )
    plains_code = code_names.index("plains")
    assert (out[17:23, 17:23] == plains_code).all()  # every neighbour is plains
    assert stats["land"] == 1


def test_patch_codes_no_rules_is_a_no_op():
    ck3_raster, _, codes_tgt, code_names, ck2_to_ck3, water_mask = _fixture()
    out, stats = l2l.patch_codes(
        codes_tgt, ck3_raster, ck2_to_ck3, {}, code_names, water_mask,
    )
    assert out is codes_tgt
    assert stats == {}


# --------------------------------------------------------------------------- #
# 4. inpaint_heights -- the part that actually fixes the shaft
# --------------------------------------------------------------------------- #
def test_inpaint_heights_raises_the_hole_to_plateau_level():
    ck3_raster, heights, _, _, ck2_to_ck3, water_mask = _fixture()
    rules = {101: l2l.LakeToLandRule(101, "land")}
    out, stats = l2l.inpaint_heights(
        heights, ck3_raster, ck2_to_ck3, rules, water_mask, iterations=200,
    )
    hole = out[17:23, 17:23].astype(np.int64)
    # the whole point: no longer near sea level, close to the surrounding
    # plateau (a flat 20000 all around the fixture's own hole)
    assert hole.min() > 15000, f"hole min {hole.min()} still reads like a shaft"
    assert abs(int(np.median(hole)) - 20000) < 2000
    assert stats["holes_px"] == 36
    assert stats["before_median"] == 4700.0
    assert stats["after_min"] > stats["before_min"]
    # land outside the hole is byte-identical
    assert (out[:15, :] == heights[:15, :]).all()


def test_inpaint_heights_no_rules_is_a_no_op():
    ck3_raster, heights, _, _, ck2_to_ck3, water_mask = _fixture()
    out, stats = l2l.inpaint_heights(heights, ck3_raster, ck2_to_ck3, {}, water_mask)
    assert out is heights
    assert stats == {}


def test_inpaint_heights_skips_a_rule_with_no_surviving_ck3_id():
    ck3_raster, heights, _, _, ck2_to_ck3, water_mask = _fixture()
    rules = {999: l2l.LakeToLandRule(999, "land")}  # never in ck2_to_ck3
    out, stats = l2l.inpaint_heights(heights, ck3_raster, ck2_to_ck3, rules, water_mask)
    assert stats == {"holes_px": 0}
    assert (out == heights).all()


# --------------------------------------------------------------------------- #
# 5. the CLI-facing config builder actually reads the key
# --------------------------------------------------------------------------- #
def test_cli_config_builder_reads_the_key():
    """A key the CLI builder never reads is a silent no-op whatever the TOML
    says. This is exactly the bug the coordinator's first real conversion
    run caught for `lake_to_land`/`lake_to_land_csv`: they were parsed
    correctly by `ck2ck3.map.config.load` (the standalone
    `ck2ck3.map.build` entry point) but `ck2ck3.steps.map._map_config` --
    what the real `ck2ck3` CLI actually calls -- built `MapConfig` field by
    field and never read them, so `overrides/lake_to_land.csv` had no effect
    on a real `uv run ck2ck3 --config configs/faerun.toml` run even though
    every unit test above passed. Every new `[map]` key gets this test
    (see `tests/test_map_terrain_history.py`, `tests/test_map_locators.py`).
    """
    from ck2ck3.steps import map as map_step

    class Cfg:
        raw = {
            "map": {
                "vanilla_km_per_px": 1.0,
                "source_km_per_px": 1.0,
                "lake_to_land": False,
                "lake_to_land_csv": "overrides/other_lakes.csv",
                "river_valleys": False,
                "river_valleys_csv": "overrides/other_rivers.csv",
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
    assert cfg.lake_to_land is False
    assert cfg.lake_to_land_csv == Path("overrides/other_lakes.csv")
    assert cfg.river_valleys is False
    assert cfg.river_valleys_csv == Path("overrides/other_rivers.csv")

    Cfg.raw["map"] = {"vanilla_km_per_px": 1.0, "source_km_per_px": 1.0}
    cfg = map_step._map_config(Ctx())
    assert cfg.lake_to_land is True
    assert cfg.lake_to_land_csv == Path("overrides/lake_to_land.csv")
    assert cfg.river_valleys is True
    assert cfg.river_valleys_csv == Path("overrides/river_valleys.csv")


def test_faerun_config_enables_it():
    import tomllib

    repo = Path(__file__).resolve().parents[1]
    raw = tomllib.loads((repo / "configs" / "faerun.toml").read_text())
    m = raw["map"]
    assert m.get("lake_to_land", True) is True
    csv_path = m.get("lake_to_land_csv", "overrides/lake_to_land.csv")
    assert (repo / csv_path).is_file()
    assert m.get("river_valleys", True) is True
    rv_csv_path = m.get("river_valleys_csv", "overrides/river_valleys.csv")
    assert (repo / rv_csv_path).is_file()


# --------------------------------------------------------------------------- #
# 6. `valley` -- a river province that stays water but is not pinned
# (docs/step_map_heightmap.md §2h (d))
# --------------------------------------------------------------------------- #
def test_patch_water_ids_skips_a_valley_rule():
    """The whole point of `valley`: unlike marsh/land, province
    classification (`sea_ids`/`lake_ids`/`river_ids`) must be untouched --
    the province stays exactly the water province CK2 had it as."""
    rules = {101: l2l.LakeToLandRule(101, "valley")}
    sea_ids, lake_ids, river_ids = l2l.patch_water_ids(
        rules, sea_ids={9, 101}, lake_ids=set(), river_ids={101},
    )
    assert sea_ids == {9, 101}
    assert river_ids == {101}
    assert lake_ids == set()


def test_valley_rules_filters_to_valley_action_only():
    rules = {
        101: l2l.LakeToLandRule(101, "marsh"),
        202: l2l.LakeToLandRule(202, "valley"),
        303: l2l.LakeToLandRule(303, "land"),
    }
    out = l2l.valley_rules(rules)
    assert set(out) == {202}
    assert out[202].action == "valley"


def test_valley_mask_marks_only_the_valley_provinces_own_pixels():
    ck3_raster, _, _, _, ck2_to_ck3, _ = _fixture()
    rules = {101: l2l.LakeToLandRule(101, "valley")}
    mask = l2l.valley_mask(ck3_raster, ck2_to_ck3, rules)
    assert mask.shape == ck3_raster.shape
    assert mask.sum() == 36  # the 6x6 hole in _fixture()
    assert mask[17:23, 17:23].all()
    assert not mask[:15, :].any()


def test_valley_mask_no_rules_is_all_false():
    ck3_raster, _, _, _, ck2_to_ck3, _ = _fixture()
    mask = l2l.valley_mask(ck3_raster, ck2_to_ck3, {})
    assert not mask.any()


def test_carve_valleys_cuts_a_shallow_dip_below_the_bank_not_to_water_level():
    """The whole point of `valley` over `inpaint_heights`: the result must
    sit *below* the surrounding bank by ~`depth`, and strictly *above*
    `water_level` -- never pinned flat to it, never level with real land.

    Regression for the first cut's own bug (docs §2h (d)): a canvas-wide
    iterative diffusion measured `bank_median` 5347.6 against a
    ring-verified 6545-7653, because every OTHER water pixel on the whole
    canvas was "free" in that diffusion too, not just this province's own
    hole. The fixed version below is a direct ring-dilation search (this
    fixture's ring never has to widen, since the flat 20000 plateau is only
    2 px from the hole), so this test's bank estimate should land almost
    exactly on 20000, not just "closer than before"."""
    ck3_raster, heights, _, _, ck2_to_ck3, _ = _fixture()
    water_level = 4883
    rules = {101: l2l.LakeToLandRule(101, "valley")}
    out, stats = l2l.carve_valleys(
        heights, ck3_raster, ck2_to_ck3, rules,
        land_mask=~np.isin(ck3_raster, [2]),  # everything but the hole is land
        water_level=water_level, depth=300.0,
    )
    hole = out[17:23, 17:23].astype(np.int64)
    assert stats["holes_px"] == 36
    assert stats["provinces_carved"] == 1
    assert stats["depth"] == 300.0
    assert stats["stranded_ck2_ids"] == []
    # bank estimate should read close to the surrounding flat 20000 plateau
    # -- a ring search that actually reaches real land, not a diffusion that
    # stalls partway to it
    assert abs(stats["bank_median"] - 20000) < 100
    # carved result is below the bank by ~depth...
    assert abs((20000 - int(np.median(hole))) - 300) < 50
    # ...but never at or below the water level
    assert hole.min() > water_level
    # land outside the hole is byte-identical
    assert (out[:15, :] == heights[:15, :]).all()


def test_carve_valleys_no_rules_is_a_no_op():
    ck3_raster, heights, _, _, ck2_to_ck3, water_mask = _fixture()
    out, stats = l2l.carve_valleys(
        heights, ck3_raster, ck2_to_ck3, {}, land_mask=~water_mask, water_level=4883,
    )
    assert out is heights
    assert stats == {}


def test_carve_valleys_skips_a_rule_with_no_surviving_ck3_id():
    ck3_raster, heights, _, _, ck2_to_ck3, water_mask = _fixture()
    rules = {999: l2l.LakeToLandRule(999, "valley")}  # never in ck2_to_ck3
    out, stats = l2l.carve_valleys(
        heights, ck3_raster, ck2_to_ck3, rules, land_mask=~water_mask, water_level=4883,
    )
    assert stats == {"holes_px": 0, "stranded_ck2_ids": []}
    assert (out == heights).all()


def test_carve_valleys_widens_the_ring_when_boxed_in_by_other_water():
    """A province with no true land within `ring_px` must not silently
    report the nearest OTHER water's height as its bank -- the exact
    contamination bug the diffusion version had. Widening the ring is the
    fix; this proves it actually reaches the real plateau two rings out."""
    h, w = 60, 60
    ck3_raster = np.ones((h, w), dtype=np.int32)  # land (id 1) far out
    ck3_raster[10:50, 10:50] = 3  # a 40x40 moat of OTHER water (not `valley`)
    ck3_raster[27:33, 27:33] = 2  # the valley hole, ck2 101 -> ck3 2, at its centre
    heights = np.full((h, w), 20000, dtype=np.uint16)
    heights[10:50, 10:50] = 4700  # the moat, pinned like any other water
    heights[27:33, 27:33] = 4700  # the hole itself, pinned the same way
    land_mask = ~np.isin(ck3_raster, [2, 3])  # true land only
    ck2_to_ck3 = {101: 2}
    rules = {101: l2l.LakeToLandRule(101, "valley")}
    out, stats = l2l.carve_valleys(
        heights, ck3_raster, ck2_to_ck3, rules,
        land_mask=land_mask, water_level=4883, depth=300.0, ring_px=15,
    )
    assert stats["stranded_ck2_ids"] == []
    assert stats["rings_widened"] == 1
    # must reach the real 20000 plateau, not the 4700 moat around it
    assert abs(stats["bank_median"] - 20000) < 100
    hole = out[27:33, 27:33].astype(np.int64)
    assert hole.min() > 4883
