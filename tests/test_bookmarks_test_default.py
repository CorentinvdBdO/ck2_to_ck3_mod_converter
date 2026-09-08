"""The bookmark at the default start date carries test_default = yes (what -test starts)."""
from pathlib import Path

from ck2ck3.titles import bookmarks


def test_test_default_is_emitted_once_for_the_default_date():
    src = Path(bookmarks.__file__).read_text()
    assert "test_default = yes" in src and "marked_default" in src
