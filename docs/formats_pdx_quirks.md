# Paradox script — grammar and real-world quirks

Evidence for `src/ck2ck3/pdx/`. All items `verified` on 2026-09-07 against the
Faerûn clone (`Faerun/Faerun`, 6437 script files, 37 MB) and CK3 1.19.0.6
(`Crusader Kings III/game`, 3785 script files, 116 MB) unless marked
`assumed`. Reproduce with:

```
uv run scripts/pdx_scan.py                                   # Faerun
uv run scripts/pdx_scan.py "<CK3>/game" --roundtrip 4000     # CK3 vanilla
```

Result at the commit that added this file: **Faerûn 6437/6437 parsed, 0
failures, 0 round-trip failures, 5.2 s; CK3 3785/3785 parsed, 0 failures, 0
round-trip failures, 14.4 s.**

## 1. Grammar the parser accepts

| construct | example | evidence |
|---|---|---|
| `key = value` | `culture = illuskan` | `history/provinces/1 - Waterdeep.txt:16` |
| comparison ops `== != < > <= >=` | `society_rank == 3` | `common/scripted_triggers/00_scripted_triggers.txt:234` |
| `?=` (CK3 only) | `scope:secret_target ?= scope:secret_owner` | CK3 `common/secret_types/dynastic_cycle_secrets.txt:43`; 0 in Faerûn |
| nested blocks | `limit = { ROOT = { … } }` | everywhere |
| bare value list | `severe_winter = { 4 10 17 … }` | `map/climate.txt:1` |
| bare identifier list | `allow = { a b }` | `common/landed_titles/landed_titles.txt` |
| mixed block (items + nodes) | `x = { 1 key = v }` | CK3 `common/coat_of_arms/coat_of_arms/01_random_templates.txt:3` |
| anonymous block items | `x = { { a = 1 } { a = 2 } }` | CK3 `common/bookmark_portraits/bookmark_adventurers_almos_arpad.txt:124` |
| quoted strings, `\"` escapes, `""` | `set_name = ""` | `common/cb_types/shou_lung_cb_types.txt:1545` |
| negative and fractional numbers | `fertility = -0.25` | `common/traits/roleplaying_traits.txt:17` |
| dates as a distinct type | `1355.07.28 = { holder = 1 }` | `history/titles/c_thingulphar.txt:10` |
| `yes` / `no` booleans | `landless = yes` | `common/landed_titles/titular_titles.txt` |
| `@var = 5` / `@var` references | `@lifestyle_bonus_tier_1_value = 0.15` | CK3 `common/accolade_types/04_ep2_eminent_attributes.txt:12`; 0 in Faerûn. Kept symbolic, `pdx.resolve()` substitutes |
| `rgb {}` / `hsv {}` / `hsv360 {}` | `color = rgb { 20 30 40 }` | CK3 `common/coat_of_arms/coat_of_arms/01_landed_titles.txt:5344`, `common/culture/cultures/00_akan.txt:61`, `common/named_colors/default_colors.txt:13`. Faerûn only uses untagged `color={ 0 0 0 }` (`common/landed_titles/landed_titles.txt:10`) |
| comments, preserved | `#Owol[5405]` | `history/titles/c_thingulphar.txt:9` |

## 2. Quirks found in the wild, and how each is handled

### 2.1 CR-only line endings — `history/titles/k_horthgars_horde.txt:1`
The whole file is one physical line terminated by bare `\r` (classic Mac).
A `#` comment on such a line would swallow the rest of the file, which is
exactly what the regex parser did. Handled two ways: `read_text()` normalises
`\r\n` and lone `\r` to `\n`, and the tokenizer itself treats `\r` as a line
break. Only file of the 6437 affected.

### 2.2 A comment after a closing brace on the same line — `history/titles/c_thingulphar.txt:9`
`1324.1.1={holder=30928} #Owol[5405]` — the comment documents the *block*, not
its first child. The parser attaches it as the node's `trailing_comment`, and
the writer emits it after the closing brace. A comment on the *opening* line
(`potential = { FROMFROM = { … } #`, `common/buildings/unique_city_buildings.txt:20`)
belongs to the first inner entry instead. Getting this backwards was the only
round-trip bug the 6437-file sweep found.

### 2.3 A bare `#` as a whole comment — `common/buildings/unique_city_buildings.txt:20`
Empty comment text. Kept verbatim; an empty *string* in a comment list means
something else (a preserved blank line, see 2.9), so `"#"` and `""` are
distinct.

### 2.4 `@` inside an identifier — `common/cb_types/pagan_cbs.txt:229`
`set_character_flag = won_war@event_target:defender_target`. In CK2 `@` is an
ordinary identifier character; only a *leading* `@` marks a script variable.
41 Faerûn files contain `@` and none of them is a variable definition.

### 2.5 An operator used as a value — CK3 `events/diarchy_events/vizierate_events.txt:109`
`OPERATOR = <=` passes a comparison operator as a trigger parameter. Parsed as
an `Operator` value so the writer emits it bare instead of quoting it. Absent
from Faerûn; it is why the CK3 sweep matters.

### 2.6 Exponent floats — CK3 `common/script_values/00_faction_values.txt`
`-0.00003` is a float whose `repr()` is `-3e-05`. Paradox script has no
exponent syntax, so the writer always emits plain decimals; the tokenizer
accepts exponent form on input anyway.

### 2.7 `scripted_trigger <name> = { … }` — CK3 `events/diarchy_events/vizierate_events.txt:106`
Two words before the `=`. The tree records this as a bare `Item`
(`scripted_trigger`) followed by a `Node` (`<name> = { … }`): the pair survives
a round trip but the association is not modelled. Fine for the converter, which
never rewrites inline CK3 scripted triggers. Revisit if a lane needs to edit
them.

### 2.8 Mixed encodings in one mod
Faerûn: 6274 files decode as UTF-8, 163 as Windows-1252. Sniffing (utf-8-sig
first, cp1252 on failure, with a warning) is therefore mandatory; a fixed
`encoding=` would corrupt one group or the other. CK3 vanilla is also mixed
(3722 / 63).

### 2.9 Blank lines
A blank line before an entry is kept as `Entry.blank_before`. A blank line
*between two comments of one group* is kept as an empty string inside
`leading_comments`, so `# c_waterdeep` / blank / `# County Title`
(`history/provinces/1 - Waterdeep.txt:1-3`) comes back unchanged. A blank line
before the first entry of a block is dropped on purpose, so the round trip is
idempotent.

### 2.10 No space between a colour tag and its brace — CK3 `common/governments/00_government_types.txt:320`
`color = rgb{ 85 207 198 }`. The tokenizer never folds `{` into a word, so this
parses like the spaced form. The writer always emits the spaced form.

### 2.11 Zero-padded date keys — `history/titles/c_thingulphar.txt:10`
`1355.07.28 = { … }`. A key is always a string and is written back verbatim, so
the padding survives; date *values* become `Date` objects and are written
without padding.

## 3. Quirks the assessment expected but Faerûn does not have

Searched and **not found** in `common/ history/ decisions/ events/ map/`:

- stray `}` with no matching `{` (0 occurrences — the parser has a
  `stray_close_brace` recovery in lenient mode, unexercised on real data)
- `key =` with no value (0 occurrences — `missing_value` recovery, likewise)
- multi-line quoted strings (0 lines with an odd quote count outside comments)
- `\"` escapes (0 occurrences in Faerûn; supported for CK3)
- `[[ … ]]` localisation-style promotion inside script (0 occurrences)
- `!` or `?` outside a comment or an operator (0 occurrences), which is what
  lets the tokenizer exclude them from identifier characters

Because none of these appear, the parser defaults to **strict**: an oddity is a
`PdxSyntaxError` with `file:line:col`. Pass `lenient=True` to collect them on
`Document.problems` instead. Nothing is ever skipped silently.

## 4. Performance

`scripts/pdx_scan.py` on this machine: Faerûn `common/` + `history/` +
`decisions/` + `events/` + `map/` = 6437 files / 37.1 MB in **5.2 s**
(target was 60 s). CK3 vanilla 3785 files / 116.2 MB in 14.4 s. One master
regex, one pass, no per-character Python loop.
