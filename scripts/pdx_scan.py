#!/usr/bin/env python3
"""Parse every Paradox script file of a CK2 mod and report failures.

Usage:
    uv run scripts/pdx_scan.py [mod_dir] [--lenient] [--roundtrip N] [--limit N]

Prints one line per failure (``file:line:col: message``) and a summary. Used to
drive `docs/formats_pdx_quirks.md`; the pytest integration test asserts the
same thing.
"""

from __future__ import annotations

import argparse
import random
import sys
import time
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ck2ck3.ck2mod import script_files  # noqa: E402
from ck2ck3.pdx import (  # noqa: E402
    PdxSyntaxError,
    parse,
    read_text,
    structurally_equal,
    write,
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("mod_dir", nargs="?", default="Faerun/Faerun", type=Path)
    ap.add_argument("--lenient", action="store_true", help="collect problems, do not raise")
    ap.add_argument("--roundtrip", type=int, default=0, help="round-trip N random files")
    ap.add_argument("--limit", type=int, default=0, help="stop after N files")
    ap.add_argument("--seed", type=int, default=20260907)
    args = ap.parse_args()

    files = script_files(args.mod_dir)
    if args.limit:
        files = files[: args.limit]
    if not files:
        print(f"no script files under {args.mod_dir}", file=sys.stderr)
        return 2

    failures: list[str] = []
    problems: list[str] = []
    encodings: dict[str, int] = {}
    bytes_read = 0
    start = time.perf_counter()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for path in files:
            text, used = read_text(path)
            encodings[used] = encodings.get(used, 0) + 1
            bytes_read += len(text)
            try:
                doc = parse(text, str(path), lenient=args.lenient)
            except PdxSyntaxError as exc:
                failures.append(str(exc))
                continue
            problems.extend(str(p) for p in doc.problems)
    elapsed = time.perf_counter() - start

    rt_failures: list[str] = []
    if args.roundtrip:
        rng = random.Random(args.seed)
        sample = rng.sample(files, min(args.roundtrip, len(files)))
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            for path in sample:
                text, _ = read_text(path)
                try:
                    first = parse(text, str(path), lenient=True)
                    second = parse(write(first), str(path), lenient=True)
                except PdxSyntaxError as exc:
                    rt_failures.append(f"{path}: reparse failed: {exc}")
                    continue
                if not structurally_equal(first, second):
                    rt_failures.append(f"{path}: round trip not structurally equal")

    for line in failures:
        print(f"FAIL {line}")
    for line in problems:
        print(f"PROB {line}")
    for line in rt_failures:
        print(f"RTFAIL {line}")
    print(
        f"parsed {len(files) - len(failures)}/{len(files)} files, "
        f"{bytes_read / 1e6:.1f} MB, {elapsed:.1f} s, "
        f"encodings={encodings}, failures={len(failures)}, "
        f"problems={len(problems)}, roundtrip_failures={len(rt_failures)}"
    )
    return 1 if failures or rt_failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
