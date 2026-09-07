"""Layout of the generated CK3 mod folder.

The output folder is a git repository of its own, generated and never
hand-edited (`docs/PROJECT.md`). `clean` therefore removes everything that is
not on :data:`PROTECTED`, which is stricter than listing the folders a step
might have produced: a folder left behind by an older converter version also
goes.
"""

from __future__ import annotations

import shutil
from pathlib import Path

#: Never deleted by `clean`. Repository plumbing and hand-written files.
PROTECTED: frozenset[str] = frozenset(
    {
        ".git",
        ".gitattributes",
        ".gitignore",
        "LICENSE",
        "README.md",
        "descriptor.mod",
        "docs",
        "thumbnail.png",
    }
)

#: Top-level folders a CK3 total conversion uses. Informational: `clean` does
#: not rely on it, steps do (each owns a subtree, see docs/cli.md).
CK3_DIRS: tuple[str, ...] = (
    "common",
    "decisions",
    "events",
    "gfx",
    "gui",
    "history",
    "localization",
    "map_data",
    "music",
)


def looks_like_a_mod(folder: Path) -> bool:
    """True when ``folder`` is empty, missing, or holds a mod descriptor.

    Guard against a mistyped ``[paths] out`` wiping an unrelated directory.
    """
    if not folder.exists():
        return True
    if not folder.is_dir():
        return False
    entries = list(folder.iterdir())
    if not entries:
        return True
    names = {e.name for e in entries}
    return bool(names & {"descriptor.mod", "README.md", ".git"})


def removable(folder: Path) -> list[Path]:
    """Top-level entries `clean` would delete, sorted."""
    if not folder.is_dir():
        return []
    return sorted(e for e in folder.iterdir() if e.name not in PROTECTED)


def remove(entry: Path) -> None:
    """Delete a file or a whole directory tree."""
    if entry.is_dir() and not entry.is_symlink():
        shutil.rmtree(entry)
    else:
        entry.unlink()
