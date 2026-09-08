"""Which vanilla CK3 script files name a vanilla map object, and how to hide them.

A total conversion deletes vanilla titles, provinces, characters and dynasties.
Every vanilla script that still names one is *live content pointing at nothing*:
at best error spam, at worst a crash when the player clicks the thing that runs
it. This module is the single owner of two rules:

``references_map_objects(text, ids)``
    does one file's text name a vanilla title / province / character / dynasty?
``shadow_text(rel)``
    what an empty same-name override of that file looks like.

Both the ``tc_template`` step and ``scripts/tc_scan_vanilla_refs.py`` go through
here, so the inventory in ``docs/tc_template.md`` and the files the converter
writes can never drift apart.

Id sets are read out of the installed vanilla tree, never guessed from a token
shape: ``k_from_dynasty`` is a real script token that is not a title, and
``h_india`` is a title whose tier letter is not one of the usual five
(`verified` 2026-09-08, ``common/landed_titles/00_landed_titles.txt``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

#: Script suffixes worth scanning. `.info` files are documentation vanilla
#: ships next to its databases; they are not loaded, but they are cheap to
#: shadow and tiger reads them.
SCRIPT_SUFFIXES = (".txt", ".gui", ".asset")

COMMENT_RE = re.compile(r"#.*")
TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
PROVINCE_RE = re.compile(r"\bprovince:\d+")
CHARACTER_RE = re.compile(r"\bcharacter:[A-Za-z0-9_]+")
DYNASTY_RE = re.compile(r"\bdynasty:[A-Za-z0-9_]+")
TITLE_SCOPE_RE = re.compile(r"\btitle:([A-Za-z_][A-Za-z0-9_]*)")

#: ``h_`` (above-empire) is a real tier in 1.19 and ``b_``/``c_``/``d_``/``k_``/
#: ``e_`` are the usual five.
TITLE_BLOCK_RE = re.compile(r"^\s*([behkdc]_[A-Za-z0-9_]+)\s*=\s*\{", re.MULTILINE)


@dataclass(frozen=True)
class VanillaIds:
    """The id sets a reference is checked against."""

    titles: frozenset[str]

    def __bool__(self) -> bool:  # pragma: no cover - trivial
        return bool(self.titles)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig", errors="replace")


def strip_comments(text: str) -> str:
    """Drop ``#`` comments: a commented-out title reference is not live."""
    return COMMENT_RE.sub("", text)


@lru_cache(maxsize=4)
def vanilla_ids(game: Path) -> VanillaIds:
    """Read the vanilla title id set out of ``<game>/common/landed_titles``.

    Cached: the step calls this once per run but the scan script calls it per
    invocation and it costs a second over 11 files and 17 081 titles.
    """
    root = Path(game) / "common" / "landed_titles"
    titles: set[str] = set()
    if root.is_dir():
        for path in sorted(root.rglob("*.txt")):
            titles.update(TITLE_BLOCK_RE.findall(_read(path)))
    return VanillaIds(titles=frozenset(titles))


def count_refs(text: str, ids: VanillaIds) -> dict[str, int]:
    """Per-class reference counts in one file's text.

    ``text`` is expected comment-free (:func:`strip_comments`).
    """
    title_scope = [t for t in TITLE_SCOPE_RE.findall(text) if t in ids.titles]
    bare = sum(1 for token in TOKEN_RE.findall(text) if token in ids.titles)
    counts = {
        "title_scope": len(title_scope),
        # `title:x` is also seen by the bare pass; report the bare class net of
        # it so a file is not counted twice for one reference.
        "title_bare": max(0, bare - len(title_scope)),
        "province": len(PROVINCE_RE.findall(text)),
        "character": len(CHARACTER_RE.findall(text)),
        "dynasty": len(DYNASTY_RE.findall(text)),
    }
    counts["total"] = sum(counts.values())
    return counts


def references_map_objects(text: str, ids: VanillaIds) -> bool:
    """True when this file names at least one vanilla title/province/character."""
    return count_refs(strip_comments(text), ids)["total"] > 0


def folder_files(game: Path, folder: str) -> list[Path]:
    """Every vanilla script file *directly* in ``folder`` (not below it).

    Directly, because ``replace_path`` is not recursive and neither is an
    override by filename: a shadow is per file, and a subfolder is its own row
    in ``mappings/tc_template.csv``.
    """
    base = Path(game) / folder
    if not base.is_dir():
        return []
    return sorted(
        p
        for p in base.iterdir()
        if p.is_file() and p.suffix in SCRIPT_SUFFIXES
    )


def dirty_files(game: Path, folder: str) -> list[Path]:
    """The files of ``folder`` that name a vanilla map object."""
    ids = vanilla_ids(Path(game))
    return [p for p in folder_files(game, folder) if references_map_objects(_read(p), ids)]


#: A definition at column 0 of a vanilla database file, and a file-scope
#: ``@constant``. Both have to survive a neutralisation: a caller in a file we
#: keep looks the definition up by name.
TOP_KEY_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=", re.MULTILINE)
AT_CONST_RE = re.compile(r"^(@[A-Za-z_][A-Za-z0-9_]*\s*=\s*\S+)", re.MULTILINE)

#: The neutral body a re-declared key gets, by owning folder. An empty trigger
#: block evaluates **true** in CK3, so a blanked trigger must say ``always =
#: no`` or it silently unlocks whatever it used to gate; a script value is a
#: bare number, not a block; everything else (effects, modifiers, on_actions)
#: is a no-op as an empty block.
NEUTRAL_BODIES: tuple[tuple[str, str], ...] = (
    ("common/scripted_triggers", "{ always = no }"),
    ("common/script_values", "0"),
)
DEFAULT_NEUTRAL_BODY = "{}"


def neutral_body(folder: str) -> str:
    """The body a re-declared key gets in ``folder``."""
    for prefix, body in NEUTRAL_BODIES:
        if folder.startswith(prefix):
            return body
    return DEFAULT_NEUTRAL_BODY


def neutralise_text(source: Path, folder: str, ids: VanillaIds) -> str:
    """A same-name override that keeps ``source``'s keys and drops their bodies.

    Blanking a vanilla file outright deletes the definitions in it, and a
    vanilla file the mod *keeps* may still call one — a mechanic quietly not
    running, which is worse than the dangling title the shadow fixed. So for a
    file inside a mechanic database, re-declare every top-level key with an
    empty body: the reference resolves, and the vanilla titles, provinces and
    characters that lived in the body are gone.

    The pattern is Elder Kings 2's (`verified` 2026-09-08:
    ``common/situation/catalysts/catalysts.txt``, 120 bytes, every vanilla
    catalyst key re-declared as ``key = {}``).
    """
    text = source.read_text(encoding="utf-8-sig", errors="replace")
    body = neutral_body(folder)
    lines = [
        f"# Neutralised: keeps the keys vanilla {source.name} declares, so a",
        "# caller still resolves, and drops the bodies, which named vanilla",
        "# titles, provinces, characters or dynasties this conversion lacks.",
    ]
    lines.extend(AT_CONST_RE.findall(text))
    seen: set[str] = set()
    for key in TOP_KEY_RE.findall(strip_comments(text)):
        if key in seen:
            continue
        seen.add(key)
        lines.append(f"{key} = {body}")
    return "\n".join(lines) + "\n"


def shadow_text(source: Path | str, reason: str = "") -> str:
    """The body of an empty same-name override of ``source``.

    One comment line, no script. CK3 loads the mod file instead of the vanilla
    one of the same relative path, so the vanilla definitions in it are gone
    without a ``replace_path`` — the pattern Elder Kings 2 and Godherja both
    ship (`verified` 2026-09-08: 149 and 137 stub-sized same-path files).
    """
    name = Path(source).name
    tail = f" {reason}" if reason else ""
    return (
        f"# Intentionally empty: shadows vanilla {name}, which names vanilla\n"
        f"# titles, provinces, characters or dynasties this total conversion\n"
        f"# does not have.{tail}\n"
    )
