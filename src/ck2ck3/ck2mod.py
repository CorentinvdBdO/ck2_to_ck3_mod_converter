"""Layout of a CK2 mod folder: where the script and localisation files live."""

from __future__ import annotations

from pathlib import Path

#: Directories of a CK2 mod (or of the CK2/CK3 game) that hold Paradox script.
#: ``gfx/`` and ``interface/`` use their own dialects and are excluded.
SCRIPT_GLOBS = (
    "common/**/*.txt",
    "history/**/*.txt",
    "decisions/**/*.txt",
    "events/**/*.txt",
    "map/*.txt",
)

#: CK2 localisation: semicolon-separated CSV, Windows-1252.
LOC_GLOB = "localisation/*.csv"


def script_files(mod_dir: str | Path) -> list[Path]:
    """Every Paradox script file of ``mod_dir``, sorted, duplicates removed."""
    mod_dir = Path(mod_dir)
    found: list[Path] = []
    seen: set[Path] = set()
    for pattern in SCRIPT_GLOBS:
        for path in sorted(mod_dir.glob(pattern)):
            if path not in seen:
                seen.add(path)
                found.append(path)
    return found


def loc_files(mod_dir: str | Path) -> list[Path]:
    """Every CK2 localisation CSV of ``mod_dir``, sorted."""
    return sorted(Path(mod_dir).glob(LOC_GLOB))
