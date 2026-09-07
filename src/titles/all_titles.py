"""CK2-side readers for definitions, province history, climate and landed titles.

Reads through `ck2ck3.pdx` (tokenizer parser, comments kept, cp1252 sniffed).
The write side belongs to lane `titles-history`.
"""

from pathlib import Path
from typing import Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

from ck2ck3.pdx import Block, Color, Date, parse_file
from ck2ck3.pdx.encoding import CK2_ENCODING, read_text

#: The five CK2 / CK3 title tiers, by identifier prefix.
TITLE_PREFIXES = ("e_", "k_", "d_", "c_", "b_")


class Definition(BaseModel):
    id: Optional[int] = None
    r: Optional[int] = None
    g: Optional[int] = None
    b: Optional[int] = None
    name: str
    comment: Optional[str] = None


def open_definitions(
    definitions_path: Path,
) -> Tuple[List[object], Dict[str, int]]:
    """Read CK2 `map/definition.csv`, keeping comment lines in place.

    Windows-1252 like the rest of a CK2 mod. Returns the rows in file order
    (a `Definition` or the raw comment string) and a province-id → row-index
    map.
    """
    text, _ = read_text(definitions_path, CK2_ENCODING)
    rows: List[object] = []
    id_to_line: Dict[str, int] = {}
    lines = text.split("\n")
    for index, raw in enumerate(lines[1:]):
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            rows.append(line)
            continue
        values = line.split(";")
        id_to_line[values[0]] = index
        head, tail = values[0:4], values[-1]
        name = " ".join(values[4:-1])
        comment = "#".join(tail.split("#")[1:]) or None
        rows.append(
            Definition(
                id=int(head[0]) if head[0] else None,
                r=int(head[1]) if len(head) > 1 and head[1] else None,
                g=int(head[2]) if len(head) > 2 and head[2] else None,
                b=int(head[3]) if len(head) > 3 and head[3] else None,
                name=name,
                comment=comment,
            )
        )
    return rows, id_to_line


class BaronyHistory(BaseModel):
    holding: Optional[str]  # Some default holdings do exist
    history: Dict[str, Dict] = Field(default_factory=dict)  # holding changes


class CountyProvinceHistory(BaseModel):
    id: int
    title: Optional[str] = None
    base_culture: Optional[str] = None
    base_religion: Optional[str] = None
    baronies_history: Dict[str, BaronyHistory] = Field(default_factory=dict)
    history: Dict[str, Dict] = Field(default_factory=dict)  # culture / religion
    max_settlements: Optional[int] = None
    terrain: Optional[str] = None
    comments: Optional[str] = None


def _is_date(key: str) -> bool:
    try:
        Date.parse(key)
    except (ValueError, TypeError):
        return False
    return True


def read_province_history(province_id: int, file_path: Path) -> CountyProvinceHistory:
    """Read one `history/provinces/<id> - <name>.txt` file."""
    document = parse_file(file_path)
    province = CountyProvinceHistory(id=province_id, comments="")

    for node in document.nodes():
        key, value = node.key, node.value
        if key == "title":
            province.title = str(value)
        elif key == "max_settlements":
            province.max_settlements = int(value)
        elif key == "terrain":
            province.terrain = str(value)
        elif key == "culture":
            province.base_culture = str(value)
        elif key == "religion":
            province.base_religion = str(value)
        elif key.startswith("b_") and not isinstance(value, Block):
            province.baronies_history[key] = BaronyHistory(
                holding=str(value), history={}
            )
        elif _is_date(key) and isinstance(value, Block):
            _apply_dated_block(province, key, value)
    return province


def _apply_dated_block(
    province: CountyProvinceHistory, date: str, block: Block
) -> None:
    """Fold one `<date> = { … }` block into the province history."""
    for node in block.nodes():
        if node.key.startswith("b_"):
            barony = province.baronies_history.setdefault(
                node.key, BaronyHistory(holding="none", history={})
            )
            barony.history.setdefault(date, {})["holding"] = node.value
        else:
            province.history.setdefault(date, {})[node.key] = node.value


def read_all_histories(
    indices, original_province_history_folder: Path
) -> Dict[int, CountyProvinceHistory]:
    """Read the province history of every id in `indices` that has a file."""
    id_to_history: Dict[int, CountyProvinceHistory] = {}
    for index in indices:
        matches = sorted(original_province_history_folder.glob(f"{index} - *"))
        if not matches:
            # Sea zones and coastline provinces have no history file.
            continue
        id_to_history[int(index)] = read_province_history(int(index), matches[0])
    return id_to_history


def read_provinces_climate(climate_path: Path) -> Dict[int, str]:
    """Read CK2 `map/climate.txt` into province id → climate type.

    ``severe_winter = { 4 10 17 … }`` becomes ``{4: "severe_winter", …}``.
    """
    document = parse_file(climate_path)
    id_to_climate: Dict[int, str] = {}
    for node in document.nodes():
        if not node.key.endswith("_winter") or not isinstance(node.value, Block):
            continue
        for province_id in node.value.list_values():
            id_to_climate[int(province_id)] = node.key
    return id_to_climate


class LandedTitle(BaseModel):
    rank: int
    title_name: str
    color: Optional[Tuple[int, int, int]] = None
    color2: Optional[Tuple[int, int, int]] = None
    cultural_names: Dict[str, str] = Field(default_factory=dict)
    capital: Optional[int] = None
    capital_comment: Optional[str] = None
    comment: Optional[str] = None
    children: List["LandedTitle"] = Field(default_factory=list)

    assimilate: Optional[bool] = None
    title_female: Optional[str] = None
    title: Optional[str] = None
    short_name: Optional[bool] = None
    landless: Optional[bool] = None
    independent: Optional[bool] = None
    primary: Optional[bool] = None
    dynasty_title_names: Optional[bool] = None
    can_be_claimed: Optional[bool] = None
    can_be_usurped: Optional[bool] = None
    extra_ai_eval_troops: Optional[int] = None
    #: Every key this model has no field for, kept verbatim so lane
    #: `titles-history` can decide what to do with it.
    extra: Dict[str, object] = Field(default_factory=dict)


class Empire(LandedTitle):
    rank: int = 1


class Kingdom(LandedTitle):
    rank: int = 2


class Duchy(LandedTitle):
    rank: int = 3


class County(LandedTitle):
    rank: int = 4


class Barony(LandedTitle):
    rank: int = 5


title_from_id = {"e": Empire, "k": Kingdom, "d": Duchy, "c": County, "b": Barony}

#: Boolean `landed_titles` keys carried straight onto the model.
_FLAGS = (
    "short_name",
    "landless",
    "independent",
    "primary",
    "dynasty_title_names",
    "can_be_claimed",
    "can_be_usurped",
    "assimilate",
)

#: Every CK2 `landed_titles` keyword that takes a scalar. Measured on Faerun
#: (`docs/formats_ck2_landed_titles.md`): any *other* scalar key inside a title
#: block is a culture or culture-group id and its value is a cultural name.
_SCALAR_KEYWORDS = frozenset(
    {
        "assimilate",
        "caliphate",
        "can_be_claimed",
        "can_be_usurped",
        "capital",
        "controls_religion",
        "creation_requires_capital",
        "culture",
        "dignity",
        "dynasty_title_names",
        "extra_ai_eval_troops",
        "foa",
        "graphical_culture",
        "holy_order",
        "holy_site",
        "independent",
        "landless",
        "location_ruler_title",
        "mercenary",
        "mercenary_type",
        "monthly_income",
        "name_tier",
        "pirate",
        "primary",
        "rebel",
        "religion",
        "short_name",
        "strength_growth_per_century",
        "title",
        "title_female",
        "title_prefix",
        "tribe",
    }
)

#: Block keys that are not cultural name overrides.
_BLOCK_KEYWORDS = frozenset(
    {"allow", "gain_effect", "color", "color2", "male_names", "female_names"}
)


def _color(value: object) -> Optional[Tuple[int, int, int]]:
    """`color = { 20 30 40 }` or `color = rgb { 20 30 40 }` → an RGB tuple."""
    if isinstance(value, Color):
        components = value.components
    elif isinstance(value, Block):
        components = value.list_values()
    else:
        return None
    if len(components) < 3:
        return None
    return tuple(int(c) for c in components[:3])  # type: ignore[return-value]


def _parse_title_block(title_name: str, block: Block) -> LandedTitle:
    title = title_from_id[title_name[0]](title_name=title_name)
    for node in block.nodes():
        key, value = node.key, node.value
        if key == "color":
            title.color = _color(value)
        elif key == "color2":
            title.color2 = _color(value)
        elif key == "capital":
            title.capital = int(value)
            title.capital_comment = node.trailing_comment
        elif key in ("title", "title_female"):
            setattr(title, key, str(value))
        elif key in _FLAGS:
            title.__setattr__(key, bool(value))
        elif key == "extra_ai_eval_troops":
            title.extra_ai_eval_troops = int(value)
        elif isinstance(value, Block):
            if key.startswith(TITLE_PREFIXES):
                title.children.append(_parse_title_block(key, value))
            elif key not in _BLOCK_KEYWORDS:
                title.extra[key] = value
        elif key in _SCALAR_KEYWORDS:
            title.extra[key] = value
        else:
            # A culture or culture-group id: `green_elf = Cormanthor`.
            title.cultural_names[key] = str(value)
    return title


def read_landed_titles(file_path: Path) -> List[LandedTitle]:
    """Read one `common/landed_titles/*.txt` file into a title hierarchy."""
    document = parse_file(file_path)
    return [
        _parse_title_block(node.key, node.value)
        for node in document.nodes()
        if node.key.startswith(TITLE_PREFIXES) and isinstance(node.value, Block)
    ]


def read_all_titles(landed_titles_path: Path) -> Dict[str, List[LandedTitle]]:
    """Read every landed-titles file of a folder, keyed by file stem."""
    return {
        path.stem: read_landed_titles(path)
        for path in sorted(landed_titles_path.glob("*.txt"))
    }


def flatten_titles(titles: List[LandedTitle]) -> List[LandedTitle]:
    """Depth-first list of a title hierarchy, parents before children."""
    flat: List[LandedTitle] = []
    stack = list(reversed(titles))
    while stack:
        title = stack.pop()
        flat.append(title)
        stack.extend(reversed(title.children))
    return flat


def convert_titles(
    original_mod_folder: str,
    new_mod_folder: str,
    start_definition_id: int,
):
    """Read the CK2 title side. Writing is lane `titles-history`.

    Change of paradigm between the games:

    - CK2: counties are in `map/definition.csv`, de jure titles in
      `common/landed_titles`, winter climate in `map/climate.txt`, history in
      `history/titles` and `history/provinces` (title, culture, religion,
      baronies as holding types, terrain), localisation in `localisation/`,
      coats of arms in `gfx/flags`.
    - CK3: baronies are in `map_data/definition.csv` and are de jure titles in
      `common/landed_titles` with a province id; terrain in
      `common/province_terrain`, winter in `common/province_properties`,
      province history in `history/provinces` (culture, religion), title
      history in `history/titles`.
    """
    original_mod_folder = Path(original_mod_folder)
    definitions, id_to_line = open_definitions(
        original_mod_folder / "map" / "definition.csv"
    )
    id_to_history = read_all_histories(
        [key for key in id_to_line if not key.startswith("#")],
        original_mod_folder / "history" / "provinces",
    )
    id_to_climate = read_provinces_climate(
        original_mod_folder / "map" / "climate.txt"
    )
    titles = read_all_titles(original_mod_folder / "common" / "landed_titles")
    return definitions, id_to_history, id_to_climate, titles
