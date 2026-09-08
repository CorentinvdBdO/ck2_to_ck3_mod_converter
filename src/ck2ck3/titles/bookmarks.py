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

import math
import zlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from ..ids import fae_id
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

#: CK3 animation ids for bookmark characters.  All eight are `verified` twice:
#: they are declared in ``gfx/portraits/portrait_animations/animations.txt``
#: (lines 3135, 4011, 3938, 2968, 3304, 3621, 3389, 3768) and used by vanilla's
#: own bookmark characters in ``common/bookmarks/bookmarks/00_bookmarks.txt``
#: (lines 37, 608, 738, 169, 50, 332, 1414, 188).  They are the eight most
#: frequent of the 55 animation ids that file uses
#: (``scripts/survey_vanilla_bookmark_positions.py``).  The pick is a
#: deterministic ``crc32`` of the character's loc key, the same pattern the
#: portrait ``random_seed`` below uses - ``hash()`` is salted per process.
ANIMATIONS: tuple[str, ...] = (
    "personality_bold",
    "personality_cynical",
    "personality_zealous",
    "personality_honorable",
    "personality_greedy",
    "personality_rational",
    "personality_content",
    "personality_compassionate",
)

#: Kept for callers that want the single vanilla default.
ANIMATION = ANIMATIONS[0]

#: The bookmark screen's usable rectangle, ``(x0, y0, x1, y1)``, **measured**
#: from CK3 1.19 vanilla rather than guessed: the 93 displayed
#: ``position = { x y }`` values of
#: ``common/bookmarks/bookmarks/00_bookmarks.txt`` span x 290..1220 and
#: y 150..820 (``scripts/survey_vanilla_bookmark_positions.py``).  The 18
#: ``display = no`` animation-test characters, all stacked on ``{ 1130 480 }``,
#: are excluded - they are never drawn.
CANVAS: tuple[float, float, float, float] = (290.0, 150.0, 1220.0, 820.0)

#: Geographic positions are projected into the canvas inset by this margin, so
#: the repulsion pass below has somewhere to push an edge character to without
#: immediately clamping it back.
CANVAS_MARGIN = 40.0

#: Minimum on-screen distance between two characters of the same bookmark.
#: Vanilla's smallest displayed pairwise distance is 251.6 px, over bookmarks
#: of at most 6 characters (same survey).  Half of that is used here: our
#: capitals are projected from real geography, so neighbouring rulers start out
#: much closer than a hand-placed vanilla screen and a 250 px floor would erase
#: the geography entirely.
MIN_DISTANCE = 120.0

#: Fixed iteration count - no convergence test, no randomness, so two runs on
#: the same input are byte-identical.
REPULSION_ITERATIONS = 60

#: Index into the 7 coordinate pairs of a CK2 ``map/positions.txt`` entry.
#: Slot 0 is the city slot (``ck2ck3.map.config`` ``city_slot``, docs/map_scale.md
#: 2b: inside its own province 91.9 % of the time).
CK2_CITY_SLOT = 0

GROUP_HEADER = (
    "# Bookmark groups. `default_start_date` exists ONLY here in CK3",
    "# (verified: it is not in common/defines).",
)

BOOKMARK_HEADER = (
    "# Bookmarks converted from CK2 common/bookmarks.",
    "# CK2 `age` becomes a birth date (start date minus age); CK2 `era = yes`",
    "# becomes is_playable + a weight, since CK3 has no era screen.",
    "# `position` is the character's CK2 capital province coordinate from",
    "# map/positions.txt, normalised over every live county and scaled into",
    "# the measured vanilla canvas x 290-1220 / y 150-820, y flipped, then",
    "# pushed apart to a 120 px floor. See docs/step_titles.md (Bookmarks).",
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


def animation_for(name_key: str) -> str:
    """Deterministic animation id for a bookmark character."""
    return ANIMATIONS[zlib.crc32(name_key.encode()) % len(ANIMATIONS)]


def county_positions(
    *,
    ck2_of_county: Mapping[str, int],
    own_county: Mapping[str, str],
    live_titles: frozenset[str] | set[str],
    positions: Mapping[int, Sequence[tuple[float, float]]],
    city_slot: int = CK2_CITY_SLOT,
) -> dict[str, tuple[float, float]]:
    """``CK2 title id -> its capital's CK2 map coordinate`` (y bottom-up).

    A county maps to its own CK2 province coordinate; every higher title maps
    to the coordinate of the live county ``model.own_counties`` picked for it,
    so a duchy/kingdom/empire sits on its capital.  Only **live** counties are
    included, which is also what makes the bounding box stable: it does not
    move when a bookmark gains or loses a character.

    y stays in Paradox bottom-up space (`verified`: Waterdeep province 1
    y=2838, Amphail province 2 y=2893, and Amphail is north of Waterdeep);
    :func:`place_characters` does the flip when it projects to screen space.
    """
    out: dict[str, tuple[float, float]] = {}
    for county, pid in ck2_of_county.items():
        if county not in live_titles:
            continue
        slots = positions.get(pid)
        if not slots or len(slots) <= city_slot:
            continue
        out[county] = (float(slots[city_slot][0]), float(slots[city_slot][1]))
    for title, county in own_county.items():
        if title not in out and county in out:
            out[title] = out[county]
    return out


def bounding_box(
    source: Mapping[str, tuple[float, float]],
) -> tuple[float, float, float, float] | None:
    """``(min x, min y, max x, max y)`` over every coordinate, or None."""
    if not source:
        return None
    xs = [p[0] for p in source.values()]
    ys = [p[1] for p in source.values()]
    return (min(xs), min(ys), max(xs), max(ys))


def effective_min_distance(
    count: int,
    *,
    canvas: tuple[float, float, float, float] = CANVAS,
    margin: float = CANVAS_MARGIN,
    min_distance: float = MIN_DISTANCE,
) -> float:
    """``min_distance``, lowered when that many characters cannot fit.

    Faerûn's fullest bookmark holds 6 characters, so this never bites today;
    it keeps the guarantee true for a source mod with a crowded bookmark
    instead of letting the repulsion pass silently fail.
    """
    if count < 2:
        return min_distance
    x0, y0, x1, y1 = canvas
    area = max(x1 - x0 - 2 * margin, 1.0) * max(y1 - y0 - 2 * margin, 1.0)
    return min(min_distance, 0.8 * math.sqrt(area / count))


def _grid_point(
    index: int,
    count: int,
    canvas: tuple[float, float, float, float],
    margin: float,
) -> tuple[float, float]:
    """Evenly spread deterministic slot ``index`` of ``count`` in the canvas."""
    x0, y0, x1, y1 = canvas
    cols = max(1, math.ceil(math.sqrt(count)))
    rows = max(1, math.ceil(count / cols))
    col, row = index % cols, index // cols
    left, top = x0 + margin, y0 + margin
    width, height = (x1 - margin) - left, (y1 - margin) - top
    return (
        left + width * (col + 0.5) / cols,
        top + height * (row + 0.5) / rows,
    )


def place_characters(
    points: Sequence[tuple[float, float] | None],
    *,
    bbox: tuple[float, float, float, float] | None,
    canvas: tuple[float, float, float, float] = CANVAS,
    margin: float = CANVAS_MARGIN,
    min_distance: float = MIN_DISTANCE,
    iterations: int = REPULSION_ITERATIONS,
) -> list[tuple[int, int]]:
    """Screen positions for one bookmark's characters, in input order.

    ``points`` holds each character's CK2 map coordinate (y bottom-up) or
    ``None``.  A coordinate is normalised over ``bbox`` - the box of *all*
    live counties, not of this bookmark - so two bookmarks stay comparable,
    then scaled into ``canvas`` inset by ``margin``, with **y flipped**
    (Paradox y grows north, screen y grows down).  A ``None`` takes the next
    slot of an evenly spread grid, assigned after the geographic ones.

    Then a fixed number of repulsion passes pushes any pair closer than
    ``min_distance`` apart and clamps everything back inside the canvas.  No
    randomness and no convergence test: the output is a pure function of the
    input and byte-identical between runs.
    """
    x0, y0, x1, y1 = canvas
    left, top = x0 + margin, y0 + margin
    right, bottom = x1 - margin, y1 - margin

    placed: list[list[float]] = []
    fallback_total = sum(1 for p in points if p is None)
    fallback_seen = 0
    for point in points:
        if point is None or bbox is None:
            placed.append(list(_grid_point(fallback_seen, max(fallback_total, 1),
                                           canvas, margin)))
            fallback_seen += 1
            continue
        bx0, by0, bx1, by1 = bbox
        span_x = bx1 - bx0 or 1.0
        span_y = by1 - by0 or 1.0
        nx = min(max((point[0] - bx0) / span_x, 0.0), 1.0)
        ny = min(max((point[1] - by0) / span_y, 0.0), 1.0)
        # y flip: ny == 1 is the north edge of the CK2 map, which is the *top*
        # of the screen, i.e. the smallest screen y.
        placed.append([left + nx * (right - left), bottom - ny * (bottom - top)])

    floor = effective_min_distance(
        len(points), canvas=canvas, margin=margin, min_distance=min_distance
    )
    for _ in range(iterations):
        for i in range(len(placed)):
            for j in range(i + 1, len(placed)):
                dx = placed[j][0] - placed[i][0]
                dy = placed[j][1] - placed[i][1]
                dist = math.hypot(dx, dy)
                if dist >= floor:
                    continue
                if dist < 1e-9:
                    # exactly coincident: separate along a fixed direction
                    # derived from the pair's indices, never a random one.
                    angle = 2.0 * math.pi * ((i * 7 + j * 13) % 12) / 12.0
                    dx, dy, dist = math.cos(angle), math.sin(angle), 1.0
                push = (floor - dist) / 2.0 + 0.5
                ux, uy = dx / dist, dy / dist
                placed[i][0] -= ux * push
                placed[i][1] -= uy * push
                placed[j][0] += ux * push
                placed[j][1] += uy * push
        for point_ in placed:
            point_[0] = min(max(point_[0], x0), x1)
            point_[1] = min(max(point_[1], y0), y1)
    return [(int(round(px)), int(round(py))) for px, py in placed]


def render(
    bookmarks: list[Ck2Bookmark],
    *,
    characters: Mapping[str, Ck2CharacterStub],
    live_titles: frozenset[str],
    default_date: str,
    government_map: Mapping[str, str] | None = None,
    prefix: str = "fae",
    group: str | None = None,
    title_positions: Mapping[str, tuple[float, float]] | None = None,
) -> BookmarkResult:
    """Render the bookmark, group and shadow files.

    ``title_positions`` maps a CK2 title id to its capital's CK2 map
    coordinate (y bottom-up), as :func:`county_positions` builds it.  It is
    an argument rather than something read from a ``Context`` so ``render``
    stays a pure function of its inputs; the empty default sends every
    character to the fallback grid.
    """
    result = BookmarkResult()
    group = group or f"bm_group_{prefix}"
    title_positions = title_positions or {}
    # the box of every live county, not of the bookmark's own characters, so
    # the same capital lands on the same pixel in every bookmark
    bbox = bounding_box(title_positions)
    positioned = 0
    gridded = 0

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
    marked_default = False
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
        if stamp == default_date and not marked_default:
            # `-test` (and the scripted-test harness) starts the bookmark with
            # test_default = yes (vanilla: bm_1066_rags_to_riches). Without one
            # the game state is generated at date -1.1.1: no holder ever
            # applies and every bookmark character is unborn (verified
            # 2026-09-08, first In Game run: 46 of 46 holder tests failed).
            out.line(1, "test_default = yes")
            marked_default = True
        out.line(1, f"group = {group}")
        out.line(1, "weight = {")
        out.line(2, f"value = {100 if stamp == default_date else (10 if bookmark.era else 0)}")
        out.line(1, "}")
        spots = place_characters(
            [title_positions.get(c.title) for c in playable], bbox=bbox
        )
        for character, spot in zip(playable, spots):
            if title_positions.get(character.title) is None or bbox is None:
                gridded += 1
                result.warnings.append(
                    f"{bookmark.id}: character {character.ck2_id} title "
                    f"{character.title} has no CK2 province coordinate, "
                    "placed on the fallback grid"
                )
            else:
                positioned += 1
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
                # `fae_<ck2 id>`, NOT `fae_dyn_<ck2 id>`: the `dynasties`
                # step owns the id (ck2ck3.ids.fae_id) and mints no `dyn_`
                # infix. The mismatch was 80 ck3-tiger
                # `error(missing-item): dynasty fae_dyn_N not defined`
                # (`verified` 2026-09-08).
                out.line(2, f"dynasty = {fae_id(character.dynasty, prefix)}")
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
            out.line(2, f"position = {{ {spot[0]} {spot[1]} }}")
            out.line(2, f"animation = {animation_for(name_key)}")
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
    result.counts = {
        "bookmarks": written,
        "bookmark_characters": chars,
        "positioned_from_map": positioned,
        "positioned_on_grid": gridded,
    }
    return result
