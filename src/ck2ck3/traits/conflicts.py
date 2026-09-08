"""CK3 trait-conflict rules, read from the CK3 game's own trait files.

Once a vanilla-table dedupe (`docs/step_traits.md` rule 1: `exact`/`approx`/
`nearest`) can point two different CK2 traits at the same or an incompatible
CK3 trait, a character that legally held both CK2 traits can end up in a
state CK3 itself forbids: the same trait twice, two traits CK3 declares
`opposites`, or two levels of one leveled trait. `docs/step_traits.md` rule 3
resolves this by keeping the CK2-first-listed trait and commenting the rest;
this module supplies the CK3-side facts that decision needs.

Nothing here is Faerûn-specific: it is a straight read of CK3 1.19
`common/traits/*.txt`, independent of what a mod ports.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..pdx import Block, parse_file
from ..pdx.encoding import CK3_ENCODING


@dataclass
class TraitConflicts:
    """CK3's own exclusivity rules between trait ids."""

    #: CK3 trait id -> the raw tokens of its `opposites = { }` list. A token
    #: is either another trait id or a bare `group` name — CK3 lets an
    #: `opposites` entry name a whole leveled family at once (`verified`:
    #: `beauty_bad_1` opposes the group token `beauty_good`, CK3 1.19
    #: `common/traits/00_traits.txt:6824-6830`, no trait literally named
    #: `beauty_good` exists).
    opposites: dict[str, frozenset[str]] = field(default_factory=dict)
    #: CK3 trait id -> (`group`, `level`) for a leveled trait, e.g.
    #: `beauty_bad_1` -> ("beauty_bad", 1). Covers families that rely on
    #: `group`/`level` alone with no explicit `opposites` between tiers
    #: (the `education_*` ladders).
    group_level: dict[str, tuple[str, int]] = field(default_factory=dict)

    def _opposes(self, a: str, b: str) -> bool:
        for token in self.opposites.get(a, ()):
            if token == b:
                return True
            group = self.group_level.get(b)
            if group is not None and token == group[0]:
                return True
        return False

    def conflict(self, held: list[str], candidate: str) -> str | None:
        """The first trait of ``held`` (CK2 declaration order) ``candidate``
        may not join, or ``None``. Checks, in order: identical id, mutual
        `opposites` (either side may name the other, or the other's group),
        same `group` at a different `level`."""
        for other in held:
            if other == candidate:
                return other
            if self._opposes(candidate, other) or self._opposes(other, candidate):
                return other
            g1 = self.group_level.get(candidate)
            g2 = self.group_level.get(other)
            if g1 is not None and g2 is not None and g1[0] == g2[0] and g1[1] != g2[1]:
                return other
        return None


def read_trait_conflicts(traits_dir: Path) -> TraitConflicts:
    """Read `opposites`/`group`/`level` from every `.txt` of ``traits_dir``
    (the CK3 install's `common/traits`)."""
    opposites: dict[str, frozenset[str]] = {}
    group_level: dict[str, tuple[str, int]] = {}
    traits_dir = Path(traits_dir)
    if not traits_dir.is_dir():
        return TraitConflicts()
    for path in sorted(traits_dir.glob("*.txt")):
        try:
            doc = parse_file(path, encoding=CK3_ENCODING)
        except Exception:
            continue
        for node in doc.nodes():
            if node.key.startswith("@") or not isinstance(node.value, Block):
                continue
            block = node.value
            opp = block.get("opposites")
            if isinstance(opp, Block):
                tokens = frozenset(str(entry.value) for entry in opp.entries)
                if tokens:
                    opposites[node.key] = tokens
            group = block.get("group")
            level = block.get("level")
            if isinstance(group, str) and level is not None:
                try:
                    group_level[node.key] = (group, int(level))
                except (TypeError, ValueError):
                    pass
    return TraitConflicts(opposites=opposites, group_level=group_level)
