# CK3 1.19 title formats — what the converter had to verify

Reference for lane `titles-history` (steps `titles`, `history_titles`,
`bookmarks`). Every claim is `verified` against the local install through the
repo symlink `../claudespace/game_files` (CK3 **1.19.0.6 Scribe**) or against
`ck3-tiger` v1.19.0, with the file and line. `mappings/title_fields.csv` holds
the field-level CK2→CK3 table; this file records only the CK3 facts that the
table did not already state, or stated wrongly.

Short names: `GAME` = `../claudespace/game_files`, `TIGER` = `ck3-tiger`
v1.19.0 run through `scripts/tiger_titles_check.py`.

## 1. `common/landed_titles`

| fact | evidence |
|---|---|
| Tier nesting `e_ > k_ > d_ > c_ > b_`; a county must contain ≥1 barony, a barony may not exist outside a county | `GAME/common/landed_titles/_landed_titles.info:8-20` |
| `province = <int>` is mandatory on a barony and is the *only* link to the map | `_landed_titles.info:121-124` |
| `capital` must be a **county** title | `_landed_titles.info:127-129` |
| `color = { r g b }` accepts 0-255 ints; it is the map border colour, not the CoA | `_landed_titles.info:36`; 17454 live uses |
| **Baronies carry a colour in vanilla**: 9933 of 10041 set one | counted over `GAME/common/landed_titles/*.txt` |
| `cultural_names` is keyed by **name list**, not culture, and takes a **loc key**; CK3 derives the cultural adjective as `<key>_adj` | `_landed_titles.info:220-229`; live `00_landed_titles.txt:631-633` (`name_list_khitan = cn_kara_khitai`) |
| The landless-title recipe | `01_japan_noble_family.txt:10-15` — `landless`, `ruler_uses_title_name = no`, `always_follows_primary_heir`, `no_automatic_claims`, `destroy_if_invalid_heir`; `require_landless` at `_landed_titles.info:56-60`, live at `01_japan.txt:1756` |
| `definite_form`, `no_automatic_claims`, `can_be_named_after_dynasty`, `de_jure_drift_disabled`, `holding_regnal_male_names`, `ai_primary_priority` all exist | `_landed_titles.info:88`, `:95`, `:114`, `:130`, `:172`, `:193`; `ai_primary_priority` live at `00_landed_titles.txt:62` |
| `de_jure_liege` is **history only** inside `landed_titles`; the de jure tree is the nesting | `_landed_titles.info:243` |
| A **redefined field inside one block** is a diagnostic, not silently merged | `TIGER warning(duplicate-field)`: "`no_automatic_claims` is redefined in a following line" |
| A **non-ASCII** script file needs a UTF-8 BOM | `TIGER warning(encoding): Expected UTF-8 BOM encoding`; vanilla `common/landed_titles/00_landed_titles.txt` and `common/bookmarks/bookmarks/00_bookmarks.txt` start `ef bb bf`, the pure-ASCII `history/titles/k_england.txt` does not |
| `capital` outside the title's own de jure area is a diagnostic | `TIGER warning(title-tier): capital 'c_abarun' is not in de jure 'd_omans_isle'` |

## 2. `common/coat_of_arms/coat_of_arms`

| fact | evidence |
|---|---|
| A CoA is a separate database keyed by **title id**, not a `landed_titles` key | `GAME/common/coat_of_arms/coat_of_arms/` is title-keyed, 1878 blocks |
| The minimal valid entry is vanilla's own `default` | `default.txt:1-4` — `pattern = "pattern_solid.dds"` + `color1 = "green"` |
| `color1` accepts a **raw RGB** triple, not only a named colour | `90_dynasties.txt:389` — `color1=rgb { 255 255 255 }`; 33 rgb uses against 6379 named ones |
| Named colours live in `common/named_colors` and are hsv/float, so a CK2 0-255 colour cannot reuse one | `common/named_colors/default_colors.txt:1-20` |
| A bookmark character's **dynasty** wants a CoA or its shield is blank | `TIGER warning(missing-item)`: "coa … not defined … bookmark characters must have a defined coa" |

## 3. `history/titles`

| fact | evidence |
|---|---|
| **No top-level keys**: everything sits in a dated block | `verified` 0 depth-1 keys across all 183 files of `GAME/history/titles/` |
| `holder = 0` is the valid "exists but unheld" value | `GAME/history/titles/k_saryarka.txt:9` |
| String character ids are legal | 33104 of 71124 vanilla history ids are strings; Elder Kings 2 uses strings for 100 % of its 16515 characters |
| `succession_laws = { … }` is a braced list and replaces **per law group**; one order law and one gender law coexist | `GAME/history/titles/k_england.txt:13` (`succession_laws = { saxon_elective_succession_law }`); 1446 uses across `history/titles` |
| The law ids live in two files | `common/laws/00_succession_laws.txt` (order + gender + government-specific) and `common/laws/01_title_succession_laws.txt` (elective, `noble_family_succession_law`, `temporal_head_of_faith_succession_law`) |
| `gaelic_elective_succession_law` is CK3's **Tanistry** | `localization/english/*`: `gaelic_elective_succession_law: "Tanistry Elective"` |
| `government` on the title is authoritative and heavily used | 5960 uses in `GAME/history/titles/` against Faerun's 44 |
| `set_title_name` is an **effect** taking a loc key; there is no dated `adjective` key | `common/effect_localization/00_landed_title_effects.txt:16`; `reset_title_name` at `:30` |
| `liege` must be a **strictly higher tier** | `TIGER error(title-tier): liege must be higher tier than d_chigidi` |
| `liege = X` needs X to have a **living** holder at that date, or the line is ignored | `TIGER error(history)`: "X has no holder at D" / "holder of X is not alive at D", both with "setting the liege will not have effect here" |
| A title used as a `liege` must itself have a history entry | `TIGER error(missing-item): d_coffee_coast has no title history` |

## 4. `history/provinces`

| fact | evidence |
|---|---|
| Keyed by **numeric province id**; files grouped freely (177 vanilla files for ~11k provinces) | `GAME/history/_provinces.info`; `history/provinces/k_sardinia.txt` |
| Top-level `culture` / `religion` / `holding` **plus** dated blocks; a dated `holding` is legal | `k_sardinia.txt:4-8` and `:33-46`; 1538 dated `holding` lines across `GAME/history/provinces/` |
| `holding` values come from `common/holdings` — only castle / tribal / city / church / nomad / herder / temple_citadel exist | `common/holdings/00_holdings.txt:1,54,83,135,186,199,215` |
| `buildings = { }` needs an explicit `holding` (not `auto`) and a later dated `buildings` block **replaces** the earlier ones | `GAME/history/_provinces.info` |
| A province defined twice (mod + vanilla) is a diagnostic — which is what makes the `replace_path` list load-bearing | `TIGER warning(duplicate-item): province is redefined by another province` |

## 5. `common/bookmarks`

| fact | evidence |
|---|---|
| A bookmark needs `start_date` + ≥1 `character`; all 19 vanilla ones also set `is_playable`, `group`, `weight` | `GAME/common/bookmarks/bookmarks/_bookmarks.info`; `00_bookmarks.txt:1-24` |
| A bookmark character needs `name`, `type`, `birth`, `title`, `government`, `culture`, `religion`, `difficulty`, `history_id`, `position`, `animation`; `dynasty` / `dynasty_house` optional | `00_bookmarks.txt:10-27` (all 110 vanilla characters) |
| CK3 wants a **birth date**, CK2 gives an **age** — and CK2's age is often cosmetic (`age = 30 # This seems to be simply graphical age`, Faerun `common/bookmarks/00_bookmarks.txt:57`) | — |
| `default_start_date` exists **only** in `common/bookmarks/groups`, not in `common/defines` | `GAME/common/bookmarks/groups/00_bookmark_groups.txt:2,6,10` |
| The bookmark's **own database key** is its localisation key | `GAME/common/bookmarks/groups/_bookmark_groups.info:1-2` |
| **`common/bookmark_portraits` cannot be left empty.** A bookmark character with no file there crashes the game | `TIGER fatal(crash)`: "bookmark portrait for `<name>` not found in common/bookmark_portraits … This causes a crash in CK3 1.13". **This corrects `docs/mapping_world.md` gotcha 8**, which said the folder must stay empty. |
| The portrait file name is the character's `name` value | 332 vanilla files, e.g. `bookmark_adventurers_almos_arpad.txt` declaring `bookmark_adventurers_almos_arpad={ … }` |
| Bookmark art is looked up by the bookmark key and has no CK2 source | `TIGER warning(missing-file)`: `gfx/interface/bookmarks/<key>.dds`, `gfx/interface/bookmarks/start_buttons/<key>.dds`, `gfx/interface/icons/bookmark_buttons/<key>.dds` |
| `challenge_characters` takes the same `character = { }` block plus `start_date` | `GAME/common/bookmarks/challenge_characters/_challenge_characters.info` |

## 6. ck3-tiger, as a tool

- It reads the **`.mod` file given on the command line, not `descriptor.mod`**. A
  `.mod` without the `replace_path` lines makes every replaced vanilla file
  load, which showed up as 1707 spurious `warning(duplicate-item): province is
  redefined` against `GAME/history/provinces/k_england.txt`.
  `scripts/tiger_titles_check.py` copies the lines across.
- `--game` wants the **install directory**, not its `game/` subfolder; given
  `…/Crusader Kings III/game` it prints "That does not look like a CK3
  directory" and retries the parent.
- Diagnostic lines are ANSI-coloured; the class is
  `severity(kind): message` followed by a `--> [MOD|CK3] path` line. Ownership
  needs both, because a message about a missing culture is reported against
  *our* file.

## 7. CK2 side, corrections to earlier docs

- `common/landed_titles` `capital` is a **province id**, never a title:
  `verified` 465 `capital =` lines in Faerun, all numeric
  (`Faerun/Faerun/common/landed_titles/offmap_toril_landed_titles.txt:5`,
  `capital = 1363`). The province→county link is `title = c_x` inside the
  province-history file, and nowhere else.
- Faerun's title counts, re-measured with this lane's own reader
  (`scripts/survey_ck2_titles.py`): **65 e_, 267 k_, 979 d_, 2132 c_,
  15356 b_ = 18799 titles** in 7 files. `mappings/title_fields.csv` quotes
  272 k_ / 983 d_; those numbers were taken over the CK2 *base* install as
  well, so the file-level counts here are the ones to trust for Faerun.
- The 7 landed-titles files split cleanly by role: `01_landed_titles.txt` +
  `01_laerakond.txt` are the de jure tree (42 empires), `titular_titles.txt`
  317 titular titles (20 e_, 98 k_, 199 d_), `mercenaries.txt` 156 duchy-tier
  companies, `landed_titles.txt` `e_rebels` + `e_pirates`,
  `offmap_toril_landed_titles.txt` one offmap empire, and **`republics.txt`
  161 root-level `b_` patrician families** — the only file whose contents
  cannot exist in CK3 at all.
- Faerun's CK2 localisation has **zero `*_adj` keys** (`verified` over
  `Faerun/Faerun/localisation/*.csv`), while CK3 reads a title's adjective from
  `<title>_adj`. Hence `mappings/loc_key_renames_titles.csv`.
- Faerun writes **no** `history/titles` top-level keys (`verified` 0 of 3420
  files), so the "wrap CK2 top-level keys in an early date" path exists but is
  never exercised by this mod.
