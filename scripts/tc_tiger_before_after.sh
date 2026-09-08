#!/usr/bin/env bash
# Lane `tc-template` evidence: ck3-tiger over one full conversion with the
# tc_template step and one without, into throwaway --out folders, so the
# difference is the step and nothing else.
#
# Usage: scripts/tc_tiger_before_after.sh <scratch dir>
# Writes <scratch>/tiger_before.txt and <scratch>/tiger_after.txt.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SC="${1:?scratch dir}"
BEFORE_STEPS="clean,descriptor,map,dynasties,cultures,religions,titles,history_titles,bookmarks,traits,characters,loc,tests"
for phase in before after; do
  OUT="$SC/mod_$phase"
  mkdir -p "$OUT"; printf 'name="scratch"\n' > "$OUT/descriptor.mod"
  if [ "$phase" = before ]; then STEPS="$BEFORE_STEPS"; else STEPS=all; fi
  ( cd "$HERE" && uv run ck2ck3 --config configs/faerun.toml --out "$OUT" \
      --steps "$STEPS" --no-evidence )
  "$HERE/scripts/validate_output_mod.sh" "$OUT" "$SC/tiger_$phase.txt"
done
