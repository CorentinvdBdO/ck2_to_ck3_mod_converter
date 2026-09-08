#!/usr/bin/env bash
# Must be green before /ship. Usage: ci/checks.sh
set -uo pipefail
cd "$(dirname "$0")/.."
fail=0; ok(){ echo "ok    $*"; }; ko(){ echo "FAIL  $*"; fail=1; }
for f in scripts/*.sh ci/*.sh; do [ -f "$f" ] && { bash -n "$f" && ok "bash -n $f" || ko "syntax $f"; }; done
uv run python -m compileall -q src scripts >/dev/null 2>&1 && ok "python compileall" || ko "python syntax error"
if ls tests/test_*.py >/dev/null 2>&1; then uv run pytest -q 2>&1 | tail -3; [ "${PIPESTATUS[0]}" -eq 0 ] && ok "pytest" || ko "pytest"; else echo "warn  no tests yet"; fi
uv run ck2ck3 --list-steps >/dev/null 2>&1 && ok "ck2ck3 --list-steps" || ko "ck2ck3 CLI broken"
uv run scripts/build_loc_key_map.py --check >/dev/null 2>&1 && ok "overrides/loc_keys.csv fresh" || ko "overrides/loc_keys.csv stale (uv run scripts/build_loc_key_map.py)"
for d in docs/PROJECT.md docs/DECISIONS.md STATUS.md CLAUDE.md docs/cli.md docs/formats_pdx_quirks.md docs/integration_run.md; do [ -f "$d" ] && ok "$d" || ko "$d missing"; done
grep -q '<YYYY' STATUS.md 2>/dev/null && ko "STATUS.md placeholders" || ok "STATUS.md filled"
[ -d Faerun/Faerun/map ] && ok "Faerun clone present" || echo "warn  Faerun/ not cloned (git clone --depth 1 https://github.com/ProjectFaerun/Faerun Faerun)"
[ $fail -eq 0 ] && echo "checks green" || { echo "checks RED"; exit 1; }
