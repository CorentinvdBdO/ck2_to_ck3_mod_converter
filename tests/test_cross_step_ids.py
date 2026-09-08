"""Ids two steps have to agree on (`ck2ck3.ids`).

Each assertion below stands for a class of ck3-tiger `missing-item` that one
full run produced and neither step's own output could have shown, because both
halves looked internally consistent (`docs/evidence/tiger_full_2026-09-08.md`).
"""

from __future__ import annotations

from dataclasses import dataclass

from ck2ck3 import ids
from ck2ck3.steps import cultures as cultures_step


@dataclass(frozen=True)
class _Culture:
    id: str


@dataclass(frozen=True)
class _Group:
    slug: str


def test_the_name_list_id_is_the_one_the_cultures_step_writes():
    """2848 `error(missing-item): name list ... not defined` when it was not."""
    culture = _Culture(id="sun_elf")
    assert cultures_step.name_list_id("fae", culture) == "name_list_fae_sun_elf"
    assert ids.name_list_id("fae", culture.id) == "name_list_fae_sun_elf"


def test_titles_reads_the_name_list_id_from_ids_not_its_own_rule():
    """The `titles` step's `cultural_names` block must resolve."""
    from ck2ck3.titles import model

    assert model.name_list_id is ids.name_list_id


def test_pillar_ids_agree_with_the_cultures_step():
    group = _Group(slug="elf_group")
    assert cultures_step.heritage_id("fae", group) == ids.heritage_id("fae", "elf_group")
    assert cultures_step.language_id("fae", group) == ids.language_id("fae", "elf_group")


def test_the_dynasty_id_has_no_dyn_infix():
    """80 `error(missing-item): dynasty fae_dyn_N not defined` when it had."""
    from ck2ck3.pdx import Block, Node
    from ck2ck3.port.dynasties import DynastyPort

    port = DynastyPort(prefix="fae")
    assert ids.fae_id(7743, "fae") == "fae_7743"
    out = port.convert_dynasty(Node(key="7743", value=Block([Node(key="name", value="X")])))
    assert out.key == "fae_7743"


def test_bookmarks_mints_the_dynasty_id_through_ids():
    from ck2ck3.titles import bookmarks

    assert bookmarks.fae_id is ids.fae_id


def test_fae_id_is_idempotent():
    """A CK2 id that already carries the prefix must not gain a second one."""
    assert ids.fae_id("fae_7743") == "fae_7743"
    assert ids.fae_id(7743) == "fae_7743"
