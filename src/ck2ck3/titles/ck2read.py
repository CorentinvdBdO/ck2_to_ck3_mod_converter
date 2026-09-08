"""Readers for the CK2 title side: landed titles, both histories, bookmarks.

Migrated from the legacy ``src/titles/all_titles.py`` (pydantic models, no
writer) and extended with the three files that lane had no reader for at all:
``history/titles``, ``common/bookmarks`` and ``common/cultures``.  The keyword
lists were measured on the Faerun clone; the evidence is in
``docs/formats_ck2_landed_titles.md``.

Everything a CK2 title block carries is kept: keys with a CK3 home land on a
field, keys without one stay in :attr:`Ck2Title.extra` verbatim so the writer
can emit them as a comment rather than drop them silently.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

from ..pdx import Block, Color, Date, Node, parse_file

#: The five CK2 / CK3 title tiers, by identifier prefix.
TITLE_PREFIXES = ("e_", "k_", "d_", "c_", "b_")

#: Tier number per prefix, empire = 1 … barony = 5 (CK2's own `rank`).
TIER_BY_PREFIX = {"e": 1, "k": 2, "d": 3, "c": 4, "b": 5}

#: Every CK2 ``landed_titles`` key that takes a scalar and is *not* a culture
#: id.  Any other scalar key inside a title block is a culture or
#: culture-group id and its value is that culture's name for the title
#: (`verified`, ``docs/formats_ck2_landed_titles.md``).
SCALAR_KEYWORDS = frozenset(
    {
        "assimilate",
        "caliphate",
        "can_be_claimed",
        "can_be_usurped",
        "capital",
        "controls_religion",
        "creation_requires_capital",
        "culture",
        "dignity",
        "duchy_revokation",
        "dynasty_title_names",
        "extra_ai_eval_troops",
        "foa",
        "graphical_culture",
        "has_top_de_jure_capital",
        "hire_range",
        "holy_order",
        "holy_site",
        "independent",
        "landless",
        "location_ruler_title",
        "mercenary",
        "mercenary_type",
        "monthly_income",
        "monster",
        "name_tier",
        "pentarchy",
        "pirate",
        "planar",
        "primary",
        "purple_born_heirs",
        "rebel",
        "religion",
        "short_name",
        "spectator",
        "strength_growth_per_century",
        "title",
        "title_female",
        "title_prefix",
        "top_de_jure_capital",
        "tribe",
        "used_for_dynasty_names",
    }
)

#: Faerun-custom ``<x>_group = yes`` title markers.  They look exactly like a
#: culture-group cultural-name override (``dwarf_group = Hollowbold``), so they
#: are told apart by the *value*: a bool is a marker, a string is a name.
GROUP_MARKER_SUFFIX = "_group"

#: Block-valued keys of a title block that are not cultural names.
BLOCK_KEYWORDS = frozenset(
    {
        "allow",
        "color",
        "color2",
        "female_names",
        "gain_effect",
        "male_names",
    }
)

#: Block keys inside a CK2 culture *group* that are not cultures.
_CULTURE_GROUP_KEYWORDS = frozenset(
    {
        "graphical_cultures",
        "alternate_start",
        "unit_graphical_cultures",
    }
)


def _rgb(value: object) -> tuple[int, int, int] | None:
    """``color = { 20 30 40 }`` or ``color = rgb { … }`` -> an RGB tuple.

    CK2 writes 0-255 ints in Faerun (`verified`: 0 float colours in the 7
    landed-titles files), but the 0-1 float form is legal CK2, so both are
    accepted and normalised to 0-255 for CK3.
    """
    if isinstance(value, Color):
        components = value.components
    elif isinstance(value, Block):
        components = value.list_values()
    else:
        return None
    nums = [c for c in components if isinstance(c, (int, float))]
    if len(nums) < 3:
        return None
    triple = nums[:3]
    if all(isinstance(c, float) and 0.0 <= c <= 1.0 for c in triple):
        return tuple(int(round(c * 255)) for c in triple)  # type: ignore[return-value]
    return tuple(max(0, min(255, int(c))) for c in triple)  # type: ignore[return-value]


@dataclass
class Ck2Title:
    """One ``e_/k_/d_/c_/b_`` block of ``common/landed_titles``."""

    id: str
    tier: int
    source: str = ""
    line: int = 0
    color: tuple[int, int, int] | None = None
    color2: tuple[int, int, int] | None = None
    capital: str | None = None
    capital_comment: str | None = None
    #: culture or culture-group id -> the literal name CK2 gives the title.
    cultural_names: dict[str, str] = field(default_factory=dict)
    #: ``<x>_group = yes`` Faerun markers (bool-valued, not names).
    group_markers: list[str] = field(default_factory=list)
    #: every keyword key CK2 set, value as parsed (duplicates lost).
    keywords: dict[str, object] = field(default_factory=dict)
    #: block-valued keys that have no CK3 home, kept for the comment pass.
    blocks: dict[str, Block] = field(default_factory=dict)
    leading_comments: list[str] = field(default_factory=list)
    trailing_comment: str | None = None
    children: list["Ck2Title"] = field(default_factory=list)
    parent: str | None = None

    @property
    def prefix(self) -> str:
        return self.id[0]

    def flag(self, key: str) -> bool:
        """A CK2 boolean keyword, tolerating ``yes`` / ``1`` / ``"yes"``."""
        value = self.keywords.get(key)
        if isinstance(value, bool):
            return value
        if isinstance(value, int):
            return bool(value)
        if isinstance(value, str):
            return value.lower() in ("yes", "true", "1")
        return False


def _parse_title(node: Node, source: str, parent: str | None) -> Ck2Title:
    title = Ck2Title(
        id=node.key,
        tier=TIER_BY_PREFIX[node.key[0]],
        source=source,
        line=node.line,
        leading_comments=list(node.leading_comments),
        trailing_comment=node.trailing_comment,
        parent=parent,
    )
    for entry in node.block:
        if not isinstance(entry, Node):
            continue
        key, value = entry.key, entry.value
        if key == "color":
            title.color = _rgb(value)
        elif key == "color2":
            title.color2 = _rgb(value)
        elif key == "capital":
            title.capital = str(value)
            title.capital_comment = entry.trailing_comment
        elif isinstance(value, Block):
            if key.startswith(TITLE_PREFIXES) and len(key) > 2:
                title.children.append(_parse_title(entry, source, title.id))
            elif key in BLOCK_KEYWORDS:
                title.blocks[key] = value
            else:
                title.blocks[key] = value
        elif key in SCALAR_KEYWORDS:
            title.keywords[key] = value
        elif key.endswith(GROUP_MARKER_SUFFIX) and isinstance(value, bool):
            title.group_markers.append(key)
        else:
            # A culture or culture-group id: `green_elf = Cormanthor`.
            title.cultural_names[key] = str(value)
    return title


def read_landed_titles(path: Path) -> list[Ck2Title]:
    """Read one ``common/landed_titles/*.txt`` into a title hierarchy."""
    document = parse_file(path)
    return [
        _parse_title(node, path.name, None)
        for node in document.nodes()
        if node.key.startswith(TITLE_PREFIXES)
        and len(node.key) > 2
        and isinstance(node.value, Block)
    ]


def read_landed_titles_dir(directory: Path) -> list[Ck2Title]:
    """Read every ``*.txt`` of a CK2 ``common/landed_titles`` folder."""
    roots: list[Ck2Title] = []
    for path in sorted(directory.glob("*.txt")):
        roots.extend(read_landed_titles(path))
    return roots


def flatten(titles: Iterable[Ck2Title]) -> list[Ck2Title]:
    """Depth-first list of a title hierarchy, parents before children."""
    flat: list[Ck2Title] = []
    stack = list(reversed(list(titles)))
    while stack:
        title = stack.pop()
        flat.append(title)
        stack.extend(reversed(title.children))
    return flat


def index(titles: Iterable[Ck2Title]) -> dict[str, Ck2Title]:
    """``title id -> title`` over the whole tree."""
    return {t.id: t for t in flatten(titles)}


# ---------------------------------------------------------------- provinces


@dataclass
class Ck2ProvinceHistory:
    """One ``history/provinces/<id> - <Name>.txt`` file."""

    id: int
    file: str = ""
    title: str | None = None
    culture: str | None = None
    religion: str | None = None
    terrain: str | None = None
    max_settlements: int | None = None
    #: barony id -> the holding it starts with (``None`` = declared, not built).
    holdings: dict[str, str] = field(default_factory=dict)
    #: ``(date, barony id, holding)`` in file order.
    holding_changes: list[tuple[Date, str, str]] = field(default_factory=list)
    #: ``(date, key, value)`` for culture / religion / anything else dated.
    dated: list[tuple[Date, str, object]] = field(default_factory=list)
    leading_comments: list[str] = field(default_factory=list)

    def first_holding_date(self, barony: str) -> Date | None:
        """The date ``barony`` is first built, or ``None`` if built at file top."""
        if barony in self.holdings:
            return None
        for date, bid, holding in self.holding_changes:
            if bid == barony and holding not in ("none", "0"):
                return date
        return None


def _is_date_key(key: str) -> bool:
    try:
        Date.parse(key)
    except (ValueError, TypeError, AttributeError):
        return False
    return True


def read_province_history(province_id: int, path: Path) -> Ck2ProvinceHistory:
    """Read one CK2 province-history file."""
    document = parse_file(path)
    province = Ck2ProvinceHistory(id=province_id, file=path.name)
    for entry in document:
        if not isinstance(entry, Node):
            continue
        key, value = entry.key, entry.value
        if key == "title":
            province.title = str(value)
        elif key == "culture":
            province.culture = str(value)
        elif key == "religion":
            province.religion = str(value)
        elif key == "terrain":
            province.terrain = str(value)
        elif key == "max_settlements":
            try:
                province.max_settlements = int(value)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                pass
        elif key.startswith("b_") and not isinstance(value, Block):
            province.holdings[key] = str(value)
        elif _is_date_key(key) and isinstance(value, Block):
            date = Date.parse(key)
            for sub in value:
                if not isinstance(sub, Node):
                    continue
                if sub.key.startswith("b_") and not isinstance(sub.value, Block):
                    province.holding_changes.append((date, sub.key, str(sub.value)))
                else:
                    province.dated.append((date, sub.key, sub.value))
    return province


_PROVINCE_FILE_RE = "* - *.txt"


def read_province_histories(directory: Path) -> dict[int, Ck2ProvinceHistory]:
    """Read a CK2 ``history/provinces`` folder, keyed by province id."""
    out: dict[int, Ck2ProvinceHistory] = {}
    for path in sorted(directory.glob("*.txt")):
        head = path.name.split("-", 1)[0].strip()
        if not head.isdigit():
            continue
        out[int(head)] = read_province_history(int(head), path)
    return out


# ------------------------------------------------------------- title history


@dataclass
class Ck2TitleHistory:
    """One ``history/titles/<title>.txt`` file, dates in file order."""

    id: str
    file: str = ""
    #: ``(date, [nodes])``; a CK2 file may repeat a date, so this is a list.
    dated: list[tuple[Date, list[Node]]] = field(default_factory=list)
    #: keys CK2 wrote at the top level.  CK3 forbids them (`verified`: 0
    #: depth-1 keys across all 183 vanilla files) so the writer wraps them in
    #: an early date.
    toplevel: list[Node] = field(default_factory=list)
    leading_comments: list[str] = field(default_factory=list)

    def dates(self) -> Iterator[Date]:
        for date, _ in self.dated:
            yield date


def read_title_history(path: Path) -> Ck2TitleHistory:
    """Read one CK2 title-history file.  The title id is the file stem."""
    document = parse_file(path)
    history = Ck2TitleHistory(id=path.stem, file=path.name)
    for entry in document:
        if not isinstance(entry, Node):
            continue
        if _is_date_key(entry.key) and isinstance(entry.value, Block):
            nodes = [e for e in entry.value if isinstance(e, Node)]
            history.dated.append((Date.parse(entry.key), nodes))
        else:
            history.toplevel.append(entry)
    return history


def read_title_histories(directory: Path) -> dict[str, Ck2TitleHistory]:
    """Read a CK2 ``history/titles`` folder, keyed by title id."""
    out: dict[str, Ck2TitleHistory] = {}
    for path in sorted(directory.glob("*.txt")):
        if not path.stem.startswith(TITLE_PREFIXES):
            continue
        out[path.stem] = read_title_history(path)
    return out


# ---------------------------------------------------------------- bookmarks


@dataclass
class Ck2BookmarkCharacter:
    """One ``selectable_character = { … }`` of a CK2 bookmark."""

    ck2_id: str
    name: str | None = None
    title: str | None = None
    title_name: str | None = None
    age: int | None = None
    dynasty: str | None = None
    culture: str | None = None
    religion: str | None = None
    government: str | None = None
    comment: str | None = None


@dataclass
class Ck2Bookmark:
    """One ``bm_*`` block of CK2 ``common/bookmarks``."""

    id: str
    date: Date | None = None
    name: str | None = None
    desc: str | None = None
    era: bool = False
    picture: str | None = None
    characters: list[Ck2BookmarkCharacter] = field(default_factory=list)


def _bookmark_character(block: Block) -> Ck2BookmarkCharacter:
    inner = block.get("character")
    char = Ck2BookmarkCharacter(ck2_id=str(block.get("id", "")))
    char.name = _opt_str(block.get("name"))
    char.title = _opt_str(block.get("title"))
    char.title_name = _opt_str(block.get("title_name"))
    age = block.get("age")
    if isinstance(age, int):
        char.age = age
    if isinstance(inner, Block):
        char.dynasty = _opt_str(inner.get("dynasty"))
        char.culture = _opt_str(inner.get("culture"))
        char.religion = _opt_str(inner.get("religion"))
        char.government = _opt_str(inner.get("government"))
    return char


def _opt_str(value: object) -> str | None:
    return None if value is None else str(value)


def read_bookmarks(path: Path) -> list[Ck2Bookmark]:
    """Read CK2 ``common/bookmarks/*.txt``."""
    document = parse_file(path)
    out: list[Ck2Bookmark] = []
    for node in document.nodes():
        if not isinstance(node.value, Block):
            continue
        bookmark = Ck2Bookmark(id=node.key)
        date = node.value.get("date")
        if isinstance(date, Date):
            bookmark.date = date
        bookmark.name = _opt_str(node.value.get("name"))
        bookmark.desc = _opt_str(node.value.get("desc"))
        bookmark.era = bool(node.value.get("era", False))
        bookmark.picture = _opt_str(node.value.get("picture"))
        for entry in node.value:
            if (
                isinstance(entry, Node)
                and entry.key == "selectable_character"
                and isinstance(entry.value, Block)
            ):
                char = _bookmark_character(entry.value)
                char.comment = entry.trailing_comment
                bookmark.characters.append(char)
        out.append(bookmark)
    return out


def read_bookmarks_dir(directory: Path) -> list[Ck2Bookmark]:
    out: list[Ck2Bookmark] = []
    for path in sorted(directory.glob("*.txt")):
        out.extend(read_bookmarks(path))
    return out


# ----------------------------------------------------------------- cultures


def read_culture_groups(directory: Path) -> dict[str, list[str]]:
    """``culture group id -> [culture ids]`` from CK2 ``common/cultures``.

    Needed because a CK2 cultural-name override may be keyed by a culture
    *group* (``dwarf_group = Hollowbold``) while CK3 ``cultural_names`` is keyed
    by name list, i.e. by culture: a group key has to be expanded to its
    members.
    """
    groups: dict[str, list[str]] = {}
    for path in sorted(directory.glob("*.txt")):
        document = parse_file(path)
        for node in document.nodes():
            if not isinstance(node.value, Block):
                continue
            members = [
                sub.key
                for sub in node.value.nodes()
                if isinstance(sub.value, Block)
                and sub.key not in _CULTURE_GROUP_KEYWORDS
            ]
            groups.setdefault(node.key, []).extend(members)
    return groups


def culture_of_group(groups: dict[str, list[str]]) -> dict[str, str]:
    """``culture id -> its group id``."""
    return {c: g for g, members in groups.items() for c in members}


# ---------------------------------------------------------------- republics


def republic_titles(path: Path) -> set[str]:
    """Title ids declared in CK2 ``common/landed_titles/republics.txt``.

    CK2 stores no government on a character; a merchant republic is a title
    that lives in this file (`verified`: every Faerun republic title is
    declared there and nowhere else).  That makes the file the government
    derivation's republic input — see :mod:`ck2ck3.titles.tables`.
    """
    if not path.exists():
        return set()
    return {t.id for t in flatten(read_landed_titles(path))}


# --------------------------------------------------------------- characters


@dataclass
class Ck2CharacterStub:
    """The three character facts this lane needs; the rest is another lane's.

    Holder integrity (a ``holder`` that names no character is a hard CK3
    error) needs the id set and the birth date; the bookmark writer needs the
    gender because CK3 ``character = { type = male|female }`` is mandatory and
    CK2 states it on the character, not on the bookmark.
    """

    id: str
    birth: Date | None = None
    death: Date | None = None
    female: bool = False
    name: str | None = None


def read_character_index(directory: Path) -> dict[str, Ck2CharacterStub]:
    """``CK2 character id -> stub`` over a whole ``history/characters`` folder."""
    out: dict[str, Ck2CharacterStub] = {}
    for path in sorted(directory.glob("*.txt")):
        document = parse_file(path)
        for node in document.nodes():
            if not isinstance(node.value, Block):
                continue
            stub = Ck2CharacterStub(id=str(node.key))
            stub.name = _opt_str(node.value.get("name"))
            stub.female = bool(node.value.get("female", False))
            for sub in node.value.nodes():
                if not isinstance(sub.value, Block):
                    continue
                try:
                    date = Date.parse(sub.key)
                except (ValueError, TypeError, AttributeError):
                    continue
                if "birth" in sub.value and stub.birth is None:
                    stub.birth = date
                if "death" in sub.value and stub.death is None:
                    stub.death = date
            out[stub.id] = stub
    return out
