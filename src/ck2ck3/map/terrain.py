"""CK2 ``terrain.bmp`` -> CK3 ``common/province_terrain`` terrain keys.

How CK2 stores terrain (`verified` on Faerûn):

* ``map/terrain.bmp`` is an 8-bit **palette-indexed** bitmap; the index, not the
  RGB triple, is what matters.
* ``map/terrain.txt`` ends in ``text_<n> = { type = <category> color = { <n> }
  priority = <n> }`` lines that map palette index -> CK2 terrain category
  (``Faerun/Faerun/map/terrain.txt:171-197``).
* Forest is **not** a terrain.bmp index in Faerûn.  CK2 derives it from
  ``map/trees.bmp`` together with the ``tree = { 3 4 7 10 }`` list in
  ``map/default.map`` (``Faerun/Faerun/map/default.map:38``: "Define which
  indices in trees.bmp palette which should count as trees for automatic
  terrain assignment").  ``trees.bmp`` is 512x416, i.e. 1/8 of the province
  bitmap on each axis, so one tree pixel covers an 8x8 province-bitmap block.
  The converter reproduces that rule; without it every Faerûn forest would come
  out as plains, since terrain index 20 (``type = forest``) has zero pixels.
* Faerûn's terrain index 19 is labelled ``coastal_desert`` but the comment on
  ``terrain.txt:190`` says "Underwater texture uses desert texture by looping
  around" — it is the ocean, 6.69 M of the 13.6 M pixels.  Water provinces take
  their terrain from ``default.map``, so index 19 is simply ignored for land.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

#: CK2 terrain category -> CK3 1.19 terrain key.
#:
#: CK3 keys are the 17 in ``common/terrain_types/00_terrains.txt``: plains,
#: farmlands, hills, terraced_hills, mountains, desert, desert_mountains, oasis,
#: jungle, forest, taiga, wetlands, steppe, floodplains, drylands, sea,
#: coastal_sea.
#:
#: Where CK2 has no CK3 equivalent the nearest key is used and the reason is
#: recorded here rather than invented in code (see CLAUDE.md: no invention).
CK2_TO_CK3_TERRAIN: dict[str, str] = {
    "plains": "plains",
    "farmlands": "farmlands",
    "coastal": "farmlands",  # CK2 `coastal` shares farmlands' colour; same value
    "forest": "forest",
    "woods": "forest",  # CK3 has one forest tier
    "hills": "hills",
    "mountain": "mountains",
    "impassable_mountains": "mountains",  # also listed impassable in default.map
    "steppe": "steppe",
    "desert": "desert",
    "coastal_desert": "drylands",  # arid but habitable coast
    "jungle": "jungle",
    "marsh": "wetlands",
    "arctic": "taiga",  # no arctic in CK3; taiga is the cold-forest key
    "glacier": "taiga",  # no glacier in CK3
    "subterranean": "mountains",  # NO CK3 EQUIVALENT: Underdark. See note below.
    "pti": "plains",  # CK2 "province terrain identifier" filler
    "ocean": "sea",
    "inland_ocean": "coastal_sea",
}

#: CK2 categories with no real CK3 counterpart; the converter emits a comment
#: for each affected province instead of pretending the mapping is faithful.
NO_CK3_EQUIVALENT = {
    "subterranean": "CK2 Underdark; CK3 has no subterranean terrain",
    "glacier": "CK2 glacier; nearest CK3 key is taiga",
    "arctic": "CK2 arctic; nearest CK3 key is taiga",
}

#: CK3 terrain keys that are water, so a land province must never get one.
CK3_WATER_TERRAIN = {"sea", "coastal_sea"}

#: CK2 terrain categories a castle seed prefers: defensible high ground.
#: Used only as a *bias* when a barony seed is sampled
#: (``docs/step_map_baronies.md``), never to decide a province's terrain, so a
#: county with no high ground simply gets an unbiased seed.
CK2_HIGH_GROUND = {"hills", "mountain", "impassable_mountains"}

#: CK2 categories that mean "blocks movement". CK3 has no terrain key for this;
#: it is expressed by listing the province under `impassable_mountains` in
#: default.map (`verified`: vanilla map_data/default.map has an
#: "IMPASSABLE TERRAIN" section and its own comment says the `wasteland`
#: heading is also written as impassable_mountains).
CK2_IMPASSABLE_CATEGORIES = {"impassable_mountains"}


@dataclass
class TerrainResult:
    #: province id -> CK3 terrain key
    by_province: dict[int, str]
    #: province id -> the winning CK2 category, so callers can spot e.g.
    #: `impassable_mountains` (which must also go in default.map, not just here)
    category: dict[int, str]
    #: CK3 terrain key -> province count, for the run report
    histogram: Counter[str]
    #: provinces whose CK2 category has no CK3 equivalent
    notes: dict[int, str]
    #: provinces with no usable land pixel at all; they got the default
    fallbacks: list[int]


def expand_trees(trees: np.ndarray, target_shape: tuple[int, int]) -> np.ndarray:
    """Nearest-neighbour upscale of ``trees.bmp`` to the province-bitmap shape.

    ``trees.bmp`` is a whole-number fraction of the province bitmap (1/8 in
    Faerûn), so integer index arithmetic is exact and no interpolation is
    needed.  Non-integer ratios still work, they just round.
    """
    th, tw = trees.shape
    h, w = target_shape
    rows = (np.arange(h) * th // h).clip(0, th - 1)
    cols = (np.arange(w) * tw // w).clip(0, tw - 1)
    return trees[rows[:, None], cols[None, :]]


def ck2_category_grid(
    terrain_idx: np.ndarray,
    texture_map: dict[int, str],
    *,
    trees: np.ndarray | None = None,
    tree_indices: tuple[int, ...] = (),
    forest_mask: np.ndarray | None = None,
) -> np.ndarray:
    """CK2 terrain.bmp indices -> an array of CK2 category names (object dtype).

    Applies the CK2 ``tree`` override: any pixel whose ``trees.bmp`` index is in
    ``tree_indices`` becomes ``forest``, whatever ``terrain.bmp`` said.
    ``forest_mask`` (source-resolution boolean) overrides that derivation
    entirely, which is how lane `paint-edges` feeds in a smoothly interpolated
    tree mask instead of the nearest-neighbour ``np.repeat`` block expansion
    (:func:`ck2ck3.map.paint_edges.forest_coverage`).
    """
    lut = np.empty(256, dtype=object)
    lut[:] = ""
    for idx, cat in texture_map.items():
        if 0 <= idx < 256:
            lut[idx] = cat
    cats = lut[terrain_idx]
    if forest_mask is not None:
        cats = np.where(forest_mask, "forest", cats)
    elif trees is not None and tree_indices:
        tree_grid = expand_trees(trees, terrain_idx.shape)
        cats = np.where(np.isin(tree_grid, list(tree_indices)), "forest", cats)
    return cats


def category_codes(categories: np.ndarray) -> tuple[np.ndarray, list[str]]:
    """Factorise a string/object category grid into ``(uint16 codes, names)``.

    Code 0 always means "no category" (an empty string), so callers can test a
    pixel with ``codes != 0`` without consulting ``names``.
    """
    names_arr, inverse = np.unique(categories.reshape(-1), return_inverse=True)
    names = ["" if n in ("", None) else str(n) for n in names_arr.tolist()]
    codes = inverse.astype(np.uint16).reshape(categories.shape)
    if "" not in names:
        names = [""] + names
        codes = codes + 1
    elif names.index("") != 0:
        zero = names.index("")
        perm = np.arange(len(names), dtype=np.uint16)
        perm[zero], perm[0] = 0, zero
        names[zero], names[0] = names[0], names[zero]
        codes = perm[codes]
    return codes, names


def ck2_category_codes(
    terrain_idx: np.ndarray,
    texture_map: dict[int, str],
    *,
    trees: np.ndarray | None = None,
    tree_indices: tuple[int, ...] = (),
    forest_mask: np.ndarray | None = None,
) -> tuple[np.ndarray, list[str]]:
    """:func:`ck2_category_grid` as integer codes, for a 55 M-pixel canvas.

    The object-dtype grid is 8 bytes a pixel and cannot be resized with integer
    indexing without copying Python objects; the code grid is 2 bytes and
    resizes and votes like any other array.  Same result, same order of
    ``names`` (sorted, with ``""`` first).
    """
    lut_names = [""] + sorted({c for c in texture_map.values() if c})
    if (tree_indices or forest_mask is not None) and "forest" not in lut_names:
        lut_names.append("forest")
    code_of = {n: i for i, n in enumerate(lut_names)}
    lut = np.zeros(256, dtype=np.uint16)
    for idx, cat in texture_map.items():
        if 0 <= idx < 256:
            lut[idx] = code_of.get(cat, 0)
    codes = lut[terrain_idx]
    if forest_mask is not None:
        codes = np.where(forest_mask, code_of["forest"], codes).astype(np.uint16)
    elif trees is not None and tree_indices:
        tree_grid = expand_trees(trees, terrain_idx.shape)
        codes = np.where(
            np.isin(tree_grid, list(tree_indices)), code_of["forest"], codes
        ).astype(np.uint16)
    return codes, lut_names


def majority_terrain_codes(
    province_ids: np.ndarray,
    codes: np.ndarray,
    names: Sequence[str],
    *,
    land_ids: set[int],
    mapping: dict[str, str] | None = None,
    default: str = "plains",
) -> TerrainResult:
    """:func:`majority_terrain` on an integer code grid.

    One ``np.bincount`` over ``province_id * ncat + code`` instead of a sort and
    a per-province ``np.unique``: O(pixels) with no 55 M-element argsort, which
    is what makes a per-barony vote on the target canvas affordable.
    """
    flat_ids = province_ids.reshape(-1).astype(np.int64, copy=False)
    flat_codes = codes.reshape(-1).astype(np.int64, copy=False)
    ncat = len(names)
    max_id = int(flat_ids.max()) if flat_ids.size else 0
    hist = np.bincount(
        flat_ids * ncat + flat_codes, minlength=(max_id + 1) * ncat
    ).reshape(max_id + 1, ncat)
    counts: dict[int, Counter[str]] = {}
    for pid in sorted(land_ids):
        if pid > max_id:
            continue
        row = hist[pid]
        nz = np.flatnonzero(row)
        counts[pid] = Counter(
            {names[int(c)]: int(row[c]) for c in nz.tolist() if names[int(c)]}
        )
    return _resolve(counts, land_ids, mapping=mapping, default=default)


def majority_terrain(
    province_ids: np.ndarray,
    categories: np.ndarray,
    *,
    land_ids: set[int],
    mapping: dict[str, str] | None = None,
    default: str = "plains",
) -> TerrainResult:
    """Majority CK2 category per land province -> one CK3 terrain key.

    ``province_ids`` and ``categories`` must be the same shape and in the *same*
    pixel space (both at CK2 resolution, or both at target resolution).  Water
    categories never win: a coastal province whose pixels are mostly the ocean
    texture would otherwise come out as ``sea``.
    """
    if categories.dtype.kind in "iu":
        raise TypeError(
            "majority_terrain wants a category-name grid; use "
            "majority_terrain_codes for an integer code grid"
        )
    codes, names = category_codes(categories)
    return majority_terrain_codes(
        province_ids, codes, names, land_ids=land_ids, mapping=mapping, default=default
    )


def _resolve(
    counts: dict[int, "Counter[str]"],
    land_ids: set[int],
    *,
    mapping: dict[str, str] | None,
    default: str,
) -> TerrainResult:
    """Winning non-water category per province -> CK3 key, plus the bookkeeping."""
    table = dict(CK2_TO_CK3_TERRAIN if mapping is None else mapping)
    by_province: dict[int, str] = {}
    category: dict[int, str] = {}
    notes: dict[int, str] = {}
    fallbacks: list[int] = []
    hist: Counter[str] = Counter()
    for pid in sorted(land_ids):
        counter = counts.get(pid, Counter())
        best_cat = None
        for cat, _ in counter.most_common():
            key = table.get(cat, default)
            if key not in CK3_WATER_TERRAIN:
                best_cat = cat
                break
        if best_cat is None:
            by_province[pid] = default
            fallbacks.append(pid)
            hist[default] += 1
            continue
        key = table.get(best_cat, default)
        by_province[pid] = key
        category[pid] = best_cat
        hist[key] += 1
        if best_cat in NO_CK3_EQUIVALENT:
            notes[pid] = NO_CK3_EQUIVALENT[best_cat]
    return TerrainResult(
        by_province=by_province,
        category=category,
        histogram=hist,
        notes=notes,
        fallbacks=fallbacks,
    )
