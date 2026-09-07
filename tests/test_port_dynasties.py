"""Dynasty conversion: string ids, the name shape change, the dropped keys."""

from __future__ import annotations

from ck2ck3.pdx import Block, Node, parse, write
from ck2ck3.port.dynasties import DynastyPort, convert_dynasty_file, output_name

SAMPLE = """
###ÄNSI
1 = { name = "Bhaal" culture = highcoaster used_for_random = no}
2 = {
    name = "Dlardrageth"
    culture = "feyri"
    coat_of_arms = {
        template = 0
        layer = { texture = 10 texture_internal = 11 emblem = 0 color = 0 }
    }
    used_for_random = no
}
4 = { name = "Monster" culture = monster religion = arcane }
"""


def convert(text: str = SAMPLE) -> tuple[str, DynastyPort]:
    port = DynastyPort()
    block = convert_dynasty_file(parse(text), port)
    return write(block), port


def test_ids_are_prefixed_strings() -> None:
    out, port = convert()
    assert "fae_1 = {" in out
    assert "fae_2 = {" in out
    assert port.id_map == {"1": "fae_1", "2": "fae_2", "4": "fae_4"}


def test_name_becomes_a_loc_key_and_the_literal_goes_to_the_yml() -> None:
    out, port = convert()
    assert 'name = "dynn_fae_2"' in out
    assert port.loc["dynn_fae_2"] == "Dlardrageth"
    # The literal also stays visible in the script as a comment.
    assert '# CK2: name = "Dlardrageth"' in out


def test_culture_is_kept_verbatim() -> None:
    out, _ = convert()
    assert "culture = highcoaster" in out
    assert "culture = feyri" in out


def test_used_for_random_and_religion_are_commented() -> None:
    out, port = convert()
    assert "# CK2: used_for_random = no" in out
    assert "# CK2: religion = arcane" in out
    assert sum(
        n for (k, _l, _r), n in port.report.dropped.items() if k == "used_for_random"
    ) == 2
    assert sum(
        n for (k, _l, _r), n in port.report.dropped.items() if k == "religion"
    ) == 1


def test_coat_of_arms_is_dropped_and_recorded() -> None:
    out, port = convert()
    assert "# CK2: coat_of_arms = { template layer }" in out
    assert "texture_internal" not in out
    assert len(port.dropped_coa) == 1
    ck3_id, ck2_id, name, culture, script = port.dropped_coa[0]
    assert (ck3_id, ck2_id, name, culture) == ("fae_2", "2", "Dlardrageth", "feyri")
    assert "texture_internal" in script  # the CK2 block survives in the evidence CSV


def test_ck2_codepage_marker_does_not_reach_the_output() -> None:
    out, _ = convert()
    assert "NSI" not in out


def test_missing_name_or_culture_warns() -> None:
    _, port = convert("9 = { }")
    assert any("has no name" in w for w in port.report.warnings)
    assert any("has no culture" in w for w in port.report.warnings)


def test_unknown_dynasty_key_is_commented_and_warned() -> None:
    out, port = convert('9 = { name = "X" culture = y sigil = 3 }')
    assert "# CK2: sigil = 3" in out
    assert any("sigil" in w for w in port.report.warnings)


def test_non_dynasty_top_level_entry_is_commented() -> None:
    out, port = convert("some_flag = yes")
    assert "# CK2: some_flag = yes (not a dynasty)" in out
    assert port.report.counts["dynasties"] == 0


def test_output_name() -> None:
    assert output_name("Faerun_Dynasties.txt") == "fae_faerun_dynasties.txt"
    assert output_name("01_animal_dynasties.txt") == "fae_01_animal_dynasties.txt"


def test_loc_keys_are_unique_per_dynasty() -> None:
    _, port = convert()
    assert len(port.loc) == len({k for k in port.loc})
    assert set(port.loc) == {"dynn_fae_1", "dynn_fae_2", "dynn_fae_4"}


def test_the_written_block_reparses() -> None:
    out, _ = convert()
    doc = parse(out)
    keys = [e.key for e in doc.entries if isinstance(e, Node)]
    assert keys == ["fae_1", "fae_2", "fae_4"]
    for entry in doc.entries:
        assert isinstance(entry, Node) and isinstance(entry.value, Block)
