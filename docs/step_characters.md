# Steps `dynasties` and `characters`

Lane `characters`. Ports all 18124 Faerûn characters and 11952 dynasties to
CK3 1.19. Format facts and their evidence: `docs/formats_characters.md`.

```
uv run ck2ck3 --config configs/faerun.toml --steps dynasties,characters
uv run scripts/tiger_characters.sh          # validate with ck3-tiger
uv run scripts/verify_character_tables.py   # must print MISSES: 0
uv run scripts/survey_characters.py         # refresh the key tally
uv run scripts/build_nickname_map.py        # refresh mappings/nicknames.csv
```

## What each step owns

| step | OUTPUTS | why |
|---|---|---|
| `dynasties` | `common/dynasties`, `common/dynasty_houses`, `localization/english/fae_dynasties_l_english.yml` | the yml is the only place CK2's literal dynasty names can survive, and only this step reads `common/dynasties` |
| `characters` | `history/characters` | — |

`common/dynasty_houses` is owned but **deliberately left empty**: CK2 has no
cadet houses, and a character may reference `dynasty` directly. It is claimed
so no other lane writes it by accident. If a government needs
`noble_families` (administrative, celestial), a house per dynasty becomes a
separate decision — the mapping table already records the shape.

`dynasties` runs before `characters` and hands it the dynasty id set through
`ctx.data["dynasties"]["ck3_ids"]`. Run `characters` alone and it reads the
dynasty ids straight from CK2 instead, so the referential check never
degrades into a silent pass.

## Architecture

Rules live in `src/ck2ck3/port/`, not in the step modules, because a rule is a
pure function of a parse tree plus the tables — so every rule has a test with
a three-line CK2 fixture and no `Context`.

| module | what |
|---|---|
| `port/tables.py` | loads the six CSVs, exposes `Tables.rule/death_reason/nickname/trait` |
| `port/common.py` | `fae_id`, `BlockBuilder` (drop-to-comment), `PortReport`, the CK2 codepage marker |
| `port/characters.py` | the character converter |
| `port/dynasties.py` | the dynasty converter |
| `port/integrity.py` | referential-integrity checks |
| `port/loc_hash.py` | MURMUR3A over loc keys, collision resolution |
| `port/evidence.py` | the review sheets written into `docs/evidence/` |

### Dropping a key means commenting it, in place

The parse tree has no standalone comment entry: a comment is metadata on the
entry below it. So `BlockBuilder` holds a dropped key as a *pending* comment
and flushes it onto the next entry, or into the block's `end_comments` when it
was the last thing there. That is what makes

```
1250.1.1 = {
    # CK2: create_bloodline = { type } (CK3 has no bloodlines)
}
```

possible, and it is why a block whose every entry was dropped still round-trips.

A dropped *block* is summarised by its keys, never pasted: Faerûn's
`spawn_unit` blocks are dozens of lines.

## The tables

| file | rows | decides |
|---|---|---|
| `mappings/character_effects.csv` | 103 | per-key CK3 name and `form` (40 history, 4 dated overrides, 59 effects; 40 drop) |
| `mappings/death_reasons.csv` | 181 | `death_reason` value remap (74 exact, 78 approx, 29 fallback) |
| `mappings/nicknames.csv` | 837 | `give_nickname` value remap (81 mapped, 756 commented) |
| `mappings/vanilla_traits.csv` | 112 | CK2 vanilla trait → CK3 trait (owned by the mappings lane) |
| `docs/evidence/faerun_custom_traits.csv` | 1092 | which Faerûn traits the mod keeps (108 port + 117 race) |
| `mappings/trait_id_map.csv` | *optional* | the traits lane's dedupe post-pass |

`level` is where the key sits: `history` (a character block), `effect` (inside
an `effect = { }` block), or `dated` — a **narrow override** for the four keys
CK3 treats differently inside a dated block. A lookup tries `dated` first and
falls back to `history`, so a `dated` row exists only where CK3 differs:
`father`/`mother` need the `set_father`/`set_mother` effect form there (a bare
`father` is a tiger `structure` error) and `fertility`/`health` cannot be used
at all (`fertility` is a trigger, not an effect).

`form` is the shape the port builds. Adding a form means adding it to
`CharacterPort._shape`, to `WRAPPED_FORMS` if it needs an `effect = { }`
wrapper, and to `KNOWN_FORMS` in `tests/test_port_tables.py` — that test fails
otherwise, rather than the converter raising mid-run.

Trait conversion is two stages on purpose: the port set decides *whether* a
trait survives, then `mappings/trait_id_map.csv` decides its final id. The
second stage is a no-op while that file is absent (the `traits` lane owns it),
which is why it is a post-pass and not baked into the port set.

## Results (Faerûn, 2026-09-07)

```
dynasties   11952 dynasties in 3 files, 11951 name loc keys, 20 CK2 CoAs dropped   1.4 s
characters  18124 characters in 80 files, 47107 dated blocks,
            16874 CK2 entries commented out, 0 integrity problems                  2.2 s
```

Well inside the two-minute budget. Losses, by kind:

| kind | count | where it goes |
|---|---|---|
| trait uses dropped | 11782 of 42819 | the 867 Faerûn traits classified `comment` |
| nickname uses dropped | 821 of 1040 | `mappings/nicknames.csv`; a `nicknames` step would recover them |
| `used_for_random` | 754 | no CK3 random world |
| `coat_of_arms` | 20 | `docs/evidence/dynasty_coa_dropped.csv` |
| every other dropped key | — | `docs/evidence/characters_dropped_keys.csv`, by key and reason |

Referential integrity over the real mod: **0 problems** — no dangling
`father`/`mother`/`employer`/spouse/`killer`, every `dynasty` resolves, every
character has a birth date, no death before birth. The checks are unit-tested
against deliberately broken input (`tests/test_port_integrity.py`), because a
check that can never fail is not a check.

## Known issues for the coordinator

1. **Faerûn dynasty 15817 is defined twice** ("Zyxenel", "Phaethoxoris"). CK2
   takes the last; CK3 sees a duplicate id and tiger reports it. The converter
   keeps both and warns — a human must delete one, or an `overrides/` row must
   say which wins.
2. **Faerûn dynasty 644 has no name.** CK3 requires one; the converter warns
   rather than inventing.
3. **`configs/faerun.toml` lists `replace_path = "history"`**, which ck3-tiger
   rejects outright ("you should replace the paths under it"). Not this lane's
   file.
4. **`ck2ck3.port.loc_hash` should be promoted** out of `port/` and used by
   the `loc` lane: any mechanically minted loc key needs the MURMUR3A check
   (`docs/formats_characters.md` ss8).
5. **756 Faerûn nicknames are one cheap step away.** Nobody owns
   `common/nicknames`.
6. **`ck2ck3.port.evidence.write_csv` writes into this repository** (`docs/evidence/`)
   rather than the generated mod, mirroring `docs/evidence/last_run.md`. If that
   is the wrong place for review sheets, say so and it moves.
7. **54 Faerûn characters have a blank `name`** — 52 write `name = " "` (a
   single space; CK2 characters 35003-35054, the Yikarians, every one of them
   commented `# Lotus Emperor` — a title, not 52 distinct names) and 2 write
   `name = ""` (41775 and 42317). One character also has `set_name = ""`. CK3
   *requires* `name`, so the blank value is kept verbatim (dropping it turns a
   tiger warning into a `field-missing` error) and counted as `empty_names` in
   the run log. A human or an `overrides/` row has to supply real names — and
   for the Yikarians has to invent 52 of them, which is out per the
   no-invention rule, so it is a content decision, not a conversion one.
8. **`src/ck2ck3/pdx/encoding.py` `OUT_ENCODING` should emit a UTF-8 BOM for
   script files too** — vanilla does and tiger warns without it
   (`docs/formats_characters.md` §10). Shared code, not changed here.

## ck3-tiger

`scripts/tiger_characters.sh` runs four passes (each subtree alone, then
combined) and writes a **summary** to `docs/evidence/tiger_characters.txt`; the
full logs stay in the scratch dir because the combined pass alone is 437k
lines.

Combined pass, 2026-09-07: `fatal: 0, error: 71397, warning: 108, untidy: 15946`.
Every error is an id another lane owns:

| count | category | owner |
|---|---|---|
| 31148 | `missing-item: culture <x> not defined` | cultures-religions |
| 20377 | `missing-item: trait <x> not defined` | traits |
| 18499 | `missing-item: faith <x> not defined` | cultures-religions |
| 1171 | `unknown-field: unknown token <trait>` (dated `add_trait`/`remove_trait`) | traits |
| 113 | `missing-item: title <x> not defined` | titles-history |
| 75 | `missing-item: modifier <x> not defined` (CK2 character modifiers) | modifiers |
| 15946 | `untidy(missing-localization): missing english localization for name <x>` | loc |

Not another lane's, and not a defect: 14 `wrong-gender` (CK2 pairs a
`add_matrilineal_spouse` with a non-female target), 2 `warning(history)`
(a spouse set twice, a courtier not yet alive), 1 `exact-duplicate-item`
(dynasty 15817), 1 `warning(encoding)` (the BOM item above). All are CK2 data
faults or shared-code items, listed above.
