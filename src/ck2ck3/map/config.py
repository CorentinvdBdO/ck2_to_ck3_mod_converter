"""Config for the physical-map step, loaded from a TOML file.

Everything mod-specific lives in the TOML; nothing is hardcoded in the code
path.  See ``configs/faerun_map.toml`` for the documented reference file.
"""

from __future__ import annotations

import math
import tomllib
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
    """Target ``map_data`` geometry."""

    width: int
    height: int
    #: scaled source size (before padding)
    scaled_width: int
    scaled_height: int
    #: where the scaled source is pasted (top-left, target pixels)
    offset_x: int
    offset_y: int
    factor: float

    def to_target(self, x: float, y: float) -> tuple[int, int]:
        """CK2 pixel (top-left origin) -> target pixel."""
        return (
            int(round(x * self.factor)) + self.offset_x,
            int(round(y * self.factor)) + self.offset_y,
        )


def plan_canvas(src_w: int, src_h: int, scale: ScaleConfig) -> Canvas:
    """Smallest canvas that fits the scaled source plus a sea margin.

    Rounded up to ``canvas_multiple`` on both axes and the source is centred in
    the slack, so the margin is never smaller than requested on any side.
    """
    factor = scale.factor
    if factor <= 0:
        raise ValueError(f"scale factor must be positive, got {factor}")
    sw = int(math.ceil(src_w * factor))
    sh = int(math.ceil(src_h * factor))
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


@dataclass(frozen=True)
class ProvincesConfig:
    #: a CK2 colour that ends up with fewer pixels than this is reported lost
    min_pixels: int = 16
    #: RGB of the padding ocean; registered in definition.csv as a sea province
    ocean_rgb: tuple[int, int, int] = (0, 0, 96)
    ocean_name: str = "Padding Ocean"
    #: try one dilation pass inside the CK2 footprint to rescue tiny provinces
    regrow_lost: bool = True


@dataclass(frozen=True)
class MapConfig:
    ck2_map_dir: Path
    out_mod_dir: Path
    scale: ScaleConfig
    heightmap: HeightmapConfig = field(default_factory=HeightmapConfig)
    provinces: ProvincesConfig = field(default_factory=ProvincesConfig)
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
        provinces=ProvincesConfig(
            min_pixels=int(pr.get("min_pixels", 16)),
            ocean_rgb=tuple(int(v) for v in pr.get("ocean_rgb", (0, 0, 96))),  # type: ignore[arg-type]
            ocean_name=str(pr.get("ocean_name", "Padding Ocean")),
            regrow_lost=bool(pr.get("regrow_lost", True)),
        ),
        terrain_map=dict(tr.get("map", {})),
        terrain_default=str(tr.get("default", "plains")),
        lake_region_names=tuple(raw.get("regions", {}).get("lake_names", ("Lakes",))),
        tree_indices=tuple(int(v) for v in tr.get("tree_indices", ())),
        prefix=str(out.get("prefix", "fae")),
        evidence_dir=_path(str(out.get("evidence_dir", "docs/evidence"))),
        mod_name=str(out.get("mod_name", "Faerun (CK2 conversion, raw)")),
        mod_version=str(out.get("mod_version", "0.1.0")),
        supported_version=str(out.get("supported_version", "1.19.*")),
    )
