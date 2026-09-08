#!/usr/bin/env python
"""Validate the titles/history output with ck3-tiger and summarise per class.

Builds a throwaway copy of the generated mod in a scratch folder, re-runs the
three steps of lane ``titles-history`` into it, writes the ``.mod`` file
ck3-tiger wants (it reads that file, **not** ``descriptor.mod``, so the
``replace_path`` lines have to be copied into it or vanilla content shadows
nothing), and prints one line per diagnostic class.

``--stub-characters`` also writes a ``history/characters`` file declaring every
``fae_<id>`` the title history references, with the CK2 birth and death dates.
That folder belongs to lane ``characters``; the stub exists **only** inside the
throwaway copy, so the "character not defined" and "holder is not alive"
classes can be told apart from real problems in this lane's own output.

    uv run scripts/tiger_titles_check.py --out docs/evidence/tiger_titles.txt
    uv run scripts/tiger_titles_check.py --mod /tmp/titles_out   # check as-is

With ``--mod`` the folder is copied and validated as it stands: no steps are
re-run, so the report describes exactly the output of the run that made it.
"""

from __future__ import annotations

import argparse
import collections
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from ck2ck3.config import Config  # noqa: E402
from ck2ck3.titles import ck2read, model  # noqa: E402

ANSI = re.compile(r"\x1b\[[0-9;]*m")
CLASS = re.compile(r"^([a-z]+)\(([a-z0-9-]+)\): (.*)$")
FILE = re.compile(r"^\s*-->\s*\[(MOD|CK3)\]\s*(\S+)")
STEPS = "titles,history_titles,bookmarks"

#: Diagnostics whose *subject* belongs to another lane, keyed by the first
#: word of the message.
FOREIGN_SUBJECT = {
    "character": "characters",
    "dynasty": "characters",
    "coa": "characters",
    "faith": "cultures-religions",
    "religion": "cultures-religions",
    "culture": "cultures-religions",
    "name": "cultures-religions",  # "name list name_list_x not defined"
}

#: Diagnostics reported *against a file* another lane owns.
FOREIGN_FILE = (
    ("history/characters", "characters"),
    ("zz_stub_characters", "characters"),
    ("common/culture", "cultures-religions"),
    ("common/religion", "cultures-religions"),
    ("common/dynasties", "characters"),
    ("map_data", "map-physical"),
    ("common/province_terrain", "map-physical"),
    ("common/defines", "map-physical"),
    ("localization", "loc"),
)

OURS = "titles-history"


def strip_ansi(text: str) -> str:
    return ANSI.sub("", text)


#: Diagnostic kinds that are always the loc lane's, whatever file they name.
LOC_KINDS = ("missing-localization", "suggest-localization")


def owner(message: str, path: str, kind: str = "") -> str:
    if kind in LOC_KINDS and "characters" not in path:
        return "loc"
    for token, lane in FOREIGN_FILE:
        if token in path:
            return lane
    head = message.split(" ", 1)[0]
    if head == "name" and message.startswith("name list "):
        return "cultures-religions"
    if head in FOREIGN_SUBJECT and head != "name":
        return FOREIGN_SUBJECT[head]
    return OURS


def write_mod_file(path: Path, mod_dir: Path, descriptor: Path) -> None:
    """The ``.mod`` file tiger reads, including the replace_path lines."""
    lines = [f'path = "{mod_dir}"']
    if descriptor.exists():
        for line in descriptor.read_text(encoding="utf-8").splitlines():
            if line.startswith(("version", "name", "supported_version", "replace_path")):
                lines.append(line)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def stub_characters(mod_dir: Path, ck2_mod: Path, prefix: str) -> int:
    """Declare every CK2 character as ``<prefix>_<id>`` so holders resolve."""
    index = ck2read.read_character_index(ck2_mod / "history" / "characters")
    out = [
        "# THROWAWAY: written by scripts/tiger_titles_check.py so ck3-tiger can",
        "# check the title history without lane `characters`. Never shipped.",
        "",
    ]
    for cid, stub in index.items():
        out.append(f"{prefix}_{cid} = {{")
        out.append(f'\tname = "{stub.name or cid}"')
        if stub.female:
            out.append("\tfemale = yes")
        birth = stub.birth or None
        out.append(f"\t{birth or '1.1.1'} = {{ birth = yes }}")
        if stub.death:
            out.append(f"\t{stub.death} = {{ death = yes }}")
        out.append("}")
    target = mod_dir / "history" / "characters"
    target.mkdir(parents=True, exist_ok=True)
    for existing in target.glob("*.txt"):
        existing.unlink()
    (target / "zz_stub_characters.txt").write_text("\n".join(out) + "\n", encoding="utf-8")
    return len(index)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(ROOT / "configs" / "faerun.toml"))
    ap.add_argument(
        "--scratch",
        default="/tmp/ck2ck3_tiger_titles",
        help="throwaway mod folder (wiped on every run)",
    )
    ap.add_argument("--out", default=str(ROOT / "docs" / "evidence" / "tiger_titles.txt"))
    ap.add_argument(
        "--mod",
        help="validate this already-built mod folder as it stands (no steps re-run)",
    )
    ap.add_argument("--stub-characters", action="store_true", default=True)
    ap.add_argument("--no-stub-characters", dest="stub_characters", action="store_false")
    ap.add_argument("--tiger", default=str(Path.home() / ".local/bin/ck3-tiger"))
    args = ap.parse_args()

    config = Config.load(args.config)
    scratch = Path(args.scratch)
    mod_dir = scratch / "mod"
    if scratch.exists():
        shutil.rmtree(scratch)
    scratch.mkdir(parents=True)
    source = Path(args.mod) if args.mod else config.out
    shutil.copytree(
        source, mod_dir, ignore=shutil.ignore_patterns(".git", "docs")
    )
    steps = "as built" if args.mod else STEPS
    if not args.mod:
        for rel in ("common/landed_titles", "history/titles", "history/provinces"):
            for path in (mod_dir / rel).glob("*.txt"):
                path.unlink()

        run = subprocess.run(
            [
                sys.executable,
                "-m",
                "ck2ck3",
                "--config",
                args.config,
                "--steps",
                STEPS,
                "--out",
                str(mod_dir),
                "--no-evidence",
            ],
            cwd=ROOT,
            env={**__import__("os").environ, "PYTHONPATH": str(ROOT / "src")},
            capture_output=True,
            text=True,
        )
        print(run.stdout.strip() or run.stderr.strip())
        if run.returncode != 0:
            return run.returncode

    stubs = 0
    if args.stub_characters:
        stubs = stub_characters(mod_dir, config.ck2_mod, config.prefix)

    mod_file = scratch / "check.mod"
    write_mod_file(mod_file, mod_dir, mod_dir / "descriptor.mod")
    game = config.ck3_game.parent  # tiger wants the install dir, not game/
    tiger = subprocess.run(
        [args.tiger, str(mod_file), "--game", str(game)],
        capture_output=True,
        text=True,
    )
    text = strip_ansi(tiger.stdout + tiger.stderr)

    # a diagnostic is "class + message" on one line, then a `--> [MOD] path`
    # line; ownership needs both, so the file is attached after the fact.
    entries: list[tuple[str, str, str]] = []
    pending: list[int] = []
    for line in text.splitlines():
        match = CLASS.match(line)
        if match:
            severity, kind, message = match.groups()
            entries.append((f"{severity}({kind})", message, ""))
            pending = [len(entries) - 1]
            continue
        hit = FILE.match(line)
        if hit and pending:
            index = pending.pop()
            cls, message, _ = entries[index]
            entries[index] = (cls, message, hit.group(2))

    classes: collections.Counter[tuple[str, str]] = collections.Counter()
    samples: dict[tuple[str, str], str] = {}
    for cls, message, path in entries:
        kind = cls.split("(", 1)[1].rstrip(")")
        key = (cls, owner(message, path, kind))
        classes[key] += 1
        samples.setdefault(key, f"{message}  [{path or 'no file'}]")

    report = [
        "# ck3-tiger on the titles-history lane output",
        f"# mod: {source}",
        f"# steps: {steps}",
        f"# stub history/characters: {'yes, ' + str(stubs) + ' characters' if stubs else 'no'}",
        "# owner = the lane that has to fix the class; titles-history is ours.",
        "",
        f"{'count':>7}  {'class':<32} {'owner':<28} example",
    ]
    for (cls, lane), count in classes.most_common():
        report.append(f"{count:>7}  {cls:<32} {lane:<20} {samples[(cls, lane)][:96]}")
    ours = sum(c for (_cls, lane), c in classes.items() if lane == OURS)
    report += ["", f"total diagnostics: {sum(classes.values())}, ours: {ours}"]
    body = "\n".join(report) + "\n"
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(body, encoding="utf-8")
    (scratch / "tiger_full.txt").write_text(text, encoding="utf-8")
    print(body)
    print(f"full output: {scratch / 'tiger_full.txt'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
