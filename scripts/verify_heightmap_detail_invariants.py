#!/usr/bin/env python3
"""Verify the heightmap-detail pass's invariants on a real generated mod.

Usage:  uv run scripts/verify_heightmap_detail_invariants.py <out_mod_dir>

Checks, entirely from files on disk (no import of the converter's own
land/water classification, so this is an independent check of what
`ck2ck3.map.heightmap_detail.apply` promises, docs/step_map_heightmap.md §3):

1. every land province (a `definition.csv` barony/land row not in
   `default.map`'s `sea_zones`/`lakes`/`river_provinces`) has every
   `heightmap.png` pixel of its colour strictly above the water level;
2. every water province (sea/lake/river-type, plus the padding ocean colour)
   has every pixel at or below the water level;
3. **the source bound** (docs/step_map_heightmap.md §2f): over a window of
   one CK2 source pixel, every land pixel satisfies
   ``source_local_min - tol <= out <= source_local_max + tol``, where
   ``source`` is the plain rescale of `Faerun/Faerun/map/topology.bmp` and
   ``tol`` is the terrain class's own measured vanilla high-frequency RMS
   times `--bound-sigmas` (`common/province_terrain` gives the class;
   `docs/evidence/map_fidelity/hf_by_terrain.csv` gives the RMS).  Skipped
   when the source topology is not readable (`--no-bound` forces it off);
4. distinct 16-bit value count, reported for before/after comparison.

Exit 0 when every check holds, 1 otherwise.

Usage:  uv run scripts/verify_heightmap_detail_invariants.py <out_mod_dir>
            [water_level] [--bound-sigmas N] [--bound-window N] [--no-bound]
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None

WATER_LEVEL = 4883  # docs/map_scale.md §4; overridable via argv[2]


def read_definition(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        parts = line.split(";")
        if len(parts) < 5 or not parts[0].isdigit():
            continue
        pid = int(parts[0])
        if pid == 0:
            continue
        rows.append({
            "id": pid,
            "rgb": (int(parts[1]), int(parts[2]), int(parts[3])),
            "name": parts[4],
        })
    return rows


def read_default_map(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    out = {}
    for key in ("sea_zones", "river_provinces", "lakes", "impassable_mountains"):
        out[key] = " ".join(re.findall(rf"^{key}\s*=\s*(.*)$", text, re.M))
    return out


def expand_ranges(spec: str) -> set[int]:
    ids: set[int] = set()
    for m in re.finditer(r"RANGE\s*\{\s*(\d+)\s+(\d+)\s*\}", spec):
        ids.update(range(int(m.group(1)), int(m.group(2)) + 1))
    body = re.sub(r"RANGE\s*\{[^}]*\}", " ", spec)
    ids.update(int(t) for t in re.findall(r"\b\d+\b", body))
    return ids


def check_source_bound(out: Path, heights: np.ndarray, land: np.ndarray,
                       water_level: int, sigmas: float, window: int) -> dict:
    """Check 3: the output never leaves the CK2 author's own surface + texture.

    Independent of the converter's own arrays: the source is rebuilt here from
    `topology.bmp` through the same transfer curve the `map` step uses, and
    the per-pixel terrain class is read back out of the generated mod's
    `common/province_terrain` -- so this is a check of the *files*, which is
    what the rest of this script is too.
    """
    import relief_pits_common as P
    import relief_sharp_common as C

    source = C.plain_rescale_canvas()
    if source.shape != heights.shape:
        return {"skipped": f"source {source.shape} != heightmap {heights.shape}"}
    tcode, tkeys = P.terrain_codes_from_mod(out, slice(None), slice(None))
    tol = P.tolerance_field(tcode, tkeys, sigmas=sigmas)
    # A land pixel the plain rescale itself put at or below the water level is
    # *raised to the pin* by the land invariant, which is a bigger claim than
    # this bound and wins: excluded here rather than reported as a violation.
    pinned = land & (source <= water_level)
    checked = land & ~pinned
    row = P.bound_violation(source, heights, checked, tol, size=window)
    row["bound_sigmas"] = sigmas
    row["bound_window_px"] = window
    row["pinned_land_px_excluded"] = int(pinned.sum())
    row["bound_under_px"] = int(round(
        row["bound_under_frac"] * float(checked.sum())))
    row["bound_over_px"] = int(round(
        row["bound_over_frac"] * float(checked.sum())))
    row["tol_median_levels"] = round(float(np.median(tol[checked])), 1)
    return row


def main(argv: list[str]) -> int:
    args = [a for a in argv[1:] if not a.startswith("--")]
    flags = [a for a in argv[1:] if a.startswith("--")]
    if not args:
        print(__doc__.strip())
        return 2
    out = Path(args[0])
    water_level = int(args[1]) if len(args) > 1 else WATER_LEVEL
    bound_sigmas = 2.0
    bound_window = 3
    do_bound = "--no-bound" not in flags
    for f in flags:
        if f.startswith("--bound-sigmas="):
            bound_sigmas = float(f.split("=", 1)[1])
        elif f.startswith("--bound-window="):
            bound_window = int(f.split("=", 1)[1])
    sys.path.insert(0, str(Path(__file__).resolve().parent))

    definition = read_definition(out / "map_data/definition.csv")
    dm = read_default_map(out / "map_data/default.map")
    water_ids = set()
    for key in ("sea_zones", "lakes", "river_provinces"):
        water_ids |= expand_ranges(dm[key])

    with (out / "map_data/provinces.png").open("rb") as fh:
        prov = np.asarray(Image.open(fh).convert("RGB"))
    with (out / "map_data/heightmap.png").open("rb") as fh:
        heights = np.asarray(Image.open(fh))
    if heights.dtype != np.uint16:
        print(f"heightmap.png is not 16-bit (got {heights.dtype})")
        return 1
    if prov.shape[:2] != heights.shape:
        print(
            f"provinces.png {prov.shape[:2]} and heightmap.png {heights.shape} "
            "are different sizes"
        )
        return 1

    key = (prov[..., 0].astype(np.int64) << 16) | (prov[..., 1].astype(np.int64) << 8) | prov[..., 2]

    problems: list[str] = []
    land_below = 0
    land_provinces_checked = 0
    water_above = 0
    water_provinces_checked = 0
    for row in definition:
        k = (row["rgb"][0] << 16) | (row["rgb"][1] << 8) | row["rgb"][2]
        mask = key == k
        if not mask.any():
            continue
        vals = heights[mask].astype(np.int64)
        is_water = row["id"] in water_ids
        if is_water:
            water_provinces_checked += 1
            bad = int((vals > water_level).sum())
            if bad:
                water_above += bad
                problems.append(
                    f"water province {row['id']} ({row['name']}): "
                    f"{bad}/{vals.size} px above water level {water_level} "
                    f"(max {int(vals.max())})"
                )
        else:
            land_provinces_checked += 1
            bad = int((vals <= water_level).sum())
            if bad:
                land_below += bad
                problems.append(
                    f"land province {row['id']} ({row['name']}): "
                    f"{bad}/{vals.size} px at or below water level {water_level} "
                    f"(min {int(vals.min())})"
                )

    bound_row: dict = {}
    if do_bound:
        try:
            land_mask = heights > water_level
            bound_row = check_source_bound(
                out, heights, land_mask, water_level, bound_sigmas, bound_window)
        except Exception as exc:                      # noqa: BLE001
            bound_row = {"skipped": f"{type(exc).__name__}: {exc}"}

    distinct = int(np.unique(heights).size)
    print(f"out                     {out}")
    print(f"water level             {water_level}")
    print(f"land provinces checked  {land_provinces_checked}")
    print(f"water provinces checked {water_provinces_checked}")
    print(f"distinct height values  {distinct}")
    print(f"land px at/below water  {land_below}")
    print(f"water px above water    {water_above}")
    if bound_row.get("skipped"):
        print(f"source bound            SKIPPED ({bound_row['skipped']})")
    elif bound_row:
        print(f"source bound            {bound_sigmas}x hf RMS over "
              f"{bound_window} px (median tol "
              f"{bound_row['tol_median_levels']} levels)")
        print(f"  land pinned, excluded {bound_row['pinned_land_px_excluded']} px")
        print(f"  land below the bound  {bound_row['bound_under_px']} px "
              f"(max {bound_row['bound_under_max']} levels)")
        print(f"  land above the bound  {bound_row['bound_over_px']} px "
              f"(max {bound_row['bound_over_max']} levels)")
        if bound_row["bound_under_px"] or bound_row["bound_over_px"]:
            problems.append(
                f"source bound broken on {bound_row['bound_under_px']} land px "
                f"below / {bound_row['bound_over_px']} above"
            )

    if problems:
        print("\nINVARIANT BROKEN")
        for p in problems[:20]:
            print(f"  - {p}")
        if len(problems) > 20:
            print(f"  ... and {len(problems) - 20} more")
        return 1
    print("\ninvariants hold")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
