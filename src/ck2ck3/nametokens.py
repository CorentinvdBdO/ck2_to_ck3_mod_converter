"""CK2 literal person names → CK3 name-list tokens (which are loc keys).

Why this module exists (`verified` 2026-09-08, headless CK3 1.19.0.6,
`docs/evidence/game_load_2026-09-08.md`):

* A CK3 ``male_names`` / ``female_names`` entry is **a localisation key**, not
  a display string.  Vanilla ``common/culture/name_lists/00_ainu.txt:108``
  lists ``Akarakay Antaaynu …`` and
  ``localization/english/names/character_names_l_english.yml`` carries
  ``Akarakay:0 "Akarakay"``.  Copying CK2's literal names through with no loc
  produced **77 736** ``culture_name_equivalency.cpp:101: Missing loc X``
  errors in one boot.
* A bare token that does not start with a letter **breaks the script parser**
  for the rest of the file.  Faerûn's ``modron`` culture names are serial
  numbers (``2BD71SF2``); the game reported
  ``Unexpected token: female_names, near line: 3458`` and then failed every one
  of the 14 ``name_list_*`` blocks that followed it in
  ``common/culture/name_lists/fae_monsters.txt``, leaving 14 cultures with no
  name list at all.
* A token may not contain whitespace.  Vanilla spells multi-word names with an
  underscore (``Asir_Rera``, ``00_ainu.txt:149``); the converter used to emit
  ``"Sergeant Reckless"`` quoted, which the equivalency table could not look up.
* **A localisation key must be ASCII.**  ``localization_reader.cpp:445: Invalid
  character '<x>' in key name 'Bj<ö>rn'`` — 251 of them.  Vanilla agrees: 0 of
  its 55 948 name keys hold a non-ASCII byte, and its own north-Germanic list
  spells Björn ``BjO_rn``, Andrés ``AndrE_s`` and Åke ``A__ke``, with the
  accented spelling only in the loc value.  So the token is ASCII-folded and a
  collision is broken with a trailing underscore, which is the same idiom.

The characters vanilla actually uses in a name key are letters, digits, ``_``
and ``-`` (997 hyphens across those 55 948 keys); an apostrophe also passes
(571 of ours drew no complaint).

Display is unchanged by any of this: the loc file says what each token means.
"""

from __future__ import annotations

import re
import unicodedata

#: Characters a name token may keep.  Everything else is dropped after the
#: ASCII fold below.
_KEEP = re.compile(r"[^A-Za-z0-9_'.\-]")
_WHITESPACE = re.compile(r"\s+", re.UNICODE)

#: Letters :func:`unicodedata.normalize` will not decompose, and their ASCII
#: spelling.  Everything with a combining accent (``é``, ``ö``, ``ñ``, ``ç``)
#: is handled by NFKD and needs no row here.
_FOLD = {
    "ø": "o", "Ø": "O",
    "æ": "ae", "Æ": "Ae",
    "œ": "oe", "Œ": "Oe",
    "ß": "ss",
    "ð": "d", "Ð": "D",
    "đ": "d", "Đ": "D",
    "þ": "th", "Þ": "Th",
    "ł": "l", "Ł": "L",
    "ı": "i", "İ": "I",
    "ŋ": "ng", "Ŋ": "Ng",
    "ħ": "h", "Ħ": "H",
    "ə": "e", "Ə": "E",
    "ʻ": "'", "ʼ": "'", "’": "'",
    "–": "-", "—": "-",
}

#: Prefix for a name whose first character is not a letter or an underscore.
#: A leading digit is what actually breaks the parser; the prefix is spelled
#: out so the loc file stays readable.
DIGIT_PREFIX = "name_"


def ascii_fold(text: str) -> str:
    """``Björn`` → ``Bjorn``, ``Åke`` → ``Ake``, ``Đôçã`` → ``Doca``."""
    mapped = "".join(_FOLD.get(ch, ch) for ch in text)
    decomposed = unicodedata.normalize("NFKD", mapped)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def name_token(name: str) -> str | None:
    """One CK2 literal name → a parser-safe ASCII token, or ``None`` if empty.

    >>> name_token("Sergeant Reckless")
    'Sergeant_Reckless'
    >>> name_token("2BD71SF2")
    'name_2BD71SF2'
    >>> name_token('  "Clever Hans" ')
    'Clever_Hans'
    >>> name_token("Björn")
    'Bjorn'
    >>> name_token("Qiu-te")
    'Qiu-te'
    >>> name_token("---")
    """
    text = str(name).strip().strip('"').strip()
    if not text:
        return None
    text = _WHITESPACE.sub("_", text)
    text = _KEEP.sub("", ascii_fold(text))
    text = text.strip("_.-'")
    if not text:
        return None
    if not (text[0] == "_" or text[0].isalpha()):
        text = DIGIT_PREFIX + text
    return text


def tokenise(names: list[str], taken: dict[str, str] | None = None) -> list[str]:
    """A CK2 name list → its tokens, recording ``{token: literal}`` in ``taken``.

    ``taken`` is shared across every name list of the run, so one literal keeps
    one token everywhere (the same name appears in dozens of Faerûn cultures)
    and two literals that fold onto one token get distinct ones: the second
    gains a trailing ``_``, which is how vanilla separates ``Aki`` from ``Áki``.

    Repeats inside one list are dropped: CK2 lists ``Beauty`` twice for its
    ``horse`` culture and CK3 gains nothing from it.
    """
    if taken is None:
        taken = {}
    by_literal = {literal: token for token, literal in taken.items()}
    out: list[str] = []
    emitted: set[str] = set()
    for raw in names:
        literal = str(raw).strip().strip('"').strip()
        token = by_literal.get(literal)
        if token is None:
            token = name_token(raw)
            if token is None:
                continue
            while token in taken and taken[token] != literal:
                token += "_"
            taken[token] = literal
            by_literal[literal] = token
        if token not in emitted:
            emitted.add(token)
            out.append(token)
    return out
