"""``common/coat_of_arms/coat_of_arms`` — a placeholder CoA per converted title.

A coat of arms is a **separate database keyed by title id** in CK3, not a
``landed_titles`` key, so it is written here rather than in
:mod:`ck2ck3.titles.landed`.

What CK2 gives us is a ``gfx/flags/<title>.tga`` bitmap per title (3455 files
in Faerun) and the title's map ``color``.  Per ``docs/DECISIONS.md`` the flags
are **not** converted in this lane: CK3 wants either a vector composition
(``pattern`` + ``colored_emblem``, 1360 reusable ``ce_*.dds``) or a
``textured_emblem`` .dds, and turning 3455 .tga into either is its own lane.
So every title gets the same placeholder vanilla itself ships as ``default``
(``common/coat_of_arms/coat_of_arms/default.txt:1``) — ``pattern_solid.dds``
— tinted with the CK2 map colour, and the flag list is recorded in
``docs/evidence/ck2_flags.csv`` for the later lane.

``color1=rgb { r g b }`` is `verified` legal (vanilla
``common/coat_of_arms/coat_of_arms/90_dynasties.txt:389``); 6379 vanilla lines
use a named colour instead, which we cannot, since CK2 gives us raw RGB.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from .ck2read import Ck2Title
from .text import Lines

HEADER = (
    "# Placeholder coats of arms for the converted Faerun titles.",
    "# pattern_solid.dds tinted with the CK2 landed_titles `color` - the same",
    "# recipe as vanilla's own `default` entry (default.txt:1).",
    "# The 3455 CK2 gfx/flags/*.tga are NOT converted here (docs/DECISIONS.md);",
    "# docs/evidence/ck2_flags.csv lists them for a later lane.",
)


@dataclass
class CoaResult:
    text: str = ""
    counts: dict[str, int] = field(default_factory=dict)
    #: ``(title, flag file name)`` for every CK2 flag we did not convert.
    flags: list[tuple[str, str]] = field(default_factory=list)


def render(
    titles: Iterable[Ck2Title],
    *,
    live: frozenset[str],
    flags_dir: Path | None = None,
    prefix: str = "fae",
) -> CoaResult:
    """One entry per live title that CK2 gave a colour."""
    out = Lines()
    for line in HEADER:
        out.raw(line)
    out.raw("")
    result = CoaResult()
    flag_files: dict[str, str] = {}
    if flags_dir and flags_dir.is_dir():
        for path in sorted(flags_dir.iterdir()):
            if path.suffix.lower() in (".tga", ".dds", ".png"):
                flag_files[path.stem] = path.name
    written = 0
    with_flag = 0
    for title in titles:
        if title.id not in live:
            continue
        if title.color is None:
            continue
        r, g, b = title.color
        out.line(0, f"{title.id} = {{")
        out.line(1, 'pattern = "pattern_solid.dds"')
        out.line(1, f"color1=rgb {{ {r} {g} {b} }}")
        if title.color2:
            r2, g2, b2 = title.color2
            out.line(1, f"color2=rgb {{ {r2} {g2} {b2} }}")
        flag = flag_files.get(title.id)
        if flag:
            out.comment(1, f"CK2 flag: gfx/flags/{flag} (not converted)")
            result.flags.append((title.id, flag))
            with_flag += 1
        out.line(0, "}")
        written += 1
    result.text = out.text()
    result.counts = {"coats_of_arms": written, "ck2_flags_recorded": with_flag}
    return result


def flags_csv(rows: Iterable[tuple[str, str]]) -> str:
    """``docs/evidence/ck2_flags.csv`` — the hand-off to the CoA lane."""
    lines = ["title,flag_file"]
    lines += [f"{title},{flag}" for title, flag in sorted(rows)]
    return "\n".join(lines) + "\n"
