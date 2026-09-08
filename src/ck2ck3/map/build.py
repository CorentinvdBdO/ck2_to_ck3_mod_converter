"""The physical-map conversion: CK2 ``map/`` -> CK3 ``map_data/``.

Two front doors, one implementation:

* the CLI step ``ck2ck3.steps.map``, which passes a
  :class:`~ck2ck3.map.sink.ContextSink` so ``--dry-run`` works and every file
  lands in the run log;
* the standalone entry point below, which passes a
  :class:`~ck2ck3.map.sink.DirectorySink`::

      uv run python -m ck2ck3.map.build --config configs/faerun_map.toml

:func:`run` never touches the filesystem for output — everything goes through
the sink, as ``docs/cli.md`` requires.  Inputs are read directly, because the
CK2 bitmaps are 40 MB files that no parse-tree reader covers.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
import time
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

import numpy as np
from PIL import Image

from .. import csvloc
from . import (
    baronies,
    bootstrap,
    ck2read,
    ck2titles,
    flatmap,
    graphical,
    heightmap,
    holdings,
    idmap,
    locators,
    provinces,
    rivers,
    table,
    terrain,
    terrain_paint,
    writers,
)
from .config import MapConfig, load, plan_canvas
from .sink import DirectorySink, Sink

Image.MAX_IMAGE_PIXELS = None


def run(cfg: MapConfig, sink: Sink, *, skip_images: bool = False) -> dict:
    """Convert the physical map, writing through ``sink``. Returns a report dict.

    The report carries two things the caller decides what to do with:
    ``localisation`` (key -> text, for ``ctx.write_loc``) and ``_evidence``
    (filename -> CSV text, for the converter repo's ``docs/evidence/``, which is
    *not* part of the output mod).
    """
    src = cfg.ck2_map_dir
    mod = cfg.ck2_mod_dir or src.parent
    prefix = cfg.prefix
    report: dict = {}
    log = sink.info

    # ---------------------------------------------------------------- inputs
    log(f"reading CK2 map from {src}")
    ck2_provs = ck2read.read_definitions(src / "definition.csv")
    dm = ck2read.read_default_map(src / "default.map")
    climate = ck2read.read_climate(src / "climate.txt")
    islands = ck2read.read_island_regions(src / "island_region.txt")
    geo = ck2read.read_geographical_regions(src / "geographical_region.txt")
    adj = ck2read.read_adjacencies(src / "adjacencies.csv")
    tex_map = ck2read.read_terrain_texture_map(src / "terrain.txt")
    tree_indices = cfg.tree_indices or tuple(
        ck2read.parse_file(src / "default.map").ints("tree")
    )
    positions = ck2read.read_positions(src / "positions.txt")

    log(f"reading CK2 titles and province history from {mod}")
    tree = ck2titles.read_dir(mod / "common" / "landed_titles")
    province_history = holdings.read_dir(mod / "history" / "provinces")
    loc_names = _barony_names(mod, tree)
    log(
        f"{len(tree.county_baronies)} CK2 counties, "
        f"{sum(len(v) for v in tree.county_baronies.values())} defined baronies, "
        f"{len(province_history)} province history files"
    )

    # ----------------------------------------------------- canvas and raster
    src_ids_full = _source_id_raster(src / "provinces.bmp", ck2_provs)
    src_h, src_w = src_ids_full.shape
    crop = (
        provinces.painted_extent(src_ids_full)
        if cfg.provinces.crop_to_painted
        else None
    )
    canvas = plan_canvas(src_w, src_h, cfg.scale, crop)
    log(
        f"scale factor {canvas.factor:.6f} -> canvas {canvas.width}x{canvas.height} "
        f"(scaled {canvas.scaled_width}x{canvas.scaled_height}, "
        f"offset {canvas.offset_x},{canvas.offset_y}, "
        f"crop {canvas.crop_x0},{canvas.crop_y0}-{canvas.crop_x1},{canvas.crop_y1})"
    )
    if crop == (0, 0, src_w, src_h):
        log(
            "painted extent is the whole source bitmap, so the crop is a no-op "
            "(docs/map_scale.md §7)"
        )
    report["source"] = {"width": src_w, "height": src_h, "provinces": len(ck2_provs)}
    report["canvas"] = {
        "width": canvas.width,
        "height": canvas.height,
        "factor": canvas.factor,
        "offset_x": canvas.offset_x,
        "offset_y": canvas.offset_y,
        "crop": [canvas.crop_x0, canvas.crop_y0, canvas.crop_x1, canvas.crop_y1],
        "vanilla_km_per_px": cfg.scale.vanilla_km_per_px,
        "source_km_per_px": cfg.scale.source_km_per_px,
    }

    log("rasterising provinces (NEAREST on the id array)")
    raster = provinces.build_raster(
        src / "provinces.bmp",
        ck2_provs,
        canvas,
        min_pixels=cfg.provinces.min_pixels,
        regrow=cfg.provinces.regrow_lost,
    )
    log(
        f"{len(raster.surviving)} provinces survived, {len(raster.lost)} lost, "
        f"{len(raster.regrown)} regrown, "
        f"{len(raster.undefined_colours)} undefined colours in the bitmap"
    )
    for pid, (src_n, _) in sorted(raster.lost.items()):
        sink.warn(f"CK2 province {pid} dropped ({src_n} source pixels)")

    sea_ids = dm.sea_ids()
    lake_ids = dm.lake_ids(cfg.lake_region_names)
    river_ids = set(dm.major_rivers)
    ck2_names = {p.id: p.name for p in ck2_provs}
    ck2_water = sea_ids | lake_ids | river_ids
    ck2_land = raster.surviving - ck2_water

    # ------------------------------------------------- CK2 terrain code grid
    log("reading CK2 terrain")
    with Image.open(src / "terrain.bmp") as im:
        terrain_idx = np.asarray(im)
    trees = None
    if (src / "trees.bmp").exists():
        with Image.open(src / "trees.bmp") as im:
            trees = np.asarray(im)
    codes_src, code_names = terrain.ck2_category_codes(
        terrain_idx, tex_map, trees=trees, tree_indices=tree_indices
    )

    # ------------------------------------------------------- barony planning
    bcfg = cfg.baronies
    min_px = bcfg.min_pixels(canvas.width, canvas.height)
    selections = {
        pid: holdings.select(
            hist,
            bookmark=bcfg.bookmark,
            latest=bcfg.latest_bookmark,
            order=tree.county_baronies.get(hist.county or ""),
        )
        for pid, hist in sorted(province_history.items())
        if pid in ck2_land
    }
    selections = {pid: sel for pid, sel in selections.items() if sel.baronies}
    log(
        f"barony set at {'%d.%d.%d' % bcfg.bookmark} (union to "
        f"{'%d.%d.%d' % bcfg.latest_bookmark}): "
        f"{sum(len(s.baronies) for s in selections.values())} holdings in "
        f"{len(selections)} counties, min_barony_pixels={min_px}"
    )

    high_bias = _resize_bool(
        _codes_in(codes_src, code_names, terrain.CK2_HIGH_GROUND), canvas
    )
    water_bias = _water_bias(src, canvas, raster, ck2_water)
    seeds_csv = _repo_path(cfg, bcfg.seeds_csv)
    gazetteer_csv = _repo_path(cfg, bcfg.gazetteer_csv)
    plan = baronies.plan(
        raster_ids=raster.ids,
        canvas=canvas,
        selections=selections,
        tree=tree,
        cfg=replace(bcfg, min_barony_pixels=min_px),
        positions=positions,
        source_height=src_h,
        loc_names=loc_names,
        seed_overrides=baronies.read_seed_overrides(seeds_csv),
        gazetteer=baronies.read_gazetteer(gazetteer_csv),
        water_bias=water_bias,
        high_bias=high_bias,
        warn=sink.warn,
    )
    del water_bias, high_bias
    log(
        f"{len(plan.placed)} baronies placed, {len(plan.demoted)} demoted, "
        f"seeds {plan.seed_counts}"
    )
    report["baronies"] = {
        "placed": len(plan.placed),
        "demoted": len(plan.demoted),
        "counties": len(plan.by_province),
        "counties_with_demotions": len(plan.counties_with_demotions()),
        "min_barony_pixels": min_px,
        "orphan_pixels": plan.orphan_pixels,
        "bookmark": "%d.%d.%d" % bcfg.bookmark,
        "latest_bookmark": "%d.%d.%d" % bcfg.latest_bookmark,
        **{f"seed_{k}": v for k, v in sorted(plan.seed_counts.items())},
    }

    # -------------------------------------------------------------- id remap
    ids = idmap.build_with_baronies(
        ck2_provs,
        raster.surviving,
        plan,
        sea_ids=sea_ids,
        lake_ids=lake_ids,
        impassable_ids=set(),
        river_ids=river_ids,
        padding_rgb=cfg.provinces.ocean_rgb,
        padding_name=cfg.provinces.ocean_name,
    )
    ck3_raster = _paint_ck3_ids(raster, plan, ids)
    log(f"{len(ids.provinces)} CK3 provinces (padding ocean is id {ids.padding.id})")

    # ------------------------------------------- terrain vote, per CK3 province
    log("terrain majority vote (per CK3 province, target resolution)")
    codes_tgt = _resize_codes(codes_src, canvas)
    land_ck3 = {
        p.id for p in ids.provinces if not p.is_water and p.ck2_id is not None
    }
    tres = terrain.majority_terrain_codes(
        ck3_raster,
        codes_tgt,
        code_names,
        land_ids=land_ck3,
        mapping=cfg.terrain_map or None,
        default=cfg.terrain_default,
    )
    # kept for the terrain-paint pass below (same code grid, no second resize);
    # freed immediately when that pass will not run
    keep_codes_tgt = cfg.terrain_paint and not skip_images
    if not keep_codes_tgt:
        del codes_tgt
    impassable_ck3 = {
        pid
        for pid, cat in tres.category.items()
        if cat in terrain.CK2_IMPASSABLE_CATEGORIES
    }
    ids = replace(
        ids,
        provinces=[
            replace(p, is_impassable=p.id in impassable_ck3) for p in ids.provinces
        ],
    )
    log(f"terrain: {dict(tres.histogram.most_common())}")
    log(f"{len(impassable_ck3)} CK3 provinces are impassable_mountains")
    report["terrain"] = dict(tres.histogram)
    report["terrain_no_ck3_equivalent"] = len(tres.notes)
    report["terrain_fallbacks"] = len(tres.fallbacks)
    report["impassable"] = len(impassable_ck3)

    # a barony must never be impassable: it holds a holding
    bad = [p for p in ids.provinces if p.is_barony and p.is_impassable]
    if bad:
        sink.warn(
            f"{len(bad)} baronies voted impassable_mountains terrain; kept "
            "passable because they carry a holding"
        )
        impassable_ck3 -= {p.id for p in bad}
        ids = replace(
            ids,
            provinces=[
                replace(p, is_impassable=p.id in impassable_ck3) for p in ids.provinces
            ],
        )

    # CK3 demands that every land province either carries a barony title or is
    # impassable ("Province N has no associated title in common/landed_titles.
    # FIX THIS. Game will probably crash", 210 of them on the first In Game run,
    # 2026-09-08). CK2 wasteland (no title, any terrain: highlands, deserts,
    # islands) therefore becomes impassable_mountains whatever its terrain.
    untitled_land = {
        p.id for p in ids.provinces if not p.is_water and not p.is_barony
    }
    if untitled_land - impassable_ck3:
        log(
            f"{len(untitled_land - impassable_ck3)} untitled land provinces "
            "(CK2 wasteland) forced impassable_mountains"
        )
    impassable_ck3 |= untitled_land
    ids = replace(
        ids,
        provinces=[
            replace(p, is_impassable=p.id in impassable_ck3) for p in ids.provinces
        ],
    )
    report["impassable"] = len(impassable_ck3)

    water_ck3 = {p.id for p in ids.provinces if p.is_water}
    land_ck3 = {
        p.id for p in ids.provinces if not p.is_water and p.ck2_id is not None
    }
    water_mask = np.isin(ck3_raster, list(water_ck3))
    terrain_ck3 = {pid: key for pid, key in tres.by_province.items()}

    # ---------------------------------------------------------------- images
    if not skip_images:
        log("writing provinces.png")
        rgb = _to_rgb(ck3_raster, ids)
        sink.binary("map_data/provinces.png", lambda p: provinces.save_png(rgb, p))
        del rgb

        # traced before the heightmap: the detail pass below carves river
        # valleys along the same body pixels, so the (canvas-resolution) trace
        # is computed once here and reused for map_data/rivers.png later
        # rather than tracing twice.
        log("tracing and redrawing rivers")
        riv = rivers.render(src / "rivers.bmp", canvas, water_mask)
        report["rivers"] = rivers.stats(riv)
        _check_river_survival(sink, src / "rivers.bmp", riv, report)
        log(f"rivers: {report['rivers']}")

        log("building heightmap")
        heights = heightmap.build(src / "topology.bmp", canvas, cfg.heightmap)

        if cfg.heightmap_detail.enabled:
            from . import heightmap_detail

            log(f"synthesising heightmap detail (seed {cfg.heightmap_detail.seed}, "
                "docs/map_fidelity.md §4.2)")
            f = cfg.heightmap.resolution_factor
            terrain_code, terrain_keys = _terrain_code_grid(
                ck3_raster, terrain_ck3, cfg.terrain_default
            )
            river_body = (riv >= rivers.BODY_MIN) & (riv <= rivers.BODY_MAX)
            heights, detail_stats = heightmap_detail.apply(
                heights,
                land_mask=_nn_upsample(~water_mask, f),
                terrain_code=_nn_upsample(terrain_code, f),
                terrain_keys=terrain_keys,
                river_body=_nn_upsample(river_body, f),
                river_width_index=_nn_upsample(riv.astype(np.float32), f),
                km_per_px=cfg.scale.vanilla_km_per_px / f,
                water_level=cfg.heightmap.ck3_water_level,
                max_level=cfg.heightmap.ck3_max_level,
                cfg=cfg.heightmap_detail,
            )
            report["heightmap_detail"] = detail_stats
            log(
                f"heightmap detail: {detail_stats['distinct_values_before']} -> "
                f"{detail_stats['distinct_values_after']} distinct values "
                f"({detail_stats['elapsed_s']}s)"
            )

        sink.binary("map_data/heightmap.png", lambda p: heightmap.save_png(heights, p))

        log("packing heightmap")
        meta = _write_packed(sink, heights, cfg)
        report["heightmap"] = {
            "width": int(heights.shape[1]),
            "height": int(heights.shape[0]),
            "resolution_factor": cfg.heightmap.resolution_factor,
            "water_level": cfg.heightmap.ck3_water_level,
            **{k: v for k, v in meta.items() if isinstance(v, (int, float, str))},
        }
        log("painting the flat (paper) map")
        paper = flatmap.render(
            water_mask, heights, water_level=cfg.heightmap.ck3_water_level
        )
        sink.binary(flatmap.FLATMAP_PATH, lambda p: flatmap.save(paper, p))
        report["flatmap"] = {
            "width": int(paper.shape[1]),
            "height": int(paper.shape[0]),
            "format": "DXT1",
        }
        del paper, heights

        if cfg.terrain_paint:
            log("painting terrain (gfx/map/terrain/detail_index.tga + "
                "detail_intensity.tga)")
            paint = terrain_paint.build_layers(
                codes_tgt,
                code_names,
                material_map=terrain_paint.read_material_map(
                    _repo_path(cfg, cfg.terrain_paint_csv)
                ),
                ordinals=terrain_paint.material_ordinals(
                    (cfg.ck3_game_dir or Path())
                    / "gfx" / "map" / "terrain" / "materials.settings"
                ),
                mapping=cfg.terrain_map or None,
                default=cfg.terrain_default,
                quantize=cfg.terrain_paint_quantize,
                warn=sink.warn,
            )
            sink.binary(
                terrain_paint.DETAIL_INDEX_PATH,
                lambda p: terrain_paint.save_tga(paint.index, p),
            )
            sink.binary(
                terrain_paint.DETAIL_INTENSITY_PATH,
                lambda p: terrain_paint.save_tga(paint.intensity, p),
            )
            report["terrain_paint"] = {
                "classes": paint.classes,
                "missing_material": paint.missing_material,
                "missing_ordinal": paint.missing_ordinal,
                "quantize": paint.quantize,
            }
            log(f"terrain paint: {dict(sorted(paint.classes.items()))}")
            del paint
        if keep_codes_tgt:
            del codes_tgt

        sink.binary("map_data/rivers.png", lambda p: rivers.save_png(riv, p))
        del riv

    # -------------------------------------------------------- text map files
    log("writing map_data text files")
    keys = bootstrap.unique_keys(ids.provinces)
    sink.text(
        "map_data/definition.csv",
        writers.render_definition_csv(
            ids.provinces, bootstrap.definition_names(ids.provinces, keys)
        ),
    )
    sink.text(
        "map_data/default.map",
        writers.render_default_map(ids, sea_zone_names=_sea_zone_names(dm, ids)),
    )
    dropped_adj: list[str] = []
    centroids = _centroids(ck3_raster, ids)
    adj_text, kept_adj = writers.render_adjacencies_csv(
        adj, ids, dropped_log=dropped_adj, endpoint=_endpoint_picker(ids, centroids)
    )
    sink.text("map_data/adjacencies.csv", adj_text)
    for message in dropped_adj:
        sink.warn(message)
    # ------------------------------------------------- map object locators
    # Without these the game keeps vanilla's coordinates for every id vanilla
    # also defines, and 3179 of Faerun's 3694 holdings drew a median 3040 px
    # from their own land (docs/evidence/map_ui_research.md §1.3).  The engine
    # only fills *gaps*, so a partial override is worse than none.
    locator_land = {
        p.id for p in ids.provinces if not p.is_water and not p.is_impassable
    }
    locator_passable = {p.id for p in ids.provinces if not p.is_impassable}
    locator_xy = {pid: (x, y) for pid, (y, x) in centroids.items()}
    for rel, text in locators.render_all(
        locator_xy,
        canvas.height,
        land_ids=locator_land,
        passable_ids=locator_passable,
    ).items():
        sink.text(rel, text)
    log(
        f"locators: {len(locators.LOCATOR_SPECS)} files, "
        f"{len(locator_land)} land / {len(locator_passable)} passable provinces"
    )
    foliage = (
        locators.render_foliage_stubs(cfg.ck3_game_dir)
        if cfg.strip_vanilla_foliage
        else {}
    )
    for rel, text in foliage.items():
        sink.text(rel, text)
    if foliage:
        log(f"{len(foliage)} vanilla foliage generators emptied")
    report["locators"] = {
        "files": len(locators.LOCATOR_SPECS),
        "land": len(locator_land),
        "passable": len(locator_passable),
        "foliage_stubs": len(foliage),
    }

    # ------------------------------------------------------ the 3D map table
    tables = table.render_all(
        cfg.ck3_game_dir, width=canvas.width, height=canvas.height
    )
    if not tables:
        sink.warn(
            "no vanilla gfx/map/map_object_data/map_table_*.txt found at "
            f"{cfg.ck3_game_dir}: the map table keeps vanilla's size and a map "
            "taller than 4608 px overhangs it (docs/evidence/map_ui_research.md §3)"
        )
    for rel, text in tables.items():
        sink.text(rel, text)
    report["map_table"] = {
        "files": len(tables),
        "scale": round(table.scale_factor(canvas.width, canvas.height), 4),
    }

    sink.text("map_data/climate.txt", writers.render_climate(climate, ids))
    sink.text("map_data/island_region.txt", writers.render_island_region(islands, ids))
    graphical_buckets = graphical.assign(
        history=province_history,
        idmap=ids,
        land_ck3=land_ck3,
        graphical_culture_of_culture=ck2read.read_graphical_culture_of_culture(
            mod / "common" / "cultures"
        ),
        region_of_gfx=graphical.region_of_ck2_gfx(
            _building_gfx_of_ck2_gfx(_repo_path(cfg, Path("overrides") / "gfx_of_culture_group.csv"))
        ),
        bookmark=cfg.baronies.bookmark,
    )
    log(
        "graphical regions: "
        + ", ".join(
            f"{name}={len(graphical_buckets.get(name, ()))}"
            for name, _ in graphical.GRAPHICAL_REGIONS
        )
    )
    vanilla_regions = ck2read.read_ck3_region_names(
        (cfg.ck3_game_dir or Path()) / "map_data" / "geographical_regions"
    )
    if not vanilla_regions:
        sink.warn(
            "no CK3 map_data/geographical_regions found at "
            f"{cfg.ck3_game_dir}: vanilla region names are not re-declared, and "
            "a vanilla GUI lookup of one crashes the frontend "
            "(docs/evidence/game_load_2026-09-08.md)"
        )
    sink.text(
        f"map_data/geographical_regions/{prefix}_regions.txt",
        writers.render_geographical_regions(
            geo, ids, graphical_buckets, vanilla_regions
        ),
    )
    sink.text(
        "map_data/continent.txt",
        writers.render_continent(name=f"{prefix}_continent", province_ids=land_ck3),
    )
    sink.text("map_data/seasons.txt", writers.render_seasons())
    sink.text("map_data/positions.txt", writers.render_positions_stub(canvas))
    sink.text(
        f"common/province_terrain/{prefix}_province_terrain.txt",
        writers.render_province_terrain(terrain_ck3, default=cfg.terrain_default),
    )
    report["adjacencies"] = {"kept": kept_adj, "dropped": len(dropped_adj)}

    # ------------------------------------------------------------ bootstrap
    sink.text(
        f"common/defines/{prefix}_defines.txt",
        bootstrap.render_defines(width=canvas.width, height=canvas.height),
    )
    sink.text(
        f"common/defines/graphic/{prefix}_graphics.txt",
        bootstrap.render_camera_defines(width=canvas.width, height=canvas.height),
    )
    for rel, text in bootstrap.render_empty_replacements().items():
        sink.text(rel, text)
    # The throwaway one-barony-per-province title scaffolding this step used to
    # write is gone: lane `titles-history` owns common/landed_titles,
    # history/titles and history/provinces and writes the real Faerun tree
    # there (steps `titles` and `history_titles`).  `cfg.title_scaffolding`
    # brings it back for a map-only run - see docs/step_titles.md.
    n_titles = n_hist = 0
    if cfg.title_scaffolding:
        log("writing throwaway title scaffolding")
        titles_text, n_titles = bootstrap.render_landed_titles(ids.provinces, keys)
        sink.text(f"common/landed_titles/{prefix}_landed_titles.txt", titles_text)
        hist_text, n_hist = bootstrap.render_province_history(ids.provinces)
        sink.text(f"history/provinces/{prefix}_provinces.txt", hist_text)
        sink.text(
            f"history/titles/{prefix}_titles.txt", bootstrap.render_title_history()
        )
    report["bootstrap"] = {"baronies": n_titles, "province_history": n_hist}
    report["localisation"] = bootstrap.localisation_entries(
        ids.provinces, keys, loc_names=loc_names
    )

    # --------------------------------------------------------------- report
    report["provinces"] = {
        "ck3_total": len(ids.provinces),
        "land": len(land_ck3),
        "baronies": len(ids.baronies()),
        "sea": sum(1 for p in ids.provinces if p.is_sea),
        "lake": sum(1 for p in ids.provinces if p.is_lake),
        "river": sum(1 for p in ids.provinces if p.is_river),
        "impassable": sum(1 for p in ids.provinces if p.is_impassable),
        "lost": len(raster.lost),
        "regrown": len(raster.regrown),
    }
    report["_evidence"] = {
        "province_id_map.csv": idmap.render_id_map_csv(ids),
        "lost_provinces.csv": provinces.render_lost_report(raster, ck2_names),
        "barony_set.csv": baronies.render_barony_set_csv(
            plan, province_names=ck2_names
        ),
        "nonbarony_holdings.csv": holdings.render_nonbarony_csv(
            selections, names=ck2_names
        ),
    }
    report["_plan"] = plan
    report["_ids"] = ids
    report["_canvas"] = canvas
    report["_raster"] = ck3_raster
    return report


# --------------------------------------------------------------------------- #
# helpers the barony split needs
# --------------------------------------------------------------------------- #
def _barony_names(mod: Path, tree: ck2titles.Ck2TitleTree) -> dict[str, str]:
    """CK2 barony key -> localised English name, for gazetteer matching.

    Falls back to nothing rather than to a guess: a barony with no
    localisation simply cannot be matched by name, and the next seed source
    takes over.
    """
    loc_dir = mod / "localisation"
    if not loc_dir.is_dir():
        return {}
    merged, _ = csvloc.read_ck2_loc(mod)
    return {
        key: merged[key]
        for key in tree.titles
        if key.startswith("b_") and merged.get(key)
    }


def _building_gfx_of_ck2_gfx(path: Path) -> dict[str, str]:
    """The two columns of ``overrides/gfx_of_culture_group.csv`` the map needs.

    The `cultures` step reads the same file through `ck2ck3.overrides`; the map
    pipeline has no `Context`, so it reads the two columns itself rather than
    growing a dependency on the step layer.
    """
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    with path.open("r", encoding="utf-8", newline="") as fh:
        rows = csv.DictReader(line for line in fh if not line.lstrip().startswith("#"))
        for row in rows:
            key = (row.get("ck2_graphical_culture") or "").strip()
            value = (row.get("building_gfx") or "").strip()
            if key and value:
                out[key] = value
    return out


def _repo_path(cfg: MapConfig, rel: Path) -> Path:
    if rel.is_absolute():
        return rel
    base = cfg.repo_dir or Path.cwd()
    return base / rel


def _codes_in(
    codes: np.ndarray, names: Sequence[str], wanted: set[str]
) -> np.ndarray:
    """Boolean grid: True where the pixel's CK2 terrain category is in ``wanted``."""
    keep = [i for i, n in enumerate(names) if n in wanted]
    return np.isin(codes, keep) if keep else np.zeros(codes.shape, dtype=bool)


def _resize_bool(mask: np.ndarray, canvas) -> np.ndarray:
    """NEAREST resize of a source-resolution boolean grid onto the canvas."""
    return provinces._resize_ids(mask.astype(np.int32), canvas).astype(bool)


def _resize_codes(codes: np.ndarray, canvas) -> np.ndarray:
    """NEAREST resize of the terrain code grid onto the canvas."""
    return provinces._resize_ids(codes.astype(np.int32), canvas).astype(np.uint16)


def _water_bias(
    src: Path, canvas, raster: provinces.ProvinceRaster, ck2_water: set[int]
) -> np.ndarray:
    """Land pixels a city seed should prefer: next to water, or on a river.

    Coast is computed on the CK2 id raster at *target* resolution (a land pixel
    with a water pixel or padding among its four neighbours) and unioned with
    the rescaled ``rivers.bmp`` mask, dilated by one pixel so a bank counts as
    river access.
    """
    ids = raster.ids
    water = np.isin(ids, list(ck2_water)) | (ids == provinces.PADDING)
    coast = np.zeros(water.shape, dtype=bool)
    coast[1:, :] |= water[:-1, :]
    coast[:-1, :] |= water[1:, :]
    coast[:, 1:] |= water[:, :-1]
    coast[:, :-1] |= water[:, 1:]
    coast &= ~water
    river_bmp = src / "rivers.bmp"
    if river_bmp.exists():
        with Image.open(river_bmp) as im:
            river = rivers.river_mask(np.asarray(im))
        rmask = _resize_bool(river, canvas)
        near = rmask.copy()
        near[1:, :] |= rmask[:-1, :]
        near[:-1, :] |= rmask[1:, :]
        near[:, 1:] |= rmask[:, :-1]
        near[:, :-1] |= rmask[:, 1:]
        coast |= near & ~water
    return coast


def _paint_ck3_ids(
    raster: provinces.ProvinceRaster, plan, ids: idmap.IdMap
) -> np.ndarray:
    """CK3 province id per canvas pixel: barony labels first, CK2 ids elsewhere."""
    labels = plan.labels
    max_ck2 = max(ids.ck2_to_ck3) if ids.ck2_to_ck3 else 0
    lut = np.zeros(max_ck2 + 1, dtype=np.int32)
    for ck2_id, ck3_id in ids.ck2_to_ck3.items():
        lut[ck2_id] = ck3_id
    out = lut[np.clip(raster.ids, 0, max_ck2)]
    out[raster.ids == provinces.PADDING] = ids.padding.id
    if labels is not None and ids.label_to_id:
        max_label = max(ids.label_to_id)
        llut = np.zeros(max_label + 1, dtype=np.int32)
        for label, ck3_id in ids.label_to_id.items():
            llut[label] = ck3_id
        painted = labels > 0
        out[painted] = llut[np.clip(labels[painted], 0, max_label)]
    return out


def _to_rgb(ck3_raster: np.ndarray, ids: idmap.IdMap) -> np.ndarray:
    """``provinces.png`` pixels, straight off the CK3 id raster."""
    max_id = max(p.id for p in ids.provinces)
    lut = np.zeros((max_id + 1, 3), dtype=np.uint8)
    lut[0] = ids.padding.rgb
    for p in ids.provinces:
        lut[p.id] = p.rgb
    return lut[np.clip(ck3_raster, 0, max_id)]


def _centroids(ck3_raster: np.ndarray, ids: idmap.IdMap) -> dict[int, tuple[float, float]]:
    """CK3 province id -> (y, x) pixel centroid, for the strait endpoint rule."""
    flat = ck3_raster.reshape(-1)
    w = ck3_raster.shape[1]
    n = int(flat.max()) + 1
    counts = np.bincount(flat, minlength=n).astype(np.float64)
    idx = np.arange(flat.size, dtype=np.int64)
    sy = np.bincount(flat, weights=idx // w, minlength=n)
    sx = np.bincount(flat, weights=idx % w, minlength=n)
    out: dict[int, tuple[float, float]] = {}
    for p in ids.provinces:
        if counts[p.id]:
            out[p.id] = (sy[p.id] / counts[p.id], sx[p.id] / counts[p.id])
    return out


def _endpoint_picker(ids: idmap.IdMap, centroids: dict[int, tuple[float, float]]):
    """Pick which barony of a split CK2 province a strait attaches to.

    CK2 ``adjacencies.csv`` carries no coordinates (all four columns are ``-1``
    in Faerûn), so "the barony containing the adjacency endpoint pixel" has to
    be derived.  The crossing goes *from -> through -> to*, and ``through`` is
    the water province being crossed, so the endpoint is the barony of the
    county whose centroid is nearest that water province's centroid: the strait
    lands on the side of the county that faces the water.  Falls back to the
    other endpoint's centroid when the crossing has no ``through``.
    """

    def pick(ck2_id: int, toward_ck2: int) -> int | None:
        options = ids.all_ck3(ck2_id)
        if len(options) <= 1:
            return options[0] if options else None
        target = centroids.get(ids.ck3(toward_ck2) or -1)
        if target is None:
            return options[0]
        best, best_d = options[0], None
        for cid in options:
            c = centroids.get(cid)
            if c is None:
                continue
            d = (c[0] - target[0]) ** 2 + (c[1] - target[1]) ** 2
            if best_d is None or d < best_d:
                best, best_d = cid, d
        return best

    return pick


def _terrain_code_grid(
    ck3_raster: np.ndarray, terrain_ck3: dict[int, str], default: str
) -> tuple[np.ndarray, list[str]]:
    """Per-pixel CK3 terrain-key index, for the heightmap detail pass's gain.

    Reuses the per-province majority-vote result (``terrain_ck3``) rather than
    reclassifying pixels from ``terrain.bmp`` itself, so this stays consistent
    with ``common/province_terrain`` by construction and never touches the
    terrain-paint/vote code lane ``map-terrain-paint`` owns.
    """
    keys = sorted(set(terrain_ck3.values()) | {default})
    index = {k: i for i, k in enumerate(keys)}
    max_id = int(ck3_raster.max()) if ck3_raster.size else 0
    lut = np.full(max_id + 1, index[default], dtype=np.uint8)
    for pid, key in terrain_ck3.items():
        if 0 <= pid <= max_id:
            lut[pid] = index.get(key, index[default])
    return lut[np.clip(ck3_raster, 0, max_id)], keys


def _nn_upsample(a: np.ndarray, factor: int) -> np.ndarray:
    """Nearest-neighbour upsample, for ``[map.heightmap] resolution_factor``.

    The province raster (and everything derived from it) is always at canvas
    resolution; the heightmap is canvas resolution times ``resolution_factor``
    (1 by default, 2 for a vanilla-sized heightmap). A no-op at 1.
    """
    if factor == 1:
        return a
    return np.repeat(np.repeat(a, factor, axis=0), factor, axis=1)


def _write_packed(sink: Sink, heights: np.ndarray, cfg: MapConfig) -> dict:
    """Pack the heightmap into the atlas pair the game actually loads.

    ``packed_heightmap.write_packed`` produces three files that must sit beside
    each other, so it gets one ``sink.binary`` call on the descriptor and writes
    its two siblings next to the path it is handed.  The siblings are recorded
    afterwards so the run log still names them.
    """
    from . import packed_heightmap

    meta: dict = {}

    def save(path: Path) -> None:
        meta.update(
            packed_heightmap.write_packed(
                heights, path.parent, tile_size=cfg.heightmap.tile_size
            )
        )

    sink.binary("map_data/heightmap.heightmap", save)
    if sink.dry_run:
        return {"tile_size": cfg.heightmap.tile_size}
    return meta


def _check_river_survival(
    sink: Sink, src_bmp: Path, out: np.ndarray, report: dict
) -> None:
    """Warn if a river source / merge / split did not reach the output."""
    with Image.open(src_bmp) as im:
        before = rivers.count_specials(np.asarray(im))
    after = rivers.count_specials(out)
    report["rivers_specials"] = {"ck2": before, "ck3": after}
    for key, n in before.items():
        if after[key] < n:
            sink.warn(
                f"rivers: {n - after[key]} of {n} {key} did not survive "
                "(they fall on a pixel the province map says is water)"
            )


def _source_id_raster(bmp: Path, ck2_provs: list[ck2read.Ck2Province]) -> np.ndarray:
    """CK2 province ids at source resolution (for the painted-extent crop)."""
    with Image.open(bmp) as im:
        rgb = np.asarray(im.convert("RGB"))
    lookup = {(p.rgb[0] << 16) | (p.rgb[1] << 8) | p.rgb[2]: p.id for p in ck2_provs}
    ids, _ = provinces._keys_to_ids(provinces.rgb_key(rgb), lookup)
    return ids


def _sea_zone_names(dm: ck2read.Ck2DefaultMap, ids: idmap.IdMap) -> dict[int, str]:
    """CK3 sea province id -> the CK2 sea-zone comment it came from."""
    out: dict[int, str] = {}
    for (a, b), name in zip(dm.sea_zones, dm.sea_zone_names):
        for ck2_id in range(a, b + 1):
            ck3 = ids.ck3(ck2_id)
            if ck3 is not None:
                out[ck3] = name
    return out


# --------------------------------------------------------------------------- #
# standalone entry point
# --------------------------------------------------------------------------- #
def _stamp(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", required=True, help="path to a map config TOML")
    ap.add_argument(
        "--out",
        help="override output.mod_dir (needed from a git worktree, where the "
        "config's relative path points somewhere else)",
    )
    ap.add_argument("--ck2-map-dir", help="override input.ck2_map_dir")
    ap.add_argument(
        "--skip-images",
        action="store_true",
        help="only write the text files (fast; for iterating on formats)",
    )
    ap.add_argument("--dry-run", action="store_true", help="write nothing")
    args = ap.parse_args(argv)

    cfg = load(args.config)
    if args.out:
        cfg = replace(cfg, out_mod_dir=Path(args.out).resolve())
    if args.ck2_map_dir:
        cfg = replace(cfg, ck2_map_dir=Path(args.ck2_map_dir).resolve())

    sink = DirectorySink(cfg.out_mod_dir, dry_run=args.dry_run)
    sink.info = _stamp  # type: ignore[method-assign]
    report = run(cfg, sink, skip_images=args.skip_images)

    # Under the CLI these two belong elsewhere: descriptor.mod to the
    # `descriptor` step, localisation to ctx.write_loc. The standalone path has
    # neither, so it writes them itself.
    sink.text(
        "descriptor.mod",
        bootstrap.render_descriptor(
            name=cfg.mod_name,
            version=cfg.mod_version,
            supported_version=cfg.supported_version,
        ),
    )
    loc = report.pop("localisation", {})
    sink.text(
        f"localization/english/{cfg.prefix}_titles_l_english.yml",
        "l_english:\n" + "".join(f' {k}: "{v}"\n' for k, v in loc.items()),
        bom=True,
    )

    evidence = report.pop("_evidence", {})
    for key in [k for k in report if k.startswith("_")]:
        report.pop(key)  # numpy arrays and dataclasses: not JSON, not the report
    if not args.dry_run:
        cfg.evidence_dir.mkdir(parents=True, exist_ok=True)
        for name, text in evidence.items():
            (cfg.evidence_dir / name).write_text(text, encoding="utf-8", newline="")
        path = cfg.evidence_dir / "map_build_report.json"
        path.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        _stamp(f"report -> {path}")
    _stamp(f"{len(sink.written)} files written, {len(sink.warnings)} warnings")
    return 0


if __name__ == "__main__":
    sys.exit(main())
