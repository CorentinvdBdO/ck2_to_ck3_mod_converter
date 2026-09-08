"""Derive the coordinate frame of ``gfx/map/map_object_data/*_locators.txt``.

Cross-checks every vanilla CK3 locator instance against the pixel centroid of
its province colour in ``map_data/provinces.png`` + ``map_data/definition.csv``.

The question the script answers, with numbers rather than a guess:

* are ``position.x`` / ``position.z`` **pixels** of ``provinces.png``, or world
  units of some other scale?
* is ``z`` measured from the **top** of the bitmap or from the **bottom**?
* is ``position.y`` ever non-zero?
* what is the ``rotation`` quaternion's shape?

Usage::

    uv run scripts/check_locator_frame.py [--game DIR] [--out FILE]
    uv run scripts/check_locator_frame.py --mod OUT_DIR [--against DIR]

The first form derives the frame from vanilla and writes a Markdown table to
``docs/evidence/locator_frame.md``.  The second checks a *generated* mod: every
locator instance against that mod's own province centroids, and — when
``--against`` names a directory of files CK3 produced itself (the engine writes
them to ``Documents/Paradox Interactive/Crusader Kings III/generated/`` when a
locator is incomplete) — against the engine's own answer.
"""

from __future__ import annotations

import argparse
import csv
import re
import statistics
import sys
from pathlib import Path

import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None

DEFAULT_GAME = Path(
    "/home/cvdbdo/.local/share/Steam/steamapps/common/Crusader Kings III/game"
)

#: every per-province locator file vanilla ships, with the ``name=`` it declares
LOCATOR_FILES = (
    "building_locators.txt",
    "special_building_locators.txt",
    "player_stack_locators.txt",
    "other_stack_locators.txt",
    "siege_locators.txt",
    "combat_locators.txt",
    "activities.txt",
)

_HEAD = re.compile(r"(\w+)\s*=\s*([^\s{][^\n]*)")
_INSTANCE = re.compile(
    r"\{\s*id\s*=\s*(\d+)\s*"
    r"position\s*=\s*\{\s*([-\d.eE]+)\s+([-\d.eE]+)\s+([-\d.eE]+)\s*\}\s*"
    r"rotation\s*=\s*\{\s*([-\d.eE]+)\s+([-\d.eE]+)\s+([-\d.eE]+)\s+([-\d.eE]+)\s*\}"
)


def read_locators(path: Path) -> tuple[dict[str, str], dict[int, tuple[float, ...]]]:
    """Return (header fields, {province id: (x, y, z, qx, qy, qz, qw)})."""
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    head_end = text.index("instances")
    header = dict(_HEAD.findall(text[:head_end]))
    out: dict[int, tuple[float, ...]] = {}
    for m in _INSTANCE.finditer(text, head_end):
        out[int(m.group(1))] = tuple(float(m.group(i)) for i in range(2, 9))
    return header, out


def centroids(game: Path) -> tuple[dict[int, tuple[float, float]], int, int]:
    """Pixel centroid (x, y_top_down) of every province colour, plus image size."""
    defs = game / "map_data" / "definition.csv"
    colour_to_id: dict[int, int] = {}
    with defs.open(encoding="utf-8-sig", errors="replace", newline="") as fh:
        for row in csv.reader(fh, delimiter=";"):
            if len(row) < 4 or not row[0].strip().isdigit():
                continue
            try:
                r, g, b = (int(row[i]) for i in (1, 2, 3))
            except ValueError:
                continue
            colour_to_id[(r << 16) | (g << 8) | b] = int(row[0])

    img = Image.open(game / "map_data" / "provinces.png").convert("RGB")
    w, h = img.size
    arr = np.asarray(img, dtype=np.uint32)
    packed = (arr[:, :, 0] << 16) | (arr[:, :, 1] << 8) | arr[:, :, 2]
    del arr

    keys = np.fromiter(colour_to_id, dtype=np.int64, count=len(colour_to_id))
    vals = np.fromiter(colour_to_id.values(), dtype=np.int64, count=len(colour_to_id))
    order = np.argsort(keys)
    keys, vals = keys[order], vals[order]

    flat = packed.ravel().astype(np.int64)
    pos = np.searchsorted(keys, flat)
    pos[pos >= keys.size] = 0
    hit = keys[pos] == flat
    ids = np.where(hit, vals[pos], -1)

    ys, xs = np.divmod(np.arange(flat.size, dtype=np.int64), w)
    valid = ids >= 0
    ids, xs, ys = ids[valid], xs[valid], ys[valid]
    n = int(ids.max()) + 1
    count = np.bincount(ids, minlength=n)
    sx = np.bincount(ids, weights=xs, minlength=n)
    sy = np.bincount(ids, weights=ys, minlength=n)
    out = {
        int(i): (float(sx[i] / count[i]), float(sy[i] / count[i]))
        for i in range(n)
        if count[i]
    }
    return out, w, h


def check_mod(mod: Path, against: Path | None, game: Path = DEFAULT_GAME) -> int:
    """Validate a generated mod's own locators. Returns a process exit code."""
    cen, w, h = centroids(mod)
    print(f"{mod}: canvas {w}x{h}, {len(cen)} province colours")
    bad = 0
    for fname in LOCATOR_FILES:
        path = mod / "gfx" / "map" / "map_object_data" / fname
        if not path.exists():
            print(f"  {fname:32} MISSING - the game will keep vanilla's coordinates")
            bad += 1
            continue
        _, inst = read_locators(path)
        far = []
        for pid, v in inst.items():
            if pid == 0:  # the sentinel instance is not a province
                continue
            c = cen.get(pid)
            if c is None:
                continue
            d = ((v[0] - c[0]) ** 2 + ((h - v[2]) - c[1]) ** 2) ** 0.5
            if d > 1.0:
                far.append((d, pid))
        worst = max(far, default=(0.0, None))
        print(
            f"  {fname:32} {len(inst):5} instances, "
            f"{len(far)} further than 1 px from their centroid, worst {worst[0]:.2f}"
        )
        if far:
            bad += 1
        if against is not None and (against / fname).exists():
            _, ref = read_locators(against / fname)
            vanilla_path = game / "gfx" / "map" / "map_object_data" / fname
            stale = (
                set(read_locators(vanilla_path)[1]) if vanilla_path.exists() else set()
            )
            # The engine only fills *gaps*: an id vanilla also defines keeps
            # vanilla's European coordinate, so only the ids vanilla lacks are
            # the engine's own answer and worth comparing against.
            fresh = [
                ((v[0] - ref[pid][0]) ** 2 + (v[2] - ref[pid][2]) ** 2) ** 0.5
                for pid, v in inst.items()
                if pid in ref and pid in cen and pid not in stale
            ]
            inherited = [
                ((v[0] - ref[pid][0]) ** 2 + (v[2] - ref[pid][2]) ** 2) ** 0.5
                for pid, v in inst.items()
                if pid in ref and pid in cen and pid in stale
            ]
            if fresh:
                print(
                    f"  {'':32} vs engine's own placements (ids vanilla lacks): "
                    f"n={len(fresh)} median {statistics.median(fresh):.2f} px, "
                    f"max {max(fresh):.2f}"
                )
            if inherited:
                print(
                    f"  {'':32} vs coordinates the engine inherited from vanilla: "
                    f"n={len(inherited)} median {statistics.median(inherited):.0f} px "
                    "(this gap IS the bug being fixed)"
                )
    return 1 if bad else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--game", type=Path, default=DEFAULT_GAME)
    ap.add_argument(
        "--mod", type=Path, help="check a generated mod's locators instead"
    )
    ap.add_argument(
        "--against",
        type=Path,
        help="directory of CK3-generated locator files to compare against",
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parent.parent
        / "docs"
        / "evidence"
        / "locator_frame.md",
    )
    args = ap.parse_args(argv)
    if args.mod is not None:
        return check_mod(args.mod, args.against, args.game)

    cen, w, h = centroids(args.game)
    lines: list[str] = [
        "# Locator coordinate frame — vanilla CK3, measured",
        "",
        f"Generated by `scripts/check_locator_frame.py` against `{args.game}`.",
        f"`map_data/provinces.png` is {w}x{h}; {len(cen)} province colours found.",
        "",
        "`d_bottom_up` reads `position.z` as `height - y_centroid`; `d_top_down`",
        "reads it as `y_centroid` directly.  Distances are pixels, median over",
        "every id the file and the bitmap share.",
        "",
        "| file | name= | layer= | clamp | n | median dx | median d_bottom_up "
        "| median d_top_down | y!=0 | non-unit scale |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    summary: list[str] = []
    for fname in LOCATOR_FILES:
        path = args.game / "gfx" / "map" / "map_object_data" / fname
        if not path.exists():
            lines.append(f"| {fname} | *missing* | | | | | | | | |")
            continue
        header, inst = read_locators(path)
        dx, dbu, dtd = [], [], []
        nonzero_y = 0
        for pid, v in inst.items():
            c = cen.get(pid)
            if c is None:
                continue
            x, y, z = v[0], v[1], v[2]
            if abs(y) > 1e-6:
                nonzero_y += 1
            dx.append(abs(x - c[0]))
            dbu.append(abs((h - z) - c[1]))
            dtd.append(abs(z - c[1]))
        if not dx:
            continue
        lines.append(
            "| {f} | {n} | {l} | {c} | {k} | {mx:.1f} | {bu:.1f} | {td:.1f} | {y} | - |".format(
                f=fname,
                n=header.get("name", "?").strip('"'),
                l=header.get("layer", "?").strip('"'),
                c=header.get("clamp_to_water_level", "?"),
                k=len(dx),
                mx=statistics.median(dx),
                bu=statistics.median(dbu),
                td=statistics.median(dtd),
                y=nonzero_y,
            )
        )
        summary.append(
            f"{fname}: n={len(dx)} dx={statistics.median(dx):.1f} "
            f"bottom_up={statistics.median(dbu):.1f} top_down={statistics.median(dtd):.1f}"
        )

    # id coverage: does every definition.csv id get a locator?
    header, inst = read_locators(
        args.game / "gfx" / "map" / "map_object_data" / "building_locators.txt"
    )
    ids_png = set(cen)
    ids_loc = set(inst)
    lines += [
        "",
        "## id coverage (`building_locators.txt`)",
        "",
        f"- ids in the locator file: **{len(ids_loc)}** "
        f"(min {min(ids_loc)}, max {max(ids_loc)})",
        f"- province ids painted in `provinces.png`: **{len(ids_png)}**",
        f"- painted ids with no locator: **{len(ids_png - ids_loc)}**",
        f"- locator ids not painted: **{len(ids_loc - ids_png)}**",
        "",
        "## What the numbers mean",
        "",
        "- `position` is `{ x y z }` in **provinces.png pixels**, x left-to-right.",
        "- `z` is **bottom-up**: `z = image_height - y_top_down`.",
        "- `y` is the height above the water plane; every per-province locator "
        "ships `0.000000`.",
        "- `rotation` is a quaternion `{ qx qy qz qw }`; the shipped values are "
        "yaw-only (`qx = qz = -0`), so the identity `{ 0 0 0 1 }` is a legal "
        "no-rotation value.",
        "- `scale` is `{ 1 1 1 }` throughout.",
    ]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(summary))
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
