"""CK2 religion groups / religions → CK3 families, religions, faiths, holy sites.

Field-by-field source: `mappings/religion_fields.csv` (78 rows). Method and every
default this module invents are written up in `docs/step_cultures_religions.md`.

Structure (`docs/mapping_world.md` "Structural mapping"):

* CK2 religion group (15) → one CK3 **religion family** *and* one CK3
  **religion** (the object owning `faiths = { }`); the pair is 1:1, which is the
  mechanical way to fill a level CK2 does not have.
* CK2 religion (94) → one CK3 **faith**, with all 23 mandatory doctrine groups
  plus 3 core tenets.
* CK2 title `holy_site = <religion>` → a `holy_site_type` object plus a
  `holy_site =` line on the faith: the relation is **inverted**.

CK2 keys with no CK3 equivalent become a comment inside the block, shaped
``# CK2: key = value (no CK3 equivalent: note)``.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

from .. import overrides
from ..config import REPO_ROOT
from ..context import Context, StepResult
from ..pdx import Block, Item, Node, parse_file
from ..pdx.encoding import CK3_ENCODING
from . import cultures as cultures_step

DESCRIPTION = (
    "religions: CK2 religion groups/religions -> CK3 religion families, "
    "religions, faiths and holy sites"
)
OUTPUTS: tuple[str, ...] = (
    "common/religion/religion_types",
    "common/religion/religion_family_types",
    "common/religion/holy_site_types",
    "common/modifier_definition_formats/fae_faith_opinions.txt",
)

#: A CK2 religion-group child block is a *religion* when it carries one of
#: these. `verified`: 94/94 Faerûn religions define `scripture_name` and
#: `evil_god_names`; no group-level block key does. Needed because
#: `interface_skin = { }` and `color = { }` sit at the same brace depth.
RELIGION_MARKERS = ("scripture_name", "evil_god_names", "god_names", "high_god_name")

#: Where the 23 mandatory doctrine groups get their value when no CK2 flag
#: decides it. Straight from vanilla `paganism_religion`
#: (`common/religion/religion_types/00_paganism.txt:1-40`), the safest doctrine
#: set for a polytheistic pantheon — see `mappings/religion_fields.csv`,
#: section `minimal_faith`.
PAGANISM_DEFAULTS: dict[str, str] = {
    "hostility_group": "pagan_hostility_doctrine",
    "doctrine_theism": "doctrine_polytheist",
    "doctrine_head_of_faith": "doctrine_no_head",
    "doctrine_gender": "doctrine_gender_male_dominated",
    "doctrine_pluralism": "doctrine_pluralism_pluralistic",
    "doctrine_theocracy": "doctrine_theocracy_temporal",
    "doctrine_marriage_type": "doctrine_concubines",
    "doctrine_divorce": "doctrine_divorce_allowed",
    "doctrine_bastardry": "doctrine_bastardry_legitimization",
    "doctrine_consanguinity": "doctrine_consanguinity_cousins",
    "doctrine_homosexuality": "doctrine_homosexuality_shunned",
    "doctrine_adultery_men": "doctrine_adultery_men_crime",
    "doctrine_adultery_women": "doctrine_adultery_women_crime",
    "doctrine_kinslaying": "doctrine_kinslaying_close_kin_crime",
    "doctrine_deviancy": "doctrine_deviancy_crime",
    "doctrine_witchcraft": "doctrine_witchcraft_accepted",
    "doctrine_clerical_function": "doctrine_clerical_function_recruitment",
    "doctrine_clerical_gender": "doctrine_clerical_gender_either",
    "doctrine_clerical_marriage": "doctrine_clerical_marriage_allowed",
    "doctrine_clerical_succession": "doctrine_clerical_succession_temporal_appointment",
    "doctrine_pilgrimage": "doctrine_pilgrimage_encouraged",
    "doctrine_funeral": "doctrine_funeral_cremation",
    "doctrine_coronation": "doctrine_no_anointment",
}

#: Emitted on the religion, so all its faiths inherit them; a faith only repeats
#: a doctrine when a CK2 flag makes it differ.
RELIGION_LEVEL_GROUPS = (
    "hostility_group",
    "doctrine_theocracy",
    "doctrine_bastardry",
    "doctrine_homosexuality",
    "doctrine_adultery_men",
    "doctrine_adultery_women",
    "doctrine_kinslaying",
    "doctrine_deviancy",
    "doctrine_witchcraft",
    "doctrine_clerical_function",
    "doctrine_pilgrimage",
    "doctrine_funeral",
    "doctrine_coronation",
)

#: `docs/DECISIONS.md`: default core tenets, overridable per faith in
#: `overrides/faith_tenets.csv`. `assumed` — CK2 has no tenet concept.
DEFAULT_TENETS = (
    "tenet_ritual_celebrations",
    "tenet_sanctity_of_nature",
    "tenet_ancestor_worship",
)

#: CK2 flag → the CK3 core tenet it justifies, in priority order. A flag-derived
#: tenet displaces a default one, because it is CK2 data rather than a guess.
TENET_OF_FLAG = (
    ("pacifist", "tenet_pacifism"),
    ("allow_looting", "tenet_warmonger"),
    ("divine_blood", "tenet_mystical_birthright"),
    ("autocephaly", "tenet_pentarchy"),
    ("can_retire_to_monastery", "tenet_monasticism"),
)

#: Only 10 `graphical_faith` values exist unless the mod ships temple assets;
#: `pagan_gfx` is the right one for a polytheistic pantheon
#: (`mappings/religion_fields.csv`).
DEFAULT_GRAPHICAL_FAITH = "pagan_gfx"
DEFAULT_PIETY_ICON_GROUP = "pagan"
DEFAULT_DOCTRINE_BACKGROUND = "core_tenet_banner_pagan.dds"
HOSTILITY_DOCTRINE = "pagan_hostility_doctrine"

#: A faith carrying `unreformed_faith_doctrine` **must** also set
#: `reformed_icon` — `verified`: ck3-tiger reports
#: `fatal(field-missing): required field reformed_icon missing` without it.
#: The value is an icon file name; the only ones that exist are vanilla's 43
#: `*_reformed.dds`, so the generic pagan one is used until the assets lane
#: slices Faerûn's own icon atlas.
DEFAULT_REFORMED_ICON = "pagan_reformed"

#: Where the religion-level 128-key `localization` baseline is copied from.
LOCALIZATION_SOURCE = ("common", "religion", "religion_types", "00_paganism.txt")
LOCALIZATION_SOURCE_ID = "paganism_religion"

NO_CK3_EQUIVALENT = {
    "heresy_icon": "CK3 has no separate heresy icon; heresies are ordinary faiths",
    "religious_clothing_head": (
        "CK2 2D clergy vestment sprite; CK3 clergy clothing comes from the "
        "culture's clothing_gfx"
    ),
    "religious_clothing_priest": (
        "CK2 2D clergy vestment sprite; CK3 clergy clothing comes from the "
        "culture's clothing_gfx"
    ),
    "piety_name": "CK3 only lets you swap the piety ICON SET, not the resource name",
    "interface_skin": "CK3 has no per-faith interface skin",
    "matrilineal_marriages": "CK3 always allows matrilineal marriage",
    "can_grant_claim": "CK3 head-of-faith interactions are fixed",
    "can_demand_religious_conversion": "conversion is always available in CK3",
    "can_call_crusade": (
        "CK3 great holy wars are gated on doctrine_pluralism_* and a head of "
        "faith, not a boolean"
    ),
    "crusade_cb": "CK3 GHWs are configured in common/religion/great_holy_wars",
    "allow_viking_invasion": "CK3 has no prepared-invasion CB tied to a faith",
    "allow_rivermovement": "in CK3 river travel is a wanua_government flag",
    "seafarer": "in CK3 this is a culture property (tradition_seafaring)",
    "defensive_attrition": "CK3 has no faith-based attrition",
    "ignores_defensive_attrition": "CK3 has no faith-based attrition",
    "hard_to_convert": "no CK3 key; a fundamentalist faith resists conversion",
    "features": "CK2 2.8 religion_features sub-system; no CK3 equivalent",
    "allow_in_ruler_designer": "no per-faith ruler-designer gating in CK3",
    "playable": "CK3 playability is a game rule, not a religion property",
    "has_coa_on_barony_only": "CK2 temple-holding CoA display flag",
    "secret_religion": "CK3 replaces secret religions with common/secret_types",
    "dynamic_cult": "CK3 replaces secret religions with common/secret_types",
    "alternate_start": "no CK3 random world",
    "ai_peaceful": "CK2 AI tuning; no CK3 faith key",
    "ai_fabricate_claims": "CK2 AI tuning; no CK3 faith key",
    "aggression": "CK2 AI tuning; no CK3 faith key",
    "ai_convert_same_group": "CK3 AI conversion follows the hostility doctrine",
    "ai_convert_other_group": "CK3 AI conversion follows the hostility doctrine",
    "peace_prestige_loss": "hardcoded CK2 knob with no CK3 faith key",
    "peace_piety_gain": "hardcoded CK2 knob with no CK3 faith key",
    "attacking_same_religion_piety_loss": "hardcoded CK2 knob with no CK3 faith key",
    "raised_vassal_opinion_loss": "hardcoded CK2 knob with no CK3 faith key",
    "landed_kin_prestige_bonus": "hardcoded CK2 knob with no CK3 faith key",
    "independence_war_score_bonus": "no CK3 modifier of this kind exists at all",
    "short_reign_opinion_year_mult": "hardcoded CK2 knob with no CK3 faith key",
    "dislike_tribal_organization": "hardcoded CK2 knob with no CK3 faith key",
    "join_crusade_if_bordering_hostile": "CK2 AI tuning; no CK3 faith key",
    "has_heir_designation": (
        "CK3 makes this a title succession law (history/titles), not a faith key"
    ),
    "uses_decadence": "CK3 has no decadence",
    "character_modifier": (
        "a CK3 faith cannot carry a modifier; it needs a generated carrier "
        "doctrine in common/religion/doctrine_types, which this step does not own"
    ),
    "unit_modifier": (
        "a CK3 faith cannot carry a modifier; it needs a generated carrier "
        "doctrine in common/religion/doctrine_types, which this step does not own"
    ),
    "unit_home_modifier": (
        "a CK3 faith cannot carry a modifier; it needs a generated carrier "
        "doctrine in common/religion/doctrine_types, which this step does not own"
    ),
    "male_names": (
        "CK2 lists names GIVEN to followers; CK3 reserved_*_names lists names "
        "withheld from others - inverted semantics, not converted"
    ),
    "female_names": (
        "CK2 lists names GIVEN to followers; CK3 reserved_*_names lists names "
        "withheld from others - inverted semantics, not converted"
    ),
    "secret_religion_visibility_trigger": (
        "CK3 replaces secret religions with common/secret_types"
    ),
}


# -- CK2 reading ------------------------------------------------------------
@dataclass
class CK2Religion:
    id: str
    block: Block
    group: "CK2ReligionGroup" = field(repr=False, default=None)  # type: ignore[assignment]

    def flag(self, key: str) -> bool | None:
        value = self.block.get(key)
        return value if isinstance(value, bool) else None

    def number(self, key: str) -> int:
        value = self.block.get(key)
        return value if isinstance(value, int) and not isinstance(value, bool) else 0

    @property
    def intermarry(self) -> list[str]:
        return [str(v) for v in self.block.get_all("intermarry")]

    @property
    def god_names(self) -> list[str]:
        value = self.block.get("god_names")
        return [str(v) for v in value.list_values()] if isinstance(value, Block) else []

    @property
    def evil_god_names(self) -> list[str]:
        value = self.block.get("evil_god_names")
        return [str(v) for v in value.list_values()] if isinstance(value, Block) else []

    @property
    def reformed_into(self) -> str | None:
        value = self.block.get("reformed")
        return str(value) if value else None


@dataclass
class CK2ReligionGroup:
    id: str
    source: str
    block: Block
    religions: list[CK2Religion] = field(default_factory=list)

    @property
    def slug(self) -> str:
        return group_slug(self.id)

    @property
    def hostile_within_group(self) -> bool:
        return self.block.get("hostile_within_group") is True


def group_slug(group_id: str) -> str:
    """`good_human_pantheon_group` → `good_human_pantheon`."""
    return group_id[: -len("_group")] if group_id.endswith("_group") else group_id


def read_ck2_religions(ck2_mod: Path) -> list[CK2ReligionGroup]:
    groups: list[CK2ReligionGroup] = []
    folder = ck2_mod / "common" / "religions"
    for path in sorted(folder.glob("*.txt")):
        doc = parse_file(path)
        for entry in doc.entries:
            if not isinstance(entry, Node) or not isinstance(entry.value, Block):
                continue
            if entry.key in NO_CK3_EQUIVALENT:  # secret_religion_visibility_trigger
                continue
            group = CK2ReligionGroup(id=entry.key, source=path.name, block=entry.value)
            for child in entry.value.entries:
                if not isinstance(child, Node) or not isinstance(child.value, Block):
                    continue
                if not any(m in child.value for m in RELIGION_MARKERS):
                    continue
                group.religions.append(
                    CK2Religion(id=child.key, block=child.value, group=group)
                )
            groups.append(group)
    return groups


#: Where the `map` step records which counties actually got a barony. This
#: step runs before `titles`, so it cannot ask the title model which counties
#: survived; this CSV is the same evidence `titles` places baronies from.
BARONY_SET_CSV = "docs/evidence/barony_set.csv"


def read_live_counties(root: Path) -> set[str]:
    """Counties the `map` step placed at least one barony in.

    A county with no barony is dropped by the `titles` step, so a holy site on
    it is `error(missing-item): title c_x not defined in
    common/landed_titles/` -- one such in Faerûn, `c_barakuir` (`verified`
    2026-09-08). Empty set means "unknown" and nothing is filtered, so a run
    before the map step degrades to the old behaviour rather than emitting
    nothing.
    """
    path = root / BARONY_SET_CSV
    if not path.is_file():
        return set()
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return {
            row["county"]
            for row in csv.DictReader(handle)
            if row.get("county") and row.get("status") == "placed"
        }


def read_holy_sites(
    ck2_mod: Path, live_counties: set[str] | None = None
) -> tuple[dict[str, list[str]], list[str]]:
    """CK2 religion → the county titles marked `holy_site = <religion>`.

    `verified`: all 470 Faerûn marks sit on `c_*` titles, 5 per religion, so the
    relation is complete and the 5-per-faith CK3 cap is never exceeded.

    Returns `(marks, dropped)`; `dropped` names the `(religion, county)` pairs
    whose county did not survive the map step.
    """
    out: dict[str, list[str]] = {}
    folder = ck2_mod / "common" / "landed_titles"
    for path in sorted(folder.glob("*.txt")):
        _walk_titles(parse_file(path, lenient=True), [], out)
    if not live_counties:
        return out, []
    dropped: list[str] = []
    for religion, counties in list(out.items()):
        kept = [c for c in counties if c in live_counties]
        dropped += [f"{religion} -> {c}" for c in counties if c not in live_counties]
        out[religion] = kept
    return out, dropped


def _walk_titles(block: Block, path: list[str], out: dict[str, list[str]]) -> None:
    for entry in block.entries:
        if not isinstance(entry, Node):
            continue
        if entry.key == "holy_site":
            county = next((p for p in reversed(path) if p.startswith("c_")), None)
            if county:
                out.setdefault(str(entry.value), []).append(county)
        if isinstance(entry.value, Block):
            _walk_titles(entry.value, path + [entry.key], out)


# -- naming -----------------------------------------------------------------
def family_id(prefix: str, group: CK2ReligionGroup) -> str:
    return f"rf_{prefix}_{group.slug}"


def religion_id(prefix: str, group: CK2ReligionGroup) -> str:
    return f"{prefix}_{group.slug}_religion"


def faith_id(religion: CK2Religion) -> str:
    """CK2 religion ids are kept unchanged: `common/religion/religion_types` is
    in `replace_paths`, so a vanilla collision cannot duplicate a definition,
    and the localisation lane keeps CK2 key names."""
    return religion.id


def holy_site_id(prefix: str, county: str) -> str:
    """One holy-site object per county, shared by every faith that marks it.

    255 counties carry Faerûn's 470 marks, so sharing keeps the object count and
    the localisation surface at one per place rather than one per (faith, place).
    """
    return f"{prefix}_hs_{county[2:] if county.startswith('c_') else county}"


# -- doctrine decisions -----------------------------------------------------
def decide_doctrines(religion: CK2Religion) -> dict[str, str]:
    """CK2 flag → CK3 doctrine, one per mandatory group.

    Every branch is a row of `mappings/religion_fields.csv`; the fallback is
    `PAGANISM_DEFAULTS`. Returns `{doctrine_group: doctrine}`.
    """
    out = dict(PAGANISM_DEFAULTS)

    # theism: CK3 offers only monotheist / polytheist, and a CK2 pantheon's own
    # god list is the only mechanical signal available.
    out["doctrine_theism"] = (
        "doctrine_polytheist" if len(religion.god_names) > 1 else "doctrine_monotheist"
    )

    # gender
    women = religion.flag("women_can_take_consorts")
    men = religion.flag("men_can_take_consorts")
    if women is True and men is False:
        out["doctrine_gender"] = "doctrine_gender_female_dominated"
    elif religion.flag("feminist") is True:
        out["doctrine_gender"] = "doctrine_gender_equal"

    # pluralism, from the shape of the CK2 intermarry graph
    partners = religion.intermarry
    if not partners:
        out["doctrine_pluralism"] = "doctrine_pluralism_fundamentalist"
    else:
        siblings = {r.id for r in religion.group.religions}
        crosses = any(p not in siblings for p in partners)
        out["doctrine_pluralism"] = (
            "doctrine_pluralism_pluralistic"
            if crosses
            else "doctrine_pluralism_righteous"
        )

    # head of faith: doctrine_spiritual_head additionally needs
    # `religious_head = <title>`, which only the titles lane can supply.
    if religion.flag("can_excommunicate") is True:
        out["doctrine_head_of_faith"] = "doctrine_temporal_head"

    # marriage type: concubines wins over polygamy (one pick per group)
    if religion.number("max_consorts") > 0:
        out["doctrine_marriage_type"] = "doctrine_concubines"
    elif religion.number("max_wives") > 1:
        out["doctrine_marriage_type"] = "doctrine_polygamy"
    else:
        out["doctrine_marriage_type"] = "doctrine_monogamy"

    # divorce
    divorce = religion.flag("can_grant_divorce")
    if divorce is True:
        out["doctrine_divorce"] = "doctrine_divorce_approval"
    elif divorce is False:
        out["doctrine_divorce"] = "doctrine_divorce_disallowed"

    # consanguinity: most permissive CK2 flag wins
    if religion.flag("bs_marriage") is True or religion.flag("pc_marriage") is True:
        out["doctrine_consanguinity"] = "doctrine_consanguinity_unrestricted"
    elif religion.flag("psc_marriage") is True or religion.flag("divine_blood") is True:
        out["doctrine_consanguinity"] = "doctrine_consanguinity_dynastic"
    elif religion.flag("cousin_marriage") is True:
        out["doctrine_consanguinity"] = "doctrine_consanguinity_cousins"
    else:
        out["doctrine_consanguinity"] = "doctrine_consanguinity_restricted"

    # clerical gender: CK2 male_temple_holders defaults to yes
    female = religion.flag("female_temple_holders")
    male = religion.flag("male_temple_holders")
    if female is True and male is not False:
        out["doctrine_clerical_gender"] = "doctrine_clerical_gender_either"
    elif female is True and male is False:
        out["doctrine_clerical_gender"] = "doctrine_clerical_gender_female_only"
    elif female is False:
        out["doctrine_clerical_gender"] = "doctrine_clerical_gender_male_only"

    # clerical marriage
    marry = religion.flag("priests_can_marry")
    if marry is not None:
        out["doctrine_clerical_marriage"] = (
            "doctrine_clerical_marriage_allowed"
            if marry
            else "doctrine_clerical_marriage_disallowed"
        )

    # clerical succession: CK2 asks who keeps the holding, CK3 who appoints
    inherit = religion.flag("priests_can_inherit")
    if inherit is not None:
        out["doctrine_clerical_succession"] = (
            "doctrine_clerical_succession_temporal_appointment"
            if inherit
            else "doctrine_clerical_succession_spiritual_appointment"
        )
    return out


def decide_tenets(religion: CK2Religion, override: list[str] | None) -> list[str]:
    """Exactly three core tenets: CK2-justified ones first, defaults after."""
    if override:
        return override
    chosen = [
        tenet for flag, tenet in TENET_OF_FLAG if religion.flag(flag) is True
    ][:3]
    for tenet in DEFAULT_TENETS:
        if len(chosen) == 3:
            break
        if tenet not in chosen:
            chosen.append(tenet)
    return chosen


# -- block builders ---------------------------------------------------------
def _render(value: object) -> str:
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, Block):
        return "{ ... }"
    return str(value)


def _comment_for(key: str, value: object) -> str:
    note = NO_CK3_EQUIVALENT.get(key, "no mapping row")
    return f"# CK2: {key} = {_render(value)} (no CK3 equivalent: {note})"


def _unmapped_comments(block: Block, handled: frozenset[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for key, value in block.pairs():
        if key in handled or key in seen:
            continue
        seen.add(key)
        out.append(_comment_for(key, value))
    return out


_FAITH_HANDLED = frozenset(
    {
        "color",
        "icon",
        "graphical_culture",
        "high_god_name",
        "god_names",
        "evil_god_names",
        "scripture_name",
        "priest_title",
        "crusade_name",
        "intermarry",
        "reformed",
        "uses_jizya_tax",
        "pacifist",
        "allow_looting",
        "divine_blood",
        "autocephaly",
        "can_retire_to_monastery",
        "feminist",
        "women_can_take_consorts",
        "men_can_take_consorts",
        "can_excommunicate",
        "max_consorts",
        "max_wives",
        "can_grant_divorce",
        "bs_marriage",
        "pc_marriage",
        "psc_marriage",
        "cousin_marriage",
        "female_temple_holders",
        "male_temple_holders",
        "priests_can_marry",
        "priests_can_inherit",
    }
)
_GROUP_HANDLED = frozenset({"color", "graphical_culture", "hostile_within_group"})


def build_families(prefix: str, groups: list[CK2ReligionGroup]) -> Block:
    """One family per CK2 religion group, so family/religion stay 1:1."""
    out = Block()
    for index, group in enumerate(groups):
        body = Block(
            entries=[
                Node(key="graphical_faith", value=DEFAULT_GRAPHICAL_FAITH, quoted_value=True),
                Node(key="piety_icon_group", value=DEFAULT_PIETY_ICON_GROUP, quoted_value=True),
                Node(key="hostility_doctrine", value=HOSTILITY_DOCTRINE),
                Node(
                    key="doctrine_background_icon",
                    value=DEFAULT_DOCTRINE_BACKGROUND,
                    quoted_value=True,
                ),
            ]
        )
        comments = [
            f"# CK2 religion group {group.id} ({group.source})",
            "# CK3 has a level above religion that CK2 lacks: one family per CK2"
            " group keeps the mapping 1:1",
        ]
        if group.hostile_within_group:
            comments.append(
                "# CK2: hostile_within_group = yes (approx: a per-group hostility"
                " doctrine needs common/religion/doctrine_types, not owned by"
                " this step; using the vanilla pagan one)"
            )
        out.append(
            Node(
                key=family_id(prefix, group),
                value=body,
                blank_before=index > 0,
                leading_comments=comments,
            )
        )
    return out


def build_localization_baseline(ctx: Context) -> Block:
    """The 128-key `localization` block of vanilla `paganism_religion`.

    `localization` is inherited faith ← religion, and a key missing from the
    whole chain is a runtime localisation error, so the religion carries a
    complete block. Copied live from the CK3 install rather than transcribed, so
    it cannot drift from the installed version. Faiths then override only the
    keys CK2 actually supplies.
    """
    path = ctx.ck3(*LOCALIZATION_SOURCE)
    if not path.is_file():
        raise RuntimeError(
            f"{path} not found: [paths] ck3_game must point at a CK3 1.19 "
            "install, the religion localisation baseline is copied from it"
        )
    doc = parse_file(path, encoding=CK3_ENCODING, lenient=True)
    religion = doc.get(LOCALIZATION_SOURCE_ID)
    if not isinstance(religion, Block):
        raise RuntimeError(f"{LOCALIZATION_SOURCE_ID} not found in {path}")
    block = religion.get("localization")
    if not isinstance(block, Block):
        raise RuntimeError(f"{LOCALIZATION_SOURCE_ID} has no localization block")
    return block


def faith_localization(religion: CK2Religion) -> tuple[Block, list[tuple[str, str]]]:
    """The CK2-derived part of a faith's `localization`, plus loc rename rows.

    CK2 keeps one loc key where CK3 wants a family of keys (a possessive, a
    plural, three synonyms), so the extra shapes are requested from the
    localisation lane through `mappings/loc_key_renames_cultures_religions.csv`
    instead of being invented here.
    """
    entries: list[Node] = []
    renames: list[tuple[str, str]] = []

    high = religion.block.get("high_god_name")
    if high:
        key = str(high)
        possessive = f"{key}_possessive"
        renames.append((key, possessive))
        entries += [
            Node(key="HighGodName", value=key),
            Node(key="HighGodName2", value=key),
            Node(key="HighGodNamePossessive", value=possessive),
            Node(key="HighGodNameAlternate", value=key),
            Node(key="HighGodNameAlternatePossessive", value=possessive),
        ]

    good = religion.god_names
    if good:
        entries.append(
            Node(
                key="GoodGodNames",
                value=Block(entries=[Item(value=v) for v in good]),
            )
        )
    evil = religion.evil_god_names
    if evil:
        possessive = f"{evil[0]}_possessive"
        renames.append((evil[0], possessive))
        entries += [
            Node(
                key="EvilGodNames",
                value=Block(entries=[Item(value=v) for v in evil]),
            ),
            Node(key="DevilName", value=evil[0]),
            Node(key="DevilNamePossessive", value=possessive),
        ]

    scripture = religion.block.get("scripture_name")
    if scripture:
        key = str(scripture)
        entries += [
            Node(key="ReligiousText", value=key),
            Node(key="ReligiousText2", value=key),
            Node(key="ReligiousText3", value=key),
        ]

    priest = religion.block.get("priest_title")
    if priest:
        key = str(priest)
        plural = f"{key}_plural"
        renames.append((key, plural))
        for family in ("Priest", "Bishop"):
            entries += [
                Node(key=f"{family}Male", value=key),
                Node(key=f"{family}MalePlural", value=plural),
                Node(key=f"{family}Female", value=key),
                Node(key=f"{family}FemalePlural", value=plural),
                Node(key=f"{family}Neuter", value=key),
                Node(key=f"{family}NeuterPlural", value=plural),
            ]
        entries.append(Node(key="AltPriestTermPlural", value=plural))

    crusade = religion.block.get("crusade_name")
    if crusade:
        key = str(crusade)
        plural = f"{key}_plural"
        renames.append((key, plural))
        entries += [
            Node(key="GHWName", value=key),
            Node(key="GHWNamePlural", value=plural),
        ]
    return Block(entries=entries), renames


def build_faith(
    prefix: str,
    religion: CK2Religion,
    *,
    doctrines: dict[str, str],
    religion_doctrines: dict[str, str],
    tenets: list[str],
    holy_sites: list[str],
    unreformed: bool,
) -> tuple[Node, list[tuple[str, str]]]:
    entries: list[object] = []
    color = religion.block.get("color")
    if color is not None:
        entries.append(Node(key="color", value=color))

    icon = religion.block.get("icon")
    icon_comment = (
        f"# CK2: icon = {icon} (approx: a strip-atlas index into "
        "gfx/interface/religion_icon_strip.dds; CK3 wants one "
        f"gfx/interface/icons/faith/<icon>.dds per faith, so no icon is emitted)"
        if icon is not None
        else None
    )

    for group, doctrine in doctrines.items():
        if religion_doctrines.get(group) == doctrine:
            continue  # inherited from the religion
        entries.append(Node(key="doctrine", value=doctrine))
    for tenet in tenets:
        entries.append(Node(key="doctrine", value=tenet))
    if religion.flag("uses_jizya_tax") is True:
        entries.append(Node(key="doctrine", value="special_doctrine_jizya"))
    if unreformed:
        entries.append(
            Node(
                key="doctrine",
                value="unreformed_faith_doctrine",
                leading_comments=[
                    f"# CK2: reformed = {religion.reformed_into} (CK3 inverts it: "
                    "the religion sets pagan_roots and the unreformed faith "
                    "carries this doctrine)"
                ],
            )
        )
        entries.append(
            Node(
                key="reformed_icon",
                value=DEFAULT_REFORMED_ICON,
                leading_comments=[
                    "# mandatory alongside unreformed_faith_doctrine; the "
                    "vanilla icon, because CK2's icon atlas is not sliced yet"
                ],
            )
        )

    kept = holy_sites[:5]
    for index, site in enumerate(kept):
        entries.append(
            Node(
                key="holy_site",
                value=holy_site_id(prefix, site),
                blank_before=index == 0,
            )
        )

    loc, renames = faith_localization(religion)
    if loc.entries:
        entries.append(Node(key="localization", value=loc, blank_before=True))

    comments: list[str] = []
    if icon_comment:
        comments.append(icon_comment)
    partners = religion.intermarry
    if partners:
        comments.append(
            "# CK2: intermarry = "
            + ", ".join(partners)
            + " (approx: CK3 has no per-pair intermarriage table; kept as the "
            "pluralism doctrine plus this list)"
        )
    for site in holy_sites[5:]:
        comments.append(
            f"# CK2: holy_site {site} (dropped: CK3 allows 5 holy_site lines "
            "per faith)"
        )
    comments += _unmapped_comments(religion.block, _FAITH_HANDLED)

    body = Block(entries=entries)
    body.end_comments = comments
    node = Node(
        key=faith_id(religion),
        value=body,
        leading_comments=[f"# CK2 religion {religion.id}"],
    )
    return node, renames


def build_religion(
    prefix: str,
    group: CK2ReligionGroup,
    *,
    baseline: Block,
    doctrines_by_faith: dict[str, dict[str, str]],
    faiths: Block,
    pagan_roots: bool,
) -> Node:
    religion_doctrines = _religion_level_doctrines(group, doctrines_by_faith)
    entries: list[object] = [
        Node(key="family", value=family_id(prefix, group)),
        Node(key="graphical_faith", value=DEFAULT_GRAPHICAL_FAITH, quoted_value=True),
    ]
    if pagan_roots:
        entries.append(
            Node(
                key="pagan_roots",
                value=True,
                leading_comments=[
                    "# CK2 reformable pantheon (a religion of this group has a "
                    "`reformed` pointer)"
                ],
            )
        )
    for doctrine_group in RELIGION_LEVEL_GROUPS:
        doctrine = religion_doctrines.get(doctrine_group)
        if doctrine:
            entries.append(
                Node(
                    key="doctrine",
                    value=doctrine,
                    blank_before=doctrine_group == RELIGION_LEVEL_GROUPS[0],
                )
            )
    entries.append(
        Node(
            key="localization",
            value=baseline,
            blank_before=True,
            leading_comments=[
                "# Complete 128-key baseline copied from vanilla "
                f"{LOCALIZATION_SOURCE_ID}: `localization` is inherited "
                "faith <- religion and a key missing from the whole chain is a "
                "runtime loc error. Faiths override the keys CK2 supplies."
            ],
        )
    )
    entries.append(Node(key="faiths", value=faiths, blank_before=True))
    color = group.block.get("color")
    body = Block(entries=entries)
    body.end_comments = [
        (
            f"# CK2: color = {{ ... }} (no CK3 equivalent: only FAITHS have a "
            "colour; the group colour is unused because all 94 CK2 religions "
            "carry their own)"
        )
        if color is not None
        else "",
        *_unmapped_comments(group.block, _GROUP_HANDLED),
    ]
    body.end_comments = [c for c in body.end_comments if c]
    return Node(
        key=religion_id(prefix, group),
        value=body,
        leading_comments=[f"# CK2 religion group {group.id} ({group.source})"],
    )


def _religion_level_doctrines(
    group: CK2ReligionGroup, doctrines_by_faith: dict[str, dict[str, str]]
) -> dict[str, str]:
    """A doctrine goes on the religion when every faith of the group agrees."""
    out: dict[str, str] = {}
    for doctrine_group in RELIGION_LEVEL_GROUPS:
        values = {
            doctrines_by_faith[r.id][doctrine_group]
            for r in group.religions
            if r.id in doctrines_by_faith
        }
        out[doctrine_group] = (
            values.pop() if len(values) == 1 else PAGANISM_DEFAULTS[doctrine_group]
        )
    return out


def build_holy_sites(prefix: str, counties: list[str]) -> Block:
    """One `holy_site_type` per county. `county = c_<id>` is the only field that
    matters; the titles lane guarantees the county exists."""
    out = Block()
    for county in counties:
        out.append(
            Node(
                key=holy_site_id(prefix, county),
                value=Block(entries=[Node(key="county", value=county)]),
            )
        )
    return out


def build_opinion_formats(keys: list[str], *, skip: set[str] = frozenset()) -> Block:
    """Vanilla shapes: `christianity_religion_opinion` (a religion),
    `rf_pagan_opinion` (a family), `catholic_opinion` (a faith)."""
    out = Block()
    for key in keys:
        if key in skip:
            out.end_comments.append(
                f"# {key} is already declared by vanilla; not re-declared "
                "(common/modifier_definition_formats is not a replace_path)"
            )
            continue
        out.append(Node(key=key, value=Block(entries=[Node(key="decimals", value=0)])))
    return out


def opinion_keys(prefix: str, groups: list[CK2ReligionGroup]) -> list[str]:
    """`<faith>_opinion` per CK2 religion, plus `<religion>_opinion` and
    `<family>_opinion` per CK2 religion group (vanilla shapes:
    `christianity_religion_opinion`, `rf_pagan_opinion`)."""
    keys: list[str] = []
    for group in groups:
        keys.append(f"{religion_id(prefix, group)}_opinion")
        keys.append(f"{family_id(prefix, group)}_opinion")
        keys += [f"{faith_id(r)}_opinion" for r in group.religions]
    return keys


# -- step -------------------------------------------------------------------
def run(ctx: Context) -> StepResult:
    prefix = ctx.config.prefix
    groups = read_ck2_religions(ctx.config.ck2_mod)
    if not groups:
        # No `common/religions` in the source mod: nothing to convert.
        return StepResult(
            summary=f"no religion groups in {ctx.config.ck2_mod}/common/religions",
            skipped=True,
        )
    religions = [r for g in groups for r in g.religions]
    live_counties = read_live_counties(REPO_ROOT)
    sites, dropped_sites = read_holy_sites(ctx.config.ck2_mod, live_counties)
    for pair in dropped_sites:
        ctx.warn(
            f"religions: holy site {pair} dropped: the map step placed no "
            f"barony in that county, so the titles step does not declare it"
        )
    tenet_overrides = {
        (row.get("ck2_religion") or "").strip(): [
            (row.get(f"tenet_{n}") or "").strip() for n in (1, 2, 3)
        ]
        for row in overrides.read_rows(ctx.config, "faith_tenets.csv")
    }

    baseline = build_localization_baseline(ctx)
    doctrines_by_faith = {r.id: decide_doctrines(r) for r in religions}
    reformable = {
        g.id for g in groups if any(r.reformed_into for r in g.religions)
    }

    written: list[Path] = []
    written.append(
        ctx.write_script(
            f"common/religion/religion_family_types/{prefix}_families.txt",
            build_families(prefix, groups),
            source="common/religions (religion groups)",
        )
    )

    renames: list[tuple[str, str]] = []
    counts_sites = 0
    for group in groups:
        faiths = Block()
        for religion in group.religions:
            override = tenet_overrides.get(religion.id)
            node, faith_renames = build_faith(
                prefix,
                religion,
                doctrines=doctrines_by_faith[religion.id],
                religion_doctrines=_religion_level_doctrines(group, doctrines_by_faith),
                tenets=decide_tenets(
                    religion, override if override and all(override) else None
                ),
                holy_sites=sites.get(religion.id, []),
                unreformed=bool(religion.reformed_into),
            )
            node.blank_before = bool(faiths.entries)
            faiths.append(node)
            renames += faith_renames
            counts_sites += min(5, len(sites.get(religion.id, [])))
        block = Block(
            entries=[
                build_religion(
                    prefix,
                    group,
                    baseline=baseline,
                    doctrines_by_faith=doctrines_by_faith,
                    faiths=faiths,
                    pagan_roots=group.id in reformable or group.id == "pagan_group",
                )
            ]
        )
        written.append(
            ctx.write_script(
                f"common/religion/religion_types/{prefix}_{group.slug}.txt",
                block,
                source=f"common/religions ({group.id})",
            )
        )

    counties = sorted({c for marks in sites.values() for c in marks})
    written.append(
        ctx.write_script(
            f"common/religion/holy_site_types/{prefix}_holy_sites.txt",
            build_holy_sites(prefix, counties),
            source="common/landed_titles (holy_site marks)",
        )
    )

    keys = opinion_keys(prefix, groups)
    declared = cultures_step.vanilla_modifier_formats(ctx)
    skipped = sorted(set(keys) & declared)
    for key in skipped:
        ctx.warn(
            f"{key} is already declared by vanilla CK3; not re-declared "
            "(common/modifier_definition_formats is not a replace_path)"
        )
    written.append(
        ctx.write_script(
            f"common/modifier_definition_formats/{prefix}_faith_opinions.txt",
            build_opinion_formats(keys, skip=declared),
            source="mappings/modifiers.csv (<religion>_opinion rows)",
        )
    )

    without_sites = [r.id for r in religions if not sites.get(r.id)]
    for religion_id_ in without_sites:
        ctx.warn(f"CK2 religion {religion_id_!r} has no holy site marked on a county")

    ctx.data["religions"] = {
        "families": {g.id: family_id(prefix, g) for g in groups},
        "religions": {g.id: religion_id(prefix, g) for g in groups},
        "faiths": {r.id: faith_id(r) for r in religions},
        "holy_sites": {c: holy_site_id(prefix, c) for c in counties},
        "loc_renames": renames,
        "opinion_keys": keys,
    }
    return StepResult(
        summary=(
            f"{len(groups)} religion groups -> {len(groups)} families + "
            f"{len(groups)} religions; {len(religions)} faiths with "
            f"{counts_sites} holy sites over {len(counties)} counties"
        ),
        counts={
            "religion_groups": len(groups),
            "families": len(groups),
            "faiths": len(religions),
            "holy_site_types": len(counties),
            "holy_site_links": counts_sites,
            "faiths_without_holy_site": len(without_sites),
            "holy_sites_dropped_dead_county": len(dropped_sites),
            "pagan_roots_religions": len(reformable | {"pagan_group"} & {g.id for g in groups}),
            "loc_rename_rows": len(renames),
            "opinion_formats": len(keys) - len(skipped),
            "opinion_formats_vanilla_already": len(skipped),
        },
        warnings=list(ctx.warnings),
        written=written,
    )
