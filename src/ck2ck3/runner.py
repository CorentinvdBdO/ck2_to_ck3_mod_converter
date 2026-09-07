"""Run steps in order and write the run log to ``docs/evidence/last_run.md``."""

from __future__ import annotations

import datetime as dt
import logging
import time
import warnings
from dataclasses import dataclass
from pathlib import Path

from . import steps as steps_registry
from .config import REPO_ROOT, Config
from .context import Context, StepResult
from .pdx.encoding import EncodingWarning

#: Where the runner records what happened, in the converter repository.
EVIDENCE = REPO_ROOT / "docs" / "evidence" / "last_run.md"


@dataclass
class StepRun:
    name: str
    result: StepResult
    seconds: float
    files: int
    error: str | None = None


def run_steps(
    config: Config,
    names: list[str],
    *,
    dry_run: bool = False,
    logger: logging.Logger | None = None,
) -> tuple[Context, list[StepRun]]:
    """Run ``names`` against ``config``; stop at the first failing step."""
    ctx = Context(config, dry_run=dry_run, logger=logger)
    runs: list[StepRun] = []
    for name in names:
        module = steps_registry.load(name)
        started = time.perf_counter()
        before = len(ctx.written)
        try:
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always", EncodingWarning)
                raw = module.run(ctx)
        except Exception as exc:  # noqa: BLE001 - reported, then re-raised
            runs.append(
                StepRun(
                    name=name,
                    result=StepResult(summary=f"failed: {exc}"),
                    seconds=time.perf_counter() - started,
                    files=len(ctx.written) - before,
                    error=f"{type(exc).__name__}: {exc}",
                )
            )
            raise
        result = _as_result(raw, name)
        for warning in caught:
            ctx.warnings.append(f"{name}: {warning.message}")
        runs.append(
            StepRun(
                name=name,
                result=result,
                seconds=time.perf_counter() - started,
                files=len(ctx.written) - before,
            )
        )
        ctx.log.info("%-12s %s", name, result.summary)
    return ctx, runs


def _as_result(raw: object, name: str) -> StepResult:
    if isinstance(raw, StepResult):
        return raw
    if isinstance(raw, str):
        return StepResult(summary=raw)
    if raw is None:
        return StepResult(summary=f"{name} finished")
    raise TypeError(f"step {name!r} returned {type(raw).__name__}, expected StepResult")


def write_evidence(
    config: Config,
    ctx: Context,
    runs: list[StepRun],
    *,
    path: Path | None = None,
    dry_run: bool = False,
) -> Path:
    """Write the run log. Overwritten on every run, never appended."""
    path = Path(path) if path is not None else EVIDENCE
    stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    total = sum(r.seconds for r in runs)
    lines = [
        "# Last converter run",
        "",
        "Overwritten by `ck2ck3` on every run; do not edit by hand.",
        "",
        f"- when: {stamp}",
        f"- config: `{config.path}`",
        f"- mode: {'dry run (nothing written)' if dry_run else 'write'}",
        f"- source: `{config.ck2_mod}`",
        f"- output: `{config.out}`",
        f"- steps: {', '.join(r.name for r in runs) or 'none'}",
        f"- files written: {len(ctx.written)}",
        f"- warnings: {len(ctx.warnings)}",
        f"- total time: {total:.1f} s",
        "",
        "## Steps",
        "",
        "| step | seconds | files | counts | summary |",
        "|---|---|---|---|---|",
    ]
    for run in runs:
        state = run.error or run.result.summary
        lines.append(
            f"| {run.name} | {run.seconds:.2f} | {run.files} | "
            f"{run.result.count_line() or '-'} | {state} |"
        )
    if ctx.warnings:
        lines += ["", "## Warnings", ""]
        lines += [f"- {w}" for w in ctx.warnings[:200]]
        if len(ctx.warnings) > 200:
            lines.append(f"- … {len(ctx.warnings) - 200} more")
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
