"""Tests for the `on_actions` step (lane `on-actions`).

Covers: the mapping-CSV reader, the event-reference extractor (bare
`events = { }` items vs weighted `random_events = { }` nodes), the
live/stub/unknown routing, the additive (append-only) output shape, and a
full `run(ctx)` that chains `events` -> `on_actions` and checks the `orphan`
flag flips off for a wired event (docs/step_events.md §on_actions).
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from ck2ck3.config import Config  # noqa: E402
from ck2ck3.context import Context  # noqa: E402
from ck2ck3.pdx import Block, Item, Node, parse  # noqa: E402
from ck2ck3.steps import events as events_step  # noqa: E402
from ck2ck3.steps import on_actions as step  # noqa: E402


def _block(text: str) -> Block:
    return parse(f"x = {{ {text} }}\n").entries[0].value


# -- extract_event_refs -------------------------------------------------------

def test_extract_event_refs_reads_bare_events_list() -> None:
    block = _block("events = { TST.1 TST.2 delay = { days = 5 } TST.3 }")
    refs = step.extract_event_refs(block)
    assert [r.ck2_event_id for r in refs] == ["TST.1", "TST.2", "TST.3"]
    assert all(r.list_kind == "events" and r.weight is None for r in refs)


def test_extract_event_refs_reads_weighted_random_events() -> None:
    block = _block(
        "random_events = { chance_to_happen = 25 100 = TST.1 100 = 0 200 = TST.2 }"
    )
    refs = step.extract_event_refs(block)
    assert [(r.ck2_event_id, r.weight) for r in refs] == [("TST.1", 100), ("TST.2", 200)]


def test_extract_event_refs_ignores_other_keys() -> None:
    block = _block("on_actions = { some_other_action } effect = { add_gold = 1 }")
    assert step.extract_event_refs(block) == []


# -- collect_faerun_on_actions merges same-name blocks across files ----------

@pytest.fixture
def ck2_mod(tmp_path: Path) -> Path:
    root = tmp_path / "ck2mod"
    oa = root / "common" / "on_actions"
    oa.mkdir(parents=True)
    (oa / "00_on_actions.txt").write_text(
        "on_death = {\n\tevents = {\n\t\tTST.1\n\t}\n}\n"
        "on_marriage = {\n\trandom_events = {\n\t\t100 = TST.2\n\t}\n}\n",
        encoding="utf-8",
    )
    # A second file adding more to `on_death` - additive merge across files.
    (oa / "01_more.txt").write_text(
        "on_death = {\n\tevents = {\n\t\tTST.3\n\t}\n}\n",
        encoding="utf-8",
    )
    return root


def test_collect_faerun_on_actions_merges_same_name_across_files(ck2_mod, tmp_path) -> None:
    config_path = tmp_path / "cfg.toml"
    config_path.write_text(f"""
[mod]
name = "Test"
prefix = "tst"
version = "1.0.0"
supported_version = "1.19.*"
tags = ["Total Conversion"]
bookmark_date = "1357.1.1"

[paths]
ck2_game = "{tmp_path / 'ck2game'}"
ck2_mod = "{ck2_mod}"
ck3_game = "{tmp_path / 'ck3game'}"
out = "{tmp_path / 'mod'}"
""")
    ctx = Context(Config.load(config_path), dry_run=True)
    merged = step.collect_faerun_on_actions(ctx)
    ids_ = [r.ck2_event_id for r in step.extract_event_refs(merged["on_death"])]
    assert ids_ == ["TST.1", "TST.3"]


# -- run(ctx): events -> on_actions chained -----------------------------------

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

[on_actions]
enabled = true
mapping = "{mapping}"
evidence = "{oa_evidence}"
"""

TEST_TRIGGERS = "ck2_key,ck3_key,status,confidence,note\nage,age,exact,verified,unchanged\n"
TEST_EFFECTS = "ck2_key,ck3_key,status,confidence,note\nadd_gold,add_gold,exact,verified,unchanged\n"
TEST_THEMES = "ck2_field,ck2_value,ck3_theme,note,faerun_new_uses\n"

CK2_EVENTS = """namespace = TST

character_event = {
\tid = TST.1
\thide_window = yes
\ttrigger = { age = 16 }
\timmediate = { add_gold = 5 }
}

character_event = {
\tid = TST.2
\thide_window = yes
\timmediate = { society_member_of = brotherhood }
}
"""

CK2_ON_ACTIONS = """on_death = {
\tevents = {
\t\tTST.1
\t\tTST.2
\t\tTST.99
\t}
}
"""


@pytest.fixture
def run_ctx(tmp_path: Path):
    ck2_mod = tmp_path / "ck2mod"
    (ck2_mod / "events").mkdir(parents=True)
    (ck2_mod / "events" / "test_events.txt").write_text(CK2_EVENTS, encoding="utf-8")
    (ck2_mod / "common" / "on_actions").mkdir(parents=True)
    (ck2_mod / "common" / "on_actions" / "00_on_actions.txt").write_text(
        CK2_ON_ACTIONS, encoding="utf-8",
    )

    provenance = tmp_path / "events_provenance.csv"
    with open(provenance, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow([
            "id", "kind", "faerun_file", "vanilla_file", "status", "changed_keys",
            "uses_faerun_mechanic", "vanilla_dup_count", "faerun_dup_count",
        ])
        writer.writerow(["TST.1", "character_event", "events/test_events.txt", "", "new", "", "", "0", "0"])
        writer.writerow(["TST.2", "character_event", "events/test_events.txt", "", "new", "", "", "0", "0"])

    mapping = tmp_path / "on_actions_map.csv"
    with open(mapping, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["ck2_on_action", "status", "ck3_on_action", "ck3_root_scope", "confidence", "note"])
        writer.writerow(["on_death", "modified", "on_death", "character (dying)", "verified", "test row"])

    out = tmp_path / "mod"
    out.mkdir()
    paths = {
        "provenance": provenance,
        "evidence": tmp_path / "events_convertibility.csv",
        "triggers": tmp_path / "triggers.csv",
        "effects": tmp_path / "effects.csv",
        "themes": tmp_path / "themes.csv",
        "mapping": mapping,
        "oa_evidence": tmp_path / "on_actions_convertibility.csv",
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
    return ctx, out, paths["oa_evidence"]


def test_run_wires_a_live_event_and_comments_out_the_rest(run_ctx) -> None:
    ctx, out, oa_evidence = run_ctx
    events_result = events_step.run(ctx)
    assert events_result.counts["live"] == 1     # TST.1; TST.2 is societies-unmapped
    result = step.run(ctx)

    text = (out / "common" / "on_action" / "fae_on_actions.txt").read_text(encoding="utf-8")
    assert "on_death = {" in text
    assert "tst_tst.1" in text                    # TST.1 wired live
    assert "# CK2 on_death -> TST.2: not wired" in text   # stub, stays a comment
    assert "# CK2 on_death -> TST.99: not wired" in text  # not a `new` event at all

    assert result.counts["live_events_wired"] == 1
    assert result.counts["hookups_skipped"] == 2

    rows = list(csv.DictReader(open(oa_evidence, encoding="utf-8")))
    wired_rows = [r for r in rows if r["wired"] == "yes"]
    assert wired_rows[0]["ck3_event_id"] == "tst_tst.1"
    assert wired_rows[0]["trigger_first_line"]     # safety-rule soak list


def test_run_clears_orphan_on_the_wired_event(run_ctx) -> None:
    ctx, out, _ = run_ctx
    events_step.run(ctx)
    events_text_before = (out / "events" / "tst_test_events.txt").read_text(encoding="utf-8")
    assert "orphan = yes" in events_text_before     # nothing calls it yet

    step.run(ctx)
    events_text_after = (out / "events" / "tst_test_events.txt").read_text(encoding="utf-8")
    assert "tst_tst.1 = {" in events_text_after
    # orphan cleared specifically on tst_tst.1 (it may still be true elsewhere
    # if a future fixture adds another unreached live event).
    lines = events_text_after.splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.strip() == "tst_tst.1 = {")
    end = next(i for i in range(start, len(lines)) if lines[i].strip() == "}")
    assert not any("orphan" in ln for ln in lines[start:end])


def test_run_without_events_data_is_a_safe_no_op(tmp_path: Path) -> None:
    config_path = tmp_path / "cfg.toml"
    config_path.write_text(f"""
[mod]
name = "Test"
prefix = "tst"
version = "1.0.0"
supported_version = "1.19.*"
tags = ["Total Conversion"]
bookmark_date = "1357.1.1"

[paths]
ck2_game = "{tmp_path / 'ck2game'}"
ck2_mod = "{tmp_path / 'ck2mod'}"
ck3_game = "{tmp_path / 'ck3game'}"
out = "{tmp_path / 'mod'}"
""")
    (tmp_path / "ck2mod").mkdir()
    ctx = Context(Config.load(config_path), dry_run=True)
    result = step.run(ctx)
    assert result.counts["live_events_wired"] == 0


def test_run_can_be_disabled(run_ctx) -> None:
    ctx, out, _ = run_ctx
    events_step.run(ctx)
    ctx.config.raw["on_actions"]["enabled"] = False
    result = step.run(ctx)
    assert result.counts["on_action_files"] == 0
    assert not (out / "common" / "on_action" / "fae_on_actions.txt").exists()
