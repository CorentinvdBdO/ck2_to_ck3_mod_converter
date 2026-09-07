"""Step ``loc``: CSV quirks in, valid CK3 ``.yml`` out."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from ck2ck3.config import Config
from ck2ck3.context import Context
from ck2ck3.steps import loc as loc_step
from ck2ck3.steps.loc import LocConfig, out_name

REPO = Path(__file__).resolve().parents[1]
FAERUN = REPO / "Faerun" / "Faerun"
sys.path.insert(0, str(REPO / "scripts"))

ENGLISH_ONLY = '\n[loc]\nlanguages = ["english"]\n'

HEADER = "#CODE;ENGLISH;FRENCH;GERMAN;;SPANISH;;;;;;;x\r\n"

#: One row per quirk found in Faerûn (`docs/formats_loc.md`).
QUIRKS = (
    "###ANSI;;;;;;;;;;;;x\r\n"
    + HEADER
    + "c_plain;Plain;Plaine;Ebene;;Llano;;;;;;;x\r\n"
    + 'd_quote;He said "no";;;;;;;;;;;x\r\n'
    + "d_semi;Half a line; and the rest;;;;;;;;;;x\r\n"
    + "d_break;One\\nTwo;;;;;;;;;;;x\r\n"
    + "d_colour;\xa7YGold\xa7! and \xa7Rred\xa7!;;;;;;;;;;;x\r\n"
    + "d_code;Hail [Root.GetTitledFirstName];;;;;;;;;;;x\r\n"
    + "d_var;Costs $VALUE|R$;;;;;;;;;;;x\r\n"
    + "d_icon;Pay \xa31\xa3;;;;;;;;;;;x\r\n"
    + "# a comment in the middle\r\n"
    + "d_stray;Support [From.GetTitledName;;;;;;;;;;;x\r\n"
    + "d_high;Bj\xf8rn's Tower;;;;;;;;;;;x\r\n"
    + "Bad Key;dropped;;;;;;;;;;;x\r\n"
    + ";;;;;;;;;;;;x\r\n"
    + "d_short;Short row\r\n"
    + "d_plain_dup;First;;;;;;;;;;;x\r\n"
)
LATER = HEADER + "d_plain_dup;Second wins;;;;;;;;;;;x\r\n"

CONFIG = """
[mod]
name = "Test"
prefix = "tst"
bookmark_date = "1357.1.1"

[paths]
ck2_game = "{root}/ck2"
ck2_mod = "{mod}"
ck3_game = "{root}/ck3"
out = "{out}"
{loc}
"""


@pytest.fixture
def ck2_mod(tmp_path) -> Path:
    folder = tmp_path / "src" / "localisation"
    folder.mkdir(parents=True)
    (folder / "00_quirks.csv").write_bytes(QUIRKS.encode("cp1252"))
    (folder / "99_later.csv").write_bytes(LATER.encode("cp1252"))
    custom = folder / "customizable_localisation"
    custom.mkdir()
    (custom / "00_custom.txt").write_text(
        "defined_text = {\n\tname = GetMyGreeting\n}\n", encoding="cp1252"
    )
    return tmp_path / "src"


def make_context(tmp_path, ck2_mod, loc_table: str = "") -> Context:
    out = tmp_path / "mod"
    out.mkdir(exist_ok=True)
    (out / "README.md").write_text("keep\n")
    path = tmp_path / "test.toml"
    path.write_text(
        CONFIG.format(root=tmp_path, mod=ck2_mod, out=out, loc=loc_table)
    )
    return Context(Config.load(path))


def read_yml(path: Path) -> dict[str, str]:
    raw = path.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf"), "CK3 localisation needs a BOM"
    entries = {}
    for line in raw.decode("utf-8-sig").split("\r\n"):
        if line.startswith(" "):
            key, _, value = line[1:].partition(":")
            quoted = value.partition(" ")[2]
            assert quoted.startswith('"') and quoted.endswith('"'), quoted
            entries[key] = quoted[1:-1]
    return entries


# -- filenames -------------------------------------------------------------
def test_output_name_is_prefixed_and_language_suffixed():
    assert out_name("fae", "0000_titles", "english") == "fae_0000_titles_l_english.yml"


def test_output_name_is_lower_case_and_safe():
    assert out_name("fae", "zzCogenital Trait!", "german") == "fae_zzcogenital_trait_l_german.yml"


# -- languages -------------------------------------------------------------
def test_english_plus_columns_over_min_share(tmp_path, ck2_mod):
    ctx = make_context(tmp_path, ck2_mod)
    plan = loc_step.build(ctx, LocConfig())
    # c_plain fills the other three columns: 1 of 14 rows, over the 5% default
    assert plan.languages == ["english", "french", "german", "spanish"]


def test_a_thin_column_gets_no_file(tmp_path, ck2_mod):
    ctx = make_context(tmp_path, ck2_mod)
    plan = loc_step.build(ctx, LocConfig(min_share=0.5))
    assert plan.languages == ["english"]


def test_languages_can_be_pinned(tmp_path, ck2_mod):
    ctx = make_context(tmp_path, ck2_mod)
    plan = loc_step.build(ctx, LocConfig(languages=("english", "french")))
    assert plan.languages == ["english", "french"]


def test_an_empty_cell_falls_back_to_english(tmp_path, ck2_mod):
    ctx = make_context(tmp_path, ck2_mod)
    plan = loc_step.build(ctx, LocConfig(languages=("french",)))
    entries = dict(plan.per_language["french"])["00_quirks"]
    assert entries["c_plain"] == "Plaine"
    assert entries["d_high"] == "Bj\xf8rn's Tower"


# -- quirks ----------------------------------------------------------------
@pytest.fixture
def english(tmp_path, ck2_mod) -> dict[str, str]:
    ctx = make_context(tmp_path, ck2_mod, loc_table=ENGLISH_ONLY)
    result = loc_step.run(ctx)
    assert result.counts["files"] == 2
    path = ctx.out_path("localization", "english", "tst_00_quirks_l_english.yml")
    return read_yml(path)


def test_a_quote_is_escaped(english):
    assert english["d_quote"] == 'He said \\"no\\"'


def test_a_semicolon_truncates_the_text_like_ck2_does(english):
    assert english["d_semi"] == "Half a line"


def test_a_newline_escape_is_kept(english):
    assert english["d_break"] == "One\\nTwo"


def test_colours_and_codes_are_converted(english):
    assert english["d_colour"] == "#M Gold#! and #N red#!"
    assert english["d_code"] == "Hail [ROOT.Char.GetTitledFirstName]"


def test_a_variable_survives(english):
    assert english["d_var"] == "Costs $VALUE|R$"


def test_an_icon_is_marked(english):
    assert english["d_icon"] == "Pay <!CK2:icon_1!>"


def test_an_unbalanced_bracket_is_removed(english):
    assert english["d_stray"] == "Support From.GetTitledName"


def test_a_short_row_still_gives_its_english(english):
    assert english["d_short"] == "Short row"


def test_a_key_ck3_cannot_reference_is_skipped(english):
    assert "Bad Key" not in english


def test_a_comment_line_is_not_a_key(english):
    assert not any(k.startswith("#") for k in english)


# -- dedupe, renames, collisions ------------------------------------------
def test_the_last_file_wins_and_the_step_says_where(tmp_path, ck2_mod):
    ctx = make_context(tmp_path, ck2_mod, loc_table=ENGLISH_ONLY)
    result = loc_step.run(ctx)
    first = read_yml(ctx.out_path("localization", "english", "tst_00_quirks_l_english.yml"))
    later = read_yml(ctx.out_path("localization", "english", "tst_99_later_l_english.yml"))
    assert "d_plain_dup" not in first
    assert later["d_plain_dup"] == "Second wins"
    assert result.counts["duplicate_keys"] == 1
    assert any("d_plain_dup" in w and "99_later.csv wins" in w for w in result.warnings)


def test_the_key_map_is_applied_last(tmp_path, ck2_mod):
    table = tmp_path / "keys.csv"
    table.write_text("ck2_key,ck3_key\nc_plain,fae_c_plain\n")
    ctx = make_context(tmp_path, ck2_mod)
    plan = loc_step.build(
        ctx, LocConfig(languages=("english",), key_map=table)
    )
    entries = dict(plan.per_language["english"])["00_quirks"]
    assert "fae_c_plain" in entries and "c_plain" not in entries
    assert plan.renamed == 1


def test_vanilla_collisions_are_kept_unless_asked(tmp_path, ck2_mod):
    keys = tmp_path / "vanilla.txt"
    keys.write_text("# header\nc_plain\n")
    ctx = make_context(tmp_path, ck2_mod)
    kept = loc_step.build(ctx, LocConfig(languages=("english",), vanilla_keys=keys))
    assert "c_plain" in dict(kept.per_language["english"])["00_quirks"]
    skipped = loc_step.build(
        ctx,
        LocConfig(
            languages=("english",), vanilla_keys=keys, skip_vanilla_collisions=True
        ),
    )
    assert "c_plain" not in dict(skipped.per_language["english"])["00_quirks"]
    assert skipped.vanilla_skipped == 1


def test_a_missing_vanilla_key_file_warns_instead_of_failing(tmp_path, ck2_mod):
    ctx = make_context(tmp_path, ck2_mod)
    loc_step.build(
        ctx,
        LocConfig(
            languages=("english",),
            vanilla_keys=tmp_path / "nope.txt",
            skip_vanilla_collisions=True,
        ),
    )
    assert any("skip_vanilla_collisions" in w for w in ctx.warnings)


# -- contract --------------------------------------------------------------
def test_the_step_owns_only_localization():
    assert loc_step.OUTPUTS == ("localization",)


def test_dry_run_writes_nothing(tmp_path, ck2_mod):
    ctx = make_context(tmp_path, ck2_mod, loc_table=ENGLISH_ONLY)
    ctx.dry_run = True
    result = loc_step.run(ctx)
    assert result.counts["files"] == 2
    assert not ctx.out_path("localization").exists()


def test_a_bad_unknown_codes_value_is_an_error(tmp_path, ck2_mod):
    ctx = make_context(tmp_path, ck2_mod, loc_table='\n[loc]\nunknown_codes = "wat"\n')
    with pytest.raises(ValueError):
        loc_step.run(ctx)


def test_the_loc_table_is_read_from_the_config(tmp_path, ck2_mod):
    ctx = make_context(
        tmp_path,
        ck2_mod,
        loc_table='\n[loc]\nlanguages = ["english"]\nmin_share = 0.5\n',
    )
    config = LocConfig.from_raw(ctx.config.raw["loc"])
    assert config.languages == ("english",)
    assert config.min_share == 0.5


# -- the real mod ----------------------------------------------------------
@pytest.mark.slow
@pytest.mark.skipif(not FAERUN.is_dir(), reason="Faerun/ not cloned")
def test_the_whole_faerun_localisation_converts_cleanly(tmp_path):
    from check_ck3_loc import check_file

    ctx = make_context(tmp_path, FAERUN)
    result = loc_step.run(ctx)
    counts = result.counts
    assert counts["files"] == 480, "120 csv × 4 languages"
    assert counts["keys_english"] > 100_000
    for language in ("french", "german", "spanish"):
        assert counts[f"keys_{language}"] == counts["keys_english"]
    coverage = counts["codes_converted"] / counts["codes"]
    assert coverage > 0.93, f"text-code coverage dropped to {coverage:.1%}"

    problems: list[str] = []
    keys = 0
    for path in sorted(ctx.out_path("localization").rglob("*.yml")):
        found, count, language = check_file(path)
        problems.extend(found)
        keys += count
    assert problems == [], problems[:5]
    assert keys == sum(
        counts[f"keys_{language}"]
        for language in ("english", "french", "german", "spanish")
    )
