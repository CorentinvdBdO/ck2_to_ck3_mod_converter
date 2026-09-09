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


def scatter(
    eligible: np.ndarray,
    terrain_code: np.ndarray,
    terrain_keys: list[str],
    mesh_of_terrain: dict[str, str],
    *,
    target_total: int,
    seed: int = 4242,
    jitter: float = 0.9,
) -> tuple[dict[str, np.ndarray], int]:
    """Deterministic point scatter over ``eligible`` pixels.

    Picks up to ``target_total`` points uniformly at random from the eligible
    (forest & land & passable) pixels via a partition on a random key array —
    O(n), deterministic given ``seed`` — then jitters each within its own
    pixel cell so the result does not read as a grid, and groups by the
    generated file the pixel's CK3 terrain key maps to.

    Returns ``(file -> (n, 2) float array of (x, y) canvas pixels, dropped,
    dropped_by_terrain)`` where ``dropped`` counts points whose terrain key
    has no row (or an empty row) in ``mesh_of_terrain`` — logged, never
    silently invented, same contract as ``terrain_paint``'s
    ``missing_material`` — and ``dropped_by_terrain`` breaks that down by CK3
    terrain key, for the run report.
    """
    ys, xs = np.nonzero(eligible)
    n_eligible = ys.size
    if n_eligible == 0 or target_total <= 0:
        return {}, 0, {}
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
    rng = np.random.default_rng(seed ^ (hash(mesh.file) & 0xFFFFFFFF))
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
) -> tuple[dict[str, str], dict[str, int], int, dict[str, int]]:
    """``{mod-relative path: text}`` for every vanilla generated file.

    Every file vanilla ships gets an override — populated where
    ``mappings/tree_meshes.csv`` names it, an empty stub otherwise — so
    nothing keeps vanilla's own European foliage. Returns the file map,
    per-file instance counts (only the populated ones), the number of
    scattered points dropped for lack of a mesh row, and that drop broken
    down by CK3 terrain key (for the run report).
    """
    heads = read_generated_heads(Path(game_dir)) if game_dir else {}
    mesh_of_terrain = read_mesh_table(mesh_csv)
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
    return out, counts, dropped, dropped_by_terrain
