#!/usr/bin/env bash
# Validate the generated mod with ck3-tiger.
#
# Usage:  scripts/validate_output_mod.sh [mod_dir] [out_report]
#   mod_dir     default ../claudespace/mods/faerun_ck2_to_ck3_converted
#   out_report  default docs/evidence/tiger_<date>.txt
#
# Why the temp descriptor: ck3-tiger takes the path to a .mod FILE and reads a
# `path=` line out of it to find the mod, but a mod's own descriptor.mod must
# NOT contain `path=` (the launcher adds it, and scripts/push_mod.sh in the CK3
# workspace refuses a descriptor that has one). So this script writes a throwaway
# copy with `path=` appended, in a temp dir, and points tiger at that.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MOD_DIR="${1:-$HERE/../claudespace/mods/faerun_ck2_to_ck3_converted}"
MOD_DIR="$(cd "$MOD_DIR" && pwd)"
GAME="${CK3_GAME:-$HOME/.local/share/Steam/steamapps/common/Crusader Kings III/game}"
TIGER="${CK3_TIGER:-$HOME/.local/bin/ck3-tiger}"
REPORT="${2:-$HERE/docs/evidence/tiger_$(date +%F).txt}"

command -v "$TIGER" >/dev/null 2>&1 || [ -x "$TIGER" ] || {
  echo "no ck3-tiger at $TIGER (set CK3_TIGER)" >&2; exit 1; }
[ -d "$GAME" ] || { echo "no CK3 game dir at $GAME (set CK3_GAME)" >&2; exit 1; }
[ -f "$MOD_DIR/descriptor.mod" ] || { echo "no descriptor.mod in $MOD_DIR" >&2; exit 1; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
DESC="$TMP/faerun_ck2_to_ck3_converted.mod"
{ cat "$MOD_DIR/descriptor.mod"; echo "path=\"$MOD_DIR\""; } > "$DESC"

mkdir -p "$(dirname "$REPORT")"
echo "ck3-tiger $(date -Is)"          >  "$REPORT"
echo "mod:  $MOD_DIR"                 >> "$REPORT"
echo "game: $GAME"                    >> "$REPORT"
echo "---"                            >> "$REPORT"
"$TIGER" "$DESC" --game "$GAME" >> "$REPORT" 2>&1
RC=$?

# tiger prints one block per finding, headed by a severity keyword
errors=$(grep -cE '^(error|fatal)' "$REPORT" || true)
warns=$(grep -cE '^warning' "$REPORT" || true)
tips=$(grep -cE '^(tips|untidy|advice)' "$REPORT" || true)
{
  echo "---"
  echo "summary: $errors error/fatal, $warns warning, $tips tips/untidy (tiger exit $RC)"
} >> "$REPORT"
tail -2 "$REPORT"
echo "report   $REPORT"
# tiger exits non-zero when it finds anything; the counts above are the signal
exit 0
