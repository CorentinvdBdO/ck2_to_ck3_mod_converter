#!/usr/bin/env python3
"""Per-duchy barony review sheets for a converted map.

    uv run scripts/barony_review_sheets.py [--config configs/faerun.toml]
                                           [--out docs/evidence/baronies]
                                           [--max-px 1024] [--samples d_a,d_b]

Runs the map step's barony planning again (it is deterministic, so the sheets
match the mod on disk) and writes one PNG per CK2 duchy plus ``index.md``.
Roughly 3 minutes and 40 MB for Faerûn's 979 duchies, so run it under nohup:

    nohup uv run scripts/barony_review_sheets.py \\
        > docs/evidence/barony_sheets.log 2>&1 &

Only ``index.md`` and the sheets named by ``--samples`` are committed; the rest
are gitignored (see ``.gitignore``). Editing loop for a human:
``docs/step_map_baronies.md`` §"Override workflow".
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from ck2ck3.config import Config  # noqa: E402
from ck2ck3.map import build as map_build  # noqa: E402
from ck2ck3.map import review  # noqa: E402
from ck2ck3.map.sink import DirectorySink  # noqa: E402


def _stamp(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default=str(REPO / "configs" / "faerun.toml"))
    ap.add_argument("--out", default=str(REPO / "docs" / "evidence" / "baronies"))
    ap.add_argument("--max-px", type=int, default=review.MAX_PX)
    ap.add_argument(
        "--samples",
        default="",
        help="comma-separated duchy keys to name as committed samples in index.md",
    )
    args = ap.parse_args(argv)

    from ck2ck3.steps import map as map_step

    cfg_cli = Config.load(args.config)
    ctx = _fake_context(cfg_cli)
    cfg = map_step._map_config(ctx)

    # dry_run: the mod on disk is not touched, only the sheets are written
    sink = DirectorySink(Path("/nonexistent"), dry_run=True, verbose=False)
    sink.info = _stamp  # type: ignore[method-assign]
    _stamp("planning the barony split (nothing is written to the mod)")
    report = map_build.run(cfg, sink, skip_images=True)

    out_dir = Path(args.out)
    samples = [s.strip() for s in args.samples.split(",") if s.strip()]
    n = review.write_all(
        out_dir=out_dir,
        plan=report["_plan"],
        ids=report["_ids"],
        raster=report["_raster"],
        tree=review.load_tree(cfg),
        max_px=args.max_px,
        log=_stamp,
        samples=samples,
    )
    _stamp(f"{n} duchy sheets + index.md -> {out_dir}")
    return 0


def _fake_context(cfg_cli):
    """The minimum a Context has to be for ``map_step._map_config``."""

    class Ctx:
        config = cfg_cli
        dry_run = True

        def ck2(self, *parts: str) -> Path:
            return cfg_cli.ck2_mod.joinpath(*parts)

    return Ctx()


if __name__ == "__main__":
    sys.exit(main())
