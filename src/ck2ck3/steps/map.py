"""Convert the physical map: CK2 ``map/`` -> CK3 ``map_data/``.

One CK3 province per CK2 province, at the same physical km-per-pixel as the
vanilla CK3 map.  Barony subdivision is a later lane (``docs/design_map.md`` §B).

Reads the ``[map]`` table of the CLI config; the derivation of every number is
in ``docs/map_scale.md`` and the CK3 formats in ``docs/formats_map.md`` and
``docs/formats_packed_heightmap.md``.

``common/landed_titles``, ``history/titles`` and ``history/provinces`` belong
to lane ``titles-history`` (steps ``titles`` and ``history_titles``).  This
step can still emit its throwaway one-barony-per-province layer there for a
map-only boot, but only when ``[map] title_scaffolding = true`` is set, and
then the two steps must not be run together.
"""

from __future__ import annotations

from ..context import Context, StepResult
from ..map import build as map_build
from ..map import config as map_config
from ..map.sink import ContextSink

DESCRIPTION = "provinces/heightmap/rivers + definition.csv, default.map, terrain"

OUTPUTS: tuple[str, ...] = (
    "map_data",
    "common/province_terrain",
    "common/defines",
)


#: keys the step cannot run without; a config that lacks them gets skipped
#: rather than crashing, so a minimal config (the CLI's own tests, a new mod)
#: still runs the other steps.
REQUIRED_MAP_KEYS = ("vanilla_km_per_px", "source_km_per_px")


def run(ctx: Context) -> StepResult:
    raw = ctx.config.raw.get("map", {})
    missing = [k for k in REQUIRED_MAP_KEYS if k not in raw]
    if missing:
        return StepResult(
            summary=(
                "skipped: [map] is missing "
                + ", ".join(missing)
                + " (see docs/map_scale.md for how they are measured)"
            ),
            skipped=True,
        )
    cfg = _map_config(ctx)
    sink = ContextSink(ctx)
    report = map_build.run(cfg, sink, skip_images=_skip_images(ctx))

    # localisation goes through ctx.write_loc, which owns the BOM and the CRLF
    loc = report.pop("localisation", {})
    if loc:
        ctx.write_loc(
            f"localization/english/{ctx.config.prefix}_titles_l_english.yml", loc
        )

    # the id map and the lost-province report are evidence for THIS repo, not
    # files of the generated mod, so they do not go through ctx.write_*
    evidence = report.pop("_evidence", {})
    if not ctx.dry_run:
        for name, text in evidence.items():
            path = ctx.config.path.parent.parent / "docs" / "evidence" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8", newline="")

    canvas = report["canvas"]
    prov = report["provinces"]
    return StepResult(
        summary=(
            f"map {canvas['width']}x{canvas['height']} at scale "
            f"{canvas['factor']:.4f} ({cfg.scale.source_km_per_px} -> "
            f"{cfg.scale.vanilla_km_per_px} km/px): "
            f"{prov['ck3_total']} provinces, {prov['lost']} lost"
        ),
        counts={
            "provinces": prov["ck3_total"],
            "land": prov["land"],
            "sea": prov["sea"],
            "lakes": prov["lake"],
            "river_provinces": prov["river"],
            "lost": prov["lost"],
            "regrown": prov["regrown"],
            "adjacencies": report["adjacencies"]["kept"],
            "baronies_placeholder": report["bootstrap"]["baronies"],
        },
        warnings=list(sink.warnings),
        written=list(sink.written),
    )


def _skip_images(ctx: Context) -> bool:
    """``[map] skip_images = true`` builds the text files only.

    Useful when iterating on a format: the four PNGs are 30 s and ~45 MB.
    """
    return bool(ctx.config.raw.get("map", {}).get("skip_images", False))


def _map_config(ctx: Context) -> map_config.MapConfig:
    """Build the map pipeline's config from the CLI config's ``[map]`` table."""
    raw = dict(ctx.config.raw.get("map", {}))
    # The measured inputs are flat keys under [map], not a [map.scale] table:
    # `scale` under [map] is already the derived float that Config.map.scale
    # reads, and TOML will not let a key be both a value and a table.
    hm = dict(raw.get("heightmap", {}))
    pr = dict(raw.get("provinces", {}))
    tr = dict(raw.get("terrain", {}))

    return map_config.MapConfig(
        ck2_map_dir=ctx.ck2("map"),
        out_mod_dir=ctx.config.out,
        scale=map_config.ScaleConfig(
            vanilla_km_per_px=float(raw["vanilla_km_per_px"]),
            source_km_per_px=float(raw["source_km_per_px"]),
            factor_override=(
                float(raw["factor_override"]) if raw.get("factor_override") else None
            ),
            sea_margin_px=int(raw.get("sea_margin_px", 64)),
            canvas_multiple=int(raw.get("canvas_multiple", 64)),
            max_canvas_px=int(raw.get("max_canvas_px", 32768)),
        ),
        heightmap=map_config.HeightmapConfig(
            resolution_factor=int(hm.get("resolution_factor", 1)),
            ck2_sea_level=int(hm.get("ck2_sea_level", 95)),
            ck3_water_level=int(hm.get("ck3_water_level", 4883)),
            ck3_max_level=int(hm.get("ck3_max_level", 49205)),
            curve=[(int(a), int(b)) for a, b in hm.get("curve", [])],
            tile_size=int(hm.get("tile_size", 33)),
        ),
        provinces=map_config.ProvincesConfig(
            min_pixels=int(pr.get("min_pixels", 16)),
            ocean_rgb=tuple(int(v) for v in pr.get("ocean_rgb", (0, 0, 96))),  # type: ignore[arg-type]
            ocean_name=str(pr.get("ocean_name", "Padding Ocean")),
            regrow_lost=bool(pr.get("regrow_lost", True)),
        ),
        terrain_map=dict(tr.get("map", {})),
        terrain_default=str(tr.get("default", "plains")),
        lake_region_names=tuple(raw.get("lake_names", ("Lakes",))),
        tree_indices=tuple(int(v) for v in tr.get("tree_indices", ())),
        prefix=ctx.config.prefix,
        title_scaffolding=bool(raw.get("title_scaffolding", False)),
        mod_name=ctx.config.name,
        mod_version=ctx.config.version,
        supported_version=ctx.config.supported_version,
    )
