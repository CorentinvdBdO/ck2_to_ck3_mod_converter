"""scripts/dna_parse.py: ethnicity gene-table resolution and deterministic
DNA sampling.

Research prototype (lane research-races, docs/research_race_tooling.md) — not
a converter reader/writer, but tested the same way: a fixture snippet of the
real ethnicity grammar (`template =` / `using =` inheritance included),
exercised without touching the game install.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "scripts"
sys.path.insert(0, str(REPO / "src"))

spec = importlib.util.spec_from_file_location("dna_parse", SCRIPTS / "dna_parse.py")
dna_parse = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dna_parse)

from ck2ck3.pdx import parser as pdx_parser  # noqa: E402

FIXTURE = """
base_ethnicity = {
	skin_color = {
		10 = { 0.5 0.4 0.8 0.5 }
	}
	hair_color = {
		10 = { 0.1 0.1 0.5 0.5 }
	}
	eye_color = {
		10 = { 0.0 0.0 1.0 1.0 }
	}
	gene_eyebrows_shape = {
		10 = { name = avg_spacing_avg_thickness range = { 0.5 1.0 } }
	}
}

child_ethnicity = {
	template = "base_ethnicity"

	gene_eyebrows_shape = {
		10 = { name = far_spacing_low_thickness range = { 0.2 0.4 } }
		5 = { name = close_spacing_high_thickness range = { 0.2 0.4 } }
	}
}
"""


def _write_fixture(tmp_path: Path) -> Path:
    d = tmp_path / "ethnicities"
    d.mkdir()
    (d / "00_fixture.txt").write_text(FIXTURE, encoding="utf-8")
    return d


def test_index_ethnicities_finds_both_blocks(tmp_path):
    d = _write_fixture(tmp_path)
    index = dna_parse.index_ethnicities(d)
    assert set(index) == {"base_ethnicity", "child_ethnicity"}


def test_resolve_gene_table_inherits_via_template_and_overrides_by_key(tmp_path):
    d = _write_fixture(tmp_path)
    index = dna_parse.index_ethnicities(d)
    table = dna_parse.resolve_gene_table("child_ethnicity", index)
    # inherited from base_ethnicity, untouched by the child:
    assert set(table) == {"skin_color", "hair_color", "eye_color", "gene_eyebrows_shape"}
    # the child's own gene_eyebrows_shape replaces the base's wholesale
    # (2 options, not 1) rather than merging the two weighted lists:
    assert len(table["gene_eyebrows_shape"]) == 2
    names = {opt[0] for _, opt in table["gene_eyebrows_shape"]}
    assert names == {"far_spacing_low_thickness", "close_spacing_high_thickness"}


def test_resolve_gene_table_tolerates_a_missing_using_target(tmp_path):
    # verified vanilla 1.19 quirk this prototype must not crash on:
    # 01_ethnicities_mediterranean.txt declares using = "basque" with no
    # basque block in this install.
    d = tmp_path / "ethnicities"
    d.mkdir()
    (d / "00_fixture.txt").write_text(
        'orphan = {\n\tusing = "nonexistent"\n\tskin_color = {\n\t\t10 = { 0.5 0.4 0.8 0.5 }\n\t}\n}\n',
        encoding="utf-8",
    )
    index = dna_parse.index_ethnicities(d)
    table = dna_parse.resolve_gene_table("orphan", index)
    assert set(table) == {"skin_color"}


def test_sample_dna_is_deterministic_in_the_seed_key(tmp_path):
    d = _write_fixture(tmp_path)
    index = dna_parse.index_ethnicities(d)
    table = dna_parse.resolve_gene_table("child_ethnicity", index)
    a = dna_parse.sample_dna(table, "seed:0")
    b = dna_parse.sample_dna(table, "seed:0")
    c = dna_parse.sample_dna(table, "seed:1")
    assert a == b
    assert a != c


def test_sample_dna_bytes_are_in_range(tmp_path):
    d = _write_fixture(tmp_path)
    index = dna_parse.index_ethnicities(d)
    table = dna_parse.resolve_gene_table("child_ethnicity", index)
    for i in range(20):
        genes = dna_parse.sample_dna(table, f"seed:{i}")
        for gene, payload in genes.items():
            nums = [v for v in payload[1:] if isinstance(v, int)]
            assert nums, f"no byte values in {gene}={payload!r}"
            assert all(0 <= n <= 255 for n in nums), f"{gene}={payload!r} out of 0..255"


def test_format_dna_entry_round_trips_through_the_real_parser(tmp_path):
    d = _write_fixture(tmp_path)
    index = dna_parse.index_ethnicities(d)
    table = dna_parse.resolve_gene_table("child_ethnicity", index)
    genes = dna_parse.sample_dna(table, "roundtrip")
    text = dna_parse.format_dna_entry("fae_demo_0000", genes)
    out = tmp_path / "sample.txt"
    out.write_text(text, encoding="utf-8")
    reparsed = pdx_parser.parse_file(out)
    assert not reparsed.problems
    genes_block = reparsed["fae_demo_0000"]["portrait_info"]["genes"]
    assert len(genes_block.keys()) == len(table)
