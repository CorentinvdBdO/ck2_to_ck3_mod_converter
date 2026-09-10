#!/usr/bin/env bash
# One full `map` run per ablation of the §2d fix, into its own output dir, so
# every default this lane changes is measured against the map without it.
# Usage: scripts/relief_sharp_ablate.sh   (from the worktree root)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUTBASE="${OUTBASE:-$ROOT/../_out/relief-sharp-ablate}"
cd "$ROOT"
trap 'rm -f "$ROOT"/configs/_ablate_*.toml' EXIT
run() {  # run <name> <sed expression on configs/faerun.toml>
  local name="$1"; shift
  # the config has to live beside configs/faerun.toml: every [paths] entry in
  # it is relative to the config file's own directory
  local cfg="configs/_ablate_$name.toml"
  mkdir -p "$OUTBASE"
  sed "$@" configs/faerun.toml > "$cfg"
  echo "== $name"
  uv run ck2ck3 --config "$cfg" --steps map --out "$OUTBASE/$name" --no-evidence \
    > "$ROOT/docs/evidence/relief_sharp/ablate_$name.log" 2>&1
  grep -o 'heightmap detail .*' "$ROOT/docs/evidence/relief_sharp/ablate_$name.log" | tail -1
}
run no_fix          -e 's/^heightmap_detail_fill_min_cycles_per_km = .*/heightmap_detail_fill_min_cycles_per_km = 0.01/' \
                    -e 's/^heightmap_detail_erosion_slope_ceiling_steps = .*/heightmap_detail_erosion_slope_ceiling_steps = 0.0/' \
                    -e 's/^heightmap_detail_headroom_fraction = .*/heightmap_detail_headroom_fraction = 1.0/'
run fillmin_only    -e 's/^heightmap_detail_erosion_slope_ceiling_steps = .*/heightmap_detail_erosion_slope_ceiling_steps = 0.0/' \
                    -e 's/^heightmap_detail_headroom_fraction = .*/heightmap_detail_headroom_fraction = 1.0/'
run slopecap_only   -e 's/^heightmap_detail_fill_min_cycles_per_km = .*/heightmap_detail_fill_min_cycles_per_km = 0.01/' \
                    -e 's/^heightmap_detail_headroom_fraction = .*/heightmap_detail_headroom_fraction = 1.0/'
run headroom_1.0    -e 's/^heightmap_detail_headroom_fraction = .*/heightmap_detail_headroom_fraction = 1.0/'
run slopecap_1.0    -e 's/^heightmap_detail_erosion_slope_ceiling_steps = .*/heightmap_detail_erosion_slope_ceiling_steps = 1.0/'
echo done
