"""Split each CK2 county into physical baronies (``docs/design_map.md`` §B).

One CK3 province per **built holding**, not per defined barony: Faerûn defines
15,356 baronies and builds 3,857 holdings at 1357, and 15k provinces on this
canvas would be 8x8 px each.  The set comes from :mod:`ck2ck3.map.holdings`;
this module places them on the canvas and hands back a label raster.

The four steps, and the reason each exists:

1. **Capacity.** A county that cannot hold ``min_barony_pixels`` per barony
   loses its lowest-priority holdings *before* any pixels are spent.  Priority
   is the CK2 ``landed_titles`` declaration order, capital first — CK2's own
   ordering, which puts the seat of the county at the top.  Demoted holdings
   are not deleted: they go to ``docs/evidence/barony_set.csv`` with status
   ``demoted`` so the titles lane can emit them as commented-out baronies.
2. **Seeds**, first match wins: ``overrides/barony_seeds.csv`` ->
   ``overrides/gazetteer.csv`` (matched on the CK2 localised barony name) ->
   the county capital at the CK2 ``positions.txt`` **city** slot (slot 0,
   `verified` ``docs/map_scale.md`` §2b) -> farthest-point sampling biased by
   holding type.
3. **Growth**: :func:`ck2ck3.map.growth.geodesic_voronoi`, so a barony only
   takes pixels reachable through its own county.
4. **Straggler demotion**: a barony that still ends under ``min_barony_pixels``
   after growth (a county shaped like a starfish can do this) is demoted and
   the county regrown, at most ``max_regrow_passes`` times.

Determinism is a hard requirement: same inputs and overrides -> byte-identical
provinces.png.  Every ordering in here is therefore explicit, every tie-break
is documented, and nothing iterates a set.
"""

from __future__ import annotations

import csv
import io
import re
import unicodedata
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .ck2titles import Ck2TitleTree
from .config import BaronyConfig, Canvas
from .growth import farthest_point, geodesic_voronoi, snap_to_mask
from .holdings import BaronySelection, Date

#: seed source labels, in priority order; they appear in barony_set.csv
SEED_SOURCES = ("override", "gazetteer", "capital_position", "sampled", "fallback")

#: CK3 holding type -> which pixels its seed should prefer
#: (``docs/design_map.md`` §B.2).  A city wants water access, a castle wants
#: high ground, a church and a tribe want neither.
HOLDING_BIAS: dict[str, str] = {
    "city_holding": "water",
    "castle_holding": "high",
    "church_holding": "",
    "tribal_holding": "",
}


# --------------------------------------------------------------------------- #
# overrides
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class SeedOverride:
    barony: str
    x: int
    y: int
    note: str = ""


@dataclass(frozen=True)
class GazetteerEntry:
    place: str
    x: int
    y: int
    #: ``ck3`` (canvas pixels, the default) or ``ck2`` (source bitmap pixels)
    space: str = "ck3"
    source: str = ""


SEED_CSV_HEADER = "barony_id,x,y,note"
GAZETTEER_CSV_HEADER = "place_name,x,y,space,source"


def read_seed_overrides(path: str | Path) -> dict[str, SeedOverride]:
    """``overrides/barony_seeds.csv``: ``barony_id,x,y,note`` in canvas pixels."""
    out: dict[str, SeedOverride] = {}
    for row in _rows(path, 3):
        key = row[0].strip()
        if not key.startswith("b_"):
            key = f"b_{key}"
        out[key] = SeedOverride(
            barony=key,
            x=int(float(row[1])),
            y=int(float(row[2])),
            note=row[3].strip() if len(row) > 3 else "",
        )
    return out


def read_gazetteer(path: str | Path) -> list[GazetteerEntry]:
    """``overrides/gazetteer.csv``: ``place_name,x,y,space,source``.

    ``space`` says which pixel grid the coordinates are in: ``ck3`` (the
    generated canvas, the default) or ``ck2`` (the source ``provinces.bmp``,
    which is what a coordinate read off the CK2 map or off the atlas overlay
    is in).  ``ck2`` rows are put through the map transform, so a gazetteer
    survives a change of canvas size.
    """
    out: list[GazetteerEntry] = []
    for row in _rows(path, 3):
        out.append(
            GazetteerEntry(
                place=row[0].strip(),
                x=int(float(row[1])),
                y=int(float(row[2])),
                space=(row[3].strip().lower() or "ck3") if len(row) > 3 else "ck3",
                source=row[4].strip() if len(row) > 4 else "",
            )
        )
    return out


def _rows(path: str | Path, min_cols: int) -> list[list[str]]:
    p = Path(path)
    if not p.exists():
        return []
    out: list[list[str]] = []
    with p.open("r", encoding="utf-8", newline="") as fh:
        for row in csv.reader(fh):
            if not row or row[0].lstrip().startswith("#"):
                continue
            if len(row) < min_cols:
                continue
            if not _is_number(row[1]) or not _is_number(row[2]):
                continue  # the header row
            out.append(row)
    return out


def _is_number(text: str) -> bool:
    try:
        float(text)
    except ValueError:
        return False
    return True


def normalise_place(name: str) -> str:
    """Fold a place name for gazetteer matching: ascii, lowercase, alnum only."""
    folded = unicodedata.normalize("NFKD", name)
    folded = "".join(c for c in folded if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "", folded.lower())


# --------------------------------------------------------------------------- #
# results
# --------------------------------------------------------------------------- #
@dataclass
class Barony:
    """One physical barony, before or after placement."""

    key: str
    county: str
    ck2_province: int
    holding: str
    built: Date
    is_capital: bool
    #: depth-first order in the CK2 landed_titles hierarchy
    order: int
    #: order inside the county (0 = capital)
    rank: int
    status: str = "placed"
    seed_source: str = ""
    seed_y: int = -1
    seed_x: int = -1
    pixels: int = 0
    #: True when a later bookmark, not the configured one, builds this holding
    later_bookmark: bool = False

    @property
    def title(self) -> str:
        return self.key


@dataclass
class BaronyPlan:
    #: placed baronies, in CK2 hierarchy order; index+1 is the growth label
    placed: list[Barony] = field(default_factory=list)
    #: demoted holdings, hierarchy order; no pixels, no CK3 province
    demoted: list[Barony] = field(default_factory=list)
    #: canvas-shaped int32; 0 = not a barony pixel, else index into ``placed`` + 1
    labels: np.ndarray | None = None
    #: CK2 province id -> its placed baronies, capital first
    by_province: dict[int, list[Barony]] = field(default_factory=dict)
    #: pixels that no seed could reach and were attached to the nearest barony
    orphan_pixels: int = 0
    #: seed source -> count, for the run report
    seed_counts: dict[str, int] = field(default_factory=dict)

    def counties_with_demotions(self) -> list[str]:
        return sorted({b.county for b in self.demoted})


# --------------------------------------------------------------------------- #
# planning
# --------------------------------------------------------------------------- #
def plan(
    *,
    raster_ids: np.ndarray,
    canvas: Canvas,
    selections: dict[int, BaronySelection],
    tree: Ck2TitleTree,
    cfg: BaronyConfig,
    positions: dict[int, list[tuple[float, float]]] | None = None,
    source_height: int = 0,
    loc_names: dict[str, str] | None = None,
    seed_overrides: dict[str, SeedOverride] | None = None,
    gazetteer: Sequence[GazetteerEntry] | None = None,
    water_bias: np.ndarray | None = None,
    high_bias: np.ndarray | None = None,
    warn: Callable[[str], None] = lambda _m: None,
) -> BaronyPlan:
    """Place every barony of every county and grow them over the canvas.

    ``raster_ids`` is the canvas-sized CK2 province-id raster (the output of
    :func:`ck2ck3.map.provinces.build_raster`).  ``selections`` must only
    contain provinces that survived it.
    """
    h, w = raster_ids.shape
    if (h, w) != (canvas.height, canvas.width):
        raise ValueError(
            f"raster {(h, w)} does not match canvas {(canvas.height, canvas.width)}"
        )
    result = BaronyPlan()
    pixels_by_province = _group_pixels(raster_ids, set(selections))

    # ------------------------------------------------------------- capacity
    candidates: list[Barony] = []
    for pid in sorted(selections):
        sel = selections[pid]
        county = sel.county or f"c_province_{pid}"
        order = tree.county_baronies.get(county) or list(sel.baronies)
        ranked = [k for k in order if k in sel.baronies]
        ranked += [k for k in sel.baronies if k not in ranked]
        area = int(pixels_by_province.get(pid, _EMPTY).size)
        capacity = max(1, area // max(1, cfg.min_barony_pixels))
        for rank, key in enumerate(ranked):
            b = Barony(
                key=key,
                county=county,
                ck2_province=pid,
                holding=sel.baronies[key],
                built=sel.built.get(key, (0, 0, 0)),
                is_capital=(rank == 0),
                order=tree.titles[key].order if key in tree.titles else 1 << 30,
                rank=rank,
                later_bookmark=key in sel.later,
            )
            if rank >= capacity:
                b.status = "demoted"
                result.demoted.append(b)
            else:
                candidates.append(b)
        if area == 0:
            warn(f"county {county} (CK2 province {pid}) has no canvas pixels")

    candidates.sort(key=lambda b: (b.order, b.key))
    result.demoted.sort(key=lambda b: (b.order, b.key))

    # ---------------------------------------------------------------- seeds
    _seed(
        candidates,
        pixels_by_province=pixels_by_province,
        canvas=canvas,
        cfg=cfg,
        positions=positions or {},
        source_height=source_height,
        loc_names=loc_names or {},
        seed_overrides=seed_overrides or {},
        gazetteer=gazetteer or (),
        water_bias=water_bias,
        high_bias=high_bias,
        warn=warn,
    )

    # --------------------------------------------------------------- growth
    groups = np.where(np.isin(raster_ids, list(selections)), raster_ids, 0)
    groups = groups.astype(np.int32, copy=False)

    def grow(members: list[Barony]) -> np.ndarray:
        return geodesic_voronoi(
            groups, [(b.seed_y, b.seed_x, i + 1) for i, b in enumerate(members)]
        )

    def measure(members: list[Barony], labels: np.ndarray) -> None:
        counts = np.bincount(labels.reshape(-1), minlength=len(members) + 1)
        for i, b in enumerate(members):
            b.pixels = int(counts[i + 1])

    labels = grow(candidates)
    # Lloyd relaxation, but only on the seeds the converter chose itself: a
    # farthest-point seed sits in a corner of the county by construction, which
    # makes the partition lopsided and demotes baronies that would have fitted.
    # Moving each sampled seed to its own region's centroid evens the areas out.
    # Seeds that came from a human, a gazetteer or CK2 positions.txt are PINNED
    # — the whole point of an override is that it stays where it was put.
    for _ in range(max(0, cfg.relax_passes)):
        if not _relax(candidates, labels, canvas.width):
            break
        labels = grow(candidates)

    for attempt in range(cfg.max_regrow_passes + 1):
        measure(candidates, labels)
        weak = [
            b
            for b in candidates
            if b.pixels < cfg.min_barony_pixels and not _is_only(b, candidates)
        ]
        if not weak or attempt == cfg.max_regrow_passes:
            break
        # demote one straggler per county per pass: removing the worst first
        # often lifts the others over the line, so this converges quickly
        worst: dict[int, Barony] = {}
        for b in weak:
            cur = worst.get(b.ck2_province)
            if cur is None or (b.pixels, -b.rank) < (cur.pixels, -cur.rank):
                worst[b.ck2_province] = b
        drop = {id(b) for b in worst.values()}
        for b in worst.values():
            b.status = "demoted"
            b.pixels = 0
            result.demoted.append(b)
        candidates = [b for b in candidates if id(b) not in drop]
        labels = grow(candidates)

    result.demoted.sort(key=lambda b: (b.order, b.key))
    result.placed = candidates
    result.labels = labels
    result.orphan_pixels = _attach_orphans(labels, groups, candidates, canvas.width)
    if result.orphan_pixels:
        counts = np.bincount(labels.reshape(-1), minlength=len(candidates) + 1)
        for i, b in enumerate(candidates):
            b.pixels = int(counts[i + 1])
        warn(
            f"{result.orphan_pixels} county pixels were unreachable from any seed "
            "(a detached piece of the county); attached to the nearest barony"
        )
    for b in candidates:
        result.by_province.setdefault(b.ck2_province, []).append(b)
    for baronies in result.by_province.values():
        baronies.sort(key=lambda b: b.rank)
    seed_counts: dict[str, int] = {}
    for b in candidates:
        seed_counts[b.seed_source] = seed_counts.get(b.seed_source, 0) + 1
    result.seed_counts = seed_counts
    return result


_EMPTY = np.zeros(0, dtype=np.int64)


def _relax(
    candidates: Sequence[Barony], labels: np.ndarray, width: int
) -> bool:
    """Move every ``sampled`` seed to the centroid of the region it grew.

    Returns True if any seed moved.  The new seed is the region pixel *nearest*
    the centroid, never the centroid itself: a crescent-shaped barony's centre
    of mass can land outside it, and a seed off its own mask is ignored by the
    growth pass.
    """
    flat = labels.reshape(-1)
    order = np.argsort(flat, kind="stable")
    sorted_labels = flat[order]
    bounds = np.searchsorted(sorted_labels, np.arange(len(candidates) + 2))
    moved = False
    for i, b in enumerate(candidates):
        if b.seed_source != "sampled":
            continue
        start, stop = int(bounds[i + 1]), int(bounds[i + 2])
        if stop <= start:
            continue
        px = order[start:stop]
        py, pxx = px // width, px % width
        cy, cx = py.mean(), pxx.mean()
        j = int(np.argmin((py - cy) ** 2 + (pxx - cx) ** 2))
        ny, nx = int(py[j]), int(pxx[j])
        if (ny, nx) != (b.seed_y, b.seed_x):
            b.seed_y, b.seed_x = ny, nx
            moved = True
    return moved


def _is_only(b: Barony, candidates: Sequence[Barony]) -> bool:
    """A county's last barony is never demoted: every county needs a province."""
    return sum(1 for o in candidates if o.ck2_province == b.ck2_province) <= 1


def _group_pixels(
    raster_ids: np.ndarray, wanted: set[int]
) -> dict[int, np.ndarray]:
    """CK2 province id -> its flat canvas pixel indices, ascending.

    One argsort over the land pixels only: a full argsort of the canvas would
    be 55 M int64 for no gain, since three quarters of it is water.
    """
    flat = raster_ids.reshape(-1)
    land = np.flatnonzero(np.isin(flat, list(wanted)))
    if land.size == 0:
        return {}
    ids = flat[land]
    order = np.argsort(ids, kind="stable")
    ids, land = ids[order], land[order]
    bounds = np.flatnonzero(np.diff(ids)) + 1
    out: dict[int, np.ndarray] = {}
    for start, stop in zip(
        np.concatenate(([0], bounds)), np.concatenate((bounds, [ids.size]))
    ):
        out[int(ids[start])] = np.sort(land[start:stop])
    return out


def _seed(
    candidates: list[Barony],
    *,
    pixels_by_province: dict[int, np.ndarray],
    canvas: Canvas,
    cfg: BaronyConfig,
    positions: dict[int, list[tuple[float, float]]],
    source_height: int,
    loc_names: dict[str, str],
    seed_overrides: dict[str, SeedOverride],
    gazetteer: Sequence[GazetteerEntry],
    water_bias: np.ndarray | None,
    high_bias: np.ndarray | None,
    warn: Callable[[str], None],
) -> None:
    """Fill in ``seed_y``/``seed_x``/``seed_source`` on every candidate."""
    w = canvas.width
    gaz = {normalise_place(g.place): g for g in gazetteer}
    water_flat = None if water_bias is None else water_bias.reshape(-1)
    high_flat = None if high_bias is None else high_bias.reshape(-1)

    by_province: dict[int, list[Barony]] = {}
    for b in candidates:
        by_province.setdefault(b.ck2_province, []).append(b)

    for pid in sorted(by_province):
        pixels = pixels_by_province.get(pid, _EMPTY)
        chosen: list[int] = []
        for b in sorted(by_province[pid], key=lambda x: x.rank):
            flat, source = _seed_one(
                b,
                pixels=pixels,
                width=w,
                canvas=canvas,
                cfg=cfg,
                positions=positions,
                source_height=source_height,
                loc_names=loc_names,
                seed_overrides=seed_overrides,
                gazetteer=gaz,
                chosen=chosen,
                water_flat=water_flat,
                high_flat=high_flat,
            )
            if flat is None:
                b.seed_source = "fallback"
                b.seed_y, b.seed_x = -1, -1
                warn(f"{b.key}: no seed could be placed in CK2 province {pid}")
                continue
            chosen.append(flat)
            b.seed_source = source
            b.seed_y, b.seed_x = divmod(flat, w)


def _seed_one(
    b: Barony,
    *,
    pixels: np.ndarray,
    width: int,
    canvas: Canvas,
    cfg: BaronyConfig,
    positions: dict[int, list[tuple[float, float]]],
    source_height: int,
    loc_names: dict[str, str],
    seed_overrides: dict[str, SeedOverride],
    gazetteer: dict[str, GazetteerEntry],
    chosen: list[int],
    water_flat: np.ndarray | None,
    high_flat: np.ndarray | None,
) -> tuple[int | None, str]:
    if pixels.size == 0:
        return None, "fallback"

    ov = seed_overrides.get(b.key)
    if ov is not None:
        flat = _snap(ov.y, ov.x, pixels, canvas, cfg)
        if flat is not None:
            return flat, "override"

    entry = gazetteer.get(normalise_place(loc_names.get(b.key, "")))
    if entry is not None:
        x, y = entry.x, entry.y
        if entry.space == "ck2":
            x, y = canvas.to_target(x, y)
        flat = _snap(y, x, pixels, canvas, cfg)
        if flat is not None:
            return flat, "gazetteer"

    if b.is_capital:
        slot = positions.get(b.ck2_province)
        if slot:
            cx, cy = slot[cfg.city_slot] if len(slot) > cfg.city_slot else slot[0]
            # positions.txt y is measured from the BOTTOM of the CK2 bitmap
            # (`verified`, docs/map_scale.md §2b)
            x, y = canvas.to_target(cx, source_height - cy)
            flat = _snap(y, x, pixels, canvas, cfg)
            if flat is not None:
                return flat, "capital_position"

    want = HOLDING_BIAS.get(b.holding, "")
    bias = None
    if want == "water" and water_flat is not None:
        bias = water_flat[pixels]
    elif want == "high" and high_flat is not None:
        bias = high_flat[pixels]
    free = pixels[~np.isin(pixels, chosen)] if chosen else pixels
    if free.size == 0:
        return None, "fallback"
    if bias is not None and free.size != pixels.size:
        bias = bias[~np.isin(pixels, chosen)]
    return (
        farthest_point(
            free, width, chosen, bias=bias, bias_gain=cfg.bias_gain
        ),
        "sampled",
    )


def _snap(
    y: int, x: int, pixels: np.ndarray, canvas: Canvas, cfg: BaronyConfig
) -> int | None:
    if not (0 <= y < canvas.height and 0 <= x < canvas.width):
        return None
    return snap_to_mask(
        y * canvas.width + x, pixels, canvas.width, max_distance=cfg.snap_radius_px
    )


def _attach_orphans(
    labels: np.ndarray, groups: np.ndarray, candidates: Sequence[Barony], width: int
) -> int:
    """Give pixels no seed could reach to the nearest seed of their own county.

    This happens when a county has a detached piece — an island, or a strip cut
    off by the rescaled coastline — that holds no seed.  The alternative would
    be to leave the pixels as padding ocean, which silently shrinks the county.
    The barony ends up non-contiguous; the review sheet shows it.
    """
    orphan = np.flatnonzero((groups.reshape(-1) != 0) & (labels.reshape(-1) == 0))
    if orphan.size == 0:
        return 0
    seeds_by_province: dict[int, list[tuple[int, int]]] = {}
    for i, b in enumerate(candidates):
        if b.seed_y >= 0:
            seeds_by_province.setdefault(b.ck2_province, []).append(
                (b.seed_y * width + b.seed_x, i + 1)
            )
    flat_groups = groups.reshape(-1)
    flat_labels = labels.reshape(-1)
    oy, ox = orphan // width, orphan % width
    for pid in np.unique(flat_groups[orphan]).tolist():
        seeds = seeds_by_province.get(int(pid))
        if not seeds:
            continue
        sel = flat_groups[orphan] == pid
        best_d = np.full(int(sel.sum()), np.inf)
        best_l = np.zeros(int(sel.sum()), dtype=np.int32)
        for flat, label in seeds:
            sy, sx = divmod(flat, width)
            d = (oy[sel] - sy) ** 2 + (ox[sel] - sx) ** 2
            take = d < best_d
            best_d[take] = d[take]
            best_l[take] = label
        flat_labels[orphan[sel]] = best_l
    return int(orphan.size)


# --------------------------------------------------------------------------- #
# evidence
# --------------------------------------------------------------------------- #
def render_barony_set_csv(
    plan_: BaronyPlan, *, province_names: dict[int, str] | None = None
) -> str:
    """``docs/evidence/barony_set.csv`` — the contract with the titles lane.

    The titles lane reads this to know which baronies exist as CK3 provinces
    (``placed``, ``override``) and which to emit as commented-out baronies
    (``demoted``).
    """
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(
        [
            "county",
            "barony",
            "holding",
            "built_date",
            "seed_source",
            "pixels",
            "status",
            "ck2_province",
            "ck2_province_name",
            "capital",
            "later_bookmark",
        ]
    )
    rows = sorted(
        [*plan_.placed, *plan_.demoted], key=lambda b: (b.order, b.key)
    )
    for b in rows:
        status = "override" if b.seed_source == "override" else b.status
        w.writerow(
            [
                b.county,
                b.key,
                b.holding,
                "initial" if b.built == (0, 0, 0) else "%d.%d.%d" % b.built,
                b.seed_source,
                b.pixels,
                status,
                b.ck2_province,
                (province_names or {}).get(b.ck2_province, ""),
                "yes" if b.is_capital else "no",
                "yes" if b.later_bookmark else "no",
            ]
        )
    return buf.getvalue()


SEED_TEMPLATE = f"""# {SEED_CSV_HEADER}
#
# Human override for where a barony's seed pixel goes. Highest priority of all
# seed sources: a row here wins over the gazetteer, over the CK2 positions.txt
# city slot and over farthest-point sampling.
#
# x,y are CANVAS pixels of the generated map_data/provinces.png, top-left
# origin. Read them off that PNG, or off docs/evidence/baronies/<d_id>.png,
# which is cropped to the duchy and labelled.
#
# A seed that lands outside its own county is snapped to the nearest county
# pixel; if the nearest one is further than [map.baronies] snap_radius_px the
# row is ignored and the converter falls through to the next source, so a
# typo degrades instead of moving a barony to another county.
#
# Uncomment and edit. The barony id is the CK2 one, with or without `b_`.
#b_castle_waterdeep,1543,1102,county seat, keep it on the harbour
#b_sea_ward,1520,1090,north-west of the castle
#b_the_plinth,1556,1121,inland, on the temple hill
"""

GAZETTEER_TEMPLATE = f"""# {GAZETTEER_CSV_HEADER}
#
# Place-name gazetteer: coordinates for named settlements, matched against the
# CK2 localised barony name (Faerun/Faerun/localisation/*.csv, English column).
# Matching folds accents, case and punctuation, so "Wyrm's Crossing" matches
# `wyrmscrossing`.
#
# Second priority, below overrides/barony_seeds.csv and above everything the
# converter derives. This is the file a lore search or an LLM pass fills in.
#
# space: `ck3` (default) = canvas pixels of the generated provinces.png;
#        `ck2` = pixels of Faerun/Faerun/map/provinces.bmp, which is what a
#        coordinate measured on the CK2 map or the atlas overlay is in. `ck2`
#        rows survive a change of canvas size, `ck3` rows do not.
# source: where the coordinate came from, for review. Free text.
#
#Wyrm's Crossing,2087,2464,ck2,atlas 1371 guide map
#Amphail,1901,1183,ck3,measured on provinces.png
"""
