"""Tests for CK2 trees.bmp -> CK3 gfx/map/map_object_data/generated scatter."""

from __future__ import annotations

import numpy as np

from ck2ck3.map import tree_scatter


def test_forest_mask_is_any_nonzero_pixel():
    idx = np.array([[0, 1, 0], [3, 0, 9]], dtype=np.uint8)
    mask = tree_scatter.forest_mask_from_trees_bmp(idx)
    assert mask.tolist() == [[False, True, False], [True, False, True]]


def test_upsample_to_source_exact_multiple():
    small = np.array([[1, 2], [3, 4]], dtype=np.uint8)
    up = tree_scatter.upsample_to_source(small, src_h=4, src_w=4)
    assert up.shape == (4, 4)
    assert up[0, 0] == 1 and up[0, 3] == 2 and up[3, 0] == 3 and up[3, 3] == 4


def test_upsample_to_source_crops_to_requested_shape():
    small = np.ones((3, 3), dtype=np.uint8)
    up = tree_scatter.upsample_to_source(small, src_h=7, src_w=5)
    assert up.shape == (7, 5)


def _terrain_grid(shape, terrain_keys, key_for_all):
    idx = terrain_keys.index(key_for_all)
    return np.full(shape, idx, dtype=np.uint8)


def test_scatter_is_deterministic_for_a_fixed_seed():
    eligible = np.zeros((50, 50), dtype=bool)
    eligible[10:40, 10:40] = True
    keys = ["plains", "forest"]
    code = _terrain_grid(eligible.shape, keys, "forest")
    mesh_map = {"forest": "tree_leaf_high_generator_1.txt"}

    g1, d1, _ = tree_scatter.scatter(
        eligible, code, keys, mesh_map, target_total=200, seed=99
    )
    g2, d2, _ = tree_scatter.scatter(
        eligible, code, keys, mesh_map, target_total=200, seed=99
    )
    assert d1 == d2 == 0
    assert set(g1) == set(g2) == {"tree_leaf_high_generator_1.txt"}
    assert np.array_equal(
        g1["tree_leaf_high_generator_1.txt"], g2["tree_leaf_high_generator_1.txt"]
    )
    assert g1["tree_leaf_high_generator_1.txt"].shape[0] == 200


def test_scatter_never_places_outside_eligible_pixels():
    eligible = np.zeros((30, 30), dtype=bool)
    eligible[5:10, 5:10] = True  # a small 5x5 block, water/impassable elsewhere
    keys = ["forest"]
    code = np.zeros(eligible.shape, dtype=np.uint8)
    mesh_map = {"forest": "f.txt"}

    groups, dropped, dropped_by_terrain = tree_scatter.scatter(
        eligible, code, keys, mesh_map, target_total=1000, seed=7, jitter=0.4
    )
    pts = groups["f.txt"]
    # at most one point per eligible pixel (no replacement in the partition)
    assert pts.shape[0] == 25
    assert dropped == 0
    assert (pts[:, 0] >= 5 - 0.4).all() and (pts[:, 0] <= 10 + 0.4).all()
    assert (pts[:, 1] >= 5 - 0.4).all() and (pts[:, 1] <= 10 + 0.4).all()


def test_scatter_drops_points_with_no_mesh_row():
    eligible = np.ones((10, 10), dtype=bool)
    keys = ["plains"]  # no row in mesh_of_terrain
    code = np.zeros(eligible.shape, dtype=np.uint8)
    groups, dropped, dropped_by_terrain = tree_scatter.scatter(
        eligible, code, keys, {}, target_total=50, seed=1
    )
    assert groups == {}
    assert dropped == 50
    assert dropped_by_terrain == {"plains": 50}


def test_render_generated_file_empty_is_a_stub():
    mesh = tree_scatter.MeshInfo(
        file="f.txt", name="f_0", layer="tree_high_layer", pdxmesh="tree_x_mesh"
    )
    text = tree_scatter.render_generated_file(None, 100, mesh)
    assert 'name="f_0"' in text
    assert "instances={\n\t}\n" in text
    assert "count=" not in text


def test_render_generated_file_matches_vanilla_shape():
    mesh = tree_scatter.MeshInfo(
        file="f.txt", name="f_0", layer="tree_high_layer", pdxmesh="tree_x_mesh"
    )
    points = np.array([[10.0, 20.0], [30.0, 40.0]])
    text = tree_scatter.render_generated_file(points, canvas_height=100, mesh=mesh, seed=1)
    assert "count=2\n" in text
    assert 'pdxmesh="tree_x_mesh"' in text
    assert 'layer="tree_high_layer"' in text
    # transform has exactly 2 lines of 10 floats each
    m = text.split('transform="')[1].rsplit('"', 1)[0]
    lines = m.strip().split("\n")
    assert len(lines) == 2
    for line in lines:
        vals = line.split()
        assert len(vals) == 10
        assert float(vals[7]) == float(vals[8]) == float(vals[9]) == 1.0  # scale
    # bottom-up z: point (10, 20) -> z = 100 - 20 = 80
    first = [float(v) for v in lines[0].split()]
    assert first[0] == 10.0
    assert first[2] == 80.0


def test_read_mesh_table_skips_comments_and_empty_files(tmp_path):
    p = tmp_path / "tree_meshes.csv"
    p.write_text(
        "# a comment\n"
        "ck3_terrain,file,note\n"
        "forest,tree_leaf_high_generator_1.txt,broadleaf\n"
        "plains,,no trees\n",
        encoding="utf-8",
    )
    table = tree_scatter.read_mesh_table(p)
    assert table["forest"] == "tree_leaf_high_generator_1.txt"
    assert table["plains"] == ""


def test_mesh_csv_covers_every_ck3_terrain_key():
    """Same completeness contract as mappings/terrain_paint.csv."""
    from pathlib import Path

    from ck2ck3.map.terrain import CK2_TO_CK3_TERRAIN

    repo = Path(__file__).resolve().parents[1]
    table = tree_scatter.read_mesh_table(repo / "mappings" / "tree_meshes.csv")
    ck3_keys = set(CK2_TO_CK3_TERRAIN.values())
    missing = ck3_keys - set(table)
    assert not missing, f"mappings/tree_meshes.csv is missing rows for {missing}"
