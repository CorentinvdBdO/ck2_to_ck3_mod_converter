# Events provenance: Faerûn CK2 vs vanilla CK2, and a CK3 vanilla bridge

Lane `events-provenance`, README §5 steps 1–2 (writes no mod output — CSVs
and this doc only). Companion evidence:
`docs/evidence/events_provenance.csv`, `docs/evidence/decisions_provenance.csv`,
`docs/evidence/on_actions_provenance.csv`, `mappings/events_ck2_ck3_vanilla.csv`.
Scripts: `scripts/events_provenance.py` (provenance pass, importable + unit
tested), `scripts/events_provenance_summary.py` (the tables below, regenerate
with `uv run scripts/events_provenance_summary.py`), `scripts/build_events_bridge_table.py`
(the bridge table).

## 1. Method

`scripts/events_provenance.py` parses both trees with `ck2ck3.pdx.parse_file`
(`lenient=True`, `encoding="auto"` — the same tokenizer the rest of the
converter uses; it round-trips comments and auto-detects cp1252 vs UTF-8,
`verified` against 249 vanilla + 332 Faerûn event files, 8.6 s total). Keys:

- **events**: the value of a `<type>_event = { id = … }` block's `id` field.
  CK2 already writes the namespace into the id for namespaced events
  (`id = ADV.1` parses as the string `"ADV.1"`, verified against the
  tokenizer), so no separate namespace bookkeeping is needed — the id string
  *is* the global key, exactly as the CK2 engine treats it.
- **decisions**: the key inside any top-level `<x>decisions = { }` group —
  `decisions`, `targetted_decisions`/`targeted_decisions` (both spellings
  occur, `verified`), `title_decisions`, `society_decisions`,
  `settlement_decisions`, `offmap_decisions`, `plot_decisions`,
  `trade_post_decisions`, `hospital_decisions`, `fort_decisions`.
- **on_actions**: the `on_...` block's own key.

**Classification** per id: `new` (Faerûn only), `deleted` (vanilla only),
and for ids in both — `kept` if the two blocks are structurally equal
ignoring comments and blank-line layout (`ck2ck3.pdx.structurally_equal`),
else `modified` with `changed_keys` = the sorted top-level keys whose value
differs or whose entry count differs (handles duplicate keys, e.g. multiple
`option` blocks, by comparing them pairwise in source order).

**Duplicate ids** within one source (an id defined twice) are recorded via
`vanilla_dup_count`/`faerun_dup_count`, not merged — comparison uses the
first occurrence. `verified` on the real trees: 0 duplicated ids in either
events or decisions, in either source.

**on_actions is additive, unlike events/decisions.** The CK2 engine merges
same-name `on_...` blocks across files (`verified`: vanilla's
`00_zeus_education.txt` adds to `on_adolescence_pulse`/`on_childhood_pulse`,
already defined in `00_on_actions.txt`; Faerûn does the same to
`on_quest_success`, `on_five_year_pulse`, `on_character_ask_to_join_society`
across its own files). So on_actions comparison concatenates every
same-source definition (sorted by file, then line) into one synthetic block
before diffing, and the `faerun_file`/`vanilla_file` columns list every
contributing file, `;`-joined.

**This makes on_actions `deleted` mean something different from events'.**
Faerûn `replace_path`s `events` and `decisions` (`Faerun/Faerun/Faerun.mod`),
so a vanilla id absent from Faerûn's own files there is truly gone from the
game. `common/on_actions` is **not** `replace_path`d (`verified`, the same
`.mod` file), so a vanilla on_action name absent from Faerûn's own
`on_actions/` files still fires unmodified — it is not deleted from the
running game, only from Faerûn's own contribution to it. Read the
`on_actions_provenance.csv` `deleted` rows as "vanilla-only, still active",
not "removed".

**`uses_faerun_mechanic`** is a cheap keyword heuristic (`assumed`, not a
real dependency analysis): every Node key and scalar string in the Faerûn
block, lower-cased, checked by substring against a table of Faerûn/CK2
mechanics with no direct CK3 port (`MECHANIC_KEYWORDS` in the script, drawn
from `docs/mechanics_inventory.md`'s `stub`-converter rows — societies,
offmap powers, bloodlines, wonders, trade routes, execution methods,
disease, custom governments, sorcerer/lich/vampire flavour, job/minor
titles, objectives). A hit means "touches this mechanic's vocabulary",
not "requires it to have logic".

## 2. Summary — status × kind

Regenerate with `uv run scripts/events_provenance_summary.py`.

**events** (13457 ids; runtime 8.6 s):

| status | character | letter | long_character | narrative | province | diploresponse | society_quest | unit | total |
|---|---|---|---|---|---|---|---|---|---|
| deleted | 2282 | 241 | 57 | 466 | 187 | 0 | 7 | 1 | 3241 |
| kept | 4779 | 357 | 20 | 218 | 69 | 87 | 13 | 0 | 5543 |
| modified | 2579 | 93 | 11 | 172 | 36 | 7 | 13 | 0 | 2911 |
| new | 1588 | 56 | 7 | 53 | 32 | 0 | 26 | 0 | 1762 |

**decisions** (959 ids): `deleted`=307, `kept`=3, `modified`=239, `new`=410,
spread over 8 groups (`decisions` dominates: 164 deleted / 70 modified / 246
new). `kept`=3 is real, not a bug: vanilla's `revoke_allowed = { always = no }`
block is present on hundreds of vanilla decisions and absent from almost
every one of them that Faerûn keeps (`verified`: 43 vanilla decision files
use `revoke_allowed` vs 9 Faerûn files, each with far fewer hits), so nearly
every kept vanilla decision reads as `modified` on that one key alone —
Faerûn appears to have systematically stripped decision-revocation locks.

**on_actions** (197 ids): `kept`=107, `modified`=90, `new`=0, `deleted`=0 —
Faerûn adds no new on_action *names* (only content to existing ones) and
removes none of vanilla's (expected: it doesn't `replace_path` the folder,
see above).

## 3. Top event namespaces by modified-count

DLC identity per namespace `verified` by grepping the first vanilla file
declaring `namespace = <ns>` and reading its filename/content (2026-09-08).

| namespace | modified events |
|---|---|
| `<numeric>` (bare vanilla id, no namespace) | 918 |
| HFP (Holy Fury pregnancy/health) | 372 |
| MNM (Monks & Mystics) | 326 |
| HF (Holy Fury) | 310 |
| TOG (The Old Gods) | 248 |
| JD (Jade Dragon) | 204 |
| RIP (Reaper's Due) | 138 |
| WoL (Way of Life) | 118 |
| HL (Horse Lords) | 57 |
| ZE | 56 |
| SoA (Sons of Abraham) | 35 |
| CM (Charlemagne) | 29 |
| LT (Legacy of Rome — `verified` via `hippodrome_events.txt`'s `namespace = LT`) | 26 |
| RoI (Rajas of India) | 16 |
| LoR | 12 |

## 4. Modified events: loc-only vs logic

Of 2911 `modified` events, **98 (3.4 %) change only loc/desc-shaped keys**
(`desc`, `title`, `picture`, `scaled_picture`, `sound`, `quick_desc`,
`border` — `LOC_ONLY_EVENT_KEYS` in the script); **2813 (96.6 %) touch
something else** (trigger, mean_time_to_happen, option, immediate, effect,
…). Faerûn's edits to vanilla events are overwhelmingly mechanical, not
re-flavouring — expected for a total conversion replacing the whole world,
but worth knowing before assuming a `modified` row is "just retitled".

## 5. Duplicate ids

0 duplicated ids in either events or decisions, in either source
(`verified`, `scripts/events_provenance_summary.py`). Nothing to triage.

## 6. Bridge table: `mappings/events_ck2_ck3_vanilla.csv`

**Coverage is file-level and partial, by design.** CK3 replaced CK2's
per-file flavour-event model (13k+ events across 249 vanilla files) with a
handful of shared systems (schemes, lifestyles, activities, relations) plus
DLC-flavour files — there is no way to name a CK3 counterpart for every one
of the 8454 `kept`+`modified` CK2 ids without inventing one, and
`docs/evidence/` evidence rules forbid that. Instead
`scripts/build_events_bridge_table.py` curates **one counterpart per vanilla
CK2 event file** (`FILE_COUNTERPARTS`, 40 entries — the CK3 events file/folder
covering the same theme, a named CK3 system with no events file, e.g. dynasty
legacies, or `none` with a one-line reason from `docs/mechanics_inventory.md`)
and applies it to every `kept`/`modified` id in that file. This covers the
**40 vanilla files with the most kept+modified events — 4760 of 8454 (56.3 %,
`verified`)**. Confidence is `medium` for a specific, otherwise-unclaimed
theme match (e.g. `HF_tribal_events.txt` → `government_events/tribal_events.txt`),
`low` for a broad or uncertain one, `n/a` for `none` rows.

No exact CK2-id → CK3-id row was attempted: `grep -r` for `CK2`,
`"Crusader Kings II"` or any bare CK2 event id across the whole CK3
`game/events/` tree came back **empty** (`verified` 2026-09-08) — CK3 events
carry no comment naming their CK2 ancestor, so any per-event claim beyond
"same file-level theme" would be invented, not evidenced.

**Distribution** (4760 rows): 2979 `event_folder`, 0 `system`, 1781 `none`;
confidence 2116 `medium`, 1232 `low`, 1412 `n/a`.

**Uncovered**: 162 vanilla files (43.7 % of kept+modified events) have no
row. Extending coverage is adding a `FILE_COUNTERPARTS` entry and
re-running `uv run scripts/build_events_bridge_table.py` — the next-highest
files by kept+modified count are visible via
`scripts/events_provenance_summary.py`'s "top namespaces" pass restricted to
`vanilla_file` (not currently a CLI flag; ad hoc via the CSV).

## 7. Cross-check against `docs/evidence/vanilla_events_naming_titles.csv`

That CSV (from lane `tc-template`, `scripts/tc_events_naming_titles.py`)
lists the 101 vanilla CK3 event files that name a vanilla title tag — files
`tc_template` deliberately leaves alone because blanking them would delete
definitions vanilla's own `on_action` entries still call
(`docs/output_bootstrap.md` §4). Two of those 101 files are also a bridge-table
counterpart we would be overriding once the events port writes CK3-side
overrides:

| CK3 file | title_refs | as counterpart of (CK2 file) | confidence |
|---|---|---|---|
| `events/dlc/ce1/epidemic_events.txt` | 30 (30 county/barony) | `events/rip_flavor_events.txt` | low |
| `events/religion_events/faith_conversion_events.txt` | 1 (0 county/barony) | `events/HF_religious_events.txt` | low |

Both are `low`-confidence, file-level theme guesses, not verified per-event
matches — so this is a flag for the future events-port lane, not a blocker:
if the port ever emits a CK3-vanilla-event override for `rip_flavor_events.txt`
or `HF_religious_events.txt` content, it must re-derive
`epidemic_events.txt`/`faith_conversion_events.txt`'s own vanilla-title
references (30 county/barony tags in the epidemic file) rather than assume
they can be blanked, exactly the same caution `tc_template` already applies
to the other 99 files with no bridge-table connection to Faerûn's
kept/modified events.

## 8. Verification

- `uv run pytest tests/test_events_provenance.py tests/test_build_events_bridge_table.py -q`
  — 12 tests, synthetic fixtures covering new/kept/modified/deleted, the
  duplicate-id path, the on_actions cross-file merge, and the mechanic
  keyword heuristic.
- `uv run pytest -q` (whole suite) — 1009 passed (`verified` 2026-09-08,
  `ci/checks.sh`).
- `uv run scripts/events_provenance.py` — 8.6 s, writes the three CSVs
  (13457 + 959 + 197 rows).
- `uv run scripts/build_events_bridge_table.py` — < 1 s, 4760 rows.

## 9. Open questions for the human

1. Bridge-table coverage stops at the top 40 vanilla files (56.3 %) —
   extend `FILE_COUNTERPARTS` for the next tier (top 100 files reaches 86.3 %,
   `docs/evidence/events_provenance.csv` filtered to `kept`/`modified` by
   `vanilla_file`) before the events-port lane starts, or port opportunistically
   and backfill the bridge row per file as it is ported?
2. `gbc_events.txt` (65 kept+modified events) has an unidentified CK2 DLC
   prefix — no CK3 counterpart guess was made; worth a human pass if `gbc_`
   events matter to Faerûn's flavour.
3. `jd_chinese_diplomacy_events.txt`'s CK3 counterpart cites `dlc/tgp/tgp_china_yearly_events.txt`
   under an unverified CK3 DLC name ("tgp") — confirm which CK3 expansion
   this is before quoting it anywhere user-facing.
