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

OUTPUTS: tuple[str, ...] = (
    "history/titles",
    "history/provinces",
    "history/province_mapping",
)


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

    spans = history.holder_spans(data.title_history)
    # hand-off to the characters step: who is landed when (employer validity)
    ctx.data["titles"] = {"landed": history.landed_intervals(spans)}
    titles = history.render(
        data.title_history,
        history.HistoryConfig(
            government=data.government,
            characters=data.characters,
            live_titles=data.live_titles,
            dead_titles=data.dead_titles,
            spans=spans,
            prefix=prefix,
            capital_baronies=frozenset(
                baronies[0]
                for baronies in data.plan.by_county.values()
                if baronies
            ),
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

    # history/province_mapping must not be empty. The province-history loader
    # binary-searches this table and dereferences its begin pointer even when
    # the count is zero (ck3.exe 1.19.0.6 @0x14207f7b1, bisected 2026-09-08:
    # any province block crashed the game until one mapping line existed;
    # Godherja ships a single `6 = 20` for the same reason). One entry between
    # two placed baronies of the same county is the least intrusive content.
    mapping = _province_mapping_entry(data.plan)
    if mapping is not None:
        target, source, county = mapping
        ctx.write_text(
            f"history/province_mapping/{prefix}_province_mapping.txt",
            with_bom(
                ctx.header("engine requirement, not CK2 data")
                + "# The CK3 province-history loader crashes on an EMPTY province_mapping\n"
                + "# table (null begin pointer, verified 2026-09-08 against 1.19.0.6).\n"
                + "# Vanilla, Elder Kings 2 and Godherja all ship at least one entry.\n"
                + f"# Two placed baronies of {county}; both keep their own history.\n"
                + f"{target} = {source}\n"
            ),
        )
    else:
        ctx.warn("province_mapping: no county with two placed baronies; table left empty (game will crash on load)")

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


def _province_mapping_entry(plan) -> tuple[int, int, str] | None:
    """Two placed baronies of one county, as ``(target, source, county)``.

    Deterministic: the first county in plan order with two placed baronies.
    """
    for county, baronies in plan.by_county.items():
        provinces = [
            plan.by_barony[b].province
            for b in baronies
            if plan.by_barony.get(b) is not None and plan.by_barony[b].province is not None
        ]
        if len(provinces) >= 2:
            return provinces[1], provinces[0], county
    return None
