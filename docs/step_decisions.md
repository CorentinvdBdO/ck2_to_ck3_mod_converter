# Step `decisions`: CK2 decisions → CK3 1.19 syntax

Lane `events-decisions`, README §5 step 3, restricted to **decisions** — the
small, self-contained first slice of the events port (events/on_actions are a
later lane). Vocabulary-table method and coverage: `docs/mapping_triggers_effects.md`.
Code: `src/ck2ck3/steps/decisions.py` (single module, no split business-logic
module — the step is small enough). Registry position: after `loc` and
`traits`, before `tests` (`src/ck2ck3/steps/__init__.py`).

## 1. Which CK2 decisions get a CK3 landing place

CK2 groups eight kinds of decision block under `decisions/*.txt`; CK3
decisions are **always character-scope** (a bare `<id> = { ... }` at the top
level of `common/decisions/*.txt`, `verified` against every vanilla file —
there is no group wrapper at all, unlike CK2's `decisions = { }`,
`title_decisions = { }`, etc.). Only three CK2 groups are themselves
character-scope at the root (no `filter=`/`ai_target_filter=`/third-party
field — the taker's own scope is `ROOT`, `verified` by reading each group's
`.info` doc and a sample file per group):

| CK2 group | root scope | emitted? |
|---|---|---|
| `decisions` | character | **yes** |
| `society_decisions` | character (gated by `is_in_society`) | **yes**, heavily commented (societies do not exist in CK3) |
| `plot_decisions` | character (gated by `has_plot`) | **yes**, heavily commented (CK2 plots have no CK3 counterpart) |
| `title_decisions` | title (via `filter=`) | no — CK3 has no title-scope decisions |
| `settlement_decisions` | settlement/holding (via `filter=`) | no — CK3 has no settlement-scope decisions |
| `offmap_decisions` | offmap power | no — offmap powers do not exist in CK3 |
| `targeted_decisions` / `targetted_decisions` | third-party (`ROOT`=target, `FROM`=taker) | no — maps to CK3 character interactions, out of this lane's scope |
| `trade_post_decisions` | trade post | no — trade routes/posts do not exist in CK3 1.19 |

The five "no" rows become evidence-only rows in
`docs/evidence/decisions_convertibility.csv` (`emitted=no`, a `reason`
column), never written to the mod (`EMIT_KINDS`/`OUT_OF_SCOPE_REASONS` in
`decisions.py`). Of the goal's 410 `new` decisions this leaves **293**
emit-eligible (246 `decisions` + 46 `society_decisions` + 1 `plot_decisions`);
of 239 `modified`, **103** (70 + 16 + 17).

**`modified` decisions are ported exactly like `new`.** The bridge table
`mappings/events_ck2_ck3_vanilla.csv` (lane `events-provenance`) was checked
and has **zero rows of kind `decisions`** (`verified`,
`grep decision mappings/events_ck2_ck3_vanilla.csv` → nothing) — CK3
vanilla decisions carry no per-id CK2 ancestry the way `events_provenance.py`
found for `character_event`/`letter_event`/etc, so the "emit an override of
the CK3 counterpart" path in the goal never applies here; every `modified`
decision is ported as if `new`.

## 2. The port

`convert_decision` builds a CK3 body from five CK2 sections
(`ck3_field_of` in `decisions.py`):

| CK2 | CK3 | table |
|---|---|---|
| `potential` | `is_shown` | trigger |
| `allow` | `is_valid` | trigger |
| `from_potential` | `ai_potential` | trigger |
| `ai_will_do` | `ai_will_do` | trigger (its body is a jomini modifier/MTTH block — trigger-shaped, not effect keys, `verified` by reading real usage) |
| `effect` | `effect` | effect |

`ai_check_interval` copies verbatim, defaulted to 24 months if the CK2
decision has none (CK3 requires one unless `ai_goal = yes`). `only_playable`,
`is_high_prio`, `ai`, `revoke_allowed` have no CK3 decision field at all —
kept as a trailing `# CK2:` comment, not scored (they are decision-level
flags, not trigger/effect vocabulary). `cost` is **not** auto-derived: CK2 has
no `cost = {}` block, only ad hoc `gold =`/`piety =` checks inside `allow`
plus a matching negative `add_gold`/`add_piety` in `effect` — inventing a
`cost = {}` from that pattern risked double-charging or mis-costing, so it is
left at CK3's default (0) and the human sees the original checks as normal
converted trigger/effect content instead.

**`convert_block`** recursively rewrites one trigger/effect block (see §3.
of `src/ck2ck3/steps/decisions.py`'s module docstring for the exact
algorithm). Four special cases besides the plain vocabulary-table lookup:

1. **Scope words** (`ROOT`/`FROM`/`FROMFROM`/`PREV`/`PREVPREV`/`THIS`) are
   rewritten via `ck2ck3.decisions_vocab.SCOPE_WORDS` — `root`/`this`/`prev`/
   `prev.prev` unchanged constructs, `FROM`/`FROMFROM` to a saved scope
   (`scope:ck2_from`/`scope:ck2_fromfrom`, the same naming convention the
   `loc` step already uses for text codes, `docs/loc_codes.md`). Decisions
   never bind `FROM` automatically (no third-party groups are emitted), so
   this path is rare in practice but kept for completeness and any nested
   effect that saves and re-enters a scope under that name.
2. **A bare title-tag key** (`c_x`/`d_x`/`k_x`/`e_x`/`b_x = { ... }`, CK2's
   "open this title's scope" shorthand) becomes `title:<id> = { ... }`
   (`verified`: `game/common/scripted_triggers` uses the identical
   `title:k_france = { ... }` shape). The id is assumed unchanged from CK2 —
   the titles lane keeps CK2 ids verbatim, so this holds for every title the
   titles step actually emitted; a title that step commented out (11,658 of
   them) still resolves to a dangling reference here, same as any other
   `common/decisions` file referencing a title CK3 doesn't have.
3. **Bare `<trait> = yes/no`** (CK2 trigger/effect shorthand for "has/add/
   remove this trait") and **explicit `trait = X`/`remove_trait = X`**
   resolve the trait id through `ctx.data["traits"]` (the `traits` step's own
   id map — never re-derived, per the CLAUDE.md invariant on independently
   derived ids). A trait that step deduped to a CK3 vanilla id, kept live, is
   pure sexuality, or has no CK3 counterpart at all each get the right
   outcome (`has_trait <ck3 id>` / `# CK2-unmapped` with the specific
   reason). **A trait the `traits` step commented out (867 of them,
   `fae_traits_unported.txt`) must be treated as unmapped too** — it is a
   real CK2 trait, distinct from a bare word this table has never heard of,
   and the first version of this code did not check that set, so an id like
   `renowned_wizard` fell through every check and was passed through
   unchanged as if it were already a valid CK3 trait id (`error(unknown-field):
   unknown token` in ck3-tiger). Fixed via `TraitInfo.unported`.
4. **`limit`/`trigger` always force `kind="trigger"` for their body**, even
   nested inside an `effect` section (`effect = { if = { limit = { trait = x
   } ... } }` is common CK2 shape). The generic structural pass-through
   originally kept the parent's kind, so an explicit `trait = x` inside such
   a `limit` picked the *effect* table (`add_trait`) instead of the trigger
   one (`has_trait`) — `error(wrong-use): add_trait is an effect, and can't
   be used in a trigger`. Fixed; a synthetic regression test
   (`test_convert_block_limit_inside_effect_uses_trigger_table`) pins it.

Every other key goes through `_lookup(key, primary, secondary)` — **no
cross-table fallback** (originally there was one, "try the other table if
this one has nothing"; it produced real, wrong output: `wealth`/`piety`/
`prestige`/`opinion` are trigger-only comparisons in CK3, only reachable via
`add_gold`/`add_piety`/`add_prestige`/`add_opinion` on the effect side, and
the fallback happily rewrote `wealth = -10` inside an `effect` block to a
bare `wealth` pass-through because the *trigger* table had it mapped to
`gold`. `_lookup` now consults only the table for the section's own kind).
Unmapped keys — whole subtree, comments and all — are rendered via
`pdx.write` and attached as `# CK2: <line>` comment lines (leading comments
of the next kept sibling, or the block's `end_comments` if nothing follows),
never dropped silently.

**Score** = mapped keys ÷ total trigger/effect-vocabulary keys, accumulated
across every section of one decision (`ConvertStats`). A decision below
`[decisions] min_score` (default 0.6) keeps every converted field — the
comments and all — but its `is_shown` is overwritten to `{ always = no }`
and the header comment gains `# fae_unported = yes (below [decisions]
min_score, ...)`. It is not moved to a separate file: goal 2 explicitly
wants it "inspectable" in place, unlike the `traits` step's dead-code file
convention.

## 3. Known limitations (not fixed in this pass)

1. **No cross-context field validation for a mapped key's *nested* schema.**
   `create_character`/`spawn_unit` genuinely exist in CK3 (`verified`), but
   their inner field set is a fixed template (`template=`/`faith=`/
   `culture=`/... for `create_character`; `location=`/`army_composition=`
   for `spawn_army`) that does not match CK2's open body
   (`remove_trait=`/`attributes={}`/`province=`/`owner=`/`leader=`/
   `troops={}`). Approximating just the *outer* key left CK2's own field
   names inside it, live and wrong (`error(unknown-field)`/
   `error(missing-item)`). Both are marked `none` in the tables instead
   (comment out the whole call) rather than half-convert it — the general
   fix (validate a mapped key's *own* required/allowed nested fields, not
   just whether the key itself exists) is out of this pass's scope.
2. **`X = value` vs `X >= value` semantics.** CK2 authors commonly use `=`
   where they mean "at least" (`gold = 100` inside `allow`, read as a
   minimum); CK3 tiger flags every such line
   (`warning(logic): 'gold =' means exactly equal to that amount`, 198+88+42
   instances for gold/piety/prestige alone). The operator is copied
   verbatim (`entry.op`) — rewriting it would be inventing intent the
   converter cannot verify from the CK2 source alone.
3. **CK2 government/tier id values are not translated, only the keys.**
   `tier = KING` and `government = republic_government`-shaped CK2 values
   pass through unchanged; CK3 wants `tier_kingdom`-style tier constants
   and a `government_map.csv`-mapped (titles lane) government id. Wiring
   that value-level translation into `convert_block` (which currently only
   rewrites keys, never values, except for the trait-id special case) is
   future work.
4. **`any_X` vs `every_X`.** CK3 iterator naming differs by whether it is
   used inside a trigger (`any_X`, boolean) or an effect (`every_X`, runs a
   sub-effect on each). `mappings/event_targets.csv` records the pair where
   curated, but `convert_block` does not yet apply it contextually — a
   handful of `any_X` keys survive unchanged inside `effect` sections
   (`error(validation): cannot use any_ lists in an effect`, 8 instances).
5. **Text**: nothing extra was needed. `faerun_decisions.csv`'s only loc
   keys are `<id>` (title) and `<id>_desc` (description) — `verified`, 0
   `[`-bracket text codes anywhere in that CSV, so no `save_scope_as`
   plumbing is required for decision text specifically. The `loc` step
   already ports both keys verbatim (same CSV-wide machinery every other
   lane relies on); `decisions.py` only adds `selection_tooltip`/
   `confirm_text`, both pointed at `<id>_desc` (CK3's own defaults would be
   `<id>_tooltip`/`<id>_confirm`, which Faerûn never defines, so CK3 would
   show the raw key instead of text — `assumed` design choice, reusing the
   description text is more useful than a broken key).

## 3b. Load crash found by the coordinator's soak, and the two fixes (2026-09-09)

The first build of this step crashed the game during database init (access violation
0x141946BC4, before the main menu). Bisecting the 37 `fae_*` decision files with
`claudespace/scripts/ck3_bisect_probe.sh --mode empty` showed several culprit files; two
defects covered them all:

1. **No `picture` block.** Every vanilla 1.19 decision has `picture = { reference = "..." }`
   (302/302, `verified`); the engine logged `Decision picture ... missing entries` and died.
   The step now emits vanilla's generic `decision_misc.dds` when the CK2 decision has none or
   has a CK2 `GFX_evt_*` name.
2. **`trigger_event` to CK2 event ids.** `character_event`/`letter_event`/`narrative_event`/
   `long_character_event` mapped to `trigger_event`, but no CK2 event is ported yet, so every
   target failed validation (`Event [NE.1] not found`). Those rows are `none` in
   `mappings/effects.csv` until the events step exists; the CK2 block stays as a `# CK2:` comment.

After both: `ck3_soak.sh` 60 s alive, ck3-tiger fatal 0 / error 989 (baseline 58; classes
unknown-field 427, missing-item 332, field-missing 101, structure 62 — the hidden, below-threshold
decisions still carry half-mapped bodies; they are inspectable by design).

**Status after the fixes (coordinator, 2026-09-09 14:45):** not enough. The regenerated build
loaded in 2 of 3 launches and crashed at database init in the third (same address
0x141946BC4); when it loaded, the `-test` runner never executed a test (an always-failing canary
in the mod's own `tests/` passed silently).

**Root cause and the shipped policy (coordinator, 2026-09-09 17:00).** Probe soaks with a canary
test (`claudespace/scripts/ck3_soak.sh`, `canary=fired|silent`) on a build named
`faerun_dec2` with the step enabled:

| probe | canary |
|---|---|
| all 37 files as emitted | silent (3/3) |
| all 37 files emptied | fired |
| all emptied + one hand-written minimal decision | fired |
| one file kept as emitted (`fae_ze_war_chest.txt`, 2 decisions) | silent |
| same file, `is_shown`/`is_valid` stubbed | fired |
| same file, `effect` stubbed | fired |
| same file, `ai_will_do = { base = 0 }` | fired |
| all 37 files, only `ai_will_do` zeroed | silent (4/4) |
| all 396 decisions stubbed (structure only) | fired |

So the converted trigger/effect bodies are the problem class, not any single file: any live
decision whose body carries half-converted CK2 script (CK2 scope words, `factor` weights, empty
`NOT = { }`/`liege = { }` left by commented content) silences the test runner and, in about one
launch in three, crashes database init. A structure-only decision is harmless. Policy now
implemented in `convert_decision`:

1. `min_score = 1.0`: a decision goes live only when every trigger/effect key mapped. Today that is
   3 of 396 (`close_gov_list`, `close_psi_spellbook`, `close_rituals`).
2. Every other decision is an **inert stub**: `is_shown = { always = no }`, `is_valid = { always = yes }`,
   `effect = { }`, `ai_potential = { always = no }`, no `cost`; the converted draft of each section
   is kept above it as `# draft:` comment lines, the original CK2 as `# CK2:` lines. Inspectable,
   never evaluated.
3. `ai_will_do = { base = 0 }` for every ported decision, live or stub: CK2's factor/modifier MTTH
   block is not a CK3 weight. The CK2 block is kept as a comment; the submod re-enables AI use per
   decision.
4. `picture` is emitted once-quoted (`reference = "gfx/..."`); an earlier build double-quoted it and
   desynced the parser (`Decision picture } missing entries`).
5. CK2 event-firing effects (`character_event`, `letter_event`, `narrative_event`,
   `long_character_event`) stay commented until the events step exists.

Verification of the shipped policy, 10 launches each with an in-mod canary
(`claudespace/scripts/ck3_soak.sh`): stub build 8/10 canary fired, 2/10 post-test crash at
0x141972299; baseline build without any decision 9/10 fired, 3/10 the same post-test crash. The two
are indistinguishable; that post-test crash is pre-existing and tracked in STATUS.md. Test config for
this kind of check: `configs/faerun_dec2.toml` (distinct mod `name`, step enabled) — build it to
`wt/_out/dec2`, symlink under `claudespace/mods/`, drop a canary into its `tests/`.

The step is therefore enabled by default again; the scores rise as the vocabulary tables grow
(`mappings/triggers.csv`, `effects.csv`) and decisions go live automatically when they reach 1.0.

## 4. Integration touch outside this lane's own files

`src/ck2ck3/steps/tc_template.py`'s `OUTPUTS` previously included
`common/decisions` (it shadows *vanilla* decision filenames there, blanking
717 `title_links` from vanilla decisions naming vanilla titles,
`mappings/tc_template.csv`). This step also writes to `common/decisions`
(new `fae_*.txt` files, filename-disjoint from every vanilla shadow) — the
two are functionally compatible, but `tests/test_cli.py::
test_step_outputs_do_not_overlap` treats one shared folder string as a
conflict regardless. Fixed by trimming that one folder out of
`tc_template`'s declared `OUTPUTS` (a one-line change with a comment
explaining why); `tc_template.run()` itself, and the vanilla-file shadowing
it does, is unchanged.

## 5. Counts (`verified`, `docs/evidence/last_run.md` this run)

- 959 decisions total; 293 of 410 `new` and 103 of 239 `modified` are
  character-scope (`decisions`/`society_decisions`/`plot_decisions`) —
  **396 emit-eligible**.
- Of those 396: **122 ported live** (`is_shown` as converted), **274** below
  `min_score` (`is_shown = { always = no }`, still inspectable) — mean score
  0.51, median 0.50.
- 253 decisions in the five out-of-scope groups (all `new`/`modified`
  rows), 181 `deleted`-status rows in the three emit-eligible groups
  (outside this lane's job — README §5 covers `new`/`modified` only).
- 37 `common/decisions/fae_*.txt` files, one per CK2 source file that
  contributed at least one emit-eligible decision.
- Full mod run: 1379 files, 0 dry-run/crash issues, ~64 s
  (`docs/evidence/last_run.md`).
- ck3-tiger over the whole generated mod: **fatal 0**, error 1193 (vs the
  build-3 baseline of 58, `docs/evidence/tiger_build3_2026-09-08.txt`) —
  the increase is entirely inside `common/decisions/` (2569 findings there,
  `docs/evidence/tiger_events_decisions_2026-09-09_summary.txt`), consistent
  with §3's limitations. No other lane's output changed.

## 6. Open questions for the human

1. §3.1 — a nested-schema validator (or a second, smaller curated table of
   "safe to approximate the whole nested body" vs "outer key only") would
   let `create_character`/`spawn_unit`/similar be ported instead of
   commented, likely the single biggest quality lever left.
2. §3.3 — wiring `mappings/government_map.csv` (titles lane) and a
   `tier_<x>` constant table into `convert_block`'s value path (today it
   only ever rewrites keys) would clear the `government`/`KING`/`EMPEROR`
   `unknown-field` class (~90 findings).
3. Whether to raise `[decisions] min_score` given the low mean (0.51) — a
   higher bar hides more content behind `is_shown = never` but does not
   change what is *emitted* (everything in scope is always written,
   inspectable or not); a lower bar shows more decisions that may misfire
   in-game. Left at the goal's suggested default (0.6).
4. `docs/mapping_triggers_effects.md` §5's coverage numbers are
   instance-weighted over Faerûn's own usage, not the full CK2/CK3
   vocabulary — extending the curated core (vs. the ground-truth-presence
   auto tier) is incremental, ordered by `decision_uses` in
   `mappings/triggers.csv`/`effects.csv`.
