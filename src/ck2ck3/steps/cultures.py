"""CK2 culture groups / cultures → CK3 pillars, cultures, name lists, ethnicities.

Field-by-field source: `mappings/culture_fields.csv` (53 rows). Method and every
default this module invents are written up in `docs/step_cultures_religions.md`.

Structure (`docs/mapping_world.md` "Structural mapping"):

* CK2 culture group (67) → one `heritage` **and** one `language` pillar.
* CK2 culture (419) → one CK3 culture + its own `name_list` object.
* CK2 keys with no CK3 equivalent → a comment line inside the block, shaped
  ``# CK2: key = value (no CK3 equivalent: note)``.

The step never invents flavour: colours, names, dynasty prefixes and name
chances are copied from CK2. The four CK3 keys CK2 cannot supply (`ethos`,
`martial_custom`, `head_determination`, `ethnicities`) come from a deterministic
table keyed on CK2 flags, overridable in `overrides/`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .. import ids, overrides
from ..context import Context, StepResult
from ..pdx import Block, Color, Item, Node, parse_file
from ..pdx.encoding import CK3_ENCODING

DESCRIPTION = (
    "cultures: CK2 culture groups/cultures -> CK3 pillars, cultures, "
    "name lists, placeholder ethnicities"
)
OUTPUTS: tuple[str, ...] = (
    "common/culture/pillars",
    "common/culture/cultures",
    "common/culture/name_lists",
    "common/ethnicities",
    "common/modifier_definition_formats/fae_culture_opinions.txt",
)

# -- CK2 vocabulary ---------------------------------------------------------
#: A CK2 culture-group child block is a *culture* when it carries a name list.
#: `verified`: 419/419 Faerûn cultures define both `male_names` and
#: `female_names`, and no group-level key does (see
#: `scripts/survey_cultures_religions.py`).
CULTURE_MARKERS = ("male_names", "female_names")

#: Keys copied verbatim onto the CK3 **name list** (same key, same shape).
NAME_LIST_VERBATIM = (
    "male_names",
    "female_names",
    "pat_grf_name_chance",
    "mat_grf_name_chance",
    "father_name_chance",
    "pat_grm_name_chance",
    "mat_grm_name_chance",
    "mother_name_chance",
    "founder_named_dynasties",
    "grammar_transform",
    "bastard_dynasty_prefix",
)

#: CK2 culture keys with no CK3 home, and the note that goes in the comment.
#: Every note is the `note` column of `mappings/culture_fields.csv`, shortened.
NO_CK3_EQUIVALENT = {
    "alternate_start": "no CK3 random/shattered world",
    "used_for_random": "no CK3 random world",
    "allow_in_ruler_designer": "no per-culture ruler-designer gate in CK3",
    "nomadic_in_alt_start": "CK2 random/shattered world only",
    "disinherit_from_blinding": "CK3 removed blinding as a mechanic",
    "baron_titles_hidden": "CK3 always shows barony titles",
    "count_titles_hidden": "CK3 always shows county titles",
    "secondary_event_pictures": (
        "CK3 event art comes from common/event_backgrounds + event_themes"
    ),
    "dukes_called_kings": (
        "CK3 renames titles through common/flavorization, not the culture"
    ),
    "tribal_name": "common/flavorization, keyed on the government",
    "castes": "no CK3 caste mechanic; nearest is a tradition",
    "horde": "CK3 derives the herd head_determination from the government",
    "parent": (
        "CK3 `parents` only means anything with `created`; both are optional"
    ),
    "modifier": (
        "CK2 culture `modifier` is a PROVINCE modifier; its only CK3 home is a "
        "generated tradition with province_modifier"
    ),
    "dynasty_title_names": (
        "CK3 `can_be_named_after_dynasty` lives on the title, not the culture "
        "(titles lane)"
    ),
    "character_modifier": (
        "documented in _cultures.info but rejected by the 1.19 parser "
        "(`verified`: ck3-tiger reports `unknown field character_modifier`, and "
        "0/244 vanilla cultures use it); a culture modifier's only CK3 home is "
        "a generated tradition"
    ),
}

# -- CK3 vocabulary (`verified` against CK3 1.19.0.6, see tests) ------------
ETHOS_IDS = (
    "ethos_bellicose",
    "ethos_stoic",
    "ethos_bureaucratic",
    "ethos_spiritual",
    "ethos_courtly",
    "ethos_egalitarian",
    "ethos_communal",
)
MARTIAL_CUSTOM_IDS = (
    "martial_custom_male_only",
    "martial_custom_equal",
    "martial_custom_female_only",
)
HEAD_DETERMINATION_IDS = ("head_determination_domain", "head_determination_herd")

#: CK2 flag → CK3 tradition. Only these two flags justify a tradition; nothing
#: else in a Faerûn culture maps onto one (`mappings/culture_fields.csv`).
TRADITION_OF_FLAG = {
    "seafarer": "tradition_seafaring",
    "allow_looting": "tradition_practiced_pirates",
}

DEFAULT_GFX = {
    "coa_gfx": "western_coa_gfx",
    "building_gfx": "western_building_gfx",
    "clothing_gfx": "western_clothing_gfx",
    "unit_gfx": "western_unit_gfx",
}
DEFAULT_ETHNICITY = "mediterranean"
DEFAULT_RACE = "unknown"
PLACEHOLDER_ETHNICITY_BASE = "mediterranean"


# -- CK2 reading ------------------------------------------------------------
@dataclass
class CK2Culture:
    id: str
    block: Block
    group: "CK2CultureGroup" = field(repr=False, default=None)  # type: ignore[assignment]

    def flag(self, key: str) -> bool:
        return self.block.get(key) is True

    @property
    def color(self) -> object:
        return self.block.get("color")


@dataclass
class CK2CultureGroup:
    id: str
    source: str
    block: Block
    cultures: list[CK2Culture] = field(default_factory=list)

    @property
    def slug(self) -> str:
        return group_slug(self.id)

    @property
    def graphical_cultures(self) -> list[str]:
        value = self.block.get("graphical_cultures")
        return [str(v) for v in value.list_values()] if isinstance(value, Block) else []


def group_slug(group_id: str) -> str:
    """`dark_elf_group` → `dark_elf`, `aberration_culture_group` → `aberration`.

    `verified` unique across Faerûn's 67 groups (test
    `test_group_slugs_are_unique`), so the shortened form is safe in pillar ids.
    """
    for suffix in ("_culture_group", "_group"):
        if group_id.endswith(suffix):
            return group_id[: -len(suffix)]
    return group_id


def read_ck2_cultures(ck2_mod: Path) -> list[CK2CultureGroup]:
    """Every CK2 culture group of the mod, in file order."""
    groups: list[CK2CultureGroup] = []
    folder = ck2_mod / "common" / "cultures"
    for path in sorted(folder.glob("*.txt")):
        if path.stat().st_size == 0:  # Faerûn ships an empty 00_cultures.txt
            continue
        doc = parse_file(path)
        for entry in doc.entries:
            if not isinstance(entry, Node) or not isinstance(entry.value, Block):
                continue
            group = CK2CultureGroup(id=entry.key, source=path.name, block=entry.value)
            for child in entry.value.entries:
                if not isinstance(child, Node) or not isinstance(child.value, Block):
                    continue
                if not any(m in child.value for m in CULTURE_MARKERS):
                    continue
                group.cultures.append(
                    CK2Culture(id=child.key, block=child.value, group=group)
                )
            groups.append(group)
    return groups


# -- naming -----------------------------------------------------------------
# The three id shapes another step also has to know are defined in
# `ck2ck3.ids`; these wrappers only unpack the CK2 object.
def heritage_id(prefix: str, group: CK2CultureGroup) -> str:
    return ids.heritage_id(prefix, group.slug)


def language_id(prefix: str, group: CK2CultureGroup) -> str:
    return ids.language_id(prefix, group.slug)


def name_list_id(prefix: str, culture: CK2Culture) -> str:
    return ids.name_list_id(prefix, culture.id)


def culture_id(culture: CK2Culture) -> str:
    """CK2 culture ids are kept unchanged.

    `common/culture/cultures` is in `replace_paths`, so a vanilla collision
    cannot produce a duplicate definition, and the localisation lane keeps CK2
    key names (`scripts/check_id_collisions.py`).
    """
    return culture.id


# -- derived CK3 values -----------------------------------------------------
def derive_ethos(culture: CK2Culture) -> str:
    """`assumed`. CK2 has no ethos; this is the table from culture_fields.csv.

    `allow_looting` or `seafarer` → `ethos_bellicose`; everything else
    `ethos_communal`. Faerûn sets neither `castes` nor a culture-level
    `feminist` (`verified` 0 uses), so no other branch can fire.
    """
    if culture.flag("allow_looting") or culture.flag("seafarer"):
        return "ethos_bellicose"
    return "ethos_communal"


def derive_martial_custom(culture: CK2Culture) -> str:
    """`assumed`. CK2 `feminist` is a *religion* key in Faerûn, never a culture
    one (`verified` 0 culture uses), so every culture takes the CK3 default."""
    if culture.flag("feminist"):
        return "martial_custom_equal"
    return "martial_custom_male_only"


def derive_head_determination(culture: CK2Culture) -> str:
    """`assumed`. `head_determination_herd` needs CK2 `horde`, which Faerûn
    never sets (`verified` 0 uses); the government-derived variant belongs to
    the governments lane."""
    if culture.flag("horde"):
        return "head_determination_herd"
    return "head_determination_domain"


def derive_traditions(culture: CK2Culture) -> list[str]:
    return [
        tradition
        for flag, tradition in TRADITION_OF_FLAG.items()
        if culture.flag(flag)
    ]


def _gfx_chain(
    axis: str,
    culture: CK2Culture,
    gfx_map: dict[str, dict[str, str]],
) -> list[str]:
    """CK3 accepts a fallback chain per axis: culture value, then group value."""
    chain: list[str] = []
    ck2_axis = (
        "unit_graphical_cultures" if axis == "unit_gfx" else "graphical_cultures"
    )
    sources: list[str] = []
    value = culture.block.get(ck2_axis)
    if isinstance(value, Block):
        sources += [str(v) for v in value.list_values()]
    sources += culture.group.graphical_cultures
    for source in sources:
        mapped = gfx_map.get(source, {}).get(axis)
        if mapped and mapped not in chain:
            chain.append(mapped)
    if DEFAULT_GFX[axis] not in chain:
        chain.append(DEFAULT_GFX[axis])
    return chain


# -- block builders ---------------------------------------------------------
def _comment_for(key: str, value: object) -> str:
    note = NO_CK3_EQUIVALENT.get(key, "no mapping row")
    return f"# CK2: {key} = {_render(value)} (no CK3 equivalent: {note})"


def _render(value: object) -> str:
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, Color):
        return f"{value.tag} {{ ... }}"
    if isinstance(value, Block):
        return "{ ... }"
    return str(value)


def _copy(block: Block, key: str) -> Node | None:
    node = block.get_node(key)
    if node is None:
        return None
    return Node(key=node.key, value=node.value, quoted_value=node.quoted_value)


def build_heritages(
    prefix: str, groups: list[CK2CultureGroup], race_of_group: dict[str, str]
) -> tuple[Block, list[str]]:
    """One `heritage` pillar per CK2 culture group, carrying the species flag.

    `docs/design_races.md` item 1: the heritage's
    `parameters = { species_<race> = yes }` is what scripts test with
    `has_cultural_pillar`. Race comes from `overrides/race_of_culture_group.csv`.
    """
    out = Block()
    warnings: list[str] = []
    for index, group in enumerate(groups):
        race = race_of_group.get(group.id)
        if not race:
            race = DEFAULT_RACE
            warnings.append(
                f"no race for culture group {group.id!r} in "
                f"overrides/race_of_culture_group.csv; used species_{DEFAULT_RACE}"
            )
        body = Block(
            entries=[
                Node(key="type", value="heritage"),
                Node(
                    key="parameters",
                    value=Block(entries=[Node(key=f"species_{race}", value=True)]),
                ),
            ]
        )
        out.append(
            Node(
                key=heritage_id(prefix, group),
                value=body,
                blank_before=index > 0,
                leading_comments=[f"# CK2 culture group {group.id} ({group.source})"],
            )
        )
    return out, warnings


def build_languages(prefix: str, groups: list[CK2CultureGroup]) -> Block:
    """One `language` pillar per CK2 culture group.

    A language pillar needs a `color` (the language UI paints it) and CK2 culture
    *groups* carry none (`verified`: the only group-level keys in Faerûn are
    `graphical_cultures` and `alternate_start`), so the colour is taken from the
    group's first culture — copied CK2 data, not an invented value.
    """
    out = Block()
    for index, group in enumerate(groups):
        entries: list[Node] = [Node(key="type", value="language")]
        first = group.cultures[0] if group.cultures else None
        color = first.color if first is not None else None
        if color is not None:
            entries.append(Node(key="color", value=color))
        comments = [f"# CK2 culture group {group.id} ({group.source})"]
        if first is not None and color is not None:
            comments.append(
                f"# color copied from its first culture {first.id} "
                "(CK2 culture groups have no colour of their own)"
            )
        out.append(
            Node(
                key=language_id(prefix, group),
                value=Block(entries=entries),
                blank_before=index > 0,
                leading_comments=comments,
            )
        )
    return out


def build_culture(
    prefix: str,
    culture: CK2Culture,
    *,
    gfx_map: dict[str, dict[str, str]],
    ethnicities: dict[str, str],
    culture_defaults: dict[str, dict[str, str]],
) -> Node:
    """One CK3 culture, field by field through `mappings/culture_fields.csv`."""
    group = culture.group
    row = culture_defaults.get(culture.id, {})
    entries: list[object] = []

    color = culture.color
    if color is not None:
        entries.append(Node(key="color", value=color))

    ethos = row.get("ethos") or derive_ethos(culture)
    martial = row.get("martial_custom") or derive_martial_custom(culture)
    head = row.get("head_determination") or derive_head_determination(culture)
    entries.append(Node(key="ethos", value=ethos, blank_before=True))
    entries.append(Node(key="heritage", value=heritage_id(prefix, group)))
    entries.append(Node(key="language", value=language_id(prefix, group)))
    entries.append(Node(key="martial_custom", value=martial))
    entries.append(Node(key="head_determination", value=head))
    entries.append(
        Node(key="name_list", value=name_list_id(prefix, culture), blank_before=True)
    )

    traditions = derive_traditions(culture)
    if traditions:
        entries.append(
            Node(
                key="traditions",
                value=Block(entries=[Item(value=t) for t in traditions]),
                blank_before=True,
                leading_comments=[
                    "# from CK2 flags: "
                    + ", ".join(
                        f"{flag} = yes"
                        for flag in TRADITION_OF_FLAG
                        if culture.flag(flag)
                    )
                ],
            )
        )

    ethnicity = ethnicities.get(group.id, DEFAULT_ETHNICITY)
    entries.append(
        Node(
            key="ethnicities",
            value=Block(entries=[Node(key="10", value=ethnicity)]),
            blank_before=True,
            leading_comments=[
                "# CK2 has no ethnicity concept; from "
                "overrides/ethnicity_of_culture_group.csv"
            ],
        )
    )

    for index, axis in enumerate(("coa_gfx", "building_gfx", "clothing_gfx", "unit_gfx")):
        chain = _gfx_chain(axis, culture, gfx_map)
        entries.append(
            Node(
                key=axis,
                value=Block(entries=[Item(value=v) for v in chain]),
                blank_before=index == 0,
            )
        )

    comments = _unmapped_comments(culture.block, handled=_CULTURE_HANDLED)
    body = Block(entries=entries)
    if comments:
        body.end_comments = comments
    return Node(
        key=culture_id(culture),
        value=body,
        leading_comments=[f"# CK2 culture {culture.id} of group {group.id}"],
    )


#: CK2 culture keys this module consumes (mapped or deliberately moved onto the
#: name list); anything else becomes a comment.
_CULTURE_HANDLED = frozenset(
    {
        "color",
        "graphical_cultures",
        "unit_graphical_cultures",
        "seafarer",
        "allow_looting",
        "feminist",
        *NAME_LIST_VERBATIM,
        "from_dynasty_prefix",
        "male_patronym",
        "female_patronym",
        "prefix",
        "dynasty_name_first",
    }
)


def _unmapped_comments(block: Block, *, handled: frozenset[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for key, value in block.pairs():
        if key in handled or key in seen:
            continue
        seen.add(key)
        out.append(_comment_for(key, value))
    return out


def build_name_list(prefix: str, culture: CK2Culture) -> Node:
    """One `name_list` object: CK2 keeps names per culture, CK3 per name list."""
    entries: list[object] = []
    for key in NAME_LIST_VERBATIM:
        node = _copy(culture.block, key)
        if node is not None:
            entries.append(node)

    literal = culture.block.get("from_dynasty_prefix")
    if isinstance(literal, str) and literal.strip():
        entries.append(
            Node(
                key="dynasty_of_location_prefix",
                value=f"dynnp_{prefix}_{culture.id}",
                quoted_value=True,
                blank_before=True,
                leading_comments=[
                    f"# CK2 from_dynasty_prefix = \"{literal}\" -> a CK3 loc key "
                    "(localisation lane writes the literal)"
                ],
            )
        )

    is_prefix = culture.block.get("prefix") is True
    for gender in ("male", "female"):
        patronym = culture.block.get(f"{gender}_patronym")
        if not (isinstance(patronym, str) and patronym.strip()):
            continue
        key = f"patronym_{'prefix' if is_prefix else 'suffix'}_{gender}"
        entries.append(
            Node(
                key=key,
                value=f"dynnpat_{'pre' if is_prefix else 'suf'}_{prefix}_{culture.id}",
                quoted_value=True,
                blank_before=gender == "male",
                leading_comments=[
                    f'# CK2 {gender}_patronym = "{patronym}" with prefix = '
                    f"{'yes' if is_prefix else 'no'}"
                ],
            )
        )
    if any(
        isinstance(culture.block.get(f"{g}_patronym"), str)
        and str(culture.block.get(f"{g}_patronym")).strip()
        for g in ("male", "female")
    ):
        entries.append(
            Node(
                key="always_use_patronym",
                value=True,
                leading_comments=[
                    "# CK3 defaults this to no: without it the converted "
                    "patronym never shows (mapping_world.md gotcha 5)"
                ],
            )
        )

    if culture.block.get("dynasty_name_first") is True:
        entries.append(
            Node(
                key="dynasty_name_first",
                value=True,
                blank_before=True,
                leading_comments=["# CK2 dynasty_name_first = yes"],
            )
        )

    return Node(
        key=name_list_id(prefix, culture),
        value=Block(entries=entries),
        leading_comments=[f"# CK2 culture {culture.id} of group {culture.group.id}"],
    )


def build_placeholder_ethnicities(races: list[str]) -> Block:
    """One 3-line placeholder ethnicity per non-human race.

    `docs/design_races.md` item 5 tier 3: without an asset pack the ethnicity is
    a placeholder inheriting a vanilla look. Vanilla precedent for the shape:
    `common/ethnicities/01_ethnicities_mediterranean.txt:113`
    (`mediterranean_byzantine = { visible = no template = "mediterranean" }`).
    """
    out = Block()
    for index, race in enumerate(races):
        out.append(
            Node(
                key=f"fae_placeholder_{race}",
                value=Block(
                    entries=[
                        Node(key="visible", value=False),
                        Node(
                            key="template",
                            value=PLACEHOLDER_ETHNICITY_BASE,
                            quoted_value=True,
                        ),
                    ]
                ),
                blank_before=index > 0,
                leading_comments=[
                    f"# TODO real ethnicity for race {race}: needs a "
                    "ck3_fantasy_assets pack (docs/design_races.md item 5)"
                ],
            )
        )
    return out


def vanilla_modifier_formats(ctx: Context) -> set[str]:
    """Keys vanilla already declares in `common/modifier_definition_formats`.

    That folder is **not** in `replace_paths`, so re-declaring one of its keys is
    a duplicate definition. `verified`: Faerûn's `gur` and `mari` cultures share
    their id with a vanilla CK3 culture, so `gur_opinion` / `mari_opinion` exist
    already (`scripts/check_id_collisions.py`).
    """
    out: set[str] = set()
    folder = ctx.ck3("common", "modifier_definition_formats")
    for path in sorted(folder.glob("*.txt")):
        if path.name.startswith("_"):
            continue
        doc = parse_file(path, encoding=CK3_ENCODING, lenient=True)
        out.update(e.key for e in doc.entries if isinstance(e, Node))
    return out


def build_opinion_formats(keys: list[str], *, skip: set[str] = frozenset()) -> Block:
    """`common/modifier_definition_formats/` declarations for `<x>_opinion`.

    Shape copied from vanilla `00_culture_definitions.txt:1`
    (`akan_opinion = { decimals = 0 }`). A dynamic modifier the game generates
    still needs a format entry or its tooltip is unformatted.
    """
    out = Block()
    for key in keys:
        if key in skip:
            out.end_comments.append(
                f"# {key} is already declared by vanilla; not re-declared "
                "(common/modifier_definition_formats is not a replace_path)"
            )
            continue
        out.append(
            Node(
                key=key,
                value=Block(entries=[Node(key="decimals", value=0)]),
            )
        )
    return out


def culture_opinion_keys(groups: list[CK2CultureGroup]) -> list[str]:
    return [f"{culture_id(c)}_opinion" for g in groups for c in g.cultures]


# -- step -------------------------------------------------------------------
def run(ctx: Context) -> StepResult:
    prefix = ctx.config.prefix
    groups = read_ck2_cultures(ctx.config.ck2_mod)
    if not groups:
        # No `common/cultures` in the source mod: nothing to convert. Skipping
        # keeps the step usable in the default order against any CK2 mod.
        return StepResult(
            summary=f"no culture groups in {ctx.config.ck2_mod}/common/cultures",
            skipped=True,
        )
    cultures = [c for g in groups for c in g.cultures]

    race_of_group = overrides.read_map(
        ctx.config, "race_of_culture_group.csv", "ck2_culture_group", "race"
    )
    ethnicity_of_group = overrides.read_map(
        ctx.config, "ethnicity_of_culture_group.csv", "ck2_culture_group", "ck3_ethnicity"
    )
    gfx_map: dict[str, dict[str, str]] = {}
    for row in overrides.read_rows(ctx.config, "gfx_of_culture_group.csv"):
        key = (row.get("ck2_graphical_culture") or "").strip()
        if key:
            gfx_map[key] = {
                axis: (row.get(axis) or "").strip() for axis in DEFAULT_GFX
            }
    culture_defaults: dict[str, dict[str, str]] = {
        (row.get("ck2_culture") or "").strip(): row
        for row in overrides.read_rows(ctx.config, "culture_defaults.csv")
        if (row.get("ck2_culture") or "").strip()
    }

    written: list[Path] = []
    heritages, warnings = build_heritages(prefix, groups, race_of_group)
    for message in warnings:
        ctx.warn(message)
    written.append(
        ctx.write_script(
            f"common/culture/pillars/{prefix}_heritages.txt",
            heritages,
            source="common/cultures (culture groups)",
        )
    )
    written.append(
        ctx.write_script(
            f"common/culture/pillars/{prefix}_languages.txt",
            build_languages(prefix, groups),
            source="common/cultures (culture groups)",
        )
    )

    missing_ethnicity = sorted(
        {g.id for g in groups if g.id not in ethnicity_of_group}
    )
    for group_id in missing_ethnicity:
        ctx.warn(
            f"no ethnicity for culture group {group_id!r} in "
            f"overrides/ethnicity_of_culture_group.csv; used {DEFAULT_ETHNICITY}"
        )

    by_source: dict[str, list[CK2CultureGroup]] = {}
    for group in groups:
        by_source.setdefault(Path(group.source).stem, []).append(group)

    for stem, file_groups in sorted(by_source.items()):
        culture_block = Block()
        name_block = Block()
        for group in file_groups:
            for culture in group.cultures:
                node = build_culture(
                    prefix,
                    culture,
                    gfx_map=gfx_map,
                    ethnicities=ethnicity_of_group,
                    culture_defaults=culture_defaults,
                )
                node.blank_before = bool(culture_block.entries)
                culture_block.append(node)
                name_node = build_name_list(prefix, culture)
                name_node.blank_before = bool(name_block.entries)
                name_block.append(name_node)
        written.append(
            ctx.write_script(
                f"common/culture/cultures/{prefix}_{stem}.txt",
                culture_block,
                source=f"common/cultures/{stem}.txt",
            )
        )
        written.append(
            ctx.write_script(
                f"common/culture/name_lists/{prefix}_{stem}.txt",
                name_block,
                source=f"common/cultures/{stem}.txt",
            )
        )

    races = sorted(
        {
            race
            for group in groups
            if (race := race_of_group.get(group.id, DEFAULT_RACE)) != "human"
        }
    )
    written.append(
        ctx.write_script(
            f"common/ethnicities/{prefix}_placeholder_ethnicities.txt",
            build_placeholder_ethnicities(races),
            source="overrides/race_of_culture_group.csv",
        )
    )

    opinion_keys = culture_opinion_keys(groups)
    declared = vanilla_modifier_formats(ctx)
    skipped = sorted(set(opinion_keys) & declared)
    for key in skipped:
        ctx.warn(
            f"{key} is already declared by vanilla CK3; not re-declared "
            "(common/modifier_definition_formats is not a replace_path)"
        )
    written.append(
        ctx.write_script(
            f"common/modifier_definition_formats/{prefix}_culture_opinions.txt",
            build_opinion_formats(opinion_keys, skip=declared),
            source="mappings/modifiers.csv (<culture>_opinion rows)",
        )
    )

    ctx.data["cultures"] = {
        "groups": {g.id: g.slug for g in groups},
        "cultures": {c.id: c.group.id for c in cultures},
        "heritages": {g.id: heritage_id(prefix, g) for g in groups},
        "languages": {g.id: language_id(prefix, g) for g in groups},
        "opinion_keys": opinion_keys,
    }
    return StepResult(
        summary=(
            f"{len(groups)} culture groups -> {len(groups)} heritage + "
            f"{len(groups)} language pillars; {len(cultures)} cultures with "
            f"{len(cultures)} name lists; {len(races)} placeholder ethnicities"
        ),
        counts={
            "culture_groups": len(groups),
            "cultures": len(cultures),
            "name_lists": len(cultures),
            "placeholder_ethnicities": len(races),
            "traditions_emitted": sum(len(derive_traditions(c)) for c in cultures),
            "opinion_formats": len(opinion_keys) - len(skipped),
            "opinion_formats_vanilla_already": len(skipped),
            "missing_race_overrides": sum(
                1 for g in groups if g.id not in race_of_group
            ),
            "missing_ethnicity_overrides": len(missing_ethnicity),
        },
        warnings=list(ctx.warnings),
        written=written,
    )
