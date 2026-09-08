"""Referential-integrity checks over the converted characters and dynasties.

CK3 fails loudly on a dangling ``father``/``mother``/``employer``/spouse id and
silently on an unknown trait, so these run as part of the step (warnings in the
run log) *and* as pytest assertions over the real Faerûn clone.

Every check returns a list of one-line problems; an empty list is a pass.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Iterable

from .characters import CharacterFacts

#: How many examples of one problem kind to keep; the count is always exact.
SAMPLE = 5


@dataclass
class Issue:
    kind: str
    detail: str


@dataclass
class IntegrityResult:
    counts: Counter = field(default_factory=Counter)
    issues: list[Issue] = field(default_factory=list)

    def add(self, kind: str, detail: str) -> None:
        self.counts[kind] += 1
        if self.counts[kind] <= SAMPLE:
            self.issues.append(Issue(kind, detail))

    def summary_lines(self) -> list[str]:
        """One line per problem kind, count first, then up to SAMPLE examples."""
        lines: list[str] = []
        for kind, total in sorted(self.counts.items(), key=lambda kv: -kv[1]):
            samples = [i.detail for i in self.issues if i.kind == kind]
            shown = "; ".join(samples)
            more = "" if total <= len(samples) else f" (+{total - len(samples)} more)"
            lines.append(f"{kind}: {total} - {shown}{more}")
        return lines

    @property
    def clean(self) -> bool:
        return not self.counts


def check(
    facts: dict[str, CharacterFacts],
    dynasty_ids: Iterable[str],
    known_traits: Iterable[str],
) -> IntegrityResult:
    """Every character reference, dynasty reference, trait and date."""
    result = IntegrityResult()
    dynasties = set(dynasty_ids)
    traits = set(known_traits)

    for char in facts.values():
        for kind, target in char.refs:
            if target not in facts:
                result.add(
                    f"dangling {kind}",
                    f"{char.ck3_id} ({char.source}) -> {target}",
                )
        if char.dynasty is not None and char.dynasty not in dynasties:
            result.add(
                "unknown dynasty",
                f"{char.ck3_id} ({char.source}) -> {char.dynasty}",
            )
        for trait in char.traits:
            if trait not in traits:
                result.add("unknown trait", f"{char.ck3_id} -> {trait}")
        if char.birth is None:
            result.add("no birth date", char.ck3_id)
        elif char.death is not None and _tuple(char.death) < _tuple(char.birth):
            result.add(
                "death before birth",
                f"{char.ck3_id} born {char.birth} died {char.death}",
            )
        for kind, target in char.refs:
            # CK3 1.19 has no same-gender marriage: `add_spouse` between two
            # characters of one gender is `error(wrong-gender)` and the line is
            # ignored. Faerûn has a handful, flagged in CK2 itself with
            # `Audax Validator "." Ignore_NEXT`. Reported, not rewritten: the
            # port is one pass per file and the partner may live in another.
            if kind not in ("add_spouse", "add_matrilineal_spouse", "marry"):
                continue
            other = facts.get(target)
            if other is not None and other.female == char.female:
                result.add(
                    "same-sex spouse",
                    f"{char.ck3_id} ({char.source}) {kind} {target}",
                )
        if char.father is not None and char.father == char.ck3_id:
            result.add("self as father", char.ck3_id)
        if char.mother is not None and char.mother == char.ck3_id:
            result.add("self as mother", char.ck3_id)

    return result


def _tuple(date: object) -> tuple[int, int, int]:
    return (date.year, date.month, date.day)  # type: ignore[attr-defined]
