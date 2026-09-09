# Playtest the converted mod

The generated mod lives in `/home/cvdbdo/git/paradox/ck3/claudespace/mods/faerun_ck2_to_ck3_converted`
(git repo, branch `main`). Nothing is copied anywhere: the game reads that folder directly.
It is registered with the launcher by `claudespace/scripts/push_mod.sh` (a `.mod` file with `path=`
inside the live user dir, see below).

## What to expect (build 8, 2026-09-10)

- Map of Faerûn at vanilla scale, 3705 baronies / 2127 counties, 1357 DR bookmark "Before the Storm",
  17 bookmarks total (1357–1501). Start as any of the 82 bookmark characters or pick a ruler on the map.
- **Both unpause crashes are fixed.** Build 3 died every time (emptied vanilla scripted effects); build 4-6 died about one launch in four a few seconds after unpausing (your 18:33 crash: the blank `flavorization` folder left every ruler without a title name). Build 7 keeps vanilla flavorization and survived 10/10 headless launches. Start a new game; do not continue an older save.
- The map is painted: CK2 terrain classes drive CK3's materials, 711,875 trees are scattered from CK2's `trees.bmp`, the colour wash is a tint measured off vanilla, and the sea has a real floor so it reads as deep water rather than beach. Zoom in on Anauroch (desert) and the Sword Coast (forest, snowed in because the bookmark is 2 January and Faerun's own climate marks 43 % of provinces wintery).
- Rulers now have proper titles (King of X, Duke of Y) from vanilla's generic flavorization; CK2 mercenary companies and holy orders are plain feudal realms for now (their CK2 nature is a comment in `history/titles`).
- The converted CK2 decisions exist as inert stubs (3 live); the decisions menu shows only vanilla content.
- New since your playtest 2: characters are dressed again (portrait base files were shadowed by mistake);
  removed CK2 traits (`cruel`, `envious`…) no longer exist — they map to CK3 traits (`sadistic`,
  `compassionate`, `arrogant`…) or are dropped; baronies are seeded from CK2 city/port positions; the terrain
  is painted from CK2 terrain classes (`assumed` correct until you look: check the Sword Coast and Anauroch);
  the heightmap has vanilla-like relief detail instead of flat terraces (`assumed`: look at the Spine of the
  World and river valleys).
- Vanilla mechanics only. No Faerûn events, decisions, buildings, wonders, societies (not converted yet).
- Placeholders you will see: coats of arms are solid colours; every faith icon and most trait icons are
  missing (missing-file warnings, harmless); non-human cultures use a vanilla ethnicity look
  (`# TODO real ethnicity`); heritage pillars have no audio; no bookmark art; placeholder traditions.
- Known rough edges: 1 generated test fails (ruler-holds-capital, 3 rulers); ck3-tiger error classes
  accepted and listed in `docs/evidence/tiger_build3_2026-09-08.txt`.
- Things to report on this build: does the terrain paint render (or is the ground uniform/garbled)? Does
  relief look right at province borders and coasts? Any character still naked or bald? Any CK2-named trait
  left in a trait list?

## Way 1 — official launcher

1. Make sure the mod is registered (idempotent):
   ```sh
   cd /home/cvdbdo/git/paradox/ck3/claudespace
   scripts/push_mod.sh mods/faerun_ck2_to_ck3_converted
   ```
2. Start CK3 from Steam. In the Paradox launcher: **Playsets → Add playset → enable
   "Faerun (CK2 conversion, raw)"** only (no other mod, no Elder Kings / Godherja). Tick **Game settings →
   Open game in Debug Mode** if you want the console (`~`).
3. Play. Pick the 1357 bookmark. Each bookmark character has a portrait placeholder.

## Way 2 — direct launch, no launcher clicks

From `claudespace`, on your desktop session (the game needs a screen):
```sh
cd /home/cvdbdo/git/paradox/ck3/claudespace
scripts/ck3_launch.sh faerun_ck2_to_ck3_converted --debug --keep
```
`ck3_launch.sh` registers the mod, enables it in `dlc_load.json` (restoring your previous playset file
afterwards), starts the game through Proton with `-debug_mode`, waits for the main menu and, with `--keep`,
leaves it running for you. Add `--args "-test"` to auto-start the default bookmark (it also runs
`tests/fae_generated_tests.txt`). `--headless` runs on a private off-screen display instead (for automated
runs, not for playing).

## While playing

- Console (debug mode, key `~`): `observe`, `play <character id>` (ids are strings: `play fae_52101`),
  `event <id>`, `reload localization`, `explorer` (object browser). Character ids are `fae_<ck2 id>`;
  title ids are the CK2 ones (`k_cormyr`, `c_waterdeep`, `b_wyrms_crossing`).
- Errors of this run: `scripts/ck3_errors.sh fae` (or `/fk-errors faerun_ck2_to_ck3_converted` in a
  Claude session). The live log is
  `~/.local/share/Steam/steamapps/compatdata/1158310/pfx/drive_c/users/steamuser/Documents/Paradox Interactive/Crusader Kings III/logs/error.log`
  (the `~/.local/share/Paradox Interactive/...` tree is a stale copy, ignore it).
- Report a problem with: what you did, the character/title id, and the first `error.log` lines that
  mention it. Put it in `docs/integration_backlog.md` of this repo or tell the coordinator.

## Regenerate after a converter change

```sh
cd /home/cvdbdo/git/paradox/ck3/ck2_to_ck3_mod_converter
uv run ck2ck3 --config configs/faerun.toml          # ~65 s, 13 steps, writes the mod folder
scripts/validate_output_mod.sh "" docs/evidence/tiger_<tag>.txt   # ck3-tiger, must stay fatal 0
cd ../claudespace && scripts/ck3_test.sh faerun_ck2_to_ck3_converted --headless   # In Game + 173 tests
```
Then commit the mod repo on a lane and merge (`docs/integration_run.md`). Never hand-edit the mod folder:
fix the converter, regenerate.
