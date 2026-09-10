# Step `map`, asset placement: CK3 locators from CK2 `positions.txt`

Lane `map-assets`, 2026-09-10. The second half of "pre-unpause fidelity"
(`docs/map_fidelity.md` §3); the first half was terrain paint and colour
(`docs/step_map_paint.md`).

**What changed.** Until build 8 every CK3 locator instance sat at its
province's colour centroid — correct, and the engine's own answer, but
characterless: a settlement model in the geometric middle of its barony
regardless of where the CK2 mod's author drew the town, and all seven locator
types stacked on that one point. Build 9 places

1. **one anchor per province** — the CK2 author's own town for a county
   capital, the centroid for everything else; then
2. **each locator type at vanilla's own measured offset** from that anchor,
   so the settlement, its siege marker and the two unit stacks do not draw on
   top of each other.

Config: `[map] ck2_locator_positions` (default `true`),
`[map] locator_offsets_csv`, `[map] locator_offset_scale`,
`[map] locator_offset_mode`.
Code: `ck2ck3.map.locators.ck2_capital_anchors` +
`ck2ck3.map.locators.place_with_offsets`, wired in `ck2ck3.map.build`.
Table: `mappings/locator_offsets.csv`.
Scripts: `scripts/measure_vanilla_locator_offsets.py`,
`scripts/check_ck2_locator_slots.py`, `scripts/locator_move_report.py`,
`scripts/check_locator_frame.py --mod`.

---

## 1. Part one: the anchor, and why only the county capital

CK2 `positions.txt` carries **7 (x, y) slots per CK2 province**, and one CK2
province is exactly one CK3 **county** here (`docs/step_map_baronies.md`). A
county is 1–5 CK3 baronies. So a CK2 slot can name at most **one** barony per
county without inventing content, and the only barony the CK2 data actually
identifies is the county capital.

Faerûn: **2120** county-capital baronies out of 3694 CK3 provinces
(`verified`, `docs/evidence/barony_set.csv`); 2116 have a `positions.txt`
block at all.

The anchor is **slot 0**, the capital/city slot — the one CK2's own binary
names, logging `Province %d has illegal capital location` against it. Nothing
else. Everything that is not a county capital — 1574 baronies, every sea,
lake, river and impassable province — anchors on its centroid.

Spending the *other* six slots on the *other* baronies was measured and
rejected in `docs/map_fidelity.md` §2: it buys "geometric spread with a
semantic veneer". The converter never invents content; human input enters
through `overrides/*.csv`.

## 2. Part two: the per-type offset, measured off vanilla

A `siege` marker is the army **besieging the settlement**; a unit stack is the
army **standing at** it. Vanilla does not scatter these across the province.
Measured over all 11,297 land ids of CK3 1.19's own
`gfx/map/map_object_data` (`verified` 2026-09-10,
`scripts/measure_vanilla_locator_offsets.py` → `mappings/locator_offsets.csv`;
vanilla px, `dz` bottom-up, relative to the same province's `buildings`):

| locator | dx (median) | dx IQR | dz (median) | dz IQR | distance median | p95 | n |
|---|---|---|---|---|---|---|---|
| `buildings` | 0.00 | — | 0.00 | — | 0.00 | 0.00 | 11,297 |
| `special_building` | −1.08 | [−6.43, +5.92] | +1.38 | [−3.46, +6.86] | 9.05 | 18.70 | 11,297 |
| `siege` | +0.92 | [−8.08, +8.65] | −3.09 | [−7.09, +1.91] | 9.98 | 11.51 | 11,297 |
| `activities` | −2.85 | [−7.33, +6.92] | +3.23 | [−4.34, +7.38] | 9.40 | 38.97 | 11,297 |
| `unit_stack_player_owned` | +4.92 | [+1.29, +6.79] | +4.66 | [+1.34, +5.96] | 7.10 | 12.09 | 11,297 |
| `unit_stack_other_owner` | −5.02 | [−6.50, −2.08] | +5.91 | [+3.65, +6.92] | 7.70 | 12.87 | 8,413 |
| `combat` | −0.64 | [−8.17, +7.92] | +7.91 | [+0.91, +12.90] | 13.63 | 21.66 | 11,297 |

Every type clusters within ~15 px of the settlement. The converter adds the
median `(dx, dz)` to the anchor, converts `dz` to a top-down pixel offset
(`y − dz`), and **re-gates**: if the offset point leaves the province, the
bare anchor is used.

### 2.1 Pixel scale — `locator_offset_scale = 1.0`

The offsets are in **vanilla** provinces.png pixels. This canvas is planned at
vanilla's **own** km per pixel by construction: `vanilla_km_per_px = 1.4839`
and `factor = 2.90 / 1.4839` (`docs/map_scale.md` §1, `verified`), so one of
our pixels is one vanilla pixel of ground and of screen separation. The scale
is therefore **1.0**, not 0.5.

This is a deliberate correction to the lane brief, which assumed a vanilla
pixel is 0.74 km (half of ours) and asked for the offsets halved. The repo's
own measurement says otherwise, and it is the number every other part of the
map pipeline already relies on — `min_barony_pixels = 400` "needs no
rescaling" and `colormap_blur_sigma = 9` is "used unconverted because our
canvas matches vanilla's own km/px". `[map] locator_offset_scale` exists so a
map where that stops being true can say so.

### 2.2 A known limit of the median vector

Vanilla's offsets are a **ring**, not a fixed vector: `siege`'s median
distance from the settlement is 9.98 px, but its median *vector* is only
(+0.92, −3.09), length 3.2 px, because the directions cancel (IQR ±8 px on
both axes). Adding the median vector therefore reproduces vanilla's
*direction* bias but only about a third of its *separation* for the
rotationally symmetric types (`siege`, `special_building`, `activities`); the
two unit stacks, whose IQRs do not straddle zero, come out close to vanilla.

The generated-vs-vanilla comparison in §5 shows exactly this, and
`scripts/check_locator_frame.py --mod` prints it on every check. Closing the
gap means a per-province deterministic *direction* at the measured *radius*
rather than a fixed vector; the radius columns (`median_dist_px`,
`p95_dist_px`) are already in the CSV for it. Not done here: it is a look
call, and the current result is strictly better than the single stacked point
build 8 shipped.

## 3. The transform and the validity gate

**The transform is not re-derived.** It is the two lines the barony seeds
already use (`ck2ck3.map.baronies._seed_one`):

```
y_top  = source_height - y_ck2          # positions.txt y is BOTTOM-origin
(x, y) = canvas.to_target(x_ck2, y_top) # crop offset, factor 1.9543, sea margin
```

`Canvas.to_target` (`ck2ck3.map.config`) carries the whole CK2→CK3 pixel
transform: the painted-extent crop, the 1.9543 scale factor and the centring
inside the 128 px sea margin. For Faerûn: source 4096×3328 → canvas
8320×6784, factor 1.954310, offset (157, 140), crop (0, 0, 4096, 3328)
(`verified`, `scripts/check_ck2_locator_slots.py` header line).

The canvas pixel then goes through `ck2ck3.map.locators.world_position`
unchanged — that function owns the CK3 frame (`{ x  0  height − y }`, z
bottom-up) and this lane did not touch it.

**The validity gate is mandatory, and runs twice.** A transformed slot 0
becomes the anchor only if the generated `map_data/provinces.png` says that
pixel belongs to that barony's **own** province; otherwise the centroid is
used. The offset point is gated the same way against the anchor. Without the
gate, a town CK2's author placed on the harbour would put the settlement model
in the sea, and a 13 px offset in a 400 px barony would sometimes cross the
border.

## 4. Which slot, measured — and why not slot 1 or slot 3

All seven slots, put through the same transform and the same gate against the
county-capital barony (`verified` 2026-09-10,
`scripts/check_ck2_locator_slots.py` →
`docs/evidence/map_fidelity/locator_slots.csv`, 2116 candidates each):

| slot | inside own barony | elsewhere | accept rate | median move vs centroid | distance from slot 0 | used |
|---|---|---|---|---|---|---|
| **0** | **2108** | 8 | **99.6 %** | 9.9 px | — | **anchor** |
| 1 | 1723 | 393 | 81.4 % | 19.5 px | 22.5 px (p95 39.4) | no |
| 2 | 1802 | 314 | 85.2 % | 14.5 px | 10.5 px | no |
| 3 | 1572 | 544 | 74.3 % | 9.4 px | 0.0 px | no |
| 4 | 1108 | 1008 | 52.4 % | 23.3 px | 25.5 px | no (it is a barony *seed*) |
| 5 | 1363 | 753 | 64.4 % | 24.3 px | 28.2 px | no |
| 6 | 1095 | 1021 | 51.7 % | 21.4 px | 40.1 px | no |

Slot 0's 99.6 % is the strongest signal in the table. It is partly circular —
the capital barony is grown from the slot-0 seed
(`docs/step_map_baronies.md` §3) — and that is the point: the anchor and the
territory agree by construction. Only 8 of 2116 disagreed.

**Slot 1 → unit stacks: rejected.** Slot 1 is the most reliably in-province
slot in CK2 vanilla (98.6 %, `docs/map_fidelity.md` §1.6), which is why the
brief proposed it. But its median distance from slot 0 is **22.5 canvas px** (p95 39.4),
**three times** vanilla's own 7.1 px stack offset (§2). Using it would place
unit stacks much farther from the settlement than CK3 ever does, and it drops
19 % of capitals to the centroid on top. Vanilla's measured offset does the
same job with the right magnitude. Slot 1 stays documented as the alternative
if a playtest ever wants a wider spread.

**Slot 3 → `siege`: rejected.** Three reasons, in order of weight:

1. `siege` is not an independent point at all — it is the army besieging the
   settlement, and vanilla puts it 10.0 px from it (§2). The whole premise of
   looking for a separate CK2 slot for it was wrong.
2. Slot 3 is **byte-identical to slot 0 in 58.1 %** of Faerûn's blocks, median
   offset 0.0 px (`docs/evidence/map_fidelity/ck2_slots.csv`). It is not an
   independent point in CK2 either.
3. Where it does differ it is worse: 74.3 % in-province against slot 0's
   99.6 %.

The only thing that singles slot 3 out is `height = 20.000` in every block of
both maps, which is a rendering height, not a semantic label.

## 5. Measured effect on the shipped mod

Build 9 vs build 8 (`scripts/locator_move_report.py` →
`docs/evidence/map_fidelity/locator_moves.csv`):

| file | instances | moved vs build 8 | median move | p90 | max |
|---|---|---|---|---|---|
| `building_locators.txt` | 3705 | 2108 (56.9 %) | 9.87 px | 26.47 | 99.68 |
| `special_building_locators.txt` | 3705 | 3699 (99.8 %) | 3.04 px | 21.13 | 98.63 |
| `siege_locators.txt` | 3705 | 3699 (99.8 %) | 4.26 px | 22.00 | 102.44 |
| `activities.txt` | 3705 | 3696 (99.8 %) | 4.34 px | 21.75 | 97.36 |
| `player_stack_locators.txt` | 4067 | 3954 (97.2 %) | 6.78 px | 21.18 | 93.99 |
| `other_stack_locators.txt` | 4067 | 3930 (96.6 %) | 7.76 px | 21.79 | 95.46 |
| `combat_locators.txt` | 4067 | 3914 (96.2 %) | 7.94 px | 21.53 | 92.23 |

**27,021 instances, 25,000 moved**, no id lost, every file still complete.
`building_locators.txt` moves only where a CK2 anchor was accepted (2108 of
2116 county capitals); the other six move almost everywhere because they also
take their per-type offset. The large `max` values (~100 px) are county
capitals whose CK2 town is far from the barony's geometric middle — exactly
the characterlessness this lane set out to fix.

No id was lost from any file — the script exits 1 if one is, because an id
missing from a locator file does **not** fall back to a centroid: it silently
inherits **vanilla's European coordinate**, since the engine fills only gaps
(`CLAUDE.md`; `gameobjectlocators.cpp:126`). `render_locator_file` therefore
takes the placements as a *patch* over the complete centroid map.

Per-type distance to the same province's `buildings` instance, ours against
vanilla (`scripts/check_locator_frame.py --mod`):

| locator | ours median | ours p95 | vanilla median | vanilla p95 |
|---|---|---|---|---|
| `special_building` | 1.75 | 1.75 | 9.05 | 18.70 |
| `siege` | 3.22 | 3.22 | 9.98 | 11.50 |
| `activities` | 4.31 | 4.31 | 9.40 | 38.97 |
| `unit_stack_player_owned` | **6.78** | 6.78 | **7.10** | 12.09 |
| `unit_stack_other_owner` | **7.76** | 7.76 | **7.69** | 12.87 |
| `combat` | 7.94 | 7.94 | 13.63 | 21.66 |

The two unit stacks land on vanilla's number. The three symmetric types come
out short, for the reason in §2.2 — the median vector is shorter than the
median distance when the directions cancel. Our p95 equals our median because
a fixed vector gives every province the same separation; vanilla's spread is a
distribution. `[map] locator_offset_mode = "median_radius"` is the one-line
switch that makes each row match its vanilla median instead
(`verified` in `tests/test_map_locators.py`). **It is the shipped default**
since 2026-09-10 (`docs/DECISIONS.md`): the distance is what a player sees,
and the median vector would put the siege marker on the settlement model.
The table above is the `median_vector` measurement kept for the record.

`uv run scripts/check_locator_frame.py --mod <out dir>` still validates, exit
0. Its `--mod` check now asserts the right invariant: an instance may sit away
from its centroid (that is the point of this lane), but it must be **inside
its own province**. It reports 3–51 instances per file that are not, and every
one of them is a **concave** province whose *centroid* falls outside its own
shape — 176 of the map's 4276 colours — which is a pre-existing property of
the fallback placement, not something this lane moved. The script counts those
as the baseline and fails only on an instance the converter itself put
outside.

ck3-tiger over the resulting mod: **fatal 0, error 58** — 41
`localization-key-collision`, 14 `wrong-gender`, 2 `unknown-field`, 1
`history`, the same accepted set as build 8
(`docs/evidence/tiger_map_assets_2026-09-10_summary.txt`). Locator coordinates
are invisible to it, which is exactly why the three scripts above exist.

## 5b. Seen in game (coordinator, 2026-09-10 12:34)

Build 9 (`locator_offset_mode = "median_radius"`) was run headless with the
camera probe over Waterdeep (`scripts/camera_probe.py --place waterdeep
--zoom 4` plus `REALM_COLOR_MAP_START_ZOOM_STEP = 0`) and screenshotted
110 s after `Setting idler 'In Game'`
(`claudespace/scripts/ck3_shot.sh`, evidence
`claudespace/docs/evidence/b9_waterdeep_locators.png`). `verified`:

* Waterdeep's holding model and its coat of arms stand at the CK2 author's
  town — the tooltip reads `b_castle_ward`, `X: 2345, Y: 5724`, which is the
  slot-0 anchor, 19 px from the province centroid `(2351.8, 5706.6)` the
  build-8 map used.
* Every visible settlement sits on its own land with its coat of arms on it;
  no model in the sea, none stacked on another. Title icons are on the
  correct coast.
* The game stayed alive for the 240 s soak; the scripted tests ran
  (`fae_map_every_ruler_holds_its_capital` logged, as in every build), so the
  session did unpause.

Distances checked against vanilla on the shipped files
(`scripts/check_locator_frame.py --mod`, median px to the same province's
`buildings`): special_building 9.05 / 9.05, player stack 7.10 / 7.10, other
stack 7.69 / 7.69, siege 9.98 / 9.98, combat 13.63 / 13.63, activities
9.40 / 9.40 — ours / vanilla, every row equal by construction. Our p95 equals
our median (a fixed bearing per type) where vanilla's is a spread; §7 open
question 1.

Also found by this run: the mod's own `tests/` had **no canary** — the
`fae_canary_must_fail` test the soak looks for had only ever been added by
hand to probe copies, so `ck3_soak.sh` reported `canary=silent` on a run
whose tests did execute. The `tests` step now emits it (`steps/tests.py`).

## 6. Config, and proving the keys are read

```toml
[map]
ck2_locator_positions = true                        # false = build 8's pure centroids
locator_offsets_csv   = "mappings/locator_offsets.csv"
locator_offset_scale  = 1.0                         # vanilla px -> our px
locator_offset_mode   = "median_radius"             # or "median_vector", §2.2
```

The keys are read in **two** places and both are needed:

* `ck2ck3.map.config.load` — the standalone `configs/faerun_map.toml` entry
  point;
* `ck2ck3.steps.map._map_config` — the **real CLI**'s config builder.

A key the CLI builder never reads is a **silent no-op** whatever the TOML
says. That is not hypothetical: `[map] colormap = false` was ignored for two
builds for exactly this reason (see the `BUG FIXED (lane colormap-fix)`
comment in `src/ck2ck3/steps/map.py`). Proof is
`tests/test_map_locators.py::test_cli_config_builder_reads_the_keys`, which
drives `_map_config` directly and asserts both the explicit values and the
defaults, plus `test_shipped_faerun_config_turns_the_import_on`.

In `configs/faerun.toml` the keys sit under the **real** `[map]` header line
(line 66), not under a comment that merely mentions the section — a past bug.

`mappings/locator_offsets.csv` opens with a `#` provenance block;
`read_locator_offsets` skips comment lines, as every `mappings/*.csv` reader
must (`CLAUDE.md`). An absent table is not an error — it means no offsets, and
the run warns.

## 7. Open questions

1. **The median vector under-separates the symmetric types** (§2.2, measured
   in §5: `siege` 3.2 px against vanilla's 10.0). `[map] locator_offset_mode
   = "median_radius"` fixes the magnitude and is the shipped default
   (coordinator decision 2026-09-10). A per-province *direction* as well as
   radius — vanilla's ring, not a fixed bearing — would go further and is not
   implemented.
2. **`locator_offset_scale = 1.0` contradicts the lane brief's 0.5.** The
   repo's `verified` km/px says 1.0 (§2.1). If the brief's 0.74 km/px figure
   has a source this doc has not seen, flip the key — that is all it takes.
3. **The 8 slot-0 gate rejections** fall back to the centroid silently.
   Snapping to the nearest in-barony pixel (what the barony seeds do,
   `snap_radius_px = 48`) is the alternative and is untested; it moves a point
   a human authored.
4. **Rotation is not ported.** CK2's per-slot radian maps exactly onto CK3's
   yaw-only quaternion (`docs/map_fidelity.md` §1.6), but Faerûn leaves it at
   0.000 in 80–100 % of slots, so the converter keeps its own deterministic
   golden-ratio yaw.
5. **Non-capital baronies** (1574) have no CK2 anchor and never will. They now
   at least get the per-type spread around their centroid. A human override
   file for locator anchors does not exist and is only worth building if a
   playtest says the centroid reads wrong.
6. **In-game check pending.** ck3-tiger cannot see a wrong coordinate; the
   camera probe (`scripts/camera_probe.py`) is the instrument.
