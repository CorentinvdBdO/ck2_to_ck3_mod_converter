"""Tests for the vanilla-matched heightmap detail synthesis pass.

``docs/map_fidelity.md`` §4.2: a synthetic island stands in for the real
Faerûn heightmap so these run in milliseconds. The invariants that matter are
the sea-level pin, the coastline (no land pixel below water, no water pixel
touched at all), determinism, and terrain-aware amplitude -- not any exact
numeric output, which is stochastic by design.
"""

from __future__ import annotations

import numpy as np
import pytest
from scipy.ndimage import distance_transform_edt, gaussian_filter

from ck2ck3.map import heightmap_detail as hd
from ck2ck3.map.config import HeightmapDetailConfig

WATER = 4883
MAXLVL = 49205
KM_PER_PX = 1.4839


def _island(h: int = 120, w: int = 140, margin: int = 20, plateau: int = 20000):
    """A square island with a smooth (not cliff) coastal ramp, all plains."""
    land = np.zeros((h, w), dtype=bool)
    land[margin : h - margin, margin : w - margin] = True
    d_land = distance_transform_edt(land)
    taper = np.clip(d_land / 8, 0, 1)
    land_height = WATER + 1 + taper * (plateau - WATER - 1)
    heights = np.where(land, land_height, WATER)
    heights = np.clip(heights, 0, MAXLVL).astype(np.uint16)
    terrain_code = np.zeros((h, w), dtype=np.uint8)
    river_body = np.zeros((h, w), dtype=bool)
    river_width_index = np.zeros((h, w), dtype=np.float32)
    return heights, land, terrain_code, river_body, river_width_index


#: 16-bit levels per 8-bit CK2 source step for the shipped transfer curve
QUANT = (MAXLVL - WATER) / 160.0


def _terraced_island(h: int = 160, w: int = 200, margin: int = 20,
                     cliff_steps: int = 5, riser_every: int = 3):
    """The fixture that matters: quantisation risers *and* one real cliff.

    A land square whose height rises west to east one 277-level quantisation
    step at a time -- exactly what an 8-bit CK2 source through the transfer
    curve produces -- with a single ``cliff_steps``-step jump in the middle,
    which is what a real escarpment (Thay's plateau edge, the Spine of the
    World) looks like after the same curve.  A de-terrace pass has to erase
    the first and keep the second.

    ``riser_every`` is 3 px because the canvas is a 1.95x LANCZOS upsample of
    the CK2 source, so a slope of one source step per source pixel lands its
    risers 2-3 canvas pixels apart -- an isolated riser is the easy case and
    not the one Faerun actually presents.
    """
    land = np.zeros((h, w), dtype=bool)
    land[margin:h - margin, margin:w - margin] = True
    xs = np.arange(w)
    level = np.clip((xs - margin) // riser_every, 0, None)
    level = level + cliff_steps * (xs >= w // 2)           # the real cliff
    heights = np.where(land, WATER + 1 + level[None, :] * QUANT, WATER)
    heights = np.clip(heights, 0, MAXLVL).astype(np.uint16)
    terrain_code = np.zeros((h, w), dtype=np.uint8)
    river_body = np.zeros((h, w), dtype=bool)
    river_width_index = np.zeros((h, w), dtype=np.float32)
    return heights, land, terrain_code, river_body, river_width_index


def _step_survival(before: np.ndarray, after: np.ndarray, mask: np.ndarray,
                   lo: float, hi: float) -> float:
    """Fraction of the horizontal step amplitude in ``[lo, hi)`` still there.

    ``lo``/``hi`` are in quantisation steps, measured on ``before``; only
    pairs where ``mask`` holds on both sides count.
    """
    db = np.diff(before.astype(np.float64), axis=1)
    da = np.diff(after.astype(np.float64), axis=1)
    m = mask[:, 1:] & mask[:, :-1]
    sel = m & (np.abs(db) >= lo * QUANT) & (np.abs(db) < hi * QUANT)
    if not sel.any():
        return 0.0
    return float(np.abs(da[sel]).sum() / np.abs(db[sel]).sum())


def _apply(heights, land, terrain_code, river_body, river_width_index,
           terrain_keys=("plains",), **cfg_kw):
    cfg_kw.setdefault("seed", 1357)
    cfg = HeightmapDetailConfig(enabled=True, **cfg_kw)
    return hd.apply(
        heights,
        land_mask=land,
        terrain_code=terrain_code,
        terrain_keys=list(terrain_keys),
        river_body=river_body,
        river_width_index=river_width_index,
        km_per_px=KM_PER_PX,
        water_level=WATER,
        max_level=MAXLVL,
        cfg=cfg,
    )


# --------------------------------------------------------------------------- #
# the sea-level pin and the coastline
# --------------------------------------------------------------------------- #
def test_water_pixels_are_byte_identical_to_the_input():
    heights, land, tc, rb, rw = _island()
    out, _ = _apply(heights, land, tc, rb, rw)
    assert np.array_equal(out[~land], heights[~land])


def test_every_land_pixel_stays_strictly_above_the_water_level():
    heights, land, tc, rb, rw = _island()
    out, _ = _apply(heights, land, tc, rb, rw)
    assert (out[land].astype(np.int64) > WATER).all()


def test_every_land_pixel_stays_at_or_below_the_configured_ceiling():
    heights, land, tc, rb, rw = _island()
    out, _ = _apply(heights, land, tc, rb, rw)
    assert (out[land].astype(np.int64) <= MAXLVL).all()


def test_output_is_uint16():
    heights, land, tc, rb, rw = _island()
    out, _ = _apply(heights, land, tc, rb, rw)
    assert out.dtype == np.uint16


def test_output_shape_matches_input():
    heights, land, tc, rb, rw = _island()
    out, _ = _apply(heights, land, tc, rb, rw)
    assert out.shape == heights.shape


def test_water_pixels_above_the_pin_in_the_input_are_clamped_down():
    """The plain rescale (heightmap.build) can itself leave a water pixel
    above the water level -- provinces.png's land/water classification and
    topology.bmp's own value do not perfectly agree at every coastline pixel.
    This pass must not pass such a pixel through unfixed.
    """
    heights, land, tc, rb, rw = _island()
    heights = heights.copy()
    stray = ~land
    ys, xs = np.nonzero(stray)
    heights[ys[0], xs[0]] = WATER + 500  # a pre-existing rescale artefact
    out, stats = _apply(heights, land, tc, rb, rw)
    assert int(out[ys[0], xs[0]]) <= WATER
    assert stats["water_px_clamped"] == 1


def test_all_sea_no_land_is_a_no_op():
    """A province set with no land at all must not crash or touch anything."""
    h, w = 40, 40
    heights = np.full((h, w), WATER, dtype=np.uint16)
    land = np.zeros((h, w), dtype=bool)
    tc = np.zeros((h, w), dtype=np.uint8)
    rb = np.zeros((h, w), dtype=bool)
    rw = np.zeros((h, w), dtype=np.float32)
    out, stats = _apply(heights, land, tc, rb, rw)
    assert np.array_equal(out, heights)
    assert stats["distinct_values_after"] == 1


# --------------------------------------------------------------------------- #
# determinism
# --------------------------------------------------------------------------- #
def test_same_seed_is_deterministic():
    heights, land, tc, rb, rw = _island()
    out1, _ = _apply(heights, land, tc, rb, rw)
    out2, _ = _apply(heights, land, tc, rb, rw)
    assert np.array_equal(out1, out2)


def test_different_seed_changes_the_land_pixels():
    heights, land, tc, rb, rw = _island()
    # force a nonzero gain (the default island's HF is already near vanilla's
    # own "plains" target, which would make both seeds add ~0 noise)
    big_target = {"plains": 5000.0}
    out1, _ = _apply(heights, land, tc, rb, rw, seed=1, hf_targets=big_target)
    out2, _ = _apply(heights, land, tc, rb, rw, seed=2, hf_targets=big_target)
    assert not np.array_equal(out1[land], out2[land])
    # the invariant still holds under a different seed
    assert np.array_equal(out1[~land], out2[~land])


# --------------------------------------------------------------------------- #
# detail actually gets added
# --------------------------------------------------------------------------- #
def test_distinct_values_increase():
    """The whole point: fewer than ~160 flat levels in, many more out."""
    heights, land, tc, rb, rw = _terraced_island()
    out, stats = _apply(heights, land, tc, rb, rw)
    assert stats["distinct_values_after"] > stats["distinct_values_before"]
    assert stats["distinct_values_before"] == int(np.unique(heights).size)
    assert stats["distinct_values_after"] == int(np.unique(out).size)


def test_stats_report_elapsed_time_and_terrain_gain_rows():
    heights, land, tc, rb, rw = _island()
    _, stats = _apply(heights, land, tc, rb, rw)
    assert stats["elapsed_s"] >= 0
    assert stats["terrain_gain"], "expected at least one terrain-class gain row"
    assert stats["terrain_gain"][0]["terrain"] == "plains"


# --------------------------------------------------------------------------- #
# terrain-aware amplitude: mountains rougher than plains
# --------------------------------------------------------------------------- #
def test_mountains_get_more_detail_than_plains():
    """Same flat starting elevation, split coast-to-coast; only the terrain
    label differs. Vanilla's mountains HF RMS (311.4) is far above plains'
    (86.3, docs/map_fidelity.md §1.2), so the synthesised noise must be too.
    """
    h, w, margin = 300, 300, 30
    land = np.zeros((h, w), dtype=bool)
    land[margin : h - margin, margin : w - margin] = True
    d_land = distance_transform_edt(land)
    taper = np.clip(d_land / 8, 0, 1)
    land_height = WATER + 1 + taper * (20000 - WATER - 1)
    heights = np.clip(np.where(land, land_height, WATER), 0, MAXLVL).astype(np.uint16)

    terrain_code = np.zeros((h, w), dtype=np.uint8)
    terrain_code[:, w // 2 :] = 1  # west = plains (0), east = mountains (1)
    river_body = np.zeros((h, w), dtype=bool)
    river_width_index = np.zeros((h, w), dtype=np.float32)

    out, _ = _apply(
        heights, land, terrain_code, river_body, river_width_index,
        terrain_keys=("plains", "mountains"), seed=7,
    )

    # measured away from the coastal ramp, where both halves started identical
    inner = (d_land > 20) & land
    sigma_px = hd.HF_SIGMA_KM / KM_PER_PX

    def hf_rms(mask: np.ndarray) -> float:
        r = out.astype(np.float64) - gaussian_filter(
            out.astype(np.float64), sigma_px, mode="nearest"
        )
        return float(r[mask].std())

    plains_hf = hf_rms(inner & (terrain_code == 0))
    mountains_hf = hf_rms(inner & (terrain_code == 1))
    assert mountains_hf > 3 * plains_hf


# --------------------------------------------------------------------------- #
# river valleys never raise a pixel
# --------------------------------------------------------------------------- #
def test_river_carving_only_lowers_land_never_raises_it():
    heights, land, tc, rb, rw = _island()
    rb = rb.copy()
    mid = heights.shape[0] // 2
    rb[mid, :] = land[mid, :]
    rw = rw.copy()
    rw[rb] = 5.0

    out_river, _ = _apply(heights, land, tc, rb, rw, seed=99)
    out_no_river, _ = _apply(heights, land, tc, np.zeros_like(rb), rw, seed=99)

    river_land = rb & land
    # the river row must not end up higher than it would with no river at all
    assert (
        out_river[river_land].astype(np.int64) <= out_no_river[river_land].astype(np.int64)
    ).all()


def test_river_stays_above_the_water_level_even_when_carved():
    heights, land, tc, rb, rw = _island()
    rb = rb.copy()
    mid = heights.shape[0] // 2
    rb[mid, :] = land[mid, :]
    rw = rw.copy()
    rw[rb] = 3.0  # widest body colour -> deepest cut

    out, _ = _apply(heights, land, tc, rb, rw, river_depth=900.0)
    assert (out[rb & land].astype(np.int64) > WATER).all()


# --------------------------------------------------------------------------- #
# input validation
# --------------------------------------------------------------------------- #
def test_rejects_non_uint16_heights():
    heights, land, tc, rb, rw = _island()
    with pytest.raises(ValueError, match="uint16"):
        _apply(heights.astype(np.int32), land, tc, rb, rw)


def test_rejects_a_mask_shape_mismatch():
    heights, land, tc, rb, rw = _island()
    with pytest.raises(ValueError, match="does not match"):
        _apply(heights, land[:-1, :], tc, rb, rw)


# --------------------------------------------------------------------------- #
# §2b cliff-aware de-terrace: single-step risers go, multi-step cliffs stay
# --------------------------------------------------------------------------- #
def test_cliff_aware_deterrace_keeps_a_multi_step_cliff_the_gaussian_destroys():
    """The measurement the mode exists for, on the synthetic fixture.

    Faerun's own numbers are in docs/step_map_heightmap.md §2b; this pins the
    mechanism so a future change to sigma or the threshold cannot quietly
    reintroduce the blur.
    """
    heights, land, tc, rb, rw = _terraced_island()
    h0 = heights.astype(np.float32)
    gauss = gaussian_filter(h0, 1.6, mode="nearest")
    cliff = hd.erosion.deterrace_cliff_aware(h0, 1.6, 1.5 * hd.erosion.QUANTISATION_STEP_LEVELS)

    g_cliff = _step_survival(h0, gauss, land, 2.0, 99.0)
    c_cliff = _step_survival(h0, cliff, land, 2.0, 99.0)
    assert g_cliff < 0.5, f"the Gaussian is supposed to blunt the cliff, got {g_cliff}"
    assert 0.95 < c_cliff < 1.25, f"the cliff must survive, and not be sharpened away from its own amplitude: {c_cliff}"
    assert c_cliff > 2 * g_cliff


def test_cliff_aware_deterrace_removes_more_single_step_riser_than_the_gaussian():
    heights, land, tc, rb, rw = _terraced_island()
    h0 = heights.astype(np.float32)
    gauss = gaussian_filter(h0, 1.6, mode="nearest")
    cliff = hd.erosion.deterrace_cliff_aware(h0, 1.6, 1.5 * hd.erosion.QUANTISATION_STEP_LEVELS)
    g_left = _step_survival(h0, gauss, land, 0.5, 1.5)
    c_left = _step_survival(h0, cliff, land, 0.5, 1.5)
    assert c_left < g_left, (
        f"cliff-aware left {c_left} of the risers, the Gaussian {g_left}"
    )


def test_deterrace_iterations_match_the_requested_gaussian_sigma():
    """In a flat region the diffusion is the heat equation, so it must blur
    like the Gaussian it replaces -- otherwise the two modes are not
    comparable and the config key changes more than it says."""
    rng = np.random.default_rng(0)
    a = rng.standard_normal((160, 160)).astype(np.float32) * 50.0
    gauss = gaussian_filter(a, 2.0, mode="nearest")
    # threshold far above any local difference -> pure linear diffusion
    lin = hd.erosion.deterrace_cliff_aware(a, 2.0, 1e9)
    inner = (slice(20, -20), slice(20, -20))
    assert abs(float(lin[inner].std()) - float(gauss[inner].std())) < 0.15 * float(
        gauss[inner].std()
    )


def test_unknown_deterrace_mode_is_rejected():
    heights, land, tc, rb, rw = _terraced_island()
    with pytest.raises(ValueError, match="deterrace_mode"):
        _apply(heights, land, tc, rb, rw, deterrace_mode="bilateral")


def test_both_deterrace_modes_keep_the_water_and_land_invariants():
    heights, land, tc, rb, rw = _terraced_island()
    for mode in ("gaussian", "cliff_aware"):
        out, _ = _apply(heights, land, tc, rb, rw, deterrace_mode=mode)
        assert np.array_equal(out[~land], heights[~land])
        assert (out[land].astype(np.int64) > WATER).all()
        assert (out[land].astype(np.int64) <= MAXLVL).all()


# --------------------------------------------------------------------------- #
# §2c eroded relief
# --------------------------------------------------------------------------- #
def test_eroded_relief_is_deterministic_and_unit_scaled():
    heights, land, tc, rb, rw = _terraced_island()
    base = heights.astype(np.float32)
    f1, d1 = hd.erosion.eroded_relief(base, land, np.random.default_rng(3),
                                      iterations=4, accum_iterations=2)
    f2, d2 = hd.erosion.eroded_relief(base, land, np.random.default_rng(3),
                                      iterations=4, accum_iterations=2)
    assert np.array_equal(f1, f2)
    assert abs(float(f1[land].std()) - 1.0) < 1e-3
    assert d1 == d2


def test_eroded_relief_beats_white_noise_on_drainage_concentration():
    """Dendritic means flow concentrates: a few channel pixels carry most of
    the catchment.  White noise with the same spectrum does not.
    """
    rng = np.random.default_rng(11)
    h, w = 256, 256
    land = np.ones((h, w), dtype=bool)
    base = np.full((h, w), 20000.0, dtype=np.float32)
    field, _ = hd.erosion.eroded_relief(base, land, rng, iterations=24,
                                        accum_iterations=4)

    def top1_share(a: np.ndarray) -> float:
        weights = hd.erosion._mfd_weights(a.astype(np.float32), 4.0)
        acc = hd.erosion.flow_accumulation(weights, land, 48)
        v = np.sort(acc.ravel())[::-1]
        return float(v[: max(1, v.size // 100)].sum() / v.sum())

    white = hd.erosion.fractal_seed((h, w), np.random.default_rng(11))
    assert top1_share(field) > 1.25 * top1_share(white)


def test_flow_accumulation_conserves_the_catchment_downstream():
    """One tilted plane: every pixel drains south, so the accumulated area at
    the bottom row must be far above the top row's, and nothing is lost."""
    h, w = 40, 40
    land = np.ones((h, w), dtype=bool)
    ramp = np.tile(np.arange(h, 0, -1, dtype=np.float32)[:, None], (1, w)) * 100.0
    weights = hd.erosion._mfd_weights(ramp, 4.0)
    acc = hd.erosion.flow_accumulation(weights, land, h)
    assert acc[-1, w // 2] > 5 * acc[0, w // 2]
    assert acc.min() >= 1.0 - 1e-5


def test_eroded_relief_mode_keeps_every_invariant():
    heights, land, tc, rb, rw = _terraced_island()
    out, stats = _apply(heights, land, tc, rb, rw, relief_mode="eroded",
                        erosion_iterations=4, erosion_accum_iterations=2)
    assert np.array_equal(out[~land], heights[~land])
    assert (out[land].astype(np.int64) > WATER).all()
    assert (out[land].astype(np.int64) <= MAXLVL).all()
    assert stats["relief_mode"] == "eroded"
    assert stats["erosion_iterations"] == 4


def test_unknown_relief_mode_is_rejected():
    heights, land, tc, rb, rw = _terraced_island()
    with pytest.raises(ValueError, match="relief_mode"):
        _apply(heights, land, tc, rb, rw, relief_mode="ridged")


def test_eroded_relief_still_hits_the_per_terrain_amplitude_target():
    """The structure pass must not disturb the amplitude calibration: the
    spectral equaliser reshapes the eroded field's radial spectrum onto the
    same deficit the white-noise version used, so mountains must still come
    out far rougher than plains.
    """
    h, w, margin = 300, 300, 30
    land = np.zeros((h, w), dtype=bool)
    land[margin:h - margin, margin:w - margin] = True
    d_land = distance_transform_edt(land)
    taper = np.clip(d_land / 8, 0, 1)
    heights = np.clip(np.where(land, WATER + 1 + taper * (20000 - WATER - 1), WATER),
                      0, MAXLVL).astype(np.uint16)
    terrain_code = np.zeros((h, w), dtype=np.uint8)
    terrain_code[:, w // 2:] = 1
    rb = np.zeros((h, w), dtype=bool)
    rw = np.zeros((h, w), dtype=np.float32)
    out, _ = _apply(heights, land, terrain_code, rb, rw,
                    terrain_keys=("plains", "mountains"), seed=7,
                    relief_mode="eroded", erosion_iterations=6,
                    erosion_accum_iterations=2)
    inner = (d_land > 20) & land
    sigma_px = hd.HF_SIGMA_KM / KM_PER_PX
    r = out.astype(np.float64) - gaussian_filter(out.astype(np.float64), sigma_px,
                                                 mode="nearest")
    assert float(r[inner & (terrain_code == 1)].std()) > 3 * float(
        r[inner & (terrain_code == 0)].std()
    )


# --------------------------------------------------------------------------- #
# the config keys are actually read, under the header the code actually reads
# --------------------------------------------------------------------------- #
def test_every_new_flat_map_key_reaches_the_config():
    """A `[map] heightmap_detail_*` key that nothing reads is silent: the run
    succeeds and the setting is simply absent.  This pins the flat CLI form
    (docs/step_map_heightmap.md §5) key by key.
    """
    from ck2ck3.map.config import heightmap_detail_config

    raw = {
        "heightmap_detail": True,
        "heightmap_detail_deterrace_mode": "gaussian",
        "heightmap_detail_cliff_step_levels": 500.0,
        "heightmap_detail_relief_mode": "isotropic",
        "heightmap_detail_target_mode": "power_law",
        "heightmap_detail_target_gain": 0.75,
        "heightmap_detail_gain_mode": "hf_target",
        "heightmap_detail_fill_gain": 0.4,
        "heightmap_detail_erosion_iterations": 5,
        "heightmap_detail_erosion_accum_iterations": 2,
        "heightmap_detail_erosion_seed_amplitude": 111.0,
        "heightmap_detail_erosion_mfd_exponent": 2.0,
        "heightmap_detail_erosion_incision": 0.25,
        "heightmap_detail_erosion_diffusion": 0.02,
    }
    cfg = heightmap_detail_config(raw)
    assert cfg.enabled
    assert cfg.deterrace_mode == "gaussian"
    assert cfg.cliff_step_levels == 500.0
    assert cfg.relief_mode == "isotropic"
    assert cfg.target_mode == "power_law"
    assert cfg.target_gain == 0.75
    assert cfg.gain_mode == "hf_target"
    assert cfg.fill_gain == 0.4
    assert cfg.erosion_iterations == 5
    assert cfg.erosion_accum_iterations == 2
    assert cfg.erosion_seed_amplitude == 111.0
    assert cfg.erosion_mfd_exponent == 2.0
    assert cfg.erosion_incision == 0.25
    assert cfg.erosion_diffusion == 0.02


def test_the_new_keys_also_work_in_the_standalone_nested_table():
    """`configs/faerun_map.toml` nests a real `[heightmap_detail]` table; the
    two readers must not drift apart."""
    from ck2ck3.map.config import _heightmap_detail_from_table

    cfg = _heightmap_detail_from_table({
        "enabled": True, "deterrace_mode": "gaussian", "cliff_step_levels": 300.0,
        "relief_mode": "isotropic", "target_mode": "power_law",
        "target_gain": 0.5, "gain_mode": "hf_target", "fill_gain": 0.6,
        "erosion_iterations": 3, "erosion_accum_iterations": 1,
        "erosion_seed_amplitude": 9.0, "erosion_mfd_exponent": 1.5,
        "erosion_incision": 0.1, "erosion_diffusion": 0.01,
    })
    assert (cfg.deterrace_mode, cfg.relief_mode, cfg.target_mode) == (
        "gaussian", "isotropic", "power_law")
    assert cfg.cliff_step_levels == 300.0
    assert cfg.target_gain == 0.5
    assert cfg.gain_mode == "hf_target"
    assert cfg.fill_gain == 0.6
    assert cfg.erosion_iterations == 3


def test_the_defaults_are_the_ones_the_docs_claim():
    from ck2ck3.map.config import HeightmapDetailConfig
    d = HeightmapDetailConfig()
    assert d.deterrace_mode == "cliff_aware"
    assert d.cliff_step_levels == 415.5           # 1.5 x 277.0125
    assert d.relief_mode == "eroded"
    assert d.target_mode == "vanilla_curve"
    assert d.target_gain == 1.0
    assert d.gain_mode == "deficit"
    assert d.fill_gain == 0.70
    assert d.deterrace_sigma_px == 2.2


# --------------------------------------------------------------------------- #
# the fill must fit in the headroom, not be clamped back afterwards
# --------------------------------------------------------------------------- #
def test_a_lowland_fill_does_not_end_on_the_clamp_floor():
    """The shipped build put 8.19 % of all land on `water_level + 1` because
    the fill wrote below sea level and the closing clip rescued it
    (docs/evidence/report_map_paint/clamp_floor.csv, lane relief-report).
    A plateau at Faerun's own land median with vanilla's own plains
    amplitude must not end up there at all.
    """
    h, w, margin = 200, 200, 20
    land = np.zeros((h, w), dtype=bool)
    land[margin:h - margin, margin:w - margin] = True
    heights = np.where(land, WATER + 4200, WATER).astype(np.uint16)  # ~9000
    tc = np.zeros((h, w), dtype=np.uint8)
    rb = np.zeros((h, w), dtype=bool)
    rw = np.zeros((h, w), dtype=np.float32)
    out, stats = _apply(heights, land, tc, rb, rw)
    assert stats["land_pct_on_clamp_floor"] < 0.5, stats
    assert (out[land].astype(np.int64) > WATER).all()


def test_the_headroom_limiter_is_the_identity_on_small_offsets():
    from ck2ck3.map import heightmap_detail as mod
    base = np.full((8, 8), 20000.0, dtype=np.float32)
    land = np.ones((8, 8), dtype=bool)
    delta = np.full((8, 8), 30.0, dtype=np.float32)
    out, diag = mod._limit_excursion(delta, base, 4884.0, 49205.0, land)
    assert np.allclose(out, delta, rtol=2e-4)
    assert diag["excursion_limited_px"] == 0


def test_the_headroom_limiter_never_reaches_the_floor_or_the_ceiling():
    from ck2ck3.map import heightmap_detail as mod
    base = np.array([[5000.0, 49000.0]], dtype=np.float32)
    land = np.ones((1, 2), dtype=bool)
    delta = np.array([[-100000.0, 100000.0]], dtype=np.float32)
    out, _ = mod._limit_excursion(delta, base, 4884.0, 49205.0, land)
    assert (base + out >= 4884.0).all()
    assert (base + out <= 49205.0).all()


def test_the_vanilla_target_curve_is_monotone_and_covers_our_nyquist():
    """The baked-in table has to reach our 1x Nyquist (0.337 cycles/km) or the
    fill has no target where the report says we are worst."""
    ks = [k for k, _ in hd.VANILLA_LAND_SPECTRUM]
    amps = [a for _, a in hd.VANILLA_LAND_SPECTRUM]
    assert ks == sorted(ks)
    assert all(b <= a for a, b in zip(amps, amps[1:])), "vanilla's law is falling"
    assert ks[-1] >= 0.34


def test_unknown_target_mode_is_rejected():
    heights, land, tc, rb, rw = _terraced_island()
    with pytest.raises(ValueError, match="target_mode"):
        _apply(heights, land, tc, rb, rw, target_mode="loglog")


def test_unknown_gain_mode_is_rejected():
    heights, land, tc, rb, rw = _terraced_island()
    with pytest.raises(ValueError, match="gain_mode"):
        _apply(heights, land, tc, rb, rw, gain_mode="per_province")


def test_the_relative_terrain_gain_has_a_land_mean_of_one():
    """The per-terrain table stops being an absolute calibration in
    `gain_mode = "deficit"` and becomes a modulation; it must not also move
    the overall level, or the spectral match it sits on top of is undone."""
    from ck2ck3.map import heightmap_detail as mod
    h = w = 120
    land = np.ones((h, w), dtype=bool)
    code = np.zeros((h, w), dtype=np.uint8)
    code[:, w // 2:] = 1
    amp, rows = mod._relative_terrain_gain(
        (h, w), land, code, ["plains", "mountains"],
        {"plains": 86.3, "mountains": 311.4}, 0.0)
    assert abs(float(amp[land].mean()) - 1.0) < 1e-3
    gains = {r["terrain"]: r["gain"] for r in rows}
    assert abs(gains["mountains"] / gains["plains"] - 311.4 / 86.3) < 0.01
