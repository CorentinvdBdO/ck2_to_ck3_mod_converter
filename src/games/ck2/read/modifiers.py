from pathlib import Path
from typing import Dict

from ck2ck3.pdx import as_dict, parse_file

from ..classes import CustomModifier


def read_modifiers_file(file_path: str | Path) -> Dict[str, CustomModifier]:
    """Read one `common/modifier_definitions/*.txt` file."""
    document = parse_file(file_path)
    modifiers: Dict[str, CustomModifier] = {}
    for node in document.nodes():
        modifiers[node.key] = CustomModifier(name=node.key, **as_dict(node.value))
    return modifiers


def read_all_modifiers(mod_path: str | Path) -> Dict[str, Dict[str, CustomModifier]]:
    """Read every modifier definition file of a CK2 mod, keyed by file stem."""
    modifiers_path = Path(mod_path) / "common" / "modifier_definitions"
    files = sorted(
        f for f in modifiers_path.iterdir() if f.is_file() and f.suffix == ".txt"
    )
    return {f.stem: read_modifiers_file(f) for f in files}
