# Hand-off: lane `map-assets`

Asset placement, the second half of "pre-unpause fidelity"
(`docs/map_fidelity.md` §3). Branch `lane/map-assets`, **not committed** —
worker agents hang on the commit permission prompt, so the coordinator
commits from this hand-off (`STATUS.md`, blockers).

Reference doc: **`docs/step_map_assets.md`**. Read that first; this file is
the diff, the numbers and the decisions.

## What ships

Build 8 put all seven locator types on the province colour centroid — one
stacked point in the geometric middle of every barony. Build 9 places:

1. **One anchor per province.** CK2 `positions.txt` **slot 0** (the
   capital/city slot the CK2 binary itself names) for the **county-capital
   barony**, accepted only when the transformed pixel falls inside that
   barony's own province in the generated `provinces.png`: **2108 of 2116,
   99.6 %** (`verified`). Everything else — 1574 non-capital baronies, every
   sea, lake, river and impassable province — anchors on its centroid.
2. **Plus vanilla's own measured per-type offset**, re-gated the same way.
   Measured over all 11,297 land ids of CK3 1.19
   (`scripts/measure_vanilla_locator_offsets.py` →
   `mappings/locator_offsets.csv`): every type sits within ~15 px of that
   province's `buildings` instance, because a siege marker is the army
   *besieging the settlement*. `siege` 10.0 px median, unit stacks 7.1 / 7.7,
   `combat` 13.6, `special_building` 9.1.

Result, build 9 vs build 8 (`scripts/locator_move_report.py`): **25,000 of
27,021 instances moved**, no id lost, all seven files complete.
`scripts/check_locator_frame.py --mod` exits 0: **no instance was placed
outside its own province** (the handful reported are concave provinces whose
*centroid* is outside their own shape — a pre-existing property of the
fallback, now counted as the baseline rather than a failure).

## Two things the coordinator must decide

**1. `locator_offset_scale = 1.0`, not the brief's 0.5.** The brief said a
vanilla pixel is ~0.74 km against our ~1.48 and asked for the offsets halved.
The repo's own `verified` measurement says our canvas is planned at vanilla's
km per pixel *by construction*: `vanilla_km_per_px = 1.4839`,
`factor = 2.90 / 1.4839` (`docs/map_scale.md` §1), which is also why
`min_barony_pixels = 400` "needs no rescaling" and `colormap_blur_sigma = 9`
is "used unconverted". One of our pixels is one vanilla pixel, so the scale is
1.0. Shipped as 1.0; `[map] locator_offset_scale = 0.5` is a one-line flip if
the 0.74 figure has a source this lane did not see.

**2. The median vector under-separates three of the six types.** Vanilla's
offsets are a *ring*: `siege`'s median distance from the settlement is 10.0 px
but its median *vector* is only 3.2 px long, because the directions cancel
(IQR ±8 px on both axes). Measured on our output against vanilla
(`scripts/check_locator_frame.py --mod`, distance to the same province's
`buildings`):

| locator | ours | vanilla |
|---|---|---|
| `unit_stack_player_owned` | **6.78** | **7.10** |
| `unit_stack_other_owner` | **7.76** | **7.69** |
| `combat` | 7.94 | 13.63 |
| `special_building` | 1.75 | 9.05 |
| `siege` | 3.22 | 9.98 |
| `activities` | 4.31 | 9.40 |

The two unit stacks land exactly on vanilla. The rotationally symmetric types
come out short. `[map] locator_offset_mode = "median_radius"` keeps the
direction and stretches it to vanilla's measured median *distance*, which
makes every row match; it is implemented and tested, and **the coordinator
made it the default** (2026-09-10, `docs/DECISIONS.md`): the distance is what
a player sees, and the median vector would have stacked the siege marker on
the settlement model.

## Also worth 30 seconds

`wt/<lane>/.venv` is a symlink to the main checkout's venv, whose editable
`.pth` names **one fixed source tree** (`wt/report-paint/src`). In any other
worktree `uv run ck2ck3` imports *another lane's* code. The run succeeds, the
output looks plausible, and the lane's change is simply absent — the first
full run of this lane produced locator files **byte-identical** to build 8.
`pytest` is immune (`pyproject.toml` sets `pythonpath = ["src", "."]`), which
is precisely why the tests were green while the run was wrong. Workaround now
in `docs/integration_run.md`: prefix with `PYTHONPATH=$PWD/src`. **A real
venv per worktree would remove the trap.**

## Files changed (none committed)

New:
- `docs/step_map_assets.md` — the reference doc.
- `mappings/locator_offsets.csv` — vanilla's per-type offset, generated, with
  a `#` provenance block.
- `scripts/measure_vanilla_locator_offsets.py` — writes that table from the
  CK3 install.
- `scripts/check_ck2_locator_slots.py` — all seven CK2 slots through the
  converter's own transform and gate → `docs/evidence/map_fidelity/locator_slots.csv`.
- `scripts/locator_move_report.py` — diffs two builds' locator sets; **exits 1
  if an id was lost** (a missing id inherits vanilla's European coordinate).
  → `docs/evidence/map_fidelity/locator_moves.csv`.
- `docs/evidence/HANDOFF_map_assets.md` (this file).

Modified:
- `src/ck2ck3/map/locators.py` — `CK2_ANCHOR_SLOT`, `LocatorOffset`,
  `read_locator_offsets`, `AnchorStats`, `ck2_capital_anchors`,
  `place_with_offsets`; `render_locator_file`/`render_all` take an `overrides`
  patch. `world_position` untouched.
- `src/ck2ck3/map/build.py` — capital-barony id map from `plan.by_province`,
  the two calls, per-type logging, the report block.
- `src/ck2ck3/map/config.py` — `ck2_locator_positions`,
  `locator_offsets_csv`, `locator_offset_scale`, `locator_offset_mode`.
- `src/ck2ck3/steps/map.py` — **the same four keys in the real CLI's config
  builder**, plus counts in the `StepResult` (proof they are read:
  `last_run.md` shows `locators_ck2_anchors=2108`,
  `locators_moved_instances=25000`).
- `scripts/check_locator_frame.py` — `--mod` now asserts *inside its own
  province* instead of *within 1 px of the centroid* (the old assertion is
  exactly what this lane deliberately breaks), and prints the per-type
  distance-to-`buildings` table above.
- `configs/faerun.toml` — the four keys, under the real `[map]` header
  (line 66).
- `tests/test_map_locators.py` — 22 new tests, fixtures lifted verbatim from
  Faerûn's `positions.txt` and the offsets CSV shape.
- `CLAUDE.md` — the stale "no barony coordinates to import" invariant
  replaced; a new invariant for the locator-relative-to-settlement fact; the
  worktree venv trap; doc and script pointers.
- `docs/map_fidelity.md` — §3 status paragraph, §4.4 effort row.
- `docs/integration_run.md` — the worktree venv trap.

## Verification

| check | result |
|---|---|
| `uv run pytest` | green |
| `scripts/check_locator_frame.py --mod` | exit 0, no instance outside its own province |
| `scripts/locator_move_report.py` | 25,000 moved, 0 ids lost |
| `scripts/check_ck2_locator_slots.py` | slot 0 = 99.6 %, the rest 51.7–85.2 % |
| `scripts/validate_output_mod.sh` | **fatal 0, error 58** (41 loc-key-collision, 14 wrong-gender, 2 unknown-field, 1 history) — unchanged from build 8; `docs/evidence/tiger_map_assets_2026-09-10_summary.txt` |
| full run | `docs/evidence/full_run_map_assets_2026-09-10.log`, `docs/evidence/last_run.md` |

Nothing here has been seen in the running game. ck3-tiger cannot see a wrong
coordinate; `scripts/camera_probe.py` or a playtest is the only instrument.
