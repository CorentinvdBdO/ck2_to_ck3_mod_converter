# Steps `cultures` and `religions`

What the two steps emit, where every value comes from, and every default they
invent. Field tables: `mappings/culture_fields.csv` (53 rows) and
`mappings/religion_fields.csv` (78 rows). Structural background:
`docs/mapping_world.md`. Race model: `docs/design_races.md`.

```sh
uv run ck2ck3 --config configs/faerun.toml --steps cultures,religions
uv run scripts/survey_cultures_religions.py        # the CK2/CK3 facts below
uv run scripts/seed_culture_overrides.py           # first draft of overrides/*.csv
uv run scripts/export_opinion_modifier_map.py      # tables for the traits + loc lanes
uv run scripts/check_id_collisions.py              # id safety against vanilla
uv run scripts/validate_cultures_religions.py      # ck3-tiger + docs/evidence/
```

## What comes out

| file | count | from |
|---|---|---|
| `common/culture/pillars/fae_heritages.txt` | 67 | one per CK2 culture group |
| `common/culture/pillars/fae_languages.txt` | 67 | one per CK2 culture group |
| `common/culture/cultures/fae_<ck2 file>.txt` | 12 files, 419 cultures | one per CK2 culture |
| `common/culture/name_lists/fae_<ck2 file>.txt` | 12 files, 419 name lists | one per CK2 culture |
| `common/ethnicities/fae_placeholder_ethnicities.txt` | 37 | one per non-human race |
| `common/modifier_definition_formats/fae_culture_opinions.txt` | 417 | `<culture>_opinion` |
| `common/religion/religion_family_types/fae_families.txt` | 15 | one per CK2 religion group |
| `common/religion/religion_types/fae_<group>.txt` | 15 files, 94 faiths | religion + its faiths |
| `common/religion/holy_site_types/fae_holy_sites.txt` | 255 | one per marked county |
| `common/modifier_definition_formats/fae_faith_opinions.txt` | 124 | faith + religion + family |

`common/culture/traditions` is **not** written: see "No generated traditions".

## Facts about the source, `verified` by `scripts/survey_cultures_religions.py`

- 67 culture groups, **419** cultures (`docs/faerun_ck2_survey.md`'s "~495" was
  an upper bound; `mappings/culture_fields.csv` already carried 419).
- A CK2 culture *group* has exactly two real attribute keys: `graphical_cultures`
  (67/67) and `alternate_start` (9/67). **It has no colour**, so the language
  pillar's mandatory `color` is copied from the group's first culture.
- 15 religion groups, **94** religions. `interface_skin = { }`, `color = { }` and
  `male_names = { }` sit at the same brace depth as a religion, so the reader
  identifies a religion positively (`scripture_name` / `evil_god_names` /
  `god_names` / `high_god_name`) rather than by a key blacklist. A culture is
  identified the same way, by `male_names` / `female_names` (419/419).
- Faerûn ships `common/cultures/00_cultures.txt` at **0 bytes**; the reader skips
  empty files.
- 470 `holy_site` marks, **all on `c_*` titles**, exactly 5 per religion. The CK3
  cap of 5 `holy_site =` lines per faith is therefore never hit — the code still
  caps and comments the remainder so an upstream change cannot break the output.
- Faerûn's culture `modifier` key points at `default_culture_modifier` in
  403/406 cases, and `common/static_modifiers.txt:853` defines it **empty**.
- CK2 ships its faith icons as one strip atlas
  (`gfx/interface/religion_icon_strip.dds`) indexed by `icon = <int>`, not as
  per-faith files.
- Faerûn's `christian_opinion`, `muslim_opinion`, `zoroastrian_opinion` and
  `thasmudyan_opinion` name religions the mod never defines (CK2-base leftovers
  plus one typo for `thasmudyanic`).

## Identifiers

| object | id | why |
|---|---|---|
| heritage | `heritage_fae_<group slug>` | `common/culture/pillars` is **additive**, so the id must not collide with vanilla |
| language | `language_fae_<group slug>` | same |
| culture | the CK2 culture id, unchanged | `common/culture/cultures` is a `replace_path`; keeps localisation keys on CK2 names |
| name list | `name_list_fae_<culture>` | additive-safe, and CK2 stores names per culture |
| religion family | `rf_fae_<group slug>` | vanilla shape (`rf_pagan`) |
| religion | `fae_<group slug>_religion` | vanilla shape (`paganism_religion`) |
| faith | the CK2 religion id, unchanged | `religion_types` is a `replace_path` |
| holy site | `fae_hs_<county without `c_`>` | one object per **county**, shared by every faith that marks it: 255 objects for 470 marks, and one loc key per place |
| placeholder ethnicity | `fae_placeholder_<race>` | `common/ethnicities` is additive |

*group slug* strips a trailing `_culture_group` or `_group`
(`dark_elf_group` → `dark_elf`); `verified` unique across all 67 groups.

`scripts/check_id_collisions.py` reports what collides with vanilla and whether
it matters. Two real collisions exist and both are handled:

- Faerûn's `gur` and `mari` cultures share their id with a vanilla CK3 culture.
  Harmless in `common/culture/cultures` (replaced) but **fatal** in
  `common/modifier_definition_formats` (additive), so `gur_opinion` and
  `mari_opinion` are not re-declared; a comment stands in their place.
- Faerûn's `pagan` religion shares its id with the vanilla `pagan` faith.
  Harmless: `religion_types` is replaced.

## Derived culture keys (`assumed`, all overridable)

CK2 supplies nothing for four keys CK3 requires. The table is deterministic; a
row in `overrides/culture_defaults.csv` overrides any of the first three per
culture (a blank cell falls back to the derived value).

| CK3 key | rule | Faerûn effect |
|---|---|---|
| `ethos` | `allow_looting` or `seafarer` → `ethos_bellicose`, else `ethos_communal` | 77 bellicose |
| `martial_custom` | `feminist` → `martial_custom_equal`, else `martial_custom_male_only` | all male_only: `feminist` is a *religion* key in Faerûn, `verified` 0 culture uses |
| `head_determination` | `horde` → `head_determination_herd`, else `head_determination_domain` | all domain: `verified` 0 `horde` uses; the government-derived herd variant belongs to the governments lane |
| `ethnicities` | `overrides/ethnicity_of_culture_group.csv`, weight 10 | human groups → nearest vanilla ethnicity, others → `fae_placeholder_<race>` |

`traditions` is only emitted when a CK2 flag justifies it —
`seafarer` → `tradition_seafaring`, `allow_looting` →
`tradition_practiced_pirates` (97 lines over 419 cultures). Nothing else in a
Faerûn culture maps onto a vanilla tradition, and inventing one is forbidden.

The four gfx axes are a fallback chain: the CK2 culture's own
`graphical_cultures` (or `unit_graphical_cultures` for `unit_gfx`), then its
group's, then the `western_*` default. `overrides/gfx_of_culture_group.csv` maps
the 49 CK2 values that have a real-world CK3 analogue; Faerûn uses **320**
distinct values, and the ~270 fantasy ones (`drowgfx`, `beholdergfx`, …) have no
CK3 counterpart and fall through to the default.

## Name lists

The six `*_name_chance` keys, `founder_named_dynasties`, `grammar_transform` and
`bastard_dynasty_prefix` move onto the name list **verbatim**, including CK2's
`Name_Base` variant syntax.

`male_names` / `female_names` do **not**. A CK3 name-list entry is a
**localisation key**, not a display string: vanilla
`common/culture/name_lists/00_ainu.txt:108` lists `Akarakay Antaaynu …` and
`localization/english/names/character_names_l_english.yml` carries
`Akarakay:0 "Akarakay"`. So `ck2ck3.nametokens` turns every CK2 literal into a
token and the literal becomes the token's localisation, written by the `loc`
step (which owns `localization/`) as
`localization/<lang>/fae_names_l_<lang>.yml` from
`ctx.data["cultures"]["name_loc"]`. On Faerûn: **44,231 tokens**.

The token rules, each one paid for by a boot (`docs/evidence/game_load_2026-09-08.md`):

| rule | why |
|---|---|
| whitespace → `_` | a token may not contain a space; vanilla spells two-word names `Asir_Rera` (`00_ainu.txt:149`). Quoting `"Sergeant Reckless"` instead left the name equivalency table unable to look it up. |
| ASCII-fold, `_` per collision | a loc key must be ASCII (251 `Invalid character in key name`). Vanilla does the same: `BjO_rn`, `AndrE_s`, `A__ke`. |
| a leading non-letter gets the `name_` prefix | **a bare token starting with a digit breaks the CK3 parser for the rest of the file.** Faerûn's `modron` names are serial numbers (`2BD71SF2`); one of them cost the 14 `name_list_*` blocks after it in `fae_monsters.txt`, and then a character of one of those cultures caused an `EXCEPTION_ACCESS_VIOLATION` in `characterhistory.cpp`. |
| one token per literal, run-wide | the same name appears in dozens of cultures; a per-file table would give it different keys. |
| duplicates dropped inside one list | CK2 lists `Beauty` twice for `horse`. |

Two more conversions are not verbatim:

- `from_dynasty_prefix` / `male_patronym` / `female_patronym` are literal strings
  in CK2 and **loc keys** in CK3. The step emits
  `dynnp_fae_<culture>` / `dynnpat_{pre,suf}_fae_<culture>` and keeps the literal
  in a comment; `prefix = yes/no` picks the prefix or suffix key.
- `always_use_patronym = yes` is added whenever a patronym exists: CK3 defaults
  it to **no**, and without it a converted patronym is invisible
  (`docs/mapping_world.md` gotcha 5).

`dynasty_names` **is** filled here, and it is why the `dynasties` step now runs
**before** this one (`src/ck2ck3/steps/__init__.py`). CK2 keeps dynasty names
globally in `common/dynasties`, each block carrying a `culture`; CK3 keeps them
per name list. So the `dynasties` step hands over
`ctx.data["dynasties"]["names_by_culture"]` — CK2 culture → the `dynn_fae_<id>`
loc keys of its dynasties — and each name list takes its own culture's keys,
topped up from the **culture group** when the culture alone has fewer than
`MINIMUM_DYNASTY_NAMES`. That top-up is not an invention: vanilla's own define
says so — `common/defines/00_defines.txt:1145`, "We'll log an error for any
culture with less dynasty names than this. Dynasty names from the culture group
will count". A culture whose whole group has no dynasties gets an empty list and
a comment saying which. On Faerûn: **396 of 419** cultures reach the minimum;
the 23 that do not are the animal and undead cultures (`horse`, `cat`, `bear`,
`lich`, `vampire`, `wraith`, `dracolich`, …), for which CK2 defines no dynasty
anywhere in the group. The step names them in a warning; filling them is human
input, not a derivation.

Without it the game logged `culture_name_lists.cpp:169: Name list
name_list_fae_X has only 0 dynasty names defined, which is less than
MINIMUM_DYNASTY_NAMES` **838 times** — one per name list — which also means CK3
had no name to mint a generated character's dynasty from
(`docs/evidence/game_load_2026-09-08.md`).

`cadet_dynasty_names` stays empty: CK2 has no cadet houses to convert.

## Culture localisation

CK3 asks a culture for **three** keys and CK2 supplies one. Vanilla
`localization/english/culture/cultures_l_english.yml:460-462`:

```
 norse:0 "Norse"
 norse_prefix:0 "Norse"
 norse_collective_noun:0 "Norse"
```

Without the latter two the game logs `culture_template.cpp: Missing
localization for <culture>_prefix` — 832 keys over 416 cultures on Faerûn.
`scripts/export_opinion_modifier_map.py` therefore adds a `copy`-mode row per
culture per suffix to `mappings/loc_key_renames_cultures_religions.csv` (137
rows → 965), which `scripts/build_loc_key_map.py` merges into
`overrides/loc_keys.csv` for the `loc` step to apply.

Nine Faerûn cultures (`cat`, `horse`, `lich`, `mouther`, `red_panda`,
`undead_dwarf`, `undeadgiant`, `vampire`, `wight`) have **no CK2 localisation
row at all**, so there is nothing to copy and CK3 shows the raw id. Open:
whether a title-cased id is an acceptable mechanical fallback or human input.

## Faith doctrines

A faith needs one doctrine from each of **23 mandatory groups** plus three core
tenets. The fallback for all 23 is vanilla `paganism_religion`
(`common/religion/religion_types/00_paganism.txt:1-40`), the safest set for a
polytheistic pantheon. `PAGANISM_DEFAULTS` in the step is that set; a slow test
asserts each id exists and sits in the group it claims.

Doctrines every faith of a group agrees on are emitted **once on the religion**
and inherited; a faith repeats one only where a CK2 flag makes it differ.

CK2 flag → doctrine, one row per branch of `decide_doctrines`:

| CK3 doctrine group | rule |
|---|---|
| `doctrine_theism` | more than one `god_names` entry → `doctrine_polytheist`, else `doctrine_monotheist`. CK3 offers only these two, and the pantheon's own god list is the only mechanical signal |
| `doctrine_gender` | `women_can_take_consorts = yes` **and** `men_can_take_consorts = no` → `female_dominated`; else `feminist = yes` → `equal`; else `male_dominated` |
| `doctrine_pluralism` | `intermarry` crosses the group → `pluralistic`; only inside the group → `righteous`; no `intermarry` → `fundamentalist` |
| `doctrine_head_of_faith` | `can_excommunicate = yes` → `doctrine_temporal_head`, else `doctrine_no_head`. **Not** `doctrine_spiritual_head`: that additionally requires `religious_head = <title>`, which only the titles lane can supply |
| `doctrine_marriage_type` | `max_consorts > 0` → `concubines`; `max_wives > 1` → `polygamy`; else `monogamy`. One pick per group, so concubines wins |
| `doctrine_divorce` | `can_grant_divorce = yes` → `approval`; `= no` → `disallowed`; absent → `allowed` |
| `doctrine_consanguinity` | most permissive flag wins: `bs_marriage`/`pc_marriage` → `unrestricted`; `psc_marriage`/`divine_blood` → `dynastic`; `cousin_marriage` → `cousins`; else `restricted` |
| `doctrine_clerical_gender` | `female_temple_holders` yes + `male_temple_holders` not no → `either`; female yes + male no → `female_only`; female no → `male_only` |
| `doctrine_clerical_marriage` | `priests_can_marry` → `allowed` / `disallowed` |
| `doctrine_clerical_succession` | `priests_can_inherit = yes` → `temporal_appointment` (liege picks), `no` → `spiritual_appointment` (head of faith picks). Not an exact concept match: CK2 asks who keeps the holding, CK3 who appoints |
| the other 13 | the `paganism_religion` value |

Extra doctrines outside the mandatory 23:

- `uses_jizya_tax = yes` → `special_doctrine_jizya` (clean 1:1; it is a CK2
  *religion* key, not a government one).
- a `reformed = <x>` pointer → `unreformed_faith_doctrine` on the faith **and**
  `pagan_roots = yes` on its religion (CK3 inverts CK2's direction). 9 Faerûn
  religions point at a reformed version, over 6 groups.
  Such a faith **must** also set `reformed_icon` — `verified`: ck3-tiger reports
  `fatal(field-missing): required field reformed_icon missing` without it. The
  value names a `.dds`, and the only ones that exist are vanilla's 43
  `*_reformed.dds`, so `pagan_reformed` is used until the assets lane slices
  Faerûn's atlas.

### Core tenets

Three per faith. A CK2 flag beats a default, because it is data rather than a
guess; the defaults from `docs/DECISIONS.md` fill the remaining picks:

| CK2 flag | tenet |
|---|---|
| `pacifist` | `tenet_pacifism` |
| `allow_looting` | `tenet_warmonger` |
| `divine_blood` | `tenet_mystical_birthright` |
| `autocephaly` | `tenet_pentarchy` |
| `can_retire_to_monastery` | `tenet_monasticism` |

Defaults, in order: `tenet_ritual_celebrations`, `tenet_sanctity_of_nature`,
`tenet_ancestor_worship`. `overrides/faith_tenets.csv` replaces all three for a
named faith (all three columns must be filled).

## Faith localisation

`localization` is inherited **faith ← religion**, and a key missing from the
whole chain is a runtime localisation error. So:

1. Each religion carries the **complete 128-key block of vanilla
   `paganism_religion`**, read live from the CK3 install at run time rather than
   transcribed, so it cannot drift from the installed version. Every value is a
   real vanilla loc key, so no key is ever unresolved.
2. Each faith overrides only the keys CK2 supplies. Pronoun keys
   (`*SheHe`, `*HerHis`, `HighGodHerselfHimself`) are **never** overridden: CK2
   records no deity gender, so inventing one is out of scope and the inherited
   vanilla value stands.

CK2 stores one key where CK3 wants a family of them, so the extra shapes are
requested from the localisation lane through
`mappings/loc_key_renames_cultures_religions.csv` (127 rows):

| CK2 key | CK3 keys it feeds | extra shape requested |
|---|---|---|
| `high_god_name` | `HighGodName`, `HighGodName2`, `HighGodNameAlternate` | `<key>_possessive` for the two possessive keys |
| `god_names` | `GoodGodNames` (a list) | — |
| `evil_god_names` | `EvilGodNames`, `DevilName` (first entry) | `<first>_possessive` |
| `scripture_name` | `ReligiousText`, `…2`, `…3` | — |
| `priest_title` | 6 `Priest*` + 6 `Bishop*` + `AltPriestTermPlural` | `<key>_plural` |
| `crusade_name` | `GHWName` | `<key>_plural` |

Faith, religion, family and holy-site base keys (`<faith_id>`, `_adj`,
`_adherent`, `_adherent_plural`, `_desc`, `holy_site_<id>_name`) keep the CK2
names, so nothing renames and they are not in the file.

## Opinion modifier formats

CK3 generates a `<x>_opinion` modifier per culture, faith, religion and family,
but each still needs a **format declaration** or its tooltip is unformatted.
Shape from vanilla `00_culture_definitions.txt:1`: `akan_opinion = { decimals = 0 }`.

`mappings/opinion_modifier_map.csv` (161 rows) resolves the placeholder rows of
`mappings/modifiers.csv` for the traits lane:

- CK2 `<religion>_opinion` → `<faith>_opinion`, exact.
- CK2 `<religion_group>_opinion` → `<religion>_opinion`; the sibling
  `rf_fae_<group>_opinion` is named in the note.
- CK2 `<culture>_opinion` → `<culture>_opinion`, exact.
- CK2 `<culture_group>_opinion` → **one row per culture of the group**. CK3 has
  no culture-group opinion scope (`verified`: 0 `heritage_*_opinion` keys exist
  in 1.19), so the single CK2 line fans out.
- The four dangling CK2 keys get a `none` row with the reason.

## No generated traditions

`mappings/culture_fields.csv` notes that a CK2 culture `modifier` is a *province*
modifier whose only CK3 home is a generated tradition. This step generates none,
because there is nothing to generate: `default_culture_modifier` is **empty**
(403 of 406 users), and the other two — `monster_culture_modifier`
(`levy_size`/`local_tax_modifier`) and `lythari_culture_modifier`
(`elven_pantheon_opinion = 20`) — cover 3 cultures. All three are emitted as
comments. `common/culture/traditions` is left to whichever lane needs it.

Likewise `character_modifier` on a culture is **not** emitted: `_cultures.info`
documents it, but `verified` ck3-tiger rejects it (`unknown field
character_modifier`) and 0/244 vanilla cultures use it. Faerûn's 9 uses (all in
`99_animals.txt`) become comments.

## Things this step deliberately does not own

| thing | owner | why |
|---|---|---|
| a per-group hostility doctrine from `hostile_within_group` | `common/religion/doctrine_types` | not in this step's `OUTPUTS`; all 15 families use the vanilla `pagan_hostility_doctrine` and the CK2 flag is a comment |
| carrier doctrines for CK2 `character_modifier` / `unit_modifier` on a religion (62 + 22 uses) | `doctrine_types` | same; emitted as comments |
| `religious_head = <title>` and therefore `doctrine_spiritual_head` | titles lane | needs `controls_religion` / `caliphate` titles |
| cultural title names, flavorization (`dukes_called_kings`, `tribal_name`) | titles lane | `common/flavorization` |
| `dynasty_names` on the name lists | characters lane | needs the dynasty→culture grouping |
| faith icons, real race ethnicities | assets lane | CK2's atlas must be sliced; no licensed race art exists |
| every `.yml` | localisation lane | this lane writes **no** localisation, only the rename rows above |

## Validation

`docs/evidence/tiger_cultures_religions.txt`, regenerated by
`uv run scripts/validate_cultures_religions.py`. Current result (`verified`,
ck3-tiger 1.19.0 against CK3 1.19.0.6):

```
fatal: 0, error: 255, warning: 94, untidy: 0, tips: 0
```

- **255 errors**, all `title c_<county> not defined in common/landed_titles/` —
  the counties the CK2 holy sites sit on. The titles lane generates them with
  their CK2 ids, so they resolve once it lands.
- **93 warnings**, all `gfx/interface/icons/faith/<faith>.dds does not exist` —
  tiger infers an icon path from the faith id when no `icon` is set. CK2 has only
  the strip atlas, so this is image work; visible-but-non-fatal in game.
- **1 warning** `Expected UTF-8 BOM encoding`, covering all 46 generated files.
  `pdx.encoding.OUT_ENCODING` writes plain UTF-8 for script, while tiger and
  vanilla want a BOM on script files too. That is a converter-wide writer
  setting owned by the foundation lane — **for the coordinator to decide**, not
  something this step can fix without changing every other lane's output.
