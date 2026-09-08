# CK2 → CK3 mapping tables: modifiers, trait fields, vanilla traits

Machine-readable output of the `mappings` lane. The trait, character and building
lanes read these CSVs; nothing here is design — every row is either a key that
exists on both sides, or a `none` row saying what comment to emit.

| file | rows | what it maps |
|---|---|---|
| `mappings/modifiers.csv` | 296 | every modifier key the Faerûn CK2 mod uses in `common/traits/` or `common/buildings/` → CK3 modifier key |
| `mappings/trait_fields.csv` | 88 | CK2 trait-block property → CK3 trait property |
| `mappings/vanilla_traits.csv` | 112 | CK2 `common/traits/00_traits.txt` trait → CK3 `common/traits/00_traits.txt` trait |
| `docs/evidence/faerun_custom_traits.csv` | 1092 | Faerûn-specific traits classified by file of origin |

Status counts (`verified`, from the generators):

- `modifiers.csv` — exact 33, approx 122, none 141
- `trait_fields.csv` — exact 36, approx 17, none 35
- `vanilla_traits.csv` — exact 83, approx 16, none 13 (2026-09-08: 6 `approx`
  rows were re-read and downgraded, see `docs/step_traits.md` rule 1). The
  three statuses now mean three *actions*, not three confidence levels:
  `exact` dedupes, `approx` ports **and** records the CK3 near-equivalent,
  `none` ports. The file's own header states it.
- `faerun_custom_traits.csv` — port 108, race_trait 117, comment 867

## Method

Run order (all stdlib-only, no network):

```
uv run scripts/collect_ck2_modifier_keys.py   # -> docs/evidence/ck2_modifier_keys.csv
uv run scripts/build_modifiers_csv.py         # -> mappings/modifiers.csv
uv run scripts/classify_faerun_traits.py      # -> docs/evidence/faerun_custom_traits.csv
uv run scripts/verify_ck3_keys.py             # -> docs/evidence/verify_ck3_keys.txt
```

- `collect_ck2_modifier_keys.py` tokenises the Faerûn files (Windows-1252, `#`
  comments stripped) and walks the block tree. In a trait file a modifier is a
  leaf at depth 1 (inside the trait block) or inside `command_modifier`; in a
  building file it is a leaf at depth 2 (holding → building → key). Leaves whose
  key is a known trait/building *property* are filtered out — the CK2 property
  list is the "variables" section of the CK2 install's
  `common/traits/traits.info`. Result: **295 distinct modifier keys, 4690
  occurrences** (`verified`).
- `build_modifiers_csv.py` holds the hand-derived table plus family rules. The
  dynamic CK2 opinion families are resolved by looking the key stem up in the
  Faerûn culture / culture-group / religion / religion-group / trait name sets
  parsed straight out of `Faerun/Faerun/common/{cultures,religions,traits}`, so
  new Faerûn content is classified without a new table row. The script fails if
  any collected key is unmapped, so the CSV can never silently lose coverage.
- `verify_ck3_keys.py` checks every non-`none` CK3 key against the CK3 1.19
  install. **0 misses** (`verified`, `docs/evidence/verify_ck3_keys.txt`). Of the
  95 verified modifier keys, 91 are declared in
  `game/common/modifier_definition_formats/` and 4 (`health`, `same_opinion`,
  `opposite_opinion`, `same_opinion_if_same_faith`) exist only as usage — they
  are engine-core modifiers and trait properties that need no declaration.

## CK3 modifier grammar — where a modifier may be written

`verified` from the CK3 1.19 install.

### In a trait

A CK3 trait block is **character scope only**. Everything the engine does not
recognise as a trait property is read as a character modifier
(`game/common/traits/_traits.info:247`: *"Any other unknown property is read in
as a modifier applied to anyone who holds the trait"*). There are exactly three
nested places a modifier may go:

- `culture_modifier = { parameter = <culture param> … }` (`_traits.info:236`)
- `faith_modifier = { parameter = <doctrine param> … }` (`_traits.info:242`)
- `tracks = { <track> = { <xp> = { … } } }` / `track = { … }` (`_traits.info:193`)

County- and holding-scoped keys **can** appear in a trait, but only through
`culture_modifier`: vanilla `brave` writes `county_opinion_add = 10` inside
`culture_modifier = { parameter = trait_county_opinion_modifiers … }`
(`game/common/traits/00_traits.txt:3272-3275`). There is no way to attach a
province modifier to a trait.

Consequence for the converter: a CK2 trait carrying `tax_income`, `levy_size`,
`garrison_size` or `fort_level` has no CK3 landing place inside the trait — those
rows are marked for the building lane, not the trait lane.

### In a building

`game/common/buildings/_buildings.info` lists the modifier collections, and each
one fixes the scope of the keys inside it (`verified`, line numbers in that file):

| block | scope | line |
|---|---|---|
| `character_modifier` | holding owner | 152 |
| `character_culture_modifier` / `character_faith_modifier` | owner, gated on a parameter | 157 / 161 |
| `province_modifier` | the province (holding) | 174 |
| `province_culture_modifier` / `province_faith_modifier` / `province_terrain_modifier` | province, gated | 180 / 187 / 194 |
| `county_modifier` | the whole county, stacking across its provinces | 217 |
| `county_holding_modifier = { holding = castle_holding … }` | one holding type in the county | 284 |
| `county_holder_character_modifier` | the county holder | 298 |
| `duchy_capital_county_modifier` | every de jure county of the duchy (duchy-capital buildings only) | 237 |

Flat building fields, not modifiers: `levy` (int), `max_garrison` (int),
`garrison_reinforcement_factor`, `construction_time`, `cost`/`cost_gold`
(`_buildings.info:10-26`, `cost` at 139). So CK2 `levy_size = 0.025` has two possible CK3
targets — the flat `levy` field or `province_modifier = { levy_size = 0.025 }`;
the mapping keeps the modifier form because the CK2 value is a fraction.
Worked example: `barracks_01` uses `cost_gold`, `levy`, `province_modifier`,
`character_culture_modifier`, `county_culture_modifier` and
`province_culture_modifier` in one block
(`game/common/buildings/00_standard_military_buildings.txt:4107-4148`).

### Dynamic modifier keys must be declared

CK2 declares custom modifiers in `common/modifier_definitions/` (Faerûn declares
512 of them). CK3 does the same in `common/modifier_definition_formats/`: every
`<culture>_opinion` (`00_culture_definitions.txt`), `<faith>_opinion` and
`<religion>_religion_opinion` (`00_religion_definitions.txt`) exists only because
it is listed there. 1950 keys are declared in vanilla 1.19 (`verified`).
Two consequences:

- 60 of the 295 Faerûn keys map to a **placeholder** (`<ck3_culture>_opinion`,
  `<ck3_faith>_opinion`, `<ck3_religion>_religion_opinion`). They resolve only
  once the cultures/religions lane produces its name map, and the converter must
  then also emit the matching `modifier_definition_formats` file.
- CK3 has no culture-*group* opinion scope. CK2 `dwarf_group_opinion` has to
  fan out to one `<culture>_opinion` per CK3 culture in that group.

## Scale derivations

`scale` is the multiplier to apply to the CK2 value. Every number below comes
from comparing the *same* vanilla trait on both sides — CK2
`common/traits/00_traits.txt` vs CK3 `game/common/traits/00_traits.txt`.

| family | scale | derivation |
|---|---|---|
| attributes (`diplomacy` … `learning`) | **1** | `genius` +5/+5/+5/+5/+5 (CK2:949) = `intellect_good_3` +5 ×5 (CK3:7364). `quick` +3 (CK2:980) = `intellect_good_2` +3 (CK3:7306). `imbecile` −8 (CK2:1025) = `intellect_bad_3` −8 (CK3:7200). `brave` martial 2 (CK2:1727) = `brave` martial 2 (CK3:3264). |
| `health` | **1** | `strong` 1 (CK2:1082) = `physique_good_3` 1 (CK3:7649); `weak` −1 (CK2:1101) = `physique_bad_3` −1 (CK3:7507). Outlier: `ill` −2 (CK2:382) vs −1 (CK3:5364) — CK3 rebalanced illness, so illness values need capping. |
| `fertility` | **1** | additive fraction on a base on both sides; CK2 trait p90 0.2, CK3 trait p90 0.2. |
| `sex_appeal_opinion` → `attraction_opinion` | **1** | `fair` 30 (CK2:884) = `beauty_good_3` 30 (CK3:7053); `ugly` −20 (CK2:902) = `beauty_bad_2` −20 (CK3:6876); `weak` −10 (CK2:1107) = `physique_bad_3` −10 (CK3:7510). |
| opinion families (`vassal_opinion`, `same_opinion`, `general_opinion`, …) | **1** | both engines use −100…100 opinion points. CK3 vanilla is roughly 2× more generous (`brave` same_opinion 5 → 10) but that is balance, not units, so the converter stays 1:1. |
| `monthly_character_prestige` → `monthly_prestige` | **1** | same units; CK2 trait absmax 2.0, CK3 trait absmax 2.0. |
| `monthly_character_piety` → `monthly_piety` | **1** | same units; CK2 absmax 1.0, CK3 absmax 2.0. |
| `combat_rating` → `prowess` | **0.1** | CK2 2.x multiplied combat_rating by 10 — the vanilla file still carries the old value in a comment (`combat_rating = 10 #old value: 1`, CK2:1728). Faerûn's range is [−100, 60] (absmax 100); CK3 trait `prowess` runs [−10, 8] (absmax 10). ÷10 maps one range onto the other exactly. Applies to `hidden_combat_rating` → `prowess_no_portrait` too. |
| `demesne_size` → `domain_limit` | **1** | whole holdings on both sides; CK2 traits use 1…3, CK3 traits −1…3. |
| `birth` (trait property) | **0.01** | CK2 `birth` is per 10 000 (`traits.info` header); CK3 `birth` is a percent out of 100 (`_traits.info:107`). |
| `global_revolt_risk` / `local_revolt_risk` → `county_opinion_add` | **−100** | CK2 revolt risk is a 0…1 fraction and *lower is better*; CK3 expresses the same unrest as county opinion on −100…100 where *higher is better*, so the value is ×100 and the sign flips. Faerûn only ever uses −0.05…−0.15, i.e. +5…+15 county opinion. |
| `siege` / `siege_speed` → `siege_phase_time` | **−1** | CK2 positive = faster siege; CK3 `siege_phase_time` is a *time* modifier, lower = faster. |
| `plot_power_modifier` family → `*_scheme_success_chance_add` | **100** (defensive: **−100**) | CK2 is a fraction of plot power; CK3 takes percentage points of success chance. The defensive row flips sign because CK3 expresses it as the *enemy's* success chance. |
| `build_time_modifier` → `holding_build_speed` | **1** | CK3's key carries `MOD_TIME_PREFIX` with `color = bad` (`00_holding_definitions.txt:1-6`), i.e. it is a build-*time* modifier where negative = faster — the same sign convention as CK2. |
| `days_of_supply` → `supply_duration` | see note | CK2 counts days, CK3 counts months; divide by 30. Left in the note, not the scale column, because it is a unit change rather than a range rescale. |

## Notable non-mappings

The 140 `none` rows fall into six groups (`verified` from the CSV notes):

1. **78 rows** — CK2 `<trait>_opinion` / `opinion_of_<trait>` (mostly Faerûn god
   patrons). CK3 has no per-trait opinion modifier; the replacement is a
   `compatibility = { <trait> = X }` entry inside the trait block
   (`_traits.info:157`).
2. **31 rows** — Faerûn `text_effect_*`, `trait_effect_*`, `tolerates_*`: custom
   modifiers declared purely so a value shows in the UI and can be read back by
   triggers. CK3 has no display-only modifier.
3. Army morale (`morale_offence`, `morale_defence`, `land_morale`) and battle
   position (`flank`, `narrow_flank`, `center`) — CK3 removed both systems.
4. Special units Faerûn invented (`giant_troops`, `undead_troops`, `mob_troops`)
   — each needs a new CK3 `men_at_arms_type`, which is design, not conversion.
5. Republic/nomad/offmap subsystems (`max_tradeposts`, `monthly_grace`,
   `ai_republic_modifier`, `convert_to_castle`) — no CK3 counterpart.
6. Naval (`galleys`) — CK3 has no navy.

## Open questions

1. **Illness health values.** CK2 illness traits go to `health_penalty = -7`
   while CK3's worst illness is `health = -1`. Scale 1 is right for congenital
   traits but wrong for disease. Cap, or an `overrides/` row per illness trait?
2. **CK2 `is_health` vs CK3 `category`.** CK3 `category` is single-valued, so a
   Faerûn trait that is both `is_health = yes` and `personality = yes` cannot
   keep both. Which wins?
3. **`caste_tier`.** Faerûn reuses the CK2 Indian caste tier as a race tier on
   728 trait blocks. Classified `none` here; the races lane has to decide whether
   it becomes a CK3 `group`/`level` pair or is dropped.
4. **Culture-group fan-out.** 20 keys are `<culture_group>_opinion`. Emitting one
   `<culture>_opinion` per member culture multiplies trait size; is a single
   heritage-level opinion (via `culture_modifier` + a heritage parameter)
   acceptable instead?
5. **Education tiers.** CK2 has 4 education tiers, CK3 has 5. The mapping uses
   1→1 … 4→4 and leaves tier 5 unused. Should the top CK2 tier map to 5 instead?
6. **`fair` tier choice.** `fair` matches `beauty_good_3` on attraction (30 = 30)
   but `beauty_good_1` on diplomacy (1 = 1). The table follows attraction because
   it is the defining stat of the beauty family; flag if the trait lane disagrees.

## Evidence files

- `docs/evidence/ck2_modifier_keys.csv` — the 295 collected keys with counts, source files and sample values
- `docs/evidence/faerun_custom_traits.csv` — 1092 Faerûn-specific traits by source file
- `docs/evidence/verify_ck3_keys.txt` — verifier output, 0 misses
- `docs/evidence/wiki_ck3_modifier_list.txt` — https://ck3.paradoxwikis.com/Modifier_list (archive.org snapshot; the live site bot-blocks curl)
- `docs/evidence/wiki_ck3_trait_modding.txt` — https://ck3.paradoxwikis.com/Trait_modding (archive.org snapshot)

The wiki pages were used only as a cross-check; every `exact`/`approx` key in the
CSVs is verified against the local CK3 1.19 install, not against the wiki.
