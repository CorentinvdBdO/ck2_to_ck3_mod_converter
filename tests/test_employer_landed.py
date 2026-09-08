"""employer = X survives only while X holds a title (CK3 crashes on landless employers)."""
from ck2ck3.titles.history import landed_intervals, is_landed_at


def test_landed_intervals_and_lookup():
    spans = {
        "c_a": [((1300, 1, 1), "10"), ((1350, 1, 1), "11"), ((1360, 1, 1), None)],
        "d_b": [((1340, 1, 1), "10")],
    }
    landed = landed_intervals(spans)
    assert is_landed_at(landed, "10", (1320, 1, 1))
    assert is_landed_at(landed, "10", (1355, 1, 1))  # via d_b, open-ended
    assert is_landed_at(landed, "11", (1355, 1, 1))
    assert not is_landed_at(landed, "11", (1365, 1, 1))  # holder = 0 ends it
    assert not is_landed_at(landed, "12", (1355, 1, 1))
