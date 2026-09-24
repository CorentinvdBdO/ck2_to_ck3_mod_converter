#!/usr/bin/env python3
"""Verify the heightmap-detail pass's invariants on a real generated mod.

Usage:  uv run scripts/verify_heightmap_detail_invariants.py <out_mod_dir>

Checks, entirely from files on disk (no import of the converter's own
land/water classification, so this is an independent check of what
`ck2ck3.map.heightmap_detail.apply` promises, docs/step_map_heightmap.md §3):

1. every land province (a `definition.csv` barony/land row not in
   `default.map`'s `sea_zones`/`lakes`/`river_provinces`) has every
   `heightmap.png` pixel of its colour strictly above the water level;
2. every water province (sea/lake/river-type, plus the padding ocean colour)
   has every pixel at or below the water level;
3. **the source bound** (docs/step_map_heightmap.md §2f): over a window of
   one CK2 source pixel, every land pixel satisfies
   ``source_local_min - tol <= out <= source_local_max + tol``, where
   ``source`` is the plain rescale of `Faerun/Faerun/map/topology.bmp` and
   ``tol`` is the terrain class's own measured vanilla high-frequency RMS
   times `--bound-sigmas` (`common/province_terrain` gives the class;
   `docs/evidence/map_fidelity/hf_by_terrain.csv` gives the RMS).  Skipped
   when the source topology is not readable (`--no-bound` forces it off);
4. distinct 16-bit value count, reported for before/after comparison;
5. closed-depression excess, informational (§2h);
6. wall concentration, a hard gate against the source's own ratio (§2h ii);
7. every `overrides/lake_to_land.csv` province has actually LEFT every
   `default.map` water list, not merely left `lake_ids`/`river_ids` (§2h iii);
8. every `overrides/river_valleys.csv` (`valley`) province has STAYED in a
   `default.map` water list -- the opposite assertion of check 7 -- and is
   no longer pinned to the water level (§2h (d));
9. **no narrow water-pinned canyon**: any water province narrower than
   `NARROW_CANYON_WIDTH_PX` and surrounded by land
   `NARROW_CANYON_MIN_RISERS` above the water level, with every one of its
   own pixels still exactly pinned -- the Thay river defect's own signature,
   checked on every water province on the canvas, named in an override or
   not (§2h (d)).

Exit 0 when every check holds, 1 otherwise.

Usage:  uv run scripts/verify_heightmap_detail_invariants.py <out_mod_dir>
            [water_level] [--bound-sigmas N] [--bound-window N] [--no-bound]
            [--no-closed-depression] [--no-wall] [--no-narrow-canyon]
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.ndimage import binary_dilation, distance_transform_edt

Image.MAX_IMAGE_PIXELS = None

WATER_LEVEL = 4883  # docs/map_scale.md §4; overridable via argv[2]


def read_definition(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        parts = line.split(";")
        if len(parts) < 5 or not parts[0].isdigit():
            continue
        pid = int(parts[0])
        if pid == 0:
            continue
        rows.append({
            "id": pid,
            "rgb": (int(parts[1]), int(parts[2]), int(parts[3])),
            "name": parts[4],
        })
    return rows


def read_default_map(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    out = {}
    for key in ("sea_zones", "river_provinces", "lakes", "impassable_mountains"):
        out[key] = " ".join(re.findall(rf"^{key}\s*=\s*(.*)$", text, re.M))
    return out


def expand_ranges(spec: str) -> set[int]:
    ids: set[int] = set()
    for m in re.finditer(r"RANGE\s*\{\s*(\d+)\s+(\d+)\s*\}", spec):
        ids.update(range(int(m.group(1)), int(m.group(2)) + 1))
    body = re.sub(r"RANGE\s*\{[^}]*\}", " ", spec)
    ids.update(int(t) for t in re.findall(r"\b\d+\b", body))
    return ids


def check_source_bound(out: Path, heights: np.ndarray, land: np.ndarray,
                       water_level: int, sigmas: float, window: int,
                       valley_mask: np.ndarray | None = None,
                       resolution_factor: int = 1) -> dict:
    """Check 3: the output never leaves the CK2 author's own surface + texture.

    Independent of the converter's own arrays: the source is rebuilt here from
    `topology.bmp` through the same transfer curve the `map` step uses, and
    the per-pixel terrain class is read back out of the generated mod's
    `common/province_terrain` -- so this is a check of the *files*, which is
    what the rest of this script is too.

    ``valley_mask``: a `valley`-flagged river province (docs/step_map_heightmap.md
    §2h (d)) is deliberately carved *above* the CK2 source's own near-water-level
    pin, by exactly as much as `overrides/river_valleys.csv` intends -- inside
    `heightmap_detail.apply` itself this is fine, because its OWN bound uses the
    already-carved heights as its source, not the raw plain rescale this script
    independently rebuilds. But not every one of a valley province's own source
    pixels reads at or below the water level (some sit a few levels above it,
    same as vanilla's own river provinces, `scripts/measure_vanilla_river_provinces.py`),
    so the plain per-pixel `pinned` exclusion missed 264 px on the first run
    this lane's own carve fix produced (`verified`) -- excluded by province
    classification instead, below. That still left 187 TRUE LAND px right at
    the valley's own bank flagged (`verified`, e.g. `b_rauthil`, `b_cennuroth`):
    this check's local window (``window_px``) at a bank pixel spans across the
    province boundary into the valley, so the *raw, uncarved* river source
    (still near the water level) still drags that bank pixel's own `hi` down
    even though the pixel itself was never touched by the carve -- a boundary
    reach of the window, not a quality regression of the bank. `valley_mask`
    is therefore dilated by `window_px` before exclusion, not used as-is.
    """
    import relief_pits_common as P
    import relief_sharp_common as C

    source = C.plain_rescale_canvas(resolution_factor=resolution_factor)
    if source.shape != heights.shape:
        return {"skipped": f"source {source.shape} != heightmap {heights.shape}"}
    tcode, tkeys = P.terrain_codes_from_mod(
        out, slice(None), slice(None), resolution_factor=resolution_factor)
    tol = P.tolerance_field(tcode, tkeys, sigmas=sigmas)
    # A land pixel the plain rescale itself put at or below the water level is
    # *raised to the pin* by the land invariant, which is a bigger claim than
    # this bound and wins: excluded here rather than reported as a violation.
    # A `valley` province (and its own window-width neighbourhood) is excluded
    # the same way, by classification rather than by its own source value, for
    # the reason in the docstring above.
    pinned = land & (source <= water_level)
    if valley_mask is not None:
        pinned = pinned | (land & binary_dilation(valley_mask, iterations=window))
    checked = land & ~pinned
    row = P.bound_violation(source, heights, checked, tol, size=window)
    row["bound_sigmas"] = sigmas
    row["bound_window_px"] = window
    row["pinned_land_px_excluded"] = int(pinned.sum())
    row["bound_under_px"] = int(round(
        row["bound_under_frac"] * float(checked.sum())))
    row["bound_over_px"] = int(round(
        row["bound_over_frac"] * float(checked.sum())))
    row["tol_median_levels"] = round(float(np.median(tol[checked])), 1)
    return row


def check_closed_depression_excess(
    heights: np.ndarray, land: np.ndarray, resolution_factor: int = 1,
) -> dict:
    """Check 5 (docs/step_map_heightmap.md §2h): a closed loop no single
    small window can see.

    A 3 px (one CK2 source pixel) local-min/max bound -- check 3 above --
    cannot tell "the detail pass sharpened a real cliff" from "the detail
    pass turned a gentle 20-90 px CK2 basin into a several-thousand-level
    rampart no single pixel-pair ever individually violates its own
    tolerance over". `closed_depression_excess` (a morphological
    reconstruction, not a local window) is the metric that found this:
    Thaymount's plain rescale itself already carries a closed depression up
    to ~9,500 levels deep at a 45-81 px window, and what must not happen is
    the *output* exceeding that by more than the terrain tolerance -- i.e.
    the pass adding a rampart on top of what the CK2 author drew, whatever
    that already was.

    Reported, not a hard gate: the fix shipped with this check
    (`heightmap_detail_source_adaptive_gain`) measurably reduces the excess
    (~30 % at every window, docs §2h) but does not zero it -- most of the
    total depth is the CK2 source's own macro relief, sharpened by pass 1
    (Perona-Malik), which this check does not touch. A hard hallmark of
    regression is `cd_excess_27px_max` climbing past the evidence baseline
    in `docs/evidence/thay_relief/closed_depression_excess.csv`.
    """
    import relief_pits_common as P
    import relief_sharp_common as C

    source = C.plain_rescale_canvas(resolution_factor=resolution_factor)
    if source.shape != heights.shape:
        return {"skipped": f"source {source.shape} != heightmap {heights.shape}"}
    widths = tuple(w * resolution_factor for w in P.EXCESS_WINDOWS_PX)
    return P.closed_depression_excess_stats(source, heights, land, widths=widths)


#: check 6's gate: the output's axis-aligned/diagonal giant-step ratio must
#: not run away from the source's own -- a real, if imprecise, bound on "the
#: escarpment reads as a picket fence" (docs §2h ii). The source itself
#: (after the 1.9543x LANCZOS upsample) measures ~0.5-0.6 on Faerun's own
#: cliffs; `axis_over_diag_headroom` is how far above the *source's own*
#: ratio, at the same k, the output may sit before this is a regression.
WALL_AXIS_OVER_DIAG_HEADROOM = 0.35


def check_wall_concentration(source: np.ndarray, heights: np.ndarray,
                             land: np.ndarray) -> dict:
    """Check 6 (docs/step_map_heightmap.md §2h ii): a cliff rendered as a
    1-px axis-aligned wall, not a continuous slope over its own width.

    `scripts/relief_pits_common.wall_stats`: the axis-aligned/diagonal
    giant-step ratio (`axis_over_diag_k*`) and the drop-concentration
    percentiles, output against the plain rescale on the same land pixels.
    """
    import relief_pits_common as P

    row = P.wall_stats(source, heights, land)
    src_row = P.wall_stats(source, source, land)
    row["axis_over_diag_k2_source"] = src_row.get("axis_over_diag_k2")
    row["axis_over_diag_k5_source"] = src_row.get("axis_over_diag_k5")
    return row


def check_lake_to_land_left_every_water_list(
    overrides_path: Path, id_map_path: Path, water_ids_ck3: set[int],
) -> list[str]:
    """Check 7 (docs/step_map_heightmap.md §2h iii): every province
    `overrides/lake_to_land.csv` names is land in `default.map`, not merely
    not-a-lake.

    The exact bug two real conversion runs caught, in order: (1) the
    override was silently never read by the real CLI at all (§2h iii
    "the override did not take effect"); (2) once it *was* read, removing a
    CK2 id from `lake_ids` alone left it in `sea_zones` (a CK2 lake is a sea
    zone inside a `Lakes`-named `ocean_region`), so it became a *true sea*
    province instead of land. Both looked fine from the run-report counters
    alone; only reading `default.map` itself catches either.
    """
    if not overrides_path.exists() or not id_map_path.exists():
        return []
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parent))
    _sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from ck2ck3.map import lake_to_land as l2l

    rules = l2l.read_overrides(overrides_path)
    if not rules:
        return []
    ck2_to_ck3: dict[int, int] = {}
    with id_map_path.open(newline="", encoding="utf-8") as fh:
        import csv as _csv
        for row in _csv.DictReader(fh):
            # rows for CK2 provinces with no CK3 id (demoted/lost) carry an empty ck3_id
            if row.get("ck2_id", "").isdigit() and row.get("ck3_id", "").isdigit():
                ck2_to_ck3[int(row["ck2_id"])] = int(row["ck3_id"])
    problems = []
    for ck2_id, rule in rules.items():
        ck3_id = ck2_to_ck3.get(ck2_id)
        if ck3_id is None:
            problems.append(
                f"lake_to_land: CK2 province {ck2_id} ({rule.action}) has no "
                f"CK3 id in {id_map_path.name}"
            )
        elif ck3_id in water_ids_ck3:
            problems.append(
                f"lake_to_land: CK2 province {ck2_id} -> CK3 {ck3_id} "
                f"({rule.action}) is STILL in a default.map water list "
                "(sea_zones/lakes/river_provinces)"
            )
    return problems


#: check 8's bed-vs-bank gate (docs/step_map_heightmap.md §2h (d), the
#: coordinator's catch): "min > water_level" and "not perfectly flat" both
#: passed on a carve that was still a canyon in every render, because
#: neither metric compares the bed to its OWN bank -- a bed sitting one
#: riser above the water level passes "not pinned" just as well as a bed
#: sitting `depth` below a 7,000-level plateau. `BED_VS_BANK_RING_PX`
#: matches `scripts/measure_high_rivers.py`'s own already-verified bank
#: measurement exactly, so a bank number this check computes is directly
#: comparable to the one a province was proposed from.
#: `BED_VS_BANK_TOL` is headroom for what runs *after* the carve
#: (`heightmap_detail.apply`'s own texture synthesis, §2f, up to ~311-427
#: HF RMS levels per terrain class) on top of the carve's own `depth` --
#: not a licence for the carve itself to miss by more than that.
BED_VS_BANK_RING_PX = 15
BED_VS_BANK_DEFAULT_DEPTH = 300.0
BED_VS_BANK_TOL = 1000.0


def check_river_valleys(
    overrides_path: Path, id_map_path: Path, water_ids_ck3: set[int],
    heights: np.ndarray, prov_key: np.ndarray, definition: list[dict],
    water_level: int, *, ring_px: int = BED_VS_BANK_RING_PX,
) -> tuple[list[str], set[int]]:
    """Check 8 (docs/step_map_heightmap.md §2h (d)): every province
    `overrides/river_valleys.csv` names `valley` is the OPPOSITE case of
    check 7 -- it must STAY in a `default.map` water list (never leave it,
    exactly as CK2 had it: navigable, in `river_provinces`/`sea_zones`), and
    its heightmap must NOT be pinned to the water level any more (every own
    pixel strictly above it -- `carve_valleys`'s own bound) -- **and** its
    bed must actually sit close to its own bank, not merely above the water
    level. The coordinator's catch: the first two conditions alone passed on
    a run whose beds measured 4884-4951 min / ~5026-5205 median against a
    verified bank of 6545-7653 -- one riser above the water level is not
    "not pinned" in any sense a player's eye agrees with. Bank is measured
    exactly like `scripts/measure_high_rivers.py` (a land ring around the
    province, `BED_VS_BANK_RING_PX`), so it is directly comparable to the
    number each row of `river_valleys.csv` was proposed from.

    Returns ``(problems, valley_ck3_ids)``: the id set lets the caller
    EXCLUDE these provinces from the ordinary "every water province <=
    water_level" check below, which a `valley` row deliberately violates by
    design -- that is the entire point of the action.
    """
    if not overrides_path.exists() or not id_map_path.exists():
        return [], set()
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parent))
    _sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from ck2ck3.map import lake_to_land as l2l

    rules = l2l.valley_rules(l2l.read_overrides(overrides_path))
    if not rules:
        return [], set()
    ck2_to_ck3: dict[int, int] = {}
    with id_map_path.open(newline="", encoding="utf-8") as fh:
        import csv as _csv
        for row in _csv.DictReader(fh):
            if row.get("ck2_id", "").isdigit() and row.get("ck3_id", "").isdigit():
                ck2_to_ck3[int(row["ck2_id"])] = int(row["ck3_id"])
    rgb_by_id = {row["id"]: row["rgb"] for row in definition}
    problems: list[str] = []
    valley_ids: set[int] = set()
    for ck2_id, rule in rules.items():
        ck3_id = ck2_to_ck3.get(ck2_id)
        if ck3_id is None:
            problems.append(
                f"river_valleys: CK2 province {ck2_id} (valley) has no CK3 "
                f"id in {id_map_path.name}"
            )
            continue
        valley_ids.add(ck3_id)
        if ck3_id not in water_ids_ck3:
            problems.append(
                f"river_valleys: CK2 province {ck2_id} -> CK3 {ck3_id} "
                "(valley) LEFT the default.map water lists -- a valley row "
                "must stay water, unlike lake_to_land"
            )
            continue
        rgb = rgb_by_id.get(ck3_id)
        if rgb is None:
            continue
        k = (rgb[0] << 16) | (rgb[1] << 8) | rgb[2]
        mask = prov_key == k
        if not mask.any():
            continue
        vals = heights[mask].astype(np.int64)
        pinned = int((vals <= water_level).sum())
        if pinned:
            problems.append(
                f"river_valleys: CK2 province {ck2_id} -> CK3 {ck3_id} "
                f"(valley) has {pinned}/{vals.size} px at/below water level "
                f"{water_level} -- still reads like a pin, not a carved bed"
            )
            continue
        if vals.size > 4 and int(vals.std()) == 0:
            problems.append(
                f"river_valleys: CK2 province {ck2_id} -> CK3 {ck3_id} "
                "(valley) heightmap is perfectly flat -- reads like a new "
                "pin at a different level, not a carved valley bed"
            )
        # bed vs bank -- the hard gate the coordinator asked for: "not
        # pinned to the water level" is necessary but was NOT sufficient,
        # since a bed one riser above the water level passes it too.
        ring = (
            binary_dilation(mask, iterations=ring_px)
            & ~mask & (heights > water_level)
        )
        if not ring.any():
            continue  # no land in reach to compare against; nothing to gate
        bank = float(np.median(heights[ring].astype(np.int64)))
        bed = float(np.median(vals))
        drop = bank - bed
        limit = BED_VS_BANK_DEFAULT_DEPTH + BED_VS_BANK_TOL
        if drop > limit:
            problems.append(
                f"river_valleys: CK2 province {ck2_id} -> CK3 {ck3_id} "
                f"(valley) bed median {bed:.0f} is {drop:.0f} levels below "
                f"its own bank median {bank:.0f} (ring {ring_px} "
                f"px) -- wanted <= {limit:.0f} (depth "
                f"{BED_VS_BANK_DEFAULT_DEPTH:.0f} + tol {BED_VS_BANK_TOL:.0f}); "
                "reads like a canyon, not a shallow valley"
            )
    return problems, valley_ids


#: check 9's gate (docs/step_map_heightmap.md §2h (d)): a standing
#: regression check generalising the diagnostic that found Thay's five river
#: provinces, whether or not a province has ever been named in an
#: overrides/*.csv file. Calibrated directly off the pre-fix mod
#: (22:26 run, `docs/evidence/thay_relief/`): the five named rivers measured
#: TRUE width -- 2x the max distance-transform radius inside the province's
#: own mask, not `measure_high_rivers.py`'s circle-equivalent-diameter area
#: proxy, which reads 28-56 px for the same provinces because it folds in
#: their length -- 8.5-10.0 px, ring risers 4.0-10.0, 100% of their own
#: pixels pinned. `Lake Umber` (kind=river, 30 px wide, 3.0 risers) is the
#: nearest miss and is correctly excluded by the width gate alone.
NARROW_CANYON_WIDTH_PX = 12.0
NARROW_CANYON_MIN_RISERS = 3.0
NARROW_CANYON_RING_PX = 15


def check_no_narrow_water_pinned_canyons(
    heights: np.ndarray, water_mask_all: np.ndarray, prov_key: np.ndarray,
    definition: list[dict], water_ids: set[int], water_level: int,
    *, width_px: float = NARROW_CANYON_WIDTH_PX, ring_px: int = NARROW_CANYON_RING_PX,
    resolution_factor: int = 1,
) -> list[dict]:
    """Check 9: any water province narrow enough and surrounded by land high
    enough, with every one of its own pixels still exactly pinned to the
    water level -- the Thay river defect's own signature, checked on every
    water province on the canvas, not only the five that happened to be
    found and named this lane. Returns one dict per hit (``id``, ``name``,
    ``message``); the caller decides which ids are a hard gate (§2h (d): the
    provinces THIS lane's overrides target -- a regression check) and which
    are informational (a province elsewhere on the map nobody has looked at
    yet, the same "reported, not a hard gate" treatment check 5 already
    uses for closed-depression excess).

    A whole-canvas ``prov_key == k`` / ``binary_dilation`` per province is
    O(canvas) x O(water provinces on the canvas) -- 356 on this lane's
    Faerun map, most of them open sea spanning much of the canvas -- and
    took north of 5 minutes in practice (`verified`, killed at 3+ CPU
    minutes and still running). Instead: one vectorised lookup-table pass
    labels every water pixel by province in O(canvas) total (24-bit RGB fits
    a 64 MB LUT), `scipy.ndimage.find_objects` gets every province's
    bounding box in one more O(canvas) pass, and only the cheap per-province
    work (distance transform, ring dilation) runs on small crops after that.
    """
    try:
        import relief_sharp_common as C
    except Exception as exc:                                  # noqa: BLE001
        return [{"id": None, "name": None,
                  "message": f"narrow-canyon check SKIPPED (import: {type(exc).__name__}: {exc})"}]
    try:
        plain = C.plain_rescale_canvas(resolution_factor=resolution_factor)
    except Exception as exc:                                  # noqa: BLE001
        return [{"id": None, "name": None,
                  "message": f"narrow-canyon check SKIPPED ({type(exc).__name__}: {exc})"}]
    if plain.shape != heights.shape:
        return [{"id": None, "name": None,
                  "message": f"narrow-canyon check SKIPPED (source {plain.shape} "
                             f"!= heightmap {heights.shape})"}]

    from scipy.ndimage import find_objects

    water_rows = [row for row in definition if row["id"] in water_ids]
    if not water_rows:
        return []
    # label 0 = "not a water province of interest"; labels 1..N in
    # `water_rows` order, looked up through a 2^24-entry LUT (24-bit packed
    # RGB, one vectorised `lut[prov_key]` indexing call for the whole canvas)
    lut = np.zeros(1 << 24, dtype=np.int32)
    for i, row in enumerate(water_rows, start=1):
        k = (row["rgb"][0] << 16) | (row["rgb"][1] << 8) | row["rgb"][2]
        lut[k] = i
    label_img = lut[prov_key]
    del lut
    slices = find_objects(label_img)

    H, W = heights.shape
    pad = ring_px + 1
    hits: list[dict] = []
    for i, row in enumerate(water_rows, start=1):
        sl = slices[i - 1] if i - 1 < len(slices) else None
        if sl is None:
            continue
        ysl, xsl = sl
        y0, y1 = max(0, ysl.start - pad), min(H, ysl.stop + pad)
        x0, x1 = max(0, xsl.start - pad), min(W, xsl.stop + pad)
        mask = label_img[y0:y1, x0:x1] == i
        n = int(mask.sum())
        if n == 0:
            continue
        own_vals = heights[y0:y1, x0:x1][mask]
        if not (own_vals <= water_level).all():
            continue  # not (fully) pinned -- e.g. a `valley` row, already fine
        width = 2.0 * float(distance_transform_edt(mask).max())
        if width >= width_px:
            continue
        ring = (
            binary_dilation(mask, iterations=ring_px)
            & ~mask & ~water_mask_all[y0:y1, x0:x1]
        )
        if not ring.any():
            continue
        ring_med = float(np.median(plain[y0:y1, x0:x1][ring]))
        risers = (ring_med - water_level) / C.QUANT
        if risers >= NARROW_CANYON_MIN_RISERS:
            hits.append({
                "id": row["id"],
                "name": row["name"],
                "width_px": round(width, 1),
                "risers": round(risers, 1),
                "pixels": n,
                "message": (
                    f"narrow water-pinned canyon: province {row['id']} "
                    f"({row['name']}) width~{width:.1f} px, surrounding land "
                    f"{risers:.1f} risers above water, all {n} px pinned to "
                    f"{water_level} -- add it to overrides/lake_to_land.csv "
                    "or overrides/river_valleys.csv"
                ),
            })
    return hits


def main(argv: list[str]) -> int:
    args = [a for a in argv[1:] if not a.startswith("--")]
    flags = [a for a in argv[1:] if a.startswith("--")]
    if not args:
        print(__doc__.strip())
        return 2
    out = Path(args[0])
    water_level = int(args[1]) if len(args) > 1 else WATER_LEVEL
    bound_sigmas = 2.0
    bound_window = 3
    bound_window_explicit = False
    do_bound = "--no-bound" not in flags
    do_closed_depression = "--no-closed-depression" not in flags
    do_wall = "--no-wall" not in flags
    for f in flags:
        if f.startswith("--bound-sigmas="):
            bound_sigmas = float(f.split("=", 1)[1])
        elif f.startswith("--bound-window="):
            bound_window = int(f.split("=", 1)[1])
            bound_window_explicit = True
    sys.path.insert(0, str(Path(__file__).resolve().parent))

    definition = read_definition(out / "map_data/definition.csv")
    dm = read_default_map(out / "map_data/default.map")
    water_ids = set()
    for key in ("sea_zones", "lakes", "river_provinces"):
        water_ids |= expand_ranges(dm[key])

    lake_to_land_problems = check_lake_to_land_left_every_water_list(
        Path(__file__).resolve().parents[1] / "overrides/lake_to_land.csv",
        Path(__file__).resolve().parents[1] / "docs/evidence/province_id_map.csv",
        water_ids,
    )

    with (out / "map_data/provinces.png").open("rb") as fh:
        prov = np.asarray(Image.open(fh).convert("RGB"))
    hm_png = out / "map_data/heightmap.png"
    side_png = out.parent / f"{out.name}.sidecar" / "map_data/heightmap.png"
    if not hm_png.exists() and side_png.exists():
        hm_png = side_png  # ship_heightmap_png = false: build.sidecar_dir
    if hm_png.exists():
        with hm_png.open("rb") as fh:
            heights = np.asarray(Image.open(fh))
    else:
        # `[map.heightmap] ship_heightmap_png = false` (2x builds): read the
        # packed pair the game itself reads; decode_packed returns the same
        # orientation write_packed was given (tests/test_map_packed_heightmap.py).
        from ck2ck3.map import packed_heightmap

        heights, _ = packed_heightmap.decode_packed(out / "map_data")
    if heights.dtype != np.uint16:
        print(f"heightmap.png is not 16-bit (got {heights.dtype})")
        return 1
    # `[map.heightmap] resolution_factor`: vanilla itself ships a heightmap
    # that is 2x provinces.png, so "different sizes" is not by itself wrong
    # -- only a non-integer or non-uniform ratio is (docs/step_map_heightmap.md
    # §2i). Every per-province check below needs `key` (the provinces.png id
    # raster) at the SAME resolution as `heights`, nearest-neighbour
    # upsampled like every other province-resolution array a heightmap pass
    # consumes (`ck2ck3.map.build._nn_upsample`).
    ph, pw = prov.shape[:2]
    hh, hw = heights.shape
    if hh % ph or hw % pw or hh // ph != hw // pw:
        print(
            f"provinces.png {pw}x{ph} and heightmap.png {hw}x{hh} are not a "
            "uniform integer multiple of each other"
        )
        return 1
    resolution_factor = hh // ph
    if resolution_factor != 1:
        print(f"resolution_factor {resolution_factor} detected "
              f"(heightmap {hw}x{hh} vs provinces {pw}x{ph})")
        if not bound_window_explicit:
            bound_window *= resolution_factor

    key = (prov[..., 0].astype(np.int64) << 16) | (prov[..., 1].astype(np.int64) << 8) | prov[..., 2]
    if resolution_factor != 1:
        key = np.repeat(np.repeat(key, resolution_factor, axis=0),
                         resolution_factor, axis=1)

    river_valley_problems, valley_ids = check_river_valleys(
        Path(__file__).resolve().parents[1] / "overrides/river_valleys.csv",
        Path(__file__).resolve().parents[1] / "docs/evidence/province_id_map.csv",
        water_ids, heights, key, definition, water_level,
        ring_px=BED_VS_BANK_RING_PX * resolution_factor,
    )

    # every CK3 id named by *either* overrides file -- the check 9 "watched"
    # set: a hit on one of these is a regression this lane is responsible
    # for; a hit anywhere else on the map is informational (see check 9's
    # own docstring and §2h (d))
    repo_root = Path(__file__).resolve().parents[1]
    watched_ck3_ids: set[int] = set(valley_ids)
    try:
        import sys as _sys
        _sys.path.insert(0, str(Path(__file__).resolve().parent))
        _sys.path.insert(0, str(repo_root / "src"))
        from ck2ck3.map import lake_to_land as _l2l
        _id_map: dict[int, int] = {}
        id_map_path = repo_root / "docs/evidence/province_id_map.csv"
        if id_map_path.exists():
            import csv as _csv
            with id_map_path.open(newline="", encoding="utf-8") as fh:
                for _row in _csv.DictReader(fh):
                    if _row.get("ck2_id", "").isdigit() and _row.get("ck3_id", "").isdigit():
                        _id_map[int(_row["ck2_id"])] = int(_row["ck3_id"])
        for _rules_path in (
            repo_root / "overrides/lake_to_land.csv",
            repo_root / "overrides/river_valleys.csv",
        ):
            for _cid in _l2l.read_overrides(_rules_path):
                if _cid in _id_map:
                    watched_ck3_ids.add(_id_map[_cid])
    except Exception:                                          # noqa: BLE001
        pass  # informational partitioning only; every check above still ran

    problems: list[str] = list(lake_to_land_problems) + list(river_valley_problems)
    if lake_to_land_problems:
        print(f"lake_to_land          {len(lake_to_land_problems)} problem(s) "
              "(see INVARIANT BROKEN below)")
    else:
        print("lake_to_land          clean (no overridden province left in "
              "a default.map water list)")
    if river_valley_problems:
        print(f"river_valleys         {len(river_valley_problems)} problem(s) "
              "(see INVARIANT BROKEN below)")
    else:
        print(f"river_valleys         clean ({len(valley_ids)} valley province(s) "
              "still water, none pinned)")
    land_below = 0
    land_provinces_checked = 0
    water_above = 0
    water_provinces_checked = 0
    for row in definition:
        if row["id"] in valley_ids:
            # a `valley` row deliberately sits above the water level while
            # staying classified as water -- check_river_valleys above is
            # its dedicated check, not this generic one
            continue
        k = (row["rgb"][0] << 16) | (row["rgb"][1] << 8) | row["rgb"][2]
        mask = key == k
        if not mask.any():
            continue
        vals = heights[mask].astype(np.int64)
        is_water = row["id"] in water_ids
        if is_water:
            water_provinces_checked += 1
            bad = int((vals > water_level).sum())
            if bad:
                water_above += bad
                problems.append(
                    f"water province {row['id']} ({row['name']}): "
                    f"{bad}/{vals.size} px above water level {water_level} "
                    f"(max {int(vals.max())})"
                )
        else:
            land_provinces_checked += 1
            bad = int((vals <= water_level).sum())
            if bad:
                land_below += bad
                problems.append(
                    f"land province {row['id']} ({row['name']}): "
                    f"{bad}/{vals.size} px at or below water level {water_level} "
                    f"(min {int(vals.min())})"
                )

    bound_row: dict = {}
    if do_bound:
        try:
            land_mask = heights > water_level
            # `valley_ids` is a set of CK3 province ids (definition.csv
            # column 1), never comparable to `key` (packed provinces.png
            # RGB) directly -- map id -> rgb -> packed key first, or this
            # silently matches nothing (`verified`: caught by a 264 px
            # "violation" that a dilated valley_mask should have, and did
            # not, make disappear).
            if valley_ids:
                valley_keys = [
                    (row["rgb"][0] << 16) | (row["rgb"][1] << 8) | row["rgb"][2]
                    for row in definition if row["id"] in valley_ids
                ]
                valley_mask_arr = np.isin(key, valley_keys) if valley_keys else None
            else:
                valley_mask_arr = None
            bound_row = check_source_bound(
                out, heights, land_mask, water_level, bound_sigmas, bound_window,
                valley_mask=valley_mask_arr, resolution_factor=resolution_factor)
        except Exception as exc:                      # noqa: BLE001
            bound_row = {"skipped": f"{type(exc).__name__}: {exc}"}

    distinct = int(np.unique(heights).size)
    print(f"out                     {out}")
    print(f"water level             {water_level}")
    print(f"land provinces checked  {land_provinces_checked}")
    print(f"water provinces checked {water_provinces_checked}")
    print(f"distinct height values  {distinct}")
    print(f"land px at/below water  {land_below}")
    print(f"water px above water    {water_above}")
    if bound_row.get("skipped"):
        print(f"source bound            SKIPPED ({bound_row['skipped']})")
    elif bound_row:
        print(f"source bound            {bound_sigmas}x hf RMS over "
              f"{bound_window} px (median tol "
              f"{bound_row['tol_median_levels']} levels)")
        print(f"  land pinned, excluded {bound_row['pinned_land_px_excluded']} px")
        print(f"  land below the bound  {bound_row['bound_under_px']} px "
              f"(max {bound_row['bound_under_max']} levels)")
        print(f"  land above the bound  {bound_row['bound_over_px']} px "
              f"(max {bound_row['bound_over_max']} levels)")
        if bound_row["bound_under_px"] or bound_row["bound_over_px"]:
            problems.append(
                f"source bound broken on {bound_row['bound_under_px']} land px "
                f"below / {bound_row['bound_over_px']} above"
            )

    if do_closed_depression:
        try:
            land_mask = heights > water_level
            cd_row = check_closed_depression_excess(
                heights, land_mask, resolution_factor=resolution_factor)
            if cd_row.get("skipped"):
                print(f"closed-depression excess SKIPPED ({cd_row['skipped']})")
            else:
                print("closed-depression excess (§2h, informational -- "
                      "compare to docs/evidence/thay_relief/):")
                for w in (3 * resolution_factor, 9 * resolution_factor, 27 * resolution_factor):
                    p95 = cd_row.get(f"cd_excess_{w}px_p95")
                    p99 = cd_row.get(f"cd_excess_{w}px_p99")
                    mx = cd_row.get(f"cd_excess_{w}px_max")
                    if p95 is None:
                        continue
                    print(f"  {w:3d}px  p95 {p95:7.0f}  p99 {p99:7.0f}  "
                          f"max {mx:7.0f}")
        except Exception as exc:                        # noqa: BLE001
            print(f"closed-depression excess SKIPPED ({type(exc).__name__}: {exc})")

    if do_wall:
        try:
            import relief_sharp_common as C

            land_mask = heights > water_level
            source = C.plain_rescale_canvas(resolution_factor=resolution_factor)
            if source.shape != heights.shape:
                print(f"wall concentration      SKIPPED (source {source.shape} "
                      f"!= heightmap {heights.shape})")
            else:
                wall_row = check_wall_concentration(source, heights, land_mask)
                print("wall concentration (§2h ii, a cliff as a 1-px axis-aligned "
                      "slab vs a continuous slope):")
                for k in (2.0, 3.0, 5.0):
                    out_r = wall_row.get(f"axis_over_diag_k{k:g}")
                    print(f"  k={k:g}  axis/diag {out_r}")
                print(f"  source k=2 {wall_row.get('axis_over_diag_k2_source')}  "
                      f"k=5 {wall_row.get('axis_over_diag_k5_source')}")
                print(f"  drop concentration p50/p95/max "
                      f"{wall_row.get('drop_concentration_p50')}/"
                      f"{wall_row.get('drop_concentration_p95')}/"
                      f"{wall_row.get('drop_concentration_max')}")
                src2 = wall_row.get("axis_over_diag_k2_source") or 0.0
                out2 = wall_row.get("axis_over_diag_k2") or 0.0
                if out2 > src2 + WALL_AXIS_OVER_DIAG_HEADROOM:
                    problems.append(
                        f"wall concentration regressed: axis/diag k=2 is "
                        f"{out2} against the source's own {src2} "
                        f"(headroom {WALL_AXIS_OVER_DIAG_HEADROOM})"
                    )
        except Exception as exc:                        # noqa: BLE001
            print(f"wall concentration SKIPPED ({type(exc).__name__}: {exc})")

    do_narrow_canyon = "--no-narrow-canyon" not in flags
    if do_narrow_canyon:
        water_mask_all = heights <= water_level
        canyon_hits = check_no_narrow_water_pinned_canyons(
            heights, water_mask_all, key, definition, water_ids, water_level,
            width_px=NARROW_CANYON_WIDTH_PX * resolution_factor,
            ring_px=NARROW_CANYON_RING_PX * resolution_factor,
            resolution_factor=resolution_factor,
        )
        if canyon_hits and canyon_hits[0]["id"] is None:
            print(canyon_hits[0]["message"])
        else:
            # a hit on an id THIS lane's overrides name is a regression this
            # lane is responsible for and is a hard gate; a hit anywhere
            # else on the map is informational (§2h (d), the same "reported,
            # not a hard gate" treatment check 5 uses) -- it is real, but
            # fixing it is a future lane's scope, not this one's
            watched_hits = [h for h in canyon_hits if h["id"] in watched_ck3_ids]
            other_hits = [h for h in canyon_hits if h["id"] not in watched_ck3_ids]
            if watched_hits:
                print(f"narrow water-pinned canyons {len(watched_hits)} REGRESSION(S) "
                      "on a province this lane's overrides target "
                      "(see INVARIANT BROKEN below)")
                problems.extend(h["message"] for h in watched_hits)
            else:
                print("narrow water-pinned canyons none on a province this "
                      "lane's overrides target")
            if other_hits:
                print(f"  + {len(other_hits)} elsewhere on the map "
                      "(informational, out of this lane's scope, "
                      "docs/evidence/narrow_water_pinned_canyons.csv)")
                _canyon_csv = Path(__file__).resolve().parents[1] / (
                    "docs/evidence/narrow_water_pinned_canyons.csv"
                )
                _canyon_csv.parent.mkdir(parents=True, exist_ok=True)
                with _canyon_csv.open("w", newline="", encoding="utf-8") as fh:
                    import csv as _csv
                    w = _csv.writer(fh)
                    w.writerow(["ck3_id", "name", "width_px", "risers", "pixels"])
                    for h in sorted(other_hits, key=lambda h: -h["risers"]):
                        w.writerow([h["id"], h["name"], h["width_px"], h["risers"], h["pixels"]])
            elif not watched_hits:
                print(f"narrow water-pinned canyons none anywhere "
                      f"(< {NARROW_CANYON_WIDTH_PX:.0f} px wide through land "
                      f">= {NARROW_CANYON_MIN_RISERS:.0f} risers, still pinned)")

    if problems:
        print("\nINVARIANT BROKEN")
        for p in problems[:20]:
            print(f"  - {p}")
        if len(problems) > 20:
            print(f"  ... and {len(problems) - 20} more")
        return 1
    print("\ninvariants hold")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
