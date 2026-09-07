# CK2 source sea level (measured)

Source: `Faerun/Faerun/map`  ·  script: `scripts/measure_ck2_sea_level.py`

Method: classify every province pixel as water or land from
`definition.csv` + the `sea_zones` ranges in `default.map`, then compare the
`topology.bmp` histograms of the two sets. The coastline sits where they meet.

| measure | value |
|---|---|
| water pixels | 3,740,901 |
| land pixels | 6,924,353 |
| water median | 71 |
| water 99th percentile | 92 |
| land 1st percentile | 97 |
| land median | 110 |
| **suggested `ck2_sea_level`** | **94** |

## Histogram around the boundary

| topology value | water px | land px |
|---|---|---|
| 86 | 93,766 | 0 |
| 87 | 79,410 | 1 |
| 88 | 98,582 | 5 |
| 89 | 107,413 | 2 |
| 90 | 158,614 | 6 |
| 91 | 112,590 | 23 |
| 92 | 147,450 | 339 |
| 93 | 0 | 0 |
| 94 | 0 | 0 |
| 95 | 0 | 0 |
| 96 | 0 | 0 |
| 97 | 20 | 206,723 |
| 98 | 20 | 125,957 |
| 99 | 6 | 132,061 |
| 100 | 1 | 164,383 |
| 101 | 6 | 243,407 |
| 102 | 3 | 226,901 |
| 103 | 2 | 349,967 |
