# Handoff: lane `events-provenance`

Branch `lane/events-provenance` (worktree `wt/events-provenance`). README §5
steps 1–2. No mod output written — this lane produces CSVs, mapping tables
and one doc only.

## Files changed (all new)

- `scripts/events_provenance.py` — importable + CLI provenance pass over
  `events/`, `decisions/`, `common/on_actions/` for CK2 vanilla vs Faerûn,
  using `ck2ck3.pdx.parse_file`.
- `scripts/events_provenance_summary.py` — regenerates the summary tables in
  the doc, reading the three CSVs back.
- `scripts/build_events_bridge_table.py` — curated file-level CK2→CK3 vanilla
  bridge table builder (`FILE_COUNTERPARTS`, 40 entries).
- `docs/evidence/events_provenance.csv` (13457 rows), `decisions_provenance.csv`
  (959 rows), `on_actions_provenance.csv` (197 rows).
- `mappings/events_ck2_ck3_vanilla.csv` (4760 rows, 56.3 % of kept+modified
  events).
- `docs/events_provenance.md` — method, summary tables, bridge-table
  methodology and coverage, the `vanilla_events_naming_titles.csv`
  cross-check (step 3), open questions.
- `tests/test_events_provenance.py` (5 tests), `tests/test_build_events_bridge_table.py`
  (2 tests) — synthetic fixtures, no dependency on the real Faerûn clone or
  CK2 install.

## Commands and results

- `uv run scripts/events_provenance.py` — 8.6 s.
  `events: 13457 ids deleted=3241, kept=5543, modified=2911, new=1762`
  `decisions: 959 ids deleted=307, kept=3, modified=239, new=410`
  `on_actions: 197 ids kept=107, modified=90`
- `uv run scripts/build_events_bridge_table.py` — <1 s.
  `4760 rows (40 vanilla files) of 8454 kept+modified events (56.3% coverage)`
- `uv run scripts/events_provenance_summary.py` — prints the tables in
  `docs/events_provenance.md` §2–5.
- `uv run pytest -q` — **1011 passed** (`verified`, includes the 7 new tests
  from this lane; the other 1004 are pre-existing).
- `bash ci/checks.sh` — **checks green** (54 s, dominated by the full pytest
  run and the slow Faerûn-parsing tests, neither touched by this lane).

## Counts

| tree | ids | new | kept | modified | deleted |
|---|---|---|---|---|---|
| events | 13457 | 1762 | 5543 | 2911 | 3241 |
| decisions | 959 | 410 | 3 | 239 | 307 |
| on_actions | 197 | 0 | 107 | 90 | 0 (see caveat below) |

Duplicate ids: 0 in either source, either tree (`verified`).
Modified events: 98 loc/desc-only vs 2813 logic-touching (of 2911).

**on_actions caveat** (in the doc, §1 and §2): Faerûn does not `replace_path`
`common/on_actions`, so a vanilla-only on_action name there is still active
in-game — `on_actions_provenance.csv` has 0 `deleted` rows, not because
Faerûn kept every vanilla on_action's *content*, but because absence from
Faerûn's files doesn't remove it from the running game the way it does for
`events`/`decisions`.

## Bridge-table coverage

**56.3 %** of the 8454 vanilla `kept`+`modified` events (4760 ids), via a
**file-level** correspondence over the top 40 vanilla event files by
kept+modified count — not a per-event CK3 id match (none exist to find:
`grep -r` for `CK2`/`"Crusader Kings II"`/any CK2 event id across CK3's whole
`game/events/` tree came back empty, `verified`). 2979 rows point at a real
CK3 events file/folder (confidence `medium` 2116, `low` 1232), 1781 rows are
`none` with a one-line reason. Method, per-file rationale and the full
`FILE_COUNTERPARTS` table are in `scripts/build_events_bridge_table.py`;
summary in `docs/events_provenance.md` §6. 162 files (43.7 % of
kept+modified events) are uncovered — extending is adding rows to
`FILE_COUNTERPARTS` and re-running the script.

## Step 3 (vanilla_events_naming_titles.csv cross-check)

2 of the 101 CK3 vanilla files that name a vanilla title are also a
bridge-table counterpart: `events/dlc/ce1/epidemic_events.txt` (30 title
refs, all county/barony) and `events/religion_events/faith_conversion_events.txt`
(1 title ref). Both `low` confidence. Detail and the caution this implies for
a future events-port lane: `docs/events_provenance.md` §7.

## Open questions for the human

1. Extend bridge-table coverage past 56.3 % before or during the events-port
   lane? Top 100 files reaches 86.3 %.
2. `events/gbc_events.txt` (65 kept+modified) — unidentified CK2 DLC prefix,
   no CK3 counterpart guessed. Worth a human pass if it matters to Faerûn.
3. `events/jd_chinese_diplomacy_events.txt`'s bridge counterpart cites CK3's
   `dlc/tgp/tgp_china_yearly_events.txt` — the "tgp" DLC's real name is
   unverified; confirm before quoting user-facing.
4. Vanilla decisions' `revoke_allowed` finding (§2 of the doc — Faerûn seems
   to have systematically stripped decision-revocation locks) is worth a
   second look by whoever ports decisions next; it dominates the `modified`
   bucket and might be one deliberate global edit rather than per-decision
   design.

## Suggested commit message

```
events: provenance pass + CK2->CK3 vanilla bridge table (README §5 steps 1-2)

Parses CK2 vanilla and Faerun events/decisions/on_actions with the pdx
tokenizer, classifies every id as new/kept/modified/deleted, and curates a
file-level bridge table from the vanilla events Faerun keeps or modifies to
their CK3 vanilla counterpart (56.3% coverage, 40 highest-value files).
Writes no mod output: docs/evidence/*_provenance.csv,
mappings/events_ck2_ck3_vanilla.csv, docs/events_provenance.md.
```
