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
    #: pass 1 (de-terrace): Gaussian sigma, canvas px
    deterrace_sigma_px: float = 1.6
    #: pass 2 (spectral fill): vanilla's land elevation spectrum is
    #: amplitude ~ f**slope
    spectral_slope: float = -2.0
    #: pass 2: Gaussian blur (canvas px) on the per-pixel noise-gain field, so
    #: terrain-class borders leave no amplitude seam
    gain_blur_px: float = 6.0
    #: pass 2: per-CK3-terrain target high-frequency RMS (16-bit levels); a
    #: terrain key missing from this table falls back to its "plains" entry
    hf_targets: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_HF_TARGETS))
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
        spectral_slope=float(
            raw.get("heightmap_detail_spectral_slope", d.spectral_slope)
        ),
        gain_blur_px=float(raw.get("heightmap_detail_gain_blur_px", d.gain_blur_px)),
        hf_targets=hf_targets,
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
        spectral_slope=float(hmd.get("spectral_slope", d.spectral_slope)),
        gain_blur_px=float(hmd.get("gain_blur_px", d.gain_blur_px)),
        hf_targets=hf_targets,
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
        lake_region_names=tuple(raw.get("regions", {}).get("lake_names", ("Lakes",))),
        tree_indices=tuple(int(v) for v in tr.get("tree_indices", ())),
        prefix=str(out.get("prefix", "fae")),
        title_scaffolding=bool(out.get("title_scaffolding", False)),
        terrain_paint=bool(raw.get("terrain_paint", True)),
        terrain_paint_csv=Path(
            str(raw.get("terrain_paint_csv", "mappings/terrain_paint.csv"))
        ),
        terrain_paint_quantize=int(raw.get("terrain_paint_quantize", 16)),
        terrain_paint_format=str(raw.get("terrain_paint_format", "tga")),
        terrain_paint_scale=float(raw.get("terrain_paint_scale", 1.0)),
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
