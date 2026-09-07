"""CK2 localisation CSV reader and CK3 localisation YAML writer.

CK2 ships one semicolon-separated CSV per topic, Windows-1252, CRLF, with a
header line naming the languages::

    ###ANSI;;;;;;;;;;;;x
    #CODE;ENGLISH;FRENCH;GERMAN;;SPANISH;;;;;;;x
    c_abaltrer;Abaltrer;Abaltrer;Abaltrer;;Abaltrer;;;;;;;x

CK3 ships one YAML-ish file per language, UTF-8 **with BOM**, CRLF::

    l_english:
     c_abaltrer:0 "Abaltrer"

Evidence (`verified` 2026-09-07): `Faerun/Faerun/localisation/0000_titles.csv`
(7429 of 7443 rows have 13 fields, 57 files carry the 13-field header, 20 a
15-field one), CK3 1.19 `localization/english/titles_l_english.yml`, and
`\"` escaping in `localization/english/debug_story_test_event_l_english.yml:24`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Mapping

from .pdx.encoding import CK2_ENCODING, OUT_LOC_ENCODING, read_text

#: Column index → language, for a CK2 file with no usable header. Index 0 is
#: the key and the last column is the ``x`` marker.
CK2_COLUMNS: dict[int, str] = {
    1: "english",
    2: "french",
    3: "german",
    5: "spanish",
}

#: CK3 line endings for localisation, as shipped by vanilla and by Elder Kings
#: 2 (`verified` 2026-09-07).
YML_NEWLINE = "\r\n"


@dataclass
class LocEntry:
    """One localisation key and its translations."""

    key: str
    values: dict[str, str] = field(default_factory=dict)
    line: int = 0

    def text(self, language: str = "english") -> str:
        return self.values.get(language, "")


@dataclass
class LocFile:
    """A parsed CK2 localisation CSV. Comment lines are kept, in order."""

    path: Path | None = None
    entries: list[LocEntry] = field(default_factory=list)
    #: ``(line_number, raw_line)`` for every ``#`` line, header included.
    comments: list[tuple[int, str]] = field(default_factory=list)
    #: Column index → language actually used for this file.
    languages: dict[int, str] = field(default_factory=dict)
    #: Rows that had fewer fields than the header, as ``(line, raw)``.
    short_rows: list[tuple[int, str]] = field(default_factory=list)

    def __iter__(self):
        return iter(self.entries)

    def __len__(self) -> int:
        return len(self.entries)

    def get(self, key: str, language: str = "english") -> str | None:
        for entry in self.entries:
            if entry.key == key:
                return entry.values.get(language)
        return None

    def to_dict(self, language: str = "english") -> dict[str, str]:
        """Key → text, dropping empty translations. Later rows win."""
        out: dict[str, str] = {}
        for entry in self.entries:
            text = entry.values.get(language)
            if text:
                out[entry.key] = text
        return out


def _languages_from_header(fields: list[str]) -> dict[int, str]:
    """Map column index → language from a ``#CODE;ENGLISH;...`` header."""
    languages: dict[int, str] = {}
    for index, label in enumerate(fields):
        if index == 0:
            continue
        name = label.strip().lower()
        if name and name != "x":
            languages[index] = name
    return languages


def read_ck2_csv(path: str | Path, encoding: str = CK2_ENCODING) -> LocFile:
    """Read one CK2 localisation CSV.

    ``encoding`` defaults to Windows-1252; pass ``"auto"`` to sniff. Comment
    lines (``#``) are kept so a converted file can cite them; a ``#CODE;...``
    line also sets the language columns.
    """
    path = Path(path)
    text, _ = read_text(path, encoding)
    loc = LocFile(path=path, languages=dict(CK2_COLUMNS))
    for number, raw in enumerate(text.split("\n"), start=1):
        line = raw.rstrip("\r")
        if not line.strip():
            continue
        if line.startswith("#"):
            loc.comments.append((number, line))
            fields = line.split(";")
            if fields[0].lstrip("#").strip().upper() == "CODE":
                found = _languages_from_header(fields)
                if found:
                    loc.languages = found
            continue
        fields = line.split(";")
        key = fields[0].strip()
        if not key:
            loc.short_rows.append((number, line))
            continue
        entry = LocEntry(key=key, line=number)
        for index, language in loc.languages.items():
            if index < len(fields):
                value = fields[index].strip()
                if value:
                    entry.values[language] = value
        if len(fields) <= max(loc.languages, default=0):
            loc.short_rows.append((number, line))
        loc.entries.append(entry)
    return loc


def read_ck2_loc(
    mod_dir: str | Path,
    language: str = "english",
    encoding: str = CK2_ENCODING,
) -> tuple[dict[str, str], list[str]]:
    """Read every CSV of ``mod_dir/localisation`` into one key → text dict.

    Files are read in filename order and a later file overrides an earlier one
    (`assumed`: CK2 load order for localisation is alphabetical and the last
    definition wins). The second return value lists the keys that were
    overridden, so a lane can report on them.
    """
    from .ck2mod import loc_files

    merged: dict[str, str] = {}
    overridden: list[str] = []
    for path in loc_files(mod_dir):
        for key, text in read_ck2_csv(path, encoding).to_dict(language).items():
            if key in merged and merged[key] != text:
                overridden.append(key)
            merged[key] = text
    return merged, overridden


def escape_yml(text: str) -> str:
    """Escape a localisation value for a CK3 ``.yml`` file.

    Only the double quote is escaped: a backslash is meaningful in CK2 and CK3
    text (``\\n`` is a line break in both), so backslashes are passed through —
    except a trailing one, which would otherwise escape the closing quote.
    """
    escaped = text.replace('"', '\\"')
    trailing = len(escaped) - len(escaped.rstrip("\\"))
    if trailing % 2:
        escaped += "\\"
    return escaped


def write_ck3_yml(
    path: str | Path,
    entries: Mapping[str, str] | Iterable[tuple[str, str]],
    *,
    language: str = "english",
    version: int = 0,
    header_comments: Iterable[str] = (),
    newline: str = YML_NEWLINE,
) -> int:
    """Write a CK3 localisation file and return the number of keys written.

    UTF-8 with BOM, CRLF, ``l_<language>:`` header, one ``' key:0 "text"'``
    line per entry. ``header_comments`` are written as ``#`` lines under the
    header.
    """
    path = Path(path)
    pairs = list(entries.items() if isinstance(entries, Mapping) else entries)
    lines = [f"l_{language}:"]
    lines.extend(f"# {c}" if not c.startswith("#") else c for c in header_comments)
    for key, text in pairs:
        lines.append(f' {key}:{version} "{escape_yml(text)}"')
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding=OUT_LOC_ENCODING, newline="") as handle:
        handle.write(newline.join(lines) + newline)
    return len(pairs)
