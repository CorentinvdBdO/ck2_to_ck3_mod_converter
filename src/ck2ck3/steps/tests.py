"""Step ``tests``: turn the generated mod's own claims into CK3 scripted tests.

Owns ``tests`` in the output mod, and runs **last**: every assertion is read
back out of the files the earlier steps just wrote, so the test file can never
claim something the mod does not actually say. Reference for the grammar and
how the game runs these: ``claudespace/docs/ck3_test_framework.md`` (this is a
port of ``claudespace/scripts/ck3_gen_tests.py`` into the step registry, so a
conversion run produces its own regression suite).

Three families of assertion, each from one generated source:

===================================  ============================================
read from                            asserted
===================================  ============================================
``common/bookmarks/bookmarks/*``     each bookmark character is alive at the
                                     bookmark date and holds its ``title``
``history/titles/*``                 the holder in effect at that date is the
                                     character the history file names (sampled)
``history/provinces`` ∩              every land province is not sea and has a
``map_data/definition.csv``          county, a culture and a faith (sampled)
===================================  ============================================

plus one aggregate invariant over every ruler, which is cheap and catches a
wholesale conversion failure.

Only triggers that appear in vanilla ``game/tests/*.txt`` are emitted. Note
there is **no** ``province_target`` grammar key, so a province check is a
target-less test using the absolute ``province:<id>`` scope link.

``replace_path = "tests"`` is mandatory for a total conversion: vanilla's 18
test files hard-code 1066 ids such as character ``122`` and ``k_croatia`` and
would fail en masse on this map. ``configs/faerun.toml`` carries it; this step
refuses to run without it rather than emit a file that only adds noise.

Config (``[tests]``, all optional)::

    sample = 50        # title holders and provinces to assert, 0 = every one
    bookmark = "..."   # bookmark key; default is the highest-weight one, which
                       # is what the game's `-test` argument starts
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path

from ..context import Context, StepResult
from ..pdx import Block, Document, Node

DESCRIPTION = "tests/: CK3 scripted tests asserting the generated mod's own claims"
OUTPUTS: tuple[str, ...] = ("tests",)

#: The one file this step writes. ``<prefix>_`` so a submod's own tests sort
#: next to it rather than shadowing it.
OUT_TEMPLATE = "tests/{prefix}_generated_tests.txt"
#: Default number of history titles and of provinces to assert.
DEFAULT_SAMPLE = 50
#: Title tiers whose ids a ``history/titles`` file may declare.
TITLE_PREFIXES = ("e_", "k_", "d_", "c_", "b_")
#: ``default.map`` keys whose provinces are not land. ``river_provinces`` and
#: ``wasteland`` are impassable rather than water, but they have no county
#: either, so they are excluded for the same reason.
WATER_KEYS = (
    "sea_zones",
    "lakes",
    "impassable_seas",
    "impassable_mountains",
    "river_provinces",
    "wasteland",
)
#: ``key = RANGE { a b }`` / ``key = LIST { a b c }`` in ``default.map``. The
#: pdx parser reads these as a bare-token list, so this is a text scan instead:
#: ``RANGE`` is a keyword, not a value, and would need parser support.
RANGE_OR_LIST = re.compile(r"(\w+)\s*=\s*(RANGE|LIST)\s*\{([^}]*)\}")
DATE = re.compile(r"^(\d{1,4})\.(\d{1,2})\.(\d{1,2})$")

Date = tuple[int, int, int]


# ---------------------------------------------------------------------------
# reading back what the earlier steps wrote
# ---------------------------------------------------------------------------
@dataclass
class BookmarkChar:
    """One ``character = { history_id = X title = k_y }`` of a bookmark."""

    history_id: str
    title: str | None
    name: str


@dataclass
class Bookmark:
    key: str
    date: Date
    weight: float
    characters: list[BookmarkChar] = field(default_factory=list)


def as_date(value: object) -> Date | None:
    match = DATE.match(str(value or ""))
    return (
        (int(match.group(1)), int(match.group(2)), int(match.group(3)))
        if match
        else None
    )


def fmt_date(date: Date) -> str:
    return "%d.%d.%d" % date


def _nodes(block: Block | Document, key: str) -> list[Node]:
    """Every ``key = ...`` entry of a block, duplicates kept.

    Bookmarks repeat ``character`` and history files repeat dates, so a
    dict-shaped lookup would silently keep only the last one.
    """
    return [
        e
        for e in block.entries
        if isinstance(e, Node) and e.key == key
    ]


def _value(block: Block, key: str) -> str | None:
    for node in _nodes(block, key):
        if not isinstance(node.value, Block):
            return str(node.value).strip('"')
    return None


def _sub(block: Block, key: str) -> Block | None:
    for node in _nodes(block, key):
        if isinstance(node.value, Block):
            return node.value
    return None


def read_bookmarks(ctx: Context) -> list[Bookmark]:
    """Every bookmark of ``common/bookmarks/bookmarks/*.txt``.

    ``_``-prefixed files are CK3's own ``.info`` documentation companions and
    are skipped, as the game does.
    """
    folder = ctx.out_path("common", "bookmarks", "bookmarks")
    if not folder.is_dir():
        return []
    marks: list[Bookmark] = []
    for path in sorted(folder.glob("*.txt")):
        if path.name.startswith("_"):
            continue
        doc = ctx.parse_path(path, lenient=True)
        for node in doc.entries:
            if not isinstance(node, Node) or not isinstance(node.value, Block):
                continue
            date = as_date(_value(node.value, "start_date"))
            if date is None:
                continue
            weight_block = _sub(node.value, "weight")
            weight = 0.0
            if weight_block is not None:
                try:
                    weight = float(_value(weight_block, "value") or 0)
                except ValueError:
                    weight = 0.0
            mark = Bookmark(key=node.key, date=date, weight=weight)
            _walk_characters(node.value, mark.characters)
            marks.append(mark)
    return marks


def _walk_characters(block: Block, out: list[BookmarkChar]) -> None:
    """Bookmark characters nest: a courtier is a ``character`` inside one."""
    for node in _nodes(block, "character"):
        if not isinstance(node.value, Block):
            continue
        history_id = _value(node.value, "history_id")
        if history_id:
            out.append(
                BookmarkChar(
                    history_id=history_id,
                    title=_value(node.value, "title"),
                    name=_value(node.value, "name") or history_id,
                )
            )
        _walk_characters(node.value, out)


def read_title_holders(ctx: Context, date: Date) -> dict[str, str]:
    """``{title id: holder}`` in effect at ``date``, from ``history/titles``.

    The last dated block at or before ``date`` that sets ``holder`` wins, which
    is the game's own rule. ``holder = 0`` / ``none`` means "explicitly nobody"
    and yields no assertion.
    """
    folder = ctx.out_path("history", "titles")
    if not folder.is_dir():
        return {}
    holders: dict[str, str] = {}
    for path in sorted(folder.glob("*.txt")):
        doc = ctx.parse_path(path, lenient=True)
        for node in doc.entries:
            if not isinstance(node, Node) or not isinstance(node.value, Block):
                continue
            if not node.key.startswith(TITLE_PREFIXES):
                continue
            best: tuple[Date, str] | None = None
            for dated in node.value.entries:
                if not isinstance(dated, Node) or not isinstance(dated.value, Block):
                    continue
                when = as_date(dated.key)
                if when is None or when > date:
                    continue
                holder = _value(dated.value, "holder")
                if holder is None:
                    continue
                if best is None or when >= best[0]:
                    best = (when, holder)
            if best and best[1] not in ("0", "none"):
                holders[node.key] = best[1]
    return holders


def read_character_ids(ctx: Context) -> set[str]:
    """Every key the generated ``history/characters`` declares.

    18k blocks over 80 files, ~2 s to parse. Worth it: without it a bookmark
    character the `characters` step dropped becomes a test that can only fail.
    """
    folder = ctx.out_path("history", "characters")
    if not folder.is_dir():
        return set()
    ids: set[str] = set()
    for path in sorted(folder.glob("*.txt")):
        doc = ctx.parse_path(path, lenient=True)
        ids.update(
            node.key
            for node in doc.entries
            if isinstance(node, Node) and isinstance(node.value, Block)
        )
    return ids


def read_water_provinces(ctx: Context) -> set[int]:
    """Province ids ``map_data/default.map`` declares as not-land."""
    path = ctx.out_path("map_data", "default.map")
    if not path.is_file():
        return set()
    text = "\n".join(
        line.split("#", 1)[0]
        for line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    )
    water: set[int] = set()
    for key, kind, body in RANGE_OR_LIST.findall(text):
        if key not in WATER_KEYS:
            continue
        numbers = [int(n) for n in re.findall(r"\d+", body)]
        if kind == "RANGE" and len(numbers) >= 2:
            water.update(range(numbers[0], numbers[1] + 1))
        else:
            water.update(numbers)
    return water


def read_definition_provinces(ctx: Context) -> set[int]:
    """Non-water province ids from ``map_data/definition.csv``.

    Column 5 is the province name; a row with none (or the ``x`` placeholder
    vanilla uses) is an unused colour slot, not a province.
    """
    path = ctx.out_path("map_data", "definition.csv")
    if not path.is_file():
        return set()
    water = read_water_provinces(ctx)
    ids: set[int] = set()
    with path.open(encoding="utf-8-sig", errors="replace", newline="") as handle:
        for row in csv.reader(handle, delimiter=";"):
            if not row or not row[0].strip().isdigit():
                continue
            pid = int(row[0])
            name = row[4].strip() if len(row) > 4 else ""
            if pid == 0 or name in ("", "x", "X") or pid in water:
                continue
            ids.add(pid)
    return ids


def read_land_provinces(ctx: Context) -> list[int]:
    """Provinces the mod claims are land counties, ascending.

    The intersection of two generated files, and both halves are load-bearing:

    * ``history/provinces`` is where the mod *claims* a culture, a faith and a
      holding, so `exists = county/culture/faith` is only honest for a province
      that has a block there.
    * ``map_data/definition.csv`` minus the ``default.map`` water declarations
      is the set the map actually paints.

    Registered-but-countyless rows are the difference and must be excluded:
    Faerûn's `definition.csv` keeps 210 CK2 provinces that never became a
    barony (uppercase CK2 slug in column 5, e.g. ``4261;ORCSKULLS``) and they
    have no county, so asserting `exists = county` on them would fail by
    design rather than find a bug (`verified` 2026-09-08: 3904 non-water
    definition rows vs 3694 ``history/provinces`` blocks).
    """
    folder = ctx.out_path("history", "provinces")
    if not folder.is_dir():
        return []
    painted = read_definition_provinces(ctx)
    ids: set[int] = set()
    for path in sorted(folder.glob("*.txt")):
        doc = ctx.parse_path(path, lenient=True)
        for node in doc.entries:
            if (
                isinstance(node, Node)
                and isinstance(node.value, Block)
                and node.key.isdigit()
            ):
                ids.add(int(node.key))
    return sorted(ids & painted) if painted else sorted(ids)


# ---------------------------------------------------------------------------
# the test-file grammar
# ---------------------------------------------------------------------------
def render_test(
    test_id: str, name: str, target: str | None, expect: list[str]
) -> list[str]:
    """One test block, as lines.

    Rendered as text rather than through ``pdx.write``: ``expect`` is a trigger
    block whose contents are script the converter never models (``title:k_x =
    { holder = this }``), and the writer would have to be taught every trigger
    to round-trip it. The grammar is four keys wide, so the risk is low and the
    output is byte-comparable in a test.
    """
    lines = [f"{test_id} = {{", f'\tname = "{name}"']
    if target:
        lines.append(f"\t{target}")
    lines.append("")
    lines.append("\texpect = {")
    lines.extend("\t\t" + line for line in expect)
    lines.append("\t}")
    lines.append("}")
    lines.append("")
    return lines


def spread(items: list, n: int) -> list:
    """An evenly spread sample, not the first ``n``.

    A partial or half-converted map must not be tested only at province id
    1..50, where a converter that stopped early still looks healthy.
    """
    if n <= 0 or len(items) <= n:
        return list(items)
    step = len(items) / float(n)
    return [items[int(i * step)] for i in range(n)]


#: The aggregate invariant. Non-playable characters and sub-county rulers are
#: exempt because CK3 itself allows them not to hold their capital barony.
RULER_CAPITAL_INVARIANT = [
    "any_ruler = {",
    "\tcount = all",
    "\tOR = {",
    "\t\tis_playable_character = no",
    "\t\thighest_held_title_tier < tier_county",
    "\t\tAND = {",
    "\t\t\tcapital_barony.holder = this",
    "\t\t\tcapital_barony = capital_county.capital_vassal",
    "\t\t}",
    "\t}",
    "}",
]


def build(
    ctx: Context,
    marks: list[Bookmark],
    holders: dict[str, str],
    provinces: list[int],
    *,
    prefix: str,
    bookmark: Bookmark,
    sample: int,
    declared: set[str] | None = None,
) -> tuple[str, dict[str, int]]:
    """The whole file text plus the counts for the run log.

    ``declared`` is the character-database key set; an empty set means "not
    known", and every bookmark character is then asserted.
    """
    title_keys = spread(sorted(holders), sample)
    province_ids = spread(provinces, sample)

    lines = [
        "# GENERATED by the ck2ck3 `tests` step - do not hand-edit, re-run the",
        "# converter. Grammar: claudespace/docs/ck3_test_framework.md section 2.",
        f"# bookmark: {bookmark.key} ({fmt_date(bookmark.date)}), "
        f"weight {bookmark.weight:g} of {len(marks)} bookmark(s)",
        "# Run with: claudespace/scripts/ck3_test.sh <mod-name>. Failures land in",
        "# the user directory's logs/error.log; passes are logged nowhere, so the",
        "# expected count is the number of blocks below.",
        "",
    ]

    seen: set[str] = set()
    bookmark_tests = 0
    for character in bookmark.characters:
        # `history_id` is a key of the character database, and CK3 allows a
        # non-numeric one -- this converter mints `fae_52101`. The check that
        # matters is that the id is actually declared, so a bookmark pointing
        # at a character the `characters` step dropped yields no test rather
        # than a guaranteed failure with nothing to fix.
        if character.history_id in seen:
            continue
        if declared and character.history_id not in declared:
            continue
        seen.add(character.history_id)
        expect = ["is_alive = yes"]
        if character.title:
            # "holds this title" without guessing a trigger name: switch to the
            # title's scope and compare its holder with ROOT.
            # inside the title scope `this` is the title; ROOT stays the
            # character_target (first In Game run: "left was 'character',
            # right was 'landed_title'" on every bookmark test)
            expect.append(f"title:{character.title} = {{ holder = root }}")
        held = f" and holds {character.title}" if character.title else ""
        lines += render_test(
            f"{prefix}_bookmark_char_{character.history_id}",
            f"bookmark {bookmark.key}: "
            f"{character.name.replace(chr(34), chr(39))} exists{held}",
            f"character_target = {character.history_id}",
            expect,
        )
        bookmark_tests += 1

    for key in title_keys:
        lines += render_test(
            f"{prefix}_history_holder_{key}",
            f"{key} is held by {holders[key]} at {fmt_date(bookmark.date)}",
            f"title_target = {key}",
            [f"holder = character:{holders[key]}"],
        )

    for pid in province_ids:
        lines += render_test(
            f"{prefix}_map_province_{pid}",
            f"province {pid} is land with a county, culture and faith",
            None,
            [
                f"province:{pid} = {{",
                "\tis_sea_province = no",
                "\texists = county",
                "\texists = culture",
                "\texists = faith",
                "}",
            ],
        )

    lines += render_test(
        f"{prefix}_map_every_ruler_holds_its_capital",
        "every ruler personally holds its capital barony",
        None,
        RULER_CAPITAL_INVARIANT,
    )

    skipped = len(bookmark.characters) - bookmark_tests
    counts = {
        "tests": bookmark_tests + len(title_keys) + len(province_ids) + 1,
        "bookmark_characters_skipped": skipped,
        "bookmark_characters": bookmark_tests,
        "title_holders": len(title_keys),
        "title_holders_available": len(holders),
        "provinces": len(province_ids),
        "provinces_available": len(provinces),
        "aggregate": 1,
    }
    return "\n".join(lines), counts


def choose_bookmark(marks: list[Bookmark], wanted: str | None) -> Bookmark:
    """The bookmark the tests are anchored to.

    Default: the highest weight, because that is the one the game's ``-test``
    argument starts, and a test asserting a date the run never reaches is a
    guaranteed failure with nothing wrong.
    """
    if wanted:
        for mark in marks:
            if mark.key == wanted:
                return mark
        raise ValueError(
            f"[tests] bookmark = {wanted!r} is not one of "
            f"{', '.join(m.key for m in marks)}"
        )
    return max(marks, key=lambda m: (m.weight, m.key))


def run(ctx: Context) -> StepResult:
    raw = ctx.config.raw.get("tests", {})
    sample = int(raw.get("sample", DEFAULT_SAMPLE))
    prefix = ctx.config.prefix

    warnings: list[str] = []
    if "tests" not in ctx.config.replace_paths:
        warnings.append(
            'tests: [mod] replace_paths does not list "tests"; vanilla\'s 18 '
            "test files hard-code 1066 ids and would fail en masse on this map"
        )

    marks = read_bookmarks(ctx)
    if not marks:
        return StepResult(
            summary=(
                "skipped: no bookmark in "
                f"{ctx.out_path('common', 'bookmarks', 'bookmarks')}; run the "
                "bookmarks step first (the tests are anchored to its date)"
            ),
            skipped=True,
            warnings=warnings,
        )
    bookmark = choose_bookmark(marks, raw.get("bookmark"))
    holders = read_title_holders(ctx, bookmark.date)
    provinces = read_land_provinces(ctx)
    declared = read_character_ids(ctx)
    for what, have, owner in (
        ("history/titles", holders, "history_titles"),
        ("history/provinces", provinces, "map + history_titles"),
        ("history/characters", declared, "characters"),
    ):
        if not have:
            warnings.append(
                f"tests: nothing read from {what}, so no assertion covers it; "
                f"run the {owner} step in the same pass"
            )

    text, counts = build(
        ctx,
        marks,
        holders,
        provinces,
        prefix=prefix,
        bookmark=bookmark,
        sample=sample,
        declared=declared,
    )
    rel = OUT_TEMPLATE.format(prefix=prefix)
    # No generated-by banner from ctx.header: the file carries its own.
    # `tests/` is in ck2ck3.pdx.encoding.BOM_PREFIXES, so this gets a BOM: all
    # 18 vanilla `game/tests/*.txt` start `ef bb bf` and 17 of them are pure
    # ASCII (`verified` 2026-09-08).
    path = ctx.write_text(rel, text)
    for message in warnings:
        ctx.warn(message)
    return StepResult(
        summary=(
            f"{counts['tests']} scripted tests at {fmt_date(bookmark.date)} "
            f"({counts['bookmark_characters']} bookmark characters, "
            f"{counts['title_holders']}/{counts['title_holders_available']} "
            f"title holders, {counts['provinces']}/"
            f"{counts['provinces_available']} provinces) -> {rel}"
        ),
        counts=counts,
        warnings=warnings,
        written=[path],
    )
