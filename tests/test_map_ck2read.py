"""Tests for the CK2 ``map/`` readers, on fixture snippets taken from Faerûn."""

from __future__ import annotations

from ck2ck3.map import ck2read as r

# --- fixtures (verbatim shapes from Faerun/Faerun/map/, trimmed) ------------ #

DEFINITION_CSV = """\
province;red;green;blue;x;x
1;131;206;243;Waterdeep;x
2;131;167;167;Amphail;x
# a comment row that CK2 tolerates
3;91;170;213;Daggerford;x
3;9;9;9;DuplicateIgnored;x
"""

DEFAULT_MAP = """\
max_provinces = 2720
sea_zones = { 10 12 } #Trackless Sea 1
sea_zones = { 20 21 } #Lakes 2
sea_zones = { 30 30 } #Lakes 3

ocean_region = {\t# Trackless Sea
\tsea_zones = { 1 }
}
ocean_region = {\t# Lakes
\tsea_zones = { 2 3 }
}
major_rivers = { 40 41 }
externals = { 99 }
"""

CLIMATE = """\
severe_winter = {
\t4 10 17
}
normal_winter = {
\t1 2
}
mild_winter = {
\t8
}
"""

ISLAND_REGION = """\
region_mintarn = {
\tprovinces = { 223 }
}

region_ruathym = {
\tprovinces = { 224 1179 1180 }
}
"""

GEO_REGION = """\
#a comment
sword_coast_north_region = {
\tduchies = {
\t\td_waterdeep d_leilon d_runedardath
\t}
}
sword_coast_region = {
\tregions = {
\t\tsword_coast_north_region
\t}
}
prov_region = {
\tprovinces = { 5 6 }
}
"""

ADJACENCIES = """\
From;To;Type;Through;-1;-1;-1;-1;Comment
1007;1015;sea;1936;-1;-1;-1;-1;stillshore to mulsantir
1453;1554;sea;2061;-1;-1;-1;-1;Hiyal-Karzuwa
"""

TERRAIN = """\
terrain = 17
categories = {
\tocean = {
\t\tmovement_cost = 1.0
\t\tis_water = yes
\t\tcolor = { 255 255 255 }
\t}
\thills = {
\t\tmovement_cost = 1.3
\t\tcolor = { 135 70 0 }
\t}
}
text_0\t= { type = plains color = { 0 } priority = 0 }
text_4\t= { type = hills  color = { 4 } priority = 4 }
text_20\t= { type = forest color = { 20 } priority = 20 }
"""

POSITIONS = """\
#Waterdeep
\t1=
\t{
\t\tposition={1119.000 2838.000 1116.000 2844.000 1112.000 2849.000 1117.000 2844.000 1113.000 2833.000 1111.000 2826.000 1118.000 2832.000}
\t\trotation={0.000 0.000 0.785 0.000 0.785 0.000 0.785}
\t\theight={0.000 0.000 0.000 20.000 0.000 0.000 0.000}
\t}
"""


def _w(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(text, encoding="cp1252")
    return p


# --- definition.csv -------------------------------------------------------- #
def test_read_definitions_skips_header_comments_and_duplicates(tmp_path):
    provs = r.read_definitions(_w(tmp_path, "definition.csv", DEFINITION_CSV))
    assert [p.id for p in provs] == [1, 2, 3]
    assert provs[0] == r.Ck2Province(id=1, rgb=(131, 206, 243), name="Waterdeep")
    assert provs[2].name == "Daggerford"  # first definition wins


# --- default.map ----------------------------------------------------------- #
def test_read_default_map_sea_zones_and_names(tmp_path):
    dm = r.read_default_map(_w(tmp_path, "default.map", DEFAULT_MAP))
    assert dm.max_provinces == 2720
    assert dm.sea_zones == [(10, 12), (20, 21), (30, 30)]
    assert dm.sea_zone_names == ["Trackless Sea 1", "Lakes 2", "Lakes 3"]
    assert dm.major_rivers == [40, 41]
    assert dm.externals == [99]


def test_sea_ids_expands_ranges_inclusively(tmp_path):
    dm = r.read_default_map(_w(tmp_path, "default.map", DEFAULT_MAP))
    assert dm.sea_ids() == {10, 11, 12, 20, 21, 30}


def test_lake_ids_uses_the_ocean_region_comment(tmp_path):
    """CK2 only labels lakes by the ocean_region comment text."""
    dm = r.read_default_map(_w(tmp_path, "default.map", DEFAULT_MAP))
    assert dm.ocean_regions == {"Trackless Sea": [1], "Lakes": [2, 3]}
    assert dm.lake_ids() == {20, 21, 30}


# --- the rest -------------------------------------------------------------- #
def test_read_climate(tmp_path):
    c = r.read_climate(_w(tmp_path, "climate.txt", CLIMATE))
    assert c == {
        "severe_winter": [4, 10, 17],
        "normal_winter": [1, 2],
        "mild_winter": [8],
    }


def test_read_island_regions(tmp_path):
    i = r.read_island_regions(_w(tmp_path, "island_region.txt", ISLAND_REGION))
    assert i == {"region_mintarn": [223], "region_ruathym": [224, 1179, 1180]}


def test_read_geographical_regions(tmp_path):
    g = r.read_geographical_regions(_w(tmp_path, "geographical_region.txt", GEO_REGION))
    by_name = {x.name: x for x in g}
    assert by_name["sword_coast_north_region"].duchies == [
        "d_waterdeep",
        "d_leilon",
        "d_runedardath",
    ]
    assert by_name["sword_coast_region"].regions == ["sword_coast_north_region"]
    assert by_name["prov_region"].provinces == [5, 6]


def test_read_adjacencies(tmp_path):
    a = r.read_adjacencies(_w(tmp_path, "adjacencies.csv", ADJACENCIES))
    assert len(a) == 2
    assert a[0] == r.Ck2Adjacency(
        from_id=1007, to_id=1015, type="sea", through=1936,
        comment="stillshore to mulsantir",
    )


def test_read_terrain_texture_map_uses_palette_index_not_rgb(tmp_path):
    p = _w(tmp_path, "terrain.txt", TERRAIN)
    assert r.read_terrain_texture_map(p) == {0: "plains", 4: "hills", 20: "forest"}


def test_read_terrain_categories_is_water(tmp_path):
    p = _w(tmp_path, "terrain.txt", TERRAIN)
    assert r.read_terrain_categories(p) == {"ocean": True, "hills": False}


def test_read_positions_returns_seven_slots(tmp_path):
    pos = r.read_positions(_w(tmp_path, "positions.txt", POSITIONS))
    assert len(pos[1]) == 7
    assert pos[1][0] == (1119.0, 2838.0)
    assert r.CK2_POSITION_SLOTS[0] == "city"
