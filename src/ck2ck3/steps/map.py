"""Convert the physical map: CK2 ``map/`` -> CK3 ``map_data/``.

One CK3 province per **built CK2 holding**, at the same physical km-per-pixel
as the vanilla CK3 map: each CK2 county is split into its built baronies by
seeded geodesic Voronoi (``docs/step_map_baronies.md``, ``docs/design_map.md``
§B).  Human overrides come from ``overrides/barony_seeds.csv`` and
``overrides/gazetteer.csv``.

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

from pathlib import Path

from ..context import Context, StepResult
from ..map import build as map_build
from ..map import config as map_config
from ..map.sink import ContextSink

DESCRIPTION = "provinces/heightmap/rivers, baronies, definition.csv, default.map"

OUTPUTS: tuple[str, ...] = (
    "map_data",
    "common/province_terrain",
    "common/defines",
    # locators, the 3D map table and the flat map: everything that has to
    # follow a non-vanilla canvas (docs/evidence/map_ui_research.md)
    "gfx/map/map_object_data",
    "gfx/map/terrain/flat_maps",
    # detail_index.tga / detail_intensity.tga, the runtime terrain paint pair
    # (docs/step_map_paint.md); same-filename override, no replace_path needed
    "gfx/map/terrain",
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

    private = {k: report.pop(k) for k in list(report) if k.startswith("_") and k != "_evidence"}

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

    if cfg.baronies.review_sheets and not ctx.dry_run:
        from ..map import review

        n = review.write_all(
            out_dir=ctx.config.path.parent.parent / "docs" / "evidence" / "baronies",
            plan=private["_plan"],
            ids=private["_ids"],
            raster=private["_raster"],
            tree=review.load_tree(cfg),
            log=ctx.info,
        )
        ctx.info(f"{n} duchy review sheets written")

    canvas = report["canvas"]
    prov = report["provinces"]
    bar = report["baronies"]
    trees = report.get("trees", {})
    colormap = report.get("colormap", {})
    th = report.get("terrain_history", {})
    loc = report.get("locators", {})
    # the heightmap-detail switches are named in the step summary on purpose:
    # last_run.md is then the proof that the `[map] heightmap_detail_*` keys
    # were read, which a key under the wrong header silently is not
    # (docs/step_map_heightmap.md §5)
    hd = report.get("heightmap_detail", {})
    hd_summary = (
        f"; heightmap detail {hd['deterrace_mode']}/{hd['relief_mode']}"
        f"/{hd.get('target_mode', 'power_law')}, "
        f"fill>={hd.get('fill_min_cycles_per_km', 0)} c/km, "
        f"slope ceiling {hd.get('erosion_slope_ceiling_steps', 0)} steps, "
        f"{hd['land_pct_on_clamp_floor']} % of land on the clamp floor"
        if hd else ""
    )
    return StepResult(
        summary=(
            f"map {canvas['width']}x{canvas['height']} at scale "
            f"{canvas['factor']:.4f} ({cfg.scale.source_km_per_px} -> "
            f"{cfg.scale.vanilla_km_per_px} km/px): "
            f"{prov['ck3_total']} provinces, {bar['placed']} baronies in "
            f"{bar['counties']} counties, {bar['demoted']} demoted, "
            f"{prov['lost']} lost" + hd_summary
        ),
        counts={
            "provinces": prov["ck3_total"],
            "land": prov["land"],
            "baronies": prov["baronies"],
            "baronies_demoted": bar["demoted"],
            "counties": bar["counties"],
            "sea": prov["sea"],
            "lakes": prov["lake"],
            "river_provinces": prov["river"],
            "impassable": prov["impassable"],
            "lost": prov["lost"],
            "regrown": prov["regrown"],
            "adjacencies": report["adjacencies"]["kept"],
            **({"trees_placed": trees["placed"], "trees_dropped": trees["dropped_no_mesh"]}
               if trees else {}),
            **({"colormap_px": colormap["width"] * colormap["height"]}
               if colormap else {}),
            # how many locator instances left the province centroid, and how
            # many county capitals took their CK2 positions.txt slot-0 town
            # as the anchor (docs/step_map_assets.md)
            **({"locators_ck2_anchors": loc["ck2_anchors"]["accepted"],
                "locators_ck2_anchor_candidates": loc["ck2_anchors"]["candidates"]}
               if loc.get("ck2_anchors") else {}),
            **({"locators_moved_instances": loc["moved_instances"]}
               if "moved_instances" in loc else {}),
            # lane `province-terrain`: the CK2 history `terrain = X` override
            # (docs/step_map_terrain.md). Counted here so a run report says
            # how many counties the author's own choice actually moved.
            **({"terrain_override_counties": th["counties_with_override"],
                "terrain_override_provinces_changed": th["provinces_changed"],
                "terrain_override_applied_capital": th["applied_capital"],
                "terrain_override_applied_weak": th["applied_weak_bitmap"],
                "terrain_override_kept_bitmap": (
                    th["kept_strong_bitmap"] + th["kept_rule"]
                ),
                "terrain_override_already_agreed": th["already_agreed"],
                "terrain_override_unmapped": sum(
                    th["unmapped_categories"].values()
                ),
                "terrain_override_class_px_moved": th["class_grid_pixels_moved"]}
               if th.get("enabled") else {}),
            **({"heightmap_fill_min_cycles_per_km":
                    hd.get("fill_min_cycles_per_km", 0),
                "heightmap_erosion_slope_ceiling_steps":
                    hd.get("erosion_slope_ceiling_steps", 0),
                "heightmap_distinct_values": hd["distinct_values_after"],
                "heightmap_clamp_floor_px": hd["land_px_on_clamp_floor"],
                "heightmap_excursion_limited_px": hd["excursion_limited_px"],
                "heightmap_detail_seconds": int(hd["elapsed_s"])}
               if hd else {}),
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
        ck2_mod_dir=ctx.ck2(),
        ck3_game_dir=ctx.ck3(),
        repo_dir=ctx.config.path.parent.parent,
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
            deepen_sea=bool(hm.get("deepen_sea", True)),
            sea_shelf_px=int(hm.get("sea_shelf_px", 24)),
            sea_floor=int(hm.get("sea_floor", 0)),
        ),
        heightmap_detail=map_config.heightmap_detail_config(raw),
        provinces=map_config.ProvincesConfig(
            min_pixels=int(pr.get("min_pixels", 16)),
            ocean_rgb=tuple(int(v) for v in pr.get("ocean_rgb", (0, 0, 96))),  # type: ignore[arg-type]
            ocean_name=str(pr.get("ocean_name", "Padding Ocean")),
            regrow_lost=bool(pr.get("regrow_lost", True)),
        ),
        baronies=map_config.barony_config(
            {
                "bookmark": ctx.config.bookmark_date,
                # [map] ck2_position_seeds is the documented flag (§A); a
                # [map.baronies] table may still override it explicitly.
                "ck2_position_seeds": raw.get("ck2_position_seeds", True),
                **dict(raw.get("baronies", {})),
            }
        ),
        terrain_map=dict(tr.get("map", {})),
        terrain_default=str(tr.get("default", "plains")),
        # `[map] province_terrain_history` (lane `province-terrain`). Read HERE
        # as well as in `ck2ck3.map.config.load`, for the reason the
        # `ck2_locator_positions` comment above gives: a key this CLI-facing
        # builder never reads is a silent no-op whatever the TOML says.
        # tests/test_map_terrain_history.py::test_cli_config_builder_reads_the_key
        # pins all three.
        terrain_history=bool(raw.get("province_terrain_history", True)),
        terrain_history_csv=Path(
            str(
                raw.get(
                    "terrain_history_csv", "mappings/terrain_history_overrides.csv"
                )
            )
        ),
        terrain_history_weak=tuple(
            str(v)
            for v in raw.get("terrain_history_weak_classes", ("plains", "farmlands"))
        ),
        lake_region_names=tuple(raw.get("lake_names", ("Lakes",))),
        tree_indices=tuple(int(v) for v in tr.get("tree_indices", ())),
        prefix=ctx.config.prefix,
        title_scaffolding=bool(raw.get("title_scaffolding", False)),
        # `[map] ck2_locator_positions` (lane `map-assets`). Read HERE as well
        # as in `ck2ck3.map.config.load`: a key this CLI-facing builder never
        # reads is a silent no-op whatever the TOML says - that is exactly how
        # `[map] colormap = false` was ignored for two builds (see below).
        # tests/test_map_locators.py::test_cli_config_builder_reads_the_key
        # pins it.
        ck2_locator_positions=bool(raw.get("ck2_locator_positions", True)),
        locator_offsets_csv=Path(
            str(raw.get("locator_offsets_csv", "mappings/locator_offsets.csv"))
        ),
        locator_offset_scale=float(raw.get("locator_offset_scale", 1.0)),
        locator_offset_mode=str(raw.get("locator_offset_mode", "median_radius")),
        strip_vanilla_foliage=bool(raw.get("strip_vanilla_foliage", True)),
        terrain_paint=bool(raw.get("terrain_paint", True)),
        terrain_paint_csv=Path(
            str(raw.get("terrain_paint_csv", "mappings/terrain_paint.csv"))
        ),
        terrain_paint_quantize=int(raw.get("terrain_paint_quantize", 16)),
        terrain_paint_format=str(raw.get("terrain_paint_format", "tga")),
        terrain_paint_scale=float(raw.get("terrain_paint_scale", 1.0)),
        # BUG FIXED (lane `colormap-fix`): this builder never read any of the
        # five `[map] colormap*` keys, so `configs/faerun.toml`'s own
        # `colormap = false` (set by the coordinator after the CK2-colormap
        # resample was found wrong, docs/step_map_paint.md §9.6) was silently
        # ignored by the real CLI pipeline - every run kept using the
        # `MapConfig` dataclass default (`colormap: bool = True`) and painted
        # the broken resample anyway. `ck2ck3.map.config.load` (the
        # standalone-TOML entry point) already read these correctly; only
        # this CLI-facing builder was missing them.
        colormap=bool(raw.get("colormap", True)),
        colormap_tints_csv=Path(
            str(raw.get("colormap_tints_csv", "mappings/colormap_tints.csv"))
        ),
        colormap_blur_sigma=float(raw.get("colormap_blur_sigma", 9.0)),
        colormap_scale=float(raw.get("colormap_scale", 0.25)),
        colormap_mips=bool(raw.get("colormap_mips", True)),
        # SAME BUG, SAME LANE (`trees-regional`, 2026-09-10): none of the
        # `[map] trees*` keys were read here either, so `[map] trees = false`
        # in configs/faerun.toml would have been a silent no-op exactly like
        # `colormap = false` was. Every key below is pinned by
        # tests/test_map_tree_mix.py::test_cli_config_builder_reads_the_tree_keys.
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
        mod_name=ctx.config.name,
        mod_version=ctx.config.version,
        supported_version=ctx.config.supported_version,
    )
