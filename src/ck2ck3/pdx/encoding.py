"""Text encodings for CK2 input and CK3 output.

CK2 ships Windows-1252 script and localisation; CK3 ships UTF-8 and wants a BOM
on localisation ``.yml`` **and on every script file under ``common/`` or
``history/``, whether or not its content is pure ASCII**.

The BOM rule is by *path*, not by content. Getting this wrong twice cost two
runs, so the evidence in full:

* ``ck3-tiger`` 1.19 reports ``warning(encoding)`` "Expected UTF-8 BOM
  encoding" for a BOM-less file in one of those databases even when the file is
  pure ASCII (`verified` 2026-09-08: 98 generated files, all ASCII, all warned
  about -- ``common/culture/cultures``, ``common/dynasties``, ``common/traits``,
  ``common/religion/*``, ``common/ethnicities``, ...).
* Vanilla agrees everywhere except two history databases: every one of the 55
  ``common/culture/cultures``, 51 ``common/culture/name_lists``, 8
  ``common/dynasties``, 10 ``common/landed_titles`` and 207
  ``history/characters`` files starts ``ef bb bf``, while ``history/titles``
  (56 of 183) and ``history/provinces`` (91 of 177) ship BOM-less pure-ASCII
  files. So a content-conditional BOM is *vanilla laxity in two folders*, never
  a requirement -- writing one always is safe and quiet.
* ``events/`` is the same: all 536 vanilla event files start ``ef bb bf``
  (`verified` 2026-09-08), and tiger warns about a BOM-less one. Lane
  `tc-template` was the first step to write there and drew the warning.
* The flat ``map_data`` files (``definition.csv``, ``default.map``,
  ``adjacencies.csv``, ...) must **not** have one; vanilla's do not, and the
  map loader is not the script parser. Nor does ``descriptor.mod`` (`verified`:
  none of the four installed workshop mods puts a BOM there).

Hence :func:`encoding_for`, which turns an output-relative path into the codec,
and :data:`BOM_PREFIXES`, the one table both this module and
``ck2ck3.map.writers`` read. A CK2 mod that has been edited on a modern machine
mixes both input encodings, so reading defaults to sniffing.
"""

from __future__ import annotations

import warnings
from pathlib import Path

#: CK2 game and mod files.
CK2_ENCODING = "cp1252"
#: CK3 game and mod files (``utf-8-sig`` also accepts a BOM-less file).
CK3_ENCODING = "utf-8-sig"
#: Encoding the converter writes script with: UTF-8 with a BOM.
OUT_ENCODING = "utf-8-sig"
#: Plain UTF-8, no BOM ever. For ``descriptor.mod`` and the flat ``map_data``
#: files.
OUT_PLAIN_ENCODING = "utf-8"
#: Encoding the converter writes localisation ``.yml`` with.
OUT_LOC_ENCODING = "utf-8-sig"
#: Output-relative path prefixes whose files get a BOM. Everything else does
#: not: the flat ``map_data`` files, ``descriptor.mod``, and the CSV/markdown
#: evidence a step drops next to the mod.
BOM_PREFIXES: tuple[str, ...] = (
    "common/",
    "events/",
    "history/",
    "localization/",
    "map_data/geographical_regions/",
    "map_data/heightmap.heightmap",
    "gfx/",
    "tests/",
)


def needs_bom(rel: str) -> bool:
    """Whether the output file at ``rel`` (mod-relative, ``/``) gets a BOM."""
    return str(rel).replace("\\", "/").startswith(BOM_PREFIXES)


def encoding_for(rel: str) -> str:
    """The codec for an output-relative path: see the module docstring."""
    return OUT_ENCODING if needs_bom(rel) else OUT_PLAIN_ENCODING


class EncodingWarning(UserWarning):
    """Raised when a file had to be decoded with the fallback encoding."""


def _normalize(text: str) -> str:
    """Universal newlines: CRLF and lone CR both become LF.

    Faerûn has at least one file with CR-only line endings
    (``history/titles/k_horthgars_horde.txt``), where a ``#`` comment would
    otherwise swallow the rest of the file.
    """
    if "\r" not in text:
        return text
    return text.replace("\r\n", "\n").replace("\r", "\n")


def read_text(path: str | Path, encoding: str = "auto") -> tuple[str, str]:
    """Read ``path`` and return ``(text, encoding_used)``.

    ``encoding="auto"`` tries ``utf-8-sig`` first and falls back to ``cp1252``
    with an :class:`EncodingWarning`; every byte is decoded either way, so a
    mixed-encoding mod never loses characters silently. Any other value is used
    as given and a decode failure propagates.
    """
    path = Path(path)
    data = path.read_bytes()
    if encoding != "auto":
        return _normalize(data.decode(encoding)), encoding
    try:
        return _normalize(data.decode(CK3_ENCODING)), CK3_ENCODING
    except UnicodeDecodeError as exc:
        warnings.warn(
            f"{path}: not valid UTF-8 ({exc.reason} at byte {exc.start}), "
            f"decoded as {CK2_ENCODING}",
            EncodingWarning,
            stacklevel=2,
        )
        return _normalize(data.decode(CK2_ENCODING, errors="replace")), CK2_ENCODING


def resolve_encoding(encoding: str, text: str) -> tuple[str, str]:
    """Return ``(codec, text)`` for writing ``text`` with ``encoding``.

    A *literal* leading ``U+FEFF`` — the ``titles``/``bookmarks`` lanes and
    ``map.sink`` prepend one to the string themselves — is stripped and turned
    into a ``utf-8-sig`` codec, so the file gets exactly one BOM instead of two.
    Every other codec name passes through, so an explicit
    :data:`OUT_PLAIN_ENCODING` still means "no BOM, whatever the content".
    """
    if text.startswith("\ufeff"):
        return "utf-8-sig", text[1:]
    return encoding, text


def write_text(
    path: str | Path,
    text: str,
    encoding: str = OUT_ENCODING,
    *,
    newline: str = "\n",
) -> None:
    """Write ``text`` to ``path``, creating parent directories."""
    encoding, text = resolve_encoding(encoding, text)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding=encoding, newline=newline) as handle:
        handle.write(text)
