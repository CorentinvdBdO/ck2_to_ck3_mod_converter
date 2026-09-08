"""Deterministic detail synthesis for the CK3 16-bit heightmap.

The plain rescaled heightmap (``heightmap.py``) is faithful but flat: an
8-bit CK2 source through a linear transfer curve leaves land with only ~160
distinct levels 277 apart, which reads as terraced contour lines rather than
terrain (``docs/map_fidelity.md`` §1.2, 212 distinct values against vanilla's
31,516). Prototyped on the Sword Coast in
``scripts/prototype_heightmap_detail.py``; this module is the same four
passes, vectorised for the whole canvas (``docs/map_fidelity.md`` §4.2):

1. **de-terrace** — a small Gaussian on land only removes the transfer
   curve's risers. Legitimate because the real signal is band-limited to the
   CK2 source's own Nyquist frequency anyway, so nothing true is lost.
2. **spectral fill** — vanilla's land elevation is a clean power law,
   amplitude ~ f^slope. This pass fits that law to the heightmap's own
   well-resolved low frequencies, injects noise shaped to exactly the
   per-frequency shortfall, and scales it per pixel so each CK3 terrain class
   (mountains, plains, ...) hits its own measured high-frequency amplitude
   (``DEFAULT_HF_TARGETS``, from vanilla). Frequencies below
   ``KEEP_STRUCTURE_BELOW_KM`` are never touched, so real large-scale
   structure (the CK2 source's own mountains and valleys) survives untouched.
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
#: number of radial frequency bins for the power-spectrum fit
_N_RADIAL_BINS = 2048

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
    smooth = gaussian_filter(h0, cfg.deterrace_sigma_px, mode="nearest")
    h2 = np.where(land, smooth, h0)
    del smooth

    # 2. spectral fill, amplitude per CK3 terrain class ------------------
    noise, spec_diag = _spectral_deficit_noise(
        h2, land, km_per_px, cfg.spectral_slope, rng
    )
    sigma_px = HF_SIGMA_KM / km_per_px
    hp_signal = _high_pass(h2, sigma_px)
    hp_noise = _high_pass(noise, sigma_px)
    amp, gain_rows = _terrain_gain(
        hp_signal, hp_noise, land, terrain_code, terrain_keys,
        cfg.hf_targets, cfg.gain_blur_px,
    )
    del hp_signal, hp_noise
    out = h2 + amp * noise
    del h2, amp, noise

    # 3. river valleys -----------------------------------------------------
    out = _carve_rivers(out, land, river_body, river_width_index, cfg.river_depth)

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
        "power_law_c": spec_diag["power_law_c"],
        "fit_band_bins": spec_diag["fit_band_bins"],
        "elapsed_s": round(time.time() - t0, 1),
        "terrain_gain": gain_rows,
    }
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
) -> tuple[np.ndarray, dict]:
    """Unit-scaled noise field shaped to the shortfall against vanilla's law.

    Water is replaced by the land mean before the FFT (not left at the true,
    much lower, water level): otherwise every coastline is a step of
    thousands of 16-bit levels and the spectrum is dominated by coastline
    edges instead of terrain, which is exactly the artefact this pass exists
    to remove.
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

    with np.errstate(divide="ignore"):
        target_rad = c * np.where(centres > 0, centres ** slope, 0.0)
    deficit_rad = np.sqrt(np.clip(target_rad ** 2 - amp_rad ** 2, 0, None))
    deficit_rad[centres < KEEP_STRUCTURE_BELOW_KM] = 0.0

    # interpolate through populated bins only, so an empty bin's spurious
    # zero never creates a fake dip in the noise shape
    if has_data.any():
        shape = np.interp(
            k.ravel(), centres[has_data], deficit_rad[has_data]
        ).astype(np.float32).reshape(k.shape)
    else:
        shape = np.zeros_like(k, dtype=np.float32)
    white = rng.standard_normal((H, W)).astype(np.float32)
    noise = np.fft.irfft2(np.fft.rfft2(white) * shape, s=(H, W))
    s = float(noise[land].std()) if land.any() else float(noise.std())
    noise = (noise / max(s, 1e-9)).astype(np.float32)
    return noise, {"power_law_c": round(c, 1), "fit_band_bins": int(band.sum())}


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
