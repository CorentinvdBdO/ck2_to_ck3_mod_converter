"""``overrides/lake_to_land.csv``: a CK2 lake province drawn on high ground
becomes a CK3 land or marsh province instead of a hole down to sea level.

**The problem this fixes** (`docs/step_map_heightmap.md` §2h iii, the user's
decision 2026-09-23). CK3 has one global water level; a CK2 lake on a plateau
is already a hole through it (`docs/step_map_heightmap.md` §2f). Worse: CK2's
own ``topology.bmp`` draws a lake's *own* pixels near sea level (Lake
Thaylambar's raw bytes are 85-92 of 255, against a plateau of ~20,000-40,000
CK3 levels around it) regardless of the plateau under it -- CK2 apparently
never needed the bed to be plausible, since its own renderer decides "this is
a lake" from the province, not the height. So `heightmap.deepen_sea`'s own
water test (``heights <= water_level``, a raw-height threshold with no
province lookup at all) already flattens these pixels to the sea floor
*before* this module ever runs, whether or not the province is reclassified.
Reclassifying the province alone is not enough; the height has to be replaced
too, or "land" just means "a flat pit that used to be blue".

**The fix, three independent patches, applied in this order in
``ck2ck3.map.build``:**

1. :func:`patch_water_ids` -- before ``ck2_water``/baronies/``idmap`` ever see
   them, pull the overridden CK2 ids out of ``lake_ids``/``river_ids``. From
   here on the whole existing pipeline treats the province as ordinary land:
   barony planning includes it (a real CK2 title, if one somehow exists,
   produces a real barony), and the untitled-land rule already in
   ``ck2ck3.map.build`` (`docs/step_map_baronies.md`) forces it to
   ``impassable_mountains`` like any other CK2 wasteland if no title turns
   up -- the same "least invasive" identity every other titleless CK2
   province already gets, not a new mechanism.
2. :func:`patch_codes` -- the per-pixel CK2 terrain-category code grid feeds
   *both* the gameplay-terrain majority vote and the paint pass
   (``ck2ck3.map.terrain_paint``) from the very same array, so patching it
   once fixes both: a ``marsh`` row forces every one of the province's pixels
   to CK2's own ``marsh`` category (-> CK3 ``wetlands``, both gameplay and
   paint); a ``land`` row copies the code that is the mode of the
   surrounding *already-land* pixels' codes (paint edge, not vote), so the
   province reads as whatever the plateau around it already is.
3. :func:`inpaint_heights` -- the actual reason this module exists: replace
   the province's own plain-rescale elevation with a harmonic (Laplace)
   fill from the surrounding land's *already-computed* elevation, run
   *before* ``deepen_sea``, so the pin sees plateau-height pixels and never
   fires. The result becomes the "source" `heightmap_detail`'s own bound
   (`docs/step_map_heightmap.md` §2f) measures against, so the detail pass
   treats these pixels exactly like the ordinary land beside them --
   the sloped-shore treatment `docs/step_map_heightmap.md` §2h iii
   originally proposed, achieved by construction rather than a special case.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.ndimage import binary_dilation, gaussian_filter

MARSH = "marsh"
LAND = "land"
ACTIONS = (MARSH, LAND)

#: CK2 terrain.txt category name a `marsh` row forces every pixel to
#: (`ck2ck3.map.terrain.CK2_TO_CK3_TERRAIN["marsh"] == "wetlands"`)
MARSH_CATEGORY = "marsh"


@dataclass(frozen=True)
class LakeToLandRule:
    ck2_id: int
    action: str
    reason: str = ""


def read_overrides(path: str | Path) -> dict[int, LakeToLandRule]:
    """Read ``overrides/lake_to_land.csv``. Comment lines (``#``) are skipped
    (CLAUDE.md: every ``mappings``/``overrides`` CSV reader must)."""
    p = Path(path)
    if not p.exists():
        return {}
    text = p.read_text(encoding="utf-8-sig")
    lines = [ln for ln in text.splitlines() if not ln.lstrip().startswith("#")]
    out: dict[int, LakeToLandRule] = {}
    for row in csv.DictReader(lines):
        raw_id = (row.get("ck2_id") or "").strip()
        if not raw_id:
            continue
        try:
            ck2_id = int(raw_id)
        except ValueError as exc:
            raise ValueError(f"{path}: bad ck2_id {raw_id!r}") from exc
        action = (row.get("action") or "").strip().lower()
        if action not in ACTIONS:
            raise ValueError(
                f"{path}: CK2 province {ck2_id} has action {action!r}; "
                f"expected one of {ACTIONS}"
            )
        out[ck2_id] = LakeToLandRule(
            ck2_id=ck2_id, action=action,
            reason=(row.get("reason") or "").strip(),
        )
    return out


def patch_water_ids(
    rules: dict[int, LakeToLandRule],
    *,
    sea_ids: set[int],
    lake_ids: set[int],
    river_ids: set[int],
    warn=lambda msg: None,
) -> tuple[set[int], set[int], set[int]]:
    """``(sea_ids, lake_ids, river_ids)`` with every overridden CK2 id
    removed from **all three**.

    A true ``sea_zones`` id -- open ocean, in ``sea_ids`` but in neither
    ``lake_ids`` nor ``river_ids`` -- is refused: the whole point is a CK2
    province drawn on a plateau, and a true sea province is never that.

    **A CK2 lake id is also a ``sea_zones`` id** -- CK2 defines a lake as a
    sea zone inside an ``ocean_region`` named like a lake
    (``ck2read.Ck2DefaultMap.lake_ids``) -- so it is not enough to remove it
    from ``lake_ids`` alone: ``ck2ck3.map.idmap.build`` decides ``is_sea`` as
    ``in sea_ids and not in lake_ids and not in river_ids``, so a lake
    dropped from ``lake_ids`` but left in ``sea_ids`` does not become land,
    it becomes a *true sea province* -- worse than the original bug, and
    exactly what the coordinator's second real conversion run caught
    (`default.map` still listed the overridden ids, now under `sea_zones`
    instead of `lakes`; `sea` count +5 while `lakes` -5). Every id this
    module removes from `lake_ids`/`river_ids` must be removed from
    `sea_ids` in the same call, or it is not "land", it is a different kind
    of water.
    """
    sea_ids = set(sea_ids)
    lake_ids = set(lake_ids)
    river_ids = set(river_ids)
    for ck2_id in rules:
        was_lake_or_river = ck2_id in lake_ids or ck2_id in river_ids
        if ck2_id in sea_ids and not was_lake_or_river:
            warn(
                f"lake_to_land override for CK2 province {ck2_id} is a true "
                "sea zone (open ocean), not a lake/river province; ignored"
            )
            continue
        sea_ids.discard(ck2_id)
        lake_ids.discard(ck2_id)
        river_ids.discard(ck2_id)
    return sea_ids, lake_ids, river_ids


def patch_codes(
    codes_tgt: np.ndarray,
    ck3_raster: np.ndarray,
    ck2_to_ck3: dict[int, int],
    rules: dict[int, LakeToLandRule],
    code_names: list[str],
    water_mask: np.ndarray,
    *,
    ring_px: int = 6,
    warn=lambda msg: None,
) -> tuple[np.ndarray, dict]:
    """Force every overridden province's own pixels to one terrain code.

    ``marsh`` -> CK2's own ``marsh`` category code (present in
    ``code_names`` whenever CK2's ``terrain.txt`` defines the category at
    all, whether or not any pixel currently uses it -- Faerûn's is index 15).
    ``land`` -> the mode of the codes among the *already-land* pixels within
    ``ring_px`` of the province (``water_mask`` here is the water mask
    *after* :func:`patch_water_ids`, so it already excludes every overridden
    province and the ring cannot pick its own old lake code back up).
    """
    if not rules:
        return codes_tgt, {}
    codes_tgt = codes_tgt.copy()
    marsh_code = code_names.index(MARSH_CATEGORY) if MARSH_CATEGORY in code_names else None
    fallback_code = code_names.index("plains") if "plains" in code_names else (
        1 if len(code_names) > 1 else 0
    )
    stats = {"marsh": 0, "land": 0, "land_fallback": 0, "no_ck3_id": 0, "no_pixels": 0}
    for ck2_id, rule in rules.items():
        ck3_id = ck2_to_ck3.get(ck2_id)
        if ck3_id is None:
            stats["no_ck3_id"] += 1
            continue
        mask = ck3_raster == ck3_id
        if not mask.any():
            stats["no_pixels"] += 1
            continue
        if rule.action == MARSH:
            if marsh_code is None:
                warn(
                    f"lake_to_land: CK2 province {ck2_id} wants 'marsh' but "
                    "this CK2 mod's terrain.txt defines no 'marsh' category; "
                    "using plains instead"
                )
                codes_tgt[mask] = fallback_code
            else:
                codes_tgt[mask] = marsh_code
            stats["marsh"] += 1
        else:  # LAND
            ring = binary_dilation(mask, iterations=ring_px) & ~mask & ~water_mask
            vals = codes_tgt[ring]
            vals = vals[vals != 0]
            if vals.size:
                code = int(np.bincount(vals).argmax())
                stats["land"] += 1
            else:
                code = fallback_code
                stats["land_fallback"] += 1
            codes_tgt[mask] = code
    return codes_tgt, stats


def inpaint_heights(
    heights: np.ndarray,
    ck3_raster: np.ndarray,
    ck2_to_ck3: dict[int, int],
    rules: dict[int, LakeToLandRule],
    water_mask: np.ndarray,
    *,
    iterations: int = 400,
    sigma_px: float = 1.5,
) -> tuple[np.ndarray, dict]:
    """Replace every overridden province's plain-rescale elevation with a
    harmonic fill from the surrounding land.

    Iterative Gaussian-blur-and-restore (the discrete heat equation's own
    steady state is the harmonic/Laplace interpolant): every "hole" pixel is
    repeatedly set to a blur of its neighbours, every non-hole pixel is
    restored to its own original value after each pass, so the fill can only
    ever propagate inward from the true land boundary. ``water_mask`` is the
    mask *after* :func:`patch_water_ids`, so the overridden pixels are
    already "land" and are not in it -- they are found here from
    ``ck3_raster`` directly, the same way :func:`patch_codes` finds them.
    """
    if not rules:
        return heights, {}
    hole_ids = {ck2_to_ck3[cid] for cid in rules if cid in ck2_to_ck3}
    if not hole_ids:
        return heights, {"holes_px": 0}
    holes = np.isin(ck3_raster, list(hole_ids))
    if not holes.any():
        return heights, {"holes_px": 0}
    out = heights.astype(np.float32).copy()
    original = out.copy()
    fixed = ~holes  # every pixel that must keep its own value every pass
    before = out[holes]
    for _ in range(iterations):
        out = gaussian_filter(out, sigma_px, mode="nearest")
        out[fixed] = original[fixed]
    stats = {
        "holes_px": int(holes.sum()),
        "before_median": round(float(np.median(before)), 1),
        "after_median": round(float(np.median(out[holes])), 1),
        "before_min": round(float(before.min()), 1),
        "after_min": round(float(out[holes].min()), 1),
    }
    result = heights.copy()
    result[holes] = np.rint(out[holes]).astype(heights.dtype)
    return result, stats
