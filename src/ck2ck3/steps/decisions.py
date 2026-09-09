"""Step ``decisions``: port CK2 character-scope decisions to CK3 1.19 syntax.

README §5 step 3, restricted to decisions (the small, self-contained first
slice; events/on_actions are a later lane). Rules, vocabulary-table method
and open questions: ``docs/step_decisions.md``.

Runs after ``loc`` (decision title/desc text is already ``<id>``/``<id>_desc``
in the CK2 loc CSVs, ported verbatim by that step - `docs/step_decisions.md`
§3) and ``traits`` (bare ``<trait> = yes/no`` shorthand needs the live
trait-id/rename map, ``ctx.data["traits"]``).

Only three of the eight CK2 decision groups have a character-scope root
(no ``filter=``/third-party target) and so a CK3 landing place at all:
``decisions``, ``society_decisions``, ``plot_decisions``. The rest
(``title_decisions``, ``settlement_decisions``, ``offmap_decisions``,
``targeted_decisions``/``targetted_decisions``, ``trade_post_decisions``) are
evidence-only rows (`docs/evidence/decisions_convertibility.csv`), never
written to the mod: CK3 decisions are always character-scope, and there is
no counterpart for a title/settlement/offmap-targeted CK2 decision or a
third-party one (those map to CK3 character interactions, out of this
lane's scope, `docs/step_decisions.md` §1).
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

from .. import pdx
from ..config import REPO_ROOT
from ..context import Context, StepResult
from ..decisions_vocab import SCOPE_WORDS, TITLE_TAG_RE, VocabRow, read_vocab_csv
from ..pdx import Block, Node, Item

DESCRIPTION = "port Faerûn's character-scope CK2 decisions to CK3 1.19 syntax"
OUTPUTS: tuple[str, ...] = ("common/decisions",)

#: The only CK2 decision groups whose root scope is the character taking the
#: decision (`docs/step_decisions.md` §1, `verified` against
#: `decisions/plot_decisions.txt`/`faerun_societies_decisions.txt` - no
#: `filter=`/third-party field - vs. `title_decisions.txt`/
#: `settlement_decisions.txt`, which do).
EMIT_KINDS = frozenset({"decisions", "society_decisions", "plot_decisions"})
OUT_OF_SCOPE_REASONS: dict[str, str] = {
    "title_decisions": "title-scope (filter=/ai_target_filter=), CK3 has no title-scope decisions",
    "settlement_decisions": "settlement-scope (filter=/ai_target_filter=), CK3 has no settlement-scope decisions",
    "offmap_decisions": "offmap-power-scope; offmap powers do not exist in CK3 (docs/mechanics_inventory.md)",
    "targeted_decisions": "third-party character-targeted; maps to CK3 character interactions, out of this lane's scope",
    "targetted_decisions": "third-party character-targeted; maps to CK3 character interactions, out of this lane's scope",
    "trade_post_decisions": "trade-post-scope; trade routes/posts do not exist in CK3 1.19 (docs/mechanics_inventory.md)",
}
EMIT_STATUSES = frozenset({"new", "modified"})

#: Keys that pass through unchanged: jomini logic/structure, never vocabulary.
STRUCTURAL_KEYS = frozenset(
    {
        "and", "or", "not", "nor", "nand",
        "if", "else", "else_if",
        "trigger_if", "trigger_else", "trigger_else_if", "trigger_switch",
        "limit", "trigger", "modifier", "factor", "value", "weight",
        "ai_chance", "first_valid", "random_valid", "triggered_desc",
        "desc", "text",
    }
)
#: CK2 top-level decision keys with a direct 1:1 CK3 field of the same
#: shape (scalar/simple), copied verbatim.
PASSTHROUGH_SCALARS = ("ai_check_interval",)
#: CK2 sections that hold trigger-shaped content (`docs/step_decisions.md`
#: §2; `ai_will_do`'s body is a jomini modifier/MTTH block, trigger-shaped,
#: not effect keys - matches `scripts/decisions_vocab_survey.py`).
TRIGGER_SECTIONS = ("potential", "allow", "from_potential", "ai_will_do", "ai_potential")
#: CK3 keys whose scalar argument is itself a trait id, needing the traits
#: step's id map (`has_trait`/`add_trait` also reachable via the explicit
#: CK2 `trait = X` form, not just the bare `<trait> = yes/no` shorthand).
TRAIT_VALUE_KEYS = frozenset({"has_trait", "add_trait", "remove_trait"})
EFFECT_SECTIONS = ("effect",)


@dataclass
class DecisionsConfig:
    provenance: Path = REPO_ROOT / "docs" / "evidence" / "decisions_provenance.csv"
    min_score: float = 1.0
    #: On by default again (2026-09-09 evening) since below-threshold
    #: decisions are inert stubs and the AI weight is always 0
    #: (docs/step_decisions.md §3b). `[decisions] enabled = false` skips the step.
    enabled: bool = True
    evidence: Path = REPO_ROOT / "docs" / "evidence" / "decisions_convertibility.csv"
    triggers: Path = REPO_ROOT / "mappings" / "triggers.csv"
    effects: Path = REPO_ROOT / "mappings" / "effects.csv"

    @classmethod
    def from_raw(cls, raw: dict) -> "DecisionsConfig":
        def _resolve(value: str | None, default: Path) -> Path:
            path = Path(value).expanduser() if value else default
            return path if path.is_absolute() else REPO_ROOT / path

        return cls(
            provenance=_resolve(raw.get("provenance"), cls.provenance),
            min_score=float(raw.get("min_score", 1.0)),
            enabled=bool(raw.get("enabled", True)),
            evidence=_resolve(raw.get("evidence"), cls.evidence),
            triggers=_resolve(raw.get("triggers"), cls.triggers),
            effects=_resolve(raw.get("effects"), cls.effects),
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
                    id=row["id"],
                    kind=row["kind"],
                    status=row["status"],
                    faerun_file=row["faerun_file"],
                )
            )
    return rows


@dataclass
class TraitInfo:
    """The bare-`<trait> = yes/no` shorthand resolution table."""

    live: set[str] = field(default_factory=set)
    renames: dict[str, str] = field(default_factory=dict)
    drop_notes: dict[str, str] = field(default_factory=dict)
    sexuality: dict[str, str] = field(default_factory=dict)
    #: Commented out by the `traits` step (no CK3 trait exists for it, but
    #: it *is* a real CK2 trait, unlike a key merely absent from all four
    #: sets above). Without this, an id like `renowned_wizard` (a real
    #: Faerûn trait `traits` left unported) fell through every check and was
    #: passed through unchanged as if it were already a valid CK3 id -
    #: ck3-tiger `error(unknown-field): unknown token` (`verified` against
    #: docs/evidence/tiger_events_decisions_2026-09-09.txt before this fix).
    unported: set[str] = field(default_factory=set)

    @classmethod
    def from_ctx(cls, ctx: Context) -> "TraitInfo":
        data = ctx.data.get("traits")
        if not data:
            return cls()
        return cls(
            live=set(data.get("live", ())),
            renames=dict(data.get("renames", {})),
            drop_notes=dict(data.get("drop_notes", {})),
            sexuality=dict(data.get("sexuality", {})),
            unported=set(data.get("unported", ())),
        )

    def __contains__(self, key: str) -> bool:
        return (
            key in self.live or key in self.renames or key in self.drop_notes
            or key in self.sexuality or key in self.unported
        )

    def resolve(self, key: str) -> str | None:
        """The CK3 trait id, or ``None`` if it has no CK3 trait counterpart."""
        if key in self.renames:
            return self.renames[key]
        if key in self.live:
            return key
        return None


@dataclass
class ConvertStats:
    mapped: int = 0
    total: int = 0

    @property
    def score(self) -> float:
        return 1.0 if self.total == 0 else self.mapped / self.total


def _lookup(key: str, primary: dict[str, VocabRow], secondary: dict[str, VocabRow]) -> VocabRow | None:
    """The vocab row for ``key`` in its own table only.

    No cross-table fallback: CK3 genuinely separates trigger and effect
    keywords for shared concepts (`piety`/`wealth`/`gold` compare, only
    `add_piety`/`add_gold` change them; `has_trait` checks, only
    `add_trait`/`remove_trait` change) and a fallback that borrowed the
    other table's mapping produced real `error(wrong-use)`/
    `error(unknown-field)` ck3-tiger findings (`docs/step_decisions.md` §2
    limitation #1, `verified` against `docs/evidence/tiger_events_decisions_2026-09-09.txt`
    before this fix). ``secondary`` is kept as a parameter for callers that
    still want it (none currently do) and to keep the signature stable.
    """
    return primary.get(key)


def _render_comment(entry: Node | Item) -> list[str]:
    """The original CK2 entry, rendered as ``# CK2: ...`` comment lines."""
    text = pdx.write(Block(entries=[entry]))
    lines = [f"# CK2: {line}" if line else "# CK2:" for line in text.splitlines()]
    return lines


def _is_number(key: str) -> bool:
    try:
        float(key)
        return True
    except ValueError:
        return False


def _is_bool_scalar(value: object) -> bool | None:
    """``yes``/``no`` already parse as Python ``bool`` (`ck2ck3.pdx.tokens`)."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.lower() in ("yes", "no"):
        return value.lower() == "yes"
    return None


def convert_block(
    source: Block,
    *,
    kind: str,
    triggers: dict[str, VocabRow],
    effects: dict[str, VocabRow],
    traits: TraitInfo,
    stats: ConvertStats,
) -> Block:
    """Recursively port one CK2 trigger/effect block to CK3 syntax.

    ``kind`` is ``"trigger"`` or ``"effect"`` - it selects which vocabulary
    table is tried first (`_lookup` falls back to the other table, a
    deliberate simplification: a handful of keys are only reachable through
    the "wrong" table's context, e.g. a trigger nested in an effect's
    ``limit = {}``, see `docs/step_decisions.md` §2 limitation #1).
    """
    primary, secondary = (triggers, effects) if kind == "trigger" else (effects, triggers)
    out = Block(multiline=True)
    pending_comments: list[str] = []

    def flush_onto(entry: Node | Item) -> None:
        nonlocal pending_comments
        if pending_comments:
            entry.leading_comments = [*pending_comments, *entry.leading_comments]
            pending_comments = []

    for entry in source.entries:
        if isinstance(entry, Item):
            new_item = Item(
                value=entry.value,
                quoted=entry.quoted,
                leading_comments=list(entry.leading_comments),
                trailing_comment=entry.trailing_comment,
                blank_before=entry.blank_before,
            )
            flush_onto(new_item)
            out.append(new_item)
            continue

        key = entry.key
        lower = key.lower()
        upper = key.upper()

        # -- scope word (ROOT/FROM/PREV/THIS/...) --------------------------
        if upper in SCOPE_WORDS:
            new_key = SCOPE_WORDS[upper]
            new_value = entry.value
            if isinstance(entry.value, Block):
                new_value = convert_block(
                    entry.value, kind=kind, triggers=triggers, effects=effects,
                    traits=traits, stats=stats,
                )
            node = Node(
                key=new_key, op=entry.op, value=new_value,
                leading_comments=list(entry.leading_comments),
                trailing_comment=entry.trailing_comment,
                blank_before=entry.blank_before,
            )
            flush_onto(node)
            out.append(node)
            continue

        # -- bare title-tag scope key (c_x/d_x/k_x/e_x/b_x = { ... }) ------
        if TITLE_TAG_RE.match(key) and isinstance(entry.value, Block):
            new_value = convert_block(
                entry.value, kind=kind, triggers=triggers, effects=effects,
                traits=traits, stats=stats,
            )
            node = Node(
                key=f"title:{key}", op=entry.op, value=new_value,
                leading_comments=list(entry.leading_comments),
                trailing_comment=entry.trailing_comment,
                blank_before=entry.blank_before,
            )
            flush_onto(node)
            out.append(node)
            continue

        # -- structural / jomini logic, unchanged, recurse ------------------
        if lower in STRUCTURAL_KEYS or _is_number(key):
            # `limit`/`trigger` are always trigger-shaped, even nested inside
            # an `effect` block (`if = { limit = { ... } }` inside an
            # `effect` section is common) - the kind must switch, not
            # inherit, or an explicit `trait = X` / bare shorthand inside
            # picks the wrong table (`error(wrong-use)`, `verified` against
            # docs/evidence/tiger_events_decisions_2026-09-09.txt before this
            # fix: add_trait leaking into a trigger via effect->if->limit).
            child_kind = "trigger" if lower in ("limit", "trigger") else kind
            new_value = entry.value
            if isinstance(entry.value, Block):
                new_value = convert_block(
                    entry.value, kind=child_kind, triggers=triggers, effects=effects,
                    traits=traits, stats=stats,
                )
            node = Node(
                key=key, op=entry.op, value=new_value,
                leading_comments=list(entry.leading_comments),
                trailing_comment=entry.trailing_comment,
                blank_before=entry.blank_before,
            )
            flush_onto(node)
            out.append(node)
            continue

        # -- bare <trait> = yes/no shorthand --------------------------------
        if lower in traits:
            stats.total += 1
            polarity = _is_bool_scalar(entry.value)
            ck3_trait = traits.resolve(lower)
            if ck3_trait is not None and polarity is not None:
                stats.mapped += 1
                if kind == "trigger":
                    if polarity:
                        node = Node(key="has_trait", op="=", value=ck3_trait)
                    else:
                        node = Node(
                            key="NOT", op="=",
                            value=Block(entries=[Node(key="has_trait", op="=", value=ck3_trait)]),
                        )
                else:
                    node = Node(
                        key="add_trait" if polarity else "remove_trait",
                        op="=", value=ck3_trait,
                    )
                node.leading_comments = list(entry.leading_comments)
                node.blank_before = entry.blank_before
                flush_onto(node)
                out.append(node)
                continue
            if lower in traits.sexuality:
                reason = f"{key}: CK3 has no trait for this, it is a sexuality ({traits.sexuality[lower]})"
            elif lower in traits.drop_notes:
                reason = f"{key}: {traits.drop_notes[lower]}"
            else:
                reason = f"{key}: trait has no CK3 counterpart"
            pending_comments.extend(_render_comment(entry))
            pending_comments.append(f"# CK2-unmapped: {reason}")
            continue

        # -- vocabulary table -----------------------------------------------
        if lower not in STRUCTURAL_KEYS:
            stats.total += 1
        row = _lookup(lower, primary, secondary)
        if row and row.ck3_key:
            # `trait = X` / `add_trait = X` / `remove_trait = X`: X is a CK2
            # trait id that itself needs the traits step's id map (dedupe
            # rename, or "no CK3 counterpart") - the key mapping succeeding
            # does not mean the argument does.
            if row.ck3_key in TRAIT_VALUE_KEYS and isinstance(entry.value, str):
                arg = entry.value.lower()
                if arg in traits:
                    resolved = traits.resolve(arg)
                    if resolved is None:
                        reason = (
                            traits.sexuality.get(arg)
                            and f"trait argument {entry.value!r}: CK3 has no trait for this, it is a sexuality ({traits.sexuality[arg]})"
                            or f"trait argument {entry.value!r}: {traits.drop_notes.get(arg, 'no CK3 counterpart')}"
                        )
                        pending_comments.extend(_render_comment(entry))
                        pending_comments.append(f"# CK2-unmapped: {key}: {reason}")
                        continue
                    value = resolved
                else:
                    value = entry.value
            else:
                value = entry.value
                if isinstance(entry.value, Block):
                    value = convert_block(
                        entry.value, kind=kind, triggers=triggers, effects=effects,
                        traits=traits, stats=stats,
                    )
            stats.mapped += 1
            node = Node(
                key=row.ck3_key, op=entry.op, value=value,
                leading_comments=list(entry.leading_comments),
                trailing_comment=entry.trailing_comment,
                blank_before=entry.blank_before,
            )
            flush_onto(node)
            out.append(node)
            continue

        pending_comments.extend(_render_comment(entry))
        if row:
            pending_comments.append(f"# CK2-unmapped: {key}: {row.note}")
        else:
            pending_comments.append(f"# CK2-unmapped: {key}: not in mappings/triggers.csv or effects.csv")

    if pending_comments:
        out.end_comments = [*out.end_comments, *pending_comments]
    return out


@dataclass
class ConvertedDecision:
    id: str
    kind: str
    status: str
    score: float
    mapped: int
    total: int
    block: Block


def convert_decision(
    ck2_id: str,
    ck2_block: Block,
    *,
    status: str,
    kind: str,
    triggers: dict[str, VocabRow],
    effects: dict[str, VocabRow],
    traits: TraitInfo,
    min_score: float,
) -> ConvertedDecision:
    stats = ConvertStats()
    body = Block(multiline=True)

    ck3_field_of = {
        "potential": ("is_shown", "trigger"),
        "allow": ("is_valid", "trigger"),
        "from_potential": ("ai_potential", "trigger"),
        "ai_will_do": ("ai_will_do", "trigger"),
        "ai_potential": ("ai_potential", "trigger"),
        "effect": ("effect", "effect"),
    }
    fields: dict[str, Node] = {}
    trailing: list[str] = []
    ck2_ai_will_do: Block | None = None
    for entry in ck2_block.entries:
        if not isinstance(entry, Node):
            continue
        key = entry.key
        if key == "ai_will_do" and isinstance(entry.value, Block):
            ck2_ai_will_do = entry.value
        if key in ck3_field_of and isinstance(entry.value, Block):
            ck3_key, table_kind = ck3_field_of[key]
            converted = convert_block(
                entry.value, kind=table_kind, triggers=triggers, effects=effects,
                traits=traits, stats=stats,
            )
            fields[ck3_key] = Node(key=ck3_key, value=converted, blank_before=True)
        elif key in PASSTHROUGH_SCALARS:
            fields[key] = Node(key=key, value=entry.value, blank_before=True)
        elif key in ("only_playable", "is_high_prio", "ai", "revoke_allowed"):
            # CK2 fields with no direct CK3 counterpart tracked separately -
            # kept as an evidence comment, not scored (not trigger/effect
            # vocabulary), see docs/step_decisions.md §2 limitation #2.
            trailing.extend(_render_comment(entry))
            trailing.append(f"# CK2-unmapped: {key}: no direct CK3 decision field (docs/step_decisions.md)")
        # `desc`/`title`/other loc overrides never occur in Faerûn's decisions
        # (docs/step_decisions.md §3) - nothing else to carry over.

    if "ai_check_interval" not in fields:
        fields["ai_check_interval"] = Node(
            key="ai_check_interval", value=24, blank_before=True,
            leading_comments=["# CK2 decision had no ai_check_interval; CK3 requires one, defaulted to 24 months"],
        )

    # Every vanilla 1.19 decision carries a picture block (302/302, `verified`);
    # without one the game logs "Decision picture ... missing entries" at
    # database init and the ported set crashed the load (2026-09-09 bisection,
    # claudespace/docs/evidence/bisect_probe_faerun_decisions_test_2026-09-09_135700.log).
    if "picture" not in fields:
        fields["picture"] = Node(
            key="picture",
            value=Block(entries=[Node(
                key="reference", op="=",
                value="gfx/interface/illustrations/decisions/decision_misc.dds",
                quoted_value=True,
            )]),
            leading_comments=["# CK2 GFX_evt_* picture has no CK3 counterpart; vanilla's generic decision illustration"],
        )
    # AI off for every ported decision (2026-09-09). CK2 `ai_will_do` is a
    # factor/modifier MTTH block, CK3's is base/add: the converted block is
    # not a valid weight, and with it in place the scripted-test runner never
    # fired (single-file probe: as-is silent; ai_will_do = { base = 0 } fired;
    # claudespace/docs/evidence/bisect_probe_faerun_dec2_2026-09-09_154020.log
    # and the v0..v4 variant soaks). The CK2 block stays as a comment for the
    # human who re-enables AI use per decision in the submod.
    ai_comment = []
    if "ai_will_do" in fields:
        ai_comment = _render_comment(Node(key="ai_will_do", value=ck2_ai_will_do)) if ck2_ai_will_do is not None else []
    fields["ai_will_do"] = Node(
        key="ai_will_do", value=Block(entries=[Node(key="base", op="=", value=0)]), blank_before=True,
        leading_comments=["# AI never takes a raw-ported decision (docs/step_decisions.md §3b); CK2 weights below:", *ai_comment],
    )
    order = ["picture", "is_shown", "is_valid", "cost", "effect", "ai_potential", "ai_will_do", "ai_check_interval"]
    for name in order:
        if name in fields:
            body.append(fields[name])
    # selection_tooltip/confirm_text: Faerûn ships no <id>_tooltip/<id>_confirm
    # loc keys (docs/step_decisions.md §3), so both default to <id>_desc
    # rather than showing CK3's raw-key fallback.
    body.append(Node(
        key="selection_tooltip", value=f"{ck2_id}_desc", blank_before=True,
    ))
    body.append(Node(key="confirm_text", value=f"{ck2_id}_desc"))
    if trailing:
        body.end_comments = [*body.end_comments, *trailing]

    score = stats.score
    below = score < min_score
    if below:
        # Below the threshold the decision becomes an INERT STUB: is_shown off,
        # is_valid trivially true, empty effect. The converted draft of each
        # section is kept as `# draft:` comment lines above the stub. Reason
        # (2026-09-09): with the converted bodies in place the scripted-test
        # runner never fired and the game crashed at database init in ~1 of 3
        # launches; with every body stubbed (structure only) the runner fires
        # (claudespace soak probes `allstub`, `v0..v4`). Only a decision whose
        # every trigger/effect key mapped is emitted live.
        stub_values = {
            "is_shown": Block(entries=[Node(key="always", value=False)]),
            "is_valid": Block(entries=[Node(key="always", value=True)]),
            "effect": Block(entries=[]),
            "ai_potential": Block(entries=[Node(key="always", value=False)]),
        }

        def _draft(n: Node) -> list[str]:
            lines = _render_comment(Node(key=n.key, value=n.value))
            return [("# draft: " + l[7:]) if l.startswith("# CK2: ") else "# draft:" for l in lines]

        new_entries: list = []
        seen: set[str] = set()
        carried: list[str] = []   # draft of a dropped `cost`, attached to the next stub
        for n in body.entries:
            if isinstance(n, Node) and n.key == "cost":
                carried.extend(["# cost dropped: a stub cannot be taken", *_draft(n)])
                continue
            if isinstance(n, Node) and n.key in stub_values:
                seen.add(n.key)
                new_entries.append(Node(
                    key=n.key, value=stub_values[n.key], blank_before=n.blank_before,
                    leading_comments=[*n.leading_comments, *carried, *_draft(n)],
                ))
                carried = []
            else:
                new_entries.append(n)
        if carried:
            body.end_comments = [*body.end_comments, *carried]
        if "is_shown" not in seen:
            new_entries.insert(0, Node(key="is_shown", value=Block(entries=[Node(key="always", value=False)])))
        body.entries = new_entries

    header = [
        f"# convertibility: {score:.2f} ({stats.mapped}/{stats.total} keys mapped)"
        if stats.total else "# convertibility: 1.00 (no trigger/effect keys)",
    ]
    if below:
        header.append(f"# fae_unported = yes (below [decisions] min_score, score {score:.2f})")
    body.entries and setattr(body.entries[0], "leading_comments", [*header, *body.entries[0].leading_comments])
    if not body.entries:
        body.end_comments = [*header, *body.end_comments]

    return ConvertedDecision(
        id=ck2_id, kind=kind, status=status, score=score,
        mapped=stats.mapped, total=stats.total, block=body,
    )


def find_decision_block(doc_block: Block, kind: str, decision_id: str) -> Block | None:
    for entry in doc_block.entries:
        if isinstance(entry, Node) and entry.key == kind and isinstance(entry.value, Block):
            for sub in entry.value.entries:
                if isinstance(sub, Node) and sub.key == decision_id and isinstance(sub.value, Block):
                    return sub.value
    return None


def run(ctx: Context) -> StepResult:
    config = DecisionsConfig.from_raw(ctx.config.raw.get("decisions", {}))
    if not config.enabled:
        return StepResult(
            summary="skipped: [decisions] enabled = false (opt-in until the port is stable, docs/step_decisions.md §3b)",
            counts={"emitted": 0, "files": 0},
        )
    triggers = read_vocab_csv(config.triggers)
    effects = read_vocab_csv(config.effects)
    traits = TraitInfo.from_ctx(ctx)
    if not traits.live and not traits.renames:
        ctx.warn(
            "decisions: no trait data from step `traits` in this pass; bare "
            "`<trait> = yes/no` shorthand in decisions will show as unmapped "
            "comments (run `traits` in the same pass)"
        )

    rows = read_provenance(config.provenance)
    parsed_cache: dict[Path, Block] = {}
    convertibility_rows: list[list[str]] = []
    by_file: dict[str, list[ConvertedDecision]] = {}
    counts = {"emitted": 0, "hidden": 0, "skipped_group": 0, "skipped_other": 0}

    for row in rows:
        if row.kind not in EMIT_KINDS:
            reason = OUT_OF_SCOPE_REASONS.get(row.kind, f"kind {row.kind!r} out of this lane's scope")
            convertibility_rows.append([row.id, row.kind, row.status, "no", "", reason])
            if row.status in EMIT_STATUSES:
                counts["skipped_group"] += 1
            continue
        if row.status not in EMIT_STATUSES:
            convertibility_rows.append([row.id, row.kind, row.status, "no", "", f"status {row.status}: out of this lane's scope (README §5 step 3 ports new/modified only)"])
            counts["skipped_other"] += 1
            continue

        path = ctx.ck2(row.faerun_file)
        if path not in parsed_cache:
            try:
                parsed_cache[path] = ctx.parse_path(path, lenient=True)
            except OSError:
                # The provenance CSV is a fixed evidence snapshot (goal 2);
                # a run against a ck2_mod that does not match it (e.g. a
                # synthetic test mod) must degrade to "not found", not crash.
                parsed_cache[path] = Block()
        ck2_block = find_decision_block(parsed_cache[path], row.kind, row.id)
        if ck2_block is None:
            ctx.warn(f"decisions: {row.id} ({row.faerun_file}) not found, skipped")
            convertibility_rows.append([row.id, row.kind, row.status, "no", "", "not found in source file at run time"])
            counts["skipped_other"] += 1
            continue

        converted = convert_decision(
            row.id, ck2_block, status=row.status, kind=row.kind,
            triggers=triggers, effects=effects, traits=traits,
            min_score=config.min_score,
        )
        below = converted.score < config.min_score
        counts["hidden" if below else "emitted"] += 1
        convertibility_rows.append([
            row.id, row.kind, row.status, "yes", f"{converted.score:.3f}",
            "below min_score, is_shown forced off" if below else "",
        ])
        by_file.setdefault(row.faerun_file, []).append(converted)

    written: list[Path] = []
    for source_rel, decisions in sorted(by_file.items()):
        stem = Path(source_rel).stem
        out_rel = f"common/decisions/{ctx.config.prefix}_{stem}.txt"
        # CK3 decision files are flat: each decision is a bare top-level key,
        # unlike CK2's `decisions = { ... }`/`society_decisions = { ... }`
        # wrapper groups (`verified` against game/common/decisions/*.txt -
        # no top-level group key anywhere). The CK2 group name only decided
        # emit-eligibility (`EMIT_KINDS`) and is not part of the output.
        top = Block(multiline=True)
        for dec in sorted(decisions, key=lambda d: d.id):
            top.append(Node(key=dec.id, value=dec.block, blank_before=True))
        written.append(ctx.write_script(out_rel, top, source=f"{ctx.ck2_mod.name}/{source_rel}"))

    evidence_path = config.evidence
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    with open(evidence_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["id", "kind", "status", "emitted", "score", "reason"])
        for row in sorted(convertibility_rows, key=lambda r: (r[0])):
            writer.writerow(row)

    return StepResult(
        summary=(
            f"{counts['emitted']} decisions ported live, {counts['hidden']} below "
            f"min_score (is_shown off, inspectable), {counts['skipped_group']} "
            f"out-of-scope groups, {counts['skipped_other']} other skips, "
            f"{len(written)} files"
        ),
        counts=counts | {"files": len(written)},
    )
