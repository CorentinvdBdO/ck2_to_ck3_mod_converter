"""Write ``descriptor.mod`` for the generated mod.

Shape copied from Elder Kings 2 (`verified` 2026-09-07,
``workshop/content/1158310/2887120253/descriptor.mod``): ``version``, a
``tags`` block, ``name``, ``supported_version``, then one ``replace_path`` line
per replaced vanilla folder — a repeated key, which is exactly why the parse
tree keeps duplicate keys in order.
"""

from __future__ import annotations

from ..context import Context, StepResult
from ..pdx import Block, Item, Node

DESCRIPTION = "write descriptor.mod (name, version, tags, replace_path list)"
OUTPUTS: tuple[str, ...] = ("descriptor.mod",)


def build(ctx: Context) -> Block:
    config = ctx.config
    tags = Block(
        entries=[Item(value=t, quoted=True) for t in config.tags],
        multiline=True,
    )
    entries = [
        Node(key="version", value=config.version, quoted_value=True),
        Node(key="tags", value=tags),
        Node(key="name", value=config.name, quoted_value=True),
        Node(
            key="supported_version",
            value=config.supported_version,
            quoted_value=True,
        ),
    ]
    for index, replaced in enumerate(config.replace_paths):
        entries.append(
            Node(
                key="replace_path",
                value=replaced,
                quoted_value=True,
                blank_before=index == 0,
            )
        )
    return Block(entries=entries)


def run(ctx: Context) -> StepResult:
    block = build(ctx)
    # No generated-by banner: descriptor.mod is read by the launcher and
    # vanilla / Elder Kings 2 keep it free of comments.
    path = ctx.write_script("descriptor.mod", block, header=False)
    return StepResult(
        summary=(
            f"descriptor.mod: {ctx.config.name!r} {ctx.config.version} "
            f"for CK3 {ctx.config.supported_version}, "
            f"{len(ctx.config.replace_paths)} replace_path"
        ),
        counts={
            "tags": len(ctx.config.tags),
            "replace_paths": len(ctx.config.replace_paths),
        },
        written=[path],
    )
