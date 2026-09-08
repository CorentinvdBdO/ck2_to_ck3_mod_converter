"""``common/bookmarks`` from CK2 ``common/bookmarks``.

CK2 and CK3 bookmarks are close in shape but not in content: CK2's
``selectable_character`` nests the character's own data (dynasty, culture,
religion, government) inside an ``id``/``age``/``title`` wrapper, while CK3's
``character = { }`` is flat, wants a **birth date** rather than an age, a
``type = male|female`` (which CK2 keeps on the character, not the bookmark)
and a ``group`` that must name a declared bookmark group.

`verified` CK3 1.19 grammar (``common/bookmarks/bookmarks/_bookmarks.info``
plus ``00_bookmarks.txt``): a bookmark needs ``start_date`` and at least one
``character``; all 19 vanilla bookmarks also set ``is_playable`` and ``group``,
and all 110 vanilla bookmark characters set ``name``, ``title``,
``government``, ``religion``, ``difficulty``, ``position = { x y }`` and
``dynasty_splendor_level``.  ``default_start_date`` lives only in
``common/bookmarks/groups`` (`verified`: it is not in ``common/defines``).

Vanilla's own bookmark, group and challenge-character files name vanilla
titles and characters, so this step also writes an **empty file at each of
their three paths** to shadow them by filename — the Elder Kings 2 / Godherja
pattern, which needs no ``replace_path`` (``docs/output_bootstrap.md`` fact
0.2).

``common/bookmark_portraits`` **cannot** stay empty, which corrects
``docs/mapping_world.md`` gotcha 8: ck3-tiger reports
``fatal(crash): bookmark portrait for <name> not found in
common/bookmark_portraits`` — "This causes a crash in CK3 1.13" — for every
bookmark character without a file there.  The real files are engine-generated
(``dump_bookmark_portraits``), so this step writes a minimal placeholder per
character, named after the character's ``name`` value the way vanilla names
its 332 files.
"""

from __future__ import annotations

import zlib
from collections.abc import Mapping
from dataclasses import dataclass, field

from ..pdx import Date
from .ck2read import Ck2Bookmark, Ck2CharacterStub
from .text import Lines

#: ``common/bookmarks`` script files carry a UTF-8 BOM in vanilla and
#: ck3-tiger requires it (``warning(encoding): Expected UTF-8 BOM encoding``).
#: Written as a character; ``ctx.write_text`` encodes the file as UTF-8.
BOM = "\ufeff"

#: CK3 difficulty ids, `verified` in ``00_bookmarks.txt``.  CK2 has no
#: difficulty on a bookmark character, so every converted one is MEDIUM.
DIFFICULTY = "BOOKMARK_CHARACTER_DIFFICULTY_MEDIUM"

#: CK3 needs an animation id; ``personality_bold`` exists in vanilla and is
#: what Atlantis uses for its placeholder bookmark character.
ANIMATION = "personality_bold"

GROUP_HEADER = (
    "# Bookmark groups. `default_start_date` exists ONLY here in CK3",
    "# (verified: it is not in common/defines).",
)

BOOKMARK_HEADER = (
    "# Bookmarks converted from CK2 common/bookmarks.",
    "# CK2 `age` becomes a birth date (start date minus age); CK2 `era = yes`",
    "# becomes is_playable + a weight, since CK3 has no era screen.",
    "# common/bookmark_portraits is left empty on purpose: those files are",
    "# engine-generated (dump_bookmark_portraits).",
)

SHADOW_NOTE = (
    "# Intentionally empty: this file shadows the vanilla file of the same name",
    "# so vanilla bookmarks - which name vanilla titles and characters that do",
    "# not exist on this map - do not load. Override-by-filename needs no",
    "# replace_path (docs/output_bootstrap.md fact 0.2).",
)

#: A bookmark character with no ``common/bookmark_portraits`` entry crashes
#: the game (ck3-tiger ``fatal(crash)``).  The real file is a gene dump; the
#: placeholder keeps the block key, the type and an empty ``genes`` block, so
#: the portrait is derived from the character instead.
PORTRAIT_NOTE = (
    "# Placeholder, NOT a dump_bookmark_portraits output: a bookmark character",
    "# with no entry here crashes CK3 (ck3-tiger fatal(crash)). Replace this",
    "# file with a real dump once the mod can be started in game.",
)

#: vanilla files this step shadows, relative to the output mod.
SHADOWED = (
    "common/bookmarks/bookmarks/00_bookmarks.txt",
    "common/bookmarks/groups/00_bookmark_groups.txt",
    "common/bookmarks/challenge_characters/00_challenge_characters.txt",
)


@dataclass
class BookmarkResult:
    files: dict[str, str] = field(default_factory=dict)
    loc: dict[str, str] = field(default_factory=dict)
    #: ``(ck2 loc key, ck3 loc key)`` rows for mappings/loc_key_renames_titles.csv
    renames: list[tuple[str, str]] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def _birth(date: Date, age: int | None, stub: Ck2CharacterStub | None) -> Date:
    """CK3 wants a birth date; CK2 gives an age (often a graphical one)."""
    if stub is not None and stub.birth is not None:
        return stub.birth
    years = age if age and age > 0 else 30
    return Date(date.year - years, date.month, date.day)


def render(
    bookmarks: list[Ck2Bookmark],
    *,
    characters: Mapping[str, Ck2CharacterStub],
    live_titles: frozenset[str],
    default_date: str,
    government_map: Mapping[str, str] | None = None,
    prefix: str = "fae",
    group: str | None = None,
) -> BookmarkResult:
    """Render the bookmark, group and shadow files."""
    result = BookmarkResult()
    group = group or f"bm_group_{prefix}"

    groups = Lines()
    for line in GROUP_HEADER:
        groups.raw(line)
    groups.raw("")
    groups.line(0, f"{group} = {{")
    groups.line(1, f"default_start_date = {default_date}")
    groups.line(0, "}")
    result.files[f"common/bookmarks/groups/{prefix}_bookmark_groups.txt"] = groups.text()
    result.loc[group] = "Faerun"

    out = Lines()
    for line in BOOKMARK_HEADER:
        out.raw(line)
    out.raw(f"# default bookmark date from the CLI config: {default_date}")
    out.raw("")
    written = 0
    chars = 0
    for bookmark in bookmarks:
        if bookmark.date is None:
            result.warnings.append(f"{bookmark.id}: CK2 bookmark has no date")
            continue
        playable = [
            c
            for c in bookmark.characters
            if c.title in live_titles and c.ck2_id in characters
        ]
        for candidate in bookmark.characters:
            if candidate in playable:
                continue
            reason = (
                "title is not live"
                if candidate.title not in live_titles
                else "character is not in CK2 history/characters"
            )
            out.comment(
                0,
                f"{bookmark.id}: dropped selectable_character {candidate.ck2_id} "
                f"({candidate.title}) - {reason}",
            )
            result.warnings.append(
                f"{bookmark.id}: character {candidate.ck2_id} dropped, {reason}"
            )
        if not playable:
            out.comment(
                0,
                f"{bookmark.id}: no convertible character, bookmark not emitted",
            )
            continue
        stamp = f"{bookmark.date.year}.{bookmark.date.month}.{bookmark.date.day}"
        # CK3 uses the bookmark's own key as its localisation key
        # (common/bookmarks/groups/_bookmark_groups.info); CK2 named a separate
        # loc key, so the CK2 -> CK3 key move is a row for the loc lane.
        if bookmark.name:
            result.renames.append((bookmark.name.strip('"'), bookmark.id))
        if bookmark.desc:
            result.renames.append((bookmark.desc.strip('"'), f"{bookmark.id}_desc"))
        out.line(0, f"{bookmark.id} = {{")
        out.line(1, f"start_date = {stamp}")
        out.line(1, "is_playable = yes")
        out.line(1, f"group = {group}")
        out.line(1, "weight = {")
        out.line(2, f"value = {100 if stamp == default_date else (10 if bookmark.era else 0)}")
        out.line(1, "}")
        for character in playable:
            stub = characters.get(character.ck2_id)
            birth = _birth(bookmark.date, character.age, stub)
            out.line(1, "character = {")
            name_key = f"bookmark_{prefix}_{character.ck2_id}"
            out.line(2, f'name = "{name_key}"')
            result.loc[name_key] = (
                (stub.name if stub and stub.name else character.name) or name_key
            )
            result.loc.setdefault(f"{name_key}_desc", result.loc[name_key])
            if character.dynasty:
                out.line(2, f"dynasty = {prefix}_dyn_{character.dynasty}")
            out.line(2, "dynasty_splendor_level = 1")
            out.line(2, f"type = {'female' if stub and stub.female else 'male'}")
            out.line(2, f"birth = {birth.year}.{birth.month}.{birth.day}")
            out.line(2, f"title = {character.title}")
            ck2_gov = (character.government or "").strip('"')
            ck3_gov = (government_map or {}).get(ck2_gov)
            if ck2_gov and not ck3_gov:
                result.warnings.append(
                    f"{bookmark.id}: CK2 government {ck2_gov} has no CK3 target"
                )
            out.line(2, f"government = {ck3_gov or 'feudal_government'}")
            if ck2_gov and ck3_gov != ck2_gov:
                out.comment(2, f"CK2 government = {ck2_gov}")
            if character.culture:
                out.line(2, f"culture = {character.culture}")
            if character.religion:
                out.line(2, f"religion = {character.religion}")
            out.line(2, f'difficulty = "{DIFFICULTY}"')
            out.line(2, f"history_id = {prefix}_{character.ck2_id}")
            out.line(2, "position = { 0 0 }")
            out.line(2, f"animation = {ANIMATION}")
            out.line(1, "}")
            portrait = Lines()
            for line in PORTRAIT_NOTE:
                portrait.raw(line)
            portrait.line(0, f"{name_key}={{")
            portrait.line(1, f"type={'female' if stub and stub.female else 'male'}")
            portrait.line(1, f"id={chars + 1}")
            # deterministic: python hash() is salted per process
            portrait.line(1, f"random_seed={zlib.crc32(name_key.encode()) % 2147483647}")
            portrait.line(1, "age=0.500000")
            portrait.line(1, "genes={")
            portrait.line(1, "}")
            portrait.line(0, "}")
            result.files[f"common/bookmark_portraits/{name_key}.txt"] = portrait.text()
            chars += 1
        out.line(0, "}")
        out.blank()
        written += 1
    result.files[f"common/bookmarks/bookmarks/{prefix}_bookmarks.txt"] = out.text()

    shadow = "\n".join(SHADOW_NOTE) + "\n"
    for rel in SHADOWED:
        result.files[rel] = shadow
    result.counts = {"bookmarks": written, "bookmark_characters": chars}
    return result
