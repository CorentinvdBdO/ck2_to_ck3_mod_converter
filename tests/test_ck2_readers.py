"""The CK2 trait / modifier readers.

Fixture snippets first (CLAUDE.md: every reader gets one).  The title,
province-history, climate and ``definition.csv`` readers that used to live here
moved out with ``src/titles/`` (lane titles-history): the title side is
``tests/test_titles_ck2read.py`` and the map side ``tests/test_map_ck2read.py``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from games.ck2.read.modifiers import read_modifiers_file
from games.ck2.read.traits import read_traits_file

REPO = Path(__file__).resolve().parents[1]
FAERUN = REPO / "Faerun" / "Faerun"


def write_cp1252(path: Path, text: str) -> Path:
    path.write_bytes(text.encode("cp1252"))
    return path


# -- traits and modifiers ---------------------------------------------------
def test_read_modifiers_file(tmp_path):
    path = write_cp1252(
        tmp_path / "mods.txt",
        "my_modifier = {\n\tis_good = yes\n\tmax_decimals = 2\n}\n",
    )
    modifiers = read_modifiers_file(path)
    assert modifiers["my_modifier"].is_good is True
    assert modifiers["my_modifier"].max_decimals == 2


def test_read_traits_file_splits_fields_from_modifiers(tmp_path):
    path = write_cp1252(
        tmp_path / "traits.txt",
        "brave = {\n\tpersonality = yes\n\tmartial = 2\n\topposites = { craven }\n}\n",
    )
    traits = read_traits_file(path, check_modifiers=True)
    trait = traits["brave"]
    assert trait.personality is True
    assert trait.opposites == ["craven"]
    assert trait.modifiers == {"martial": 2}


def test_read_traits_file_reports_every_unknown_key(tmp_path):
    path = write_cp1252(
        tmp_path / "traits.txt",
        "odd = {\n\tnot_a_modifier = 1\n\talso_not = 2\n}\n",
    )
    with pytest.raises(ValueError) as exc:
        read_traits_file(path, all_modifiers={}, check_modifiers=True)
    assert "also_not, not_a_modifier" in str(exc.value)
