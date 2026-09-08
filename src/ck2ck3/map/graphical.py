"""The seven CK3 ``graphical_*`` geographical regions, and who goes in them.

Why the converter has to emit them (`verified` 2026-09-08, headless CK3
1.19.0.6, `docs/evidence/game_load_2026-09-08.md`):

* ``map_data/geographical_regions`` is a ``replace_path`` for this mod, so
  vanilla's ``geographical_region.txt`` — the only file that defines
  ``graphical_western``, ``graphical_mena``, ``graphical_india``,
  ``graphical_mediterranean``, ``graphical_steppe``, ``graphical_siberia`` and
  ``graphical_east_asia`` — does not load.  Every vanilla building asset names
  all seven in its ``graphical_regions = { … }`` filter
  (``common/buildings/00_castle_buildings.txt:99``), which produced **2611**
  ``deferred_database_lookup: '<name>' in field 'geographical region' … could
  not be found in the database`` errors in one boot.
* A land province in **no** ``graphical = yes`` region is a second error:
  ``geographical_region.cpp: Province N b_x has no visual geographical region
  assigned``, 3904 of them.

Elder Kings 2 solves it the same way
(``workshop/content/1158310/2887120253/map_data/geographical_regions/geographical_region.txt:1224``):
it redefines all seven under its own map, some with an empty ``regions = { }``.

How a province is assigned here: CK2 province history says the province's
culture, the CK2 culture (or its group) says its ``graphical_cultures``, and
``overrides/gfx_of_culture_group.csv`` — the human table the ``cultures`` step
already reads — says which CK3 ``building_gfx`` that CK2 graphical culture maps
onto.  :data:`REGION_OF_BUILDING_GFX` then names the vanilla region that ships
that building set.  Anything with no row anywhere falls through to
:data:`DEFAULT_GRAPHICAL_REGION`, which is what the ``cultures`` step's gfx
defaults already assume.
"""

from __future__ import annotations

from collections.abc import Mapping

from .holdings import ProvinceHistory
from .idmap import IdMap

#: The seven regions vanilla declares, with vanilla's own colours
#: (``game/map_data/geographical_regions/geographical_region.txt:2115-2172``).
#: Order and colours are copied so a save or a debug map-mode looks the same.
GRAPHICAL_REGIONS: tuple[tuple[str, tuple[int, int, int]], ...] = (
    ("graphical_western", (255, 0, 0)),
    ("graphical_mena", (255, 255, 0)),
    ("graphical_india", (0, 255, 0)),
    ("graphical_mediterranean", (0, 0, 255)),
    ("graphical_steppe", (0, 255, 255)),
    ("graphical_siberia", (0, 255, 155)),
    ("graphical_east_asia", (155, 255, 155)),
)

#: Where every land province goes when nothing else applies. `graphical_western`
#: is the region vanilla puts western Europe in, and `western_building_gfx` is
#: the `cultures` step's default building set, so the two agree.
DEFAULT_GRAPHICAL_REGION = "graphical_western"

#: CK3 ``building_gfx`` → the vanilla ``graphical_*`` region that covers the
#: part of the vanilla map shipping that building set.  Each row is read off
#: vanilla's own region lists (same file, `regions = { … }`):
#: `world_europe_*` → western, `world_europe_west_iberia`/`world_europe_south`/
#: `world_asia_minor` → mediterranean, `world_africa`/`world_middle_east` →
#: mena, `world_india`/`world_tibet`/southeast Asia → india,
#: `world_steppe_*` → steppe, `world_asia_china`/`world_asia_japan` → east asia.
REGION_OF_BUILDING_GFX: dict[str, str] = {
    "western_building_gfx": "graphical_western",
    "norse_building_gfx": "graphical_western",
    "east_slavic_building_gfx": "graphical_western",
    "mediterranean_building_gfx": "graphical_mediterranean",
    "iberian_building_gfx": "graphical_mediterranean",
    "byzantine_building_gfx": "graphical_mediterranean",
    "mena_building_gfx": "graphical_mena",
    "african_building_gfx": "graphical_mena",
    "berber_group_building_gfx": "graphical_mena",
    "iranian_building_gfx": "graphical_mena",
    "indian_building_gfx": "graphical_india",
    "tibetan_building_gfx": "graphical_india",
    "southeast_asian_building_gfx": "graphical_india",
    "steppe_building_gfx": "graphical_steppe",
    "chinese_building_gfx": "graphical_east_asia",
    "japanese_building_gfx": "graphical_east_asia",
}


def region_of_ck2_gfx(building_gfx_of_ck2_gfx: Mapping[str, str]) -> dict[str, str]:
    """``{ck2 graphical culture: graphical region}`` from the overrides table.

    ``building_gfx_of_ck2_gfx`` is the ``ck2_graphical_culture`` →
    ``building_gfx`` column pair of ``overrides/gfx_of_culture_group.csv``.  A
    CK2 graphical culture whose building set is not in
    :data:`REGION_OF_BUILDING_GFX` is left out, so the caller's default applies.
    """
    out: dict[str, str] = {}
    for ck2_gfx, building_gfx in building_gfx_of_ck2_gfx.items():
        region = REGION_OF_BUILDING_GFX.get(str(building_gfx).strip())
        if region:
            out[str(ck2_gfx).strip()] = region
    return out


def assign(
    *,
    history: Mapping[int, ProvinceHistory],
    idmap: IdMap,
    land_ck3: set[int] | frozenset[int],
    graphical_culture_of_culture: Mapping[str, str],
    region_of_gfx: Mapping[str, str],
    bookmark: tuple[int, int, int],
    default: str = DEFAULT_GRAPHICAL_REGION,
) -> dict[str, list[int]]:
    """Every CK3 land province id, bucketed into one ``graphical_*`` region.

    Exactly one bucket per province: CK3 warns about a province in none and
    (as the 130 ``multiple entries for the province`` errors showed) about one
    counted twice.  Every land id is placed, including ids whose CK2 province
    has no history file at all — those get ``default``.
    """
    out: dict[str, list[int]] = {name: [] for name, _ in GRAPHICAL_REGIONS}
    placed: set[int] = set()
    for ck2_id, hist in sorted(history.items()):
        culture = hist.culture_at(bookmark)
        gfx = graphical_culture_of_culture.get(culture or "", "")
        region = region_of_gfx.get(gfx, default)
        for ck3_id in idmap.all_ck3(ck2_id):
            if ck3_id in land_ck3 and ck3_id not in placed:
                placed.add(ck3_id)
                out.setdefault(region, []).append(ck3_id)
    for ck3_id in sorted(set(land_ck3) - placed):
        out.setdefault(default, []).append(ck3_id)
    for ids in out.values():
        ids.sort()
    return out
