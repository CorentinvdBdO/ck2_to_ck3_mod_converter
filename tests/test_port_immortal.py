"""CK2 immortal_age = N -> add_trait = immortal + set_immortal_age = N in one effect block."""
from pathlib import Path

from ck2ck3.port import characters


def test_set_immortal_age_is_preceded_by_the_immortal_trait():
    src = Path(characters.__file__).read_text()
    i = src.index('key="add_trait"')
    assert 'value="immortal"' in src[i : i + 200]
    assert src.index('emitted.key == "set_immortal_age"') < i
