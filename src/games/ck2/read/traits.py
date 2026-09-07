from pathlib import Path
from typing import Dict

from ck2ck3.pdx import as_dict, parse_file

from ..classes import CustomModifier, Modifiers, Trait


def read_traits_file(
    file_path: str | Path,
    all_modifiers: Dict[str, Dict[str, CustomModifier]] | None = None,
    check_modifiers: bool = True,
) -> Dict[str, Trait]:
    """Read one `common/traits/*.txt` file.

    Keys that are not `Trait` fields are treated as modifiers. With
    `check_modifiers`, every such key must be a base modifier
    (`classes.Modifiers`) or a custom one from `all_modifiers`; unknown keys are
    collected and reported together instead of one at a time.
    """
    document = parse_file(file_path)
    traits: Dict[str, Trait] = {}
    for node in document.nodes():
        trait_data = as_dict(node.value)
        modifiers_data: Dict[str, object] = {}
        unknown: list[str] = []
        for key in list(trait_data):
            if key in Trait.model_fields:
                continue
            value = trait_data.pop(key)
            if not check_modifiers or key in Modifiers.__members__:
                modifiers_data[key] = value
                continue
            if all_modifiers is None:
                raise ValueError(
                    f"{file_path}: check_modifiers is True but all_modifiers is None"
                )
            for modifier_data in all_modifiers.values():
                if key in modifier_data:
                    modifiers_data[key] = value
                    break
            else:
                unknown.append(key)
        if unknown:
            raise ValueError(
                f"{file_path}: trait {node.key}: keys not found in Trait, base "
                f"modifiers or custom modifiers: {', '.join(sorted(unknown))}"
            )
        traits[node.key] = Trait(name=node.key, **trait_data, modifiers=modifiers_data)
    return traits


def read_all_traits(
    mod_path: str | Path,
    all_modifiers: Dict[str, Dict[str, CustomModifier]] | None = None,
    check_modifiers: bool = True,
) -> Dict[str, Dict[str, Trait]]:
    """Read every trait file of a CK2 mod, keyed by file stem."""
    traits_path = Path(mod_path) / "common" / "traits"
    files = sorted(
        f for f in traits_path.iterdir() if f.is_file() and f.suffix == ".txt"
    )
    return {f.stem: read_traits_file(f, all_modifiers, check_modifiers) for f in files}
