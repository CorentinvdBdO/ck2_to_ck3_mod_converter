"""Step ``titles``: the CK3 de jure title tree and its placeholder coats of arms.

Owns ``common/landed_titles`` and ``common/coat_of_arms/coat_of_arms``.  The
history of those titles is the ``history_titles`` step and the bookmarks are
the ``bookmarks`` step; all three share one parse of the CK2 side through
:mod:`ck2ck3.titles.model`.

Rules and evidence: ``docs/step_titles.md``, ``docs/formats_titles.md``,
``mappings/title_fields.csv``.
"""

from __future__ import annotations

from ..context import Context, StepResult
from ..titles.text import with_bom
from ..titles import coa, landed, model

DESCRIPTION = "common/landed_titles + placeholder coats of arms from CK2 landed_titles"

OUTPUTS: tuple[str, ...] = (
    "common/landed_titles",
    "common/coat_of_arms/coat_of_arms",
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

    result = landed.render(
        data.roots,
        landed.LandedConfig(
            plan=data.plan,
            county_of_province=data.county_of_province,
            by_id=data.by_id,
            live_titles=data.live_titles,
            dead_titles=data.dead_titles,
            name_list_of_culture=data.name_list_of_culture,
            culture_groups=data.culture_groups,
            own_county=data.own_county,
            placeholder_capital=data.placeholder_capital,
            prefix=prefix,
        ),
    )
    ctx.write_text(
        f"common/landed_titles/{prefix}_landed_titles.txt",
        with_bom(ctx.header("CK2 common/landed_titles") + result.text),
    )
    if result.loc:
        ctx.write_loc(
            f"localization/english/{prefix}_title_cultural_names_l_english.yml",
            dict(sorted(result.loc.items())),
        )

    arms = coa.render(
        data.flat,
        live=data.live_titles,
        flags_dir=ctx.ck2("gfx", "flags"),
        prefix=prefix,
    )
    ctx.write_text(
        f"common/coat_of_arms/coat_of_arms/{prefix}_titles.txt",
        with_bom(ctx.header("CK2 landed_titles colours") + arms.text),
    )

    evidence = model.repo_root(ctx) / "docs" / "evidence"
    if not ctx.dry_run:
        evidence.mkdir(parents=True, exist_ok=True)
        (evidence / "ck2_flags.csv").write_text(
            coa.flags_csv(arms.flags), encoding="utf-8"
        )
        (evidence / "title_holy_sites.csv").write_text(
            "title,ck2_religion\n"
            + "".join(f"{t},{r}\n" for t, r in sorted(result.holy_sites)),
            encoding="utf-8",
        )
        (evidence / "title_flavorization.csv").write_text(
            "title,ck2_key,value\n"
            + "".join(
                f'{t},{k},"{v}"\n' for t, k, v in sorted(result.flavorization)
            ),
            encoding="utf-8",
        )
        # grouped, not one row per title: the bulk of the 13k commented
        # baronies share one reason and the whole set is replaced when lane
        # `baronies` publishes barony_set.csv.
        grouped: dict[str, list[str]] = {}
        for title, reason in sorted(result.commented):
            grouped.setdefault(reason, []).append(title)
        (evidence / "titles_commented_out.csv").write_text(
            "reason,count,first_ten\n"
            + "".join(
                f'"{reason}",{len(ids)},"{" ".join(ids[:10])}"\n'
                for reason, ids in sorted(grouped.items(), key=lambda kv: -len(kv[1]))
            ),
            encoding="utf-8",
        )

    counts = dict(result.counts)
    counts.update(arms.counts)
    counts.update(
        {f"placement_{k}": v for k, v in sorted(data.plan.counts().items())}
    )
    live = sum(len(v) for v in result.emitted.values())
    return StepResult(
        summary=(
            f"{live} CK3 titles ({result.counts.get('e_titles', 0)} e_, "
            f"{result.counts.get('k_titles', 0)} k_, "
            f"{result.counts.get('d_titles', 0)} d_, "
            f"{result.counts.get('c_titles', 0)} c_, "
            f"{result.counts.get('b_titles', 0)} b_), "
            f"{len(result.commented)} commented out, "
            f"placement mode {data.plan.mode}"
        ),
        counts=counts,
        warnings=result.warnings,
    )
