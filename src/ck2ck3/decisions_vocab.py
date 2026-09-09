"""CK2 -> CK3 trigger/effect/scope vocabulary for the ``decisions`` step.

Three tables, read from ``mappings/`` at runtime (built by
``scripts/build_decisions_vocab_tables.py``, method and coverage in
``docs/mapping_triggers_effects.md``):

* ``mappings/triggers.csv`` -- CK2 trigger key -> CK3 trigger key.
* ``mappings/effects.csv`` -- CK2 effect key -> CK3 effect key.
* ``mappings/event_targets.csv`` -- CK2 scope-changing key (a key whose value
  is a block that moves the current scope, e.g. ``liege = { ... }``) -> CK3
  event target / list iterator.

Plus two small hardcoded tables that are conventions, not curated data:

* :data:`SCOPE_WORDS` -- the CK2 ``ROOT``/``FROM``/``PREV``/``THIS`` chain
  words -> the CK3 script scope word or saved-scope name. CK3 script has no
  ``FROM`` (unlike CK2, which auto-binds it from the calling context); the
  convention already used by the ``loc`` step for text codes
  (``ck2_from``, `docs/loc_codes.md`) is reused here so a decision's
  ``desc``/effect and its localisation agree on the same saved-scope name.
* :data:`TITLE_TAG_RE` -- CK2 lets a bare title id be used as a scope-opening
  key (``k_ammarindar = { has_holder = no }``); this is general CK2 syntax,
  not per-key vocabulary, so it is recognised structurally rather than
  listed in ``event_targets.csv``.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path

#: CK2 scope-chain word -> CK3 script scope word or saved-scope reference.
#: `verified`: CK3 script has ``root``/``prev``/``this`` and chains
#: ``prev.prev`` for further steps back (unlike CK2 loc, which has no such
#: chaining - `docs/loc_codes.md`); it has no ``FROM`` at all, so the
#: convention is a saved scope named like the loc step's, `ck2_from`.
SCOPE_WORDS: dict[str, str] = {
    "ROOT": "root",
    "THIS": "this",
    "PREV": "prev",
    "PREVPREV": "prev.prev",
    "PREVPREVPREV": "prev.prev.prev",
    "FROM": "scope:ck2_from",
    "FROMFROM": "scope:ck2_fromfrom",
    "FROMFROMFROM": "scope:ck2_fromfromfrom",
}

#: The CK2 title-tag shape (``c_``/``d_``/``k_``/``e_``/``b_`` + name).
#: A bare key of this shape inside a trigger/effect block opens that title's
#: scope (CK2 general syntax, not a per-key vocabulary entry); CK3 keeps the
#: same construct spelled ``title:<id> = { ... }`` (`verified`,
#: `game/common/scripted_triggers` uses `title:k_france = { ... }` shaped
#: calls throughout).
TITLE_TAG_RE = re.compile(r"^[bcdke]_[a-z0-9_]+$")

#: CK2 effect ``<trait_id> = yes/no`` and trigger ``<trait_id> = yes`` are
#: shorthand for ``trait``/``add_trait``/``remove_trait`` with that trait as
#: the argument (`verified` CK2 `decisions/decisions.info` "shorthand"
#: triggers). Resolved against the live trait id set the `traits` step
#: already ported (``ctx.data["traits"]``), never re-derived.


@dataclass(frozen=True)
class VocabRow:
    ck2_key: str
    ck3_key: str | None
    status: str  # exact | approx | none
    confidence: str  # verified | assumed
    note: str


def read_vocab_csv(path: Path) -> dict[str, VocabRow]:
    """``ck2_key,ck3_key,status,confidence,note`` -> row, keyed by ck2_key.

    Header optional, ``#``-comment lines skipped (repo convention, see
    ``mappings/vanilla_traits.csv``).
    """
    rows: dict[str, VocabRow] = {}
    with open(path, encoding="utf-8-sig", newline="") as handle:
        for row in csv.reader(handle):
            if not row or row[0].lstrip().startswith("#"):
                continue
            if row[0].strip().lower() == "ck2_key":
                continue
            ck2_key, ck3_key, status, confidence, note = (row + [""] * 5)[:5]
            rows[ck2_key.strip()] = VocabRow(
                ck2_key=ck2_key.strip(),
                ck3_key=ck3_key.strip() or None,
                status=status.strip() or "none",
                confidence=confidence.strip() or "assumed",
                note=note.strip(),
            )
    return rows
