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
import struct
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

#: ``[map] terrain_paint_format`` candidates (docs/step_map_paint.md §size).
PAINT_FORMATS = ("tga", "tga_rle", "dds")


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


def save_tga(arr: np.ndarray, path: str | Path, *, rle: bool = False) -> None:
    """Write an RGBA layer as a TGA, plain (vanilla's own format) or RLE.

    `verified` against the vanilla game folder: vanilla's own shipped files
    are image type 2 (uncompressed truecolour), not RLE (type 10). But two
    installed workshop total conversions — Elder Kings 2 (`2887120253`) and
    Godherja (`2326030123`) — ship `detail_index.tga`/`detail_intensity.tga`
    as image type **10** (RLE), full `provinces.png` resolution, and both are
    functioning published mods (`verified` file-header bytes,
    `docs/step_map_paint.md` §size). ``rle=True`` uses PIL's RLE TGA writer,
    which produces the same image-type byte (`verified` by
    :func:`save_tga`'s own round-trip test).
    """
    Image.fromarray(arr, "RGBA").save(path, "TGA", rle=rle)


def load_tga(path: str | Path) -> np.ndarray:
    """Decode a TGA (plain or RLE) back to an HxWx4 uint8 RGBA array."""
    return np.asarray(Image.open(path).convert("RGBA"))


# --------------------------------------------------------------------------- #
# DDS — uncompressed BGRA8, DX9 header, no mipmaps
# --------------------------------------------------------------------------- #
#
# docs/step_map_paint.md §size documents why this candidate is implemented
# but unverified: the only two occurrences of the strings "detail_index" /
# "detail_intensity" anywhere in ck3.exe are next to a literal ".tga" and
# come from ``mapeditor_detail_data.cpp`` (the map editor's own mask-bake
# step) — no generic-extension search (like the one the mask-PNG loader logs,
# "png,bmp,tga") was found for this specific pair, so a same-name-override
# ``detail_index.dds`` may simply never be looked for. Implemented anyway per
# spec, self-consistent (round-trips through :func:`load_dds`), and its
# header is a standard uncompressed-ARGB8 DDS (DDPF_RGB|DDPF_ALPHAPIXELS,
# masks 0x00FF0000/0x0000FF00/0x000000FF/0xFF000000 — the layout most DDS
# tooling calls "A8R8G8B8"), stored top-down with B,G,R,A byte order per
# pixel (the mask layout implies that byte order; this module's arrays are
# RGBA, so channels 0 and 2 are swapped on the way in and out).

DDS_MAGIC = b"DDS "

#: magic(4s) + header(dwSize dwFlags dwHeight dwWidth dwPitchOrLinearSize
#: dwDepth dwMipMapCount) + dwReserved1[11] + pixelformat(dwSize dwFlags
#: dwFourCC dwRGBBitCount dwRBitMask dwGBitMask dwBBitMask dwABitMask) +
#: dwCaps dwCaps2 dwCaps3 dwCaps4 dwReserved2. 4 + 124 = 128 bytes total.
_DDS_STRUCT = struct.Struct("<4s7I11I8I5I")

_DDSD_CAPS = 0x1
_DDSD_HEIGHT = 0x2
_DDSD_WIDTH = 0x4
_DDSD_PITCH = 0x8
_DDSD_PIXELFORMAT = 0x1000
_DDPF_ALPHAPIXELS = 0x1
_DDPF_RGB = 0x40
_DDSCAPS_TEXTURE = 0x1000


def _dds_header(width: int, height: int) -> bytes:
    flags = _DDSD_CAPS | _DDSD_HEIGHT | _DDSD_WIDTH | _DDSD_PITCH | _DDSD_PIXELFORMAT
    return _DDS_STRUCT.pack(
        DDS_MAGIC,
        124,  # dwSize
        flags,
        height,
        width,
        width * 4,  # dwPitchOrLinearSize (uncompressed: bytes per scanline)
        0,  # dwDepth
        0,  # dwMipMapCount
        *([0] * 11),  # dwReserved1
        32,  # pixelformat.dwSize
        _DDPF_ALPHAPIXELS | _DDPF_RGB,  # pixelformat.dwFlags
        0,  # pixelformat.dwFourCC (unused: not compressed)
        32,  # pixelformat.dwRGBBitCount
        0x00FF0000,  # dwRBitMask
        0x0000FF00,  # dwGBitMask
        0x000000FF,  # dwBBitMask
        0xFF000000,  # dwABitMask
        _DDSCAPS_TEXTURE,  # dwCaps
        0, 0, 0,  # dwCaps2..4
        0,  # dwReserved2
    )


def save_dds(arr: np.ndarray, path: str | Path) -> None:
    """Write an RGBA layer as an uncompressed 32bpp BGRA8 DDS. See module
    docstring above for the header layout and why this candidate is
    unverified against the actual game."""
    h, w = arr.shape[0], arr.shape[1]
    bgra = np.ascontiguousarray(arr[..., (2, 1, 0, 3)])
    Path(path).write_bytes(_dds_header(w, h) + bgra.tobytes())


def load_dds(path: str | Path) -> np.ndarray:
    """Decode a DDS written by :func:`save_dds` back to an HxWx4 RGBA array."""
    raw = Path(path).read_bytes()
    fields = _DDS_STRUCT.unpack(raw[: _DDS_STRUCT.size])
    magic = fields[0]
    if magic != DDS_MAGIC:
        raise ValueError(f"not a DDS file: magic {magic!r}")
    height, width = fields[3], fields[4]
    pixels = raw[_DDS_STRUCT.size :]
    bgra = np.frombuffer(pixels, dtype=np.uint8, count=height * width * 4)
    bgra = bgra.reshape(height, width, 4)
    return np.ascontiguousarray(bgra[..., (2, 1, 0, 3)])


def paint_ext(fmt: str) -> str:
    """File extension for a ``[map] terrain_paint_format`` value."""
    if fmt not in PAINT_FORMATS:
        raise ValueError(f"unknown terrain_paint_format {fmt!r}, want one of {PAINT_FORMATS}")
    return "dds" if fmt == "dds" else "tga"


def save_paint(arr: np.ndarray, path: str | Path, fmt: str) -> None:
    """Dispatch to the writer for ``[map] terrain_paint_format``."""
    if fmt == "tga":
        save_tga(arr, path, rle=False)
    elif fmt == "tga_rle":
        save_tga(arr, path, rle=True)
    elif fmt == "dds":
        save_dds(arr, path)
    else:
        raise ValueError(f"unknown terrain_paint_format {fmt!r}, want one of {PAINT_FORMATS}")


def load_paint(path: str | Path, fmt: str) -> np.ndarray:
    """Dispatch to the reader for ``[map] terrain_paint_format``."""
    if fmt in ("tga", "tga_rle"):
        return load_tga(path)
    if fmt == "dds":
        return load_dds(path)
    raise ValueError(f"unknown terrain_paint_format {fmt!r}, want one of {PAINT_FORMATS}")


# --------------------------------------------------------------------------- #
# downsample — [map] terrain_paint_scale
# --------------------------------------------------------------------------- #
def downsample_index(arr: np.ndarray, scale: float) -> np.ndarray:
    """Nearest-neighbour resample of the ``detail_index`` layer.

    The only method safe for an ordinal layer: interpolating two material
    ordinals (say 12 and 46) would invent a bogus intermediate material (29)
    that may not even exist. ``scale`` of 0.5 halves both dimensions.
    """
    h, w = arr.shape[:2]
    nh = max(1, round(h * scale))
    nw = max(1, round(w * scale))
    yi = np.minimum((np.arange(nh) / scale).astype(np.int64), h - 1)
    xi = np.minimum((np.arange(nw) / scale).astype(np.int64), w - 1)
    return arr[yi][:, xi]


def downsample_intensity(arr: np.ndarray, scale: float) -> np.ndarray:
    """Box-filter resample of the ``detail_intensity`` layer.

    Averages **all four** channels over each ``factor x factor`` block
    (``factor = round(1/scale)``) and then re-normalises the pixel so the
    four still sum to exactly 255 — independent rounding of four box averages
    need not, and the runtime's ``materials_limit`` contract requires it
    (`build_layers` / `paint_edges.build_soft_blend` assert it on the
    full-resolution pair; this keeps the invariant across a downsample too).

    Lane `paint-edges` changed this from "average channel 0 and derive
    channel 1 as its complement": that shortcut silently deleted channels 2
    and 3, which the soft-edge blend actually uses (a class interior carries
    three materials, a boundary four). It is still correct for the old
    two-channel layer, which simply has zeros in 2/3.
    """
    factor = round(1.0 / scale)
    if factor < 1:
        raise ValueError(f"terrain_paint_scale must be <= 1.0, got {scale}")
    h, w = arr.shape[:2]
    nh, nw = h // factor, w // factor
    trimmed = arr[: nh * factor, : nw * factor, :4].astype(np.float64)
    boxed = trimmed.reshape(nh, factor, nw, factor, 4).mean(axis=(1, 3))
    flat = boxed.reshape(-1, 4)
    total = np.maximum(flat.sum(axis=1, keepdims=True), 1e-9)
    q = np.rint(flat / total * 255.0).astype(np.int32)
    lead = np.argmax(q, axis=1)
    rows = np.arange(q.shape[0])
    q[rows, lead] += 255 - q.sum(axis=1)
    np.clip(q, 0, 255, out=q)
    return q.astype(np.uint8).reshape(nh, nw, 4)
