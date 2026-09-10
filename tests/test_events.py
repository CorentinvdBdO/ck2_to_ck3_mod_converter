"""Tests for the `events` step (lane `events`, README §5 step 3).

Covers the id scheme, every live gate, the theme table, the CK2 shapes that
needed a real conversion (gated `desc`, option `name`, `event_target:`,
event-firing effects, top-level trigger shorthands), and a full `run(ctx)`
over a synthetic CK2 mod - including that `[events]` config keys are actually
read (the silent-no-op class, `docs/step_events.md` §8).
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from ck2ck3 import ids  # noqa: E402
from ck2ck3.config import Config  # noqa: E402
from ck2ck3.context import Context  # noqa: E402
from ck2ck3.decisions_vocab import VocabRow  # noqa: E402
from ck2ck3.pdx import Block, Node, parse, write  # noqa: E402
from ck2ck3.steps import events as step  # noqa: E402
from ck2ck3.steps.decisions import TraitInfo  # noqa: E402

TRIGGERS = {
    "age": VocabRow("age", "age", "exact", "verified", "unchanged"),
    "is_alive": VocabRow("is_alive", "is_alive", "exact", "verified", "unchanged"),
    "society": VocabRow("society", None, "none", "verified", "societies do not exist in CK3"),
}
EFFECTS = {
    "add_gold": VocabRow("add_gold", "add_gold", "exact", "verified", "unchanged"),
    "save_event_target_as": VocabRow(
        "save_event_target_as", "save_scope_as", "approx", "verified", "renamed"
    ),
    "society": VocabRow("society", None, "none", "verified", "societies do not exist in CK3"),
}
THEMES = {
    ("picture", "GFX_evt_bishop"): "faith",
    ("border", "GFX_event_normal_frame_war"): "war",
}


def _event(text: str, kind: str = "character_event") -> Block:
    doc = parse(f"{kind} = {{ {text} }}\n")
    return doc.entries[0].value


def convert(
    text: str,
    *,
    kind: str = "character_event",
    ck2_id: str = "TST.1",
    live_ids: set[str] | None = None,
    ck3_id_of: dict[str, str] | None = None,
    scoped_out: dict[str, str] | None = None,
    min_score: float = 1.0,
) -> step.ConvertedEvent:
    ck3_id_of = ck3_id_of if ck3_id_of is not None else {ck2_id: ids.event_id("tst", ck2_id)}
    return step.convert_event(
        ck2_id, _event(text, kind), kind=kind, prefix="tst",
        triggers=TRIGGERS, effects=EFFECTS, traits=TraitInfo(live={"brave"}),
        themes=THEMES, default_theme="default", ck3_id_of=ck3_id_of,
        live_ids=live_ids if live_ids is not None else set(ck3_id_of),
        scoped_out=scoped_out or {}, min_score=min_score,
        source_file="events/test.txt",
    )


# -- id scheme ---------------------------------------------------------------

def test_event_id_keeps_the_ck2_number_and_lower_cases_the_namespace() -> None:
    assert ids.event_id("fae", "uthgar.0") == "fae_uthgar.0"
    assert ids.event_id("fae", "BRO.1456") == "fae_bro.1456"
    assert ids.event_namespace("fae", "FaerunSocieties.12") == "fae_faerunsocieties"


def test_bare_numeric_ck2_ids_share_one_namespace() -> None:
    """CK2 numeric ids are globally unique, so one namespace holds them all."""
    assert ids.event_id("fae", "104999") == "fae_ck2.104999"
    assert ids.event_namespace("fae", "8011") == "fae_ck2"


def test_event_id_rejects_a_non_event_id() -> None:
    with pytest.raises(ValueError):
        ids.event_id("fae", "not_an_event")


# -- live path ---------------------------------------------------------------

def test_fully_mapped_event_goes_live_with_ck3_grammar() -> None:
    conv = convert(
        "id = TST.1 desc = TST_1_DESC picture = GFX_evt_bishop is_triggered_only = yes "
        "trigger = { age = 16 } immediate = { add_gold = 5 } "
        "option = { name = TST_1_A add_gold = 1 }"
    )
    assert conv.live, conv.gates
    text = write(Block(entries=[Node(key=conv.ck3_id, value=conv.body)]))
    assert "type = character_event" in text
    assert "theme = faith" in text        # picture beats border/default
    assert "desc = TST_1_DESC" in text
    assert "left_portrait = root" in text
    assert "option = {" in text and "name = TST_1_A" in text
    # `is_triggered_only` is CK3's default and has no field
    assert "is_triggered_only" not in text
    assert conv.loc_keys == ["TST_1_A", "TST_1_DESC"] or set(conv.loc_keys) == {"TST_1_A", "TST_1_DESC"}


def test_letter_event_gets_a_sender() -> None:
    conv = convert("id = TST.1 desc = D option = { name = A }", kind="letter_event")
    text = write(Block(entries=[Node(key=conv.ck3_id, value=conv.body)]))
    assert "type = letter_event" in text and "sender = root" in text


def test_theme_falls_back_border_then_default() -> None:
    border = convert("id = TST.1 desc = D border = GFX_event_normal_frame_war option = { name = A }")
    assert border.theme == "war"
    plain = convert("id = TST.1 desc = D picture = GFX_evt_unknown_thing option = { name = A }")
    assert plain.theme == "default"


def test_hidden_event_needs_no_option() -> None:
    conv = convert("id = TST.1 hide_window = yes immediate = { add_gold = 1 }")
    assert conv.live and conv.hidden
    text = write(Block(entries=[Node(key=conv.ck3_id, value=conv.body)]))
    assert "hidden = yes" in text and "theme" not in text


# -- gates -------------------------------------------------------------------

def test_below_min_score_is_an_inert_stub_carrying_its_draft() -> None:
    conv = convert("id = TST.1 hide_window = yes immediate = { society = yes add_gold = 1 }")
    assert not conv.live and conv.gates == ["score"]
    text = write(Block(entries=[step.render_event(conv)]))
    assert "hidden = yes" in text
    assert "orphan = yes" in text
    assert "trigger = {\n\t\talways = no" in text or "always = no" in text
    assert "immediate = { }" in text or "immediate = {}" in text
    assert "# draft:" in text
    assert "# fae_unported = yes" in text
    # the draft records what was dropped, so a human can revive it
    assert any("society" in line for line in text.splitlines() if "# draft:" in line)


def test_mean_time_to_happen_is_never_live() -> None:
    conv = convert(
        "id = TST.1 hide_window = yes mean_time_to_happen = { months = 6 } "
        "immediate = { add_gold = 1 }"
    )
    assert "mtth" in conv.gates
    text = write(Block(entries=[step.render_event(conv)]))
    assert "mean_time_to_happen" in text  # kept as evidence
    assert "# CK2 mean_time_to_happen" in text


def test_ck2_from_scope_is_never_live() -> None:
    conv = convert("id = TST.1 hide_window = yes immediate = { FROM = { add_gold = 1 } }")
    assert "from_scope" in conv.gates and "unsaved_scope" in conv.gates


def test_shown_event_without_an_option_is_never_live() -> None:
    conv = convert("id = TST.1 desc = D immediate = { add_gold = 1 }")
    assert "no_option" in conv.gates


def test_reading_a_scope_the_event_never_saves_is_never_live() -> None:
    conv = convert(
        "id = TST.1 hide_window = yes immediate = { event_target:helper = { add_gold = 1 } }"
    )
    assert "unsaved_scope" in conv.gates
    saved = convert(
        "id = TST.1 hide_window = yes immediate = { save_event_target_as = helper "
        "event_target:helper = { add_gold = 1 } }"
    )
    assert "unsaved_scope" not in saved.gates
    text = write(Block(entries=[Node(key=saved.ck3_id, value=saved.body)]))
    assert "scope:helper = {" in text and "save_scope_as = helper" in text


# -- event-firing effects ----------------------------------------------------

def test_trigger_event_only_to_a_live_target() -> None:
    both = {"TST.1": "tst_tst.1", "TST.2": "tst_tst.2"}
    live = convert(
        "id = TST.1 hide_window = yes immediate = { character_event = { id = TST.2 days = 3 } }",
        ck3_id_of=both, live_ids={"TST.1", "TST.2"},
    )
    text = write(Block(entries=[Node(key=live.ck3_id, value=live.body)]))
    assert "trigger_event = {" in text and "id = tst_tst.2" in text and "days = 3" in text
    assert "dead_call" not in live.gates

    dead = convert(
        "id = TST.1 hide_window = yes immediate = { character_event = { id = TST.2 } }",
        ck3_id_of=both, live_ids={"TST.1"},
    )
    dead_text = write(Block(entries=[Node(key=dead.ck3_id, value=dead.body)]))
    assert "trigger_event" not in dead_text
    assert "# CK2: character_event" in dead_text
    assert "dead_call" in dead.gates


def test_trigger_event_to_an_unknown_id_is_a_comment() -> None:
    conv = convert(
        "id = TST.1 hide_window = yes immediate = { character_event = { id = HF.99 } }"
    )
    text = write(Block(entries=[Node(key=conv.ck3_id, value=conv.body)]))
    assert "trigger_event" not in text
    assert "HF.99" in text and "dead_call" in conv.gates


def test_event_call_with_a_field_ck3_has_no_counterpart_for_is_a_comment() -> None:
    both = {"TST.1": "tst_tst.1", "TST.2": "tst_tst.2"}
    conv = convert(
        "id = TST.1 hide_window = yes immediate = { character_event = { id = TST.2 random = 3 } }",
        ck3_id_of=both, live_ids={"TST.1", "TST.2"},
    )
    text = write(Block(entries=[Node(key=conv.ck3_id, value=conv.body)]))
    assert "trigger_event = {" not in text
    assert "# CK2-unmapped: character_event" in text


# -- CK2 shapes --------------------------------------------------------------

def test_gated_desc_becomes_first_valid_triggered_desc() -> None:
    conv = convert(
        "id = TST.1 desc = { text = D_A trigger = { age = 16 } } desc = { text = D_B } "
        "option = { name = A }"
    )
    text = write(Block(entries=[Node(key=conv.ck3_id, value=conv.body)]))
    assert "first_valid = {" in text
    assert "triggered_desc = {" in text
    assert "desc = D_A" in text and "desc = D_B" in text
    assert set(conv.loc_keys) >= {"D_A", "D_B", "A"}


def test_option_name_block_keeps_the_ck2_shape() -> None:
    conv = convert(
        "id = TST.1 desc = D option = { name = { text = A_BRAVE trigger = { age = 16 } } add_gold = 1 }"
    )
    text = write(Block(entries=[Node(key=conv.ck3_id, value=conv.body)]))
    assert "name = {" in text and "text = A_BRAVE" in text


def test_ck2_ai_chance_is_dropped_with_a_comment() -> None:
    conv = convert(
        "id = TST.1 desc = D option = { name = A ai_chance = { factor = 5 } add_gold = 1 }"
    )
    text = write(Block(entries=[Node(key=conv.ck3_id, value=conv.body)]))
    assert "ai_chance = {\n" not in text.replace("# CK2: ai_chance = {\n", "")
    assert "# CK2-unmapped: ai_chance" in text


def test_top_level_shorthands_fold_into_the_trigger() -> None:
    conv = convert(
        "id = TST.1 hide_window = yes min_age = 16 capable_only = yes immediate = { add_gold = 1 }"
    )
    text = write(Block(entries=[Node(key=conv.ck3_id, value=conv.body)]))
    assert "age >= 16" in text
    assert "is_incapable = no" in text
    assert conv.live, conv.gates


def test_unknown_top_level_key_goes_through_the_trigger_table() -> None:
    conv = convert("id = TST.1 hide_window = yes society = yes immediate = { add_gold = 1 }")
    text = write(Block(entries=[Node(key=conv.ck3_id, value=conv.body)]))
    assert "# CK2-unmapped: society" in text
    assert conv.total > conv.mapped


# -- tables ------------------------------------------------------------------

def test_header_trigger_keys_are_real_ck3_keys() -> None:
    """Same bar as `scripts/verify_decisions_vocab.py`: no key from memory."""
    truth = REPO / "docs" / "evidence" / "ck3_vocab_ground_truth.txt"
    if not truth.is_file():
        pytest.skip("ck3_vocab_ground_truth.txt not generated in this checkout")
    known = set(truth.read_text(encoding="utf-8").split())
    misses = sorted(
        ck3 for ck3, _op, _t in step.EVENT_HEADER_TRIGGERS.values() if ck3 not in known
    )
    assert misses == [], misses


def test_theme_table_only_names_installed_ck3_themes() -> None:
    table = step.read_themes(REPO / "mappings" / "event_themes.csv")
    assert table, "mappings/event_themes.csv is empty"
    game = Config.load(REPO / "configs" / "faerun.toml").ck3_game
    folder = game / "common" / "event_themes"
    if not folder.is_dir():
        pytest.skip("CK3 1.19 install not present in this checkout")
    sys.path.insert(0, str(REPO / "scripts"))
    from build_event_themes_csv import installed_themes  # noqa: E402

    known = installed_themes(game)
    misses = sorted(set(table.values()) - known)
    assert misses == [], misses


def test_file_stem_is_sanitised() -> None:
    """Faerûn ships `events/faerun_adoption_events .txt` - trailing space."""
    assert step._file_stem("events/faerun_adoption_events .txt") == "faerun_adoption_events"
    assert step._file_stem("events/HF_religious_events.txt") == "hf_religious_events"


# -- run(ctx) ----------------------------------------------------------------

CONFIG_TEMPLATE = """
[mod]
name = "Test Mod"
prefix = "tst"
version = "1.0.0"
supported_version = "1.19.*"
tags = ["Total Conversion"]
bookmark_date = "1357.1.1"

[paths]
ck2_game = "{ck2_game}"
ck2_mod = "{ck2_mod}"
ck3_game = "{ck3_game}"
out = "{out}"

[events]
enabled = true
provenance = "{provenance}"
evidence = "{evidence}"
triggers = "{triggers}"
effects = "{effects}"
themes_csv = "{themes}"
min_score = 1.0
default_theme = "dungeon"
"""

VOCAB_HEADER = "ck2_key,ck3_key,status,confidence,note\n"
TEST_TRIGGERS = VOCAB_HEADER + "age,age,exact,verified,unchanged\n"
TEST_EFFECTS = VOCAB_HEADER + (
    "add_gold,add_gold,exact,verified,unchanged\n"
    "society_member_of,,none,verified,societies do not exist in CK3\n"
)
TEST_THEMES = (
    "ck2_field,ck2_value,ck3_theme,note,faerun_new_uses\n"
    "picture,GFX_evt_bishop,faith,clergy,1\n"
)

CK2_EVENTS = """namespace = TST

character_event = {
\tid = TST.1
\tdesc = EVTDESC_TST_1
\tpicture = GFX_evt_bishop
\tis_triggered_only = yes
\ttrigger = { age = 16 }
\toption = { name = EVTOPTA_TST_1 add_gold = 5 }
}

character_event = {
\tid = TST.2
\thide_window = yes
\timmediate = { society_member_of = brotherhood }
}

province_event = {
\tid = TST.3
\thide_window = yes
\timmediate = { add_gold = 1 }
}
"""


@pytest.fixture
def run_ctx(tmp_path: Path):
    ck2_mod = tmp_path / "ck2mod"
    (ck2_mod / "events").mkdir(parents=True)
    (ck2_mod / "events" / "test_events.txt").write_text(CK2_EVENTS, encoding="utf-8")

    provenance = tmp_path / "events_provenance.csv"
    with open(provenance, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow([
            "id", "kind", "faerun_file", "vanilla_file", "status", "changed_keys",
            "uses_faerun_mechanic", "vanilla_dup_count", "faerun_dup_count",
        ])
        writer.writerow(["TST.1", "character_event", "events/test_events.txt", "", "new", "", "", "0", "0"])
        writer.writerow(["TST.2", "character_event", "events/test_events.txt", "", "new", "", "", "0", "0"])
        writer.writerow(["TST.3", "province_event", "events/test_events.txt", "", "new", "", "", "0", "0"])
        writer.writerow(["TST.4", "character_event", "events/test_events.txt", "", "kept", "", "", "0", "0"])

    out = tmp_path / "mod"
    out.mkdir()
    paths = {
        "provenance": provenance,
        "evidence": tmp_path / "events_convertibility.csv",
        "triggers": tmp_path / "triggers.csv",
        "effects": tmp_path / "effects.csv",
        "themes": tmp_path / "themes.csv",
    }
    paths["triggers"].write_text(TEST_TRIGGERS, encoding="utf-8")
    paths["effects"].write_text(TEST_EFFECTS, encoding="utf-8")
    paths["themes"].write_text(TEST_THEMES, encoding="utf-8")
    config_path = tmp_path / "test.toml"
    config_path.write_text(CONFIG_TEMPLATE.format(
        ck2_game=tmp_path / "ck2game", ck2_mod=ck2_mod, ck3_game=tmp_path / "ck3game",
        out=out, **paths,
    ))
    ctx = Context(Config.load(config_path), dry_run=False)
    return ctx, out, paths["evidence"]


def test_run_writes_namespaced_event_files_and_evidence(run_ctx) -> None:
    ctx, out, evidence = run_ctx
    result = step.run(ctx)
    assert result.counts["live"] == 1
    assert result.counts["stub"] == 1
    assert result.counts["skipped_scope"] == 1     # province_event
    assert result.counts["skipped_status"] == 1    # `kept`

    written = out / "events" / "tst_test_events.txt"
    assert written.is_file()
    text = written.read_text(encoding="utf-8")
    assert text.startswith("﻿")               # CLAUDE.md: events/ takes a BOM
    assert "namespace = tst_tst" in text
    assert "tst_tst.1 = {" in text and "tst_tst.2 = {" in text
    assert "theme = faith" in text
    assert "tst_tst.3" not in text                 # province events are never emitted

    rows = {r["ck2_id"]: r for r in csv.DictReader(open(evidence, encoding="utf-8"))}
    assert rows["TST.1"]["live"] == "yes"
    assert rows["TST.2"]["live"] == "no"
    assert rows["TST.3"]["emitted"] == "no"
    assert "TST.4" not in rows                     # `kept` is another lane's job


def test_run_can_be_disabled(run_ctx) -> None:
    ctx, out, _ = run_ctx
    ctx.config.raw["events"]["enabled"] = False
    result = step.run(ctx)
    assert result.counts["live"] == 0
    assert not (out / "events").exists()


def test_config_keys_are_really_read(run_ctx) -> None:
    """The silent-no-op guard: every `[events]` key must change the output."""
    ctx, out, _ = run_ctx
    raw = ctx.config.raw["events"]
    config = step.EventsConfig.from_raw(raw)
    assert config.min_score == 1.0
    assert config.default_theme == "dungeon"
    assert config.themes_csv == Path(raw["themes_csv"])

    # min_score = 0 makes the below-threshold event live too
    raw["min_score"] = 0.0
    assert step.run(ctx).counts["live"] == 2

    # default_theme reaches the file
    raw["min_score"] = 1.0
    raw["themes_csv"] = str(Path(raw["themes_csv"]).with_name("empty.csv"))
    Path(raw["themes_csv"]).write_text("ck2_field,ck2_value,ck3_theme,note,uses\n", encoding="utf-8")
    step.run(ctx)
    assert "theme = dungeon" in (out / "events" / "tst_test_events.txt").read_text(encoding="utf-8")


def test_run_reports_loc_key_misses(run_ctx) -> None:
    ctx, out, _ = run_ctx
    ctx.data["loc"] = {"keys": frozenset({"EVTDESC_TST_1"})}
    result = step.run(ctx)
    # EVTOPTA_TST_1 has no text behind it
    assert result.counts["loc_key_misses"] == 1


def test_event_id_and_the_whole_set_map_agree() -> None:
    """Leading zeros: `event_id` and `build_event_id_map` must not disagree."""
    assert ids.event_id("fae", "FCE.0001") == "fae_fce.1"
    ck2 = ["FCE.0001", "FCE.1", "KNI.70000"]
    mapped = ids.build_event_id_map("fae", ck2)
    for one in ck2:
        if int(one.split(".")[-1]) <= ids.MAX_EVENT_NUMBER:
            assert mapped[one] == ids.event_id("fae", one)
    assert mapped["KNI.70000"] == f"fae_kni.{ids.MAX_EVENT_NUMBER}"


def test_ck2_at_variable_is_never_live() -> None:
    """`remove_character_flag = x@FROM` breaks CK3's reader, not just its engine."""
    conv = convert(
        "id = TST.1 hide_window = yes immediate = { add_gold = duel@FROM }"
    )
    assert "ck2_variable" in conv.gates


def test_rejected_keys_are_commented_even_though_the_table_maps_them() -> None:
    triggers = dict(TRIGGERS)
    triggers["religion"] = VocabRow("religion", "faith", "approx", "verified", "faith")
    conv = step.convert_event(
        "TST.1", _event("id = TST.1 hide_window = yes religion = eilistraee"),
        kind="character_event", prefix="tst", triggers=triggers, effects=EFFECTS,
        traits=TraitInfo(), themes=THEMES, default_theme="default",
        ck3_id_of={"TST.1": "tst_tst.1"}, live_ids={"TST.1"}, scoped_out={},
        min_score=1.0, source_file="events/test.txt",
    )
    text = write(Block(entries=[Node(key=conv.ck3_id, value=conv.body)]))
    assert "faith = eilistraee" not in text
    assert "# CK2-unmapped: religion" in text
    assert not conv.live
