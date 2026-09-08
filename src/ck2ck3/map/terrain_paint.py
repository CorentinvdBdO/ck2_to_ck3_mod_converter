"""CK2 painted terrain -> CK3 runtime terrain paint.

CK3 does **not** render from the 120 mask PNGs `gfx/map/terrain/materials.settings`
lists; the renderer reads `gfx/map/terrain/detail_index.tga` +
`detail_intensity.tga`, both RGBA8 and **exactly `provinces.png`-sized**
(`verified` against the vanilla game folder: both are 9216x4608, uncompressed
truecolour TGA, origin bottom-left — `docs/evidence/map_fidelity/`,
``docs/map_fidelity.md`` §1.3). Channel 0/1 of `detail_index` are ordinals into
`materials.settings` **declaration order**; the matching channels of
`detail_intensity` are their blend weights and the four channels of a pixel
must sum to exactly 255 (`detail_data.settings` caps it at
`"materials_limit": 4`). Ship neither file and CK3 samples vanilla's own pair
in UV space across our canvas — Faerun wears Europe's terrain textures
(``docs/map_fidelity.md`` §1.3, "what we ship today: nothing").

Pipeline (``docs/step_map_paint.md``, prototyped in
``scripts/prototype_terrain_masks.py``):

1. **class map** — the CK2 terrain-category code grid already built for
   ``common/province_terrain`` (:mod:`ck2ck3.map.terrain`) -> a CK3 terrain key
   per pixel, via :data:`ck2ck3.map.terrain.CK2_TO_CK3_TERRAIN` (or a config
   override, same table `common/province_terrain` uses, so the paint and the
   gameplay terrain never disagree);
2. **material choice** — CK3 terrain key -> (primary, secondary) vanilla
   material id, from ``mappings/terrain_paint.csv``. Existing vanilla
   materials are used deliberately: no new ``.dds`` has to be authored and the
   colour/tiling match vanilla by construction;
3. **edge treatment** — CK2's palette edges are hard; vanilla's are dithered.
   The two materials are blended with a Gaussian-filtered noise field so class
   boundaries break up, and the blend weight is quantised (16 steps by
   default) so `detail_intensity.tga` stays compressible;
4. **write** — channel 0/1 = primary/secondary ordinal, 2/3 = 0 (unused);
   intensities always sum to 255.
"""

from __future__ import annotations

import csv
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter

from .terrain import CK2_TO_CK3_TERRAIN

MATERIAL_CSV_HEADER = "ck3_terrain,primary_material,secondary_material,note"

#: used when a CK3 terrain key has no row in mappings/terrain_paint.csv, or a
#: named material is not in the vanilla materials.settings this run has.
DEFAULT_MATERIALS = ("plains_01", "plains_01_noisy")

DETAIL_INDEX_PATH = "gfx/map/terrain/detail_index.tga"
DETAIL_INTENSITY_PATH = "gfx/map/terrain/detail_intensity.tga"


@dataclass
class PaintLayers:
    #: HxWx4 uint8, RGBA — channel 0/1 = primary/secondary material ordinal
    index: np.ndarray
    #: HxWx4 uint8, RGBA — channel 0/1 = primary/secondary blend weight (sum 255)
    intensity: np.ndarray
    #: CK3 terrain key -> pixel count, for the run report
    classes: dict[str, int] = field(default_factory=dict)
    #: CK3 terrain keys with no row in mappings/terrain_paint.csv (used the default)
    missing_material: list[str] = field(default_factory=list)
    #: material ids named by the table but absent from materials.settings
    missing_ordinal: list[str] = field(default_factory=list)
    quantize: int = 16


def read_material_map(path: str | Path) -> dict[str, tuple[str, str]]:
    """``mappings/terrain_paint.csv``: CK3 terrain key -> (primary, secondary).

    ``#`` comment lines are skipped like every other reader in this repo. A
    missing file returns ``{}``, so every key falls back to
    :data:`DEFAULT_MATERIALS` rather than raising.
    """
    p = Path(path)
    if not p.exists():
        return {}
    with p.open("r", encoding="utf-8", newline="") as fh:
        lines = [line for line in fh if not line.lstrip().startswith("#")]
    out: dict[str, tuple[str, str]] = {}
    for row in csv.DictReader(lines):
        key = (row.get("ck3_terrain") or "").strip()
        if not key:
            continue
        prim = (row.get("primary_material") or "").strip() or DEFAULT_MATERIALS[0]
        sec = (row.get("secondary_material") or "").strip() or DEFAULT_MATERIALS[1]
        out[key] = (prim, sec)
    return out


_ID_RE = re.compile(r'\bid\s*=\s*"([^"]+)"')
_BLOCK_RE = re.compile(r"\{([^{}]*)\}")


def material_ordinals(path: str | Path) -> dict[str, int]:
    """``gfx/map/terrain/materials.settings`` -> {material id: ordinal}.

    The ordinal is the material's **declaration order** in the file, which is
    what the runtime reads `detail_index.tga` channels as (`verified`,
    ``docs/map_fidelity.md`` §1.3: where `snow_mask.png` is saturated the
    channel-0 index is `mountain_02_snow` = 46). Blocks in this file do not
    nest, so a non-nested brace-block regex is sufficient and cheap.
    """
    p = Path(path)
    if not p.exists():
        return {}
    txt = p.read_text(encoding="utf-8-sig", errors="replace")
    out: dict[str, int] = {}
    i = 0
    for blk in _BLOCK_RE.finditer(txt):
        m = _ID_RE.search(blk.group(1))
        if m:
            out.setdefault(m.group(1), i)
            i += 1
    return out


def build_layers(
    codes: np.ndarray,
    code_names: Sequence[str],
    *,
    material_map: dict[str, tuple[str, str]],
    ordinals: dict[str, int],
    mapping: dict[str, str] | None = None,
    default: str = "plains",
    quantize: int = 16,
    seed: int = 11,
    noise_sigma: float = 1.5,
    warn: Callable[[str], None] = lambda _m: None,
) -> PaintLayers:
    """Build the `detail_index`/`detail_intensity` RGBA pair.

    ``codes`` is a CK2-terrain-category code grid (:func:`ck2ck3.map.terrain
    .ck2_category_codes`, resized to whatever resolution the caller wants —
    normally the target canvas, so the paint lines up with `provinces.png`)
    and ``code_names`` names each code, code 0 always meaning "no category"
    (:func:`ck2ck3.map.terrain.category_codes`). Deterministic: the noise
    field is seeded, so two runs on the same input produce byte-identical
    output.
    """
    table = dict(CK2_TO_CK3_TERRAIN if mapping is None else mapping)
    ck3_of_code = [table.get(name, default) if name else default for name in code_names]

    missing_material: set[str] = set()
    missing_ordinal: set[str] = set()

    def _ordinals_for(ck3_key: str) -> tuple[int, int]:
        prim, sec = material_map.get(ck3_key, (None, None))
        if prim is None:
            missing_material.add(ck3_key)
            prim, sec = material_map.get(default, DEFAULT_MATERIALS)
        p_ord = ordinals.get(prim)
        if p_ord is None:
            missing_ordinal.add(prim)
            p_ord = 0
        s_ord = ordinals.get(sec)
        if s_ord is None:
            missing_ordinal.add(sec)
            s_ord = 0
        return p_ord, s_ord

    n = len(code_names)
    primary_lut = np.zeros(n, dtype=np.uint8)
    secondary_lut = np.zeros(n, dtype=np.uint8)
    for code, ck3_key in enumerate(ck3_of_code):
        p_ord, s_ord = _ordinals_for(ck3_key)
        primary_lut[code] = p_ord
        secondary_lut[code] = s_ord

    for name in sorted(missing_material):
        warn(
            f"terrain_paint: CK3 terrain '{name}' has no row in "
            "mappings/terrain_paint.csv; using the default material"
        )
    for name in sorted(missing_ordinal):
        warn(
            f"terrain_paint: material '{name}' is not declared in the vanilla "
            "materials.settings this run read; ordinal 0 used"
        )

    h, w = codes.shape
    idx = np.zeros((h, w, 4), dtype=np.uint8)
    idx[..., 0] = primary_lut[codes]
    idx[..., 1] = secondary_lut[codes]

    # Edge treatment: blend primary/secondary by a Gaussian-filtered noise
    # field so CK2's hard palette edges do not read as pixel art
    # (docs/map_fidelity.md §4.1). The field ignores class boundaries on
    # purpose - it is texture-space dithering, not a class-aware blend.
    rng = np.random.default_rng(seed)
    noise = gaussian_filter(
        rng.standard_normal((h, w)).astype(np.float32), noise_sigma
    )
    std = float(noise.std()) or 1.0
    noise = (noise - float(noise.mean())) / std
    weight = np.clip(0.72 + 0.22 * noise, 0.30, 0.98)
    step = max(1, int(quantize))
    q = np.round(weight * 255.0 / step) * step
    prim_w = np.clip(q, 1, 254).astype(np.uint8)

    inten = np.zeros((h, w, 4), dtype=np.uint8)
    inten[..., 0] = prim_w
    inten[..., 1] = 255 - prim_w

    total = inten[..., 0].astype(np.uint16) + inten[..., 1].astype(np.uint16)
    assert bool((total == 255).all()), "detail_intensity channels must sum to 255"

    counts = np.bincount(codes.reshape(-1), minlength=n)
    classes: dict[str, int] = {}
    for code, cnt in enumerate(counts.tolist()):
        if cnt:
            key = ck3_of_code[code]
            classes[key] = classes.get(key, 0) + cnt

    return PaintLayers(
        index=idx,
        intensity=inten,
        classes=classes,
        missing_material=sorted(missing_material),
        missing_ordinal=sorted(missing_ordinal),
        quantize=step,
    )


def save_tga(arr: np.ndarray, path: str | Path) -> None:
    """Write an RGBA layer as an uncompressed TGA, matching vanilla exactly.

    `verified` against the vanilla game folder: both shipped files are image
    type 2 (uncompressed truecolour), not RLE (type 10) — so this writer does
    not use PIL's ``rle=True`` option, which would ship a format CK3's own
    files never use.
    """
    Image.fromarray(arr, "RGBA").save(path, "TGA")
