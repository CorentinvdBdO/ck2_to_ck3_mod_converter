#!/usr/bin/env python3
"""Write a tiny probe mod that re-points the starting camera at a named place.

Goal D of lane `map-colour`: the headless `-test` harness reaches `In Game`
(``CLAUDE.md`` invariant, `verified` 54 s vanilla control) but our own
generated ``common/defines/graphic/fae_graphics.txt``
(``ck2ck3.map.bootstrap.render_camera_defines``) points ``NCamera.START_LOOK_AT``
at the bare canvas centre, which is not any of the three regions this lane's
evidence composites cover. `NCamera.START_LOOK_AT` / `START_ZOOM_STEP` are
real vanilla defines (`verified`,
``game/common/defines/graphic/00_graphics.txt:172-175``) in exactly the same
bottom-up pixel frame as the locators (``ck2ck3.map.locators.world_position``)
-- our own camera defines already use that frame for the canvas-centre
default, so no new coordinate system needs deriving here.

This script writes a probe mod: one file,
``common/defines/graphic/zzz_camera_probe_graphics.txt``, overriding just
those two keys. Load it *after* the converted mod
(``claudespace/scripts/ck3_soak.sh <mod> --extra <probe dir>`` per
``docs/step_map_paint.md`` §8.6's own pattern) so its ``NCamera`` block wins.

**Not tested in game from this lane** (the hard rule: the coordinator runs
every in-game check) -- this is the exact snippet, not a verified result.

Usage::

    uv run scripts/camera_probe.py <out_dir> <probe_dir> [--place waterdeep|anauroch|spine] [--zoom N]
    uv run scripts/camera_probe.py <out_dir> <probe_dir> --x 2351.8 --z 5706.6
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None

#: CK3 province id, from docs/evidence/province_id_map.csv, of a representative
#: barony for each named place this lane's evidence covers (module docstring
#: of scripts/render_map_colour_evidence.py has the region boxes).
PLACES: dict[str, tuple[int, int, int]] = {
    # (r, g, b) of the province in map_data/provinces.png
    "waterdeep": (247, 228, 169),  # b_north_ward, c_waterdeep
}
#: (x0, y0, w, h) canvas-pixel boxes, top-down y, from render_map_colour_evidence.py
REGION_CENTRES = {
    "sword_coast": (2080 + 1024, 940 + 1024),
    "anauroch": (2297 + 1024, 43 + 1024),
    "spine": (1405 + 1024, 0 + 512),
}


def province_centroid_px(mod: Path, rgb: tuple[int, int, int]) -> tuple[float, float]:
    with Image.open(mod / "map_data" / "provinces.png") as im:
        arr = np.asarray(im.convert("RGB"))
    mask = (
        (arr[..., 0] == rgb[0]) & (arr[..., 1] == rgb[1]) & (arr[..., 2] == rgb[2])
    )
    ys, xs = np.nonzero(mask)
    if xs.size == 0:
        raise ValueError(f"no pixels of rgb {rgb} found in {mod}/map_data/provinces.png")
    return float(xs.mean()), float(ys.mean())


def canvas_size(mod: Path) -> tuple[int, int]:
    with Image.open(mod / "map_data" / "provinces.png") as im:
        return im.size  # (w, h)


def world_look_at(x_px: float, y_px_topdown: float, canvas_height: int) -> tuple[float, float]:
    """Same frame as ck2ck3.map.locators.world_position: (x, height - y)."""
    return x_px, float(canvas_height) - y_px_topdown


def render_probe(x: float, z: float, zoom_step: int) -> str:
    return (
        "# Probe mod (lane map-colour, Goal D): re-points the starting camera.\n"
        "# NOT tested in game from this lane -- the coordinator runs every\n"
        "# in-game check (docs/step_map_paint.md). Load after the converted mod:\n"
        "#   claudespace/scripts/ck3_soak.sh <mod> --extra <this dir>\n"
        "NCamera = {\n"
        f"\tSTART_LOOK_AT = {{ {x:.1f} 0 {z:.1f} }}\n"
        f"\tSTART_ZOOM_STEP = {zoom_step}\n"
        "}\n"
    )


_DESCRIPTOR = (
    'version="0.0.1"\n'
    'name="ck2ck3 camera probe"\n'
    'supported_version="1.19.*"\n'
)


def write_probe(probe_dir: Path, x: float, z: float, zoom_step: int) -> Path:
    rel = Path("common") / "defines" / "graphic" / "zzz_camera_probe_graphics.txt"
    path = probe_dir / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_probe(x, z, zoom_step), encoding="utf-8-sig")
    # ck3_soak.sh --extra requires a descriptor.mod in the extra dir (it strips
    # any path= line and appends its own, docs/step_map_paint.md §8.6's
    # pattern); no replace_path is needed here, a distinctly-named defines
    # file just adds alongside fae_graphics.txt and overrides NCamera's
    # individual keys when loaded after the main mod.
    (probe_dir / "descriptor.mod").write_text(_DESCRIPTOR, encoding="utf-8")
    return path


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("out_dir", help="a built converter output (needs map_data/provinces.png)")
    ap.add_argument("probe_dir", help="where to write the probe mod folder")
    ap.add_argument(
        "--place", choices=sorted(set(PLACES) | set(REGION_CENTRES)), default="waterdeep"
    )
    ap.add_argument("--x", type=float, help="override: canvas pixel x (top-down frame)")
    ap.add_argument("--y", type=float, help="override: canvas pixel y (top-down frame)")
    ap.add_argument("--zoom", type=int, default=15, help="START_ZOOM_STEP (0=closest, 34=furthest)")
    args = ap.parse_args(argv)

    mod = Path(args.out_dir)
    _, canvas_h = canvas_size(mod)

    if args.x is not None and args.y is not None:
        px, py = args.x, args.y
        source = f"explicit ({px}, {py})"
    elif args.place in PLACES:
        px, py = province_centroid_px(mod, PLACES[args.place])
        source = f"province centroid for {args.place}"
    else:
        px, py = REGION_CENTRES[args.place]
        source = f"evidence region centre for {args.place}"

    x, z = world_look_at(px, py, canvas_h)
    probe_dir = Path(args.probe_dir)
    path = write_probe(probe_dir, x, z, args.zoom)
    print(f"place: {args.place} ({source}) -> canvas px ({px:.1f}, {py:.1f}) "
          f"-> START_LOOK_AT {{ {x:.1f} 0 {z:.1f} }}, START_ZOOM_STEP {args.zoom}")
    print(f"wrote {path}")
    print(f"load with: claudespace/scripts/ck3_soak.sh <mod> --extra {probe_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
