"""A CK3 name-list entry is a loc key, and the parser is fussy about tokens."""

from __future__ import annotations

from ck2ck3.nametokens import name_token, tokenise


def test_whitespace_becomes_an_underscore():
    """Vanilla spells a two-word name `Asir_Rera` (00_ainu.txt:149); the
    converter used to emit `"Sergeant Reckless"` quoted, which the name
    equivalency table could not look up."""
    assert name_token("Sergeant Reckless") == "Sergeant_Reckless"
    assert name_token('  "Clever Hans" ') == "Clever_Hans"


def test_a_leading_digit_is_prefixed():
    """The real bug: Faerun's `modron` names are serial numbers, and a bare
    token starting with a digit broke the CK3 parser for the whole rest of
    `fae_monsters.txt` — 14 name lists lost (`verified` 2026-09-08)."""
    assert name_token("2BD71SF2") == "name_2BD71SF2"
    assert name_token("9TC5CKZC") == "name_9TC5CKZC"


def test_letters_hyphens_and_apostrophes_pass_through():
    assert name_token("Qiu-te") == "Qiu-te"
    assert name_token("O'Brien") == "O'Brien"  # 571 of ours, no complaint


def test_a_key_must_be_ascii():
    """`localization_reader.cpp:445: Invalid character in key name 'Bj\xf6rn'`,
    251 of them; 0 of vanilla's 55 948 name keys hold a non-ASCII byte, and its
    own list spells Bj\xf6rn `BjO_rn` (`verified` 2026-09-08)."""
    assert name_token("Bj\xf6rn") == "Bjorn"
    assert name_token("\xc1ki") == "Aki"
    assert name_token("Da\xf1-Xayaa") == "Dan-Xayaa"
    assert name_token("\xc5ke") == "Ake"
    assert name_token("\xd8rjan") == "Orjan"  # no NFKD decomposition, needs the table
    assert name_token("Ba\xf1a\u0148") == "Banan"
    for raw in ("Bj\xf6rn", "\xc5ke", "Bugelvi\u0161", "Ch\xf6mch\xfc\xfcne"):
        assert name_token(raw).isascii()


def test_nothing_usable_is_dropped():
    assert name_token("") is None
    assert name_token("   ") is None
    assert name_token("---") is None


def test_tokenise_dedupes_and_records_the_literal():
    loc: dict[str, str] = {}
    tokens = tokenise(["Beauty", "Beauty", "Clever Hans", "", "2BD71SF2"], loc)
    assert tokens == ["Beauty", "Clever_Hans", "name_2BD71SF2"]
    assert loc == {
        "Beauty": "Beauty",
        "Clever_Hans": "Clever Hans",
        "name_2BD71SF2": "2BD71SF2",
    }


def test_two_literals_that_fold_together_get_distinct_tokens():
    """Vanilla's own idiom: a trailing underscore separates `Aki` from `\xc1ki`."""
    loc: dict[str, str] = {}
    first = tokenise(["Aki", "\xc1ki"], loc)
    assert first == ["Aki", "Aki_"]
    assert loc == {"Aki": "Aki", "Aki_": "\xc1ki"}
    # and the mapping is stable across name lists sharing the table
    assert tokenise(["\xc1ki", "Aki"], loc) == ["Aki_", "Aki"]
    assert len(loc) == 2


def test_every_token_is_parser_safe():
    """The property that matters: whatever comes out starts with a letter or an
    underscore and contains no whitespace."""
    for raw in ("2BD71SF2", "Sergeant Reckless", " 42 ", "'Tis", ".dot", "-x-"):
        token = name_token(raw)
        assert token is not None
        assert not any(c.isspace() for c in token)
        assert token[0].isalpha() or token[0] == "_"
