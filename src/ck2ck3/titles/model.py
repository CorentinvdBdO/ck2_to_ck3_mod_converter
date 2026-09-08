"""One parse of the CK2 title side, shared by the three steps of this lane.

``titles``, ``history_titles`` and ``bookmarks`` all need the same inputs (the
title tree, both histories, the barony placement, the government derivation),
so the model is built once and cached on ``ctx.data`` — while still being
buildable from scratch, because ``--steps history_titles`` alone has to work.

:func:`liveness` is the single source of truth for "does this CK2 title exist
as a CK3 title", and both the ``landed_titles`` writer and the two history
writers read it, so a title can never be defined in one file and missing from
another.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..ids import name_list_id
from ..pdx import Date
from . import ck2read, place, tables
from .ck2read import Ck2Bookmark, Ck2CharacterStub, Ck2ProvinceHistory, Ck2Title
from .place import PlacementPlan
from .tables import GovernmentChoice

#: ``ctx.data`` key the model is cached under.
CACHE_KEY = "titles_model"


def liveness(
    *,
    flat: list[Ck2Title],
    plan: PlacementPlan,
    patricians: frozenset[str],
) -> tuple[frozenset[str], dict[str, str]]:
    """``(live title ids, dead title id -> reason)``.

    The three rules, in order (a dead title kills its whole subtree):

    1. a CK2 patrician family from ``republics.txt`` is a **root-level
       barony**, and CK3 forbids a barony outside a county;
    2. a barony with no CK3 province cannot exist — ``province = <id>`` is
       mandatory for a CK3 barony;
    3. a county with no live barony cannot exist — a CK3 county must contain at
       least one barony.

    Duchies, kingdoms and empires survive with no children: CK3 calls that a
    titular title and it is legal (``_landed_titles.info``).
    """
    dead: dict[str, str] = {}
    for title in flat:
        if title.id in patricians:
            dead[title.id] = (
                "CK2 patrician family (common/landed_titles/republics.txt): a "
                "root-level barony; CK3 forbids a barony outside a county and "
                "has no patrician families"
            )
            continue
        if title.prefix == "b":
            placement = plan.get(title.id)
            if placement is None:
                dead[title.id] = "not in the barony placement plan"
            elif not placement.placed:
                dead[title.id] = f"{placement.status}: {placement.reason}"
    for title in flat:
        if title.prefix != "c" or title.id in dead:
            continue
        if not any(
            child.prefix == "b" and child.id not in dead for child in title.children
        ):
            dead[title.id] = (
                "no live barony: a CK3 county needs at least one barony and a "
                "barony needs province = <id>"
            )
    # propagate: a child of a dead title cannot be emitted either
    for title in flat:
        if title.id not in dead:
            continue
        for descendant in ck2read.flatten([title])[1:]:
            dead.setdefault(descendant.id, f"ancestor {title.id} is not a CK3 title")
    live = frozenset(t.id for t in flat if t.id not in dead)
    return live, dead


def own_counties(
    roots: list[Ck2Title], live: frozenset[str]
) -> dict[str, str]:
    """``title -> the first live county inside its own de jure subtree``.

    CK3 warns when a title's ``capital`` is a county outside it
    (ck3-tiger ``warning(title-tier)``), so this is what a title falls back to
    when the CK2 capital province's county did not survive.
    """
    out: dict[str, str] = {}

    def walk(title: Ck2Title) -> str | None:
        found: str | None = None
        if title.prefix == "c" and title.id in live:
            found = title.id
        for child in title.children:
            child_county = walk(child)
            if found is None:
                found = child_county
        if found is not None:
            out[title.id] = found
        return found

    for root in roots:
        walk(root)
    return out


def kingdoms_of_counties(roots: list[Ck2Title]) -> dict[str, str]:
    """``county id -> the de jure kingdom above it`` (empire if there is none).

    Used only to group ``history/provinces`` into files the way vanilla does
    (177 files for ~11k provinces, one per kingdom).
    """
    out: dict[str, str] = {}

    def walk(title: Ck2Title, kingdom: str | None, empire: str | None) -> None:
        if title.prefix == "e":
            empire = title.id
        elif title.prefix == "k":
            kingdom = title.id
        elif title.prefix == "c":
            out[title.id] = kingdom or empire or "unplaced"
            return
        for child in title.children:
            walk(child, kingdom, empire)

    for root in roots:
        walk(root, None, None)
    return out


@dataclass
class TitleModel:
    """Everything the lane's three steps read."""

    roots: list[Ck2Title]
    flat: list[Ck2Title]
    by_id: dict[str, Ck2Title]
    counties: dict[str, list[str]]
    patricians: frozenset[str]
    province_history: dict[int, Ck2ProvinceHistory]
    #: county id -> its CK2 province history
    county_history: dict[str, Ck2ProvinceHistory]
    county_of_province: dict[int, str]
    kingdom_of_county: dict[str, str]
    plan: PlacementPlan
    live_titles: frozenset[str]
    dead_titles: dict[str, str]
    title_history: dict[str, ck2read.Ck2TitleHistory]
    characters: dict[str, Ck2CharacterStub]
    culture_groups: dict[str, list[str]]
    name_list_of_culture: dict[str, str]
    government: dict[str, GovernmentChoice]
    government_map: dict[str, str]
    own_county: dict[str, str]
    bookmarks: list[Ck2Bookmark]
    placeholder_capital: str
    bookmark_date: Date
    warnings: list[str] = field(default_factory=list)


def _explicit_governments(
    histories: dict[str, ck2read.Ck2TitleHistory], bookmark: Date
) -> dict[str, str]:
    """CK2 ``government = x`` from ``history/titles``, latest at the bookmark."""
    out: dict[str, str] = {}
    for title, history in histories.items():
        best: tuple[tuple[int, int, int], str] | None = None
        for date, nodes in history.dated:
            stamp = (date.year, date.month, date.day)
            if stamp > (bookmark.year, bookmark.month, bookmark.day):
                continue
            for node in nodes:
                if node.key == "government":
                    if best is None or stamp >= best[0]:
                        best = (stamp, str(node.value).strip('"'))
        if best:
            out[title] = best[1]
    return out


def build(
    *,
    ck2_mod: Path,
    definition_csv: Path,
    province_id_map: Path,
    government_map_csv: Path,
    bookmark_date: str,
    barony_set_csv: Path | None = None,
    prefix: str = "fae",
) -> TitleModel:
    """Parse the CK2 title side and derive everything that has no 1:1 source."""
    lt_dir = ck2_mod / "common" / "landed_titles"
    roots = ck2read.read_landed_titles_dir(lt_dir)
    flat = ck2read.flatten(roots)
    by_id = {t.id: t for t in flat}
    counties = place.counties_with_baronies(flat)
    patricians = frozenset(ck2read.republic_titles(lt_dir / "republics.txt"))

    province_history = ck2read.read_province_histories(
        ck2_mod / "history" / "provinces"
    )
    id_map = place.read_province_id_map(province_id_map)
    ck3_of_county, ck2_of_county = place.county_province_map(province_history, id_map)
    county_history = {
        county: province_history[pid] for county, pid in ck2_of_county.items()
    }
    county_of_province = {
        pid: history.title
        for pid, history in province_history.items()
        if history.title
    }
    definition_names = (
        place.read_definition_names(definition_csv) if definition_csv.exists() else {}
    )
    barony_set = (
        place.read_barony_set(barony_set_csv)
        if barony_set_csv and barony_set_csv.exists()
        else None
    )
    bookmark = Date.parse(bookmark_date)
    plan = place.build_plan(
        counties=counties,
        province_of_county=ck3_of_county,
        histories=county_history,
        bookmark=bookmark,
        definition_names=definition_names,
        barony_set=barony_set,
    )
    live, dead = liveness(flat=flat, plan=plan, patricians=patricians)

    title_history = ck2read.read_title_histories(ck2_mod / "history" / "titles")
    characters = ck2read.read_character_index(ck2_mod / "history" / "characters")
    culture_groups = ck2read.read_culture_groups(ck2_mod / "common" / "cultures")
    # `name_list_{prefix}_{ck2 culture}`, NOT `name_list_{ck2 culture}`: the
    # `cultures` step is the owner of the id and prefixes it
    # (ck2ck3.steps.cultures.name_list_id). Dropping the prefix here produced
    # 2848 ck3-tiger `error(missing-item): name list name_list_sun_elf not
    # defined` against this file (`verified` 2026-09-08); a test asserts the
    # two agree (tests/test_titles_write.py).
    name_list_of_culture = {
        culture: name_list_id(prefix, culture)
        for members in culture_groups.values()
        for culture in members
    }

    government_map = tables.load_government_map(government_map_csv)
    explicit = _explicit_governments(title_history, bookmark)
    government = {
        title.id: tables.derive_government(
            title_id=title.id,
            keywords=title.keywords,
            explicit_ck2=explicit.get(title.id),
            is_republic=title.id in patricians,
            government_map=government_map,
        )
        for title in flat
        if title.id in live
    }
    bookmarks = ck2read.read_bookmarks_dir(ck2_mod / "common" / "bookmarks")

    placeholder = next(
        (c for c in sorted(counties) if c in live),
        "c_placeholder",
    )
    return TitleModel(
        roots=roots,
        flat=flat,
        by_id=by_id,
        counties=counties,
        patricians=patricians,
        province_history=province_history,
        county_history=county_history,
        county_of_province=county_of_province,
        kingdom_of_county=kingdoms_of_counties(roots),
        plan=plan,
        live_titles=live,
        dead_titles=dead,
        title_history=title_history,
        characters=characters,
        culture_groups=culture_groups,
        name_list_of_culture=name_list_of_culture,
        government=government,
        government_map=government_map,
        own_county=own_counties(roots, live),
        bookmarks=bookmarks,
        placeholder_capital=placeholder,
        bookmark_date=bookmark,
        warnings=list(plan.warnings),
    )


def repo_root(ctx: Any) -> Path:
    """The converter repository root, derived from the config file's path.

    ``docs/evidence`` is evidence about *this* repository, not a file of the
    generated mod, so it never goes through ``ctx.write_*``.
    """
    return ctx.config.path.parent.parent


def load(ctx: Any) -> TitleModel:
    """The cached model for this run, built on first use."""
    cached = ctx.data.get(CACHE_KEY)
    if isinstance(cached, TitleModel):
        return cached
    root = repo_root(ctx)
    model = build(
        ck2_mod=ctx.ck2_mod,
        definition_csv=ctx.out_path("map_data", "definition.csv"),
        province_id_map=root / "docs" / "evidence" / "province_id_map.csv",
        government_map_csv=root / "mappings" / "government_map.csv",
        bookmark_date=ctx.config.bookmark_date,
        barony_set_csv=root / "docs" / "evidence" / "barony_set.csv",
        prefix=ctx.config.prefix,
    )
    ctx.data[CACHE_KEY] = model
    for warning in model.warnings:
        ctx.warn(warning)
    return model
