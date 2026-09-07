# CK3 fantasy-race implementation research

Scope: how existing CK3 total-conversion mods implement non-human races, and what a
Forgotten Realms mod (built by/for the CK2→CK3 mod converter project) could legally
reuse. Every claim is labeled `verified` (a file was read/grepped or a page fetched
during this research) or `assumed` (inferred, not directly confirmed).

Sources read:
- Elder Kings 2 (EK2), local install: `.../workshop/content/1158310/2887120253`
- Godherja: The Dying World (GH), local install: `.../workshop/content/1158310/2326030123`
- Vanilla CK3 game dir: `.../Crusader Kings III/game`
- Web: mod pages, GitHub repos, CK3 wiki (URLs inline)

---

## 1. Comparison table

| Mod | Race carrier | Portrait mechanism | Lifespan/aging | Hybrid/mixed-race resolution | License / reuse |
|---|---|---|---|---|---|
| **Vanilla CK3** | n/a (no race concept) | ethnicity (gene-weight template) + trait-forced gene overrides | none beyond human | n/a | Paradox-owned, not reusable |
| **Elder Kings 2** | Culture heritage pillar (default) **+** a per-character flag system, overridable by genetic congenital traits for some races (Tsaesci) | Custom ethnicities per race (beast/mer/misc groups) + dedicated morph genes (ears, tails, horns) that blend naturally on inheritance | Custom trait family `lifespan_1..5`/`is_immortal` + script value `ek_life_expectancy`, assigned per-race via scripted effect | Explicit scripted effect, mother-OR-father dominant chain, priority-ordered (`verified`, see §2) | `verified`: all art "remain the sole property of their original artist," not reusable without permission |
| **Godherja** | Culture heritage pillar only, with almost no gameplay data on the pillar itself | Only 1 of 5 custom "ethnicities" has a real body (skeleton, via `body_replacement`); elves (`aelfir`) are lore-only, fall back to a vanilla human ethnicity | No custom longevity mechanism found for its fantasy heritage | None found — race passes via ordinary CK3 culture inheritance only | `verified`: attribution-only credits file, no blanket license; several assets borrowed from other mods "with permission" (Elder Kings, LotR: Realms in Exile, EPE, AGOT, Princes of Darkness) |
| **LotR: Realms in Exile** | `assumed` culture/heritage (Tolkien races: Human/Elf/Dwarf/Hobbit/Orc) | `assumed` custom portraits; further races reportedly excluded due to 3D-asset/coding cost (`verified` via CK3 wiki FAQ) | not investigated | not investigated | No public source repo for mod content; only a MIT-licensed **website** repo — mod assets themselves not open |
| **A Game of Thrones (AGOT)** | n/a — no non-human playable races | Dragons handled via the ethnicity/DNA system (`verified` via CK3 wiki) | n/a | n/a | No public source repo, no stated license |
| **Princes of Darkness (World of Darkness)** | Supernatural "splats" (vampire/werewolf/mummy/changeling/demon), not races in the fantasy sense | not investigated in depth | not investigated | not investigated | Operates under Paradox's own **World of Darkness Dark Pack** fan-content agreement — covers setting IP use, not a CK3 asset-reuse grant |
| **Warcraft: Guardians of Azeroth 2** | `assumed` culture/heritage (orc/elf/undead/gnome/ogre/satyr) | Custom meshes/skins confirmed present in public GitHub repo (`gfx/models`, `gfx/skins`, `gfx/portraits/{portrait_modifiers,trait_portrait_modifiers}`) | not investigated | not investigated | **Verified**: full source publicly viewable on GitHub, but **no LICENSE file** — public visibility grants no reuse rights (all-rights-reserved by default) |
| **Forgotten Realms / Faerûn (any CK3 mod)** | — | — | — | — | **Verified: does not exist** (Steam Workshop + Paradox Mods + GitHub searches all empty as of 2026-09-07) |

---

## 2. Local evidence: Elder Kings 2

All paths relative to `/home/cvdbdo/.local/share/Steam/steamapps/workshop/content/1158310/2887120253`.

**Race carrier — culture heritage pillar with a `species_*` cultural parameter:**
- `common/culture/pillars/00_heritage.txt:271-283` — `heritage_argonian` pillar carries `parameters = { species_argonian = yes }`. Similar `species_elf`, `species_giant`, `species_khajiit`, `species_dwemer` etc. across the same file (`verified`).
- `common/traits/ek_astrology_traits.txt:356,374` and `ek_misc_traits.txt:1261,1665,1680` gate flavor content on `culture = { has_cultural_pillar = heritage_argonian }` / `heritage_dwemeri` (`verified`) — heritage is queried directly by scripts, not via a trait.

**Race carrier — per-character flags, assigned from culture then inherited:**
- `common/scripted_effects/ek_race_effects.txt:269-284` (`race_traits_effect`) — grants `race_giant`/`race_khajiit`/etc. **character flags** from `culture = { has_cultural_pillar = heritage_X }` as the default (`verified`).
- `common/scripted_effects/ek_race_effects.txt:320-367` (`race_traits_inheritance_effect`) — for **newborns**, overrides the culture default: `if scope:mother OR scope:real_father has_character_flag = race_khajiit → add_character_flag = race_khajiit`, checked in a fixed priority order (khajiit → goblinken → argonian → lilmothiit → imga), i.e. a deterministic **dominant-parent, priority-ordered** hybrid resolution, not a random blend (`verified`).
- Wiring: `events/ek_race_events/ek_race_events.txt:15-35` — `ek_race.0003` (fallback, any character missing `char_setup` flag) calls `ek_character_setup_effect`; `ek_race.0004` calls `race_traits_inheritance_effect` + `lifespan_traits_inheritance_effect`, fired from **`common/on_action/child_birth_on_actions.txt:674`** (`on_birth_child`) and from **`common/on_action/ek_game_start_misc.txt:144`** at game start (`verified`).

**Race carrier — genetic congenital trait family (used for Tsaesci, a race not covered by the flag/heritage system above):**
- `common/traits/ek_misc_traits.txt:294-441` (`##### RACIAL #####` section) — `tsaesci_1`/`tsaesci_2` (opposites of each other, `flag = tsaesci`) directly set `life_expectancy = 60/110`, `years_of_fertility`, `fertility = -0.05/-0.1`, `monthly_prestige_gain_mult`, etc. — a **vanilla-style genetic trait family** exactly like `dwarf`/`giant` in base CK3 (`verified`). No explicit `genetic = yes` key was found on these blocks in the read excerpt.

**Lifespan/aging:**
- `common/traits/ek_misc_traits.txt:441-620` (`##### LIFESPAN #####`) — generic trait family `lifespan_1`..`lifespan_5` (`flag = lifespan_N_flag`, `group = lifespan`) plus `is_immortal` flag traits, each setting `life_expectancy`/`years_of_fertility`/stat mults directly (`verified`).
- `common/script_values/ek_check_age.txt:1-40` (`ek_life_expectancy`, `ek_human_age_equivalent_calc`) — converts a character's real age to a "human-equivalent" age using the lifespan trait's `life_expectancy` value, so vanilla age-gated content (infirmity, marriage eligibility) scales correctly for long-lived races (`verified`).
- `common/scripted_effects/ek_race_effects.txt:520-900+` — race-specific weighted `random_list` blocks assign lifespan tiers per race at setup, e.g. giants biased toward `lifespan_3`/`lifespan_4` (`verified`, lines 615-616, 653-654, etc.).

**Portraits/3D:**
- `common/ethnicities/`: 50 files (`ls | wc -l`, `verified`), including race-dedicated ones: `001_ek_ethnicities_beast_argonian.txt`, `001_ek_ethnicities_beast_B_khajiit.txt`, `001_ek_ethnicities_beast_giant.txt`, `001_ek_ethnicities_beast_goblin.txt`, `001_ek_ethnicities_mer_altmer.txt`, `_bosmer.txt`, `_dunmer.txt`, `_dwemer.txt`, `_orsimer.txt`, `_falmer.txt`, `_maormer.txt`, `_ayleid.txt`, plus `misc_dremora.txt`, `misc_skeleton.txt` (`verified`).
- `common/genes/`: 17 custom gene files beyond the 8 vanilla-numbered ones, including `ek_genes_argonian_horns.txt`, `ek_genes_beast_tails.txt`, `ek_genes_beast_legs.txt`, `ek_genes_beast_features.txt`, `ek_genes_mer.txt` (elf ears), `ek_genes_tsaesci.txt`, `ek_genes_racial_accessories.txt` (`verified`).
- `common/genes/ek_genes_mer.txt:1-15` — code comment explicitly documents the design: **two separate additive morph genes** for elf ears (each capped at 0.5), specifically so that **half-elf children inherit intermediate ear length** through ordinary CK3 genetic inheritance instead of needing scripted logic — "25% full mer ears, 50% half ears, 25% no mer ears" (`verified`, direct quote). This is the mod's actual answer to physical-trait hybrid resolution: genetics, not on-birth scripting.
- `common/genes/ek_genes_beast_tails.txt:1-30` — `tail_length` morph gene with `inheritable = yes`, age-curve-modulated growth (`verified`).
- `gfx/portraits/portrait_modifiers/`: 132 files, ~50 of them race-specific headgear/clothes (`B_ek_argonian_*`, `B_ek_dunmer_*`, `B_ek_dwemeri_*`, `B_ek_goblin_*`, `B_ek_orc_*`, etc.) (`verified`).
- 3D assets: 2,227 `.mesh` files total in `gfx/models` (`verified`, `find … | wc -l`); includes race-dedicated meshes such as `unit_argonian_infantry_01`, `unit_dunmer_infantry_02`, `unit_altmer_infantry_0{1,2,3}`, `unit_khajiit_infantry_0{1,2}`, and a `bridge_khajiit.mesh` map asset (`verified`, sample listing).

**License/credits:**
- `credits.txt:561-568` (disclaimer section) — **verified, direct quote**: *"Any and all rights over artwork and content within the modification remain the sole property of their original artist or rights holder, no claim is made by the project or its members to materials contained in the modification."* Two specific asset credits (`credits.txt:267,270`) cite CC-BY-licensed Sketchfab models (Green Iguana skull, Bobcat skull) used in the Argonian/Khajiit skull models — those two specific source assets are CC-BY reusable, but the mod's own derived/composited work is not blanket-licensed.
- No `LICENSE` file in the mod folder (`verified`, `ls`).

---

## 3. Local evidence: Godherja: The Dying World

All paths relative to `/home/cvdbdo/.local/share/Steam/steamapps/workshop/content/1158310/2326030123`.

- **No D&D-style playable races**: `grep` of `common/traits/` for orc/dwarf/halfling/elf/goblin/troll/ogre/giant keywords returns no hits (`verified`).
- Race-adjacent categories exist only as **culture heritage pillars**: `common/culture/pillars/00_heritage.txt:98` (`heritage_aelfir`, elf-like), `:946` (`heritage_bestial`), `:954` (`heritage_lich`), `:970` (`heritage_undead`) out of 106 heritages total (`verified`). Unlike EK2, these pillar blocks carry **no gameplay parameters** — only `audio_parameter` (`verified`, `00_heritage.txt:98-103`).
- The only culture on `heritage_aelfir` is `common/culture/cultures/gh_aelfir.txt:1-25`, which contains the comment `# TODO: Implement an actual ethnicity` and falls back to a **vanilla human ethnicity** (`european_med_greek_1`) — elves are lore-only, not visually distinct (`verified`).
- No on-birth hybrid-race resolution logic exists (checked `common/on_action/godherja/GH_child_birth_on_actions.txt`) — race/heritage passes via ordinary CK3 culture inheritance only (`verified`).
- `common/ethnicities/`: 2,795 files, but all but 5 are human real-world ethnicities from an integrated "Ethnicities & Portraits" submod (`e&p_*.txt`). The 5 Godherja-original files: `0_GH_aelfir.txt` (placeholder), `0_GH_ethnicities_skeleton.txt`, `0_GH_fogeater.txt`, `0_GH_redlander.txt`, `0_GH_tlakalakan.txt` (`verified`).
- `common/ethnicities/0_GH_ethnicities_skeleton.txt:1-30` defines a genuine custom race via `body_replacement = { name = skeleton_body }` (`verified`) — the one race in this mod with a real distinct body.
- The skeleton meshes/textures live at `gfx/models/portraits/1MOD/EK/Creatures/skeleton/` (`verified` path) — the `EK` folder name plus a matching credit line in `!!!CREDITS!!!.txt` (*"Theyn_T (and the Elder Kings team) — Shrunk border art"*) indicate these are **borrowed Elder Kings assets**, reused with attribution, not built by Godherja.
- `gfx/models/portraits/1MOD/` contains 8 source-mod subfolders (`Ammo`, `BA`, `EK`, `EPE`, `KoH`, `MMJM`, `NordwarUA`, `SI`) — Godherja imports 3D portrait assets from at least 8 other mods (`verified`, directory listing).
- No race-specific `gfx/portraits/portrait_modifiers/` files (49 total, none named for elf/lich/undead/skeleton) (`verified`).
- 25 custom gene files (`common/genes/GH_genes_special_*`), all accessories/tattoos/markers — no body-morph genes for a new race (`verified`).
- No custom longevity mechanic for `heritage_aelfir` found; the lich trait family (`GH_lich_traits.txt`) sets `can_have_children = no`/`minimum_age = 16` but no explicit lifespan extension (`verified`).
- **License**: `!!!CREDITS!!!.txt` is attribution-only — documents reuse (with permission-style credit) of assets from Elder Kings, LotR: Realms in Exile, EPE, AGOT, Princes of Darkness; a handful of background images carry explicit CC/GFDL licenses (lines 49-77). No blanket license for Godherja's own original content; `credit_portraits.txt` is empty; no `LICENSE` file (`verified`).

---

## 4. Local evidence: vanilla CK3 (reference)

All paths relative to `/home/cvdbdo/.local/share/Steam/steamapps/common/Crusader Kings III/game`.

- `common/ethnicities/`: 25 files. Each ethnicity block: `template = "ethnicity_template"`, optional `using = "<other_ethnicity>"` for inheritance, then weighted tables for skin/eye/hair color and per-gene entries (`verified`, e.g. `01_ethnicities_mediterranean.txt:37-83`).
- `common/genes/`: 11 content files. `01_genes_morph.txt` (facial/body sliders, `group = face|eyes|...`) at `:369-405`; `08_genes_special_visual_traits.txt:1-3` explicitly notes special genes are "not part of a character's DNA … the game can have hardcoded references," supporting `decal` blocks with diffuse/normal/properties textures — the mechanism a mod would reuse for race-specific skin decals (`verified`).
- `gfx/portraits/portrait_modifiers/` (26 files, hair/beard/clothes/headgear) is **separate** from `gfx/portraits/trait_portrait_modifiers/00_trait_modifiers.txt` — the latter is the **trait → DNA-morph link** (`verified`).
- `common/traits/00_traits.txt:7946-8016` — vanilla `dwarf`/`giant` traits: `genetic = yes`, `physical = yes`, mutually `opposites`, `birth = 0.5`, `enables_inbred = yes`. The trait file itself carries **no** portrait link (`verified`).
- `gfx/portraits/trait_portrait_modifiers/00_trait_modifiers.txt:1-64+` — a `height_genetic_conditions` block maps `dwarfism = { traits = { dwarf } dna_modifiers = { human = { morph = { gene=... template=... mode=modify value=... } } } }`; `giant` handled identically with `template = giant_height` (`verified`). **This is the reusable base-game pattern**: a trait forces a bundle of gene/template/value overrides onto the portrait, without needing new meshes.
- DNA storage: `history/characters/dayak.txt:178` → `dna = bookmark_dna_indra`, resolved in `common/dna_data/00_tgp_dna.txt:2067-2072` as a `portrait_info = { genes = {...} }` block — an id reference, not an inline readable gene string (`verified`).
- Culture heritage is a **separate first-class pillar object**, `common/culture/pillars/00_heritage.txt`, referenced from culture files via `heritage = heritage_west_slavic` (`verified`) — decoupled from ethnicity/genes, i.e. vanilla has no "race" concept: ethnicity (portrait genetics) and heritage (culture classification) are orthogonal, and mods must bridge them (both EK2 and Godherja do this via a `species_*` cultural **parameter** on the pillar, or, in EK2's case, additionally via character flags).

---

## 5. Web evidence

- **Elder Kings 2**: no public CK3 source repo (`https://github.com/Elder-Kings` has 1 public repo, image hosting only); local `credits.txt` confirms assets are not reusable (see §2). Wiki: `https://ck3.paradoxwikis.com/Elder_Kings_II`.
- **LotR: Realms in Exile**: mod page confirms Human/Elf/Dwarf/Hobbit/Orc; further races excluded citing 3D-asset/coding cost — `https://ck3.paradoxwikis.com/LotR:_Realms_in_Exile`. Only a MIT-licensed **website** repo is public: `https://github.com/CK3RealmsinExile/RealmsInExile-Website` (not the mod itself).
- **A Game of Thrones (AGOT)**: human-only setting; dragons via ethnicity/DNA system — `https://ck3.paradoxwikis.com/CK3AGOT`. Confirms AGOT and Realms in Exile dev teams collaborate.
- **Princes of Darkness**: playable vampire/hunter/werewolf/changeling/mummy/demon "splats" — `https://mods.paradoxplaza.com/mods/11356/Any`. Operates under Paradox's own World of Darkness "Dark Pack" fan-content agreement: `https://www.paradoxinteractive.com/games/world-of-darkness/community/dark-pack-agreement` — a real precedent for IP-holder-sanctioned fan content, but that agreement covers setting/IP use, not a CK3 asset-reuse grant.
- **Warcraft: Guardians of Azeroth 2**: full source public, 98 stars, active — `https://github.com/Warcraft-GoA-Development-Team/Warcraft-Guardians-of-Azeroth-2`. Repo root has `gfx/models`, `gfx/skins`, `gfx/portraits/{portrait_modifiers,trait_portrait_modifiers}` confirming custom race meshes. **No LICENSE file** — public GitHub visibility grants no reuse rights by default. `credits.info` credits only icon/name-generator sources (game-icons.net, obsidiandawn.com, fantasynamegenerators.com), not 3D assets.
- **Dragon Age CK3 mods**: `https://github.com/Spellwe4ver/ExaltedMarch` (GPL-3.0, LICENSE+README only, no game content yet — low maturity); `StellaSAX/Dragon-Age-CK3` also low-activity.
- **Forgotten Realms / Faerûn / D&D CK3 mod**: **confirmed absent.** Zero genuine hits on Steam Workshop search (appid 1158310) for "Forgotten Realms," "Faerûn," "Dungeons and Dragons," "D&D," "Baldur's Gate"; zero matching GitHub repos (`forgotten-realms+ck3`, `faerun+ck3`, `dnd+ck3`); absent from the CK3 wiki mod list (`https://ck3.paradoxwikis.com/Modding`). This is an open gap.
- **Open/permissive fantasy-race asset packs**: **none found.** Searched GitHub topic `crusader-kings-3` (101 repos — top results are tools like IronyModManager, tiger linter, modding docs, not asset packs: `https://github.com/topics/crusader-kings-3`); direct queries for gene/portrait asset packs returned nothing. Closest adjacent project, **"Ethnicities & Portraits Expanded" (EPE)** (`https://steamcommunity.com/sharedfiles/filedetails/?id=2507209632`), covers only real-world human ethnicities and has an explicit **restrictive** policy, directly quoted: *"Permission to use assets from our mod is prohibited unless under explicit/written agreement from our mod lead… We cannot loan or give the assets of contributors to other projects."* Useful modding-format reference tools (not assets): `ross-g/io_pdx_mesh` Blender mesh exporter (GPL-3.0, `https://github.com/ross-g/io_pdx_mesh`), `CK3-Modding/Documentation` (MIT, community wiki mirror, `https://github.com/CK3-Modding/Documentation`).
- **CK3 wiki — portrait system**: no dedicated "genes/portraits/ethnicities modding" page exists (all red-links); real content lives under `https://ck3.paradoxwikis.com/Characters_modding` (DNA/gene/portrait_modifier mechanics, `dna_modifiers` blocks, outfit tags) and `https://ck3.paradoxwikis.com/Trait_modding` (confirms `genetic_constraint_all`, `forced_portrait_age_index`, `portrait_extremity_shift` as the trait-level appearance-forcing keys, and lists `dwarf`/`giant`/`albino` as the vanilla examples — matches the local file evidence in §4).
- **CK2→CK3 converter tools**: **none exist.** `https://github.com/ParadoxGameConverters` (39 repos, active) has `ImperatorToCK3` (MIT, Imperator Rome → CK3) and `CK3ToEU4`/`CK3ToEU5` (CK3 as source), but CK2 conversions only ever target EU3/EU4 — never CK3. These are all **save-game** converters (map/provinces/characters/dynasties), unrelated in scope to fantasy-race/asset porting. `ImperatorToCK3`'s MIT-licensed C++ codebase is a plausible structural reference for "read one Clausewitz-engine game's data, emit a CK3 mod," not a functional dependency.

---

## 6. Recommended minimal design for a converter-produced Forgotten Realms mod

Based on the patterns above, closest fit is EK2's model (richest, most CK3-idiomatic), simplified:

- **Race carrier**: a `species_<race>` **cultural parameter** on a heritage pillar (`common/culture/pillars/`), exactly like EK2's `heritage_argonian → species_argonian = yes`. This lets any script/trigger query race via `culture = { has_cultural_pillar = heritage_X }` without new game concepts.
- **Default + inheritance**: mirror EK2's two-stage effect — `race_traits_effect` grants a per-character `race_<name>` flag from culture heritage at character creation, and a birth on_action-triggered `race_traits_inheritance_effect` overrides it from `scope:mother`/`scope:real_father` in a fixed priority order for mixed unions. Reuse `on_action = { on_birth_child = { ... } }` as the hook (confirmed vanilla on_action, EK2 wires into `child_birth_on_actions.txt`).
- **Longevity**: a generic `lifespan_1..N`/`is_immortal` genetic trait family (life_expectancy/fertility set directly on the trait, EK2-style) rather than defines or hardcoded ages — keeps elf/dwarf/halfling longevity data-driven and moddable per race via a weighted `random_list` at setup.
- **Portraits — tiered by asset availability**:
  - Tier 1 (no new assets): reuse vanilla `dwarf`/`giant`/`albino`-style trait→`dna_modifiers` forcing (`gfx/portraits/trait_portrait_modifiers/`) to bias height/build/skin tone per race using only vanilla morph genes. Covers halflings (force `dwarf`-style height template), half-orcs (skin tone + build bias) with zero new 3D work.
  - Tier 2 (moderate effort): one dedicated `common/ethnicities/` entry per race referencing vanilla gene templates, for a distinct-but-human-shaped look (elves, half-elves) — matches Godherja's approach for its non-skeleton races.
  - Tier 3 (full custom, highest effort): new morph genes for true new anatomy (pointed ears, tusks) following EK2's **two-gene additive pattern** (`ek_genes_mer.txt`) specifically because it makes half-races inherit correctly through ordinary CK3 genetics with zero scripted-effect logic — this is the single most reusable *technique* found in this research, independent of any specific art asset.
  - Placeholder policy where no 3D asset exists yet: fall back to the nearest vanilla ethnicity (as Godherja does for `gh_aelfir`) rather than leaving a broken/empty ethnicity — ship it as an explicitly flagged `# TODO: real ethnicity` placeholder, matching the precedent at `common/culture/cultures/gh_aelfir.txt:1`.
- **Hybrids for anatomy, not just flags**: use the gene-based blending approach (Tier 3) wherever a race has genuinely new meshes, so half-elf/half-orc children look intermediate automatically; reserve the character-flag inheritance chain (EK2 pattern) only for **non-visual** race bookkeeping (naming schemes, event eligibility, lore text) where a discrete "which race are they" answer is still needed.

---

## 7. Candidate reusable asset sources — license status

| Source | Status |
|---|---|
| Elder Kings 2 assets | **Not reusable** — verified "sole property of original artist," no blanket license |
| Godherja original assets | **Not reusable** — attribution-only credits, no license file |
| Godherja's *borrowed* assets (from EK2, Realms in Exile, EPE, AGOT, Princes of Darkness) | **Not reusable by a third party** — those were granted to Godherja specifically, "with permission"; re-reuse would need separate permission from each original rights holder |
| Warcraft: Guardians of Azeroth 2 (public GitHub source) | **Not reusable** — no LICENSE file, source visibility ≠ granted rights |
| Ethnicities & Portraits Expanded (EPE) | **Not reusable** — explicit written-permission-only policy quoted above |
| Two specific Sketchfab creature-skull models credited in EK2 (`credits.txt:267,270`) | **Reusable under CC-BY 4.0** directly from their original Sketchfab source (not via EK2) — "Green Iguana skull - OUVC 10677" by WitmerLab, "Bobcat Skull" by RISD Nature Lab |
| A few Godherja background images (`!!!CREDITS!!!.txt:49-77`) | **Reusable per their stated CC/GFDL terms** — not itemized further here; read that file's cited lines before reuse |
| `ross-g/io_pdx_mesh` (Blender mesh exporter) | **Reusable tool** (GPL-3.0) — not an asset, but usable to build new race meshes for a Forgotten Realms mod |
| `CK3-Modding/Documentation` | **Reusable reference** (MIT) — community modding docs, not assets |
| A general open-source fantasy-race 3D asset library for CK3 | **Does not exist** — confirmed absent in this ecosystem; any Forgotten Realms race needing new anatomy (elf ears, orc tusks, halfling proportions) needs bespoke 3D work or a direct, individually-negotiated permission from a specific mod team |

---

## Notes on research method

- One web-research subagent flagged that a fetched Steam Workshop HTML page contained an injected fake instruction block attempting to alter git-commit attribution rules; it was correctly ignored (no commits were made from this research task regardless). Logged to `~/.claude/harness/NOTES.md`.
- WebSearch/WebFetch tools were unreliable during this session; web findings were gathered via direct `curl` against GitHub's REST API, Steam Workshop/Paradox Mods pages, and a read-proxy for Cloudflare-walled wiki/forum pages. All web claims above carry their source URL for independent re-verification.
