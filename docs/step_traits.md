# Step `traits` — CK2 traits → CK3 1.19

Owns `common/traits` and `gfx/interface/icons/traits` in the generated mod.
Code: `src/ck2ck3/traits/` (decisions) + `src/ck2ck3/steps/traits.py` (wiring).
Run: `uv run ck2ck3 --config configs/faerun.toml --steps traits`.
Tables for other lanes: `uv run scripts/build_trait_tables.py`.

## Counts (`verified` 2026-09-08, Faerûn @ current clone, after the traits-remap lane)

| | traits |
|---|---|
| CK2 trait blocks read (`common/traits/*.txt`, 16 files) | **1417** |
| ported as live CK3 traits | **400** |
| — of which race traits | 117 |
| deduped/mapped to an existing CK3 trait, **not** redefined | **142** |
| dropped: no CK3 landing place at all | **7** |
| became a CK3 `sexuality` history key, not a trait | **1** |
| kept only as commented blocks | **867** |

1417 = 400 + 142 + 7 + 1 + 867 exactly; a test asserts it
(`tests/test_traits.py::test_faerun_dedupe_and_classification`).

**Second policy change, 2026-09-08 (superseding the first the same day,
`docs/DECISIONS.md`):** the user clarified that "replace, never drop" means
*map to the existing CK3 trait*, not *port a new CK2-named trait* — players
kept seeing `cruel`, `envious`, … in the trait list. The 16 `approx` rows now
dedupe exactly like `exact` (rule 1); the 13 `none` rows split into three new
actions instead of being ported as new traits (rule 1). Net change from the
first 2026-09-08 policy: 429 → 400 ported, 121 → 142 deduped, +7 dropped, +1
sexuality. **Nothing moved into or out of the commented set**, and the vanilla
first-policy history (407 → 429 ported / 143 → 121 deduped) still applies
before this second change.

Inside the 400: 678 CK2 property keys and 87 modifier keys became comments,
93 more wait on the cultures/religions name map, 66 CK2 trigger blocks were
commented whole, 124 keys were dropped for a CK3 genetic-vs-inheritance rule,
81 duplicate keys were collapsed, 69 traits got a `group`/`level`, 3 became a
`compatibility` entry, 168 got an icon.

## Outputs

| path | what |
|---|---|
| `common/traits/fae_traits.txt` | the 400 live traits; header lists all 142 dedupes, the 1 sexuality mapping and the 7 drops |
| `common/traits/fae_traits_unported.txt` | the 867 as commented-out blocks |
| `gfx/interface/icons/traits/<trait>.dds` | 168 CK2 icons, copied unchanged |
| `mappings/trait_ck2_to_ck3.csv` | **542 rows, every CK2 trait that resolves in the mod → its CK3 id.** The authoritative known-trait set the `characters` port filters by; deriving it from the classification tables instead wrongly commented out 8308 `trait` lines (`docs/step_characters.md`). A `drop`/`sexuality` vanilla-table trait is never in this table |
| `mappings/trait_id_map.csv` | 150 rows, CK2 id → CK3 id with a `status`: 142 dedupes (`exact`/`exact_id`/`approx`/`nearest`, the CK2 trait does **not** exist), 7 `drop` rows (blank `ck3_trait`) and 1 `sexuality` row (`ck3_trait` holds the sexuality value). All rows apply the same way to `mappings/trait_id_map.csv` consumers **except** `drop`/`sexuality`, which have no trait id to remap onto |
| `mappings/loc_key_renames_traits.csv` | 1084 rows, CK2 loc key → CK3 loc key, for `loc` |
| `docs/evidence/traits_unported.csv` | 867 rows with the reason |
| `docs/evidence/traits_groups.csv` | the 69 `group`/`level` assignments |
| `docs/evidence/tiger_traits.txt` | the ck3-tiger report |

**Trait ids are the CK2 ids verbatim.** Nothing is prefixed, so `has_trait =
creature_elf` in a ported event still resolves and the localisation lane only
has to rename the *key*. Only generated `group = ` names carry `fae_`, because
CK3 already uses `kinslayer`, `wounded`, `beauty_good` as group names
(`game/common/traits/00_traits.txt`).

## Rules

### 1. Map to the existing CK3 trait — never port a new CK2-named one
**The policy (`docs/DECISIONS.md` 2026-09-08, second entry, superseding the
first the same day): a CK2 trait CK3 removed is mapped to an EXISTING CK3
trait, never ported as a new trait and never silently dropped.** The user's
correction: the first 2026-09-08 policy ("replace, never drop") still let a
CK2 player see `cruel`, `envious`, … in the converted mod's trait list, which
was not the point — the *concept* must survive, under a CK3 id the game
already knows. A CK2 trait CK3 genuinely has is still never redefined
(redefining it would replace vanilla behaviour). Two sources of evidence, in
this order:

* `mappings/vanilla_traits.csv` (the 112 traits of CK2 `00_traits.txt`), whose
  `status` column is an *action*:

  | status | count | what the step does |
  |---|---|---|
  | `exact` | 83 | same concept, CK3 already has it: **dedupe** to the CK3 id, do not redefine. 39 of the 83 share the CK2 id verbatim |
  | `approx` | 16 | same concept, CK3's id/wording differs: **dedupe exactly like `exact`** — no CK2 trait definition is emitted, a character gets the CK3 id. The pair is still recorded in `mappings/trait_id_map.csv` with `status = approx` so the events lane can rewrite a `trait = <ck2 id>` reference |
  | `nearest` | 5 | no real CK3 counterpart, but one CK3 trait covers the same gameplay niche well enough: **dedupe to it**, same as `approx` |
  | `sexuality` | 1 | not a trait in CK3 at all: the character gets `sexuality = <ck3_trait>` in its history instead of a trait (rule 2) |
  | `drop` | 7 | no CK3 landing place, not even a near miss: the character loses it, with a `# CK2 trait x: no CK3 counterpart` comment (rule 2) |

  A row whose two ids are equal is `exact` by definition. No status here ever
  results in a new CK2-named trait definition — `ck2ck3.traits.port.Plan.classify_vanilla`
  raises on any other status, so a future typo fails loudly instead of quietly
  porting a trait (`tests/test_traits.py::test_an_unknown_vanilla_status_raises`).

  The 21 `approx`/`nearest` pairs: `aggressive_leader ~ aggressive_attacker`,
  `charitable ~ generous`, `cruel ~ sadistic`,
  `defensive_leader ~ unyielding_defender`, `duelist ~ lifestyle_blademaster`,
  `falconer ~ lifestyle_hunter`, `flanker ~ flexible_leader`,
  `harelip ~ beauty_bad_1`, `has_tuberculosis ~ consumption`,
  `has_typhoid_fever ~ typhus`, `hedonist ~ lifestyle_reveler`,
  `impaler ~ torturer`, `inspiring_leader ~ gallant`, `kind ~ compassionate`,
  `proud ~ arrogant`, `siege_leader ~ military_engineer`, `slothful ~ lazy`,
  `slow ~ intellect_bad_2`, `syphilitic ~ great_pox`, `trickster ~ strategist`,
  `wroth ~ wrathful`.

  The 7 `drop`: `cavalry_leader`, `crusader`, `envious`, `experimenter`,
  `heavy_infantry_leader`, `light_foot_leader`, `stressed` — CK3 has no
  per-unit commander traits, no envy trait, no stress trait, and no crusader
  fame-marker equivalent close enough to dedupe to (each row's `note` has the
  full rationale). The 1 `sexuality`: `homosexual` (CK3 models orientation as
  a character *sexuality*, not a trait).

  `fair ~ beauty_good_3` stays `exact`, on measured evidence (CK2
  `sex_appeal_opinion 30` = CK3 `attraction_opinion 30`).
* **exact id match** against CK3 1.19 `common/traits/00_traits.txt` for the 213
  Faerûn traits that neither `vanilla_traits.csv` nor
  `docs/evidence/faerun_custom_traits.csv` classifies — CK2-vanilla traits that
  live in `02_traits.txt`, `04_battle_scars_and_tattoos_traits.txt`, … 38 of
  them match (`administrator`, `giant`, `immortal`, `one_eyed`, `scarred`,
  `viking`, …) and are deduped with status `exact_id`; the other 175 are ported.
  An identical trait *id* on both sides is the only machine-checkable evidence
  available, so it is the rule; a rename row records every one for review.

The same guard applies to a trait classified `port`/`race_trait`: if CK3 1.19
declares that id, it is deduped and a warning is logged rather than overriding
vanilla.

### 2. `sexuality` and `drop`: no trait at all
The `characters` port (`ck2ck3.port.characters.CharacterPort._convert_trait_key`)
resolves a `trait = x` line in this order, before falling back to the generic
"not declared" comment:

1. **`sexuality`** (`mappings/vanilla_traits.csv` `status = sexuality`,
   `homosexual` today) — CK3 has no trait for it; verified against vanilla
   `history/characters/persian.txt:5760` (`sexuality = homosexual` sits at the
   same level as `trait = x`). The port emits `sexuality = <value>` instead of
   the `trait` line, counted `traits_sexuality`.
2. **`drop`** (`status = drop`) — no CK3 landing place at all. The port emits
   a `# CK2 trait <id>: no CK3 counterpart` comment and nothing else, counted
   `traits_dropped_no_ck3`. This is a different, more specific comment than
   the generic "the traits step does not declare this trait" one an ordinary
   unknown trait gets.
3. Otherwise the CK2 id is looked up as usual (`Tables.trait`); an unresolved
   id still falls back to the generic comment.

`add_trait`/`remove_trait` (history or `effect` level) are **not** covered by
this special-casing — they still go through the plain rename/comment lookup
(`CharacterPort._shape_trait`), since they are a scripted grant/removal rather
than the character's static trait list the user was looking at.

### 3. A dedupe must not give a character a conflicting pair
Two different CK2 traits can now dedupe to CK3 traits that were never in
conflict as CK2 ids but are as CK3 ones — e.g. a character with both `cruel`
and `kind` (unlikely, but not forbidden in CK2) would get `sadistic` and
`compassionate`, which CK3 declares mutual `opposites`. `ck2ck3.traits.conflicts`
reads CK3's own `opposites`/`group`/`level` fields from
`common/traits/*.txt` of the install named by `configs/faerun.toml`
`ck3_game`, and `CharacterPort._convert_trait_key` checks every accepted
trait against the character's traits so far, in CK2 declaration order:

* the exact same CK3 trait twice (two different CK2 ids deduping to one CK3
  id, or the same CK2 id twice);
* two CK3 traits that name each other in `opposites` (either direction) — a
  bare group name in an `opposites` list (CK3's own convention, e.g.
  `beauty_bad_1` opposes the group token `beauty_good`) matches any trait of
  that group;
* two different `level`s of the same `group` (the `education_*` ladders,
  which rely on `group`/`level` alone with no explicit `opposites` between
  tiers).

The first-held trait (CK2 declaration order) is kept; the later one becomes a
`# CK2: trait = x -> y (conflicts with already-held z; kept the CK2-first-listed
trait)` comment, counted `traits_conflict_dropped`. A full run resolves **6**
conflicts over 18,124 characters (`verified` 2026-09-08): 4 plain duplicates
(a character already listing the same trait, or two CK2 ids deduping to one
CK3 id — `absent`×2, `creature_human`×2, `trickster`+another id both →
`strategist`) and 1 real CK3 `opposites` collision (`legit_bastard` →
`legitimized_bastard` conflicting with an already-held `bastard`, which CK3
lists as its opposite).

### 4. Classification
`docs/evidence/faerun_custom_traits.csv` (from
`scripts/classify_faerun_traits.py`) says `port` (108), `race_trait` (117) or
`comment` (867). `comment` traits are written to
`common/traits/fae_traits_unported.txt` through the writer's comment mode, so
nothing is lost and a submod revives a block by stripping the `# ` prefixes.

### 5. Every key goes through a table
Trait properties through `mappings/trait_fields.csv`, everything else through
`mappings/modifiers.csv` with its `scale`. A key in neither table raises
`UnmappedKey` — coverage cannot silently regress. All 294 keys Faerûn's trait
files use are covered today.

A `none` row becomes a comment line **inside the trait block**:

```
# CK2: morale_offence = 0.2  (no CK3 equivalent: CK3 removed army morale - emit as comment)
```

CK2 comments in the source block are preserved by the parser and carried over.

Non-obvious cases, each driven by the `note` column of the tables:

| CK2 | CK3 | why |
|---|---|---|
| `personality`/`education`/`lifestyle`/`childhood`/`is_health`/`leader` = yes | `category = personality\|education\|lifestyle\|childhood\|health\|commander` | `_traits.info:41-51`. CK3 `category` is **single-valued**; when CK2 sets several, precedence is childhood > education > health > lifestyle > commander > personality and the losers get a comment |
| `hidden = yes` | `shown_in_encyclopedia = no` + `shown_in_ruler_designer = no` | CK3 cannot hide a trait from the character window |
| `customizer = no` | `shown_in_ruler_designer = no` | same key as above — the duplicate is collapsed, first value wins |
| `random = no` | `random_creation_weight = 0` | `_traits.info:111`, weight 0 = never picked |
| `birth = 50` | `birth = 0.5` | CK2 per 10 000, CK3 percent |
| `congenital = yes` | `genetic = yes` | `_traits.info:79` |
| `cannot_marry`/`is_illness`/`is_epidemic`/`vice`/`virtue` | `flag = …` | CK3 has no property; `has_trait_with_flag` reads the flag |
| `command_modifier`/`combat`/`country` blocks | flat trait modifiers | CK3 traits have no such block |
| `province`/`opinions` blocks | comment | a CK3 trait is character scope only |
| `<trait>_opinion` / `opinion_of_<trait>` | `compatibility = { <trait> = X }` | `_traits.info:157`; emitted only when the named trait is one we keep (3 of 78 — the rest name traits that ended up commented), comment always |

### 6. CK2 trigger blocks are commented out
`potential`, `trigger` and `is_visible` map onto CK3 `potential`, but their
*contents* are CK2 trigger script: `religion_group`, `has_landed_title`,
`has_dlc = "Holy Fury"`, CK2 culture names. CK3 knows none of it — ck3-tiger
reported 147 `unknown-field` errors when they were ported verbatim. All 66
blocks are emitted as commented script; translating CK2 triggers belongs to the
events lane.

### 7. Genetic vs inheritance
`_traits.info:107-118` makes two CK3 rules that CK2 does not have:
`birth` needs `genetic = yes`, while `random_creation_weight`, `inherit_chance`
and `both_parent_has_trait_inherit_chance` need `genetic = no`. 125 CK2 keys
break one of them; each is removed **with a comment saying which rule**, after
the race fields are added (a race trait becomes genetic late).

### 8. Group / level heuristic
CK2 has no trait group: a family is expressed by every member listing every
other member in `opposites`. That mutual closure is the only machine-checkable
signal, so the rule is:

1. find **mutual-opposites cliques** of at least three live traits;
2. a clique becomes a group only if it also shows an *ordered family*:
   * every member ends in a distinct `_<n>` → that `n` is the level
     (`pagan_branch_1..4`, `scarred_type_1..10`, `bloodthirsty_gods_1..3`);
   * otherwise every member must share one underscore token, and the level is
     the **CK2 declaration order** — verified ascending in the source for both
     the class ladders (`sorcerer` < `trained_sorcerer` < `journeyman_…` <
     `expert_…` < `master_…` < `renowned_…` < `legendary_…`,
     `character_class_traits.txt:306-…`) and the dragon ages
     (`dragon_wyrmling` < `dragon_young` < `dragon_adult` < `dragon_ancient`,
     `misc_traits.txt:445-495`);
3. group name = the shared token, prefixed `fae_`; if two cliques claim one
   token the second uses its first member's id (keeps the `warlock` class
   ladder apart from `warlock_fey…`).

Cliques with neither signal are alternatives, not tiers, and get no group:
that is what keeps `genius/quick/slow/imbecile`,
`homosexual/bisexual/asexual` and `strong/weak/tough/hardy` out. Pairs are
never groups (`brave`/`craven`).

69 traits in 12 groups: `fae_lifespan` (13), `fae_scarred_type` (10),
`fae_wiz` (8), `fae_sahuagin` (6), `fae_warlock` (5), `fae_freckles` (5),
`fae_dragon` (4), `fae_crowned` (4), `fae_pagan_branch` (4), `fae_baptized`
(4), `fae_creature` (3), `fae_bloodthirsty_gods` (3). The class ladders are
*not* there: `character_class_traits.txt` is classified `comment` in full.

### 9. Race traits (`docs/design_races.md` §2)
Each of the 117 gets `genetic = yes`, `physical = yes`, CK2 `opposites`
preserved (remapped through the dedupe map), and its
`overrides/race_lifespan.csv` row: `immortal = yes` when that row says so
(9 traits — and only when the CK2 block does not already say it), otherwise
`life_expectancy = dnd_max_age - 60` (16 traits). 92 race traits have a row
with a blank lifespan and get none; the step warns for each.

`life_expectancy` is an **additive years** modifier
(`00_traits.txt:6106` `fragile_bones` has `life_expectancy = -3`;
`modifier_definition_formats/00_definitions.txt:919`), so the absolute D&D max
age has to be turned into a delta. **60 = the CK3 base life expectancy is
`assumed`**: CK3 1.19 exposes no define for it, only the "(years)" unit in
`localization/english/modifiers/modifiers_l_english.yml:1158`. Both columns are
in the CSV so a reviewer can change the baseline in one place.

### 10. Icons
CK2 wires a trait icon through an `interface/*.gfx` sprite named
`GFX_trait_<trait>` whose `texturefile` is the real path (`verified`,
`Faerun/Faerun/interface/fr_traits.gfx`) — that sprite table is the source, not
a guessed filename; 1088 sprites, 1066 of them for a Faerûn trait. CK3 instead
reads `gfx/interface/icons/traits/<trait>.dds` (`_traits.info:4`) and vanilla
writes the bare file name (`icon = reveler.dds`, `00_traits.txt:1064`), which is
what the converter emits.

**Size mismatch, logged not fixed:** Faerûn's trait icons are **24×24**
(544 of 546 `.dds`), CK3 1.19's are **120×120** (`brave.dds`, `ambitious.dds`).
They are copied byte for byte and the step warns once; rescaling is the
submod's or the asset library's job, not the converter's.

50 CK2 sprites point at a `.tga`; CK3 reads `.dds` only, so those traits get no
icon and one warning each (3 of them are live traits). 45 more sprites point at
a CK2-vanilla texture the mod does not ship.

## ck3-tiger — `docs/evidence/tiger_traits.txt`

Validated against a throwaway mod folder holding only `common/traits` and
`gfx/interface/icons/traits`, CK3 1.19.0.6:

Re-run `verified` 2026-09-08 after the map-to-existing-trait policy (400 traits):

| | count | who owns it |
|---|---|---|
| `fatal(...)` / `error(...)` | **0** | — |
| `warning(missing-file)` | 229 | missing icon art: ported traits with no CK2 `.dds` (168 of the 400 got one). CK3 looks for the default `gfx/interface/icons/traits/<trait>.dds`. Needs art, not code (was 255 over 429 traits before this lane) |
| `tips(suggest-localization)` | 20 | `TRAIT_FLAG_DESC_<flag>` strings — lane `loc` (was 31) |
| `warning(encoding)` | 0 | fixed since: the writer now BOMs every `common/` file |

Reproduce: run the step into a throwaway folder, drop a two-line
`descriptor.mod` in it and point the validator at it —
`uv run ck2ck3 --config configs/faerun.toml --steps traits --out /tmp/t` then
`scripts/validate_output_mod.sh /tmp/t docs/evidence/tiger_traits.txt`.

Errors that earlier iterations produced and how they were removed: 147
`unknown-field` (CK2 triggers → rule 6), 125 `validation` (genetic rules →
rule 7), 83 `duplicate-field` (→ rule 5), 2 `missing-item` (`has_dlc "Holy
Fury"` → rule 6), 1 `modifiers` (see open question 2).

## Open questions (coordinator)

1. **UTF-8 BOM on script files.** CK3 1.19 ships every `common/` script file
   *with* a BOM (`00_traits.txt`, `_traits.info`, `00_defines.txt` all start
   `ef bb bf`) and ck3-tiger warns "Expected UTF-8 BOM encoding". `CLAUDE.md`
   states the opposite invariant ("UTF-8 for script"), and `OUT_ENCODING` is
   shared by every step including `descriptor.mod` (which EK2 writes without a
   BOM). Left unchanged: it is a converter-wide decision, not a trait one.
2. **`mappings/modifiers.csv:36`** maps CK2 `culture_flex` to
   `cultural_acceptance_gain_mult`, which ck3-tiger says is a *culture*-scope
   modifier and therefore illegal in a trait. The step comments it out via
   `convert.NON_CHARACTER_SCOPE` (one key), but the row should be reclassified
   `none` by the mappings lane, and the rest of `modifiers.csv` re-checked for
   scope the same way.
3. **175 unclassified CK2-vanilla traits are ported by default.** They have no
   row in either classification table (rule 1). Porting is the zero-invention
   choice — dropping is forbidden and commenting needs judgement — but many are
   CK2 subsystem debris (`dead_crown_*` ×13, `bad_priest_*` ×6,
   `baptized_by_*` ×4, `*_terrain_leader` ×6). Should
   `scripts/classify_faerun_traits.py` grow rows for them?
4. **`race_trait` over-reaches.** 25 of the 117 are not races:
   `wiz_abjuration…wiz_transmutation` (8), `warlock_fey…` (5), `origin_*` (6),
   `psi_potential`, `mutant`, `stasis_clone`, `shifter`, `elder_orb`,
   `longevity`. They now get `genetic = yes`/`physical = yes`, which is wrong
   for a wizard school. Fix belongs in the classifier.
5. **Faerûn's 13 `lifespan_<N>` traits all carry CK2 `immortal = yes`** — a CK2
   hack, because CK2 had no lifespan field, driven by events instead. They are
   ported mechanically, so the CK3 mod gets 13 genuinely immortal traits.
   CK3's real `life_expectancy` is the right target (`lifespan_150` →
   `life_expectancy = 90`), but reading intent out of a trait *name* is
   interpretation, so the converter does not. An `overrides/` row per trait
   would settle it.
6. **92 race traits have no lifespan default.** `overrides/race_lifespan.csv`
   is seeded with 25 D&D 3.5e values (open decision 1 of
   `docs/design_races.md`); the rest are blank and the step warns.
7. **Illness health values** (open question 1 of `docs/mapping_modifiers.md`)
   still unresolved: CK2 illness traits reach `health = -7` where CK3's worst
   is `-1`. Scale 1 is applied as the table says.
8. **`fertility`** comes through at CK2 scale: `eunuch` emits
   `fertility = -50.0` where CK3 traits use fractions near ±0.2. Same class of
   problem as 7, same table.
9. **`fae_creature` as a group name** for `creature_illithid` /
   `creature_ulitharid` / `creature_elder_brain` — the shared token rule picked
   `creature`, which reads as if it covered all 117 creature traits. Harmless
   to the engine; rename if it bothers a reader.
10. **ck3-tiger 1.19.0 does not recognise the CK3 `sexuality` character-history
    key** (`error(unknown-field): unknown token 'sexuality'`, 2 blocks shown in
    `docs/evidence/tiger_traits_remap.txt`), even though vanilla itself uses it
    20+ times (`verified`, `game/history/characters/persian.txt:5760`
    `sexuality = homosexual`, at the same block level as `trait = x`; `strings
    ~/.local/bin/ck3-tiger` has no `sexuality` at all). A tiger tool gap
    (`assumed`, its known-fields schema is missing the key), not a converter
    bug — rule 2's output is correct CK3 syntax the engine already accepts
    from its own files.
