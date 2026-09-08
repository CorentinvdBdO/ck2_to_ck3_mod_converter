"""history_titles writes one province_mapping entry: the loader crashes on an empty table."""
from ck2ck3.steps.history_titles import OUTPUTS, _province_mapping_entry
from ck2ck3.titles.place import Placement, PlacementPlan


def test_outputs_include_province_mapping():
    assert "history/province_mapping" in OUTPUTS


def test_entry_is_two_placed_baronies_of_one_county():
    plan = PlacementPlan(mode="test")
    plan.by_barony["b_a"] = Placement("b_a", "c_one", 10, "castle", None, "placed", "")
    plan.by_barony["b_b"] = Placement("b_b", "c_one", None, None, None, "demoted", "")
    plan.by_barony["b_c"] = Placement("b_c", "c_two", 20, "castle", None, "placed", "")
    plan.by_barony["b_d"] = Placement("b_d", "c_two", 21, "city", None, "placed", "")
    plan.by_county["c_one"] = ["b_a", "b_b"]
    plan.by_county["c_two"] = ["b_c", "b_d"]
    assert _province_mapping_entry(plan) == (21, 20, "c_two")


def test_no_pair_returns_none():
    plan = PlacementPlan(mode="test")
    plan.by_barony["b_a"] = Placement("b_a", "c_one", 10, "castle", None, "placed", "")
    plan.by_county["c_one"] = ["b_a"]
    assert _province_mapping_entry(plan) is None
