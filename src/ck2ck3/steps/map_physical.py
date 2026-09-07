"""Conversion step: the physical map.

Registry entry point for the ``ck2ck3`` CLI (lane ``foundation``):

    ck2ck3 --config configs/faerun.toml --step map_physical

Until that CLI lands the same work runs standalone:

    uv run python -m ck2ck3.map.build --config configs/faerun_map.toml
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..map import build as map_build
from ..map import config as map_config

#: what this step writes, relative to the output mod root; the coordinator can
#: use it to decide ordering against other steps
OUTPUTS = (
    "map_data/provinces.png",
    "map_data/heightmap.png",
    "map_data/packed_heightmap.png",
    "map_data/indirection_heightmap.png",
    "map_data/heightmap.heightmap",
    "map_data/rivers.png",
    "map_data/definition.csv",
    "map_data/default.map",
    "map_data/adjacencies.csv",
    "map_data/climate.txt",
    "map_data/continent.txt",
    "map_data/island_region.txt",
    "map_data/positions.txt",
    "map_data/seasons.txt",
    "map_data/geographical_regions/",
    "common/province_terrain/",
    "common/defines/",
    # throwaway scaffolding, replaced by the titles-history lane
    "common/landed_titles/",
    "history/provinces/",
    "history/titles/",
    "localization/english/",
    "descriptor.mod",
)


def run(ctx: Any) -> dict:
    """Run the physical-map conversion.

    ``ctx`` is the CLI's context object.  Only three things are read from it, by
    ``getattr`` so this module does not depend on the ``foundation`` lane's
    final shape:

    * ``ctx.map_config`` — path to a map config TOML (or ``ctx.config`` with a
      ``[map]`` table naming one under ``config``);
    * ``ctx.out_dir`` — output mod root, overriding the TOML;
    * ``ctx.skip_images`` — text files only.

    Returns the run report, which the CLI can fold into its own summary.
    """
    cfg_path = _pick_config(ctx)
    cfg = map_config.load(cfg_path)

    out_dir = getattr(ctx, "out_dir", None)
    if out_dir:
        cfg = _replace(cfg, out_mod_dir=Path(out_dir).resolve())
    ck2_dir = getattr(ctx, "ck2_map_dir", None)
    if ck2_dir:
        cfg = _replace(cfg, ck2_map_dir=Path(ck2_dir).resolve())

    return map_build.run(cfg, skip_images=bool(getattr(ctx, "skip_images", False)))


def _pick_config(ctx: Any) -> Path:
    for attr in ("map_config", "map_config_path"):
        value = getattr(ctx, attr, None)
        if value:
            return Path(value)
    config = getattr(ctx, "config", None)
    if isinstance(config, dict):
        named = config.get("map", {}).get("config")
        if named:
            return Path(named)
    raise ValueError(
        "map_physical needs a map config TOML: set ctx.map_config, or a "
        "[map] config = \"configs/faerun_map.toml\" table in the CLI config"
    )


def _replace(cfg: map_config.MapConfig, **kw) -> map_config.MapConfig:
    from dataclasses import replace

    return replace(cfg, **kw)
