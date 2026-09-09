#!/usr/bin/env bash
# Build terrain-paint format/scale probe mods from a converter run.
#
# Usage:  scripts/paint_variants.sh <converter out dir> [--variants-dir DIR]
#
# Thin wrapper around scripts/paint_variants.py (the encode/decode logic
# lives there so it can share ck2ck3.map.terrain_paint's writers/readers).
# Writes <out>/../paint_variants/<variant>/{descriptor.mod,gfx/map/terrain/*}
# and docs/evidence/paint_variants.csv (sizes per variant). Load one at a
# time after the main mod: claudespace/scripts/ck3_soak.sh <mod> --extra
# <out>/../paint_variants/<variant>.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec uv run --project "$HERE" python "$HERE/scripts/paint_variants.py" "$@"
