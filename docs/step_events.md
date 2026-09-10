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
| `score` | 1530 | below `[events] min_score` (1.0): some trigger/effect key did not map |
| `unsaved_scope` | 550 | the body reads `scope:x` without a `save_scope_as = x` of its own. **A CK3 saved scope dies with its event**; a CK2 `event_target` is stored on the character and survives, so the literal translation is broken at runtime |
| `dead_call` | 529 | it fires an event that is itself stubbed, out of scope, or not part of this slice — a `trigger_event` to an id CK3 cannot resolve fails validation at load and is what crashed the decisions build (`docs/step_decisions.md` §3b.2) |
| `from_scope` | 320 | it uses CK2's `FROM`/`FROMFROM`. CK3 has no `FROM`; the converter rewrites it to `scope:ck2_from` (the name the `loc` step already uses, `docs/loc_codes.md`) and nothing saves that scope yet |
| `ck2_variable` | 15 | a CK2 `@` reader variable or `@`-concatenated flag name (`remove_character_flag = nomadrule_duel@FROM`) survived. This breaks CK3's **reader**, not just its script engine, so the rest of the file goes with it |
| `mtth` | 3 | CK3 has no `mean_time_to_happen` on events. The CK2 block is kept as a comment; the CK3 shape is an on_action pulse, and on_actions are the next lane. **No on_action hookup is invented** |
| `no_option` | 0 | a shown CK3 event needs at least one option (a `hidden` one needs none — `game/events/misc_events.txt:3`) |

`live = 160` (145 `character_event` + 15 `letter_event`), `stub = 1544`.
174 events reach score 1.0; 14 of those are held back by a gate.
Score mean 0.410, median 0.375.

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
- **160 live, 1544 inert stubs.** 81 ids remapped for the number ceiling
  (94 numbers rewritten in all, counting leading zeros).
  1499 CK2 event-firing calls seen; only those to a live target become
  `trigger_event`.
- **40 loc-key misses** out of every `desc`/`title`/option-`name` key emitted,
  measured against the `loc` step's own english key set
  (`ctx.data["loc"]["keys"]`, 112,569 keys) — 16 of them reach a live event
  and show as `warning(missing-localization)`.
- Top unmapped CK2 keys (`docs/evidence/events_unmapped_keys.csv`, 1330
  distinct): `character_event` 1345 (a call to a stubbed event),
  `trait` 990 / `add_trait` 710 (a CK2 trait with no CK3 counterpart),
  `mother_even_if_dead` 907, `true_father_even_if_dead` 857, `culture` 636,
  `ai` 617, `religion` 495, `opinion` 429, `hidden_tooltip` 404.
- **ck3-tiger over the whole generated mod: fatal 0, error 58** — exactly the
  build-3/build-12 baseline (`docs/evidence/tiger_events_2026-09-10_summary.txt`,
  `docs/evidence/tiger_build3_2026-09-08.txt`). **No error comes from
  `events/`**; the lane's whole tiger footprint is 18 warnings (16
  `missing-localization`, 1 `use-of-this`, 1 `scopes`).
- `uv run pytest -q` — the full suite green, 27 of them in
  `tests/test_events.py`.
- Full run: 16 steps (the 15 shipped ones plus `events`), **1482 files, 116 s**
  (`docs/evidence/events_fullrun.log`); no other step's counts moved.
- **No in-game soak was run from this lane.** `claudespace/scripts/ck3_soak.sh`
  needs the mod registered under `claudespace/mods/` and rewrites the Proton
  prefix's `dlc_load.json`; both are outside this worktree's write scope. The
  coordinator's command is
  `claudespace/scripts/ck3_soak.sh <name> --secs 120` against a copy of
  `wt/_out/events` with a distinct mod `name` and the canary in its `tests/`
  (`claudespace/docs/ck3_test_framework.md` §8.1).

## 11. Open questions for the human

1. **Rewrite faith/culture/religion *values*** (§7). The `religions` and
   `cultures` steps keep the CK2 ids (`verified`:
   `common/religion/religion_types/fae_elven_pantheon.txt` defines
   `eilistraee`; `common/culture/cultures/fae_elves.txt` defines
   `dark_elf`), so `religion = eilistraee` → `faith = faith:eilistraee`
   through `ctx.data["religions"]`/`["cultures"]` is a small job that would
   un-reject nine of the highest-frequency keys (1131 uses of
   `culture`+`religion` alone). Same fix clears `docs/step_decisions.md`
   §3.3.
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
5. **Nothing fires these events yet** (they are all `is_triggered_only` in
   CK2, and `orphan = yes` here). That is the on_actions lane —
   `docs/evidence/HANDOFF_events.md` §3.
