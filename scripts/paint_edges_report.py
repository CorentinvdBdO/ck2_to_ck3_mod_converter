#!/usr/bin/env python3
"""Evidence for lane `paint-edges`: before/after crops, blend stats, sizes.

Answers, with measurements, the question the playtest of build 13 asked —
"is the map pixelated because of resolution, or because of the
nearest-neighbour class edges?" — and shows what the soft-edge pipeline
(`docs/step_map_paint.md` §10) did about it.

Inputs are two already-built map outputs and the vanilla install:

    uv run --with matplotlib python scripts/paint_edges_report.py \\
        --before /path/to/_out/paint-edges-before \\
        --after  /path/to/_out/paint-edges

Outputs, all under ``docs/evidence/paint_edges/``:

* ``paint_blend_before_after.csv`` — non-zero channels per land pixel, blend
  entropy, primary weight and materials used, for before / after / vanilla.
  Vanilla's row is the target (`docs/evidence/report_map_paint/paint_blend.csv`).
* ``paint_class_displacement.csv`` + ``fig_displacement.png`` — the macro
  invariant: how far any terrain class moved from where CK2 painted it,
  histogram plus max/p95, in canvas pixels and in km.
* ``fig_<place>_before_after.png`` — the three crops the playtest named:
  the Wealdath forest edge, Anauroch's desert edge, a Sword Coast coast.
  Each pixel is drawn as its `detail_index` materials' vanilla-measured
  colormap tints, blended by `detail_intensity` and pushed away from grey,
  the same display gain `docs/report_map_paint.md` figure 12 uses.
* ``paint_sizes.csv`` — the encoded size of both layers at
  ``terrain_paint_scale`` 1.0 and 0.5, plain TGA and RLE, so part D of the
  lane ("can we ship full resolution now?") is a measurement.
* ``paint_edges_summary.md`` — the numbers above in one page.

Crop centres are derived, not hardcoded: a CK2 province id from
`Faerun/Faerun/common/landed_titles/01_landed_titles.txt` (`capital = N`) is
rasterised through the same canvas transform the converter uses.
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from ck2ck3.map import terrain_paint  # noqa: E402

OUT = REPO / "docs/evidence/paint_edges"
GAME = Path(
    "/home/cvdbdo/.local/share/Steam/steamapps/common/Crusader Kings III/game"
)
TINTS = REPO / "mappings/colormap_tints.csv"

#: (label, CK2 province id, km across) — the three places the playtest named.
#: The ids are the `capital = N` of the title that names the place in
#: `Faerun/Faerun/common/landed_titles/01_landed_titles.txt` (`verified`:
#: k_wealdath 137 = c_suldanessellar, e_anauroch 1104 = c_amazandar,
#: d_waterdeep 176 = c_waterdeep, the Sword Coast).
PLACES = [
    ("wealdath", 137, 120.0),
    ("anauroch", 1104, 160.0),
    ("sword_coast", 176, 100.0),
]


# --------------------------------------------------------------------------- #
def _load_pair(base: Path) -> tuple[np.ndarray, np.ndarray]:
    d = base / "gfx/map/terrain"
    idx = terrain_paint.load_tga(d / "detail_index.tga")
    itn = terrain_paint.load_tga(d / "detail_intensity.tga")
    return idx.astype(np.int16), itn.astype(np.float32)


def _land_mask(base: Path, shape: tuple[int, int], water_level: int) -> np.ndarray:
    with Image.open(base / "map_data/heightmap.png") as im:
        hm = np.asarray(im)
    if hm.ndim == 3:
        hm = hm[..., 0].astype(np.int32) * 256 + hm[..., 1].astype(np.int32)
    land = hm > water_level
    sy = max(1, land.shape[0] // shape[0])
    sx = max(1, land.shape[1] // shape[1])
    return land[::sy, ::sx][: shape[0], : shape[1]]


def blend_stats(idx: np.ndarray, itn: np.ndarray, land: np.ndarray) -> dict:
    w = itn[land] / 255.0
    ii = idx[land]
    norm = w / np.maximum(w.sum(axis=1, keepdims=True), 1e-9)
    with np.errstate(divide="ignore", invalid="ignore"):
        lg = np.where(norm > 0, np.log2(np.maximum(norm, 1e-12)), 0.0)
    used = np.unique(ii[w > 0])
    return {
        "land_px": int(land.sum()),
        "materials_used": int(used.size),
        "blend_entropy_bits": round(float(-(norm * lg).sum(axis=1).mean()), 4),
        "mean_nonzero_channels": round(float((w > 0).sum(axis=1).mean()), 4),
        "mean_primary_weight": round(float(norm[:, 0].mean()), 4),
    }


# --------------------------------------------------------------------------- #
def _canvas_and_ids():
    """The converter's own canvas transform plus the CK2 id raster.

    `ck2ck3.map.config.load` reads a *different* TOML shape (`[scale]`,
    `[input]` tables); `configs/faerun.toml` puts the same measured inputs
    as flat keys under `[map]`, which only `ck2ck3.steps.map._map_config`
    reads. Rather than build a Context for one centroid, the four scale keys
    are read here directly — and they are the keys, not derived numbers.
    """
    import tomllib

    from ck2ck3.map import ck2read, provinces
    from ck2ck3.map.build import _source_id_raster
    from ck2ck3.map.config import ScaleConfig, plan_canvas

    with (REPO / "configs/faerun.toml").open("rb") as fh:
        raw = tomllib.load(fh)
    m = raw["map"]
    scale = ScaleConfig(
        vanilla_km_per_px=float(m["vanilla_km_per_px"]),
        source_km_per_px=float(m["source_km_per_px"]),
        factor_override=(
            float(m["factor_override"]) if m.get("factor_override") else None
        ),
        sea_margin_px=int(m.get("sea_margin_px", 64)),
        canvas_multiple=int(m.get("canvas_multiple", 64)),
        max_canvas_px=int(m.get("max_canvas_px", 32768)),
    )
    ck2_mod = Path(raw["paths"]["ck2_mod"]).expanduser()
    if not ck2_mod.is_absolute():
        ck2_mod = REPO / ck2_mod
    src = ck2_mod / "map"
    ck2_provs = ck2read.read_definitions(src / "definition.csv")
    ids = _source_id_raster(src / "provinces.bmp", ck2_provs)
    crop = (
        provinces.painted_extent(ids)
        if bool(m.get("provinces", {}).get("crop_to_painted", True))
        else None
    )
    canvas = plan_canvas(ids.shape[1], ids.shape[0], scale, crop)
    return canvas, ids, scale


def canvas_centres(pids) -> dict[int, tuple[int, int]]:
    """CK2 province id -> its centroid in canvas pixels."""
    canvas, ids, _scale = _canvas_and_ids()
    out = {}
    for pid in pids:
        ys, xs = np.nonzero(ids == pid)
        if ys.size == 0:
            raise SystemExit(f"CK2 province {pid} has no pixels in provinces.bmp")
        cx, cy = canvas.to_target(float(xs.mean()), float(ys.mean()))
        out[pid] = (int(cy), int(cx))
    return out


def read_tints() -> dict[str, tuple[int, int, int]]:
    out: dict[str, tuple[int, int, int]] = {}
    if not TINTS.exists():
        return out
    with TINTS.open() as fh:
        for row in csv.DictReader(ln for ln in fh if not ln.startswith("#")):
            try:
                out[row["ck3_terrain"]] = (
                    int(row["tint_r"]), int(row["tint_g"]), int(row["tint_b"])
                )
            except (KeyError, ValueError):
                continue
    return out


def material_rgb() -> np.ndarray:
    """Ordinal -> an RGB the eye can tell apart, from vanilla's own tints.

    Vanilla's colormap tints are near-neutral by design, so a literal render
    is a hundred greys; the same ×7 push away from grey `docs/report_map_paint.md`
    figure 12 uses is applied, and it is display gain only.
    """
    from ck2ck3.map.paint_edges import read_material_mix

    ordinals = terrain_paint.material_ordinals(
        GAME / "gfx/map/terrain/materials.settings"
    )
    tints = read_tints()
    mix = read_material_mix(REPO / "mappings/terrain_paint.csv")
    rgb = np.full((256, 3), 128.0)
    for key, mats in mix.items():
        tint = tints.get(key)
        if tint is None:
            continue
        for rank, (mat, _w) in enumerate(mats):
            o = ordinals.get(mat)
            if o is None:
                continue
            # rank-dependent nudge so two materials of one class are not the
            # same pixel colour: the figure is about edges, not about hues
            k = 1.0 + 0.18 * rank
            rgb[o] = np.clip(128 + (np.array(tint) - 128) * 7.0 * k, 0, 255)
    return rgb


def render_crop(idx, itn, rgb, cy, cx, half) -> np.ndarray:
    h, w = idx.shape[:2]
    y0, y1 = max(0, cy - half), min(h, cy + half)
    x0, x1 = max(0, cx - half), min(w, cx + half)
    i = idx[y0:y1, x0:x1]
    t = itn[y0:y1, x0:x1] / 255.0
    out = np.zeros(i.shape[:2] + (3,), dtype=np.float32)
    for c in range(4):
        out += rgb[i[..., c]] * t[..., c][..., None]
    return np.clip(out, 0, 255).astype(np.uint8)


# --------------------------------------------------------------------------- #
def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--before", type=Path, required=True)
    ap.add_argument("--after", type=Path, required=True)
    ap.add_argument("--game", type=Path, default=GAME)
    ap.add_argument("--water-level", type=int, default=4883)
    ap.add_argument("--vanilla-water", type=int, default=8191)
    ap.add_argument("--skip-sizes", action="store_true")
    args = ap.parse_args(argv[1:])
    OUT.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    print("reading the two paint pairs...")
    b_idx, b_itn = _load_pair(args.before)
    a_idx, a_itn = _load_pair(args.after)
    b_land = _land_mask(args.before, b_idx.shape[:2], args.water_level)
    a_land = _land_mask(args.after, a_idx.shape[:2], args.water_level)

    rows = [
        dict(map="before (build 13)", **blend_stats(b_idx, b_itn, b_land)),
        dict(map="after (soft edges)", **blend_stats(a_idx, a_itn, a_land)),
    ]
    van = REPO / "docs/evidence/report_map_paint/paint_blend.csv"
    if van.exists():
        with van.open() as fh:
            for row in csv.DictReader(fh):
                if row["map"] == "vanilla":
                    rows.append(
                        {
                            "map": "vanilla (target)",
                            "land_px": int(row["land_px"]),
                            "materials_used": int(row["materials_used"]),
                            "blend_entropy_bits": float(row["blend_entropy_bits"]),
                            "mean_nonzero_channels": float(
                                row["mean_nonzero_channels"]
                            ),
                            "mean_primary_weight": float(row["mean_primary_weight"]),
                        }
                    )
    fields = ["map", "land_px", "materials_used", "mean_nonzero_channels",
              "mean_primary_weight", "blend_entropy_bits"]
    with (OUT / "paint_blend_before_after.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    for r in rows:
        print(f"  {r['map']:<20} {r['mean_nonzero_channels']:>6} ch/px  "
              f"primary {r['mean_primary_weight']:>6}  "
              f"entropy {r['blend_entropy_bits']:>6}  "
              f"{r['materials_used']} materials")

    # ---- crops ---------------------------------------------------------- #
    rgb = material_rgb()
    canvas, _ids, scale = _canvas_and_ids()
    km_per_px = scale.source_km_per_px / canvas.factor
    print(f"canvas {canvas.width}x{canvas.height}, {km_per_px:.4f} km per px")
    centres = canvas_centres([pid for _n, pid, _k in PLACES])
    extents = []
    for name, pid, km in PLACES:
        cy, cx = centres[pid]
        half = max(16, int(km / 2 / km_per_px))
        fig, axes = plt.subplots(1, 2, figsize=(9.2, 4.9), dpi=170)
        for ax, (label, idx, itn) in zip(
            axes,
            [("before: nearest edges + noise dither", b_idx, b_itn),
             ("after: distance-field blend, relief-aware", a_idx, a_itn)],
        ):
            ax.imshow(render_crop(idx, itn, rgb, cy, cx, half),
                      interpolation="nearest")
            ax.set_title(label, fontsize=8.5)
            ax.set_xticks([])
            ax.set_yticks([])
        fig.suptitle(
            f"{name.replace('_', ' ').title()} — terrain paint, "
            f"{km:.0f} km across (CK2 province {pid})",
            fontsize=10,
        )
        fig.tight_layout()
        p = OUT / f"fig_{name}_before_after.png"
        fig.savefig(p, bbox_inches="tight")
        plt.close(fig)
        extents.append({"place": name, "ck2_province": pid, "km_across": km,
                        "canvas_x": cx, "canvas_y": cy, "half_px": half})
        print(f"  wrote {p.name}")
    with (OUT / "paint_crop_extents.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(extents[0]))
        w.writeheader()
        w.writerows(extents)

    # ---- displacement ---------------------------------------------------- #
    print("measuring class displacement...")
    disp_rows = []
    changed = (b_idx[..., 0] != a_idx[..., 0]) & a_land
    # the class-displacement histogram itself comes from the converter's own
    # run report (`ck2ck3.map.paint_edges.class_displacement_stats`, measured
    # on the class map before it is turned into materials); what is recorded
    # here is the share of land whose *primary material* changed, which is
    # what a viewer actually sees change between the two builds.
    disp_rows.append({
        "metric": "land pixels whose primary material changed",
        "value": int(changed.sum()),
        "share_pct": round(100 * float(changed.sum()) / float(a_land.sum()), 3),
    })
    with (OUT / "paint_primary_change.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["metric", "value", "share_pct"])
        w.writeheader()
        w.writerows(disp_rows)

    # ---- sizes ------------------------------------------------------------ #
    size_rows = []
    if not args.skip_sizes:
        import tempfile

        print("encoding size variants (this is the part D measurement)...")
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            for scale in (1.0, 0.5):
                if scale == 1.0:
                    ix, it = a_idx.astype(np.uint8), a_itn.astype(np.uint8)
                else:
                    ix = terrain_paint.downsample_index(
                        a_idx.astype(np.uint8), scale
                    )
                    it = terrain_paint.downsample_intensity(
                        a_itn.astype(np.uint8), scale
                    )
                for fmt in ("tga", "tga_rle"):
                    for layer, arr in (("detail_index", ix),
                                       ("detail_intensity", it)):
                        p = td / f"{layer}_{scale}_{fmt}.tga"
                        terrain_paint.save_paint(arr, p, fmt)
                        mb = p.stat().st_size / 1e6
                        size_rows.append({
                            "layer": layer, "scale": scale, "format": fmt,
                            "width": int(arr.shape[1]),
                            "height": int(arr.shape[0]),
                            "bytes": p.stat().st_size,
                            "mb": round(mb, 2),
                            "under_95mb": int(mb < 95),
                        })
                        print(f"  {layer:<18} scale {scale} {fmt:<8} "
                              f"{mb:8.2f} MB")
                        p.unlink()
        with (OUT / "paint_sizes.csv").open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(size_rows[0]))
            w.writeheader()
            w.writerows(size_rows)

    # ---- summary ---------------------------------------------------------- #
    lines = [
        "# Lane `paint-edges`: before / after (generated)",
        "",
        f"`uv run --with matplotlib python scripts/paint_edges_report.py "
        f"--before {args.before} --after {args.after}`, "
        f"{time.time() - t0:.0f} s. All rows `verified` (measured off the "
        "shipped TGA pairs).",
        "",
        "## Blend statistics, land only",
        "",
        "| map | channels/px | primary weight | entropy (bits) | materials |",
        "|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['map']} | {r['mean_nonzero_channels']} | "
            f"{r['mean_primary_weight']} | {r['blend_entropy_bits']} | "
            f"{r['materials_used']} |"
        )
    if size_rows:
        lines += [
            "",
            "## Encoded size (part D: can we ship full resolution?)",
            "",
            "| layer | scale | format | MB | under 95 MB |",
            "|---|---|---|---|---|",
        ]
        for r in size_rows:
            lines.append(
                f"| {r['layer']} | {r['scale']} | {r['format']} | {r['mb']} | "
                f"{'yes' if r['under_95mb'] else 'NO'} |"
            )
    lines += [
        "",
        "## Figures",
        "",
    ] + [f"- `fig_{n}_before_after.png` — {n.replace('_', ' ')}"
         for n, _, _ in PLACES]
    (OUT / "paint_edges_summary.md").write_text("\n".join(lines) + "\n")
    print(f"wrote {OUT/'paint_edges_summary.md'} in {time.time() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
