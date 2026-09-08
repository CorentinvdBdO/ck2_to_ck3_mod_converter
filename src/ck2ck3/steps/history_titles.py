"""Step ``history_titles``: holders, lieges, laws, governments and holdings.

Owns ``history/titles`` and ``history/provinces``.  Both come from the same
CK2 files as the ``titles`` step and reuse its model, so a title is never
defined in one file and missing from the other.
"""

from __future__ import annotations

from ..context import Context, StepResult
from ..titles.text import with_bom
from ..titles import history, model, provinces

DESCRIPTION = "history/titles + history/provinces from CK2 history"

OUTPUTS: tuple[str, ...] = ("history/titles", "history/provinces")


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

    titles = history.render(
        data.title_history,
        history.HistoryConfig(
            government=data.government,
            characters=data.characters,
            live_titles=data.live_titles,
            dead_titles=data.dead_titles,
            spans=history.holder_spans(data.title_history),
            prefix=prefix,
        ),
    )
    for rel, text in sorted(titles.files.items()):
        ctx.write_text(rel, with_bom(ctx.header("CK2 history/titles") + text))
    if titles.loc:
        ctx.write_loc(
            f"localization/english/{prefix}_title_history_names_l_english.yml",
            dict(sorted(titles.loc.items())),
        )

    provs = provinces.render(
        histories=data.county_history,
        counties=data.counties,
        kingdom_of_county=data.kingdom_of_county,
        plan=data.plan,
        prefix=prefix,
    )
    for rel, text in sorted(provs.files.items()):
        ctx.write_text(rel, with_bom(ctx.header("CK2 history/provinces") + text))

    counts = dict(titles.counts)
    counts.update(provs.counts)
    warnings = titles.warnings + provs.warnings
    return StepResult(
        summary=(
            f"{titles.counts['titles_with_history']} title histories, "
            f"{titles.counts['history_commented_out']} commented out, "
            f"{provs.counts['province_blocks']} province blocks in "
            f"{provs.counts['files']} files"
        ),
        counts=counts,
        warnings=warnings[:200],
    )
