"""Step `tc_template` and the shadow rules it shares with the scan scripts."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from ck2ck3 import tcshadow
from ck2ck3.steps import tc_template

IDS = tcshadow.VanillaIds(titles=frozenset({"k_france", "c_paris", "h_india"}))


# -- the reference rule ---------------------------------------------------


def test_bare_and_scoped_title_tags_both_count() -> None:
    counts = tcshadow.count_refs("scope = title:k_france\nfoo = c_paris\n", IDS)
    assert counts["title_scope"] == 1
    assert counts["title_bare"] == 1
    assert counts["total"] == 2


def test_a_token_that_only_looks_like_a_title_does_not_count() -> None:
    # `k_from_dynasty` has the shape but is not in landed_titles.
    assert not tcshadow.references_map_objects("x = k_from_dynasty\n", IDS)


def test_h_tier_titles_count() -> None:
    # `h_` is a real above-empire tier in 1.19; a five-letter tier regex misses it.
    assert tcshadow.references_map_objects("this = title:h_india\n", IDS)


def test_a_commented_out_reference_is_not_live() -> None:
    assert not tcshadow.references_map_objects("# this = title:k_france\n", IDS)


def test_province_character_and_dynasty_links_count() -> None:
    text = "a = province:113 b = character:1234 c = dynasty:70"
    assert tcshadow.count_refs(text, IDS)["total"] == 3


# -- the two neutralisation shapes ----------------------------------------


def test_shadow_text_is_comment_only(tmp_path: Path) -> None:
    body = tcshadow.shadow_text(tmp_path / "00_thing.txt")
    assert "00_thing.txt" in body
    assert all(line.startswith("#") for line in body.splitlines() if line)


def test_neutralise_keeps_keys_and_drops_bodies(tmp_path: Path) -> None:
    source = tmp_path / "00_effects.txt"
    source.write_text(
        "@const = 7\n"
        "some_effect = {\n\ttitle:k_france = { destroy_title = yes }\n}\n"
        "# commented_effect = {}\n"
        "other_effect = {\n\tx = c_paris\n}\n",
        encoding="utf-8",
    )
    out = tcshadow.neutralise_text(source, "common/scripted_effects", IDS)
    assert "some_effect = {}" in out
    assert "other_effect = {}" in out
    assert "@const = 7" in out
    assert "commented_effect" not in out
    assert "k_france" not in out and "c_paris" not in out


def test_a_neutralised_trigger_says_always_no(tmp_path: Path) -> None:
    # An empty trigger block evaluates TRUE in CK3, which would silently unlock
    # whatever the trigger used to gate.
    source = tmp_path / "00_triggers.txt"
    source.write_text("gate_trigger = {\n\tthis = title:k_france\n}\n", encoding="utf-8")
    out = tcshadow.neutralise_text(source, "common/scripted_triggers", IDS)
    assert "gate_trigger = { always = no }" in out


def test_a_neutralised_script_value_is_a_bare_number(tmp_path: Path) -> None:
    source = tmp_path / "00_values.txt"
    source.write_text("titles_held_in_k_maghreb = {\n\tvalue = 3\n}\n", encoding="utf-8")
    out = tcshadow.neutralise_text(source, "common/script_values", IDS)
    assert "titles_held_in_k_maghreb = 0" in out


# -- the decision table ---------------------------------------------------


def test_the_shipped_table_loads_and_every_row_is_justified() -> None:
    rows = tc_template.load_table()
    assert rows
    assert all(row["note"].strip() for row in rows)
    assert {row["mode"] for row in rows} <= tc_template.VALID_MODES


def test_every_table_path_still_exists_in_the_installed_game() -> None:
    game = Path(
        "/home/cvdbdo/.local/share/Steam/steamapps/common/Crusader Kings III/game"
    )
    if not game.is_dir():
        pytest.skip("CK3 1.19 not installed here")
    missing = []
    for row in tc_template.load_table():
        folder, _ = tc_template._split(row["path"])
        if not (game / folder).is_dir():
            missing.append(row["path"])
    assert missing == []


def test_outputs_come_from_the_table_and_are_folders() -> None:
    assert tc_template.OUTPUTS
    assert all("*" not in folder and not folder.endswith(".txt") for folder in tc_template.OUTPUTS)
    assert len(set(tc_template.OUTPUTS)) == len(tc_template.OUTPUTS)


def test_a_glob_row_splits_into_folder_and_pattern() -> None:
    assert tc_template._split("common/script_values/00_x.txt") == (
        "common/script_values",
        "00_x.txt",
    )
    assert tc_template._split("common/decisions") == ("common/decisions", "")
    assert tc_template._split("common/scripted_effects/10_*.txt") == (
        "common/scripted_effects",
        "10_*.txt",
    )


def _write_table(path: Path, rows: list[tuple[str, str, str]]) -> Path:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["path", "mode", "note"])
        writer.writerows(rows)
    return path


def test_an_unknown_mode_is_refused(tmp_path: Path) -> None:
    table = _write_table(tmp_path / "t.csv", [("common/decisions", "delete", "why")])
    with pytest.raises(tc_template.TableError, match="unknown mode"):
        tc_template.load_table(table)


def test_a_row_without_a_note_is_refused(tmp_path: Path) -> None:
    table = _write_table(tmp_path / "t.csv", [("common/decisions", "shadow", "")])
    with pytest.raises(tc_template.TableError, match="no note"):
        tc_template.load_table(table)


def test_a_duplicate_path_is_refused(tmp_path: Path) -> None:
    table = _write_table(
        tmp_path / "t.csv",
        [("common/decisions", "shadow", "a"), ("common/decisions", "keep", "b")],
    )
    with pytest.raises(tc_template.TableError, match="twice"):
        tc_template.load_table(table)


# -- the step -------------------------------------------------------------


def _fake_game(root: Path) -> Path:
    game = root / "game"
    (game / "common" / "landed_titles").mkdir(parents=True)
    (game / "common" / "landed_titles" / "00.txt").write_text(
        "k_france = {\n\tc_paris = {\n\t\tb_paris = { province = 1 }\n\t}\n}\n",
        encoding="utf-8",
    )
    (game / "common" / "decisions").mkdir(parents=True)
    (game / "common" / "decisions" / "00_d.txt").write_text(
        "found_france = {\n\tis_shown = { title:k_france = { exists = yes } }\n}\n",
        encoding="utf-8",
    )
    (game / "common" / "laws").mkdir(parents=True)
    (game / "common" / "laws" / "00_clean.txt").write_text(
        "some_law = { flag = yes }\n", encoding="utf-8"
    )
    (game / "common" / "laws" / "01_dirty.txt").write_text(
        "other_law = { x = c_paris }\n", encoding="utf-8"
    )
    return game


def _run(tmp_path: Path, rows: list[tuple[str, str, str]], monkeypatch):
    from ck2ck3.config import Config
    from ck2ck3.context import Context

    game = _fake_game(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    table = _write_table(tmp_path / "table.csv", rows)
    monkeypatch.setattr(tc_template, "TABLE", table)
    config = Config(
        path=tmp_path / "cfg.toml",
        name="t",
        prefix="fae",
        version="0",
        supported_version="1.19.*",
        tags=(),
        replace_paths=("tests",),
        bookmark_date="1357.1.1",
        ck2_game=tmp_path,
        ck2_mod=tmp_path,
        ck3_game=game,
        out=out,
    )
    result = tc_template.run(Context(config))
    return out, result


def test_shadow_writes_one_empty_file_per_vanilla_file(tmp_path, monkeypatch) -> None:
    out, result = _run(
        tmp_path, [("common/decisions", "shadow", "content")], monkeypatch
    )
    written = out / "common" / "decisions" / "00_d.txt"
    assert written.is_file()
    assert "k_france" not in written.read_text(encoding="utf-8-sig")
    assert result.counts["shadows"] == 1


def test_shadow_dirty_leaves_the_clean_files_alone(tmp_path, monkeypatch) -> None:
    out, result = _run(tmp_path, [("common/laws", "shadow_dirty", "mixed")], monkeypatch)
    assert (out / "common" / "laws" / "01_dirty.txt").is_file()
    assert not (out / "common" / "laws" / "00_clean.txt").exists()
    assert result.counts["shadows"] == 1


def test_a_shadow_carries_the_utf8_bom(tmp_path, monkeypatch) -> None:
    # ck3-tiger wants one on every script file under common/, history/ and
    # events/ (CLAUDE.md invariant).
    out, _ = _run(tmp_path, [("common/decisions", "shadow", "content")], monkeypatch)
    raw = (out / "common" / "decisions" / "00_d.txt").read_bytes()
    assert raw[:3] == b"\xef\xbb\xbf"


def test_replace_path_mode_warns_when_the_config_does_not_list_it(
    tmp_path, monkeypatch
) -> None:
    _, result = _run(
        tmp_path, [("common/decisions", "replace_path", "config owns it")], monkeypatch
    )
    assert result.counts["replace_paths"] == 1
    assert any("does not" in w for w in result.warnings)


def test_a_row_that_selects_nothing_warns_instead_of_passing(
    tmp_path, monkeypatch
) -> None:
    _, result = _run(
        tmp_path, [("common/gone_in_this_patch", "shadow", "stale")], monkeypatch
    )
    assert any("selected no vanilla file" in w for w in result.warnings)
