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
from collections import Counter
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
    colormap,
    flatmap,
    graphical,
    heightmap,
    holdings,
    idmap,
    locators,
    provinces,
    rivers,
    surround,
    table,
    terrain,
    terrain_history,
    paint_edges,
    terrain_paint,
    tree_scatter,
    water,
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
    # lane `paint-edges`: trees.bmp is 1/8 resolution (23.2 km per tree pixel
    # on Faerun), and `np.repeat`-ing it is what makes a forest read as Lego
    # at close zoom.  Two masks, because the converter has always used two
    # different index sets and they disagree: `tree_indices` is CK2's own
    # `tree = { ... }` list from default.map (the terrain/paint promotion to
    # `forest`), while the tree SCATTER has always taken any non-zero index.
    # Both are now built the same smooth way (docs/step_map_paint.md §10.3).
    forest_src_mask = None
    scatter_src_mask = None
    if trees is not None and cfg.trees_mask_smooth:
        if tree_indices:
            forest_src_mask = (
                paint_edges.forest_coverage(
                    trees,
                    tree_indices,
                    terrain_idx.shape,
                    smooth=True,
                    blur_px=cfg.trees_mask_blur_px,
                )
                >= cfg.trees_mask_threshold
            )
        scatter_src_mask = (
            paint_edges.forest_coverage(
                trees,
                sorted({int(v) for v in np.unique(trees) if int(v) != 0}),
                terrain_idx.shape,
                smooth=True,
                blur_px=cfg.trees_mask_blur_px,
            )
            >= cfg.trees_mask_threshold
        )
    codes_src, code_names = terrain.ck2_category_codes(
        terrain_idx, tex_map, trees=trees, tree_indices=tree_indices,
        forest_mask=forest_src_mask,
    )
    if forest_src_mask is not None:
        report["trees_mask"] = {
            "smooth": True,
            "threshold": cfg.trees_mask_threshold,
            "blur_px": cfg.trees_mask_blur_px,
            "forest_src_px": int(forest_src_mask.sum()),
            "scatter_src_px": int(scatter_src_mask.sum()),
        }
        log(
            "smooth trees.bmp mask (bilinear + threshold "
            f"{cfg.trees_mask_threshold}): {int(forest_src_mask.sum())} source "
            f"px promoted to forest, {int(scatter_src_mask.sum())} eligible "
            "for the tree scatter"
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
    # kept for the terrain-paint and colormap passes below (both want the
    # same canvas-resolution CK2 code grid, no second resize); freed
    # immediately when neither pass will run
    keep_codes_tgt = (cfg.terrain_paint or cfg.colormap) and not skip_images
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

    # ------------------------------ CK2 province-history `terrain = X` override
    # In CK2 that line IS the province's gameplay terrain and the bitmap
    # majority above is only the fallback, so it wins here too
    # (docs/step_map_terrain.md). Applied AFTER impassability is decided, on
    # purpose: `impassable_ck3` stays a pure terrain.bmp property, exactly as
    # before this lane.
    terrain_bitmap_only = dict(terrain_ck3)
    if cfg.terrain_history:
        rules = terrain_history.read_rules(
            _repo_path(cfg, cfg.terrain_history_csv)
        )
        overrides = {
            pid: cat
            for pid, hist in province_history.items()
            if (cat := hist.terrain_at(cfg.baronies.bookmark))
        }
        capitals = {
            b.key: b.is_capital
            for bs in plan.by_province.values()
            for b in bs
        }
        refs = [
            terrain_history.BaronyRef(
                ck3_id=p.id,
                ck2_id=p.ck2_id,
                # a land province that was never split IS its own county
                is_capital=capitals.get(p.barony or "", True),
                barony=p.barony or "",
                county=p.county or "",
            )
            for p in ids.provinces
            if not p.is_water and p.ck2_id is not None
        ]
        hres = terrain_history.apply_overrides(
            terrain_ck3,
            refs=refs,
            overrides=overrides,
            rules=rules,
            weak_classes=cfg.terrain_history_weak,
        )
        terrain_ck3 = hres.terrain
        report["terrain_history"] = {
            "enabled": True,
            "overrides_in_ck2_history": len(overrides),
            **hres.summary(),
        }
        report["terrain"] = dict(Counter(terrain_ck3.values()))
        log(
            f"province-history terrain override: {len(overrides)} CK2 counties "
            f"declare one, {hres.summary()['counties_with_override']} usable; "
            f"{hres.changed} CK3 provinces changed "
            f"(capital {hres.outcomes['applied_capital']}, "
            f"non-capital-weak {hres.outcomes['applied_weak_bitmap']}, "
            f"kept strong bitmap {hres.outcomes['kept_strong_bitmap']}, "
            f"already agreed {hres.outcomes['already_agreed']}, "
            f"unmapped {sum(hres.unmapped.values())})"
        )
        if hres.unmapped:
            sink.warn(
                "CK2 history terrain categories with no row in "
                f"{cfg.terrain_history_csv}: "
                + ", ".join(f"{k} ({v})" for k, v in sorted(hres.unmapped.items()))
                + " - bitmap majority kept"
            )
        log(f"terrain after override: {dict(Counter(terrain_ck3.values()).most_common())}")
        # How far this moves the two passes that read the per-PROVINCE terrain
        # class rather than the per-pixel one: the heightmap detail gain and
        # the tree mesh choice (both go through `_terrain_code_grid`).  The
        # terrain PAINT is per-pixel and does not move at all
        # (docs/step_map_terrain.md §5).
        changed_ids = [
            pid for pid, key in terrain_ck3.items() if key != terrain_bitmap_only[pid]
        ]
        moved_px = (
            int(np.isin(ck3_raster, changed_ids).sum()) if changed_ids else 0
        )
        report["terrain_history"]["class_grid_pixels_moved"] = moved_px
        report["terrain_history"]["class_grid_pixels_moved_share"] = round(
            moved_px / float(ck3_raster.size), 6
        )
        log(
            f"terrain class grid (heightmap detail + tree meshes): "
            f"{moved_px} px moved "
            f"({100 * moved_px / float(ck3_raster.size):.2f} % of the canvas)"
        )
        _terrain_history_evidence = terrain_history.render_evidence_csv(hres)
    else:
        report["terrain_history"] = {"enabled": False}
        _terrain_history_evidence = None

    # ---------------------------------------------------------------- images
    paint_warp = None
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

        if cfg.heightmap.deepen_sea:
            # CK2 carries almost no bathymetry; CK3 paints shallow water as
            # sand (docs/step_map_heightmap.md, 2026-09-10 in-game check).
            log(f"deepening the sea (floor {cfg.heightmap.sea_floor}, "
                f"shelf {cfg.heightmap.sea_shelf_px} px)")
            before = heights[heights <= cfg.heightmap.ck3_water_level]
            heights = heightmap.deepen_sea(
                heights,
                cfg.heightmap.ck3_water_level,
                shelf_px=cfg.heightmap.sea_shelf_px,
                floor=cfg.heightmap.sea_floor,
            )
            after = heights[heights <= cfg.heightmap.ck3_water_level]
            report["sea_floor"] = {
                "median_before": int(np.median(before)) if before.size else 0,
                "median_after": int(np.median(after)) if after.size else 0,
                "water_level": int(cfg.heightmap.ck3_water_level),
                "shelf_px": int(cfg.heightmap.sea_shelf_px),
            }
            log(f"sea floor: median {report['sea_floor']['median_before']} -> "
                f"{report['sea_floor']['median_after']} (water level "
                f"{cfg.heightmap.ck3_water_level})")

        if cfg.heightmap_detail.enabled:
            from . import heightmap_detail

            # every switched key is named in the run log, so `last_run.md` is
            # proof the config was actually read -- a `[map]` key spelled or
            # placed wrong is silently ignored otherwise
            log(f"synthesising heightmap detail (seed {cfg.heightmap_detail.seed}, "
                f"deterrace={cfg.heightmap_detail.deterrace_mode}"
                f"@sigma {cfg.heightmap_detail.deterrace_sigma_px}px"
                f"/cliff {cfg.heightmap_detail.cliff_step_levels} levels, "
                f"relief={cfg.heightmap_detail.relief_mode}"
                f"@{cfg.heightmap_detail.erosion_iterations}x"
                f"{cfg.heightmap_detail.erosion_accum_iterations}, "
                f"target={cfg.heightmap_detail.target_mode}, "
                f"fill>={cfg.heightmap_detail.fill_min_cycles_per_km} c/km, "
                f"slope ceiling {cfg.heightmap_detail.erosion_slope_ceiling_steps}"
                " steps; docs/step_map_heightmap.md §2b/§2c/§2d)")
            f = cfg.heightmap.resolution_factor
            # every `*_px` key is a *canvas*-pixel length, so at
            # resolution_factor > 1 it has to be re-expressed in heightmap
            # pixels or the same number means half the distance on the
            # ground: a sigma 2.2 px de-terrace at 2x blurs 1.6 km instead
            # of 3.3 km and leaves the transfer curve's risers behind
            # (docs/step_map_heightmap.md §2e).
            detail_cfg = (
                cfg.heightmap_detail if f == 1 else replace(
                    cfg.heightmap_detail,
                    deterrace_sigma_px=cfg.heightmap_detail.deterrace_sigma_px * f,
                    gain_blur_px=cfg.heightmap_detail.gain_blur_px * f,
                    coast_smooth_px=cfg.heightmap_detail.coast_smooth_px * f,
                )
            )
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
                cfg=detail_cfg,
            )
            detail_stats["resolution_factor"] = f
            detail_stats["deterrace_sigma_px_used"] = detail_cfg.deterrace_sigma_px
            report["heightmap_detail"] = detail_stats
            log(
                f"heightmap detail: {detail_stats['distinct_values_before']} -> "
                f"{detail_stats['distinct_values_after']} distinct values, "
                f"{detail_stats['land_pct_on_clamp_floor']} % of land on the "
                f"water+1 clamp floor "
                f"({detail_stats['excursion_limited_pct_of_land']} % of land "
                f"had its offset saturated into the headroom) "
                f"({detail_stats['elapsed_s']}s)"
            )

        # lane `paint-edges`: the terrain-class boundary should follow the
        # ground, not the CK2 pixel grid.  Derived HERE because `heights` is
        # deleted a few lines below and the paint pass runs after that; the
        # field is two int8 canvas planes (112 MB), not a copy of the
        # heightmap.  Displacement is bounded by construction
        # (docs/step_map_paint.md §10.2).
        if (
            cfg.terrain_paint
            and cfg.terrain_paint_soft_edges
            and cfg.terrain_paint_relief_shift_px > 0
        ):
            paint_warp = paint_edges.relief_warp(
                heights,
                (canvas.height, canvas.width),
                shift_px=cfg.terrain_paint_relief_shift_px,
                sigma_px=cfg.terrain_paint_relief_sigma_px,
                land_mask=~water_mask,
                gradient_percentile=cfg.terrain_paint_relief_percentile,
            )
            moved = int(((paint_warp[0] != 0) | (paint_warp[1] != 0)).sum())
            report["paint_relief_warp"] = {
                "shift_px": cfg.terrain_paint_relief_shift_px,
                "sigma_px": cfg.terrain_paint_relief_sigma_px,
                "percentile": cfg.terrain_paint_relief_percentile,
                "displaced_px": moved,
                "displaced_share": round(moved / float(water_mask.size), 6),
            }
            log(
                "relief warp for the paint edges: max "
                f"{cfg.terrain_paint_relief_shift_px} canvas px, {moved} px "
                f"({100 * moved / float(water_mask.size):.1f} % of the canvas) "
                "displaced"
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

        if cfg.colormap:
            tint_map = colormap.read_tint_map(_repo_path(cfg, cfg.colormap_tints_csv))
            if not tint_map:
                sink.warn(
                    f"[map] colormap = true but {cfg.colormap_tints_csv} is "
                    "missing or empty; shipping a flat default-grey colormap"
                )
            log("painting gfx/map/terrain/colormap.dds (measured terrain tint)")
            cm = colormap.build_from_terrain(
                codes_tgt,
                code_names,
                tint_map=tint_map,
                water_mask=water_mask,
                mapping=cfg.terrain_map or None,
                default=cfg.terrain_default,
                blur_sigma=cfg.colormap_blur_sigma,
                warn=sink.warn,
            )
            land_px = cm[~water_mask].astype(np.float64)
            water_px = cm[water_mask].astype(np.float64)
            report["colormap"] = {
                "land_mean_rgb": [round(float(x), 1) for x in land_px.mean(axis=0)],
                "land_std_rgb": [round(float(x), 1) for x in land_px.std(axis=0)],
                "water_mean_rgb": [round(float(x), 1) for x in water_px.mean(axis=0)],
                "water_std_rgb": [round(float(x), 1) for x in water_px.std(axis=0)],
                "blur_sigma": cfg.colormap_blur_sigma,
            }
            cm = colormap.downsample(cm, cfg.colormap_scale)
            sink.binary(
                colormap.COLORMAP_PATH,
                lambda p, cm=cm: colormap.save(cm, p, mips=cfg.colormap_mips),
            )
            report["colormap"]["width"] = int(cm.shape[1])
            report["colormap"]["height"] = int(cm.shape[0])
            report["colormap"]["scale"] = cfg.colormap_scale
            report["colormap"]["mips"] = cfg.colormap_mips
            log(
                f"colormap: {cm.shape[1]}x{cm.shape[0]}, land mean "
                f"{report['colormap']['land_mean_rgb']}, water mean "
                f"{report['colormap']['water_mean_rgb']}"
            )
            del cm, land_px, water_px

        if cfg.water:
            report["water"] = _write_water_rasters(sink, cfg, water_mask, log)

        if cfg.terrain_paint:
            log("painting terrain (gfx/map/terrain/detail_index.tga + "
                "detail_intensity.tga)")
            paint_csv = _repo_path(cfg, cfg.terrain_paint_csv)
            paint_ordinals = terrain_paint.material_ordinals(
                (cfg.ck3_game_dir or Path())
                / "gfx" / "map" / "terrain" / "materials.settings"
            )
            soft = None
            if cfg.terrain_paint_soft_edges:
                # docs/step_map_paint.md §10: distance-field class blend +
                # per-class material mix + relief-aware boundary.
                soft = paint_edges.build_soft_blend(
                    codes_tgt,
                    code_names,
                    material_mix=paint_edges.read_material_mix(paint_csv),
                    ordinals=paint_ordinals,
                    mapping=cfg.terrain_map or None,
                    default=cfg.terrain_default,
                    quantize=cfg.terrain_paint_quantize,
                    sigma_px=cfg.terrain_paint_edge_sigma_px,
                    warp=paint_warp,
                    max_shift_px=(
                        canvas.factor * cfg.terrain_paint_max_shift_source_px
                    ),
                    land_mask=~water_mask,
                    warn=sink.warn,
                )
                paint = terrain_paint.PaintLayers(
                    index=soft.index,
                    intensity=soft.intensity,
                    classes=_class_pixel_counts(codes_tgt, code_names, cfg),
                    quantize=max(1, int(cfg.terrain_paint_quantize)),
                )
            else:
                paint = terrain_paint.build_layers(
                    codes_tgt,
                    code_names,
                    material_map=terrain_paint.read_material_map(paint_csv),
                    ordinals=paint_ordinals,
                    mapping=cfg.terrain_map or None,
                    default=cfg.terrain_default,
                    quantize=cfg.terrain_paint_quantize,
                    warn=sink.warn,
                )
            paint_format = cfg.terrain_paint_format
            paint_scale = cfg.terrain_paint_scale
            index_out, intensity_out = paint.index, paint.intensity
            if paint_scale != 1.0:
                index_out = terrain_paint.downsample_index(index_out, paint_scale)
                intensity_out = terrain_paint.downsample_intensity(
                    intensity_out, paint_scale
                )
            ext = terrain_paint.paint_ext(paint_format)
            index_path = f"gfx/map/terrain/detail_index.{ext}"
            intensity_path = f"gfx/map/terrain/detail_intensity.{ext}"
            sink.binary(
                index_path,
                lambda p: terrain_paint.save_paint(index_out, p, paint_format),
            )
            sink.binary(
                intensity_path,
                lambda p: terrain_paint.save_paint(intensity_out, p, paint_format),
            )
            report["terrain_paint"] = {
                "classes": paint.classes,
                "missing_material": paint.missing_material,
                "missing_ordinal": paint.missing_ordinal,
                "quantize": paint.quantize,
                "format": paint_format,
                "scale": paint_scale,
                "index_size": [int(index_out.shape[1]), int(index_out.shape[0])],
                "soft_edges": bool(cfg.terrain_paint_soft_edges),
            }
            log(f"terrain paint: {dict(sorted(paint.classes.items()))}")
            if soft is not None:
                km_per_px = cfg.scale.source_km_per_px / canvas.factor
                disp = paint_edges.class_displacement_stats(
                    soft.class_index_hard,
                    soft.class_index,
                    km_per_px=km_per_px,
                    mask=~water_mask,
                )
                report["terrain_paint"]["blend"] = soft.stats
                report["terrain_paint"]["displacement"] = disp
                log(
                    "paint blend (land): "
                    f"{soft.stats['mean_nonzero_channels']} channels/px, "
                    f"primary {soft.stats['mean_primary_weight']}, entropy "
                    f"{soft.stats['blend_entropy_bits']} bits "
                    "(vanilla 3.467 / 0.525 / 1.492)"
                )
                log(
                    "class displacement vs the CK2 grid: max "
                    f"{disp['max_km']} km, p95 {disp['p95_km']} km, "
                    f"{disp['changed_share'] * 100:.1f} % of land pixels "
                    f"(bound: {cfg.terrain_paint_max_shift_source_px} CK2 "
                    f"source pixel = {cfg.scale.source_km_per_px} km, "
                    f"{int(soft.stats['reverted_px'])} px reverted to CK2's "
                    "own class)"
                )
                del soft
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
    # ...except the county-capital barony, which can take the CK2 author's own
    # coordinates: `positions.txt` is per CK2 province = per CK3 county, so
    # slot 0 places its capital's holding and slot 1 its unit stacks
    # (docs/step_map_assets.md). Everything else keeps the centroid.
    locator_anchors: dict[int, tuple[float, float]] = {}
    locator_anchor_stats: locators.AnchorStats | None = None
    if cfg.ck2_locator_positions:
        barony_id_of = {p.barony: p.id for p in ids.provinces if p.barony}
        capital_ids = {}
        for ck2_pid, bs in plan.by_province.items():
            cap = next((b for b in bs if b.is_capital), None)
            if cap is None:
                continue
            cap_id = barony_id_of.get(cap.key)
            if cap_id is not None:
                capital_ids[ck2_pid] = cap_id
        locator_anchors, locator_anchor_stats = locators.ck2_capital_anchors(
            positions=positions,
            capital_ids=capital_ids,
            canvas=canvas,
            source_height=src_h,
            raster=ck3_raster,
            centroids=locator_xy,
        )
    # ...and every locator TYPE then sits at vanilla's own measured offset
    # from that anchor, so the siege marker, the two unit stacks and the
    # settlement do not draw on one point (mappings/locator_offsets.csv).
    locator_offsets = locators.read_locator_offsets(
        _repo_path(cfg, cfg.locator_offsets_csv)
    )
    if not locator_offsets:
        sink.warn(
            f"no locator offset table at {cfg.locator_offsets_csv}: every "
            "locator type will draw on the same point per province "
            "(uv run scripts/measure_vanilla_locator_offsets.py)"
        )
    locator_overrides, locator_type_stats = locators.place_with_offsets(
        centroids=locator_xy,
        anchors=locator_anchors,
        offsets=locator_offsets,
        raster=ck3_raster,
        land_ids=locator_land,
        passable_ids=locator_passable,
        scale=cfg.locator_offset_scale,
        mode=cfg.locator_offset_mode,
    )
    for rel, text in locators.render_all(
        locator_xy,
        canvas.height,
        land_ids=locator_land,
        passable_ids=locator_passable,
        overrides=locator_overrides,
    ).items():
        sink.text(rel, text)
    log(
        f"locators: {len(locators.LOCATOR_SPECS)} files, "
        f"{len(locator_land)} land / {len(locator_passable)} passable provinces"
    )
    if locator_anchor_stats is not None:
        a = locator_anchor_stats
        log(
            f"  CK2 slot {a.slot} anchors: {a.accepted}/{a.candidates} "
            f"county capitals accepted ({100 * a.accept_rate:.1f} %), "
            f"{a.outside_province} outside own province, "
            f"{a.off_canvas} off canvas, median move {a.median_move_px:.1f} px"
        )
    for name, s in locator_type_stats.items():
        log(
            f"  {name}: {s['moved_from_centroid']} of {s['ids']} off the "
            f"centroid ({s['ck2_anchored']} CK2-anchored, "
            f"{s['offset_applied']} offset applied, "
            f"{s['offset_rejected']} offset rejected), "
            f"median move {s['median_move_px']:.1f} px"
        )
    if cfg.trees and cfg.ck3_game_dir and trees is not None:
        log("scattering trees (docs/map_fidelity.md §4.3, "
            f"seed {cfg.trees_seed})")
        if scatter_src_mask is not None:
            # lane `paint-edges`: the same bilinear+threshold mask the paint
            # uses, so the trees stand exactly where the forest is painted
            # instead of inside a 15.6-canvas-pixel Lego block.
            forest_src = scatter_src_mask
        else:
            trees_full = tree_scatter.upsample_to_source(trees, src_h, src_w)
            forest_src = tree_scatter.forest_mask_from_trees_bmp(trees_full)
        forest_canvas = _resize_bool(forest_src, canvas)
        if paint_warp is not None:
            forest_canvas = paint_edges.warp_apply(
                forest_canvas.astype(np.uint8), paint_warp[0], paint_warp[1]
            ).astype(bool)
        impassable_mask = np.isin(ck3_raster, list(impassable_ck3))
        eligible = forest_canvas & ~water_mask & ~impassable_mask
        tree_terrain_code, tree_terrain_keys = _terrain_code_grid(
            ck3_raster, terrain_ck3, cfg.terrain_default
        )
        target_total = round(
            cfg.trees_density_per_px * canvas.width * canvas.height
        )
        # The regional mix conditions on the *ported* winter climate zone
        # (map_data/climate.txt, written a few lines below from this same
        # `climate` dict) as well as the terrain class and the latitude band
        # - docs/step_map_paint.md §9.9.
        mix_table: dict[tuple[str, str, str], tree_scatter.MixDist] = {}
        tree_climate_code = None
        tree_climate_keys = None
        if cfg.trees_regional:
            mix_table = tree_scatter.read_mix_table(
                _repo_path(cfg, cfg.trees_mix_csv)
            )
            mix_overrides = tree_scatter.read_mix_table(
                _repo_path(cfg, cfg.trees_mix_overrides_csv)
            )
            if mix_overrides:
                mix_table = tree_scatter.apply_mix_overrides(
                    mix_table, mix_overrides
                )
            if not mix_table:
                sink.warn(
                    f"no tree mix table at {cfg.trees_mix_csv}: every tree "
                    "falls back to its terrain key's single row in "
                    f"{cfg.trees_csv} (uv run "
                    "scripts/measure_vanilla_tree_mix.py && uv run "
                    "scripts/build_tree_mix_csv.py)"
                )
            tree_climate_code, tree_climate_keys = _climate_code_grid(
                ck3_raster, climate, ids
            )
        (
            foliage,
            tree_counts,
            tree_dropped,
            tree_dropped_by_terrain,
            tree_levels,
        ) = tree_scatter.render_all(
            cfg.ck3_game_dir,
            _repo_path(cfg, cfg.trees_csv),
            eligible,
            tree_terrain_code,
            tree_terrain_keys,
            canvas.height,
            target_total=target_total,
            seed=cfg.trees_seed,
            mix_table=mix_table,
            climate_code=tree_climate_code,
            climate_keys=tree_climate_keys,
            cell_px=cfg.trees_cell_px,
            coherence=cfg.trees_cell_coherence,
        )
        placed = sum(tree_counts.values())
        log(f"trees: {placed} of {target_total} target instances placed "
            f"({tree_dropped} dropped, no mesh row: {tree_dropped_by_terrain}), "
            f"{tree_counts}")
        if cfg.trees_regional:
            log(f"  regional mix ({len(mix_table)} conditions, cell "
                f"{cfg.trees_cell_px} px, coherence "
                f"{cfg.trees_cell_coherence}): {tree_levels}")
        report["trees"] = {
            "target_total": target_total,
            "placed": placed,
            "dropped_no_mesh": tree_dropped,
            "dropped_by_terrain": tree_dropped_by_terrain,
            "eligible_px": int(eligible.sum()),
            "regional": cfg.trees_regional,
            "mix_conditions": len(mix_table),
            "mix_levels": tree_levels,
            "cell_px": cfg.trees_cell_px,
            "cell_coherence": cfg.trees_cell_coherence,
            **tree_counts,
        }
    elif cfg.strip_vanilla_foliage:
        foliage = locators.render_foliage_stubs(cfg.ck3_game_dir)
    else:
        foliage = {}
    for rel, text in foliage.items():
        sink.text(rel, text)
    if foliage:
        log(f"{len(foliage)} gfx/map/map_object_data/generated files written")
    report["locators"] = {
        "files": len(locators.LOCATOR_SPECS),
        "land": len(locator_land),
        "passable": len(locator_passable),
        "foliage_stubs": len(foliage),
        "ck2_positions": cfg.ck2_locator_positions,
        "ck2_anchors": (
            locator_anchor_stats.as_dict() if locator_anchor_stats else {}
        ),
        "offsets": {k: [v.dx, v.dz] for k, v in sorted(locator_offsets.items())},
        "offset_scale": cfg.locator_offset_scale,
        "offset_mode": cfg.locator_offset_mode,
        "by_type": locator_type_stats,
        "moved_instances": sum(len(v) for v in locator_overrides.values()),
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

    # ----------------------------------------------- the frame around the map
    if cfg.surround_mask and not skip_images:
        report["surround_mask"] = _write_surround_mask(sink, cfg, canvas, log)

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
    if _terrain_history_evidence is not None:
        report["_evidence"]["terrain_history_baronies.csv"] = (
            _terrain_history_evidence
        )
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


def _write_water_rasters(sink: Sink, cfg: MapConfig, water_mask, log) -> dict:
    """The three whole-map rasters that otherwise show vanilla's Earth.

    ``gfx/map/water/watercolor_rgb_waterspec_a.dds``, ``.../foam_map.dds`` and
    ``gfx/map/textures/snow_mask.dds`` are all sampled at a whole-map UV, so a
    mod that ships none draws Europe's oceans and the Sahara's heat belt under
    its own continent (`docs/step_map_water_border.md`, ``ck2ck3.map.water``).
    """
    profile = water.read_water_profile(_repo_path(cfg, cfg.water_profile_csv))
    if not profile:
        sink.warn(
            f"[map] water = true but {cfg.water_profile_csv} is missing or "
            "empty; shipping flat deep-water colour and no shore foam"
        )
    canvas_h, canvas_w = water_mask.shape
    report: dict = {}

    for name, scale, builder, path in (
        ("watercolor", cfg.water_scale, water.build_watercolor,
         water.WATERCOLOR_PATH),
        ("foam_map", cfg.water_foam_scale, water.build_foam_map,
         water.FOAM_MAP_PATH),
    ):
        # Resample the mask, not the finished raster: coast distance has to be
        # measured on the grid the texture is written at, or the shelf ramp
        # comes out scaled by the downsample factor.
        mask = _resample_mask(water_mask, scale)
        raster = builder(mask, profile=profile, px_per_texel=1.0 / scale)
        sink.binary(path, lambda p, r=raster: water.save(r, p))
        report[name] = {
            "width": int(raster.shape[1]),
            "height": int(raster.shape[0]),
            "scale": scale,
            "format": "A8R8G8B8",
        }
        log(f"{name}: {raster.shape[1]}x{raster.shape[0]} "
            f"({scale:g} x canvas)")
        del raster, mask

    snow_h = max(4, round(canvas_h * cfg.snow_mask_scale))
    snow_w = max(4, round(canvas_w * cfg.snow_mask_scale))
    snow = water.build_snow_mask(
        (snow_h, snow_w),
        no_snow=cfg.snow_mask_no_snow,
        game_dir=cfg.ck3_game_dir,
    )
    sink.binary(water.SNOW_MASK_PATH, lambda p, r=snow: water.save(r, p))
    report["snow_mask"] = {
        "width": snow_w,
        "height": snow_h,
        "scale": cfg.snow_mask_scale,
        "no_snow_r": cfg.snow_mask_no_snow,
    }
    log(f"snow_mask: {snow_w}x{snow_h} (flat R = {cfg.snow_mask_no_snow})")
    return report


def _resample_mask(mask, scale: float):
    """Nearest-neighbour resample of a boolean mask; identity at scale 1."""
    if scale == 1.0:
        return mask
    h, w = mask.shape
    nh, nw = max(4, round(h * scale)), max(4, round(w * scale))
    ys = (np.arange(nh) / scale).astype(np.int64).clip(0, h - 1)
    xs = (np.arange(nw) / scale).astype(np.int64).clip(0, w - 1)
    return mask[ys[:, None], xs[None, :]]


def _write_surround_mask(sink: Sink, cfg: MapConfig, canvas, log) -> dict:
    """The frame that vanilla paints around Earth and we have to re-cut.

    Vanilla's own ``surround_mask.dds`` hides up to 67 % of the map height at
    the top (`verified`, ``scripts/measure_vanilla_surround.py``) — empty
    Arctic there, real territory on ours.
    """
    profile = surround.read_profile(_repo_path(cfg, cfg.surround_profile_csv))
    if len(profile) <= 1:
        sink.warn(
            f"[map] surround_mask = true but {cfg.surround_profile_csv} is "
            "missing or empty; shipping an unframed mask (map fully visible)"
        )
    width = max(4, round(canvas.width * cfg.surround_scale)) // 4 * 4
    height = max(4, round(canvas.height * cfg.surround_scale)) // 4 * 4
    mask = surround.build(width, height, profile)
    sink.binary(
        surround.SURROUND_MASK_PATH, lambda p, m=mask: surround.save(m, p)
    )
    log(f"surround_mask: {width}x{height} (DXT1), frame {len(profile)} texels")
    return {
        "width": width,
        "height": height,
        "scale": cfg.surround_scale,
        "frame_texels": int(len(profile)),
        "format": "DXT1",
    }


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


def _class_pixel_counts(codes: np.ndarray, code_names, cfg) -> dict[str, int]:
    """CK3 terrain key -> canvas pixel count, the run report's `classes` row.

    Same number `ck2ck3.map.terrain_paint.build_layers` reports; recomputed
    here because the soft-edge path (lane `paint-edges`) does not go through
    it.  Counted on the CK2 class map *before* the blend, so the report keeps
    measuring what CK2 painted.
    """
    table = dict(terrain.CK2_TO_CK3_TERRAIN if not cfg.terrain_map else cfg.terrain_map)
    counts = np.bincount(codes.reshape(-1), minlength=len(code_names))
    out: dict[str, int] = {}
    for code, cnt in enumerate(counts.tolist()):
        if not cnt:
            continue
        name = code_names[code]
        key = table.get(name, cfg.terrain_default) if name else cfg.terrain_default
        out[key] = out.get(key, 0) + int(cnt)
    return out


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


def _climate_code_grid(
    ck3_raster: np.ndarray, ck2_climate: dict[str, list[int]], ids
) -> tuple[np.ndarray, list[str]]:
    """Per-pixel winter climate zone, from the CK2 mod's own map/climate.txt.

    The same remap ``writers.render_climate`` uses for ``map_data/climate.txt``
    itself (CK2 province -> its CK3 baronies), so the zone a tree is sampled
    under is the zone the game will read for that province.  A province in no
    block gets ``none`` - CK3's own default, and vanilla leaves most of its
    own map out of ``climate.txt`` too (635 of 11,651 land provinces), so the
    measured table has a real ``none`` column to condition on.
    """
    zone_of_id: dict[int, str] = {}
    for zone, ck2_ids in ck2_climate.items():
        key = zone.replace("_winter", "")
        for ck3_id in ids.remap_ids(list(ck2_ids)):
            zone_of_id.setdefault(ck3_id, key)
    keys = sorted({"none", *zone_of_id.values()})
    index = {k: i for i, k in enumerate(keys)}
    max_id = int(ck3_raster.max()) if ck3_raster.size else 0
    lut = np.full(max_id + 1, index["none"], dtype=np.uint8)
    for pid, zone in zone_of_id.items():
        if 0 <= pid <= max_id:
            lut[pid] = index[zone]
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
