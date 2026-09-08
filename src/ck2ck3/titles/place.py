"""Which CK2 baronies get a CK3 province, and which province id each gets.

A CK3 province *is* a barony, so every emitted barony needs
``province = <id>`` and every land province in ``map_data/definition.csv``
needs exactly one barony.  Both facts are owned by other lanes — ``map`` and
``baronies`` write ``definition.csv`` — so this module only *reads* their
output and never invents an id.

Two modes, picked automatically:

``barony_set``
    lane ``baronies`` has published ``docs/evidence/barony_set.csv``
    (``county,barony,holding,built_date,seed_source,pixels,status``) and
    ``definition.csv`` names its rows ``b_<barony>``.  The placed set is the
    rows with status ``placed`` or ``override``; the province id is the
    ``definition.csv`` row whose name matches.

``county_capital``
    the pre-``baronies`` state: ``definition.csv`` has one row per CK2 province
    (i.e. per county) and names it after the CK2 province, not the barony.  One
    barony per county is placed — the county capital, i.e. the first barony of
    the CK2 ``landed_titles`` order that is built at the bookmark date — and it
    takes that county's province id from ``docs/evidence/province_id_map.csv``.

Everything not placed is emitted as a **commented** barony block, so the
submod can promote it without re-running the converter.
"""

from __future__ import annotations

import csv
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from ..pdx import Date
from .ck2read import Ck2ProvinceHistory, Ck2Title

#: statuses of ``barony_set.csv`` that mean "this barony is on the map".
PLACED_STATUSES = frozenset({"placed", "override"})


@dataclass(frozen=True)
class Placement:
    """One barony's map slot (or the reason it has none)."""

    barony: str
    county: str
    province: int | None
    holding: str | None
    built: Date | None
    #: ``placed`` / ``demoted`` / ``unbuilt`` / ``no_province``
    status: str
    reason: str = ""

    @property
    def placed(self) -> bool:
        return self.province is not None


@dataclass
class PlacementPlan:
    """The whole barony -> province decision, plus how it was reached."""

    mode: str
    by_barony: dict[str, Placement] = field(default_factory=dict)
    by_province: dict[int, str] = field(default_factory=dict)
    #: county -> its placed baronies, in landed_titles order.
    by_county: dict[str, list[str]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def get(self, barony: str) -> Placement | None:
        return self.by_barony.get(barony)

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for placement in self.by_barony.values():
            out[placement.status] = out.get(placement.status, 0) + 1
        return out


# ------------------------------------------------------------------ readers


def read_definition_names(path: Path) -> dict[str, int]:
    """``map_data/definition.csv`` -> ``name -> province id``.

    Column layout is ``id;r;g;b;name;x`` (`verified`, vanilla and our own map
    step).  The name is compared case-insensitively because the map step
    uppercases it (vanilla writes ``VESTFIRDIR``) while lane ``baronies``
    writes a lowercase ``b_<barony>``.
    """
    out: dict[str, int] = {}
    text = path.read_text(encoding="utf-8", errors="replace")
    for line in text.splitlines()[1:]:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(";")
        if len(parts) < 5 or not parts[0].isdigit():
            continue
        pid = int(parts[0])
        if pid == 0:
            continue
        out.setdefault(parts[4].strip().lower(), pid)
    return out


def read_province_id_map(path: Path) -> dict[int, int]:
    """``docs/evidence/province_id_map.csv`` -> CK2 province id -> CK3 id."""
    out: dict[int, int] = {}
    if not path.exists():
        return out
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            ck2, ck3 = row.get("ck2_id", ""), row.get("ck3_id", "")
            if ck2 and ck3:
                out[int(ck2)] = int(ck3)
    return out


@dataclass(frozen=True)
class BaronySetRow:
    county: str
    barony: str
    holding: str
    built_date: str
    status: str


def read_barony_set(path: Path) -> list[BaronySetRow]:
    """``docs/evidence/barony_set.csv``, the contract with lane ``baronies``."""
    rows: list[BaronySetRow] = []
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            rows.append(
                BaronySetRow(
                    county=row.get("county", "").strip(),
                    barony=row.get("barony", "").strip(),
                    holding=row.get("holding", "").strip(),
                    built_date=row.get("built_date", "").strip(),
                    status=row.get("status", "").strip().lower(),
                )
            )
    return rows


# --------------------------------------------------------------- derivation


def _parse_date(text: str) -> Date | None:
    try:
        return Date.parse(text)
    except (ValueError, TypeError, AttributeError):
        return None


def built_holdings(
    province: Ck2ProvinceHistory, *, until: Date | None = None
) -> dict[str, tuple[str, Date | None]]:
    """``barony -> (holding, built date)`` for every holding built by ``until``.

    ``built date`` is ``None`` when CK2 declares the holding at the top of the
    file (i.e. it exists from the start of history).  A later ``b_x = none``
    (or a ``remove_settlement``) removes the barony from the result, so this is
    the *state* at ``until``, not a log.
    """
    state: dict[str, tuple[str, Date | None]] = {
        barony: (holding, None)
        for barony, holding in province.holdings.items()
        if holding not in ("none", "0")
    }
    changes = sorted(
        province.holding_changes, key=lambda c: (c[0].year, c[0].month, c[0].day)
    )
    for date, barony, holding in changes:
        if until is not None and _after(date, until):
            break
        if holding in ("none", "0"):
            state.pop(barony, None)
        else:
            state[barony] = (holding, date)
    for date, key, value in province.dated:
        if key != "remove_settlement":
            continue
        if until is not None and _after(date, until):
            continue
        state.pop(str(value), None)
    return state


def _after(left: Date, right: Date) -> bool:
    return (left.year, left.month, left.day) > (right.year, right.month, right.day)


def county_capital(
    baronies: Iterable[str], built: Mapping[str, tuple[str, Date | None]]
) -> str | None:
    """The barony a one-per-county map places: first built in CK2 order.

    CK2 has no explicit county capital key in ``landed_titles`` (``capital``
    there is a *province* id), so declaration order is the only signal, and it
    is the order CK2 itself uses to pick the county's main holding.
    """
    ordered = list(baronies)
    for barony in ordered:
        if barony in built:
            return barony
    return None


def build_plan(
    *,
    counties: Mapping[str, list[str]],
    province_of_county: Mapping[str, int],
    histories: Mapping[str, Ck2ProvinceHistory],
    bookmark: Date,
    definition_names: Mapping[str, int],
    barony_set: list[BaronySetRow] | None = None,
) -> PlacementPlan:
    """Decide every barony's province.  See the module docstring for the modes.

    ``counties`` is ``county id -> barony ids in landed_titles order``,
    ``province_of_county`` is ``county id -> CK3 province id`` (used by the
    fallback mode only) and ``histories`` is ``county id -> CK2 province
    history`` so the built set can be computed at ``bookmark``.
    """
    if barony_set:
        return _plan_from_barony_set(
            counties=counties,
            histories=histories,
            bookmark=bookmark,
            definition_names=definition_names,
            barony_set=barony_set,
        )
    return _plan_county_capital(
        counties=counties,
        province_of_county=province_of_county,
        histories=histories,
        bookmark=bookmark,
    )


def _plan_from_barony_set(
    *,
    counties: Mapping[str, list[str]],
    histories: Mapping[str, Ck2ProvinceHistory],
    bookmark: Date,
    definition_names: Mapping[str, int],
    barony_set: list[BaronySetRow],
) -> PlacementPlan:
    plan = PlacementPlan(mode="barony_set")
    rows = {row.barony: row for row in barony_set}
    for county, baronies in counties.items():
        history = histories.get(county)
        built = built_holdings(history, until=bookmark) if history else {}
        for barony in baronies:
            row = rows.get(barony)
            holding = built.get(barony, (None, None))[0]
            date = built.get(barony, (None, None))[1]
            if row is None:
                plan.by_barony[barony] = Placement(
                    barony, county, None, holding, date, "unbuilt",
                    "absent from barony_set.csv",
                )
                continue
            if row.status not in PLACED_STATUSES:
                plan.by_barony[barony] = Placement(
                    barony, county, None, holding, date, "demoted",
                    f"barony_set.csv status = {row.status or 'empty'}",
                )
                continue
            province = definition_names.get(barony.lower())
            if province is None:
                plan.warnings.append(
                    f"{barony}: barony_set.csv says {row.status} but "
                    "map_data/definition.csv has no row named after it"
                )
                plan.by_barony[barony] = Placement(
                    barony, county, None, holding, date, "no_province",
                    "no definition.csv row",
                )
                continue
            plan.by_barony[barony] = Placement(
                barony, county, province, holding or row.holding, date, "placed",
                "barony_set.csv",
            )
            plan.by_province[province] = barony
            plan.by_county.setdefault(county, []).append(barony)
    return plan


def _plan_county_capital(
    *,
    counties: Mapping[str, list[str]],
    province_of_county: Mapping[str, int],
    histories: Mapping[str, Ck2ProvinceHistory],
    bookmark: Date,
) -> PlacementPlan:
    plan = PlacementPlan(mode="county_capital")
    for county, baronies in counties.items():
        history = histories.get(county)
        built = built_holdings(history, until=bookmark) if history else {}
        if not built and history is not None:
            # nothing at the bookmark: fall back to anything ever built, so a
            # later bookmark still has a province to play on.
            built = built_holdings(history)
        capital = county_capital(baronies, built)
        province = province_of_county.get(county)
        if province is None:
            plan.warnings.append(
                f"{county}: no CK3 province (province_id_map.csv), "
                "county and its baronies are commented out"
            )
            for barony in baronies:
                holding, date = built.get(barony, (None, None))
                plan.by_barony[barony] = Placement(
                    barony, county, None, holding, date, "no_province",
                    "county has no CK3 province",
                )
            continue
        for barony in baronies:
            holding, date = built.get(barony, (None, None))
            if barony != capital:
                plan.by_barony[barony] = Placement(
                    barony,
                    county,
                    None,
                    holding,
                    date,
                    "demoted" if barony in built else "unbuilt",
                    "one province per county until lane baronies lands",
                )
                continue
            plan.by_barony[barony] = Placement(
                barony, county, province, holding, date, "placed", "county capital"
            )
            plan.by_province[province] = barony
            plan.by_county.setdefault(county, []).append(barony)
    return plan


def county_province_map(
    histories: Mapping[int, Ck2ProvinceHistory], id_map: Mapping[int, int]
) -> tuple[dict[str, int], dict[str, int]]:
    """``(county -> CK3 province id, county -> CK2 province id)``.

    The CK2 province -> county link is ``title = c_x`` inside the province
    history file; CK2 has no other place for it.
    """
    ck3: dict[str, int] = {}
    ck2: dict[str, int] = {}
    for pid, history in histories.items():
        if not history.title:
            continue
        ck2[history.title] = pid
        target = id_map.get(pid)
        if target is not None:
            ck3[history.title] = target
    return ck3, ck2


def counties_with_baronies(titles: Iterable[Ck2Title]) -> dict[str, list[str]]:
    """``county id -> its barony ids`` in CK2 ``landed_titles`` order."""
    out: dict[str, list[str]] = {}
    for title in titles:
        if title.prefix != "c":
            continue
        out[title.id] = [c.id for c in title.children if c.prefix == "b"]
    return out
