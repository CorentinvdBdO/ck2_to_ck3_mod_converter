# Hand-off — lane `playtest-fixes` (2026-09-08)

Worktree `wt/playtest-fixes`, branch `lane/playtest-fixes` off `main` 484b17c.
**Nothing is committed**; the whole change sits in the working tree. The
coordinator commits, in the order below.

Three independent playtest fixes: A traits policy, B placeholder culture
traditions, C bookmark character positions. No file is shared between A, B and
C except `CLAUDE.md`, `docs/DECISIONS.md` and this file, which the coordinator
may split or keep in commit A.

## Checks

| | |
|---|---|
| `uv run pytest -q` | **949 passed** |
| `ci/checks.sh` | **checks green** |
| `uv run scripts/verify_ck3_keys.py` | **MISSES: 0** |
| `uv run scripts/check_trait_key_coverage.py` | **UNMAPPED KEYS: 0** over 429 live traits |
| `uv run scripts/verify_culture_traditions.py` | **MISSES: 0, DLC-ONLY: 0** (32 distinct ids) |
| `uv run scripts/check_bookmark_positions.py` | 0 violations |
| ck3-tiger over the traits output | **fatal 0 / error 0**, 255 `warning(missing-file)` (icon art), 31 `tips(suggest-localization)` |

Scratch regenerations (never into the real mod):

* `--steps traits` → `<scratch>/out_traits_after`
* `--steps cultures` → `<scratch>/out_cultures`
* `--steps bookmarks` → `<scratch>/out_bookmarks`

where `<scratch>` is
`/tmp/claude-1000/-home-cvdbdo-git-paradox-ck3/b4f0a39f-254b-421f-b3de-c413d45932be/scratchpad`.

---

## Proposed commit 1 — `traits: replace CK2 content CK3 removed, never drop it`

**What changed.** `mappings/vanilla_traits.csv` `status` is now an *action*,
not a confidence level:

| status | before | after | what the step does now |
|---|---|---|---|
| `exact` | 83 | 83 | dedupe to the CK3 id, do not redefine (unchanged) |
| `approx` | 22 | **16** | **port the CK2 trait under its own id** and record the CK3 near-equivalent in `mappings/trait_id_map.csv` with `status = approx`. Both traits exist; the CK3 one is untouched |
| `none` | 7 | **13** | port as a new trait, modifiers through `mappings/modifiers.csv`, CK2 `opposites` preserved (this already worked; only the CSV notes said "emit as comment") |

Six `approx` rows were re-read and downgraded to `none` as **not the same
concept** (`assumed`; the rejected CK3 candidate is kept in each row's `note`):
`crusader` (holy_warrior), `flanker` (flexible_leader), `has_typhoid_fever`
(typhus), `homosexual` (sodomite), `inspiring_leader` (gallant), `trickster`
(strategist). `fair ~ beauty_good_3` stays `exact` — measured evidence.

Guard added: a `none`/`approx` row whose CK2 id CK3 1.19 declares verbatim is
deduped anyway with a warning (no Faerûn row hits it today).

**Counts (Faerûn, `verified`).**

| | before | after |
|---|---|---|
| CK2 trait blocks read | 1417 | 1417 |
| ported as live CK3 traits | 407 | **429** |
| — with a CK3 near-equivalent recorded | 0 | **16** |
| deduped, not redefined | 143 | **121** |
| commented out (unported) | 867 | **867 — unchanged** |
| `mappings/trait_id_map.csv` rows | 143 | 137 (121 dedupe + 16 approx) |
| `mappings/trait_ck2_to_ck3.csv` rows | 550 | 550 (22 rows changed decision) |

1417 = 429 + 121 + 867 exactly, asserted by
`tests/test_traits.py::test_faerun_dedupe_and_classification`.

**Paths.**

* `mappings/vanilla_traits.csv` — 13 rows rewritten + a `#` header stating the policy
* `mappings/modifiers.csv` — **one new row**, `random` → `none` (see "outside scope")
* `mappings/character_effects.csv` — note on the `trait` row: `approx` rows are skipped
* `mappings/trait_id_map.csv`, `mappings/trait_ck2_to_ck3.csv`, `mappings/loc_key_renames_traits.csv`, `overrides/loc_keys.csv` — regenerated
* `src/ck2ck3/traits/port.py` — `Plan.near_equivalents`, `Plan.classify_vanilla()`
* `src/ck2ck3/traits/convert.py` — no `opposites = { }` when every entry vanished
* `src/ck2ck3/steps/traits.py` — header lists the near-equivalents, `near_equivalents` count and hand-off
* `src/ck2ck3/port/tables.py` — skip `approx` rows of `trait_id_map.csv`; `_read` skips `#` lines
* `scripts/build_trait_tables.py`, `scripts/verify_ck3_keys.py` — approx rows, `#` lines
* `scripts/check_trait_key_coverage.py` — **new**, lists every uncovered CK2 trait key at once
* `tests/test_traits.py`, `tests/test_port_characters.py`, `tests/test_port_tables.py`, `tests/test_mappings.py`
* `docs/step_traits.md` (rule 1 rewritten, counts, tiger table), `docs/mapping_modifiers.md`, `docs/evidence/tiger_traits.txt`, `docs/evidence/verify_ck3_keys.txt`, `README.md`, `CLAUDE.md`, `docs/DECISIONS.md`

**Outside the stated scope, and why.**

1. `mappings/modifiers.csv` — porting `trickster` uncovered
   `command_modifier.random`, which is in neither table, and the converter
   raises `UnmappedKey` by design. Added as `none` with the single CK2 use
   cited (`00_traits.txt:2018`). The mappings lane owns this table.
2. `src/ck2ck3/port/tables.py` — required: `trait_id_map.csv` is loaded as a
   rename map on the fallback path, and applying an `approx` row there would
   swap a ported trait for a vanilla one.
3. `scripts/verify_ck3_keys.py`, `tests/test_mappings.py`,
   `src/ck2ck3/port/tables.py::_read` — three plain `csv.DictReader` call
   sites broke on the new `#` header block. All now skip comment lines, like
   `ck2ck3.overrides` and `ck2ck3.traits.tables` already did.

---

## Proposed commit 2 — `cultures: placeholder traditions per culture group`

**What changed.** Only two CK2 flags mapped onto a CK3 tradition, so 322 of 419
cultures had no `traditions` block and an empty culture screen. New human-input
table `overrides/traditions_of_culture_group.csv` (67 rows), seeded from the
`race` column of `overrides/race_of_culture_group.csv` plus 14 per-group
refinements. `derive_traditions()` merges CK2-flag traditions with the group
row, dedupes, and truncates to `MAX_TRADITIONS = 5`
(`DEFAULT_MAX_TRADITIONS`, `00_defines.txt:1163`, `verified`).

**Counts (`verified`).**

| | before | after |
|---|---|---|
| cultures with ≥ 1 tradition | 97 | **392** |
| cultures with none | 322 | **27** (all in the 11 by-design groups) |
| traditions emitted | 97 | **916** |
| groups with no override row | — | **0** |
| distinct tradition ids used | 2 | **32**, all base game |

"No traditions" by design (`verified` 11 groups / 29 cultures): races `horse`,
`cat`, `bear`, `hedgehog`, `duck`, `dog`, `elephant`, `panda`, `undead`,
`construct`, `monster`. Every other culture ends with ≥ 2, asserted by
`test_every_faerun_culture_has_two_traditions_unless_deliberately_none`.

**Every value is `assumed`.** The CSV header says
`assumed placeholders, submod to replace`; so does the comment above each
emitted `traditions` block.

**Gotcha found (`verified`).** CK3 1.19 has **no `tradition_caste_system` and
no `tradition_druidism`** — the real ids are `tradition_ruling_caste` and
`tradition_sacred_groves`. Two of the ids the task named do not exist. Recorded
in `CLAUDE.md`.

**Paths.** `overrides/traditions_of_culture_group.csv` (new),
`scripts/seed_culture_traditions.py` (new),
`scripts/verify_culture_traditions.py` (new),
`docs/evidence/culture_traditions_check.txt` (new),
`src/ck2ck3/steps/cultures.py`, `tests/test_step_cultures.py`,
`docs/step_cultures_religions.md`, `CLAUDE.md`.

---

## Proposed commit 3 — `bookmarks: real character positions and animation variety`

**What changed.** Every bookmark character had `position = { 0 0 }` (82 of 82
stacked in the top-left corner, unclickable) and a constant
`animation = personality_bold`.

* Coordinates: CK2 `map/positions.txt` slot 0 (the city slot) of the
  character's capital county's CK2 province; a duchy or higher uses the live
  county `model.own_counties()` already picks. `TitleModel` gained one field,
  `ck2_of_county`, which `build()` already computed and threw away.
* Projection: normalised over the bounding box of **all live counties** (not of
  the bookmark's own characters), so the same capital lands on the same pixel
  in every bookmark; y flipped (Paradox y grows north).
* Canvas `verified`: x **290–1220**, y **150–820**, from the 93 *displayed*
  positions of CK3 1.19 `common/bookmarks/bookmarks/00_bookmarks.txt`. The 18
  `display = no` animation-test characters, all on `{ 1130 480 }`, are excluded.
  **This is much smaller than the 100–1900 / 100–1000 the task assumed.**
* Repulsion: 60 fixed passes, no randomness, floor 120 px — half vanilla's
  measured 251.6 px minimum pairwise distance. Vanilla's fullest bookmark is 6
  characters; so is ours, so the floor always fits.
* Fallback: an evenly spread deterministic grid, assigned after the geographic
  positions.
* Animation: deterministic `crc32(name_key) % 8` over eight ids that are both
  declared in `gfx/portraits/portrait_animations/animations.txt` and used by
  vanilla bookmarks.

**Counts (`verified`).** 82/82 characters positioned, **zero `{ 0 0 }`**; 63
from the map, 19 on the grid (all 19 hold titular titles — `e_zhentarim`,
`k_red_wizards`, … — with no live county in their subtree). All 8 animations in
use. Two consecutive CLI runs are byte-identical (`cmp` clean).

**Paths.** `src/ck2ck3/titles/bookmarks.py`, `src/ck2ck3/steps/bookmarks.py`,
`src/ck2ck3/titles/model.py` (one field),
`tests/test_bookmarks_test_default.py` (17 tests),
`scripts/survey_vanilla_bookmark_positions.py` (new),
`scripts/check_bookmark_positions.py` (new), `docs/step_titles.md`.

---

## Proposed commit 4 — `docs: --out does not redirect docs/evidence`

`docs/cli.md`. A partial run into a throwaway `--out` still overwrites
committed evidence tables in *this* repo: `--steps traits,characters` rewrote
`docs/evidence/characters_dropped_keys.csv` 427 rows shorter, because without
the `titles` step there is no landed-title hand-off. Restored here; worth a
`git status docs/evidence` after any partial run.

---

## Open questions for the coordinator

1. **The 6 `approx` → `none` downgrades are judgement, not measurement.**
   Accept `crusader`, `flanker`, `has_typhoid_fever`, `homosexual`,
   `inspiring_leader`, `trickster` as "not the same concept"? Each row's `note`
   states the reasoning, so a reversal is a one-cell edit plus
   `scripts/build_trait_tables.py`.
2. **`homosexual` is now a live CK3 trait** carrying CK2's `fertility = -0.15`
   and `same_opinion = 5`. CK3 models orientation as a character sexuality; a
   trait is a different mechanic. Keep, or add an `overrides/` row?
3. **The 16 `approx` pairs create a doubled concept in game** — a character can
   hold `kind` *and* CK3 `compassionate`. That is the point (events can choose),
   but no `opposites`/`compatibility` link is emitted between the two. Should
   the step add one?
4. **`docs/playtest_2026-09-08.md` rows 2, 9, 14 do not exist** — no such file
   in this repo, in `wt/*` or in `claudespace/docs/evidence`. I worked from the
   task text alone. If the playtest log exists somewhere, its rows should be
   cross-checked against what was actually fixed.
5. **Culture traditions are 100 % invented content.** The converter's charter is
   "never invents content"; this lane deliberately breaks it behind an
   `overrides/` file, on the user's explicit request. A `DECISIONS.md` line
   says so — confirm the wording, or tighten the charter in `docs/PROJECT.md`
   to name the exception.
6. **Should the 19 titular-title bookmark rulers use their holder's realm
   capital** (characters-lane data) instead of the fallback grid?
7. **`--steps bookmarks` into a fresh empty `--out`** finds no
   `map_data/definition.csv` and treats every county as dead. Worth a CLI guard
   that says so instead of emitting an empty bookmark file?
8. **Not run:** ck3-tiger over the cultures and bookmarks output, and no game
   launch (both forbidden for this lane). `scripts/validate_cultures_religions.py`
   was not re-run, so `docs/evidence/tiger_cultures_religions.txt` is stale.
9. **`docs/evidence/traits_unported.csv` is unchanged at 867 rows** — nothing
   moved into or out of the commented set, which is the claim worth
   double-checking before shipping.
