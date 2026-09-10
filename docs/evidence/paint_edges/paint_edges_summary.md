# Lane `paint-edges`: before / after (generated)

`uv run --with matplotlib python scripts/paint_edges_report.py --before /home/cvdbdo/git/paradox/ck3/wt/_out/paint-edges-before --after /home/cvdbdo/git/paradox/ck3/wt/_out/paint-edges`, 10 s. All rows `verified` (measured off the shipped TGA pairs).

## Blend statistics, land only

| map | channels/px | primary weight | entropy (bits) | materials |
|---|---|---|---|---|
| before (build 13) | 2.0 | 0.7116 | 0.7136 | 20 |
| after (soft edges) | 3.23 | 0.5379 | 1.5046 | 27 |
| vanilla (target) | 3.467 | 0.5247 | 1.4916 | 101 |

## Encoded size (part D: can we ship full resolution?)

| layer | scale | format | MB | under 95 MB |
|---|---|---|---|---|
| detail_index | 1.0 | tga | 225.77 | NO |
| detail_intensity | 1.0 | tga | 225.77 | NO |
| detail_index | 1.0 | tga_rle | 20.42 | yes |
| detail_intensity | 1.0 | tga_rle | 24.41 | yes |
| detail_index | 0.5 | tga | 56.44 | yes |
| detail_intensity | 0.5 | tga | 56.44 | yes |
| detail_index | 0.5 | tga_rle | 7.14 | yes |
| detail_intensity | 0.5 | tga_rle | 9.2 | yes |

## Figures

- `fig_wealdath_before_after.png` — wealdath
- `fig_anauroch_before_after.png` — anauroch
- `fig_sword_coast_before_after.png` — sword coast
