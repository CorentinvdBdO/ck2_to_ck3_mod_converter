#!/usr/bin/env python3
"""Global per-terrain high-frequency amplitude check, on a real generated mod.

Usage:  uv run scripts/check_heightmap_detail_amplitude.py <out_mod_dir>

Measures the achieved high-pass RMS (16-bit levels) per CK3 terrain class
over the *whole* map, the same way `docs/evidence/map_fidelity/hf_by_terrain.csv`
measured vanilla's, and compares against `DEFAULT_HF_TARGETS`
(`ck2ck3.map.config`). This is the actual per-class contract the detail pass
promises -- a single crop (docs/evidence/heightmap_detail/) can and does
deviate from its class average by chance, since the gain field is a shared
per-class scalar, not a per-pixel exact match.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from ck2ck3.map.config import DEFAULT_HF_TARGETS  # noqa: E402
from ck2ck3.map.heightmap_detail import HF_SIGMA_KM  # noqa: E402

Image.MAX_IMAGE_PIXELS = None
KM_PER_PX = 1.4839
WATER = 4883


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
        rows.append({"id": pid, "rgb": (int(parts[1]), int(parts[2]), int(parts[3]))})
    return rows


def read_province_terrain(path: Path) -> dict[int, str]:
    out: dict[int, str] = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k = k.strip()
        if k.isdigit():
            out[int(k)] = v.strip()
    return out


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__.strip())
        return 2
    out = Path(sys.argv[1])
    definition = read_definition(out / "map_data/definition.csv")
    terrain = read_province_terrain(out / "common/province_terrain/fae_province_terrain.txt")

    with (out / "map_data/provinces.png").open("rb") as fh:
        prov = np.asarray(Image.open(fh).convert("RGB"))
    with (out / "map_data/heightmap.png").open("rb") as fh:
        heights = np.asarray(Image.open(fh)).astype(np.float64)

    key = (prov[..., 0].astype(np.int64) << 16) | (prov[..., 1].astype(np.int64) << 8) | prov[..., 2]
    id_of_key: dict[int, int] = {}
    for r in definition:
        k = (r["rgb"][0] << 16) | (r["rgb"][1] << 8) | r["rgb"][2]
        id_of_key[k] = r["id"]

    flat_key = key.ravel()
    uniq_keys, inverse = np.unique(flat_key, return_inverse=True)
    id_per_uniq = np.array([id_of_key.get(int(k), 0) for k in uniq_keys], dtype=np.int64)
    pid_grid = id_per_uniq[inverse].reshape(key.shape)

    sigma_px = HF_SIGMA_KM / KM_PER_PX
    hp = heights - gaussian_filter(heights, sigma_px)

    land_mask = heights > WATER
    print(f"{'terrain':<16} {'px':>10} {'target':>8} {'achieved':>9} {'ratio':>6}")
    rows = []
    for tkey in sorted(set(terrain.values())):
        pids = {pid for pid, t in terrain.items() if t == tkey}
        if not pids:
            continue
        mask = np.isin(pid_grid, list(pids)) & land_mask
        n = int(mask.sum())
        if n == 0:
            continue
        achieved = float(hp[mask].std())
        target = DEFAULT_HF_TARGETS.get(tkey, DEFAULT_HF_TARGETS.get("plains", 90.0))
        ratio = achieved / target if target else float("nan")
        rows.append((tkey, n, target, achieved, ratio))
        print(f"{tkey:<16} {n:>10} {target:>8.1f} {achieved:>9.1f} {ratio:>6.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
