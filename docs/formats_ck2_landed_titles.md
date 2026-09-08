# CK2 `common/landed_titles` — keys, and how cultural names are spotted

Evidence for `src/ck2ck3/titles/ck2read.py` (the reader was
`src/titles/all_titles.py` until lane `titles-history` replaced it). Measured
on the Faerûn clone (`Faerun/Faerun/common/landed_titles/*.txt`, 7 files) on
2026-09-07, `verified` unless marked otherwise. Reproduce with
`uv run scripts/survey_ck2_titles.py`.

## Shape

Titles nest by tier: `e_*` → `k_*` → `d_*` → `c_*` → `b_*`. A title block mixes
CK2 keywords with **cultural name overrides**, and both are plain
`key = value` lines, so telling them apart needs a keyword list.

Counted in Faerûn: 65 empires, 267 kingdoms, 979 duchies, 2132 counties,
15356 baronies (18799 titles across the 7 files, `titular_titles.txt` and
`mercenaries.txt` included). The 2132 counties match
`scripts/faerun_barony_stats.py`.

## Block-valued keys

Only five, in the whole mod: `color` (3443), `color2` (3364), `allow` (321),
`male_names` (2), `female_names` (1). Colours are untagged
(`color={ 0 0 0 }`, `common/landed_titles/landed_titles.txt:10`); CK3 also
allows `rgb { … }` / `hsv { … }`, which the reader accepts too.

## Scalar-valued keywords

Every scalar key that is **not** a culture id, with the mod-wide count where it
is interesting:

`assimilate`, `caliphate`, `can_be_claimed`, `can_be_usurped`,
`capital` (1300), `controls_religion`, `creation_requires_capital`,
`culture` (378), `dignity` (92), `dynasty_title_names`,
`extra_ai_eval_troops`, `foa` (195), `graphical_culture`, `holy_order`,
`holy_site` (470), `independent` (150), `landless` (187),
`location_ruler_title`, `mercenary` (136), `mercenary_type` (156),
`monthly_income`, `name_tier`, `pirate`, `primary` (190), `rebel`,
`religion` (183), `short_name` (133), `strength_growth_per_century` (154),
`title` (346), `title_female` (343), `title_prefix`, `tribe`.

This is the list in `ck2ck3.titles.ck2read.SCALAR_KEYWORDS`.

## Cultural names

**Any other scalar key inside a title block is a culture or culture-group id,
and its value is that culture's name for the title.** 3313 such lines in
Faerûn, e.g. `green_elf = Cormanthor` (141 `green_elf` lines, 137 `moon_elf`,
137 `sun_elf`, 134 `astral_elf`, …). Culture-group keys look the same
(`dwarf_group`, `calishite_group`, `maztican_group`, `gith_group`,
`giant_group`, `giantkin_group`, `mordrin_group`).

Cross-check: Faerûn defines 421 cultures in `common/cultures/*.txt`, and every
non-keyword scalar key of `landed_titles` is one of those 421 ids or a
`*_group` name. So the keyword list above is complete for this mod (`assumed`
for other CK2 mods: they may use keywords Faerûn never touches, in which case a
keyword would be misread as a culture id — lane `titles-history` should
validate `cultural_names` keys against the culture list it loads anyway).

The previous regex-parser-based reader collected cultural names only from
*block*-valued keys and therefore found **none** of these 3313 names.

## What the reader keeps

`Ck2Title` has fields for the keys with a CK3 home; every other scalar keyword
lands in `Ck2Title.keywords` and every non-cultural block in `Ck2Title.blocks`
verbatim, so nothing is dropped silently and the writer can decide per key
(`docs/step_titles.md`, "Nothing is dropped silently"). `capital`'s trailing
comment is kept in `capital_comment` — in Faerûn it usually names the province,
and the value itself is a **province id**, not a title.

Counts re-measured with this reader: 65 e_, 267 k_, 979 d_, 2132 c_, 15356 b_
= 18799, and 3314 cultural-name lines over 226 distinct keys, 7 of which are
culture *groups* (`docs/formats_titles.md` §7).
