from pydantic import BaseModel, Field
from typing import Optional, Dict, List, Tuple

# All objects in CK2

class Definition(BaseModel):
    id: int
    r: Optional[int] = None
    g: Optional[int] = None
    b: Optional[int] = None
    name: str

class OceanRegion(BaseModel):
    sea_zones:List[int] = []

class DefaultDotMap(BaseModel):
    max_provinces:int
    definitions:str = "definition.csv"
    provinces:str = "provinces.bmp"
    positions:str = "positions.txt"
    terrain:str = "terrain.bmp"
    rivers:str = "rivers.bmp"
    terrain_definition:str = "terrain.txt"
    heightmap:str = "topology.bmp"
    tree_definition:str = "trees.bmp"
    continent:str = "continent.txt"
    adjacencies:str = "adjacencies.csv"
    climate:str = "climate.txt"
    region:str = "island_region.txt"
    geographical_region:str = "geographical_region.txt"
    static:str = "statics"
    seasons:str = "seasons.txt"

    externals:List[int] = []
    sea_zones:Dict[int, List[int]] = {}
    ocean_regions:Dict[int, OceanRegion] = {}
    major_rivers: List[int] = []

    tree: List[int] = []

class BaronyHistory(BaseModel):
    holding: Optional[str]     # Some default holdings do exist
    history: Dict[str, Dict] = Field(default_factory=dict) # Changes in buildings and holdings

class CountyProvinceHistory(BaseModel):
    id: int
    title: Optional[str] = None
    base_culture: Optional[str] = None
    base_religion: Optional[str] = None
    baronies_history: Dict[str, BaronyHistory] = Field(default_factory=dict)
    history: Dict[str, Dict] = Field(default_factory=dict) # Changes in culture and religion
    max_settlements: Optional[int] = None
    terrain: Optional[str] = None
    comments: Optional[str] = None

class LandedTitle(BaseModel):
    rank: int
    title_name: str
    color: Optional[Tuple[int, int, int]] = None
    color2: Optional[Tuple[int, int, int]] = None
    cultural_names: Optional[Dict[str, str]] = {}
    capital: Optional[int] = None
    capital_comment: Optional[str] = None
    comment: Optional[str] = None
    children: Optional[List["LandedTitle"]] = []

    # More properties
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

class Empire(LandedTitle):
    rank: int = 1
    pass

class Kingdom(LandedTitle):
    rank: int = 2
    pass

class Duchy(LandedTitle):
    rank: int = 3
    pass

class County(LandedTitle):
    rank: int = 4
    pass

class Barony(LandedTitle):
    rank: int = 5
    capital: Optional[int] = None
    color: Optional[Tuple[int, int, int]] = None
    color2: Optional[Tuple[int, int, int]] = None
    pass

class Character(BaseModel):
    name: str
    history: Dict[str, Dict] = {}

class Culture(BaseModel):
    name: str
    color: Optional[Tuple[int, int, int]] = None

class Religion(BaseModel):
    name: str
    color: Optional[Tuple[int, int, int]] = None

class Modifier(BaseModel):
    name: str

class Event(BaseModel):
    name: str

title_from_id = {
    "e": Empire,
    "k": Kingdom,
    "d": Duchy,
    "c": County,
    "b": Barony
}