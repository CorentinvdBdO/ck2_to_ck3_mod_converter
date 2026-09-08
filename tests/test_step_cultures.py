"""The `cultures` step: readers, derivation rules, block shapes, CK3 vocabulary.

Fast tests run on inline CK2 fixture snippets. The `slow` ones parse the whole
Faerûn clone and assert the counts the lane is judged on.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ck2ck3.config import Config
from ck2ck3.context import Context
from ck2ck3.pdx import Block, Node, parse, parse_file, write
from ck2ck3.pdx.encoding import CK3_ENCODING
from ck2ck3.steps import cultures as step

REPO = Path(__file__).resolve().parents[1]
REFERENCE_CONFIG = REPO / "configs" / "faerun.toml"
FAERUN = REPO / "Faerun" / "Faerun"

FIXTURE = """
test_group = { # two cultures
\tgraphical_cultures = { norsegfx westerngfx }

\ttest_raider = {
\t\tgraphical_cultures = { norsegfx }
\t\tunit_graphical_cultures = { mongolgfx }
\t\tcolor = { 0.1 0.2 0.3 }
\t\tmale_names = { Ari Bjorn }
\t\tfemale_names = { Ada Bera }
\t\tseafarer = yes
\t\tallow_looting = yes
\t\tfrom_dynasty_prefix = "af "
\t\tmale_patronym = "sson"
\t\tfemale_patronym = "sdottir"
\t\tprefix = no
\t\tpat_grf_name_chance = 40
\t\tdynasty_name_first = yes
\t\tmodifier = default_culture_modifier
\t\tbaron_titles_hidden = no
\t}

\ttest_farmer = {
\t\tcolor = { 0.9 0.9 0.9 }
\t\tmale_names = { Cai }
\t\tfemale_names = { Cora }
\t}
}
"""


@pytest.fixture
def groups(tmp_path: Path) -> list[step.CK2CultureGroup]:
    folder = tmp_path / "common" / "cultures"
    folder.mkdir(parents=True)
    (folder / "test.txt").write_text(FIXTURE, encoding="cp1252")
    (folder / "00_cultures.txt").write_text("", encoding="cp1252")
    return step.read_ck2_cultures(tmp_path)


# -- reader -----------------------------------------------------------------
def test_reader_finds_groups_and_cultures(groups):
    assert [g.id for g in groups] == ["test_group"]
    group = groups[0]
    assert group.source == "test.txt"
    assert [c.id for c in group.cultures] == ["test_raider", "test_farmer"]
    assert group.graphical_cultures == ["norsegfx", "westerngfx"]


def test_reader_skips_the_empty_faerun_file(groups):
    # 00_cultures.txt is 0 bytes in Faerûn; parsing it must not add a group.
    assert len(groups) == 1


def test_reader_does_not_mistake_a_block_key_for_a_culture(tmp_path: Path):
    folder = tmp_path / "common" / "cultures"
    folder.mkdir(parents=True)
    (folder / "t.txt").write_text(
        "g = { color = { 1 1 1 } alternate_start = { always = no }"
        " c = { male_names = { A } female_names = { B } } }",
        encoding="cp1252",
    )
    groups = step.read_ck2_cultures(tmp_path)
    assert [c.id for c in groups[0].cultures] == ["c"]


def test_group_slug_strips_both_suffixes():
    assert step.group_slug("dark_elf_group") == "dark_elf"
    assert step.group_slug("aberration_culture_group") == "aberration"
    assert step.group_slug("weird") == "weird"


# -- derivation rules -------------------------------------------------------
def test_ethos_is_bellicose_for_looters_and_seafarers(groups):
    raider, farmer = groups[0].cultures
    assert step.derive_ethos(raider) == "ethos_bellicose"
    assert step.derive_ethos(farmer) == "ethos_communal"


def test_martial_custom_and_head_determination_take_the_ck3_default(groups):
    farmer = groups[0].cultures[1]
    assert step.derive_martial_custom(farmer) == "martial_custom_male_only"
    assert step.derive_head_determination(farmer) == "head_determination_domain"


def test_traditions_without_the_override_table_are_the_ck2_flags(groups):
    raider, farmer = groups[0].cultures
    assert step.derive_traditions(raider) == [
        "tradition_seafaring",
        "tradition_practiced_pirates",
    ]
    # the gap the override table exists to close: no flag, no tradition
    assert step.derive_traditions(farmer) == []


@pytest.mark.parametrize(
    "index,row,expected",
    [
        # no flags: the group row is the whole answer
        (1, ["tradition_forest_folk", "tradition_sacred_groves"],
         ["tradition_forest_folk", "tradition_sacred_groves"]),
        # flags first, then the row, in file order
        (0, ["tradition_mountain_homes"],
         ["tradition_seafaring", "tradition_practiced_pirates",
          "tradition_mountain_homes"]),
        # deduped against the flag traditions, not repeated
        (0, ["tradition_seafaring", "tradition_hunters"],
         ["tradition_seafaring", "tradition_practiced_pirates",
          "tradition_hunters"]),
        # a deliberate empty row leaves only the flags
        (0, [], ["tradition_seafaring", "tradition_practiced_pirates"]),
        (1, [], []),
    ],
)
def test_traditions_merge_the_flags_with_the_group_override(
    groups, index, row, expected
):
    culture = groups[0].cultures[index]
    assert step.derive_traditions(culture, {"test_group": row}) == expected


def test_traditions_are_truncated_to_the_ck3_maximum(groups):
    row = [f"tradition_x{i}" for i in range(step.MAX_TRADITIONS + 3)]
    out = step.derive_traditions(groups[0].cultures[0], {"test_group": row})
    assert len(out) == step.MAX_TRADITIONS
    # the CK2-flag traditions are the ones that survive the cut
    assert out[:2] == ["tradition_seafaring", "tradition_practiced_pirates"]


def test_traditions_block_names_the_override_file(groups):
    node = _culture_node(
        groups,
        1,
        traditions_of_group={"test_group": ["tradition_forest_folk"]},
    )
    text = write(Block(entries=[node]))
    assert "tradition_forest_folk" in text
    assert "assumed placeholders, submod to replace" in text


def test_override_table_separators_and_dedupe(tmp_path: Path):
    config = Config.load(REFERENCE_CONFIG, out=tmp_path)
    table = step.read_traditions_of_group(config)
    assert table, "overrides/traditions_of_culture_group.csv did not parse"
    for group_id, traditions in table.items():
        assert len(set(traditions)) == len(traditions), group_id
        assert len(traditions) <= step.MAX_TRADITIONS, group_id
        for tradition in traditions:
            assert tradition.startswith("tradition_"), (group_id, tradition)


def test_override_table_distinguishes_empty_from_missing(tmp_path: Path):
    config = Config.load(REFERENCE_CONFIG, out=tmp_path)
    table = step.read_traditions_of_group(config)
    # the documented "no traditions" groups: a row that is present and empty
    assert table.get("undead_group") == []
    assert table.get("construct_group") == []
    assert table.get("cat_group") == []
    assert "not_a_culture_group" not in table


# -- pillars ----------------------------------------------------------------
def test_heritage_carries_the_species_parameter(groups):
    block, warnings = step.build_heritages("fae", groups, {"test_group": "orc"})
    assert warnings == []
    text = write(block)
    assert "heritage_fae_test = {" in text  # _group is stripped
    assert "type = heritage" in text
    assert "species_orc = yes" in text


def test_missing_race_override_warns_and_falls_back(groups):
    block, warnings = step.build_heritages("fae", groups, {})
    assert len(warnings) == 1
    assert "race_of_culture_group.csv" in warnings[0]
    assert f"species_{step.DEFAULT_RACE} = yes" in write(block)


def test_language_pillar_borrows_its_first_culture_colour(groups):
    text = write(step.build_languages("fae", groups))
    assert "language_fae_test = {" in text
    assert "type = language" in text
    # test_raider's colour, because CK2 culture groups have none of their own
    assert "color = { 0.1 0.2 0.3 }" in text


# -- culture ----------------------------------------------------------------
def _culture_node(groups, index=0, **kwargs):
    defaults = dict(
        gfx_map={}, ethnicities={}, culture_defaults={}, traditions_of_group={}
    )
    defaults.update(kwargs)
    return step.build_culture("fae", groups[0].cultures[index], **defaults)


def test_culture_has_every_mandatory_ck3_key(groups):
    body = _culture_node(groups).block
    for key in (
        "color",
        "ethos",
        "heritage",
        "language",
        "martial_custom",
        "head_determination",
        "name_list",
        "ethnicities",
        "coa_gfx",
        "building_gfx",
        "clothing_gfx",
        "unit_gfx",
    ):
        assert key in body, key


def test_culture_keeps_the_ck2_colour_verbatim(groups):
    assert write(_culture_node(groups).block).count("color = { 0.1 0.2 0.3 }") == 1


def test_unmapped_ck2_keys_become_comments(groups):
    comments = _culture_node(groups).block.end_comments
    joined = "\n".join(comments)
    assert "# CK2: modifier = default_culture_modifier (no CK3 equivalent:" in joined
    assert "# CK2: baron_titles_hidden = no (no CK3 equivalent:" in joined
    # a mapped key never turns into a comment
    assert "male_names" not in joined


def test_gfx_chain_is_culture_then_group_then_default(groups):
    gfx_map = {
        "norsegfx": {
            "coa_gfx": "norse_coa_gfx",
            "building_gfx": "norse_building_gfx",
            "clothing_gfx": "fp1_norse_clothing_gfx",
            "unit_gfx": "norse_unit_gfx",
        },
        "westerngfx": {
            "coa_gfx": "western_coa_gfx",
            "building_gfx": "western_building_gfx",
            "clothing_gfx": "western_clothing_gfx",
            "unit_gfx": "western_unit_gfx",
        },
        "mongolgfx": {
            "coa_gfx": "mongol_coa_gfx",
            "building_gfx": "steppe_building_gfx",
            "clothing_gfx": "mongol_clothing_gfx",
            "unit_gfx": "mongol_unit_gfx",
        },
    }
    body = _culture_node(groups, gfx_map=gfx_map).block
    assert [str(v) for v in body["coa_gfx"].list_values()] == [
        "norse_coa_gfx",
        "western_coa_gfx",
    ]
    # unit_gfx reads the CK2 culture-level unit_graphical_cultures first
    assert [str(v) for v in body["unit_gfx"].list_values()] == [
        "mongol_unit_gfx",
        "norse_unit_gfx",
        "western_unit_gfx",
    ]


def test_overrides_beat_the_derived_values(groups):
    body = _culture_node(
        groups,
        culture_defaults={
            "test_raider": {
                "ck2_culture": "test_raider",
                "ethos": "ethos_stoic",
                "martial_custom": "",
                "head_determination": "head_determination_herd",
            }
        },
    ).block
    assert body["ethos"] == "ethos_stoic"
    assert body["head_determination"] == "head_determination_herd"
    # a blank cell falls back to the derived value
    assert body["martial_custom"] == "martial_custom_male_only"


# -- name list --------------------------------------------------------------
def test_name_list_copies_names_and_chances_verbatim(groups):
    body = step.build_name_list("fae", groups[0].cultures[0]).block
    assert [str(v) for v in body["male_names"].list_values()] == ["Ari", "Bjorn"]
    assert body["pat_grf_name_chance"] == 40
    assert body["dynasty_name_first"] is True


def test_names_become_loc_keys_and_the_literals_are_collected(groups):
    """A CK3 name-list entry is a localisation key, not a display string:
    copying CK2's literals through was 77 736 "Missing loc X" errors in one
    boot (`verified` 2026-09-08, docs/evidence/game_load_2026-09-08.md)."""
    culture = groups[0].cultures[0]
    culture.block.get_node("male_names").value = parse(
        'x = { "Sergeant Reckless" 2BD71SF2 Ari Ari }'
    ).entries[0].value
    loc: dict[str, str] = {}
    body = step.build_name_list("fae", culture, loc).block
    tokens = [str(v) for v in body["male_names"].list_values()]
    assert tokens == ["Sergeant_Reckless", "name_2BD71SF2", "Ari"]
    assert loc["Sergeant_Reckless"] == "Sergeant Reckless"
    assert loc["name_2BD71SF2"] == "2BD71SF2"
    # every token is a bare, parser-safe word: no quotes, no leading digit
    assert '"' not in write(body["male_names"])


def test_patronym_literal_becomes_a_loc_key_with_always_use_patronym(groups):
    body = step.build_name_list("fae", groups[0].cultures[0]).block
    # prefix = no in the fixture, so the suffix keys are the target
    assert body["patronym_suffix_male"] == "dynnpat_suf_fae_test_raider"
    assert body["patronym_suffix_female"] == "dynnpat_suf_fae_test_raider"
    assert body["always_use_patronym"] is True
    assert body["dynasty_of_location_prefix"] == "dynnp_fae_test_raider"
    # the literal survives as a comment so nothing is lost
    assert 'af ' in write(body)


def test_prefix_yes_routes_to_the_prefix_keys(groups):
    culture = groups[0].cultures[0]
    culture.block.get_node("prefix").value = True
    body = step.build_name_list("fae", culture).block
    assert "patronym_prefix_male" in body
    assert "patronym_suffix_male" not in body


def test_name_list_of_a_bare_culture_is_just_the_names(groups):
    body = step.build_name_list("fae", groups[0].cultures[1]).block
    assert body.keys() == ["male_names", "female_names"]


# -- ethnicities and opinion formats ----------------------------------------
def test_placeholder_ethnicity_inherits_a_vanilla_one():
    text = write(step.build_placeholder_ethnicities(["orc", "elf"]))
    assert "fae_placeholder_orc = {" in text
    assert f'template = "{step.PLACEHOLDER_ETHNICITY_BASE}"' in text
    assert "# TODO real ethnicity for race orc" in text


def test_opinion_formats_use_the_vanilla_shape():
    text = write(step.build_opinion_formats(["a_opinion"]))
    assert text.strip() == "a_opinion = {\n\tdecimals = 0\n}"


def test_vanilla_declared_opinion_keys_are_skipped():
    block = step.build_opinion_formats(
        ["mine_opinion", "gur_opinion"], skip={"gur_opinion"}
    )
    assert block.keys() == ["mine_opinion"]
    assert any("gur_opinion is already declared" in c for c in block.end_comments)


# -- output ownership -------------------------------------------------------
def test_outputs_match_what_the_step_writes(tmp_path: Path, groups):
    config = Config.load(REFERENCE_CONFIG, out=tmp_path)
    ctx = Context(config, dry_run=True)
    result = step.run(ctx)
    for path in result.written:
        rel = path.relative_to(tmp_path).as_posix()
        assert any(
            rel == owned or rel.startswith(f"{owned}/") for owned in step.OUTPUTS
        ), rel


# -- CK3 vocabulary ---------------------------------------------------------
def _ck3_ids(game: Path, rel: str) -> set[str]:
    out: set[str] = set()
    for path in sorted((game / rel).glob("*.txt")):
        if path.name.startswith("_"):
            continue
        doc = parse_file(path, encoding=CK3_ENCODING, lenient=True)
        out.update(
            e.key for e in doc.entries if isinstance(e, Node) and not e.key.startswith("@")
        )
    return out


@pytest.mark.slow
def test_every_ck3_id_the_step_emits_exists_in_the_game():
    game = Config.load(REFERENCE_CONFIG).ck3_game
    if not game.is_dir():
        pytest.skip("CK3 game files not present")
    pillars = _ck3_ids(game, "common/culture/pillars")
    assert set(step.ETHOS_IDS) <= pillars
    assert set(step.MARTIAL_CUSTOM_IDS) <= pillars
    assert set(step.HEAD_DETERMINATION_IDS) <= pillars
    traditions = _ck3_ids(game, "common/culture/traditions")
    assert set(step.TRADITION_OF_FLAG.values()) <= traditions
    table = step.read_traditions_of_group(Config.load(REFERENCE_CONFIG))
    emitted = {t for row in table.values() for t in row}
    assert emitted <= traditions, sorted(emitted - traditions)
    ethnicities = _ck3_ids(game, "common/ethnicities")
    assert {step.DEFAULT_ETHNICITY, step.PLACEHOLDER_ETHNICITY_BASE} <= ethnicities
    cultures = _ck3_ids(game, "common/culture/cultures")
    for axis, value in step.DEFAULT_GFX.items():
        assert any(
            value in write(block)
            for path in (game / "common/culture/cultures").glob("*.txt")
            if not path.name.startswith("_")
            for block in [parse_file(path, encoding=CK3_ENCODING, lenient=True)]
        ), f"{axis} default {value} unused in vanilla"
    assert cultures  # sanity: the folder parsed


# -- the real Faerûn --------------------------------------------------------
@pytest.mark.slow
def test_faerun_counts():
    if not FAERUN.is_dir():
        pytest.skip("Faerun/ not cloned")
    groups = step.read_ck2_cultures(FAERUN)
    cultures = [c for g in groups for c in g.cultures]
    assert len(groups) == 67
    assert len(cultures) == 419
    assert len({c.id for c in cultures}) == 419


@pytest.mark.slow
def test_group_slugs_are_unique():
    if not FAERUN.is_dir():
        pytest.skip("Faerun/ not cloned")
    groups = step.read_ck2_cultures(FAERUN)
    slugs = [g.slug for g in groups]
    assert len(set(slugs)) == len(slugs)


@pytest.mark.slow
def test_every_faerun_culture_gets_a_complete_ck3_block(tmp_path: Path):
    if not FAERUN.is_dir():
        pytest.skip("Faerun/ not cloned")
    config = Config.load(REFERENCE_CONFIG, out=tmp_path)
    ctx = Context(config, dry_run=True)
    result = step.run(ctx)
    assert result.counts["culture_groups"] == 67
    assert result.counts["cultures"] == 419
    assert result.counts["name_lists"] == 419
    assert result.counts["missing_race_overrides"] == 0
    assert result.counts["missing_ethnicity_overrides"] == 0
    assert result.counts["missing_tradition_overrides"] == 0
    assert (
        result.counts["cultures_with_traditions"]
        + result.counts["cultures_without_traditions"]
        == 419
    )


@pytest.mark.slow
def test_every_faerun_culture_has_two_traditions_unless_deliberately_none():
    """The invariant the placeholder table exists for.

    A culture may end up with no traditions only when its CK2 group carries a
    deliberately empty row (animals, undead, constructs, the monster filler);
    every other culture gets at least two, so the CK3 culture screen is never
    blank. `docs/step_cultures_religions.md`, `Placeholder culture traditions`.
    """
    if not FAERUN.is_dir():
        pytest.skip("Faerun/ not cloned")
    config = Config.load(REFERENCE_CONFIG)
    table = step.read_traditions_of_group(config)
    groups = step.read_ck2_cultures(FAERUN)
    no_traditions = {g for g, row in table.items() if not row}
    thin: list[str] = []
    for group in groups:
        assert group.id in table, group.id
        for culture in group.cultures:
            got = step.derive_traditions(culture, table)
            if group.id in no_traditions:
                # only the CK2-flag traditions may still appear
                assert set(got) <= set(step.TRADITION_OF_FLAG.values()), culture.id
                continue
            if len(got) < 2:
                thin.append(f"{group.id}/{culture.id}")
            assert len(got) <= step.MAX_TRADITIONS, culture.id
    assert thin == []


@pytest.mark.slow
def test_generated_culture_files_round_trip(tmp_path: Path):
    if not FAERUN.is_dir():
        pytest.skip("Faerun/ not cloned")
    config = Config.load(REFERENCE_CONFIG, out=tmp_path)
    ctx = Context(config, dry_run=False)
    step.run(ctx)
    for path in sorted(tmp_path.rglob("*.txt")):
        first = parse_file(path, encoding=CK3_ENCODING)
        again = parse(write(first))
        assert len(first.entries) == len(again.entries), path


# -- dynasty names ----------------------------------------------------------
def test_dynasty_names_come_from_the_cultures_own_dynasties(groups):
    """CK2 keeps dynasty names in common/dynasties with a `culture` each; CK3
    keeps them per name list, and fewer than MINIMUM_DYNASTY_NAMES is
    `culture_name_lists.cpp:169` plus no name to mint a generated character's
    dynasty from (`verified` 2026-09-08, 838 of them)."""
    table = {"test_raider": ["dynn_fae_1", "dynn_fae_2", "dynn_fae_3"]}
    body = step.build_name_list(
        "fae", groups[0].cultures[0], {}, table
    ).block
    assert [str(v) for v in body["dynasty_names"].list_values()] == [
        "dynn_fae_1",
        "dynn_fae_2",
        "dynn_fae_3",
    ]
    assert '"dynn_fae_1"' in write(body)  # vanilla quotes them


def test_the_culture_group_tops_up_a_culture_below_the_minimum(groups):
    """Vanilla's own define says so: "Dynasty names from the culture group will
    count" (common/defines/00_defines.txt:1145)."""
    table = {"test_raider": ["dynn_fae_1"], "test_farmer": ["dynn_fae_9"]}
    keys, source = step.dynasty_names_for(groups[0].cultures[0], table)
    assert keys == ["dynn_fae_1", "dynn_fae_9"]
    assert "culture group" in source
    # a culture already at the minimum is left alone
    keys, source = step.dynasty_names_for(
        groups[0].cultures[0], {"test_raider": ["a", "b"], "test_farmer": ["c"]}
    )
    assert keys == ["a", "b"] and source == "own culture"


def test_no_dynasty_anywhere_in_the_group_invents_nothing(groups):
    keys, source = step.dynasty_names_for(groups[0].cultures[0], {})
    assert keys == []
    assert "CK2 defines no dynasty" in source
