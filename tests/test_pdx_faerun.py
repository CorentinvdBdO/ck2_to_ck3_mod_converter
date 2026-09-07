"""Integration: parse the real Faerûn mod, then round-trip a sample of it.

Marked ``slow``; skipped when the Faerûn clone is absent (it is gitignored,
see CLAUDE.md for the clone command).
"""

from __future__ import annotations

import warnings
from pathlib import Path

import pytest

from ck2ck3.ck2mod import script_files
from ck2ck3.pdx import (
    PdxSyntaxError,
    parse,
    read_text,
    structurally_equal,
    write,
)

REPO = Path(__file__).resolve().parents[1]
FAERUN = REPO / "Faerun" / "Faerun"
ROUNDTRIP_SAMPLE = 200

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(not FAERUN.is_dir(), reason="Faerun/ clone absent"),
]


@pytest.fixture(scope="module")
def faerun_files() -> list[Path]:
    files = script_files(FAERUN)
    assert files, f"no script files under {FAERUN}"
    return files


def test_every_faerun_script_file_parses(faerun_files, record_property):
    failures: list[str] = []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for path in faerun_files:
            text, _ = read_text(path)
            try:
                parse(text, str(path.relative_to(REPO)))
            except PdxSyntaxError as exc:
                failures.append(str(exc))
    record_property("files_parsed", len(faerun_files) - len(failures))
    record_property("files_total", len(faerun_files))
    assert not failures, (
        f"{len(failures)}/{len(faerun_files)} files failed to parse:\n"
        + "\n".join(failures[:20])
    )


def test_a_sample_of_faerun_round_trips(faerun_files, record_property):
    step = max(1, len(faerun_files) // ROUNDTRIP_SAMPLE)
    sample = faerun_files[::step][:ROUNDTRIP_SAMPLE]
    failures: list[str] = []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for path in sample:
            name = str(path.relative_to(REPO))
            text, _ = read_text(path)
            first = parse(text, name)
            second = parse(write(first), name)
            if not structurally_equal(first, second):
                failures.append(name)
    record_property("files_round_tripped", len(sample) - len(failures))
    assert not failures, "round trip changed the tree for:\n" + "\n".join(failures)


def test_faerun_encodings_are_all_decodable(faerun_files):
    """Every file decodes; the sniffer reports which encoding it used."""
    counts: dict[str, int] = {}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for path in faerun_files:
            _, used = read_text(path)
            counts[used] = counts.get(used, 0) + 1
    assert sum(counts.values()) == len(faerun_files)
    # Faerûn is a CK2 mod edited on modern machines: it holds both.
    assert set(counts) <= {"utf-8-sig", "cp1252"}
