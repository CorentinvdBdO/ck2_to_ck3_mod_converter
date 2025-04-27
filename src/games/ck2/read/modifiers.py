from pathlib import Path
from typing import List
from src.utils.paradox_file_parser import regex_paradox_parser
from ..classes import CustomModifier


def read_modifiers_file(file_path: str) -> List[CustomModifier]:
    file_json = regex_paradox_parser(file_path) 
    modifiers = {}
    for modifier_name, modifier_data in file_json.items():
        modifier = CustomModifier(name=modifier_name, **modifier_data)
        modifiers[modifier_name] = modifier
    return modifiers


def read_all_modifiers(mod_path: str) -> List[CustomModifier]:
    modifiers_path = Path(mod_path) / "common" / "modifier_definitions"
    # files endig with .txt
    modifier_files = [f for f in modifiers_path.iterdir() if f.is_file() and f.suffix == ".txt"]
    return {
        f.stem: read_modifiers_file(f) for f in modifier_files
    }

if __name__ == "__main__":
    from pprint import pprint
    pprint(read_all_modifiers("/home/cvdbdo/git/mod/ck3/forgotten_kings/ck2_mod_converter/Faerun/Faerun"))