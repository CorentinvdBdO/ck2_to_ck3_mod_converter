"""Tests for barony placement: capacity, seed priority, demotion, evidence."""

from __future__ import annotations

import numpy as np
import pytest

from ck2ck3.map import baronies, ck2titles, holdings
from ck2ck3.map.config import BaronyConfig, ScaleConfig, plan_canvas

TITLES = """
e_x = {
\tk_x = {
\t\td_x = {
\t\t\tc_alpha = {
\t\t\t\tb_alpha = {}
\t\t\t\tb_beta = {}
\t\t\t\tb_gamma = {}
\t\t\t}
\t\t\tc_omega = {
\t\t\t\tb_omega = {}
\t\t\t}
\t\t}
\t}
}
"""


@pytest.fixture
def tree(tmp_path):
    p = tmp_path / "titles.txt"
    p.write_text(TITLES, encoding="cp1252")
    return ck2titles.read([p])


def _canvas(w=64, h=32):
    """A canvas with factor 1 and no offset, so pixel maths is readable."""
    scale = ScaleConfig(
        vanilla_km_per_px=1.0,
        source_km_per_px=1.0,
        sea_margin_px=0,
        canvas_multiple=1,
    )
    return plan_canvas(w, h, scale)


def _selection(pid, county, baronies_map, later=frozenset()):
    return holdings.BaronySelection(
        province_id=pid,
        county=county,
        baronies=dict(baronies_map),
        built={k: (1000, 1, 1) for k in baronies_map},
        later=frozenset(later),
    )


def _plan(raster, selections, tree, cfg=None, **kw):
    canvas = _canvas(raster.shape[1], raster.shape[0])
    return baronies.plan(
        raster_ids=raster,
        canvas=canvas,
        selections=selections,
        tree=tree,
        cfg=cfg or BaronyConfig(min_barony_pixels=1, relax_passes=0),
        **kw,
    )


def _two_counties():
    """Left half is CK2 province 1 (c_alpha), right half province 2 (c_omega).

    64x64 so county 1 is 2048 px: big enough that the capacity rule and the
    growth balance can be tested apart from each other.
    """
    raster = np.zeros((64, 64), dtype=np.int32)
    raster[:, :32] = 1
    raster[:, 32:] = 2
    sels = {
        1: _selection(
            1,
            "c_alpha",
            {
                "b_alpha": "castle_holding",
                "b_beta": "city_holding",
                "b_gamma": "church_holding",
            },
        ),
        2: _selection(2, "c_omega", {"b_omega": "tribal_holding"}),
    }
    return raster, sels


def test_every_barony_gets_pixels_and_the_county_is_covered(tree):
    raster, sels = _two_counties()
    p = _plan(raster, sels, tree)
    assert len(p.placed) == 4
    assert not p.demoted
    assert sum(b.pixels for b in p.placed) == int((raster > 0).sum())
    assert {b.key for b in p.placed} == {"b_alpha", "b_beta", "b_gamma", "b_omega"}


def test_placed_order_follows_the_landed_titles_hierarchy(tree):
    raster, sels = _two_counties()
    p = _plan(raster, sels, tree)
    assert [b.key for b in p.placed] == ["b_alpha", "b_beta", "b_gamma", "b_omega"]


def test_a_county_never_loses_its_last_barony(tree):
    """Done-criterion: every county keeps at least one CK3 province."""
    raster, sels = _two_counties()
    cfg = BaronyConfig(min_barony_pixels=100_000, relax_passes=0)
    p = _plan(raster, sels, tree, cfg=cfg)
    assert {b.ck2_province for b in p.placed} == {1, 2}
    assert len([b for b in p.placed if b.ck2_province == 1]) == 1
    assert [b.key for b in p.placed if b.ck2_province == 1] == ["b_alpha"]


def test_min_pixels_demotes_the_lowest_priority_holdings_first(tree):
    raster, sels = _two_counties()
    # county 1 is 2048 px: room for two baronies of 700, not three, so the
    # capacity pass drops the last one declared in landed_titles
    cfg = BaronyConfig(min_barony_pixels=700)
    p = _plan(raster, sels, tree, cfg=cfg)
    kept = [b.key for b in p.placed if b.ck2_province == 1]
    assert kept == ["b_alpha", "b_beta"]
    assert [b.key for b in p.demoted] == ["b_gamma"]
    assert p.demoted[0].status == "demoted"
    assert p.demoted[0].pixels == 0
    assert min(b.pixels for b in p.placed if b.ck2_province == 1) >= 700


def test_relaxation_saves_a_barony_an_unbalanced_split_would_demote(tree):
    """Why ``relax_passes`` exists: farthest-point seeds sit in corners.

    County 1 has room for two 700 px baronies. Without relaxation the sampled
    seed lands in a corner, the split comes out lopsided, and the straggler
    pass demotes a holding that fits perfectly well.

    Relaxation is an improvement, not a guarantee: Lloyd converges to *a*
    centroidal partition, not to an equal-area one, so a small enough county
    can still end up lopsided. That is what the demotion pass is for.
    """
    raster, sels = _two_counties()
    lopsided = _plan(
        raster, sels, tree, cfg=BaronyConfig(min_barony_pixels=700, relax_passes=0)
    )
    relaxed = _plan(raster, sels, tree, cfg=BaronyConfig(min_barony_pixels=700))
    assert len([b for b in lopsided.placed if b.ck2_province == 1]) == 1
    assert len([b for b in relaxed.placed if b.ck2_province == 1]) == 2


def test_relaxation_never_moves_a_pinned_seed(tree):
    raster, sels = _two_counties()
    p = _plan(
        raster,
        sels,
        tree,
        cfg=BaronyConfig(min_barony_pixels=1, relax_passes=3),
        seed_overrides={"b_alpha": baronies.SeedOverride("b_alpha", x=1, y=1)},
    )
    alpha = next(b for b in p.placed if b.key == "b_alpha")
    assert (alpha.seed_y, alpha.seed_x) == (1, 1)


def test_demoted_baronies_are_reported_by_county(tree):
    raster, sels = _two_counties()
    p = _plan(raster, sels, tree, cfg=BaronyConfig(min_barony_pixels=700))
    assert p.counties_with_demotions() == ["c_alpha"]


# ------------------------------------------------------------ seed priority
def test_seed_priority_override_beats_everything(tree):
    raster, sels = _two_counties()
    p = _plan(
        raster,
        sels,
        tree,
        seed_overrides={"b_alpha": baronies.SeedOverride("b_alpha", x=3, y=4)},
        gazetteer=[baronies.GazetteerEntry("Alpha", x=20, y=20)],
        loc_names={"b_alpha": "Alpha"},
        positions={1: [(10.0, 10.0)] * 7},
        source_height=64,
    )
    alpha = next(b for b in p.placed if b.key == "b_alpha")
    assert (alpha.seed_y, alpha.seed_x) == (4, 3)
    assert alpha.seed_source == "override"


def test_seed_priority_gazetteer_beats_the_capital_position(tree):
    raster, sels = _two_counties()
    p = _plan(
        raster,
        sels,
        tree,
        gazetteer=[baronies.GazetteerEntry("Alpha!", x=20, y=21)],
        loc_names={"b_alpha": "alpha"},
        positions={1: [(10.0, 10.0)] * 7},
        source_height=64,
    )
    alpha = next(b for b in p.placed if b.key == "b_alpha")
    assert (alpha.seed_y, alpha.seed_x) == (21, 20)
    assert alpha.seed_source == "gazetteer"


def test_seed_priority_capital_position_beats_sampling(tree):
    raster, sels = _two_counties()
    p = _plan(
        raster, sels, tree, positions={1: [(10.0, 12.0)] * 7}, source_height=64
    )
    alpha = next(b for b in p.placed if b.key == "b_alpha")
    # positions.txt y is measured from the bottom: 64 - 12 = 52
    assert (alpha.seed_y, alpha.seed_x) == (52, 10)
    assert alpha.seed_source == "capital_position"


def test_only_the_capital_takes_the_positions_txt_coordinate(tree):
    raster, sels = _two_counties()
    p = _plan(
        raster, sels, tree, positions={1: [(10.0, 12.0)] * 7}, source_height=64
    )
    others = [b for b in p.placed if b.ck2_province == 1 and not b.is_capital]
    assert {b.seed_source for b in others} == {"sampled"}


def test_a_seed_outside_its_county_is_snapped_within_the_radius(tree):
    raster, sels = _two_counties()
    # x=40 is in county 2; county 1 ends at x=31, so the snap is 9 px
    p = _plan(
        raster,
        sels,
        tree,
        cfg=BaronyConfig(min_barony_pixels=1, relax_passes=0, snap_radius_px=16),
        seed_overrides={"b_alpha": baronies.SeedOverride("b_alpha", x=40, y=5)},
    )
    alpha = next(b for b in p.placed if b.key == "b_alpha")
    assert alpha.seed_source == "override"
    assert (alpha.seed_y, alpha.seed_x) == (5, 31)


def test_a_seed_too_far_out_is_ignored_and_the_next_source_wins(tree):
    raster, sels = _two_counties()
    p = _plan(
        raster,
        sels,
        tree,
        cfg=BaronyConfig(min_barony_pixels=1, relax_passes=0, snap_radius_px=2),
        seed_overrides={"b_alpha": baronies.SeedOverride("b_alpha", x=60, y=5)},
        positions={1: [(7.0, 12.0)] * 7},
        source_height=64,
    )
    alpha = next(b for b in p.placed if b.key == "b_alpha")
    assert alpha.seed_source == "capital_position"


def test_holding_bias_pulls_a_city_seed_toward_water(tree):
    raster, sels = _two_counties()
    water = np.zeros(raster.shape, dtype=bool)
    water[0, :32] = True  # the northern shore of county 1
    p = _plan(
        raster,
        sels,
        tree,
        cfg=BaronyConfig(min_barony_pixels=1, relax_passes=0, bias_gain=5.0),
        water_bias=water,
    )
    beta = next(b for b in p.placed if b.key == "b_beta")  # the city
    assert beta.holding == "city_holding"
    assert beta.seed_y == 0


def test_pixels_no_seed_can_reach_are_attached_not_lost(tree):
    """A detached piece of a county must still end up in one of its baronies."""
    raster = np.zeros((16, 16), dtype=np.int32)
    raster[0:4, 0:4] = 1
    raster[12:16, 12:16] = 1  # detached island of the same county
    sels = {1: _selection(1, "c_omega", {"b_omega": "castle_holding"})}
    p = _plan(raster, sels, tree)
    assert p.orphan_pixels == 16
    assert p.placed[0].pixels == 32
    assert (p.labels[(raster == 1)] == 1).all()


# --------------------------------------------------------------- overrides
def test_the_shipped_seed_template_parses_to_nothing(tmp_path):
    p = tmp_path / "barony_seeds.csv"
    p.write_text(baronies.SEED_TEMPLATE, encoding="utf-8")
    assert baronies.read_seed_overrides(p) == {}


def test_the_shipped_gazetteer_template_parses_to_nothing(tmp_path):
    p = tmp_path / "gazetteer.csv"
    p.write_text(baronies.GAZETTEER_TEMPLATE, encoding="utf-8")
    assert baronies.read_gazetteer(p) == []


def test_a_seed_row_without_the_b_prefix_still_matches(tmp_path):
    p = tmp_path / "s.csv"
    p.write_text("barony_id,x,y,note\ncastle_waterdeep,10,20,seat\n", encoding="utf-8")
    got = baronies.read_seed_overrides(p)
    assert got["b_castle_waterdeep"] == baronies.SeedOverride(
        "b_castle_waterdeep", 10, 20, "seat"
    )


def test_a_missing_override_file_is_not_an_error(tmp_path):
    assert baronies.read_seed_overrides(tmp_path / "nope.csv") == {}
    assert baronies.read_gazetteer(tmp_path / "nope.csv") == []


def test_gazetteer_ck2_coordinates_go_through_the_map_transform(tree):
    raster, sels = _two_counties()
    canvas = _canvas(64, 64)
    assert canvas.to_target(6, 7) == (6, 7)  # factor 1, no margin
    p = _plan(
        raster,
        sels,
        tree,
        gazetteer=[baronies.GazetteerEntry("Alpha", x=6, y=7, space="ck2")],
        loc_names={"b_alpha": "Alpha"},
    )
    alpha = next(b for b in p.placed if b.key == "b_alpha")
    assert (alpha.seed_y, alpha.seed_x) == (7, 6)


def test_place_name_normalisation_folds_case_accents_and_punctuation():
    assert baronies.normalise_place("Wyrm's Crossing") == "wyrmscrossing"
    assert baronies.normalise_place("Amphaïl") == "amphail"
    assert baronies.normalise_place("  al-Sartan ") == "alsartan"


# ---------------------------------------------------------------- evidence
def test_barony_set_csv_carries_every_holding_and_its_status(tree):
    raster, sels = _two_counties()
    p = _plan(raster, sels, tree, cfg=BaronyConfig(min_barony_pixels=700))
    csv = baronies.render_barony_set_csv(p, province_names={1: "Alpha", 2: "Omega"})
    lines = csv.splitlines()
    assert lines[0].startswith("county,barony,holding,built_date,seed_source,pixels,status")
    assert len(lines) == 5  # header + 4 holdings
    assert any(line.startswith("c_alpha,b_gamma,church_holding") for line in lines)
    assert any(",demoted," in line for line in lines)


def test_an_undated_holding_reads_as_initial_not_0_0_0(tree):
    raster, sels = _two_counties()
    sels[2].built["b_omega"] = holdings.EPOCH
    p = _plan(raster, sels, tree)
    csv = baronies.render_barony_set_csv(p)
    assert "b_omega,tribal_holding,initial," in csv
    assert "0.0.0" not in csv


def test_planning_is_deterministic(tree):
    raster, sels = _two_counties()
    a = _plan(raster.copy(), sels, tree)
    b = _plan(raster.copy(), sels, tree)
    assert [(x.key, x.seed_y, x.seed_x, x.pixels) for x in a.placed] == [
        (x.key, x.seed_y, x.seed_x, x.pixels) for x in b.placed
    ]


def test_a_raster_that_does_not_match_the_canvas_is_rejected(tree):
    raster, sels = _two_counties()
    with pytest.raises(ValueError, match="does not match canvas"):
        baronies.plan(
            raster_ids=raster,
            canvas=_canvas(8, 8),
            selections=sels,
            tree=tree,
            cfg=BaronyConfig(min_barony_pixels=1),
        )
