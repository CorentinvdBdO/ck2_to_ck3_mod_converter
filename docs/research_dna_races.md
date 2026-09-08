# CK3 DNA and fantasy races: structure, mod precedent, and picture→DNA feasibility

Scope: (1) how CK3 DNA/portraits work, (2) how EK2/Godherja/Princes of Darkness (PoD) build
non-human races, (3) whether a CK2 picture → CK3 DNA pipeline is feasible, (4) what the
converter should build now vs. defer to an asset library vs. treat as research.

Sources: CK3 game `.../Crusader Kings III/game` (verified, local read); CK2 base game
`.../Crusader Kings II` (verified, local read); CK2 Faerûn mod `Faerun/Faerun` symlink
(verified, local read); workshop mods EK2 `2887120253`, Godherja `2326030123`, PoD
`2216659254` (verified, local read); prior repo research `docs/races_research.md`,
`docs/design_races.md`, `docs/faerun_ck2_survey.md`, `docs/formats_characters.md` (verified,
read and extended, not duplicated); web sources per §3 (labeled `assumed` unless an official
Paradox page). Evidence CSVs: `docs/evidence/dna/gene_files_vanilla.csv`,
`docs/evidence/dna/mod_race_inventory.csv`.

---

## 1. CK3 DNA structure

### 1.1 Gene declaration

- Three gene *kinds*, three different file groups, `verified` `game/common/genes/`:
  - **Morph genes** (`01_genes_morph.txt`, 98 genes, one file): continuous body/face
    sliders. Block = named "templates" (usually a `_neg`/`_pos` pair) each with `index`,
    optional `visible = no` (hides from chargen UI, still in DNA), and per-gender
    (`male`/`female`/`boy`/`girl`) `setting = { attribute = "..." value = {min max} age =
    <age_preset> }` (`01_genes_morph.txt:371-408`, `gene_chin_forward`, quoted in full in
    evidence). `age_presets` (top container, `01_genes_morph.txt:16-24`) are named curves,
    `mode = add|multiply` + `curve = {{x y}...}` control points — those are the *only* two
    modes in the whole gene system.
  - **Color genes** (`00_genes_color.txt`, 19 lines, 3 genes only: `hair_color`,
    `skin_color`, `eye_color`). Each declares `group`, `color` (which palette texture:
    `hair`/`skin`/`eye`), `blend_range` (dominant/recessive blend ratio), optionally
    `sync_inheritance_with`. Palette is a **texture**, not a script enum:
    `hair_palette.dds` 512×512, `skin_palette.dds`/`eye_palette.dds` 256×256
    (`common/portrait_types/00_human_types.txt:2-6`, `verified`) — a color gene value is a
    continuous 2D coordinate into that texture, not a discrete swatch pick.
  - **Accessory genes** (`02_..10_genes_special_*.txt`, 9 files): hairstyles, beards,
    clothes, headgear, makeup, misc props, "special visual traits" (engine-hardcoded, see
    below). Declared as `inheritable = no` (`02_genes_accessories_misc.txt:17`), templates
    with `index`, and per-gender blocks whose value is `weight = "asset_name_string"`
    (uniform-random pick among named mesh/texture assets), e.g. `male = { 1 =
    "male_hair_western_01" 1 = "male_hair_western_02" ... }`.
- `common/genes/_genes.info` (25 lines, explicitly "very incomplete") is the only dev doc;
  it defines `blend_range` (dominant/recessive blend ratio on inheritance), `decal` blocks
  (skin/paint textures with `atlas_pos`/`alpha_curve`), and
  `ugliness_feature_categories` (links a gene to the `ugliness_portrait_extremity_shift`
  trait mechanic).
- `08_genes_special_visual_traits.txt:1-2` (`verified`, quoted): *"These special genes will
  not be part of a character's DNA. The game can have hardcoded references to them"* — 28
  such genes exist (disease decals, pregnancy morph, hue-shift curves for age-graying);
  they are engine features layered on top of DNA, not inherited genetic data.
- Per-file gene/template counts (brace-depth parse, `verified`, full table in
  `docs/evidence/dna/gene_files_vanilla.csv`): color 3 genes; morph 98 genes across
  groups `face`(29) `mouth`(19) `nose`(15) `eyes`(13) `head_neck`(8) `ears`(5) `body`(5)
  `hair`(2); accessories: eye/teeth/eyelash 13 templates, hairstyles 85, beards 47, clothes
  199, headgear 245, misc props 295, makeup 7, special-visual 28, special-misc 13.
- **Body-shape vs. face**: `group = body` covers only `gene_height`, `gene_bs_body_type`
  (fat/thin), `gene_bs_body_shape` (musculature), `gene_neck_length`/`_width`,
  `gene_body_hair` — 5 genes total. Everything else in the 98 morph genes is face/head
  (`verified` group tally above). No shoulder-width or torso-length axis exists.

### 1.2 The DNA string: two different formats

- **Plaintext script format** (used in `common/dna_data/*.txt` and mod files) —
  `verified` locally: `_dna_data.info` documents `portrait_info = { genes = { hair_color=
  {14 244 25 255} gene_cheek_puffy={cheek_puffy_neg 109 cheek_puffy_neg 92} } }`. Real
  example, `common/dna_data/00_dna.txt:4-113` (`163112_halfdan_whiteshirt`, quoted in
  evidence CSV): a **color gene** value is 4 raw integers 0–255 (two (x,y) pairs,
  dominant/recessive); a **morph or accessory gene** value is two `"template_name" byte`
  pairs (dominant allele, recessive allele — CK3 characters are diploid at the gene level).
  Confirmed independently by two community tools' source (`assumed`, web):
  `raccoonwannafly/CK3_Gallery` dev-docs and `Deticaru/CK3-DNA-Duplicator` both parse
  exactly this two-value-pair grammar.
- `history/characters/*.txt` `dna =` is **always a reference into `common/dna_data`**, never
  an inline literal string — `verified`, 80 files contain `dna =`, all forms like
  `dna = bookmark_dna_duan_silian` or `dna = "218800_kulin_bosna"`. Zero inline base64-like
  literals found in vanilla script (`grep` for a 20+-char DNA literal returns 0 hits).
- **Binary clipboard format** ("Copy DNA" in the in-game Ruler Designer) is a *different*,
  base64-encoded fixed-length byte blob, distinct from the plaintext form — `assumed`, web:
  CK3 Wiki's Ruler Designer page confirms copy/paste DNA text exists and that a few genes
  (body shape, male body hair, bust shape, aging style, eyebrow wrinkles) are **not exposed
  in the chargen UI** and are only reachable by hand-editing the DNA string. A community
  tool (`raccoonwannafly/crusader-kings-3-dna-updater`) documents the blob as
  **version-pinned and length-checked** by the game's paste parser (example cited: "old DNA
  ~200 bytes" vs "new DNA ~400 bytes," facial features in "the first ~100 bytes") — the
  game rejects a pasted blob whose length mismatches the current version's schema.
- `common/defines/00_defines.txt:1350-1383`, `NPortrait` block (`verified`, quoted in
  full in evidence): `GENE_DATABASE_VERSION = 5` — *"If the version saved in a file does
  not match this number, the portrait DNAs will get regenerated"* — confirms a versioned
  gene-index schema; any custom gene added by a mod changes this schema and breaks
  cross-version/cross-mod DNA compatibility. Also: `MAX_AGE = 100.0` (age gene reaches full
  strength), `PORTRAIT_MALE_ADULT_AGE = 18` (boy→male portrait switch),
  `MAX_PORTRAIT_GENERATION_DEPTH = 8` (ancestor-portrait generation depth for missing DNA).
- **Practical implication for the converter**: generate DNA in the **plaintext
  `common/dna_data` format only** (game-version-stable, human-readable, script-declared)
  — never attempt to emit or reverse-engineer the binary clipboard blob, which is
  explicitly version-pinned at the byte level.

### 1.3 Ethnicities constrain gene distributions, per-gene independently

- `common/ethnicities/01_ethnicities_mediterranean.txt:37-117` (`verified`, quoted in
  full): block = `template = "ethnicity_template"` (inherits the full default gene table
  from `00_ethnicities_templates.txt`), optional `using = "<other_ethnicity>"` (layered
  inheritance on top of `template`), then weighted tables per gene.
- **Color gene** weighted entry: `weight = { min_x min_y max_x max_y }` — a 4-float 2D
  *range* into the palette texture, e.g. `skin_color = { 10 = {0.5 0.4 0.8 0.5} }`.
- **Morph gene** weighted entry: `weight = { name = template_name range = {min max} }`,
  e.g. `10 = { name = avg_spacing_avg_thickness range = {0.5 1.0} }`.
- Weight semantics: ordinary Paradox weighted-list, `weight / sum(weights in that gene's
  table)`, resolved **independently per gene** — no cross-gene correlation is declared
  anywhere in ethnicity files (`verified`, no such define exists in
  `common/defines/00_defines.txt`).
- 25 ethnicity files, 46 distinct top-level ethnicity blocks (brace-depth count,
  `verified`). No global define blends mixed-parentage children beyond the per-gene
  `blend_range` (color) / dominant-recessive allele pick (morph) baked into the gene
  definitions themselves.

### 1.4 portrait_modifiers / accessory_variations / portrait_types / trait_portrait_modifiers

| System | Location | Purpose (`verified`) |
|---|---|---|
| `portrait_modifiers` | `gfx/portraits/portrait_modifiers/` (33 files) | Conditional accessory/gene-override *selection*: a group picks at most one entry by weighted random or max-weight, gated by `outfit_tags`, culture, gender, script triggers (`06_makeup.txt:1-35` example: `no_makeup` forces `gene_makeup` via `dna_modifiers`, weighted by nudity/culture triggers). |
| `accessory_variations` | `gfx/portraits/accessory_variations/` (39 entries) | Maps an already-chosen accessory mesh to weighted **cloth-pattern + color-palette texture** combinations (`western.txt`, `example.txt:60-104`) — material variety layered on top of mesh choice, not ethnicity-level. |
| `portrait_types` | `common/portrait_types/00_human_types.txt` (1 file; **not** under `gfx/`) | Binds palette textures per species/sex/age bracket and the base mesh/rig entity (`male = { sex=male minimum_age=18 head="head_basic_entity_male" torso="male_body_entity" }`) — the species/sex/age→mesh+palette wiring point. |
| `trait_portrait_modifiers` | `gfx/portraits/trait_portrait_modifiers/00_trait_modifiers.txt` (1 content file, 2024 lines) | Trait → forced `dna_modifiers` bundle (gene/template/value overrides), first-match priority order. **The reusable zero-mesh mechanism**: a trait can reshape a portrait with no new meshes. |

- `00_trait_modifiers.txt` full catalogue of trait-forced overrides (`verified`, complete
  read, not just dwarf/giant as previously documented in `races_research.md:172-173`):
  `dwarfism`(:2, height+head), `gigantism`(:75, `giant_height` template),
  `albino`(:162, forces `skin_color`/`hair_color` x=-1,y=-1 and `eye_color` x=-1,y=0, plus
  brow-morph flattening), `scaly`(:463, `gene_scaly` decal, real shipped reptile-skin
  texture on head+torso), `spindly`(:1926, build-shrink: `gene_spindly` +
  `gene_neck_width -0.5` + `gene_height +0.1` + `gene_bs_body_type ×0.6` +
  `gene_bs_body_shape ×0.5`), plus 17 disease/disfigurement blocks. **No ear/tail/horn
  block exists in vanilla.**

### 1.5 Age/gender variants

- **Age**: one stored intensity byte per gene, scaled at render time by a named curve
  (`age_preset_*`, `mode = add|multiply` + control points) referenced from the gene's
  `setting`, e.g. `age = age_preset_child_features` — no discrete age-indexed gene sets
  (`verified`, `01_genes_morph.txt:248-255,391`; consistent with `NPortrait.MAX_AGE`).
- **Gender**: each gene/template carries separate `male`/`female`/`boy`/`girl` sub-blocks
  in the same declaration (own attribute range per gender, e.g. `@maleMin/@maleMax` vs.
  `@femaleMin/@femaleMax`), aliasable (`boy = male`) or fully excludable (empty block,
  `no_eyes = { male={} female={} boy={} girl={} }`) — no separate gene files or
  ethnicities per gender.

---

## 2. Races in mods

Detailed EK2 and Godherja evidence already exists at `docs/races_research.md` — not
repeated here beyond the summary table. Princes of Darkness (previously marked "not
investigated") is new in this doc.

### 2.1 Comparison table (`verified` unless noted)

| Mod | Race carrier | Custom gene files | Custom ethnicities | Custom `portrait_modifiers` | `.mesh` count | License |
|---|---|---|---|---|---|---|
| Vanilla | n/a | 0 | 25 (base) | 33 (base) | — | Paradox |
| **Elder Kings 2** | culture heritage pillar `species_x` parameter + inherited character flags | 17 (ears/tails/horns/legs morph genes) | 50 | ~50 of 132 | 2,227 | **Not reusable** — "sole property of original artist," no license file |
| **Godherja** | culture heritage pillar only, mostly cosmetic | 25 (accessories/tattoos only, no body morphs) | 5 of 2,795 (1 real body: skeleton) | 0 of 49 | 0 own (borrows EK2's) | **Not reusable** — attribution-only, no license file |
| **Princes of Darkness** | trait (`splat` mutually-exclusive group: werewolf/vampire/etc.), *not* culture/heritage | 6 non-empty (horns, Nosferatu/Tzimisce deformation, beast legs, claws, fangs, HSV skin/hair recolor) | **0** (same 25 as vanilla) | 15 of 28 | **463** (373 under a dedicated `POD/` creature folder — one dir per Werewolf breed, plus dragon/demon/unicorn assets) | **Reusable** — Unlicense/public domain (`POD_license.info`, quoted); WoD *brand names* still restricted by Paradox's Dark Pack agreement, but the code/asset work itself is unencumbered |

- **PoD is the deepest race-morphology implementation of the three**, not Godherja as the
  size numbers alone might suggest, and it is also the only one with a real reuse grant.
  It represents splats via a **trait**, not culture — a different design axis than
  EK2/Godherja's heritage-pillar pattern, worth considering for the converter's own
  half-race/hybrid bookkeeping.
- PoD body-size changes use **two different mechanisms** depending on magnitude: partial
  forms (Fera intermediate stages) reuse vanilla's own `giant_height` template exactly
  like dwarf/giant (`gene_height` `mode = modify_multiply`); full "crinos" battle-forms
  instead **swap in an entirely new body mesh** via an accessory-gene slot
  (`clothes_custom_2` template `werewolf_body`) — a full mesh replacement, not a morph.
- PoD's horn/tail/wing/hoof genes (`POD_accessory_genes.txt`, 1612 lines: `POD_horns`,
  `POD_tail_accessory`, `POD_wings`, `POD_hooves`, real meshes) are a concrete, license-clear
  reference implementation for exactly the anatomy Faerûn races need (tiefling
  horns/tails, dragonborn horns, etc.) — worth studying as *technique*, and its
  Unlicense means its actual gene/mesh-wiring code could be adapted directly, though its
  meshes (werewolf/vampire-styled) are the wrong *shape* for D&D races and would still
  need re-sculpting or replacement.

### 2.2 Minimal viable race from vanilla assets only

`verified`, full read of `00_trait_modifiers.txt` and all `common/genes/*.txt`:

| Race | Vanilla-only feasible | Needs new mesh/gene for |
|---|---|---|
| Elves | Nothing usable directly — an `ears` morph group exists (5 blendshapes: angle, inner-shape, bend, outward, size) but no "point" target | True pointed ear tip (new blendshape, EK2's actual approach) |
| Dwarves | Height via existing `dwarfism` trait_portrait_modifier; stockiness via pushing `gene_bs_body_type`/`body_shape`/`neck_width`, zero new assets | Nothing strictly required — fully data-only race |
| Halflings | Same `dwarfism`-style height forcing, milder value | Nothing strictly required |
| Gnomes | Same mechanism again | Nothing strictly required; visually indistinguishable from dwarf/halfling without new assets |
| Half-orcs/orcs | Build via `gene_bs_body_type`/`body_shape`; green/grey skin via the vanilla `skin_hsv_shift_curve` primitive (already used for age-graying; new small gene block, zero mesh) | Tusks (confirmed zero vanilla tusk/horn-on-body accessory gene) |
| Dragonborn | Scale-skin via existing `gene_scaly` decal (real shipped texture, head+torso) | Horns, tail, snout — zero vanilla gene for any |
| Tieflings | Skin recolor via `skin_hsv_shift_curve` (script-only) | Horns and tail (confirmed zero vanilla accessory gene) |
| Drow | Pale/white hair by reusing `albino`'s exact override; script-only | Grey/dark-purple skin — outside vanilla's skin-gradient texture range, needs new gradient texture or the HSV primitive (untested visual quality) |

- The single reusable primitive not previously documented: `skin_hsv_shift_curve` /
  `hair_hsv_shift_curve` (`01_genes_morph.txt:9745-9757`, `08_genes_special_visual_traits.txt:422`)
  — vanilla uses it only for age-related graying, but it is the exact mechanism PoD reuses
  (`POD_morph_genes.txt:652-877`) to build blue/grey/red/green skin and colored hair —
  script-only, zero new mesh, usable today for orc/tiefling/drow-adjacent skin tones.
- No body-attached horn/tail/wing/tusk/claw gene exists anywhere in vanilla
  (`grep -rin tusk common/genes/` = 0 hits; the only "horn" hit is a held drinking-horn
  prop, not anatomy). Any race needing these needs new gene+mesh work — this is the hard
  floor of "zero new art."

---

## 3. Picture → DNA feasibility

### 3.1 Which genes are visible/continuous vs. discrete (from §1)

- **Continuous, portrait-visible, good regression targets**: the 98 morph genes (face
  shape, ~29 face + 19 mouth + 15 nose + 13 eyes + 8 head/neck + 5 ears + 5 body), each a
  0–255 (or 0–1 normalized) intensity per allele — this is the natural target space for a
  learned photo model, consistent with community precedent (§3.3).
- **Continuous but 2D-coordinate, not scalar**: the 3 color genes (skin/hair/eye), each a
  point in a palette texture rather than a single slider — a regressor needs two outputs
  per color gene (x,y), not one.
- **Discrete, categorical**: accessory genes (hairstyle/beard/clothes/headgear/makeup —
  ~899 templates across the 9 accessory files) — a photo-based mapping to these is a
  classification problem (nearest named asset), not regression, and far less reliable from
  a 2D CK2 portrait or a real photo (occlusion by clothing/headgear, stylization).
- **Not part of DNA at all**: 28 "special visual traits" genes (disease decals, pregnancy)
  are engine-hardcoded, not learnable targets.

### 3.2 Can the game render batches headlessly?

- **No general headless batch-render tool exists**, official or community
  (`assumed`, web, checked directly against the CK3 Console Commands wiki page and
  multiple GitHub tool repos). The closest official mechanism is the console command
  `dump_bookmark_portraits`, which renders portraits for **all current bookmark
  characters only** (not arbitrary custom DNA) to
  `Documents/Paradox Interactive/Crusader Kings III/common/bookmark_portraits` — a batch
  capability, but scoped to bookmarks, not a general (DNA→image) generator.
- Real precedent for how the community actually built (image, DNA) training pairs at scale
  was **manual**, not headless: a 2021 Paradox-forum "Picture to Persistent DNA Generator"
  project had contributors use the in-game Debug Menu → Portrait Editor to export DNA per
  character and screenshot by hand, "batches of 150" at a time (`assumed`, web, forum
  archived via Wayback Machine).
- **Practical implication**: building a headless render harness (likely: automate the
  in-game portrait editor via input injection, or reverse-engineer more of the
  `dump_bookmark_portraits` code path to accept arbitrary DNA) is itself a nontrivial,
  currently-undocumented engineering task and should be budgeted as its own line item, not
  assumed free.

### 3.3 Existing community tools and direct CK3 precedent

- Plaintext/binary DNA converters (all `assumed`, web, MIT or unlicensed small repos):
  `CristianCamillo/CK3_DNA_Converter` (clipboard blob → plaintext), `Deticaru/CK3-DNA-Duplicator`
  (forces both allele slots equal, MIT), `guga06436/ck3-dna-beautifier`,
  `huangfanglong/CK3-Gene-Homogenizer` and `CK3-Character-Gallery` (DNA+portrait archive/workbench),
  `raccoonwannafly`'s `crusader-kings-3-dna-updater` (byte-length version migration) and
  `CK3_Gallery`/"DNA Forge" (React slider editor + dev docs describing the plaintext grammar).
- **Direct precedent for this exact problem, found and worth treating as the strongest
  single data point in this research**: `Hakim1625/ck3-image-portrait-modeling`
  (`assumed`, web, GitHub, 28 stars, last pushed 2022-07-08, PyTorch + PyTorch Lightning +
  torchvision + dlib) — a ResNet-based regressor mapping face photos/screenshots directly
  to CK3 persistent-DNA gene-slider values. Trained on a **crowdsourced dataset of ~23,000
  (screenshot, DNA) pairs covering ~8,900 unique characters**, built manually over ~6
  months, no synthetic data. Adding gender as a predicted output *degraded* accuracy —
  evidence that output-space growth costs data non-linearly.
- No synthetic-data-only strategy (render CK3 portraits from known random DNA, train only
  on those pairs, skip crowdsourcing) was found documented for CK3 or any comparable game
  — flagged as an open, untested idea rather than a validated shortcut.

### 3.4 CK2 → CK3 encoding: the actual answer for the converter (highest-value finding)

- CK2's own portrait encoding (`verified`, local read of CK2 base game and Faerûn):
  `dna =` (11 lowercase a-z chars, fixed length, genetic/inherited) and `properties =`
  (12–19 chars, `0`-padded, non-genetic customization) are both present in vanilla CK2
  history. `interface/portraits/portraits.gfx:9-85` documents the **slot semantics**
  in script (`"GFX_western_male_chin:d1"` etc. — DNA byte index → body part, per
  `portraitType`), plus named `hair_color_index=8`/`eye_color_index=9` slots. But the
  **byte-value → visual-frame mapping is not in script** — it depends on each sprite's
  frame-pool size (`portrait_sprites.gfx`), which is engine-scaled per race's art pack.
- **Cross-race proof this makes raw DNA bytes non-portable**: Faerûn's own custom
  `portraits_saurial.gfx`/`portraits_saurial_sprites.gfx` uses the *same* slot indices as
  vanilla western portraits but a flat 20-frame pool per part vs. vanilla's 4–13 —
  reusing a human's raw DNA byte on a saurial would select an arbitrary, mismatched frame,
  not a "same face, saurial-styled" result.
- **The decisive negative finding**: Faerûn's `dna =`/`properties =` usage is present on
  only **221 of 18,124 characters (~1.2%)** and **26 (~0.14%)** respectively — sampled
  strings from human, elf, and fiend characters are format-identical (11 a-z chars,
  no race-correlated signal). Faerûn does **not** carry per-character CK2 portrait genetic
  data broadly enough to deterministically map into CK3 DNA at scale. There is no general
  "translate this character's CK2 face into a CK3 face" pipeline available from the data —
  only a race/culture-level signal.
- **The positive counter-finding**: Faerûn *does* carry strong per-race visual signal
  through **`graphical_cultures`** — 270 custom `graphicalculturetypes` and 386
  race-specific `gfx/characters/<race>_male|female/` art directories (elves, dwarves,
  orcs, drow, aasimar, saurials, tieflings, etc. all have dedicated 2D portrait art, not
  human reskins), assigned per culture group as fallback-ordered lists (e.g.
  `elves.txt:4`: `graphical_cultures = { elfgfx turkishgfx indiangfx westerngfx }`).
  This means CK2 race data is real and usable — just at the **culture-group/ethnicity
  template level**, not the per-character-DNA level.
- **Conclusion for the converter**: a deterministic per-character CK2-DNA→CK3-DNA mapping
  is not viable as a general mechanism (too little source data, and even where present,
  CK2's byte values aren't portable across CK2's own graphical_culture art packs, let alone
  into CK3's incompatible gene system). The viable deterministic path is: **CK2 culture
  group / `creature_*` race trait → CK3 ethnicity template** (one ethnicity per race,
  built once, reused for all characters of that race) — exactly the design already fixed
  in `docs/design_races.md` §"What the converter emits," now confirmed correct by this
  research rather than assumed. The ≤221 characters with real CK2 `dna=`/`properties=`
  (deities, canon NPCs) are a small, worthwhile special case for hand-curated
  `common/dna_data` entries, not a template for the general converter.

### 3.5 Staged plan and effort estimate

| Stage | What | Feasibility | Effort (`assumed`, my estimate from the above) |
|---|---|---|---|
| **a. Race templates** | `common/dna_data` + per-race `common/ethnicities` gene ranges, written by the converter from per-race parameters (skin-tone bias via HSV primitive, height via `dwarfism`-style trait_portrait_modifiers, ear/horn morphs only where an asset pack supplies them) | High — format fully reverse-engineered locally (§1), no new engine capability needed | 1–2 person-weeks for the plaintext generation plumbing once the target gene/template names for the current CK3 version are pinned down against a live install |
| **b. CK2 data → CK3 genes, deterministic, rule-based** | Culture-group/race-trait → ethnicity template (the real, data-supported path, §3.4); the ≤221 hand-authored CK2 `dna=`/`properties=` characters get bespoke `dna_data` entries where it matters (bookmark/canon NPCs) | High for the culture-group path; low-value/low-effort for literal DNA translation (too little source data, bytes not portable) | 1 person-week for culture→ethnicity wiring (reuses existing converter race-trait work); a few hours per hand-curated canon character if desired, not a general pipeline |
| **c. Learned photo→DNA model** | A regressor from an arbitrary photo (or CK2 portrait) to the ~98 continuous morph genes (skip accessories/discrete choices) | Plausible — one CK3-specific precedent exists and worked (Hakim1625, ~23k pairs, 6 months hobbyist effort) but needs its own real-photo training data and a render harness that doesn't currently exist | 3–8 person-weeks for a scoped continuous-gene-only regressor reusing that precedent's pipeline shape, **plus** an unbudgeted, currently-undocumented headless-render engineering task (§3.2) for any synthetic-data strategy; double to 6–16 weeks if real-photo generalization quality matters and a real-photo dataset must be crowdsourced or purchased rather than synthesized |

---

## 4. Recommendation

- **Implement now, zero new art** (`verified` feasible from local evidence):
  - CK2 culture group / `creature_*` race trait → one CK3 `common/ethnicities/fae_<race>`
    per race, built from vanilla gene templates (already the design in
    `docs/design_races.md`; now confirmed as the *only* data-supported deterministic path
    from CK2, not merely the simplest one).
  - Per-race body-shape bias via `trait_portrait_modifiers` (dwarf/halfling/gnome height,
    orc build), zero new meshes — reuses vanilla's own `dwarfism`/`spindly` pattern.
  - Skin-tone variation for orc/tiefling/drow via the `skin_hsv_shift_curve` primitive
    (script-only, already shipped in vanilla for age-graying, reused by PoD for exactly
    this purpose) — a small, self-contained gene addition, not an asset dependency.
  - Emit no `dna =` on generated characters generally (CK2 doesn't supply usable per-
    character source data); let the game randomize within the race ethnicity, exactly as
    `design_races.md` §"DNA" already states — now with the negative finding (§3.4) as its
    justification rather than an assumption. Hand-curate `common/dna_data` for the ≤221
    named canon characters separately, if the submod wants that polish.
- **Belongs to the asset library, not the converter** (`ck3_fantasy_assets`): true new
  anatomy — elf ear-tip blendshape/mesh, orc/dragonborn tusks, tiefling/dragonborn horns
  and tails, drow skin-gradient texture beyond the HSV primitive's range. PoD's
  Unlicensed gene/mesh-wiring code (`POD_accessory_genes.txt` horn/tail/wing/hoof
  templates) is a concrete, license-clear starting point for the *technique*, though its
  werewolf/vampire meshes are the wrong shape and need re-sculpting, not direct reuse of
  art.
- **Remains research, not a build task yet**: stage (c) learned photo→DNA. The one
  CK3-specific precedent (Hakim1625) proves the problem class is tractable but not free;
  before committing engineering time, first (i) confirm whether a headless/batch render
  path is buildable at all against the current CK3 version (undocumented, §3.2), and (ii)
  decide whether the target input is CK2 portraits (low-value per §3.4 — too few CK2
  characters carry real portrait data) or arbitrary player-supplied photos (a different,
  more defensible use case: letting a submod artist generate a starting DNA from a
  reference photo, independent of the converter's CK2 pipeline).
- **Format choice for any generated DNA**: always the plaintext `common/dna_data`
  script format (§1.2); never the binary Ruler Designer clipboard blob, which is
  explicitly version-pinned at the byte level and would break on every CK3 patch.

---

## Notes on research method

- This doc reuses `docs/races_research.md` (EK2/Godherja) and `docs/formats_characters.md`
  (general CK2/CK3 key mapping) rather than re-deriving them; only Princes of Darkness, the
  DNA/gene/ethnicity structural deep-dive, the CK2 dna/properties/graphical_culture
  investigation, and the picture→DNA web research are new work products of this task.
- Four parallel research passes fed this doc: CK3 DNA structure (local), CK2
  dna/properties/graphical_culture (local), Princes of Darkness + vanilla-only race
  inventory (local), and web research on tools/feasibility (web). Each pass's raw findings
  are condensed here; nothing here contradicts a source pass, but some raw quotes/line
  ranges were trimmed for length — the evidence CSVs carry the fuller citations for the
  counts tables.
