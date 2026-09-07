# CK2 and CK3 character / dynasty formats

Facts, each with file:line evidence from `Faerun/Faerun/` (CK2) or the CK3
1.19.0.6 install (`common/`, `history/`). Everything here is `verified` by
reading the file named, or by `ck3-tiger` accepting the output, unless the line
says `assumed`.

Companion: `docs/step_characters.md` (what the steps do), `mappings/character_effects.csv`
(the per-key decisions), `mappings/death_reasons.csv`, `mappings/nicknames.csv`.

## 1. Volume (Faerûn, `verified` by `scripts/survey_characters.py`)

| thing | count |
|---|---|
| characters | 18124 in 80 files (`history/characters/<id range> <region>.txt`) |
| dated blocks inside them | 47107 |
| distinct traits used | 634 |
| distinct CK2 history keys | 40 |
| distinct CK2 effect tokens | 63 |
| dynasties | 11952 in 3 files (11951 distinct ids) |
| dynasty coats of arms | 20 |

Full key tally with sample values: `docs/evidence/characters_key_tally.csv`.

## 2. Ids

- CK3 character and dynasty ids may be **strings**. `verified`: 33104 of 71124
  vanilla history ids are non-numeric (`sephardi_0001`, `bai_yang_2_1`), and
  Elder Kings 2 uses string ids for all 16515 of its characters.
- Vanilla numeric ids reach 1000230517, so a numeric range is not safe to
  squat. Converted ids are `fae_<ck2_id>` (`docs/DECISIONS.md`).
- `history/characters/*.txt` `killer` takes a **bare id**, not a `character:`
  scope — `verified` `history/characters/bai.txt:1395` (`killer = bai_yang_2_1`)
  and 20 uses of `killer = japanese_taira_kanmu_34`.
- **GOTCHA**: Faerûn defines dynasty `15817` **twice** in
  `common/dynasties/Faerun_Dynasties.txt` ("Zyxenel", then "Phaethoxoris").
  CK2 lets the last definition win. CK3 loads both and `ck3-tiger` reports
  `duplicate-item`. The converter keeps both blocks (it never invents a
  resolution) and warns; a human must delete one.

### Four keys behave differently inside a dated block

`verified` by ck3-tiger against the generated output:

| key | in a character block | in a dated block |
|---|---|---|
| `father` / `mother` | history key | **`structure` error** ("expected block, found value"); use `effect = { set_father = character:<id> }` |
| `fertility` | history key | **`wrong-use` error**: "`fertility` is a trigger and can't be used as an effect" |
| `health` | history key | same as `fertility` (`assumed`: 0 dated uses in Faerûn to test with) |

Faerûn has one dated `father`, one dated `mother` and one dated `fertility`,
so this is three characters — but it is three load errors, and nothing in the
`.info` file says so.

## 3. Keys CK3 accepts in `history/characters`

`history/_characters.info` (note: at the *root* of `history/`, not inside
`history/characters/`) lists: `name dna female martial prowess diplomacy
intrigue stewardship learning trait father mother disallow_random_traits faith
culture dynasty dynasty_house give_nickname sexuality health fertility set_house
set_culture set_character_faith_no_effect add_spouse add_matrilineal_spouse
add_same_sex_spouse portrait_override`.

The `.info` is not exhaustive. Also live in vanilla history: `religion`
(69× more common than `faith`), `capital`, `employer`, `remove_spouse`,
`add_concubine`, `add_trait`, `remove_trait`, `birth`, `death`, `effect`,
`real_father`.

- `prowess` is CK3's sixth attribute; Faerûn never sets `combat_rating`, so
  there is nothing to derive it from (`verified`: 0 uses).
- `death` takes `yes`, a quoted date, or
  `{ death_reason = x killer = y }` — `verified`
  `history/characters/afghan.txt:341-344`.

## 4. Effects, and the ones that do not exist

Verified by grepping `common/effect_localization/*.txt` (983 effect names) and,
for effects that have no loc entry, the game's own `events/`, `common/` and
`history/` scripts.

| CK2 | CK3 | evidence |
|---|---|---|
| `add_friend` | `set_relation_friend = { reason = <r> target = character:<id> }` | 60 block-form uses in `history/characters/`; `saka.txt` |
| `add_rival` | `set_relation_rival` (71 uses) | same |
| `add_lover` | `set_relation_lover` (17 uses) | same |
| `remove_friend/rival/lover` | `remove_relation_friend/rival/lover` | `effect_localization` |
| `set_character_flag` | `add_character_flag` (6221 uses) | takes a bare flag or `{ flag = x days = n }` |
| `clr_character_flag` | `remove_character_flag` (2389 uses) | — |
| `set_name` | `change_first_name` | **`set_name` does not exist in CK3** (0 uses) |
| `add_claim` | `add_pressed_claim = title:<id>` | 602 `add_pressed_claim` / 12 `add_unpressed_claim` uses |
| `add_consort` | `add_concubine` (54 uses) | needs `doctrine_concubines` |
| `immortal_age` | `set_immortal_age` | `common/effect_localization/00_additional_effects.txt`; `common/traits/_traits.info:99` |
| `add_character_modifier = { name duration }` | `add_character_modifier = { modifier years }` | `history/characters/` (`confederate_king_modifier`, `years = 5`) |
| `wealth` / `prestige` | `add_gold` / `add_prestige` (delta, not absolute) | — |

Relation `reason` values that exist as loc keys
(`localization/english/relationship_reasons_l_english.yml`, `verified`):
`friend_generic_history` (50 uses), `friend_historical`, `rival_historical`
(58 uses), `lover_history` (16 uses).

### `effect_even_if_dead` does not exist in CK3

**GOTCHA**: Faerûn uses `effect_even_if_dead = { ... }` 407 times (liches,
deities, dragons). Grepping the whole 1.19 install returns **0** occurrences.
It is ported as a plain `effect = { ... }` with a comment saying so. Whether
CK3 runs history effects on an already-dead character is `assumed` untested.

### Effects with no CK3 counterpart at all

`join_society` / `leave_society` / `society_rank_up` / `set_society_grandmaster`
(no societies), `create_bloodline` / `add_bloodline_member` (no bloodlines),
`spawn_unit` / `spawn_fleet` / `disband_event_forces`, `set_graphical_culture`,
`give_minor_title` / `give_job_title` / `set_special_character_title`,
`set_reincarnation`, `add_ambition`, `set_gender`, `set_dynasty_name`,
`secret_religion` / `set_secret_religion`, `imprison` / `banish` / `prisoner`
(CK3 wants `{ target imprisoner }`, which CK2 history does not supply),
`opinion` (needs a target scope), `add_artifact` / `new_artifact` (CK3 artifacts
are their own `history/artifacts` database).

CK2 scope changes inside an effect (`c_bloodstone = { ROOT = { capital = PREV } }`,
`e_tan_shou_lung = { set_title_flag = ... }`) are commented: a CK3 history
effect runs in the character's scope and cannot switch to a title.

## 5. Death reasons

- CK3 1.19 defines **313** ids across `common/deathreasons/00_natural_deaths.txt`,
  `00_event_deaths.txt`, `00_activity_deaths.txt`.
- Faerûn defines **181** in `common/death/` (`00_death.txt`, `fr_death.txt`,
  `shou_lung_death.txt`) and uses **80** of them.
- Only **8** of the 80 used ids exist verbatim in CK3, so a value table is
  mandatory: `mappings/death_reasons.csv` maps all 181 (74 `exact`, 78
  `approx`, 29 `fallback`). `scripts/verify_character_tables.py` proves every
  target exists in the install (`MISSES: 0`).
- CK3 has **no** death reason for cold/freezing accidents beyond `death_froze`
  and `death_hypothermia`, none for flaying, impaling, stoning, magic, dragons
  or volcanoes. Those become the nearest generic plus a comment.
- Unknown reason → `death_natural_causes` and a run-log warning.

## 6. Nicknames

- CK3 defines **683** ids in `common/nicknames/`; Faerûn defines **2314** and
  uses **837** on characters.
- Only **80** match verbatim, plus one semantic match
  (`nick_dragonslayer` → `nick_the_dragonslayer`). The other 756 are
  Faerûn-invented and become comments: `mappings/nicknames.csv`.
- **The cheap win**: those 756 are already defined in Faerûn's own
  `common/nicknames/`, whose CK2 shape (`nick_x = { ... }` with a loc key) is
  close to CK3's. A `nicknames` step porting that folder would recover the 821
  of 1040 `give_nickname` uses that are currently commented out. No lane owns `common/nicknames` yet.

## 7. Dynasties

- CK3 `common/dynasties` takes `name`, optional `prefix`, `culture`, optional
  `motto`. `name` is a **localisation key**, not a literal —
  `verified` `common/dynasties/00_dynasties.txt:4` (`name = "dynn_Orsini"`).
  CK2 stores the literal, so the converter emits `dynn_fae_<id>` and writes the
  literal to `localization/english/fae_dynasties_l_english.yml`.
- CK3 dynasties have **no** `religion` field (only `forced_coa_religiongroup`,
  which picks a CoA style). Faerûn sets `religion` on 4 dynasties; dropped.
- `used_for_random` (754 uses) has no CK3 counterpart: no random world.
- CK2 `coat_of_arms` blocks are numeric indices into CK2's own flag atlas
  (`template = 0`, `texture = 10`, `emblem = 0`) and carry no colour or shape
  information a CK3 `pattern` / `colored_emblem` could use. Emitted as a
  comment; the 20 blocks are kept verbatim in
  `docs/evidence/dynasty_coa_dropped.csv`.
- **GOTCHA**: Faerûn dynasty 644 has a `culture` but no `name`. CK3 needs a
  name; the converter warns instead of inventing one.

## 8. Localisation keys are hashed — collisions silently lose

**GOTCHA, and the one that cost this lane the most time.** CK3 stores
localisation in a hash table keyed by **MurmurHash3 x86_32 (MURMUR3A), seed 0**,
of the key name. Two keys with the same hash collide and one of them fails to
load. `ck3-tiger` reports it as `localization-key-collision`.

11951 mechanically generated `dynn_fae_<id>` keys hit two vanilla keys on the
first run (`verified` 2026-09-07):

| generated key | vanilla key | hash |
|---|---|---|
| `dynn_fae_109` | `Burnon` (`localization/english/names/character_names_l_english.yml:3677`) | `0x57BC1D19` |
| `dynn_fae_1215` | `b_tradruk` (`localization/english/titles_l_english.yml:20921`) | `0x0D6EC7CE` |

So **any lane that mints localisation keys mechanically must check the hash**,
not hope. `ck2ck3.port.loc_hash` implements MURMUR3A (its doctest reproduces
both hashes above) and `resolve_collisions()` appends `_x` until the hash is
free. Vanilla English defines ~289k keys and reading them all takes well under
a second, so the check is cheap. **This helper should be promoted out of
`port/` and used by the `loc` lane too.**

## 9. CK2 file quirks

- Every Faerûn character and dynasty file opens with the bytes `###\xc4NSI`
  ("###ANSI" with a cp1252 A-umlaut) — a CK2 codepage hint. It is dropped, not
  carried into 83 CK3 files as noise.
- CK2 input is Windows-1252; the parser sniffs and warns per file, which is why
  the run log is dominated by `EncodingWarning`. Expected, not a defect.
- `common/dynasties/00_dynasties.txt` and `01_animal_dynasties.txt` contain no
  dynasties at all: they exist only to shadow CK2 vanilla's files. They convert
  to comment-only CK3 files, which is harmless.

## 10. `ck3-tiger` notes

- `--game` wants the **install root** (`.../Crusader Kings III`), not
  `.../game`. Given `.../game` it prints "That does not look like a CK3
  directory", retries the parent and carries on — but scripts should pass the
  root.
- `replace_path = "history"` is **rejected**: "So replace_path = history is not
  useful, you should replace the paths under it." `configs/faerun.toml` lists
  both `history` and `history/characters`; the `history` entry has to go.
  Not this lane's file to change — flagged for the coordinator.
- **ck3-tiger 1.19.0 bug, minimal reproducer**: an *empty string* value makes
  tiger panic with `index out of bounds: the len is 0 but the index is
  18446744073709551615` at `src/trigger.rs:1454` — but only when the mod also
  ships a `localization/` folder (tiger does not reach that analysis pass
  otherwise). The whole reproducer is:

  ```
  # history/characters/x.txt          # plus any localization/english/*.yml
  fae_1 = { name = Test 1300.1.1 = { birth = yes
      effect = { change_first_name = "" } } }
  ```

  Found by `scripts/bisect_tiger_panic.py` (13 tiger runs, 455 blocks → 1;
  trace in `docs/evidence/tiger_bisect.log`). The converter no longer emits it:
  `set_name = ""` (1 use in Faerûn) is commented instead. Worth reporting to
  github.com/amtep/tiger.
- **CK3 script files carry a UTF-8 BOM.** `verified`: vanilla
  `common/dynasties/00_dynasties.txt`, `common/traits/00_traits.txt` and
  `history/characters/norse.txt` all begin `EF BB BF`, and tiger warns
  `warning(encoding): Expected UTF-8 BOM encoding` on the generated
  `common/dynasties/*.txt`. CLAUDE.md's invariant says "UTF-8 with BOM for
  localisation, UTF-8 for script", which is incomplete. Fixing it means
  changing `OUT_ENCODING` in `src/ck2ck3/pdx/encoding.py` — shared code, so
  flagged for the coordinator rather than changed here.
- Faiths are looked up in `common/religion/religions/`, not
  `common/religion/religion_types/` — useful for the cultures-religions lane.
