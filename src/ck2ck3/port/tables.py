"""The lookup tables the character/dynasty port is driven by.

Every table is a CSV in ``mappings/`` (or ``docs/evidence/`` for the trait
classification the traits lane produced), so a mapping decision is reviewable
as a diff and testable without running the converter.

+---------------------------------------+-------------------------------------+
| file                                  | what it decides                     |
+=======================================+=====================================+
| ``mappings/character_effects.csv``    | per-key CK3 name and shape          |
| ``mappings/death_reasons.csv``        | ``death_reason`` value remap        |
| ``mappings/nicknames.csv``            | ``give_nickname`` value remap       |
| ``mappings/vanilla_traits.csv``       | CK2 vanilla trait -> CK3 trait      |
| ``docs/evidence/faerun_custom_traits``| which Faerûn traits the mod keeps   |
| ``mappings/trait_id_map.csv``         | *optional* post-pass id remap       |
+---------------------------------------+-------------------------------------+

``mappings/trait_id_map.csv`` is written by the parallel ``traits`` lane and
may not exist yet; when it is missing every trait id is passed through
unchanged (see :meth:`Tables.trait`).
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

#: Repository root, so a table can be loaded without a Context.
REPO_ROOT = Path(__file__).resolve().parents[3]

CHARACTER_EFFECTS = "mappings/character_effects.csv"
DEATH_REASONS = "mappings/death_reasons.csv"
NICKNAMES = "mappings/nicknames.csv"
VANILLA_TRAITS = "mappings/vanilla_traits.csv"
FAERUN_TRAITS = "docs/evidence/faerun_custom_traits.csv"
TRAIT_ID_MAP = "mappings/trait_id_map.csv"

#: What a CK2 key with no CK3 equivalent falls back to.
UNKNOWN_DEATH_REASON = "death_natural_causes"


@dataclass(frozen=True)
class KeyRule:
    """One row of ``mappings/character_effects.csv``."""

    ck2_key: str
    level: str          # "history" or "effect"
    ck3_key: str
    form: str
    status: str
    note: str

    @property
    def drops(self) -> bool:
        return self.form == "comment"

    @property
    def relation_reason(self) -> str | None:
        """``friend_generic_history`` for ``form = relation:friend_...``."""
        return self.form.split(":", 1)[1] if self.form.startswith("relation:") else None


@dataclass
class Tables:
    """Every lookup the port needs, loaded once per run."""

    rules: dict[tuple[str, str], KeyRule] = field(default_factory=dict)
    death_reasons: dict[str, str] = field(default_factory=dict)
    death_reason_status: dict[str, str] = field(default_factory=dict)
    nicknames: dict[str, str] = field(default_factory=dict)
    #: CK2 trait id -> CK3 trait id for traits the mod keeps.
    known_traits: dict[str, str] = field(default_factory=dict)
    #: Why a trait id is known: "vanilla", "faerun" or "race".
    trait_origin: dict[str, str] = field(default_factory=dict)
    #: Post-pass applied after `known_traits`; empty until the traits lane lands.
    trait_id_map: dict[str, str] = field(default_factory=dict)
    trait_id_map_present: bool = False

    # -- lookups -----------------------------------------------------------
    def rule(self, key: str, level: str) -> KeyRule | None:
        return self.rules.get((key, level))

    def death_reason(self, ck2_reason: str) -> tuple[str, str]:
        """``(ck3_reason, status)``; unknown falls back to natural causes."""
        if ck2_reason in self.death_reasons:
            return self.death_reasons[ck2_reason], self.death_reason_status[ck2_reason]
        return UNKNOWN_DEATH_REASON, "unknown"

    def nickname(self, ck2_nickname: str) -> str | None:
        """The CK3 nickname id, or ``None`` when it must become a comment."""
        return self.nicknames.get(ck2_nickname) or None

    def trait(self, ck2_trait: str) -> str | None:
        """The CK3 trait id, or ``None`` when the trait must become a comment.

        Two stages: the mod's own port set decides *whether* a trait survives,
        then ``mappings/trait_id_map.csv`` (the traits lane's dedupe table)
        decides what its final CK3 id is. The second stage is a no-op while
        that file is absent, which is why it is a post-pass and not baked in.
        """
        ck3 = self.known_traits.get(ck2_trait)
        if ck3 is None:
            return None
        return self.trait_id_map.get(ck3, ck3)


def _read(root: Path, rel: str) -> list[dict[str, str]]:
    path = root / rel
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def load_tables(root: Path | None = None) -> Tables:
    """Load every table from ``root`` (default: the repository root)."""
    root = root or REPO_ROOT
    tables = Tables()

    for row in _read(root, CHARACTER_EFFECTS):
        rule = KeyRule(
            ck2_key=row["ck2_key"],
            level=row["level"],
            ck3_key=row["ck3_key"],
            form=row["form"],
            status=row["status"],
            note=row["note"],
        )
        tables.rules[(rule.ck2_key, rule.level)] = rule

    for row in _read(root, DEATH_REASONS):
        tables.death_reasons[row["ck2_death_reason"]] = row["ck3_death_reason"]
        tables.death_reason_status[row["ck2_death_reason"]] = row["status"]

    for row in _read(root, NICKNAMES):
        if row["ck3_nickname"]:
            tables.nicknames[row["ck2_nickname"]] = row["ck3_nickname"]

    # Vanilla CK2 traits that have a CK3 counterpart.
    for row in _read(root, VANILLA_TRAITS):
        if row["status"] == "none" or not row["ck3_trait"]:
            continue
        tables.known_traits[row["ck2_trait"]] = row["ck3_trait"]
        tables.trait_origin[row["ck2_trait"]] = "vanilla"

    # Faerûn's own traits: the ones the mod ports keep their CK2 id.
    for row in _read(root, FAERUN_TRAITS):
        treatment = row["ck3_treatment"]
        if treatment not in ("port", "race_trait"):
            continue
        tables.known_traits[row["ck2_trait"]] = row["ck2_trait"]
        tables.trait_origin[row["ck2_trait"]] = (
            "race" if treatment == "race_trait" else "faerun"
        )

    trait_map = root / TRAIT_ID_MAP
    if trait_map.exists():
        tables.trait_id_map_present = True
        for row in _read(root, TRAIT_ID_MAP):
            source = row.get("ck2_trait") or row.get("from") or ""
            target = row.get("ck3_trait") or row.get("to") or ""
            if source and target:
                tables.trait_id_map[source] = target

    return tables
