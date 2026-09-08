"""Config, step registry, context, runner and the two built-in steps."""

from __future__ import annotations

from pathlib import Path

import pytest

from ck2ck3 import steps
from ck2ck3.ck3mod import PROTECTED, looks_like_a_mod, removable
from ck2ck3.cli import main
from ck2ck3.config import Config, ConfigError
from ck2ck3.context import Context, IdAllocator
from ck2ck3.pdx import parse
from ck2ck3.runner import run_steps, write_evidence
from ck2ck3.steps import clean as clean_step
from ck2ck3.steps import descriptor as descriptor_step

REPO = Path(__file__).resolve().parents[1]
REFERENCE_CONFIG = REPO / "configs" / "faerun.toml"

CONFIG_TEMPLATE = """
[mod]
name = "Test Mod"
prefix = "tst"
version = "1.2.3"
supported_version = "1.19.*"
tags = ["Total Conversion", "Map"]
bookmark_date = "1357.1.1"
replace_paths = ["history", "common/landed_titles"]

[paths]
ck2_game = "{ck2_game}"
ck2_mod = "{ck2_mod}"
ck3_game = "{ck3_game}"
out = "{out}"

[map]
dimensions = [4096, 2048]
scale = 2.0
offset = [-10, 5]
"""


@pytest.fixture
def config(tmp_path) -> Config:
    out = tmp_path / "mod"
    out.mkdir()
    (out / "README.md").write_text("keep me\n")
    path = tmp_path / "test.toml"
    path.write_text(
        CONFIG_TEMPLATE.format(
            ck2_game=tmp_path / "ck2", ck2_mod=tmp_path / "src", ck3_game=tmp_path / "ck3", out=out
        )
    )
    return Config.load(path)


# -- config ----------------------------------------------------------------
def test_config_reads_every_section(config):
    assert config.name == "Test Mod"
    assert config.prefix == "tst"
    assert config.version == "1.2.3"
    assert config.tags == ("Total Conversion", "Map")
    assert config.replace_paths == ("history", "common/landed_titles")
    assert config.map.dimensions == (4096, 2048)
    assert config.map.scale == 2.0
    assert config.map.offset == (-10, 5)


def test_config_parses_the_bookmark_date(config):
    assert (config.bookmark.year, config.bookmark.month) == (1357, 1)


def test_config_resolves_relative_paths_against_the_repo_root(tmp_path):
    path = tmp_path / "rel.toml"
    path.write_text(
        CONFIG_TEMPLATE.format(ck2_game="a", ck2_mod="Faerun/Faerun", ck3_game="c", out="d")
    )
    assert Config.load(path).ck2_mod == REPO / "Faerun" / "Faerun"


def test_config_out_can_be_overridden(config, tmp_path):
    other = tmp_path / "elsewhere"
    assert Config.load(config.path, out=other).out == other.resolve()


def test_config_missing_key_is_an_error(tmp_path):
    path = tmp_path / "bad.toml"
    path.write_text("[mod]\nname = 'x'\n")
    with pytest.raises(ConfigError):
        Config.load(path)


def test_config_missing_file_is_an_error(tmp_path):
    with pytest.raises(ConfigError):
        Config.load(tmp_path / "nope.toml")


def test_reference_config_loads():
    config = Config.load(REFERENCE_CONFIG)
    assert config.prefix == "fae"
    assert config.bookmark_date == "1357.1.1"
    assert config.ck2_mod.name == "Faerun"
    assert config.out.name == "faerun_ck2_to_ck3_converted"
    assert config.supported_version == "1.19.*"


# -- registry ---------------------------------------------------------------
def test_registry_lists_and_loads_steps():
    assert {"clean", "descriptor"} <= set(steps.available())
    assert callable(steps.load("descriptor").run)
    assert steps.describe("clean")


def test_registry_rejects_an_unknown_step():
    with pytest.raises(steps.UnknownStep):
        steps.load("nope")


def test_resolve_defaults_and_dedupes():
    assert steps.resolve(None) == list(steps.DEFAULT_ORDER)
    assert steps.resolve(["descriptor", "descriptor"]) == ["descriptor"]
    assert steps.resolve(["all"]) == list(steps.DEFAULT_ORDER)


def test_every_step_declares_the_contract():
    for name in steps.available():
        module = steps.load(name)
        assert isinstance(module.OUTPUTS, tuple) and module.OUTPUTS
        assert getattr(module, "DESCRIPTION", "")


def test_step_outputs_do_not_overlap():
    owned: dict[str, str] = {}
    for name in steps.available():
        for output in steps.load(name).OUTPUTS:
            if output == "*":
                continue
            assert output not in owned, f"{name} and {owned[output]} both own {output}"
            owned[output] = name


# -- id allocator -----------------------------------------------------------
def test_id_allocator_is_stable_per_key():
    ids = IdAllocator("province", start=10)
    assert ids.allocate("a") == 10
    assert ids.allocate("b") == 11
    assert ids.allocate("a") == 10
    assert ids.get("b") == 11
    assert ids.mapping() == {"a": 10, "b": 11}


def test_id_allocator_skips_reserved_ids():
    ids = IdAllocator("character")
    ids.reserve(1)
    ids.reserve(2)
    assert ids.allocate() == 3


# -- context ----------------------------------------------------------------
def test_context_paths(config):
    ctx = Context(config)
    assert ctx.ck2("map", "climate.txt").name == "climate.txt"
    assert ctx.out_path("map_data").parent == config.out


def test_context_dry_run_writes_nothing(config):
    ctx = Context(config, dry_run=True)
    path = ctx.write_script("common/x.txt", parse("a = 1"))
    assert not path.exists()
    assert ctx.written == [path]


def test_context_write_script_adds_a_header(config):
    ctx = Context(config)
    path = ctx.write_script("common/x.txt", parse("a = 1"), source="src.txt")
    # utf-8-sig, not utf-8: `common/` is a BOM database (ck2ck3.pdx.encoding).
    text = path.read_text(encoding="utf-8-sig")
    assert text.startswith("# Generated by ck2ck3 from src.txt.")
    assert text.endswith("a = 1\n")


def test_context_write_loc(config):
    ctx = Context(config)
    path = ctx.write_loc("localization/english/tst_l_english.yml", {"k": "v"})
    text = path.read_bytes().decode("utf-8-sig")
    assert text.startswith("l_english:\r\n#")
    assert ' k:0 "v"' in text


# -- clean ------------------------------------------------------------------
def test_clean_removes_generated_and_keeps_protected(config):
    out = config.out
    (out / "common" / "traits").mkdir(parents=True)
    (out / "common" / "traits" / "x.txt").write_text("stale\n")
    (out / "descriptor.mod").write_text('name = "old"\n')
    (out / ".git").mkdir()
    ctx = Context(config)
    result = clean_step.run(ctx)
    assert result.counts["removed"] == 1
    assert not (out / "common").exists()
    assert (out / "README.md").exists()
    assert (out / "descriptor.mod").exists()
    assert (out / ".git").exists()


def test_clean_dry_run_removes_nothing(config):
    (config.out / "common").mkdir()
    clean_step.run(Context(config, dry_run=True))
    assert (config.out / "common").exists()


def test_clean_refuses_a_folder_that_is_not_a_mod(config, tmp_path):
    stranger = tmp_path / "not_a_mod"
    stranger.mkdir()
    (stranger / "important.txt").write_text("keep\n")
    ctx = Context(Config.load(config.path, out=stranger))
    result = clean_step.run(ctx)
    assert result.skipped
    assert (stranger / "important.txt").exists()
    assert ctx.warnings


def test_protected_covers_the_files_the_lane_promised():
    assert {".git", "README.md", "descriptor.mod"} <= PROTECTED


def test_looks_like_a_mod(tmp_path):
    assert looks_like_a_mod(tmp_path / "missing")
    assert looks_like_a_mod(tmp_path)
    (tmp_path / "random.txt").write_text("x")
    assert not looks_like_a_mod(tmp_path)
    (tmp_path / "descriptor.mod").write_text("x")
    assert looks_like_a_mod(tmp_path)
    assert removable(tmp_path) == [tmp_path / "random.txt"]


# -- descriptor -------------------------------------------------------------
def test_descriptor_content(config):
    ctx = Context(config)
    descriptor_step.run(ctx)
    written = (config.out / "descriptor.mod").read_text(encoding="utf-8")
    assert not written.startswith("#")  # the launcher reads this file
    doc = parse(written, "descriptor.mod")
    assert doc["name"] == "Test Mod"
    assert doc["version"] == "1.2.3"
    assert doc["supported_version"] == "1.19.*"
    assert doc["tags"].list_values() == ["Total Conversion", "Map"]
    assert doc.get_all("replace_path") == ["history", "common/landed_titles"]


def test_descriptor_tags_block_is_multiline(config):
    ctx = Context(config)
    descriptor_step.run(ctx)
    text = (config.out / "descriptor.mod").read_text(encoding="utf-8")
    assert 'tags = {\n\t"Total Conversion"\n\t"Map"\n}' in text


# -- runner and CLI ---------------------------------------------------------
def test_run_steps_reports_each_step(config):
    ctx, runs = run_steps(config, ["clean", "descriptor"])
    assert [r.name for r in runs] == ["clean", "descriptor"]
    assert all(r.error is None for r in runs)
    assert runs[1].files == 2  # descriptor.mod + credit_portraits.txt shadow


def test_run_steps_reraises_and_records(config, monkeypatch):
    def boom(ctx):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(descriptor_step, "run", boom)
    with pytest.raises(RuntimeError):
        run_steps(config, ["descriptor"])


def test_write_evidence(config, tmp_path):
    ctx, runs = run_steps(config, ["descriptor"])
    path = write_evidence(config, ctx, runs, path=tmp_path / "last_run.md")
    text = path.read_text(encoding="utf-8")
    assert "# Last converter run" in text
    assert "| descriptor |" in text
    assert str(config.out) in text


def test_cli_dry_run(config, capsys):
    code = main(
        ["--config", str(config.path), "--dry-run", "--no-evidence"]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "dry run" in out
    assert "descriptor" in out
    assert not (config.out / "descriptor.mod").exists()


def test_cli_list_steps(capsys):
    assert main(["--list-steps"]) == 0
    assert "descriptor" in capsys.readouterr().out


def test_cli_unknown_step_exits_two(config, capsys):
    code = main(["--config", str(config.path), "--steps", "nope"])
    assert code == 2
    assert "unknown step" in capsys.readouterr().err


def test_cli_bad_config_exits_two(tmp_path, capsys):
    code = main(["--config", str(tmp_path / "nope.toml")])
    assert code == 2
    assert "not found" in capsys.readouterr().err


def test_cli_writes_the_run_log(config, tmp_path, monkeypatch):
    log = tmp_path / "evidence" / "last_run.md"
    monkeypatch.setattr("ck2ck3.runner.EVIDENCE", log)
    assert main(["--config", str(config.path), "--steps", "descriptor"]) == 0
    assert "descriptor" in log.read_text(encoding="utf-8")
