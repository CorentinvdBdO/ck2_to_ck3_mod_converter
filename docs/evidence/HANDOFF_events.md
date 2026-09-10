# Hand-off from lane `events` (the `new` slice) to the next event lanes

Lane `events` ported the **1762 `new`** CK2 events (README §5 step 3). Two
jobs are explicitly *not* done and are named here with everything they need:
the **2911 `modified`** vanilla-CK2 events, and **`common/on_actions`**.
Rules and counts for what *was* done: `docs/step_events.md`.

## 1. Contracts the next lanes must reuse, not re-derive

| thing | where | why |
|---|---|---|
| CK2 event id → CK3 id | `ck2ck3.ids.event_id` / `build_event_id_map` | An on_action naming `fae_uthgar.0` while the events step wrote something else is the independently-derived-id failure CLAUDE.md already records twice (2848 + 80 `missing-item`). |
| CK2 namespace → CK3 namespace | `ck2ck3.ids.event_namespace` | `<prefix>_<lower(ck2 namespace)>`; bare-numeric CK2 ids all land in `<prefix>_ck2`. |
| the number ceiling | `ck2ck3.ids.MAX_EVENT_NUMBER` (65535) | 79 Faerûn ids are above it and are re-allocated per namespace, counting down from the ceiling. **A lane that hard-codes `<ns>.<ck2 number>` will point at the wrong event for those 79.** Read `docs/evidence/events_convertibility.csv` (`ck2_id`, `ck3_id`) instead. |
| what is live | `docs/evidence/events_convertibility.csv`, column `live` | A `trigger_event` to a stubbed id is what crashed the decisions build (`docs/step_decisions.md` §3b.2). |
| trigger/effect vocabulary | `mappings/triggers.csv`, `effects.csv`, `event_targets.csv` | Shared with `decisions`; `ck2ck3.steps.decisions.convert_block` is the one converter, with the `hooks` parameter for keys whose CK3 form depends on run state. |
| CK2 art → CK3 theme | `mappings/event_themes.csv` (`scripts/build_event_themes_csv.py`) | 108 rows, every theme id checked against the 1.19 install. |

## 2. The `modified` lane (2911 events)

- **Provenance is already computed**: `docs/evidence/events_provenance.csv`,
  `status = modified`, with `changed_keys` per row. 98 of the 2911 change only
  loc/desc-shaped keys, 2813 touch logic (`docs/events_provenance.md` §4).
- **The bridge table decides the shape of the port**, not this lane:
  `mappings/events_ck2_ck3_vanilla.csv` covers 4760 of 8454 kept+modified ids
  (56.3 %) at *file* level. README §5 step 2 wants a `modified` event whose
  vanilla ancestor has a CK3 counterpart emitted as an **override of the CK3
  event** carrying only the Faerûn delta — that path was never exercised here
  (every `new` event is a fresh id, no CK3 ancestor).
- **Two bridge-table counterparts are also `tc_template` "keep" files**
  (`docs/events_provenance.md` §7): `events/dlc/ce1/epidemic_events.txt` (30
  vanilla title tags) and `events/religion_events/faith_conversion_events.txt`.
  Overriding either means re-deriving its vanilla title references.
- **Reuse this step as is.** `ck2ck3.steps.events.EMIT_STATUSES` is
  `{"new"}`; the whole pipeline is status-agnostic apart from that frozenset
  and the two `OUT_OF_SCOPE_REASONS` kinds. A `modified` slice is
  `EMIT_STATUSES = {"new", "modified"}` plus a decision on the override path
  above — but note the id scheme then has to cope with vanilla CK2 numbers
  (many are 5-digit and above the 65535 ceiling; `build_event_id_map` handles
  it, a hand-rolled f-string does not).
- **Filename collisions**: this lane writes `events/<prefix>_<ck2 stem>.txt`.
  A `modified` lane emitting from the same CK2 file must write into the same
  file or pick a different stem, or the two steps clobber each other. The
  registry's one-owner-per-output rule (`OUTPUTS = ("events",)`) will not
  catch it.

## 3. The `on_actions` lane

- **Provenance**: `docs/evidence/on_actions_provenance.csv`, 197 ids,
  `kept` 107 / `modified` 90 / `new` 0 / `deleted` 0. Faerûn adds no new
  on_action *names* and `common/on_actions` is **not** `replace_path`d, so a
  vanilla name absent from Faerûn's files still fires
  (`docs/events_provenance.md` §1).
- **This is the lane that makes ported events fire at all.** Every event here
  is `is_triggered_only` in CK2 (1759 of 1762) and nothing in the generated
  mod calls them yet, so all 1704 emitted events carry `orphan = yes` or are
  reachable only from another ported event. Wiring CK2 on_action names to CK3
  on_action names is the missing table; CK3's own list is
  `game/common/on_action/*.txt`.
- **MTTH is your job too.** CK3 has no `mean_time_to_happen` on events. The 3
  `new` events that use one are stubbed with the CK2 block kept as a comment
  and gate `mtth` in the evidence CSV; the CK3 shape is an on_action pulse
  with `random_events`/`trigger_event = { days = ... }`. The `modified` slice
  will bring far more of them.
- **`FROM` binding.** 320 of the 1704 events are stubbed only or partly
  because they read CK2's `FROM`. CK3 has no `FROM`; the converter rewrites it
  to `scope:ck2_from`, the name the `loc` step already uses for text codes
  (`docs/loc_codes.md`). An on_action (or the caller's `trigger_event`) that
  does `save_scope_as = ck2_from` before firing would let a large block of
  these go live — **this is the single biggest lever left** (see
  `docs/step_events.md` §4, gate `from_scope`, and `unsaved_scope`, 550).

## 4. Loose ends this lane created for others

1. **`[loc] named_scope = "marker"` can become `"reference"`** once the event
   port ships and events run `save_scope_as`: 64,803 references to a CK2 saved
   scope are currently visible `<!CK2:...!>` markers (the `loc` step says so
   in its own run summary). Only flip it in the same commit that makes the
   scopes exist.
2. **`common/modifiers` is emitted by no step.** 24 distinct CK2 character/
   province modifier ids reach live events, so
   `ck2ck3.steps.events.REJECT_CK2_KEYS` comments every
   `add_character_modifier`-family call out. A modifiers lane would turn all
   of them back on with no change here beyond deleting those rows.
3. **Faith/culture arguments are not rewritten.** `religion = eilistraee`
   should be `faith = faith:eilistraee`; the `religions`/`cultures` steps do
   keep the CK2 ids (`verified`: `common/religion/religion_types/fae_elven_pantheon.txt`
   defines `eilistraee`, `common/culture/cultures/fae_elves.txt` defines
   `dark_elf`), so a value-rewriting pass through `ctx.data["religions"]` /
   `ctx.data["cultures"]` is a small, well-defined job — and it is the same
   gap `docs/step_decisions.md` §3.3 lists.
4. **`decisions` can fire events now.** `mappings/effects.csv` still marks
   `character_event`/`letter_event`/`narrative_event`/`long_character_event`
   as `none` with the note "commented out until the events step exists". That
   note is stale: the events step exists, and `decisions.convert_block` now
   takes the same `hooks` parameter the events step uses to rewrite those
   calls. Wiring it means giving the `decisions` step the live-event id map.
5. **`province_event` (32) and `society_quest_event` (26) are unported by
   design** — evidence-only rows in `docs/evidence/events_convertibility.csv`
   with `emitted = no`. CK3 has no province event type; societies do not
   exist. A submod that re-implements societies would revisit the 26.
