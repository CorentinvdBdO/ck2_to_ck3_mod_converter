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

The placement rule is the **province colour centroid** — not a guess: the CK3
engine's own generated entries sit 1.6 px (median, max 2.2) from it.  CK2
`positions.txt` is not used: it is per CK2 province and one CK2 county becomes
many CK3 baronies here, so it cannot place a holding (CLAUDE.md invariant).
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

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
) -> str:
    """One ``game_object_locator={}`` block.

    ``positions`` maps province id -> ``(x, y)`` bitmap pixels, y top-down.
    ``ids`` restricts and orders the instances; it defaults to every id in
    ``positions``, ascending.
    """
    order = sorted(positions) if ids is None else sorted(ids)
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
        xy = positions.get(pid)
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
) -> dict[str, str]:
    """``{mod-relative path: file text}`` for every locator file vanilla ships.

    ``land_ids`` are the provinces that can hold a building — everything the
    engine asked for in ``buildings``/``special_building``/``siege``/
    ``activities``.  ``passable_ids`` adds sea, lake and river (but not
    impassable), which is what ``combat``/``unit_stack_*`` want.
    """
    land = set(land_ids)
    passable = set(passable_ids)
    return {
        f"{MAP_OBJECT_DIR}/{spec.file}": render_locator_file(
            spec,
            positions,
            canvas_height,
            ids=(land if spec.land_only else passable),
        )
        for spec in LOCATOR_SPECS
    }
