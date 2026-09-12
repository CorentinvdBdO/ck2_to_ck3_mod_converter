"""Lane ``province-edges``: the smooth id upsample and its enforced bounds.

The synthetic map is three provinces with a diagonal border, which is the
shape NEAREST turns into a staircase and the shape the smooth argmax has to
turn back into a line.
"""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from ck2ck3.map import province_edges, provinces
from ck2ck3.map.ck2read import Ck2Province
from ck2ck3.map.config import Canvas

FACTOR = 1.9543  # Faerun's own upsample (docs/map_scale.md)


def three_province_source(n: int = 32) -> np.ndarray:
    """Ids 1/2/3: a diagonal split, plus an island of 3 inside 1."""
    y, x = np.mgrid[0:n, 0:n]
    src = np.where(x + y < n, 1, 2).astype(np.int32)
    src[(y - 6) ** 2 + (x - 6) ** 2 <= 9] = 3
    return src


def make_canvas(n: int, factor: float = FACTOR, pad: int = 4) -> Canvas:
    sw = int(n * factor)
    sh = int(n * factor)
    return Canvas(
        width=sw + 2 * pad,
        height=sh + 2 * pad,
        scaled_width=sw,
        scaled_height=sh,
        offset_x=pad,
        offset_y=pad,
        factor=factor,
        crop_x0=0,
        crop_y0=0,
        crop_x1=n,
        crop_y1=n,
    )


def mean_crack_run(labels: np.ndarray) -> float:
    """Mean straight run of a boundary crack — the staircase's own period."""

    def runs(mask: np.ndarray) -> np.ndarray:
        pad = np.zeros((mask.shape[0], 1), dtype=np.int8)
        flat = np.concatenate([pad, mask.astype(np.int8), pad], axis=1).ravel()
        d = np.diff(flat)
        return np.flatnonzero(d == -1) - np.flatnonzero(d == 1)

    lens = np.concatenate(
        [runs(labels[:-1, :] != labels[1:, :]), runs((labels[:, :-1] != labels[:, 1:]).T)]
    )
    return float(lens.mean())


# --------------------------------------------------------------------------- #
# the upsample itself
# --------------------------------------------------------------------------- #
def test_smooth_upsample_keeps_every_province_and_invents_none():
    src = three_province_source()
    out = province_edges.smooth_resize_ids(src, make_canvas(32))
    got = set(np.unique(out).tolist())
    assert got == {province_edges.PADDING, 1, 2, 3}
    for pid in (1, 2, 3):
        assert (out == pid).sum() > 0, f"province {pid} lost every pixel"


def test_no_canvas_pixel_inside_the_scaled_region_is_unassigned():
    src = three_province_source()
    c = make_canvas(32)
    out = province_edges.smooth_resize_ids(src, c)
    inner = out[
        c.offset_y : c.offset_y + c.scaled_height,
        c.offset_x : c.offset_x + c.scaled_width,
    ]
    assert not (inner == province_edges.PADDING).any()


def test_smooth_upsample_is_deterministic():
    src = three_province_source()
    c = make_canvas(32)
    a = province_edges.smooth_resize_ids(src, c)
    b = province_edges.smooth_resize_ids(src, c)
    assert np.array_equal(a, b)


def test_tiling_does_not_show_a_seam():
    """A tile is a compute detail; the result must not depend on its size."""
    src = three_province_source(48)
    c = make_canvas(48)
    whole = province_edges.smooth_resize_ids(src, c, tile_px=4096)
    tiled = province_edges.smooth_resize_ids(src, c, tile_px=16)
    assert np.array_equal(whole, tiled)


def test_smoothing_shortens_the_staircase_runs():
    """The point of the lane, as a number: the boundary stops running straight."""
    src = three_province_source(64)
    c = make_canvas(64)
    nn = provinces._resize_ids(src, c)
    sm = province_edges.smooth_resize_ids(src, c)
    assert mean_crack_run(sm) < mean_crack_run(nn)


def test_sigma_zero_is_still_smooth_and_still_valid():
    src = three_province_source()
    out = province_edges.smooth_resize_ids(src, make_canvas(32), sigma_src_px=0.0)
    assert set(np.unique(out).tolist()) == {province_edges.PADDING, 1, 2, 3}


def test_negative_sigma_is_refused():
    with pytest.raises(ValueError, match="sigma_src_px"):
        province_edges.smooth_resize_ids(
            three_province_source(), make_canvas(32), sigma_src_px=-1.0
        )


# --------------------------------------------------------------------------- #
# the bookkeeping helpers
# --------------------------------------------------------------------------- #
def test_adjacency_delta_counts_both_directions():
    a = np.array([[1, 1, 2], [1, 1, 2], [3, 3, 3]], dtype=np.int32)
    b = np.array([[1, 2, 2], [1, 1, 2], [3, 3, 3]], dtype=np.int32)
    d = province_edges.adjacency_delta(a, b)
    assert d["pairs_before"] == d["pairs_after"] == 3
    assert d["pairs_added"] == d["pairs_removed"] == 0


def test_region_area_delta_flags_only_the_big_movers():
    before = np.array([[1] * 10 + [2] * 10], dtype=np.int32)
    after = np.array([[1] * 5 + [2] * 15], dtype=np.int32)
    d = province_edges.region_area_delta(before, after, tolerance=0.20)
    assert d["beyond_tolerance"] == 2
    assert d["vanished"] == []
    assert dict((r[0], r[3]) for r in d["worst"])[1] == pytest.approx(-0.5)


def test_region_area_delta_reports_a_vanished_id():
    before = np.array([[1, 1, 2]], dtype=np.int32)
    after = np.array([[1, 1, 1]], dtype=np.int32)
    assert province_edges.region_area_delta(before, after)["vanished"] == [2]


# --------------------------------------------------------------------------- #
# through build_raster: the bound, and the province set
# --------------------------------------------------------------------------- #
def _write_bmp(src: np.ndarray, path):
    lut = np.array([[0, 0, 0], [10, 0, 0], [0, 10, 0], [0, 0, 10]], dtype=np.uint8)
    Image.fromarray(lut[src], mode="RGB").save(path)
    return path


def _provs() -> list[Ck2Province]:
    return [
        Ck2Province(1, (10, 0, 0), "A"),
        Ck2Province(2, (0, 10, 0), "B"),
        Ck2Province(3, (0, 0, 10), "C"),
    ]


def test_build_raster_smooth_keeps_the_province_set(tmp_path):
    src = three_province_source()
    c = make_canvas(32)
    hard = provinces.build_raster(
        _write_bmp(src, tmp_path / "p.bmp"), _provs(), c, min_pixels=1
    )
    soft = provinces.build_raster(
        tmp_path / "p.bmp", _provs(), c, min_pixels=1, smooth_edges=True
    )
    assert soft.surviving == hard.surviving == {1, 2, 3}
    assert soft.lost == {}
    assert soft.edges["smooth"] == 1


def test_build_raster_smooth_respects_the_one_source_pixel_bound(tmp_path):
    src = three_province_source()
    c = make_canvas(32)
    r = provinces.build_raster(
        tmp_path / "p.bmp" if (tmp_path / "p.bmp").exists()
        else _write_bmp(src, tmp_path / "p.bmp"),
        _provs(), c, min_pixels=1, smooth_edges=True,
        max_shift_source_px=1.0,
    )
    # the bound is in canvas pixels; nothing may travel further
    assert r.edges["max_shift_px"] <= r.edges["bound_px"] + 1e-9
    assert r.edges["beyond_bound_px"] == 0.0


def test_build_raster_smooth_is_deterministic(tmp_path):
    src = three_province_source()
    c = make_canvas(32)
    p = _write_bmp(src, tmp_path / "p.bmp")
    a = provinces.build_raster(p, _provs(), c, min_pixels=1, smooth_edges=True)
    b = provinces.build_raster(p, _provs(), c, min_pixels=1, smooth_edges=True)
    assert np.array_equal(a.ids, b.ids)


def test_build_raster_relief_warp_moves_the_border_and_stays_bounded(tmp_path):
    src = three_province_source()
    c = make_canvas(32)
    p = _write_bmp(src, tmp_path / "p.bmp")
    dy = np.full((c.height, c.width), 1, dtype=np.int8)
    dx = np.zeros((c.height, c.width), dtype=np.int8)
    r = provinces.build_raster(
        p, _provs(), c, min_pixels=1, smooth_edges=True, warp=(dy, dx)
    )
    assert r.edges["relief_warped_px"] == c.height * c.width
    assert r.edges["max_shift_px"] <= r.edges["bound_px"] + 1e-9
    assert r.surviving == {1, 2, 3}


def test_build_raster_rejects_a_warp_of_the_wrong_shape(tmp_path):
    src = three_province_source()
    c = make_canvas(32)
    p = _write_bmp(src, tmp_path / "p.bmp")
    bad = np.zeros((4, 4), dtype=np.int8)
    with pytest.raises(ValueError, match="relief warp"):
        provinces.build_raster(
            p, _provs(), c, min_pixels=1, smooth_edges=True, warp=(bad, bad)
        )


def test_nearest_is_still_the_default_of_build_raster(tmp_path):
    """Callers that did not ask for the lane get byte-identical old output."""
    src = three_province_source()
    c = make_canvas(32)
    p = _write_bmp(src, tmp_path / "p.bmp")
    r = provinces.build_raster(p, _provs(), c, min_pixels=1)
    assert r.edges == {}
    assert np.array_equal(r.ids, provinces._resize_ids(src, c))


# --------------------------------------------------------------------------- #
# the keys have to be read by the REAL CLI config builder
# --------------------------------------------------------------------------- #
def _ctx(map_table: dict):
    from pathlib import Path as _P

    class Cfg:
        raw = {"map": {"vanilla_km_per_px": 1.0, "source_km_per_px": 1.0,
                       **map_table}}
        path = _P("configs/x.toml")
        out = _P("/tmp/out")
        prefix = "fae"
        bookmark_date = (1357, 1, 1)
        name = "n"
        version = "0"
        supported_version = "1.19.*"

    class Ctx:
        config = Cfg()

        def ck2(self, *parts):
            return _P("/tmp/ck2").joinpath(*parts)

        def ck3(self, *parts):
            return _P("/tmp/ck3").joinpath(*parts)

    return Ctx()


#: attribute on ProvincesConfig -> (value under [map.provinces], flat [map]
#: alias, default).  A key `_map_config` never reads is a silent no-op — the
#: `[map] colormap = false` and `[map] trees*` bugs, twice over.
_EDGE_KEYS = {
    "smooth_edges": (False, "province_edges", True),
    "smooth_sigma_src_px": (1.25, "province_edges_sigma_src_px", 0.6),
    "smooth_max_shift_source_px": (0.5, "province_edges_max_shift_source_px", 1.0),
    "smooth_relief_shift_px": (0.0, "province_edges_relief_shift_px", 1.0),
}


def test_cli_config_builder_reads_the_province_edge_keys():
    from ck2ck3.steps import map as map_step

    table = {k: v for k, (v, _alias, _d) in _EDGE_KEYS.items()}
    cfg = map_step._map_config(_ctx({"provinces": table}))
    for key, (value, _alias, _default) in _EDGE_KEYS.items():
        assert getattr(cfg.provinces, key) == value, key

    cfg = map_step._map_config(_ctx({}))
    for key, (_value, _alias, default) in _EDGE_KEYS.items():
        assert getattr(cfg.provinces, key) == default, key


def test_flat_map_aliases_of_the_province_edge_keys_are_read_too():
    """`province_edges = false` under `[map]` has to work like the others."""
    from ck2ck3.steps import map as map_step

    flat = {alias: value for _k, (value, alias, _d) in _EDGE_KEYS.items()}
    cfg = map_step._map_config(_ctx(flat))
    for key, (value, _alias, _default) in _EDGE_KEYS.items():
        assert getattr(cfg.provinces, key) == value, key


def test_standalone_map_toml_reads_the_province_edge_keys(tmp_path):
    """`configs/faerun_map.toml`'s own reader is a second, separate builder.

    `map_config.load` and `steps.map._map_config` both build a
    `ProvincesConfig` and neither delegates to the other, so a key added to
    one is silently ignored by the other.
    """
    from ck2ck3.map import config as map_config

    cfgdir = tmp_path / "configs"
    cfgdir.mkdir()
    body = "\n".join(
        f"{k} = {str(v).lower() if isinstance(v, bool) else v}"
        for k, (v, _a, _d) in _EDGE_KEYS.items()
    )
    (cfgdir / "x.toml").write_text(
        f"""
[input]
ck2_map_dir = "{tmp_path}"
[output]
mod_dir = "{tmp_path}"
[scale]
vanilla_km_per_px = 1.0
source_km_per_px = 1.0
[provinces]
{body}
""",
        encoding="utf-8",
    )
    cfg = map_config.load(cfgdir / "x.toml")
    for key, (value, _alias, _default) in _EDGE_KEYS.items():
        assert getattr(cfg.provinces, key) == value, key
