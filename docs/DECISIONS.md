# Decisions (append-only; date, decision, reason)

- 2026-09-07 — Converter stays in Python 3.12 (uv), no Rust rewrite. Reason: Rust toolchain absent on the dev machine, team fluency, PIL/numpy/scipy cover the image work; revisit only if parsing speed on 16k-file mods becomes a blocker.
- 2026-09-07 — Three repos: converter, generated mod (`faerun_ck3`, never hand-edited), submod (`forgotten_kings`), plus an asset library. Reason: upstream Faerun CK2 mod is still updated; a clean regenerate must stay possible.
- 2026-09-07 — Target CK3 1.19.x; vanilla map is 9216×4608 (not 8192×4096 as the old `convert.py` assumed). Map dimensions become a converter parameter.
- 2026-09-07 — Canon political map: Atlas of Ice and Fire "Nations of the Forgotten Realms" (1371 DR). Reference image kept locally in `refs/` (gitignored, copyrighted).
- 2026-09-07 — Anything without a CK3 equivalent is emitted as a comment next to the nearest CK3 construct. No invention in the converter.
- 2026-09-07 — Human-judgement inputs (barony seeds, race→asset mapping, id remaps) are override files read by the converter, so a re-run after an upstream update keeps human work.
