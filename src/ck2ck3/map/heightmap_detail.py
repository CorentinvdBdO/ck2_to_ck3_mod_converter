"""Deterministic detail synthesis for the CK3 16-bit heightmap.

The plain rescaled heightmap (``heightmap.py``) is faithful but flat: an
8-bit CK2 source through a linear transfer curve leaves land with only ~160
distinct levels 277 apart, which reads as terraced contour lines rather than
terrain (``docs/map_fidelity.md`` §1.2, 212 distinct values against vanilla's
31,516). Prototyped on the Sword Coast in
``scripts/prototype_heightmap_detail.py``; this module is the same four
passes, vectorised for the whole canvas (``docs/map_fidelity.md`` §4.2):

1. **de-terrace** — removes the transfer curve's risers on land only.
   ``deterrace_mode = "gaussian"`` is a small blind blur; ``"cliff_aware"``
   (the default) is Perona-Malik anisotropic diffusion, which erases a
   one-step riser and keeps a multi-step cliff
   (``heightmap_erosion.deterrace_cliff_aware``, docs §2b). Legitimate
   either way because the real signal is band-limited to the CK2 source's
   own Nyquist frequency, so nothing true is lost.
2. **spectral fill** — the per-frequency shortfall of our own land spectrum
   against vanilla's, injected as noise shaped to exactly that deficit.
   Three switches (docs §2c): the *target* is vanilla's own measured radial
   curve (``VANILLA_LAND_SPECTRUM``) or a fitted power law; the *phase
   source* is an eroded, dendritic relief field
   (``heightmap_erosion.eroded_relief``) or white noise; and the *amplitude
   authority* is the measured deficit with ``DEFAULT_HF_TARGETS`` as a
   relative per-terrain modulation, or the original per-class
   ``sqrt(want**2 - have**2)``. ``have`` is measured on all-land interior
   patches, not on the whole canvas, because a coastline is a 4884-level
   step that makes every frequency look full. Frequencies below
   ``KEEP_STRUCTURE_BELOW_KM`` are never touched, so real large-scale
   structure (the CK2 source's own mountains and valleys) survives untouched.
   The synthesised offset is finally saturated into the headroom each pixel
   actually has, so the closing clamp is a rare event rather than the thing
   that flattens 8 % of the land.
3. **river valleys** — a smooth Gaussian cross-section carved along the
   traced ``rivers.png`` body pixels (indices 3-11), depth by the config,
   width by the CK2 river-width index. Applied on land only, so a river
   valley is never *raised* — only ever cut lower than its banks, which is
   what keeps water flowing downhill in valleys instead of ridges.
4. **coast smoothing** — the synthesised offset is damped over the first few
   pixels of land, so a beach stays flat instead of gaining mountain-scale
   noise right at the shore. It used to contract the *height* toward the
   water level, which dug an 8,000-level crater around every one of Faerun's
   high-altitude CK2 lakes (docs §2f); ``coast_mode = "blend_to_water"``
   restores that.
5. **the source bound** — the output is held inside
   ``[source_local_min - tol, source_local_max + tol]`` over a window of one
   CK2 source pixel, ``tol`` being the pixel's terrain class's own measured
   vanilla high-frequency amplitude. Detail is texture on the CK2 author's
   surface, never a hole in it (docs §2f).

Invariants this module must never break (``docs/map_fidelity.md`` §4.2,
``CLAUDE.md``):

* every water pixel (``land_mask`` False — sea, lake, river-type province,
  the padding ocean, from the province raster + ``default.map`` sea_zones and
  lakes, not from a topology threshold) never ends up above ``water_level``.
  Synthesis never touches a water pixel's value at all -- the four passes
  only ever write where ``land_mask`` is True -- so in practice this pixel
  is byte-identical to the input; the one exception is a pixel the plain
  rescale (``heightmap.build``) itself already put above the water level
  before this pass ever ran (``provinces.png``'s land/water classification
  and ``topology.bmp``'s own value do not perfectly agree at every coastline
  pixel), which is clamped down to ``water_level`` rather than passed
  through, so the invariant holds on the *output* unconditionally;
* every land pixel is clamped strictly above ``water_level`` after synthesis
  (the same reasoning, the other direction: the plain rescale alone already
  leaves some land pixels at or below the pin), so a river valley or a
  de-terrace ripple can never sink land back under water either;
* the output never leaves the source's own surface plus texture (pass 5,
  docs §2f); the hit fraction of that backstop is reported as
  ``bound_limited_pct_of_land``, because a backstop that binds often means
  the passes in front of it are writing terrain the source has no basis for;
* deterministic: the same inputs and the same ``HeightmapDetailConfig.seed``
  always produce the same output array.
"""

from __future__ import annotations

import time

import numpy as np
from scipy.ndimage import (
    distance_transform_edt,
    gaussian_filter,
    grey_dilation,
    grey_erosion,
)

from . import heightmap_erosion as erosion
from .config import HeightmapDetailConfig

#: sigma (km) of the high-pass filter used to *measure* per-terrain detail
#: amplitude -- the same band `hf_by_terrain.csv` (docs/map_fidelity.md §1.2)
#: was itself measured with: sigma=4 px on vanilla's 2x heightmap (0.742
#: km/px) = 2.968 km.
HF_SIGMA_KM = 4.0 * 0.742

#: power-law fit band, cycles/km: our own low frequencies below the CK2
#: source's Nyquist are the well-resolved ones the law is fitted against
#: (the prototype's own choice, docs/map_fidelity.md §4.2).
FIT_BAND_MIN_KM = 0.004
FIT_BAND_MAX_KM = 0.03
FIT_BAND_FALLBACK_MAX_KM = 0.05
#: frequencies below this are real large-scale structure, never touched
KEEP_STRUCTURE_BELOW_KM = 0.01
#: The CK2 source raster is 4096 x 3328 upscaled 1.9543x onto the canvas, so
#: one source pixel is 2.90 km and the source's own Nyquist is
#: ``1 / (2 * 2.90)`` = **0.172 cycles/km** (`verified`,
#: ``docs/map_scale.md``).  Below it the CK2 author's terrain is fully
#: *resolved*; it is only *quantised*, to 277-level steps.  That matters for
#: where the fill is allowed to work -- see ``FILL_FULL_ABOVE_KM``.
SOURCE_NYQUIST_KM = 0.172
#: Ground size of one CK2 source pixel, km (``docs/map_scale.md`` §7).  The
#: §2f bound and the §2f erosion gate are both defined per source pixel, not
#: per canvas pixel, so neither moves when the canvas resolution does.
SOURCE_PX_KM = 2.90
#: Default frequency at which the spectral fill reaches full strength, with a
#: cosine roll-on over ``FILL_RAMP_OCTAVES`` below it (docs §2d).
#:
#: Why this is not ``KEEP_STRUCTURE_BELOW_KM``.  A quantiser only ever *adds*
#: broadband noise (step / sqrt(12) = 80 levels, white); it cannot remove
#: energy at 30-90 km.  So a shortfall against vanilla down there is not a
#: bit-depth deficit the pass is entitled to fill -- it is the difference
#: between Faerun's macro relief and Europe's, and filling it fabricates
#: mountain-scale terrain on top of ground the CK2 author drew flat.  On
#: build 13 that put +-20,000 levels of 35-60 km undulation across Thay's
#: plateaus: the cliff-foot moat the playtest reported.  Above ~0.05
#: cycles/km the deficit *is* ours to fill: the de-terrace (a sigma 2.2 px =
#: 3.3 km diffusion) attenuates there, and past the source Nyquist there is
#: no source content at all.
FILL_FULL_ABOVE_KM = 0.05
#: width of the roll-on below ``fill_min_cycles_per_km``, in octaves.  A hard
#: spectral wall rings in space (Gibbs), which beside a cliff is another
#: moat; one octave of raised cosine does not.
FILL_RAMP_OCTAVES = 1.0
#: Vanilla CK3's own measured radial land-elevation spectrum: (cycles/km,
#: mean amplitude in 16-bit levels) over 48 all-land 256x256 patches of
#: ``game/map_data/heightmap.png``, log-resampled from
#: ``docs/evidence/report_map_paint/spectrum.csv`` (lane ``relief-report``,
#: 2026-09-10, `verified`).  Baked in for the same reason
#: ``DEFAULT_HF_TARGETS`` is: a conversion run must not depend on a research
#: evidence file.
#:
#: This replaces the single fitted power law as the fill target.  A law is
#: not good enough: fitted on our own well-resolved 0.004-0.03 band and
#: extrapolated, it over-fills 0.03-0.1 (the shipped build is 1.4-1.7x
#: vanilla's Norwegian coast over 9.5-38 km) and under-fills above 0.08
#: (0.37x vanilla at 0.1 cycles/km, 0.23x at 0.2).  Vanilla's own curve is
#: steeper than f^-2 in the middle -- the fitted exponent over 0.02-0.4 is
#: -2.195 -- and flattens near its Nyquist.
VANILLA_LAND_SPECTRUM: tuple[tuple[float, float], ...] = (
    (0.00400, 43207.3), (0.00499, 43207.3), (0.00624, 38960.8),
    (0.00779, 32181.1), (0.00972, 23716.1), (0.01214, 17360.5),
    (0.01515, 12071.6), (0.01892, 8590.3), (0.02362, 5788.6),
    (0.02950, 3488.7), (0.03683, 1984.2), (0.04598, 1125.9),
    (0.05741, 687.4), (0.07168, 450.6), (0.08950, 260.3),
    (0.11175, 163.2), (0.13953, 98.6), (0.17421, 61.3),
    (0.21751, 37.4), (0.27158, 23.1), (0.33908, 15.0),
    (0.42337, 9.4), (0.52861, 6.9), (0.66000, 5.6),
)


#: number of radial frequency bins for the power-spectrum fit
_N_RADIAL_BINS = 2048
#: floor under the structured field's own radial amplitude before it is
#: divided out, as a fraction of that field's peak.  Only a guard against a
#: genuinely empty bin turning into a ring: it must NOT double as a cap on
#: the gain itself.  It was a cap (8x the median) in the first draft and that
#: was the bug -- the eroded field's difference-from-the-macro is inherently
#: blue, so the equaliser needs three orders of magnitude of gain to bend it
#: back onto vanilla's red curve, and clipping it left the fill adding
#: nothing at 0.05 cycles/km and 2.1x vanilla at 0.3.
_EQUALISER_FLOOR_FRACTION = 1e-4

#: river-valley cross-section: width (canvas px) = BASE + (11 - index) * PER
#: (index 3 is the widest body colour, 11 the narrowest), the CK2 width code
#: mapped the same way the prototype does it
_RIVER_WIDTH_BASE_PX = 2.0
_RIVER_WIDTH_PER_INDEX = 0.6
_RIVER_BLUR_PX = 3.0
_RIVER_MARGIN_PX = 2.0
#: coast smoothing: land at the shoreline itself keeps this fraction of its
#: noise amplitude (0 would flatten the first pixel completely)
_COAST_MIN_FACTOR = 0.45

#: fraction of the source bound's own interval the tanh saturation uses, so
#: the bound is approached smoothly instead of clipped flat (docs §2f)
_BOUND_SOFT_FRACTION = 0.25


def apply(
    heights: np.ndarray,
    *,
    land_mask: np.ndarray,
    terrain_code: np.ndarray,
    terrain_keys: list[str],
    river_body: np.ndarray,
    river_width_index: np.ndarray,
    km_per_px: float,
    water_level: int,
    max_level: int,
    cfg: HeightmapDetailConfig,
) -> tuple[np.ndarray, dict]:
    """Return ``(detailed heights uint16, stats dict)``.

    ``heights`` is the plain rescaled heightmap (``heightmap.build``'s
    output), top-down, ``uint16``. All the mask/code arrays must be the same
    shape as ``heights`` -- at ``resolution_factor > 1`` the caller must
    upsample the province-raster-resolution masks first (nearest neighbour;
    ``map.build._nn_upsample``).
    """
    if heights.dtype != np.uint16:
        raise ValueError(f"heights must be uint16, got {heights.dtype}")
    if heights.shape != land_mask.shape:
        raise ValueError(
            f"land_mask {land_mask.shape} does not match heights {heights.shape}"
        )
    for name, arr in (
        ("terrain_code", terrain_code),
        ("river_body", river_body),
        ("river_width_index", river_width_index),
    ):
        if arr.shape != heights.shape:
            raise ValueError(f"{name} {arr.shape} does not match heights {heights.shape}")

    t0 = time.time()
    land = land_mask.astype(bool)
    h0 = heights.astype(np.float32)
    rng = np.random.default_rng(cfg.seed)

    # 1. de-terrace -----------------------------------------------------
    if cfg.deterrace_mode == "cliff_aware":
        smooth = erosion.deterrace_cliff_aware(
            h0, cfg.deterrace_sigma_px, cfg.cliff_step_levels
        )
    elif cfg.deterrace_mode == "gaussian":
        smooth = gaussian_filter(h0, cfg.deterrace_sigma_px, mode="nearest")
    else:
        raise ValueError(
            f"unknown heightmap_detail_deterrace_mode {cfg.deterrace_mode!r} "
            f"(expected 'cliff_aware' or 'gaussian')"
        )
    h2 = np.where(land, smooth, h0)
    del smooth

    # 2. structured or isotropic relief, spectrally shaped, then scaled
    #    to each CK3 terrain class's own vanilla amplitude ---------------
    relief_diag: dict = {}
    if cfg.relief_mode == "eroded":
        # §2f: the erosion may only run where the *source* has macro slope.
        # §2g: mountains and hills get a ridged seed and less hillslope
        # diffusion, both as per-pixel fields blurred like the amplitude one
        # so a terrain-class border leaves no seam.
        gate = erosion.macro_slope_gate(
            h2, km_per_px, cfg.erosion_slope_gate_steps,
            source_km=SOURCE_PX_KM,
        )
        ridged_w = _class_field(
            terrain_code, terrain_keys, cfg.ridged_classes,
            cfg.ridged_weight, 0.0, cfg.gain_blur_px,
        )
        diff_scale = _class_field(
            terrain_code, terrain_keys, cfg.ridged_classes,
            cfg.ridged_diffusion_scale, 1.0, cfg.gain_blur_px,
        )
        field, relief_diag = erosion.eroded_relief(
            h2, land, rng,
            seed_amplitude=cfg.erosion_seed_amplitude,
            iterations=cfg.erosion_iterations,
            accum_iterations=cfg.erosion_accum_iterations,
            mfd_exponent=cfg.erosion_mfd_exponent,
            incision=cfg.erosion_incision,
            diffusion=cfg.erosion_diffusion,
            slope_ceiling_steps=cfg.erosion_slope_ceiling_steps,
            incision_gate=gate,
            ridged_weight=ridged_w,
            ridged_sharpness=cfg.ridged_sharpness,
            diffusion_scale=diff_scale,
        )
        del gate, ridged_w, diff_scale
        relief_diag["erosion_slope_gate_steps"] = round(
            float(cfg.erosion_slope_gate_steps), 2)
    elif cfg.relief_mode == "isotropic":
        field = None
    else:
        raise ValueError(
            f"unknown heightmap_detail_relief_mode {cfg.relief_mode!r} "
            f"(expected 'eroded' or 'isotropic')"
        )
    noise, spec_diag = _spectral_deficit_noise(
        h2, land, km_per_px, cfg.spectral_slope, rng, field=field,
        target_mode=cfg.target_mode, target_gain=cfg.target_gain,
        fill_min_cycles_per_km=cfg.fill_min_cycles_per_km,
    )
    del field
    spec_diag.update(relief_diag)
    sigma_px = HF_SIGMA_KM / km_per_px
    if cfg.gain_mode == "deficit":
        # The absolute level comes from the per-frequency shortfall, measured
        # with the very operator the evidence measures with, and the vanilla
        # per-terrain table is applied as a *relative* modulation around 1.
        #
        # Why not the original rule.  `need = sqrt(want**2 - have**2)` on a
        # ~3 km high-pass reads the de-terraced base's own residual as detail
        # already present -- and a cliff-aware de-terrace deliberately keeps
        # broadband edge energy, so `have` comes out at or above `want` and
        # the pass decides no fill is needed at all.  The two halves of this
        # lane fight each other through that one subtraction.
        scale, gain_diag = _match_deficit_amplitude(
            noise, land, km_per_px, spec_diag.pop("_deficit_curve"), rng
        )
        scale *= cfg.fill_gain
        gain_diag["deficit_scale"] = round(scale, 4)
        spec_diag.update(gain_diag)
        if gain_diag["deficit_match_bins"]:
            noise *= scale
            amp, gain_rows = _relative_terrain_gain(
                noise.shape, land, terrain_code, terrain_keys,
                cfg.hf_targets, cfg.gain_blur_px,
            )
        else:
            # no all-land interior patch fits (a small map, a synthetic
            # fixture, an archipelago): there is nothing to match the
            # absolute amplitude against, so fall back to the per-class
            # high-pass rule, which needs no interior
            hp_signal = _high_pass(h2, sigma_px)
            hp_noise = _high_pass(noise, sigma_px)
            amp, gain_rows = _terrain_gain(
                hp_signal, hp_noise, land, terrain_code, terrain_keys,
                cfg.hf_targets, cfg.gain_blur_px,
            )
            del hp_signal, hp_noise
    elif cfg.gain_mode == "hf_target":
        spec_diag.pop("_deficit_curve", None)
        hp_signal = _high_pass(h2, sigma_px)
        hp_noise = _high_pass(noise, sigma_px)
        amp, gain_rows = _terrain_gain(
            hp_signal, hp_noise, land, terrain_code, terrain_keys,
            cfg.hf_targets, cfg.gain_blur_px,
        )
        del hp_signal, hp_noise
    else:
        raise ValueError(
            f"unknown heightmap_detail_gain_mode {cfg.gain_mode!r} "
            f"(expected 'deficit' or 'hf_target')"
        )
    delta = amp * noise
    del amp, noise

    # 3. river valleys -----------------------------------------------------
    delta = _carve_rivers(delta, land, river_body, river_width_index, cfg.river_depth)

    # 3b. bound the excursion by the headroom that actually exists ---------
    delta, headroom_diag = _limit_excursion(
        delta, h2, float(water_level) + 1.0, float(max_level), land,
        fraction=cfg.headroom_fraction,
    )
    out = h2 + delta
    del delta

    # 4. coast smoothing -----------------------------------------------------
    out = _smooth_coast(
        out, h2, land, cfg.coast_smooth_px, cfg.coast_mode, float(water_level))
    del h2

    # 5. the hard bound: detail is texture on the author's surface, never a
    #    hole in it.  Last, so what it guarantees is what the map ships with.
    out, bound_diag = _bound_to_source(
        out, h0, land, terrain_code, terrain_keys, cfg.hf_targets,
        window_px=cfg.bound_window_px, sigmas=cfg.bound_tolerance_sigmas,
        floor=float(water_level) + 1.0, ceiling=float(max_level),
    )

    # --- invariants: land strictly above sea, water at or below it --------
    # Land is built from `out` (the synthesised array); water is the input
    # heights, clamped down only in the rare case the plain rescale itself
    # already put a water pixel above the pin -- this pass never otherwise
    # writes a water pixel, so the clamp is a no-op almost everywhere.
    result = heights.copy()
    land_vals = np.clip(np.rint(out[land]), water_level + 1, max_level)
    result[land] = land_vals.astype(np.uint16)
    water = ~land
    water_vals = np.minimum(heights[water].astype(np.int64), water_level)
    result[water] = water_vals.astype(np.uint16)

    stats = {
        "seed": cfg.seed,
        "water_px_clamped": int((heights[water].astype(np.int64) > water_level).sum()),
        "land_px_raised_to_pin": int(
            (heights[land].astype(np.int64) <= water_level).sum()
        ),
        "distinct_values_before": int(np.unique(heights).size),
        "distinct_values_after": int(np.unique(result).size),
        # what fraction of land the closing clip had to rescue: this is the
        # number lane relief-report measured at 8.193 % on the shipped build
        # (docs/evidence/report_map_paint/clamp_floor.csv) and the target is
        # < 0.5 %.  A high number means the fill is writing terrain the map
        # has no room for, not that the clamp is doing its job.
        "land_px_on_clamp_floor": int((land_vals <= water_level + 1).sum()),
        "land_pct_on_clamp_floor": round(
            100.0 * float((land_vals <= water_level + 1).sum())
            / max(int(land.sum()), 1), 3
        ),
        "land_px_at_ceiling": int((land_vals >= max_level).sum()),
        **headroom_diag,
        **bound_diag,
        "deterrace_mode": cfg.deterrace_mode,
        "relief_mode": cfg.relief_mode,
        "coast_mode": cfg.coast_mode,
        "bound_window_px": cfg.bound_window_px,
        "bound_tolerance_sigmas": cfg.bound_tolerance_sigmas,
        "ridged_classes": ",".join(cfg.ridged_classes),
        "ridged_weight": cfg.ridged_weight,
        "power_law_c": spec_diag["power_law_c"],
        "fit_band_bins": spec_diag["fit_band_bins"],
        "elapsed_s": round(time.time() - t0, 1),
        "terrain_gain": gain_rows,
    }
    for key in ("erosion_iterations", "erosion_accum_iterations",
                "erosion_uplift_levels", "erosion_field_rms_levels",
                "erosion_slope_ceiling_steps", "erosion_slope_gate_steps",
                "erosion_gate_land_mean", "erosion_ridged_land_mean",
                "target_mode", "target_anchor_scale", "fill_min_cycles_per_km",
                "deficit_scale", "deficit_match_bins"):
        if key in spec_diag:
            stats[key] = spec_diag[key]
    return result, stats


# --------------------------------------------------------------------------- #
# pass 2: spectral fill
# --------------------------------------------------------------------------- #
def _radial_k_grid(h: int, w: int, km_per_px: float) -> np.ndarray:
    """``(h, w//2+1)`` grid of spatial frequency magnitude, cycles/km.

    Matches ``np.fft.rfft2``'s output shape: real physical frequency, not a
    pixel radius, so a non-square canvas bins correctly.
    """
    fy = np.fft.fftfreq(h, d=km_per_px).astype(np.float32)[:, None]
    fx = np.fft.rfftfreq(w, d=km_per_px).astype(np.float32)[None, :]
    return np.hypot(fy, fx)


def _radial_average(
    values: np.ndarray, k: np.ndarray, bins: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Mean of ``values`` per radial ``k`` bin, and how many samples fed each.

    The counts matter: a fine bin grid over a small array can have bins no
    real ``rfft2`` frequency falls into, and treating those as "amplitude 0"
    rather than "no data" would bias the power-law fit toward zero.
    """
    idx = np.clip(np.digitize(k.ravel(), bins) - 1, 0, len(bins) - 2)
    sums = np.bincount(idx, weights=values.ravel(), minlength=len(bins) - 1)
    counts = np.bincount(idx, minlength=len(bins) - 1)
    return sums / np.maximum(counts, 1), counts


def fill_band_weight(
    centres: np.ndarray, full_above: float, ramp_octaves: float = FILL_RAMP_OCTAVES
) -> np.ndarray:
    """0 below the band, 1 above it, raised cosine in log-frequency between.

    ``full_above`` is where the fill is at full strength; the roll-on starts
    ``ramp_octaves`` octaves below.  Zeroing the deficit with a step instead
    would ring: a brick-wall radial filter has a sinc-shaped impulse
    response, and a sinc beside an escarpment is exactly the artefact §2d
    exists to remove.
    """
    if full_above <= 0.0:
        return np.ones_like(centres, dtype=np.float32)
    lo = full_above / (2.0 ** max(ramp_octaves, 1e-6))
    with np.errstate(divide="ignore", invalid="ignore"):
        t = np.log(np.maximum(centres, 1e-12) / lo) / np.log(full_above / lo)
    t = np.clip(np.nan_to_num(t, nan=0.0, posinf=1.0, neginf=0.0), 0.0, 1.0)
    return (0.5 * (1.0 - np.cos(np.pi * t))).astype(np.float32)


def _spectral_deficit_noise(
    h2: np.ndarray,
    land: np.ndarray,
    km_per_px: float,
    slope: float,
    rng: np.random.Generator,
    field: np.ndarray | None = None,
    target_mode: str = "vanilla_curve",
    target_gain: float = 1.0,
    fill_min_cycles_per_km: float = FILL_FULL_ABOVE_KM,
) -> tuple[np.ndarray, dict]:
    """Unit-scaled noise field shaped to the shortfall against vanilla's law.

    Water is replaced by the land mean before the FFT (not left at the true,
    much lower, water level): otherwise every coastline is a step of
    thousands of 16-bit levels and the spectrum is dominated by coastline
    edges instead of terrain, which is exactly the artefact this pass exists
    to remove.

    ``field`` is the *phase* source.  ``None`` keeps the original behaviour
    (white noise, so the output's radial amplitude is the deficit itself and
    the result is isotropic).  Given an eroded relief field instead
    (``heightmap_erosion.eroded_relief``), the same deficit is imposed as a
    radial *equaliser* -- the field's own radial amplitude is divided out and
    the target multiplied in.  A radial filter changes no phase, so the
    valleys and ridges the erosion built survive intact while the spectrum
    ends up exactly where the isotropic version put it.
    """
    H, W = h2.shape
    fill = float(h2[land].mean()) if land.any() else float(h2.mean())
    a = np.where(land, h2, fill).astype(np.float32) - fill
    wy = np.hanning(H).astype(np.float32)
    wx = np.hanning(W).astype(np.float32)
    a *= wy[:, None] * wx[None, :]

    F = np.fft.rfft2(a)
    power = (np.abs(F) ** 2) / (H * W)
    k = _radial_k_grid(H, W, km_per_px)

    kmax = float(k.max())
    # one radial bin per achievable frequency step at most: a fine bin grid
    # on a small array leaves most bins with no real rfft2 sample in them
    nbins = max(8, min(_N_RADIAL_BINS, min(H, W) // 2))
    bins = np.linspace(0.0, kmax, nbins + 1, dtype=np.float32)
    centres = (bins[:-1] + bins[1:]) / 2
    p_rad, counts = _radial_average(power, k, bins)
    has_data = counts > 0
    amp_rad = np.sqrt(np.maximum(p_rad, 0.0))

    band = has_data & (centres > FIT_BAND_MIN_KM) & (centres < FIT_BAND_MAX_KM)
    if not band.any():
        band = has_data & (centres > 0) & (centres < FIT_BAND_FALLBACK_MAX_KM)
    with np.errstate(divide="ignore", invalid="ignore"):
        c_samples = amp_rad[band] * centres[band] ** (-slope)
    c_samples = c_samples[np.isfinite(c_samples)]
    c = float(np.median(c_samples)) if c_samples.size else 0.0

    if target_mode == "vanilla_curve":
        # `have` must be measured the way the comparison is measured: on
        # all-land interior patches.  The whole-canvas spectrum above is
        # dominated by coastlines (a 4884-level step) and by the padding
        # ocean, and reading a deficit off it says "0.05 cycles/km is
        # already full" for a map whose interior carries 42 % of vanilla
        # there (docs/report_map_paint.md §6).
        patch_k, patch_amp, n_patches = _interior_patch_spectrum(
            h2, land, km_per_px, rng
        )
        if n_patches:
            have_rad = np.where(
                centres > 0,
                np.interp(centres, patch_k, patch_amp, left=np.nan, right=np.nan),
                np.nan,
            )
            fell_back = np.isnan(have_rad)
            have_rad = np.where(fell_back, amp_rad, have_rad)
        else:
            have_rad = amp_rad
        vk = np.array([p[0] for p in VANILLA_LAND_SPECTRUM], dtype=np.float64)
        va = np.array([p[1] for p in VANILLA_LAND_SPECTRUM], dtype=np.float64)
        with np.errstate(divide="ignore", invalid="ignore"):
            shape_rad = np.exp(
                np.interp(np.log(np.maximum(centres, 1e-9)), np.log(vk), np.log(va))
            )
        # vanilla's curve at face value, not rescaled to our own map.  Both
        # sheets are 16-bit at the same km per pixel with the same max level,
        # so the amplitudes are directly comparable -- and anchoring to our
        # own low band was tried and is wrong: our de-terraced base carries
        # 0.58x vanilla at 0.02 cycles/km, so the anchored target came out
        # 0.58x everywhere and the deficit at 0.05 collapsed to zero, leaving
        # that end of the band exactly as under-filled as before.  The
        # *absolute* level of the output is still set downstream by the
        # per-terrain gain against `DEFAULT_HF_TARGETS`; this only decides
        # the shape of the shortfall.
        anchor_scale = float(target_gain)
        target_rad = anchor_scale * shape_rad
        amp_rad = np.where(np.isfinite(have_rad), have_rad, amp_rad)
        spec_extra = {"interior_patches": n_patches}
    elif target_mode == "power_law":
        with np.errstate(divide="ignore"):
            target_rad = c * np.where(centres > 0, centres ** slope, 0.0)
        anchor_scale = c
        spec_extra = {"interior_patches": 0}
    else:
        raise ValueError(
            f"unknown heightmap_detail_target_mode {target_mode!r} "
            f"(expected 'vanilla_curve' or 'power_law')"
        )
    deficit_rad = np.sqrt(np.clip(target_rad ** 2 - amp_rad ** 2, 0, None))
    # §2d: the fill only owns the band the source cannot carry.  Below it the
    # shortfall against vanilla is Faerun's own macro relief, not a deficit,
    # and filling it is what put a 4,900-level trench beside Thay's cliffs.
    band_w = fill_band_weight(centres, fill_min_cycles_per_km)
    deficit_rad = deficit_rad * band_w
    deficit_rad[centres < KEEP_STRUCTURE_BELOW_KM] = 0.0

    if field is None:
        source = np.fft.rfft2(rng.standard_normal((H, W)).astype(np.float32))
        gain_rad = deficit_rad
    else:
        source = np.fft.rfft2(np.ascontiguousarray(field, dtype=np.float32))
        f_power = (np.abs(source) ** 2) / (H * W)
        f_rad, f_counts = _radial_average(f_power, k, bins)
        del f_power
        f_amp = np.sqrt(np.maximum(f_rad, 0.0))
        # divide the field's own radial amplitude out and multiply the target
        # in; the floor is only there so a bin the field never populated
        # cannot become a division by zero
        peak = float(f_amp[f_counts > 0].max()) if (f_counts > 0).any() else 0.0
        floor = max(peak * _EQUALISER_FLOOR_FRACTION, 1e-12)
        with np.errstate(divide="ignore", invalid="ignore"):
            gain_rad = deficit_rad / np.maximum(f_amp, floor)
        gain_rad = np.where(np.isfinite(gain_rad) & (f_counts > 0), gain_rad, 0.0)
        gain_rad[centres < KEEP_STRUCTURE_BELOW_KM] = 0.0

    # interpolate through populated bins only, so an empty bin's spurious
    # zero never creates a fake dip in the noise shape
    if has_data.any():
        shape = np.interp(
            k.ravel(), centres[has_data], gain_rad[has_data]
        ).astype(np.float32).reshape(k.shape)
    else:
        shape = np.zeros_like(k, dtype=np.float32)
    noise = np.fft.irfft2(source * shape, s=(H, W))
    del source
    s = float(noise[land].std()) if land.any() else float(noise.std())
    noise = (noise / max(s, 1e-9)).astype(np.float32)
    return noise, {
        "power_law_c": round(c, 1),
        "fit_band_bins": int(band.sum()),
        "target_mode": target_mode,
        "target_anchor_scale": round(anchor_scale, 4),
        "fill_min_cycles_per_km": round(float(fill_min_cycles_per_km), 4),
        "_deficit_curve": (centres.copy(), deficit_rad.copy()),
        **spec_extra,
    }


def _high_pass(a: np.ndarray, sigma_px: float) -> np.ndarray:
    return a - gaussian_filter(a, sigma_px, mode="nearest")


def _terrain_gain(
    hp_signal: np.ndarray,
    hp_noise: np.ndarray,
    land: np.ndarray,
    terrain_code: np.ndarray,
    terrain_keys: list[str],
    hf_targets: dict[str, float],
    blur_px: float,
) -> tuple[np.ndarray, list[dict]]:
    """Per-pixel noise gain so each terrain class hits its vanilla HF RMS.

    One shared high-pass residual for the whole canvas (``hp_signal``,
    ``hp_noise``, computed once by the caller) rather than one Gaussian
    filter per terrain class -- ~17 classes over a full canvas would
    otherwise mean ~17 redundant full-canvas Gaussian passes.
    """
    amp = np.zeros(hp_signal.shape, dtype=np.float32)
    default_target = hf_targets.get("plains", 90.0)
    rows: list[dict] = []
    for i, key in enumerate(terrain_keys):
        m = (terrain_code == i) & land
        n = int(m.sum())
        if n == 0:
            continue
        want = hf_targets.get(key, default_target)
        have = float(hp_signal[m].std())
        unit = float(hp_noise[m].std()) or 1.0
        need = max(want ** 2 - have ** 2, 0.0) ** 0.5
        amp[m] = need / unit
        rows.append({
            "terrain": key, "px": n,
            "vanilla_hf_rms": round(want, 1),
            "before_hf_rms": round(have, 1),
            "gain": round(need / unit, 1),
        })
    amp = gaussian_filter(amp, blur_px, mode="nearest")
    return amp, rows


# --------------------------------------------------------------------------- #
# pass 3 + 4
# --------------------------------------------------------------------------- #
def _limit_excursion(
    delta: np.ndarray,
    base: np.ndarray,
    floor: float,
    ceiling: float,
    land: np.ndarray,
    fraction: float = 1.0,
) -> tuple[np.ndarray, dict]:
    """Saturate the synthesised offset into the headroom the pixel really has.

    Without this the fill happily pushes a 7000-level lowland 4000 levels
    down and the closing ``np.clip`` puts it back on ``water_level + 1``:
    over the shipped build that flattened **8.19 % of all land** (2,166,924
    px, mean 3485 levels destroyed, median 113 km from any water --
    ``docs/evidence/report_map_paint/clamp_floor.csv``, lane ``relief-report``).
    A clamp is not a bound, it is a bug report after the fact.

    ``tanh`` rather than ``minimum``: a hard bound would print the shape of
    the floor into the map as a plateau, exactly the artefact being removed.
    Where ``|delta|`` is small against the headroom the saturation is the
    identity to first order, so nothing changes on real relief.

    ``fraction`` (§2d).  Saturating at the *whole* headroom still reaches
    the floor: ``tanh`` tends to 1, so a pixel whose fill is several times
    its headroom lands on ``water_level + 1`` exactly, and a run of them
    prints a flat trench.  That is where the moat survived on Thay after the
    other two fixes: the ground at the foot of a tall escarpment is low, so
    it has the least headroom on the map and gets the same fill as the
    plateau above it -- 4.2 % of Thay's land sat on the clamp floor.
    Saturating at ``fraction`` of the headroom instead keeps the last bit of
    room unused, so the fill fades out where the map runs out of range
    rather than clipping flat.
    """
    frac = max(float(fraction), 1e-3)
    down = np.maximum(base - floor, 0.0) * frac
    up = np.maximum(ceiling - base, 0.0) * frac
    room = np.where(delta < 0, down, up)
    del down, up
    out = np.sign(delta) * room * np.tanh(np.abs(delta) / np.maximum(room, 1.0))
    n_land = int(land.sum())
    over = int((np.abs(delta) > room)[land].sum()) if n_land else 0
    return out.astype(np.float32), {
        "excursion_limited_px": over,
        "excursion_limited_pct_of_land": (
            round(100.0 * over / n_land, 3) if n_land else 0.0
        ),
    }


def _class_field(
    terrain_code: np.ndarray,
    terrain_keys: list[str],
    classes: tuple[str, ...] | list[str],
    value: float,
    other: float,
    blur_px: float,
) -> np.ndarray:
    """``value`` on the listed terrain classes, ``other`` elsewhere, blurred.

    The blur is the one the amplitude field already uses: a hard per-class
    switch would print the province-terrain mosaic into the relief as a
    visible seam, and the terrain classes themselves are a majority vote per
    province, not a smooth field.
    """
    want = {c for c in classes}
    lut = np.array(
        [value if k in want else other for k in terrain_keys], dtype=np.float32
    )
    if lut.size == 0:
        return np.full(terrain_code.shape, other, dtype=np.float32)
    idx = np.clip(terrain_code.astype(np.int32), 0, lut.size - 1)
    out = lut[idx]
    if blur_px > 0:
        out = gaussian_filter(out, blur_px, mode="nearest")
    return out.astype(np.float32)


def _bound_to_source(
    out: np.ndarray,
    source: np.ndarray,
    land: np.ndarray,
    terrain_code: np.ndarray,
    terrain_keys: list[str],
    hf_targets: dict[str, float],
    *,
    window_px: int,
    sigmas: float,
    floor: float,
    ceiling: float,
) -> tuple[np.ndarray, dict]:
    """Hold the output inside the CK2 author's own surface, plus texture (§2f).

    ``source_local_min - tol <= out <= source_local_max + tol`` over a window
    of one CK2 source pixel, with ``tol`` the terrain class's own measured
    vanilla high-frequency amplitude times ``sigmas``
    (``docs/evidence/map_fidelity/hf_by_terrain.csv``: plains 86, hills 213,
    mountains 311 levels RMS).

    **Why a local min and not the source value.**  The window is one source
    pixel wide, so at a cliff it already spans both sides: the top of an
    escarpment is bounded below by the *foot* of it, and the bound costs a
    real cliff nothing.  On ground the author drew flat the two collapse
    together and the bound is exactly "texture, no holes".

    **Why toward the source and not to the water level.**  §2c(d)'s headroom
    limiter bounds the fill by the room between the pixel and the sea, which
    is the right bound for *not drowning* land and the wrong one for
    *not digging*: on a 20,000-level plateau it permits a 15,000-level pit.

    The approach is a ``tanh`` saturation over the last quarter of the
    tolerance rather than a hard clip, for the same reason ``_limit_excursion``
    saturates: a hard clip prints the bound's own shape into the map as a flat
    spot, which is the artefact being removed.  The bound is still exact --
    ``tanh`` tends to 1, so the output never leaves the interval.

    The hit fraction is reported, not swallowed: this is a backstop, and if it
    binds on more than a fraction of a percent of land the passes in front of
    it are writing terrain the source has no basis for.
    """
    if sigmas <= 0 or window_px < 1:
        return out, {"bound_limited_px": 0, "bound_limited_pct_of_land": 0.0}
    default_target = hf_targets.get("plains", 90.0)
    lut = np.array(
        [float(hf_targets.get(k, default_target)) * float(sigmas)
         for k in terrain_keys],
        dtype=np.float32,
    )
    if lut.size == 0:
        lut = np.array([default_target * float(sigmas)], dtype=np.float32)
    tol_band = lut[np.clip(terrain_code.astype(np.int32), 0, lut.size - 1)]
    src = source.astype(np.float32)
    lo = np.maximum(
        grey_erosion(src, size=window_px, mode="nearest") - tol_band, floor)
    hi = np.minimum(
        grey_dilation(src, size=window_px, mode="nearest") + tol_band, ceiling)
    # keep the interval non-empty even where the floor/ceiling squeeze it
    hi = np.maximum(hi, lo)
    # The saturation band is a fraction of the *tolerance*, not of the whole
    # interval: the interval is as tall as the local relief, so a fraction of
    # it would squash perfectly legal terrain (measured: a 20,000-level
    # plateau beside a lake came out at 19,186).  Half the interval is the cap
    # for the rare pixel whose floor and ceiling nearly meet.
    soft = np.minimum(_BOUND_SOFT_FRACTION * tol_band, 0.5 * (hi - lo))
    soft = np.maximum(soft, 1.0)
    mid_lo = lo + soft
    mid_hi = hi - soft
    res = out.astype(np.float32)
    under = res < mid_lo
    over = res > mid_hi
    res = np.where(
        under, mid_lo - soft * np.tanh((mid_lo - res) / soft), res)
    res = np.where(
        over, mid_hi + soft * np.tanh((res - mid_hi) / soft), res)
    # "hit" means the saturation actually moved the pixel, not merely that it
    # entered the soft band: the band starts a quarter of a tolerance from
    # each end, so counting entries overstates the backstop's work by an
    # order of magnitude (15.0 % of Faerun's land merely entered it).
    moved = (np.abs(res - out.astype(np.float32)) > 1.0) & land
    n_land = int(land.sum())
    # how far outside the *hard* interval the unbounded field wanted to go
    excess = np.maximum(lo - out.astype(np.float32), 0.0)
    exc = excess[land] if n_land else np.empty(0, dtype=np.float32)
    return np.where(land, res, out).astype(np.float32), {
        "bound_limited_px": int(moved.sum()),
        "bound_limited_pct_of_land": (
            round(100.0 * float(moved.sum()) / n_land, 3) if n_land else 0.0
        ),
        "bound_excess_below_p99": (
            round(float(np.percentile(exc, 99)), 1) if exc.size else 0.0
        ),
        "bound_excess_below_max": (
            round(float(exc.max()), 1) if exc.size else 0.0
        ),
    }


def _carve_rivers(
    out: np.ndarray,
    land: np.ndarray,
    river_body: np.ndarray,
    river_width_index: np.ndarray,
    depth: float,
) -> np.ndarray:
    """Gaussian cross-section valley along the traced river body pixels.

    Subtracted on land only, so a river never raises a pixel above its
    neighbours -- it can only cut a valley into what pass 1+2 already built.
    """
    if not river_body.any():
        return out
    dist = distance_transform_edt(~river_body).astype(np.float32)
    width_px = np.zeros(river_body.shape, dtype=np.float32)
    width_px[river_body] = (
        _RIVER_WIDTH_BASE_PX
        + (11.0 - river_width_index[river_body]) * _RIVER_WIDTH_PER_INDEX
    )
    wsp = gaussian_filter(width_px, _RIVER_BLUR_PX, mode="nearest") + _RIVER_MARGIN_PX
    valley = depth * np.exp(-((dist / wsp) ** 2))
    return out - valley * land


def _smooth_coast(
    out: np.ndarray,
    reference: np.ndarray,
    land: np.ndarray,
    smooth_px: float,
    mode: str = "damp_detail",
    water_level: float = 0.0,
) -> np.ndarray:
    """Damp the *synthesised detail* over the first few land pixels of a shore.

    The pass's job is that a beach does not gain mountain-scale noise at the
    waterline, and damping the offset is all of that job.

    **It used to contract the height itself toward the water level**
    (``water_level + (out - water_level) * factor``, factor 0.45 at the
    shoreline), and that is what playtest 4 saw as "Thay's pits are even
    larger" (docs/step_map_heightmap.md §2f).  Faerun's CK2 lakes and river
    provinces sit *on high ground* -- the median such pixel in the Thay crop
    is at 14,301 -- and the heightmap owes CK3 a water pixel at or below the
    4883 water level, so each one is already a hole in the plateau.  The old
    coast pass then pulled the ring of land around it 55 % of the way down to
    the water level as well, which on a 20,000-level plateau is an
    8,000-level crater.  Measured on the Thay window: the 8.4 % of land
    within 5 px of a water province carried pit p95 **4086** and max 8141
    levels against the plateau interior's 290 (`verified`,
    `docs/evidence/relief_pits/pits_zones_both.csv`).

    Damping the offset instead leaves the shore at the height the CK2 author
    drew, so the drop into a lake happens in the one pixel where the lake
    starts -- which is what a lake shore is -- and the §2f source bound then
    holds at a coast with no exemption.
    """
    if mode == "damp_detail":
        toward = reference
    elif mode == "blend_to_water":
        toward = np.float32(water_level)
    else:
        raise ValueError(
            f"unknown heightmap_detail_coast_mode {mode!r} "
            f"(expected 'damp_detail' or 'blend_to_water')"
        )
    d_sea = distance_transform_edt(land).astype(np.float32)
    coast = np.clip(d_sea / max(smooth_px, 1e-6), 0, 1)
    factor = _COAST_MIN_FACTOR + (1.0 - _COAST_MIN_FACTOR) * coast
    return np.where(land, toward + (out - toward) * factor, out)


# --------------------------------------------------------------------------- #
# the interior-patch spectrum the fill target is read against
# --------------------------------------------------------------------------- #
#: geometry of the all-land patches `have` is measured on.  Identical to
#: `scripts/report_map_paint_plots.py` and `scripts/heightmap_erosion_evidence.py`,
#: so the number the pass aims at and the number the evidence reports are the
#: same measurement: 256 px (380 km on our canvas), 48 of them, 100 % land.
_PATCH_PX = 256
_PATCH_COUNT = 48
_PATCH_TRIES = 4000
#: the all-land test is run on this stride first -- a full `.all()` over 65k
#: booleans per candidate would dominate the pass on a canvas this size
_PATCH_STRIDE = 8


def _interior_patch_spectrum(
    h2: np.ndarray, land: np.ndarray, km_per_px: float,
    rng: np.random.Generator,
) -> tuple[np.ndarray, np.ndarray, int]:
    """Mean radial amplitude over all-land patches: ``(cycles/km, levels, n)``.

    An empty result (no all-land patch fits, which is the case for every
    synthetic fixture and for a map with no interior) is the caller's signal
    to fall back to the whole-canvas spectrum.
    """
    H, W = h2.shape
    n = _PATCH_PX
    if H <= n or W <= n:
        return np.empty(0), np.empty(0), 0
    small = land[::_PATCH_STRIDE, ::_PATCH_STRIDE]
    step = n // _PATCH_STRIDE
    origins: list[tuple[int, int]] = []
    tries = 0
    while len(origins) < _PATCH_COUNT and tries < _PATCH_TRIES:
        tries += 1
        y = int(rng.integers(0, H - n))
        x = int(rng.integers(0, W - n))
        ys, xs = y // _PATCH_STRIDE, x // _PATCH_STRIDE
        if not small[ys:ys + step, xs:xs + step].all():
            continue
        if land[y:y + n, x:x + n].all():
            origins.append((y, x))
    if not origins:
        return np.empty(0), np.empty(0), 0

    win = np.hanning(n).astype(np.float32)
    win2 = win[:, None] * win[None, :]
    yy, xx = np.mgrid[0:n, 0:n]
    r = np.hypot(yy - n // 2, xx - n // 2).astype(int)
    counts = np.maximum(np.bincount(r.ravel(), minlength=n)[: n // 2], 1)
    acc = np.zeros(n // 2, dtype=np.float64)
    for (y, x) in origins:
        w = h2[y:y + n, x:x + n].astype(np.float64)
        w = (w - w.mean()) * win2
        p = (np.abs(np.fft.fftshift(np.fft.fft2(w))) ** 2) / (n * n)
        prof = np.bincount(r.ravel(), weights=p.ravel(), minlength=n)[: n // 2]
        acc += np.sqrt(prof / counts)
    return (np.arange(n // 2)[1:] / n / km_per_px,
            (acc / len(origins))[1:], len(origins))


#: band the absolute amplitude of the fill is matched in, cycles/km.  The one
#: the goal names and the one docs/report_map_paint.md §6 reports.
MATCH_BAND_MIN_KM = 0.05
MATCH_BAND_MAX_KM = 0.30


def _match_deficit_amplitude(
    noise: np.ndarray,
    land: np.ndarray,
    km_per_px: float,
    deficit_curve: tuple[np.ndarray, np.ndarray],
    rng: np.random.Generator,
) -> tuple[float, dict]:
    """Scalar that puts ``noise`` on the deficit's own absolute amplitude.

    Measured, not derived: the shaped field's radial amplitude is read with
    :func:`_interior_patch_spectrum` -- the same operator the deficit itself
    was read with -- and the median ratio over 0.05-0.3 cycles/km is the
    scale.  Deriving it from the FFT normalisation instead would be exact
    only if nothing downstream touched the field, and the terrain envelope,
    the river carve and the headroom limiter all do.
    """
    centres, deficit_rad = deficit_curve
    nk, na, n_patches = _interior_patch_spectrum(noise, land, km_per_px, rng)
    if not n_patches:
        return 1.0, {"deficit_scale": 1.0, "deficit_match_bins": 0}
    want = np.interp(nk, centres, deficit_rad, left=0.0, right=0.0)
    band = (nk >= MATCH_BAND_MIN_KM) & (nk <= MATCH_BAND_MAX_KM) & (na > 0) & (want > 0)
    if not band.any():
        return 1.0, {"deficit_scale": 1.0, "deficit_match_bins": 0}
    scale = float(np.median(want[band] / na[band]))
    return scale, {"deficit_scale": round(scale, 4),
                   "deficit_match_bins": int(band.sum())}


def _relative_terrain_gain(
    shape: tuple[int, int],
    land: np.ndarray,
    terrain_code: np.ndarray,
    terrain_keys: list[str],
    hf_targets: dict[str, float],
    blur_px: float,
) -> tuple[np.ndarray, list[dict]]:
    """Vanilla's per-terrain table as a modulation whose land mean is 1.

    Keeps the whole point of the table -- desert_mountains 4.6x taiga -- while
    leaving the absolute level to the spectral match, so the two calibrations
    cannot cancel each other out.
    """
    amp = np.zeros(shape, dtype=np.float32)
    default_target = hf_targets.get("plains", 90.0)
    rows: list[dict] = []
    total_px = 0
    weighted = 0.0
    for i, key in enumerate(terrain_keys):
        n = int(((terrain_code == i) & land).sum())
        if n:
            total_px += n
            weighted += n * hf_targets.get(key, default_target)
    mean_target = weighted / total_px if total_px else default_target
    for i, key in enumerate(terrain_keys):
        m = (terrain_code == i) & land
        n = int(m.sum())
        if n == 0:
            continue
        want = hf_targets.get(key, default_target)
        amp[m] = want / max(mean_target, 1e-6)
        rows.append({"terrain": key, "px": n,
                     "vanilla_hf_rms": round(want, 1),
                     "gain": round(want / max(mean_target, 1e-6), 3)})
    amp = gaussian_filter(amp, blur_px, mode="nearest")
    return amp, rows
