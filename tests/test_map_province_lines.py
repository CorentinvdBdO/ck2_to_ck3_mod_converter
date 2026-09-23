import numpy as np

from ck2ck3.map import provinces


def test_black_line_takes_nearest_province_and_white_stays_padding():
    keys = np.full((5, 7), 0x112233, dtype=np.int64)
    keys[:, 3] = 0x000000          # a drawn black line splitting two provinces
    keys[:, 6] = provinces.UNPAINTED_KEY
    ids = np.where(keys == 0x112233, 1, provinces.PADDING).astype(np.int32)
    ids[:, 4:6] = 2
    keys[:, 4:6] = 0x445566
    out = provinces.fill_undefined_lines(ids, keys)
    assert (out[:, 3] != provinces.PADDING).all()
    assert set(np.unique(out[:, 3])) <= {1, 2}
    assert (out[:, 6] == provinces.PADDING).all()


def test_no_lines_is_identity():
    keys = np.full((3, 3), 0x010203, dtype=np.int64)
    ids = np.ones((3, 3), dtype=np.int32)
    assert provinces.fill_undefined_lines(ids, keys) is ids
