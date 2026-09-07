"""Standalone entry point for the physical-map conversion.

    uv run python -m ck2ck3.map.build --config configs/faerun_map.toml

The same work is exposed to the CLI as the ``map_physical`` step
(``ck2ck3.steps.map_physical.run``); this module is what makes it runnable
before that CLI lands.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import replace
from pathlib import Path

import numpy as np
from PIL import Image

from . import bootstrap, ck2read, heightmap, idmap, provinces, rivers, terrain, writers
from .config import MapConfig, load, plan_canvas

Image.MAX_IMAGE_PIXELS = None


def _log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def run(cfg: MapConfig, *, skip_images: bool = False) -> dict:
    """Convert the physical map. Returns a report dict (also written as JSON)."""
    src = cfg.ck2_map_dir
    out = cfg.out_mod_dir
    map_data = out / "map_data"
    report: dict = {}

    # ---------------------------------------------------------------- inputs
    _log(f"reading CK2 map from {src}")
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

    with Image.open(src / "provinces.bmp") as im:
        src_w, src_h = im.size
    canvas = plan_canvas(src_w, src_h, cfg.scale)
    _log(
        f"scale factor {canvas.factor:.6f} -> canvas {canvas.width}x{canvas.height} "
        f"(scaled {canvas.scaled_width}x{canvas.scaled_height}, "
        f"offset {canvas.offset_x},{canvas.offset_y})"
    )
    report["source"] = {"width": src_w, "height": src_h, "provinces": len(ck2_provs)}
    report["canvas"] = {
        "width": canvas.width,
        "height": canvas.height,
        "factor": canvas.factor,
        "offset_x": canvas.offset_x,
        "offset_y": canvas.offset_y,
        "vanilla_km_per_px": cfg.scale.vanilla_km_per_px,
        "source_km_per_px": cfg.scale.source_km_per_px,
    }

    # ------------------------------------------------------------ provinces
    _log("rasterising provinces (NEAREST on the id array)")
    raster = provinces.build_raster(
        src / "provinces.bmp",
        ck2_provs,
        canvas,
        min_pixels=cfg.provinces.min_pixels,
        regrow=cfg.provinces.regrow_lost,
    )
    _log(
        f"{len(raster.surviving)} provinces survived, {len(raster.lost)} lost, "
        f"{len(raster.regrown)} regrown, "
        f"{len(raster.undefined_colours)} undefined colours in the bitmap"
    )

    sea_ids = dm.sea_ids()
    lake_ids = dm.lake_ids(cfg.lake_region_names)
    river_ids = set(dm.major_rivers)
    ck2_names = {p.id: p.name for p in ck2_provs}

    # ------------------------------------------------------- terrain (CK2 ids)
    # The vote runs on CK2 ids and CK2 resolution, before the remap, for two
    # reasons: it is 3.4x cheaper than voting on the target canvas, and the
    # winning category is what decides which provinces go in default.map's
    # `impassable_mountains` list - which idmap.build needs as an input.
    _log("terrain majority vote (CK2 resolution)")
    with Image.open(src / "terrain.bmp") as im:
        terrain_idx = np.asarray(im)
    trees = None
    if (src / "trees.bmp").exists():
        with Image.open(src / "trees.bmp") as im:
            trees = np.asarray(im)
    cats = terrain.ck2_category_grid(
        terrain_idx, tex_map, trees=trees, tree_indices=tree_indices
    )
    ck2_water = sea_ids | lake_ids | river_ids
    ck2_land = raster.surviving - ck2_water
    src_ids = _source_id_raster(src / "provinces.bmp", ck2_provs)
    tres_ck2 = terrain.majority_terrain(
        src_ids,
        cats,
        land_ids=ck2_land,
        mapping=cfg.terrain_map or None,
        default=cfg.terrain_default,
    )
    impassable_ck2 = {
        pid
        for pid, cat in tres_ck2.category.items()
        if cat in terrain.CK2_IMPASSABLE_CATEGORIES
    }
    _log(f"terrain: {dict(tres_ck2.histogram.most_common())}")
    _log(f"{len(impassable_ck2)} provinces are CK2 impassable_mountains")

    # -------------------------------------------------------------- id remap
    ids = idmap.build(
        ck2_provs,
        raster.surviving,
        sea_ids=sea_ids,
        lake_ids=lake_ids,
        impassable_ids=impassable_ck2,
        river_ids=river_ids,
        padding_rgb=cfg.provinces.ocean_rgb,
        padding_name=cfg.provinces.ocean_name,
    )
    _log(f"{len(ids.provinces)} CK3 provinces (incl. padding ocean id {ids.padding.id})")

    cfg.evidence_dir.mkdir(parents=True, exist_ok=True)
    idmap.write_id_map_csv(ids, cfg.evidence_dir / "province_id_map.csv")
    provinces.write_lost_report(raster, ck2_names, cfg.evidence_dir / "lost_provinces.csv")

    # terrain keyed by CK3 id; impassable provinces keep their mountains key
    terrain_ck3 = {
        ck3: tres_ck2.by_province[ck2]
        for ck2, ck3 in ids.ck2_to_ck3.items()
        if ck2 in tres_ck2.by_province
    }
    report["terrain"] = dict(tres_ck2.histogram)
    report["terrain_no_ck3_equivalent"] = len(tres_ck2.notes)
    report["terrain_fallbacks"] = len(tres_ck2.fallbacks)
    report["impassable"] = len(impassable_ck2)

    # ------------------------------------------------------------ water mask
    max_ck2 = max(ck2_names) if ck2_names else 0
    ck2_to_ck3_lut = np.zeros(max_ck2 + 1, dtype=np.int32)
    for ck2_id, ck3_id in ids.ck2_to_ck3.items():
        ck2_to_ck3_lut[ck2_id] = ck3_id
    ck3_raster = ck2_to_ck3_lut[np.clip(raster.ids, 0, max_ck2)]
    ck3_raster[raster.ids == provinces.PADDING] = ids.padding.id

    water_ck3 = {p.id for p in ids.provinces if p.is_water}
    land_ck3 = {p.id for p in ids.provinces if not p.is_water and p.ck2_id is not None}
    water_mask = np.isin(ck3_raster, list(water_ck3))

    if not skip_images:
        _log("writing provinces.png")
        provinces.render_png(
            raster,
            {p.id: p.rgb for p in ids.provinces if p.ck2_id is not None},
            cfg.provinces.ocean_rgb,
            map_data / "provinces.png",
        )

    # ------------------------------------------------------------ heightmap
    if not skip_images:
        _log("building heightmap")
        heights = heightmap.build(src / "topology.bmp", canvas, cfg.heightmap)
        heightmap.write_png(heights, map_data / "heightmap.png")
        _log("packing heightmap")
        # imported here so the text-only path works before the packer lands
        from . import packed_heightmap

        meta = packed_heightmap.write_packed(
            heights,
            map_data,
            tile_size=cfg.heightmap.tile_size,
        )
        report["heightmap"] = {
            "width": int(heights.shape[1]),
            "height": int(heights.shape[0]),
            "resolution_factor": cfg.heightmap.resolution_factor,
            "water_level": cfg.heightmap.ck3_water_level,
            **{k: v for k, v in meta.items() if isinstance(v, (int, str))},
        }

        # ------------------------------------------------------------- rivers
        _log("tracing and redrawing rivers")
        riv = rivers.render(src / "rivers.bmp", canvas, water_mask)
        rivers.write_png(riv, map_data / "rivers.png")
        report["rivers"] = rivers.stats(riv)
        _log(f"rivers: {report['rivers']}")

    # -------------------------------------------------------- text map files
    _log("writing map_data text files")
    writers.write_definition_csv(ids.provinces, map_data / "definition.csv")
    sea_zone_names = _sea_zone_names(dm, ids)
    writers.write_default_map(ids, map_data / "default.map", sea_zone_names=sea_zone_names)
    dropped_adj: list[str] = []
    kept_adj = writers.write_adjacencies_csv(
        adj, ids, map_data / "adjacencies.csv", dropped_log=dropped_adj
    )
    writers.write_climate(climate, ids, map_data / "climate.txt")
    writers.write_island_region(islands, ids, map_data / "island_region.txt")
    writers.write_geographical_regions(
        geo, ids, map_data / "geographical_regions" / f"{cfg.prefix}_regions.txt"
    )
    writers.write_continent(
        map_data / "continent.txt", name=f"{cfg.prefix}_continent", province_ids=land_ck3
    )
    writers.write_seasons(map_data / "seasons.txt")
    writers.write_positions_stub(map_data / "positions.txt", canvas)
    writers.write_province_terrain(
        terrain_ck3,
        out / "common" / "province_terrain" / f"{cfg.prefix}_province_terrain.txt",
        default=cfg.terrain_default,
    )
    report["adjacencies"] = {"kept": kept_adj, "dropped": len(dropped_adj)}

    # ------------------------------------------------------------ bootstrap
    _log("writing throwaway title scaffolding")
    keys = bootstrap.unique_keys(ids.provinces)
    bootstrap.write_descriptor(
        out / "descriptor.mod",
        name=cfg.mod_name,
        version=cfg.mod_version,
        supported_version=cfg.supported_version,
    )
    bootstrap.write_defines(
        out / "common" / "defines" / f"{cfg.prefix}_defines.txt",
        width=canvas.width,
        height=canvas.height,
    )
    n_titles = bootstrap.write_landed_titles(
        ids.provinces, keys, out / "common" / "landed_titles" / f"{cfg.prefix}_landed_titles.txt"
    )
    n_hist = bootstrap.write_province_history(
        ids.provinces, out / "history" / "provinces" / f"{cfg.prefix}_provinces.txt"
    )
    bootstrap.write_title_history(out / "history" / "titles" / f"{cfg.prefix}_titles.txt")
    bootstrap.write_empty_replacements(out)
    bootstrap.write_localisation(
        ids.provinces,
        keys,
        out / "localization" / "english" / f"{cfg.prefix}_titles_l_english.yml",
    )
    report["bootstrap"] = {"baronies": n_titles, "province_history": n_hist}

    # --------------------------------------------------------------- report
    report["provinces"] = {
        "ck3_total": len(ids.provinces),
        "land": len(land_ck3),
        "sea": sum(1 for p in ids.provinces if p.is_sea),
        "lake": sum(1 for p in ids.provinces if p.is_lake),
        "river": sum(1 for p in ids.provinces if p.is_river),
        "lost": len(raster.lost),
        "regrown": len(raster.regrown),
    }
    path = cfg.evidence_dir / "map_build_report.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _log(f"report -> {path}")
    return report


def _source_id_raster(bmp: Path, ck2_provs: list[ck2read.Ck2Province]) -> np.ndarray:
    """CK2 province ids at source resolution (for the terrain vote)."""
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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", required=True, help="path to a map config TOML")
    ap.add_argument(
        "--out",
        help="override output.mod_dir (needed when running from a git worktree, "
        "where the config's relative path points somewhere else)",
    )
    ap.add_argument("--ck2-map-dir", help="override input.ck2_map_dir")
    ap.add_argument(
        "--skip-images",
        action="store_true",
        help="only write the text files (fast; for iterating on formats)",
    )
    args = ap.parse_args(argv)
    cfg = load(args.config)
    overrides = {}
    if args.out:
        overrides["out_mod_dir"] = Path(args.out).resolve()
    if args.ck2_map_dir:
        overrides["ck2_map_dir"] = Path(args.ck2_map_dir).resolve()
    if overrides:
        cfg = replace(cfg, **overrides)
    run(cfg, skip_images=args.skip_images)
    return 0


if __name__ == "__main__":
    sys.exit(main())
