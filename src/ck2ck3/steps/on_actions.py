"""Step ``on_actions``: wire ported-**live** CK2 events into CK3 on_actions.

Lane `on-actions`, README §5 the `events` hand-off's §3
(`docs/evidence/HANDOFF_events.md`). Every event the `events` step emits is
``is_triggered_only`` in CK2 (`docs/step_events.md` §2), so nothing calls it
in the generated mod - the game logs `Event X is orphaned` for every one of
them. This step is what makes a live event **reachable**: it reads
``mappings/on_actions_ck2_ck3.csv`` (CK2 on_action name -> CK3 counterpart,
built by ``scripts/build_on_actions_map.py``), finds the *live* event ids
Faerûn's own on_action blocks already hook up, and appends them to the
matching CK3 on_action's ``events``/``random_events`` list.

**Additive, never a redefinition.** CK3 merges same-name on_action blocks
across files (`verified`, `game/common/on_action/yearly_on_actions.txt:1975`
and `:2915` both declare `three_year_playable_pulse`, each contributing its
own `events = { }` list - both fire). This step's output file only ever
carries `events =` / `random_events =` keys, never `trigger`/`effect`/other
on_action fields, so it cannot silently delete a vanilla hookup the way a
full redefinition would.

**A hookup to a stubbed or unmapped event stays a `# ` comment.** Firing a
`trigger_event` to a stubbed id is what crashed the decisions build
(`docs/step_decisions.md` §3b.2); the same rule applies here one level up.

Runs after ``events`` (needs ``ctx.data["events"]``: the converted bodies,
the live-id set and the CK2->CK3 id map) - and re-renders `events`'s own
output files with the fuller reachability the on_action hookups add, so the
`orphan` flag is right without re-parsing any CK2 source
(`ck2ck3.steps.events.write_events`).
"""

from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from ..config import REPO_ROOT
from ..context import Context, StepResult
from ..pdx import Block, Item, Node
from . import events as events_step

DESCRIPTION = "wire ported-live CK2 events into CK3 common/on_action hookups"
#: File-disjoint from `tc_template`'s `common/on_action/story_cycles` shadow
#: and from vanilla (`mappings/tc_template.csv`: `common/on_action` itself is
#: `keep`, not shadowed) - this step only ever writes new `fae_*.txt` files.
OUTPUTS: tuple[str, ...] = ("common/on_action",)

#: CK2/CK3 on_action list keys that name events (`_on_actions.info` STRUCTURE).
EVENT_LIST_KEYS = ("events", "random_events")
#: Control keys inside an `events =`/`random_events =` block that are not an
#: event reference (`_on_actions.info`).
CONTROL_KEYS = frozenset({"delay", "chance_to_happen", "chance_of_no_event"})


@dataclass
class OnActionsConfig:
    enabled: bool = True
    mapping: Path = REPO_ROOT / "mappings" / "on_actions_ck2_ck3.csv"
    evidence: Path = REPO_ROOT / "docs" / "evidence" / "on_actions_convertibility.csv"

    @classmethod
    def from_raw(cls, raw: dict) -> "OnActionsConfig":
        def _resolve(value: str | None, default: Path) -> Path:
            path = Path(value).expanduser() if value else default
            return path if path.is_absolute() else REPO_ROOT / path

        return cls(
            enabled=bool(raw.get("enabled", cls.enabled)),
            mapping=_resolve(raw.get("mapping"), cls.mapping),
            evidence=_resolve(raw.get("evidence"), cls.evidence),
        )


@dataclass
class MapRow:
    ck2_on_action: str
    status: str
    ck3_on_action: str
    ck3_root_scope: str
    confidence: str
    note: str


def read_mapping(path: Path) -> list[MapRow]:
    rows: list[MapRow] = []
    with open(path, encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            rows.append(MapRow(
                ck2_on_action=row["ck2_on_action"], status=row["status"],
                ck3_on_action=row["ck3_on_action"], ck3_root_scope=row["ck3_root_scope"],
                confidence=row["confidence"], note=row["note"],
            ))
    return rows


def collect_faerun_on_actions(ctx: Context) -> dict[str, Block]:
    """CK2 on_action name -> merged Block, across every Faerûn on_actions file.

    CK2 (and CK3) both merge same-name on_action blocks additively across
    files (`verified`, `docs/events_provenance.md` §1: Faerûn itself defines
    `on_quest_success`/`on_five_year_pulse`/... in more than one file). A
    fresh, lightweight pass rather than reusing
    `scripts/events_provenance.collect_on_actions` - that module lives in
    `scripts/`, which `src/` does not import from.
    """
    entries_by_name: dict[str, list] = defaultdict(list)
    oa_dir = ctx.ck2("common", "on_actions")
    if not oa_dir.is_dir():
        return {}
    for path in sorted(oa_dir.glob("*.txt")):
        doc = ctx.parse_path(path, lenient=True)
        for entry in doc.entries:
            if isinstance(entry, Node) and entry.key.startswith("on_") and isinstance(entry.value, Block):
                entries_by_name[entry.key].extend(entry.value.entries)
    return {name: Block(entries=entries) for name, entries in entries_by_name.items()}


@dataclass
class EventRef:
    ck2_event_id: str
    list_kind: str  # "events" | "random_events"
    weight: int | None = None


def extract_event_refs(block: Block) -> list[EventRef]:
    """Every event id named in an on_action's `events =`/`random_events =` lists.

    `events = { id1 id2 }` is a bare list (`Item` entries); `random_events =
    { 100 = id1 }` is `weight = id` (`Node` entries) - both documented in
    `game/common/on_action/_on_actions.info` STRUCTURE. `delay =`/
    `chance_to_happen =`/`chance_of_no_event =` are on_action machinery, not
    event references, and a `random_events` weight of `0` is CK2/CK3's
    "chance nothing fires" placeholder, not an id.
    """
    refs: list[EventRef] = []
    for entry in block.entries:
        if not (isinstance(entry, Node) and entry.key in EVENT_LIST_KEYS):
            continue
        value = entry.value
        if not isinstance(value, Block):
            continue
        for sub in value.entries:
            if isinstance(sub, Item):
                refs.append(EventRef(str(sub.value), entry.key))
            elif isinstance(sub, Node):
                if sub.key in CONTROL_KEYS:
                    continue
                if entry.key == "random_events":
                    try:
                        weight = int(sub.key)
                    except ValueError:
                        continue
                    target = str(sub.value)
                    if target == "0":
                        continue
                    refs.append(EventRef(target, entry.key, weight))
                else:
                    # `events = { id delay = {...} }`: a Node here is `delay`
                    # (already skipped) or a malformed entry - not an id.
                    continue
    return refs


def _trigger_first_line(conv) -> str:
    """The trigger's first line, for the safety-rule soak list (§ below)."""
    for entry in conv.body.entries:
        if isinstance(entry, Node) and entry.key == "trigger" and isinstance(entry.value, Block):
            for sub in entry.value.entries:
                if isinstance(sub, Node):
                    return f"{sub.key} {sub.op} {sub.value}"
            return "(empty trigger, always fires)"
    return "(no trigger block, always fires)"


@dataclass
class WiredEvent:
    ck2_on_action: str
    ck2_event_id: str
    ck3_event_id: str
    list_kind: str
    weight: int | None
    trigger_first_line: str


def run(ctx: Context) -> StepResult:
    config = OnActionsConfig.from_raw(ctx.config.raw.get("on_actions", {}))
    if not config.enabled:
        return StepResult(
            summary="skipped: [on_actions] enabled = false",
            counts={"on_action_files": 0, "live_events_wired": 0},
        )

    events_data = ctx.data.get("events")
    if not events_data:
        ctx.warn(
            "on_actions: step `events` did not populate ctx.data['events'] in "
            "this pass; nothing to wire (run `events` and `on_actions` together)"
        )
        return StepResult(
            summary="skipped: no events data (run `events` in the same pass)",
            counts={"on_action_files": 0, "live_events_wired": 0},
        )

    ck3_id_of: dict[str, str] = events_data["ck3_id_of"]
    live_ids: set[str] = events_data["live_ids"]
    converted = events_data["converted"]

    mapping_rows = read_mapping(config.mapping)
    mapped = [r for r in mapping_rows if r.confidence == "verified" and r.ck3_on_action]
    faerun_blocks = collect_faerun_on_actions(ctx)

    # ck3_on_action -> list_kind -> [WiredEvent]
    wired: dict[str, dict[str, list[WiredEvent]]] = defaultdict(lambda: {"events": [], "random_events": []})
    # ck3_on_action -> [comment lines for a skipped hookup]
    skipped_comments: dict[str, list[str]] = defaultdict(list)
    evidence_rows: list[dict[str, str]] = []

    for row in mapped:
        block = faerun_blocks.get(row.ck2_on_action)
        if block is None:
            evidence_rows.append({
                "ck2_on_action": row.ck2_on_action, "ck3_on_action": row.ck3_on_action,
                "ck2_event_id": "", "ck3_event_id": "", "list_kind": "", "weight": "",
                "wired": "no", "reason": "CK2 on_action not found in Faerûn's own files at run time",
                "trigger_first_line": "",
            })
            continue
        for ref in extract_event_refs(block):
            if ref.ck2_event_id not in ck3_id_of:
                reason = "not a `new` event this converter ports (vanilla CK2 kept/modified, or an id outside this run's scope) - the modified-events lane owns it"
                wired_flag = "no"
                ck3_event_id = ""
                first_line = ""
            elif ref.ck2_event_id not in live_ids:
                reason = "emitted as an inert stub (fae_unported), not live"
                wired_flag = "no"
                ck3_event_id = ck3_id_of[ref.ck2_event_id]
                first_line = ""
            else:
                ck3_event_id = ck3_id_of[ref.ck2_event_id]
                conv = converted[ref.ck2_event_id]
                first_line = _trigger_first_line(conv)
                wired[row.ck3_on_action][ref.list_kind].append(WiredEvent(
                    ck2_on_action=row.ck2_on_action, ck2_event_id=ref.ck2_event_id,
                    ck3_event_id=ck3_event_id, list_kind=ref.list_kind,
                    weight=ref.weight, trigger_first_line=first_line,
                ))
                reason = ""
                wired_flag = "yes"
            if wired_flag == "no":
                skipped_comments[row.ck3_on_action].append(
                    f"# CK2 {row.ck2_on_action} -> {ref.ck2_event_id}: not wired ({reason})"
                )
            evidence_rows.append({
                "ck2_on_action": row.ck2_on_action, "ck3_on_action": row.ck3_on_action,
                "ck2_event_id": ref.ck2_event_id, "ck3_event_id": ck3_event_id,
                "list_kind": ref.list_kind, "weight": str(ref.weight or ""),
                "wired": wired_flag, "reason": reason, "trigger_first_line": first_line,
            })

    # -- write the hookup file ------------------------------------------------
    top = Block(multiline=True)
    for ck3_name in sorted(wired):
        lists = wired[ck3_name]
        if not lists["events"] and not lists["random_events"]:
            continue  # every hookup for this target was skipped
        body = Block(multiline=True)
        if lists["events"]:
            events_block = Block(multiline=True)
            for w in lists["events"]:
                events_block.append(Item(
                    value=w.ck3_event_id,
                    trailing_comment=f"# CK2 {w.ck2_event_id} via {w.ck2_on_action}",
                ))
            body.append(Node(key="events", op="=", value=events_block))
        if lists["random_events"]:
            random_block = Block(multiline=True)
            for w in lists["random_events"]:
                random_block.append(Node(
                    key=str(w.weight or 100), op="=", value=w.ck3_event_id,
                    trailing_comment=f"# CK2 {w.ck2_event_id} via {w.ck2_on_action}",
                ))
            body.append(Node(key="random_events", op="=", value=random_block))
        body.end_comments = list(skipped_comments.get(ck3_name, ()))
        top.append(Node(key=ck3_name, op="=", value=body, blank_before=True))

    # Root-scope note, once per mapped CK3 target, as a file-level comment -
    # the safety-rule soak list (docs/step_events.md §on_actions).
    scope_notes = sorted({
        f"# {r.ck3_on_action}: root = {r.ck3_root_scope} ({r.note})"
        for r in mapped if r.ck3_on_action in wired and (
            wired[r.ck3_on_action]["events"] or wired[r.ck3_on_action]["random_events"]
        )
    })
    top.end_comments = ["# Root scope of every target below, verified against the 1.19 install:", *scope_notes]

    written = []
    if top.entries:
        written.append(ctx.write_script(
            "common/on_action/fae_on_actions.txt", top,
            source="mappings/on_actions_ck2_ck3.csv + common/on_actions (Faerûn)",
        ))

    # -- re-render `events`'s own files: on_action hookups make more live
    # -- events reachable, so `orphan` needs recomputing (no re-parsing).
    reachable_from_here = frozenset(
        w.ck3_event_id
        for lists in wired.values()
        for kind_list in lists.values()
        for w in kind_list
    )
    full_reachable = frozenset(events_data["reachable_ids"]) | reachable_from_here
    events_step.write_events(ctx, events_data["prefix"], events_data["by_file"], full_reachable)
    events_data["reachable_ids"] = full_reachable

    # -- evidence ---------------------------------------------------------------
    config.evidence.parent.mkdir(parents=True, exist_ok=True)
    with open(config.evidence, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "ck2_on_action", "ck3_on_action", "ck2_event_id", "ck3_event_id",
            "list_kind", "weight", "wired", "reason", "trigger_first_line",
        ])
        writer.writeheader()
        writer.writerows(evidence_rows)

    still_orphaned = live_ids - {
        ck2 for ck2, ck3 in ck3_id_of.items() if ck3 in full_reachable
    }
    counts = {
        "on_action_files": len(written),
        "on_action_targets": sum(1 for n in wired if wired[n]["events"] or wired[n]["random_events"]),
        "live_events_wired": len(reachable_from_here),
        "hookups_skipped": sum(1 for r in evidence_rows if r["wired"] == "no"),
        "mapped_on_actions": len({r.ck2_on_action for r in mapped}),
        "live_events_still_orphaned": len(still_orphaned & live_ids),
    }
    return StepResult(
        summary=(
            f"{counts['live_events_wired']} live events wired from "
            f"{counts['mapped_on_actions']} mapped CK2 on_actions into "
            f"{counts['on_action_targets']} CK3 on_action targets "
            f"({counts['hookups_skipped']} hookups skipped as comments); "
            f"{counts['live_events_still_orphaned']} live events still orphaned"
        ),
        counts=counts,
    )
