# Last converter run

Overwritten by `ck2ck3` on every run; do not edit by hand.

- when: 2026-09-07 20:32:52
- config: `configs/faerun.toml`
- mode: write
- source: `/home/cvdbdo/git/paradox/ck3/wt/map-physical/Faerun/Faerun`
- output: `/home/cvdbdo/git/paradox/ck3/claudespace/mods/faerun_ck2_to_ck3_converted`
- steps: clean, descriptor, map
- files written: 25
- warnings: 9
- total time: 37.4 s

## Steps

| step | seconds | files | counts | summary |
|---|---|---|---|---|
| clean | 0.00 | 0 | removed=4, removed_dirs=4, kept=3 | cleaned /home/cvdbdo/git/paradox/ck3/claudespace/mods/faerun_ck2_to_ck3_converted: removed 4 entries, kept .git, README.md, descriptor.mod |
| descriptor | 0.00 | 1 | tags=3, replace_paths=16 | descriptor.mod: 'Faerun (CK2 conversion, raw)' 0.1.0 for CK3 1.19.*, 16 replace_path |
| map | 37.39 | 24 | provinces=2696, land=2335, sea=180, lakes=95, river_provinces=86, lost=3, regrown=1, adjacencies=319, baronies_placeholder=2335 | map 8192x6656 at scale 1.9543 (2.9 -> 1.4839 km/px): 2696 provinces, 3 lost |

## Warnings

- CK2 province 2314 dropped (1 source pixels)
- CK2 province 2316 dropped (1 source pixels)
- CK2 province 2698 dropped (0 source pixels)
- rivers: 19 of 350 sources did not survive (they fall on a pixel the province map says is water)
- rivers: 22 of 308 merges did not survive (they fall on a pixel the province map says is water)
- adjacency 1691->1686 (major_river): CK2 gives no Through province and CK3 requires one; row dropped
- adjacency 1690->1686 (major_river): CK2 gives no Through province and CK3 requires one; row dropped
- adjacency 1687->1686 (major_river): CK2 gives no Through province and CK3 requires one; row dropped
- adjacency 1690->1687 (major_river): CK2 gives no Through province and CK3 requires one; row dropped
