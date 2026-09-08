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
import io
import json
import sys
import time
from dataclasses import replace
from pathlib import Path

import numpy as np
from PIL import Image

from . import bootstrap, ck2read, heightmap, idmap, provinces, rivers, terrain, writers
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

    with Image.open(src / "provinces.bmp") as im:
        src_w, src_h = im.size
    canvas = plan_canvas(src_w, src_h, cfg.scale)
    log(
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

    # ------------------------------------------------------ terrain (CK2 ids)
    # The vote runs on CK2 ids at CK2 resolution, before the remap, for two
    # reasons: it is 3.8x cheaper than voting on the target canvas, and the
    # winning category decides which provinces go in default.map's
    # `impassable_mountains` list, which idmap.build needs as an input.
    log("terrain majority vote (CK2 resolution)")
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
    tres = terrain.majority_terrain(
        src_ids,
        cats,
        land_ids=ck2_land,
        mapping=cfg.terrain_map or None,
        default=cfg.terrain_default,
    )
    impassable_ck2 = {
        pid
        for pid, cat in tres.category.items()
        if cat in terrain.CK2_IMPASSABLE_CATEGORIES
    }
    log(f"terrain: {dict(tres.histogram.most_common())}")
    log(f"{len(impassable_ck2)} provinces are CK2 impassable_mountains")

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
    log(f"{len(ids.provinces)} CK3 provinces (padding ocean is id {ids.padding.id})")

    terrain_ck3 = {
        ck3: tres.by_province[ck2]
        for ck2, ck3 in ids.ck2_to_ck3.items()
        if ck2 in tres.by_province
    }
    report["terrain"] = dict(tres.histogram)
    report["terrain_no_ck3_equivalent"] = len(tres.notes)
    report["terrain_fallbacks"] = len(tres.fallbacks)
    report["impassable"] = len(impassable_ck2)

    # ------------------------------------------------------------ water mask
    max_ck2 = max(ck2_names) if ck2_names else 0
    lut = np.zeros(max_ck2 + 1, dtype=np.int32)
    for ck2_id, ck3_id in ids.ck2_to_ck3.items():
        lut[ck2_id] = ck3_id
    ck3_raster = lut[np.clip(raster.ids, 0, max_ck2)]
    ck3_raster[raster.ids == provinces.PADDING] = ids.padding.id

    water_ck3 = {p.id for p in ids.provinces if p.is_water}
    land_ck3 = {p.id for p in ids.provinces if not p.is_water and p.ck2_id is not None}
    water_mask = np.isin(ck3_raster, list(water_ck3))

    # ---------------------------------------------------------------- images
    if not skip_images:
        log("writing provinces.png")
        rgb = provinces.to_rgb(
            raster,
            {p.id: p.rgb for p in ids.provinces if p.ck2_id is not None},
            cfg.provinces.ocean_rgb,
        )
        sink.binary("map_data/provinces.png", lambda p: provinces.save_png(rgb, p))

        log("building heightmap")
        heights = heightmap.build(src / "topology.bmp", canvas, cfg.heightmap)
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

        log("tracing and redrawing rivers")
        riv = rivers.render(src / "rivers.bmp", canvas, water_mask)
        sink.binary("map_data/rivers.png", lambda p: rivers.save_png(riv, p))
        report["rivers"] = rivers.stats(riv)
        _check_river_survival(sink, src / "rivers.bmp", riv, report)
        log(f"rivers: {report['rivers']}")

    # -------------------------------------------------------- text map files
    log("writing map_data text files")
    keys = bootstrap.unique_keys(ids.provinces)
    sink.text(
        "map_data/definition.csv",
        writers.render_definition_csv(
            ids.provinces, bootstrap.definition_names(keys)
        ),
    )
    sink.text(
        "map_data/default.map",
        writers.render_default_map(ids, sea_zone_names=_sea_zone_names(dm, ids)),
    )
    dropped_adj: list[str] = []
    adj_text, kept_adj = writers.render_adjacencies_csv(
        adj, ids, dropped_log=dropped_adj
    )
    sink.text("map_data/adjacencies.csv", adj_text)
    for message in dropped_adj:
        sink.warn(message)
    sink.text("map_data/climate.txt", writers.render_climate(climate, ids))
    sink.text("map_data/island_region.txt", writers.render_island_region(islands, ids))
    sink.text(
        f"map_data/geographical_regions/{prefix}_regions.txt",
        writers.render_geographical_regions(geo, ids),
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
    report["localisation"] = bootstrap.localisation_entries(ids.provinces, keys)

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
    report["_evidence"] = {
        "province_id_map.csv": idmap.render_id_map_csv(ids),
        "lost_provinces.csv": provinces.render_lost_report(raster, ck2_names),
    }
    return report


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
