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

from .port.common import fae_id

__all__ = ["fae_id", "name_list_id", "heritage_id", "language_id"]


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
