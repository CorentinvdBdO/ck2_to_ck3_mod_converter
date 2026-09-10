"""Step ``events``: port Faerûn's **new** CK2 events to CK3 1.19 syntax.

README §5 step 3, the `new` slice (1762 events). The `modified` 2911 events
and `common/on_actions` are later lanes - `docs/evidence/HANDOFF_events.md`
says what they need from here. Rules, id scheme, theme table, counts and open
questions: ``docs/step_events.md``.

Architecture is the `decisions` step's (`docs/step_decisions.md`), reused
rather than re-implemented: the same three vocabulary tables
(`mappings/triggers.csv`, `effects.csv`, `event_targets.csv`), the same
recursive :func:`ck2ck3.steps.decisions.convert_block`, the same
convertibility score, and the same stabilisation policy - **a half-converted
body is never live**. Everything below ``[events] min_score`` (or failing any
of the hard gates in :data:`GATE_REASONS`) is emitted as an inert stub:
``hidden = yes``, ``trigger = { always = no }``, empty ``immediate``, with the
whole converted draft kept above it as ``# draft:`` comment lines.

Runs after ``decisions`` (which shares the vocabulary tables), ``traits``
(bare ``<trait> = yes/no`` shorthand needs ``ctx.data["traits"]``) and ``loc``
(event ``desc``/option ``name`` are CK2 loc keys the `loc` step ports
verbatim; ``ctx.data["loc"]["keys"]`` is what the miss count is measured
against).
"""

from __future__ import annotations

import csv
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from .. import pdx
from ..config import REPO_ROOT
from ..context import Context, StepResult
from ..decisions_vocab import SCOPE_WORDS, VocabRow, read_vocab_csv
from ..ids import build_event_id_map, event_id, event_namespace
from ..pdx import Block, Item, Node, VarRef
from .decisions import ConvertStats, TraitInfo, convert_block
from .decisions import _render_comment as render_ck2_comment

DESCRIPTION = "port Faerûn's new CK2 events to CK3 1.19 syntax"
#: `tc_template` owns two *sub*folders of `events/` (`events/decisions_events`,
#: `events/story_cycles`, both vanilla shadows); this step owns the folder
#: itself and only writes new `<prefix>_*.txt` files there, so the two are
#: file-disjoint (`docs/step_events.md` §7).
OUTPUTS: tuple[str, ...] = ("events",)

#: CK2 event kind -> the CK3 `type =` it becomes.
#: `verified` against `game/events/_events.info`: CK3 has exactly four event
#: types (`character_event`, `letter_event`, `court_event`, `activity_event`)
#: and defaults to `character_event`. CK2's `long_character_event` and
#: `narrative_event` are the same character-scope event in a different window,
#: so both land on `character_event` (CK3 expresses the window difference with
#: `window = big_event_window`, which this step does not emit - it changes only
#: presentation and would be a guess per event).
EMIT_KINDS: dict[str, str] = {
    "character_event": "character_event",
    "letter_event": "letter_event",
    "long_character_event": "character_event",
    "narrative_event": "character_event",
}
OUT_OF_SCOPE_REASONS: dict[str, str] = {
    "province_event": (
        "province-scope root; CK3 has no province event type and a non-character "
        "root scope must be hidden or major (game/events/_events.info)"
    ),
    "society_quest_event": (
        "society quest event; societies do not exist in CK3 "
        "(docs/mechanics_inventory.md)"
    ),
}
#: README §5 step 3 is the `new` slice only.
EMIT_STATUSES = frozenset({"new"})

#: CK2 effect keys that fire another event. Handled by a hook rather than the
#: effect table, because the CK3 form depends on whether the *target* event is
#: itself emitted live (`docs/step_events.md` §5).
EVENT_FIRING_KEYS = frozenset(
    {
        "character_event", "letter_event", "narrative_event",
        "long_character_event", "province_event", "society_quest_event",
    }
)
#: The only fields of a CK2 event-firing block this step carries into CK3's
#: `trigger_event`. Anything else in the block (CK2 `random`, `tooltip`,
#: `weight_multiplier`) makes the whole call unmapped rather than half-ported.
TRIGGER_EVENT_FIELDS = frozenset({"id", "days", "months", "years"})

#: CK2 event top-level keys this step handles itself (everything else at the
#: top level of a CK2 event is an implicit root-scope trigger condition and is
#: folded into `trigger = { }`, `docs/step_events.md` §3).
STRUCTURAL_EVENT_KEYS = frozenset(
    {
        "id", "desc", "title", "picture", "border", "trigger", "immediate",
        "after", "option", "hide_window", "is_triggered_only", "major",
        "major_trigger", "mean_time_to_happen", "fail_trigger_effect",
        # CK2 presentation/AI fields with no CK3 event field: dropped to a
        # comment, never scored (they are not trigger/effect vocabulary).
        "portrait", "sound", "notification", "hide_from", "hide_new",
        "show_root", "show_from_from", "weight_multiplier", "quest_target",
        "min_age", "max_age", "prisoner", "only_men", "only_women",
        "only_rulers", "capable_only", "only_capable",
    }
)
#: CK2 presentation fields that become a trailing `# CK2:` comment.
COMMENT_ONLY_KEYS = frozenset(
    {
        "portrait", "sound", "notification", "hide_from", "hide_new",
        "show_root", "show_from_from", "weight_multiplier", "quest_target",
    }
)
#: CK2 event *header* trigger shorthands -> a CK3 trigger line. These are
#: top-level keys whose CK3 form needs an operator or a polarity flip, so they
#: cannot live in `mappings/triggers.csv` (whose rows are key->key only).
#: Every CK3 key here is in `docs/evidence/ck3_vocab_ground_truth.txt`
#: (`verified`, pinned by `tests/test_events.py::test_header_trigger_keys_are_real_ck3_keys`).
#: value: (ck3_key, operator, value-transform)
EVENT_HEADER_TRIGGERS: dict[str, tuple[str, str, str]] = {
    "min_age": ("age", ">=", "copy"),
    "max_age": ("age", "<=", "copy"),
    "prisoner": ("is_imprisoned", "=", "copy"),
    "only_men": ("is_male", "=", "copy"),
    "only_women": ("is_female", "=", "copy"),
    "only_rulers": ("is_ruler", "=", "copy"),
    "capable_only": ("is_incapable", "=", "invert"),
    "only_capable": ("is_incapable", "=", "invert"),
}

#: CK2's saved-target prefix. ``event_target:x = { ... }`` opens the scope of
#: a target saved with ``save_event_target_as = x``; CK3 spells the identical
#: construct ``scope:x = { ... }`` (`verified`,
#: `game/events/witch_events.txt:56` `scope:guardian = { ... }`).
EVENT_TARGET_PREFIX = "event_target:"
EVENT_TARGET_RE = re.compile(r"^event_target:([A-Za-z_][A-Za-z_0-9]*)$")

#: CK2 keys whose *argument* is an id no lane of this converter emits, or a
#: nested field CK3 spells differently. The vocabulary tables map the key
#: itself, which is not enough: ck3-tiger flagged every one of these in the
#: first live build (`docs/evidence/tiger_events_2026-09-10_summary.txt`, 2026-09-10), so
#: they are commented out here and the event is demoted with the rest.
#: Resolving them properly is `docs/step_events.md` §9 open question 1.
REJECT_CK2_KEYS: dict[str, str] = {
    # `common/modifiers` is emitted by no step; every CK2 modifier id is a
    # dangling reference (`error(missing-item): modifier X not defined`).
    "add_character_modifier": "CK2 modifier id; no step emits common/modifiers",
    "remove_character_modifier": "CK2 modifier id; no step emits common/modifiers",
    "has_character_modifier": "CK2 modifier id; no step emits common/modifiers",
    "add_province_modifier": "CK2 modifier id; no step emits common/modifiers",
    "remove_province_modifier": "CK2 modifier id; no step emits common/modifiers",
    "has_province_modifier": "CK2 modifier id; no step emits common/modifiers",
    "add_holding_modifier": "CK2 modifier id; no step emits common/modifiers",
    "remove_holding_modifier": "CK2 modifier id; no step emits common/modifiers",
    # A CK3 faith/culture argument is a *prefixed* reference (`faith:x`,
    # `culture:x`); this step only ever rewrites keys, never values
    # (docs/step_decisions.md §3 limitation 3), so the bare CK2 id reaches
    # CK3 as `error(unknown-field): unknown token x`.
    "religion": "CK3 wants `faith = faith:<id>`; this step does not rewrite values",
    "religion_group": "CK3 wants `religion = religion:<id>`; this step does not rewrite values",
    "set_religion": "CK3 wants `set_faith = faith:<id>`; this step does not rewrite values",
    "secret_religion": "CK3 wants `faith:<id>`; this step does not rewrite values",
    "set_secret_religion": "CK3 wants `faith:<id>`; this step does not rewrite values",
    "culture": "CK3 wants `culture = culture:<id>`; this step does not rewrite values",
    "culture_group": "CK3 has no culture group; heritage/language pillars replace it",
    "set_culture": "CK3 wants `set_culture = culture:<id>`; this step does not rewrite values",
    "set_graphical_culture": "CK3 graphical culture is a culture field, not an effect",
    # CK2 spells a modifier's lifetime `duration = N` (-1 = forever); CK3
    # spells it `years`/`months`/`days` inside the effect block.
    "duration": "CK2 modifier lifetime; CK3 spells it years/months/days",
    # CK2 DLC names ("Holy Fury") are not CK3 dlc_metadata names.
    "has_dlc": "CK2 DLC name; CK3 dlc_metadata has no counterpart",
    "lacks_dlc": "CK2 DLC name; CK3 dlc_metadata has no counterpart",
}

#: Why an event may not go live even at score 1.0. Each is a real failure
#: mode, not a style preference - see `docs/step_events.md` §4.
GATE_REASONS: dict[str, str] = {
    "score": "convertibility below [events] min_score",
    "mtth": (
        "CK2 mean_time_to_happen: CK3 has no MTTH on events, only on_action "
        "pulses, and this lane does not write on_actions"
    ),
    "from_scope": (
        "uses CK2 FROM/FROMFROM: CK3 has no FROM and nothing saves "
        "scope:ck2_from for this event yet (docs/loc_codes.md)"
    ),
    "no_option": "not hidden and no option survived conversion; a shown CK3 event needs one",
    "dead_call": "fires an event that is itself stubbed or out of scope",
    "ck2_variable": (
        "uses a CK2 `@name` reader variable; CK3's reader has no such "
        "definition and drops the line (error(reader-directives))"
    ),
    "unsaved_scope": (
        "reads a saved scope this event never saves; a CK3 saved scope does "
        "not outlive its event, unlike a CK2 event_target on the character"
    ),
}


@dataclass
class EventsConfig:
    provenance: Path = REPO_ROOT / "docs" / "evidence" / "events_provenance.csv"
    #: 1.0 = only a fully mapped event goes live, the `decisions` lane's
    #: stabilisation policy (docs/step_decisions.md §3b).
    min_score: float = 1.0
    enabled: bool = True
    evidence: Path = REPO_ROOT / "docs" / "evidence" / "events_convertibility.csv"
    triggers: Path = REPO_ROOT / "mappings" / "triggers.csv"
    effects: Path = REPO_ROOT / "mappings" / "effects.csv"
    themes_csv: Path = REPO_ROOT / "mappings" / "event_themes.csv"
    default_theme: str = "default"

    @classmethod
    def from_raw(cls, raw: dict) -> "EventsConfig":
        def _resolve(value: str | None, default: Path) -> Path:
            path = Path(value).expanduser() if value else default
            return path if path.is_absolute() else REPO_ROOT / path

        return cls(
            provenance=_resolve(raw.get("provenance"), cls.provenance),
            min_score=float(raw.get("min_score", cls.min_score)),
            enabled=bool(raw.get("enabled", cls.enabled)),
            evidence=_resolve(raw.get("evidence"), cls.evidence),
            triggers=_resolve(raw.get("triggers"), cls.triggers),
            effects=_resolve(raw.get("effects"), cls.effects),
            themes_csv=_resolve(raw.get("themes_csv"), cls.themes_csv),
            default_theme=str(raw.get("default_theme", cls.default_theme)),
        )


@dataclass
class ProvenanceRow:
    id: str
    kind: str
    status: str
    faerun_file: str


def read_provenance(path: Path) -> list[ProvenanceRow]:
    rows: list[ProvenanceRow] = []
    with open(path, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            rows.append(
                ProvenanceRow(
                    id=row["id"], kind=row["kind"], status=row["status"],
                    faerun_file=row["faerun_file"],
                )
            )
    return rows


def read_themes(path: Path) -> dict[tuple[str, str], str]:
    """``mappings/event_themes.csv`` -> ``(ck2_field, ck2_value) -> ck3 theme``."""
    table: dict[tuple[str, str], str] = {}
    if not path.is_file():
        return table
    with open(path, encoding="utf-8-sig", newline="") as handle:
        for row in csv.reader(handle):
            if not row or row[0].lstrip().startswith("#"):
                continue
            if row[0].strip() == "ck2_field":
                continue
            field_name, value, theme = (row + [""] * 3)[:3]
            if theme.strip():
                table[(field_name.strip(), value.strip())] = theme.strip()
    return table


# -- scope-word values -------------------------------------------------------

def rewrite_scope_values(block: Block) -> int:
    """Rewrite CK2 scope words and event targets used as a *value*.

    ``convert_block`` rewrites scope words used as a **key**
    (``FROM = { ... }``); CK2 also uses them as arguments
    (``add_opinion = { who = FROM }``, ``character = event_target:my_guy``),
    which the key pass never sees. Left alone they reach CK3 as the bare
    token ``FROM`` (``error(unknown-field)``). Returns how many rewrites
    landed on the FROM family - a hard live-gate, since CK3 has no FROM and
    nothing saves ``scope:ck2_from`` for a ported event yet.
    """
    from_uses = 0

    def visit(b: Block) -> None:
        nonlocal from_uses
        for entry in b.entries:
            if isinstance(entry, Node) and entry.key.startswith("scope:ck2_from"):
                from_uses += 1
            value = getattr(entry, "value", None)
            if isinstance(value, Block):
                visit(value)
                continue
            if isinstance(value, str):
                if value.upper() in SCOPE_WORDS:
                    new = SCOPE_WORDS[value.upper()]
                    if new.startswith("scope:ck2_from"):
                        from_uses += 1
                    entry.value = new
                elif value.startswith(EVENT_TARGET_PREFIX):
                    entry.value = "scope:" + value[len(EVENT_TARGET_PREFIX):]

    visit(block)
    return from_uses


def scope_usage(block: Block) -> tuple[set[str], set[str]]:
    """``(saved, used)`` saved-scope names in one converted event body.

    A CK3 saved scope lives only for the duration of the event that saved it
    (unlike a CK2 ``event_target``, which is stored on the character), so an
    event that reads ``scope:x`` without a ``save_scope_as = x`` of its own is
    broken at runtime - ``script_system.cpp`` "Cannot find scope". This is the
    ``unsaved_scope`` live gate.
    """
    saved: set[str] = set()
    used: set[str] = set()

    def visit(b: Block) -> None:
        for entry in b.entries:
            if isinstance(entry, Node):
                if entry.key in ("save_scope_as", "save_temporary_scope_as") and isinstance(entry.value, str):
                    saved.add(entry.value)
                if entry.key.startswith("scope:"):
                    used.add(entry.key.split(".", 1)[0][len("scope:"):])
                if isinstance(entry.value, str) and entry.value.startswith("scope:"):
                    used.add(entry.value.split(".", 1)[0][len("scope:"):])
            value = getattr(entry, "value", None)
            if isinstance(value, Block):
                visit(value)

    visit(block)
    return saved, used


# -- the event-firing hook ---------------------------------------------------

def make_event_hook(
    *,
    ck3_id_of: dict[str, str],
    live_ids: set[str],
    scoped_out: dict[str, str],
):
    """A `convert_block` hook for CK2's event-firing effects.

    ``character_event = { id = X days = 5 }`` becomes
    ``trigger_event = { id = <ck3 id> days = 5 }`` **only** when X is an event
    this run emits *live*. Anything else - a target that is stubbed, out of
    scope, or not a `new` event at all - stays a `# CK2:` comment: the
    `decisions` lane learned the hard way that a `trigger_event` to an id CK3
    cannot resolve fails validation at load (`docs/step_decisions.md` §3b.2).
    """
    calls: list[str] = []

    def hook(entry: Node, kind: str) -> tuple[Node | None, str]:
        if kind != "effect" or not isinstance(entry.value, Block):
            return None, "CK2 event-firing call outside an effect block"
        target: str | None = None
        extra: list[str] = []
        delay: Node | None = None
        for sub in entry.value.entries:
            if not isinstance(sub, Node):
                extra.append("<bare item>")
                continue
            if sub.key == "id":
                target = str(sub.value)
            elif sub.key in TRIGGER_EVENT_FIELDS and isinstance(sub.value, (int, float, str)):
                delay = Node(key=sub.key, op="=", value=sub.value)
            else:
                extra.append(sub.key)
        if target is None:
            return None, "event-firing call with no id"
        calls.append(target)
        if extra:
            return None, (
                f"target {target}: CK3 trigger_event has no counterpart for "
                f"{', '.join(sorted(set(extra)))}"
            )
        if target in scoped_out:
            return None, f"target {target} is out of scope: {scoped_out[target]}"
        if target not in ck3_id_of:
            return None, (
                f"target {target} is not a `new` event this lane ports "
                "(vanilla CK2 kept/modified, or deleted) - the modified-events "
                "lane owns it (docs/evidence/HANDOFF_events.md)"
            )
        if target not in live_ids:
            return None, f"target {target} is emitted as an inert stub, not live"
        body = Block(entries=[Node(key="id", op="=", value=ck3_id_of[target])])
        if delay is not None:
            body.append(delay)
        return Node(key="trigger_event", op="=", value=body), ""

    hook.calls = calls  # type: ignore[attr-defined]
    return hook


class EventHooks:
    """The ``hooks`` mapping `convert_block` consults, with one pattern rule.

    `convert_block` only ever calls ``.get(lower_key)``, so a plain dict is
    enough for the fixed event-firing keys; ``event_target:<name>`` is a
    *family* of keys (one per CK2 saved target), which is why this is a small
    class rather than a dict literal.
    """

    def __init__(self, fixed: dict[str, object], scope_hook) -> None:
        self._fixed = fixed
        self._scope_hook = scope_hook

    def get(self, key: str):
        hook = self._fixed.get(key)
        if hook is not None:
            return hook
        if EVENT_TARGET_RE.match(key):
            return self._scope_hook
        reason = REJECT_CK2_KEYS.get(key)
        if reason is not None:
            return lambda _entry, _kind, _reason=reason: (None, _reason)
        return None


# -- one event ---------------------------------------------------------------

@dataclass
class ConvertedEvent:
    ck2_id: str
    ck3_id: str
    namespace: str
    kind: str
    ck3_type: str
    theme: str
    score: float
    mapped: int
    total: int
    gates: list[str] = field(default_factory=list)
    calls: list[str] = field(default_factory=list)
    loc_keys: list[str] = field(default_factory=list)
    hidden: bool = False
    body: Block = field(default_factory=Block)
    source_file: str = ""

    @property
    def live(self) -> bool:
        return not self.gates


def _theme_for(ck2_block: Block, themes: dict[tuple[str, str], str], default: str) -> str:
    picture = border = None
    for entry in ck2_block.entries:
        if isinstance(entry, Node) and entry.key == "picture" and isinstance(entry.value, str):
            picture = entry.value
        elif isinstance(entry, Node) and entry.key == "border" and isinstance(entry.value, str):
            border = entry.value
    if picture and ("picture", picture) in themes:
        return themes[("picture", picture)]
    if border and ("border", border) in themes:
        return themes[("border", border)]
    return default


def _convert_desc(
    entries: list[Node], *, ck3_key: str, ctxargs: dict, loc_keys: list[str],
) -> Node | None:
    """CK2 ``desc``/``title`` (scalar or gated blocks) -> a CK3 dynamic desc.

    CK2's ``desc = { text = KEY trigger = { ... } }``, possibly repeated, is
    CK3's ``desc = { first_valid = { triggered_desc = { trigger = {...}
    desc = KEY } ... } }`` (`verified`, `game/events/_events.info` "Dynamic
    Description Appendix" §3, pattern `adultery.1006`).
    """
    plain = [e for e in entries if not isinstance(e.value, Block)]
    gated = [e for e in entries if isinstance(e.value, Block)]
    if not gated and len(plain) == 1:
        loc_keys.append(str(plain[0].value))
        return Node(key=ck3_key, op="=", value=str(plain[0].value))
    if not gated and not plain:
        return None
    choices = Block(multiline=True)
    for entry in gated:
        text = None
        trigger_block = None
        for sub in entry.value.entries:
            if not isinstance(sub, Node):
                continue
            if sub.key == "text" and not isinstance(sub.value, Block):
                text = str(sub.value)
            elif sub.key == "trigger" and isinstance(sub.value, Block):
                trigger_block = sub.value
        if text is None:
            return None
        loc_keys.append(text)
        inner = Block(multiline=True)
        if trigger_block is not None:
            inner.append(Node(
                key="trigger", op="=",
                value=convert_block(trigger_block, kind="trigger", **ctxargs),
            ))
        inner.append(Node(key="desc", op="=", value=text))
        choices.append(Node(key="triggered_desc", op="=", value=inner))
    for entry in plain:
        loc_keys.append(str(entry.value))
        choices.append(Node(key="desc", op="=", value=str(entry.value)))
    return Node(
        key=ck3_key, op="=",
        value=Block(entries=[Node(key="first_valid", op="=", value=choices)], multiline=True),
    )


def _convert_option(
    ck2_option: Block, *, ctxargs: dict, loc_keys: list[str], stats: ConvertStats,
) -> tuple[Node, list[str]]:
    """One CK2 ``option = { }`` -> one CK3 ``option = { }``."""
    notes: list[str] = []
    body = Block(multiline=True)
    names = [
        e for e in ck2_option.entries
        if isinstance(e, Node) and e.key == "name"
    ]
    effects = Block()
    for entry in ck2_option.entries:
        if not isinstance(entry, Node):
            effects.append(entry)
            continue
        key = entry.key.lower()
        if key == "name":
            continue
        if key == "trigger" and isinstance(entry.value, Block):
            body.append(Node(
                key="trigger", op="=",
                value=convert_block(entry.value, kind="trigger", **ctxargs),
            ))
            continue
        if key == "ai_chance":
            # CK2's ai_chance is a factor/modifier MTTH block; CK3's is
            # base/add. Not a valid CK3 weight, and the `decisions` lane
            # measured that shipping a raw-converted AI weight is what
            # silenced the scripted-test runner (docs/step_decisions.md §3b).
            # Dropping it is safe: with no ai_chance CK3 weights every valid
            # option equally.
            notes.extend(render_ck2_comment(entry))
            notes.append("# CK2-unmapped: ai_chance: CK2 factor/modifier weight is not a CK3 ai_chance (dropped, CK3 defaults to equal weights)")
            continue
        effects.append(entry)
    # name: CK3 accepts both CK2 shapes verbatim (`name = key` and
    # `name = { text = key trigger = { } }`, `game/events/_events.info`
    # "Option name specifics"), so each candidate is emitted in order.
    name_at = 0
    for entry in names:
        if isinstance(entry.value, Block):
            text = None
            trig = None
            for sub in entry.value.entries:
                if isinstance(sub, Node) and sub.key == "text" and not isinstance(sub.value, Block):
                    text = str(sub.value)
                elif isinstance(sub, Node) and sub.key == "trigger" and isinstance(sub.value, Block):
                    trig = sub.value
            if text is None:
                notes.extend(render_ck2_comment(entry))
                notes.append("# CK2-unmapped: option name: no plain `text = <loc key>` to carry over")
                stats.total += 1
                continue
            loc_keys.append(text)
            inner = Block(multiline=True, entries=[Node(key="text", op="=", value=text)])
            if trig is not None:
                inner.append(Node(
                    key="trigger", op="=",
                    value=convert_block(trig, kind="trigger", **ctxargs),
                ))
            body.entries.insert(name_at, Node(key="name", op="=", value=inner))
            name_at += 1
        else:
            loc_keys.append(str(entry.value))
            body.entries.insert(name_at, Node(key="name", op="=", value=str(entry.value)))
            name_at += 1
    converted_effects = convert_block(effects, kind="effect", **ctxargs)
    body.entries.extend(converted_effects.entries)
    body.end_comments = [*body.end_comments, *converted_effects.end_comments, *notes]
    return Node(key="option", op="=", value=body, blank_before=True), notes


def convert_event(
    ck2_id: str,
    ck2_block: Block,
    *,
    kind: str,
    prefix: str,
    triggers: dict[str, VocabRow],
    effects: dict[str, VocabRow],
    traits: TraitInfo,
    themes: dict[tuple[str, str], str],
    default_theme: str,
    ck3_id_of: dict[str, str],
    live_ids: set[str],
    scoped_out: dict[str, str],
    min_score: float,
    source_file: str = "",
) -> ConvertedEvent:
    """Convert one CK2 event; the caller decides live vs stub from `.gates`."""
    stats = ConvertStats()
    loc_keys: list[str] = []
    hook = make_event_hook(ck3_id_of=ck3_id_of, live_ids=live_ids, scoped_out=scoped_out)
    ctxargs: dict = {
        "triggers": triggers, "effects": effects, "traits": traits,
        "stats": stats,
    }

    def scope_hook(entry: Node, kind_: str) -> tuple[Node | None, str]:
        """``event_target:x = { ... }`` -> ``scope:x = { ... }``."""
        match = EVENT_TARGET_RE.match(entry.key.lower())
        if match is None or not isinstance(entry.value, Block):
            return None, "event_target reference with no block body"
        return Node(
            key=f"scope:{match.group(1)}", op=entry.op,
            value=convert_block(entry.value, kind=kind_, **ctxargs),
            trailing_comment=entry.trailing_comment,
        ), ""

    ctxargs["hooks"] = EventHooks({k: hook for k in EVENT_FIRING_KEYS}, scope_hook)

    body = Block(multiline=True)
    trailing: list[str] = []
    header_triggers = Block(multiline=True)
    trigger_block: Block | None = None
    options: list[Node] = []
    descs: list[Node] = []
    titles: list[Node] = []
    hidden = False
    has_mtth = False
    major = None
    major_trigger = None
    immediate = after = fail_effect = None

    for entry in ck2_block.entries:
        if not isinstance(entry, Node):
            continue
        key = entry.key.lower()
        if key == "id":
            continue
        if key == "hide_window":
            hidden = bool(entry.value) if isinstance(entry.value, bool) else str(entry.value).lower() == "yes"
            continue
        if key == "is_triggered_only":
            # CK3 events never fire on their own: `is_triggered_only` is the
            # CK3 default and has no field (`game/events/_events.info`).
            continue
        if key in ("picture", "border"):
            continue  # folded into `theme` below
        if key == "mean_time_to_happen":
            has_mtth = True
            trailing.extend(render_ck2_comment(entry))
            trailing.append(
                "# CK2 mean_time_to_happen: CK3 has no MTTH on events. Firing this "
                "event needs an on_action pulse with trigger_event = { days = ... } "
                "(out of this lane's scope, docs/evidence/HANDOFF_events.md)"
            )
            continue
        if key == "desc":
            descs.append(entry)
            continue
        if key == "title":
            titles.append(entry)
            continue
        if key == "trigger" and isinstance(entry.value, Block):
            trigger_block = convert_block(entry.value, kind="trigger", **ctxargs)
            continue
        if key == "major_trigger" and isinstance(entry.value, Block):
            major_trigger = convert_block(entry.value, kind="trigger", **ctxargs)
            continue
        if key == "major":
            major = entry.value
            continue
        if key == "immediate" and isinstance(entry.value, Block):
            immediate = convert_block(entry.value, kind="effect", **ctxargs)
            continue
        if key == "after" and isinstance(entry.value, Block):
            after = convert_block(entry.value, kind="effect", **ctxargs)
            continue
        if key == "fail_trigger_effect" and isinstance(entry.value, Block):
            # CK3 `on_trigger_fail` is the same idea (`_events.info`).
            fail_effect = convert_block(entry.value, kind="effect", **ctxargs)
            continue
        if key == "option" and isinstance(entry.value, Block):
            node, _ = _convert_option(entry.value, ctxargs=ctxargs, loc_keys=loc_keys, stats=stats)
            options.append(node)
            continue
        if key in EVENT_HEADER_TRIGGERS:
            ck3_key, op, transform = EVENT_HEADER_TRIGGERS[key]
            value = entry.value
            if transform == "invert":
                if not isinstance(value, bool):
                    stats.total += 1
                    trailing.extend(render_ck2_comment(entry))
                    trailing.append(f"# CK2-unmapped: {key}: expected yes/no")
                    continue
                value = not value
            stats.total += 1
            stats.mapped += 1
            header_triggers.append(Node(key=ck3_key, op=op, value=value))
            continue
        if key in COMMENT_ONLY_KEYS:
            trailing.extend(render_ck2_comment(entry))
            trailing.append(
                f"# CK2-unmapped: {key}: CK2 event presentation/AI field with no CK3 event field"
            )
            continue
        # Anything else at the top level of a CK2 event is an implicit
        # root-scope trigger condition (`religion_group = X`, `has_dlc = X`,
        # `only_playable = yes`, ...). Fold it into `trigger = { }` through
        # the trigger table, scored like any other trigger key.
        folded = convert_block(
            Block(entries=[Node(key=entry.key, op=entry.op, value=entry.value)]),
            kind="trigger", **ctxargs,
        )
        header_triggers.entries.extend(folded.entries)
        header_triggers.end_comments = [*header_triggers.end_comments, *folded.end_comments]

    theme = _theme_for(ck2_block, themes, default_theme)
    ck3_type = EMIT_KINDS[kind]
    ck3_id = ck3_id_of.get(ck2_id) or event_id(prefix, ck2_id)

    # -- assemble the converted (draft) body ---------------------------------
    body.append(Node(key="type", op="=", value=ck3_type))
    if ck3_type == "letter_event":
        # `sender` is a REQUIRED field of a CK3 letter event, hidden or not
        # (`error(field-missing): required field sender missing` on 41 hidden
        # ones in the first build). CK2 binds the sender to FROM, which does
        # not exist in CK3, so the honest stand-in is root - and any event
        # that really used FROM is gated out anyway.
        body.append(Node(key="sender", op="=", value="root"))
    if hidden:
        body.append(Node(key="hidden", op="=", value=True))
    else:
        body.append(Node(key="theme", op="=", value=theme))
        title_node = _convert_desc(titles, ck3_key="title", ctxargs=ctxargs, loc_keys=loc_keys)
        if title_node is not None:
            body.append(title_node)
        desc_node = _convert_desc(descs, ck3_key="desc", ctxargs=ctxargs, loc_keys=loc_keys)
        if desc_node is not None:
            body.append(desc_node)
        # `left_portrait = root` is the CK3 shape for "the character this
        # event is about" (`verified`, e.g. game/events/witch_events.txt:70
        # `left_portrait = scope:child`); root is the event's own scope.
        body.append(Node(key="left_portrait", op="=", value="root"))
    if major is not None:
        body.append(Node(key="major", op="=", value=major))
    if major_trigger is not None:
        body.append(Node(key="major_trigger", op="=", value=major_trigger))

    full_trigger = Block(multiline=True)
    if trigger_block is not None:
        full_trigger.entries.extend(trigger_block.entries)
        full_trigger.end_comments = [*full_trigger.end_comments, *trigger_block.end_comments]
    full_trigger.entries.extend(header_triggers.entries)
    full_trigger.end_comments = [*full_trigger.end_comments, *header_triggers.end_comments]
    if full_trigger.entries or full_trigger.end_comments:
        body.append(Node(key="trigger", op="=", value=full_trigger, blank_before=True))
    if fail_effect is not None:
        body.append(Node(key="on_trigger_fail", op="=", value=fail_effect, blank_before=True))
    if immediate is not None:
        body.append(Node(key="immediate", op="=", value=immediate, blank_before=True))
    for node in options:
        body.append(node)
    if after is not None:
        body.append(Node(key="after", op="=", value=after, blank_before=True))
    if trailing:
        body.end_comments = [*body.end_comments, *trailing]

    from_uses = rewrite_scope_values(body)

    # -- gates ---------------------------------------------------------------
    gates: list[str] = []
    score = stats.score
    if score < min_score:
        gates.append("score")
    if has_mtth:
        gates.append("mtth")
    if from_uses:
        gates.append("from_scope")
    if not hidden and not options:
        gates.append("no_option")
    if any(
        c not in live_ids or c in scoped_out or c not in ck3_id_of
        for c in hook.calls  # type: ignore[attr-defined]
    ):
        gates.append("dead_call")
    if _has_var_ref(body):
        gates.append("ck2_variable")
    saved, used = scope_usage(body)
    if used - saved:
        gates.append("unsaved_scope")

    return ConvertedEvent(
        ck2_id=ck2_id, ck3_id=ck3_id, namespace=event_namespace(prefix, ck2_id),
        kind=kind, ck3_type=ck3_type, theme=theme, score=score,
        mapped=stats.mapped, total=stats.total, gates=gates,
        calls=list(hook.calls),  # type: ignore[attr-defined]
        loc_keys=loc_keys, hidden=hidden, body=body, source_file=source_file,
    )


def render_event(converted: ConvertedEvent) -> Node:
    """The Node actually written: the live body, or an inert stub + draft."""
    header = [
        f"# CK2: {converted.ck2_id} ({converted.kind} -> {converted.ck3_type}) "
        f"from {converted.source_file}",
        (
            f"# convertibility: {converted.score:.2f} "
            f"({converted.mapped}/{converted.total} keys mapped)"
            if converted.total else "# convertibility: 1.00 (no trigger/effect keys)"
        ),
    ]
    if converted.live:
        body = converted.body
        body.entries and setattr(
            body.entries[0], "leading_comments",
            [*header, *body.entries[0].leading_comments],
        )
        return Node(key=converted.ck3_id, op="=", value=body, blank_before=True)

    header.append(
        f"# fae_unported = yes: {'; '.join(GATE_REASONS[g] for g in converted.gates)}"
    )
    header.append("# The converted draft follows; nothing below `# draft:` is live.")
    draft = pdx.write(Block(entries=[Node(key=converted.ck3_id, value=converted.body)]))
    header.extend(
        f"# draft: {line}" if line else "# draft:" for line in draft.splitlines()
    )
    stub = Block(multiline=True)
    # Always `character_event`, whatever the CK2 kind was: a CK3 letter event
    # requires a `sender` and a court/activity event a host, and a stub has
    # no scopes to point them at. The intended type is in the header comment
    # and in the draft below it.
    stub.append(Node(
        key="type", op="=", value="character_event", leading_comments=header,
    ))
    # An inert CK3 event: never shown, never true, no effect. This is the
    # shape the `decisions` lane's soak probes proved harmless
    # (docs/step_decisions.md §3b); `hidden = yes` also means no `option` is
    # required (vanilla `game/events/misc_events.txt:3` is exactly this
    # shape), and `orphan = yes` stops CK3 logging it as unreferenced
    # (`game/events/_events.info:242`, used by vanilla in 8 files).
    stub.append(Node(key="hidden", op="=", value=True))
    stub.append(Node(key="orphan", op="=", value=True))
    stub.append(Node(
        key="trigger", op="=",
        value=Block(entries=[Node(key="always", op="=", value=False)]),
    ))
    stub.append(Node(key="immediate", op="=", value=Block()))
    return Node(key=converted.ck3_id, op="=", value=stub, blank_before=True)


def find_event_block(doc_block: Block, kind: str, event_id_value: str) -> Block | None:
    for entry in doc_block.entries:
        if not isinstance(entry, Node) or entry.key != kind or not isinstance(entry.value, Block):
            continue
        for sub in entry.value.entries:
            if isinstance(sub, Node) and sub.key == "id" and str(sub.value) == event_id_value:
                return entry.value
    return None


def run(ctx: Context) -> StepResult:
    config = EventsConfig.from_raw(ctx.config.raw.get("events", {}))
    if not config.enabled:
        return StepResult(
            summary="skipped: [events] enabled = false (docs/step_events.md §4)",
            counts={"live": 0, "stub": 0, "files": 0},
        )

    prefix = ctx.config.prefix
    triggers = read_vocab_csv(config.triggers)
    effects = read_vocab_csv(config.effects)
    themes = read_themes(config.themes_csv)
    if not themes:
        ctx.warn(
            f"events: no theme rows read from {config.themes_csv}; every event "
            f"falls back to theme {config.default_theme!r} "
            "(regenerate with scripts/build_event_themes_csv.py)"
        )
    traits = TraitInfo.from_ctx(ctx)
    if not traits.live and not traits.renames:
        ctx.warn(
            "events: no trait data from step `traits` in this pass; bare "
            "`<trait> = yes/no` shorthand will show as unmapped comments "
            "(run `traits` in the same pass)"
        )
    loc_keys_available: set[str] = set(ctx.data.get("loc", {}).get("keys", ()))

    rows = read_provenance(config.provenance)
    scoped_out: dict[str, str] = {}
    emit_rows: list[ProvenanceRow] = []
    counts = {"live": 0, "stub": 0, "skipped_scope": 0, "skipped_status": 0, "not_found": 0}
    for row in rows:
        if row.status not in EMIT_STATUSES:
            counts["skipped_status"] += 1
            continue
        if row.kind not in EMIT_KINDS:
            scoped_out[row.id] = OUT_OF_SCOPE_REASONS.get(row.kind, f"kind {row.kind!r} out of scope")
            counts["skipped_scope"] += 1
            continue
        emit_rows.append(row)

    # -- parse the CK2 side once --------------------------------------------
    parsed: dict[Path, Block] = {}
    sources: list[tuple[ProvenanceRow, Block]] = []
    for row in emit_rows:
        path = ctx.ck2(row.faerun_file)
        if path not in parsed:
            try:
                parsed[path] = ctx.parse_path(path, lenient=True)
            except OSError:
                parsed[path] = Block()
        block = find_event_block(parsed[path], row.kind, row.id)
        if block is None:
            ctx.warn(f"events: {row.id} ({row.faerun_file}) not found, skipped")
            counts["not_found"] += 1
            continue
        sources.append((row, block))

    # Not `event_id` per row: a CK2 number above ids.MAX_EVENT_NUMBER has to
    # be re-allocated inside its namespace, which only the whole set can do.
    ck3_id_of = build_event_id_map(prefix, (row.id for row, _ in sources))

    # -- fixpoint: a call to a stubbed event is itself unmapped, which can
    # -- demote the caller. The live set only ever shrinks, so this converges.
    live_ids: set[str] = set(ck3_id_of)
    converted: dict[str, ConvertedEvent] = {}
    passes = 0
    for passes in range(1, 11):
        converted = {}
        for row, block in sources:
            converted[row.id] = convert_event(
                row.id, block, kind=row.kind, prefix=prefix,
                triggers=triggers, effects=effects, traits=traits,
                themes=themes, default_theme=config.default_theme,
                ck3_id_of=ck3_id_of, live_ids=live_ids, scoped_out=scoped_out,
                min_score=config.min_score, source_file=row.faerun_file,
            )
        new_live = {i for i, c in converted.items() if c.live}
        if new_live == live_ids:
            break
        live_ids = new_live

    # -- write ---------------------------------------------------------------
    by_file: dict[str, list[ConvertedEvent]] = {}
    for row, _ in sources:
        by_file.setdefault(row.faerun_file, []).append(converted[row.id])

    written: list[Path] = []
    namespaces: set[str] = set()
    for source_rel, group in sorted(by_file.items()):
        top = Block(multiline=True)
        file_namespaces = sorted({c.namespace for c in group})
        namespaces.update(file_namespaces)
        for ns in file_namespaces:
            top.append(Node(key="namespace", op="=", value=ns))
        for conv in sorted(group, key=lambda c: (c.namespace, _num(c.ck3_id))):
            top.append(render_event(conv))
            counts["live" if conv.live else "stub"] += 1
        stem = _file_stem(source_rel)
        written.append(ctx.write_script(
            f"events/{prefix}_{stem}.txt", top,
            source=f"{ctx.ck2_mod.name}/{source_rel}",
        ))

    # -- evidence ------------------------------------------------------------
    unmapped: Counter = Counter()
    loc_misses: set[str] = set()
    for conv in converted.values():
        for line in _all_comments(conv.body):
            if line.startswith("# CK2-unmapped: "):
                unmapped[line[len("# CK2-unmapped: "):].split(":")[0].strip()] += 1
        if loc_keys_available:
            loc_misses.update(k for k in conv.loc_keys if k not in loc_keys_available)

    config.evidence.parent.mkdir(parents=True, exist_ok=True)
    with open(config.evidence, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow([
            "ck2_id", "ck3_id", "namespace", "kind", "ck3_type", "theme",
            "emitted", "live", "score", "mapped", "total", "gates",
            "calls", "loc_keys", "source_file",
        ])
        for row in rows:
            if row.status not in EMIT_STATUSES:
                continue
            conv = converted.get(row.id)
            if conv is None:
                writer.writerow([
                    row.id, "", "", row.kind, "", "", "no", "no", "", "", "",
                    scoped_out.get(row.id, "not found in source file at run time"),
                    "", "", row.faerun_file,
                ])
                continue
            writer.writerow([
                conv.ck2_id, conv.ck3_id, conv.namespace, conv.kind, conv.ck3_type,
                conv.theme, "yes", "yes" if conv.live else "no", f"{conv.score:.3f}",
                conv.mapped, conv.total, ";".join(conv.gates), ";".join(conv.calls),
                ";".join(conv.loc_keys), conv.source_file,
            ])

    unmapped_path = config.evidence.with_name("events_unmapped_keys.csv")
    with open(unmapped_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["ck2_key", "unmapped_uses"])
        for key, n in unmapped.most_common():
            writer.writerow([key, n])

    counts |= {
        "files": len(written),
        "namespaces": len(namespaces),
        "fixpoint_passes": passes,
        "unmapped_keys": len(unmapped),
        "loc_key_misses": len(loc_misses),
    }
    top_unmapped = ", ".join(f"{k}({n})" for k, n in unmapped.most_common(5))
    return StepResult(
        summary=(
            f"{counts['live']} events live, {counts['stub']} inert stubs, "
            f"{counts['skipped_scope']} skipped by scope, {len(written)} files, "
            f"{len(namespaces)} namespaces; top unmapped: {top_unmapped or 'none'}"
        ),
        counts=counts,
    )


def _has_var_ref(block: Block) -> bool:
    """A CK2 ``@`` reader variable or ``@``-concatenated id survived.

    Two shapes, both fatal to CK3's *reader* (not just its script engine, so
    the rest of the file goes with them): a bare ``@name`` token, and CK2's
    habit of building a flag name by concatenation -
    ``remove_character_flag = nomadrule_duel@FROM`` drew
    ``error(structure): found loose value @FROM`` **and**
    ``error(reader-directives): reader variable FROM not defined``
    (`verified` 2026-09-10, `docs/evidence/tiger_events_2026-09-10_summary.txt`).
    """
    for entry in block.entries:
        if isinstance(entry, Node) and "@" in entry.key:
            return True
        value = getattr(entry, "value", None)
        if isinstance(value, VarRef):
            return True
        if isinstance(value, str) and "@" in value:
            return True
        if isinstance(value, Block) and _has_var_ref(value):
            return True
    return False


def _file_stem(source_rel: str) -> str:
    """Output filename stem for a CK2 event file.

    Faerûn ships `events/faerun_adoption_events .txt` - a trailing space in
    the filename, which would reach the generated mod verbatim. Whitespace is
    folded to `_` and the stem lower-cased so two CK2 files differing only in
    case cannot collide on a case-insensitive filesystem.
    """
    stem = Path(source_rel).stem.strip().lower()
    return re.sub(r"[^a-z0-9_.-]+", "_", stem)


def _num(ck3_id: str) -> int:
    tail = ck3_id.rsplit(".", 1)[-1]
    return int(tail) if tail.isdigit() else 0


def _all_comments(block: Block) -> list[str]:
    out: list[str] = list(block.end_comments)
    for entry in block.entries:
        out.extend(entry.leading_comments)
        if entry.trailing_comment:
            out.append(entry.trailing_comment)
        value = getattr(entry, "value", None)
        if isinstance(value, Block):
            out.extend(_all_comments(value))
    return out
