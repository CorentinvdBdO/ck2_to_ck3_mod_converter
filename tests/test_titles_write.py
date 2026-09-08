"""The CK3 writers of lane ``titles-history``: landed titles, both histories,
coats of arms, bookmarks, and the barony placement they all depend on.

Every writer is checked twice: once on a fixture snippet, and once by parsing
its own output back with ``ck2ck3.pdx`` — a generated script file that the
project's own parser cannot read is not valid CK3 either.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ck2ck3.pdx import Block, Date, parse
from ck2ck3.titles import bookmarks as bm
from ck2ck3.titles import ck2read, coa, history, landed, model, place, provinces

REPO = Path(__file__).resolve().parents[1]
FAERUN = REPO / "Faerun" / "Faerun"
GOV_CSV = REPO / "mappings" / "government_map.csv"

TITLES = """\
e_north = {
\tcolor = { 10 20 30 }
\tcolor2 = { 1 2 3 }
\tcapital = 1 # Waterdeep
\tgreen_elf = Cormanthor
\tdwarf_group = Hollowbold
\tholy_site = triadic
\tculture = illuskan
\tshort_name = yes
\tassimilate = no
\tcan_be_claimed = no
\tdignity = 5
\ttitle = "HIGH_KING"

\tk_waterdeep = {
\t\tcolor = { 40 50 60 }
\t\tc_waterdeep = {
\t\t\tcolor = { 70 80 90 }
\t\t\tb_castle_waterdeep = { }
\t\t\tb_sea_ward = { }
\t\t}
\t\tc_nowhere = {
\t\t\tcolor = { 1 1 1 }
\t\t\tb_nowhere = { }
\t\t}
\t}
}
"""

PROVINCE = """\
title = c_waterdeep
max_settlements = 7
b_castle_waterdeep = castle
culture = shield_dwarf
religion = dwarven_pantheon
terrain = farmlands
1010.1.1 = {
\tb_sea_ward = city
}
1350.1.1 = {
\tculture = illuskan
\tb_sea_ward = ct_spelljammer_port
\tb_sea_ward = city
}
"""


def write_cp1252(path: Path, text: str) -> Path:
    path.write_bytes(text.encode("cp1252"))
    return path


@pytest.fixture
def world(tmp_path):
    """A two-county fixture world: c_waterdeep has a province, c_nowhere none."""
    lt = tmp_path / "common" / "landed_titles"
    lt.mkdir(parents=True)
    write_cp1252(lt / "landed_titles.txt", TITLES)
    ph = tmp_path / "history" / "provinces"
    ph.mkdir(parents=True)
    write_cp1252(ph / "1 - Waterdeep.txt", PROVINCE)

    roots = ck2read.read_landed_titles_dir(lt)
    flat = ck2read.flatten(roots)
    counties = place.counties_with_baronies(flat)
    histories = ck2read.read_province_histories(ph)
    ck3_of_county, ck2_of_county = place.county_province_map(histories, {1: 501})
    county_history = {c: histories[p] for c, p in ck2_of_county.items()}
    plan = place.build_plan(
        counties=counties,
        province_of_county=ck3_of_county,
        histories=county_history,
        bookmark=Date(1357, 1, 1),
        definition_names={},
    )
    live, dead = model.liveness(flat=flat, plan=plan, patricians=frozenset())
    return {
        "roots": roots,
        "flat": flat,
        "counties": counties,
        "county_history": county_history,
        "plan": plan,
        "live": live,
        "dead": dead,
        "by_id": ck2read.index(roots),
    }


# -- placement --------------------------------------------------------------
def test_one_barony_per_county_places_the_capital(world):
    plan = world["plan"]
    assert plan.mode == "county_capital"
    assert plan.get("b_castle_waterdeep").province == 501
    assert plan.get("b_castle_waterdeep").status == "placed"
    # b_sea_ward IS built (from 1010) but there is only one province per county
    assert plan.get("b_sea_ward").status == "demoted"
    assert plan.get("b_sea_ward").province is None
    # c_nowhere has no CK2 province at all
    assert plan.get("b_nowhere").status == "no_province"


def test_built_holdings_is_a_state_not_a_log(world):
    history_1 = world["county_history"]["c_waterdeep"]
    early = place.built_holdings(history_1, until=Date(900, 1, 1))
    assert set(early) == {"b_castle_waterdeep"}
    late = place.built_holdings(history_1, until=Date(1357, 1, 1))
    assert late["b_sea_ward"] == ("city", Date(1350, 1, 1))


def test_barony_set_mode_uses_definition_csv_names(tmp_path, world):
    rows = [
        place.BaronySetRow("c_waterdeep", "b_castle_waterdeep", "castle", "", "placed"),
        place.BaronySetRow("c_waterdeep", "b_sea_ward", "city", "1010.1.1", "placed"),
        place.BaronySetRow("c_waterdeep", "b_gone", "city", "", "demoted"),
    ]
    plan = place.build_plan(
        counties=world["counties"],
        province_of_county={},
        histories=world["county_history"],
        bookmark=Date(1357, 1, 1),
        definition_names={"b_castle_waterdeep": 501, "b_sea_ward": 502},
        barony_set=rows,
    )
    assert plan.mode == "barony_set"
    assert plan.get("b_sea_ward").province == 502
    assert plan.by_province == {501: "b_castle_waterdeep", 502: "b_sea_ward"}


def test_definition_csv_is_read_case_insensitively(tmp_path):
    path = tmp_path / "definition.csv"
    path.write_text("id;r;g;b;name;x\n0;0;0;0;x;x\n1;1;2;3;WATERDEEP;x\n")
    assert place.read_definition_names(path) == {"waterdeep": 1}


# -- liveness ---------------------------------------------------------------
def test_a_county_without_a_province_is_not_a_ck3_title(world):
    assert "c_nowhere" in world["dead"]
    assert "no live barony" in world["dead"]["c_nowhere"]
    assert "b_nowhere" in world["dead"]
    # the duchy above it survives: CK3 allows a titular kingdom
    assert "k_waterdeep" in world["live"]


def test_a_patrician_barony_is_never_live(world):
    live, dead = model.liveness(
        flat=world["flat"],
        plan=world["plan"],
        patricians=frozenset({"b_castle_waterdeep"}),
    )
    assert "b_castle_waterdeep" in dead
    assert "patrician" in dead["b_castle_waterdeep"]
    # and its county loses its only barony, so it goes too
    assert "c_waterdeep" in dead
    assert "c_waterdeep" not in live


# -- landed_titles ----------------------------------------------------------
@pytest.fixture
def landed_text(world):
    result = landed.render(
        world["roots"],
        landed.LandedConfig(
            plan=world["plan"],
            county_of_province={1: "c_waterdeep"},
            by_id=world["by_id"],
            live_titles=world["live"],
            dead_titles=world["dead"],
            name_list_of_culture={
                "green_elf": "name_list_green_elf",
                "shield_dwarf": "name_list_shield_dwarf",
            },
            culture_groups={"dwarf_group": ["shield_dwarf"]},
            own_county={"e_north": "c_waterdeep", "k_waterdeep": "c_waterdeep"},
            placeholder_capital="c_waterdeep",
        ),
    )
    return result


def test_landed_titles_parses_back(landed_text):
    document = parse(landed_text.text)
    empire = document.get("e_north")
    assert isinstance(empire, Block)
    county = empire["k_waterdeep"]["c_waterdeep"]
    assert county["b_castle_waterdeep"]["province"] == 501


def test_a_barony_carries_its_province_and_the_county_colour(landed_text):
    barony = parse(landed_text.text)["e_north"]["k_waterdeep"]["c_waterdeep"][
        "b_castle_waterdeep"
    ]
    assert barony["province"] == 501
    # CK2 gives baronies no colour, so the county's is used, not an invented one
    assert barony["color"].list_values() == [70, 80, 90]


def test_an_unplaced_barony_is_a_commented_block(landed_text):
    assert "# b_sea_ward = { } # demoted" in landed_text.text
    assert "b_sea_ward = {\n" not in landed_text.text


def test_a_dead_county_is_commented_out_with_its_subtree(landed_text):
    assert "# c_nowhere = {" in landed_text.text
    commented = dict(landed_text.commented)
    assert "c_nowhere" in commented and "b_nowhere" in commented


def test_ck2_capital_province_becomes_a_county_title(landed_text):
    assert "capital = c_waterdeep # Waterdeep" in landed_text.text


def test_cultural_names_are_keyed_by_name_list_and_take_a_loc_key(landed_text):
    block = parse(landed_text.text)["e_north"]["cultural_names"]
    assert block["name_list_green_elf"] == "cn_fae_cormanthor"
    # the group-keyed CK2 name is expanded to its member cultures
    assert block["name_list_shield_dwarf"] == "cn_fae_hollowbold"
    assert landed_text.loc["cn_fae_cormanthor"] == "Cormanthor"
    # CK3 derives the cultural adjective as <key>_adj
    assert landed_text.loc["cn_fae_cormanthor_adj"] == "Cormanthor"


def test_keys_with_a_ck3_lever_are_converted(landed_text):
    empire = parse(landed_text.text)["e_north"]
    assert empire["definite_form"] is True  # CK2 short_name
    assert empire["de_jure_drift_disabled"] is True  # CK2 assimilate = no
    assert empire["no_automatic_claims"] is True  # CK2 can_be_claimed = no
    assert empire["ai_primary_priority"]["add"] == 500  # CK2 dignity = 5


def test_keys_without_a_ck3_home_become_comments_not_silence(landed_text):
    text = landed_text.text
    assert "# CK2 color2 = { 1 2 3 }" in text
    assert "# CK2 culture = illuskan" in text
    assert "CK2 holy_site = triadic" in text
    assert "CK2 title = HIGH_KING" in text
    # and the religions / flavorization lanes get the data as evidence
    assert ("e_north", "triadic") in landed_text.holy_sites
    assert ("e_north", "title", "HIGH_KING") in landed_text.flavorization


def test_a_titular_title_gets_the_landless_recipe(tmp_path):
    lt = tmp_path / "titular_titles.txt"
    write_cp1252(lt, "e_pirates = {\n\tcolor = { 1 2 3 }\n\tpirate = yes\n}\n")
    roots = ck2read.read_landed_titles(lt)
    result = landed.render(
        roots,
        landed.LandedConfig(
            plan=place.PlacementPlan(mode="county_capital"),
            county_of_province={},
            by_id=ck2read.index(roots),
            live_titles=frozenset({"e_pirates"}),
            dead_titles={},
            name_list_of_culture={},
            culture_groups={},
            own_county={},
            placeholder_capital="c_placeholder",
        ),
    )
    block = parse(result.text)["e_pirates"]
    for key in ("landless", "require_landless", "destroy_if_invalid_heir"):
        assert block[key] is True
    # a landless title still wants a capital (EK2 precedent)
    assert str(block["capital"]) == "c_placeholder"


def test_no_field_is_emitted_twice(landed_text):
    """CK3 warns about a redefined field inside one block; the landless recipe
    overlaps with the CK2 keys `location_ruler_title` and `can_be_claimed`."""
    for block in parse(landed_text.text).nodes():
        keys = [e.key for e in block.block if hasattr(e, "key")]
        plain = [k for k in keys if not k.startswith(("e_", "k_", "d_", "c_", "b_"))]
        assert len(plain) == len(set(plain)), plain


# -- history/titles ---------------------------------------------------------
TITLE_HISTORY = """\
holder = 20001
26.1.2 = {
\tactive = yes
\tlaw = true_cognatic_succession
\tlaw = succ_primogeniture
\tholder = 20001 # Faerlthann
}
55.1.1 = {
\tholder = 20002
\tliege = e_north
\tname = "Cormyr"
}
900.1.1 = {
\tholder = 99999
}
"""


@pytest.fixture
def title_history(tmp_path, world):
    directory = tmp_path / "history" / "titles"
    directory.mkdir(parents=True)
    write_cp1252(directory / "k_waterdeep.txt", TITLE_HISTORY)
    # 20002 is born in 100.1.1, so e_north has no LIVING holder in 55.1.1 and
    # the `liege = e_north` line of k_waterdeep has to be dropped.
    write_cp1252(directory / "e_north.txt", "20.1.1 = { holder = 20002 }\n")
    write_cp1252(directory / "c_nowhere.txt", "20.1.1 = { holder = 20001 }\n")
    histories = ck2read.read_title_histories(directory)
    characters = {
        "20000": ck2read.Ck2CharacterStub("20000", birth=Date(1, 1, 1)),
        "20001": ck2read.Ck2CharacterStub("20001", birth=Date(1, 1, 1)),
        "20002": ck2read.Ck2CharacterStub("20002", birth=Date(100, 1, 1)),
    }
    return history.render(
        histories,
        history.HistoryConfig(
            government={
                t: __import__(
                    "ck2ck3.titles.tables", fromlist=["x"]
                ).GovernmentChoice("tribal_government", "CK2 tribe = yes")
                for t in world["live"]
            },
            characters=characters,
            live_titles=world["live"],
            dead_titles=world["dead"],
            spans=history.holder_spans(histories),
        ),
    )


def test_title_history_parses_back_and_has_no_toplevel_keys(title_history):
    text = title_history.files["history/titles/fae_kingdoms.txt"]
    block = parse(text)["k_waterdeep"]
    for entry in block:
        if hasattr(entry, "key"):
            Date.parse(entry.key)  # raises if a key is not a date


def test_a_ck2_toplevel_key_is_wrapped_in_an_early_date(title_history):
    text = title_history.files["history/titles/fae_kingdoms.txt"]
    early = parse(text)["k_waterdeep"]["1.1.1"]
    assert str(early["holder"]) == "fae_20001"


def test_holder_ids_are_prefixed_strings(title_history):
    text = title_history.files["history/titles/fae_kingdoms.txt"]
    assert "holder = fae_20001" in text


def test_an_unknown_holder_becomes_holder_0_and_warns(title_history):
    text = title_history.files["history/titles/fae_kingdoms.txt"]
    assert "holder = 0\t# CK2 holder = 99999, no such character" in text
    assert any("99999 is not in CK2" in w for w in title_history.warnings)


def test_a_holder_before_its_birth_warns(title_history):
    assert any("20002 is born 100.1.1" in w for w in title_history.warnings)


def test_ck2_law_lines_become_one_succession_laws_block(title_history):
    text = title_history.files["history/titles/fae_kingdoms.txt"]
    laws = parse(text)["k_waterdeep"]["26.1.2"]["succession_laws"].list_values()
    assert set(laws) == {"single_heir_succession_law", "equal_law"}


def test_government_is_synthesised_at_the_first_holder(title_history):
    text = title_history.files["history/titles/fae_kingdoms.txt"]
    block = parse(text)["k_waterdeep"]
    assert block["1.1.1"]["government"] == "tribal_government"
    assert "government" not in block["55.1.1"]


def test_a_dated_name_becomes_set_title_name_with_a_loc_key(title_history):
    text = title_history.files["history/titles/fae_kingdoms.txt"]
    key = parse(text)["k_waterdeep"]["55.1.1"]["effect"]["set_title_name"]
    assert title_history.loc[str(key)] == "Cormyr"


def test_a_liege_with_no_living_holder_is_dropped(title_history):
    """CK3 rejects `liege = X` when X is unheld then; CK2 writes it anyway."""
    text = title_history.files["history/titles/fae_kingdoms.txt"]
    assert "\tliege = e_north" not in text
    assert "CK2 liege = e_north dropped" in text
    assert any("has no holder then" in w for w in title_history.warnings)


def test_history_of_a_dead_title_is_kept_commented(title_history):
    text = title_history.files["history/titles/fae_counties.txt"]
    assert "# c_nowhere: history kept commented" in text
    assert "\nc_nowhere = {" not in text


def test_a_live_title_with_no_ck2_history_gets_a_stub(title_history):
    text = title_history.files["history/titles/fae_baronies.txt"]
    assert str(parse(text)["b_castle_waterdeep"]["1.1.1"]["holder"]) == "0"
    assert title_history.counts["history_stubs"] >= 1


def test_held_at_needs_a_living_holder():
    spans = history.holder_spans(
        {
            "k_x": ck2read.Ck2TitleHistory(
                "k_x",
                dated=[
                    (Date(700, 1, 1), []),
                ],
            )
        }
    )
    assert history.held_at(spans, "k_x", Date(800, 1, 1)) is False


# -- history/provinces ------------------------------------------------------
def test_province_history_is_one_block_per_placed_barony(world):
    result = provinces.render(
        histories=world["county_history"],
        counties=world["counties"],
        kingdom_of_county={"c_waterdeep": "k_waterdeep"},
        plan=world["plan"],
    )
    text = result.files["history/provinces/fae_k_waterdeep.txt"]
    document = parse(text)
    assert [e.key for e in document if hasattr(e, "key")] == ["501"]
    block = document["501"]
    assert block["culture"] == "shield_dwarf"
    assert block["religion"] == "dwarven_pantheon"
    assert block["holding"] == "castle_holding"
    assert result.counts["province_blocks"] == 1


def test_dated_culture_changes_are_kept(world):
    result = provinces.render(
        histories=world["county_history"],
        counties=world["counties"],
        kingdom_of_county={},
        plan=world["plan"],
    )
    text = next(iter(result.files.values()))
    assert parse(text)["501"]["1350.1.1"]["culture"] == "illuskan"


def test_terrain_and_max_settlements_are_dropped_with_a_reason(world):
    result = provinces.render(
        histories=world["county_history"],
        counties=world["counties"],
        kingdom_of_county={},
        plan=world["plan"],
    )
    text = next(iter(result.files.values()))
    assert "terrain" not in parse(text)["501"]
    assert "common/province_terrain owns" in text
    assert "max_settlements is dropped" in text


def test_two_ck2_holdings_on_one_date_do_not_redefine_a_field(world):
    """CK2 writes `b_sea_ward = ct_spelljammer_port` and `= city` on the same
    date; CK3 warns about a field redefined inside one block."""
    plan = place.build_plan(
        counties=world["counties"],
        province_of_county={},
        histories=world["county_history"],
        bookmark=Date(1357, 1, 1),
        definition_names={"b_sea_ward": 502},
        barony_set=[
            place.BaronySetRow("c_waterdeep", "b_sea_ward", "city", "", "placed")
        ],
    )
    result = provinces.render(
        histories=world["county_history"],
        counties=world["counties"],
        kingdom_of_county={},
        plan=plan,
    )
    text = next(iter(result.files.values()))
    block = parse(text)["502"]["1350.1.1"]
    assert len([e for e in block if getattr(e, "key", None) == "holding"]) == 1


# -- coats of arms ----------------------------------------------------------
def test_coa_is_a_solid_pattern_in_the_ck2_colour(world):
    result = coa.render(world["flat"], live=world["live"])
    block = parse(result.text)["e_north"]
    assert str(block["pattern"]) == "pattern_solid.dds"
    assert block["color1"].components == [10, 20, 30]
    # a title that is not live gets no entry
    assert "c_nowhere" not in result.text.replace("# c_nowhere", "")


def test_ck2_flags_are_recorded_not_converted(tmp_path, world):
    flags = tmp_path / "flags"
    flags.mkdir()
    (flags / "e_north.tga").write_bytes(b"")
    result = coa.render(world["flat"], live=world["live"], flags_dir=flags)
    assert result.flags == [("e_north", "e_north.tga")]
    assert result.counts["ck2_flags_recorded"] == 1
    assert coa.flags_csv(result.flags) == "title,flag_file\ne_north,e_north.tga\n"


# -- bookmarks --------------------------------------------------------------
BOOKMARK = """\
bm_test = {
\tname = "BM_TEST"
\tdesc = "BM_TEST_DESC"
\tdate = 1357.1.1
\tera = yes
\tselectable_character = {
\t\tid = 52101
\t\tage = 447
\t\tname = ERA_CHAR_NAME_ZHENGYI
\t\ttitle = k_waterdeep
\t\tcharacter = {
\t\t\tdynasty = 7743
\t\t\treligion = abyssal_cult
\t\t\tculture = lich
\t\t\tgovernment = "tribal_government"
\t\t}
\t}
\tselectable_character = {
\t\tid = 4242
\t\ttitle = k_gone
\t\tcharacter = { }
\t}
}
"""


@pytest.fixture
def bookmark_result(tmp_path, world):
    directory = tmp_path / "bookmarks"
    directory.mkdir()
    write_cp1252(directory / "00_bookmarks.txt", BOOKMARK)
    return bm.render(
        ck2read.read_bookmarks_dir(directory),
        characters={
            "52101": ck2read.Ck2CharacterStub(
                "52101", birth=Date(909, 3, 14), female=True, name="Zhengyi"
            )
        },
        live_titles=world["live"],
        default_date="1357.1.1",
        government_map={"tribal_government": "tribal_government"},
    )


def test_bookmark_grammar(bookmark_result):
    text = bookmark_result.files["common/bookmarks/bookmarks/fae_bookmarks.txt"]
    block = parse(text)["bm_test"]
    assert str(block["start_date"]) == "1357.1.1"
    assert block["is_playable"] is True
    assert str(block["group"]) == "bm_group_fae"
    character = block["character"]
    # CK3 wants a birth date; CK2 gives an age
    assert str(character["birth"]) == "909.3.14"
    assert str(character["type"]) == "female"
    assert str(character["title"]) == "k_waterdeep"
    assert str(character["government"]) == "tribal_government"
    assert str(character["history_id"]) == "fae_52101"
    # `fae_<ck2 id>`, no `dyn_` infix: the `dynasties` step owns the id
    # (ck2ck3.ids.fae_id) and a mismatch here is 80 ck3-tiger
    # `error(missing-item): dynasty fae_dyn_N not defined`.
    assert str(character["dynasty"]) == "fae_7743"


def test_the_config_bookmark_date_is_the_default(bookmark_result):
    text = bookmark_result.files["common/bookmarks/bookmarks/fae_bookmarks.txt"]
    assert parse(text)["bm_test"]["weight"]["value"] == 100


def test_a_character_whose_title_is_dead_is_dropped_with_a_comment(bookmark_result):
    text = bookmark_result.files["common/bookmarks/bookmarks/fae_bookmarks.txt"]
    assert "dropped selectable_character 4242" in text
    assert any("4242 dropped" in w for w in bookmark_result.warnings)


def test_the_group_file_carries_default_start_date(bookmark_result):
    text = bookmark_result.files[
        "common/bookmarks/groups/fae_bookmark_groups.txt"
    ]
    assert str(parse(text)["bm_group_fae"]["default_start_date"]) == "1357.1.1"


def test_every_bookmark_character_gets_a_portrait_file(bookmark_result):
    rel = "common/bookmark_portraits/bookmark_fae_52101.txt"
    assert rel in bookmark_result.files
    block = parse(bookmark_result.files[rel])["bookmark_fae_52101"]
    assert str(block["type"]) == "female"
    assert isinstance(block["genes"], Block)


def test_vanilla_bookmark_files_are_shadowed(bookmark_result):
    for rel in bm.SHADOWED:
        assert rel in bookmark_result.files
        assert bookmark_result.files[rel].lstrip().startswith("#")


def test_bookmark_loc_keys_are_handed_to_the_loc_lane(bookmark_result):
    assert ("BM_TEST", "bm_test") in bookmark_result.renames
    assert ("BM_TEST_DESC", "bm_test_desc") in bookmark_result.renames


# -- the whole Faerun mod ---------------------------------------------------
@pytest.fixture(scope="module")
def faerun_model():
    if not FAERUN.is_dir():
        pytest.skip("Faerun/ clone absent")
    return model.build(
        ck2_mod=FAERUN,
        definition_csv=Path("/nonexistent/definition.csv"),
        province_id_map=REPO / "docs" / "evidence" / "province_id_map.csv",
        government_map_csv=GOV_CSV,
        bookmark_date="1357.1.1",
    )


@pytest.mark.slow
def test_faerun_counts(faerun_model):
    data = faerun_model
    live_by_tier: dict[str, int] = {}
    for title in data.flat:
        if title.id in data.live_titles:
            live_by_tier[title.prefix] = live_by_tier.get(title.prefix, 0) + 1
    # every empire, kingdom and duchy survives; 12 of 2132 counties do not
    # (7 have no CK2 province, 5 no built holding), and one barony per county
    # is placed until lane `baronies` publishes barony_set.csv.
    assert live_by_tier == {"e": 65, "k": 267, "d": 979, "c": 2120, "b": 2120}
    assert data.plan.mode == "county_capital"
    assert data.plan.counts()["placed"] == 2120
    assert len(data.dead_titles) == 13248
    assert len(data.live_titles) + len(data.dead_titles) == 18799


@pytest.mark.slow
def test_faerun_every_liege_and_holder_resolves(faerun_model):
    data = faerun_model
    result = history.render(
        data.title_history,
        history.HistoryConfig(
            government=data.government,
            characters=data.characters,
            live_titles=data.live_titles,
            dead_titles=data.dead_titles,
            spans=history.holder_spans(data.title_history),
        ),
    )
    missing = [w for w in result.warnings if "not in CK2 history/characters" in w]
    unmapped = [w for w in result.warnings if "unmapped CK2 key" in w]
    assert missing == []
    assert unmapped == []
    assert result.counts["titles_with_history"] == 3193
    assert result.counts["history_commented_out"] == 227


@pytest.mark.slow
def test_faerun_governments_are_all_real_ck3_ids(faerun_model):
    from ck2ck3.titles import tables

    valid = set(tables.load_government_map(GOV_CSV).values())
    valid |= {
        "mercenary_government",
        "holy_order_government",
        "landless_adventurer_government",
        "theocracy_government",
        "republic_government",
        "tribal_government",
    }
    used = {choice.government for choice in faerun_model.government.values()}
    assert used <= valid
