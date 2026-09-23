# Can CK3 render a given DNA headlessly? A cheap probe (no game launch)

Date: 2026-09-23, lane `research-races`. Feeds `docs/research_race_tooling.md` §2.5. Everything
below is a static check against the installed binary and this machine's toolset — no game process
was started, so this is not proof the mechanism works end-to-end, only that its pieces exist.

## What exists

```
$ strings ".../Crusader Kings III/binaries/ck3.exe" | grep -i "dump_bookmark_portraits\|portrait_editor"
# Auto generated file, do not edit manually. Created using console command dump_bookmark_portraits
dump_bookmark_portraits
gui/portrait_editor_window.gui
portrait_editor
portrait_editor_window
```

- `dump_bookmark_portraits` is a real console command (`verified`): the string it writes into the
  generated file names itself. Matches `docs/research_dna_races.md` §3.2's prior `assumed` claim
  (CK3 Console Commands wiki page) — now confirmed directly in the binary. Output path per that
  prior research: `Documents/Paradox Interactive/Crusader Kings III/common/bookmark_portraits`.
- A second, undocumented mechanism exists: `portrait_editor` / `portrait_editor_window.gui`
  (`verified`, string + a real `.gui` file shipped) — a debug portrait-editing window, presumably
  reachable via the debug menu or a console command of the same name. Not explored further (would
  need a live debug-mode session); flagged as a second avenue worth trying before building a
  from-scratch render harness.

## What is missing for batch/headless use

```
$ which xdotool ydotool wtype
# none found
```

- No keyboard/mouse input-injection tool is installed in this environment (`verified`). Both
  `dump_bookmark_portraits` and `portrait_editor` are **console commands**, which this harness's
  existing automation (`ck3_launch.sh`, `ck3_probe_shots.sh`) has never driven — those scripts only
  wait for a log marker and take a `weston-screenshooter` screenshot (proven to work,
  `docs/evidence/water_border/` and the paint/relief evidence galleries), never type into the game.
- `strings` search for a batch/file-based console-command runner (`console_history`,
  `run_console_action*`) found only the interactive command-history mechanism, not a
  launch-argument or file-driven way to feed commands non-interactively (`verified`, no
  `-exec`/`-run_console_commands`-shaped string exists in the binary's argument-like strings).

## Conclusion (feeds the doc's §2.5 / §7 roadmap)

- Rendering a **bookmark** character's DNA to PNG headlessly is *plausible and cheap to try next*:
  install `ydotool` or `wtype` (needs sudo, ~5 min), extend `ck3_launch.sh`'s pattern to send
  `` ` `` (open console) + `dump_bookmark_portraits` + Enter once `Setting idler 'Frontend'` is
  logged, then copy the dumped file out of the Proton prefix's `Documents/...` path. Estimated a
  few hours including debugging keyboard-focus-under-weston issues, not a research question anymore
  — an engineering task, and one line item, not "unbudgeted" as the prior doc had to leave it.
- Rendering **arbitrary, non-bookmark DNA** (the actual synthetic-training-data use case) needs one
  more step this probe did not test: writing a throwaway `common/bookmarks` + `common/dna_data`
  entry per DNA to render, so `dump_bookmark_portraits` has something to dump — one game
  relaunch per **batch** of DNAs (bookmarks are read once at startup, not hot-reloadable), so
  throughput is bounded by restart time (~40-55 s headless, `CLAUDE.md`), not per-image cost, if
  many bookmarks can be dumped in one run (unverified how many `common/bookmarks` entries the dump
  command handles at once — untested, next cheap check: write 50 throwaway bookmarks and see if
  the dumped folder has 50 files after one launch).
