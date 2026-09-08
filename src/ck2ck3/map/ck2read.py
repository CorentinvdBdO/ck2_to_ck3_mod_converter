"""Readers for the CK2 ``map/`` directory.

Every reader returns plain dataclasses / dicts so the writers stay testable
without touching a 40 MB bitmap.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

from .blocks import Block, parse_file

CK2_ENCODING = "cp1252"


# --------------------------------------------------------------------------- #
# definition.csv
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Ck2Province:
    id: int
    rgb: tuple[int, int, int]
    name: str


def read_definitions(path: str | Path) -> list[Ck2Province]:
    """Parse CK2 ``map/definition.csv``.

    Format is ``province;red;green;blue;name;x``.  The header row is skipped by
    checking whether column 0 parses as an int, so a mod with a different
    header text still works.  Comment rows (``#...``) and short rows are
    skipped.
    """
    out: list[Ck2Province] = []
    seen: set[int] = set()
    with Path(path).open("r", encoding=CK2_ENCODING, errors="replace", newline="") as fh:
        for row in csv.reader(fh, delimiter=";"):
            if len(row) < 5 or not row[0].strip().isdigit():
                continue
            pid = int(row[0])
            if pid in seen:  # last definition wins in CK2; keep the first, warn later
                continue
            seen.add(pid)
            out.append(
                Ck2Province(
                    id=pid,
                    rgb=(int(row[1]), int(row[2]), int(row[3])),
                    name=row[4].strip(),
                )
            )
    return out


# --------------------------------------------------------------------------- #
# default.map
# --------------------------------------------------------------------------- #
@dataclass
class Ck2DefaultMap:
    max_provinces: int = 0
    #: (first, last) inclusive province-id ranges, in file order
    sea_zones: list[tuple[int, int]] = field(default_factory=list)
    #: sea-zone comment text, parallel to :attr:`sea_zones`
    sea_zone_names: list[str] = field(default_factory=list)
    #: ocean region name -> 1-based indices into :attr:`sea_zones`
    ocean_regions: dict[str, list[int]] = field(default_factory=dict)
    major_rivers: list[int] = field(default_factory=list)
    externals: list[int] = field(default_factory=list)

    def sea_ids(self) -> set[int]:
        return {i for a, b in self.sea_zones for i in range(a, b + 1)}

    def lake_ids(self, lake_region_names: tuple[str, ...] = ("Lakes",)) -> set[int]:
        """Province ids of every sea zone in an ocean region named like a lake."""
        want = {n.lower() for n in lake_region_names}
        out: set[int] = set()
        for region, idxs in self.ocean_regions.items():
            if region.lower() not in want:
                continue
            for one_based in idxs:
                if 1 <= one_based <= len(self.sea_zones):
                    a, b = self.sea_zones[one_based - 1]
                    out.update(range(a, b + 1))
        return out


def read_default_map(path: str | Path) -> Ck2DefaultMap:
    root = parse_file(path)
    dm = Ck2DefaultMap(max_provinces=root.int_("max_provinces", 0) or 0)

    for blk in root.all("sea_zones"):
        if not isinstance(blk, Block):
            continue
        nums = [int(t) for t in blk.tokens if t.lstrip("+-").isdigit()]
        if len(nums) >= 2:
            dm.sea_zones.append((nums[0], nums[1]))
            dm.sea_zone_names.append(blk.comment or "")

    for blk in root.all("ocean_region"):
        if not isinstance(blk, Block):
            continue
        name = (blk.comment or f"region_{len(dm.ocean_regions)}").strip()
        dm.ocean_regions[name] = blk.ints("sea_zones")

    for blk in root.all("major_rivers"):
        if isinstance(blk, Block):
            dm.major_rivers.extend(int(t) for t in blk.tokens if t.lstrip("+-").isdigit())
    for blk in root.all("externals"):
        if isinstance(blk, Block):
            dm.externals.extend(int(t) for t in blk.tokens if t.lstrip("+-").isdigit())
    return dm


# --------------------------------------------------------------------------- #
# climate.txt / island_region.txt / geographical_region.txt
# --------------------------------------------------------------------------- #
def read_climate(path: str | Path) -> dict[str, list[int]]:
    """``{'severe_winter': [ids], 'normal_winter': [...], 'mild_winter': [...]}``."""
    root = parse_file(path)
    return {
        key: root.ints(key)
        for key in ("severe_winter", "normal_winter", "mild_winter")
        if root.all(key)
    }


def read_island_regions(path: str | Path) -> dict[str, list[int]]:
    """``region_name -> province ids``."""
    root = parse_file(path)
    out: dict[str, list[int]] = {}
    for name, vals in root.children.items():
        if not name:
            continue
        for v in vals:
            if isinstance(v, Block):
                out.setdefault(name, []).extend(v.ints("provinces"))
    return out


@dataclass
class Ck2GeoRegion:
    name: str
    duchies: list[str] = field(default_factory=list)
    regions: list[str] = field(default_factory=list)
    provinces: list[int] = field(default_factory=list)


def read_geographical_regions(path: str | Path) -> list[Ck2GeoRegion]:
    root = parse_file(path)
    out: list[Ck2GeoRegion] = []
    for name, vals in root.children.items():
        if not name:
            continue
        for v in vals:
            if not isinstance(v, Block):
                continue
            reg = Ck2GeoRegion(name=name)
            for sub in v.all("duchies"):
                if isinstance(sub, Block):
                    reg.duchies.extend(sub.tokens)
            for sub in v.all("regions"):
                if isinstance(sub, Block):
                    reg.regions.extend(sub.tokens)
            reg.provinces.extend(v.ints("provinces"))
            out.append(reg)
    return out


# --------------------------------------------------------------------------- #
# the CK3 side: which region names vanilla declares
# --------------------------------------------------------------------------- #
def read_ck3_region_names(folder: str | Path) -> dict[str, bool]:
    """CK3 ``map_data/geographical_regions`` region name → ``generate_modifiers``.

    ``map_data/geographical_regions`` is a ``replace_path`` for a converted
    mod, so **none** of vanilla's 589 regions load, and every vanilla script,
    GUI and achievement that names one gets a null back.  One of those killed
    the game right after the main menu appeared (`verified` 2026-09-08:
    ``databases.h:36: Key dlc_fp1_region_core_mainland_scandinavia not found at
    Database: map_data/geographical_regions``, then
    ``EXCEPTION_ACCESS_VIOLATION``), and eight more produce the
    ``<region>_development_growth_factor`` modifiers vanilla's traits and
    innovations reference — hence the ``generate_modifiers`` flag is carried
    over too.

    Vanilla files are UTF-8 (with BOM) rather than cp1252, so this reader
    cannot go through :func:`parse_file`'s CK2 encoding.
    """
    out: dict[str, bool] = {}
    directory = Path(folder)
    if not directory.is_dir():
        return out
    for path in sorted(directory.glob("*.txt")):
        root = parse_file(path, encoding="utf-8-sig")
        for name, values in root.children.items():
            if not name:
                continue
            for block in values:
                if isinstance(block, Block):
                    out[name] = out.get(name, False) or bool(
                        block.first("generate_modifiers")
                    )
    return out


# --------------------------------------------------------------------------- #
# common/cultures  (only the graphical culture; the `cultures` step owns the rest)
# --------------------------------------------------------------------------- #
def read_graphical_culture_of_culture(folder: str | Path) -> dict[str, str]:
    """CK2 culture id → its first ``graphical_cultures`` value.

    `verified` (CLAUDE.md invariant): a CK2 culture *group* carries
    ``graphical_cultures``; a culture may override it.  The first entry of the
    list is the one CK2 draws with, so that is the one taken.  Cultures with no
    value anywhere are absent from the mapping and fall through to the caller's
    default.

    Only the graphical culture is read here.  The full culture-group model
    belongs to the ``cultures`` step; the ``map`` step needs this one field to
    put every land province in a CK3 ``graphical_*`` geographical region.
    """
    out: dict[str, str] = {}
    directory = Path(folder)
    if not directory.is_dir():
        return out
    for path in sorted(directory.glob("*.txt")):
        if path.stat().st_size == 0:
            continue
        root = parse_file(path)
        for _group, values in root.children.items():
            for group_block in values:
                if not isinstance(group_block, Block):
                    continue
                group_gfx = _first_graphical_culture(group_block)
                for culture, culture_values in group_block.children.items():
                    for block in culture_values:
                        if not isinstance(block, Block):
                            continue
                        if not any(m in block.children for m in _CULTURE_MARKERS):
                            continue  # `graphical_cultures`, `alternate_start`, …
                        gfx = _first_graphical_culture(block) or group_gfx
                        if gfx:
                            out.setdefault(culture, gfx)
    return out


#: What tells a culture block apart from any other child of a culture group.
#: Same test the `cultures` step uses (`verified`: 419/419 Faerûn cultures
#: define both, and no group-level key does).
_CULTURE_MARKERS = ("male_names", "female_names")


def _first_graphical_culture(block: Block) -> str | None:
    for value in block.all("graphical_cultures"):
        if isinstance(value, Block) and value.tokens:
            return str(value.tokens[0])
    return None


# --------------------------------------------------------------------------- #
# adjacencies.csv
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Ck2Adjacency:
    from_id: int
    to_id: int
    type: str
    through: int
    comment: str


def read_adjacencies(path: str | Path) -> list[Ck2Adjacency]:
    """CK2 ``From;To;Type;Through;-1;-1;-1;-1;Comment``."""
    out: list[Ck2Adjacency] = []
    with Path(path).open("r", encoding=CK2_ENCODING, errors="replace", newline="") as fh:
        for row in csv.reader(fh, delimiter=";"):
            if len(row) < 4 or not row[0].strip().lstrip("-").isdigit():
                continue
            out.append(
                Ck2Adjacency(
                    from_id=int(row[0]),
                    to_id=int(row[1]),
                    type=row[2].strip(),
                    through=int(row[3]) if row[3].strip().lstrip("-").isdigit() else -1,
                    comment=(row[8].strip() if len(row) > 8 else ""),
                )
            )
    return out


# --------------------------------------------------------------------------- #
# terrain.txt
# --------------------------------------------------------------------------- #
def read_terrain_texture_map(path: str | Path) -> dict[int, str]:
    """``terrain.bmp palette index -> CK2 terrain category``.

    Reads the ``text_N = { type = <cat> color = { N } ... }`` lines at the
    bottom of CK2 ``map/terrain.txt``.  The palette index is taken from
    ``color = { N }`` (CK2 terrain.bmp is an 8-bit indexed bitmap and this is
    the index, not an RGB triple).
    """
    root = parse_file(path)
    out: dict[int, str] = {}
    for name, vals in root.children.items():
        if not name.startswith("text_"):
            continue
        for v in vals:
            if not isinstance(v, Block):
                continue
            cat = v.str_("type")
            colours = v.ints("color")
            if cat and colours:
                out[colours[0]] = cat
    return out


def read_terrain_categories(path: str | Path) -> dict[str, bool]:
    """``CK2 terrain category -> is_water``."""
    root = parse_file(path)
    out: dict[str, bool] = {}
    for cats in root.all("categories"):
        if not isinstance(cats, Block):
            continue
        for name, vals in cats.children.items():
            if not name:
                continue
            for v in vals:
                if isinstance(v, Block):
                    out[name] = v.str_("is_water", "no") == "yes"
    return out


# --------------------------------------------------------------------------- #
# positions.txt
# --------------------------------------------------------------------------- #
#: CK2 position slot order (``position={x0 y0 x1 y1 ...}``), 7 pairs.
CK2_POSITION_SLOTS = ("city", "unit", "text", "port", "combat", "town", "special")


def read_positions(path: str | Path) -> dict[int, list[tuple[float, float]]]:
    """``province id -> [(x, y)] * 7`` from CK2 ``map/positions.txt``.

    y is in CK2 bitmap space measured from the **bottom** of the map
    (`verified`, see docs/evidence/atlas_registration.md); convert with
    ``y_top = height - y``.
    """
    root = parse_file(path)
    out: dict[int, list[tuple[float, float]]] = {}
    for key, vals in root.children.items():
        if not key.lstrip("+-").isdigit():
            continue
        pid = int(key)
        for v in vals:
            if not isinstance(v, Block):
                continue
            pos = v.first("position")
            if not isinstance(pos, Block):
                continue
            nums = [float(t) for t in pos.tokens if _is_number(t)]
            out[pid] = [(nums[i], nums[i + 1]) for i in range(0, len(nums) - 1, 2)]
    return out


def _is_number(tok: str) -> bool:
    try:
        float(tok)
    except ValueError:
        return False
    return True
