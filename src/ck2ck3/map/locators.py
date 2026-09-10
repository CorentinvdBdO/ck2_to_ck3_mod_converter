"""``gfx/map/map_object_data/*.txt`` — where CK3 draws things on the map.

Holding models, coats of arms, unit stacks, siege and combat markers and
activity icons are all placed by a **locator**: one `id` per province with a
position, a rotation and a scale.  There is one file per locator type and
vanilla ships seven of them for the 1066 map.

**They are the reason a custom map draws its icons in the wrong place.**  CK3
resolves a locator by province *id*, and a mod that does not override the file
inherits vanilla's coordinates for every id vanilla happens to define.  On the
Faerûn build 3179 of 3694 land provinces landed a median **3040 px** from their
own territory (`docs/evidence/map_ui_research.md` §1.3).  The engine only fills
*gaps*: `interface/gameobjectlocators.cpp` logs `map object locator "X" is
incomplete` and generates the ids it has none for, which is why the remaining
515 were right and the rest were not.

The frame, measured in `scripts/check_locator_frame.py` and tabulated in
`docs/evidence/locator_frame.md`:

* `position = { x y z }` in **provinces.png pixels**, 1:1 (this is what
  ``WORLD_EXTENTS_X = width - 1`` buys);
* **`z` is bottom-up**: ``z = height - y_top_down``.  Reading it top-down is
  wrong by ~1360 px on the vanilla map;
* `y` is height over the water plane and is ``0`` for every generated instance;
* `rotation` is a yaw-only quaternion ``{ 0 sin(t/2) 0 cos(t/2) }``;
* `scale` is ``{ 1 1 1 }``.

The fallback placement is the **province colour centroid** — not a guess: the
CK3 engine's own generated entries sit 1.6 px (median, max 2.2) from it.

On top of it the placement model has two parts (`docs/step_map_assets.md`).

**1. One anchor per province.**  The **county-capital barony** takes the CK2
author's own town: CK2 `map/positions.txt` **slot 0**, the capital/city slot
the CK2 binary itself names (it logs `Province %d has illegal capital
location` against it).  One CK2 province is exactly one CK3 *county*, so slot
0 can place the county capital's holding and nothing else; every other
barony, and every sea, lake, river and impassable province, anchors on its
centroid.  The transformed slot must land **inside that barony's own province
pixels** in the generated `provinces.png` or it is discarded for the centroid
— the validity gate.  ``[map] ck2_locator_positions = false`` turns the whole
import off.

**2. A small measured offset per locator type, around that anchor.**  A siege
marker is the army *besieging the settlement* and a unit stack the army
*standing at* it, so vanilla does not scatter the types across the province:
measured over all 11,297 of its land ids, every type sits within ~15 px of
that province's `buildings` instance (`verified`,
`scripts/measure_vanilla_locator_offsets.py` ->
`mappings/locator_offsets.csv`; `siege` median 10.0 px, `unit_stack_*` 7.1 /
7.7, `combat` 13.6, `special_building` 9.1).  The converter adds vanilla's own
median `(dx, dz)` for each type to the anchor and re-gates it; an offset that
would leave the province falls back to the bare anchor.

CK2 slot 1 is **not** used for the unit stacks: Faerûn's slot-0 -> slot-1
distance is a median 22.8 canvas px, three times vanilla's own stack offset,
so it would spread stacks much wider than vanilla does.  It is kept in the
doc as an alternative, not as the default.
"""

from __future__ import annotations

import csv
import math
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .config import Canvas

#: irrational stride for the deterministic yaw sequence (golden ratio - 1).
#: A fixed sequence keyed on the province id gives holdings varied facings that
#: are identical on every run, without depending on a PRNG implementation.
_GOLDEN = 0.6180339887498949


@dataclass(frozen=True)
class LocatorSpec:
    """One `gfx/map/map_object_data/<file>`, exactly as vanilla declares it."""

    file: str
    #: the `name=` the engine looks the locator up by; must match vanilla
    name: str
    layer: str
    clamp_to_water_level: bool
    #: `True` -> land provinces only; `False` -> every passable province
    land_only: bool
    #: whether instances get a varied yaw (vanilla `activities` does not)
    yaw: bool
    #: vanilla's `id=0` sentinel position, or `None` when the file has none
    sentinel: tuple[float, float, float] | None = None


#: Every per-province locator file CK3 1.19 ships, with vanilla's own header
#: values.  `verified` against
#: `game/gfx/map/map_object_data/*.txt`; the id sets are the ones the engine
#: itself demanded from our map (`docs/evidence/map_ui_research.md` §1.4).
#:
#: `stack_locators.txt` (`name="unit_stack"`) is deliberately absent: vanilla
#: 1.19 ships no such file, so there is nothing to override.  Elder Kings 2 and
#: Godherja carry one only as a leftover, and Godherja's is an empty stub.
LOCATOR_SPECS: tuple[LocatorSpec, ...] = (
    LocatorSpec("building_locators.txt", "buildings", "building_layer", True, True, True),
    LocatorSpec(
        "special_building_locators.txt",
        "special_building",
        "building_layer",
        True,
        True,
        True,
    ),
    LocatorSpec("siege_locators.txt", "siege", "unit_layer", False, True, True),
    LocatorSpec("activities.txt", "activities", "activities_layer", False, True, False),
    LocatorSpec(
        "player_stack_locators.txt",
        "unit_stack_player_owned",
        "unit_layer",
        True,
        False,
        True,
        sentinel=(3.0, 0.0, 517.0),
    ),
    LocatorSpec(
        "other_stack_locators.txt",
        "unit_stack_other_owner",
        "unit_layer",
        True,
        False,
        True,
        sentinel=(3.0, 0.0, 517.0),
    ),
    LocatorSpec(
        "combat_locators.txt",
        "combat",
        "unit_layer",
        True,
        False,
        True,
        sentinel=(0.0, 0.0, 509.0),
    ),
)

MAP_OBJECT_DIR = "gfx/map/map_object_data"


#: the CK2 ``positions.txt`` slot that anchors a county-capital barony.
#: 0 is the capital/city slot, the one CK2's own binary names (`verified`,
#: ``docs/map_fidelity.md`` §1.6).  No other slot is used: see
#: ``docs/step_map_assets.md`` §2 for slot 1 and slot 3, both rejected.
CK2_ANCHOR_SLOT = 0

#: read from ``mappings/locator_offsets.csv`` when the caller passes none
DEFAULT_OFFSETS_CSV = "mappings/locator_offsets.csv"


@dataclass(frozen=True)
class LocatorOffset:
    """Vanilla's own offset of one locator type from its ``buildings`` twin.

    ``dx``/``dz`` are **vanilla provinces.png pixels** with ``dz`` bottom-up
    (``dz > 0`` = north), the frame the locator files themselves use.
    Measured by ``scripts/measure_vanilla_locator_offsets.py``.
    """

    name: str
    dx: float
    dz: float
    median_dist_px: float = 0.0
    p95_dist_px: float = 0.0
    instances: int = 0


def read_locator_offsets(path: str | Path) -> dict[str, LocatorOffset]:
    """``mappings/locator_offsets.csv`` -> ``{locator name: LocatorOffset}``.

    The file opens with a ``#`` provenance block; every reader of a
    ``mappings/*.csv`` must skip comment lines (``CLAUDE.md`` invariant).
    Returns ``{}`` when the file is absent, which means "no offsets": every
    type lands on the anchor, the behaviour before this table existed.
    """
    p = Path(path)
    if not p.is_file():
        return {}
    rows = [ln for ln in p.read_text(encoding="utf-8-sig").splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")]
    if not rows:
        return {}
    out: dict[str, LocatorOffset] = {}
    for row in csv.DictReader(rows):
        name = (row.get("locator") or "").strip()
        if not name:
            continue
        out[name] = LocatorOffset(
            name=name,
            dx=float(row["dx_px"]),
            dz=float(row["dz_px"]),
            median_dist_px=float(row.get("median_dist_px") or 0.0),
            p95_dist_px=float(row.get("p95_dist_px") or 0.0),
            instances=int(row.get("instances") or 0),
        )
    return out


@dataclass
class AnchorStats:
    """Outcome of :func:`ck2_capital_anchors`, for the run report."""

    slot: int = CK2_ANCHOR_SLOT
    #: county-capital baronies that had a CK2 slot to try at all
    candidates: int = 0
    #: slots that landed inside their own barony and became the anchor
    accepted: int = 0
    #: transformed outside the canvas (a crop threw the source pixel away)
    off_canvas: int = 0
    #: on the canvas but in some other province: the validity gate rejected it
    outside_province: int = 0
    #: |anchor - centroid|, canvas pixels
    moves_px: list[float] = field(default_factory=list)

    @property
    def accept_rate(self) -> float:
        return self.accepted / self.candidates if self.candidates else 0.0

    @property
    def median_move_px(self) -> float:
        return float(np.median(self.moves_px)) if self.moves_px else 0.0

    def as_dict(self) -> dict:
        return {
            "slot": self.slot,
            "candidates": self.candidates,
            "accepted": self.accepted,
            "off_canvas": self.off_canvas,
            "outside_province": self.outside_province,
            "accept_rate": round(self.accept_rate, 4),
            "median_move_px": round(self.median_move_px, 2),
        }


def ck2_capital_anchors(
    *,
    positions: Mapping[int, Sequence[tuple[float, float]]],
    capital_ids: Mapping[int, int],
    canvas: Canvas,
    source_height: int,
    raster: np.ndarray,
    centroids: Mapping[int, tuple[float, float]],
    slot: int = CK2_ANCHOR_SLOT,
) -> tuple[dict[int, tuple[float, float]], AnchorStats]:
    """CK2 ``positions.txt`` slot 0 -> ``{CK3 province id: (x, y)}`` anchors.

    ``positions`` is :func:`ck2ck3.map.ck2read.read_positions` output: CK2
    province id -> seven ``(x, y)`` pairs with y measured from the **bottom**
    of the CK2 bitmap.  ``capital_ids`` maps a CK2 province id to the CK3
    province id of its **county-capital barony** — the only barony a CK2
    per-province coordinate can honestly place.

    The transform is the one the barony seeds already use
    (``ck2ck3.map.baronies._seed_one``): flip y to top-down, then
    :meth:`Canvas.to_target`.  It is not re-derived here.

    The **validity gate** is mandatory: a transformed pixel becomes the anchor
    only if ``raster`` (the canvas-shaped CK3 province-id array) holds that
    barony's own id there.  Anything else is left out, which means the caller
    falls back to the centroid.
    """
    height, width = raster.shape[:2]
    st = AnchorStats(slot=slot)
    out: dict[int, tuple[float, float]] = {}
    for ck2_id in sorted(capital_ids):
        pid = capital_ids[ck2_id]
        slots = positions.get(ck2_id)
        if not slots or len(slots) <= slot:
            continue
        st.candidates += 1
        cx, cy = slots[slot]
        # positions.txt y is bottom-origin in CK2 bitmap pixels
        # (`verified`, docs/map_scale.md §2b)
        x, y = canvas.to_target(cx, source_height - cy)
        if not (0 <= x < width and 0 <= y < height):
            st.off_canvas += 1
            continue
        if int(raster[y, x]) != pid:
            st.outside_province += 1
            continue
        st.accepted += 1
        out[pid] = (float(x), float(y))
        c = centroids.get(pid)
        if c is not None:
            st.moves_px.append(float(math.hypot(x - c[0], y - c[1])))
    return out, st


def place_with_offsets(
    *,
    centroids: Mapping[int, tuple[float, float]],
    anchors: Mapping[int, tuple[float, float]],
    offsets: Mapping[str, LocatorOffset],
    raster: np.ndarray,
    land_ids: Iterable[int],
    passable_ids: Iterable[int],
    scale: float = 1.0,
    mode: str = "median_vector",
) -> tuple[dict[str, dict[int, tuple[float, float]]], dict[str, dict]]:
    """Anchor + vanilla's per-type offset -> per-locator position overrides.

    For every locator type and every id it covers:

    1. the base point is ``anchors[pid]`` when the CK2 slot gave one, else
       ``centroids[pid]``;
    2. the type's vanilla offset is added — ``dz`` is bottom-up, so it becomes
       ``y - dz * scale`` in top-down canvas pixels;
    3. the offset point is **re-gated** against ``raster``; if it left the
       province the bare anchor is used instead.

    ``scale`` converts vanilla pixels to canvas pixels.  It is 1.0 because
    this canvas is planned at vanilla's own km per pixel by construction
    (``docs/map_scale.md``); it is a parameter so a differently scaled map can
    say so.

    ``mode`` picks what "vanilla's offset" means, because the two measurements
    disagree for the rotationally symmetric types
    (``docs/step_map_assets.md`` §2.2):

    * ``"median_vector"`` (default) — the median ``(dx, dz)``.  Faithful to
      vanilla's *direction* bias, but only ~a third of its *separation* for
      ``siege``/``special_building``/``activities``, whose directions cancel.
    * ``"median_radius"`` — the same direction stretched to vanilla's median
      *distance* from the settlement, which is the much better determined of
      the two numbers for those types.  A type whose table row has no distance
      falls back to its median vector.

    Returns ``({locator name: {id: (x, y)}}, {locator name: stats})``.  Only
    ids whose final position differs from the centroid are returned: they are
    a *patch* over the centroid map, so nothing can be dropped from a file.
    """
    height, width = raster.shape[:2]
    land = set(land_ids)
    passable = set(passable_ids)
    out: dict[str, dict[int, tuple[float, float]]] = {}
    stats: dict[str, dict] = {}
    for spec in LOCATOR_SPECS:
        ids = land if spec.land_only else passable
        off = offsets.get(spec.name)
        dx, dz = (off.dx, off.dz) if off else (0.0, 0.0)
        if mode == "median_radius" and off and off.median_dist_px > 0:
            length = math.hypot(dx, dz)
            if length > 0:
                dx, dz = (dx / length * off.median_dist_px,
                          dz / length * off.median_dist_px)
        dx *= scale
        dy = -dz * scale  # dz is bottom-up
        picked: dict[int, tuple[float, float]] = {}
        n_anchor = n_offset = n_offset_rejected = 0
        moves: list[float] = []
        for pid in sorted(ids):
            base = anchors.get(pid)
            if base is None:
                base = centroids.get(pid)
                if base is None:
                    continue
            else:
                n_anchor += 1
            x, y = base[0] + dx, base[1] + dy
            xi, yi = int(round(x)), int(round(y))
            if (dx or dy) and 0 <= xi < width and 0 <= yi < height and int(
                raster[yi, xi]
            ) == pid:
                n_offset += 1
            else:
                if dx or dy:
                    n_offset_rejected += 1
                x, y = base
            c = centroids.get(pid)
            if c is None or (x, y) != (c[0], c[1]):
                picked[pid] = (float(x), float(y))
                if c is not None:
                    moves.append(float(math.hypot(x - c[0], y - c[1])))
        out[spec.name] = picked
        stats[spec.name] = {
            "ids": len(ids),
            "ck2_anchored": n_anchor,
            "offset_applied": n_offset,
            "offset_rejected": n_offset_rejected,
            "moved_from_centroid": len(picked),
            "median_move_px": round(float(np.median(moves)), 2) if moves else 0.0,
        }
    return out, stats


# --------------------------------------------------------------------------- #
# the frame conversion — the one thing that is easy to get wrong
# --------------------------------------------------------------------------- #
def world_position(
    x_px: float, y_px: float, canvas_height: int, *, height: float = 0.0
) -> tuple[float, float, float]:
    """Bitmap pixel ``(x, y)`` (y top-down) -> locator ``{ x y z }``.

    ``z`` is bottom-up, so ``z = canvas_height - y``.  A province whose
    centroid is on the **top** row of the bitmap gets ``z ~ canvas_height``,
    i.e. the north edge of the world.
    """
    return (float(x_px), float(height), float(canvas_height) - float(y_px))


def pixel_position(
    position: tuple[float, float, float], canvas_height: int
) -> tuple[float, float]:
    """Inverse of :func:`world_position`: locator ``{ x y z }`` -> ``(x, y)``."""
    return (float(position[0]), float(canvas_height) - float(position[2]))


def yaw_quaternion(theta: float) -> tuple[float, float, float, float]:
    """Rotation about the world Y axis as CK3 writes it: ``{ qx qy qz qw }``."""
    return (0.0, math.sin(theta / 2.0), 0.0, math.cos(theta / 2.0))


def yaw_for(province_id: int) -> float:
    """A stable, well-spread facing for a province, in radians.

    Vanilla's holdings do not all face the same way and the engine's own
    generated locators give each id a different yaw.  A low-discrepancy
    sequence keyed on the id reproduces that without a PRNG, so two runs of the
    converter produce byte-identical files.
    """
    return 2.0 * math.pi * ((province_id * _GOLDEN) % 1.0)


# --------------------------------------------------------------------------- #
# rendering
# --------------------------------------------------------------------------- #
def _fmt(value: float) -> str:
    """CK3 writes six decimals; ``-0.0`` normalised away so runs are stable."""
    return f"{value + 0.0:.6f}"


def _instance(
    pid: int, position: tuple[float, float, float], rotation: tuple[float, ...]
) -> str:
    return (
        "\t\t{\n"
        f"\t\t\tid={pid}\n"
        f"\t\t\tposition={{ {' '.join(_fmt(v) for v in position)} }}\n"
        f"\t\t\trotation={{ {' '.join(_fmt(v) for v in rotation)} }}\n"
        "\t\t\tscale={ 1.000000 1.000000 1.000000 }\n"
        "\t\t}\n"
    )


def render_locator_file(
    spec: LocatorSpec,
    positions: Mapping[int, tuple[float, float]],
    canvas_height: int,
    *,
    ids: Iterable[int] | None = None,
    overrides: Mapping[int, tuple[float, float]] | None = None,
) -> str:
    """One ``game_object_locator={}`` block.

    ``positions`` maps province id -> ``(x, y)`` bitmap pixels, y top-down;
    in practice the province colour centroids.  ``ids`` restricts and orders
    the instances; it defaults to every id in ``positions``, ascending.

    ``overrides`` wins over ``positions`` for the ids it names — the anchor
    plus per-type offset from :func:`place_with_offsets`.  An id it does not
    name keeps its centroid, so **every** id still gets an instance: leaving
    one out would silently hand it vanilla's European coordinate.
    """
    order = sorted(positions) if ids is None else sorted(ids)
    over = overrides or {}
    out = [
        "game_object_locator={\n",
        f'\tname="{spec.name}"\n',
        "\trender_pass=Map\n",
        f"\tclamp_to_water_level={'yes' if spec.clamp_to_water_level else 'no'}\n",
        "\tgenerated_content=no\n",
        f'\tlayer="{spec.layer}"\n',
        "\tinstances={\n",
    ]
    if spec.sentinel is not None:
        out.append(_instance(0, spec.sentinel, (0.0, 0.0, 0.0, 1.0)))
    for pid in order:
        xy = over[pid] if pid in over else positions.get(pid)
        if xy is None:
            continue
        rotation = yaw_quaternion(yaw_for(pid)) if spec.yaw else (0.0, 0.0, 0.0, 1.0)
        out.append(_instance(pid, world_position(xy[0], xy[1], canvas_height), rotation))
    out += ["\t}\n", "}\n"]
    return "".join(out)


#: vanilla's foliage lives here, one file per mesh, `generated_content=yes`
FOLIAGE_DIR = f"{MAP_OBJECT_DIR}/generated"

_OBJECT_HEAD = re.compile(
    r"object=\{(.*?)(?:\n\tcount=|\n\ttransform=|\n\tinstances=)", re.S
)


def render_foliage_stubs(game_dir: Path | None) -> dict[str, str]:
    """Empty overrides for every vanilla ``map_object_data/generated/*.txt``.

    Those files place trees, reeds and rocks by absolute coordinate — ~52 MB of
    them, all inside vanilla's 9216x4608 sheet — and a mod that does not
    override a file by name gets it loaded over its own map.  On a different
    canvas that is forest standing in the sea and props leaning on the map
    table.  Elder Kings 2 and Godherja both ship empty ``instances={ }`` stubs
    for the generators they do not want (`gfx/map/map_object_data/generated/
    tree_leaf_low_generator_1.txt` in both); this writes one for every file
    vanilla ships, keeping each block's ``name``/``layer``/``pdxmesh`` so the
    override matches what it replaces.

    Returns ``{}`` when the CK3 install is unavailable.
    """
    if game_dir is None:
        return {}
    src_dir = Path(game_dir) / FOLIAGE_DIR
    if not src_dir.is_dir():
        return {}
    out: dict[str, str] = {}
    for src in sorted(src_dir.glob("*.txt")):
        heads = _OBJECT_HEAD.findall(src.read_text(encoding="utf-8-sig", errors="replace"))
        if not heads:
            continue
        out[f"{FOLIAGE_DIR}/{src.name}"] = (
            "# GENERATED by ck2ck3 (lane map-ui): vanilla's foliage for this mesh\n"
            "# is placed at coordinates inside its own 9216x4608 sheet and would\n"
            "# otherwise load over our canvas. Emptied, the Elder Kings 2 /\n"
            "# Godherja way. See docs/evidence/map_ui_research.md.\n"
        ) + "".join(
            "object={" + head.rstrip() + "\n\tinstances={\n\t}\n}\n" for head in heads
        )
    return out


def render_all(
    positions: Mapping[int, tuple[float, float]],
    canvas_height: int,
    *,
    land_ids: Iterable[int],
    passable_ids: Iterable[int],
    overrides: Mapping[str, Mapping[int, tuple[float, float]]] | None = None,
) -> dict[str, str]:
    """``{mod-relative path: file text}`` for every locator file vanilla ships.

    ``land_ids`` are the provinces that can hold a building — everything the
    engine asked for in ``buildings``/``special_building``/``siege``/
    ``activities``.  ``passable_ids`` adds sea, lake and river (but not
    impassable), which is what ``combat``/``unit_stack_*`` want.

    ``overrides`` is keyed by locator ``name=`` (``{"buildings": {id: (x, y)}}``)
    — the output of :func:`place_with_offsets`.  All seven files are always
    written, complete, whatever it contains.
    """
    land = set(land_ids)
    passable = set(passable_ids)
    over = overrides or {}
    return {
        f"{MAP_OBJECT_DIR}/{spec.file}": render_locator_file(
            spec,
            positions,
            canvas_height,
            ids=(land if spec.land_only else passable),
            overrides=over.get(spec.name),
        )
        for spec in LOCATOR_SPECS
    }
