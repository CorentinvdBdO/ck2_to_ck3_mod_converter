"""The `religions` step: reader, the doctrine decision table, holy sites, loc.

The doctrine tests are the point of this file: every branch of
`decide_doctrines` is a row of `mappings/religion_fields.csv`, and a faith that
misses one of the 23 mandatory doctrine groups does not load.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ck2ck3.config import Config
from ck2ck3.context import Context
from ck2ck3.pdx import Block, Node, parse, parse_file, write
from ck2ck3.pdx.encoding import CK3_ENCODING
from ck2ck3.steps import religions as step

REPO = Path(__file__).resolve().parents[1]
REFERENCE_CONFIG = REPO / "configs" / "faerun.toml"
FAERUN = REPO / "Faerun" / "Faerun"

FIXTURE = """
test_pantheon_group = {
\tgraphical_culture = westerngfx
\thostile_within_group = yes
\tplayable = yes
\tcolor = { 0.8 0.8 0.6 }
\tmale_names = { }

\ttest_good = {
\t\ticon = 7
\t\theresy_icon = 7
\t\tcolor = { 0.1 0.2 0.3 }
\t\thigh_god_name = GOD_TEST
\t\tgod_names = { GOD_A GOD_B }
\t\tevil_god_names = { GOD_EVIL GOD_WORSE }
\t\tscripture_name = words_of_test
\t\tpriest_title = PRIEST
\t\tcrusade_name = CRUSADE
\t\tfeminist = yes
\t\tpriests_can_marry = yes
\t\tpriests_can_inherit = yes
\t\tfemale_temple_holders = yes
\t\tcousin_marriage = yes
\t\tcan_grant_divorce = yes
\t\tcan_retire_to_monastery = yes
\t\tmax_consorts = 3
\t\tintermarry = test_evil
\t\tmatrilineal_marriages = yes
\t\tuses_jizya_tax = yes
\t\tcharacter_modifier = { learning = 2 }
\t}

\ttest_evil = {
\t\ticon = 8
\t\tcolor = { 0.4 0 0 }
\t\thigh_god_name = GOD_DARK
\t\tgod_names = { GOD_DARK }
\t\tevil_god_names = { GOD_A }
\t\tscripture_name = words_of_night
\t\treformed = test_good
\t\tpriests_can_marry = no
\t\tpriests_can_inherit = no
\t\tfemale_temple_holders = no
\t\tcan_grant_divorce = no
\t\tpsc_marriage = yes
\t\twomen_can_take_consorts = yes
\t\tmen_can_take_consorts = no
\t\tmax_consorts = 1
\t\tcan_excommunicate = yes
\t\tpacifist = yes
\t}
}
"""


@pytest.fixture
def groups(tmp_path: Path) -> list[step.CK2ReligionGroup]:
    folder = tmp_path / "common" / "religions"
    folder.mkdir(parents=True)
    (folder / "test.txt").write_text(FIXTURE, encoding="cp1252")
    return step.read_ck2_religions(tmp_path)


def _by_id(groups) -> dict[str, step.CK2Religion]:
    return {r.id: r for g in groups for r in g.religions}


# -- reader -----------------------------------------------------------------
def test_reader_separates_group_keys_from_religions(groups):
    assert [g.id for g in groups] == ["test_pantheon_group"]
    assert [r.id for r in groups[0].religions] == ["test_good", "test_evil"]
    assert groups[0].hostile_within_group is True


def test_reader_ignores_block_valued_group_keys(tmp_path: Path):
    # `color`, `male_names` and Faerûn's `interface_skin` sit at the same brace
    # depth as a religion; only the religion markers tell them apart.
    folder = tmp_path / "common" / "religions"
    folder.mkdir(parents=True)
    (folder / "t.txt").write_text(
        "g = { color = { 1 1 1 } interface_skin = { a = 1 } male_names = { A }"
        " r = { scripture_name = s evil_god_names = { E } } }",
        encoding="cp1252",
    )
    groups = step.read_ck2_religions(tmp_path)
    assert [r.id for r in groups[0].religions] == ["r"]


def test_group_slug_strips_group():
    assert step.group_slug("good_human_pantheon_group") == "good_human_pantheon"
    assert step.group_slug("drow_pantheon") == "drow_pantheon"


# -- doctrine decision table ------------------------------------------------
def test_every_mandatory_doctrine_group_is_filled(groups):
    for religion in _by_id(groups).values():
        doctrines = step.decide_doctrines(religion)
        assert set(doctrines) == set(step.PAGANISM_DEFAULTS)
        assert all(doctrines.values())


def test_gender_doctrine_table(groups):
    religions = _by_id(groups)
    # feminist = yes
    assert (
        step.decide_doctrines(religions["test_good"])["doctrine_gender"]
        == "doctrine_gender_equal"
    )
    # women_can_take_consorts = yes + men_can_take_consorts = no wins over it
    assert (
        step.decide_doctrines(religions["test_evil"])["doctrine_gender"]
        == "doctrine_gender_female_dominated"
    )


def test_marriage_divorce_and_consanguinity_tables(groups):
    good = step.decide_doctrines(_by_id(groups)["test_good"])
    evil = step.decide_doctrines(_by_id(groups)["test_evil"])
    assert good["doctrine_marriage_type"] == "doctrine_concubines"
    assert good["doctrine_divorce"] == "doctrine_divorce_approval"
    assert good["doctrine_consanguinity"] == "doctrine_consanguinity_cousins"
    assert evil["doctrine_divorce"] == "doctrine_divorce_disallowed"
    assert evil["doctrine_consanguinity"] == "doctrine_consanguinity_dynastic"


def test_clerical_tables(groups):
    good = step.decide_doctrines(_by_id(groups)["test_good"])
    evil = step.decide_doctrines(_by_id(groups)["test_evil"])
    assert good["doctrine_clerical_gender"] == "doctrine_clerical_gender_either"
    assert good["doctrine_clerical_marriage"] == "doctrine_clerical_marriage_allowed"
    assert (
        good["doctrine_clerical_succession"]
        == "doctrine_clerical_succession_temporal_appointment"
    )
    assert evil["doctrine_clerical_gender"] == "doctrine_clerical_gender_male_only"
    assert evil["doctrine_clerical_marriage"] == "doctrine_clerical_marriage_disallowed"
    assert (
        evil["doctrine_clerical_succession"]
        == "doctrine_clerical_succession_spiritual_appointment"
    )


def test_head_of_faith_follows_can_excommunicate(groups):
    religions = _by_id(groups)
    assert (
        step.decide_doctrines(religions["test_good"])["doctrine_head_of_faith"]
        == "doctrine_no_head"
    )
    assert (
        step.decide_doctrines(religions["test_evil"])["doctrine_head_of_faith"]
        == "doctrine_temporal_head"
    )


def test_theism_follows_the_size_of_the_ck2_pantheon(groups):
    religions = _by_id(groups)
    assert (
        step.decide_doctrines(religions["test_good"])["doctrine_theism"]
        == "doctrine_polytheist"
    )
    assert (
        step.decide_doctrines(religions["test_evil"])["doctrine_theism"]
        == "doctrine_monotheist"
    )


def test_pluralism_follows_the_intermarry_graph(groups):
    religions = _by_id(groups)
    # test_good intermarries only inside its own group
    assert (
        step.decide_doctrines(religions["test_good"])["doctrine_pluralism"]
        == "doctrine_pluralism_righteous"
    )
    # test_evil has no intermarry line at all
    assert (
        step.decide_doctrines(religions["test_evil"])["doctrine_pluralism"]
        == "doctrine_pluralism_fundamentalist"
    )


# -- tenets -----------------------------------------------------------------
def test_tenets_are_always_exactly_three(groups):
    for religion in _by_id(groups).values():
        assert len(step.decide_tenets(religion, None)) == 3


def test_ck2_flags_displace_the_default_tenets(groups):
    religions = _by_id(groups)
    good = step.decide_tenets(religions["test_good"], None)
    assert good[0] == "tenet_monasticism"  # can_retire_to_monastery = yes
    evil = step.decide_tenets(religions["test_evil"], None)
    assert evil[0] == "tenet_pacifism"  # pacifist = yes


def test_override_wins_over_everything(groups):
    religion = _by_id(groups)["test_good"]
    chosen = step.decide_tenets(religion, ["tenet_astrology", "a", "b"])
    assert chosen == ["tenet_astrology", "a", "b"]


# -- blocks -----------------------------------------------------------------
def test_family_is_one_per_group_and_notes_the_hostility_flag(groups):
    node = step.build_families("fae", groups).entries[0]
    assert node.key == "rf_fae_test_pantheon"
    assert node.block["hostility_doctrine"] == step.HOSTILITY_DOCTRINE
    assert any("hostile_within_group = yes" in c for c in node.leading_comments)


def _faith(groups, faith_id, **kwargs):
    religion = _by_id(groups)[faith_id]
    doctrines = {r.id: step.decide_doctrines(r) for r in groups[0].religions}
    defaults = dict(
        doctrines=doctrines[faith_id],
        religion_doctrines=step._religion_level_doctrines(groups[0], doctrines),
        tenets=step.decide_tenets(religion, None),
        holy_sites=[],
        unreformed=bool(religion.reformed_into),
    )
    defaults.update(kwargs)
    return step.build_faith("fae", religion, **defaults)


def test_faith_keeps_the_ck2_colour_and_drops_the_icon_index(groups):
    node, _ = _faith(groups, "test_good")
    assert write(node.block).count("color = { 0.1 0.2 0.3 }") == 1
    assert "icon" not in node.block
    assert any("CK2: icon = 7" in c for c in node.block.end_comments)


def test_faith_omits_doctrines_the_religion_already_sets(groups):
    doctrines = {r.id: step.decide_doctrines(r) for r in groups[0].religions}
    shared = step._religion_level_doctrines(groups[0], doctrines)
    node, _ = _faith(groups, "test_good")
    emitted = [str(v) for v in node.block.get_all("doctrine")]
    for doctrine in shared.values():
        assert doctrine not in emitted


def test_unreformed_faith_gets_the_doctrine_and_the_mandatory_icon(groups):
    node, _ = _faith(groups, "test_evil")
    emitted = [str(v) for v in node.block.get_all("doctrine")]
    assert "unreformed_faith_doctrine" in emitted
    assert node.block["reformed_icon"] == step.DEFAULT_REFORMED_ICON


def test_jizya_becomes_its_own_doctrine(groups):
    node, _ = _faith(groups, "test_good")
    assert "special_doctrine_jizya" in [str(v) for v in node.block.get_all("doctrine")]


def test_holy_sites_are_capped_at_five_and_the_rest_commented(groups):
    sites = [f"c_p{n}" for n in range(7)]
    node, _ = _faith(groups, "test_good", holy_sites=sites)
    emitted = [str(v) for v in node.block.get_all("holy_site")]
    assert emitted == [f"fae_hs_p{n}" for n in range(5)]
    dropped = [c for c in node.block.end_comments if "dropped" in c]
    assert len(dropped) == 2


def test_unmapped_ck2_keys_become_comments(groups):
    node, _ = _faith(groups, "test_good")
    joined = "\n".join(node.block.end_comments)
    assert "# CK2: matrilineal_marriages = yes (no CK3 equivalent:" in joined
    assert "# CK2: character_modifier = { ... } (no CK3 equivalent:" in joined
    assert "# CK2: intermarry = test_evil" in joined


def test_faith_localization_and_its_rename_rows(groups):
    block, renames = step.faith_localization(_by_id(groups)["test_good"])
    assert block["HighGodName"] == "GOD_TEST"
    assert block["HighGodNamePossessive"] == "GOD_TEST_possessive"
    assert [str(v) for v in block["GoodGodNames"].list_values()] == ["GOD_A", "GOD_B"]
    assert block["DevilName"] == "GOD_EVIL"
    assert block["ReligiousText3"] == "words_of_test"
    assert block["PriestMalePlural"] == "PRIEST_plural"
    assert block["GHWNamePlural"] == "CRUSADE_plural"
    assert ("GOD_TEST", "GOD_TEST_possessive") in renames
    assert ("PRIEST", "PRIEST_plural") in renames
    assert ("CRUSADE", "CRUSADE_plural") in renames


def test_holy_site_type_is_shared_per_county():
    block = step.build_holy_sites("fae", ["c_waterdeep"])
    node = block.entries[0]
    assert node.key == "fae_hs_waterdeep"
    assert node.block["county"] == "c_waterdeep"


def test_religion_carries_the_localization_baseline_and_faiths(tmp_path: Path, groups):
    game = Config.load(REFERENCE_CONFIG).ck3_game
    if not game.is_dir():
        pytest.skip("CK3 game files not present")
    ctx = Context(Config.load(REFERENCE_CONFIG, out=tmp_path), dry_run=True)
    baseline = step.build_localization_baseline(ctx)
    assert len(baseline.keys()) > 100
    doctrines = {r.id: step.decide_doctrines(r) for r in groups[0].religions}
    node = step.build_religion(
        "fae",
        groups[0],
        baseline=baseline,
        doctrines_by_faith=doctrines,
        faiths=Block(entries=[Node(key="test_good", value=Block())]),
        pagan_roots=True,
    )
    assert node.key == "fae_test_pantheon_religion"
    assert node.block["family"] == "rf_fae_test_pantheon"
    assert node.block["pagan_roots"] is True
    assert "HighGodName" in node.block["localization"]
    assert "test_good" in node.block["faiths"]


def test_opinion_keys_cover_faith_religion_and_family(groups):
    keys = step.opinion_keys("fae", groups)
    assert "test_good_opinion" in keys
    assert "fae_test_pantheon_religion_opinion" in keys
    assert "rf_fae_test_pantheon_opinion" in keys


# -- output ownership -------------------------------------------------------
def test_outputs_match_what_the_step_writes(tmp_path: Path):
    if not FAERUN.is_dir():
        pytest.skip("Faerun/ not cloned")
    ctx = Context(Config.load(REFERENCE_CONFIG, out=tmp_path), dry_run=True)
    result = step.run(ctx)
    for path in result.written:
        rel = path.relative_to(tmp_path).as_posix()
        assert any(
            rel == owned or rel.startswith(f"{owned}/") for owned in step.OUTPUTS
        ), rel


# -- CK3 vocabulary ---------------------------------------------------------
def _doctrine_groups(game: Path) -> dict[str, str]:
    """CK3 doctrine id → its doctrine group."""
    out: dict[str, str] = {}
    folder = game / "common" / "religion" / "doctrine_group_types"
    for path in sorted(folder.glob("*.txt")):
        doc = parse_file(path, encoding=CK3_ENCODING, lenient=True)
        for entry in doc.entries:
            if not isinstance(entry, Node) or not isinstance(entry.value, Block):
                continue
            types = entry.value.get("doctrine_types")
            if isinstance(types, Block):
                for value in types.list_values():
                    out[str(value)] = entry.key
    return out


@pytest.mark.slow
def test_every_doctrine_the_step_emits_exists_and_sits_in_the_right_group():
    game = Config.load(REFERENCE_CONFIG).ck3_game
    if not game.is_dir():
        pytest.skip("CK3 game files not present")
    lookup = _doctrine_groups(game)
    for doctrine_group, doctrine in step.PAGANISM_DEFAULTS.items():
        assert lookup.get(doctrine) == doctrine_group, doctrine
    for tenet in (*step.DEFAULT_TENETS, *(t for _, t in step.TENET_OF_FLAG)):
        assert lookup.get(tenet) == "doctrine_core_tenets", tenet
    assert lookup.get("unreformed_faith_doctrine") == "unreformed_faith"
    assert lookup.get("special_doctrine_jizya") == "has_jizya_doctrine"


@pytest.mark.slow
def test_the_23_mandatory_doctrine_groups_are_exactly_the_default_keys():
    game = Config.load(REFERENCE_CONFIG).ck3_game
    if not game.is_dir():
        pytest.skip("CK3 game files not present")
    assert len(step.PAGANISM_DEFAULTS) == 23
    lookup = _doctrine_groups(game)
    assert set(step.PAGANISM_DEFAULTS) <= set(lookup.values())


# -- the real Faerûn --------------------------------------------------------
@pytest.mark.slow
def test_faerun_counts():
    if not FAERUN.is_dir():
        pytest.skip("Faerun/ not cloned")
    groups = step.read_ck2_religions(FAERUN)
    religions = [r for g in groups for r in g.religions]
    assert len(groups) == 15
    assert len(religions) == 94
    assert len({r.id for r in religions}) == 94


@pytest.mark.slow
def test_faerun_holy_sites_are_all_counties_and_within_the_cap():
    if not FAERUN.is_dir():
        pytest.skip("Faerun/ not cloned")
    sites = step.read_holy_sites(FAERUN)
    assert sum(len(v) for v in sites.values()) == 470
    assert len(sites) == 94
    assert max(len(v) for v in sites.values()) == 5
    assert all(c.startswith("c_") for marks in sites.values() for c in marks)


@pytest.mark.slow
def test_faerun_run_counts(tmp_path: Path):
    if not FAERUN.is_dir():
        pytest.skip("Faerun/ not cloned")
    ctx = Context(Config.load(REFERENCE_CONFIG, out=tmp_path), dry_run=True)
    result = step.run(ctx)
    assert result.counts["religion_groups"] == 15
    assert result.counts["families"] == 15
    assert result.counts["faiths"] == 94
    assert result.counts["holy_site_links"] == 470
    assert result.counts["holy_site_types"] == 255
    assert result.counts["faiths_without_holy_site"] == 0


@pytest.mark.slow
def test_every_faerun_faith_resolves_all_23_groups():
    if not FAERUN.is_dir():
        pytest.skip("Faerun/ not cloned")
    for group in step.read_ck2_religions(FAERUN):
        for religion in group.religions:
            doctrines = step.decide_doctrines(religion)
            assert set(doctrines) == set(step.PAGANISM_DEFAULTS), religion.id


@pytest.mark.slow
def test_generated_religion_files_round_trip(tmp_path: Path):
    if not FAERUN.is_dir():
        pytest.skip("Faerun/ not cloned")
    ctx = Context(Config.load(REFERENCE_CONFIG, out=tmp_path), dry_run=False)
    step.run(ctx)
    for path in sorted(tmp_path.rglob("*.txt")):
        first = parse_file(path, encoding=CK3_ENCODING)
        again = parse(write(first))
        assert len(first.entries) == len(again.entries), path
