"""`scripts/build_loc_key_map.py` — the merge of the per-lane rename tables."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

_spec = importlib.util.spec_from_file_location(
    "build_loc_key_map", ROOT / "scripts" / "build_loc_key_map.py"
)
assert _spec and _spec.loader
build_loc_key_map = importlib.util.module_from_spec(_spec)
sys.modules["build_loc_key_map"] = build_loc_key_map
_spec.loader.exec_module(build_loc_key_map)


def make_tables(root: Path, tables: dict[str, str]) -> None:
    (root / "mappings").mkdir(parents=True, exist_ok=True)
    for lane, text in tables.items():
        (root / "mappings" / f"loc_key_renames_{lane}.csv").write_text(
            text, encoding="utf-8"
        )


def test_each_lane_gets_its_documented_mode(tmp_path):
    make_tables(
        tmp_path,
        {
            "traits": "ck2_key,ck3_key\nbrave,trait_brave\n",
            "titles": "ck2_key,ck3_key\nc_waterdeep,c_waterdeep_adj\n",
            "cultures_religions": "ck2_key,ck3_key\nADEPT,ADEPT_plural\n",
        },
    )
    rows, counts = build_loc_key_map.build(tmp_path)
    assert rows == [
        ("brave", "trait_brave", "rename", "traits"),
        ("c_waterdeep", "c_waterdeep_adj", "copy", "titles"),
        ("ADEPT", "ADEPT_plural", "copy", "cultures_religions"),
    ]
    assert counts == {"traits": 1, "titles": 1, "cultures_religions": 1}


def test_the_characters_table_is_excluded_not_merged(tmp_path):
    """It is a `ck3_loc_key,ck2_source,ck2_value` record, not a rename table."""
    make_tables(
        tmp_path,
        {
            "traits": "ck2_key,ck3_key\nbrave,trait_brave\n",
            "characters": 'ck3_loc_key,ck2_source,ck2_value\ndynn_fae_1,"a name",Bhaal\n',
        },
    )
    rows, counts = build_loc_key_map.build(tmp_path)
    assert [r[0] for r in rows] == ["brave"]
    assert "characters" not in counts


def test_an_unclassified_table_is_refused(tmp_path):
    make_tables(tmp_path, {"events": "ck2_key,ck3_key\na,b\n"})
    with pytest.raises(SystemExit, match="unclassified rename table"):
        build_loc_key_map.build(tmp_path)


def test_identity_rows_and_duplicates_are_dropped(tmp_path):
    make_tables(
        tmp_path,
        {
            "traits": "ck2_key,ck3_key\nbrave,brave\nbrave,trait_brave\n"
            "brave,trait_brave\n"
        },
    )
    rows, counts = build_loc_key_map.build(tmp_path)
    assert rows == [("brave", "trait_brave", "rename", "traits")]
    assert counts["traits"] == 1


def test_two_lanes_disagreeing_about_a_pair_is_an_error(tmp_path):
    make_tables(
        tmp_path,
        {
            "traits": "ck2_key,ck3_key\nx,y\n",
            "titles": "ck2_key,ck3_key\nx,y\n",
        },
    )
    with pytest.raises(SystemExit, match="wants rename"):
        build_loc_key_map.build(tmp_path)


def test_the_committed_override_file_is_up_to_date():
    """`ci/checks.sh` runs the same check; this is the pytest half."""
    assert build_loc_key_map.main(["build_loc_key_map", "--check"]) == 0


def test_the_committed_file_parses_as_a_key_map():
    from ck2ck3.steps.loc import read_key_map

    key_map = read_key_map(ROOT / "overrides" / "loc_keys.csv")
    # A trait loses its bare key; a title keeps its name and gains `_adj`.
    assert key_map.keys_for("brave") == ("trait_brave",)
    assert key_map.keys_for("c_waterdeep") == ("c_waterdeep", "c_waterdeep_adj")
