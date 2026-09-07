"""The input tables of the trait port, loaded once and validated on load.

Nothing here decides anything: every row comes from `mappings/` (produced by
the `mappings` lane), from `docs/evidence/faerun_custom_traits.csv` (produced by
`scripts/classify_faerun_traits.py`) or from `overrides/` (human input). The
converter refuses to run when a CK2 key is missing from the tables, so coverage
can never silently regress — see `docs/step_traits.md`.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

#: Repository root, i.e. the folder holding `mappings/` and `overrides/`.
REPO_ROOT = Path(__file__).resolve().parents[3]

#: CK2 keys whose *value is a block of modifiers* that CK3 flattens onto the
#: trait. `mappings/trait_fields.csv` marks them `none` with the note "its keys
#: become flat trait modifiers"; this set is the machine-readable form of that
#: note. `province` and `opinions` are deliberately absent: a CK3 trait is
#: character scope only (`docs/mapping_modifiers.md`), so those blocks are
#: commented whole.
FLATTENED_BLOCKS = frozenset({"combat", "command_modifier", "country"})

#: CK3 `category` is single-valued while CK2 uses independent booleans, so a
#: trait that sets several needs a precedence. Most specific first.
CATEGORY_PRECEDENCE = (
    "childhood",
    "education",
    "health",
    "lifestyle",
    "commander",
    "personality",
)

#: CK2 boolean -> the CK3 `category` value it asks for.
CATEGORY_OF_CK2_KEY = {
    "childhood": "childhood",
    "education": "education",
    "is_health": "health",
    "lifestyle": "lifestyle",
    "leader": "commander",
    "personality": "personality",
}


def _read(path: Path) -> list[dict[str, str]]:
    """Read a table, skipping `#` comment lines (`overrides/` files carry a
    header block explaining the columns and how sure the numbers are)."""
    with path.open(encoding="utf-8", newline="") as handle:
        lines = [line for line in handle if not line.lstrip().startswith("#")]
    return [dict(row) for row in csv.DictReader(lines)]


@dataclass(frozen=True)
class Mapping:
    """One row of `modifiers.csv` or `trait_fields.csv`."""

    ck2_key: str
    ck3_key: str
    status: str
    note: str
    scale: float = 1.0

    @property
    def mapped(self) -> bool:
        """False for a `none` row, i.e. one that must become a comment."""
        return self.status != "none" and bool(self.ck3_key)

    @property
    def placeholder(self) -> bool:
        """True for `<ck3_culture>_opinion` & friends: unresolved until the
        cultures/religions lane produces its name map."""
        return "<" in self.ck3_key


@dataclass
class Tables:
    fields: dict[str, Mapping]
    modifiers: dict[str, Mapping]
    #: CK2 vanilla trait -> CK3 vanilla trait (the 112 rows of `00_traits.txt`).
    vanilla: dict[str, Mapping]
    #: Faerûn-specific trait -> `port` | `race_trait` | `comment`.
    treatment: dict[str, str]
    #: CK2 race-trait id -> the lifespan extras (`overrides/race_lifespan.csv`).
    race_lifespan: dict[str, "RaceLifespan"] = field(default_factory=dict)
    #: Every trait id declared by CK3 1.19 `common/traits/00_traits.txt`.
    ck3_trait_ids: frozenset[str] = frozenset()

    def field_of(self, key: str) -> Mapping | None:
        return self.fields.get(key)

    def modifier_of(self, key: str) -> Mapping | None:
        return self.modifiers.get(key)


@dataclass(frozen=True)
class RaceLifespan:
    ck2_trait: str
    race: str
    dnd_max_age: int | None
    life_expectancy: int | None
    immortal: bool
    note: str


def load_tables(
    root: Path | None = None, ck3_traits_file: Path | None = None
) -> Tables:
    """Load every input table. ``ck3_traits_file`` is CK3 `00_traits.txt`."""
    root = root or REPO_ROOT
    fields = {
        row["ck2_key"]: Mapping(
            ck2_key=row["ck2_key"],
            ck3_key=row["ck3_key"],
            status=row["status"],
            note=row["note"],
        )
        for row in _read(root / "mappings" / "trait_fields.csv")
        if row["ck2_key"] != "(none)"
    }
    modifiers = {
        row["ck2_key"]: Mapping(
            ck2_key=row["ck2_key"],
            ck3_key=row["ck3_key"],
            status=row["status"],
            note=row["note"],
            scale=float(row["scale"]) if row["scale"] else 1.0,
        )
        for row in _read(root / "mappings" / "modifiers.csv")
    }
    vanilla = {
        row["ck2_trait"]: Mapping(
            ck2_key=row["ck2_trait"],
            ck3_key=row["ck3_trait"],
            status=row["status"],
            note=row["note"],
        )
        for row in _read(root / "mappings" / "vanilla_traits.csv")
    }
    treatment = {
        row["ck2_trait"]: row["ck3_treatment"]
        for row in _read(root / "docs" / "evidence" / "faerun_custom_traits.csv")
    }
    lifespan = {}
    lifespan_path = root / "overrides" / "race_lifespan.csv"
    if lifespan_path.exists():
        for row in _read(lifespan_path):
            lifespan[row["ck2_trait"]] = RaceLifespan(
                ck2_trait=row["ck2_trait"],
                race=row["race"],
                dnd_max_age=int(row["dnd_max_age"]) if row["dnd_max_age"] else None,
                life_expectancy=(
                    int(row["life_expectancy"]) if row["life_expectancy"] else None
                ),
                immortal=row["immortal"].strip().lower() in {"yes", "true", "1"},
                note=row.get("note", ""),
            )
    ck3_ids: frozenset[str] = frozenset()
    if ck3_traits_file and Path(ck3_traits_file).exists():
        ck3_ids = frozenset(read_ck3_trait_ids(Path(ck3_traits_file)))
    return Tables(
        fields=fields,
        modifiers=modifiers,
        vanilla=vanilla,
        treatment=treatment,
        race_lifespan=lifespan,
        ck3_trait_ids=ck3_ids,
    )


def read_ck3_trait_ids(path: Path) -> set[str]:
    """Trait ids declared by a CK3 trait file (`@var` definitions skipped)."""
    from ..pdx import parse_file
    from ..pdx.encoding import CK3_ENCODING

    doc = parse_file(path, encoding=CK3_ENCODING)
    return {n.key for n in doc.nodes() if not n.key.startswith("@")}
