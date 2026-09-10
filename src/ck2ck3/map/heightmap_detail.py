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
4. **coast smoothing** — the first few pixels of land are blended toward the
   water level so beaches stay flat instead of gaining mountain-scale noise
   right at the shore.

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
* deterministic: the same inputs and the same ``HeightmapDetailConfig.seed``
  always produce the same output array.
"""

from __future__ import annotations

import time

import numpy as np
from scipy.ndimage import distance_transform_edt, gaussian_filter

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
        field, relief_diag = erosion.eroded_relief(
            h2, land, rng,
            seed_amplitude=cfg.erosion_seed_amplitude,
            iterations=cfg.erosion_iterations,
            accum_iterations=cfg.erosion_accum_iterations,
            mfd_exponent=cfg.erosion_mfd_exponent,
            incision=cfg.erosion_incision,
            diffusion=cfg.erosion_diffusion,
        )
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
        delta, h2, float(water_level) + 1.0, float(max_level), land
    )
    out = h2 + delta
    del h2, delta

    # 4. coast smoothing -----------------------------------------------------
    out = _smooth_coast(out, land, float(water_level), cfg.coast_smooth_px)

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
        "deterrace_mode": cfg.deterrace_mode,
        "relief_mode": cfg.relief_mode,
        "power_law_c": spec_diag["power_law_c"],
        "fit_band_bins": spec_diag["fit_band_bins"],
        "elapsed_s": round(time.time() - t0, 1),
        "terrain_gain": gain_rows,
    }
    for key in ("erosion_iterations", "erosion_accum_iterations",
                "erosion_uplift_levels", "erosion_field_rms_levels",
                "target_mode", "target_anchor_scale",
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


def _spectral_deficit_noise(
    h2: np.ndarray,
    land: np.ndarray,
    km_per_px: float,
    slope: float,
    rng: np.random.Generator,
    field: np.ndarray | None = None,
    target_mode: str = "vanilla_curve",
    target_gain: float = 1.0,
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
    """
    down = np.maximum(base - floor, 0.0)
    up = np.maximum(ceiling - base, 0.0)
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
    out: np.ndarray, land: np.ndarray, water_level: float, smooth_px: float
) -> np.ndarray:
    """Blend the first few land pixels toward the water level so beaches stay flat."""
    d_sea = distance_transform_edt(land).astype(np.float32)
    coast = np.clip(d_sea / max(smooth_px, 1e-6), 0, 1)
    factor = _COAST_MIN_FACTOR + (1.0 - _COAST_MIN_FACTOR) * coast
    return np.where(land, water_level + (out - water_level) * factor, out)


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
