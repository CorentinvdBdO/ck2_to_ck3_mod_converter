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

import pytest

from ck2ck3.map import locators

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
