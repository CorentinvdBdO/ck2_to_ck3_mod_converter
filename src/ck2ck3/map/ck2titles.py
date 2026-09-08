"""Reader for the CK2 ``common/landed_titles/`` hierarchy.

Only the *shape* is read — tier nesting, file order, and the first barony of
each county (which is the county's capital holding in CK2).  Colours, laws,
cultural names and every other field are the ``titles-history`` lane's
business; this module exists because the map step has to answer two questions
that only the hierarchy can answer:

1. **id order.** ``map_data/definition.csv`` ids are assigned in
   (empire, kingdom, duchy, county, barony) file order, so two baronies that
   are neighbours on the map get ids that are close together.  CK3 does not
   require this, but every tool that reads a province range does.
2. **which barony is the county capital.** CK2 has no ``capital = b_x`` inside
   a county; the capital is the *first* barony declared in the county block
   (`verified` on Faerûn: ``c_waterdeep``'s first barony is
   ``b_castle_waterdeep``, which is also the only one built at 1357 and the one
   the county's ``positions.txt`` city slot sits in).  The capital gets the
   ``positions.txt`` city coordinate as its seed.

Ordering note: :func:`read` relies on ``dict`` preserving insertion order and
on title keys being unique inside their parent block, which they are — a CK2
block cannot declare ``c_foo`` twice.  Duplicate keys *across* files are
reported rather than merged.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .blocks import Block, parse_file

#: CK2 title tiers, highest first. ``b_`` is a barony, ``c_`` a county.
TIERS = ("e", "k", "d", "c", "b")


@dataclass(frozen=True)
class Ck2Title:
    """One title in the CK2 hierarchy, with its path to the root."""

    key: str
    tier: str
    #: parent title key, ``None`` for a top-level title
    parent: str | None
    #: ``(empire, kingdom, duchy, county, barony)`` keys, missing tiers ``None``
    path: tuple[str | None, ...]
    #: position in the depth-first walk of the whole hierarchy
    order: int
    #: file the title was declared in, for error messages
    source: str = ""

    def ancestor(self, tier: str) -> str | None:
        return self.path[TIERS.index(tier)]


@dataclass
class Ck2TitleTree:
    #: title key -> title, in depth-first file order
    titles: dict[str, Ck2Title] = field(default_factory=dict)
    #: county key -> its barony keys in declaration order (first = capital)
    county_baronies: dict[str, list[str]] = field(default_factory=dict)
    #: keys declared more than once (later declarations are ignored)
    duplicates: list[str] = field(default_factory=list)

    def of_tier(self, tier: str) -> list[Ck2Title]:
        return [t for t in self.titles.values() if t.tier == tier]

    def capital_barony(self, county: str) -> str | None:
        """CK2's county capital: the first barony declared in the county."""
        baronies = self.county_baronies.get(county) or []
        return baronies[0] if baronies else None

    def sort_key(self, barony: str) -> tuple[int, ...]:
        """Hierarchy sort key for a barony, for dense id assignment.

        The barony's own walk order already encodes (empire, kingdom, duchy,
        county, barony) precedence, because the walk is depth-first in file
        order.  Returned as a tuple so callers can extend it.
        """
        t = self.titles.get(barony)
        return (t.order,) if t else (1 << 30,)


def tier_of(key: str) -> str | None:
    """``'c_waterdeep' -> 'c'``; ``None`` for anything that is not a title."""
    if len(key) > 2 and key[1] == "_" and key[0] in TIERS:
        return key[0]
    return None


def read(paths: list[Path] | list[str]) -> Ck2TitleTree:
    """Read every ``common/landed_titles/*.txt`` into one tree.

    Files are read in the order given; CK2 loads them alphabetically, so pass
    ``sorted(dir.glob('*.txt'))``.
    """
    tree = Ck2TitleTree()
    counter = 0

    def walk(block: Block, parent: Ck2Title | None, source: str) -> None:
        nonlocal counter
        for key, values in block.children.items():
            tier = tier_of(key)
            if tier is None:
                continue
            for value in values:
                if not isinstance(value, Block):
                    continue
                if key in tree.titles:
                    tree.duplicates.append(key)
                    continue
                path = list(parent.path) if parent else [None] * len(TIERS)
                path[TIERS.index(tier)] = key
                # a nested tier resets everything below it
                for i in range(TIERS.index(tier) + 1, len(TIERS)):
                    path[i] = None
                title = Ck2Title(
                    key=key,
                    tier=tier,
                    parent=parent.key if parent else None,
                    path=tuple(path),
                    order=counter,
                    source=source,
                )
                counter += 1
                tree.titles[key] = title
                if tier == "b" and parent is not None and parent.tier == "c":
                    tree.county_baronies.setdefault(parent.key, []).append(key)
                walk(value, title, source)

    for p in paths:
        path = Path(p)
        walk(parse_file(path), None, path.name)
    return tree


def read_dir(directory: str | Path) -> Ck2TitleTree:
    """Read ``common/landed_titles/`` in CK2's own (alphabetical) load order."""
    return read(sorted(Path(directory).glob("*.txt")))
