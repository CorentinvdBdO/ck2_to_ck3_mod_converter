"""Tests for the `decisions` step (lane `events-decisions`, README §5 step 3).

Covers: a fully-mapped synthetic decision, a partially-mapped one (unmapped
keys become `# CK2:` comments), one below `min_score` (`is_shown` forced
off, `fae_unported` comment kept), bare `<trait> = yes/no` shorthand and the
explicit `trait = X` form resolved through the traits step's id map, scope
words / title-tag scope keys, non-character-scope groups skipped, and a
full `run(ctx)` over a tiny synthetic mod.
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
from ck2ck3.decisions_vocab import VocabRow  # noqa: E402
from ck2ck3.pdx import Block, Node, parse  # noqa: E402
from ck2ck3.steps import decisions as step  # noqa: E402

TRIGGERS = {
    "age": VocabRow("age", "age", "exact", "verified", "unchanged"),
    "gold": VocabRow("gold", "gold", "exact", "verified", "unchanged"),
    "has_dlc": VocabRow("has_dlc", "has_dlc", "exact", "verified", "unchanged"),
    "trait": VocabRow("trait", "has_trait", "approx", "verified", "resolved via traits map"),
    "society": VocabRow("society", None, "none", "verified", "societies do not exist in CK3"),
}
EFFECTS = {
    "add_gold": VocabRow("add_gold", "add_gold", "exact", "verified", "unchanged"),
    "trait": VocabRow("trait", "add_trait", "approx", "verified", "resolved via traits map"),
    "remove_trait": VocabRow("remove_trait", "remove_trait", "exact", "verified", "unchanged"),
}


def _traits() -> step.TraitInfo:
    return step.TraitInfo(
        live={"brave", "zealous"},
        renames={"greedy": "avaricious"},
        drop_notes={"dropped_trait": "no CK3 counterpart"},
        sexuality={"quirk_trait": "bisexual"},
        unported={"renowned_wizard"},
    )


def test_convert_block_unported_trait_is_unmapped_not_passed_through() -> None:
    """A real CK2 trait the `traits` step commented out must not leak as a value."""
    src = parse("trait = renowned_wizard\n")
    stats = step.ConvertStats()
    out = step.convert_block(src, kind="trigger", triggers=TRIGGERS, effects=EFFECTS, traits=_traits(), stats=stats)
    assert out.entries == []
    assert any("renowned_wizard" in c for c in out.end_comments)


# -- convert_block -----------------------------------------------------------

def test_convert_block_fully_mapped() -> None:
    src = parse("age = 16\ngold = 100\n")
    stats = step.ConvertStats()
    out = step.convert_block(src, kind="trigger", triggers=TRIGGERS, effects=EFFECTS, traits=_traits(), stats=stats)
    keys = [n.key for n in out.entries]
    assert keys == ["age", "gold"]
    assert stats.mapped == stats.total == 2


def test_convert_block_unmapped_key_becomes_comment() -> None:
    src = parse("age = 16\nsociety = yes\n")
    stats = step.ConvertStats()
    out = step.convert_block(src, kind="trigger", triggers=TRIGGERS, effects=EFFECTS, traits=_traits(), stats=stats)
    keys = [n.key for n in out.entries]
    assert keys == ["age"]
    assert stats.mapped == 1
    assert stats.total == 2
    assert any("society" in c for c in out.end_comments)
    assert any("CK2:" in c for c in out.end_comments)


def test_convert_block_scope_word_rewritten() -> None:
    src = parse("FROM = { age = 16 }\n")
    stats = step.ConvertStats()
    out = step.convert_block(src, kind="trigger", triggers=TRIGGERS, effects=EFFECTS, traits=_traits(), stats=stats)
    assert out.entries[0].key == "scope:ck2_from"
    assert out.entries[0].value.entries[0].key == "age"


def test_convert_block_title_tag_scope_key() -> None:
    src = parse("k_ammarindar = { age = 16 }\n")
    stats = step.ConvertStats()
    out = step.convert_block(src, kind="trigger", triggers=TRIGGERS, effects=EFFECTS, traits=_traits(), stats=stats)
    assert out.entries[0].key == "title:k_ammarindar"


def test_convert_block_bare_trait_shorthand_trigger() -> None:
    src = parse("brave = yes\ngreedy = yes\ndropped_trait = yes\n")
    stats = step.ConvertStats()
    out = step.convert_block(src, kind="trigger", triggers=TRIGGERS, effects=EFFECTS, traits=_traits(), stats=stats)
    # brave (live) -> has_trait, greedy (renamed) -> has_trait avaricious
    assert out.entries[0].key == "has_trait" and out.entries[0].value == "brave"
    assert out.entries[1].key == "has_trait" and out.entries[1].value == "avaricious"
    # dropped_trait has no CK3 trait -> unmapped comment, not a third entry
    assert len(out.entries) == 2
    assert any("dropped_trait" in c for c in out.end_comments)


def test_convert_block_bare_trait_shorthand_no_polarity_and_effect() -> None:
    src = parse("brave = no\n")
    stats = step.ConvertStats()
    out = step.convert_block(src, kind="trigger", triggers=TRIGGERS, effects=EFFECTS, traits=_traits(), stats=stats)
    assert out.entries[0].key == "NOT"
    assert out.entries[0].value.entries[0].key == "has_trait"
    assert out.entries[0].value.entries[0].value == "brave"

    src2 = parse("zealous = yes\n")
    stats2 = step.ConvertStats()
    out2 = step.convert_block(src2, kind="effect", triggers=TRIGGERS, effects=EFFECTS, traits=_traits(), stats=stats2)
    assert out2.entries[0].key == "add_trait" and out2.entries[0].value == "zealous"


def test_convert_block_sexuality_trait_is_unmapped() -> None:
    src = parse("quirk_trait = yes\n")
    stats = step.ConvertStats()
    out = step.convert_block(src, kind="trigger", triggers=TRIGGERS, effects=EFFECTS, traits=_traits(), stats=stats)
    assert out.entries == []
    assert any("sexuality" in c for c in out.end_comments)


def test_convert_block_explicit_trait_key_resolves_argument() -> None:
    src = parse("trait = greedy\n")
    stats = step.ConvertStats()
    out = step.convert_block(src, kind="trigger", triggers=TRIGGERS, effects=EFFECTS, traits=_traits(), stats=stats)
    assert out.entries[0].key == "has_trait"
    assert out.entries[0].value == "avaricious"

    src2 = parse("remove_trait = dropped_trait\n")
    stats2 = step.ConvertStats()
    out2 = step.convert_block(src2, kind="effect", triggers=TRIGGERS, effects=EFFECTS, traits=_traits(), stats=stats2)
    assert out2.entries == []
    assert any("dropped_trait" in c for c in out2.end_comments)


def test_convert_block_limit_inside_effect_uses_trigger_table() -> None:
    """`limit = {}` is always trigger-shaped, even nested in an effect block."""
    src = parse("if = { limit = { trait = greedy } add_gold = 10 }\n")
    stats = step.ConvertStats()
    out = step.convert_block(src, kind="effect", triggers=TRIGGERS, effects=EFFECTS, traits=_traits(), stats=stats)
    if_node = out.entries[0]
    limit_node = next(n for n in if_node.value.entries if n.key == "limit")
    assert limit_node.value.entries[0].key == "has_trait"  # not add_trait
    assert limit_node.value.entries[0].value == "avaricious"


def test_convert_block_structural_keys_pass_through() -> None:
    src = parse("AND = { age = 16 gold = 100 }\n")
    stats = step.ConvertStats()
    out = step.convert_block(src, kind="trigger", triggers=TRIGGERS, effects=EFFECTS, traits=_traits(), stats=stats)
    assert out.entries[0].key == "AND"
    inner_keys = [n.key for n in out.entries[0].value.entries]
    assert inner_keys == ["age", "gold"]
    # structural key itself is not scored, only its 2 children
    assert stats.total == 2


# -- convert_decision ---------------------------------------------------------

def _decision_block(text: str) -> Block:
    doc = parse(f"decisions = {{ my_dec = {{ {text} }} }}\n")
    return step.find_decision_block(doc, "decisions", "my_dec")


def test_convert_decision_fully_mapped_scores_high() -> None:
    block = _decision_block(
        "potential = { age = 16 } allow = { gold = 100 } effect = { add_gold = 50 }"
    )
    converted = step.convert_decision(
        "my_dec", block, status="new", kind="decisions",
        triggers=TRIGGERS, effects=EFFECTS, traits=_traits(), min_score=0.6,
    )
    assert converted.score == 1.0
    keys = [n.key for n in converted.block.entries if isinstance(n, Node)]
    assert "is_shown" in keys and "is_valid" in keys and "effect" in keys
    assert "ai_check_interval" in keys  # defaulted
    assert "selection_tooltip" in keys and "confirm_text" in keys


def test_convert_decision_partially_mapped() -> None:
    block = _decision_block(
        "potential = { age = 16 society = yes } effect = { add_gold = 50 }"
    )
    converted = step.convert_decision(
        "my_dec", block, status="new", kind="decisions",
        triggers=TRIGGERS, effects=EFFECTS, traits=_traits(), min_score=0.6,
    )
    assert 0 < converted.score < 1
    assert converted.mapped < converted.total


def test_convert_decision_below_threshold_hides_but_keeps_content() -> None:
    block = _decision_block("potential = { society = yes } effect = { add_gold = 50 }")
    converted = step.convert_decision(
        "my_dec", block, status="new", kind="decisions",
        triggers=TRIGGERS, effects=EFFECTS, traits=_traits(), min_score=0.99,
    )
    assert converted.score < 0.99
    is_shown = next(n for n in converted.block.entries if isinstance(n, Node) and n.key == "is_shown")
    assert is_shown.value.entries[0].key == "always"
    assert is_shown.value.entries[0].value is False
    header = converted.block.entries[0].leading_comments
    assert any("fae_unported" in c for c in header)
    # the effect content is still present and inspectable
    effect_node = next(n for n in converted.block.entries if isinstance(n, Node) and n.key == "effect")
    assert effect_node.value.entries[0].key == "add_gold"


# -- run(ctx) integration -----------------------------------------------------

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

[decisions]
enabled = true
provenance = "{provenance}"
evidence = "{evidence}"
triggers = "{triggers}"
effects = "{effects}"
min_score = 0.5
"""

VOCAB_HEADER = "ck2_key,ck3_key,status,confidence,note\n"
TEST_TRIGGERS = VOCAB_HEADER + (
    "age,age,exact,verified,unchanged\n"
    "gold,gold,exact,verified,unchanged\n"
)
TEST_EFFECTS = VOCAB_HEADER + "add_gold,add_gold,exact,verified,unchanged\n"


@pytest.fixture
def run_ctx(tmp_path: Path):
    ck2_mod = tmp_path / "ck2mod"
    (ck2_mod / "decisions").mkdir(parents=True)
    (ck2_mod / "decisions" / "test_decisions.txt").write_text(
        "decisions = {\n"
        "\thigh_score = {\n"
        "\t\tpotential = { age = 16 }\n"
        "\t\tallow = { gold = 100 }\n"
        "\t\teffect = { add_gold = 50 }\n"
        "\t}\n"
        "\tlow_score = {\n"
        "\t\tpotential = { society = yes }\n"
        "\t\tallow = { society = yes }\n"
        "\t\teffect = { society = yes }\n"
        "\t}\n"
        "}\n"
        "title_decisions = {\n"
        "\tnot_character_scope = {\n"
        "\t\tfilter = owned\n"
        "\t\tallow = { always = yes }\n"
        "\t}\n"
        "}\n",
        encoding="utf-8",
    )
    provenance = tmp_path / "provenance.csv"
    with open(provenance, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["id", "kind", "faerun_file", "vanilla_file", "status", "changed_keys", "uses_faerun_mechanic", "vanilla_dup_count", "faerun_dup_count"])
        writer.writerow(["high_score", "decisions", "decisions/test_decisions.txt", "", "new", "", "", "0", "0"])
        writer.writerow(["low_score", "decisions", "decisions/test_decisions.txt", "", "new", "", "societies", "0", "0"])
        writer.writerow(["not_character_scope", "title_decisions", "decisions/test_decisions.txt", "", "new", "", "", "0", "0"])

    out = tmp_path / "mod"
    out.mkdir()
    evidence = tmp_path / "decisions_convertibility.csv"
    triggers = tmp_path / "triggers.csv"
    triggers.write_text(TEST_TRIGGERS, encoding="utf-8")
    effects = tmp_path / "effects.csv"
    effects.write_text(TEST_EFFECTS, encoding="utf-8")
    config_path = tmp_path / "test.toml"
    config_path.write_text(
        CONFIG_TEMPLATE.format(
            ck2_game=tmp_path / "ck2game", ck2_mod=ck2_mod, ck3_game=tmp_path / "ck3game",
            out=out, provenance=provenance, evidence=evidence,
            triggers=triggers, effects=effects,
        )
    )
    config = Config.load(config_path)
    ctx = Context(config, dry_run=False)
    return ctx, out, evidence


def test_run_writes_common_decisions_and_evidence(run_ctx, monkeypatch: pytest.MonkeyPatch) -> None:
    ctx, out, evidence_path = run_ctx
    result = step.run(ctx)
    assert result.counts["emitted"] == 1
    assert result.counts["hidden"] == 1
    assert result.counts["skipped_group"] == 1

    written = out / "common" / "decisions" / "tst_test_decisions.txt"
    assert written.is_file()
    text = written.read_text(encoding="utf-8")
    assert text.startswith("﻿")  # BOM
    assert "high_score" in text
    assert "low_score" in text
    assert "not_character_scope" not in text  # title-scope group never emitted

    rows = {r["id"]: r for r in csv.DictReader(open(evidence_path, encoding="utf-8"))}
    assert rows["high_score"]["emitted"] == "yes"
    assert rows["low_score"]["emitted"] == "yes"
    assert rows["not_character_scope"]["emitted"] == "no"


def test_run_is_opt_in_by_default(run_ctx, monkeypatch: pytest.MonkeyPatch) -> None:
    """[decisions] enabled defaults to false: the step writes nothing (docs/step_decisions.md §3b)."""
    ctx, out, _ = run_ctx
    ctx.config.raw["decisions"]["enabled"] = False
    result = step.run(ctx)
    assert result.counts["emitted"] == 0
    assert not list((out / "common" / "decisions").glob("fae_*.txt")) if (out / "common" / "decisions").exists() else True
    assert "opt-in" in result.summary
