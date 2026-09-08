# World-data mapping: CK2 → CK3 1.19

Field-level reference for the `titles-history`, `characters` and `cultures-religions` lanes.
Written so those lanes do **not** have to re-open the game files. Companion tables:

| table | rows | what it covers |
|---|---|---|
| `mappings/culture_fields.csv` | 53 | CK2 `common/cultures` → CK3 `common/culture/{cultures,pillars,traditions,name_lists}` |
| `mappings/religion_fields.csv` | 78 | CK2 `common/religions` → CK3 `common/religion/*_types`, incl. the flag→doctrine decision table and the minimal valid faith |
| `mappings/government_map.csv` | 21 | the 19 Faerûn governments → the 18 CK3 1.19 governments |
| `mappings/title_fields.csv` | 75 | CK2 `common/landed_titles`, `history/titles`, `history/provinces` → CK3 equivalents |
| `mappings/character_fields.csv` | 60 | CK2 `history/characters`, `common/dynasties`, `common/bookmarks` → CK3 equivalents |

Columns are the same everywhere: CK2 side, CK3 side, `status` (`exact` / `approx` / `none`),
`default_when_none` (what the converter emits when CK2 gives nothing), `ck3_evidence` (`file:line`), `note`.

## Method

- CK3 side: read from the local install, `verified` against **CK3 1.19.0.6 (Scribe)**
  (`launcher/launcher-settings.json`), reached through the repo symlink `../claudespace/game_files`.
  Paradox ships `_*.info` files next to each database; those are the primary source, but several are
  stale (see Gotchas), so every claim is cross-checked against a live vanilla file and a usage count.
- CK2 side: brace-depth-aware tallies over the CK2 base install and `Faerun/Faerun/`, so key lists are
  mechanical, not eyeballed. Counts in the `ck2_uses_in_faerun` column come from those tallies.
- Third-party reference: **Elder Kings 2** (workshop `2887120253`), the only large CK3 fantasy TC on
  disk, sampled for "how does a TC actually fill this file".
- The `ck3.paradoxwikis.com` modding pages were fetched but are **largely unusable**: every one of the
  five carries a "last verified 1.0–1.4" banner. `Culture_modding` still documents the pre-1.9 flat
  culture-group model; `Religion_modding` names folders that no longer exist; `Title_modding` never
  mentions coats of arms; `History_modding` documents neither `history/provinces` nor `history/characters`.
  Nothing in the tables rests on the wiki alone.
- Verification: `uv run scripts/verify_ck3_world_keys.py` indexes every identifier in
  `game/common/**` and `game/history/**` (293k identifiers) and checks every CK3 token the tables claim.
  Output: `docs/evidence/ck3_world_keys.csv` and `docs/evidence/ck3_world_keys_summary.txt`.
  Current result (`verified`): **462 tokens checked, 455 found live, 7 documented-only, 0 missing**.
  A token found only in a `.info` file is reported `info_only` — Paradox documents it, vanilla never uses it.

## Structural mapping in one screen

| CK2 | CK3 1.19 | note |
|---|---|---|
| culture group (67 in Faerûn) | one `heritage` **and** one `language` pillar | groups double as races (`docs/design_races.md`) |
| culture (419 in Faerûn) | culture + its own `name_list` | names move out of the culture into `common/culture/name_lists` |
| religion group (15) | a CK3 **religion** (the object owning `faiths = { }`) + one **religion family** | families are a level CK2 does not have |
| religion (94) | a CK3 **faith** | |
| CK2 religion flag | a CK3 **doctrine** | 23 mandatory doctrine groups + 3 core tenets |
| title `holy_site = <religion>` | a `holy_site_type` object + `holy_site =` on the faith | relation is **inverted** |
| title `caliphate` / `controls_religion` | `religious_head = <title>` on the faith | relation is **inverted** |
| title `title` / `title_female` / `foa`, culture `dukes_called_kings` | `common/flavorization` entries | matched on `titles` / `name_lists` / `heritages` / `governments` |
| title `<culture> = "Name"` | `cultural_names = { name_list_x = <loc key> }` | keyed by **name list**, value is a **loc key** |
| CK2 flag `.tga` / `coat_of_arms { }` | `common/coat_of_arms/coat_of_arms/<title id>` | separate database, keyed by title id |
| province + its baronies | one CK3 province **per barony** | a CK3 province *is* a barony |
| province `b_x = castle` | `holding = castle_holding` on that province | |
| province `terrain` | `common/province_terrain/` (`<id>=<terrain>`) | `history/provinces` `terrain` also works, 95 vanilla uses |
| province tech levels | `history/cultures` `discover_innovation` / `join_era` | scope changes province → culture |
| CK2 government (19) | CK3 government (18) | `government_map.csv` |
| CK2 title `law = <succ law>` | `succession_laws = { ... }` in `history/titles` | braced list, and split into order + gender laws |

## Minimal valid file of each type

### culture — `common/culture/cultures/`
Mandatory in practice (all 244 vanilla cultures set them, `verified`): `color`, `ethos`, `heritage`,
`language`, `martial_custom`, `head_determination`, `name_list`, `ethnicities`, and all four gfx axes
(`coa_gfx`, `building_gfx`, `clothing_gfx`, `unit_gfx`).
Verified **omittable**: `traditions` (`greek`, `japanese` omit it), `house_coa_frame` (11 Iberian cultures omit it),
`created`, `parents`, `name_order_convention`, `history_loc_override`, `character_modifier`.
Reference: `common/culture/cultures/_cultures.info`; live shape: `00_north_germanic.txt:1-51`.

### pillar — `common/culture/pillars/`
A heritage is three lines: `type = heritage` (+ optional `is_shown`, `audio_parameter`, `parameters`).
A language needs `type = language` **plus** `color = <named_color>` (the language UI paints it).
Reference: `_pillars.info`; live: `00_heritage.txt:1-8`, `00_language.txt:1-18`.

### name list — `common/culture/name_lists/`
`male_names` + `female_names` are enough to load. 26 keys exist in total; `cadet_dynasty_names` and
`bastard_dynasty_prefix` are live (202 and 3 vanilla uses) but **absent from `_name_lists.info`**.
Reference: `_name_lists.info`, plus a complete worked example in `_example.info`.

### faith — `common/religion/religion_types/`
A religion needs `family`. A faith needs `color`, and — directly or inherited from its religion — one
doctrine from each of the **23 mandatory doctrine groups** plus **3 core tenets**.
`verified` by parsing all 140 vanilla faiths with religion-level inheritance: those 23 groups appear in
140/140 faiths, `doctrine_core_tenets` (`number_of_picks = 3`) in 138/140.
The 23: `hostility_group`, `doctrine_theism`, `doctrine_gender`, `doctrine_pluralism`, `doctrine_theocracy`,
`doctrine_head_of_faith`, `doctrine_pilgrimage`, `doctrine_marriage_type`, `doctrine_divorce`,
`doctrine_bastardry`, `doctrine_consanguinity`, `doctrine_homosexuality`, `doctrine_deviancy`,
`doctrine_adultery_men`, `doctrine_adultery_women`, `doctrine_kinslaying`, `doctrine_witchcraft`,
`doctrine_clerical_function`, `doctrine_clerical_gender`, `doctrine_clerical_marriage`,
`doctrine_clerical_succession`, `doctrine_funeral`, `doctrine_coronation`.
Everything else (`doctrine_muhammad_succession`, `doctrine_temple_authority`, `doctrine_zoroastrian_branches`,
`is_*_faith`, `unreformed_faith`, `has_jizya_doctrine`, `nudity_doctrine`, `immaterial_harmony`,
`divine_destiny`, `adoptionist_school`, `not_allowed_to_hof`, `full_tolerance`, `special_tolerance`,
`heresy_hostility`, `is_hostile_to_maitreya`) is optional or engine-internal.
The safest default doctrine block for a Faerûnian pantheon is vanilla `paganism_religion`
(`common/religion/religion_types/00_paganism.txt:1-40`) — see `religion_fields.csv`, section `minimal_faith`.
Reference: `_religion_types.info`, `doctrine_group_types/00_doctrine_group_types.txt`.

### holy site — `common/religion/holy_site_types/`
`county = c_<id>` is the only field that matters; `barony`, `parameters` (bare flags) and
`character_modifier` are optional. Vanilla has 322 sites; EK2 ships 275, all in the minimal
`county` + `parameters` shape. Reference: `_holy_site_types.info`; live: `00_holy_site_types.txt:7`.
**Practical cap: 5 `holy_site =` lines per faith** (132/140 vanilla faiths have exactly 5, the other 8 have 7).

### landed title — `common/landed_titles/`
A titular title is one line of content: `color = { r g b }`. A **barony must have `province = <id>`**.
A county must contain at least one barony; a barony may not exist outside a county.
Reference: `_landed_titles.info:8-20` (hierarchy) and `:36` (color).
The landless-title recipe vanilla uses (`01_japan_noble_family.txt:10-15`): `landless = yes`,
`ruler_uses_title_name = no`, `always_follows_primary_heir = yes`, `no_automatic_claims = yes`,
`destroy_if_invalid_heir = yes` (+ `noble_family = yes` for administrative realms).

### coat of arms — `common/coat_of_arms/coat_of_arms/`
`<title id> = { pattern = "pattern_solid.dds" color1 = "green" }` is valid, and is literally the
vanilla `default` entry (`default.txt:1`). A title may also alias another: `e_japan = k_chrysanthemum_throne`.

### title history — `history/titles/`
**Everything must sit inside a dated block**: `verified` 0 top-level keys across all 183 vanilla files.
`holder = <id>` alone is a valid entry. Reference: `history/_history.info`; live: `history/titles/k_england.txt`.

### province history — `history/provinces/`
Keyed by **numeric province id**, grouped freely into files (177 vanilla files for ~11k provinces).
`culture` + `religion` + `holding` is the normal minimum. `buildings = { ... }` requires an explicit
`holding` (it does not work with `holding = auto`) and a later dated `buildings` block **replaces**
all earlier buildings. Reference: `history/_provinces.info`; live: `history/provinces/k_sardinia.txt:35-49`.

### character history — `history/characters/`
`name` + a birth-dated block is enough. Reference: `history/_characters.info`; note that `.info`
writes `faith =` while 70119 of 71143 live entries write `religion =` — both work.

### dynasty / house — `common/dynasties/`, `common/dynasty_houses/`
Dynasty: `name` (a `dynn_*` **loc key**, not a literal) + `culture`. House: `name` + `dynasty` (both required,
558/558 vanilla houses set exactly those). Houses are optional — characters may reference a dynasty directly.

### bookmark — `common/bookmarks/bookmarks/`
`start_date` + at least one `character = { ... }`. All 19 vanilla bookmarks also set `is_playable`
and `group`; all 110 bookmark characters set `name`, `title`, `government`, `religion`, `difficulty`,
`position = { x y }` and `dynasty_splendor_level`. Reference: `_bookmarks.info`.

## Id spaces (collision avoidance)

`verified` id ranges:

| database | Faerûn CK2 | CK3 1.19 vanilla | converter rule |
|---|---|---|---|
| characters | 11952 dynasties aside, **18124 characters, ids 2 – 90008** in 80 id-range files | 38020 numeric ids, **98 – 1000230517**; plus **33104 string ids** (`sephardi_0001`, `bai_yang_2_1`) | emit **string ids** `fae_<ck2id>` — collision-proof and greppable. EK2 uses string ids for 100 % of its 16515 characters. |
| dynasties | **11952 dynasties, ids 1 – 15859** (sparse) | 4223 numeric, **2 – 1000101763**; plus **6105 string ids** | emit `fae_dyn_<ck2id>`. |
| dynasty houses | none (CK2 has no cadet houses) | 2 numeric (12319, 1029175) + **536 string ids** (`house_fujiwara_ashikaga`) | only emit if the mod needs `noble_families`; use `fae_house_<x>`. |
| provinces | 2697 rows in `definition.csv`, `max_provinces = 2720` | 11298 baronies carry a `province` | province ids are allocated by the `map-physical` / `baronies` lanes; this lane only consumes them. |

If numeric character ids are kept instead, start above **1 000 300 000** — above vanilla's highest
(1000230517) and above the Faerûn range. String ids remove the problem entirely and are what both
vanilla and EK2 do for generated content, so they are the recommendation.

Atlantis-style placeholder titles/characters that survive a run must use the same `fae_`/`fae_dyn_`
prefixes so a later grep can find and delete every one of them.

## Gotchas

1. **1.19 renamed the religion folders.** `common/religion/` contains only `religion_types`,
   `religion_family_types`, `doctrine_types`, `doctrine_group_types`, `holy_site_types`.
   The pre-1.19 `religions` / `doctrines` / `holy_sites` directories **do not exist**. EK2 already
   uses the new paths. Every tutorial and the wiki are wrong here.
2. **`_cultures.info` is stale**: it documents `martial_tradition`, but 244/244 vanilla cultures use
   `martial_custom`. Only the trigger kept the old name (`has_same_culture_martial_tradition`).
   The same file omits `head_determination`, `parents`, `house_coa_mask_offset/scale` entirely.
3. **CK3 has a title tier above empire**: `h_` (hegemony) — `h_roman_empire`, `h_eastern_roman_empire`,
   `h_dar_al_islam`, `h_india`, `h_china`. Undocumented on the wiki. A candidate home for Faerûn's
   faction/organisation empires.
4. **CK2 building history is flat, not nested.** `b_x = castle` for the holding and `b_x = ca_wall_1`
   for a building are both bare scalar assignments; the block form `b_x = { ca_wall_1 = yes }` does not
   exist in either CK2 base or Faerûn (`verified`, 0 occurrences). Faerûn writes **no building history at all**,
   so the CK3 `buildings = { }` conversion has no input for this mod.
5. **`can_be_named_after_dynasty` defaults to yes.** A CK2 culture *without* `dynasty_title_names`
   therefore needs `can_be_named_after_dynasty = no` emitted, not silence. Same trap with
   `always_use_patronym` (CK3 default **no**: a converted patronym is invisible without it).
6. **`assimilate` is inverted.** CK2 `assimilate = no` → CK3 `de_jure_drift_disabled = yes`;
   CK2 `assimilate = yes` (the default) → emit nothing.
7. **Landless titular titles still want a `capital`.** EK2 writes
   `capital = c_imperial_city #Placeholder for less errors` on five landless titles for exactly this reason.
8. **`common/bookmark_portraits` is not authorable — but must not be empty either.**
   Every file starts `# Auto generated file, do not edit manually. Created using console command
   dump_bookmark_portraits`, and the filename is the bookmark character's `name` value.
   **CORRECTED 2026-09-07 (lane `titles-history`):** the folder may *not* be left empty.
   `ck3-tiger` reports `fatal(crash): bookmark portrait for <name> not found in
   common/bookmark_portraits` — "This causes a crash in CK3 1.13" — for every bookmark character
   without a file. The converter writes a minimal placeholder (block key, `type`, `id`,
   `random_seed`, `age`, empty `genes = { }`) per character, to be replaced by a real in-game dump.
   See `docs/formats_titles.md` §5.
9. **CK2 `dna` / `properties` cannot be converted.** They are 2D sprite-layer indices. `docs/design_races.md`
   item 6 already decides: emit no `dna =` and let the ethnicity randomise.
10. **`nomadic_government` is a dead stub in Faerûn** (`potential = { always = no }`, `verified`).
    Emit nothing for it; the live nomad governments are `nomadic_tribal_government` and `semi_nomadic_government`.
11. **CK3 `nomad_government` and five TGP governments are DLC-gated** in `can_get_government`
    (`has_mpo_dlc_trigger` / `has_tgp_dlc_trigger`). `celestial_government` is **not** gated — which is
    why it is the safe target for Shou Lung. EK2's pattern for DLC-dependent content is a scripted
    `destroy_landless_title_no_dlc_effect` wrapper (227 uses in its title history).
12. **`docs/faerun_ck2_survey.md` §8 lists 18 governments; there are 19.** `celestial_bureaucracy`
    (from CK2 base `confucian_bureaucracy`) was missed. `government_map.csv` covers all 19.
13. **Faerûn key names that differ from the obvious guess** (`verified`): the title-history key is
    `clear_tribute_suzerain` (singular), not `clear_tributary_suzerains`; characters use the effect
    `set_real_father`, not a `real_father` key, and `create_bloodline`, not `add_bloodline`;
    governments use `allowed_holdings` / `preferred_holdings`, not `holding_types`, and
    `can_build_castle` (singular). There is no `history/characters/_unused/` directory.
14. **`uses_jizya_tax` is a CK2 *religion* key** (12 Faerûn uses), not a government key →
    `special_doctrine_jizya`. `dynasty_title_names` is a *culture* key, not a government key.
15. **`pentarch`, `reset_name`, `vice_royalty`, `trade_post`, `castes`, `horde`,
    `bastard_dynasty_prefix`, `grammar_transform`, `piety`, `decadence`, `real_father`, `historical`,
    `occluded`, `add_alliance`, `combat_rating`, `race`** are all **unused by Faerûn** (`verified` 0 hits),
    so the converter can skip those code paths for this mod even though the keys exist in CK2 base.
16. **CK2 `intermarry` has no CK3 equivalent** (`verified`: there is no `doctrine_religious_intermarriage`).
    Faerûn's 833 `intermarry` lines are a graph; the CK3 levers are the religion family's
    `hostility_doctrine` parameters (`hostility_same_religion` / `hostility_same_family` /
    `hostility_others`, 1 = righteous … 4 = evil) plus `doctrine_pluralism_*`. Keep the original list as a comment.
17. **A CK3 faith cannot carry a modifier.** Only its doctrines can. CK2 `character_modifier` /
    `unit_modifier` on a religion therefore needs a *generated carrier doctrine* (EK2 defines ~372 custom
    doctrine ids for exactly this). Likewise a CK2 culture `modifier` is a **province** modifier, so its
    only CK3 home is a generated **tradition** with `province_modifier` — and
    `common/culture/_cultural_traits.info` restricts culture traits to hardcoded modifiers or ones
    generated from schemes/holdings/lifestyles/regions/terrains/men_at_arms_types/governments.
18. **CK2 `holding` types with no CK3 counterpart**: `FORT`, `HOSPITAL`, `TRADE_POST`, `FAMILY_PALACE`,
    and Faerûn's own `ct_spelljammer_port` (20) / `ct_planar_portal` (5). `common/holdings` offers only
    castle / city / church / tribal / nomad / herder / temple_citadel.
19. **`death_reason` values must be remapped.** CK3 defines 313 ids in `common/deathreasons`; Faerûn uses
    80, many invented (`death_wild_magic_surge`, `death_executed_by_shou_lung_emperor`). Unknown → nearest
    generic, and never a made-up id. `killer` may be a string id.
20. **CoAs: prefer the vector route.** Vanilla uses `textured_emblem` in exactly one file (`default.txt`);
    EK2 in 2 of 31. There are 1360 reusable `ce_*.dds` colored emblems against 24 textured ones, so
    Faerûn's 3455 flag `.tga` files should be decomposed into `pattern` + `colored_emblem` combinations
    (or given placeholder CoAs, as EK2 does in `90_placeholder_titles.txt`).

## Re-running verification

```sh
uv run scripts/verify_ck3_world_keys.py                       # uses ../claudespace/game_files
uv run scripts/verify_ck3_world_keys.py --game <ck3 game dir>
```

Exit code 1 if any CK3 token on an `exact`/`approx` row is absent from the game files — wire it into
`ci/checks.sh` once the tables start being edited by the consuming lanes.
