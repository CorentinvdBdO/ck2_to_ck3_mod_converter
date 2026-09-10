"""CK2 ``history/provinces/`` -> the set of physical baronies per county.

The whole barony method rests on one fact (CLAUDE.md invariant): **Faerûn
defines 15,356 baronies but builds ~3.8k holdings**, so the barony set is the
*built* holdings, never the defined list.  Building all 15k would give baronies
of ~8x8 px.

Facts this module encodes, all `verified` on Faerûn 2026-09-07:

* The province id is in the **filename** (``history/provinces/1 - Waterdeep.txt``
  is province 1); nothing inside the file repeats it.  The county title is the
  ``title = c_x`` line.
* A holding is built by ``b_<key> = <holding type>``, either at the top of the
  file (meaning "from the start of history") or inside a dated
  ``1010.1.1 = { ... }`` block.  The same barony can be re-assigned later
  (``b_castle_waterdeep`` goes castle -> tribal -> castle -> tribal -> castle),
  so a date has to be resolved by "last assignment at or before it", not by
  "first mention".
* The right-hand side is not always a holding type: ``b_sea_ward =
  ct_planar_portal`` builds a *building*.  Only the nine CK2 holding types
  count, and of those only four have a CK3 counterpart.
* A top-level ``terrain = <category>`` line is the province's **gameplay**
  terrain in CK2, and it wins over the ``terrain.bmp`` majority (which is only
  the fallback).  1040 of Faerûn's 2125 province files carry one, all
  top-level, none dated (`verified`, ``scripts/survey_terrain_history.py``).
  Read into :attr:`ProvinceHistory.terrains`; applied by
  ``ck2ck3.map.terrain_history``.
* Faerûn uses exactly four of them (castle 1905, tribal 1465, city 1280,
  temple 697 assignments).  ``nomad``, ``family_palace``, ``fort``,
  ``hospital`` and ``trade_post`` appear nowhere, but they are handled anyway
  because the converter is not Faerûn-specific.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from pathlib import Path

from .blocks import CK2_ENCODING

#: CK2 holding type -> CK3 holding type. CK3 1.19 has four
#: (`verified`: game/common/holdings/00_holdings.txt declares castle_holding,
#: city_holding, church_holding, tribal_holding and the special
#: `none`/`auto` entries).
CK2_TO_CK3_HOLDING: dict[str, str] = {
    "castle": "castle_holding",
    "city": "city_holding",
    "temple": "church_holding",
    "tribal": "tribal_holding",
    # CK3 removed nomads (they were a CK2 Horse Lords government, not a
    # holding tier CK3 kept); tribal is the nearest thing that exists.
    "nomad": "tribal_holding",
}

#: CK2 holding types that are **not** baronies in CK3. They were built on top
#: of an existing holding slot in CK2 (a fort or a hospital occupies a barony
#: slot but has no lord), and CK3 models the equivalents as buildings or
#: special buildings, not as baronies. Listed in
#: ``docs/evidence/nonbarony_holdings.csv`` so the submod can turn them into
#: special buildings later.
NON_BARONY_HOLDINGS: dict[str, str] = {
    "fort": "CK2 fort: no CK3 holding tier; model as a special building",
    "hospital": "CK2 hospital: no CK3 holding tier; model as a building",
    "trade_post": "CK2 trade post: CK3 has no republic trade posts",
    "family_palace": "CK2 family palace: CK3 has no Indian family palaces",
}

#: every CK2 holding type, barony or not
HOLDING_TYPES = frozenset(CK2_TO_CK3_HOLDING) | frozenset(NON_BARONY_HOLDINGS)

Date = tuple[int, int, int]

#: "from the start of history": a top-level assignment with no dated block
EPOCH: Date = (0, 0, 0)

_ID_FROM_FILENAME = re.compile(r"^\s*(\d+)")
_COMMENT = re.compile(r"#[^\n]*")
_TITLE = re.compile(r"\btitle\s*=\s*(c_[A-Za-z0-9_]+)")
_MAX_SETTLEMENTS = re.compile(r"\bmax_settlements\s*=\s*(\d+)")
#: a dated block header, an opening/closing brace, a `b_x = y` assignment, a
#: `culture = x` line or a `terrain = x` line. The culture is read only to pick
#: a **graphical** region for the province's CK3 baronies
#: (`map_data/geographical_regions`); the real culture of the CK3 province is
#: written by the `history_titles` step. The terrain is the CK2 author's
#: **gameplay** terrain override for the province (see
#: `ck2ck3.map.terrain_history`); in CK2 it wins over the `terrain.bmp`
#: majority, which is only the fallback.
_EVENT = re.compile(
    r"(?P<date>(\d+)\.(\d+)\.(\d+))\s*=\s*\{"
    r"|(?P<open>\{)"
    r"|(?P<close>\})"
    r"|(?P<barony>b_[A-Za-z0-9_]+)\s*=\s*(?P<value>[A-Za-z0-9_]+)"
    r"|culture\s*=\s*(?P<culture>[A-Za-z0-9_]+)"
    r"|\bterrain\s*=\s*(?P<terrain>[A-Za-z0-9_]+)"
)


@dataclass(frozen=True)
class Holding:
    """One built holding: the barony key, its CK2 type and when it appeared."""

    barony: str
    ck2_type: str
    built: Date

    @property
    def ck3_type(self) -> str | None:
        return CK2_TO_CK3_HOLDING.get(self.ck2_type)

    @property
    def is_barony(self) -> bool:
        return self.ck2_type in CK2_TO_CK3_HOLDING


@dataclass
class ProvinceHistory:
    """What ``history/provinces/<id> - <name>.txt`` says about holdings."""

    province_id: int
    county: str | None
    name: str
    source: str
    max_settlements: int | None = None
    #: barony key -> [(date, ck2 holding type)] in file order
    assignments: dict[str, list[tuple[Date, str]]] = field(default_factory=dict)
    #: [(date, ck2 culture)] in file order; CK2 lets a province change culture
    cultures: list[tuple[Date, str]] = field(default_factory=list)
    #: [(date, ck2 terrain category)] in file order; CK2 allows a dated
    #: `terrain = x` too, so this is a history like the others rather than a
    #: single value (Faerûn never uses a dated one, `verified` —
    #: `docs/step_map_terrain.md` §1)
    terrains: list[tuple[Date, str]] = field(default_factory=list)

    def terrain_at(self, date: Date) -> str | None:
        """The CK2 terrain override in effect at ``date`` (last one wins).

        ``None`` when the province declares no override at all at or before
        ``date`` — then the ``terrain.bmp`` majority is the terrain, which is
        CK2's own fallback order.
        """
        best: tuple[Date, str] | None = None
        for when, value in self.terrains:
            if when <= date and (best is None or when >= best[0]):
                best = (when, value)
        return best[1] if best else None

    def culture_at(self, date: Date) -> str | None:
        """The CK2 culture in effect at ``date`` (last assignment wins)."""
        best: tuple[Date, str] | None = None
        for when, value in self.cultures:
            if when <= date and (best is None or when >= best[0]):
                best = (when, value)
        return best[1] if best else None

    def at(self, date: Date) -> dict[str, str]:
        """Holding type per barony as of ``date`` (last holding assignment wins).

        Assignments whose right-hand side is not a CK2 *holding type* are
        skipped rather than treated as a state change: ``b_sea_ward =
        ct_planar_portal`` builds a building inside the city, it does not stop
        the barony being a city.  Reading them as a state change loses the
        barony entirely.
        """
        out: dict[str, str] = {}
        for barony, events in self.assignments.items():
            best: tuple[Date, str] | None = None
            for when, value in events:
                if value not in HOLDING_TYPES:
                    continue
                if when <= date and (best is None or when >= best[0]):
                    best = (when, value)
            if best is not None:
                out[barony] = best[1]
        return out

    def first_built(self, barony: str, until: Date) -> Date | None:
        """Earliest date at or before ``until`` at which ``barony`` was built."""
        dates = [
            when
            for when, value in self.assignments.get(barony, ())
            if when <= until and value in HOLDING_TYPES
        ]
        return min(dates) if dates else None


def parse_date(text: str) -> Date:
    a, b, c = (int(v) for v in text.split("."))
    return (a, b, c)


def read_province_file(path: str | Path) -> ProvinceHistory | None:
    """Parse one ``history/provinces`` file. ``None`` if the id is unreadable."""
    p = Path(path)
    m = _ID_FROM_FILENAME.match(p.stem)
    if not m:
        return None
    text = _COMMENT.sub("", p.read_text(encoding=CK2_ENCODING, errors="replace"))
    title = _TITLE.search(text)
    ms = _MAX_SETTLEMENTS.search(text)
    name = p.stem.split("-", 1)[1].strip() if "-" in p.stem else p.stem
    hist = ProvinceHistory(
        province_id=int(m.group(1)),
        county=title.group(1) if title else None,
        name=name,
        source=p.name,
        max_settlements=int(ms.group(1)) if ms else None,
    )
    depth = 0
    #: date of the innermost enclosing dated block, EPOCH at depth 0
    dates: list[Date] = [EPOCH]
    for tok in _EVENT.finditer(text):
        if tok.group("date"):
            depth += 1
            dates.append(parse_date(tok.group("date")))
        elif tok.group("open"):
            depth += 1
            dates.append(dates[-1])
        elif tok.group("close"):
            depth = max(0, depth - 1)
            if len(dates) > 1:
                dates.pop()
        elif tok.group("culture"):
            hist.cultures.append((dates[-1], tok.group("culture")))
        elif tok.group("terrain"):
            hist.terrains.append((dates[-1], tok.group("terrain")))
        else:
            hist.assignments.setdefault(tok.group("barony"), []).append(
                (dates[-1], tok.group("value"))
            )
    return hist


def read_dir(directory: str | Path) -> dict[int, ProvinceHistory]:
    """Every ``history/provinces`` file, keyed by CK2 province id."""
    out: dict[int, ProvinceHistory] = {}
    for path in sorted(Path(directory).glob("*.txt")):
        hist = read_province_file(path)
        if hist is not None:
            out[hist.province_id] = hist
    return out


@dataclass(frozen=True)
class BaronySelection:
    """The barony set of one CK2 province."""

    province_id: int
    county: str | None
    #: barony key -> CK3 holding type, in the order they were selected
    baronies: dict[str, str]
    #: barony key -> the date it was first built
    built: dict[str, Date]
    #: baronies present only because a *later* bookmark builds them
    later: frozenset[str]
    #: (barony, ck2 type) pairs that CK3 has no barony tier for
    non_barony: tuple[tuple[str, str], ...] = ()


def select(
    hist: ProvinceHistory,
    *,
    bookmark: Date,
    latest: Date,
    order: list[str] | None = None,
) -> BaronySelection:
    """Baronies of one province: built at ``bookmark``, or by ``latest``.

    ``docs/design_map.md`` §B.1: the set is the holdings built at the chosen
    bookmark date **union** anything built by the latest bookmark, so a later
    bookmark still has provinces for its holdings.  A barony built later is
    still a physical barony from turn one — CK3 has no way to create a province
    mid-game — it just starts with whatever holding it eventually gets.

    ``order`` is the county's barony order from ``landed_titles`` (capital
    first); it makes the result independent of dict iteration order.
    """
    at_bookmark = hist.at(bookmark)
    ever = hist.at(latest)
    keys = list(order or ()) + [k for k in hist.assignments if not order or k not in order]

    baronies: dict[str, str] = {}
    built: dict[str, Date] = {}
    later: set[str] = set()
    non_barony: list[tuple[str, str]] = []
    for key in keys:
        ck2_type = at_bookmark.get(key) or ever.get(key)
        if ck2_type is None or ck2_type not in HOLDING_TYPES:
            continue
        if ck2_type in NON_BARONY_HOLDINGS:
            non_barony.append((key, ck2_type))
            continue
        when = hist.first_built(key, latest) or EPOCH
        baronies[key] = CK2_TO_CK3_HOLDING[ck2_type]
        built[key] = when
        if key not in at_bookmark:
            later.add(key)
    return BaronySelection(
        province_id=hist.province_id,
        county=hist.county,
        baronies=baronies,
        built=built,
        later=frozenset(later),
        non_barony=tuple(non_barony),
    )


def render_nonbarony_csv(
    selections: dict[int, BaronySelection], names: dict[int, str] | None = None
) -> str:
    """``docs/evidence/nonbarony_holdings.csv`` — CK2 holdings with no CK3 tier."""
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["ck2_province", "province_name", "county", "barony", "ck2_holding", "reason"])
    for pid in sorted(selections):
        sel = selections[pid]
        for barony, ck2_type in sel.non_barony:
            w.writerow(
                [
                    pid,
                    (names or {}).get(pid, ""),
                    sel.county or "",
                    barony,
                    ck2_type,
                    NON_BARONY_HOLDINGS[ck2_type],
                ]
            )
    return buf.getvalue()
