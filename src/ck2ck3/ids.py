"""CK3 identifiers minted from CK2 ones, in one place.

Every id shape that **more than one step has to agree on** lives here. Two
steps deriving the same id from the same CK2 name independently is how the
converter produces a mod that loads and then reports thousands of
`missing-item` — the failure is invisible in either step's own output and only
ck3-tiger or the game finds it.

`verified` 2026-09-08, both from one full run:

* `titles` wrote `cultural_names = { name_list_sun_elf = ... }` while
  `cultures` wrote `name_list_fae_sun_elf`: **2848** ck3-tiger
  `error(missing-item): name list ... not defined`.
* `bookmarks` wrote `dynasty = fae_dyn_7743` while `dynasties` wrote `fae_7743`:
  **80** `error(missing-item): dynasty fae_dyn_N not defined`.

Character and dynasty ids are :func:`ck2ck3.port.common.fae_id`, which predates
this module and stays where the character port can reach it without importing
anything else; this module re-exports it so a caller has one import to make.
"""

from __future__ import annotations

import re

from .port.common import fae_id

__all__ = [
    "fae_id",
    "name_list_id",
    "heritage_id",
    "language_id",
    "event_namespace",
    "event_id",
    "build_event_id_map",
    "NUMERIC_EVENT_NAMESPACE",
    "MAX_EVENT_NUMBER",
]

#: Largest number a CK3 event id may carry. ck3-tiger accepts every emitted
#: id up to 43308 and flags every one from 70000 up with
#: `warning(event-namespace): Event names should be in the form
#: NAMESPACE.NUMBER` (`verified` 2026-09-10 over 1704 generated ids,
#: `docs/evidence/tiger_events_2026-09-10_summary.txt`); the boundary between the two is
#: `assumed` to be the 16-bit limit. Vanilla's own highest event number is
#: 9999 over all 536 files, so nothing there pins it closer.
MAX_EVENT_NUMBER = 65535

#: The namespace every *bare numeric* CK2 event id lands in. CK2 numeric ids
#: are unique across the whole game (`verified`: 0 duplicated ids in either
#: source, `docs/events_provenance.md` §5), so one shared namespace can hold
#: all of them without a per-file rule the next lane would have to reproduce.
NUMERIC_EVENT_NAMESPACE = "ck2"

_EVENT_ID_RE = re.compile(r"^(?:(?P<ns>[A-Za-z_][A-Za-z_0-9]*)\.)?(?P<num>[0-9]+)$")
_NS_CLEAN_RE = re.compile(r"[^a-z0-9_]")


def event_namespace(prefix: str, ck2_event_id: str) -> str:
    """CK3 `namespace = X` for a CK2 event id.

    CK2 already writes the namespace into the id (``uthgar.0`` parses as the
    string ``"uthgar.0"``), so the namespace is read back off the id rather
    than tracked per file - which also keeps the mapping stable when one CK2
    namespace spans several files (`HF`, `MNM`, `RIP`, `TOG` all do).

    Owner: the `events` step. The `modified`-events and `on_actions` lanes
    must call this, not re-derive it: an on_action naming ``fae_uthgar.0``
    while the events step wrote ``fae_faerun_uthgardt_events.0`` is exactly
    the independently-derived-id failure this module exists for.
    """
    match = _EVENT_ID_RE.match(ck2_event_id.strip())
    if match is None:
        raise ValueError(f"not a CK2 event id: {ck2_event_id!r}")
    ns = match.group("ns")
    if ns is None:
        return f"{prefix}_{NUMERIC_EVENT_NAMESPACE}"
    # CK3 namespaces are lower-case in all 536 vanilla event files
    # (`verified` 2026-09-10); Faerûn mixes case (`BRO`, `FaerunSocieties`).
    return f"{prefix}_{_NS_CLEAN_RE.sub('_', ns.lower())}"


def event_id(prefix: str, ck2_event_id: str) -> str:
    """CK3 event id (``<namespace>.<number>``) for a CK2 event id.

    The number is kept, so a CK2 id stays recognisable in the generated file
    and in `docs/evidence/events_convertibility.csv` - but leading zeros are
    dropped (`FCE.0001` -> `<prefix>_fce.1`), so that this and
    :func:`build_event_id_map`, which has to compare numbers, cannot disagree
    about which id an event has.

    Use :func:`build_event_id_map` for a whole set: this function cannot know
    whether the number is above :data:`MAX_EVENT_NUMBER`.
    """
    match = _EVENT_ID_RE.match(ck2_event_id.strip())
    if match is None:
        raise ValueError(f"not a CK2 event id: {ck2_event_id!r}")
    return f"{event_namespace(prefix, ck2_event_id)}.{int(match.group('num'))}"


def build_event_id_map(prefix: str, ck2_event_ids) -> dict[str, str]:
    """CK2 event id -> CK3 event id for a whole set, numbers kept in range.

    A CK2 number above :data:`MAX_EVENT_NUMBER` (Faerûn has 79 of them, e.g.
    `KNI.70000`, `105249`) is re-allocated inside its own namespace, counting
    down from the limit so it cannot collide with the low ids CK2 authors
    actually use. Deterministic: the input is sorted first, so the same CK2
    set always produces the same CK3 ids.
    """
    by_ns: dict[str, list[str]] = {}
    for ck2_id in sorted(set(ck2_event_ids)):
        by_ns.setdefault(event_namespace(prefix, ck2_id), []).append(ck2_id)

    out: dict[str, str] = {}
    for ns, members in by_ns.items():
        numbers = {int(_EVENT_ID_RE.match(m).group("num")) for m in members}
        taken = {n for n in numbers if n <= MAX_EVENT_NUMBER}
        free = MAX_EVENT_NUMBER
        for ck2_id in sorted(members, key=lambda m: int(_EVENT_ID_RE.match(m).group("num"))):
            number = int(_EVENT_ID_RE.match(ck2_id).group("num"))
            if number > MAX_EVENT_NUMBER:
                while free in taken:
                    free -= 1
                taken.add(free)
                number = free
            out[ck2_id] = f"{ns}.{number}"
    return out


def name_list_id(prefix: str, culture_id: str) -> str:
    """`common/culture/name_lists` key for a CK2 culture.

    Owner: the `cultures` step. Read by `titles`, for the `cultural_names`
    block of a landed title.
    """
    return f"name_list_{prefix}_{culture_id}"


def heritage_id(prefix: str, group_slug: str) -> str:
    """`common/culture/pillars` heritage key for a CK2 culture *group*."""
    return f"heritage_{prefix}_{group_slug}"


def language_id(prefix: str, group_slug: str) -> str:
    """`common/culture/pillars` language key for a CK2 culture *group*."""
    return f"language_{prefix}_{group_slug}"
