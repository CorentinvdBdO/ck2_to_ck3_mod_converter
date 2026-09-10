"""Config for the physical-map step, loaded from a TOML file.

Everything mod-specific lives in the TOML; nothing is hardcoded in the code
path.  See ``configs/faerun_map.toml`` for the documented reference file.
"""

from __future__ import annotations

import math
import tomllib
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class ScaleConfig:
    """How many CK3 pixels one CK2 pixel becomes.

    ``factor`` is derived, not chosen: it is the ratio of the two maps'
    km-per-pixel, so 10 km in Faerûn spans the same number of pixels as 10 km
    in vanilla CK3.  See ``docs/map_scale.md`` for the measurements.
    """

    #: km per pixel of the vanilla CK3 1.19 map (9216x4608)
    vanilla_km_per_px: float
    #: km per pixel of the source CK2 map
    source_km_per_px: float
    #: set to override the derived factor (for experiments / regression runs)
    factor_override: float | None = None
    #: sea border added on every side, in *target* pixels, before rounding
    sea_margin_px: int = 64
    #: canvas width/height are rounded up to a multiple of this
    canvas_multiple: int = 64
    #: hard cap; a factor that would exceed this aborts the run
    max_canvas_px: int = 32768

    @property
    def factor(self) -> float:
        if self.factor_override is not None:
            return self.factor_override
        return self.source_km_per_px / self.vanilla_km_per_px


@dataclass(frozen=True)
class Canvas:
    """Target ``map_data`` geometry, including which part of the source is used.

    ``crop_*`` is the rectangle of the CK2 bitmap that gets scaled onto the
    canvas (half-open, top-left origin).  Default is the whole bitmap; a
    smaller rectangle is how the converter throws away unpainted source border
    instead of paying for it in every output file (``docs/map_scale.md`` §7).
    """

    width: int
    height: int
    #: scaled source size (before padding)
    scaled_width: int
    scaled_height: int
    #: where the scaled source is pasted (top-left, target pixels)
    offset_x: int
    offset_y: int
    factor: float
    #: source rectangle that is scaled onto the canvas (half-open)
    crop_x0: int = 0
    crop_y0: int = 0
    crop_x1: int = 0
    crop_y1: int = 0

    @property
    def crop_width(self) -> int:
        return self.crop_x1 - self.crop_x0

    @property
    def crop_height(self) -> int:
        return self.crop_y1 - self.crop_y0

    @property
    def is_cropped(self) -> bool:
        return (self.crop_x0, self.crop_y0) != (0, 0) or self.crop_x1 == 0

    def to_target(self, x: float, y: float) -> tuple[int, int]:
        """CK2 pixel (top-left origin) -> target pixel.

        A source pixel outside the crop maps outside the canvas; callers that
        can be handed one (rivers, positions) already bounds-check.
        """
        return (
            int(round((x - self.crop_x0) * self.factor)) + self.offset_x,
            int(round((y - self.crop_y0) * self.factor)) + self.offset_y,
        )


def plan_canvas(
    src_w: int,
    src_h: int,
    scale: ScaleConfig,
    crop: tuple[int, int, int, int] | None = None,
) -> Canvas:
    """Smallest canvas that fits the scaled source plus a sea margin.

    Rounded up to ``canvas_multiple`` on both axes and the source is centred in
    the slack, so the margin is never smaller than requested on any side.

    ``crop`` is ``(x0, y0, x1, y1)`` in source pixels, half-open: only that
    rectangle is scaled onto the canvas.  Pass the bounding box of the source's
    *painted* pixels to stop unpainted border from becoming padding ocean.
    """
    factor = scale.factor
    if factor <= 0:
        raise ValueError(f"scale factor must be positive, got {factor}")
    x0, y0, x1, y1 = crop or (0, 0, src_w, src_h)
    if not (0 <= x0 < x1 <= src_w and 0 <= y0 < y1 <= src_h):
        raise ValueError(
            f"crop {(x0, y0, x1, y1)} is not inside the {src_w}x{src_h} source"
        )
    sw = int(math.ceil((x1 - x0) * factor))
    sh = int(math.ceil((y1 - y0) * factor))
    m = scale.canvas_multiple
    if m <= 0:
        raise ValueError(f"canvas_multiple must be positive, got {m}")
    w = _round_up(sw + 2 * scale.sea_margin_px, m)
    h = _round_up(sh + 2 * scale.sea_margin_px, m)
    if max(w, h) > scale.max_canvas_px:
        raise ValueError(
            f"canvas {w}x{h} exceeds max_canvas_px={scale.max_canvas_px}; "
            f"factor={factor:.4f} is too large for a playable map"
        )
    return Canvas(
        width=w,
        height=h,
        scaled_width=sw,
        scaled_height=sh,
        offset_x=(w - sw) // 2,
        offset_y=(h - sh) // 2,
        factor=factor,
        crop_x0=x0,
        crop_y0=y0,
        crop_x1=x1,
        crop_y1=y1,
    )


def _round_up(value: int, multiple: int) -> int:
    return ((value + multiple - 1) // multiple) * multiple


@dataclass(frozen=True)
class HeightmapConfig:
    #: 1 = same size as provinces.png (Elder Kings 2, Godherja); 2 = vanilla
    resolution_factor: int = 1
    #: CK2 topology.bmp 8-bit value of the water surface
    ck2_sea_level: int = 95
    #: CK3 heightmap.png 16-bit value of the water surface
    ck3_water_level: int = 0
    #: CK3 16-bit value the CK2 max altitude maps to
    ck3_max_level: int = 65535
    #: extra control points (ck2_8bit, ck3_16bit), sorted, applied on top
    curve: list[tuple[int, int]] = field(default_factory=list)
    #: tile_size written into heightmap.heightmap
    tile_size: int = 33
    #: push the open sea to `sea_floor`, keeping a `sea_shelf_px` coastal ramp.
    #: CK2 has almost no bathymetry and CK3 paints shallow water as sand
    #: (docs/step_map_heightmap.md); vanilla's own sea floor is a flat 0.
    deepen_sea: bool = True
    #: pixels of coastal ramp between the water surface and `sea_floor`
    sea_shelf_px: int = 24
    #: 16-bit height of the open-sea floor (vanilla: 0)
    sea_floor: int = 0


#: vanilla per-CK3-terrain high-frequency RMS (16-bit levels, land only),
#: measured off the real 1.19 heightmap: scripts/map_fidelity_heightmap.py ->
#: docs/evidence/map_fidelity/hf_by_terrain.csv, quoted in docs/map_fidelity.md
#: §1.2. Baked in so a normal conversion run has no runtime dependency on a
#: research evidence file; override with `heightmap_detail_hf_targets` in
#: `[map]` (an inline TOML table) to load a different one.
DEFAULT_HF_TARGETS: dict[str, float] = {
    "desert": 91.2,
    "desert_mountains": 322.6,
    "drylands": 96.9,
    "farmlands": 96.7,
    "floodplains": 106.0,
    "forest": 110.7,
    "hills": 213.3,
    "jungle": 120.7,
    "mountains": 311.4,
    "oasis": 121.8,
    "plains": 86.3,
    "steppe": 97.2,
    "taiga": 70.1,
    "terraced_hills": 253.2,
    "wetlands": 70.4,
}


@dataclass(frozen=True)
class HeightmapDetailConfig:
    """``[map]`` flat keys ``heightmap_detail*`` -- vanilla-matched detail
    synthesis on the rescaled heightmap (``docs/map_fidelity.md`` §4.2,
    prototyped in ``scripts/prototype_heightmap_detail.py``).

    Flat under ``[map]``, like the ``scale`` keys above: a TOML table named
    ``heightmap_detail`` would collide with the boolean flag of that name.

    Off by default: the plain rescaled heightmap (``heightmap.py``) still
    boots a playable, coastline-correct map on its own; this only fixes how
    it looks.
    """

    enabled: bool = False
    #: deterministic RNG seed for the synthetic noise field
    seed: int = 1357
    #: pass 1 (de-terrace): Gaussian sigma, canvas px.  Under
    #: ``deterrace_mode = "cliff_aware"`` this is still the blur the pass
    #: achieves in a flat region, so the two modes are comparable -- but the
    #: right value is not the same, because the cliff-aware filter does not
    #: pay for its blur in cliff amplitude.  2.2 for cliff_aware (removes
    #: 64 % of the one-step riser against the Gaussian's 47 %, and *raises*
    #: cliff survival from 0.60 to 1.13); set it back to 1.6 alongside
    #: ``deterrace_mode = "gaussian"`` to reproduce the shipped build.
    deterrace_sigma_px: float = 2.2
    #: pass 1 mode.  ``"cliff_aware"`` (default) is Perona-Malik anisotropic
    #: diffusion: it removes the transfer curve's one-step risers but keeps a
    #: real multi-step cliff.  ``"gaussian"`` is the original blind blur,
    #: which destroys 31 % of the multi-step cliff amplitude on Thay and the
    #: Spine of the World (docs/step_map_heightmap.md §2b).
    deterrace_mode: str = "cliff_aware"
    #: pass 1: the flux half-width, 16-bit levels.  The transfer curve steps
    #: by 277 levels per 8-bit source value, so 1.5 x 277 sits between one
    #: quantisation riser and two -- exactly the discrimination wanted.
    cliff_step_levels: float = 415.5
    #: pass 2 (spectral fill): vanilla's land elevation spectrum is
    #: amplitude ~ f**slope.  Only read when ``target_mode = "power_law"``.
    spectral_slope: float = -2.0
    #: pass 2 fill target.  ``"vanilla_curve"`` (default) uses vanilla's own
    #: measured radial land spectrum, anchored to our map in the band where
    #: the two already agree; ``"power_law"`` is the original single fitted
    #: ``f**spectral_slope``, which over-fills 0.03-0.1 cycles/km and
    #: under-fills above 0.08 (docs/step_map_heightmap.md §2c).
    target_mode: str = "vanilla_curve"
    #: pass 2: multiplier on vanilla's own curve before the shortfall is
    #: taken.  1.0 = aim at vanilla's measured absolute amplitude (both
    #: sheets are 16-bit at the same km per pixel).  Only read by
    #: ``target_mode = "vanilla_curve"``.
    target_gain: float = 1.0
    #: pass 2 amplitude authority.  ``"deficit"`` (default) puts the fill on
    #: the measured per-frequency shortfall and applies the per-terrain table
    #: as a relative modulation around 1; ``"hf_target"`` is the original
    #: rule, one scalar per class from ``sqrt(want**2 - have**2)`` on a 3 km
    #: high-pass -- which a cliff-aware de-terrace starves, because the edges
    #: it keeps count as detail already present
    #: (docs/step_map_heightmap.md §2c).
    gain_mode: str = "deficit"
    #: pass 2, ``gain_mode = "deficit"`` only: empirical correction on the
    #: matched scale.  The match is made on the shaped field, but three
    #: things touch it afterwards -- the per-terrain envelope (a spatial
    #: multiply, which convolves the spectrum), the river carve and the
    #: headroom ``tanh`` (a nonlinearity) -- and together they leave the
    #: finished map above the target.  0.70 is measured, not derived: it is
    #: what brings 0.05-0.2 cycles/km inside +-30 % of vanilla on interior
    #: patches (docs/step_map_heightmap.md §2c).
    fill_gain: float = 0.70
    #: pass 2: Gaussian blur (canvas px) on the per-pixel noise-gain field, so
    #: terrain-class borders leave no amplitude seam
    gain_blur_px: float = 6.0
    #: pass 2: per-CK3-terrain target high-frequency RMS (16-bit levels); a
    #: terrain key missing from this table falls back to its "plains" entry
    hf_targets: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_HF_TARGETS))
    #: pass 2 relief source.  ``"eroded"`` (default) runs a short
    #: landscape-evolution model -- flow accumulation, stream-power incision,
    #: hillslope diffusion -- so valleys drain and ridges connect;
    #: ``"isotropic"`` is the original white noise, which has the right
    #: amplitude and spectrum and the wrong shape
    #: (docs/step_map_heightmap.md §2c).
    relief_mode: str = "eroded"
    #: pass 2 (eroded): landscape-evolution steps
    erosion_iterations: int = 16
    #: pass 2 (eroded): flow-accumulation relaxation passes per step.  The
    #: catchment is carried between steps, so the propagation distance is
    #: the product of the two.
    erosion_accum_iterations: int = 3
    #: pass 2 (eroded): initial fractal relief, 16-bit levels RMS.  Only the
    #: shape of the result is used (it is renormalised), so this sets how
    #: much there is for the erosion to cut into, not the output amplitude.
    erosion_seed_amplitude: float = 300.0
    #: pass 2 (eroded): multiple-flow-direction slope exponent.  Higher
    #: concentrates flow into fewer, sharper channels.
    erosion_mfd_exponent: float = 4.0
    #: pass 2 (eroded): stream-power coefficient K in ``dz = -K (A/Aref)^m S``
    erosion_incision: float = 0.5
    #: pass 2 (eroded): hillslope linear-diffusion coefficient per step
    erosion_diffusion: float = 0.06
    #: pass 2 (eroded): ceiling on the slope the stream-power law may see,
    #: in quantisation steps (277 levels) per pixel.  0 disables the cap and
    #: reproduces build 13, whose incision planed Thay's plateau rims by
    #: thousands of levels because ``S`` there is the *macro* escarpment
    #: (up to 4,505 levels/px against a land median of 128) --
    #: docs/step_map_heightmap.md §2d.
    erosion_slope_ceiling_steps: float = 1.0
    #: pass 2: the frequency (cycles/km) at which the spectral fill reaches
    #: full strength, with a one-octave raised-cosine roll-on below it.
    #: 0 restores the pre-2026-09-10 behaviour (fill everything above
    #: ``KEEP_STRUCTURE_BELOW_KM`` = 0.01 cycles/km), which fabricated
    #: 35-60 km relief on top of the CK2 author's own and put a 4,900-level
    #: mean trench beside Thay's escarpments -- the "plateaux dipping then
    #: coming back up" of playtest 3 (docs/step_map_heightmap.md §2d).
    #: 0.05 cycles/km = 20 km: below that the CK2 source is fully resolved
    #: (its own Nyquist is 0.172 cycles/km) and only quantised, and a
    #: quantiser adds broadband noise rather than removing macro relief, so
    #: a shortfall there is Faerun's content and not ours to invent.
    fill_min_cycles_per_km: float = 0.05
    #: pass 2/3b: the fraction of each pixel's own headroom the synthesised
    #: offset is allowed to saturate into.  1.0 is the pre-2026-09-10
    #: behaviour and still reaches the ``water_level + 1`` floor exactly,
    #: because ``tanh`` tends to 1: on Thay that pinned 4.2 % of the land
    #: flat at the foot of the escarpments, which is a moat
    #: (docs/step_map_heightmap.md §2d).  0.5 keeps the last half of the
    #: range unused so the fill fades instead of clipping.
    headroom_fraction: float = 0.5
    #: pass 3 (river valleys): depth in 16-bit levels at the centreline
    river_depth: float = 900.0
    #: pass 4 (coast smoothing): land within this many canvas px of the coast
    #: is blended toward the water level so beaches stay flat
    coast_smooth_px: float = 4.0


def heightmap_detail_config(raw: dict) -> HeightmapDetailConfig:
    """Build a :class:`HeightmapDetailConfig` from the flat ``[map]`` keys."""
    d = HeightmapDetailConfig()
    hf_raw = raw.get("heightmap_detail_hf_targets")
    hf_targets = (
        {str(k): float(v) for k, v in hf_raw.items()} if hf_raw else dict(d.hf_targets)
    )
    return HeightmapDetailConfig(
        enabled=bool(raw.get("heightmap_detail", d.enabled)),
        seed=int(raw.get("heightmap_detail_seed", d.seed)),
        deterrace_sigma_px=float(
            raw.get("heightmap_detail_deterrace_sigma_px", d.deterrace_sigma_px)
        ),
        deterrace_mode=str(
            raw.get("heightmap_detail_deterrace_mode", d.deterrace_mode)
        ),
        cliff_step_levels=float(
            raw.get("heightmap_detail_cliff_step_levels", d.cliff_step_levels)
        ),
        spectral_slope=float(
            raw.get("heightmap_detail_spectral_slope", d.spectral_slope)
        ),
        target_mode=str(raw.get("heightmap_detail_target_mode", d.target_mode)),
        target_gain=float(raw.get("heightmap_detail_target_gain", d.target_gain)),
        gain_mode=str(raw.get("heightmap_detail_gain_mode", d.gain_mode)),
        fill_gain=float(raw.get("heightmap_detail_fill_gain", d.fill_gain)),
        gain_blur_px=float(raw.get("heightmap_detail_gain_blur_px", d.gain_blur_px)),
        hf_targets=hf_targets,
        relief_mode=str(raw.get("heightmap_detail_relief_mode", d.relief_mode)),
        erosion_iterations=int(
            raw.get("heightmap_detail_erosion_iterations", d.erosion_iterations)
        ),
        erosion_accum_iterations=int(
            raw.get("heightmap_detail_erosion_accum_iterations",
                    d.erosion_accum_iterations)
        ),
        erosion_seed_amplitude=float(
            raw.get("heightmap_detail_erosion_seed_amplitude",
                    d.erosion_seed_amplitude)
        ),
        erosion_mfd_exponent=float(
            raw.get("heightmap_detail_erosion_mfd_exponent", d.erosion_mfd_exponent)
        ),
        erosion_incision=float(
            raw.get("heightmap_detail_erosion_incision", d.erosion_incision)
        ),
        erosion_diffusion=float(
            raw.get("heightmap_detail_erosion_diffusion", d.erosion_diffusion)
        ),
        erosion_slope_ceiling_steps=float(
            raw.get("heightmap_detail_erosion_slope_ceiling_steps",
                    d.erosion_slope_ceiling_steps)
        ),
        fill_min_cycles_per_km=float(
            raw.get("heightmap_detail_fill_min_cycles_per_km",
                    d.fill_min_cycles_per_km)
        ),
        headroom_fraction=float(
            raw.get("heightmap_detail_headroom_fraction", d.headroom_fraction)
        ),
        river_depth=float(raw.get("heightmap_detail_river_depth", d.river_depth)),
        coast_smooth_px=float(
            raw.get("heightmap_detail_coast_smooth_px", d.coast_smooth_px)
        ),
    )


def _heightmap_detail_from_table(hmd: dict) -> HeightmapDetailConfig:
    """Same fields as :func:`heightmap_detail_config`, from a nested table.

    Only the standalone ``configs/faerun_map.toml`` entry point uses this: it
    has no ``[map]`` wrapper to collide with, so ``[heightmap_detail]`` is a
    normal sub-table there instead of the CLI's flat ``heightmap_detail*``
    keys.
    """
    d = HeightmapDetailConfig()
    hf_raw = hmd.get("hf_targets")
    hf_targets = (
        {str(k): float(v) for k, v in hf_raw.items()} if hf_raw else dict(d.hf_targets)
    )
    return HeightmapDetailConfig(
        enabled=bool(hmd.get("enabled", d.enabled)),
        seed=int(hmd.get("seed", d.seed)),
        deterrace_sigma_px=float(hmd.get("deterrace_sigma_px", d.deterrace_sigma_px)),
        deterrace_mode=str(hmd.get("deterrace_mode", d.deterrace_mode)),
        cliff_step_levels=float(hmd.get("cliff_step_levels", d.cliff_step_levels)),
        spectral_slope=float(hmd.get("spectral_slope", d.spectral_slope)),
        target_mode=str(hmd.get("target_mode", d.target_mode)),
        target_gain=float(hmd.get("target_gain", d.target_gain)),
        gain_mode=str(hmd.get("gain_mode", d.gain_mode)),
        fill_gain=float(hmd.get("fill_gain", d.fill_gain)),
        gain_blur_px=float(hmd.get("gain_blur_px", d.gain_blur_px)),
        hf_targets=hf_targets,
        relief_mode=str(hmd.get("relief_mode", d.relief_mode)),
        erosion_iterations=int(hmd.get("erosion_iterations", d.erosion_iterations)),
        erosion_accum_iterations=int(
            hmd.get("erosion_accum_iterations", d.erosion_accum_iterations)
        ),
        erosion_seed_amplitude=float(
            hmd.get("erosion_seed_amplitude", d.erosion_seed_amplitude)
        ),
        erosion_mfd_exponent=float(
            hmd.get("erosion_mfd_exponent", d.erosion_mfd_exponent)
        ),
        erosion_incision=float(hmd.get("erosion_incision", d.erosion_incision)),
        erosion_diffusion=float(hmd.get("erosion_diffusion", d.erosion_diffusion)),
        erosion_slope_ceiling_steps=float(
            hmd.get("erosion_slope_ceiling_steps", d.erosion_slope_ceiling_steps)
        ),
        fill_min_cycles_per_km=float(
            hmd.get("fill_min_cycles_per_km", d.fill_min_cycles_per_km)
        ),
        headroom_fraction=float(
            hmd.get("headroom_fraction", d.headroom_fraction)
        ),
        river_depth=float(hmd.get("river_depth", d.river_depth)),
        coast_smooth_px=float(hmd.get("coast_smooth_px", d.coast_smooth_px)),
    )


@dataclass(frozen=True)
class BaronyConfig:
    """How CK2 counties are split into physical baronies.

    ``docs/step_map_baronies.md`` is the reference; the numbers that matter:

    * ``min_barony_pixels`` — the smallest barony the map may carry. 400 px is
      the vanilla-scale figure (a 20x20 blob at 9216x4608). Our canvas is at
      the *same* km per pixel as vanilla by construction
      (``docs/map_scale.md``), so 400 needs no rescaling; when the key is left
      out it is scaled by canvas area against the 9216-wide reference anyway,
      so a deliberately denser or coarser map still gets a sane default.
    * ``city_slot`` — index into the 7 pairs of a CK2 ``positions.txt``
      ``position={...}`` block. 0 is the city (`verified`, docs/map_scale.md
      §2b: slot 0 is inside its own province 91.9 % of the time).
    """

    #: bookmark the barony set is taken at, as (y, m, d)
    bookmark: tuple[int, int, int] = (1357, 1, 1)
    #: latest bookmark; holdings built by then are baronies too (design §B.1)
    latest_bookmark: tuple[int, int, int] = (1501, 1, 1)
    #: smallest barony in canvas pixels; 0 = derive from the canvas area
    min_barony_pixels: int = 0
    #: reference for the derived default: 400 px on a 9216-wide canvas
    reference_min_pixels: int = 400
    reference_width: int = 9216
    #: weight of the county capital's seed vs the others (design §B.3: 1.0 all)
    capital_weight: float = 1.0
    other_weight: float = 1.0
    #: how much a terrain-biased pixel is favoured in farthest-point sampling
    bias_gain: float = 0.5
    #: how far an imported seed coordinate may be snapped onto its county
    snap_radius_px: int = 48
    #: Lloyd relaxation passes on the seeds the converter sampled itself
    #: (overrides, gazetteer and positions.txt seeds are never moved)
    relax_passes: int = 4
    #: passes of "demote the worst straggler and regrow"
    max_regrow_passes: int = 3
    #: CK2 positions.txt slot that holds the city coordinate
    city_slot: int = 0
    #: CK2 positions.txt slot that holds the port/harbour coordinate
    #: (`verified`, docs/map_fidelity.md §1.6: the CK2 binary itself logs
    #: "Invalid port location for province %d" against slot 4)
    port_slot: int = 4
    #: use the CK2 positions.txt city/port slots as barony seeds at all.
    #: ``[map] ck2_position_seeds`` (default on); false reproduces the seed
    #: priority before this lane (capital only, no slot-4 port seeding).
    ck2_position_seeds: bool = True
    #: human override files, relative to the converter repo root
    seeds_csv: Path = Path("overrides/barony_seeds.csv")
    gazetteer_csv: Path = Path("overrides/gazetteer.csv")
    #: write the per-duchy review PNGs during the run (slow; usually a script)
    review_sheets: bool = False

    def min_pixels(self, canvas_width: int, canvas_height: int = 0) -> int:
        """``min_barony_pixels``, derived from the canvas width when not set.

        The derived value scales the 400 px reference by the *square* of the
        width ratio, because it is an area.  It is only a fallback: on a map
        built at vanilla's km per pixel (which ours is, by construction —
        ``docs/map_scale.md``) the honest value is the reference itself, and
        ``configs/faerun.toml`` pins it to 400 for exactly that reason.
        """
        if self.min_barony_pixels > 0:
            return self.min_barony_pixels
        ratio = canvas_width / self.reference_width
        return max(1, int(round(self.reference_min_pixels * ratio * ratio)))


@dataclass(frozen=True)
class ProvincesConfig:
    #: a CK2 colour that ends up with fewer pixels than this is reported lost
    min_pixels: int = 16
    #: RGB of the padding ocean; registered in definition.csv as a sea province
    ocean_rgb: tuple[int, int, int] = (0, 0, 96)
    ocean_name: str = "Padding Ocean"
    #: try one dilation pass inside the CK2 footprint to rescue tiny provinces
    regrow_lost: bool = True
    #: crop the canvas to the bounding box of the source's painted pixels
    crop_to_painted: bool = True


@dataclass(frozen=True)
class MapConfig:
    ck2_map_dir: Path
    out_mod_dir: Path
    scale: ScaleConfig
    heightmap: HeightmapConfig = field(default_factory=HeightmapConfig)
    heightmap_detail: HeightmapDetailConfig = field(default_factory=HeightmapDetailConfig)
    provinces: ProvincesConfig = field(default_factory=ProvincesConfig)
    baronies: BaronyConfig = field(default_factory=BaronyConfig)
    #: CK2 mod root, for common/landed_titles, history/provinces, localisation
    ck2_mod_dir: Path | None = None
    #: CK3 install `game/` dir, read-only. Needed because
    #: `map_data/geographical_regions` is a replace_path: every vanilla region
    #: name has to be re-declared or a vanilla script/GUI lookup of it fails.
    ck3_game_dir: Path | None = None
    #: converter repo root, for overrides/*.csv
    repo_dir: Path | None = None
    #: CK2 terrain category -> CK3 terrain key
    terrain_map: dict[str, str] = field(default_factory=dict)
    #: CK3 terrain key used when nothing else matches
    terrain_default: str = "plains"
    #: honour the CK2 `history/provinces` `terrain = X` override, which in CK2
    #: IS the province's gameplay terrain (the bitmap majority is only the
    #: fallback).  docs/step_map_terrain.md; false = the pre-lane behaviour,
    #: bitmap majority only.
    terrain_history: bool = True
    #: CK2 override category -> apply/keep_bitmap + CK3 key, with the reasoning
    terrain_history_csv: Path = Path("mappings/terrain_history_overrides.csv")
    #: bitmap classes a NON-capital barony lets the county override refine;
    #: any other bitmap class wins over the override for that barony
    terrain_history_weak: tuple[str, ...] = ("plains", "farmlands")
    #: CK2 ocean_region comment texts that mean "lake" rather than "sea"
    lake_region_names: tuple[str, ...] = ("Lakes",)
    #: trees.bmp palette indices that count as forest (CK2 default.map `tree`)
    tree_indices: tuple[int, ...] = ()
    #: file prefix for generated CK3 files
    prefix: str = "fae"
    #: write the throwaway one-barony-per-province title layer.  Off by
    #: default: lane `titles-history` owns common/landed_titles, history/titles
    #: and history/provinces.  Turn it on ([map] title_scaffolding = true) to
    #: boot a map-only mod without running the `titles` step.
    title_scaffolding: bool = False
    #: place the county-capital barony's locators at the CK2
    #: `positions.txt` slots instead of the province centroid: slot 0 ->
    #: `buildings` + `special_building`, slot 1 -> the two unit stacks and
    #: `combat` (`docs/step_map_assets.md`). A slot that does not land inside
    #: that barony's own province falls back to the centroid, and every other
    #: barony, sea and impassable province keeps the centroid regardless.
    #: `[map] ck2_locator_positions` (default on); false is the pure-centroid
    #: behaviour of build 8 and earlier.
    ck2_locator_positions: bool = True
    #: vanilla's own per-type offset from the `buildings` instance, added to
    #: whatever anchor a province got (CK2 slot 0 or its centroid) so a siege
    #: marker, a unit stack and the settlement do not sit on one point. CK3
    #: 1.19 keeps every type within ~15 px of the holding
    #: (`scripts/measure_vanilla_locator_offsets.py`). `[map]
    #: locator_offsets_csv`; an absent file means no offsets.
    locator_offsets_csv: Path = Path("mappings/locator_offsets.csv")
    #: vanilla px -> canvas px for those offsets. 1.0 because this canvas is
    #: planned at vanilla's own 1.4839 km per pixel by construction
    #: (`docs/map_scale.md` §1); `[map] locator_offset_scale` exists so a
    #: differently scaled map can say so instead of inheriting a wrong number.
    locator_offset_scale: float = 1.0
    #: what "vanilla's offset" means: ``"median_radius"`` (default: the measured
    #: median direction stretched to vanilla's measured median distance from
    #: the settlement) or ``"median_vector"`` (the raw measured median dx/dz).
    #: The two disagree for the rotationally symmetric types, whose median
    #: direction cancels out, and the distance is what a player sees --
    #: `docs/step_map_assets.md` §2.2, `docs/DECISIONS.md` 2026-09-10.
    #: `[map] locator_offset_mode`.
    locator_offset_mode: str = "median_radius"
    #: blank out vanilla's `gfx/map/map_object_data/generated/*.txt` foliage.
    #: Those files hold ~52 MB of tree instances at *European* coordinates and
    #: nothing stops them loading over a custom map, so on our canvas they are
    #: trees in the wrong ocean.  Elder Kings 2 and Godherja both ship empty
    #: `instances={}` stubs for the generators they do not want; this does the
    #: same for every one vanilla ships.  Set false to keep vanilla's foliage.
    strip_vanilla_foliage: bool = True
    #: write gfx/map/terrain/detail_index.tga + detail_intensity.tga, the pair
    #: CK3's renderer actually reads (docs/step_map_paint.md). ``[map]
    #: terrain_paint`` (default on). Ships nothing when false, same as before
    #: this lane, and CK3 falls back to sampling vanilla's own pair in UV
    #: space across the canvas.
    terrain_paint: bool = True
    #: CK3 terrain key -> (primary, secondary) vanilla material id
    terrain_paint_csv: Path = Path("mappings/terrain_paint.csv")
    #: blend-weight quantisation step for detail_intensity.tga (1 = none;
    #: docs/map_fidelity.md §4.1 measures 16 as visually invisible and much
    #: more compressible than the full 256 steps)
    terrain_paint_quantize: int = 16
    #: pixel format for detail_index/detail_intensity: ``"tga"`` (vanilla's
    #: own, uncompressed truecolour, image type 2), ``"tga_rle"`` (RLE, image
    #: type 10 — `verified` accepted by two shipped total-conversion workshop
    #: mods, Elder Kings 2 and Godherja, both at full resolution), or
    #: ``"dds"`` (uncompressed BGRA8 — implemented but unverified against the
    #: actual game; see docs/step_map_paint.md §size). Default unchanged
    #: until the coordinator's in-game check picks one.
    terrain_paint_format: str = "tga"
    #: nearest-neighbour (index) / box-filter (intensity) downsample factor
    #: for the paint pair. ``1.0`` matches `provinces.png` (vanilla's own
    #: choice); ``0.5`` quarters the pixel count. docs/step_map_paint.md
    #: §size. Default unchanged until the coordinator's in-game check.
    terrain_paint_scale: float = 1.0
    #: lane `paint-edges`: replace the nearest-neighbour class edges + the
    #: class-agnostic noise dither with a distance-field blend between the
    #: two strongest CK3 terrain classes, plus a per-class material *mix*
    #: (docs/step_map_paint.md §10). False restores the pre-build-14 path in
    #: `ck2ck3.map.terrain_paint.build_layers`.
    terrain_paint_soft_edges: bool = True
    #: Gaussian sigma, **canvas pixels**, of each class indicator mask. Sets
    #: how wide a class boundary's ramp is; 0 = hard edges again. Bounded by
    #: the macro invariant (a class must not migrate more than one CK2 source
    #: pixel, 2.90 km = 1.95 canvas px on Faerun).
    terrain_paint_edge_sigma_px: float = 2.0
    #: maximum displacement, **canvas pixels**, of the relief-aware warp that
    #: makes a class boundary follow the ground instead of the CK2 pixel grid
    #: (`ck2ck3.map.paint_edges.relief_warp`). 0 disables the warp.
    terrain_paint_relief_shift_px: float = 1.5
    #: Gaussian sigma, canvas pixels, applied to the heightmap before its
    #: gradient drives the warp: the boundary should follow landforms, not
    #: per-pixel noise.
    terrain_paint_relief_sigma_px: float = 8.0
    #: percentile of the land gradient magnitude at which the warp saturates
    #: at `terrain_paint_relief_shift_px`. Flat ground gets no displacement.
    terrain_paint_relief_percentile: float = 90.0
    #: the macro invariant, in **CK2 source pixels**: a terrain class may
    #: never win a canvas pixel further than this from where CK2 painted it.
    #: Converted to canvas pixels with the canvas factor and enforced (not
    #: hoped for) in `paint_edges.build_soft_blend`: an out-of-bound pixel
    #: reverts to CK2's own class. 0 disables the check.
    terrain_paint_max_shift_source_px: float = 1.0
    #: write gfx/map/terrain/colormap.dds — a measured tint per CK3 terrain
    #: key, calibrated against vanilla's own per-material colormap means
    #: (docs/step_map_paint.md §9.6/§9.7, lane `colormap-fix`; superseded the
    #: CK2-colormap resample the coordinator found painted a saturated
    #: satellite image with no sea/land distinction over the terrain).
    #: False ships neither this file nor a change to output_final_colormap.dds
    #: (vanilla's own copy is 0 bytes and needs no override either way).
    colormap: bool = True
    #: CK3 terrain key (+ "water") -> measured tint RGB
    #: (docs/step_map_paint.md §9.7, mappings/colormap_tints.csv).
    colormap_tints_csv: Path = Path("mappings/colormap_tints.csv")
    #: Gaussian blur sigma, canvas pixels, applied after painting so
    #: terrain-key boundaries do not read as flat colour blocks. Default is
    #: `scripts/measure_vanilla_colormap_blur.py`'s measured 1/e
    #: autocorrelation radius of vanilla's own colormap.dds (9 vanilla px),
    #: used unconverted because our canvas matches vanilla's own km/px
    #: (docs/map_scale.md).
    colormap_blur_sigma: float = 9.0
    #: downsample factor from canvas resolution, `verified` against two
    #: shipped total conversions (Elder Kings 2, Godherja) which both ship
    #: their own colormap.dds at exactly one-quarter of their province-map
    #: resolution, uncompressed.
    colormap_scale: float = 0.25
    #: write the full mip chain to 1x1 (Godherja's shape) vs. base level only
    #: (Elder Kings 2's shape); both load.
    colormap_mips: bool = True
    #: write gfx/map/water/watercolor_rgb_waterspec_a.dds + foam_map.dds and
    #: gfx/map/textures/snow_mask.dds. All three are sampled at a whole-map UV
    #: and encode vanilla's Earth; ship none and the sea shows Europe
    #: (docs/step_map_water_border.md, ck2ck3.map.water). Both shipped total
    #: conversions override all three.
    water: bool = True
    #: vanilla's measured colour/gloss/foam against coast distance, in canvas
    #: pixels (scripts/measure_vanilla_water.py).
    water_profile_csv: Path = Path("mappings/water_profile.csv")
    #: downsample factor from canvas resolution for the water colour map;
    #: vanilla and Elder Kings 2 both ship theirs at half canvas.
    water_scale: float = 0.5
    #: same, for the foam map. Godherja ships its own at an eighth of canvas,
    #: so the foam ramp does not need the colour map's resolution.
    water_foam_scale: float = 0.25
    #: same, for the snow mask; both reference mods ship a quarter canvas.
    snow_mask_scale: float = 0.25
    #: flat R for the snow mask: 255 = snow never falls, 0 = the engine's own
    #: winter model and hemisphere term decide. See ck2ck3.map.water for why
    #: neither of the two measured derivations survived.
    snow_mask_no_snow: int = 0
    #: write gfx/map/surround_map/surround_mask.dds. Vanilla's own hides up to
    #: 67 % of the map height at the top - empty Arctic there, real territory
    #: on any other map (docs/step_map_water_border.md §3, ck2ck3.map.surround).
    surround_mask: bool = True
    #: the measured frame profile (scripts/measure_vanilla_surround.py)
    surround_profile_csv: Path = Path("mappings/surround_profile.csv")
    #: downsample factor from canvas resolution for the surround mask
    surround_scale: float = 0.5
    #: scatter tree instances into gfx/map/map_object_data/generated/*.txt
    #: from CK2 trees.bmp (docs/step_map_paint.md §9). Default on; false
    #: falls back to strip_vanilla_foliage's empty stubs.
    trees: bool = True
    #: CK3 terrain key -> vanilla generated file name
    trees_csv: Path = Path("mappings/tree_meshes.csv")
    #: deterministic RNG seed for the scatter and per-file yaw
    trees_seed: int = 4242
    #: instances per canvas pixel; default is vanilla 1.19's own measured
    #: density, 549,126 instances over its 9216x4608 canvas (`verified`,
    #: scripts/verify_tree_density.py)
    trees_density_per_px: float = 549_126 / (9216 * 4608)
    #: pick each tree's mesh from vanilla's own measured
    #: P(mesh | terrain, climate, latitude band) instead of from the terrain
    #: key alone (docs/step_map_paint.md §9.9). Density and eligibility are
    #: unchanged either way - only the *which mesh* step differs.
    trees_regional: bool = True
    #: the measured conditional table (scripts/build_tree_mix_csv.py)
    trees_mix_csv: Path = Path("mappings/tree_mix.csv")
    #: human overrides applied on top of it, per exact condition
    trees_mix_overrides_csv: Path = Path("overrides/tree_mix.csv")
    #: square canvas cell the regional sampler draws one shared uniform for,
    #: so species read as stands rather than per-pixel salt and pepper
    trees_cell_px: int = 24
    #: share of trees that take their cell's uniform rather than their own;
    #: 1.0 is fully coherent, 0.0 fully independent. Calibrated against
    #: docs/evidence/vanilla_tree_patch_scale.csv.
    trees_cell_coherence: float = 0.55
    #: lane `paint-edges`: expand `trees.bmp` (1/8 resolution, 23.2 km per
    #: tree pixel) with a bilinear interpolation + threshold instead of
    #: `np.repeat`, so a forest edge is a rounded contour rather than a
    #: 15.6-canvas-pixel Lego block. False restores the nearest expansion.
    trees_mask_smooth: bool = True
    #: coverage level of the interpolated tree field that counts as forest.
    #: 0.5 puts the boundary on the midpoint between a forest and a
    #: non-forest source pixel, which is the area-preserving choice.
    trees_mask_threshold: float = 0.5
    #: extra Gaussian (in source pixels) on the interpolated tree field
    #: before the threshold; 0 = bilinear only.
    trees_mask_blur_px: float = 0.0
    #: evidence output directory (relative to the converter repo)
    evidence_dir: Path = Path("docs/evidence")
    #: descriptor.mod fields for the generated mod
    mod_name: str = "Faerun (CK2 conversion, raw)"
    mod_version: str = "0.1.0"
    supported_version: str = "1.19.*"


def load(path: str | Path) -> MapConfig:
    """Load a map config TOML. Relative paths resolve against the TOML's dir."""
    p = Path(path).resolve()
    with p.open("rb") as fh:
        raw = tomllib.load(fh)
    base = p.parent.parent  # configs/<x>.toml -> repo root

    def _path(value: str) -> Path:
        q = Path(value)
        return q if q.is_absolute() else (base / q).resolve()

    inp = raw.get("input", {})
    out = raw.get("output", {})
    sc = raw["scale"]
    hm = raw.get("heightmap", {})
    pr = raw.get("provinces", {})
    tr = raw.get("terrain", {})

    return MapConfig(
        ck2_map_dir=_path(inp["ck2_map_dir"]),
        out_mod_dir=_path(out["mod_dir"]),
        scale=ScaleConfig(
            vanilla_km_per_px=float(sc["vanilla_km_per_px"]),
            source_km_per_px=float(sc["source_km_per_px"]),
            factor_override=(
                float(sc["factor_override"]) if sc.get("factor_override") else None
            ),
            sea_margin_px=int(sc.get("sea_margin_px", 64)),
            canvas_multiple=int(sc.get("canvas_multiple", 64)),
            max_canvas_px=int(sc.get("max_canvas_px", 32768)),
        ),
        heightmap=HeightmapConfig(
            resolution_factor=int(hm.get("resolution_factor", 1)),
            ck2_sea_level=int(hm.get("ck2_sea_level", 95)),
            ck3_water_level=int(hm.get("ck3_water_level", 0)),
            ck3_max_level=int(hm.get("ck3_max_level", 65535)),
            curve=[(int(a), int(b)) for a, b in hm.get("curve", [])],
            tile_size=int(hm.get("tile_size", 33)),
        ),
        # standalone TOML nests this as its own [heightmap_detail] table
        # (the CLI's [map] uses flat heightmap_detail* keys instead -- see
        # heightmap_detail_config()).
        heightmap_detail=_heightmap_detail_from_table(raw.get("heightmap_detail", {})),
        provinces=ProvincesConfig(
            min_pixels=int(pr.get("min_pixels", 16)),
            ocean_rgb=tuple(int(v) for v in pr.get("ocean_rgb", (0, 0, 96))),  # type: ignore[arg-type]
            ocean_name=str(pr.get("ocean_name", "Padding Ocean")),
            regrow_lost=bool(pr.get("regrow_lost", True)),
            crop_to_painted=bool(pr.get("crop_to_painted", True)),
        ),
        baronies=barony_config(raw.get("baronies", {})),
        ck2_mod_dir=_path(inp["ck2_mod_dir"]) if inp.get("ck2_mod_dir") else None,
        repo_dir=base,
        terrain_map=dict(tr.get("map", {})),
        terrain_default=str(tr.get("default", "plains")),
        terrain_history=bool(tr.get("history", raw.get("province_terrain_history", True))),
        terrain_history_csv=Path(
            str(
                tr.get(
                    "history_csv",
                    raw.get(
                        "terrain_history_csv", "mappings/terrain_history_overrides.csv"
                    ),
                )
            )
        ),
        terrain_history_weak=tuple(
            str(v)
            for v in tr.get(
                "history_weak_classes",
                raw.get("terrain_history_weak_classes", ("plains", "farmlands")),
            )
        ),
        lake_region_names=tuple(raw.get("regions", {}).get("lake_names", ("Lakes",))),
        tree_indices=tuple(int(v) for v in tr.get("tree_indices", ())),
        prefix=str(out.get("prefix", "fae")),
        title_scaffolding=bool(out.get("title_scaffolding", False)),
        ck2_locator_positions=bool(raw.get("ck2_locator_positions", True)),
        locator_offsets_csv=Path(
            str(raw.get("locator_offsets_csv", "mappings/locator_offsets.csv"))
        ),
        locator_offset_scale=float(raw.get("locator_offset_scale", 1.0)),
        locator_offset_mode=str(raw.get("locator_offset_mode", "median_vector")),
        terrain_paint=bool(raw.get("terrain_paint", True)),
        terrain_paint_csv=Path(
            str(raw.get("terrain_paint_csv", "mappings/terrain_paint.csv"))
        ),
        terrain_paint_quantize=int(raw.get("terrain_paint_quantize", 16)),
        terrain_paint_format=str(raw.get("terrain_paint_format", "tga")),
        terrain_paint_scale=float(raw.get("terrain_paint_scale", 1.0)),
        terrain_paint_soft_edges=bool(raw.get("terrain_paint_soft_edges", True)),
        terrain_paint_edge_sigma_px=float(raw.get("terrain_paint_edge_sigma_px", 2.0)),
        terrain_paint_relief_shift_px=float(
            raw.get("terrain_paint_relief_shift_px", 1.5)
        ),
        terrain_paint_relief_sigma_px=float(
            raw.get("terrain_paint_relief_sigma_px", 8.0)
        ),
        terrain_paint_relief_percentile=float(
            raw.get("terrain_paint_relief_percentile", 90.0)
        ),
        terrain_paint_max_shift_source_px=float(
            raw.get("terrain_paint_max_shift_source_px", 1.0)
        ),
        colormap=bool(raw.get("colormap", True)),
        colormap_tints_csv=Path(
            str(raw.get("colormap_tints_csv", "mappings/colormap_tints.csv"))
        ),
        colormap_blur_sigma=float(raw.get("colormap_blur_sigma", 9.0)),
        colormap_scale=float(raw.get("colormap_scale", 0.25)),
        colormap_mips=bool(raw.get("colormap_mips", True)),
        water=bool(raw.get("water", True)),
        water_profile_csv=Path(
            str(raw.get("water_profile_csv", "mappings/water_profile.csv"))
        ),
        water_scale=float(raw.get("water_scale", 0.5)),
        water_foam_scale=float(raw.get("water_foam_scale", 0.25)),
        snow_mask_scale=float(raw.get("snow_mask_scale", 0.25)),
        snow_mask_no_snow=int(raw.get("snow_mask_no_snow", 0)),
        surround_mask=bool(raw.get("surround_mask", True)),
        surround_profile_csv=Path(
            str(raw.get("surround_profile_csv", "mappings/surround_profile.csv"))
        ),
        surround_scale=float(raw.get("surround_scale", 0.5)),
        trees=bool(raw.get("trees", True)),
        trees_csv=Path(str(raw.get("trees_csv", "mappings/tree_meshes.csv"))),
        trees_seed=int(raw.get("trees_seed", 4242)),
        trees_density_per_px=float(
            raw.get("trees_density_per_px", 549_126 / (9216 * 4608))
        ),
        trees_regional=bool(raw.get("trees_regional", True)),
        trees_mix_csv=Path(str(raw.get("trees_mix_csv", "mappings/tree_mix.csv"))),
        trees_mix_overrides_csv=Path(
            str(raw.get("trees_mix_overrides_csv", "overrides/tree_mix.csv"))
        ),
        trees_cell_px=int(raw.get("trees_cell_px", 24)),
        trees_cell_coherence=float(raw.get("trees_cell_coherence", 0.55)),
        trees_mask_smooth=bool(raw.get("trees_mask_smooth", True)),
        trees_mask_threshold=float(raw.get("trees_mask_threshold", 0.5)),
        trees_mask_blur_px=float(raw.get("trees_mask_blur_px", 0.0)),
        evidence_dir=_path(str(out.get("evidence_dir", "docs/evidence"))),
        mod_name=str(out.get("mod_name", "Faerun (CK2 conversion, raw)")),
        mod_version=str(out.get("mod_version", "0.1.0")),
        supported_version=str(out.get("supported_version", "1.19.*")),
    )


def parse_date(value: str | Sequence[int]) -> tuple[int, int, int]:
    """``"1357.1.1"`` or ``[1357, 1, 1]`` -> ``(1357, 1, 1)``."""
    if isinstance(value, str):
        parts = value.split(".")
    else:
        parts = list(value)  # type: ignore[arg-type]
    if len(parts) != 3:
        raise ValueError(f"expected a Y.M.D date, got {value!r}")
    return (int(parts[0]), int(parts[1]), int(parts[2]))


def barony_config(raw: dict) -> BaronyConfig:
    """Build a :class:`BaronyConfig` from a ``[map.baronies]`` TOML table."""
    d = BaronyConfig()
    return BaronyConfig(
        bookmark=parse_date(raw.get("bookmark", d.bookmark)),
        latest_bookmark=parse_date(raw.get("latest_bookmark", d.latest_bookmark)),
        min_barony_pixels=int(raw.get("min_barony_pixels", d.min_barony_pixels)),
        reference_min_pixels=int(
            raw.get("reference_min_pixels", d.reference_min_pixels)
        ),
        reference_width=int(raw.get("reference_width", d.reference_width)),
        capital_weight=float(raw.get("capital_weight", d.capital_weight)),
        other_weight=float(raw.get("other_weight", d.other_weight)),
        bias_gain=float(raw.get("bias_gain", d.bias_gain)),
        snap_radius_px=int(raw.get("snap_radius_px", d.snap_radius_px)),
        relax_passes=int(raw.get("relax_passes", d.relax_passes)),
        max_regrow_passes=int(raw.get("max_regrow_passes", d.max_regrow_passes)),
        city_slot=int(raw.get("city_slot", d.city_slot)),
        port_slot=int(raw.get("port_slot", d.port_slot)),
        ck2_position_seeds=bool(raw.get("ck2_position_seeds", d.ck2_position_seeds)),
        seeds_csv=Path(str(raw.get("seeds_csv", d.seeds_csv))),
        gazetteer_csv=Path(str(raw.get("gazetteer_csv", d.gazetteer_csv))),
        review_sheets=bool(raw.get("review_sheets", d.review_sheets)),
    )
