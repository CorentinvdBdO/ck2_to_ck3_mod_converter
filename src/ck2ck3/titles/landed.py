"""``common/landed_titles/<prefix>_landed_titles.txt`` from CK2 landed titles.

Field-by-field rules come from ``mappings/title_fields.csv``; the CK3 shapes
they rely on are re-verified in ``docs/formats_titles.md``.  Three rules shape
the whole file:

* **Nothing is dropped silently.**  A CK2 key with a CK3 home is converted, a
  key without one becomes a comment on the same block, so a reader of the
  generated file can see what CK2 said and a submod can act on it.
* **A barony exists only if it has a province.**  ``province = <id>`` is
  mandatory for a CK3 barony, so an unbuilt or demoted barony is emitted as a
  *commented* block instead — the submod promotes it by deleting two ``#``.
* **A county with no province cannot exist either** (a county needs at least
  one barony), so the whole county block is commented out.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field

from ..pdx import Block, write
from .ck2read import Ck2Title, flatten
from .place import PlacementPlan
from .text import Lines, rgb, slug, tail, valid_id

#: CK2 landed_titles keys with no CK3 equivalent at all: emitted as a comment
#: next to the block.  Key -> the reason written into the file.
#: Every entry corresponds to a ``status = none`` row of
#: ``mappings/title_fields.csv`` unless the note says otherwise.
COMMENT_ONLY: dict[str, str] = {
    "culture": "CK2 default culture of the title; CK3 reads the holder's culture",
    "religion": "CK2 default religion of the title; CK3 reads the holder's faith",
    "graphical_culture": "CK3 derives title graphics from the holder's culture",
    "independent": "CK3 independence is runtime state (liege = 0 in history/titles)",
    "holy_site": "religions lane owns holy sites (common/religion/holy_site_types)",
    "caliphate": "faith-side in CK3: religious_head = <title> on the faith",
    "controls_religion": "faith-side in CK3: religious_head = <title> on the faith",
    "pentarchy": "CK3 has one tenet_pentarchy on the faith, no title flag",
    "rebel": "CK3 rebels are common/factions, not a title flag",
    "monster": "Faerun-custom playability flag; no CK3 analogue",
    "planar": "Faerun-custom plane flag; no CK3 analogue",
    "spectator": "Faerun-custom playability flag; no CK3 analogue",
    "purple_born_heirs": "CK3 models this with traditions/legitimacy, not a title key",
    "has_top_de_jure_capital": "CK2 title-creation bookkeeping; CK3 derives it",
    "top_de_jure_capital": "CK2 title-creation bookkeeping; CK3 derives it",
    "duchy_revokation": "not a real CK2 key (0 uses); nothing to map",
    "can_be_usurped": "CK3 has no usurpation switch",
    "used_for_dynasty_names": "CK3 uses the name_list dynasty_names pool instead",
    "mercenary_type": "CK2 mercenary bookkeeping; no CK3 key",
    "strength_growth_per_century": "CK2 mercenary bookkeeping; no CK3 key",
    "hire_range": "CK2 mercenary bookkeeping; no CK3 key",
    "monthly_income": "CK2 mercenary bookkeeping; no CK3 key",
    "extra_ai_eval_troops": "CK2 AI bookkeeping; no CK3 key",
    "creation_requires_capital": "port the trigger to can_create (lane events-decisions)",
    "name_tier": "Faerun tier naming; CK3 route is common/flavorization",
}

#: CK2 keys that move to ``history/titles`` (the government derivation reads
#: them) and are therefore only a comment here.
GOVERNMENT_FLAGS: dict[str, str] = {
    "tribe": "government moves to history/titles: tribal_government",
    "mercenary": "government moves to history/titles: mercenary_government",
    "holy_order": "government moves to history/titles: holy_order_government",
    "pirate": "government moves to history/titles: landless_adventurer_government",
}

#: CK2 keys that move to ``common/flavorization`` — a database no step owns
#: yet.  Recorded in ``docs/evidence/title_flavorization.csv`` for that lane.
FLAVORIZATION_KEYS = ("title", "title_female", "foa", "title_prefix")

#: The vanilla landless-title recipe, `verified`
#: ``common/landed_titles/01_japan_noble_family.txt:10-15``.
LANDLESS_RECIPE: tuple[str, ...] = (
    "landless = yes",
    "require_landless = yes",
    "ruler_uses_title_name = no",
    "always_follows_primary_heir = yes",
    "no_automatic_claims = yes",
    "destroy_if_invalid_heir = yes",
)

#: CK2 files whose titles are titular organisations, not de jure land.
TITULAR_FILES = frozenset(
    {"titular_titles.txt", "mercenaries.txt", "landed_titles.txt", "offmap_toril_landed_titles.txt"}
)

#: CK2 file whose contents cannot exist in CK3 at all.
PATRICIAN_FILE = "republics.txt"


@dataclass
class LandedResult:
    text: str
    #: generated localisation, ``cn_*`` cultural-name keys (plus ``_adj``).
    loc: dict[str, str] = field(default_factory=dict)
    counts: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    #: ``(title, ck2 religion)`` for the religions lane.
    holy_sites: list[tuple[str, str]] = field(default_factory=list)
    #: ``(title, ck2 key, value)`` for a future flavorization lane.
    flavorization: list[tuple[str, str, str]] = field(default_factory=list)
    #: title ids actually emitted as live CK3 titles, by tier prefix.
    emitted: dict[str, list[str]] = field(default_factory=dict)
    #: title ids emitted commented out, with the reason.
    commented: list[tuple[str, str]] = field(default_factory=list)


@dataclass
class LandedConfig:
    """Everything the renderer needs that is not the title tree itself."""

    plan: PlacementPlan
    #: CK2 province id -> the CK3 county title that province belongs to.
    county_of_province: Mapping[int, str]
    #: every CK2 title by id, for a barony to inherit its county's colour.
    by_id: Mapping[str, Ck2Title]
    #: every title id that survives as a live CK3 title.
    live_titles: frozenset[str]
    #: title id -> why it cannot be a live CK3 title (see
    #: :func:`ck2ck3.titles.model.liveness`).
    dead_titles: Mapping[str, str]
    #: CK2 culture id -> CK3 name list id (the cultures lane's convention).
    name_list_of_culture: Mapping[str, str]
    #: CK2 culture group -> member culture ids, to expand a group-keyed name.
    culture_groups: Mapping[str, Sequence[str]]
    #: title id -> the first live county inside its own de jure subtree.  CK3
    #: warns when ``capital`` names a county outside the title
    #: (ck3-tiger ``warning(title-tier)``), so a title whose CK2 capital county
    #: did not survive takes one of its own counties instead.
    own_county: Mapping[str, str]
    #: the county used as a placeholder capital for a landless title.
    placeholder_capital: str
    prefix: str = "fae"


def _flag(value: object) -> bool | None:
    """CK2 boolean, or ``None`` when the value is not a boolean at all."""
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return bool(value)
    if isinstance(value, str) and value.lower() in ("yes", "no", "true", "false"):
        return value.lower() in ("yes", "true")
    return None


def _block_text(block: Block) -> list[str]:
    return write(block).rstrip("\n").split("\n")


class _Renderer:
    def __init__(self, config: LandedConfig) -> None:
        self.cfg = config
        self.out = Lines()
        self.result = LandedResult(text="")
        self._cn_keys: dict[str, str] = {}
        self._cn_used: set[str] = set()

    # -- cultural names ----------------------------------------------------
    def _cn_key(self, name: str) -> str:
        """Loc key for a cultural title name, shared by identical names.

        Keyed by the literal, so the 3314 CK2 cultural-name lines collapse to
        one loc entry per distinct name instead of one per (title, culture).
        """
        key = self._cn_keys.get(name)
        if key is not None:
            return key
        base = f"cn_{self.cfg.prefix}_{slug(name, 'name')}"
        key, n = base, 1
        while key in self._cn_used:
            n += 1
            key = f"{base}_{n}"
        self._cn_used.add(key)
        self._cn_keys[name] = key
        self.result.loc[key] = name
        # CK3 derives a cultural adjective as <key>_adj and warns when it is
        # missing; CK2 gives no cultural adjective, so the name doubles as one.
        self.result.loc[f"{key}_adj"] = name
        return key

    def _cultural_names(self, title: Ck2Title) -> list[str]:
        rows: dict[str, str] = {}
        for culture, name in title.cultural_names.items():
            cultures: Sequence[str]
            if culture in self.cfg.culture_groups:
                cultures = self.cfg.culture_groups[culture]
            else:
                cultures = (culture,)
            for member in cultures:
                name_list = self.cfg.name_list_of_culture.get(member)
                if not name_list:
                    continue
                rows.setdefault(name_list, self._cn_key(name))
        return [f"{k} = {v}" for k, v in sorted(rows.items())]

    # -- one title ---------------------------------------------------------
    def title(self, title: Ck2Title, indent: int) -> None:
        reason = self.cfg.dead_titles.get(title.id)
        if reason and title.prefix != "b":
            self._commented(title, indent, reason)
            return
        if title.prefix == "b":
            self._barony(title, indent, reason)
            return
        if not valid_id(title.id):
            self.result.warnings.append(f"{title.id}: not a legal CK3 title id")
        self.out.comments(indent, title.leading_comments)
        self.out.line(indent, f"{title.id} = {{{tail(title.trailing_comment)}")
        self._body(title, indent + 1)
        for child in title.children:
            self.title(child, indent + 1)
        self.out.line(indent, "}")
        self.result.emitted.setdefault(title.prefix, []).append(title.id)

    def _barony(self, title: Ck2Title, indent: int, reason: str | None) -> None:
        placement = self.cfg.plan.get(title.id)
        if reason or placement is None or not placement.placed:
            note = reason or (
                f"{placement.status}: {placement.reason}"
                if placement
                else "no placement"
            )
            self.out.comments(indent, title.leading_comments)
            self.out.line(indent, f"# {title.id} = {{ }} # {note}")
            self.result.commented.append((title.id, note))
            return
        self.out.comments(indent, title.leading_comments)
        self.out.line(indent, f"{title.id} = {{")
        self.out.line(indent + 1, f"province = {placement.province}")
        self._body(title, indent + 1)
        self.out.line(indent, "}")
        self.result.emitted.setdefault("b", []).append(title.id)

    def _commented(self, title: Ck2Title, indent: int, reason: str) -> None:
        self.out.comment(indent, reason)
        body = Lines()
        renderer = _Renderer(self.cfg)
        renderer._cn_keys = self._cn_keys
        renderer._cn_used = self._cn_used
        renderer.out = body
        renderer.result = self.result
        # render live so the commented text is a real block a submod can revive
        body.line(0, f"{title.id} = {{")
        renderer._body(title, 1, commented=True)
        body.line(0, "}")
        self.out.commented_block(indent, body.text().rstrip("\n").split("\n"))
        self.result.commented.append((title.id, reason))
        for descendant in flatten([title])[1:]:
            self.result.commented.append(
                (descendant.id, f"ancestor {title.id} commented out")
            )

    # -- the field pass ----------------------------------------------------
    def _body(self, title: Ck2Title, indent: int, *, commented: bool = False) -> None:
        out = self.out
        kw = title.keywords
        # CK3 warns about a redefined field in the same block
        # (ck3-tiger warning(duplicate-field)), and the landless recipe overlaps
        # with the CK2 keys `location_ruler_title` and `can_be_claimed`.
        seen: set[str] = set()

        def once(line: str) -> None:
            key = line.split("=", 1)[0].strip()
            if key in seen:
                return
            seen.add(key)
            out.line(indent, line)

        color = title.color or self._inherited_color(title)
        if color or title.prefix != "b":
            out.line(indent, f"color = {rgb(color)}")
        if title.color2:
            out.comment(
                indent,
                f"CK2 color2 = {rgb(title.color2)} - CK3 has no second title colour",
            )

        capital = self._capital(title)
        if capital:
            out.line(indent, f"capital = {capital}{tail(title.capital_comment)}")

        rows = self._cultural_names(title)
        if rows:
            out.line(indent, "cultural_names = {")
            for row in rows:
                out.line(indent + 1, row)
            out.line(indent, "}")

        landless_reason = self._landless_reason(title)
        if landless_reason:
            out.comment(indent, landless_reason)
            for line in LANDLESS_RECIPE:
                once(line)

        if _flag(kw.get("short_name")):
            out.comment(
                indent,
                "CK2 short_name = yes (no 'Kingdom of' prefix); definite_form is "
                "the nearest CK3 lever",
            )
            once("definite_form = yes")
        if _flag(kw.get("location_ruler_title")):
            once("ruler_uses_title_name = no")
        if _flag(kw.get("primary")) and not landless_reason:
            out.comment(indent, "CK2 primary = yes")
            once("always_follows_primary_heir = yes")
        if _flag(kw.get("assimilate")) is False:
            out.comment(indent, "CK2 assimilate = no (inverted in CK3)")
            once("de_jure_drift_disabled = yes")
        if _flag(kw.get("can_be_claimed")) is False:
            once("no_automatic_claims = yes")
        if _flag(kw.get("dynasty_title_names")) is False:
            once("can_be_named_after_dynasty = no")
        dignity = kw.get("dignity")
        if isinstance(dignity, (int, float)):
            out.comment(indent, f"CK2 dignity = {dignity}")
            out.line(indent, "ai_primary_priority = {")
            out.line(indent + 1, f"add = {int(float(dignity) * 100)}")
            out.line(indent, "}")

        names = title.blocks.get("male_names")
        if isinstance(names, Block):
            out.line(indent, "holding_regnal_male_names = {")
            for value in names.list_values():
                out.line(indent + 1, str(value))
            out.line(indent, "}")
        names = title.blocks.get("female_names")
        if isinstance(names, Block):
            out.line(indent, "holding_regnal_female_names = {")
            for value in names.list_values():
                out.line(indent + 1, str(value))
            out.line(indent, "}")

        for key in FLAVORIZATION_KEYS:
            if key in kw:
                value = str(kw[key]).strip('"')
                out.comment(
                    indent,
                    f"CK2 {key} = {value} -> common/flavorization "
                    "(docs/evidence/title_flavorization.csv)",
                )
                if not commented:
                    self.result.flavorization.append((title.id, key, value))
        for key, reason in GOVERNMENT_FLAGS.items():
            if _flag(kw.get(key)):
                out.comment(indent, f"CK2 {key} = yes -> {reason}")
        for key, reason in COMMENT_ONLY.items():
            if key not in kw:
                continue
            value = str(kw[key]).strip('"')
            out.comment(indent, f"CK2 {key} = {value} - {reason}")
            if key == "holy_site" and not commented:
                self.result.holy_sites.append((title.id, value))
        for key, block in title.blocks.items():
            if key in ("color", "color2", "male_names", "female_names"):
                continue
            out.comment(indent, f"CK2 {key} = {{ ... }} - no CK3 equivalent here:")
            self.out.commented_block(indent, _block_text(block))

    def _inherited_color(self, title: Ck2Title) -> tuple[int, int, int] | None:
        """A barony has no CK2 colour; use its county's rather than invent one."""
        parent = self.cfg.by_id.get(title.parent or "")
        return parent.color if parent else None

    def _capital(self, title: Ck2Title) -> str | None:
        raw = title.capital
        if raw is not None:
            county = self._county_of_capital(raw)
            if county and county in self.cfg.live_titles:
                return county
        # CK2 gave no capital, or the county it named did not survive.  A
        # county inside this title's own de jure subtree keeps CK3 happy;
        # only a title that contains no live county at all needs the global
        # placeholder, and then only if it is landless (EK2 precedent:
        # `capital = c_imperial_city #Placeholder for less errors`).
        own = self.cfg.own_county.get(title.id)
        note = f"CK2 capital = {raw}" if raw else "CK2 gave no capital"
        if own:
            self.result.warnings.append(
                f"{title.id}: {note} is not a live county; using its own {own}"
            )
            return f"{own} # {note}"
        if self._landless_reason(title):
            return f"{self.cfg.placeholder_capital} # placeholder, {note}"
        if raw:
            self.result.warnings.append(
                f"{title.id}: {note} is not a live county and the title has "
                "none of its own; capital omitted"
            )
        return None

    def _county_of_capital(self, raw: str) -> str:
        """CK2 ``capital`` is a *province id*, not a title (`verified`)."""
        if raw.startswith("c_"):
            return raw
        if raw.startswith("b_"):
            placement = self.cfg.plan.get(raw)
            return placement.county if placement else ""
        try:
            return self.cfg.county_of_province.get(int(raw), "")
        except ValueError:
            return ""

    def _landless_reason(self, title: Ck2Title) -> str | None:
        if _flag(title.keywords.get("landless")):
            return "CK2 landless = yes"
        if title.source in TITULAR_FILES and not title.children and title.prefix != "b":
            return (
                f"CK2 {title.source}: a titular organisation title, landless in "
                "CK3 per docs/DECISIONS.md"
            )
        return None


def render(
    roots: Iterable[Ck2Title], config: LandedConfig
) -> LandedResult:
    """Render the whole CK3 ``landed_titles`` file for the converted mod."""
    renderer = _Renderer(config)
    out = renderer.out
    out.raw(
        "# Faerun de jure title tree, converted from CK2 common/landed_titles."
    )
    out.raw("# Rules: mappings/title_fields.csv, docs/step_titles.md.")
    out.raw("# A commented `b_x = { }` is a barony CK2 never built or that lane")
    out.raw("# baronies demoted for lack of map space; delete the # to promote it.")
    out.raw("# CK2 holy_site / caliphate / controls_religion lines are comments here:")
    out.raw("# CK3 inverts the relation and the religions lane owns the faith side.")
    out.raw("# CK2 gives baronies no `color`, so a barony takes its county's - 9933")
    out.raw("# of vanilla's 10041 baronies set one, and inventing a colour is out.")
    out.raw("")
    for title in roots:
        renderer.title(title, 0)
        out.blank()
    result = renderer.result
    result.text = out.text()
    result.counts = {
        f"{tier}_titles": len(ids) for tier, ids in sorted(result.emitted.items())
    }
    result.counts["commented_titles"] = len(result.commented)
    result.counts["cultural_name_keys"] = len(renderer._cn_keys)
    return result
