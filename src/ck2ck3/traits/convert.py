"""CK2 trait block -> CK3 trait block.

The rules, in the order they are applied to one CK2 trait (full statement of
each in `docs/step_traits.md`):

1. **Dedupe.** A CK2 trait that CK3 already has is *not* redefined; the
   converter records a rename (CK2 id -> CK3 id) instead. Two sources of truth:
   `mappings/vanilla_traits.csv` (the 112 traits of CK2 `00_traits.txt`) and an
   exact id match against CK3 1.19 `common/traits/00_traits.txt` for every other
   CK2-vanilla trait Faerûn ships.
2. **Classify.** `docs/evidence/faerun_custom_traits.csv` says `port`,
   `race_trait` or `comment`. `comment` traits are written as commented blocks.
3. **Map every key.** Trait properties through `mappings/trait_fields.csv`,
   everything else through `mappings/modifiers.csv` with its `scale`. A `none`
   row becomes a comment line inside the trait block; a key that is in neither
   table raises, so coverage cannot silently regress.
4. **Group/level.** Mutual-opposites cliques that show an ordered family become
   a CK3 `group` + `level` pair (:func:`trait_groups`).
5. **Race traits** additionally get `genetic`, `physical` and the
   `overrides/race_lifespan.csv` row.

Trait *ids are kept verbatim from CK2* so the localisation lane only has to
rename the loc key (`<id>` -> `trait_<id>`), never the id itself.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Sequence

from ..pdx import Block, Item, Node, format_scalar, write
from .tables import (
    CATEGORY_OF_CK2_KEY,
    CATEGORY_PRECEDENCE,
    FLATTENED_BLOCKS,
    Tables,
)

#: Years the CK3 engine gives a character before `life_expectancy` is added.
#: `assumed`: CK3 1.19 exposes no define for it (`common/defines/00_defines.txt`
#: has none), and the modifier is documented as "(years)"
#: (`localization/english/modifiers/modifiers_l_english.yml:1158`). Used to turn
#: an absolute D&D max age into the additive CK3 value.
CK3_BASE_LIFE_EXPECTANCY = 60

#: Prefix put on generated `group = ` names. Trait ids keep their CK2 name (the
#: localisation lane depends on it) but group names are free identifiers, and
#: CK3 already uses `kinslayer`, `wounded`, `beauty_good`… as group names
#: (`game/common/traits/00_traits.txt`), so they must not collide.
GROUP_PREFIX = "fae_"

#: CK2 booleans that CK3 expresses as a free-form `flag`, per
#: `mappings/trait_fields.csv` (`note` column names the flag vanilla uses).
FLAG_OF_CK2_KEY = {
    "cannot_marry": "can_not_marry",
    "is_epidemic": "epidemic_disease",
    "is_illness": "illness",
    "vice": "vice",
    "virtue": "virtue",
}

#: The two shapes CK2 uses for a per-trait opinion modifier (78 rows of
#: `mappings/modifiers.csv`): `opinion_of_<trait>` and `<trait>_opinion`.
#: CK2 keys whose value is a *trigger* block. `mappings/trait_fields.csv` maps
#: them onto CK3 `potential`, but the block's contents are CK2 trigger script
#: (`religion_group`, `has_landed_title`, CK2 culture names, `has_dlc = "Holy
#: Fury"`), which CK3 does not know. Porting CK2 triggers belongs to the
#: events lane, so the whole block is commented out - `ck3-tiger` reports 147
#: `unknown-field` errors when it is not.
TRIGGER_BLOCKS = frozenset({"potential", "trigger", "is_visible"})

#: CK3 keys that may legitimately appear several times in one trait
#: (`_traits.info`: `flag` "can add multiple", and the modifier collections).
REPEATABLE = frozenset(
    {"flag", "triggered_opinion", "culture_modifier", "faith_modifier", "tracks"}
)

#: `_traits.info:108,117`: `random_creation`/`random_creation_weight` and the
#: manual inherit chances are "only applicable to" / "can not be set on" a
#: genetic trait, and `birth` is the opposite way round. CK2 has no such rule,
#: so a trait can arrive with a combination CK3 rejects.
GENETIC_ONLY = frozenset({"birth"})
NON_GENETIC_ONLY = frozenset(
    {"random_creation_weight", "inherit_chance", "both_parent_has_trait_inherit_chance"}
)

#: CK3 keys that `mappings/modifiers.csv` maps a CK2 trait key onto but that are
#: *not* character scope, so they cannot sit in a trait block at all
#: (docs/mapping_modifiers.md, "In a trait"). `verified` by ck3-tiger 1.19:
#: "`cultural_acceptance_gain_mult` is a modifier for culture but expected
#: character" (from `mappings/modifiers.csv:36`, `culture_flex`). Emitted as a
#: comment; the row needs the mappings lane to reclassify it.
NON_CHARACTER_SCOPE = frozenset({"cultural_acceptance_gain_mult"})

_TRAIT_OPINION_RE = re.compile(r"\A(?:opinion_of_(?P<a>.+)|(?P<b>.+)_opinion)\Z")


# --------------------------------------------------------------------------
# results
# --------------------------------------------------------------------------
@dataclass
class Rename:
    """A CK2 trait id that resolves to an existing CK3 trait id."""

    ck2_trait: str
    ck3_trait: str
    status: str
    source: str
    note: str


@dataclass
class Unported:
    ck2_trait: str
    source_file: str
    reason: str


@dataclass
class Converted:
    """One CK3 trait block plus what had to be said about it."""

    ck2_trait: str
    block: Block
    source_file: str
    kind: str  # "port" | "race_trait"
    comments: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class UnmappedKey(KeyError):
    """A CK2 trait key is in neither mapping table."""


# --------------------------------------------------------------------------
# group / level heuristic
# --------------------------------------------------------------------------
def _tokens(name: str) -> list[str]:
    return name.split("_")


def _shared_token(names: Sequence[str]) -> str | None:
    """The longest underscore token present in every name, or None."""
    common = set(_tokens(names[0]))
    for name in names[1:]:
        common &= set(_tokens(name))
    common = {t for t in common if t and not t.isdigit()}
    if not common:
        return None
    return max(sorted(common), key=len)


def _numeric_suffix(name: str) -> int | None:
    tail = _tokens(name)[-1]
    return int(tail) if tail.isdigit() else None


def opposites_cliques(traits: dict[str, Block]) -> list[list[str]]:
    """Sets of traits that all list each other in `opposites`, in CK2 order.

    CK2 has no trait group: a tiered family is expressed by every member listing
    every other member as an opposite. That mutual closure is the only
    machine-checkable signal, so it is the one the converter uses.
    """
    order = {name: i for i, name in enumerate(traits)}
    opposites: dict[str, set[str]] = {}
    for name, block in traits.items():
        value = block.get("opposites")
        if isinstance(value, Block):
            opposites[name] = {str(v) for v in value.list_values()}
    out: list[list[str]] = []
    for name, opp in opposites.items():
        clique = {name} | opp
        if len(clique) < 3 or not clique <= set(order):
            continue
        if not all(clique - {m} == opposites.get(m, set()) for m in clique):
            continue
        ranked = sorted(clique, key=lambda n: order[n])
        if ranked[0] == name:
            out.append(ranked)
    return out


def trait_groups(traits: dict[str, Block]) -> dict[str, tuple[str, int]]:
    """Map trait id -> (CK3 group name, level).

    A mutual-opposites clique (:func:`opposites_cliques`) of at least three
    members becomes a group only when it also shows an *ordered family*:

    * every member ends in a distinct ``_<n>`` -> that ``n`` is the level
      (``pagan_branch_1..4``, ``scarred_type_1..10``);
    * otherwise every member must share one underscore token, and the level is
      the CK2 declaration order (``sorcerer`` < ``trained_sorcerer`` < … and
      ``dragon_wyrmling`` < ``dragon_young`` < ``dragon_adult`` <
      ``dragon_ancient``; both ascend in the source file).

    Cliques with neither signal are alternatives, not tiers, and get no group:
    that is what keeps ``genius/quick/slow/imbecile`` and
    ``homosexual/bisexual/asexual`` out. The group name is the shared token,
    prefixed with ``fae_``; a name claimed by two cliques falls back to the
    first member's id, so ``warlock`` (the class tiers) and ``warlock_fey…``
    (the patron alternatives) do not merge.
    """
    claimed: dict[str, list[str]] = {}
    plans: list[tuple[str, list[tuple[str, int]]]] = []
    for clique in opposites_cliques(traits):
        numbers = [_numeric_suffix(n) for n in clique]
        if all(n is not None for n in numbers) and len(set(numbers)) == len(numbers):
            stems = {re.sub(r"_\d+\Z", "", n) for n in clique}
            # `pagan_branch_1..4` -> one stem, which *is* the group name.
            token = stems.pop() if len(stems) == 1 else _shared_token(sorted(stems))
            levels = list(zip(clique, [int(n) for n in numbers]))  # type: ignore[arg-type]
        else:
            token = _shared_token(clique)
            levels = [(n, i + 1) for i, n in enumerate(clique)]
        if not token:
            continue
        claimed.setdefault(token, []).append(clique[0])
        plans.append((token, levels))
    out: dict[str, tuple[str, int]] = {}
    for token, levels in plans:
        name = token if len(claimed[token]) == 1 else levels[0][0]
        for trait, level in levels:
            out[trait] = (f"{GROUP_PREFIX}{name}", level)
    return out


# --------------------------------------------------------------------------
# one trait
# --------------------------------------------------------------------------
def _comment(key: str, value: object, note: str) -> str:
    return f"# CK2: {key} = {_render(value)}  (no CK3 equivalent: {note})"


def _comment_lines(key: str, value: Block, note: str) -> list[str]:
    """A whole CK2 block as commented script, one line per source line."""
    head = f"# CK2: {key} = {{  (no CK3 equivalent: {note})"
    body = write(Block(entries=list(value.entries), end_comments=list(value.end_comments)))
    return [head, *(f"# {line}" if line else "#" for line in body.splitlines()), "# }"]


def _render(value: object) -> str:
    if isinstance(value, Block):
        if all(isinstance(e, Item) for e in value.entries):
            inner = " ".join(_render(e.value) for e in value.entries)
            return f"{{ {inner} }}"
        inner = " ".join(
            f"{e.key} {e.op} {_render(e.value)}"
            for e in value.entries
            if isinstance(e, Node)
        )
        return f"{{ {inner} }}"
    if value is None:
        return ""
    try:
        return format_scalar(value)
    except TypeError:  # pragma: no cover - defensive
        return str(value)


def _scaled(value: object, scale: float) -> object:
    if scale == 1.0 or not isinstance(value, (int, float)) or isinstance(value, bool):
        return value
    out = value * scale
    if isinstance(value, int) and float(out).is_integer():
        return int(out)
    return round(out, 4)


def _is_yes(value: object) -> bool:
    return value is True or (isinstance(value, str) and value.lower() == "yes")


class TraitConverter:
    """Converts CK2 trait blocks with one shared set of tables and counters."""

    def __init__(
        self,
        tables: Tables,
        *,
        icons: dict[str, str] | None = None,
        live_traits: Iterable[str] = (),
        groups: dict[str, tuple[str, int]] | None = None,
        renames: dict[str, str] | None = None,
    ) -> None:
        self.tables = tables
        self.icons = icons or {}
        self.live = set(live_traits)
        self.groups = groups or {}
        self.renames = renames or {}
        self.counts: dict[str, int] = {}
        #: Comment lines produced while converting the entry in flight; drained
        #: by :meth:`convert` so a comment stays where its CK2 key was.
        self._pending: list[str] = []

    def _bump(self, name: str, by: int = 1) -> None:
        self.counts[name] = self.counts.get(name, 0) + by

    # -- public ------------------------------------------------------------
    def convert(
        self, name: str, source: Block, *, source_file: str, kind: str
    ) -> Converted:
        out = Converted(
            ck2_trait=name, block=Block(multiline=True), source_file=source_file, kind=kind
        )
        categories: list[str] = []
        pending: list[str] = []  # comment lines to attach to the next entry
        has_genetic = False
        for entry in source.entries:
            if isinstance(entry, Item):
                pending.append(_comment("(bare item)", entry.value, "list entry in a trait block"))
                continue
            assert isinstance(entry, Node)
            leading = list(entry.leading_comments) + pending
            pending = []
            self._pending = []
            produced = self._convert_node(entry, out, categories)
            comments, self._pending = self._pending, []
            out.comments.extend(comments)
            if not produced:
                pending = leading + comments
                continue
            first = produced[0]
            first.leading_comments = leading + comments + list(first.leading_comments)
            first.blank_before = entry.blank_before
            if entry.trailing_comment:
                produced[-1].trailing_comment = entry.trailing_comment
            for node in produced:
                if isinstance(node, Node) and node.key == "genetic":
                    has_genetic = True
                out.block.append(node)
        for text in pending:
            out.block.end_comments.append(text)
        if out.block.entries:
            out.block.entries[0].blank_before = False

        if categories:
            best = min(
                categories,
                key=lambda c: CATEGORY_PRECEDENCE.index(c)
                if c in CATEGORY_PRECEDENCE
                else len(CATEGORY_PRECEDENCE),
            )
            if len(set(categories)) > 1:
                dropped = ", ".join(sorted(set(categories) - {best}))
                out.block.append(
                    Node(
                        key="category",
                        value=best,
                        leading_comments=[
                            "# CK2 set several category booleans; CK3 category is "
                            f"single-valued, so {dropped} could not be kept "
                            "(docs/step_traits.md, precedence)"
                        ],
                    )
                )
                self._bump("category_collisions")
            else:
                out.block.append(Node(key="category", value=best))

        if name in self.groups:
            group, level = self.groups[name]
            out.block.append(Node(key="group", value=group, blank_before=True))
            out.block.append(Node(key="level", value=level))
            self._bump("grouped")

        if kind == "race_trait":
            self._add_race_fields(name, out, has_genetic=has_genetic)

        icon = self.icons.get(name)
        if icon:
            out.block.append(Node(key="icon", value=icon, blank_before=True))
            self._bump("icons")
        self._finalise(out)
        return out

    def _finalise(self, out: Converted) -> None:
        """Enforce the CK3 rules a mechanical key-by-key map cannot see.

        Three of them, each one an error `ck3-tiger` reports otherwise:

        * a key CK3 allows once must appear once (CK2 `customizer = no` and
          `hidden = yes` both ask for `shown_in_ruler_designer = no`);
        * `compatibility` entries merge into one block;
        * `birth` needs `genetic = yes`, while `random_creation_weight` and the
          manual inherit chances need `genetic = no` (`_traits.info:108,117`).

        Nothing is dropped: every removed entry leaves a comment saying why.
        """
        genetic = any(
            isinstance(e, Node) and e.key == "genetic" and _is_yes(e.value)
            for e in out.block.entries
        )
        kept: list[object] = []
        seen: set[str] = set()
        compatibility: Node | None = None
        for entry in out.block.entries:
            if not isinstance(entry, Node):
                kept.append(entry)
                continue
            key = entry.key
            if key == "compatibility" and isinstance(entry.value, Block):
                if compatibility is None:
                    compatibility = entry
                    kept.append(entry)
                else:
                    compatibility.value.entries.extend(entry.value.entries)
                continue
            if key in seen and key not in REPEATABLE:
                out.block.end_comments.append(
                    f"# CK2 asked for {key} = {_render(entry.value)} a second time; "
                    "CK3 allows it once, the first value is kept"
                )
                self._bump("duplicate_keys")
                continue
            if key in GENETIC_ONLY and not genetic:
                out.block.end_comments.append(
                    _comment(
                        key,
                        entry.value,
                        "CK3 allows it only on a genetic trait "
                        "(_traits.info:107) and this trait is not genetic",
                    )
                )
                self._bump("genetic_conflicts")
                continue
            if key in NON_GENETIC_ONLY and genetic:
                out.block.end_comments.append(
                    _comment(
                        key,
                        entry.value,
                        "CK3 forbids it on a genetic trait "
                        "(_traits.info:108,117); genetic inheritance replaces it",
                    )
                )
                self._bump("genetic_conflicts")
                continue
            seen.add(key)
            kept.append(entry)
        out.block.entries = kept  # type: ignore[assignment]

    # -- internals ---------------------------------------------------------
    def _add_race_fields(self, name: str, out: Converted, *, has_genetic: bool) -> None:
        """`design_races.md` §2: a race trait is genetic, physical and long-lived."""
        extra = Block(multiline=True)
        if not has_genetic:
            extra.append(Node(key="genetic", value=True))
        extra.append(Node(key="physical", value=True))
        row = self.tables.race_lifespan.get(name)
        if row is None:
            out.warnings.append(
                f"{name}: race trait with no overrides/race_lifespan.csv row; "
                "no life_expectancy emitted"
            )
            self._bump("race_without_lifespan")
        elif row.immortal:
            # `immortal` may already have come from the CK2 block; do not repeat.
            if not any(
                isinstance(e, Node) and e.key == "immortal" for e in out.block.entries
            ):
                extra.append(Node(key="immortal", value=True))
            self._bump("race_immortal")
        elif row.life_expectancy is not None:
            extra.append(
                Node(
                    key="life_expectancy",
                    value=row.life_expectancy,
                    trailing_comment=(
                        f"# {row.race}: D&D max age {row.dnd_max_age} - CK3 base "
                        f"{CK3_BASE_LIFE_EXPECTANCY} (overrides/race_lifespan.csv)"
                    ),
                )
            )
            self._bump("race_lifespan")
        else:
            self._bump("race_lifespan_blank")
        if extra.entries:
            extra.entries[0].blank_before = True
            extra.entries[0].leading_comments = [
                "# race trait (docs/design_races.md 2)"
            ]
            out.block.entries.extend(extra.entries)

    def _convert_node(
        self, entry: Node, out: Converted, categories: list[str]
    ) -> list[Node]:
        key, value = entry.key, entry.value

        # 1. a CK2 trait *property*
        mapping = self.tables.field_of(key)
        if mapping is not None:
            return self._convert_field(entry, mapping, out, categories)

        # 2. a modifier
        modifier = self.tables.modifier_of(key)
        if modifier is not None:
            return self._convert_modifier(entry, modifier, out)

        raise UnmappedKey(
            f"trait {out.ck2_trait}: key {key!r} is in neither "
            "mappings/trait_fields.csv nor mappings/modifiers.csv"
        )

    def _convert_field(
        self, entry: Node, mapping, out: Converted, categories: list[str]
    ) -> list[Node]:
        key, value = entry.key, entry.value

        if key in TRIGGER_BLOCKS and isinstance(value, Block):
            self._pending.extend(
                _comment_lines(
                    key,
                    value,
                    "CK2 trigger script; CK3 trigger syntax differs "
                    "(religion_group, has_landed_title, CK2 culture names) - "
                    "the events lane owns trigger translation",
                )
            )
            self._bump("trigger_blocks_commented")
            return []

        if key in FLATTENED_BLOCKS and isinstance(value, Block):
            # `command_modifier`/`combat`/`country` keys become flat trait
            # modifiers in CK3 (mappings/trait_fields.csv note).
            produced: list[Node] = []
            for inner in value.entries:
                if not isinstance(inner, Node):
                    continue
                sub = self.tables.modifier_of(inner.key)
                if sub is None:
                    raise UnmappedKey(
                        f"trait {out.ck2_trait}: {key}.{inner.key!r} is in neither "
                        "mapping table"
                    )
                produced.extend(self._convert_modifier(inner, sub, out, prefix=key))
            if not produced and not self._pending:
                self._pending.append(
                    _comment(key, value, f"{mapping.note}; block had no mappable key")
                )
            return produced

        if not mapping.mapped:
            self._pending.append(_comment(key, value, mapping.note))
            self._bump("field_comments")
            return []

        ck3 = mapping.ck3_key

        if ck3 == "category":
            category = CATEGORY_OF_CK2_KEY.get(key)
            if category and _is_yes(value):
                categories.append(category)
                return []
            self._pending.append(_comment(key, value, f"{mapping.note}; value not yes"))
            return []

        if ck3 == "flag":
            flag = FLAG_OF_CK2_KEY.get(key)
            if flag and _is_yes(value):
                return [Node(key="flag", value=flag)]
            self._pending.append(_comment(key, value, mapping.note))
            return []

        if key == "hidden" and _is_yes(value):
            # CK3 cannot hide a trait from the character window; the closest is
            # to keep it out of the encyclopedia and the ruler designer.
            return [
                Node(key="shown_in_encyclopedia", value=False),
                Node(key="shown_in_ruler_designer", value=False),
            ]

        if key in ("agnatic", "enatic"):
            if _is_yes(value):
                sex = "male" if key == "agnatic" else "female"
                return [Node(key="parent_inheritance_sex", value=sex)]
            return []

        if key == "cannot_inherit":
            return [Node(key="inheritance_blocker", value="all" if _is_yes(value) else "none")]

        if key == "congenital":
            return [Node(key="genetic", value=_is_yes(value))]

        if key == "random":
            # CK3 has no boolean; weight 0 means "never picked randomly".
            return [] if _is_yes(value) else [Node(key="random_creation_weight", value=0)]

        if key == "customizer":
            return [Node(key="shown_in_ruler_designer", value=_is_yes(value))]

        if key == "birth":
            return [Node(key="birth", value=_scaled(value, 0.01))]

        if key == "opposites" and isinstance(value, Block):
            remapped = self._remap_trait_list(value, out)
            # Every entry was dropped (each is a commented-out CK2 trait): emit
            # nothing rather than `opposites = { }`. `homosexual` hits this
            # since the 2026-09-08 policy ports it instead of deduping it.
            if not remapped.entries:
                return []
            return [Node(key="opposites", value=remapped)]

        if key == "leadership_traits" and isinstance(value, Block):
            self._pending.append(_comment(key, value, mapping.note))
            return []

        return [Node(key=ck3, op=entry.op, value=value, quoted_value=entry.quoted_value)]

    def _remap_trait_list(self, value: Block, out: Converted) -> Block:
        """Rewrite a list of CK2 trait ids through the dedupe rename map."""
        block = Block()
        for item in value.entries:
            if not isinstance(item, Item):
                continue
            name = str(item.value)
            target = self.renames.get(name, name)
            if target not in self.live and target not in self.tables.ck3_trait_ids:
                self._pending.append(
                    f"# CK2: opposites entry {name} was not ported "
                    "(common/traits/fae_traits_unported.txt)"
                )
                continue
            block.append(Item(value=target))
        return block

    def _convert_modifier(
        self, entry: Node, mapping, out: Converted, prefix: str = ""
    ) -> list[Node]:
        key, value = entry.key, entry.value
        label = f"{prefix}.{key}" if prefix else key

        if isinstance(value, Block):
            self._pending.append(_comment(label, value, "block-valued CK2 modifier"))
            self._bump("modifier_comments")
            return []

        if not mapping.mapped:
            compat = self._compatibility(key, value, out)
            self._pending.append(_comment(label, value, mapping.note))
            self._bump("modifier_comments")
            return compat

        if mapping.ck3_key in NON_CHARACTER_SCOPE:
            self._pending.append(
                _comment(
                    label,
                    value,
                    f"CK3 {mapping.ck3_key} is not a character-scope modifier, so "
                    "it cannot sit in a trait (ck3-tiger 1.19); "
                    "mappings/modifiers.csv needs to reclassify the row",
                )
            )
            self._bump("wrong_scope_comments")
            return []

        if mapping.placeholder:
            self._pending.append(
                _comment(
                    label,
                    value,
                    f"CK3 key {mapping.ck3_key} is a placeholder - "
                    "needs the cultures/religions name map",
                )
            )
            self._bump("placeholder_comments")
            return []

        return [Node(key=mapping.ck3_key, value=_scaled(value, mapping.scale))]

    def _compatibility(self, key: str, value: object, out: Converted) -> list[Node]:
        """CK2 `<trait>_opinion` / `opinion_of_<trait>` -> CK3 `compatibility`.

        `mappings/modifiers.csv` marks these 78 keys `none` and names
        `compatibility = { <trait> = X }` (`_traits.info:157`) as the
        replacement. Emitted only when the named trait really is a trait we
        keep; otherwise the comment alone carries the information.
        """
        match = _TRAIT_OPINION_RE.match(key)
        if not match:
            return []
        target = match.group("a") or match.group("b")
        target = self.renames.get(target, target)
        if target not in self.live and target not in self.tables.ck3_trait_ids:
            return []
        self._bump("compatibility")
        return [
            Node(
                key="compatibility",
                value=Block(entries=[Node(key=target, value=value)], multiline=True),
            )
        ]
