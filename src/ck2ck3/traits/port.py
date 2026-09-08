"""Read every CK2 trait file of a mod and decide what happens to each trait.

This module is the whole decision layer of the `traits` step, kept free of
`Context` so a test can run it against a fixture folder and so
`scripts/build_trait_tables.py` can regenerate the repository-side tables
without running the converter.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..pdx import Block, Document, parse_file
from .convert import Converted, Rename, TraitConverter, Unported, trait_groups
from .tables import Tables

#: CK2 wires a trait icon through an `interface/*.gfx` sprite named
#: `GFX_trait_<trait>` whose `texturefile` is the real path (`verified`:
#: `Faerun/Faerun/interface/fr_traits.gfx`). CK3 instead looks for
#: `gfx/interface/icons/traits/<trait>.dds` (`_traits.info:4`) and vanilla
#: writes the bare file name (`icon = reveler.dds`,
#: `game/common/traits/00_traits.txt:1064`).
CK3_ICON_DIR = "gfx/interface/icons/traits"


@dataclass
class Plan:
    """What the step is going to do, before anything is written."""

    #: CK2 trait id -> its block, in CK2 declaration order across all files.
    traits: dict[str, Block] = field(default_factory=dict)
    #: CK2 trait id -> the file it was declared in.
    source_file: dict[str, str] = field(default_factory=dict)
    #: CK2 trait id -> "port" | "race_trait" | "comment" | "rename".
    decision: dict[str, str] = field(default_factory=dict)
    #: Every dedupe: `exact`/`exact_id` (CK3 already has the concept) as well
    #: as `approx` and `nearest` (CK3 only has a near-equivalent, dedupe to it
    #: anyway per `docs/step_traits.md` rule 1 — "map to the existing CK3
    #: trait", never port a new one). No CK2 trait definition is emitted for
    #: any of these; a character gets the CK3 id.
    renames: list[Rename] = field(default_factory=list)
    #: `drop` rows of `mappings/vanilla_traits.csv`: no CK3 landing place at
    #: all, not even a near miss. The trait is not defined and the characters
    #: port turns `trait = x` into a `# CK2 trait x: no CK3 counterpart`
    #: comment.
    drops: list[Rename] = field(default_factory=list)
    #: `sexuality` rows: not a trait in CK3 at all. `ck3_trait` holds the CK3
    #: `sexuality` value; the characters port emits `sexuality = <value>`
    #: instead of `trait = x`.
    sexualities: list[Rename] = field(default_factory=list)
    #: CK2 trait id -> the CK2 icon file to copy (absolute path).
    icon_source: dict[str, Path] = field(default_factory=dict)
    #: CK2 trait id -> the CK3 `icon = ` value.
    icon_value: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    @property
    def rename_map(self) -> dict[str, str]:
        return {r.ck2_trait: r.ck3_trait for r in self.renames}

    def live(self) -> list[str]:
        return [n for n, d in self.decision.items() if d in ("port", "race_trait")]

    def commented(self) -> list[str]:
        return [n for n, d in self.decision.items() if d == "comment"]

    def classify_vanilla(self, name: str, vanilla, tables: Tables) -> None:
        """Apply the CK2-vanilla trait policy to one row of `vanilla_traits.csv`.

        The user's rule (`docs/DECISIONS.md` 2026-09-08, second entry): a CK2
        trait CK3 removed is **mapped to an existing CK3 trait**, never
        ported as a new one:

        * ``exact`` / ``approx`` / ``nearest`` — CK3 has the concept exactly,
          approximately, or only a near-equivalent covering the same niche:
          all three dedupe the same way — rename to the CK3 id, no CK2 trait
          definition is emitted. ``approx``/``nearest`` still go into
          `mappings/trait_id_map.csv` with their own status so a consumer can
          tell an exact match from a near one (docs/step_traits.md rule 1).
        * ``sexuality`` — not a CK3 trait at all; recorded in
          :attr:`sexualities` so the characters port can emit
          ``sexuality = <value>`` instead of a trait.
        * ``drop`` — no CK3 landing place, not even a near miss; recorded in
          :attr:`drops` so the characters port can leave a
          ``# CK2 trait x: no CK3 counterpart`` comment.

        A row whose two ids are equal is ``exact`` by definition.
        """
        if vanilla.status in ("exact", "approx", "nearest") and vanilla.mapped:
            self.decision[name] = "rename"
            self.renames.append(
                Rename(
                    ck2_trait=name,
                    ck3_trait=vanilla.ck3_key,
                    status=vanilla.status,
                    source="mappings/vanilla_traits.csv",
                    note=vanilla.note,
                )
            )
            return
        if vanilla.status == "sexuality":
            self.decision[name] = "sexuality"
            self.sexualities.append(
                Rename(
                    ck2_trait=name,
                    ck3_trait=vanilla.ck3_key or name,
                    status="sexuality",
                    source="mappings/vanilla_traits.csv",
                    note=vanilla.note,
                )
            )
            return
        if vanilla.status == "drop":
            self.decision[name] = "drop"
            self.drops.append(
                Rename(
                    ck2_trait=name,
                    ck3_trait="",
                    status="drop",
                    source="mappings/vanilla_traits.csv",
                    note=vanilla.note,
                )
            )
            return
        raise ValueError(
            f"mappings/vanilla_traits.csv: {name!r} has status {vanilla.status!r}, "
            "expected exact/approx/nearest/sexuality/drop"
        )


def read_ck2_traits(traits_dir: Path) -> tuple[dict[str, Block], dict[str, str]]:
    """Every trait of `common/traits/*.txt`, in file then declaration order."""
    traits: dict[str, Block] = {}
    origin: dict[str, str] = {}
    for path in sorted(Path(traits_dir).glob("*.txt")):
        doc: Document = parse_file(path)
        for node in doc.nodes():
            if not isinstance(node.value, Block):
                continue
            traits[node.key] = node.value
            origin[node.key] = path.name
    return traits, origin


def collect_icons(mod_dir: Path) -> dict[str, str]:
    """`GFX_trait_<trait>` -> its `texturefile`, from every `interface/*.gfx`."""
    out: dict[str, str] = {}
    for path in sorted(Path(mod_dir).glob("interface/*.gfx")):
        try:
            doc = parse_file(path)
        except Exception:  # a .gfx the parser cannot read is not fatal here
            continue
        for sprites in doc.nodes("spriteTypes"):
            if not isinstance(sprites.value, Block):
                continue
            for sprite in sprites.value.nodes("spriteType"):
                if not isinstance(sprite.value, Block):
                    continue
                name = sprite.value.get("name")
                texture = sprite.value.get("texturefile")
                if (
                    isinstance(name, str)
                    and isinstance(texture, str)
                    and name.startswith("GFX_trait_")
                ):
                    out[name[len("GFX_trait_") :]] = texture
    return out


def build_plan(mod_dir: Path, tables: Tables) -> Plan:
    """Classify every CK2 trait. Writes nothing."""
    mod_dir = Path(mod_dir)
    plan = Plan()
    plan.traits, plan.source_file = read_ck2_traits(mod_dir / "common" / "traits")
    sprites = collect_icons(mod_dir)

    for name in plan.traits:
        vanilla = tables.vanilla.get(name)
        if vanilla is not None:
            plan.classify_vanilla(name, vanilla, tables)
            continue

        treatment = tables.treatment.get(name)
        if treatment in ("port", "race_trait", "comment"):
            if treatment != "comment" and name in tables.ck3_trait_ids:
                # Porting it would silently override a vanilla CK3 trait.
                plan.decision[name] = "rename"
                plan.renames.append(
                    Rename(
                        ck2_trait=name,
                        ck3_trait=name,
                        status="exact_id",
                        source="CK3 common/traits/00_traits.txt",
                        note="Faerûn-specific id that CK3 1.19 already declares; "
                        "kept as the vanilla trait rather than overriding it",
                    )
                )
                plan.warnings.append(
                    f"{name}: classified {treatment} but CK3 1.19 already declares "
                    "that id; deduped to vanilla instead of overriding it"
                )
            else:
                plan.decision[name] = treatment
            continue

        # Neither table knows it: a CK2-*vanilla* trait from a file other than
        # `00_traits.txt` (02_traits.txt, 04_battle_scars_…). Exact id match
        # against CK3 1.19 is the only evidence available, so it is the rule.
        if name in tables.ck3_trait_ids:
            plan.decision[name] = "rename"
            plan.renames.append(
                Rename(
                    ck2_trait=name,
                    ck3_trait=name,
                    status="exact_id",
                    source="CK3 common/traits/00_traits.txt",
                    note="CK2 vanilla trait outside 00_traits.txt whose id CK3 1.19 "
                    "declares verbatim",
                )
            )
        else:
            plan.decision[name] = "port"

    # Icons, for the traits that stay.
    for name in plan.live():
        texture = sprites.get(name) or f"gfx/traits/{name}.dds"
        source = mod_dir / texture
        if not source.exists():
            continue
        if source.suffix.lower() != ".dds":
            plan.warnings.append(
                f"{name}: CK2 icon {texture} is not a .dds; CK3 reads .dds only, "
                "no icon emitted (no format conversion in the converter)"
            )
            continue
        plan.icon_source[name] = source
        plan.icon_value[name] = f"{name}.dds"
    return plan


def convert_plan(plan: Plan, tables: Tables) -> tuple[list[Converted], TraitConverter]:
    """Convert every live trait of ``plan``, in CK2 order."""
    live = set(plan.live())
    groups = trait_groups({n: plan.traits[n] for n in plan.traits if n in live})
    converter = TraitConverter(
        tables,
        icons=plan.icon_value,
        live_traits=live,
        groups=groups,
        renames=plan.rename_map,
    )
    out: list[Converted] = []
    for name, block in plan.traits.items():
        if name not in live:
            continue
        out.append(
            converter.convert(
                name,
                block,
                source_file=plan.source_file[name],
                kind=plan.decision[name],
            )
        )
    return out, converter


def unported(plan: Plan) -> list[Unported]:
    return [
        Unported(
            ck2_trait=name,
            source_file=plan.source_file[name],
            reason="classified `comment` in docs/evidence/faerun_custom_traits.csv "
            "(Faerûn biography/roleplaying marker read only by CK2 events)",
        )
        for name in plan.commented()
    ]


def loc_key_renames(plan: Plan) -> list[tuple[str, str]]:
    """CK2 loc key -> CK3 loc key for every trait that keeps its CK2 id.

    CK2 localises a trait under its bare id (`creature_human`,
    `creature_human_desc`; `verified` in
    `Faerun/Faerun/localisation/traits_racial.csv:2`), CK3 under
    `trait_<id>` / `trait_<id>_desc` (`verified`
    `game/localization/english/traits_l_english.yml:277`). Deduped traits get a
    row too, pointing at the *CK3* trait, so the CK2 text still lands on the
    trait the characters lane will reference.
    """
    rows: list[tuple[str, str]] = []
    seen: set[str] = set()
    targets = {name: name for name in plan.live()}
    targets.update(plan.rename_map)
    for ck2, ck3 in targets.items():
        for suffix in ("", "_desc"):
            key = f"{ck2}{suffix}"
            if key in seen:
                continue
            seen.add(key)
            rows.append((key, f"trait_{ck3}{suffix}"))
    return sorted(rows)
