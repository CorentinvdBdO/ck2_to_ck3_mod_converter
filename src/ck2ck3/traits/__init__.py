"""The CK2 -> CK3 trait port: tables, per-trait conversion, whole-mod planning.

`docs/step_traits.md` states the rules; `ck2ck3.steps.traits` wires this to the
CLI. Nothing here touches the filesystem except to read the input tables and
the CK2 mod.
"""

from .conflicts import TraitConflicts, read_trait_conflicts
from .convert import (
    CK3_BASE_LIFE_EXPECTANCY,
    GROUP_PREFIX,
    Converted,
    Rename,
    TraitConverter,
    UnmappedKey,
    Unported,
    opposites_cliques,
    trait_groups,
)
from .port import (
    CK3_ICON_DIR,
    Plan,
    build_plan,
    collect_icons,
    convert_plan,
    loc_key_renames,
    read_ck2_traits,
    unported,
)
from .tables import Mapping, RaceLifespan, Tables, load_tables, read_ck3_trait_ids

__all__ = [
    "CK3_BASE_LIFE_EXPECTANCY",
    "CK3_ICON_DIR",
    "Converted",
    "GROUP_PREFIX",
    "Mapping",
    "Plan",
    "RaceLifespan",
    "Rename",
    "Tables",
    "TraitConflicts",
    "TraitConverter",
    "UnmappedKey",
    "Unported",
    "build_plan",
    "collect_icons",
    "convert_plan",
    "load_tables",
    "loc_key_renames",
    "opposites_cliques",
    "read_ck2_traits",
    "read_ck3_trait_ids",
    "read_trait_conflicts",
    "trait_groups",
    "unported",
]
