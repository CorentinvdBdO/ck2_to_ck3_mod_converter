"""Text encodings for CK2 input and CK3 output.

CK2 ships Windows-1252 script and localisation; CK3 ships UTF-8, with a BOM on
localisation ``.yml``. A CK2 mod that has been edited on a modern machine mixes
both, so reading defaults to sniffing.
"""

from __future__ import annotations

import warnings
from pathlib import Path

#: CK2 game and mod files.
CK2_ENCODING = "cp1252"
#: CK3 game and mod files (``utf-8-sig`` also accepts a BOM-less file).
CK3_ENCODING = "utf-8-sig"
#: Encoding the converter writes script with.
OUT_ENCODING = "utf-8"
#: Encoding the converter writes localisation ``.yml`` with.
OUT_LOC_ENCODING = "utf-8-sig"


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


def write_text(
    path: str | Path,
    text: str,
    encoding: str = OUT_ENCODING,
    *,
    newline: str = "\n",
) -> None:
    """Write ``text`` to ``path``, creating parent directories."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding=encoding, newline=newline) as handle:
        handle.write(text)
