"""Tests for the multi-source geodesic Voronoi and the seed samplers."""

from __future__ import annotations

import numpy as np
import pytest

from ck2ck3.map.growth import (
    farthest_point,
    geodesic_voronoi,
    snap_to_mask,
)


def test_two_seeds_split_a_rectangle_down_the_middle():
    g = np.ones((3, 8), dtype=np.int32)
    lab = geodesic_voronoi(g, [(1, 0, 1), (1, 7, 2)])
    assert (lab[:, :4] == 1).all()
    assert (lab[:, 4:] == 2).all()


def test_growth_is_geodesic_not_euclidean():
    """A lake splits the county, so the far side belongs to the far seed.

    Seeds at (0, 3) and (6, 8); a lake fills column 4 except the bottom row.
    Pixel (0, 5) is 2 px from seed 1 in a straight line and 6.7 px from seed 2,
    so a Euclidean Voronoi gives it to seed 1 — but walking inside the county
    it is 14 steps from seed 1 (down, around the lake, back up) and 9 from
    seed 2. Geodesic growth must give it to seed 2.
    """
    g = np.ones((7, 9), dtype=np.int32)
    g[0:6, 4] = 0  # a lake, open only along the bottom row
    lab = geodesic_voronoi(g, [(0, 3, 1), (6, 8, 2)])
    euclid_1 = (0 - 0) ** 2 + (5 - 3) ** 2
    euclid_2 = (0 - 6) ** 2 + (5 - 8) ** 2
    assert euclid_1 < euclid_2  # Euclidean would say seed 1
    assert lab[0, 5] == 2  # geodesic says seed 2
    assert lab[0, 3] == 1


def test_labels_never_cross_a_group_boundary():
    g = np.zeros((4, 6), dtype=np.int32)
    g[:, :3] = 7
    g[:, 3:] = 9
    lab = geodesic_voronoi(g, [(0, 0, 1), (0, 5, 2)])
    assert set(np.unique(lab[:, :3]).tolist()) == {1}
    assert set(np.unique(lab[:, 3:]).tolist()) == {2}


def test_unassignable_pixels_stay_zero():
    g = np.ones((3, 3), dtype=np.int32)
    g[0, 0] = 0
    lab = geodesic_voronoi(g, [(2, 2, 1)])
    assert lab[0, 0] == 0
    assert (lab[g == 1] == 1).all()


def test_a_seed_off_the_mask_is_ignored():
    g = np.ones((3, 3), dtype=np.int32)
    g[1, 1] = 0
    lab = geodesic_voronoi(g, [(1, 1, 1), (0, 0, 2)])
    assert 1 not in set(np.unique(lab).tolist())


def test_a_pixel_reached_on_the_same_step_goes_to_the_lower_label():
    """Determinism: the tie-break must not depend on numpy's scan order."""
    g = np.ones((1, 3), dtype=np.int32)
    lab = geodesic_voronoi(g, [(0, 0, 5), (0, 2, 2)])
    assert lab[0, 1] == 2
    lab = geodesic_voronoi(g, [(0, 0, 2), (0, 2, 5)])
    assert lab[0, 1] == 2


def test_growth_is_four_connected_so_a_diagonal_does_not_leak():
    g = np.zeros((3, 3), dtype=np.int32)
    g[0, 0] = g[1, 1] = g[2, 2] = 1  # a diagonal chain
    lab = geodesic_voronoi(g, [(0, 0, 1)])
    assert lab[0, 0] == 1
    assert lab[1, 1] == 0


def test_a_zero_or_negative_label_is_rejected():
    with pytest.raises(ValueError, match="label"):
        geodesic_voronoi(np.ones((2, 2), dtype=np.int32), [(0, 0, 0)])


def test_a_one_dimensional_mask_is_rejected():
    with pytest.raises(ValueError, match="2-D"):
        geodesic_voronoi(np.ones(4, dtype=np.int32), [(0, 0, 1)])


def test_no_usable_seed_leaves_everything_unassigned():
    lab = geodesic_voronoi(np.ones((2, 2), dtype=np.int32), [])
    assert (lab == 0).all()


# ------------------------------------------------------------ farthest point
def test_the_first_sample_is_near_the_centre_of_mass():
    pixels = np.arange(25, dtype=np.int64)  # a 5x5 block
    assert farthest_point(pixels, 5, []) == 12  # (2, 2)


def test_a_later_sample_is_the_farthest_pixel():
    pixels = np.arange(9, dtype=np.int64)  # 3x3
    assert farthest_point(pixels, 3, [0]) == 8  # opposite corner


def test_ties_go_to_the_lowest_flat_index():
    pixels = np.array([0, 2], dtype=np.int64)  # 1x3 row, both ends
    assert farthest_point(pixels, 3, [1]) == 0


def test_bias_pulls_the_sample_onto_a_preferred_pixel():
    pixels = np.arange(9, dtype=np.int64)
    bias = np.zeros(9, dtype=bool)
    plain = farthest_point(pixels, 3, [0])
    bias[5] = True  # (1, 2): nearer than the corner, but biased
    biased = farthest_point(pixels, 3, [0], bias=bias, bias_gain=2.0)
    assert plain == 8
    assert biased == 5


def test_bias_with_no_true_pixel_changes_nothing():
    pixels = np.arange(9, dtype=np.int64)
    bias = np.zeros(9, dtype=bool)
    assert farthest_point(pixels, 3, [0], bias=bias) == farthest_point(pixels, 3, [0])


def test_sampling_an_empty_mask_is_an_error():
    with pytest.raises(ValueError, match="empty"):
        farthest_point(np.zeros(0, dtype=np.int64), 3, [])


# -------------------------------------------------------------------- snap
def test_snap_finds_the_nearest_mask_pixel():
    mask = np.array([0, 8], dtype=np.int64)  # (0,0) and (2,2) on a 3-wide grid
    assert snap_to_mask(1, mask, 3, max_distance=5) == 0


def test_snap_refuses_to_move_further_than_the_bound():
    mask = np.array([8], dtype=np.int64)
    assert snap_to_mask(0, mask, 3, max_distance=1) is None
    assert snap_to_mask(0, mask, 3, max_distance=3) == 8


def test_snap_on_an_empty_mask_is_none():
    assert snap_to_mask(0, np.zeros(0, dtype=np.int64), 3, max_distance=9) is None
