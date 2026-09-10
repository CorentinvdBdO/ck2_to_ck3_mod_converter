"""``gfx/map/map_object_data/generated/*.txt`` — CK2 ``trees.bmp`` -> CK3 trees.

`docs/map_fidelity.md` §1.4/§4.3: CK3 has no tree bitmap, only placed mesh
instances (18 vanilla files under ``gfx/map/map_object_data/generated/``,
one ``object={}`` block per mesh variant, ``count=`` + a flat ``transform=``
matrix list). Lane `map-ui` emptied all 18 (``locators.render_foliage_stubs``)
because vanilla's own coordinates sit inside vanilla's 9216x4608 sheet and
would otherwise draw trees in our ocean. This module repopulates them from
Faerûn's own ``trees.bmp``.

**Density.** Vanilla 1.19 places 549,126 instances across its own 9216x4608
canvas — 1.293e-5 instances per canvas pixel (`verified`,
``scripts/verify_tree_density.py`` sums ``count=`` over the real generated
files). Applying that same rate to our 8320x6784 canvas targets ~730k
instances, matching ``docs/map_fidelity.md`` §4.3's own estimate.

**Species.** ``docs/map_fidelity.md`` §1.4 found ``trees.bmp``'s palette
structure (three colour triples, `assumed` to be three species at three
densities each) but no confirmed index->species mapping — CK2 resolves them
against a single ``Tree_Diffuse.dds`` atlas the palette alone does not name.
Rather than guess a colour->species table, this module picks the *mesh* from
the pixel's own **CK3 terrain classification** (the per-province majority
vote ``ck2ck3.map.terrain`` already computed, reused here exactly as
``build.py`` reuses it for the heightmap-detail gain field) via
``mappings/tree_meshes.csv``: forest -> broadleaf, taiga -> pine, jungle ->
jungle canopy, wetlands -> reeds, steppe -> bushes, oasis -> palm. This is
more grounded than the palette colour, and it means a class Faerûn never
paints (mountains, desert, plains, ...) simply gets no trees, the same
"still a documented row, just unused" contract ``terrain_paint.csv`` uses.

**What "any nonzero trees.bmp pixel" means.** CK2's ``default.map`` `tree`
list (``{ 3 4 7 10 }`` for both vanilla and Faerûn, `verified`) marks the
*subset* of palette indices that force automatic terrain reclassification to
forest — a narrower thing than "has canopy". The full canopy is every nonzero
index (`docs/map_fidelity.md` §1.4: 90.8% of Faerûn's ``trees.bmp`` is index
0, i.e. no trees; the rest is the nine tree indices at various species and
densities), so this module scatters over that wider set.

**Format**, `verified` against the real vanilla files
(``gfx/map/map_object_data/generated/tree_pine_01_a_generator_1.txt``): each
``object={}`` names a mesh (``pdxmesh=``), a ``layer=`` and a ``count=``, then
one line per instance in ``transform=`` — 10 floats, ``x y z qx qy qz qw sx sy
sz`` in exactly the locator frame (``ck2ck3.map.locators.world_position`` /
``yaw_quaternion``, reused unchanged so the bottom-up ``z`` convention is
never re-derived), scale always ``1 1 1`` in every sampled vanilla instance.
"""

from __future__ import annotations

import csv
import io
import re
import zlib
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from . import locators

GENERATED_DIR = f"{locators.MAP_OBJECT_DIR}/generated"

#: vanilla 1.19: 549,126 instances over its own 9216x4608 canvas
#: (`verified`, scripts/verify_tree_density.py)
VANILLA_INSTANCES = 549_126
VANILLA_CANVAS_PX = 9216 * 4608
VANILLA_DENSITY_PER_PX = VANILLA_INSTANCES / VANILLA_CANVAS_PX

_HEAD_RE = re.compile(
    r'name="([^"]+)"[^{}]*?layer="([^"]+)"[^{}]*?pdxmesh="([^"]+)"', re.S
)


@dataclass(frozen=True)
class MeshInfo:
    """One vanilla ``object={}`` header, read live from the game files."""

    file: str
    name: str
    layer: str
    pdxmesh: str
    clamp_to_water_level: bool = False


def read_generated_heads(game_dir: Path) -> dict[str, MeshInfo]:
    """The *first* ``object={}`` header of every vanilla generated file.

    A vanilla file may carry several blocks (mesh variants of one species,
    e.g. ``tree_pine_single_01_a/b/c_mesh``); this module writes one
    consolidated block per file, so only the first head's identity is used —
    a documented simplification (``docs/step_map_paint.md §9``), not a
    parse limitation.
    """
    out: dict[str, MeshInfo] = {}
    src_dir = Path(game_dir) / GENERATED_DIR
    if not src_dir.is_dir():
        return out
    for src in sorted(src_dir.glob("*.txt")):
        text = src.read_text(encoding="utf-8-sig", errors="replace")
        m = _HEAD_RE.search(text)
        if not m:
            continue
        name, layer, mesh = m.groups()
        out[src.name] = MeshInfo(file=src.name, name=name, layer=layer, pdxmesh=mesh)
    return out


def read_mesh_table(path: Path) -> dict[str, str]:
    """``mappings/tree_meshes.csv``: CK3 terrain key -> generated file name.

    A terrain key with an empty ``file`` column (or absent from the table)
    gets no trees; skips comment lines like every other ``mappings/*.csv``.
    """
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    with path.open("r", encoding="utf-8", newline="") as fh:
        rows = csv.DictReader(line for line in fh if not line.lstrip().startswith("#"))
        for row in rows:
            key = (row.get("ck3_terrain") or "").strip()
            f = (row.get("file") or "").strip()
            if key:
                out[key] = f
    return out


def forest_mask_from_trees_bmp(trees_idx: np.ndarray) -> np.ndarray:
    """Boolean, same shape: any nonzero ``trees.bmp`` palette index."""
    return trees_idx != 0


def upsample_to_source(small: np.ndarray, src_h: int, src_w: int) -> np.ndarray:
    """Nearest-neighbour upsample ``trees.bmp`` (1/8 scale) to province-bitmap size.

    CK2's tree bitmap is exactly 1/8 the province bitmap on each axis
    (`verified`, ``docs/map_fidelity.md`` §1.4); a mod whose ratio is not
    exactly integer still gets a sane result, cropped/padded to
    ``(src_h, src_w)``.
    """
    sh, sw = small.shape[:2]
    fy = max(1, round(src_h / sh))
    fx = max(1, round(src_w / sw))
    up = np.repeat(np.repeat(small, fy, axis=0), fx, axis=1)
    out = np.zeros((src_h, src_w), dtype=small.dtype)
    h = min(src_h, up.shape[0])
    w = min(src_w, up.shape[1])
    out[:h, :w] = up[:h, :w]
    return out


def pick_points(
    eligible: np.ndarray,
    *,
    target_total: int,
    seed: int = 4242,
    jitter: float = 0.9,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """The density half of the scatter: *where* the trees stand.

    Picks up to ``target_total`` points uniformly at random from the eligible
    (forest & land & passable) pixels via a partition on a random key array —
    O(n), deterministic given ``seed`` — then jitters each within its own
    pixel cell so the result does not read as a grid.

    Returns ``(py, px, fx, fy)``: the integer pixel each point belongs to (for
    the per-pixel lookups) and its jittered float canvas position.  Shared by
    the terrain-only ``scatter`` and the regional ``scatter_regional`` so the
    two differ **only** in which mesh each point gets, never in how many
    points there are or where — the density contract of
    ``docs/step_map_paint.md`` §9.2.
    """
    ys, xs = np.nonzero(eligible)
    n_eligible = ys.size
    empty = np.zeros(0, dtype=np.int64)
    if n_eligible == 0 or target_total <= 0:
        return empty, empty, empty.astype(np.float64), empty.astype(np.float64)
    rng = np.random.default_rng(seed)
    k = min(target_total, n_eligible)
    if k < n_eligible:
        keys = rng.random(n_eligible)
        idx = np.argpartition(keys, k - 1)[:k]
    else:
        idx = np.arange(n_eligible)
    py, px = ys[idx], xs[idx]
    fx = px.astype(np.float64) + 0.5 + rng.uniform(-jitter, jitter, size=k)
    fy = py.astype(np.float64) + 0.5 + rng.uniform(-jitter, jitter, size=k)
    return py, px, fx, fy


def scatter(
    eligible: np.ndarray,
    terrain_code: np.ndarray,
    terrain_keys: list[str],
    mesh_of_terrain: dict[str, str],
    *,
    target_total: int,
    seed: int = 4242,
    jitter: float = 0.9,
) -> tuple[dict[str, np.ndarray], int, dict[str, int]]:
    """Terrain-only mesh choice (``[map] trees_regional = false``).

    Groups ``pick_points``'s scatter by the generated file the pixel's CK3
    terrain key maps to in ``mappings/tree_meshes.csv``.

    Returns ``(file -> (n, 2) float array of (x, y) canvas pixels, dropped,
    dropped_by_terrain)`` where ``dropped`` counts points whose terrain key
    has no row (or an empty row) in ``mesh_of_terrain`` — logged, never
    silently invented, same contract as ``terrain_paint``'s
    ``missing_material`` — and ``dropped_by_terrain`` breaks that down by CK3
    terrain key, for the run report.
    """
    py, px, fx, fy = pick_points(
        eligible, target_total=target_total, seed=seed, jitter=jitter
    )
    k = py.size
    if k == 0:
        return {}, 0, {}

    file_names = sorted({f for f in mesh_of_terrain.values() if f})
    file_index = {f: i for i, f in enumerate(file_names)}
    file_of_key = np.full(len(terrain_keys), -1, dtype=np.int32)
    for i, key in enumerate(terrain_keys):
        f = mesh_of_terrain.get(key, "")
        if f:
            file_of_key[i] = file_index[f]

    codes = terrain_code[py, px]
    file_ids = file_of_key[codes]

    out: dict[str, np.ndarray] = {}
    for f, fi in file_index.items():
        sel = file_ids == fi
        if sel.any():
            out[f] = np.stack([fx[sel], fy[sel]], axis=1)
    drop_mask = file_ids < 0
    dropped = int(drop_mask.sum())
    dropped_by_terrain: dict[str, int] = {}
    if dropped:
        drop_codes = codes[drop_mask]
        for code, n in zip(*np.unique(drop_codes, return_counts=True)):
            dropped_by_terrain[terrain_keys[int(code)]] = int(n)
    return out, dropped, dropped_by_terrain


# --------------------------------------------------------------------------
# regional mix: P(mesh | terrain, climate, latitude band)
# --------------------------------------------------------------------------

#: north-to-south canvas row bands the mix table is conditioned on (deciles,
#: band 0 = northernmost).  Must equal ``N_BANDS`` in
#: ``scripts/measure_vanilla_tree_mix.py``, which wrote the table; pinned by
#: ``tests/test_map_tree_mix.py::test_mix_csv_bands_match_the_sampler``.
N_LAT_BANDS = 10
#: the ``climate``/``lat_band`` value that means "marginalised over"
MIX_WILDCARD = "*"


@dataclass(frozen=True)
class MixDist:
    """One conditional distribution over generated files, as a CDF."""

    files: tuple[str, ...]
    cdf: tuple[float, ...]


def _dist_from_weights(weights: dict[str, float]) -> MixDist | None:
    items = [(f, w) for f, w in sorted(weights.items()) if w > 0]
    total = sum(w for _f, w in items)
    if not items or total <= 0:
        return None
    acc = 0.0
    cdf = []
    for _f, w in items:
        acc += w / total
        cdf.append(acc)
    cdf[-1] = 1.0
    return MixDist(tuple(f for f, _w in items), tuple(cdf))


def read_mix_table(path: Path) -> dict[tuple[str, str, str], MixDist]:
    """``mappings/tree_mix.csv`` -> ``(terrain, climate, band) -> MixDist``.

    Columns ``ck3_terrain,climate,lat_band,file,count,p``; ``p`` is used when
    present and ``count`` otherwise, and each condition is renormalised so a
    hand-trimmed table still sums to 1.  Skips ``#`` comment lines like every
    other ``mappings/*.csv`` (the file opens with a ``# GENERATED`` block).
    """
    weights: dict[tuple[str, str, str], dict[str, float]] = {}
    if not Path(path).is_file():
        return {}
    with Path(path).open("r", encoding="utf-8", newline="") as fh:
        rows = csv.DictReader(line for line in fh if not line.lstrip().startswith("#"))
        for row in rows:
            key = (
                (row.get("ck3_terrain") or "").strip(),
                (row.get("climate") or "").strip() or MIX_WILDCARD,
                (row.get("lat_band") or "").strip() or MIX_WILDCARD,
            )
            f = (row.get("file") or "").strip()
            if not key[0] or not f:
                continue
            raw = (row.get("p") or "").strip() or (row.get("count") or "").strip()
            try:
                w = float(raw)
            except ValueError:
                continue
            weights.setdefault(key, {})[f] = weights.setdefault(key, {}).get(f, 0.0) + w
    out: dict[tuple[str, str, str], MixDist] = {}
    for key, ws in weights.items():
        d = _dist_from_weights(ws)
        if d is not None:
            out[key] = d
    return out


def apply_mix_overrides(
    table: dict[tuple[str, str, str], MixDist],
    overrides: dict[tuple[str, str, str], MixDist],
) -> dict[tuple[str, str, str], MixDist]:
    """``overrides/tree_mix.csv`` wins over the measured table, per condition.

    An override row set **replaces** the measured distribution for its exact
    ``(terrain, climate, lat_band)`` key — it is not blended — so forcing a
    region's species is one obvious edit, and a condition nobody overrode is
    untouched.  Same "human input lives in ``overrides/``" contract as the
    rest of the converter.
    """
    merged = dict(table)
    merged.update(overrides)
    return merged


def resolve_mix(
    table: dict[tuple[str, str, str], MixDist], terrain: str, climate: str, band: int
) -> tuple[MixDist | None, str]:
    """The fallback chain, most specific first.

    ``(terrain, climate, band)`` -> ``(terrain, *, band)`` ->
    ``(terrain, *, band-1)`` -> ``(terrain, *, band+1)`` ->
    ``(terrain, climate, *)`` -> ``(terrain, *, *)`` -> nothing.

    **Latitude before climate, because that is what vanilla measures**
    (``docs/evidence/vanilla_tree_mix_conditioning.csv``, written by
    ``scripts/build_tree_mix_csv.py``): over vanilla's own 549,126 instances,
    knowing the terrain alone predicts the generator 49.8 % of the time at
    2.056 bits of cross-entropy; adding the latitude band takes that to
    58.8 % / 1.626 bits, adding the climate zone only to 50.7 % / 2.008.
    Vanilla's ``map_data/climate.txt`` names 635 of its 11,651 land
    provinces, so its climate column is mostly ``none`` and carries little —
    ours is far denser (Faerûn's CK2 ``map/climate.txt`` is 43 % severe), but
    the *table* was measured on vanilla, so vanilla's own ordering wins
    (``docs/step_map_paint.md`` §9.9).

    The second element names the level that answered, for the run report.
    """
    b = str(band)
    chain: list[tuple[str, tuple[str, str, str]]] = [
        ("terrain+climate+band", (terrain, climate, b)),
        ("terrain+band", (terrain, MIX_WILDCARD, b)),
    ]
    # Bands are ordinal and species vary smoothly with latitude, so the
    # neighbouring band is a better estimate than throwing latitude away
    # entirely.  This is not cosmetic: vanilla has **no** forest-classified
    # province in its own band 0 at all (Iceland and northern Norway are
    # taiga and mountains), while Faerûn's band 0 is 79,028 tree instances of
    # mostly forest-classified land, so without this step the whole far north
    # fell back to the Europe-wide severe-winter forest marginal - 65 %
    # broadleaf where band 1 next door is 70 % pine.
    for delta in (-1, 1):
        nb = band + delta
        if 0 <= nb < N_LAT_BANDS:
            chain.append(
                ("terrain+neighbour_band", (terrain, MIX_WILDCARD, str(nb)))
            )
    chain += [
        ("terrain+climate", (terrain, climate, MIX_WILDCARD)),
        ("terrain", (terrain, MIX_WILDCARD, MIX_WILDCARD)),
    ]
    for level, key in chain:
        d = table.get(key)
        if d is not None:
            return d, level
    return None, "none"


def lat_band(
    y: np.ndarray, canvas_height: int, n_bands: int = N_LAT_BANDS
) -> np.ndarray:
    """Canvas row -> north-to-south band index (0 = northernmost).

    A *fractional* row on both maps, which is the whole `assumed` step in
    this table's provenance: vanilla's band 0 is Iceland and Scandinavia and
    its band 9 central Africa, ours is the Spine of the World down to Chult.
    """
    if canvas_height <= 0:
        return np.zeros_like(np.asarray(y), dtype=np.int32)
    idx = (np.asarray(y, dtype=np.float64) * n_bands / float(canvas_height)).astype(
        np.int32
    )
    return np.clip(idx, 0, n_bands - 1)


def cell_uniform(cx: np.ndarray, cy: np.ndarray, seed: int) -> np.ndarray:
    """A stable uniform in [0, 1) per integer cell, from ``zlib.crc32``.

    Positional and process-stable — never ``hash()``, which Python salts per
    process and which already cost this module a 1.4 M-line diff of pure yaw
    churn (``mesh_seed``).  Only the *distinct* cells are hashed, so the
    Python loop is over ~10^4 cells, not ~10^6 trees.
    """
    cx = np.asarray(cx, dtype=np.int64)
    cy = np.asarray(cy, dtype=np.int64)
    if cx.size == 0:
        return np.zeros(0, dtype=np.float64)
    packed = (cx + (1 << 31)) * (1 << 33) + (cy + (1 << 31))
    uniq, inv = np.unique(packed, return_inverse=True)
    salt = int(seed) & 0xFFFFFFFF
    vals = np.array(
        [
            zlib.crc32(int(k).to_bytes(16, "little", signed=True), salt) / 2**32
            for k in uniq.tolist()
        ],
        dtype=np.float64,
    )
    return vals[inv]


def assign_regional_meshes(
    px: np.ndarray,
    py: np.ndarray,
    terrain_key_of_point: np.ndarray,
    climate_key_of_point: np.ndarray,
    band_of_point: np.ndarray,
    table: dict[tuple[str, str, str], MixDist],
    mesh_of_terrain: dict[str, str],
    *,
    cell_px: int = 24,
    seed: int = 4242,
    coherence: float = 1.0,
) -> tuple[np.ndarray, list[str], dict[str, int]]:
    """Pick each tree's generated file from the measured conditional table.

    ``mappings/tree_meshes.csv`` stays the **eligibility gate**: a terrain key
    with an empty ``file`` column gets no trees at all, exactly as before, so
    the placed/dropped totals are unchanged and this pass only decides *which*
    mesh a tree that was already going to exist gets.  It is also the last
    fallback, for a terrain the table has no vanilla rows for.

    Coherence: species form stands, not per-pixel salt and pepper.  A share
    ``coherence`` of the trees draw their uniform from their **cell**
    (``cell_px`` square, hashed by position), so every such tree in one cell
    with the same condition lands on the same mesh; the rest draw
    independently, which is what keeps our stands as mixed as vanilla's own
    (``docs/evidence/vanilla_tree_patch_scale.csv``: vanilla is only 0.77
    single-species even in an 8 px cell).

    Returns ``(file index per point, file names, level counts)``; index -1
    means "no mesh, drop this point".
    """
    n = int(np.asarray(px).size)
    file_names: list[str] = []
    file_index: dict[str, int] = {}

    def _fid(f: str) -> int:
        if f not in file_index:
            file_index[f] = len(file_names)
            file_names.append(f)
        return file_index[f]

    out = np.full(n, -1, dtype=np.int32)
    levels: dict[str, int] = {}
    if n == 0:
        return out, file_names, levels

    conds = np.stack(
        [
            np.asarray(terrain_key_of_point, dtype=object),
            np.asarray(climate_key_of_point, dtype=object),
            np.asarray(band_of_point).astype(np.int64).astype(str),
        ],
        axis=1,
    )
    packed = np.array(["\x00".join(row) for row in conds.tolist()], dtype=object)
    uniq, inv = np.unique(packed.astype(str), return_inverse=True)

    cell = max(1, int(cell_px))
    u_cell = cell_uniform(
        np.asarray(px, dtype=np.float64) // cell,
        np.asarray(py, dtype=np.float64) // cell,
        seed,
    )
    rng = np.random.default_rng((int(seed) ^ zlib.crc32(b"tree_mix")) & 0xFFFFFFFF)
    u_point = rng.random(n)
    u_pick = rng.random(n)
    u = np.where(u_pick < float(coherence), u_cell, u_point)

    for i, key in enumerate(uniq.tolist()):
        terrain, climate, band = key.split("\x00")
        sel = inv == i
        if not mesh_of_terrain.get(terrain, ""):
            levels["gated_no_mesh_row"] = levels.get("gated_no_mesh_row", 0) + int(
                sel.sum()
            )
            continue
        dist, level = resolve_mix(table, terrain, climate, int(band))
        if dist is None:
            dist = MixDist((mesh_of_terrain[terrain],), (1.0,))
            level = "tree_meshes.csv"
        levels[level] = levels.get(level, 0) + int(sel.sum())
        ids = np.array([_fid(f) for f in dist.files], dtype=np.int32)
        pos = np.searchsorted(np.asarray(dist.cdf), u[sel], side="right")
        out[sel] = ids[np.clip(pos, 0, ids.size - 1)]
    return out, file_names, levels


def scatter_regional(
    eligible: np.ndarray,
    terrain_code: np.ndarray,
    terrain_keys: list[str],
    climate_code: np.ndarray,
    climate_keys: list[str],
    mesh_of_terrain: dict[str, str],
    table: dict[tuple[str, str, str], MixDist],
    *,
    canvas_height: int,
    target_total: int,
    seed: int = 4242,
    jitter: float = 0.9,
    cell_px: int = 24,
    coherence: float = 1.0,
    n_bands: int = N_LAT_BANDS,
) -> tuple[dict[str, np.ndarray], int, dict[str, int], dict[str, int]]:
    """``scatter`` with the regional mix deciding the mesh.

    Same points, same drops; only the grouping differs.  The fourth return
    value is the fallback-level histogram, so a run can say how much of the
    map got the full conditional and how much fell back.
    """
    py, px, fx, fy = pick_points(
        eligible, target_total=target_total, seed=seed, jitter=jitter
    )
    if py.size == 0:
        return {}, 0, {}, {}
    tkeys = np.array(terrain_keys, dtype=object)[terrain_code[py, px]]
    ckeys = np.array(climate_keys, dtype=object)[climate_code[py, px]]
    bands = lat_band(fy, canvas_height, n_bands)
    ids, file_names, levels = assign_regional_meshes(
        fx,
        fy,
        tkeys,
        ckeys,
        bands,
        table,
        mesh_of_terrain,
        cell_px=cell_px,
        seed=seed,
        coherence=coherence,
    )
    out: dict[str, np.ndarray] = {}
    for i, f in enumerate(file_names):
        sel = ids == i
        if sel.any():
            out[f] = np.stack([fx[sel], fy[sel]], axis=1)
    drop_mask = ids < 0
    dropped = int(drop_mask.sum())
    dropped_by_terrain: dict[str, int] = {}
    if dropped:
        for key, cnt in zip(*np.unique(tkeys[drop_mask].astype(str),
                                       return_counts=True)):
            dropped_by_terrain[str(key)] = int(cnt)
    return out, dropped, dropped_by_terrain, levels


def mesh_seed(file: str) -> int:
    """Per-mesh salt for the yaw RNG: ``crc32`` of the file name.

    It used to be ``hash(file)``, which Python randomises per process
    (``PYTHONHASHSEED``), so every regeneration rewrote all 711,875 tree yaws
    and the generated mod's diff was 1.4 M lines of pure churn (build 9,
    2026-09-10).  ``crc32`` is stable across processes and platforms.
    """
    return zlib.crc32(file.encode("utf-8")) & 0xFFFFFFFF


def render_generated_file(
    points: np.ndarray, canvas_height: int, mesh: MeshInfo, *, seed: int = 4242
) -> str:
    """One ``object={}`` block: vanilla's own header fields, our instances.

    Empty (``points`` has 0 rows) writes ``instances={ }``, matching
    ``locators.render_foliage_stubs``'s stub shape, so a terrain class this
    map never paints stays an honest empty override rather than a fabricated
    ``count=0`` block.
    """
    head = (
        "object={\n"
        f'\tname="{mesh.name}"\n'
        "\trender_pass=Map\n"
        f"\tclamp_to_water_level={'yes' if mesh.clamp_to_water_level else 'no'}\n"
        "\tgenerated_content=yes\n"
        f'\tlayer="{mesh.layer}"\n'
        f'\tpdxmesh="{mesh.pdxmesh}"\n'
    )
    n = 0 if points is None else points.shape[0]
    if n == 0:
        return head + "\tinstances={\n\t}\n}\n"
    rng = np.random.default_rng(seed ^ mesh_seed(mesh.file))
    theta = rng.uniform(0.0, 2.0 * np.pi, size=n)
    x = points[:, 0]
    z = float(canvas_height) - points[:, 1]
    qy = np.sin(theta / 2.0)
    qw = np.cos(theta / 2.0)
    zeros = np.zeros(n)
    ones = np.ones(n)
    arr = np.stack([x, zeros, z, zeros, qy, zeros, qw, ones, ones, ones], axis=1)
    buf = io.StringIO()
    np.savetxt(buf, arr, fmt="%.6f")
    transform = buf.getvalue().rstrip("\n")
    return head + f"\tcount={n}\n" + f'\ttransform="{transform}"\n' + "}\n"


def render_all(
    game_dir: Path | None,
    mesh_csv: Path,
    eligible: np.ndarray,
    terrain_code: np.ndarray,
    terrain_keys: list[str],
    canvas_height: int,
    *,
    target_total: int,
    seed: int = 4242,
    mix_table: dict[tuple[str, str, str], MixDist] | None = None,
    climate_code: np.ndarray | None = None,
    climate_keys: list[str] | None = None,
    cell_px: int = 24,
    coherence: float = 1.0,
) -> tuple[dict[str, str], dict[str, int], int, dict[str, int], dict[str, int]]:
    """``{mod-relative path: text}`` for every vanilla generated file.

    Every file vanilla ships gets an override — populated where the mesh
    choice sends trees to it, an **empty stub** otherwise — so nothing keeps
    vanilla's own European foliage and an unused generator stays an honest
    empty override rather than a fabricated block.

    With ``mix_table`` (plus the per-pixel climate grid) the mesh comes from
    the measured regional distribution (``mappings/tree_mix.csv``,
    ``docs/step_map_paint.md`` §9.9); without it, from the terrain key alone
    (§9.2, ``[map] trees_regional = false``).

    Returns the file map, per-file instance counts (only the populated ones),
    the number of scattered points dropped for lack of a mesh row, that drop
    broken down by CK3 terrain key, and the fallback-level histogram (empty
    on the terrain-only path).
    """
    heads = read_generated_heads(Path(game_dir)) if game_dir else {}
    mesh_of_terrain = read_mesh_table(mesh_csv)
    levels: dict[str, int] = {}
    if mix_table and climate_code is not None and climate_keys is not None:
        groups, dropped, dropped_by_terrain, levels = scatter_regional(
            eligible,
            terrain_code,
            terrain_keys,
            climate_code,
            climate_keys,
            mesh_of_terrain,
            mix_table,
            canvas_height=canvas_height,
            target_total=target_total,
            seed=seed,
            cell_px=cell_px,
            coherence=coherence,
        )
    else:
        groups, dropped, dropped_by_terrain = scatter(
            eligible,
            terrain_code,
            terrain_keys,
            mesh_of_terrain,
            target_total=target_total,
            seed=seed,
        )
    out: dict[str, str] = {}
    counts: dict[str, int] = {}
    for file, info in sorted(heads.items()):
        pts = groups.get(file)
        out[f"{GENERATED_DIR}/{file}"] = render_generated_file(
            pts, canvas_height, info, seed=seed
        )
        if pts is not None:
            counts[file] = int(pts.shape[0])
    orphan = sum(
        int(v.shape[0]) for f, v in groups.items() if f not in heads
    )
    if orphan:
        # a mix-table row naming a generator this CK3 install does not ship
        levels["no_vanilla_generator_file"] = orphan
    return out, counts, dropped, dropped_by_terrain, levels
