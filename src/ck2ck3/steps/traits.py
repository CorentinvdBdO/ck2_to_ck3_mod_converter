"""Step `traits`: port every CK2 trait to CK3 1.19 syntax.

Owns `common/traits` and `gfx/interface/icons/traits`. Rules and counts live in
`docs/step_traits.md`; the decision layer is `ck2ck3.traits`.

Three outputs:

* `common/traits/fae_traits.txt` — the live traits, CK2 ids kept verbatim so
  the localisation lane only renames the loc key. Its header lists every CK2
  trait that was deduped to a CK3 vanilla trait instead of being redefined.
* `common/traits/fae_traits_unported.txt` — the traits classified `comment`,
  written as commented-out blocks so nothing is lost and a submod can revive
  one by stripping the `# `.
* `gfx/interface/icons/traits/<trait>.dds` — the CK2 icon of each ported trait.

`ctx.data["traits"]` hands the characters/events lanes the rename map.
"""

from __future__ import annotations

from ..context import Context, StepResult
from ..pdx import Block, Node
from ..traits import CK3_ICON_DIR, build_plan, convert_plan, load_tables, unported

DESCRIPTION = "port CK2 traits to CK3 1.19 (dedupe vanilla, comment the rest)"
OUTPUTS = ("common/traits", "gfx/interface/icons/traits")

LIVE_FILE = "common/traits/fae_traits.txt"
UNPORTED_FILE = "common/traits/fae_traits_unported.txt"


def run(ctx: Context) -> StepResult:
    tables = load_tables(ck3_traits_file=ctx.ck3("common", "traits", "00_traits.txt"))
    plan = build_plan(ctx.ck2_mod, tables)
    for message in plan.warnings:
        ctx.warn(f"traits: {message}")

    converted, converter = convert_plan(plan, tables)
    for item in converted:
        for message in item.warnings:
            ctx.warn(f"traits: {message}")

    # -- the live file ----------------------------------------------------
    block = Block(multiline=True)
    current_file = ""
    for item in converted:
        if item.source_file != current_file:
            current_file = item.source_file
            lead = [f"# ---- from CK2 common/traits/{current_file} ----"]
        else:
            lead = []
        node = Node(
            key=item.ck2_trait,
            value=item.block,
            blank_before=True,
            leading_comments=lead,
        )
        block.append(node)
    if block.entries:
        block.entries[0].leading_comments = (
            _live_header(plan, converted) + block.entries[0].leading_comments
        )
        block.entries[0].blank_before = False
    ctx.write_script(
        LIVE_FILE, block, source=f"{ctx.ck2_mod.name}/common/traits"
    )

    # -- the commented file ----------------------------------------------
    dead = Block(multiline=True)
    for name in plan.commented():
        dead.append(
            Node(
                key=name,
                value=plan.traits[name],
                blank_before=True,
                leading_comments=[f"---- {plan.source_file[name]} ----"],
            )
        )
    ctx.write_commented_script(
        UNPORTED_FILE,
        dead,
        source=f"{ctx.ck2_mod.name}/common/traits",
        preamble=[
            "# CK2 traits with no CK3 landing place, kept as dead script so",
            "# nothing is lost. Reason per trait: "
            "docs/evidence/traits_unported.csv.",
            "# A submod revives a block by stripping the '# ' prefixes and",
            "# porting its keys through mappings/trait_fields.csv.",
        ],
    )

    # -- icons -------------------------------------------------------------
    copied = 0
    for name, source in sorted(plan.icon_source.items()):
        ctx.copy_file(f"{CK3_ICON_DIR}/{name}.dds", source)
        copied += 1
    if copied:
        ctx.warn(
            f"traits: {copied} CK2 trait icons copied unchanged at 24x24; CK3 1.19 "
            "vanilla trait icons are 120x120 "
            "(gfx/interface/icons/traits/brave.dds) - the submod must rescale"
        )

    renames = plan.rename_map
    ctx.data["traits"] = {
        "renames": renames,
        "live": sorted(plan.live()),
        "unported": [u.ck2_trait for u in unported(plan)],
        # `drop`/`sexuality` vanilla-table rows: never live, never a rename.
        # The characters port needs these to emit the right comment/key
        # (docs/step_traits.md rule 2).
        "drop_notes": {d.ck2_trait: d.note for d in plan.drops},
        "sexuality": {s.ck2_trait: s.ck3_trait for s in plan.sexualities},
    }

    counts = {
        "ck2_traits": len(plan.traits),
        "ported": len(converted),
        "race": sum(1 for c in converted if c.kind == "race_trait"),
        "deduped": len(renames),
        "dropped": len(plan.drops),
        "sexuality": len(plan.sexualities),
        "commented": len(plan.commented()),
        "icons": copied,
        **converter.counts,
    }
    return StepResult(
        summary=(
            f"{len(converted)} traits ported ({counts['race']} race), "
            f"{len(renames)} deduped to CK3 vanilla, "
            f"{len(plan.drops)} dropped (no CK3 counterpart), "
            f"{len(plan.sexualities)} became a CK3 sexuality, "
            f"{len(plan.commented())} commented out"
        ),
        counts=counts,
    )


def _live_header(plan, converted) -> list[str]:
    """The comment block that opens `fae_traits.txt`: counts and the dedupe list.

    Emitted as the leading comments of the first trait so it goes through the
    writer like any other content (the step never writes bytes itself).
    """
    lines = [
        f"# {len(converted)} traits ported, {len(plan.commented())} commented out in",
        "# fae_traits_unported.txt, "
        f"{len(plan.rename_map)} deduped to a CK3 vanilla trait.",
        "# Trait ids are the CK2 ids verbatim: the localisation lane renames the",
        "# loc key (<id> -> trait_<id>), never the id.",
        "#",
        "# Deduped - NOT redefined here, use the CK3 id "
        "(mappings/trait_id_map.csv):",
    ]
    for rename in sorted(plan.renames, key=lambda r: r.ck2_trait):
        lines.append(f"#   {rename.ck2_trait} -> {rename.ck3_trait} ({rename.status})")
    if plan.sexualities:
        lines += [
            "#",
            f"# {len(plan.sexualities)} CK2 trait(s) are not a CK3 trait at all; a",
            "# character gets a CK3 `sexuality` history key instead "
            "(docs/step_traits.md rule 2):",
        ]
        for s in sorted(plan.sexualities, key=lambda r: r.ck2_trait):
            lines.append(f"#   {s.ck2_trait} -> sexuality = {s.ck3_trait}")
    if plan.drops:
        lines += [
            "#",
            f"# {len(plan.drops)} CK2 vanilla traits have no CK3 landing place at all",
            "# (not even a near miss): a character loses the trait, with a "
            "'# CK2 trait",
            "# x: no CK3 counterpart' comment in its history "
            "(docs/step_traits.md rule 2):",
        ]
        for d in sorted(plan.drops, key=lambda r: r.ck2_trait):
            lines.append(f"#   {d.ck2_trait}")
    lines.append("#")
    return lines
