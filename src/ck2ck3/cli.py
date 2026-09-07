"""``ck2ck3`` command line.

    uv run ck2ck3 --config configs/faerun.toml [--steps map,titles] [--dry-run]

See `docs/cli.md`.
"""

from __future__ import annotations

import argparse
import logging
import sys

from . import steps as steps_registry
from .config import Config, ConfigError
from .runner import run_steps, write_evidence


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ck2ck3",
        description="Convert a CK2 total-conversion mod into a CK3 mod.",
    )
    parser.add_argument(
        "--config",
        default="configs/faerun.toml",
        help="TOML config file (default: %(default)s)",
    )
    parser.add_argument(
        "--steps",
        help="comma-separated steps to run, or 'all' (default: the standard order)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report what each step would write, touch nothing",
    )
    parser.add_argument(
        "--out",
        help="override [paths] out (useful for a throwaway output folder)",
    )
    parser.add_argument(
        "--list-steps",
        action="store_true",
        help="list the registered steps and exit",
    )
    parser.add_argument(
        "--no-evidence",
        action="store_true",
        help="do not write docs/evidence/last_run.md",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="-v for per-file logging, -vv for debug",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    level = (logging.WARNING, logging.INFO, logging.DEBUG)[min(args.verbose, 2)]
    logging.basicConfig(level=level, format="%(message)s", stream=sys.stderr)
    logger = logging.getLogger("ck2ck3")

    if args.list_steps:
        default = set(steps_registry.DEFAULT_ORDER)
        for name in steps_registry.available():
            mark = "*" if name in default else " "
            print(f"{mark} {name:<14} {steps_registry.describe(name)}")
        print("\n* = part of the default order")
        return 0

    try:
        config = Config.load(args.config, out=args.out)
        names = steps_registry.resolve(
            args.steps.split(",") if args.steps else None
        )
    except (ConfigError, steps_registry.UnknownStep, steps_registry.BadStep) as exc:
        print(f"ck2ck3: {exc}", file=sys.stderr)
        return 2

    print(
        f"ck2ck3 {config.name} — {'dry run' if args.dry_run else 'writing'} to {config.out}"
    )
    ctx, runs = run_steps(config, names, dry_run=args.dry_run, logger=logger)
    for run in runs:
        print(f"  {run.name:<14} {run.result.summary} [{run.seconds:.2f}s]")
    print(
        f"{len(ctx.written)} files {'would be ' if args.dry_run else ''}written, "
        f"{len(ctx.warnings)} warnings"
    )
    if not args.no_evidence:
        path = write_evidence(config, ctx, runs, dry_run=args.dry_run)
        print(f"run log: {path}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
