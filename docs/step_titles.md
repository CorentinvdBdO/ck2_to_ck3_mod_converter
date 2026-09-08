# Steps `titles`, `history_titles`, `bookmarks` — the Faerûn title world

Lane `titles-history`. Turns CK2 `common/landed_titles`, `history/titles`,
`history/provinces` and `common/bookmarks` into the CK3 equivalents, so the
generated mod has the full de jure tree with holders at every bookmark.

| step | owns | writes |
|---|---|---|
| `titles` | `common/landed_titles`, `common/coat_of_arms/coat_of_arms` | `fae_landed_titles.txt`, `fae_titles.txt` (CoA), `fae_title_cultural_names_l_english.yml` |
| `history_titles` | `history/titles`, `history/provinces` | `fae_{empires,kingdoms,duchies,counties,baronies}.txt`, one province file per de jure kingdom, `fae_title_history_names_l_english.yml` |
| `bookmarks` | `common/bookmarks`, `common/bookmark_portraits` | `fae_bookmarks.txt`, `fae_bookmark_groups.txt`, one portrait per bookmark character, three shadow files, `fae_bookmarks_l_english.yml` |

Field-level table: `mappings/title_fields.csv`. CK3-side facts with file:line:
`docs/formats_titles.md`. Governments: `mappings/government_map.csv`.
CK2-side shapes: `docs/formats_ck2_landed_titles.md`.

Code: `src/ck2ck3/titles/` — `ck2read` (readers), `tables` (the three derived
maps), `place` (barony → province), `model` (one shared parse + the liveness
rule), `landed` / `provinces` / `history` / `coa` / `bookmarks` (writers),
`text` (line buffer, slug, BOM).

## Run it

```sh
uv run ck2ck3 --steps titles,history_titles,bookmarks           # into the real mod
uv run ck2ck3 --steps titles,history_titles,bookmarks --out /tmp/x
uv run scripts/survey_ck2_titles.py                             # CK2-side tallies
uv run scripts/tiger_titles_check.py                            # ck3-tiger per class
uv run scripts/tiger_titles_check.py --mod /tmp/out             # ...on a built folder
uv run scripts/build_loc_key_renames_titles.py                  # the loc hand-off
```

`scripts/tiger_titles_check.py` copies the generated mod to a scratch folder,
re-runs the three steps into it, writes a throwaway `history/characters` stub
so holder diagnostics can be told apart from real ones, and writes
`docs/evidence/tiger_titles.txt`. `--mod <dir>` skips the re-run and validates
a folder exactly as it stands — the mod folder needs a `descriptor.mod` (run
the `descriptor` step into it too), because ck3-tiger takes the `replace_path`
lines from there.

## Counts (Faerûn, 2026-09-07, `verified`)

| | |
|---|---|
| CK2 titles read | 18799 — 65 e_, 267 k_, 979 d_, 2132 c_, 15356 b_ |
| emitted as live CK3 titles | **5551** — 65 e_, 267 k_, 979 d_, 2120 c_, 2120 b_ |
| emitted commented out | 13248 — 11530 unbuilt baronies, 1461 demoted, 161 patrician families, 12 counties, 84 sub-titles of those counties |
| baronies placed on the map | 2120 (one per county; see *Barony placement*) |
| title histories converted | 3193 live + 227 kept commented + 2358 stubs |
| province history blocks | 2120 in 166 files |
| bookmarks | 17 with 82 characters, default `1357.1.1` |
| coats of arms | 3431 placeholders; 3410 CK2 flag files recorded, 0 converted |
| cultural-name loc keys | 718 from 3314 CK2 cultural-name lines |
| holder / liege integrity failures | 0 missing holders, 0 unmapped CK2 keys |

## The rules

### Nothing is dropped silently

Every CK2 key with no CK3 home is written as a comment **inside the block it
came from**, with the reason. That is a repo rule (`CLAUDE.md`: "No CK3
equivalent → emit a comment next to the nearest construct"), and it is why the
writers emit text rather than a `pdx` tree: a parse tree has no way to
represent a commented-out entry between two live ones (`src/ck2ck3/titles/text.py`).

The comment lists live in the code next to the writer that emits them:
`landed.COMMENT_ONLY`, `landed.GOVERNMENT_FLAGS`, `history.COMMENT_ONLY`,
`provinces.DATED_COMMENT_ONLY`.

### Liveness — which CK2 titles become CK3 titles

`model.liveness()` is the single source of truth, so a title can never be
defined in `landed_titles` and missing from a history file. Three rules, and a
dead title kills its subtree:

1. a **patrician family** from `republics.txt` is a root-level `b_` title, and
   CK3 forbids a barony outside a county — 161 titles;
2. a **barony with no CK3 province** cannot exist (`province = <id>` is
   mandatory) — 12991 titles;
3. a **county with no live barony** cannot exist (a CK3 county needs at least
   one barony) — 12 counties: the 7 that have no CK2 province at all
   (`c_barakuir`, `c_drakkalor`, `c_korolnor`, `c_kossuths_eye`, `c_torglor`,
   `c_xothaerin`, `c_zokir`) and 5 whose province never had a built holding.

Duchies, kingdoms and empires survive childless: CK3 calls that a titular
title and it is legal.

### Barony placement

`place.build_plan()` picks one of two modes automatically.

- **`barony_set`** — lane `baronies` has published
  `docs/evidence/barony_set.csv` (`county,barony,holding,built_date,seed_source,pixels,status`)
  and `map_data/definition.csv` names its rows `b_<barony>`. Placed = rows with
  status `placed` or `override`; the province id is the `definition.csv` row of
  that name.
- **`county_capital`** — the current state: `definition.csv` has one row per
  CK2 province (i.e. per county) named after the CK2 province. One barony per
  county is placed — the **county capital**, i.e. the first barony in CK2
  `landed_titles` order that has a built holding at the bookmark date — and it
  takes that county's province id from `docs/evidence/province_id_map.csv`.
  CK2 has no explicit county-capital key (`capital` in `landed_titles` is a
  *province id*), so declaration order is the only signal.

`place.built_holdings()` computes the **state** at a date, not a log: a later
`b_x = none` or a `remove_settlement` removes the barony again.

Unplaced baronies are emitted as `# b_x = { } # <status>: <reason>`, so the
submod promotes one by deleting two characters.

### Government derivation

CK2 stores no government on a character (`verified`: 0 of 80
`history/characters` files mention one) and only 44 times on a title; CK3 makes
the title authoritative and uses 5960 `government` lines in vanilla. So the
line is synthesised, in the first dated block that gives the title a holder,
by `tables.derive_government()` — first match wins:

| # | input | CK3 government |
|---|---|---|
| 1 | CK2 `government = x` in `history/titles` | `government_map.csv` |
| 2 | `mercenary = yes` | `mercenary_government` |
| 3 | `holy_order = yes` | `holy_order_government` |
| 4 | `pirate = yes` | `landless_adventurer_government` |
| 5 | `tribe = yes` | `tribal_government` |
| 6 | declared in `republics.txt` | `republic_government` |
| 7 | `controls_religion` / `caliphate = yes` | `theocracy_government` |
| 8 | nothing | `feudal_government` |

Rows 2-5 are ordered specific-before-generic on purpose: `e_pirates` sets
`pirate`, `landless`, `primary` **and** `tribe`, and the pirate flag has to
win. The reason is written into the file as a comment above the title's
history, so the derivation is auditable per title.

Result over Faerûn: 5296 feudal, 136 mercenary, 71 tribal, 20 nomad, 20 holy
order, 5 theocracy, 2 republic, 1 landless adventurer.

### Succession laws

CK2 repeats `law = x` lines that mix succession order, gender and a dozen
unrelated law groups (crown authority, per-action council voting power, the
`ze_*` submod laws). CK3 takes one braced `succession_laws = { }` list, and
replaces **per law group**, so an order law and a gender law coexist.

`tables.map_succession_laws()` holds the table (33 CK2 laws in use, all
covered — `tests/test_titles_tables.py::test_every_faerun_law_is_covered`) and
returns three things: the CK3 laws, the CK2 laws it dropped with a reason, and
notes where the mapping lost meaning. Both lists become comments in the output.

Lossy on purpose:

- CK3 has no **seniority** or **eldership**; both become
  `single_heir_succession_law` (primogeniture).
- CK3 has no **Turkish succession**; `confederate_partition_succession_law` is
  the nearest.
- CK3 has no **patrician** succession; `city_succession_law` is the nearest.
- The Faerûn "chosen by the order" laws (`succ_magic_wizard`,
  `succ_divine_cleric`, `succ_yikaria`, `succ_wychlaran`, `succ_magister`,
  `succ_bahamut`, …) map to `bishop_theocratic_succession_law`, but that only
  makes sense on a theocracy, so a title whose derived government is not
  `theocracy_government` gets `feudal_elective_succession_law` and a comment.
- `succ_ordning` becomes `tribal_elective_succession_law`; no CK3 mechanic
  models the giant caste ladder.
- Non-succession CK2 laws (632 lines of `*_voting_power_*`, `centralization_*`,
  `revoke_title_law_*`, `ze_*`) are commented: CK3 realm laws are not set from
  history.

### Holder / liege integrity

Four checks, all warn into the run log rather than guess:

- a `holder` that names no CK2 character becomes `holder = 0` (the value
  vanilla itself uses) with the CK2 id kept in a comment;
- a `holder` dated **before its own birth** is kept, with the birth date in a
  comment;
- a `holder` dated **after its own death** is kept and warned about: dropping
  it would leave the title unheld and the next CK2 holder inherits nothing
  (19 such CK2 entries, which ck3-tiger reports as `warning(history)`);
- a `liege` is dropped, with a comment, when it is not a live title, when it is
  **not a strictly higher tier** (CK3 requirement, 14 CK2 cases) or when it has
  **no living holder at that date** (CK3 ignores the line; 963 CK2 cases).

Faerûn itself is clean on the first check: all 25994 `holder` lines resolve.

### Cultural names

CK2 puts bare `<culture> = "Literal"` pairs in the title block (3314 lines,
226 distinct keys). CK3 wraps them in `cultural_names = { }`, keys them by
**name list** and takes a **loc key**. So:

- culture `x` → `name_list_x` (the convention lane `cultures-religions` uses);
- the **7 culture-*group*** keys (`dwarf_group`, `calishite_group`,
  `giant_group`, `giantkin_group`, `gith_group`, `maztican_group`,
  `mordrin_group`) are expanded to every member culture of the group, because
  CK3 has no group-level name list;
- the literal becomes `cn_fae_<slug of the literal>`, shared by every title and
  culture that uses the same name — 3314 lines collapse to **718** keys — and
  is written to `localization/english/fae_title_cultural_names_l_english.yml`
  together with the `_adj` key CK3 derives from it.

### Coats of arms

Per `docs/DECISIONS.md`: every live title with a CK2 colour gets the
placeholder vanilla itself ships as `default` — `pattern_solid.dds` tinted with
the CK2 map colour (`color1=rgb { r g b }`, `verified` legal). The 3438 CK2
`gfx/flags/*.tga` are **not** converted; the title → flag list goes to
`docs/evidence/ck2_flags.csv` for a later lane.

### Bookmarks

CK2's `selectable_character` nests the character data inside an
`id`/`age`/`title` wrapper; CK3's `character = { }` is flat and wants a birth
date, a `type = male|female` (which CK2 keeps on the character) and a `group`.
The converter takes the birth date from `history/characters` rather than
`start_date - age`, because CK2's age is often cosmetic ("This seems to be
simply graphical age", Faerûn `common/bookmarks/00_bookmarks.txt:57`).

A `selectable_character` whose title is not live, or whose id is not in CK2
`history/characters`, is dropped with a comment naming the reason.

**`common/bookmark_portraits` cannot be left empty** — that corrects
`docs/mapping_world.md` gotcha 8. ck3-tiger reports
`fatal(crash): bookmark portrait for <name> not found`, "This causes a crash in
CK3 1.13". The step writes a minimal placeholder per character, named after the
character's `name` value the way vanilla names its 332 files; the real files
come from the in-game `dump_bookmark_portraits` console command.

Vanilla's three bookmark files name vanilla titles and characters, so the step
also writes an **empty file at each of their paths** (`00_bookmarks.txt`,
`00_bookmark_groups.txt`, `00_challenge_characters.txt`) to shadow them by
filename — no `replace_path` needed (`docs/output_bootstrap.md` fact 0.2).

### What moved out of this lane

- **`terrain`** is not written to `history/provinces`: `common/province_terrain`
  owns the bulk data and the `map` step already emits it.
- **`max_settlements`** is dropped: in CK3 the number of baronies in a county
  *is* the holding-slot count.
- **`buildings`** has no input at all — Faerûn writes no CK2 building history
  (`verified` 0 occurrences).
- **`holy_site`, `caliphate`, `controls_religion`, `pentarchy`** are comments
  here and land in `docs/evidence/title_holy_sites.csv`; CK3 inverts the
  relation and lane `cultures-religions` owns the faith side.
- **`title`, `title_female`, `foa`, `title_prefix`, `name_tier`** are comments
  and land in `docs/evidence/title_flavorization.csv`; their CK3 home is
  `common/flavorization`, which no step owns yet.
- **CK2 `effect = { }` blocks** (437) are kept commented rather than ported:
  porting CK2 effect syntax is lane `events-decisions`, and an unknown effect
  id is a hard CK3 error.

### Localisation hand-off

CK2 title names keep their keys (`d_cormyr` in CK2 is `d_cormyr` in CK3), so
lane `loc` needs no rename for them — except that Faerûn's CK2 localisation has
**zero `*_adj` keys** while CK3 reads a title's adjective from `<title>_adj`.
`scripts/build_loc_key_renames_titles.py` writes
`mappings/loc_key_renames_titles.csv` (`ck2_key,ck3_key`, 5667 rows): one
`_adj` copy per live title, plus the bookmark name/desc keys (CK3 uses the
bookmark's own database key) and the bookmark character names. A CK2 key on
several rows means "emit the same text under each CK3 key".

## Validation

`docs/evidence/tiger_titles.txt`, regenerated by
`scripts/tiger_titles_check.py`. The committed report is the
`descriptor,map,titles,history_titles` output validated `--mod` (as built, no
step re-run), with a stub `history/characters` so the `characters` lane's
classes do not mask ours: **20 diagnostics owned by this lane** out of 31906
total, and the
`error(missing-item): title d_X not defined in common/landed_titles/` class
that dominated `docs/evidence/tiger_2026-09-07.txt` (729 of 729 errors) is
**gone**.

What is left, and why:

| count | class | why |
|---|---|---|
| 19 | `warning(history)` | CK2 keeps a dead ruler as holder until the next succession entry. Kept on purpose (see *Holder / liege integrity*). |
| 1 | `error(history)` | one residual `liege` whose holder ck3-tiger considers dead earlier than CK2's own death date. |

Add the `bookmarks` step and 133 more become ours: `warning(missing-file)` for
`gfx/interface/bookmarks/<key>.dds` and two more per bookmark. No CK2 source;
needs a gfx lane (open question 4).

Everything else belongs to `characters` (the undefined character ids and the
dynasty/CoA classes), `cultures-religions` (12079 faith / culture / name-list
ids, until that lane's output is in the same mod) or `loc` (3525 title keys and
126 `_article` tips).

## Open questions for the coordinator

1. **Dynasty id shape.** The lane brief says character *and dynasty* ids are
   `fae_<ck2_id>`; `docs/mapping_world.md` §"Id spaces" says dynasties are
   `fae_dyn_<ck2_id>`. The bookmarks step writes `fae_dyn_<id>`. If lane
   `characters` chooses `fae_<id>`, one line in
   `src/ck2ck3/titles/bookmarks.py` changes.
2. **Dynasty coats of arms.** `common/coat_of_arms/coat_of_arms` is this
   lane's subtree, but the 80 `coa fae_dyn_* not defined` warnings are about
   *dynasty* CoAs, which lane `characters` produces. Either that lane gets a
   second file in the same folder (and the one-owner-per-subtree rule needs a
   carve-out) or this step generates dynasty placeholders from data it does not
   own.
3. **DLC-gated `nomad_government`.** 20 titles get it, from CK2
   `nomadic_tribal_government`. `mappings/government_map.csv` notes that CK3
   gates it behind `has_mpo_dlc_trigger` (Khans of the Steppe) and suggests
   falling back to `tribal_government` when the DLC cannot be assumed. Needs a
   project-level "which DLCs do we assume" decision.
4. **Bookmark art.** 17 bookmarks × 3 missing `.dds` + the group icon = 133
   warnings. Ship placeholder art, or drop the 16 non-default bookmarks?
5. **`[map] title_scaffolding`.** The `map` step's throwaway one-barony-per-
   province layer is now off by default and gated behind that key, since this
   lane owns the three folders. Nothing sets it; delete the code path in a
   later cleanup, or keep it as a map-only debug aid?
