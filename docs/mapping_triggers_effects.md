# Mapping CK2 triggers/effects/scopes to CK3 1.19

Lane `events-decisions`, goal 1: `mappings/triggers.csv`, `mappings/effects.csv`,
`mappings/event_targets.csv`, plus the small hardcoded `SCOPE_WORDS` table
(`src/ck2ck3/decisions_vocab.py`). Built and verified by
`scripts/build_decisions_vocab_tables.py`; consumed at runtime by the
`decisions` step (`docs/step_decisions.md`).

## 1. Why there is no `effects.log`/`triggers.log`/`event_targets.log`

The goal named these as the CK3 vocabulary lists to check names against.
Searched the whole machine (`find / -iname effects.log` etc, 2026-09-09):
**they do not exist anywhere** — neither under the CK3 install, the
workspace's `game_files` symlink, nor any Proton prefix. They are written by
the *running game's* console (`logeffects`/`logtriggers`/`logeventtargets`),
which this lane must not launch (hard rule: never launch the game). So the
CK3-side vocabulary had to come from a different, offline source.

## 2. Method

1. **Survey what Faerûn's decisions actually use**
   (`scripts/decisions_vocab_survey.py`): parse every emit-eligible decision
   (`docs/step_decisions.md` §1 — 396 of them) with `ck2ck3.pdx.parse_file`,
   walk `potential`/`allow`/`from_potential`/`ai_will_do`/`ai_potential`
   (trigger-shaped) and `effect` (effect-shaped) separately, tally every
   block/comparison key seen (excluding scope words, jomini logic keys, and
   bare numeric `random_list`/weight keys). Writes
   `docs/evidence/decisions_vocab_survey.csv` — **519 distinct trigger
   keys, 692 distinct effect keys**, 8920/9002 total usage instances.
2. **A CK3 "ground truth" vocabulary**
   (`scripts/ck3_vocab_ground_truth.py`): every `key =`/`key = {` left-hand
   side used anywhere under the local CK3 1.19 install's `game/common/` and
   `game/events/` — **86,926 distinct keys**. This is the same usage-based
   bar `scripts/verify_ck3_keys.py` already established for the modifiers
   lane's `assigned_keys` (CLAUDE.md/`docs/mapping_modifiers.md`), extended
   to `events/` because trigger/effect calls are as dense there as in
   `common/`. It is deliberately broad: it proves "a real CK3 1.19 script
   file uses this exact spelling as a key" — the strongest evidence
   available offline — not "this is a hardcoded engine keyword" (a
   scripted_trigger's own declaration counts too, and so does an unrelated
   field that happens to share a spelling — see §4).
3. **A hand-curated core** — `CURATED_TRIGGERS`/`CURATED_EFFECTS`/
   `CURATED_EVENT_TARGETS` in `scripts/build_decisions_vocab_tables.py` —
   covers the highest-frequency and semantically important keys with a real
   CK2→CK3 mapping (or an honest `none` with a reason), cross-checked
   against real CK3 usage via targeted `grep -rlE '^[ \t]*<key>[ \t]*[=<>]'`
   passes over `game/common`+`game/events` for every candidate rename
   before it was accepted (this is how, for instance, `set_character_flag`
   → `add_character_flag` and `check_variable` → `has_variable` were
   confirmed rather than guessed — CK2 knowledge alone gets this wrong).
4. **Every surveyed key gets a row.** One not in the curated core is
   auto-classified: identical spelling found in the ground truth →
   `exact`/`assumed` ("same spelling in real CK3 script, semantics not
   individually checked"); absent → `none`/`verified` ("not found in the
   CK3 1.19 vocabulary sample"). A key matching a keyword the CK2/Faerûn
   mechanic table already rules out (`society`, `bloodline`, `offmap`,
   `plot`, `wonder`, `job_`, `minor_title`, `trade_post`/`trade_route`,
   `disease`, `execution_method`, `faction`, `ambition`, or the `z_`
   character-class-trigger prefix, `docs/mechanics_inventory.md`) is
   `none`/`verified` with that mechanic's reason instead, regardless of
   ground truth.
5. **A CK2 title-tag-shaped key** (`c_x`/`d_x`/`k_x`/`e_x`/`b_x`) used to
   open a title's scope, and a bare `<trait> = yes/no` shorthand, are
   **not** table rows at all — CK2 general syntax, not vocabulary; handled
   structurally by `ck2ck3.decisions_vocab.TITLE_TAG_RE` and the `traits`
   step's id map (`docs/step_decisions.md` §2).
6. **Verify**: `scripts/verify_decisions_vocab.py` re-checks every non-empty
   `ck3_key` in all three tables (component-wise for a dot chain like
   `faith.religious_head`, ignoring a `scope:`/`title:`/`faith:`/`culture:`
   prefix the step emits itself) against the ground truth and **exits
   non-zero listing every miss** — this is the "a test must fail on an
   unknown CK3 key" requirement, wrapped by
   `tests/test_decisions_vocab.py::test_no_unknown_ck3_key`, with a second
   test (`test_synthetic_unknown_key_is_caught`) proving the check is not a
   tautology by feeding it a fabricated key.

## 3. What "verified" vs "assumed" means here, precisely

- `confidence=verified` on a **mapped** row: the exact `ck3_key` spelling
  was greped against the real CK3 1.19 install this run (either directly, or
  it is the auto-fallback tier, which only ever emits ground-truth-present
  spellings).
- `confidence=verified` on a **`none`** row: either the spelling was
  searched and genuinely absent, or the row is a mechanic-keyword match
  (`docs/mechanics_inventory.md` already establishes those as out of scope).
- `confidence=assumed`: a curated row whose *semantics* (not just spelling)
  were not independently re-derived from real CK2/CK3 modding knowledge in
  this pass, or an auto-fallback `exact` row (spelling verified, meaning
  not). Ground truth cannot distinguish "this exact word is a valid CK3
  trigger/effect key" from "this exact word happens to be some other field's
  name that means something unrelated" — the tables record that honestly
  rather than overclaiming.

## 4. A concrete case where ground truth alone was wrong

`wealth`/`piety`/`prestige`/`opinion`/`name`/`ai` are all *found* in CK3's
`common/`+`events/` — as **trigger-only** comparison keys or unrelated field
names, never as effects. The auto-fallback tier, blind to context, first
marked all of them `exact` in `effects.csv` too (spelling present = pass);
the generated mod then had `wealth = -10`/`piety = -25` inside `effect = {}`
blocks, and ck3-tiger correctly flagged `error(wrong-use): 'piety' is a
trigger and can't be used as an effect`. Fixed by curating explicit `none`
rows for the effect-context spelling (`CURATED_EFFECTS`), each pointing at
the real effect (`add_gold`/`add_piety`/`add_prestige`/`add_opinion`).
This is why `_lookup` (`ck2ck3/steps/decisions.py`) also has **no
cross-table fallback** — an earlier version tried the other table when the
current one had nothing, which reintroduced exactly this class of error via
a different path (`docs/step_decisions.md` §2).

## 5. Coverage

| table | rows | key-level mapped | instance-weighted mapped (of Faerûn's own usage) |
|---|---|---|---|
| `mappings/triggers.csv` | 449 | 112 (25%) | 5313 / 8838 (**60%**) |
| `mappings/effects.csv` | 675 | 155 (23%) | 5097 / 8985 (**57%**) |
| `mappings/event_targets.csv` | 57 (curated only, not survey-driven) | 31 (54%) | n/a |

Key-level coverage looks low because the surveyed vocabulary has a long
tail of Faerûn-specific ids used bare (custom `scripted_trigger`/
`scripted_effect` calls like `z_sorcerer`, `secret_religious_society_*`,
`spawn_good_*_effect` — porting Faerûn's own `common/scripted_effects`/
`scripted_triggers` is a separate, out-of-scope lane) and CK2 constructs CK3
genuinely dropped (societies, plots, offmap, bloodlines, wonders, job
titles, trade routes/posts — every one accounted for in
`docs/mechanics_inventory.md`). **Instance-weighted coverage (~60/57%) is
the more honest number**: most of Faerûn's actual decision content uses the
well-covered core (age, gold/wealth, culture, faith/religion, traits, court/
realm relations, character flags/modifiers, opinions, hooks, MTTH structure)
rather than the long tail.

`mappings/event_targets.csv` is curated-only (not built from the survey):
goal 1 asked specifically for CK2 scope-change keywords named in the brief
(`liege`, `top_liege`, `capital_scope`, `location`, `religion_head`,
`any_vassal`, `random_courtier`, `any_realm_province`, …) plus every one the
curated trigger/effect core also treats as a scope link — 57 rows, 31
mapped (54%).

## 6. Regenerating

```
uv run scripts/decisions_vocab_survey.py       # docs/evidence/decisions_vocab_survey.csv
uv run scripts/ck3_vocab_ground_truth.py       # docs/evidence/ck3_vocab_ground_truth.txt
uv run scripts/build_decisions_vocab_tables.py # mappings/triggers.csv, effects.csv, event_targets.csv
uv run scripts/verify_decisions_vocab.py       # must print "all mapped ck3_key values verified..."
```

`uv run pytest tests/test_decisions_vocab.py -q` runs the same checks as
tests (6 tests: table shape, the verifier itself, a synthetic-fabricated-key
negative control).
