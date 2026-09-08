"""Integration: the barony split on the real Faerûn mod.

Marked ``slow``; skipped when the Faerûn clone is absent (it is gitignored,
see CLAUDE.md for the clone command).

The counts here are the lane's done-criteria, pinned so an upstream change or a
config change has to be acknowledged rather than noticed later:

* ~3.8k built holdings, against 15,356 *defined* baronies — the invariant the
  whole method rests on (CLAUDE.md);
* every county keeps at least one CK3 province, so no county is a hole;
* ``map_data/definition.csv`` names every barony province ``b_<ck2 name>``,
  which is the contract the ``titles-history`` lane reads.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ck2ck3.config import Config
from ck2ck3.map import build as map_build
from ck2ck3.map import ck2titles, holdings
from ck2ck3.map.sink import DirectorySink
from ck2ck3.steps import map as map_step

REPO = Path(__file__).resolve().parents[1]
FAERUN = REPO / "Faerun" / "Faerun"

BOOKMARK = (1357, 1, 1)
LATEST = (1501, 1, 1)
#: the date docs/design_map.md §B measured against
DESIGN_DATE = (1368, 9, 2)

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(not FAERUN.is_dir(), reason="Faerun/ clone absent"),
]


@pytest.fixture(scope="module")
def tree() -> ck2titles.Ck2TitleTree:
    return ck2titles.read_dir(FAERUN / "common" / "landed_titles")


@pytest.fixture(scope="module")
def history() -> dict[int, holdings.ProvinceHistory]:
    return holdings.read_dir(FAERUN / "history" / "provinces")


def _select(history, tree, bookmark, latest=LATEST):
    return {
        pid: holdings.select(
            hist,
            bookmark=bookmark,
            latest=latest,
            order=tree.county_baronies.get(hist.county or ""),
        )
        for pid, hist in history.items()
    }


def test_the_hierarchy_has_the_documented_shape(tree):
    assert len(tree.of_tier("c")) == 2132
    assert len(tree.of_tier("d")) == 979
    assert len(tree.of_tier("b")) == 15356
    assert not tree.duplicates


def test_built_holdings_are_a_quarter_of_the_defined_baronies(history, tree):
    """The invariant: the barony set is the built holdings, never the list."""
    sels = _select(history, tree, BOOKMARK)
    built = sum(len(s.baronies) for s in sels.values())
    defined = sum(len(v) for v in tree.county_baronies.values())
    assert built == 3857, "barony set at 1357.1.1 union 1501.1.1"
    assert defined == 15195
    assert built < defined / 3


def test_the_design_date_count_is_still_about_3_8k(history, tree):
    """``docs/design_map.md`` §B measured 3,786 built holdings at 1368.9.2."""
    sels = _select(history, tree, DESIGN_DATE)
    built = sum(len(s.baronies) for s in sels.values())
    assert 3700 <= built <= 3900
    assert built == 3857


def test_every_province_with_history_gets_at_least_one_barony(history, tree):
    sels = _select(history, tree, BOOKMARK)
    empty = [pid for pid, s in sels.items() if not s.baronies]
    assert empty == []


def test_faerun_uses_only_the_four_ck3_holding_types(history, tree):
    sels = _select(history, tree, BOOKMARK)
    kinds = {h for s in sels.values() for h in s.baronies.values()}
    assert kinds == {
        "castle_holding",
        "city_holding",
        "church_holding",
        "tribal_holding",
    }
    non_barony = sum(len(s.non_barony) for s in sels.values())
    assert non_barony == 0, "no fort/hospital/trade_post/family_palace in Faerun"


def test_later_bookmarks_keep_their_holdings(history, tree):
    """Holdings built after 1357 still get a province (design §B.1)."""
    sels = _select(history, tree, BOOKMARK)
    later = sum(len(s.later) for s in sels.values())
    assert later == 79
    only_1357 = _select(history, tree, BOOKMARK, latest=BOOKMARK)
    assert sum(len(s.baronies) for s in only_1357.values()) == 3857 - later


# --------------------------------------------------------------------------- #
# the whole map step
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def report(tmp_path_factory):
    """Run the map step over the real mod, text files only, writing nothing."""
    cfg_cli = Config.load(REPO / "configs" / "faerun.toml")

    class Ctx:
        config = cfg_cli
        dry_run = True

        def ck2(self, *parts):
            return (REPO / cfg_cli.ck2_mod).joinpath(*parts)

    cfg = map_step._map_config(Ctx())
    sink = DirectorySink(tmp_path_factory.mktemp("mod"), dry_run=True, verbose=False)
    return map_build.run(cfg, sink, skip_images=True)


def test_the_map_is_barony_keyed(report):
    prov = report["provinces"]
    bar = report["baronies"]
    assert bar["placed"] + bar["demoted"] == 3857
    assert bar["placed"] == prov["baronies"]
    # 95 % of the built holdings survive the min_barony_pixels guard
    assert bar["placed"] / (bar["placed"] + bar["demoted"]) > 0.9
    assert prov["ck3_total"] == prov["baronies"] + prov["sea"] + prov["lake"] + (
        prov["river"]
    ) + (prov["land"] - prov["baronies"])


def test_every_county_keeps_at_least_one_province(report):
    """The done-criterion: no county may end up without a CK3 province."""
    plan = report["_plan"]
    counties_in = {b.county for b in plan.placed} | {b.county for b in plan.demoted}
    counties_out = {b.county for b in plan.placed}
    assert counties_in == counties_out
    assert len(counties_out) == 2125


def test_definition_csv_names_every_barony_with_its_title_id(report):
    ids = report["_ids"]
    baronies = ids.baronies()
    assert len(baronies) == report["baronies"]["placed"]
    assert all(p.name.startswith("b_") for p in baronies)
    assert len({p.name for p in baronies}) == len(baronies)


def test_every_province_colour_is_unique(report):
    ids = report["_ids"]
    colours = [p.rgb for p in ids.provinces]
    assert len(set(colours)) == len(colours)


def test_barony_ids_are_dense_and_start_at_one(report):
    ids = report["_ids"]
    assert [p.id for p in ids.provinces] == list(range(1, len(ids.provinces) + 1))
    assert all(p.is_barony for p in ids.provinces[: report["baronies"]["placed"]])


def test_neighbouring_baronies_get_neighbouring_ids(report):
    """Ids follow the CK2 hierarchy, so a county's baronies are consecutive."""
    ids = report["_ids"]
    by_county: dict[str, list[int]] = {}
    for p in ids.baronies():
        by_county.setdefault(p.county, []).append(p.id)
    spread = [max(v) - min(v) - (len(v) - 1) for v in by_county.values()]
    assert sum(1 for s in spread if s == 0) / len(spread) > 0.99


def test_the_evidence_files_are_written(report):
    ev = report["_evidence"]
    assert set(ev) == {
        "province_id_map.csv",
        "lost_provinces.csv",
        "barony_set.csv",
        "nonbarony_holdings.csv",
    }
    assert len(ev["barony_set.csv"].splitlines()) == 3857 + 1
    assert ev["nonbarony_holdings.csv"].strip().count("\n") == 0  # header only
