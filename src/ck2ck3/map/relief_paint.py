"""Relief-driven material redistribution within one CK2/CK3 terrain class.

Why this module exists. `docs/step_map_heightmap.md` §2g measured our
mountains at the right amplitude but the wrong *shape* (gradient kurtosis
0.45x vanilla, on the interior land mask) — a real defect the erosion pass
owns. This module answers a different, paint-side complaint the user raised
alongside it: even where the shape IS right, our paint cannot show it,
because one CK3 terrain class always wears one material mix regardless of
slope.

**Revision history, and why it matters.** The first version of this module
only ever *reordered* the 2-3 materials `mappings/terrain_paint.csv` already
names for a class. Coordinator review of the renders (`docs/evidence/
relief_paint/paintshade_spine_ours.png` vs `..._build17.png`, mean abs pixel
diff **0.51/255** — visually identical) found this does nothing, and
`mappings/terrain_paint.csv`'s own `mountains` row explains why:
`mountain_02` / `mountain_02_c` / `mountain_02_d_valleys` are all bare-rock
variants of the SAME material family, so reordering them can never produce a
green valley or a white crest. Vanilla's own mountains are not painted rock
— they are grass, forest floor, rock, and snow, and no permutation of three
rock textures can reach that.

**What this version does instead.** `scripts/measure_vanilla_relief_paint.py`
now measures vanilla's own material family (`forest`/`grass`/`rock`/`snow`/
`soil`/`other`) — not individual material — conditioned on
(class, slope bin, curvature bin, elevation bin), AND, separately, each
class's own top vanilla material *per family* regardless of relief
(`mappings/relief_paint_family_materials.csv`) — a class's real in-game
palette, not the 2-3 hand-picked rows in `mappings/terrain_paint.csv`. At
paint time, :func:`apply_relief_family_paint`:

1. looks up the measured family ranking for each pixel's own
   (class, slope, curvature, elevation) bin;
2. **spatially smooths the choice** (Gaussian blur of each family's score
   field at a vanilla-measured patch scale,
   `docs/evidence/vanilla_paint_family_patch_scale.csv`) so a class reads as
   patches of grass/rock/snow the way vanilla does, not per-pixel salt and
   pepper — the blur is on the *decision*, not a texture noise field, so the
   result is still fully deterministic;
3. maps the two winning families to that CLASS's OWN measured top material
   for each family and writes them into the primary/secondary
   `detail_index` slots — a real material substitution, not a permutation of
   what was already there.

**What is still preserved, and why.** The weight VALUES in
`detail_intensity` never move (only which ordinal a slot's existing weight
is attached to), so `docs/step_map_paint.md` §10's blend-statistics
invariant (`mean_nonzero_channels`, `blend_entropy_bits`,
`mean_primary_weight`) is exact by construction — those are functions of the
weight vector alone. The class map itself (`codes_tgt`/`soft.class_index`)
is never read or written, so the one-source-pixel class-boundary bound is
untouched.

**`interior_weight` defaults to 0 (apply everywhere), not a boundary
gate — measured, not assumed.** The first version of this pass tried
gating on "primary `detail_intensity` weight >= 0.7" to skip active
cross-class boundary blends. That gate fired on **0% of the canvas**: §10's
own per-class mix caps primary weight at its configured 0.55 EVERYWHERE,
including deep class interiors (measured max over the whole canvas:
**0.56**) — the weight already reflects the class's OWN 3-material split,
not distance to a boundary, so no threshold could ever separate the two.
`primary_changed_px` was 0 on the first real build because of this, caught
by coordinator review before shipping the default on. The substitution now
applies to every land pixel's primary+secondary channel; a future per-pixel
boundary DISTANCE (not weight) could still gate the secondary channel
specifically if boundary blend fidelity turns out to matter visually.
"""

from __future__ import annotations

import csv
import re
from collections.abc import Sequence
from pathlib import Path

import numpy as np

#: family vocabulary, fixed order so a numeric code is stable across a run.
#: "scree" is folded into "rock": vanilla's own `materials.settings` (115
#: ids) has a dedicated "snow" family but no dedicated scree/talus id, so a
#: separate scree bucket would have nothing real to point at
#: (`docs/step_map_paint.md` §11, `verified` against the full id list).
CATEGORY_NAMES = ("forest", "grass", "other", "rock", "snow", "soil")
CATEGORY_CODE = {name: i for i, name in enumerate(CATEGORY_NAMES)}

SLOPE_BINS = ("low", "mid", "high")
CURV_BINS = ("ridge", "flat", "valley")
ELEV_BINS = ("low", "mid", "high")

#: name heuristics over vanilla's own `materials.settings` ids. Order
#: matters: first match wins. Centralised here (not duplicated in the
#: measurement script) so the family a pixel's EXISTING material belongs to
#: and the family a NEW material is picked for are always the same
#: definition.
_CATEGORY_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("snow", re.compile(r"snow")),
    ("forest", re.compile(r"forest|jungle")),
    ("rock", re.compile(
        r"rock|cliff|mountain(?!.*valley)|desert_rocky|hills_01_rocks|"
        r"mountain_02_d_valleys"
    )),
    ("soil", re.compile(
        r"farm|paddy|floodplain|mud|dry_mud|desert_cracked|desert_flat|"
        r"desert_wavy"
    )),
    ("grass", re.compile(
        r"grass|plain|meadow|lowland|wetland|steppe_grass|steppe_bush|"
        r"drylands.*grassy|northern_plains"
    )),
]


def classify_material(material_id: str) -> str:
    """Vanilla material id -> one of the six families, else ``"other"``.

    A coarse, name-based split — not a claim about the underlying texture's
    actual albedo or slope-suitability, just a grouping fine enough that a
    101-material vocabulary does not starve every bin of samples, and that
    matches how a player actually reads the ground (grass, forest, rock,
    snow, bare soil).
    """
    for cat, pat in _CATEGORY_PATTERNS:
        if pat.search(material_id):
            return cat
    return "other"


# --------------------------------------------------------------------------- #
# reading the mapping tables
# --------------------------------------------------------------------------- #
def _skip_comments(path: Path):
    with path.open("r", encoding="utf-8", newline="") as fh:
        for line in fh:
            if not line.lstrip().startswith("#"):
                yield line


def read_material_categories(path: str | Path) -> dict[str, str]:
    """`mappings/paint_material_categories.csv` -> material id -> family."""
    p = Path(path)
    if not p.exists():
        return {}
    out: dict[str, str] = {}
    for row in csv.DictReader(_skip_comments(p)):
        mat = (row.get("material") or "").strip()
        cat = (row.get("category") or "").strip()
        if mat and cat in CATEGORY_CODE:
            out[mat] = cat
    return out


def category_of_ordinal_table(
    ordinals: dict[str, int], categories: dict[str, str]
) -> np.ndarray:
    """(256,) uint8: ordinal -> family code, default `other`."""
    out = np.full(256, CATEGORY_CODE["other"], dtype=np.uint8)
    for mat, o in ordinals.items():
        if 0 <= o < 256:
            out[o] = CATEGORY_CODE.get(categories.get(mat, "other"), CATEGORY_CODE["other"])
    return out


def read_relief_table(path: str | Path) -> dict[tuple[str, int, int, int], list[str]]:
    """`mappings/relief_paint.csv` -> (ck3_terrain, slope, curv, elev) ->
    family names ranked best-first."""
    p = Path(path)
    if not p.exists():
        return {}
    s_idx = {b: i for i, b in enumerate(SLOPE_BINS)}
    c_idx = {b: i for i, b in enumerate(CURV_BINS)}
    e_idx = {b: i for i, b in enumerate(ELEV_BINS)}
    out: dict[tuple[str, int, int, int], list[str]] = {}
    for row in csv.DictReader(_skip_comments(p)):
        key = (row.get("ck3_terrain") or "").strip()
        s = (row.get("slope_bin") or "").strip()
        c = (row.get("curvature_bin") or "").strip()
        e = (row.get("elevation_bin") or "").strip()
        rank = (row.get("category_rank") or "").strip()
        if not (key and s in s_idx and c in c_idx and e in e_idx and rank):
            continue
        cats = [c2 for c2 in rank.split(";") if c2 in CATEGORY_CODE]
        if cats:
            out[(key, s_idx[s], c_idx[c], e_idx[e])] = cats
    return out


def read_relief_shares_table(
    path: str | Path,
) -> dict[tuple[str, int, int, int], dict[str, float]]:
    """`mappings/relief_paint.csv`'s `category_shares` column ("cat=pct;...")
    -> (ck3_terrain, slope, curv, elev) -> {family: fraction (0-1)}.

    This is the PROPORTIONS the stochastic sampler in
    :func:`apply_relief_family_paint` needs, as opposed to
    :func:`read_relief_table`'s rank-only order: coordinator review found
    that painting only the argmax family per bin reproduces vanilla's
    top-1 family and nothing else (`mountains` measured at 93% rock in the
    output against vanilla's own 36% -- a real vanilla bin is a MIX, not a
    single winner, `docs/step_map_paint.md` §11).
    """
    p = Path(path)
    if not p.exists():
        return {}
    s_idx = {b: i for i, b in enumerate(SLOPE_BINS)}
    c_idx = {b: i for i, b in enumerate(CURV_BINS)}
    e_idx = {b: i for i, b in enumerate(ELEV_BINS)}
    out: dict[tuple[str, int, int, int], dict[str, float]] = {}
    for row in csv.DictReader(_skip_comments(p)):
        key = (row.get("ck3_terrain") or "").strip()
        s = (row.get("slope_bin") or "").strip()
        c = (row.get("curvature_bin") or "").strip()
        e = (row.get("elevation_bin") or "").strip()
        shares = (row.get("category_shares") or "").strip()
        if not (key and s in s_idx and c in c_idx and e in e_idx and shares):
            continue
        fracs: dict[str, float] = {}
        for part in shares.split(";"):
            if "=" not in part:
                continue
            fam, val = part.split("=", 1)
            if fam in CATEGORY_CODE:
                try:
                    fracs[fam] = float(val) / 100.0
                except ValueError:
                    continue
        total = sum(fracs.values())
        if total > 0:
            out[(key, s_idx[s], c_idx[c], e_idx[e])] = {
                k: v / total for k, v in fracs.items()
            }
    return out


#: families a hard physical rule can veto (see `apply_physical_family_gate`)
_BARE_FAMILIES = ("rock", "snow")


def build_share_table(
    shares_table: dict[tuple[str, int, int, int], dict[str, float]],
    class_names: Sequence[str],
    *,
    physical_gate: bool = True,
) -> np.ndarray:
    """(n_classes, 3, 3, 3, n_families) float32, each (class,s,c,e) row
    summing to 1 (or all-zero where unmeasured -- gated by
    :func:`build_measured_table`, same as the rank table).

    `physical_gate` (default on) applies `apply_physical_family_gate`: on
    genuinely flat, unprominent ground (slope bin 0 AND local-relief bin 0,
    every class, every curvature bin), `rock`/`snow` are forced to exactly
    zero and the remaining families renormalised. Coordinator review found
    vanilla's OWN measured share of `rock`/`snow` on `forest`'s flattest,
    least-prominent bin is still 9-11% (`docs/evidence/vanilla_paint_vs_relief.csv`
    row `forest,low,flat,low`) — real in vanilla's own Earth geography
    (temperate forest bordering real mountains), but sampling it on Faerun
    sprinkles grey/white blobs across ground that is, by construction,
    flat: no floor, no small residual probability, a hard veto.
    """
    n = len(class_names)
    out = np.zeros((n, 3, 3, 3, len(CATEGORY_NAMES)), dtype=np.float32)
    class_idx = {name: i for i, name in enumerate(class_names)}
    for (key, s, c, e), fracs in shares_table.items():
        ci = class_idx.get(key)
        if ci is None:
            continue
        row = np.zeros(len(CATEGORY_NAMES), dtype=np.float32)
        for fam, frac in fracs.items():
            row[CATEGORY_CODE[fam]] = frac
        out[ci, s, c, e] = row
    if physical_gate:
        apply_physical_family_gate(out)
    return out


def apply_physical_family_gate(share_table: np.ndarray) -> np.ndarray:
    """In place: zero `rock`/`snow` at (slope bin 0, elevation bin 0) --
    genuinely flat, unprominent ground, any class, any curvature bin -- and
    renormalise the remaining families back to summing to 1. A no-op on a
    row that was already all-zero (unmeasured; `build_measured_table` keeps
    those pixels untouched regardless)."""
    bare = [CATEGORY_CODE[f] for f in _BARE_FAMILIES]
    flat = share_table[:, 0, :, 0, :]  # (n_cls, 3(curv), n_fam) view
    removed = flat[..., bare].sum(axis=-1, keepdims=True)
    flat[..., bare] = 0.0
    total = flat.sum(axis=-1, keepdims=True)
    # renormalise only rows that had SOME mass left (an all-bare row, e.g.
    # a class vanilla only ever paints as rock/snow, is left all-zero --
    # `apply_relief_family_paint`'s own dup-fallback and dead-channel refill
    # already handle an all-zero row safely, same as any unmeasured bin)
    scale = np.where(total > 0, 1.0 / np.maximum(total, 1e-12), 0.0)
    flat *= scale
    del removed
    return share_table


def read_family_material_table(path: str | Path) -> dict[tuple[str, str], str]:
    """`mappings/relief_paint_family_materials.csv` -> (ck3_terrain, family)
    -> vanilla material id (that class's own measured top pick for that
    family, `scripts/measure_vanilla_relief_paint.py`)."""
    p = Path(path)
    if not p.exists():
        return {}
    out: dict[tuple[str, str], str] = {}
    for row in csv.DictReader(_skip_comments(p)):
        key = (row.get("ck3_terrain") or "").strip()
        fam = (row.get("family") or "").strip()
        mat = (row.get("material") or "").strip()
        if key and fam in CATEGORY_CODE and mat:
            out[(key, fam)] = mat
    return out


def build_priority_table(
    relief_table: dict[tuple[str, int, int, int], list[str]],
    class_names: Sequence[str],
) -> np.ndarray:
    """(n_classes, 3, 3, 3, n_families) float32: lower = higher priority.

    A `(class, s, c, e)` combination missing from `relief_table` (too few
    vanilla samples, or a class vanilla never paints at all) gets a uniform
    row (every family ties). :func:`apply_relief_family_paint` does not act
    on a uniform row's own pixels at all -- see :func:`build_measured_table`,
    which is the actual "was this combination measured" gate; a uniform
    priority row alone is not treated as meaningful data.
    """
    n = len(class_names)
    out = np.zeros((n, 3, 3, 3, len(CATEGORY_NAMES)), dtype=np.float32)
    class_idx = {name: i for i, name in enumerate(class_names)}
    for (key, s, c, e), cats in relief_table.items():
        ci = class_idx.get(key)
        if ci is None:
            continue
        worst = float(len(cats))
        row = np.full(len(CATEGORY_NAMES), worst, dtype=np.float32)
        for rank, cat in enumerate(cats):
            row[CATEGORY_CODE[cat]] = float(rank)
        out[ci, s, c, e] = row
    return out


def build_measured_table(
    relief_table: dict[tuple[str, int, int, int], list[str]],
    class_names: Sequence[str],
) -> np.ndarray:
    """(n_classes, 3, 3, 3) bool: was this exact (class, s, c, e) combination
    actually measured? A pixel whose own combination was never measured
    (too few vanilla samples, class-family unmeasured) must not be painted
    at all — a uniform `build_priority_table` row would otherwise resolve to
    family 0 ("forest") for every such pixel regardless of what the class
    actually is, which is worse than doing nothing.
    """
    n = len(class_names)
    out = np.zeros((n, 3, 3, 3), dtype=bool)
    class_idx = {name: i for i, name in enumerate(class_names)}
    for key, s, c, e in relief_table:
        ci = class_idx.get(key)
        if ci is not None:
            out[ci, s, c, e] = True
    return out


def family_material_ordinal_table(
    class_names: Sequence[str],
    family_table: dict[tuple[str, str], str],
    ordinals: dict[str, int],
    *,
    fallback_ordinal: dict[str, int] | None = None,
    missing: set[tuple[str, str]] | None = None,
) -> np.ndarray:
    """(n_classes, n_families) uint8: class + family -> material ordinal.

    A `(class, family)` vanilla never measured a material for (or whose
    material has no ordinal in this run's `materials.settings`) falls back
    to `fallback_ordinal[class]` (that class's own already-configured
    primary ordinal) — never ordinal 0, which is a seasonal effect layer,
    not terrain art (`docs/step_map_paint.md` invariant).
    """
    n_cls = len(class_names)
    n_fam = len(CATEGORY_NAMES)
    out = np.zeros((n_cls, n_fam), dtype=np.uint8)
    fallback_ordinal = fallback_ordinal or {}
    for ci, key in enumerate(class_names):
        default_o = fallback_ordinal.get(key, 0)
        for fam, fam_code in CATEGORY_CODE.items():
            mat = family_table.get((key, fam))
            o = ordinals.get(mat) if mat else None
            if o is None:
                if missing is not None:
                    missing.add((key, fam))
                o = default_o
            out[ci, fam_code] = o
    return out


# --------------------------------------------------------------------------- #
# relief bins, computed on OUR OWN finished heightmap
# --------------------------------------------------------------------------- #
#: vanilla's own measured (p33, p66) cutoffs for SLOPE and CURVATURE, baked
#: in so a normal conversion run has no dependency on `docs/evidence/*.csv`
#: (`scripts/measure_vanilla_relief_paint.py`, `verified` against vanilla's
#: own aligned `heightmap.png`, same convention `DEFAULT_HF_TARGETS`
#: elsewhere in this repo uses). **Fixed absolute thresholds, not a
#: per-map percentile** — coordinator review found that binning Faerun's OWN
#: slope by ITS OWN percentile put snow/rock on flat lowland forest:
#: Faerun's taller mountains skew what counts as "high" on a whole-map
#: basis, so a genuinely flat pixel could still land in vanilla's
#: high-slope bin, which the measured table associates with rock/snow.
#: Applying vanilla's own absolute cutoffs to Faerun instead means "low
#: slope" always means the same real-world grade on both maps, because the
#: canvas is built to match vanilla's own km/px (`docs/map_scale.md`) and
#: both maps' 16-bit height encodes world units at within 2% of the same
#: `WORLD_EXTENTS_Y` (vanilla 50, Faerun 51, `assumed` close enough not to
#: convert). Elevation does NOT get a fixed cutoff here — see
#: `compute_relief_bins`'s own docstring for why it is a PER-CLASS
#: percentile instead (a second, later coordinator finding: even a
#: whole-map-fixed local-relief cutoff over-painted Thay's uniformly
#: textured plateau).
VANILLA_SLOPE_CUTOFFS = (21.1321, 58.6177)
VANILLA_CURVATURE_CUTOFFS = (-0.6758, 0.4072)
#: local-relief smoothing width, canvas px -- must match
#: `scripts/measure_vanilla_relief_paint.py::LOCAL_RELIEF_SIGMA_PX` exactly,
#: since the cutoffs above were measured at this scale.
LOCAL_RELIEF_SIGMA_PX = 24.0


def compute_relief_bins(
    heights: np.ndarray,
    shape: tuple[int, int],
    *,
    land_mask: np.ndarray,
    cls: np.ndarray,
    n_classes: int,
    resolution_factor: int = 1,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """`(slope_bin, curvature_bin, elevation_bin)`, each `shape` uint8 in 0..2.

    `heights` may be at `resolution_factor`x the canvas (CK3's optional 2x
    heightmap); it is strided down to `shape` first, the same convention
    `paint_edges.relief_warp` uses.

    **Slope and curvature are FIXED absolute thresholds** measured on
    vanilla itself (`VANILLA_SLOPE_CUTOFFS`/`VANILLA_CURVATURE_CUTOFFS`), not
    a per-map percentile: they are comparable across two maps built to the
    same km/px (`docs/map_scale.md`), so "low slope" means the same
    real-world grade on both.

    **Elevation is a PER-CLASS percentile of LOCAL relief** (height above a
    Gaussian-blurred local base, `LOCAL_RELIEF_SIGMA_PX` — a flat lowland
    pixel reads ~0 regardless of the map's absolute height range), computed
    within each of `cls`'s own `n_classes` groups separately. Coordinator
    review, twice: (1) raw elevation is whole-map-relative, so Faerun's
    taller mountains overall put flat lowland forest in a "high" bin; fixed
    by switching to local relief. (2) A single WHOLE-MAP percentile of local
    relief was still wrong — Thay's uniformly-textured eroded plateau then
    sat in the "high" tercile almost everywhere (the class's own texture is
    rougher than the map average), painting rock/snow broadly rather than
    on real crests. Per-class percentile means "high" is always "the
    roughest third of THIS class's own pixels", so a class's internal
    variation decides the bin, never the map's overall roughness -- the
    same design vanilla's own measured table already conditions on
    (`scripts/measure_vanilla_relief_paint.py` computes it identically,
    per class, on vanilla's own land).

    `cls` is a `shape` array of class-code indices in `[0, n_classes)` (the
    CK2-category -> CK3-terrain-key lookup `paint_edges.build_soft_blend`
    itself uses, computed early — see `build.py`'s own call site).
    """
    from scipy.ndimage import gaussian_filter

    h, w = shape
    hh, hw = heights.shape[:2]
    fy = max(1, hh // h)
    fx = max(1, hw // w)
    z = heights[: h * fy : fy, : w * fx : fx].astype(np.float32, copy=True)
    if z.shape != (h, w):  # pragma: no cover - defensive, non-integer factors
        z = np.asarray(z, dtype=np.float32)[:h, :w]

    # MESO-SCALE, not raw per-pixel: slope and curvature are measured on the
    # SAME Gaussian-blurred height field elevation uses
    # (`LOCAL_RELIEF_SIGMA_PX`), not the raw heightmap. Coordinator review,
    # third pass: raw-pixel slope/curvature still flip bins every few pixels
    # on a class the erosion pass deliberately roughens at a 2-14 canvas px
    # scale (`docs/step_map_heightmap.md` §2c/§2g) -- Thay's plateau -- and
    # no amount of smoothing the STOCHASTIC DRAW in
    # `apply_relief_family_paint` can produce vanilla-sized patches from a
    # condition (which bin a pixel is in) that already flips at pixel scale.
    z_meso = gaussian_filter(z, LOCAL_RELIEF_SIGMA_PX)
    local_relief = z - z_meso
    del z

    gy, gx = np.gradient(z_meso)
    slope = np.hypot(gy, gx)
    del gy, gx

    lap = -4.0 * z_meso
    lap += np.roll(z_meso, 1, axis=0)
    lap += np.roll(z_meso, -1, axis=0)
    lap += np.roll(z_meso, 1, axis=1)
    lap += np.roll(z_meso, -1, axis=1)
    del z_meso

    def _fixed_bin(values: np.ndarray, cutoffs: tuple[float, float]) -> np.ndarray:
        p33, p66 = cutoffs
        out = np.zeros(values.shape, dtype=np.uint8)
        out[values >= p33] = 1
        out[values >= p66] = 2
        return out

    slope_bin = _fixed_bin(slope, VANILLA_SLOPE_CUTOFFS)
    del slope

    p33, p66 = VANILLA_CURVATURE_CUTOFFS
    curv_bin = np.full((h, w), 1, dtype=np.uint8)  # flat
    curv_bin[lap < p33] = 0  # ridge (concave down)
    curv_bin[lap > p66] = 2  # valley (concave up)
    del lap

    land = land_mask if land_mask.shape == (h, w) else np.ones((h, w), dtype=bool)
    elev_bin = np.zeros((h, w), dtype=np.uint8)
    for c in range(n_classes):
        cls_land = land & (cls == c)
        if not cls_land.any():
            continue
        sample = local_relief[cls_land]
        p33c, p66c = np.percentile(sample, [33.333, 66.667])
        vals = local_relief[cls_land]
        out = np.zeros(vals.shape, dtype=np.uint8)
        out[vals >= p33c] = 1
        out[vals >= p66c] = 2
        elev_bin[cls_land] = out
    return slope_bin, curv_bin, elev_bin


def build_class_eligible_mask(
    cls: np.ndarray,
    class_names: Sequence[str],
    relief_paint_classes: Sequence[str],
    slope_bin: np.ndarray,
    elev_bin: np.ndarray,
) -> np.ndarray:
    """`cls.shape` bool: True where relief-paint substitution should touch a
    pixel AT ALL -- both a class-level and a within-class gate.

    **Coordinator review, round 3.** Restricting rock/snow probability on
    flat ground (`apply_physical_family_gate`) fixed the specific defect it
    was built for, but a render check found two more: `taiga` (a class NOT
    in that gate's scope for other families) still showed white/grey
    speckle on flat ground, and `sword_coast` (mostly `plains`/`forest`,
    genuinely flat) turned into "camouflage" -- grass/forest/soil/other
    blobs sampled independently per pixel with no relation to the ground,
    worse than doing nothing. Root cause is this module's own first
    measurement (`docs/evidence/vanilla_paint_vs_relief.md`): relief
    explains only **2-8%** of a class's own material entropy -- on
    genuinely flat, low ground the measured conditional is close to that
    class's UNCONDITIONAL mix, so per-pixel stochastic sampling from it is
    almost pure noise with no spatial structure for a viewer to read as
    "relief". `mountains`/`hills`-type classes are the exception because
    their own slope/elevation range is wide enough that the conditional
    actually differs bin to bin.

    So: substitute only within the classes named in `relief_paint_classes`
    (default `("mountains", "desert_mountains", "hills")` -- the CK3
    terrain keys whose own relief range is wide, `docs/step_map_paint.md`
    §11), AND only where `slope_bin > 0 OR elev_bin > 0` -- the same
    flat-and-unprominent threshold `apply_physical_family_gate` already
    uses for rock/snow specifically, now gating every family, and every
    class outside the allow-list gets **zero** substitution: its
    `detail_index`/`detail_intensity` stay byte-identical to §10's own
    output (`tests/test_map_relief_paint.py::
    test_apply_relief_family_paint_leaves_excluded_classes_byte_identical`).
    """
    allowed = {i for i, name in enumerate(class_names) if name in set(relief_paint_classes)}
    if not allowed:
        return np.zeros(cls.shape, dtype=bool)
    class_ok = np.isin(cls, np.array(sorted(allowed), dtype=cls.dtype))
    relief_ok = (slope_bin > 0) | (elev_bin > 0)
    return class_ok & relief_ok


def compute_slope_percentile_mask(
    heights: np.ndarray,
    shape: tuple[int, int],
    *,
    land_mask: np.ndarray,
    percentile: float,
    resolution_factor: int = 1,
) -> np.ndarray:
    """`shape` bool: True where the land slope exceeds `percentile` of the
    land slope distribution -- the tree-scatter slope gate
    (`docs/step_map_paint.md` §11, `scripts/measure_vanilla_tree_slope.py`).
    Independent of :func:`compute_relief_bins` so a run with
    `trees_slope_gate = true` but `relief_paint = false` does not need the
    paint table at all.
    """
    h, w = shape
    hh, hw = heights.shape[:2]
    fy = max(1, hh // h)
    fx = max(1, hw // w)
    z = heights[: h * fy : fy, : w * fx : fx].astype(np.float32, copy=True)
    if z.shape != (h, w):  # pragma: no cover - defensive
        z = np.asarray(z, dtype=np.float32)[:h, :w]
    gy, gx = np.gradient(z)
    slope = np.hypot(gy, gx)
    land = land_mask if land_mask.shape == (h, w) else np.ones((h, w), dtype=bool)
    sample = slope[land] if land.any() else slope.reshape(-1)
    if sample.size == 0:
        return np.zeros((h, w), dtype=bool)
    cutoff = float(np.percentile(sample, percentile))
    return slope > cutoff


# --------------------------------------------------------------------------- #
# the family-level redistribution
# --------------------------------------------------------------------------- #
#: fixed seeds for the two independent coherent-noise draws (primary,
#: secondary channel) -- deterministic across runs/processes, like every
#: other seeded field in this converter (`paint_edges` seed=11,
#: `tree_scatter` seed=4242).
DEFAULT_SEED_PRIMARY = 8161
DEFAULT_SEED_SECONDARY = 8167


def _coherent_uniform_field(
    shape: tuple[int, int], *, sigma_px: float, seed: int
) -> np.ndarray:
    """A spatially-coherent field, uniform on [0, 1), via a Gaussian copula:
    blur iid standard-normal noise (correlation length ~`sigma_px`), rescale
    to unit variance (a Gaussian blur divides variance by
    `sum(kernel**2)`, so skipping this step would concentrate the field
    near 0.5 and starve the tails), then map through the standard normal
    CDF -- exactly uniform marginal, spatially smooth by construction.
    """
    from scipy.ndimage import gaussian_filter
    from scipy.stats import norm

    rng = np.random.default_rng(seed)
    z = rng.standard_normal(shape).astype(np.float32)
    if sigma_px > 0:
        z = gaussian_filter(z, sigma_px)
        std = float(z.std())
        if std > 1e-9:
            z /= std
    return norm.cdf(z).astype(np.float32)


def apply_relief_family_paint(
    index: np.ndarray,
    intensity: np.ndarray,
    cls: np.ndarray,
    class_names: Sequence[str],
    slope_bin: np.ndarray,
    curv_bin: np.ndarray,
    elev_bin: np.ndarray,
    *,
    shares_table: dict[tuple[str, int, int, int], dict[str, float]],
    family_mat_table: np.ndarray,
    sigma_px: float = 6.0,
    interior_weight: float = 0.0,
    land_mask: np.ndarray | None = None,
    eligible_mask: np.ndarray | None = None,
    seed_primary: int = DEFAULT_SEED_PRIMARY,
    seed_secondary: int = DEFAULT_SEED_SECONDARY,
) -> tuple[np.ndarray, dict]:
    """Substitute the primary/secondary `detail_index` material by
    STOCHASTIC sampling from the CLASS's own measured family MIX for the
    pixel's `(slope, curvature, elevation)` bin, on every pixel whose own
    bin was actually measured (`build_measured_table`) and whose primary
    weight is >= `interior_weight` (default 0, i.e. every land pixel — see
    the module docstring for why a weight-based interior/boundary gate does
    not work here).

    **Why sampling, not argmax.** The first version of this function picked
    the single highest-RANKED family per bin (after spatially smoothing the
    rank). Coordinator review measured the result: `mountains` painted 93%
    rock against vanilla's own measured 36% -- a real vanilla bin is a MIX
    (e.g. `mountains` at high slope+elevation+ridge is 31% snow, 29% rock,
    18% grass, `docs/evidence/vanilla_paint_vs_relief.csv`), and an argmax
    can only ever reproduce the single largest share, never the rest.
    Sampling from the actual proportions (inverse-CDF against a spatially
    coherent uniform field, so the DRAW is smooth even though the outcome is
    stochastic) reproduces the whole mix in expectation, which is what
    `scripts/verify_relief_paint_family_shares.py` checks per class.

    Unlike the v1 permutation (`apply_relief_redistribution`, superseded —
    see the module docstring), this introduces a material `detail_index`
    channel 0/1 may not have carried before, so it can put snow on a crest a
    class's default 2-3-material mix never named. `intensity` (the weight
    VALUES) is read but never written.

    `eligible_mask` (default None = every measured pixel, kept for
    call-site/test back-compat) is `build_class_eligible_mask`'s output:
    False there means the pixel is left **completely untouched**, index AND
    intensity byte-identical to the input — see that function's docstring
    for why (round-3 coordinator review: relief paint outside a class whose
    own relief range is wide reads as noise, not signal).
    """
    n_fam = len(CATEGORY_NAMES)
    share = build_share_table(shares_table, class_names)  # (n_cls,3,3,3,n_fam)
    frac_of_fam = share[cls, slope_bin, curv_bin, elev_bin]  # (H, W, n_fam) f32
    del share
    measured_table = build_measured_table(shares_table, class_names)  # (n_cls,3,3,3)
    has_data = measured_table[cls, slope_bin, curv_bin, elev_bin]  # (H, W) bool
    del measured_table

    cdf = np.cumsum(frac_of_fam, axis=-1)
    del frac_of_fam

    u1 = _coherent_uniform_field(cls.shape, sigma_px=sigma_px, seed=seed_primary)
    u2 = _coherent_uniform_field(cls.shape, sigma_px=sigma_px, seed=seed_secondary)
    best1_fam = np.argmax(cdf >= u1[..., None], axis=-1).astype(np.uint8)
    best2_fam = np.argmax(cdf >= u2[..., None], axis=-1).astype(np.uint8)
    del cdf, u1, u2

    fam1_mat = family_mat_table[cls, best1_fam]
    fam2_mat = family_mat_table[cls, best2_fam]
    del best1_fam, best2_fam
    # never write the same ordinal into two channels of one pixel
    # (`docs/step_map_paint.md` invariant: vanilla never repeats an ordinal
    # among a pixel's live channels) -- fall back to the pixel's own
    # original channel-1 material when the two draws resolve the same.
    dup = fam2_mat == fam1_mat
    fam2_mat = np.where(dup, index[..., 1], fam2_mat)
    del dup

    primary_share = intensity[..., 0].astype(np.float32) / 255.0
    interior = (primary_share >= interior_weight) & has_data
    del primary_share, has_data
    if land_mask is not None:
        interior = interior & land_mask
    if eligible_mask is not None:
        interior = interior & eligible_mask

    out = index.copy()
    changed = interior & (out[..., 0] != fam1_mat)
    out[..., 0] = np.where(interior, fam1_mat.astype(np.uint8), out[..., 0])
    out[..., 1] = np.where(interior, fam2_mat.astype(np.uint8), out[..., 1])
    del fam1_mat, fam2_mat

    # refill dead (zero-weight) channels with the pixel's own (possibly new)
    # primary, the same invariant `paint_edges.build_soft_blend` enforces.
    dead = intensity == 0
    out = np.where(dead, out[..., :1], out)

    n_land = int(interior.sum()) if land_mask is None else int((land_mask).sum())
    stats = {
        "interior_px": int(interior.sum()),
        "land_px": n_land,
        "primary_changed_px": int(changed.sum()),
        "primary_changed_share": round(float(changed.sum()) / n_land, 6) if n_land else 0.0,
        "eligible_px": int(eligible_mask.sum()) if eligible_mask is not None else n_land,
        "eligible_share": (
            round(float(eligible_mask.sum()) / n_land, 6)
            if eligible_mask is not None and n_land
            else (1.0 if n_land else 0.0)
        ),
        "sigma_px": float(sigma_px),
        "interior_weight": float(interior_weight),
    }
    return out, stats
