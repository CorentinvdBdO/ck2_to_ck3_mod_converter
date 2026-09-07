"""Tests for the CK2 terrain -> CK3 terrain-key majority vote."""

from __future__ import annotations

import numpy as np

from ck2ck3.map import terrain

# CK2 Faerûn's own palette-index -> category map (map/terrain.txt)
TEXTURE_MAP = {
    0: "plains",
    1: "farmlands",
    4: "hills",
    5: "steppe",
    7: "mountain",
    15: "marsh",
    19: "coastal_desert",  # actually the ocean texture in Faerûn
    20: "forest",
}


def test_ck2_category_grid_maps_indices_to_categories():
    idx = np.array([[0, 1], [4, 7]], dtype=np.uint8)
    cats = terrain.ck2_category_grid(idx, TEXTURE_MAP)
    assert cats.tolist() == [["plains", "farmlands"], ["hills", "mountain"]]


def test_unmapped_index_becomes_the_empty_category():
    cats = terrain.ck2_category_grid(np.array([[200]], dtype=np.uint8), TEXTURE_MAP)
    assert cats.tolist() == [[""]]


def test_trees_override_terrain_to_forest():
    """CK2 derives forest from trees.bmp, not terrain.bmp."""
    idx = np.zeros((4, 4), dtype=np.uint8)  # all plains
    trees = np.array([[3, 0], [0, 0]], dtype=np.uint8)  # 2x2 -> 4x4, index 3 = tree
    cats = terrain.ck2_category_grid(idx, TEXTURE_MAP, trees=trees, tree_indices=(3, 4))
    assert cats[0, 0] == "forest"
    assert cats[3, 3] == "plains"


def test_trees_are_ignored_when_no_tree_indices_are_configured():
    idx = np.zeros((2, 2), dtype=np.uint8)
    trees = np.full((1, 1), 3, dtype=np.uint8)
    cats = terrain.ck2_category_grid(idx, TEXTURE_MAP, trees=trees, tree_indices=())
    assert (cats == "plains").all()


def test_expand_trees_upscales_by_an_integer_ratio_exactly():
    trees = np.array([[1, 2]], dtype=np.uint8)
    out = terrain.expand_trees(trees, (2, 4))
    assert out.shape == (2, 4)
    assert out.tolist() == [[1, 1, 2, 2], [1, 1, 2, 2]]


# --------------------------------------------------------------------------- #
# majority vote
# --------------------------------------------------------------------------- #
def test_majority_wins():
    ids = np.array([[1, 1, 1, 1]])
    cats = np.array([["hills", "hills", "hills", "plains"]], dtype=object)
    res = terrain.majority_terrain(ids, cats, land_ids={1})
    assert res.by_province[1] == "hills"
    assert res.category[1] == "hills"


def test_each_province_is_voted_independently():
    ids = np.array([[1, 1, 2, 2]])
    cats = np.array([["hills", "hills", "desert", "desert"]], dtype=object)
    res = terrain.majority_terrain(ids, cats, land_ids={1, 2})
    assert res.by_province == {1: "hills", 2: "desert"}


def test_water_categories_never_win_a_land_province():
    """A coastal province is mostly ocean texture; it must not become `sea`."""
    ids = np.array([[1, 1, 1, 1, 1]])
    cats = np.array([["ocean"] * 4 + ["hills"]], dtype=object)
    res = terrain.majority_terrain(ids, cats, land_ids={1})
    assert res.by_province[1] == "hills"


def test_province_with_only_water_pixels_falls_back_to_the_default():
    ids = np.array([[1, 1]])
    cats = np.array([["ocean", "ocean"]], dtype=object)
    res = terrain.majority_terrain(ids, cats, land_ids={1}, default="plains")
    assert res.by_province[1] == "plains"
    assert res.fallbacks == [1]


def test_province_with_no_pixels_at_all_falls_back():
    ids = np.array([[2]])
    cats = np.array([["hills"]], dtype=object)
    res = terrain.majority_terrain(ids, cats, land_ids={1, 2})
    assert res.by_province[1] == "plains"
    assert 1 in res.fallbacks


def test_empty_category_pixels_are_ignored():
    ids = np.array([[1, 1, 1]])
    cats = np.array([["", "", "marsh"]], dtype=object)
    res = terrain.majority_terrain(ids, cats, land_ids={1})
    assert res.by_province[1] == "wetlands"


def test_sea_provinces_are_not_in_the_result():
    ids = np.array([[1, 2]])
    cats = np.array([["hills", "ocean"]], dtype=object)
    res = terrain.majority_terrain(ids, cats, land_ids={1})
    assert set(res.by_province) == {1}


def test_no_ck3_equivalent_categories_are_noted():
    ids = np.array([[1, 1]])
    cats = np.array([["subterranean", "subterranean"]], dtype=object)
    res = terrain.majority_terrain(ids, cats, land_ids={1})
    assert res.by_province[1] == "mountains"
    assert "Underdark" in res.notes[1]


def test_impassable_category_is_reported_so_default_map_can_list_it():
    ids = np.array([[1, 1]])
    cats = np.array([["impassable_mountains"] * 2], dtype=object)
    res = terrain.majority_terrain(ids, cats, land_ids={1})
    assert res.category[1] in terrain.CK2_IMPASSABLE_CATEGORIES
    assert res.by_province[1] == "mountains"


def test_a_custom_mapping_overrides_the_default_table():
    ids = np.array([[1]])
    cats = np.array([["marsh"]], dtype=object)
    res = terrain.majority_terrain(
        ids, cats, land_ids={1}, mapping={"marsh": "floodplains"}
    )
    assert res.by_province[1] == "floodplains"


def test_unknown_category_uses_the_default_key():
    ids = np.array([[1]])
    cats = np.array([["dragonfire"]], dtype=object)
    res = terrain.majority_terrain(ids, cats, land_ids={1}, default="drylands")
    assert res.by_province[1] == "drylands"


def test_histogram_counts_provinces_not_pixels():
    ids = np.array([[1, 1, 1, 2]])
    cats = np.array([["hills", "hills", "hills", "hills"]], dtype=object)
    res = terrain.majority_terrain(ids, cats, land_ids={1, 2})
    assert res.histogram["hills"] == 2


def test_every_default_mapping_target_is_a_real_ck3_terrain_key():
    """Guards against a typo silently producing an invalid terrain key."""
    ck3_keys = {
        "plains", "farmlands", "hills", "terraced_hills", "mountains", "desert",
        "desert_mountains", "oasis", "jungle", "forest", "taiga", "wetlands",
        "steppe", "floodplains", "drylands", "sea", "coastal_sea",
    }
    assert set(terrain.CK2_TO_CK3_TERRAIN.values()) <= ck3_keys
