"""Soft, relief-aware terrain-class edges (lane `paint-edges`).

The contracts under test are the ones `docs/step_map_paint.md` §10 promises:
the four `detail_intensity` channels still sum to exactly 255, a class
boundary is a ramp and not a step, an interior pixel carries the class's
whole material mix, and — the macro invariant — no class migrates further
than the configured bound from where CK2 painted it.
"""

from __future__ import annotations

import csv

import numpy as np
import pytest

from ck2ck3.map import paint_edges

ORDINALS = {
    "plains_01": 0,
    "plains_01_noisy": 1,
    "hills_01": 2,
    "hills_01_rocks": 3,
    "forest_leaf_01": 4,
    "forestfloor": 5,
    "grass_01": 6,
}


def _csv(tmp_path, header, rows):
    p = tmp_path / "terrain_paint.csv"
    with p.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)
    return p


# --------------------------------------------------------------------------- #
# read_material_mix
# --------------------------------------------------------------------------- #
def test_read_material_mix_reads_the_old_two_column_table(tmp_path):
    p = _csv(
        tmp_path,
        ["ck3_terrain", "primary_material", "secondary_material", "note"],
        [["plains", "plains_01", "plains_01_noisy", "n"]],
    )
    mix = paint_edges.read_material_mix(p)
    assert [m for m, _ in mix["plains"]] == ["plains_01", "plains_01_noisy"]
    assert pytest.approx(sum(w for _, w in mix["plains"])) == 1.0
    # default weights, renormalised over the two materials it does name
    assert mix["plains"][0][1] > mix["plains"][1][1]


def test_read_material_mix_reads_a_tertiary_and_explicit_weights(tmp_path):
    p = _csv(
        tmp_path,
        [
            "ck3_terrain",
            "primary_material",
            "secondary_material",
            "tertiary_material",
            "primary_weight",
            "secondary_weight",
            "tertiary_weight",
            "note",
        ],
        [["forest", "forest_leaf_01", "forestfloor", "grass_01",
          "0.5", "0.3", "0.2", "n"]],
    )
    mix = paint_edges.read_material_mix(p)
    assert mix["forest"] == [
        ("forest_leaf_01", pytest.approx(0.5)),
        ("forestfloor", pytest.approx(0.3)),
        ("grass_01", pytest.approx(0.2)),
    ]


def test_read_material_mix_sorts_descending_and_drops_zero_weights(tmp_path):
    p = _csv(
        tmp_path,
        ["ck3_terrain", "primary_material", "secondary_material",
         "tertiary_material", "primary_weight", "secondary_weight",
         "tertiary_weight"],
        [["hills", "hills_01", "hills_01_rocks", "grass_01", "1", "3", "0"]],
    )
    mix = paint_edges.read_material_mix(p)
    assert [m for m, _ in mix["hills"]] == ["hills_01_rocks", "hills_01"]


def test_read_material_mix_missing_file_is_empty(tmp_path):
    assert paint_edges.read_material_mix(tmp_path / "nope.csv") == {}


# --------------------------------------------------------------------------- #
# the blend
# --------------------------------------------------------------------------- #
CODE_NAMES = ["", "plains", "hills"]
MAPPING = {"plains": "plains", "hills": "hills"}
MIX = {
    "plains": [("plains_01", 0.5), ("plains_01_noisy", 0.3), ("grass_01", 0.2)],
    "hills": [("hills_01", 0.5), ("hills_01_rocks", 0.3), ("grass_01", 0.2)],
}


def _two_class_codes(h=64, w=64):
    codes = np.full((h, w), 1, dtype=np.uint16)
    codes[:, w // 2:] = 2
    return codes


def _blend(codes, **kw):
    kw.setdefault("material_mix", MIX)
    kw.setdefault("ordinals", ORDINALS)
    kw.setdefault("mapping", MAPPING)
    kw.setdefault("default", "plains")
    return paint_edges.build_soft_blend(codes, CODE_NAMES, **kw)


def test_intensity_channels_sum_to_255_everywhere():
    out = _blend(_two_class_codes(), sigma_px=2.0)
    assert (out.intensity.astype(np.uint16).sum(axis=2) == 255).all()


def test_interior_pixel_carries_the_whole_class_mix():
    out = _blend(_two_class_codes(), sigma_px=2.0, quantize=1)
    # far inside the plains half
    px_i = out.index[32, 4]
    px_w = out.intensity[32, 4]
    assert int(px_w.sum()) == 255
    assert int((px_w > 0).sum()) == 3, "three materials in a class interior"
    assert px_i[0] == ORDINALS["plains_01"]
    assert abs(int(px_w[0]) - round(0.5 * 255)) <= 2


def test_boundary_is_a_ramp_not_a_step():
    out = _blend(_two_class_codes(w=64), sigma_px=2.0, quantize=1)
    row = out.intensity[32, :, 0].astype(int)
    # the primary weight is not constant-then-constant: a real ramp has
    # several distinct intermediate values around the boundary
    band = row[28:37]
    assert len(set(band.tolist())) >= 4, band


def test_hard_edges_when_sigma_is_zero():
    out = _blend(_two_class_codes(), sigma_px=0.0, quantize=1)
    # every pixel is a pure class: exactly the class's own three materials
    assert (out.intensity[:, :, 3] == 0).all()


def test_a_shared_material_is_one_channel_not_two():
    """`grass_01` is in both mixes; a boundary pixel must not list it twice."""
    out = _blend(_two_class_codes(), sigma_px=2.0, quantize=1)
    for x in range(28, 37):
        ords = out.index[32, x]
        weights = out.intensity[32, x]
        live = [int(o) for o, wv in zip(ords, weights) if wv > 0]
        assert len(live) == len(set(live)), (x, ords, weights)


def test_blend_is_deterministic():
    a = _blend(_two_class_codes(), sigma_px=2.0)
    b = _blend(_two_class_codes(), sigma_px=2.0)
    assert np.array_equal(a.index, b.index)
    assert np.array_equal(a.intensity, b.intensity)


def test_blend_stats_are_reported_over_the_land_mask():
    codes = _two_class_codes()
    land = np.zeros(codes.shape, dtype=bool)
    land[:, :32] = True
    out = _blend(codes, sigma_px=2.0, land_mask=land)
    assert out.stats["land_px"] == float(land.sum())
    assert out.stats["mean_nonzero_channels"] >= 3.0


def test_a_class_with_no_row_falls_back_and_warns():
    msgs: list[str] = []
    out = _blend(
        _two_class_codes(),
        material_mix={"plains": MIX["plains"]},
        sigma_px=1.0,
        warn=msgs.append,
    )
    assert any("hills" in m for m in msgs)
    assert (out.intensity.astype(np.uint16).sum(axis=2) == 255).all()


# --------------------------------------------------------------------------- #
# relief warp
# --------------------------------------------------------------------------- #
def test_relief_warp_is_bounded_by_shift_px():
    rng = np.random.default_rng(0)
    heights = (rng.random((64, 64)) * 6000).astype(np.uint16)
    dy, dx = paint_edges.relief_warp(heights, (64, 64), shift_px=2.0, sigma_px=2.0)
    assert np.hypot(dy.astype(float), dx.astype(float)).max() <= 2.0 + 1e-6


def test_relief_warp_is_zero_on_flat_ground():
    heights = np.full((32, 32), 5000, dtype=np.uint16)
    dy, dx = paint_edges.relief_warp(heights, (32, 32), shift_px=2.0)
    assert not dy.any() and not dx.any()


def test_relief_warp_downsamples_a_2x_heightmap():
    heights = np.zeros((64, 64), dtype=np.uint16)
    heights[:, 32:] = 9000
    dy, dx = paint_edges.relief_warp(heights, (32, 32), shift_px=1.0, sigma_px=1.0)
    assert dy.shape == (32, 32) and dx.shape == (32, 32)


def test_warp_apply_with_a_zero_field_is_the_identity():
    arr = np.arange(64, dtype=np.uint8).reshape(8, 8)
    zero = np.zeros((8, 8), dtype=np.int8)
    assert np.array_equal(paint_edges.warp_apply(arr, zero, zero), arr)


def test_warp_apply_shifts_and_clamps_at_the_border():
    arr = np.tile(np.arange(8, dtype=np.uint8), (8, 1))
    dx = np.full((8, 8), 2, dtype=np.int8)
    dy = np.zeros((8, 8), dtype=np.int8)
    out = paint_edges.warp_apply(arr, dy, dx)
    assert out[0, 0] == 2
    assert out[0, 7] == 7  # clamped


# --------------------------------------------------------------------------- #
# the macro invariant
# --------------------------------------------------------------------------- #
def test_displacement_of_an_unchanged_map_is_zero():
    a = _two_class_codes().astype(np.uint8)
    stats = paint_edges.class_displacement_stats(a, a)
    assert stats["changed_px"] == 0
    assert stats["max_px"] == 0


def test_displacement_measures_a_boundary_that_moved_n_pixels():
    base = np.zeros((32, 32), dtype=np.uint8)
    base[:, 16:] = 1
    moved = np.zeros((32, 32), dtype=np.uint8)
    moved[:, 13:] = 1  # class 1 advanced three pixels
    stats = paint_edges.class_displacement_stats(moved * 0 + base, moved)
    assert stats["max_px"] == pytest.approx(3.0)
    assert stats["changed_px"] == 3 * 32


def test_displacement_bounded_and_unbounded_agree_on_a_small_map():
    base = np.zeros((32, 32), dtype=np.uint8)
    base[:, 16:] = 1
    moved = np.zeros((32, 32), dtype=np.uint8)
    moved[:, 14:] = 1
    a = paint_edges.class_displacement_stats(base, moved, max_radius=8)
    b = paint_edges.class_displacement_stats(base, moved, max_radius=0)
    assert a["max_px"] == b["max_px"]


def test_within_radius_is_the_reachability_test():
    hard = np.zeros((9, 9), dtype=np.uint8)
    hard[4, 4] = 1
    soft = np.ones((9, 9), dtype=np.uint8)
    ok = paint_edges.within_radius(hard, soft, 2.0)
    assert ok[4, 4] and ok[4, 6] and ok[3, 3]
    assert not ok[0, 0] and not ok[4, 7]


def test_max_shift_reverts_a_class_that_travelled_too_far():
    """The macro invariant is enforced, not hoped for."""
    codes = np.ones((48, 48), dtype=np.uint16)
    codes[24, 24] = 2  # a single-pixel speckle of the other class
    strict = _blend(codes, sigma_px=3.0, max_shift_px=1.0)
    loose = _blend(codes, sigma_px=3.0, max_shift_px=None)
    stats = paint_edges.class_displacement_stats(
        strict.class_index_hard, strict.class_index, max_radius=8
    )
    assert stats["max_px"] <= 1.0 + 1e-6, stats
    assert strict.stats["reverted_px"] >= 0
    # and the strict pass still writes a valid layer
    assert (strict.intensity.astype(np.uint16).sum(axis=2) == 255).all()
    assert loose.stats["max_shift_px"] == 0.0


def test_blend_never_moves_a_class_further_than_the_warp_bound():
    """The lane's macro invariant, end to end on a synthetic class map."""
    rng = np.random.default_rng(7)
    codes = np.ones((96, 96), dtype=np.uint16)
    yy, xx = np.mgrid[0:96, 0:96]
    codes[(xx + 6 * np.sin(yy / 9.0)) > 48] = 2
    heights = (rng.random((96, 96)) * 3000).astype(np.uint16)
    heights = np.cumsum(heights, axis=1).astype(np.float64)
    heights = (heights / heights.max() * 60000).astype(np.uint16)
    shift = 2.0
    warp = paint_edges.relief_warp(heights, (96, 96), shift_px=shift, sigma_px=3.0)
    out = _blend(codes, sigma_px=2.0, warp=warp)
    stats = paint_edges.class_displacement_stats(
        out.class_index_hard, out.class_index, max_radius=8
    )
    assert stats["max_px"] <= shift + 2.0, stats
    assert stats["beyond_radius_px"] == 0


# --------------------------------------------------------------------------- #
# trees.bmp
# --------------------------------------------------------------------------- #
def test_forest_coverage_nearest_matches_the_old_repeat_expansion():
    from ck2ck3.map.terrain import expand_trees

    small = np.array([[0, 3], [4, 0]], dtype=np.uint8)
    got = paint_edges.forest_coverage(small, (3, 4), (8, 8), smooth=False)
    want = np.isin(expand_trees(small, (8, 8)), [3, 4]).astype(np.float32)
    assert np.array_equal(got, want)


def test_forest_coverage_smooth_is_a_ramp_between_source_pixels():
    small = np.array([[0, 0, 3, 3]], dtype=np.uint8)
    cov = paint_edges.forest_coverage(small, (3,), (1, 32), smooth=True)
    assert cov.min() == pytest.approx(0.0)
    assert cov.max() == pytest.approx(1.0)
    assert 0.0 < cov[0, 15] < 1.0, "an interpolated edge, not a step"


def test_forest_coverage_threshold_keeps_the_boundary_within_half_a_source_px():
    small = np.zeros((8, 8), dtype=np.uint8)
    small[2:6, 2:6] = 3
    scale = 8
    cov = paint_edges.forest_coverage(small, (3,), (8 * scale, 8 * scale))
    mask = cov >= 0.5
    hard = np.isin(
        paint_edges.forest_coverage(small, (3,), (8 * scale, 8 * scale), smooth=False),
        [1.0],
    )
    # the smooth mask rounds the corners but never travels further than half
    # a source pixel from the block mask
    from scipy.ndimage import distance_transform_edt

    d_out = distance_transform_edt(~hard)[mask & ~hard]
    d_in = distance_transform_edt(hard)[hard & ~mask]
    worst = max(
        float(d_out.max()) if d_out.size else 0.0,
        float(d_in.max()) if d_in.size else 0.0,
    )
    assert worst <= scale / 2.0 + 1e-6, worst


def test_forest_coverage_is_deterministic():
    small = np.array([[0, 3], [4, 0]], dtype=np.uint8)
    a = paint_edges.forest_coverage(small, (3, 4), (16, 16))
    b = paint_edges.forest_coverage(small, (3, 4), (16, 16))
    assert np.array_equal(a, b)


# --------------------------------------------------------------------------- #
# the keys have to be read by the REAL CLI config builder
# --------------------------------------------------------------------------- #
def test_cli_config_builder_reads_the_soft_edge_keys():
    """A `[map]` key `_map_config` never reads is a silent no-op.

    That is the `[map] colormap = false` bug and the `[map] trees*` bug,
    twice over; `ck2ck3.steps.map._map_config` is the only reader of the
    `[map]` table, so every key of this lane is asserted here.
    """
    from pathlib import Path as _P

    from ck2ck3.steps import map as map_step

    keys = {
        "terrain_paint_soft_edges": (False, True),
        "terrain_paint_edge_sigma_px": (3.5, 2.0),
        "terrain_paint_relief_shift_px": (0.0, 1.5),
        "terrain_paint_relief_sigma_px": (4.0, 8.0),
        "terrain_paint_relief_percentile": (75.0, 90.0),
        "trees_mask_smooth": (False, True),
        "trees_mask_threshold": (0.25, 0.5),
        "trees_mask_blur_px": (1.5, 0.0),
    }

    class Cfg:
        raw = {
            "map": {
                "vanilla_km_per_px": 1.0,
                "source_km_per_px": 1.0,
                **{k: v[0] for k, v in keys.items()},
            }
        }
        path = _P("configs/x.toml")
        out = _P("/tmp/out")
        prefix = "fae"
        bookmark_date = (1357, 1, 1)
        name = "n"
        version = "0"
        supported_version = "1.19.*"

    class Ctx:
        config = Cfg()

        def ck2(self, *parts):
            return _P("/tmp/ck2").joinpath(*parts)

        def ck3(self, *parts):
            return _P("/tmp/ck3").joinpath(*parts)

    cfg = map_step._map_config(Ctx())
    for key, (set_value, _default) in keys.items():
        assert getattr(cfg, key) == set_value, key
    for key in keys:
        Cfg.raw["map"].pop(key)
    cfg = map_step._map_config(Ctx())
    for key, (_set_value, default) in keys.items():
        assert getattr(cfg, key) == default, key
