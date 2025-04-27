from pathlib import Path
from typing import List, Dict
from src.utils.paradox_file_parser import regex_paradox_parser
from ..classes import Trait, Modifiers, CustomModifier


def read_traits_file(file_path: str, all_modifiers: Dict[str, Dict[str, CustomModifier]]=None, check_modifiers: bool=True) -> List[Trait]:
    file_json = regex_paradox_parser(file_path) 
    traits = {}
    for trait_name, trait_data in file_json.items():
        modifiers_data = {}
        try:
            for key, value in trait_data.items():
                # key in Trait
                if key in Trait.model_fields:
                    trait_data[key] = value
                elif not check_modifiers:
                    modifiers_data[key] = value
                elif key in Modifiers:
                    modifiers_data[key] = value
                elif all_modifiers is None:
                    raise ValueError(f"check_modifiers is True but all_modifiers not provided")
                else:
                    for modifier_file, modifier_data in all_modifiers.items():
                        if key in modifier_data:
                            modifiers_data[key] = modifier_data[key]
                            break
                    else:
                        raise ValueError(f"Key {key} not found in Trait, base modifiers or custom modifiers")
        except Exception as e:
            print(trait_data)
            print(f"Error reading trait {trait_name}: {e}")
            raise e
        trait = Trait(name=trait_name, **trait_data, modifiers=modifiers_data)
        traits[trait_name] = trait
    return traits


def read_all_traits(mod_path: str, all_modifiers: Dict[str, Dict[str, CustomModifier]]=None, check_modifiers: bool=True) -> List[Trait]:
    traits_path = Path(mod_path) / "common" / "traits"
    # files endig with .txt
    trait_files = [f for f in traits_path.iterdir() if f.is_file() and f.suffix == ".txt"]
    all_traits =  {}
    for f in trait_files:
        print(f"Reading {f}")
        all_traits[f.stem] = read_traits_file(f, all_modifiers, check_modifiers)
    return all_traits