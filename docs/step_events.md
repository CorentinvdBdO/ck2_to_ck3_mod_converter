# Step `events`: Faerûn's 1762 `new` CK2 events → CK3 1.19 syntax

Lane `events`, README §5 step 3 — the **`new`** slice only. The `modified`
2911 events and `common/on_actions` are separate lanes;
`docs/evidence/HANDOFF_events.md` lists everything they need from here.
Provenance and the CK3-vanilla bridge table: `docs/events_provenance.md`.
Vocabulary-table method: `docs/mapping_triggers_effects.md`.

Code: `src/ck2ck3/steps/events.py` (single module, like `decisions`), plus
`ck2ck3.ids.event_id`/`event_namespace`/`build_event_id_map`.
Registry position: after `decisions`, before `tests`.

## 1. Same architecture as `decisions`, deliberately

The step reuses, rather than re-implements:

- `mappings/triggers.csv`, `mappings/effects.csv`,
  `mappings/event_targets.csv` — the shared CK2→CK3 vocabulary;
- `ck2ck3.steps.decisions.convert_block` — the recursive converter, with its
  scope words, title-tag scopes, bare-`<trait> = yes/no` shorthand and
  no-cross-table-fallback rule;
- `ConvertStats` — the convertibility score, mapped ÷ total
  trigger/effect-vocabulary keys;
- **the stabilisation policy of `docs/step_decisions.md` §3b: a
  half-converted body is never live.**

The one addition to `decisions.py` is an optional `hooks` parameter
(default `None`, behaviour otherwise unchanged): a map from lower-cased CK2
key to a callable that owns that key's conversion. It exists for keys whose
CK3 form depends on run state no table can hold — the event-firing effects
(§5), CK2's `event_target:<name>` scope family (§5) and the reject list
(§7).

## 2. Which CK2 events get a CK3 landing place

`verified` against `game/events/_events.info`: CK3 has exactly four event
types (`character_event`, `letter_event`, `court_event`, `activity_event`)
and defaults to `character_event`.

| CK2 kind | `new` count | CK3 `type` | emitted? |
|---|---|---|---|
| `character_event` | 1588 | `character_event` | **yes** |
| `letter_event` | 56 | `letter_event` | **yes** (always gets `sender`, §3) |
| `narrative_event` | 53 | `character_event` | **yes** — CK3 expresses the bigger window with `window = big_event_window`, a per-event look call this step does not guess |
| `long_character_event` | 7 | `character_event` | **yes**, same reason |
| `province_event` | 32 | — | no: CK3 has no province event type, and a non-character root scope must be hidden or major |
| `society_quest_event` | 26 | — | no: societies do not exist in CK3 (`docs/mechanics_inventory.md`) |

The two "no" kinds are evidence-only rows in
`docs/evidence/events_convertibility.csv` (`emitted = no`), never written to
the mod — `OUT_OF_SCOPE_REASONS` in `events.py`. **1704 of the 1762 are
emitted.**

## 3. The port, field by field

| CK2 | CK3 | note |
|---|---|---|
| `<kind>_event = { id = X }` | `<namespace>.<n> = { }` | §4 |
| `hide_window = yes` | `hidden = yes` | |
| `is_triggered_only = yes` | *(dropped)* | it **is** the CK3 default; there is no such field (1759 of 1762 events carry it) |
| `desc = KEY` / `title = KEY` | same | loc key, ported by step `loc` |
| `desc = { text = K trigger = {…} }` (×N) | `desc = { first_valid = { triggered_desc = { trigger = {…} desc = K } … } }` | `_events.info` "Dynamic Description Appendix" §3 |
| `picture` / `border` | `theme = <id>` | §8 |
| — | `left_portrait = root` | every shown character/letter event; CK3 shows nobody otherwise |
| — | `sender = root` on every letter event | **required field**, hidden or not: 41 × `error(field-missing)` in the first build |
| `trigger = { }` | `trigger = { }` | trigger table |
| `immediate` / `after` | `immediate` / `after` | effect table |
| `fail_trigger_effect` | `on_trigger_fail` | `_events.info` |
| `major`, `major_trigger` | same | |
| `option = { name = … <effects> }` | same shape | CK3 accepts both CK2 `name` forms verbatim (`name = key` and `name = { text = key trigger = {…} }`, `_events.info` "Option name specifics") |
| `option = { ai_chance = { factor = … } }` | *(dropped, kept as comment)* | CK2's factor/modifier block is not a CK3 base/add weight; shipping a raw-converted AI weight is what silenced the scripted-test runner in the decisions lane (`docs/step_decisions.md` §3b). With no `ai_chance`, CK3 weights every valid option equally |
| `mean_time_to_happen` | *(none — forces a stub)* | §4 |
| `portrait`, `sound`, `notification`, `hide_from`, `hide_new`, `show_root`, `show_from_from`, `weight_multiplier`, `quest_target` | *(comment)* | CK2 presentation/AI fields with no CK3 event field; not scored |

**Every other top-level key of a CK2 event is an implicit root-scope trigger
condition** (`religion_group = X`, `only_playable = yes`, `has_dlc = …`,
`has_character_flag = …`) and is folded into `trigger = { }` through the
trigger table, scored like any other trigger key. Eight of them need an
operator or a polarity flip that a key→key table cannot express, so they sit
in `EVENT_HEADER_TRIGGERS`: `min_age`→`age >=`, `max_age`→`age <=`,
`prisoner`→`is_imprisoned`, `only_men`→`is_male`, `only_women`→`is_female`,
`only_rulers`→`is_ruler`, `capable_only`/`only_capable`→`is_incapable`
inverted. Every one of those CK3 keys is checked against
`docs/evidence/ck3_vocab_ground_truth.txt` by
`tests/test_events.py::test_header_trigger_keys_are_real_ck3_keys`.

## 4. Ids, namespaces, and the number ceiling

CK2 already writes the namespace into the id (`uthgar.0` parses as the string
`"uthgar.0"`), so the namespace is read back off the id and never tracked per
file — which matters, because five Faerûn namespaces span several files
(`HF`, `KNI`, `MNM`, `RIP`, `TOG`) and CK3 is happy with a namespace declared
in more than one file (vanilla declares `bp1_yearly` in 11).

- `NS.N` → `<prefix>_<lower(NS)>.N` (`BRO.1456` → `fae_bro.1456`), leading
  zeros dropped (`FCE.0001` → `fae_fce.1`, 13 ids) so the single-id and
  whole-set functions cannot disagree about which id an event has.
- bare numeric `N` → `<prefix>_ck2.N`. CK2 numeric ids are unique across the
  whole game (`docs/events_provenance.md` §5), so one shared namespace holds
  all 24 of them and the next lane needs no per-file rule.
- **A CK3 event number must fit in 16 bits.** ck3-tiger accepted every
  generated id up to `43308` and flagged all 79 from `70000` up with
  `warning(event-namespace): Event names should be in the form
  NAMESPACE.NUMBER` (`verified` 2026-09-10). Vanilla's own highest number is
  9999 over all 536 event files, so nothing pins the bound closer than
  "somewhere in 43309…70000"; `ck2ck3.ids.MAX_EVENT_NUMBER = 65535` is the
  `assumed` u16 limit. `build_event_id_map` re-allocates each out-of-range id
  inside its own namespace, counting **down** from the ceiling so it cannot
  collide with the low ids CK2 authors use. **81 of the 1704 CK2 numbers are
  above the ceiling and are remapped**, 94 ids in all once the leading-zero
  cases are counted;
  the mapping is in `docs/evidence/events_convertibility.csv`
  (`ck2_id`,`ck3_id`) and must be read from there, never rebuilt by hand.

Output: one `events/<prefix>_<ck2 stem>.txt` per CK2 source file, in CK2's
own grouping, with the namespace declared at the top. The stem is lower-cased
and whitespace-folded (Faerûn ships `events/faerun_adoption_events .txt`,
with a trailing space).

## 5. The live gates

An event is written **live** only when its score reaches `[events] min_score`
*and* it clears every gate. Otherwise it is an inert stub (§6). Counts over
the 1704 emitted (one event can fail several):

| gate | events | why it is a hard gate |
|---|---|---|
| `score` | 1525 | below `[events] min_score` (1.0): some trigger/effect key did not map |
| `unsaved_scope` | 550 | the body reads `scope:x` without a `save_scope_as = x` of its own. **A CK3 saved scope dies with its event**; a CK2 `event_target` is stored on the character and survives, so the literal translation is broken at runtime |
| `dead_call` | 528 | it fires an event that is itself stubbed, out of scope, or not part of this slice — a `trigger_event` to an id CK3 cannot resolve fails validation at load and is what crashed the decisions build (`docs/step_decisions.md` §3b.2) |
| `from_scope` | 320 | it uses CK2's `FROM`/`FROMFROM`. CK3 has no `FROM`; the converter rewrites it to `scope:ck2_from` (the name the `loc` step already uses, `docs/loc_codes.md`) and nothing saves that scope yet |
| `missing_loc` | 62 | a `desc`/`title`/option-`name` loc key the event uses is not in the ported localisation (§1b). Generalised from the 5 `fae_kni.*` events whose CK2 `EVTDESC700xx` keys were among the 40 loc misses (lane `on-actions` goal 1) |
| `ck2_variable` | 15 | a CK2 `@` reader variable or `@`-concatenated flag name (`remove_character_flag = nomadrule_duel@FROM`) survived. This breaks CK3's **reader**, not just its script engine, so the rest of the file goes with it |
| `mtth` | 3 | CK3 has no `mean_time_to_happen` on events. The CK2 block is kept as a comment; the CK3 shape is an on_action pulse (§on_actions, "MTTH pulse formula") |
| `no_option` | 0 | a shown CK3 event needs at least one option (a `hidden` one needs none — `game/events/misc_events.txt:3`) |

`live = 159` (down from the pre-lane `on-actions` baseline of 160: the
faith/culture value rewrite (§1a) unblocked 5 more events to score 1.0, and
the new `missing_loc` gate (§1b) demoted 6 previously-live events —
`FaerunSorcerer.3` and the 5 `fae_kni.700{24,25,38,39,40}` events, net −1).
`stub = 1545`. 179 events reach score 1.0; 20 of those are held back by
another gate. Score mean unchanged at three decimal places.

### 1a. Faith/culture value rewrite (goal 4, `verified`)

`religion`/`religion_group`/`set_religion`/`culture`/`set_culture` used to be
blanket-rejected (`REJECT_CK2_KEYS`) even though `mappings/triggers.csv`
already carried a correct `religion -> faith` / `culture -> culture` row for
the **trigger** context — the bug was the missing `faith:`/`culture:` value
prefix, not the key mapping, and CK2 overloads the same spelling as an
*effect* setter too. `make_faith_culture_hook` (`events.py`) now resolves the
id through `ctx.data["religions"]`/`["cultures"]` (never re-derived — both
`faith_id`/`culture_id` are identity functions, so a CK2 id is also its CK3
id, `verified` against their own docstrings) and picks the CK3 key by
context:

| CK2 | kind | CK3 | evidence |
|---|---|---|---|
| `religion = X` | trigger | `faith = faith:X` | `game/events/varangian_events.txt:37` |
| `religion = X` / `set_religion = X` | effect | `set_character_faith = faith:X` | `game/events/bookmark_events.txt:2441` |
| `religion_group = X` | trigger | `religion = religion:X` | `game/events/varangian_events.txt:35` |
| `culture = X` | trigger | `culture = culture:X` | `game/common/decisions/10_culture_conversion_decisions.txt:268` |
| `culture = X` / `set_culture = X` | effect | `set_culture = culture:X` | `game/common/decisions/80_major_decisions_middle_europe.txt:1082` |

`culture_group` (no CK3 culture-group concept), `secret_religion` /
`set_secret_religion` (CK3 dropped hidden/secret faith) and
`set_graphical_culture` (a culture field, not a per-character effect) stay
rejected — there is no CK3 target to rewrite them onto, verified by a search
of the whole 1.19 `common/`/`events/` tree.

Effect: 636 `culture` + 495 `religion` = 1131 uses un-rejected (the backlog
item's own count), plus 103 `religion_group`; unmapped-key counts moved from
636/495/103 to whatever the fixpoint settles the surviving `# CK2-unmapped`
comments at (a use inside an already-dead-scored event stays a comment
regardless — `docs/evidence/events_unmapped_keys.csv` after this run).

### 1b. `missing_loc` gate (goal 1, `verified`)

A live event must have every loc key it uses. `KNI.70024`/`70025`/`70038`/
`70039`/`70040` (the `fae_kni.*` events named in the lane brief) scored 1.0
but their `desc` used a CK2 `EVTDESC700xx` key `loc` never ported — CK3
answered with `Unrecognized loc key`, 108 log lines at runtime
(STATUS.md 2026-09-10). `convert_event` now checks every collected
`desc`/`title`/option-`name` key against `ctx.data["loc"]["keys"]` (only
when that data is present — a caller with no loc data, e.g. most unit tests,
never gates) and adds `missing_loc` to `.gates` if any is absent. Generalised
rather than special-cased to those 5 ids, so the same protection covers any
future event with the same defect.

## 6. What a stub looks like

```
fae_bfl.100 = {
	# CK2: BFL.100 (character_event -> character_event) from events/faerun_brotherhood_of_true_flame_events.txt
	# convertibility: 0.40 (4/10 keys mapped)
	# fae_unported = yes: convertibility below [events] min_score
	# The converted draft follows; nothing below `# draft:` is live.
	# draft: fae_bfl.100 = {
	# draft: 	type = character_event
	# draft: 	hidden = yes
	# draft: 	trigger = { … }
	# draft: 	…
	type = character_event
	hidden = yes
	orphan = yes
	trigger = { always = no }
	immediate = { }
}
```

Three choices worth the words:

1. **`type = character_event` whatever the CK2 kind was.** A CK3 letter event
   requires a `sender` and a court/activity event a host; a stub has no scope
   to point them at. The intended type is in the header comment and in the
   draft.
2. **No `option` block.** A `hidden` event needs none —
   `game/events/misc_events.txt:3` is exactly `hidden` + `trigger` +
   `immediate` — and an `option` with no `name` would be a new risk for no
   gain. (This is the one place the lane's brief and the vanilla evidence
   disagree; the evidence won.)
3. **`orphan = yes`**, so CK3 does not log 1544 unreferenced events
   (`game/events/_events.info:242`; vanilla uses it in 8 files).

## 7. Keys rejected on purpose, even though the table maps them

`REJECT_CK2_KEYS` in `events.py`. Each of these has a CK3 key of the same
name, so the vocabulary table maps it — but the **argument** is an id no step
of this converter emits, and ck3-tiger caught every one of them in the first
live build:

- `add_character_modifier` and its seven relatives — `common/modifiers` is
  written by no step, so every CK2 modifier id is
  `error(missing-item): modifier X not defined` (24 distinct ids).
- `religion`, `religion_group`, `set_religion`, `secret_religion`,
  `set_secret_religion`, `culture`, `culture_group`, `set_culture`,
  `set_graphical_culture` — CK3 wants a **prefixed** reference
  (`faith = faith:eilistraee`), and this step rewrites keys, never values
  (the same gap as `docs/step_decisions.md` §3.3). The ids themselves *do*
  exist in the generated mod, so this is a small, well-defined follow-up
  (§9 open question 1).
- `duration` — CK2 spells a modifier's lifetime `duration = N`; CK3 spells it
  `years`/`months`/`days` inside the effect block.
- `has_dlc`/`lacks_dlc` — CK2 DLC names ("Holy Fury") are not CK3
  `dlc_metadata` names.

Two rows of `mappings/effects.csv` were also corrected, the same class the
table's own `docs/mapping_triggers_effects.md` §4 describes: `health` and
`fertility` were auto-classified `exact` because the spelling exists in CK3
script, but only as **triggers**
(`error(wrong-use): 'health' is a trigger and can't be used as an effect`).
Both are now `none` in `CURATED_EFFECTS`.

## 8. Themes: `mappings/event_themes.csv`

CK3 picks an event window's background, icon and sound from `theme = <id>`
(`common/event_themes/00_event_themes.txt`, 191 ids installed). CK2 names a
`picture = GFX_evt_*` illustration and a
`border = GFX_event_<shape>_frame_<category>` frame. The frame category is
CK2's own five-way classification (religion / war / intrigue / economy /
diplomacy) and maps cleanly; the picture is the finer signal where a CK3
theme exists for the same subject.

`scripts/build_event_themes_csv.py` writes the 108-row table (95 picture rows
+ 13 border rows) and **exits non-zero listing any theme id not defined in
the local 1.19 install** — the same bar as `scripts/verify_ck3_keys.py`, also
run as `tests/test_events.py::test_theme_table_only_names_installed_ck3_themes`.
Resolution order is picture → border → `[events] default_theme` (`default`,
itself a real vanilla theme). Result over the 1704 emitted events: `default`
656 (38.5 %), `faith` 348, `learning` 122, `witchcraft` 119, `war` 80,
`martial` 74, `travel` 56, `intrigue` 45, `stewardship` 32, `battle` 22, rest
smaller. Every used theme is defined in `00_event_themes.txt`, i.e. none
needs a DLC.

## 9. Config, and proof the keys are read

```toml
[events]
enabled = true            # false writes no events/fae_*.txt at all
provenance = "docs/evidence/events_provenance.csv"
min_score = 1.0           # mapped ÷ total trigger/effect keys
themes_csv = "mappings/event_themes.csv"
default_theme = "default"
```

`tests/test_events.py::test_config_keys_are_really_read` is the guard against
the silent-no-op class that has bitten this repo three times: it asserts that
`min_score = 0.0` really makes the below-threshold event live, that a
`themes_csv` pointing at an empty table really falls back to
`default_theme`, and that `enabled = false` really writes nothing.

## 10. Counts and verification (`verified`, this run)

- 1762 `new` events in `docs/evidence/events_provenance.csv`; **1704
  emitted** (110 files, 97 namespaces), 58 skipped by scope (32
  `province_event`, 26 `society_quest_event`), 0 not found.
- **159 live, 1545 inert stubs** (before lane `on-actions`: 160/1544 — §1a/§1b
  explain the −1). 81 ids remapped for the number ceiling (94 numbers
  rewritten in all, counting leading zeros). 1499 CK2 event-firing calls
  seen; only those to a live target become `trigger_event`.
- **62 `missing_loc` gates**, 6 of them the *only* thing keeping an
  otherwise-live event (score 1.0) a stub — §1b.
- Top unmapped CK2 keys (`docs/evidence/events_unmapped_keys.csv`): the
  faith/culture rewrite (§1a) removed `culture`/`religion`/`religion_group`
  from the list; `character_event` (a call to a stubbed event), `trait` /
  `add_trait` (a CK2 trait with no CK3 counterpart) and
  `mother_even_if_dead`/`true_father_even_if_dead` remain the largest.
- **ck3-tiger over the whole generated mod: fatal 0, error 58** — unchanged
  from the build-3/build-12/events-lane baseline
  (`docs/evidence/tiger_on_actions_2026-09-23.txt`,
  `docs/evidence/tiger_on_actions_2026-09-23_summary.txt`). Findings located
  under `events/` **dropped from 10 to 3** (the `missing_loc` gate caught the
  loc misses ck3-tiger used to flag as `warning(missing-localization)`
  post-hoc); `common/on_action/` has **zero** findings.
- `uv run pytest -q` — the full suite green (1344 total after lane
  `on-actions`; 42 in `tests/test_events.py`, 8 in `tests/test_on_actions.py`).
- Full run: 18 steps (the 16 events-lane-baseline steps plus `on_actions`),
  **1597 files, 3m25s** (`docs/evidence/last_run.md`); no step before `events`
  moved.
- **No in-game soak was run from this lane** (same constraint as `events`:
  `claudespace/scripts/ck3_soak.sh` needs the mod registered under
  `claudespace/mods/`, outside this worktree's write scope). The
  coordinator's soak list — which live events now fire from which on_action,
  with their trigger's first line, per the safety rule — is
  `docs/evidence/on_actions_convertibility.csv` (`wired = yes` rows) and the
  file-level comment block at the end of `common/on_action/fae_on_actions.txt`.

## 11. Open questions for the human

1. ~~Rewrite faith/culture/religion *values*~~ **done, lane `on-actions`**
   (§1a). `docs/step_decisions.md` §3.3 is the same gap in `decisions.py`
   and is still open — that step's `convert_block` does not (yet) take the
   `religions`/`cultures` maps `events.py` now does.
2. **Growing the vocabulary tables with the events survey was measured and
   is not worth much on its own**: of the 685 trigger and 1573 effect keys
   `scripts/events_vocab_survey.py` found, only 31 and 63 are absent from the
   tables *and* present in the CK3 ground truth — 524 + 946 instances out of
   ~35,000. The long tail is Faerûn's own `scripted_effect`/`scripted_trigger`
   calls (`increase_adv_fatigue_effect`, 221 uses) and CK2 constructs CK3
   dropped. **Porting Faerûn's `common/scripted_effects` /
   `scripted_triggers` is the bigger lever**, and it is nobody's lane yet.
3. **`min_score` and the gates are two different dials.** 174 events score
   1.0 but only 160 are live; conversely a gate like `unsaved_scope` would
   fire on far more events if `min_score` were lowered. Whether to lower
   `min_score` at all is a risk call for the coordinator after a soak — the
   decisions lane's evidence says a live half-converted body crashes database
   init in ~1 launch of 3.
4. **`narrative_event` and `long_character_event` land on a plain
   `character_event` window.** CK3 has `window = big_event_window` for the
   full-screen look; picking it per event is a design call, not a conversion
   one (60 events).
5. ~~Nothing fires these events yet~~ **partially done, lane `on-actions`**
   (§on_actions below) — 1 of 159 live events is now reachable from a CK3
   on_action; the rest wait on wider `mappings/on_actions_ck2_ck3.csv`
   coverage and the `modified`-events lane (most on_action hookups point at
   a vanilla CK2 event, not a `new` one).

## on_actions

Lane `on-actions`, `docs/evidence/HANDOFF_events.md` §3. Code:
`src/ck2ck3/steps/on_actions.py`, registry position: right after `events`.
Makes a live event **reachable**: CK2's `is_triggered_only` events fire only
because *something* names them in `common/on_actions`, and until this step
ran nothing did (§2/§6 `orphan = yes`, the 539 `Event X is orphaned` log
lines STATUS.md 2026-09-10 recorded).

### Orphan reachability, end to end

`orphan = yes` is no longer a static stub-only flag. `write_events` (moved
out of `events.run()` so it can be called twice) renders it on **any** live
event outside `reachable_ids` — reachable meaning "another live event's
`trigger_event` calls it" (`event_calls_within_live`, computed by `events`
itself) **or** "a live `common/on_action` hookup calls it" (computed by
`on_actions`, added on top). `on_actions.run()` re-renders `events`'s own
output files with the fuller set, which is idempotent (`render_event` adds
*or* removes the flag, and never duplicates the header comment — pinned by
`test_render_event_is_idempotent_either_direction`) and cheap: no
re-parsing, just re-rendering already-converted Python objects. Running
`events` alone (`--steps events`) still gets a safe, conservative answer;
running the two together (the default order) gets the real one.

### `mappings/on_actions_ck2_ck3.csv`

197 rows (`scripts/build_on_actions_map.py`, regenerate after editing
`CURATED`/`BUCKETS`): 107 `kept` (Faerûn's on_action block is byte-identical
to vanilla CK2 — nothing to port, `docs/events_provenance.md` §2) and 90
`modified`. Of the 90, **13 have a CK3 counterpart, individually verified**
against `../claudespace/game_files/common/on_action/*.txt` (name, root
scope, one piece of evidence per row — see the table's own `note` column);
the other 77 are `confidence = none` with a reason bucket (`society`: CK3 has
no societies, 9 ids; `combat-side scope`: CK3's `on_combat_end_winner`/
`_loser` root is the winning/losing *combat side*, not a character,
`verified` `game/common/on_action/combat_on_actions.txt:14` "Root = Winning
combat side" — firing a character-scope body there needs a scope hop this
pass does not synthesize, 12 ids; `war-ended scope`: `on_war_won_attacker`/
`_defender`/`_white_peace`/`_invalidated` document no character root at all,
4 ids; `crusade`: CK3 replaced crusades with great holy wars, 9 ids;
`not researched`: the remaining 43 — same per-name check as the 13 curated
rows, just not done this pass, `docs/evidence/HANDOFF_on_actions.md`).

Not a semantic-search guess: every mapped row's evidence is a vanilla
`common/on_action` file:line quote (`docs/step_events.md`'s own table in
`scripts/build_on_actions_map.py`'s `CURATED` docstring), the same bar
CLAUDE.md's invariants hold format facts to.

### Additive merge, verified for CK3 (not just CK2)

`docs/events_provenance.md` §1 already proved CK2 merges same-name
on_actions across files. **CK3 does too**, `verified` on the vanilla install
itself: `game/common/on_action/yearly_on_actions.txt:1975` and `:2915` both
declare `three_year_playable_pulse = { events = { ... } }` — two separate
declarations, each contributing its own `events` list, both fire (there is
no third file to check against; this is vanilla redeclaring its own
on_action, which only makes sense if the engine appends rather than
overwrites). `on_actions.py`'s output file therefore never writes anything
but `events =`/`random_events =` keys — never `trigger`/`effect`/other
fields — so it cannot delete a vanilla hookup the way a full redefinition
would.

### The wiring rule: live only, everything else stays a comment

For each mapped CK2 on_action, `collect_faerun_on_actions` merges every
Faerûn declaration of that name (across `common/on_actions/*.txt`, same
additive rule) and `extract_event_refs` walks its `events =`/`random_events
=` lists. Each referenced id is one of three things:

1. **Not a `new` event this converter ports** — a vanilla CK2 kept/modified
   id, or an id outside this run's scope entirely. Stays a `#` comment; the
   `modified`-events lane owns it.
2. **A `new` event, but stubbed** (`fae_unported`). Stays a `#` comment —
   the same rule `make_event_hook` already enforces for event-to-event
   calls, one level up: a hookup to an id CK3 cannot resolve is what crashed
   the decisions build (`docs/step_decisions.md` §3b.2).
3. **Live.** Appended to the matching CK3 on_action's `events`/
   `random_events` list, with a `# CK2 <id> via <on_action>` trailing
   comment, and folded into `reachable_ids` so `events`'s own `orphan` flag
   clears.

This run: **1 live event wired** (`fae_frmaint.20`, via
`on_character_convert_religion` -> `on_character_faith_change`) out of 185
hookups the 13 mapped on_actions carry — 137 point at a vanilla CK2 event
(bucket 1), 47 at a stubbed `new` event (bucket 2). The small number is the
honest consequence of two narrow gates multiplying (13/90 on_actions mapped
× 159/1704 events live), not a bug — `docs/evidence/on_actions_convertibility.csv`
has the row for every hookup this pass looked at, wired or not, with a
`reason` column.

### MTTH pulse (goal 3): formula documented, not wired

CK3 has no `mean_time_to_happen`; the shape is an on_action pulse with
`random_events` weights, `game/common/on_action/yearly_on_actions.txt:840`
`yearly_playable_pulse` (root = the playable character, fires once a year
on their birthday, `game/common/on_action/_on_actions.info`) or `:2483`
`quarterly_playable_pulse` (same, every quarter, both names `verified`
against the install — the `_on_actions.info` doc names them
`on_yearly_playable`/`quarterly_playable_pulse`, but the *id* actually
declared is `yearly_playable_pulse`, not `on_yearly_playable`; anyone citing
the `.info` comment name instead of the real id would point at nothing).

Formula, for when it is needed: `weight = round(12000 / mean_months)`,
clamped to a floor of 1, attached to `yearly_playable_pulse`'s
`random_events` (a 12-month MTTH gets weight 1000; a monthly one 12000,
correctly dominant since it only gets one roll a year instead of twelve).
`mean_months` is the CK2 block's base `months =`/`years = N × 12` only — any
`modifier = { factor = ... }` sub-block is dropped, the same treated-as-a-
weight-not-a-value limitation `docs/step_decisions.md` §3b already accepted
for `ai_chance`. `quarterly_playable_pulse` is the finer-grained alternative
for `mean_months` below ~4.

**Recounted this run** (goal 3's ask): still exactly **3** CK2 `new` events
carry `mean_time_to_happen` (`conv.70100`, `localleaders.1`,
`localleaders.5`), and all three also fail `score` (0.32–0.35) —
none is "live except for MTTH". Wiring a pulse hookup for a 32 %-mapped body
is exactly what the stabilisation policy forbids (`docs/step_decisions.md`
§3b), so **no on_action pulse hookup is emitted**. The formula above is
ready for the `modified`-events lane, which will raise both the count and
(via the shared vocabulary tables) some of these scores.

### Safety-rule soak list

Per the goal's safety rule: the one live event this run wires, its target
on_action, and its trigger's first line, is
`docs/evidence/on_actions_convertibility.csv` (`wired = yes` row) and
restated as a file-level comment at the end of
`common/on_action/fae_on_actions.txt`. ck3-tiger over the whole generated
mod: **fatal 0, error 58** (unchanged), zero findings under
`common/on_action/`. In-game soak is the coordinator's
(`docs/evidence/HANDOFF_on_actions.md`).
