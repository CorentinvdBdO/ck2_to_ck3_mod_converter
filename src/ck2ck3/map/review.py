"""Per-duchy review sheets: what the barony split actually did, as a PNG.

The barony method is only as good as the human loop around it
(``docs/design_map.md`` §B.6).  This module draws one small PNG per CK2 duchy —
county outlines in white, barony fills in their ``definition.csv`` colour, a
black dot on each seed, and the barony id next to it — so a reviewer can see a
bad seed and fix it with one row in ``overrides/barony_seeds.csv``.

Kept deliberately cheap: each sheet is cropped to the duchy's bounding box,
integer-upscaled if it came out under ``min_px`` (a small duchy crops to ~100 px,
where a 6 px bitmap label is unreadable) and capped at ``max_px`` on the long
edge.  Faerûn's 622 land-owning duchies come to 7.2 MB in ~90 s, so
``docs/evidence/baronies/*.png`` is gitignored except for the index and the
sample sheets named in it.

Text is drawn with PIL's built-in bitmap font: no font file to ship, no
dependency.  Both the dots and the labels are drawn *after* the resampling, so
they are never blown up or blurred with the pixels underneath.
"""

from __future__ import annotations

import io
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from .baronies import Barony, BaronyPlan
from .ck2titles import Ck2TitleTree, read_dir
from .config import MapConfig
from .idmap import IdMap

Image.MAX_IMAGE_PIXELS = None

#: longest edge of a written sheet, in pixels
MAX_PX = 1024
#: a sheet smaller than this is integer-upscaled first, so the labels fit
MIN_PX = 512
#: white county outline
OUTLINE = (255, 255, 255)
#: seed dot and label
INK = (0, 0, 0)


def load_tree(cfg: MapConfig) -> Ck2TitleTree:
    """Read the CK2 title hierarchy the sheets are grouped by."""
    mod = cfg.ck2_mod_dir or cfg.ck2_map_dir.parent
    return read_dir(mod / "common" / "landed_titles")


@dataclass
class Sheet:
    duchy: str
    counties: list[str]
    baronies: list[Barony]
    demoted: list[Barony]
    png: bytes = b""
    width: int = 0
    height: int = 0


def group_by_duchy(
    plan: BaronyPlan, tree: Ck2TitleTree
) -> dict[str, list[Barony]]:
    """CK2 duchy key -> its placed baronies, hierarchy order.

    A county whose duchy cannot be found (a titular county, or one the mod
    declares outside a duchy) is filed under ``d_unassigned`` rather than
    dropped: a review sheet nobody can find is worse than an ugly one.
    """
    out: dict[str, list[Barony]] = {}
    for b in sorted(plan.placed, key=lambda x: (x.order, x.key)):
        title = tree.titles.get(b.county)
        duchy = (title.ancestor("d") if title else None) or "d_unassigned"
        out.setdefault(duchy, []).append(b)
    return out


@dataclass(frozen=True)
class SheetIndex:
    """Lookups every sheet needs, built once for the whole run.

    Built once because the naive version — scanning ``ids.provinces`` for each
    barony of each duchy — is 3,857 x 6,000 comparisons per run and dominated
    the whole step.
    """

    #: (barony key, CK2 province) -> CK3 province id
    province_of: dict[tuple[str, int], int]
    #: CK3 id -> RGB, as a lookup array
    colours: np.ndarray
    #: CK3 id -> county code (0 = no county), as a lookup array
    county_codes: np.ndarray

    @classmethod
    def build(cls, ids: IdMap) -> "SheetIndex":
        max_id = max(p.id for p in ids.provinces)
        colours = np.zeros((max_id + 1, 3), dtype=np.uint8)
        county_codes = np.zeros(max_id + 1, dtype=np.int32)
        province_of: dict[tuple[str, int], int] = {}
        seen: dict[str, int] = {}
        for p in ids.provinces:
            colours[p.id] = p.rgb
            if p.county:
                county_codes[p.id] = seen.setdefault(p.county, len(seen) + 1)
            if p.barony and p.ck2_id is not None:
                province_of[(p.barony, p.ck2_id)] = p.id
        return cls(
            province_of=province_of, colours=colours, county_codes=county_codes
        )


def render_sheet(
    duchy: str,
    baronies: Sequence[Barony],
    demoted: Sequence[Barony],
    *,
    raster: np.ndarray,
    index: SheetIndex,
    max_px: int = MAX_PX,
    min_px: int = MIN_PX,
    margin: int = 8,
    background: tuple[int, int, int] = (24, 24, 32),
) -> Sheet:
    """One duchy's review PNG, cropped to its baronies' bounding box."""
    empty = Sheet(
        duchy=duchy,
        counties=sorted({b.county for b in baronies}),
        baronies=list(baronies),
        demoted=list(demoted),
    )
    ck3_ids = [
        index.province_of[(b.key, b.ck2_province)]
        for b in baronies
        if (b.key, b.ck2_province) in index.province_of
    ]
    if not ck3_ids:
        return empty

    mask = np.isin(raster, ck3_ids)
    ys, xs = np.nonzero(mask)
    if ys.size == 0:
        return empty
    y0 = max(0, int(ys.min()) - margin)
    y1 = min(raster.shape[0], int(ys.max()) + margin + 1)
    x0 = max(0, int(xs.min()) - margin)
    x1 = min(raster.shape[1], int(xs.max()) + margin + 1)
    sub = raster[y0:y1, x0:x1]

    inside = np.isin(sub, ck3_ids)
    rgb = index.colours[np.clip(sub, 0, index.colours.shape[0] - 1)]
    rgb = np.where(inside[..., None], rgb, np.array(background, dtype=np.uint8))

    # county outline: a pixel whose right or lower neighbour is another county
    counties = index.county_codes[np.clip(sub, 0, index.county_codes.size - 1)]
    edge = np.zeros(counties.shape, dtype=bool)
    edge[:, :-1] |= counties[:, :-1] != counties[:, 1:]
    edge[:-1, :] |= counties[:-1, :] != counties[1:, :]
    rgb[edge & inside] = OUTLINE

    # A small duchy crops to ~100 px, where a 6 px bitmap label is unreadable.
    # Upscale by an integer factor *before* drawing the overlay, so the dots and
    # the text are drawn at their own size on top of enlarged pixels rather than
    # being blown up with them.
    up = max(1, -(-min_px // max(rgb.shape[0], rgb.shape[1])))
    if up > 1:
        rgb = np.repeat(np.repeat(rgb, up, axis=0), up, axis=1)

    img = Image.fromarray(rgb.astype(np.uint8), mode="RGB")
    draw = ImageDraw.Draw(img)
    for b in baronies:
        if b.seed_y < 0:
            continue
        sy, sx = (b.seed_y - y0) * up, (b.seed_x - x0) * up
        if not (0 <= sy < img.height and 0 <= sx < img.width):
            continue
        draw.ellipse((sx - 3, sy - 3, sx + 3, sy + 3), fill=INK, outline=OUTLINE)
        draw.text((sx + 5, sy - 5), b.key[2:], fill=INK, stroke_width=1,
                  stroke_fill=OUTLINE)

    scale = min(1.0, max_px / max(img.width, img.height))
    if scale < 1.0:
        img = img.resize(
            (max(1, int(img.width * scale)), max(1, int(img.height * scale))),
            Image.NEAREST,
        )
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return Sheet(
        duchy=duchy,
        counties=empty.counties,
        baronies=list(baronies),
        demoted=list(demoted),
        png=buf.getvalue(),
        width=img.width,
        height=img.height,
    )


def write_all(
    *,
    out_dir: Path,
    plan: BaronyPlan,
    ids: IdMap,
    raster: np.ndarray,
    tree: Ck2TitleTree,
    max_px: int = MAX_PX,
    log: Callable[[str], None] = lambda _m: None,
    samples: Sequence[str] = (),
) -> int:
    """Write every duchy sheet plus ``index.md``. Returns the number of PNGs."""
    out_dir.mkdir(parents=True, exist_ok=True)
    grouped = group_by_duchy(plan, tree)
    demoted_by_duchy: dict[str, list[Barony]] = {}
    for b in plan.demoted:
        title = tree.titles.get(b.county)
        duchy = (title.ancestor("d") if title else None) or "d_unassigned"
        demoted_by_duchy.setdefault(duchy, []).append(b)

    index = SheetIndex.build(ids)
    written = 0
    rows: list[Sheet] = []
    for duchy in sorted(grouped):
        sheet = render_sheet(
            duchy,
            grouped[duchy],
            demoted_by_duchy.get(duchy, []),
            raster=raster,
            index=index,
            max_px=max_px,
        )
        if sheet.png:
            (out_dir / f"{duchy}.png").write_bytes(sheet.png)
            written += 1
            if written % 100 == 0:
                log(f"{written} sheets written")
        rows.append(sheet)
    (out_dir / "index.md").write_text(
        render_index(rows, plan, samples=samples), encoding="utf-8"
    )
    return written


def render_index(
    sheets: Sequence[Sheet], plan: BaronyPlan, *, samples: Sequence[str] = ()
) -> str:
    """``docs/evidence/baronies/index.md`` — the reviewer's entry point."""
    total = sum(len(s.baronies) for s in sheets)
    demoted = sum(len(s.demoted) for s in sheets)
    lines = [
        "# Barony review sheets",
        "",
        "One PNG per CK2 duchy: county outlines white, barony fills in their",
        "`map_data/definition.csv` colour, a dot on each seed, the barony id next",
        "to it. Generated by `uv run scripts/barony_review_sheets.py`.",
        "",
        f"- duchies: **{len(sheets)}**",
        f"- baronies placed: **{total}**",
        f"- baronies demoted to comments: **{demoted}**",
        f"- counties with demotions: **{len(plan.counties_with_demotions())}**",
        f"- seed sources: {', '.join(f'{k} {v}' for k, v in sorted(plan.seed_counts.items()))}",
        "",
        "The PNGs are gitignored except the samples below; regenerate the rest.",
        "",
    ]
    if samples:
        lines += ["## Committed samples", ""]
        lines += [f"- `{s}.png`" for s in samples]
        lines += [""]
    lines += [
        "## Counties with demotions",
        "",
        "A demoted holding has no CK3 province: the county could not hold one more",
        "barony of `min_barony_pixels`. It stays in `docs/evidence/barony_set.csv`",
        "with status `demoted` so the titles lane emits it as a commented barony.",
        "",
        "| duchy | county | demoted baronies |",
        "|---|---|---|",
    ]
    any_row = False
    for s in sheets:
        by_county: dict[str, list[str]] = {}
        for b in s.demoted:
            by_county.setdefault(b.county, []).append(b.key)
        for county in sorted(by_county):
            any_row = True
            lines.append(
                f"| `{s.duchy}` | `{county}` | {', '.join(sorted(by_county[county]))} |"
            )
    if not any_row:
        lines.append("| — | — | no county lost a holding |")
    lines.append("")
    return "\n".join(lines)
