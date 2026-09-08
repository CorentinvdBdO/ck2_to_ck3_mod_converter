"""Step ``bookmarks``: CK2 ``common/bookmarks`` -> CK3 ``common/bookmarks``.

Owns ``common/bookmarks``.  It also shadows vanilla's three bookmark files by
filename, because they name vanilla titles and characters that do not exist on
this map (``docs/output_bootstrap.md`` fact 0.2).
"""

from __future__ import annotations

from ..context import Context, StepResult
from ..titles.text import with_bom
from ..titles import bookmarks as bm
from ..titles import model

DESCRIPTION = "common/bookmarks (+ groups) from CK2 common/bookmarks"

OUTPUTS: tuple[str, ...] = ("common/bookmarks", "common/bookmark_portraits")


def run(ctx: Context) -> StepResult:
    data = model.load(ctx)
    if not data.flat:
        return StepResult(
            summary=(
                "skipped: no titles in "
                f"{ctx.ck2('common', 'landed_titles')} (nothing to convert)"
            ),
            skipped=True,
        )
    prefix = ctx.config.prefix
    result = bm.render(
        data.bookmarks,
        characters=data.characters,
        live_titles=data.live_titles,
        default_date=ctx.config.bookmark_date,
        government_map=data.government_map,
        prefix=prefix,
    )
    for rel, text in sorted(result.files.items()):
        # CK3 wants a UTF-8 BOM on common/bookmarks script files: vanilla's
        # 00_bookmarks.txt has one and ck3-tiger reports
        # warning(encoding): "Expected UTF-8 BOM encoding" without it.
        ctx.write_text(rel, with_bom(bm.BOM + text))
    if result.loc:
        ctx.write_loc(
            f"localization/english/{prefix}_bookmarks_l_english.yml",
            dict(sorted(result.loc.items())),
        )
    return StepResult(
        summary=(
            f"{result.counts['bookmarks']} bookmarks, "
            f"{result.counts['bookmark_characters']} characters, default "
            f"{ctx.config.bookmark_date}"
        ),
        counts=result.counts,
        warnings=result.warnings[:100],
    )
