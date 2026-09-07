# CK2 localisation CSV and CK3 localisation YAML — formats and quirks

Facts about the two file formats and every quirk the Faerûn CSVs actually
contain, with `file:line` evidence. Regenerate the evidence with
`uv run scripts/survey_faerun_loc.py` (writes `docs/evidence/loc_quirks.md`);
validate generated output with `uv run scripts/check_ck3_loc.py <mod>`.
Reader/writer: `src/ck2ck3/csvloc.py`. Step: `src/ck2ck3/steps/loc.py`.
Text codes: `docs/loc_codes.md`.

All counts `verified` 2026-09-07 on `Faerun/Faerun/localisation`: **120 csv,
112,427 non-blank lines, 109,018 distinct keys**.

## The CK2 side

One semicolon-separated file per topic, Windows-1252, CRLF, columns fixed by
position:

```
###ANSI;;;;;;;;;;;;x
#CODE;ENGLISH;FRENCH;GERMAN;;SPANISH;;;;;;;x
c_abaltrer;Abaltrer;Abaltrer;Abaltrer;;Abaltrer;;;;;;;x
```

- Column 0 is the key, 1 english, 2 french, 3 german, 5 spanish; column 4 is
  unnamed in every Faerûn header and the last column is a literal `x` marker
  (`CK2_COLUMNS` in `csvloc.py`).
- Two header shapes: 63 files use the 13-field header, 20 the 15-field one
  (`Faerun/Faerun/localisation/00_ui.csv:1`), **39 files have no `#CODE` line
  at all** and the column order has to be assumed
  (`Faerun/Faerun/localisation/000_generalvanillaloc.csv`).
- Load order is filename order and the **last definition wins**; 1,265 duplicate definitions
  cover 1,243 keys (`d_bregan_daerthe` in `0000_titles.csv` and
  `BR_events_localisation.csv`).
- Language fill rate: english 100.0 %, french / german / spanish 70.1 % each.
  An empty cell means "fall back", so the converter writes the english text
  into the other language's file rather than omitting the line — a CK3 key
  with no line prints the raw key.

### Quirks, with evidence

| quirk | rows | evidence |
|---|---|---|
| `$VAR\|fmt$` variable with a format suffix | 6,023 | `000_shou_lung.csv:43` `$OFFMAP\|Y$` |
| `\n` as a literal two-character line break | 4,192 | `000_generalvanillaloc.csv:237` |
| `#` comment line inside the body | 1,955 | `0000_titles.csv:1` `###ÄNSI;;;…` (a mis-encoded `###ANSI`) |
| row with more fields than the header (trailing `;` padding) | 1,720 | `0000_titles.csv:5421` |
| unescaped `"` inside the text | 768 | `000_generalvanillaloc.csv:304` |
| `;` **inside** the text, shifting every later column | 129 | `000_shou_lung.csv:1162` — CK2 truncates at the `;` and so does the converter |
| key defined twice in the same file | 101 | `culturesNreligions.csv` (40 rows), `buildings.csv` (28) |
| last column is not the `x` marker | 87 | `culturesNreligions.csv:792` `…;xT=` |
| unbalanced `[` or `]` | 36 | `HolyFury.csv:530`; `EVTOPTB_HF_40093` spanish is `[From.GetTitledName` with no `]` |
| `§` followed by punctuation instead of a colour letter | 28 | `HolyFury.csv:1996` |
| `£n£` icon code | 22 | `00_ui.csv:413` `£5£` |
| row with an empty key | 17 | `000_casus_belli_changes.csv:3` `;;;;;;;;;;;;x` |
| backslash that is not `\n` | 2 | `MonksAndMystics.csv:4552` |
| whole file is valid UTF-8, not cp1252 | 1 file | `00_Nicknames.csv` |
| `[code]` containing a space | 1 | `HolyFury.csv:7544` `[de GetName]` |
| row shorter than the header | 1 | `traits_template.csv:87` `shifter;Shifter` |
| lone-CR line endings | 0 | none in localisation (they do occur in `history/`, `formats_pdx_quirks.md`) |

### Keys CK3 can never reference

23 Faerûn keys contain a character CK3's `.yml` grammar cannot carry — a space,
a `:`, a `%`, or a leftover colour code. They are CK2 interface strings with no
CK3 counterpart, so the step skips them and warns:

- `0000_titles.csv:6526` — `d_twilit_land:adj` (a typo for `_adj`)
- `00_ui.csv:358` — `Army Maintenance`, `00_ui.csv:1630` — `Effect:`
- `00_ui.csv:3769` — `Not%authorized`
- `00_ui.csv:6118`…`6126` — `§bCapital:` … `§bTax:`
- `00_ui.csv:6127`…  — `§WOMENS`, `§WProvinces`, `§WReligion`
- `text1.csv:5954` — `job_viceroy name`

## The CK3 side

One file per language and topic, **UTF-8 with a BOM**, CRLF, named
`<anything>_l_<language>.yml`. `assumed`: CK3 takes the language from the
filename suffix rather than the folder — every vanilla file agrees with its
folder, so the converter makes both say the same thing:

```
l_english:
 c_abaltrer:0 "Abaltrer"
```

- The BOM: every vanilla 1.19 file has one and the converter always writes
  one (`assumed` that CK3 refuses a BOM-less file; not worth testing by
  breaking a mod).
- One leading space before the key, then `:<version>`, then a quoted value. The
  version number is ignored for mod files; the converter writes `0`.
- Only `"` needs escaping (`\"`); a backslash is meaningful in both games, so
  it passes through — `escape_yml` in `csvloc.py` only doubles a *trailing*
  backslash, which would otherwise escape the closing quote. Evidence:
  `game/localization/english/debug_story_test_event_l_english.yml:24`.
- `#` lines are comments. The converter writes the source CSV name and the
  generated-by banner under the `l_<language>:` header.
- A leftover `[` makes CK3 try to parse a data function and print an error in
  place of the text, so the step removes unbalanced brackets (39 in Faerûn).

## Output layout

`localization/<language>/<prefix>_<source csv stem>_l_<language>.yml` — one
file per source CSV per language, so a diff of the generated mod points at the
CK2 file that produced it. Faerûn produces **480 files** (120 × 4 languages)
and **108,986 keys per language** in about 1 s.
