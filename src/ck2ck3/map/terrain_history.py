"""CK2 province-history ``terrain = X`` -> CK3 ``common/province_terrain``.

**The rule this module encodes** (`verified` against CK2's own behaviour and
Faerûn's data, ``docs/step_map_terrain.md``): in CK2 a province's *gameplay*
terrain is the ``terrain = <category>`` line in its ``history/provinces`` file;
the ``terrain.bmp`` majority is only what the engine falls back to when there
is no such line.  ``ck2ck3.map.terrain`` implements the fallback.  This module
implements the first half, which the converter used to ignore entirely — 1040
of Faerûn's 2125 province files carry an override and **716 of them disagree
with their own bitmap**, so half the map shipped a terrain the CK2 author did
not choose.

Two problems the CK2 rule does not answer on its own, both settled here with a
measurement rather than a guess:

1. **Which override values mean anything.** Faerûn invents four categories CK2
   vanilla does not have (``coastal`` 141, ``subterranean`` 60, ``glacier`` 38,
   ``arctic`` 10).  Each gets an explicit row in
   ``mappings/terrain_history_overrides.csv`` — ``apply`` with a CK3 key, or
   ``keep_bitmap`` — with the evidence in the row's own note.  A value with no
   row is reported as ``unmapped`` and keeps the bitmap; nothing is guessed.

2. **County vs barony.** The CK2 override is per *province*, i.e. per CK3
   *county*; our terrain is per *barony*, because one CK2 county becomes
   several CK3 provinces (``docs/step_map_baronies.md``).  Blanket-applying the
   county's override to every barony throws away the only per-barony
   information we have (its own pixels); ignoring it for non-capitals throws
   away the author's.  The rule:

   * the **county capital** barony always takes the override (it is the barony
     the CK2 province's own history is about, and the one that inherits the
     CK2 capital position);
   * a **non-capital** barony takes it only when its own bitmap majority is a
     *weak* class — ``plains`` or ``farmlands`` by default, the two CK2
     categories that assert no relief and no vegetation, and ``plains`` is
     also the vote's own no-data fallback.  Otherwise its own pixels win, so a
     mountain barony inside an authored ``farmlands`` county stays mountains.

   ``docs/step_map_terrain.md`` §3 has the measured agreement rates this rule
   was picked from.
"""

from __future__ import annotations

import csv
import io
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

#: ``action`` values a row of ``mappings/terrain_history_overrides.csv`` may take
APPLY = "apply"
KEEP_BITMAP = "keep_bitmap"

#: bitmap classes a non-capital barony lets the county override refine.
#: ``plains`` is also ``[map.terrain] default``, the vote's own no-data answer.
DEFAULT_WEAK_CLASSES: tuple[str, ...] = ("plains", "farmlands")


@dataclass(frozen=True)
class OverrideRule:
    """One row of ``mappings/terrain_history_overrides.csv``."""

    ck2_terrain: str
    action: str
    ck3_terrain: str
    note: str = ""

    @property
    def applies(self) -> bool:
        return self.action == APPLY and bool(self.ck3_terrain)


def read_rules(path: str | Path) -> dict[str, OverrideRule]:
    """Read the decision table. Comment lines (``#``) are skipped.

    Repo rule (CLAUDE.md): every ``mappings/*.csv`` reader skips a leading
    ``#`` comment block, because several of them carry their policy there.
    """
    text = Path(path).read_text(encoding="utf-8-sig")
    lines = [ln for ln in text.splitlines() if not ln.lstrip().startswith("#")]
    out: dict[str, OverrideRule] = {}
    for row in csv.DictReader(lines):
        key = (row.get("ck2_terrain") or "").strip()
        if not key:
            continue
        action = (row.get("action") or KEEP_BITMAP).strip()
        if action not in (APPLY, KEEP_BITMAP):
            raise ValueError(
                f"{path}: row {key!r} has action {action!r}; "
                f"expected {APPLY!r} or {KEEP_BITMAP!r}"
            )
        ck3 = (row.get("ck3_terrain") or "").strip()
        if action == APPLY and not ck3:
            raise ValueError(f"{path}: row {key!r} is `apply` with no ck3_terrain")
        out[key] = OverrideRule(
            ck2_terrain=key,
            action=action,
            ck3_terrain=ck3,
            note=(row.get("note") or "").strip(),
        )
    return out


@dataclass(frozen=True)
class BaronyRef:
    """One CK3 land province, and which CK2 county it belongs to."""

    ck3_id: int
    ck2_id: int
    is_capital: bool
    #: CK2 barony key, or "" for a land province that was never split
    barony: str = ""
    county: str = ""


@dataclass(frozen=True)
class AppliedRow:
    """What happened to one CK3 province; one line of the evidence CSV."""

    ck3_id: int
    ck2_id: int
    county: str
    barony: str
    is_capital: bool
    ck2_terrain: str
    bitmap_ck3: str
    final_ck3: str
    outcome: str


#: outcomes, in the order the run report prints them
OUTCOMES = (
    "already_agreed",
    "applied_capital",
    "applied_weak_bitmap",
    "kept_strong_bitmap",
    "kept_rule",
    "kept_unmapped",
    "no_override",
)


@dataclass
class HistoryTerrainResult:
    #: CK3 province id -> terrain key, the override rule applied
    terrain: dict[int, str] = field(default_factory=dict)
    #: outcome -> how many CK3 provinces
    outcomes: Counter[str] = field(default_factory=Counter)
    #: override value with no row in the table -> how many CK2 provinces
    unmapped: Counter[str] = field(default_factory=Counter)
    #: how many CK2 counties carried an override the converter could use
    counties_with_override: int = 0
    #: how many CK3 provinces changed terrain key
    changed: int = 0
    #: old key -> new key -> count, for the run report and the paint delta
    transitions: Counter[tuple[str, str]] = field(default_factory=Counter)
    rows: list[AppliedRow] = field(default_factory=list)

    def summary(self) -> dict[str, object]:
        return {
            "counties_with_override": self.counties_with_override,
            "provinces_changed": self.changed,
            **{k: int(self.outcomes.get(k, 0)) for k in OUTCOMES},
            "unmapped_categories": dict(sorted(self.unmapped.items())),
        }


def apply_overrides(
    bitmap_terrain: dict[int, str],
    *,
    refs: list[BaronyRef],
    overrides: dict[int, str],
    rules: dict[str, OverrideRule],
    weak_classes: tuple[str, ...] = DEFAULT_WEAK_CLASSES,
) -> HistoryTerrainResult:
    """Fold the CK2 history override into the per-barony bitmap vote.

    ``bitmap_terrain`` is ``TerrainResult.by_province`` — CK3 province id -> CK3
    terrain key from the pixels.  ``overrides`` is CK2 province id -> the CK2
    category on its ``terrain =`` line.  ``refs`` says which CK3 province
    belongs to which CK2 county and which one is the capital.

    Returns a **new** terrain map; the input is not mutated, so a caller can
    diff the two (that is what ``docs/step_map_terrain.md`` §5 does for the
    heightmap-detail and tree-scatter shift).
    """
    weak = frozenset(weak_classes)
    out = dict(bitmap_terrain)
    res = HistoryTerrainResult(terrain=out)

    usable_counties: set[int] = set()
    by_ck3 = {r.ck3_id: r for r in refs}
    for ck3_id in sorted(bitmap_terrain):
        ref = by_ck3.get(ck3_id)
        bitmap = bitmap_terrain[ck3_id]
        if ref is None:
            res.outcomes["no_override"] += 1
            continue
        ck2_cat = overrides.get(ref.ck2_id, "")
        if not ck2_cat:
            res.outcomes["no_override"] += 1
            continue
        rule = rules.get(ck2_cat)
        if rule is None:
            res.unmapped[ck2_cat] += 1
            outcome = "kept_unmapped"
            final = bitmap
        elif not rule.applies:
            outcome = "kept_rule"
            final = bitmap
        else:
            usable_counties.add(ref.ck2_id)
            want = rule.ck3_terrain
            if want == bitmap:
                outcome = "already_agreed"
                final = bitmap
            elif ref.is_capital:
                outcome = "applied_capital"
                final = want
            elif bitmap in weak:
                outcome = "applied_weak_bitmap"
                final = want
            else:
                outcome = "kept_strong_bitmap"
                final = bitmap
        out[ck3_id] = final
        res.outcomes[outcome] += 1
        if final != bitmap:
            res.changed += 1
            res.transitions[(bitmap, final)] += 1
        res.rows.append(
            AppliedRow(
                ck3_id=ck3_id,
                ck2_id=ref.ck2_id,
                county=ref.county,
                barony=ref.barony,
                is_capital=ref.is_capital,
                ck2_terrain=ck2_cat,
                bitmap_ck3=bitmap,
                final_ck3=final,
                outcome=outcome,
            )
        )
    res.counties_with_override = len(usable_counties)
    return res


def render_evidence_csv(res: HistoryTerrainResult) -> str:
    """``docs/evidence/terrain_history_baronies.csv`` — one row per affected province."""
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(
        [
            "ck3_id",
            "ck2_province",
            "county",
            "barony",
            "is_capital",
            "ck2_history_terrain",
            "bitmap_ck3_terrain",
            "final_ck3_terrain",
            "outcome",
        ]
    )
    for r in res.rows:
        w.writerow(
            [
                r.ck3_id,
                r.ck2_id,
                r.county,
                r.barony,
                "yes" if r.is_capital else "no",
                r.ck2_terrain,
                r.bitmap_ck3,
                r.final_ck3,
                r.outcome,
            ]
        )
    return buf.getvalue()
