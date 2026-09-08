"""descriptor step shadows vanilla credit_portraits.txt (it names vanilla characters)."""
from pathlib import Path

from ck2ck3.steps import descriptor


def test_descriptor_step_owns_credit_portraits():
    assert "credit_portraits.txt" in descriptor.OUTPUTS
    src = Path(descriptor.__file__).read_text()
    assert '"credit_portraits.txt"' in src and "Intentionally empty" in src
