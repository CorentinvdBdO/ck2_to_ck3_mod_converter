"""CK2 localisation CSV reader and CK3 yml writer."""

from __future__ import annotations

from pathlib import Path

import pytest

from ck2ck3.csvloc import (
    CK2_COLUMNS,
    escape_yml,
    read_ck2_csv,
    read_ck2_loc,
    write_ck3_yml,
)

REPO = Path(__file__).resolve().parents[1]
FAERUN = REPO / "Faerun" / "Faerun"

SAMPLE = (
    "###ANSI;;;;;;;;;;;;x\r\n"
    "#CODE;ENGLISH;FRENCH;GERMAN;;SPANISH;;;;;;;x\r\n"
    "c_abaltrer;Abaltrer;Abaltrer;Abaltrer;;Abaltrer;;;;;;;x\r\n"
    "b_tower;Bj\xf8rn's Tower;;;;;;;;;;;x\r\n"
    "\r\n"
    "# a note in the middle\r\n"
    "d_quote;He said \"no\";;;;;;;;;;;x\r\n"
)


@pytest.fixture
def sample_csv(tmp_path) -> Path:
    path = tmp_path / "00_sample.csv"
    path.write_bytes(SAMPLE.encode("cp1252"))
    return path


def test_reads_keys_and_english(sample_csv):
    loc = read_ck2_csv(sample_csv)
    assert [e.key for e in loc] == ["c_abaltrer", "b_tower", "d_quote"]
    assert loc.get("c_abaltrer") == "Abaltrer"


def test_reads_cp1252(sample_csv):
    assert read_ck2_csv(sample_csv).get("b_tower") == "Bj\xf8rn's Tower"


def test_reads_other_languages(sample_csv):
    loc = read_ck2_csv(sample_csv)
    assert loc.get("c_abaltrer", "spanish") == "Abaltrer"
    assert loc.get("b_tower", "french") is None


def test_language_columns_come_from_the_header(sample_csv):
    loc = read_ck2_csv(sample_csv)
    assert loc.languages == CK2_COLUMNS


def test_comment_lines_are_kept_in_order(sample_csv):
    loc = read_ck2_csv(sample_csv)
    assert [line for _, line in loc.comments] == [
        "###ANSI;;;;;;;;;;;;x",
        "#CODE;ENGLISH;FRENCH;GERMAN;;SPANISH;;;;;;;x",
        "# a note in the middle",
    ]
    assert loc.comments[2][0] == 6


def test_to_dict_drops_empty_translations(sample_csv):
    assert read_ck2_csv(sample_csv).to_dict("french") == {"c_abaltrer": "Abaltrer"}


def test_missing_key_returns_none(sample_csv):
    assert read_ck2_csv(sample_csv).get("nope") is None


def test_escape_yml():
    assert escape_yml('He said "no"') == 'He said \\"no\\"'
    assert escape_yml("a\\nb") == "a\\nb"  # CK2 line break passes through
    assert escape_yml("trail\\") == "trail\\\\"


def test_write_ck3_yml_bytes(tmp_path):
    path = tmp_path / "fae_titles_l_english.yml"
    count = write_ck3_yml(path, {"c_abaltrer": "Abaltrer", "b_tower": "Bjørn's Tower"})
    assert count == 2
    raw = path.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")  # UTF-8 BOM
    assert raw.endswith(b"\r\n")
    assert raw.decode("utf-8-sig").split("\r\n") == [
        "l_english:",
        ' c_abaltrer:0 "Abaltrer"',
        ' b_tower:0 "Bjørn\'s Tower"',
        "",
    ]


def test_write_ck3_yml_escapes_quotes_and_takes_comments(tmp_path):
    path = tmp_path / "x_l_french.yml"
    write_ck3_yml(
        path,
        [("d_quote", 'He said "no"')],
        language="french",
        version=1,
        header_comments=["generated"],
    )
    text = path.read_bytes().decode("utf-8-sig")
    assert text.split("\r\n")[:3] == [
        "l_french:",
        "# generated",
        ' d_quote:1 "He said \\"no\\""',
    ]


def test_csv_to_yml_round_trip(sample_csv, tmp_path):
    loc = read_ck2_csv(sample_csv)
    out = tmp_path / "out_l_english.yml"
    write_ck3_yml(out, loc.to_dict())
    text = out.read_bytes().decode("utf-8-sig")
    assert ' b_tower:0 "Bjørn\'s Tower"' in text
    assert ' d_quote:0 "He said \\"no\\""' in text


@pytest.mark.slow
@pytest.mark.skipif(not FAERUN.is_dir(), reason="Faerun/ clone absent")
def test_reads_a_real_faerun_csv():
    loc = read_ck2_csv(FAERUN / "localisation" / "0000_titles.csv")
    assert len(loc) > 7000
    assert loc.get("c_abaltrer") == "Abaltrer"
    assert loc.languages == CK2_COLUMNS
    assert loc.comments[0][0] == 1


@pytest.mark.slow
@pytest.mark.skipif(not FAERUN.is_dir(), reason="Faerun/ clone absent")
def test_reads_every_faerun_csv():
    merged, overridden = read_ck2_loc(FAERUN)
    assert len(merged) > 20000
    assert merged["c_abaltrer"] == "Abaltrer"
    assert isinstance(overridden, list)
