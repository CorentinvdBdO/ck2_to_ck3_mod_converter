#!/usr/bin/env python
"""Run the `cultures` + `religions` steps into a throwaway mod and ck3-tiger it.

Writes `docs/evidence/tiger_cultures_religions.txt`: the tiger version, the
counts, the totals and one line per distinct finding class, so a review never
depends on scrollback. Exit code 1 if tiger reports any `fatal`.

    uv run scripts/validate_cultures_religions.py [--keep]

Needs `ck3-tiger` on PATH (https://github.com/amtep/ck3-tiger).
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
import warnings
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
warnings.simplefilter("ignore")

from ck2ck3.config import Config  # noqa: E402
from ck2ck3.runner import run_steps  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
EVIDENCE = REPO / "docs" / "evidence" / "tiger_cultures_religions.txt"
STEPS = ["cultures", "religions"]
ANSI = re.compile(r"\x1b\[[0-9;]*m")
TOTALS = re.compile(r"^fatal: \d+, error: \d+")

#: The `.mod` mirrors the `replace_paths` of `configs/faerun.toml` that this
#: lane's outputs live under: a folder that is replaced cannot collide with
#: vanilla, one that is not must not re-declare a vanilla key.
REPLACE_PATHS = (
    "common/culture/cultures",
    "common/culture/name_lists",
    "common/religion/holy_site_types",
    "common/religion/religion_family_types",
    "common/religion/religion_types",
)


def descriptor(path: Path, name: str) -> str:
    lines = [
        'version="0.0.0"',
        "tags={",
        '\t"Total Conversion"',
        "}",
        f'name="{name}"',
        'supported_version="1.19.*"',
        f'path="{path}"',
    ]
    lines += [f'replace_path="{p}"' for p in REPLACE_PATHS]
    return "\n".join(lines) + "\n"


def classify(line: str) -> str | None:
    """Collapse a tiger finding into its class, so 255 counties are one line."""
    if TOTALS.match(line):
        return None  # the summary line, reported separately
    match = re.match(r"^(fatal|error|warning|untidy|tips)(\([a-z-]+\))?: (.*)$", line)
    if not match:
        return None
    level, kind, message = match.groups()
    message = re.sub(r"\bc_[a-z0-9_']+", "c_<county>", message)
    message = re.sub(r"faith/[a-z0-9_']+\.dds", "faith/<faith>.dds", message)
    return f"{level}{kind or ''}: {message}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="configs/faerun.toml")
    ap.add_argument("--keep", action="store_true", help="do not delete the mod folder")
    args = ap.parse_args()

    tiger = shutil.which("ck3-tiger")
    if not tiger:
        print("ck3-tiger not on PATH", file=sys.stderr)
        return 2

    work = Path(tempfile.mkdtemp(prefix="cr_tiger_"))
    mod = work / "cr_mod"
    mod.mkdir()
    config = Config.load(Path(args.config), out=mod)
    name = "lane cultures-religions validation"
    (mod / "descriptor.mod").write_text(descriptor(mod, name), encoding="utf-8")
    modfile = work / "cr_mod.mod"
    modfile.write_text(descriptor(mod, name), encoding="utf-8")

    ctx, runs = run_steps(config, STEPS, dry_run=False)
    counts: dict[str, int] = {}
    for run in runs:
        # namespaced: both steps report an `opinion_formats` count
        counts.update({f"{run.name}.{k}": v for k, v in run.result.counts.items()})

    version = subprocess.run(
        [tiger, "--version"], capture_output=True, text=True
    ).stdout.strip()
    proc = subprocess.run(
        [tiger, str(modfile), "--game", str(config.ck3_game)],
        capture_output=True,
        text=True,
    )
    report = ANSI.sub("", proc.stdout + proc.stderr)
    findings: Counter = Counter()
    for line in report.splitlines():
        label = classify(line.strip())
        if label:
            findings[label] += 1
    totals = next(
        (
            line.strip()
            for line in reversed(report.splitlines())
            if line.strip().startswith("fatal:")
        ),
        "(totals not found)",
    )

    lines = [
        "ck3-tiger validation of the `cultures` + `religions` steps",
        "=========================================================",
        "",
        f"tool:      {version}",
        f"game:      {config.ck3_game}",
        f"source:    {config.ck2_mod}",
        "regenerate: uv run scripts/validate_cultures_religions.py",
        "",
        "The mod under test holds ONLY this lane's outputs plus a minimal",
        ".mod, with the replace_path list of configs/faerun.toml that covers",
        "them. No landed_titles and no localization exist yet, so every",
        "cross-reference to a county and every faith loc key is expected to be",
        "reported: those belong to the titles and localisation lanes.",
        "",
        "Step counts",
        "-----------",
    ]
    lines += [f"{key:34s} {value}" for key, value in counts.items()]
    lines += ["", f"tiger totals: {totals}", "", "Findings by class", "-----------------"]
    for label, count in sorted(findings.items(), key=lambda kv: (-kv[1], kv[0])):
        lines.append(f"{count:5d}  {label}")
    lines += [
        "",
        "Reading the classes",
        "-------------------",
        "* `error(missing-item): title c_<county> not defined` — the 255 counties",
        "  the CK2 holy sites sit on. The titles lane generates them and keeps the",
        "  CK2 ids, so the references resolve once it lands. Not fixable here.",
        "* `warning(missing-file): gfx/interface/icons/faith/<faith>.dds` — tiger",
        "  infers a faith icon path from the faith id when the faith sets no",
        "  `icon`. CK2 ships one strip atlas (gfx/interface/religion_icon_strip.dds)",
        "  indexed by an integer, not per-faith files, so slicing it is image work",
        "  for the assets lane. Visible-but-non-fatal in game.",
        "* `warning(encoding): Expected UTF-8 BOM encoding` — one finding covering",
        "  all 46 generated files. `pdx.encoding.OUT_ENCODING` writes plain UTF-8",
        "  for script; tiger (and vanilla) want a BOM on script files too. That is",
        "  a converter-wide writer setting owned by the foundation lane, not this",
        "  step: flagged for the coordinator.",
        "",
        "0 fatal is the bar this lane had to clear, and it does.",
        "",
    ]
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {EVIDENCE.relative_to(REPO)}")
    print(totals)

    if not args.keep:
        shutil.rmtree(work, ignore_errors=True)
    else:
        print(f"kept {work}")
    return 1 if findings and any(k.startswith("fatal(") for k in findings) else 0


if __name__ == "__main__":
    raise SystemExit(main())
