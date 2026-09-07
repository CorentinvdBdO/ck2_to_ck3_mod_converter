# Races design (converter side)

Evidence: `docs/races_research.md` (Elder Kings 2, Godherja, vanilla, web; 2026-09-07). This file fixes what the converter emits; art and gameplay tuning belong to the submod and the asset library.

## Facts that constrain the design (`verified`)
- Vanilla CK3 has no race concept. Portrait look = `ethnicity` (gene weights). Culture classification = `heritage` pillar. They are orthogonal.
- Best-practice bridge (Elder Kings 2): heritage pillar carries `parameters = { species_x = yes }`; scripts test `culture = { has_cultural_pillar = heritage_x }`.
- Vanilla `dwarf`/`giant` traits force portrait morphs via `gfx/portraits/trait_portrait_modifiers/00_trait_modifiers.txt` — a trait can reshape a portrait with zero new meshes.
- Long life = trait field `life_expectancy` (EK2 `lifespan_1..5`, `is_immortal`); no defines needed.
- Hybrids: EK2 resolves visible anatomy through **two additive morph genes** (half-elf ears blend by inheritance) and non-visual race bookkeeping through an on-birth scripted effect with parent priority.
- No CK3 Forgotten Realms mod exists. No permissively licensed fantasy-race 3D pack exists. EK2, Godherja, Warcraft GoA, EPE assets are not reusable without written permission.
- Faerûn CK2 encodes race twice: culture group (`elves.txt`, `dwarves.txt`…) and `creature_*` traits (incl. `creature_half_elf`, `half_dragon`, `lich`, `vampire`).

## What the converter emits
1. **Heritage per CK2 culture group** (`common/culture/pillars/fae_heritages.txt`) with `parameters = { species_<race> = yes }`, race derived from the CK2 culture file the group lives in (`elves.txt` → `elf`, `dwarves.txt` → `dwarf`, `demihuman.txt` → per-group table, `human.txt` → `human`). Override: `overrides/race_of_culture_group.csv`.
2. **Race traits**: every CK2 `creature_*`/`half_*`/undead trait becomes a CK3 trait with `genetic = yes`, `physical = yes`, `category = fame`-free, CK2 modifiers mapped by the shared trait-modifier table; unmapped modifiers commented. `life_expectancy` filled from `overrides/race_lifespan.csv` (elf 700, dwarf 350, halfling 150, gnome 350, human default…), values are D&D-sourced defaults the submod can tune.
3. **Race assignment at start**: history characters keep their CK2 `creature_*` trait (already in `history/characters`). Characters without one get it from culture heritage via a game-start scripted effect (`fae_race_setup_effect`, EK2 pattern), so no history rewrite is needed.
4. **Inheritance**: `on_birth_child` → `fae_race_inheritance_effect`, generated from `overrides/race_inheritance.csv` (`race_a, race_b, child_race`; default: human×elf → half_elf, human×orc → half_orc, same×same → same, else father's race). Table is data, not design.
5. **Portraits, tiered by asset availability**:
   - Tier 1 (always emitted): `trait_portrait_modifiers` for dwarf/halfling/gnome (vanilla `dwarfism` template scaled), giant (vanilla `giant_height`), orc/half-orc (build + skin bias with vanilla genes). Zero new meshes.
   - Tier 2: one `common/ethnicities/fae_<race>.txt` per race, built from vanilla gene templates; humans map to a vanilla ethnicity by culture group (`overrides/ethnicity_of_culture_group.csv`, default heuristics: Chondathan/Tethyrian → mediterranean, Illuskan/Damaran → north/east european, Calishite/Mulan → arabic/egyptian, Shou → east asian, Rashemi/Nar → steppe…).
   - Tier 3: real anatomy (elf ears, tusks, horns, tails) comes from an asset pack in `ck3_fantasy_assets/packs/`; the converter copies the pack's `common/genes`, `common/ethnicities`, `gfx/` and wires ethnicity names from `ck3_fantasy_assets/docs/races_mapping.md`. Without a pack, ethnicity is a **placeholder** (`# TODO real ethnicity`, Godherja precedent) using the nearest vanilla look.
6. **DNA**: CK2 has none. Emit no `dna =`; the game randomises within the ethnicity. Bookmark characters may later get `dna_data` from the submod.
7. **Non-humanoid cultures** (dragons, undead groups, aberrations, animals): heritage + traits emitted; ethnicity placeholder; `landless`/unplayable flags untouched (comment).
8. **Immortals** (lich, vampire): `immortal = yes` on the trait when CK2 trait has `immortal = yes`; otherwise `life_expectancy` only.

## Asset library contract (`../ck3_fantasy_assets`)
- `packs/<name>/PACK.toml`: `provides = ["ethnicity:elf", "gene:ear_length", ...]`, `license`, `source`, `ck3_version`.
- The converter only consumes packs whose `license` field is one of: `cc-by`, `cc-by-sa`, `cc0`, `mit`, `gpl`, `written-permission` (with the permission file present). Anything else is refused at build time.
- First pack candidates (from research): none ready. Path to real elf ears = commission or build with `io_pdx_mesh` (GPL) following EK2's two-gene additive design as *technique*, not copied data.

## Open decisions (human)
1. D&D edition for lifespans and race list (defaults from 3.5e FRCS to match 1371 DR).
2. Whether half-races are their own heritage (culture) or only a trait (default: trait only; culture follows the parents as vanilla does).
3. Race-locked mechanics from CK2 (darkvision, etc.) — port as trait modifiers where a CK3 modifier exists, else comment. No new mechanics.
