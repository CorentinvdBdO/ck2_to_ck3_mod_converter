"""Tests for the `traits` step: one per rule in docs/step_traits.md."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from ck2ck3 import pdx
from ck2ck3.traits import (
    CK3_BASE_LIFE_EXPECTANCY,
    TraitConverter,
    UnmappedKey,
    build_plan,
    collect_icons,
    convert_plan,
    load_tables,
    loc_key_renames,
    trait_groups,
    unported,
)

REPO = Path(__file__).resolve().parent.parent
CK3_GAME = Path(
    "/home/cvdbdo/.local/share/Steam/steamapps/common/Crusader Kings III/game"
)
CK3_TRAITS = CK3_GAME / "common" / "traits" / "00_traits.txt"
FAERUN = REPO / "Faerun" / "Faerun"

needs_ck3 = pytest.mark.skipif(
    not CK3_TRAITS.exists(), reason="CK3 1.19 install not present"
)
needs_faerun = pytest.mark.skipif(
    not (FAERUN / "common" / "traits").is_dir(), reason="Faerun/ not cloned"
)


@pytest.fixture(scope="module")
def tables():
    return load_tables(
        ck3_traits_file=CK3_TRAITS if CK3_TRAITS.exists() else None
    )


def one(text: str) -> tuple[str, pdx.Block]:
    """Parse a single `name = { ... }` snippet."""
    doc = pdx.parse(text)
    node = doc.nodes()[0]
    return node.key, node.value


def convert(tables, text: str, **kwargs):
    name, block = one(text)
    converter = TraitConverter(tables, **kwargs)
    return converter.convert(name, block, source_file="fixture.txt", kind="port")


def keys(result) -> list[str]:
    return [e.key for e in result.block.entries if isinstance(e, pdx.Node)]


def value_of(result, key: str):
    return result.block.get(key)


def comment_text(result) -> str:
    lines: list[str] = list(result.block.end_comments)
    for entry in result.block.entries:
        lines += entry.leading_comments
        if entry.trailing_comment:
            lines.append(entry.trailing_comment)
    return "\n".join(lines)


# ---------------------------------------------------------------- field map
def test_field_mapping_uses_the_table(tables):
    result = convert(
        tables,
        """
        t = {
            incapacitating = yes
            ai_greed = 30
            same_opinion_if_same_religion = 10
            cannot_inherit = yes
            agnatic = yes
            inbred = yes
        }
        """,
    )
    assert value_of(result, "incapacitating") is True
    assert value_of(result, "ai_greed") == 30
    # CK2 religion -> CK3 faith (mappings/trait_fields.csv, exact).
    assert value_of(result, "same_opinion_if_same_faith") == 10
    assert "same_opinion_if_same_religion" not in keys(result)
    assert value_of(result, "inheritance_blocker") == "all"
    assert value_of(result, "parent_inheritance_sex") == "male"
    assert value_of(result, "enables_inbred") is True


def test_boolean_families_become_category_and_flags(tables):
    result = convert(
        tables, "t = { personality = yes\n is_health = yes\n vice = yes\n is_illness = yes }"
    )
    # CK3 `category` is single-valued: health beats personality (precedence).
    assert value_of(result, "category") == "health"
    assert "personality could not be kept" in comment_text(result)
    assert [e.value for e in result.block.entries if getattr(e, "key", "") == "flag"] == [
        "vice",
        "illness",
    ]


def test_hidden_and_customizer_do_not_collide(tables):
    """CK2 `hidden` and `customizer` both ask for shown_in_ruler_designer."""
    result = convert(tables, "t = { customizer = no\n hidden = yes }")
    assert keys(result).count("shown_in_ruler_designer") == 1
    assert value_of(result, "shown_in_encyclopedia") is False
    assert "a second time" in comment_text(result)


def test_birth_is_rescaled_and_needs_genetic(tables):
    """CK2 `birth` is per 10 000, CK3 `birth` a percent (trait_fields.csv)."""
    genetic = convert(tables, "t = { congenital = yes\n birth = 50 }")
    assert value_of(genetic, "birth") == 0.5
    assert value_of(genetic, "genetic") is True
    # `_traits.info:107`: birth only applies to a genetic trait.
    plain = convert(tables, "t = { birth = 50 }")
    assert "birth" not in keys(plain)
    assert "only on a genetic trait" in comment_text(plain)


def test_random_no_becomes_weight_zero_but_not_on_a_genetic_trait(tables):
    plain = convert(tables, "t = { random = no }")
    assert value_of(plain, "random_creation_weight") == 0
    genetic = convert(tables, "t = { congenital = yes\n random = no }")
    assert "random_creation_weight" not in keys(genetic)
    assert "forbids it on a genetic trait" in comment_text(genetic)


# ------------------------------------------------------------ modifier map
def test_modifier_scaling(tables):
    """combat_rating /10 and revolt risk x-100, per docs/mapping_modifiers.md."""
    result = convert(
        tables,
        "t = { combat_rating = 10\n global_revolt_risk = -0.05\n martial = 3 }",
    )
    assert value_of(result, "prowess") == 1
    assert value_of(result, "county_opinion_add") == 5
    assert value_of(result, "martial") == 3


def test_command_modifier_is_flattened(tables):
    """CK3 traits have no command_modifier block; its keys go flat."""
    result = convert(tables, "t = { command_modifier = { light_infantry = 0.2 } }")
    assert "command_modifier" not in keys(result)
    assert value_of(result, "skirmishers_damage_mult") == 0.2


def test_none_modifier_becomes_a_comment_never_a_drop(tables):
    result = convert(tables, "t = { morale_offence = 0.2 }")
    assert keys(result) == []
    text = comment_text(result)
    assert "# CK2: morale_offence = 0.2" in text
    assert "no CK3 equivalent" in text


def test_placeholder_modifier_becomes_a_comment(tables):
    """`<ck3_faith>_opinion` needs the religions lane's name map first."""
    result = convert(tables, "t = { bahamut_opinion = 10 }")
    assert keys(result) == []
    assert "placeholder" in comment_text(result)


def test_non_character_scope_modifier_becomes_a_comment(tables):
    """ck3-tiger: cultural_acceptance_gain_mult is culture scope, not character."""
    result = convert(tables, "t = { culture_flex = -0.05 }")
    assert keys(result) == []
    assert "not a character-scope modifier" in comment_text(result)


def test_trigger_block_is_commented_whole(tables):
    """CK2 trigger syntax is not CK3 trigger syntax; the events lane owns it."""
    result = convert(
        tables, "t = { potential = { religion_group = evil_pantheon_group } }"
    )
    assert keys(result) == []
    text = comment_text(result)
    assert "# CK2: potential = {" in text
    assert "religion_group" in text


def test_unmapped_key_raises(tables):
    with pytest.raises(UnmappedKey):
        convert(tables, "t = { totally_made_up_key = 1 }")


def test_trait_opinion_becomes_compatibility(tables):
    """The 78 `<trait>_opinion` rows land on CK3 `compatibility` when resolvable."""
    result = convert(
        tables, "t = { loyal_opinion = 20 }", live_traits={"loyal"}
    )
    compat = value_of(result, "compatibility")
    assert isinstance(compat, pdx.Block)
    assert compat.get("loyal") == 20
    # Unresolvable target (neither ported nor a CK3 trait): comment only.
    lost = convert(tables, "t = { athar_trait_opinion = 20 }")
    assert keys(lost) == []
    assert "athar_trait_opinion" in comment_text(lost)


# ------------------------------------------------------------- group/level
def test_group_level_from_a_numeric_family(tables):
    doc = pdx.parse(
        """
        pagan_branch_1 = { opposites = { pagan_branch_2 pagan_branch_3 } }
        pagan_branch_2 = { opposites = { pagan_branch_1 pagan_branch_3 } }
        pagan_branch_3 = { opposites = { pagan_branch_1 pagan_branch_2 } }
        """
    )
    groups = trait_groups({n.key: n.value for n in doc.nodes()})
    assert groups == {
        "pagan_branch_1": ("fae_pagan_branch", 1),
        "pagan_branch_2": ("fae_pagan_branch", 2),
        "pagan_branch_3": ("fae_pagan_branch", 3),
    }


def test_group_level_from_declaration_order(tables):
    """`dragon_wyrmling < young < adult < ancient` — the CK2 file order."""
    doc = pdx.parse(
        """
        dragon_wyrmling = { opposites = { dragon_young dragon_adult } }
        dragon_young = { opposites = { dragon_wyrmling dragon_adult } }
        dragon_adult = { opposites = { dragon_wyrmling dragon_young } }
        """
    )
    groups = trait_groups({n.key: n.value for n in doc.nodes()})
    assert groups["dragon_wyrmling"] == ("fae_dragon", 1)
    assert groups["dragon_adult"] == ("fae_dragon", 3)


def test_alternatives_without_a_shared_token_get_no_group():
    """`homosexual/bisexual/asexual` are exclusive but not a tier ladder."""
    doc = pdx.parse(
        """
        homosexual = { opposites = { bisexual asexual } }
        bisexual = { opposites = { homosexual asexual } }
        asexual = { opposites = { homosexual bisexual } }
        """
    )
    assert trait_groups({n.key: n.value for n in doc.nodes()}) == {}


def test_a_pair_is_never_a_group():
    doc = pdx.parse(
        "brave = { opposites = { craven } }\ncraven = { opposites = { brave } }"
    )
    assert trait_groups({n.key: n.value for n in doc.nodes()}) == {}


def test_two_cliques_claiming_one_token_do_not_merge():
    doc = pdx.parse(
        """
        warlock = { opposites = { trained_warlock master_warlock } }
        trained_warlock = { opposites = { warlock master_warlock } }
        master_warlock = { opposites = { warlock trained_warlock } }
        warlock_fey = { opposites = { warlock_fiend warlock_old_one } }
        warlock_fiend = { opposites = { warlock_fey warlock_old_one } }
        warlock_old_one = { opposites = { warlock_fey warlock_fiend } }
        """
    )
    groups = trait_groups({n.key: n.value for n in doc.nodes()})
    assert len({g for g, _ in groups.values()}) == 2


def test_group_level_is_emitted(tables):
    result = convert(
        tables, "dragon_young = { martial = 7 }", groups={"dragon_young": ("fae_dragon", 2)}
    )
    assert value_of(result, "group") == "fae_dragon"
    assert value_of(result, "level") == 2


# ------------------------------------------------------------- race traits
def test_race_trait_gets_genetic_physical_and_lifespan(tables):
    name, block = one("creature_elf = { diplomacy = 1 }")
    converter = TraitConverter(tables)
    result = converter.convert(
        name, block, source_file="race_traits.txt", kind="race_trait"
    )
    assert value_of(result, "genetic") is True
    assert value_of(result, "physical") is True
    row = tables.race_lifespan["creature_elf"]
    assert row.dnd_max_age == 700
    assert value_of(result, "life_expectancy") == 700 - CK3_BASE_LIFE_EXPECTANCY


def test_race_trait_immortal_is_not_repeated(tables):
    """`lich` already carries CK2 immortal = yes; the override must not double it."""
    name, block = one("lich = { immortal = yes }")
    converter = TraitConverter(tables)
    result = converter.convert(
        name, block, source_file="template_traits.txt", kind="race_trait"
    )
    assert keys(result).count("immortal") == 1
    assert "life_expectancy" not in keys(result)


def test_race_trait_without_a_lifespan_row_warns(tables):
    name, block = one("creature_made_up = { diplomacy = 1 }")
    converter = TraitConverter(tables)
    result = converter.convert(
        name, block, source_file="race_traits.txt", kind="race_trait"
    )
    assert "life_expectancy" not in keys(result)
    assert any("race_lifespan.csv" in w for w in result.warnings)


def test_race_lifespan_csv_is_consistent():
    """Every filled row must be dnd_max_age - the CK3 base, or immortal."""
    path = REPO / "overrides" / "race_lifespan.csv"
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(
            csv.DictReader(l for l in handle if not l.lstrip().startswith("#"))
        )
    assert rows
    for row in rows:
        if row["dnd_max_age"] and row["life_expectancy"]:
            assert int(row["life_expectancy"]) == (
                int(row["dnd_max_age"]) - CK3_BASE_LIFE_EXPECTANCY
            ), row
        assert row["immortal"] in {"yes", "no"}


# --------------------------------------------------------- vanilla dedupe
@needs_ck3
def test_vanilla_traits_are_not_redefined(tables, tmp_path):
    """Only an `exact` row dedupes; `approx` and `none` are ported (rule 1).

    "Vanilla CK2 content that CK3 removed must be replaced, not dropped"
    (`docs/DECISIONS.md` 2026-09-08). Four cases in one fixture: an `exact`
    row of `mappings/vanilla_traits.csv`, an `approx` row (ported *and*
    recorded as a near-equivalent), a `none` row (ported, no pair), and a
    CK2-vanilla trait from outside `00_traits.txt` whose id CK3 declares
    verbatim.
    """
    traits = tmp_path / "common" / "traits"
    traits.mkdir(parents=True)
    (traits / "00_traits.txt").write_text(
        "brave = { martial = 2 }\n"          # exact  -> deduped to brave
        "charitable = { diplomacy = 1 }\n"   # approx -> ported, ~ generous
        "envious = { intrigue = 2 }\n"       # none   -> ported
        "giant = { health = 1 }\n",          # exact id in CK3 00_traits.txt
        encoding="utf-8",
    )
    plan = build_plan(tmp_path, tables)
    assert plan.decision == {
        "brave": "rename",
        "charitable": "port",
        "envious": "port",
        "giant": "rename",
    }
    assert plan.rename_map == {"brave": "brave", "giant": "giant"}
    assert {r.ck2_trait: r.status for r in plan.renames} == {
        "brave": "exact",
        "giant": "exact_id",
    }
    # the CK3 near-equivalent is recorded, but it is NOT a rename: both traits
    # exist and a ported event chooses.
    assert [(n.ck2_trait, n.ck3_trait, n.status) for n in plan.near_equivalents] == [
        ("charitable", "generous", "approx")
    ]
    converted, _ = convert_plan(plan, tables)
    assert [c.ck2_trait for c in converted] == ["charitable", "envious"]


@needs_ck3
def test_a_vanilla_row_never_overrides_a_ck3_trait_of_the_same_id(tables, tmp_path):
    """An `approx`/`none` row whose CK2 id CK3 1.19 declares is still deduped.

    Porting it would silently replace vanilla behaviour, and an identical id is
    `exact` evidence anyway. No Faerûn row hits this today; the guard is what
    keeps a future table edit from doing it.
    """
    import dataclasses

    traits = tmp_path / "common" / "traits"
    traits.mkdir(parents=True)
    (traits / "00_traits.txt").write_text("brave = { martial = 2 }\n", encoding="utf-8")
    patched = dataclasses.replace(tables.vanilla["brave"], status="none", ck3_key="")
    tables = dataclasses.replace(tables, vanilla={**tables.vanilla, "brave": patched})
    plan = build_plan(tmp_path, tables)
    assert plan.decision == {"brave": "rename"}
    assert plan.renames[0].status == "exact_id"
    assert plan.live() == []
    assert any("already declares that id" in w for w in plan.warnings)


@needs_ck3
def test_opposites_that_all_vanish_emit_no_empty_block(tables, tmp_path):
    """`opposites = { }` is not emitted when every entry was commented out."""
    traits = tmp_path / "common" / "traits"
    traits.mkdir(parents=True)
    (traits / "00_traits.txt").write_text(
        "envious = { opposites = { no_such_trait } }\n", encoding="utf-8"
    )
    plan = build_plan(tmp_path, tables)
    converted, _ = convert_plan(plan, tables)
    assert converted[0].block.get("opposites") is None


@needs_ck3
@needs_faerun
@pytest.mark.slow
def test_faerun_dedupe_and_classification(tables):
    plan = build_plan(FAERUN, tables)
    assert len(plan.traits) == 1417
    assert len(plan.renames) == 121
    assert len(plan.near_equivalents) == 16
    assert len(plan.live()) == 429
    assert len(plan.commented()) == 867
    # a near-equivalent is ported, never deduped
    assert set(n.ck2_trait for n in plan.near_equivalents) <= set(plan.live())
    assert not set(n.ck2_trait for n in plan.near_equivalents) & set(plan.rename_map)
    # nothing is lost and nothing is counted twice
    assert (
        len(plan.renames) + len(plan.live()) + len(plan.commented())
        == len(plan.traits)
    )
    # a deduped trait is never in the live set
    assert not set(plan.rename_map) & set(plan.live())
    # a live trait never overrides a CK3 vanilla trait
    assert not set(plan.live()) & tables.ck3_trait_ids


@needs_ck3
@needs_faerun
@pytest.mark.slow
def test_faerun_conversion_is_reparsable_and_complete(tables):
    plan = build_plan(FAERUN, tables)
    converted, converter = convert_plan(plan, tables)
    assert len(converted) == 429
    assert sum(1 for c in converted if c.kind == "race_trait") == 117
    block = pdx.Block(multiline=True)
    for item in converted:
        block.append(pdx.Node(key=item.ck2_trait, value=item.block, blank_before=True))
    text = pdx.write(block)
    reparsed = pdx.parse(text)
    assert len(reparsed.nodes()) == 429
    # every CK2 key that produced nothing left a comment behind
    assert converter.counts["field_comments"] > 0
    assert converter.counts["modifier_comments"] > 0
    # no CK2 key escaped both tables (convert_plan would have raised)
    for node in reparsed.nodes():
        assert isinstance(node.value, pdx.Block)


@needs_ck3
@needs_faerun
@pytest.mark.slow
def test_faerun_unported_file_round_trips_as_comments(tables):
    plan = build_plan(FAERUN, tables)
    dead = pdx.Block(multiline=True)
    for name in plan.commented():
        dead.append(pdx.Node(key=name, value=plan.traits[name], blank_before=True))
    text = pdx.write(dead, commented=True)
    assert text.splitlines()
    assert all(line.startswith("#") for line in text.splitlines())
    # inert for the game: nothing left to parse
    assert pdx.parse(text).nodes() == []
    assert len(unported(plan)) == 867


# ------------------------------------------------------------------ icons
@needs_faerun
@pytest.mark.slow
def test_icons_come_from_the_ck2_sprite_table(tables):
    sprites = collect_icons(FAERUN)
    # `verified`: Faerûn wires trait icons through GFX_trait_<trait> sprites.
    assert sprites["creature_elf"].startswith("gfx/traits/")
    plan = build_plan(FAERUN, tables)
    assert plan.icon_value["creature_elf"] == "creature_elf.dds"
    assert plan.icon_source["creature_elf"].suffix == ".dds"
    # a `.tga` icon is refused, with a warning, rather than copied as `.dds`
    assert all(p.suffix == ".dds" for p in plan.icon_source.values())
    assert any(".tga is not a .dds" in w for w in plan.warnings)
    # only ported traits get an icon
    assert set(plan.icon_source) <= set(plan.live())


# ------------------------------------------------------------- loc renames
@needs_ck3
@needs_faerun
@pytest.mark.slow
def test_loc_key_renames_cover_every_kept_trait(tables):
    plan = build_plan(FAERUN, tables)
    rows = dict(loc_key_renames(plan))
    # CK2 localises a trait bare, CK3 as trait_<id> (both `verified`).
    assert rows["creature_elf"] == "trait_creature_elf"
    assert rows["creature_elf_desc"] == "trait_creature_elf_desc"
    # a deduped trait points at the CK3 id
    assert rows["brave"] == "trait_brave"
    assert rows["detached_priest"] == "trait_education_learning_1"
    # an `approx` trait is ported under its own id, so its loc key stays its own
    assert rows["charitable"] == "trait_charitable"
    assert len(rows) == 2 * (len(plan.live()) + len(plan.rename_map))


# ------------------------------------------------------------------- step
@needs_ck3
@needs_faerun
@pytest.mark.slow
def test_step_writes_both_files_and_the_icons(tmp_path):
    """The whole step through a real Context: files, icons, counts, reparse."""
    from ck2ck3.config import Config
    from ck2ck3.context import Context
    from ck2ck3.steps import traits as step

    config = Config.load(REPO / "configs" / "faerun.toml", out=tmp_path)
    ctx = Context(config)
    result = step.run(ctx)

    assert result.counts["ck2_traits"] == 1417
    assert result.counts["ported"] == 429
    assert result.counts["deduped"] == 121
    assert result.counts["near_equivalents"] == 16
    assert result.counts["commented"] == 867

    live = tmp_path / step.LIVE_FILE
    dead = tmp_path / step.UNPORTED_FILE
    assert live.exists() and dead.exists()
    doc = pdx.parse_file(live, encoding="utf-8")
    assert len(doc.nodes()) == 429
    # the header lists the dedupes so a reader of the mod alone can see them
    head = live.read_text(encoding="utf-8")[:6000]
    assert "Deduped - NOT redefined here" in head
    assert "brave -> brave (exact)" in head
    # and the near-equivalents, which are NOT dedupes
    assert "charitable ~ generous" in head
    # a `none` row is a live trait, not a comment
    assert doc.get("envious") is not None
    # the unported file is inert
    assert pdx.parse_file(dead, encoding="utf-8").nodes() == []

    icons = tmp_path / "gfx" / "interface" / "icons" / "traits"
    assert (icons / "creature_elf.dds").exists()
    assert len(list(icons.glob("*.dds"))) == result.counts["icons"]
    # every emitted `icon = ` has a file behind it
    for node in doc.nodes():
        icon = node.value.get("icon")
        if icon:
            assert (icons / str(icon)).exists()


@needs_ck3
@needs_faerun
@pytest.mark.slow
def test_step_dry_run_writes_nothing(tmp_path):
    from ck2ck3.config import Config
    from ck2ck3.context import Context
    from ck2ck3.steps import traits as step

    config = Config.load(REPO / "configs" / "faerun.toml", out=tmp_path)
    ctx = Context(config, dry_run=True)
    result = step.run(ctx)
    assert result.counts["ported"] == 429
    assert list(tmp_path.iterdir()) == []
