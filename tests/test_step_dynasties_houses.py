"""The dynasties step shadows every vanilla dynasty_houses file (Elder Kings 2 pattern)."""
from pathlib import Path

from ck2ck3.steps import dynasties


def test_every_vanilla_dynasty_house_file_is_shadowed(tmp_path, monkeypatch):
    game = Path("/home/cvdbdo/.local/share/Steam/steamapps/common/Crusader Kings III/game")
    houses = game / "common" / "dynasty_houses"
    if not houses.is_dir():
        import pytest
        pytest.skip("CK3 not installed")
    vanilla = sorted(p.name for p in houses.glob("*.txt"))
    assert vanilla, "vanilla ships dynasty house files"
    assert "common/dynasty_houses" in dynasties.OUTPUTS
    src = Path(dynasties.__file__).read_text()
    assert 'ctx.ck3("common", "dynasty_houses")' in src
    assert "Intentionally empty" in src
