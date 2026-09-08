"""``history/provinces`` from CK2 province history, one block per barony.

The structural change: a CK2 province is a **county** whose body lists its
baronies as holding types; a CK3 province **is** a barony.  So one CK2 file
becomes one block per *placed* barony of that county, each repeating the
county's culture and faith and carrying only its own holding.

Layout follows vanilla: top-level ``culture`` / ``religion`` / ``holding``
plus dated blocks for later changes (`verified`
``history/provinces/k_sardinia.txt:33-46``; dated ``holding`` is legal and used
1538 times in vanilla).  Files are grouped by de jure kingdom, the way vanilla
groups its 177 files for ~11k provinces.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from ..pdx import Date
from .ck2read import Ck2ProvinceHistory
from .place import PlacementPlan
from .tables import map_holding
from .text import Lines

#: CK2 dated province keys with no CK3 province-history home.  Value = the
#: reason written into the generated file next to the province block.
DATED_COMMENT_ONLY: dict[str, str] = {
    "capital": "CK2 moved the county capital; CK3 uses set_capital_county on the title",
    "name": "CK3 has no dated province name; the title carries the name",
    "remove_settlement": "converted to holding = none at the same date",
    "build_wonder": "Faerun wonder; CK3 route is special_building_slot / special_building",
    "build_wonder_upgrade": "Faerun wonder upgrade; CK3 route is a building level",
    "set_wonder_stage": "Faerun wonder stage; no CK3 equivalent",
    "set_wonder_damaged": "no CK3 equivalent",
    "destroy_wonder": "no CK3 equivalent",
    "max_settlements": "CK3 has no settlement-slot count: the barony count is the slot count",
    "disease": "CK3 epidemics are common/epidemics, not province history",
    "add_province_modifier": "province modifiers are not CK3 province history",
    "remove_province_modifier": "province modifiers are not CK3 province history",
    "set_province_flag": "CK2 flags become CK3 variables (lane events-decisions)",
    "add_building": "Faerun writes no building history; nothing to convert",
    "remove_building": "Faerun writes no building history; nothing to convert",
}

HEADER = (
    "# CK3 province history, converted from CK2 history/provinces.",
    "# A CK3 province IS a barony, so one CK2 county file becomes one block per",
    "# placed barony; culture and faith are the county's, repeated per barony.",
    "# terrain is NOT written here: common/province_terrain owns the bulk data",
    "# (mappings/title_fields.csv, history/provinces terrain row) and the map step",
    "# already emits it. max_settlements is dropped: in CK3 the number of",
    "# baronies in a county IS the holding-slot count.",
    "# Faerun writes no CK2 building history at all, so there is no buildings = { }.",
)


@dataclass
class ProvinceResult:
    #: relative path -> file text
    files: dict[str, str] = field(default_factory=dict)
    counts: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def _key(date: Date) -> tuple[int, int, int]:
    return (date.year, date.month, date.day)


def render_county(
    history: Ck2ProvinceHistory,
    baronies: list[str],
    plan: PlacementPlan,
    *,
    out: Lines,
) -> tuple[int, list[str]]:
    """Append every placed barony of one CK2 county.  Returns (blocks, warnings)."""
    warnings: list[str] = []
    written = 0
    culture_changes = [
        (d, k, v) for d, k, v in history.dated if k in ("culture", "religion")
    ]
    other = [(d, k, v) for d, k, v in history.dated if k not in ("culture", "religion")]
    removals = {
        (_key(d), str(v)) for d, k, v in history.dated if k == "remove_settlement"
    }

    for barony in baronies:
        placement = plan.get(barony)
        if placement is None or not placement.placed:
            continue
        pid = placement.province
        out.line(0, f"{pid} = {{\t# {barony}, {history.title or '?'}")
        if history.culture:
            out.line(1, f"culture = {history.culture}")
        if history.religion:
            out.line(1, f"religion = {history.religion}")
        start = history.holdings.get(barony)
        if start:
            ck3, note = map_holding(start)
            if ck3 is None:
                warnings.append(
                    f"{barony}: CK2 holding {start!r} has no CK3 holding type"
                )
                out.comment(1, f"CK2 {barony} = {start} has no CK3 holding type")
                out.line(1, "holding = none")
            else:
                out.line(1, f"holding = {ck3}" + (f"\t# {note}" if note else ""))
        else:
            out.comment(
                1,
                f"CK2 built {barony} on {placement.built} - holding starts as none",
            )
            out.line(1, "holding = none")

        dated: dict[tuple[int, int, int], list[str]] = {}
        # CK2 may set the same barony twice on one date (b_x = city then
        # b_x = ct_spelljammer_port); CK3 warns about a redefined field in one
        # block (ck3-tiger warning(duplicate-field)), so the last value wins.
        holding_at: dict[tuple[int, int, int], str] = {}
        for date, bid, holding in history.holding_changes:
            if bid != barony:
                continue
            ck3, note = map_holding(holding)
            if ck3 is None:
                warnings.append(
                    f"{barony}: CK2 holding {holding!r} at {date} has no CK3 type"
                )
                continue
            holding_at[_key(date)] = (
                f"holding = {ck3}" + (f"\t# CK2 {holding}" if note else "")
            )
        for date, name in removals:
            if name == barony:
                holding_at[date] = "holding = none\t# CK2 remove_settlement"
        for stamp, line in holding_at.items():
            dated.setdefault(stamp, []).append(line)
        for date, key, value in culture_changes:
            dated.setdefault(_key(date), []).append(f"{key} = {value}")
        for stamp in sorted(dated):
            out.line(1, f"{stamp[0]}.{stamp[1]}.{stamp[2]} = {{")
            for line in dated[stamp]:
                out.line(2, line)
            out.line(1, "}")
        for date, key, value in other:
            reason = DATED_COMMENT_ONLY.get(key)
            if reason is None:
                reason = "no CK3 province-history equivalent"
            out.comment(1, f"CK2 {date} {key} = {value} - {reason}")
        out.line(0, "}")
        written += 1
    return written, warnings


def render(
    *,
    histories: Mapping[str, Ck2ProvinceHistory],
    counties: Mapping[str, list[str]],
    kingdom_of_county: Mapping[str, str],
    plan: PlacementPlan,
    prefix: str = "fae",
) -> ProvinceResult:
    """Render every ``history/provinces`` file, grouped by de jure kingdom."""
    result = ProvinceResult()
    grouped: dict[str, list[str]] = {}
    for county in counties:
        if county not in histories:
            continue
        kingdom = kingdom_of_county.get(county) or f"{prefix}_orphans"
        grouped.setdefault(kingdom, []).append(county)

    total = 0
    for kingdom, county_ids in sorted(grouped.items()):
        out = Lines()
        for line in HEADER:
            out.raw(line)
        out.raw(f"# de jure kingdom: {kingdom}")
        out.raw("")
        blocks = 0
        for county in sorted(county_ids):
            written, warnings = render_county(
                histories[county], counties[county], plan, out=out
            )
            blocks += written
            result.warnings.extend(warnings)
        if not blocks:
            continue
        result.files[f"history/provinces/{prefix}_{kingdom}.txt"] = out.text()
        total += blocks
    result.counts = {"province_blocks": total, "files": len(result.files)}
    return result
