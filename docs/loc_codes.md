# CK2 text codes → CK3 data functions

The mapping table lives in `src/ck2ck3/loc_codes.py`; this file is its
evidence and its coverage number. Regenerate the frequency table with

```
uv run scripts/collect_ck2_loc_codes.py            # docs/evidence/ck2_loc_codes.csv
uv run scripts/collect_ck2_loc_codes.py --unknown marker   # the strict variant
```

## Method

Faerûn's 120 CSVs contain **8,632 distinct `[...]` codes in 141,345
occurrences** (`verified` 2026-09-07). A per-string table would never converge,
so the converter maps *structurally*: a code is a scope chain plus a terminal
function, and each half is mapped on its own. Coverage is then measured per
occurrence.

CK3 sources used, in order of authority:

1. real usage in `game/localization/english` (CK3 1.19) — quoted per row below;
2. the data-function names embedded in `ck3-tiger` v1.19.0
   (`~/.local/share/ck3-tiger/ck3-tiger-linux-v1.19.0/ck3-tiger`), used only to
   confirm that a name exists;
3. `game/gui/preload/textformatting.gui` for the text formats;
4. `game/common/customizable_localization/` for the names a `Custom()` call may
   use.

The paradox wiki page on localisation is behind a bot challenge from this
machine (`curl` returns a JavaScript interstitial), so nothing here rests on it.

## Coverage

| status | occurrences | share | what it means |
|---|---|---|---|
| `mapped` | 61,369 | 43.4 % | in the table below |
| `custom` | 41,554 | 29.4 % | a `customizable_localisation` Faerûn itself defines → `Custom('name')` |
| `named_scope` | 25,893 | 18.3 % | a CK2 event target; CK3 references saved scopes the same way |
| `custom_unverified` | 3,996 | 2.8 % | a `Get*` that is neither a CK2 engine built-in nor defined by the mod, so in CK2 it is a *vanilla* custom localisation → emitted as `Custom('name')` and warned |
| **converted** | **132,812** | **94.0 %** | |
| `unmapped` | 8,017 | 5.7 % | a CK2 mechanic CK3 does not have → `<!CK2:…!>` |
| `language_helper` | 516 | 0.4 % | a CK2 French/German/Spanish inflection built-in → `<!CK2:…!>` |

**94.0 %, not 95 %** — and the missing point is not reachable without
inventing content, which the charter forbids (`docs/PROJECT.md`). The whole
residual is CK2 mechanics CK3 removed:

| cause | occurrences | share |
|---|---|---|
| council jobs (`Root.job_marshal`, `GetJobTitle`) — CK3 has court positions | 1,460 | 1.03 % |
| plots (`PlotTarget`, `GetPlot`) | 899 | 0.64 % |
| societies (`Root.Society`, `GetSocietyRank`) | 861 | 0.61 % |
| offmap powers (`Offmap`, `shou_lung.Ruler`, `Governor`) | 1,466 | 1.04 % |
| a title's previous holder (`OriginalOwner`) | 684 | 0.48 % |
| French/German/Spanish inflection built-ins | 516 | 0.37 % |
| society and bloodline founders (`Founder`) | 447 | 0.32 % |
| province saints | 276 | 0.20 % |
| guardian, regent, host, heir scopes | 765 | 0.54 % |
| the rest (long tail of one-off chain steps) | ~1,159 | 0.82 % |

Measured on the english column alone the numbers are 92.1 % converted of
38,753 occurrences; english has a smaller share of `custom` calls and a larger
share of plain names.

## Scopes

CK3 localisation has `ROOT`, `THIS`, `PREV`, `SCOPE`, `GetPlayer` and every
saved scope by its own name. It has **no `FROM`** — 0 uses in the whole of
`game/localization/english`.

| CK2 | CK3 | evidence |
|---|---|---|
| `Root` | `ROOT.Char` | `[ROOT.Char.GetSheHe]`, `traits_l_english.yml` |
| `This` | `THIS.Char` | `[THIS.Char.GetCulture.GetName]` |
| `Prev` | `PREV.Char` | `[PREV.…]`, 4 uses in english loc |
| `Player` | `GetPlayer` | `[Activity.GetGuestDescription( GetPlayer )]` |
| *(no scope)* | `ROOT.Char` | CK2 defaults a bare code to Root |
| `From` | `ck2_from` | **convention**, see below |
| `FromFrom` | `ck2_fromfrom` | idem (`FromFromFrom`, `PrevPrev`, … likewise) |
| anything else | kept verbatim | a CK2 event target; `[lover.GetHerHis]`, `elder_events_l_english.yml` |

### `From` has no CK3 loc scope

30 % of Faerûn's codes are `From…`. CK3 event text can only reach ROOT and
saved scopes, so the converter rewrites `From` to a saved scope with a fixed
name — `ck2_from`, `ck2_fromfrom`, … — and warns once per code
(37,054 occurrences, 166 distinct codes on the current Faerûn). **The event
port has to `save_scope_as = ck2_from` at the top of every converted event**,
or those strings resolve to nothing. That is the one hand-off this lane leaves
open, and it is in `docs/DECISIONS.md`.

### Chain steps

| CK2 | CK3 | evidence |
|---|---|---|
| `Liege` | `GetLiege` | `[ROOT.Char.GetLiege.GetShortUINamePossessiveNoTooltip]` |
| `TopLiege` | `GetTopLiege` | `[ROOT.Char.GetTopLiege.GetTitleAsName]`, `succession_laws_l_english.yml` |
| `Religion`, `TrueReligion` | `GetFaith` | `[actor.GetFaith.GetName]` |
| `RelHead` | `GetFaith.GetReligiousHead` | `[old_faith.GetReligiousHead.GetTitledFirstName]`, `major_decisions_iberia_north_africa_l_english.yml` |
| `Culture` | `GetCulture` | `[actor.GetCulture.GetName]` |
| `Capital` | `GetCapitalLocation` | `[liege.GetCapitalLocation.GetName\|V]`, `court_positions_l_english.yml` |
| `Location` | `GetLocation` | `[Character.GetDomicile.GetLocation.…]`, `my_realm_window_l_english.yml` |
| `PrimaryTitle` | `GetPrimaryTitle` | `[TARGET_CHARACTER.GetPrimaryTitle.GetBaseName]` |
| `Spouse` | `GetPrimarySpouse` | `[councillor.GetPrimarySpouse.GetShortUIName\|U]`, `council_l_english.yml` |
| `Father`, `Mother` | `GetFather`, `GetMother` | `[CHARACTER.GetFather.GetCulture.GetNameNoTooltip]` |
| `Dynasty`, `House` | `GetDynasty`, `GetHouse` | `[…GetHouse.GetBaseNameNoTooltip]`, `government_l_english.yml` |
| `Holder`, `Owner` | `GetHolder` | `[Province.GetTitle.GetHolder.GetShortUIName\|U]` |

`Society`, `Offmap`, `Ruler`, `Governor`, `PlotTarget`, `Plot`, `Founder`,
`Province`, `OriginalOwner`, `Guardian`, `Regent`, `Host`, `Heir`,
`province_saint` and `job_*` / `Job_*` have no CK3 counterpart. Anything routed
through them is marked, never guessed.

## Functions

Only the CK2 **engine built-ins** are tabled; everything else is a
customizable localisation and becomes `Custom('name')`. CK2 spells
capitalisation with a `Cap` suffix, CK3 with `|U`
(`[ROOT.Char.GetSheHe|U]`, `traits_l_english.yml`), so every `XxxCap` is
derived automatically.

| CK2 | CK3 | note |
|---|---|---|
| `GetFirstName`, `GetName` | same | |
| `GetTitledFirstName` | same | `[recipient.GetTitledFirstName]` |
| `GetTitledName`, `GetBestName`, `GetTitledFirstNameNoRegnal` | `GetTitledFirstName` | `assumed`: CK3 has no title-plus-full-name form |
| `GetFullName` | `GetName` | CK3's `GetName` is the full name |
| `GetShortName`, `GetTitledNameWithNick` | `GetShortUIName` | `[TARGET_CHARACTER.GetShortUIName]` |
| `GetFirstNameWithNick` | `GetFirstName` | CK3 folds the nickname in |
| `GetSheHe`, `GetHerHis`, `GetHerHim`, `GetHerselfHimself` | same | `[CHARACTER.GetHerselfHimself]`, `secrets_l_english.yml` |
| `GetHeShe`, `GetHisHer`, `GetHimHer`, `GetHimselfHerself` | the female-first form | CK3 only ships one order |
| `GetManWoman`, `GetWomanMan` | `GetWomanMan` | `[bg_opponent.GetWomanMan]` |
| `GetMenWomen` | `GetWomenMen` | `[CHARACTER.GetWomenMen]` |
| `GetLordLady`, `GetLadyLord` | `GetLadyLord` | `[root_scope.GetLadyLord]`, `conqueror_l_english.yml` |
| `GetHusbandWife`, `GetWifeHusband` | `GetWifeHusband` | `[TARGET_CHARACTER_2.GetWifeHusband]` |
| `GetSubjectPronoun` / `GetObjectPronoun` / `GetPossPronoun` / `GetReflexivePronoun` | `GetSheHe` / `GetHerHim` / `GetHerHis` / `GetHerselfHimself` | `assumed` |
| `GetTitle`, `GetRulerTitle` | `GetTitleAsName` | `[ROOT.Char.GetTitleAsNameNoTooltip]` |
| `GetTier` | `GetTier` | |
| `GetAdjective` | `GetAdjective` | `[GOVERNMENT_TYPE.GetAdjective]` |
| `GetHighGodName` | `GetFaith.HighGodName` | 187 uses in english loc |
| `GetRandomEvilGodName` | `GetFaith.EvilGodName` | `[…GetFaith.EvilGodName]` |
| `GetRandomGodName` | `GetFaith.HighGodName` | **lossy**: CK2 picked at random out of a pantheon, CK3 faiths have one high god |
| `GetGroupName` | `GetReligion.GetName` | `[actor.GetReligion.GetName]` — CK2's religion group is CK3's religion, CK2's religion is CK3's faith |
| `GetPriestTitle` | `GetFaith.PriestNeuter` | `[ROOT.Char.GetFaith.PriestNeuterPlural]` |
| `GetScriptureName` | `GetFaith.ReligiousText` | `[CHARACTER.GetFaith.ReligiousText]` |
| `GetHouseOfWorship` | `GetFaith.HouseOfWorship` | `[ROOT.Char.GetFaith.HouseOfWorshipPlural\|U]` |
| `GetCollectiveNoun` | `GetCulture.GetCollectiveNoun` | `[TARGET_CHARACTER.GetCulture.GetCollectiveNoun]` |
| `GetDynName`, `GetOnlyDynastyName`, `GetHouseName` | `GetHouse.GetBaseName` | a CK2 dynasty shows as a CK3 house |
| `GetSonDaughter`, `GetDaughterSon` | `Custom('DaughterSon')` | CK3 vanilla custom loc; CK3's order is daughter/son |
| `GetSisterBrother`, `GetBrotherSister` | `Custom('SisterBrother')` | `[confusion_target.Custom('SisterBrother')]` |
| `GetFatherMother`, `GetMotherFather` | `Custom('MotherFather')` | |
| `GetKingQueen` | `Custom('QueenKing')` | |
| `GetMasterMistress` | `Custom('MistressMaster')` | |
| `GetLadLass` | `Custom('LassLad')` | |
| `GetEmperorEmpress`, `GetPrincessPrince`, `GetBoyGirl` | *marked* | CK3 has no such gendered word |
| `GetSocietyRank`, `GetJobTitle`, `GetPlot` | *marked* | the mechanic is gone |

## Colours, icons, variables

CK2 `§X … §!` becomes a CK3 text format `#name … #!`. CK3's names are defined
in `game/gui/preload/textformatting.gui`, so the mapping keeps the colour:

| CK2 | CK3 | CK3 format resolves to |
|---|---|---|
| `§Y` (25,971) | `#M` | `mixed_value` → `color_yellow` |
| `§R` (2,349) | `#N` | `negative_value` → `color_red` |
| `§G` (1,949) | `#P` | `positive_value` → `color_green` |
| `§W` (1,212) | `#V` | `value` → `color_white` |
| `§Z` (363) | `#low` | `color_dark_gray` |
| `§M` (337) | `#G` | the purple italic format |
| `§L`, `§l` (196) | `#L` | `game_link` → underline |
| `§B`, `§b`, `§c` (96) | `#E` | `explanation_link` → `color_light_blue` |
| `§T` | `#T` | `tooltip_heading` |
| `§u`, `§U` | `#UND` | `underline` |
| `§h` | `#high` | `color_white` |
| `§!` (29,931) | `#!` | end of format |
| `§` + punctuation (28) | dropped | not a colour code; CK3 would print it raw |

CK3 needs a space between the tag and the text (`#EMP all#!` in
`traits_l_english.yml`), which the converter inserts.

`$VAR$` and `$VAR|fmt$` pass through unchanged — CK3 uses the same syntax
(`$RANSOM_COST|0$`, `interactions_l_english.yml`).

`£n£` icons are marked: Faerûn only uses the numeric CK2 dice icons
(`£1£`…`£5£`, 22 rows) and CK3's `@name_icon!` set has no counterpart.

## The marker

Anything with no CK3 form becomes `<!CK2:Root.Society.GetName!>` — visible in
game, greppable, and deliberately **without square brackets**: CK3 parses
`[...]` anywhere in a value, so a passed-through code would print a data-function
error instead of text. Counts land in the run log and the full per-code table in
`docs/evidence/ck2_loc_codes.csv`.
