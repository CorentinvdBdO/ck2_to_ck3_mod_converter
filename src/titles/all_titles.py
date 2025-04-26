from pathlib import Path
from pydantic import BaseModel, Field
from .definitions import convert_definitions
from typing import Dict, List, Optional, Tuple, Any
from src.utils.paradox_file_parser import regex_paradox_parser
import re
from pprint import pprint

class Definition(BaseModel):
    id: int
    r: Optional[int] = None
    g: Optional[int] = None
    b: Optional[int] = None
    name: str
    comment: str

def open_definitions(definitions_path: Path):
    """
    Open and keep in memory the comments
    """
    definitions = []
    id_to_line = {}
    with open(definitions_path, "r") as file:
        lines = file.readlines()
        line_index = 0
        for line in lines[1:]:
            line = line.strip()
            if line.startswith("#"):
               definitions.append(line)
            else:
               id_to_line[line.split(";")[0]] = line_index
               values = line.split(";")
               id = int(values[0]) if len(values[0]) > 0 else None
               r = int(values[1]) if len(values[1]) > 0 else None
               g = int(values[2]) if len(values[2]) > 0 else None
               b = int(values[3]) if len(values[3]) > 0 else None
               name = " ".join(values[4:-1])
               x = values[-1]
               x = x.split("#")
               if len(x) > 0:
                   comment = "#".join(x[1:])        
               else:
                   comment = None
               definitions.append(Definition(
                   id=id,
                   r=r,
                   g=g,
                   b=b,
                   name=name,
                   comment=comment
               ))
            line_index += 1
    return definitions, id_to_line



class BaronyHistory(BaseModel):
    holding: Optional[str]     # Some default holdings do exist
    history: Dict[str, Dict] = Field(default_factory=dict) # Changes in buildings and holdings

class CountyProvinceHistory(BaseModel):
    id: int
    title: Optional[str] = None # Initialize optional fields to None
    base_culture: Optional[str] = None
    base_religion: Optional[str] = None
    # barony_holding: Optional[str] # This seems redundant if we have baronies_history
    baronies_history: Dict[str, BaronyHistory] = Field(default_factory=dict)
    history: Dict[str, Dict] = Field(default_factory=dict) # Changes in culture and religion
    max_settlements: Optional[int] = None
    terrain: Optional[str] = None
    comments: Optional[str] = None

def read_province_history(province_id: int, file_path: Path) -> CountyProvinceHistory:
    """
    Reads and parses a province history file using the general paradox parser.
    Converts the parsed dict to a CountyProvinceHistory object.
    """
    # Parse file into dict structure
    parsed = regex_paradox_parser(file_path)
    
    # Initialize province history
    province_history = CountyProvinceHistory(
        id=province_id,
        comments=""
    )

    # Extract base properties
    if 'title' in parsed:
        province_history.title = parsed['title']
    if 'max_settlements' in parsed:
        province_history.max_settlements = int(parsed['max_settlements'])
    if 'terrain' in parsed:
        province_history.terrain = parsed['terrain']
    if 'culture' in parsed:
        province_history.base_culture = parsed['culture']
    if 'religion' in parsed:
        province_history.base_religion = parsed['religion']

    # Extract baronies (base holdings)
    for key, value in parsed.items():
        if key.startswith('b_') and isinstance(value, str):
            province_history.baronies_history[key] = BaronyHistory(
                holding=value,
                history={}
            )

    # Extract history blocks
    for key, value in parsed.items():
        if isinstance(key, str) and '.' in key:  # Date entries
            date = key
            if isinstance(value, dict):
                # Handle province-level history
                if date not in province_history.history:
                    province_history.history[date] = {}
                
                for k, v in value.items():
                    if k.startswith('b_'):
                        # Barony history
                        barony_name = k
                        if barony_name not in province_history.baronies_history:
                            province_history.baronies_history[barony_name] = BaronyHistory(
                                holding="none",
                                history={}
                            )
                        if date not in province_history.baronies_history[barony_name].history:
                            province_history.baronies_history[barony_name].history[date] = {}
                        province_history.baronies_history[barony_name].history[date]["holding"] = v
                    else:
                        # Province-level history
                        province_history.history[date][k] = v

    return province_history


def read_all_histories(indices, original_province_history_folder) -> Dict[int, CountyProvinceHistory]:
    id_to_history = {}
    for index in indices:
        # Get history/province (missing if sea or coastline)
        ls_result = list(original_province_history_folder.glob(f"{index} - *"))
        if not ls_result:  # Empty list
            print(f"No history file found for {index}")
            continue
        else:
            history_file = ls_result[0]
            history = read_province_history(index, history_file)
            id_to_history[index] = history
    return id_to_history

def read_provinces_climate(climate_path: Path) -> Dict[int, str]:
    """
    Read the climate file and return a dictionary mapping province IDs to their climate type.
    
    Example input:
    normal_winter = {
        1 2 3 5 6 7 9 11 ...
    }
    
    Returns: {1: "normal_winter", 2: "normal_winter", ...}
    """
    parsed = regex_paradox_parser(climate_path)
    
    id_to_climate = {}
    for climate_type, value in parsed.items():
        if not climate_type.endswith('_winter'):
            continue
            
        # Value should be a dict with 'enum' key containing list of province IDs
        if isinstance(value, dict) and 'enum' in value:
            for province_id in value['enum']:
                id_to_climate[int(province_id)] = climate_type
    
    return id_to_climate

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

title_from_id = {
    "e": Empire,
    "k": Kingdom,
    "d": Duchy,
    "c": County,
    "b": Barony
}

def read_landed_titles(file_path: Path) -> List[LandedTitle]:
    """
    Reads and parses a landed titles file using the general parser.
    Converts the parsed dict to LandedTitle objects maintaining hierarchy.
    """
    parsed = regex_paradox_parser(file_path)
    
    def parse_title_block(title_name: str, title_data: Dict) -> LandedTitle:
        """Convert a title block to a LandedTitle object"""
        # Get title type from name prefix
        title_type = title_name[0]  # e, k, d, c, b
        title_class = title_from_id[title_type]
        
        # Create title object
        title = title_class(
            title_name=title_name,
            children=[]
        )
        
        # Parse properties
        for key, value in title_data.items():
            if key == 'color' and isinstance(value, dict) and 'enum' in value:
                title.color = tuple(int(x) for x in value['enum'][:3])
            elif key == 'color2' and isinstance(value, dict) and 'enum' in value:
                title.color2 = tuple(int(x) for x in value['enum'][:3])
            elif key == 'capital':
                title.capital = int(value)
            elif key == 'title':
                title.title = value
            elif key == 'title_female':
                title.title_female = value
            elif key == 'short_name':
                title.short_name = value == 'yes'
            elif key == 'landless':
                title.landless = value == 'yes'
            elif key == 'independent':
                title.independent = value == 'yes'
            elif key == 'primary':
                title.primary = value == 'yes'
            elif key == 'dynasty_title_names':
                title.dynasty_title_names = value == 'yes'
            elif key == 'can_be_claimed':
                title.can_be_claimed = value == 'yes'
            elif key == 'can_be_usurped':
                title.can_be_usurped = value == 'yes'
            elif key == 'assimilate':
                title.assimilate = value == 'yes'
            elif key == 'extra_ai_eval_troops':
                title.extra_ai_eval_troops = int(value)
            elif isinstance(value, dict):
                # Nested title
                if key.startswith(('e_', 'k_', 'd_', 'c_', 'b_')):
                    child = parse_title_block(key, value)
                    title.children.append(child)
                # Culture-specific names
                elif not any(key.startswith(x) for x in ['allow', 'gain_effect', 'color']):
                    title.cultural_names[key] = value
        
        return title

    # Parse all top-level titles
    titles = []
    for title_name, title_data in parsed.items():
        if isinstance(title_data, dict) and title_name.startswith(('e_', 'k_', 'd_', 'c_', 'b_')):
            title = parse_title_block(title_name, title_data)
            titles.append(title)

    return titles

def read_all_titles(landed_titles_path: Path) -> Dict[str, LandedTitle]:
    all_titles = {}
    for file in landed_titles_path.glob("*.txt"):
        all_titles[file.stem] = read_landed_titles(file)
    return all_titles

def convert_titles(
        original_mod_folder: str,
        new_mod_folder: str,
        start_definition_id: int,
    ):
    """
    Convert the titles as is for e, d, c, b

    Specific for c and b
    In ck2: Counties in definition.csv, 
    [ ]has de jure titles in common/landed_titles
    [X] Winter climate in map/climate.txt
    [ ] History in history/titles
    [X] History in history/provinces: title definition, culture, religion,  
         baronies (holding type), terrain, 
    Localization
    CoA in gfx/flags

    In ck3: Baronies in definition.csv, as de jure titles in common/landed_titles
    as de jure titles in common/landed_titles (with province id)
    Terrain in common/province_terrain
    Winter climate in common/province_properties
    History in history/provinces: culture, religion
    Titles history in history/titles

    Need to define history/characters, cultures, religions to have proper history
    Use atlantean placeholders for now
    """
    original_mod_folder = Path(original_mod_folder)
    # Get all "useful" baronies: present in history/provinces:

    print("Opening original definitions")
    original_definitions = Path(original_mod_folder, "map", "definition.csv")
    original_province_history_folder = Path(original_mod_folder, "history", "provinces")
    new_definitions = Path(original_mod_folder, "map_data", "definition.csv")

    definitions, id_to_line = open_definitions(original_definitions)
    print("Opening original definitions")
    id_to_history = read_all_histories(
        id_to_line.keys(),  
        original_province_history_folder
    )
    id_to_climate = read_provinces_climate(
        Path(original_mod_folder, "map", "climate.txt")
    )

    print("Reading all titles")
    
    titles = read_all_titles(
        Path(original_mod_folder, "common", "landed_titles.txt")
    )
        
    pass

