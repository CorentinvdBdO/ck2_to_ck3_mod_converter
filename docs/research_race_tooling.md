# Automating race and character creation: from pictures to CK3 DNA

Lane `research-races`. Research and prototypes only — nothing here changes the converter's step
registry. Builds on `docs/research_dna_races.md` (DNA/gene structure, EK2/Godherja/Princes of
Darkness race precedent), `docs/design_races.md` (the converter's three-layer race model:
ethnicity = appearance, culture = culture, race trait = bonuses/lifespan/reproduction) and
`docs/races_research.md`. Those documents are condensed and cited here, not re-derived; new work in
this doc: the gene-range/morph/mesh classification (§1.3), the headless-render probe (§2.5, new
`verified` findings), the picture→DNA prior-art survey (§3), race-from-many-pictures (§4), the
mass-creation design for the converter's `characters` step (§5), a working prototype
(`scripts/dna_parse.py`, §6), and the roadmap (§7).

Every claim is labeled `verified` (a file was read/grepped, a command was run, or a paper/page was
fetched during this research) or `assumed` (inferred or third-party-reported, not independently
confirmed), each with a source.

---

## Summary

- **Recommended first step**: extend `scripts/dna_parse.py` (built and tested in this lane, §6)
  into the converter's actual mass-character-creation tool — it already resolves a real vanilla
  ethnicity's full ~100-gene table (inheritance chain included) and samples deterministic,
  parser-valid DNA. This is pure data work, zero new art, and plugs directly into the existing
  `overrides/race_of_culture_group.csv` (74 rows) / `overrides/race_lifespan.csv` (136 rows,
  ~30 races) tables from prior lanes (`verified`, both files read in this lane). Effort: **1-2
  weeks**, no research risk left.
- A CK3 "race" a mod actually ships is one of three tiers, and the tier predicts the cost:
  **gene-range** (reuse vanilla meshes, only new weight tables — days), **morph** (new blendshape
  genes on the *existing* mesh topology — needs a sculptor, weeks), **mesh** (new geometry/rig,
  e.g. a body swap or attached limb — needs a 3D artist and `io_pdx_mesh`, weeks-months per race).
  Of the three real mods measured (EK2, Godherja, Princes of Darkness), only Princes of Darkness is
  legally reusable (Unlicense); its horn/tail/wing/hoof gene-wiring *code* (not meshes) is a
  concrete reference for tier "morph"/"mesh" (§1).
- **Picture → DNA is not free, but it is not new either**: one directly-relevant precedent exists
  and worked (`Hakim1625/ck3-image-portrait-modeling`, a ResNet regressor trained on ~23,000
  crowdsourced (screenshot, DNA) pairs, `assumed`, `docs/research_dna_races.md` §3.3). The open
  question this doc answers concretely: **can we render a chosen DNA headlessly, to make our own
  training pairs?** Partial yes, newly `verified` in this lane: the console command
  `dump_bookmark_portraits` is real (confirmed by grepping strings in `ck3.exe`) and dumps
  bookmark-character portraits to disk; it is bookmark-scoped, not arbitrary-DNA, and driving it
  headlessly needs a keyboard-injection tool this machine does not have installed (§2.5). This
  downgrades "undocumented engineering task" (the prior doc's phrasing) to "a scoped few-day task
  with a known missing dependency."
- **CK2 → CK3 per-character DNA translation is a dead end, confirmed by data**: only 1.2% of
  Faerûn's 18,124 characters carry CK2 `dna=`, and CK2's byte values are not portable across race
  art packs anyway (`docs/research_dna_races.md` §3.4, `verified`). The viable, already-designed
  path is race-trait + culture → one shared ethnicity per race, sampled per character with a
  deterministic seed — exactly what `scripts/dna_parse.py` does (§5, §6).
- **Race-from-many-pictures** (building an ethnicity for a race with no vanilla precedent) is a
  two-stage problem: fitting existing gene ranges (cheap, an optimization loop) vs. detecting that
  the race falls outside vanilla's shape space entirely and needs a new morph gene or mesh (the
  reconstruction-error signal from any picture→DNA model, §4) — genuinely new research, not
  guesswork, but no engineering has been done here yet.

---

## 1. Anatomy of a CK3 race, measured on real mods

### 1.1 What a race touches, per mod (`verified` unless noted)

| Mod | Race carrier | Gene files | Ethnicity files | `portrait_modifiers` | `trait_portrait_modifiers` | Mesh count | License |
|---|---|---|---|---|---|---|---|
| Vanilla | n/a (no race concept) | 0 custom | 25 | 33 | 1 file, 2,024 lines (`00_trait_modifiers.txt`) | — | Paradox |
| Elder Kings 2 | culture heritage pillar `species_x` parameter + inherited char flags | 17 (ears/tails/horns/legs morph genes) | 50 | ~50 of 132 | not itemized | 2,227 | not reusable |
| Godherja | culture heritage pillar, mostly cosmetic | 25 (accessories/tattoos only, no body morph) | 5 of 2,795 (1 real body: skeleton) | 0 of 49 | 0 | 0 own (borrows EK2's) | not reusable |
| Princes of Darkness | trait (mutually-exclusive `splat` group) | 6 non-empty of 9 | 0 (same 25 as vanilla) | 15 of 28 | 0 separate file (vanilla file extended in place) | 463 (373 under a dedicated creature folder) | **reusable** (Unlicense) |

Source: `docs/evidence/dna/mod_race_inventory.csv` (this lane's condensation of
`docs/races_research.md` §2-4 and `docs/research_dna_races.md` §2.1, both full local reads of the
three mods' `common/genes`, `common/ethnicities`, `gfx/portraits/*`, and `POD_license.info`).

### 1.2 Data vs. art, per touched system

| System | Kind | Who authors it |
|---|---|---|
| `common/genes/*` (morph/color/accessory declarations) | data (script) | modder, no 3D tool needed for a *new range*; a *new blendshape target* needs the mesh re-exported with that shape baked in |
| `common/ethnicities/*` (weight tables) | pure data | modder, script only |
| `common/dna_data/*` (concrete DNA entries) | pure data | modder or **generated** — this is the converter's actual output target (§5) |
| `gfx/portraits/portrait_modifiers/*`, `trait_portrait_modifiers/*` | data (script), references art assets | modder, script only, if reusing existing meshes/textures |
| `.mesh` / rig / skeleton files | art (3D) | needs `io_pdx_mesh` (GPL, Blender exporter) and a modeler; this is where all three mods' real cost sits (EK2's 2,227 meshes vs. Godherja's near-zero own work vs. PoD's 463 in one creature folder) |
| Palette textures (`hair_palette.dds` etc.) | art (2D) | only touched for skin/hair/eye tones outside vanilla's gradient range |

### 1.3 Classification: gene-range / morph / mesh

This is the lane's own synthesis, not a Paradox-defined taxonomy, built to answer "what does it
cost to add race X":

- **gene-range** (cheapest, data-only): reuse vanilla meshes and vanilla gene *templates*, only
  write a new weight table (an ethnicity) or push an existing template past its default range
  (`trait_portrait_modifiers`, the vanilla `dwarf`/`giant` pattern, `00_trait_modifiers.txt:1-40`
  quoted in `docs/research_dna_races.md` §1.4). Zero new assets. Examples measured: Godherja's
  `gh_aelfir` (elf, explicit `# TODO: Implement an actual ethnicity`, falls back to a human
  ethnicity, `verified`); vanilla dwarf/giant height; PoD's Fera intermediate werewolf forms
  (reuses `giant_height`, `verified`, `docs/research_dna_races.md` §2.2).
- **morph** (medium, needs a sculptor once per gene, then free per character): a new blendshape
  *target* baked into the existing mesh topology, declared as a new gene so it blends naturally on
  inheritance. The one documented, reusable *technique* found in this research: EK2's
  `ek_genes_mer.txt` — two separate additive ear-length genes capped at 0.5 each, so a half-elf
  child inherits an intermediate ear length through ordinary CK3 genetics, no scripted logic
  (`verified`, direct quote in `docs/races_research.md` §2). PoD's horn/tail/wing/hoof genes
  (`POD_accessory_genes.txt`, 1,612 lines) are the license-clear reference implementation of this
  tier (`verified`).
- **mesh** (most expensive): new geometry and/or a new skeleton — a full body swap
  (`body_replacement`, Godherja's skeleton race, `verified`,
  `0_GH_ethnicities_skeleton.txt:1-30`) or an attached limb requiring its own rig (PoD's crinos
  battle-form, a full mesh swapped in via an accessory-gene slot, `verified`,
  `docs/research_dna_races.md` §2.1). This tier is where EK2's 2,227-mesh cost concentrates.
- **The hard floor**: no vanilla gene exists for tusk, horn, tail, wing, hoof or claw anywhere in
  1.19 (`verified`, `grep -rin tusk common/genes/` = 0 hits, `docs/research_dna_races.md` §2.2) — any
  D&D race needing these (orc tusks, tiefling/dragonborn horns+tails, dragonborn snout) starts at
  tier morph at best, tier mesh if the shape is too different from a humanoid head/torso topology.
  Skin-tone races (orc, tiefling, drow, genasi) can mostly stay at tier gene-range using
  `skin_hsv_shift_curve` (`01_genes_morph.txt:9745-9757`, vanilla's own age-graying primitive,
  reused by PoD for exactly this, `verified`).

---

## 2. The DNA format

Full structural detail already in `docs/research_dna_races.md` §1 (`verified`, direct reads of
`common/genes/`, `common/ethnicities/`, `common/dna_data/`, `common/defines/00_defines.txt`); this
section is the condensed version plus one new subsection (§2.5).

### 2.1 Gene declaration (three kinds)
- **Morph genes** (`01_genes_morph.txt`, 98 genes): continuous face/body sliders, named templates
  (usually `_neg`/`_pos` pairs), per-gender curves.
- **Color genes** (`00_genes_color.txt`, 3: hair/skin/eye): a 2D coordinate into a palette texture
  (`hair_palette.dds` 512×512, `skin_palette.dds`/`eye_palette.dds` 256×256), not a scalar.
- **Accessory genes** (9 files, ~899 templates: hairstyle 85, beard 47, clothes 199, headgear 245,
  misc props 295, makeup 7, eye/teeth/eyelash 13, plus 28 special-visual and 13 special-misc):
  discrete, weighted-random named-asset picks.
- Body shape is only 5 of the 98 morph genes (`gene_height`, `gene_bs_body_type`,
  `gene_bs_body_shape`, `gene_neck_length`/`_width`, `gene_body_hair`); everything else is
  face/head. No shoulder-width or torso-length axis exists at all.

### 2.2 The DNA string: plaintext only, never the binary clipboard blob
- `common/dna_data/*.txt` stores each character's genes as `gene_key = { "template_a" byte_a
  "template_b" byte_b }` (morph/accessory, diploid — two alleles) or `color_key = { xa ya xb yb }`
  (color, two 2D coordinates), `verified`, `00_dna.txt:4-113`.
- `history/characters` `dna =` is always a **reference** into `common/dna_data`, never an inline
  literal (`verified`, 80 files checked, zero inline literals).
- The in-game Ruler Designer's "Copy DNA" produces a **different**, base64-encoded,
  version-pinned binary blob (`assumed`, web, CK3 Wiki + community tool docs) —
  `GENE_DATABASE_VERSION = 5` in `common/defines/00_defines.txt:1350` confirms the schema is
  versioned and mismatched files get silently regenerated. **Any generator must target the
  plaintext `common/dna_data` format**, never the blob, which breaks on every patch that bumps that
  define.

### 2.3 Ethnicities: weighted ranges, resolved independently per gene, with inheritance
- An ethnicity block declares `template = "<base>"` (defaults) and optionally
  `using = "<other>"` (a second inherited layer), then its own weighted tables per gene; the
  block's own entries win over both inherited layers, one whole gene-table replacement at a time
  (`verified`, confirmed structurally by this lane's own parser, `scripts/dna_parse.py`
  `resolve_gene_table`, §6). No cross-gene correlation is declared anywhere (`verified`, no such
  define in `00_defines.txt`).
- Newly measured in this lane (`verified`, `dna_parse.py --self-test` against the live 1.19
  install): `mediterranean` declares only 7 of its own gene tables but **resolves to 103** through
  its `template`/`using` chain — most of an ethnicity's actual content is inherited, not local.
  One live vanilla quirk this tool had to tolerate: `mediterranean` declares `using = "basque"`,
  but no `basque` ethnicity block exists anywhere in the 1.19 install (dead or DLC-gated
  reference) — a resolver that hard-fails on a missing `using` target cannot process vanilla's own
  files as shipped.

### 2.4 Trait-forced portrait overrides (the zero-mesh mechanism)
`gfx/portraits/trait_portrait_modifiers/00_trait_modifiers.txt` (2,024 lines) maps a trait to a
bundle of forced gene/template/value overrides — vanilla's `dwarf`/`giant`/`albino`/`scaly`
examples (`verified`, quoted in full in `docs/research_dna_races.md` §1.4). This is the tier
"gene-range" mechanism from §1.3 and the one the converter already plans to use for
dwarf/halfling/gnome/orc height and build (`docs/design_races.md` item 5, Tier 1).

### 2.5 Can we render a given DNA headlessly? (new in this lane)

- **No general (arbitrary DNA → PNG) batch tool exists**, official or community (`assumed`,
  `docs/research_dna_races.md` §3.2, prior web research against the Console Commands wiki page and
  multiple GitHub tool repos — unchanged by this lane's work).
- **New, `verified` this lane**: grepping the installed `ck3.exe` for console-command strings
  confirms `dump_bookmark_portraits` is real — the string
  `"Auto generated file, do not edit manually. Created using console command
  dump_bookmark_portraits"` is embedded in the binary as the header it writes into its output file.
  A second, previously undocumented mechanism also exists in the binary: `portrait_editor` /
  `gui/portrait_editor_window.gui` — a debug portrait-editing window, unexplored (would need a live
  debug-mode session to drive). Full probe, exact commands and output:
  `docs/evidence/dna/headless_render_probe.md`.
- **What blocks batching it today**: both are console commands, and this environment has **no**
  keyboard/mouse input-injection tool installed (`xdotool`/`ydotool`/`wtype` all absent,
  `verified`, `which` check) — the existing headless harness (`ck3_launch.sh`,
  `ck3_probe_shots.sh`) only waits for a log marker and takes a `weston-screenshooter` screenshot;
  it has never typed into the game. No file- or argument-driven batch console-command runner exists
  either (`verified`, no `-exec`/`-run_console_commands`-shaped string in the binary).
- **Revised effort estimate** (was "unbudgeted, currently-undocumented" in
  `docs/research_dna_races.md` §3.2): install `ydotool`/`wtype` (needs sudo, ~5 min), extend
  `ck3_launch.sh`'s pattern to send console keystrokes once the frontend log marker appears, then
  read the dumped file out of the Proton prefix — **a few hours of scoped engineering**, not an
  open research question. Untested: how many `common/bookmarks` entries one
  `dump_bookmark_portraits` call handles per launch (bounds throughput; cheap next check, write 50
  throwaway bookmarks and count output files).
- **Practical implication for training-pair generation** (feeds §3's recommended pipeline): the
  render path is bookmark-scoped, so a synthetic-data generator must write a throwaway
  `common/bookmarks` + `common/dna_data` entry **per DNA**, batch as many as one launch will dump,
  and pay one game-restart cost (~40-55 s headless, `CLAUDE.md`) per batch, not per image.

---

## 3. Picture → DNA: survey of prior art

### 3.1 What's already known locally (condensed from `docs/research_dna_races.md` §3)
- Which genes are learnable targets: the 98 continuous morph genes (good regression targets, one
  scalar intensity per allele) and the 3 color genes (2D palette coordinates, two outputs each);
  the ~899 accessory templates are a classification problem, not regression, and much less
  reliable from a 2D source image (occlusion, stylization).
- **The one directly relevant precedent**: `Hakim1625/ck3-image-portrait-modeling` (`assumed`, web,
  GitHub, 28 stars, last pushed 2022-07-08) — a ResNet regressor, PyTorch + PyTorch Lightning +
  dlib, trained on a **crowdsourced ~23,000 (screenshot, DNA) pairs / ~8,900 unique characters**,
  built manually over ~6 months, no synthetic data. Adding gender as an output *degraded* accuracy
  — output-space growth costs data non-linearly.
- Several plaintext/binary DNA-format converter tools exist (community, small, `assumed`): CK3 DNA
  Converter, CK3-DNA-Duplicator, ck3-dna-beautifier, CK3-Gene-Homogenizer, CK3-Gallery/"DNA Forge",
  the DNA-updater byte-migration tool — all format tooling, none do picture→DNA.
- No synthetic-data-only strategy (render known DNA, train only on (render, DNA) pairs, skip
  crowdsourcing) was found documented for CK3 — an open, untested idea, not a validated shortcut.

### 3.2 Web survey: academic and adjacent prior art (this lane, new)

_[integrated from a dedicated web-research pass; see inline citations below]_

- **"Face-to-Parameter Translation for Game Character Auto-Creation" (Tianyang Shi, Yi Yuan,
  Changjie Fan, Zhengxia Zou, Zhenwei Shi, Yong Liu — NetEase Fuxi AI Lab et al., 2019)** —
  `verified` (author list confirmed against the paper's own arXiv listing, not just abstract-level),
  arXiv 1909.01064 / ICCV 2019. Self-supervised: an "imitator" neural network
  is trained to mimic the target game engine's own renderer (learned from (parameter, rendered
  image) pairs the game itself produces), then a face-recognition-network similarity loss between
  the source photo and the imitator's output is backpropagated through the imitator to optimize the
  game's face parameters directly — no differentiable renderer needed, only a differentiable
  *stand-in* for one. This is the closest published technique to "no differentiable CK3 renderer
  exists, but we can still fit its parameters," and the strongest single transferable idea for a
  CK3 pipeline: train a small neural imitator of the game's own portrait renderer from
  (DNA, rendered-headless-portrait) pairs (§2.5's render path supplies exactly this data), then
  optimize DNA against a face-similarity loss through that imitator instead of the real game.
- **"MeInGame: Create a Game Character Face from a Single Portrait" (Jiangke Lin, Yi Yuan,
  Zhengxia Zou — NetEase Fuxi AI Lab, 2021)** — `verified` (author list confirmed against the
  paper's own arXiv listing), arXiv 2102.02371 / AAAI 2021. Different architecture: regress 3DMM (3D Morphable Model)
  face-shape/texture coefficients from the photo via a CNN, render with a differentiable renderer,
  compare, and separately map 3DMM coefficients to the target game's own bone/blendshape
  parameters. Needs a differentiable renderer and a pre-existing 3DMM — a heavier dependency stack
  than F2P's, but reportedly generalizes better to identity than the direct-regression approach; a
  CK3 adaptation would need to either build a lightweight differentiable proxy of the 98-morph-gene
  system (nontrivial, no existing PyTorch reimplementation found) or skip 3DMM and use its texture
  step only.
- **CLIP / DINOv2 as the image encoder for a downstream regressor**: `assumed`, general ML
  practice, not CK3-specific — both are pretrained on large photo corpora and used off-the-shelf as
  frozen feature extractors feeding a small trainable head (linear or shallow MLP) onto a
  target-parameter vector; this is the standard cheap starting point when the labeled dataset (here,
  (photo, DNA) pairs) is small, since only the head needs training. Rough cost: encoder inference is
  a single forward pass per image (a few ms on an RTX 5070 Ti), head training is minutes-to-hours
  for a few thousand pairs.
- **Gradient-free / black-box optimization for "render, compare, update" loops**: CMA-ES and
  Bayesian optimization are the standard choices when the renderer genuinely cannot be
  differentiated through (`assumed`, general optimization literature) — directly applicable to CK3
  if F2P's imitator-network trick is skipped: run the real headless render (§2.5) as the black-box
  objective, optimize the ~100-dimensional continuous gene vector against a face-similarity score.
  Much slower per iteration (one real game restart+render vs. one imitator forward pass) but needs
  no learned proxy at all — the right choice for a small number of hand-curated canon characters
  (§3.4's "≤221 named characters" case), wrong for scaling to thousands.
- **CK3-specific/adjacent community tools beyond Hakim1625**: no additional CK3 photo→DNA tool or
  diffusion-based CK3 portrait pipeline was found beyond what `docs/research_dna_races.md` §3.3
  already lists. This remains a thin field — one hobbyist project is the entire direct precedent.
- **Legal/ethical notes on training data** (`assumed`, general web/policy knowledge, not
  CK3-specific): scraping a subreddit (e.g. a "CK3 Tinder"-style community) for face photos used as
  ML training data sits in a genuinely unsettled area — Reddit's API terms restrict bulk/commercial
  scraping and most subreddits' content is user-photos-of-real-people, which raises right-of-publicity
  and (for EU subjects) GDPR biometric-data concerns distinct from ordinary web-scraping copyright
  fights; several unrelated AI-training-data lawsuits (Getty v. Stability AI, NYT v. OpenAI) turn on
  exactly this class of question and remain unresolved. **Recommendation for this project**: prefer
  the synthetic (headless-render → DNA) pipeline for the bulk of training data (§2.5), since it
  needs no real people's photos at all; if real photos are used at all, restrict to consenting
  contributors or deceased public figures with no living likeness-rights claim, and never scrape a
  subreddit's images without explicit permission from posters.

### 3.3 CK2 → CK3: the decisive negative finding (condensed from `docs/research_dna_races.md` §3.4)
- Only **221 of 18,124** Faerûn characters (~1.2%) carry CK2 `dna=`, and CK2's byte values are not
  portable across CK2's own graphical-culture art packs (a saurial's 20-frame sprite pool vs. a
  human's 4-13), let alone into CK3's incompatible gene system (`verified`). A deterministic
  per-character CK2→CK3 DNA translation is **not viable**. The data-supported path is
  race/culture-group → one shared CK3 ethnicity, exactly `docs/design_races.md`'s design.

### 3.4 Recommended pipeline for CK3

| Stage | Approach | Data | Cost (`assumed`, this lane's estimate) |
|---|---|---|---|
| 0. Race templates (do this regardless) | rule-based CK2 culture/race → CK3 ethnicity + trait, §5 | none (script only) | 1-2 weeks (§6 prototype most of the way there) |
| 1. Synthetic pair generation | §2.5's bookmark-dump render path, N random DNAs → N portraits | thousands of (DNA, PNG) pairs, zero real people | a render engineering task (§2.5) + throughput bounded by batch size, likely low hundreds of images/hour once working |
| 2a. Imitator network (F2P-style) | small CNN trained to reproduce the game's own renderer from (DNA, PNG) pairs | the stage-1 synthetic set | days of GPU time on an RTX 5070 Ti for a network this size, once data exists |
| 2b. Photo → DNA regressor | CLIP/DINOv2 frozen encoder + small MLP head, trained against face-similarity through the imitator (F2P) or directly against known DNA for synthetic pairs | stage-1 set (synthetic) ± a small real-photo set for generalization | hours-days on an RTX 5070 Ti for the head; accuracy on **real** photos untested without real-photo eval data |
| 3. Canon/bookmark characters (small N) | CMA-ES / Bayesian optimization directly against the real headless renderer, no learned proxy | none beyond the target photo | minutes-hours per character, one-off, no training |

- Accuracy honestly cannot be estimated without building stage 1 first — the only real CK3 data
  point (Hakim1625) used **real crowdsourced pairs**, not synthetic ones, so it does not validate
  the synthetic-data shortcut this pipeline leans on. That validation (does a model trained only on
  synthetic renders generalize to real photos at all?) is this pipeline's single biggest open risk,
  and the reason §7's roadmap puts it after, not before, the deterministic race-template tool.

---

## 4. Race from many pictures

Turning a set of reference images of a fantasy race (no CK3 or CK2 precedent) into usable game data
is two separable problems, both currently unimplemented:

- **(a) An ethnicity (gene ranges)**: if the picture→DNA model from §3 exists, run it over every
  reference image and take the resulting DNA vectors' empirical distribution per gene as the new
  ethnicity's weighted ranges directly — this is mechanically simple once §3 exists (fit a
  min/max range per continuous gene, a discrete weighted list per accessory choice) and needs no
  new research, only the upstream model.
- **(b) Detecting "this needs a new morph/mesh, not just a range"**: the signal is the same model's
  own **reconstruction error** — render the fitted DNA back out (§2.5's render path) and compare to
  the source images with the same face-similarity metric used in training (§3.2, F2P's approach).
  A race that fits vanilla's shape space (e.g. an unusually pale or robust human population) should
  converge to low reconstruction error entirely within existing gene ranges; a race with actual
  novel anatomy (pointed ears, tusks, a snout) will show a **systematic, spatially-localized**
  residual — the model will find the closest vanilla-shape approximation but consistently miss in
  the same face region across every reference image of that race. This is a real, checkable
  automatic signal (not guesswork) once §3's model exists, but **no engineering toward it has
  happened in this lane** — it depends entirely on §3 existing first, so it belongs after stage 2
  of §3.4's pipeline, not before it.
- Concretely for this project: elf ears, orc/dragonborn tusks, tiefling/dragonborn horns+tails
  would all trip this signal today by inspection alone (§1.3 already establishes zero vanilla gene
  covers any of them) — the automatic detector's value is for races the project has not already
  manually classified, or for a submod's own novel races the converter never saw.

---

## 5. Mass creation for the converter

This section is the concrete design for wiring §2-4's tooling into the `characters` step, following
`docs/design_races.md`'s already-fixed three-layer model (ethnicity = appearance, culture =
culture, race trait = bonuses/lifespan/reproduction) — **the converter still never invents content**
(`CLAUDE.md`); everything below is a standalone tool feeding `overrides/`, not a new converter step.

- **What already exists** (`verified`, read in this lane): `overrides/race_of_culture_group.csv`
  (74 rows, CK2 culture group → race, seeded by `scripts/seed_culture_overrides.py`) and
  `overrides/race_lifespan.csv` (136 rows, ~30 distinct D&D races, D&D 3.5e max-age defaults). These
  already answer "what race and what lifespan" per culture group; DNA generation is the missing
  piece between "this character is a drow" and "this character has a face."
- **The tool** (extends `scripts/dna_parse.py`, §6, not a new design): for each of Faerûn's 18,124
  characters,
  1. resolve `race` from the character's existing `creature_*` trait, or from
     `overrides/race_of_culture_group.csv` via culture group if none (exactly `docs/design_races.md`
     item 3's rule, already decided, not reopened here);
  2. resolve the CK3 ethnicity for that race — Tier 2/3 per `docs/design_races.md` item 5 (a
     `common/ethnicities/fae_<race>` file, or an asset-library pack's ethnicity if one exists);
  3. sample one DNA from that ethnicity with `dna_parse.sample_dna(table, seed_key)`, where
     `seed_key` is **the character's own CK2 id** (`f"{ck2_id}:dna"` or similar) — this is what
     makes the whole run reproducible: re-running the converter after an unrelated change produces
     byte-identical DNA for every character, a property `dna_parse.py`'s `--self-test` already
     verifies for a single sample (§6) and that a real integration must verify at the 18,124-row
     scale;
  4. write `common/dna_data/fae_generated_dna.txt` (one file, all characters) and set
     `dna = <id>` on each `history/characters` entry — this is a converter-shaped change (touches
     the `characters` step's output) and is explicitly **out of scope for this research lane**; the
     tool this lane built stops at "produces valid `common/dna_data` text from an ethnicity file,"
     the wiring into `characters` is implementation work for a future lane.
- **Named/canon characters** (the ≤221 with real CK2 `dna=`/`properties=`, per
  `docs/research_dna_races.md` §3.4): not worth a general pipeline (too little source signal, bytes
  not portable, §3.3). If picture-guided DNA is wanted for specific canon NPCs (deities, named
  rulers), that is §3.4's stage-3 path (CMA-ES/Bayesian optimization against the real renderer,
  one-off, minutes-hours per character) — feed it through the same `overrides/`-style mechanism
  (a hand-curated `common/dna_data` entry per character, or a CSV of `ck2_id → reference_image_path`
  that a future tool consumes), never a converter-invented guess.
- **Cost at scale**: sampling 18,124 DNAs from ~30 ethnicities is seconds of CPU (the expensive part
  is building the ~30 ethnicities themselves, if going beyond Tier 1 gene-range reuse — an art-team
  question, not a converter question, per `docs/design_races.md`'s asset-library contract).

---

## 6. Prototype: `scripts/dna_parse.py`

Built and tested in this lane; not wired into the converter (`ci/checks.sh` green, 6 pytest cases in
`tests/test_dna_parse.py`, plus a `--self-test` mode that exercises it against the live vanilla
install). Read-only against game files; writes only to a path the caller names.

- **`index_ethnicities(dir)`**: parses every `common/ethnicities/*.txt` file with the converter's
  own `ck2ck3.pdx` parser (reused as-is, no new parser invented — the "no converter step changes"
  rule extends to not duplicating converter internals either) and resolves `@var` references
  per-file, matching how vanilla actually scopes them (each ethnicity file redeclares its own
  `@neg1_min`/`@pos1_min`/etc.).
- **`resolve_gene_table(name, index)`**: walks an ethnicity's `template =` base then `using =`
  layer then its own entries, later layers replacing a gene key wholesale — Paradox's own
  override-by-key semantics, confirmed against real files rather than assumed. Tolerates a missing
  `using` target (vanilla's own `mediterranean → basque` dead reference, §2.3) instead of crashing.
- **`sample_dna(gene_table, seed_key)`**: two independent allele draws per gene from a
  `hashlib.sha256(seed_key)`-seeded RNG — deterministic in `seed_key` alone, order-independent,
  exactly the "deterministic seed per character" property §5's design needs.
- **`format_dna_entry` / `--self-test`**: writes the exact `common/dna_data` plaintext grammar and
  round-trips the output back through the real parser as a correctness check.
- **Measured against the live 1.19 install** (`verified`, this lane): 51 ethnicities indexed;
  `mediterranean` resolves to 103 genes through inheritance (declares only 7 directly, §2.3);
  sampling is deterministic per seed key and every emitted byte value is in 0-255; the emitted
  script re-parses with zero problems.

```
$ uv run scripts/dna_parse.py --ethnicity mediterranean --count 2 --seed demo
fae_dna_sample_0 = {
	portrait_info = {
		genes={
			skin_color={ 177 124 190 113 }
			eye_color={ 60 156 84 174 }
			hair_color={ 224 210 211 229 }
			gene_chin_forward={ "chin_forward_neg" 123 "chin_forward_pos" 128 }
			... (103 genes total)
```

Usage: `docs/../scripts/dna_parse.py --help`; `--self-test` for the determinism/round-trip check;
`--list-ethnicities` to enumerate what an install (vanilla or a mod pointed at with
`--ethnicities-dir`) declares.

**Known limitations, honestly stated**: accessory genes (hairstyle, beard, clothes, headgear) are
out of scope — only the two continuous kinds (color, morph) are sampled; a real character also
needs those, currently left to the game's own randomization (matches `docs/design_races.md`'s
existing "emit no `dna =`, let the game randomize" fallback, so this is a strict improvement, not a
regression, when generation is skipped).

---

## 7. Roadmap

| Phase | What | Risk | Needs | Weeks |
|---|---|---|---|---|
| **1. Deterministic race DNA (recommended first step)** | Wire `dna_parse.py` into a converter-facing tool: per-character seed, per-race ethnicity resolution, write `common/dna_data` + set `dna =`. Build the actual Tier 2 `fae_<race>` ethnicities (currently placeholders per `docs/design_races.md`). | Low — format fully reverse-engineered, prototype already works against real data | code only, plus ~30 ethnicity files (data, no art) | 1-2 |
| **2. Headless render harness** | Install `ydotool`/`wtype`; drive `dump_bookmark_portraits` from a headless launch; verify batch size per launch; produce the first (DNA, PNG) synthetic pairs. | Medium — first real automation of game input in this harness, weston keyboard-focus is untested | sudo for one package install, a few hours of scripting against `ck3_launch.sh`'s pattern | 1 |
| **3. Synthetic-data picture→DNA regressor** | CLIP/DINOv2 encoder + small head, trained on phase-2's synthetic pairs; F2P-style imitator network as a stretch goal. | Medium-high — the synthetic-only strategy is unvalidated (§3.4); real-photo generalization is the open question | phase 2's data, GPU time (RTX 5070 Ti, days), no real-photo data needed for the synthetic-only variant | 2-4 |
| **4. Real-photo evaluation / fine-tuning** | Test phase 3's model on real photos (legally-sourced only, §3.2); decide if crowdsourcing or a small consenting-contributor set is needed. | High — legal/ethical sourcing constraints, and this is where Hakim1625's 23k-pair, 6-month precedent suggests real effort is required | a sourcing decision (human), possibly weeks of data collection | 4-8 |
| **5. Race-from-many-pictures + gap detection** | Fit an ethnicity from reference images (§4a); reconstruction-error-based new-morph/mesh detection (§4b). | Medium — mechanically simple once phase 3 exists, unbuilt today | phase 3's model | 1-2 after phase 3 |
| **6. New anatomy (art)** | Elf ears, tusks, horns+tails as tier-morph genes (EK2's two-gene additive technique, §1.3), following the asset-library contract in `docs/design_races.md`. | Low-medium technically (PoD's Unlicensed code is a clear reference), high in art-hours | a 3D modeler + `io_pdx_mesh` (GPL) | ongoing, per-race, independent of phases 1-5 |

**Recommended order**: phase 1 now (this lane's prototype gets it most of the way there, zero
research risk left); phase 2 next as a cheap, scoped engineering task that de-risks everything
downstream; phases 3-5 only after 1-2 are shipped and only if picture-guided generation is actually
wanted (phase 1 alone already solves "18,124 characters need plausible faces"); phase 6 is
independent and can start whenever the submod has art budget, using PoD's code as a technical
reference (never its meshes).

---

## Notes on research method

- Local evidence: this lane's own reads of `common/genes/`, `common/ethnicities/`,
  `common/dna_data/`, `gfx/portraits/trait_portrait_modifiers/`, and `strings` against the
  installed `ck3.exe` binary (§2.5); reused, not re-derived, evidence from
  `docs/research_dna_races.md` and `docs/races_research.md` for the EK2/Godherja/PoD mod inventory.
- Web evidence: §3.2's academic/prior-art survey ran as a dedicated research pass; every claim
  there is `assumed` (paper abstracts and community pages, not independently reproduced) and
  carries a paper name, venue and rough date for a reader to verify directly.
- The prototype (`scripts/dna_parse.py`, `tests/test_dna_parse.py`) is genuinely tested: 6 pytest
  cases against a synthetic fixture (inheritance, determinism, byte-range, round-trip) plus
  `--self-test` against the live vanilla install (51 ethnicities, 103-gene resolution for
  `mediterranean`).
