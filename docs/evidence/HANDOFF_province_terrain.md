# Hand-off — lane `province-terrain`

Date 2026-09-10. Branch `lane/province-terrain`, worktree
`wt/province-terrain`, output `wt/_out/province-terrain`.
Full doc: `docs/step_map_terrain.md`.

## What changed, in one paragraph

`common/province_terrain` was derived from the `terrain.bmp` majority alone.
In CK2 that is only the *fallback*: the `terrain = X` line in a province's
`history/provinces` file **is** its gameplay terrain. 1040 of Faerûn's 2125
province files carry that line and 716 disagree with their own pixels. The
converter now reads it (`ck2ck3.map.holdings.ProvinceHistory.terrains`),
resolves it through `mappings/terrain_history_overrides.csv`, and folds it into
the per-barony vote (`ck2ck3.map.terrain_history`) under `[map]
province_terrain_history = true`.

## Numbers the coordinator should know (`verified`, this lane's own runs)

| | |
|---|---|
| counties with an override the table applies | 899 |
| capital barony's bitmap already agreed | 333 (37.0 %) |
| all its baronies already agreed | 277 (30.8 %) |
| per barony already agreed | 553 of 1681 (32.9 %) |
| CK3 provinces changed | **946** of 3705 |
| — capital took the override | 563 |
| — non-capital, weak bitmap, took it | 383 |
| — non-capital kept its strong bitmap | 182 |
| — already agreed | 553 |
| — kept by rule (`coastal`) | 174 |
| — unmapped category | **0** |
| `farmlands` provinces | 16 → **335** |
| `plains` provinces | 1776 → 1077 |
| trees placed | 711,875 → 700,622 (−11,253, −1.6 %) |
| canvas px changing terrain class | 3,732,425 (6.61 %) |
| terrain **paint** pixels changed | **0** |
| ck3-tiger on the lane output | fatal **0**, error **58** — byte-for-byte the accepted baseline (41 loc-collision, 14 wrong-gender, 2 unknown-field, 1 history) |
| `uv run pytest` | 1173 passed (23 new) |
| `ci/checks.sh` | green |

Evidence: `docs/evidence/terrain_history_survey.md` (tallies + what the bitmap
says under each override), `docs/evidence/terrain_history_effect.md`
(before/after, two real runs), `docs/evidence/terrain_history_baronies.csv`
(one row per affected province, from the real run),
`docs/evidence/tiger_province_terrain.txt` (summary only; the 15 MB body is
regenerable),
`docs/evidence/run_province_terrain.log`.

## The three decisions the coordinator may want to overturn

1. **`coastal` (141 counties) keeps the bitmap** rather than becoming
   `farmlands`. Reasoning in the CSV row and `docs/step_map_terrain.md` §2.1:
   CK2 declares `coastal` with farmlands' exact economics but it is a coastal
   *chokepoint* tag, CK3 derives coastal-ness from the map already, and the
   bitmap under it is five landscapes with no winner (plains 63 %, desert 18 %,
   hills 9 %, arctic 7 %) on provinces named Ruathym, Purple Rocks, The
   Whalebones, al-Faraq Islands. Applying it would hand 141 island counties
   CK3's strongest terrain, 36 of them arctic or desert islets.
   **To overturn: one CSV cell** — `coastal,apply,farmlands`.
2. **A non-capital barony keeps its own bitmap unless that bitmap is `plains`
   or `farmlands`.** 182 baronies. Capital-only would change 563 provinces,
   all-baronies 1128, this rule 946. **To overturn:** `[map]
   terrain_history_weak_classes = []` (capital only) or a longer list.
3. **`glacier` and `arctic` both stay `taiga`** — that is the pixel table's own
   choice and changing it would move the terrain paint, which lane `map-paint`
   owns. `taiga` is mild for polar ground (lowest HF amplitude of all keys).

## What this lane does NOT do, and who it touches

* **Paint is untouched** — it is per pixel, this is per province. Zero paint
  pixels changed, so `docs/report_map_paint.md` **figure 5 does not move**.
  But paint and gameplay terrain now *disagree for 946 provinces*: the ground
  says plains, the tooltip says farmlands. Faithful to CK2 (the bitmap is the
  texture, the history line is the terrain), and recorded in
  `docs/step_map_paint.md` §1b, which supersedes the "never disagree" claim in
  its §2 step 1. A repaint pass is a `map-paint` lane, not this one.
* **Lane `trees-regional`**: 11,253 tree instances vanish because 317 provinces
  become `farmlands`, which `mappings/tree_meshes.csv` deliberately gives no
  mesh. Correct, but visible.
* **Heightmap detail**: 6.61 % of pixels get a new per-terrain HF amplitude
  target, almost all upward (plains 86.3 → farmlands 96.7 / forest 110.7 /
  hills 213.3; hills 213.3 → mountains 311.4). That is the direction
  `docs/step_map_heightmap.md` §7 says our interior land is short in, so lane
  `erosion` / the detail follow-up should re-measure on top of this.
* **Impassability is unchanged**: it is still derived from the bitmap category
  vote, before the override is applied. Faerûn declares
  `impassable_mountains` in no history file anyway.

## Still open

* `subterranean` (60 counties) gets `mountains`. A real Underdark needs a
  terrain type; that is the submod's job, not the converter's.
* Whether the 946 disagreeing provinces should be repainted (see above).
* Not seen in game. The lane's output was validated with ck3-tiger only; a
  headless `-test` run and a look at a farmland county at close zoom would
  close it.
