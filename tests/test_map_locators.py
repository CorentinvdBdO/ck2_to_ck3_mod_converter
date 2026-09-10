"""`gfx/map/map_object_data/*_locators.txt` — the frame conversion above all.

The fixture snippets are lifted verbatim from CK3 1.19
`game/gfx/map/map_object_data/building_locators.txt` and from the file the
engine itself generated for our map (see `docs/evidence/map_ui_research.md`).
The frame facts they pin down are measured in
`scripts/check_locator_frame.py` / `docs/evidence/locator_frame.md`.
"""

from __future__ import annotations

import math
import re
import tomllib
from pathlib import Path

import numpy as np
import pytest

from ck2ck3.map import ck2read, locators
from ck2ck3.map.config import ScaleConfig, plan_canvas

# game/gfx/map/map_object_data/building_locators.txt, province 1, on a
# 9216x4608 canvas.  Its province colour centroid is at (x=271.8, y=145.1)
# top-down, i.e. z = 4608 - 145.1 = 4462.9.
VANILLA_PROVINCE_1 = """\
		{
			id=1
			position={ 271.799835 0.000000 4462.883301 }
			rotation={ -0.000000 -0.960029 -0.000000 0.279900 }
			scale={ 1.000000 1.000000 1.000000 }
		}
"""

_POSITION = re.compile(r"id=(\d+)\s+position=\{ ([-\d.]+) ([-\d.]+) ([-\d.]+) \}")


def positions_of(text: str) -> dict[int, tuple[float, float, float]]:
    return {
        int(m.group(1)): (float(m.group(2)), float(m.group(3)), float(m.group(4)))
        for m in _POSITION.finditer(text)
    }


# --------------------------------------------------------------- the frame
def test_z_is_bottom_up():
    """A centroid on the top row of the bitmap is at the *north* of the world."""
    assert locators.world_position(100.0, 0.0, 4608) == (100.0, 0.0, 4608.0)
    assert locators.world_position(100.0, 4608.0, 4608) == (100.0, 0.0, 0.0)


def test_frame_reproduces_vanilla_province_1():
    """Vanilla's own instance, from its own centroid, to sub-pixel accuracy."""
    x, _, z = locators.world_position(271.799835, 4608 - 4462.883301, 4608)
    assert (x, z) == pytest.approx((271.799835, 4462.883301), abs=1e-4)


def test_pixel_position_round_trips():
    for xy in [(0.0, 0.0), (8319.0, 6783.0), (1234.5, 999.25)]:
        pos = locators.world_position(*xy, 6784)
        assert locators.pixel_position(pos, 6784) == pytest.approx(xy)


def test_y_is_zero_by_default():
    assert locators.world_position(1.0, 2.0, 100)[1] == 0.0


def test_yaw_quaternion_is_unit_and_y_only():
    for pid in (0, 1, 7, 3694):
        qx, qy, qz, qw = locators.yaw_quaternion(locators.yaw_for(pid))
        assert (qx, qz) == (0.0, 0.0)
        assert math.hypot(qy, qw) == pytest.approx(1.0)


def test_yaw_is_deterministic_and_varied():
    """Two runs must be byte-identical, but holdings must not all face north."""
    a = [locators.yaw_for(i) for i in range(1, 50)]
    b = [locators.yaw_for(i) for i in range(1, 50)]
    assert a == b
    assert len(set(round(v, 6) for v in a)) == len(a)


# ------------------------------------------------------------- the rendering
def test_render_matches_the_vanilla_block_shape():
    text = locators.render_locator_file(
        locators.LOCATOR_SPECS[0], {1: (271.799835, 145.116699)}, 4608
    )
    assert 'name="buildings"' in text
    assert 'layer="building_layer"' in text
    assert "clamp_to_water_level=yes" in text
    assert "render_pass=Map" in text
    assert "generated_content=no" in text
    assert text.startswith("game_object_locator={\n")
    assert text.endswith("\t}\n}\n")
    # the instance body is laid out exactly like vanilla's
    assert "\t\t\tscale={ 1.000000 1.000000 1.000000 }\n" in text
    assert positions_of(text)[1] == pytest.approx((271.799835, 0.0, 4462.883301))


def test_activities_ships_the_identity_rotation():
    """Vanilla's activities.txt has no yaw at all; ours must not either."""
    spec = next(s for s in locators.LOCATOR_SPECS if s.name == "activities")
    text = locators.render_locator_file(spec, {5: (10.0, 20.0)}, 100)
    assert "rotation={ 0.000000 0.000000 0.000000 1.000000 }" in text


def test_sentinel_id_zero_only_where_vanilla_has_one():
    land = locators.render_locator_file(
        locators.LOCATOR_SPECS[0], {1: (1.0, 1.0)}, 100
    )
    combat = locators.render_locator_file(
        next(s for s in locators.LOCATOR_SPECS if s.name == "combat"),
        {1: (1.0, 1.0)},
        100,
    )
    assert 0 not in positions_of(land)
    assert positions_of(combat)[0] == pytest.approx((0.0, 0.0, 509.0))


def test_no_negative_zero_in_output():
    """`-0.000000` would make two runs differ for no reason."""
    text = locators.render_locator_file(
        locators.LOCATOR_SPECS[0], {i: (0.0, 0.0) for i in range(1, 40)}, 100
    )
    assert "-0.000000" not in text


# --------------------------------------------------------------- the id sets
def test_render_all_splits_land_from_passable():
    """The engine demanded land-only for buildings, land+water for combat.

    `docs/evidence/map_ui_research.md` §1.4: on the Faerun build the engine
    generated 3694 `buildings` instances (land) and 4055 + id 0 for `combat`
    (everything except impassable).
    """
    pos = {i: (float(i), float(i)) for i in range(1, 11)}
    files = locators.render_all(
        pos, 100, land_ids=range(1, 6), passable_ids=range(1, 11)
    )
    assert set(files) == {
        f"{locators.MAP_OBJECT_DIR}/{s.file}" for s in locators.LOCATOR_SPECS
    }
    buildings = files[f"{locators.MAP_OBJECT_DIR}/building_locators.txt"]
    combat = files[f"{locators.MAP_OBJECT_DIR}/combat_locators.txt"]
    assert sorted(positions_of(buildings)) == [1, 2, 3, 4, 5]
    assert sorted(positions_of(combat)) == list(range(0, 11))


def test_every_vanilla_locator_file_is_covered():
    """Miss one and the game keeps vanilla's coordinates for that whole type."""
    assert {s.file for s in locators.LOCATOR_SPECS} == {
        "building_locators.txt",
        "special_building_locators.txt",
        "siege_locators.txt",
        "activities.txt",
        "player_stack_locators.txt",
        "other_stack_locators.txt",
        "combat_locators.txt",
    }


def test_locator_names_are_the_ones_the_engine_looks_up():
    assert {s.name for s in locators.LOCATOR_SPECS} == {
        "buildings",
        "special_building",
        "siege",
        "activities",
        "unit_stack_player_owned",
        "unit_stack_other_owner",
        "combat",
    }


# ------------------------------------------------------- vanilla foliage
# game/gfx/map/map_object_data/generated/tree_sakura_02_generator.txt, head.
# Its 53 instances sit at x ~7907, z ~2697 - inside vanilla's sheet, nowhere
# near ours. Godherja and Elder Kings 2 both neutralise unwanted generators
# with an empty `instances={ }` block of the same header.
VANILLA_FOLIAGE = '''object={
\tname="tree_sakura_02_generator_0"
\trender_pass=Map
\tclamp_to_water_level=no
\tgenerated_content=yes
\tlayer="tree_high_layer"
\tpdxmesh="tree_sakura_02_mesh"
\tcount=53
\ttransform="7907.358398 0.000000 2697.423828 0.000000 0.507773 0.000000 -0.861491 1.000000 1.000000 1.000000
7903.287598 0.000000 2700.194824 0.000000 0.041883 0.000000 0.999123 1.000000 1.000000 1.000000
"}
'''


def test_foliage_stub_keeps_the_header_and_drops_the_instances(tmp_path):
    gen = tmp_path / locators.FOLIAGE_DIR
    gen.mkdir(parents=True)
    (gen / "tree_sakura_02_generator.txt").write_text(VANILLA_FOLIAGE)

    out = locators.render_foliage_stubs(tmp_path)
    rel = f"{locators.FOLIAGE_DIR}/tree_sakura_02_generator.txt"
    assert set(out) == {rel}
    text = out[rel]
    assert 'pdxmesh="tree_sakura_02_mesh"' in text
    assert 'layer="tree_high_layer"' in text
    assert "instances={\n\t}\n}" in text
    assert "7907.358398" not in text
    assert "count=" not in text


def test_foliage_stubs_need_a_game_dir():
    assert locators.render_foliage_stubs(None) == {}


# --------------------------------- CK2 anchors + vanilla per-type offsets
# Faerun/map/positions.txt, provinces 1 (Waterdeep) and 2 (Amphail), verbatim.
# 7 (x, y) pairs; y is measured from the BOTTOM of the 4096x3328 CK2 bitmap.
CK2_POSITIONS = """\
#Waterdeep
\t1=
\t{
\t\tposition={1119.000 2838.000 1116.000 2844.000 1112.000 2849.000 1117.000 2844.000 1113.000 2833.000 1111.000 2826.000 1118.000 2832.000}
\t\trotation={0.000 0.000 0.785 0.000 0.785 0.000 0.785}
\t\theight={0.000 0.000 0.000 20.000 0.000 0.000 0.000}
\t}
#Amphail
\t2=
\t{
\t\tposition={1134.000 2893.000 1143.000 2898.000 1138.000 2896.000 1138.000 2896.000 1143.000 2901.000 1138.000 2896.000 1138.000 2896.000}
\t\trotation={0.000 0.000 0.000 0.000 0.000 0.000 0.000}
\t\theight={0.000 0.000 0.000 20.000 0.000 0.000 0.000}
\t}
"""

# mappings/locator_offsets.csv shape, with the real measured medians of two
# rows (scripts/measure_vanilla_locator_offsets.py over CK3 1.19).
OFFSETS_CSV = """\
# a provenance comment block every reader must skip
# locator,dx_px,dz_px,...
locator,dx_px,dz_px,median_dist_px,p95_dist_px,dx_q1,dx_q3,dz_q1,dz_q3,instances
buildings,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,11297
siege,0.92,-3.08,9.98,11.51,-8.08,8.64,-7.09,1.91,11297
unit_stack_player_owned,4.92,4.66,7.1,12.09,1.29,6.79,1.33,5.96,11297
"""


@pytest.fixture
def ck2_positions(tmp_path):
    p = tmp_path / "positions.txt"
    p.write_text(CK2_POSITIONS, encoding="latin-1")
    return ck2read.read_positions(p)


REPO = Path(__file__).resolve().parents[1]


# ------------------------------------------------------- the offset table
def test_offset_reader_skips_the_provenance_comment_block(tmp_path):
    """A mappings/*.csv may open with '#' lines; every reader must skip them."""
    p = tmp_path / "locator_offsets.csv"
    p.write_text(OFFSETS_CSV)
    off = locators.read_locator_offsets(p)
    assert set(off) == {"buildings", "siege", "unit_stack_player_owned"}
    assert off["siege"].dx == pytest.approx(0.92)
    assert off["siege"].dz == pytest.approx(-3.08)
    assert off["buildings"].dx == 0.0 and off["buildings"].dz == 0.0


def test_missing_offset_table_is_not_an_error(tmp_path):
    assert locators.read_locator_offsets(tmp_path / "nope.csv") == {}


def test_the_shipped_offset_table_covers_every_locator_type():
    """A type missing a row draws on the anchor, on top of the settlement."""
    off = locators.read_locator_offsets(REPO / "mappings" / "locator_offsets.csv")
    assert {s.name for s in locators.LOCATOR_SPECS} <= set(off)
    # `buildings` is the anchor and is measured against itself
    assert (off["buildings"].dx, off["buildings"].dz) == (0.0, 0.0)
    # every type clusters within ~15 vanilla px of the settlement (the whole
    # reason the model is anchor+offset and not one point per type)
    assert all(o.median_dist_px < 15.0 for o in off.values())


# --------------------------------------------------------- the CK2 anchor
def test_only_slot_0_anchors_and_only_county_capitals():
    """Slot 1 and slot 3 are rejected; see docs/step_map_assets.md §2."""
    assert locators.CK2_ANCHOR_SLOT == 0


def test_anchor_transform_matches_the_barony_seed_transform(ck2_positions):
    """The real reader + the real crop transform, on the real Waterdeep block.

    `positions.txt` y is bottom-origin, so y_top = source_height - y
    (`verified`, docs/map_scale.md §2b) - the same two lines
    `ck2ck3.map.baronies._seed_one` uses for the barony seeds.  Faerun's
    source bitmap is 4096x3328, so Waterdeep's slot 0 (1119, 2838) is at
    y_top 490.
    """
    assert ck2_positions[1][0] == (1119.0, 2838.0)
    canvas = plan_canvas(
        4096, 3328,
        ScaleConfig(1.0, 1.0, sea_margin_px=0, canvas_multiple=1),
        crop=(1100, 470, 1140, 510),
    )
    raster = np.full((40, 40), 9, dtype=np.int32)
    raster[490 - 470, 1119 - 1100] = 7
    anchors, st = locators.ck2_capital_anchors(
        positions=ck2_positions,
        capital_ids={1: 7},
        canvas=canvas,
        source_height=3328,
        raster=raster,
        centroids={7: (0.0, 0.0)},
    )
    assert anchors == {7: (19.0, 20.0)}
    assert (st.accepted, st.candidates, st.outside_province) == (1, 1, 0)


def test_validity_gate_rejects_an_anchor_outside_its_own_province(ck2_positions):
    canvas = plan_canvas(4096, 3328,
                         ScaleConfig(1.0, 1.0, sea_margin_px=0, canvas_multiple=1),
                         crop=(1100, 470, 1140, 510))
    raster = np.full((40, 40), 99, dtype=np.int32)   # never province 7
    anchors, st = locators.ck2_capital_anchors(
        positions=ck2_positions,
        capital_ids={1: 7},
        canvas=canvas,
        source_height=3328,
        raster=raster,
        centroids={7: (0.0, 0.0)},
    )
    assert anchors == {}
    assert (st.accepted, st.outside_province, st.accept_rate) == (0, 1, 0.0)


def test_anchor_off_the_canvas_is_counted_not_clamped():
    canvas = plan_canvas(40, 40, ScaleConfig(1.0, 1.0, sea_margin_px=0,
                                             canvas_multiple=1))
    raster = np.zeros((40, 40), dtype=np.int32)
    anchors, st = locators.ck2_capital_anchors(
        positions={1: [(5000.0, 5000.0)] * 7},
        capital_ids={1: 7},
        canvas=canvas,
        source_height=40,
        raster=raster,
        centroids={},
    )
    assert anchors == {}
    assert (st.off_canvas, st.accepted) == (1, 0)


def test_non_capital_provinces_are_never_offered_an_anchor():
    canvas = plan_canvas(40, 40, ScaleConfig(1.0, 1.0, sea_margin_px=0,
                                             canvas_multiple=1))
    raster = np.full((40, 40), 7, dtype=np.int32)
    anchors, _st = locators.ck2_capital_anchors(
        positions={1: [(19.0, 30.0)] * 7, 2: [(19.0, 30.0)] * 7},
        capital_ids={1: 7},          # CK2 province 2 has no capital entry
        canvas=canvas,
        source_height=40,
        raster=raster,
        centroids={7: (0.0, 0.0)},
    )
    assert set(anchors) == {7}


# ------------------------------------------------- anchor + type offsets
def _offsets(**kw):
    return {n: locators.LocatorOffset(n, dx, dz) for n, (dx, dz) in kw.items()}


def test_offset_is_added_to_the_anchor_with_dz_bottom_up():
    """dz > 0 is NORTH, so it becomes y - dz in top-down canvas pixels."""
    raster = np.full((40, 40), 7, dtype=np.int32)
    over, stats = locators.place_with_offsets(
        centroids={7: (20.0, 20.0)},
        anchors={7: (10.0, 30.0)},
        offsets=_offsets(siege=(1.0, -3.0), unit_stack_player_owned=(5.0, 5.0)),
        raster=raster,
        land_ids=[7],
        passable_ids=[7],
    )
    assert over["siege"][7] == (11.0, 33.0)                  # dz -3 -> y +3
    assert over["unit_stack_player_owned"][7] == (15.0, 25.0)  # dz +5 -> y -5
    assert over["buildings"][7] == (10.0, 30.0)              # no row: bare anchor
    assert stats["siege"]["ck2_anchored"] == 1
    assert stats["siege"]["offset_applied"] == 1


def test_offset_leaving_the_province_falls_back_to_the_anchor():
    raster = np.full((40, 40), 7, dtype=np.int32)
    raster[27, 30] = 99          # exactly where the offset would land
    over, stats = locators.place_with_offsets(
        centroids={7: (20.0, 20.0)},
        anchors={7: (20.0, 30.0)},
        offsets=_offsets(siege=(10.0, 3.0)),
        raster=raster,
        land_ids=[7],
        passable_ids=[7],
    )
    assert over["siege"][7] == (20.0, 30.0)
    assert stats["siege"]["offset_rejected"] == 1
    assert stats["siege"]["offset_applied"] == 0


def test_a_province_without_a_ck2_anchor_offsets_around_its_centroid():
    """Non-capital baronies and sea provinces still get the type spread."""
    raster = np.full((40, 40), 7, dtype=np.int32)
    over, stats = locators.place_with_offsets(
        centroids={7: (20.0, 20.0)},
        anchors={},
        offsets=_offsets(siege=(1.0, -3.0)),
        raster=raster,
        land_ids=[7],
        passable_ids=[7],
    )
    assert over["siege"][7] == (21.0, 23.0)
    assert stats["siege"]["ck2_anchored"] == 0
    # an id whose final position IS the centroid is left out of the patch
    assert 7 not in over["buildings"]


def test_offset_scale_converts_vanilla_pixels_to_canvas_pixels():
    raster = np.full((40, 40), 7, dtype=np.int32)
    over, _s = locators.place_with_offsets(
        centroids={7: (20.0, 20.0)},
        anchors={},
        offsets=_offsets(siege=(4.0, -4.0)),
        raster=raster,
        land_ids=[7],
        passable_ids=[7],
        scale=0.5,
    )
    assert over["siege"][7] == (22.0, 22.0)


def test_water_only_locators_skip_land_only_ids():
    raster = np.full((40, 40), 7, dtype=np.int32)
    raster[:, 20:] = 8
    over, _s = locators.place_with_offsets(
        centroids={7: (5.0, 5.0), 8: (30.0, 5.0)},
        anchors={},
        offsets=_offsets(combat=(1.0, 1.0), buildings=(0.0, 0.0)),
        raster=raster,
        land_ids=[7],
        passable_ids=[7, 8],
    )
    assert set(over["combat"]) == {7, 8}       # combat covers water
    assert 8 not in over["buildings"]          # buildings is land-only


# ------------------------------------------------------------ the patch
def test_render_all_keeps_every_id_when_overrides_move_some():
    """An id left out of a locator file silently keeps vanilla's coordinate."""
    pos = {i: (float(i), float(i)) for i in range(1, 11)}
    files = locators.render_all(
        pos, 100,
        land_ids=range(1, 6),
        passable_ids=range(1, 11),
        overrides={"buildings": {2: (50.0, 60.0)}},
    )
    buildings = positions_of(files[f"{locators.MAP_OBJECT_DIR}/building_locators.txt"])
    siege = positions_of(files[f"{locators.MAP_OBJECT_DIR}/siege_locators.txt"])
    assert sorted(buildings) == [1, 2, 3, 4, 5]
    assert buildings[2] == pytest.approx((50.0, 0.0, 40.0))   # z = 100 - 60
    assert buildings[3] == pytest.approx((3.0, 0.0, 97.0))    # untouched
    assert siege[2] == pytest.approx((2.0, 0.0, 98.0))


def test_overrides_default_to_nothing():
    """Without the patch the output is byte-identical to build 8's."""
    pos = {i: (float(i), float(i)) for i in range(1, 11)}
    a = locators.render_all(pos, 100, land_ids=range(1, 6), passable_ids=range(1, 11))
    b = locators.render_all(pos, 100, land_ids=range(1, 6), passable_ids=range(1, 11),
                            overrides={})
    assert a == b


# ------------------------------------------------------------- the config
def test_cli_config_builder_reads_the_keys():
    """`[map] ck2_locator_positions` must reach MapConfig from the REAL CLI.

    A key the CLI's own config builder never reads is a silent no-op whatever
    the TOML says; that is exactly what happened to `[map] colormap`
    (src/ck2ck3/steps/map.py, "BUG FIXED (lane colormap-fix)").
    """
    from ck2ck3.steps import map as map_step

    class Cfg:
        raw = {"map": {"vanilla_km_per_px": 1.0, "source_km_per_px": 1.0,
                       "ck2_locator_positions": False,
                       "locator_offset_scale": 0.5}}
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
    assert cfg.ck2_locator_positions is False
    assert cfg.locator_offset_scale == 0.5
    Cfg.raw["map"].pop("ck2_locator_positions")
    Cfg.raw["map"].pop("locator_offset_scale")
    cfg = map_step._map_config(Ctx())
    assert cfg.ck2_locator_positions is True
    assert cfg.locator_offset_scale == 1.0
    assert cfg.locator_offsets_csv == Path("mappings/locator_offsets.csv")


def test_shipped_faerun_config_turns_the_import_on():
    cfg = tomllib.loads((REPO / "configs" / "faerun.toml").read_text())
    assert cfg["map"]["ck2_locator_positions"] is True


def test_median_radius_mode_stretches_the_offset_to_vanillas_distance():
    """docs/step_map_assets.md §2.2: the two measurements disagree.

    `siege`'s median vector is 3.2 px long but its median *distance* from the
    settlement is 10.0 px, because vanilla's siege offsets are a ring whose
    directions cancel. `median_radius` keeps the direction and takes the
    distance.
    """
    raster = np.full((60, 60), 7, dtype=np.int32)
    off = {"siege": locators.LocatorOffset("siege", 0.922, -3.085,
                                           median_dist_px=9.982)}
    vec, _s = locators.place_with_offsets(
        centroids={7: (30.0, 30.0)}, anchors={}, offsets=off, raster=raster,
        land_ids=[7], passable_ids=[7],
    )
    rad, _s = locators.place_with_offsets(
        centroids={7: (30.0, 30.0)}, anchors={}, offsets=off, raster=raster,
        land_ids=[7], passable_ids=[7], mode="median_radius",
    )
    d_vec = math.hypot(vec["siege"][7][0] - 30.0, vec["siege"][7][1] - 30.0)
    d_rad = math.hypot(rad["siege"][7][0] - 30.0, rad["siege"][7][1] - 30.0)
    assert d_vec == pytest.approx(3.22, abs=0.02)
    assert d_rad == pytest.approx(9.982, abs=0.02)


def test_median_radius_leaves_a_row_without_a_distance_alone():
    raster = np.full((60, 60), 7, dtype=np.int32)
    off = {"siege": locators.LocatorOffset("siege", 3.0, -4.0)}
    out, _s = locators.place_with_offsets(
        centroids={7: (30.0, 30.0)}, anchors={}, offsets=off, raster=raster,
        land_ids=[7], passable_ids=[7], mode="median_radius",
    )
    assert out["siege"][7] == (33.0, 34.0)
