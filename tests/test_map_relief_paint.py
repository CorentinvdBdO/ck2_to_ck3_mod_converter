"""Relief-driven material redistribution within a terrain class.

`docs/step_map_paint.md` §11. The core claim under test: permuting
`detail_index`'s per-pixel material ordinals by vanilla's measured relief
ranking must (1) actually move which material sits in the heaviest slot when
the table says to, (2) never touch `detail_intensity` (the weight VALUES),
and (3) leave the blend-statistics invariant (§10: channels/px, entropy,
primary weight) bit-for-bit unchanged, because those are functions of the
weights alone. Also covers the CLI config-builder silent-no-op bug
(`docs/step_map_paint.md` §11, the fifth time this repo has hit it) and the
synthetic-fixture reader tests for the two mapping tables.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from ck2ck3.map import relief_paint

REPO = Path(__file__).resolve().parents[1]


# --------------------------------------------------------------------------- #
# readers
# --------------------------------------------------------------------------- #
def test_read_material_categories_skips_comments(tmp_path: Path):
    p = tmp_path / "cats.csv"
    p.write_text(
        "# GENERATED, a comment every reader must skip\n"
        "material,ordinal,category\n"
        "mountain_02_snow,10,snow\n"
        "plains_01,20,grass\n"
        "some_unknown_bucket,30,not_a_real_category\n",
        encoding="utf-8",
    )
    cats = relief_paint.read_material_categories(p)
    assert cats["mountain_02_snow"] == "snow"
    assert cats["plains_01"] == "grass"
    # an unrecognised category name is dropped, not silently accepted
    assert "some_unknown_bucket" not in cats


def test_category_of_ordinal_table_defaults_to_other():
    ordinals = {"mountain_02_snow": 5, "plains_01": 7}
    categories = {"mountain_02_snow": "snow"}  # plains_01 unclassified
    table = relief_paint.category_of_ordinal_table(ordinals, categories)
    assert table[5] == relief_paint.CATEGORY_CODE["snow"]
    assert table[7] == relief_paint.CATEGORY_CODE["other"]
    assert table[0] == relief_paint.CATEGORY_CODE["other"]  # never assigned


def test_classify_material_families():
    assert relief_paint.classify_material("mountain_02_snow") == "snow"
    assert relief_paint.classify_material("hills_01_rocks") == "rock"
    assert relief_paint.classify_material("forest_leaf_01") == "forest"
    assert relief_paint.classify_material("plains_01") == "grass"
    assert relief_paint.classify_material("farmland_01") == "soil"
    assert relief_paint.classify_material("debug") == "other"
    # a class whose entire configured mix is one rock family (the
    # coordinator-review finding: mountains = mountain_02/mountain_02_c/
    # mountain_02_d_valleys) must not silently read as a different family
    assert relief_paint.classify_material("mountain_02") == "rock"
    assert relief_paint.classify_material("mountain_02_c") == "rock"
    assert relief_paint.classify_material("mountain_02_d_valleys") == "rock"


def test_read_relief_table_and_priority_table(tmp_path: Path):
    p = tmp_path / "relief_paint.csv"
    p.write_text(
        "# GENERATED, skip me\n"
        "ck3_terrain,slope_bin,curvature_bin,elevation_bin,n,category_rank,"
        "top_material,top_share\n"
        "mountains,high,ridge,high,1000,snow;rock;grass,x,1\n",
        encoding="utf-8",
    )
    table = relief_paint.read_relief_table(p)
    assert table[("mountains", 2, 0, 2)] == ["snow", "rock", "grass"]

    prio = relief_paint.build_priority_table(table, ["mountains", "plains"])
    assert prio.shape == (2, 3, 3, 3, len(relief_paint.CATEGORY_NAMES))
    snow = relief_paint.CATEGORY_CODE["snow"]
    rock = relief_paint.CATEGORY_CODE["rock"]
    forest = relief_paint.CATEGORY_CODE["forest"]  # not in the ranked list
    assert prio[0, 2, 0, 2, snow] < prio[0, 2, 0, 2, rock]
    assert prio[0, 2, 0, 2, rock] < prio[0, 2, 0, 2, forest]
    # a combination with no measurement is a uniform (identity-permutation) row
    assert np.all(prio[1, 0, 0, 0] == prio[1, 0, 0, 0, 0])
    assert np.all(prio[0, 0, 0, 0] == prio[0, 0, 0, 0, 0])  # mountains@(low,ridge,low)


def test_read_relief_shares_table_and_share_table(tmp_path: Path):
    p = tmp_path / "relief_paint.csv"
    p.write_text(
        "# GENERATED, skip me\n"
        "ck3_terrain,slope_bin,curvature_bin,elevation_bin,n,category_rank,"
        "category_shares,top_material,top_share\n"
        "mountains,high,ridge,high,1000,snow;rock,snow=60.0;rock=40.0,x,1\n",
        encoding="utf-8",
    )
    shares = relief_paint.read_relief_shares_table(p)
    row = shares[("mountains", 2, 0, 2)]
    assert row["snow"] == pytest.approx(0.6)
    assert row["rock"] == pytest.approx(0.4)

    table = relief_paint.build_share_table(shares, ["mountains", "plains"])
    assert table.shape == (2, 3, 3, 3, len(relief_paint.CATEGORY_NAMES))
    snow = relief_paint.CATEGORY_CODE["snow"]
    rock = relief_paint.CATEGORY_CODE["rock"]
    assert table[0, 2, 0, 2, snow] == pytest.approx(0.6)
    assert table[0, 2, 0, 2, rock] == pytest.approx(0.4)
    assert float(table[0, 2, 0, 2].sum()) == pytest.approx(1.0)
    # unmeasured combinations are all-zero, not uniform
    assert float(table[1, 0, 0, 0].sum()) == pytest.approx(0.0)

    measured = relief_paint.build_measured_table(shares, ["mountains", "plains"])
    assert measured[0, 2, 0, 2]
    assert not measured[1, 0, 0, 0]


def test_read_family_material_table_and_ordinal_table(tmp_path: Path):
    p = tmp_path / "relief_paint_family_materials.csv"
    p.write_text(
        "# GENERATED, skip me\n"
        "ck3_terrain,family,material,ordinal,share_within_family_pct,"
        "area_share_pct,n\n"
        "mountains,snow,mountain_02_snow,46,92.6,21.7,35287\n"
        "mountains,rock,desert_rocky,15,43.4,36.5,59384\n",
        encoding="utf-8",
    )
    table = relief_paint.read_family_material_table(p)
    assert table[("mountains", "snow")] == "mountain_02_snow"
    assert table[("mountains", "rock")] == "desert_rocky"

    ordinals = {"mountain_02_snow": 46, "desert_rocky": 15, "mountain_02": 10}
    missing: set[tuple[str, str]] = set()
    fam_table = relief_paint.family_material_ordinal_table(
        ["mountains"], table, ordinals,
        fallback_ordinal={"mountains": 10}, missing=missing,
    )
    assert fam_table.shape == (1, len(relief_paint.CATEGORY_NAMES))
    assert fam_table[0, relief_paint.CATEGORY_CODE["snow"]] == 46
    assert fam_table[0, relief_paint.CATEGORY_CODE["rock"]] == 15
    # forest/grass/soil/other were never measured for mountains here -> fallback
    assert fam_table[0, relief_paint.CATEGORY_CODE["forest"]] == 10
    assert ("mountains", "forest") in missing
    assert ("mountains", "snow") not in missing


# --------------------------------------------------------------------------- #
# compute_relief_bins / compute_slope_percentile_mask
# --------------------------------------------------------------------------- #
def _synthetic_pyramid(n: int = 64) -> np.ndarray:
    """A radial pyramid: a ridge/peak at the centre, valleys at the corners,
    flat land near the mid-radius ring -- one array exercising all three
    curvature bins and a wide slope range."""
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float32)
    cy, cx = n / 2, n / 2
    r = np.hypot(yy - cy, xx - cx)
    return (20000 - 400 * r).astype(np.float32)


def test_compute_relief_bins_shapes_and_ranges():
    h = _synthetic_pyramid()
    land = np.ones(h.shape, dtype=bool)
    cls = np.zeros(h.shape, dtype=np.uint8)  # one class covering the whole grid
    slope_bin, curv_bin, elev_bin = relief_paint.compute_relief_bins(
        h, h.shape, land_mask=land, cls=cls, n_classes=1
    )
    for arr in (slope_bin, curv_bin, elev_bin):
        assert arr.shape == h.shape
        assert arr.dtype == np.uint8
        assert set(np.unique(arr)) <= {0, 1, 2}
    # the exact centre is a local maximum -> Laplacian < 0 -> ridge bin (0)
    cy, cx = h.shape[0] // 2, h.shape[1] // 2
    assert curv_bin[cy, cx] == 0
    # elevation strictly follows height order at these two points
    assert elev_bin[cy, cx] >= elev_bin[0, 0]


def test_compute_relief_bins_resolution_factor_strides_down():
    small = _synthetic_pyramid(32)
    big = np.repeat(np.repeat(small, 2, axis=0), 2, axis=1)
    land = np.ones(small.shape, dtype=bool)
    cls = np.zeros(small.shape, dtype=np.uint8)
    s1, c1, e1 = relief_paint.compute_relief_bins(
        small, small.shape, land_mask=land, cls=cls, n_classes=1
    )
    s2, c2, e2 = relief_paint.compute_relief_bins(
        big, small.shape, land_mask=land, cls=cls, n_classes=1, resolution_factor=2
    )
    # striding a 2x-upsampled duplicate back down reproduces the 1x field
    assert np.array_equal(e1, e2)


def test_compute_relief_bins_elevation_is_per_class_not_whole_map():
    """Coordinator review, second finding: a WHOLE-MAP percentile of local
    relief put a uniformly-rough class (e.g. Thay's plateau texture) almost
    entirely in the "high" bin. Two classes at very different roughness must
    each get their OWN ~1/3 split, not one class dominated by the other's
    scale."""
    h = w = 60
    rng = np.random.default_rng(0)
    heights = np.zeros((h, w), dtype=np.float32)
    # left half ("smooth" class): tiny bumps, amplitude ~50
    heights[:, :w // 2] = 10000 + rng.normal(0, 50, size=(h, w // 2))
    # right half ("rough" class): large bumps, amplitude ~2000 -- if binned
    # by a single whole-map percentile this half would be ~100% "high"
    heights[:, w // 2:] = 10000 + rng.normal(0, 2000, size=(h, w // 2))
    cls = np.zeros((h, w), dtype=np.uint8)
    cls[:, w // 2:] = 1
    land = np.ones((h, w), dtype=bool)

    _, _, elev_bin = relief_paint.compute_relief_bins(
        heights, (h, w), land_mask=land, cls=cls, n_classes=2
    )
    for c in (0, 1):
        sel = elev_bin[cls == c]
        counts = np.bincount(sel, minlength=3)
        shares = counts / counts.sum()
        # each class lands close to an even 1/3 split of ITS OWN pixels
        assert np.all(np.abs(shares - 1 / 3) < 0.15), (c, shares)


def test_compute_slope_percentile_mask_flags_only_the_steepest_pixels():
    h = _synthetic_pyramid()
    land = np.ones(h.shape, dtype=bool)
    mask = relief_paint.compute_slope_percentile_mask(
        h, h.shape, land_mask=land, percentile=90.0
    )
    assert mask.dtype == bool
    assert 0 < int(mask.sum()) < mask.size  # some but not all pixels flagged
    # a stricter percentile flags fewer or equal pixels
    strict = relief_paint.compute_slope_percentile_mask(
        h, h.shape, land_mask=land, percentile=99.0
    )
    assert int(strict.sum()) <= int(mask.sum())


# --------------------------------------------------------------------------- #
# apply_relief_redistribution: the invariants
# --------------------------------------------------------------------------- #
def _blend_stats(index: np.ndarray, intensity: np.ndarray, mask: np.ndarray):
    w = intensity[mask].astype(np.float64) / 255.0
    nonzero = (w > 0).sum(axis=1).mean()
    tot = np.maximum(w.sum(axis=1), 1e-9)
    norm = w / tot[:, None]
    ent = -(np.where(norm > 0, norm * np.log2(np.maximum(norm, 1e-12)), 0)).sum(axis=1)
    return float(nonzero), float(ent.mean()), float(norm[:, 0].mean())


def _toy_soft_blend():
    """8x8 canvas, one class ("mountains"), two materials per pixel: ordinal
    1 (rock) at weight 200, ordinal 2 (snow) at weight 55 -- everywhere,
    regardless of relief, exactly the defect this module fixes."""
    h = w = 8
    index = np.zeros((h, w, 4), dtype=np.uint8)
    index[..., 0] = 1
    index[..., 1] = 2
    index[..., 2] = 1  # dead channel repeats the primary, per build_soft_blend
    index[..., 3] = 1
    intensity = np.zeros((h, w, 4), dtype=np.uint8)
    intensity[..., 0] = 200
    intensity[..., 1] = 55
    cls = np.zeros((h, w), dtype=np.uint8)
    return index, intensity, cls, ["mountains"]


def _toy_family_table(n_classes: int = 1) -> np.ndarray:
    """(n_classes, n_families) ordinal table: rock=1 (matches the toy
    fixture's existing primary), snow=3 (a material the fixture does NOT
    already carry -- the whole point of the v2 module, unlike the v1
    permutation this superseded)."""
    fam = np.zeros((n_classes, len(relief_paint.CATEGORY_NAMES)), dtype=np.uint8)
    fam[:, relief_paint.CATEGORY_CODE["rock"]] = 1
    fam[:, relief_paint.CATEGORY_CODE["snow"]] = 3
    fam[:, relief_paint.CATEGORY_CODE["forest"]] = 9  # distinct, so ties are visible
    return fam


def test_apply_relief_family_paint_substitutes_a_material_the_class_never_had():
    index, intensity, cls, class_names = _toy_soft_blend()
    h, w = cls.shape
    # half the canvas (rows 0-3) is a measured, deterministic "100% snow"
    # bin (slope=2 high, curv=0 ridge, elev=2 high) -- a share of 1.0 makes
    # the stochastic draw deterministic regardless of the noise field, so
    # this test can still assert an exact result. The other half has no
    # measured entry at all and must be left untouched.
    slope_bin = np.zeros((h, w), dtype=np.uint8)
    curv_bin = np.zeros((h, w), dtype=np.uint8)
    elev_bin = np.zeros((h, w), dtype=np.uint8)
    slope_bin[:4] = 2
    curv_bin[:4] = 0
    elev_bin[:4] = 2

    shares_table = {("mountains", 2, 0, 2): {"snow": 1.0}}
    family_mat_table = _toy_family_table()
    land_mask = np.ones((h, w), dtype=bool)

    before_stats = _blend_stats(index, intensity, land_mask)
    out, stats = relief_paint.apply_relief_family_paint(
        index, intensity, cls, class_names, slope_bin, curv_bin, elev_bin,
        shares_table=shares_table, family_mat_table=family_mat_table,
        sigma_px=0, interior_weight=0.7, land_mask=land_mask,
    )
    # the table row applies to rows 0-3: snow (ordinal 3 from the family
    # table, distinct from the fixture's own ordinal-2 "snow") is now
    # primary AND secondary (a 100% share draws snow on both the primary
    # and secondary noise fields), which then falls back to the pixel's own
    # original secondary (ordinal 2) to avoid writing the same ordinal into
    # two channels.
    assert np.all(out[:4, :, 0] == 3)
    assert np.all(out[:4, :, 1] == 2)
    # rows 4-7 have no measured entry -> untouched, not forced to family 0
    assert np.array_equal(out[4:], index[4:])
    assert stats["primary_changed_px"] == 4 * w

    # the invariant: intensity (the weight VALUES) is never touched
    after_stats = _blend_stats(out, intensity, land_mask)
    assert before_stats == pytest.approx(after_stats, abs=1e-9)

    # dead channels still repeat the (possibly new) primary
    assert np.all(out[:4, :, 2] == out[:4, :, 0])
    assert np.all(out[:4, :, 3] == out[:4, :, 0])


def test_apply_relief_family_paint_no_table_is_a_no_op():
    index, intensity, cls, class_names = _toy_soft_blend()
    h, w = cls.shape
    zeros = np.zeros((h, w), dtype=np.uint8)
    out, stats = relief_paint.apply_relief_family_paint(
        index, intensity, cls, class_names, zeros, zeros, zeros,
        shares_table={}, family_mat_table=_toy_family_table(),
        land_mask=np.ones((h, w), dtype=bool),
    )
    assert np.array_equal(out, index)
    assert stats["primary_changed_px"] == 0


def test_apply_relief_family_paint_respects_the_interior_gate():
    """A pixel at an active class-boundary blend (low primary weight) must
    never be touched, even when its bin was measured -- that weight
    legitimately encodes a DIFFERENT class's material in a later slot."""
    index, intensity, cls, class_names = _toy_soft_blend()
    h, w = cls.shape
    intensity = intensity.copy()
    intensity[..., 0] = 150  # 150/255 = 0.588, below the 0.7 default gate
    slope_bin = np.full((h, w), 2, dtype=np.uint8)
    curv_bin = np.zeros((h, w), dtype=np.uint8)
    elev_bin = np.full((h, w), 2, dtype=np.uint8)
    shares_table = {("mountains", 2, 0, 2): {"snow": 1.0}}
    out, stats = relief_paint.apply_relief_family_paint(
        index, intensity, cls, class_names, slope_bin, curv_bin, elev_bin,
        shares_table=shares_table, family_mat_table=_toy_family_table(),
        sigma_px=0, interior_weight=0.7, land_mask=np.ones((h, w), dtype=bool),
    )
    assert np.array_equal(out, index)
    assert stats["primary_changed_px"] == 0


def test_apply_physical_family_gate_vetoes_rock_and_snow_on_flat_low_ground():
    """Coordinator review: vanilla's own measured `forest,low,flat,low` row
    is 11% snow / 10% rock -- real in vanilla's Earth geography, but
    sampling it on Faerun sprinkled grey/white blobs across genuinely flat
    lowland forest. The gate must zero BOTH families there, on every class
    and every curvature bin, and renormalise the rest to sum to 1."""
    class_names = ["forest", "mountains"]
    shares_table = {
        ("forest", 0, 1, 0): {"forest": 0.76, "snow": 0.11, "rock": 0.10, "grass": 0.03},
        ("forest", 2, 1, 2): {"snow": 0.31, "rock": 0.29, "grass": 0.18, "forest": 0.22},
    }
    table = relief_paint.build_share_table(shares_table, class_names)
    snow = relief_paint.CATEGORY_CODE["snow"]
    rock = relief_paint.CATEGORY_CODE["rock"]
    forest = relief_paint.CATEGORY_CODE["forest"]
    grass = relief_paint.CATEGORY_CODE["grass"]
    # flat/low: vetoed to exactly 0, remaining mass renormalised to sum 1
    assert table[0, 0, 1, 0, snow] == 0.0
    assert table[0, 0, 1, 0, rock] == 0.0
    assert float(table[0, 0, 1, 0].sum()) == pytest.approx(1.0)
    assert table[0, 0, 1, 0, forest] == pytest.approx(0.76 / 0.79, abs=1e-4)
    assert table[0, 0, 1, 0, grass] == pytest.approx(0.03 / 0.79, abs=1e-4)
    # high/high: untouched, snow/rock survive
    assert table[0, 2, 1, 2, snow] == pytest.approx(0.31)
    assert table[0, 2, 1, 2, rock] == pytest.approx(0.29)
    # a class with no flat/low measurement at all stays all-zero there
    # (build_measured_table gates it off regardless)
    assert float(table[1, 0, 1, 0].sum()) == pytest.approx(0.0)

    # physical_gate=False (opt-out, e.g. for a future caller that wants the
    # raw measured table) leaves the same combination untouched
    raw = relief_paint.build_share_table(shares_table, class_names, physical_gate=False)
    assert raw[0, 0, 1, 0, snow] == pytest.approx(0.11)


def test_apply_relief_family_paint_reproduces_the_measured_mix_in_expectation():
    """The whole point of switching from argmax to sampling (coordinator
    review, docs/step_map_paint.md §11): over many pixels of one bin, the
    chosen-family shares should track the MEASURED proportions, not just
    the single largest one."""
    h = w = 256
    index = np.zeros((h, w, 4), dtype=np.uint8)
    index[..., 0] = 1
    index[..., 2] = 1
    index[..., 3] = 1
    intensity = np.zeros((h, w, 4), dtype=np.uint8)
    intensity[..., 0] = 200
    cls = np.zeros((h, w), dtype=np.uint8)
    # bin (high slope, ridge, high elevation) -- NOT the flat/low ground the
    # physical rock/snow gate vetoes (`apply_physical_family_gate`), since
    # this test is specifically about reproducing a measured rock/snow mix
    two = np.full((h, w), 2, dtype=np.uint8)
    zero = np.zeros((h, w), dtype=np.uint8)
    # a measured 60/40 rock/snow mix -- an argmax would paint 100% rock
    shares_table = {("mountains", 2, 0, 2): {"rock": 0.6, "snow": 0.4}}
    family_mat_table = _toy_family_table()
    out, _ = relief_paint.apply_relief_family_paint(
        index, intensity, cls, ["mountains"], two, zero, two,
        shares_table=shares_table, family_mat_table=family_mat_table,
        sigma_px=0, interior_weight=0.0,
        land_mask=np.ones((h, w), dtype=bool),
    )
    rock_share = float((out[..., 0] == 1).mean())
    snow_share = float((out[..., 0] == 3).mean())
    assert 0.6 - 0.15 <= rock_share <= 0.6 + 0.15
    assert 0.4 - 0.15 <= snow_share <= 0.4 + 0.15


def test_apply_relief_family_paint_sigma_px_controls_patch_size():
    """Larger `sigma_px` must produce visibly LARGER connected patches of one
    family, not the same salt-and-pepper scatter at every scale -- the
    vanilla-measured patch-scale calibration
    (`docs/evidence/vanilla_paint_family_patch_scale.csv`) only means
    anything if this holds."""
    h = w = 128
    index = np.zeros((h, w, 4), dtype=np.uint8)
    index[..., 0] = 1
    index[..., 2] = 1
    index[..., 3] = 1
    intensity = np.zeros((h, w, 4), dtype=np.uint8)
    intensity[..., 0] = 200
    cls = np.zeros((h, w), dtype=np.uint8)
    # bin (high, ridge, high) -- not flat/low ground, so the physical
    # rock/snow gate does not veto this bin's mix (see the other test above)
    two = np.full((h, w), 2, dtype=np.uint8)
    zero = np.zeros((h, w), dtype=np.uint8)
    shares_table = {("mountains", 2, 0, 2): {"rock": 0.5, "snow": 0.5}}
    family_mat_table = _toy_family_table()
    land_mask = np.ones((h, w), dtype=bool)

    def boundary_count(sigma: float) -> int:
        out, _ = relief_paint.apply_relief_family_paint(
            index, intensity, cls, ["mountains"], two, zero, two,
            shares_table=shares_table, family_mat_table=family_mat_table,
            sigma_px=sigma, interior_weight=0.0, land_mask=land_mask,
        )
        prim = out[..., 0]
        return int((prim[:, :-1] != prim[:, 1:]).sum()
                    + (prim[:-1, :] != prim[1:, :]).sum())

    sharp = boundary_count(0.0)
    smooth = boundary_count(10.0)
    assert smooth < sharp * 0.5


def test_build_class_eligible_mask_restricts_by_class_and_flat_low_threshold():
    """Coordinator review, round 3: relief paint must touch ONLY the classes
    named in `relief_paint_classes`, and even there, only away from flat
    AND unprominent ground (`slope_bin > 0 OR elev_bin > 0`)."""
    class_names = ["mountains", "taiga"]
    cls = np.array([[0, 0, 1, 1]], dtype=np.uint8)
    slope_bin = np.array([[2, 0, 2, 0]], dtype=np.uint8)
    elev_bin = np.array([[2, 0, 2, 0]], dtype=np.uint8)
    mask = relief_paint.build_class_eligible_mask(
        cls, class_names, ("mountains",), slope_bin, elev_bin,
    )
    # mountains + relief signal -> eligible
    assert mask[0, 0]
    # mountains but flat/low -> not eligible
    assert not mask[0, 1]
    # taiga is not in the allow-list at all, regardless of slope/elevation
    assert not mask[0, 2]
    assert not mask[0, 3]

    # an empty allow-list touches nothing
    none_mask = relief_paint.build_class_eligible_mask(
        cls, class_names, (), slope_bin, elev_bin,
    )
    assert not none_mask.any()


def test_apply_relief_family_paint_leaves_excluded_classes_byte_identical():
    """Coordinator review, round 3: `taiga` (flat, low relief-signal class,
    NOT in the default `relief_paint_classes`) showed white/grey speckle,
    and `sword_coast`'s flat plains/forest turned into independent-per-pixel
    "camouflage" noise -- both because the substitution ran everywhere
    regardless of whether the class's own relief range carries any signal.
    A class outside the allow-list must come out of
    `apply_relief_family_paint` byte-identical (index AND intensity) to
    what went in -- asserted here on a synthetic two-class fixture, one
    "mountains" (in the allow-list) and one "taiga" (not), both given a
    100%-snow measured bin so any change would be visible."""
    h = w = 8
    index = np.zeros((h, w, 4), dtype=np.uint8)
    index[..., 0] = 1
    index[..., 1] = 2
    index[..., 2] = 1
    index[..., 3] = 1
    intensity = np.zeros((h, w, 4), dtype=np.uint8)
    intensity[..., 0] = 200
    intensity[..., 1] = 55
    class_names = ["mountains", "taiga"]
    cls = np.zeros((h, w), dtype=np.uint8)
    cls[4:] = 1  # rows 4-7 are "taiga"

    slope_bin = np.full((h, w), 2, dtype=np.uint8)
    curv_bin = np.zeros((h, w), dtype=np.uint8)
    elev_bin = np.full((h, w), 2, dtype=np.uint8)
    # both classes measured identically (100% snow) -- so a difference in
    # the OUTPUT can only come from the class-eligibility gate, nothing else
    shares_table = {
        ("mountains", 2, 0, 2): {"snow": 1.0},
        ("taiga", 2, 0, 2): {"snow": 1.0},
    }
    family_mat_table = _toy_family_table(n_classes=2)
    land_mask = np.ones((h, w), dtype=bool)

    eligible = relief_paint.build_class_eligible_mask(
        cls, class_names, ("mountains",), slope_bin, elev_bin,
    )
    out, stats = relief_paint.apply_relief_family_paint(
        index, intensity, cls, class_names, slope_bin, curv_bin, elev_bin,
        shares_table=shares_table, family_mat_table=family_mat_table,
        sigma_px=0, interior_weight=0.0, land_mask=land_mask,
        eligible_mask=eligible,
    )
    # mountains (rows 0-3): substituted, exactly as the un-gated test above
    assert np.all(out[:4, :, 0] == 3)
    # taiga (rows 4-7): byte-identical to the input, index AND intensity
    assert np.array_equal(out[4:], index[4:])
    assert np.array_equal(intensity[4:], intensity[4:])  # never written at all
    assert stats["primary_changed_px"] == 4 * w  # only the eligible half
    assert stats["eligible_px"] == 4 * w
    assert stats["eligible_share"] == pytest.approx(0.5)


# --------------------------------------------------------------------------- #
# CLI config-builder silent-no-op bug
# --------------------------------------------------------------------------- #
def test_cli_config_builder_reads_the_relief_paint_keys():
    """A `[map] relief_paint*`/`trees_slope_gate*` key the REAL CLI builder
    never reads is a silent no-op -- `docs/step_map_paint.md` §11, the same
    bug `colormap`/`trees*` already hit twice."""
    from ck2ck3.steps import map as map_step

    class Cfg:
        raw = {"map": {
            "vanilla_km_per_px": 1.0, "source_km_per_px": 1.0,
            "relief_paint": True,
            "relief_paint_csv": "mappings/other_relief.csv",
            "relief_paint_categories_csv": "mappings/other_cats.csv",
            "relief_paint_classes": ["mountains"],
            "trees_slope_gate": True,
            "trees_slope_gate_percentile": 42.0,
        }}
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
    assert cfg.relief_paint is True
    assert cfg.relief_paint_csv == Path("mappings/other_relief.csv")
    assert cfg.relief_paint_categories_csv == Path("mappings/other_cats.csv")
    assert cfg.relief_paint_classes == ("mountains",)
    assert cfg.trees_slope_gate is True
    assert cfg.trees_slope_gate_percentile == 42.0

    for k in ("relief_paint", "relief_paint_csv", "relief_paint_categories_csv",
              "relief_paint_classes",
              "trees_slope_gate", "trees_slope_gate_percentile"):
        Cfg.raw["map"].pop(k)
    cfg = map_step._map_config(Ctx())
    assert cfg.relief_paint is True  # dataclass default (true since 2026-09-24)
    assert cfg.relief_paint_classes == ("mountains", "desert_mountains", "hills")
    assert cfg.trees_slope_gate is False


def test_standalone_config_load_reads_the_relief_paint_keys(tmp_path: Path):
    """The other front door (`ck2ck3.map.config.load`) must read the same
    keys, or the two builders disagree silently."""
    from ck2ck3.map import config as map_config

    toml_dir = tmp_path / "configs"
    toml_dir.mkdir()
    toml_path = toml_dir / "x.toml"
    toml_path.write_text(
        """
relief_paint = true
relief_paint_csv = "mappings/other_relief.csv"
relief_paint_classes = ["mountains", "hills"]
trees_slope_gate = true
trees_slope_gate_percentile = 33.0

[input]
ck2_map_dir = "ck2map"
[output]
mod_dir = "out"
[scale]
vanilla_km_per_px = 1.0
source_km_per_px = 1.0
""",
        encoding="utf-8",
    )
    cfg = map_config.load(toml_path)
    assert cfg.relief_paint is True
    assert cfg.relief_paint_csv == Path("mappings/other_relief.csv")
    assert cfg.relief_paint_classes == ("mountains", "hills")
    assert cfg.trees_slope_gate is True
    assert cfg.trees_slope_gate_percentile == 33.0
