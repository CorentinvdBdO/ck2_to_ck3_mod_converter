"""CK2 -> CK3 conversion of characters and dynasties.

Split from the step modules on purpose: everything here is a pure function of
a parse tree plus a :class:`~ck2ck3.port.tables.Tables`, so a rule can be
tested with a three-line CK2 fixture and no :class:`~ck2ck3.context.Context`.
"""

from .tables import Tables, load_tables
from .characters import CharacterPort, convert_character, convert_character_file
from .dynasties import DynastyPort, convert_dynasty_file

__all__ = [
    "CharacterPort",
    "DynastyPort",
    "Tables",
    "convert_character",
    "convert_character_file",
    "convert_dynasty_file",
    "load_tables",
]
