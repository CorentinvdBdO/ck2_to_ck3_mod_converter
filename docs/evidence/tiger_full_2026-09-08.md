# ck3-tiger over the whole generated mod, 2026-09-08 — every class, justified

Committed report: **`docs/evidence/tiger_full_2026-09-08_summary.txt`** (444 KB)
— the header, every `error`/`fatal` block verbatim, and the validator's
`--- by kind` / `--- by message` tail. The full report is 359 MB (one block per
diagnostic, 208 k warnings) and is gitignored; regenerate it with

```
scripts/validate_output_mod.sh "" docs/evidence/tiger_full_2026-09-08.txt
```

against the output of one full `uv run ck2ck3 --config configs/faerun.toml`
and re-extract the summary with `scripts/tiger_error_extract.py`
(`docs/evidence/full_run_2026-09-08.md`), ck3-tiger 1.19.0, CK3 1.19.

## Headline

- **`fatal`: 0.** The one known crash class, an empty
  `common/bookmark_portraits`, is covered: the `bookmarks` step writes 82
  placeholder files (`CLAUDE.md` invariant).
- **`error`/`fatal`: 218**, down from 3691 before this lane. Four classes went
  to zero: `missing-item` (3444 → 0), `unknown-field` (29 → 0),
  `encoding` (1 warning over 98 files → 0), and the `name list` /
  `dynasty` / `title` id mismatches inside `missing-item`.
- **`warning`: 208 389, `tips`/`untidy`: 16 088.** 197 097 of the warnings
  (94.6 %) are one thing: localisation the converter is not the owner of.

## Every remaining `error` class

| n | class | owning step | why it is accepted, or what would fix it |
|---|---|---|---|
| 174 | `error(choice)`: expected one of `AltPriestTermPlural`, … | `loc` | `[X.GetFaith.Custom('GetPietyName')]`. CK3 validates a `Custom()` after a faith promote against a **fixed** list of 110 faith custom-loc keys; CK2's faith custom loc is open-ended, so 27 distinct CK2 keys (`GetPietyName`, `GetLordSpiritualName`, …) have no slot. `[loc] unknown_codes = "custom"` deliberately emits `Custom('GetFoo')` rather than inventing text — the converter never invents content. Fixing it means the loc lane mapping each of the 27 onto a real faith key or onto a `common/customizable_localization` entry, which is a lane of its own. Cosmetic in game: the string renders as the raw key. |
| 29 | `error(localization-key-collision)`: same MURMUR3A hash | `loc` | CK3 hashes localisation keys, and two keys with one hash silently lose one of them. 29 of our 111 323 english keys collide with a **vanilla** key (`EVTOPTC_ZE_12112` vs `stewardship_domain_special.8012.desc`; `k_rashemen` vs `diplomacy_generic.0014.withhold_information.desc`). `ck2ck3.port.loc_hash` already solves exactly this for the 11 951 dynasty keys (2 resolved this run); the `loc` step does not yet run it, because renaming a title key would break the 1408 CK2 script references that resolve only because the key kept its CK2 name (`docs/DECISIONS.md`). Backlogged. |
| 14 | `error(wrong-gender)`: character is not female / male | `characters` | 8 same-sex `add_spouse` pairs (tiger counts the dated-block copies too). CK3 1.19 has no same-gender marriage and ignores the line. CK2 allowed it; Faerûn flags them itself with `Audax Validator "." Ignore_NEXT`. **Not silently emitted any more**: the port reports them as the integrity class `same-sex spouse` (`docs/evidence/characters_integrity.csv`, and the run log). Rewriting them would mean inventing a gender or dropping a marriage the source asserts. |
| 1 | `error(history)`: holder of `d_highreach` is not alive at 657.1.1 | `history_titles` | `CLAUDE.md` invariant: a `liege` needs a **living** holder at that date or CK3 ignores the line, and tiger says so ("Info: setting the liege will not have effect here"). One title of 3236. The CK2 source asserts the vassalage at a date at which its own liege has no holder; correcting it would be invention. |

## Accepted `warning` / `tips` classes

| n | class | why accepted |
|---|---|---|
| 147 063 | `warning(missing-localization)` | 131 152 are "missing english, spanish, french and german" for a key some **other** lane still owes (event strings, the 27 unconverted code families, generated `_desc` shapes). 15 909 are `dynn_fae_N` missing in the three non-english languages: the `dynasties` step writes its literal CK2 names into `fae_dynasties_l_english.yml` only, and a dynasty name does not translate. Both are the loc surface, not a broken reference. |
| 46 198 | `warning(missing-item)`: custom localization `X` not defined | The same 235 CK2 custom-loc functions as the `error(choice)` row above, in positions where tiger only warns. Every one is named with its count in `docs/evidence/ck2_loc_codes.csv`; 93.9 % of the 147 711 CK2 text codes did convert. |
| 15 945 | `untidy(missing-localization)` | Character *names* with no loc key (`Obould`, `Manshoon`, 52 blank ones). CK3 renders a bare name fine; a key would be invention. |
| 6 788 | `warning(localization)` | Mostly `The substitution parameter $CHAR$ is not defined anywhere as a key` — CK2 `$CHAR$`-style parameters filled by an event the event lane has not ported. |
| 5 696 | `warning(datafunctions)` | Unknown datafunctions (`Recipient`, `Actor`, `EvilGodName`) and promote-chain complaints (`GetLocation cannot follow a Character promote`). The 37 067 codes that need a saved scope in the converted event are the `loc` step's documented hand-off to the event lane (`docs/loc_codes.md`). |
| 1 822 | `warning(duplicate-item)`: localization is redefined | 1265 CK2 keys are defined in more than one CK2 CSV. The `loc` step keeps the **last** definition per key and says which file won (`duplicate_keys=1265` in the run log); tiger still sees both files. |
| 462 | `warning(missing-file)` | Icons. 99 bookmark illustrations + 17 bookmark icons + 17 start-screen images the `bookmarks` step references but has no art for, and 329 trait/faith icons: 168 CK2 trait icons were copied, the rest of the 407 traits and all 94 faiths have none. Art is a submod job (`../ck3_fantasy_assets`). **Accepted by the lane brief.** |
| 319 | `warning(rivers)` | 248 "river tributary (red) not joining another river" plus source/merge losses: 19 of 350 sources and 22 of 308 merges fall on a pixel the province map calls water. Owned and quantified by the `map` step (`docs/step_map_baronies.md`). |
| 143 | `tips(suggest-localization)` | **Accepted by the lane brief.** |
| 21 | `warning(history)` | 20 "`fae_N` is not alive on `N.N.N`" (a CK2 dated block after the character's own death date) + 1 duplicate spouse. Source data, not conversion. |
| 15 | `warning(bookmarks)` | The bookmark block's `culture`/`dynasty` disagrees with the character's own history at the bookmark date, e.g. `culture = lich` in the bookmark vs `vaasan` in history. CK2 states both, in two files, and they differ; the `bookmarks` step copies the CK2 bookmark and the `characters` step copies the CK2 history. Down from 92 — the other 77 were the `fae_dyn_` id bug. Worth one backlog line: prefer history and warn. |
| 4 | `warning(markup)` | `#markup should be followed by a space`, 4 CK2 strings. |
| 1 | `warning(exact-duplicate-item)` | Faerûn defines dynasty `15817` twice in one file ("Zyxenel", then "Phaethoxoris"). CK2 lets the last win, CK3 loads both. The `dynasties` step keeps both and warns (`duplicate_ids=1`) rather than choosing for the author. |

## The four cross-step bugs this pass found and fixed

Each was invisible in the producing step's own output — both halves looked
internally consistent — and each is now guarded by a test.

1. **`name_list_<culture>` vs `name_list_fae_<culture>`** — 2848
   `error(missing-item)`. `titles` minted the id without the prefix the
   `cultures` step uses. Both now go through `ck2ck3.ids.name_list_id`
   (`tests/test_cross_step_ids.py`).
2. **`fae_dyn_<id>` vs `fae_<id>`** — 80 `error(missing-item)` + 77
   `warning(bookmarks)`. `bookmarks` invented a `dyn_` infix the `dynasties`
   step does not use. Both now go through `ck2ck3.ids.fae_id`.
3. **The known-trait set** — 8308 `trait` lines commented out of
   `history/characters` that the `traits` step *did* declare. The set was
   derived from `mappings/vanilla_traits.csv` + `docs/evidence/faerun_custom_traits.csv`,
   which disagree with what the step writes: they miss the 38 traits it dedupes
   by exact CK3 id match and the 7 `status = none` vanilla traits it ports as
   new. `mappings/trait_ck2_to_ck3.csv` (550 rows, written by
   `scripts/build_trait_tables.py`) is now the authoritative table, and
   `ctx.data["traits"]` beats it when both steps run in one pass. Character
   integrity went from 8308 mismatches to 0, and all 10 138 remaining drops are
   traits the step really commented out (`verified` by re-reading the output).
4. **A holy site on a county with no barony** — 1 `error(missing-item): title
   c_barakuir not defined`. `religions` runs before `titles` and cannot ask it
   which counties survived, so it now reads the `map` step's own
   `docs/evidence/barony_set.csv` and drops the mark with a warning.

Plus, from the same report rather than a cross-step comparison:

5. **The BOM rule is by path, not by content** — 1 `warning(encoding)` over 98
   files. `OUT_ENCODING` wrote a BOM only for non-ASCII text; tiger wants one
   on *every* file under `common/` and `history/`. See
   `ck2ck3/pdx/encoding.py` for the full evidence, including which two vanilla
   databases ship BOM-less ASCII files and why that is laxity rather than a rule.
6. **Four CK3 effect names** — 29 `error(unknown-field)`. `set_dynasty` does
   not exist (`set_house` does, and no step mints houses, so it is commented);
   `add_spouse` / `remove_spouse` / `add_concubine` are dated-**history** keys
   and the effects are `marry` / `divorce` / `make_concubine`, each taking a
   `character:<id>` scope; `change_first_name` takes a localisation key, never a
   literal name. All four are rows of `mappings/character_effects.csv`.
7. **75 `add_character_modifier` values with no CK3 modifier.** The port now
   checks the value against the 6011 ids CK3 1.19 declares in
   `common/modifiers` and comments out what it cannot resolve; those names come
   from Faerûn's own `common/event_modifiers`, which no step converts.
