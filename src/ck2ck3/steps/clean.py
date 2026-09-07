"""Delete the generated content of the output mod.

Removes every top-level entry that is not on :data:`ck2ck3.ck3mod.PROTECTED`
(``.git``, ``README.md``, ``descriptor.mod``, ``LICENSE``, ``docs``,
``thumbnail.png``, git plumbing). Refuses to touch a folder that does not look
like the generated mod, so a mistyped ``[paths] out`` cannot wipe a source tree.
"""

from __future__ import annotations

from ..ck3mod import PROTECTED, looks_like_a_mod, remove, removable
from ..context import Context, StepResult

DESCRIPTION = "delete generated folders in the output mod (keeps .git, README, descriptor)"
#: Owns the whole output mod, minus the protected entries.
OUTPUTS: tuple[str, ...] = ("*",)


def run(ctx: Context) -> StepResult:
    folder = ctx.out
    if not looks_like_a_mod(folder):
        ctx.warn(
            f"{folder} holds no descriptor.mod, README.md or .git: refusing to clean it"
        )
        return StepResult(
            summary=f"refused to clean {folder} (does not look like the generated mod)",
            skipped=True,
        )
    targets = removable(folder)
    removed_dirs = sum(1 for t in targets if t.is_dir())
    for target in targets:
        if not ctx.dry_run:
            remove(target)
        ctx.info(f"{'would remove' if ctx.dry_run else 'removed'} {target}")
    kept = sorted(p.name for p in folder.iterdir() if p.name in PROTECTED) if folder.is_dir() else []
    return StepResult(
        summary=f"cleaned {folder}: removed {len(targets)} entries, kept {', '.join(kept) or 'nothing'}",
        counts={"removed": len(targets), "removed_dirs": removed_dirs, "kept": len(kept)},
    )
