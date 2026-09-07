#!/usr/bin/env python3
"""Barony statistics for a CK2 mod: defined baronies per county vs holdings built in history/provinces.

Usage: uv run scripts/faerun_barony_stats.py [mod_root=Faerun/Faerun] [date=1368.9.2]
Prints a histogram and writes docs/evidence/barony_stats.csv (county, defined, built_at_date, max_settlements).
"""
import re, sys, glob, os, statistics as st
from collections import defaultdict

root = sys.argv[1] if len(sys.argv) > 1 else "Faerun/Faerun"
date = tuple(int(x) for x in (sys.argv[2] if len(sys.argv) > 2 else "1368.9.2").split("."))

# 1. defined baronies per county from landed_titles (brace depth tracker)
defined = defaultdict(list)
for f in glob.glob(f"{root}/common/landed_titles/*.txt"):
    txt = open(f, encoding="cp1252", errors="replace").read()
    txt = re.sub(r"#.*", "", txt)
    stack = []
    for m in re.finditer(r"([A-Za-z0-9_]+)\s*=\s*\{|\{|\}", txt):
        tok = m.group(0)
        if tok == "}":
            if stack: stack.pop()
        elif tok == "{":
            stack.append(None)
        else:
            key = m.group(1); stack.append(key)
            if key.startswith("b_"):
                county = next((k for k in reversed(stack[:-1]) if k and k.startswith("c_")), None)
                if county: defined[county].append(key)

# 2. built holdings per province from history/provinces at `date`
HOLD = {"castle", "city", "temple", "tribal", "nomad", "family_palace", "fort", "hospital", "trade_post"}
built = {}; maxset = {}; title_of = {}
for f in glob.glob(f"{root}/history/provinces/*.txt"):
    txt = open(f, encoding="cp1252", errors="replace").read()
    txt = re.sub(r"#.*", "", txt)
    t = re.search(r"\btitle\s*=\s*(c_\w+)", txt)
    if not t: continue
    county = t.group(1); title_of[os.path.basename(f)] = county
    ms = re.search(r"max_settlements\s*=\s*(\d+)", txt)
    maxset[county] = int(ms.group(1)) if ms else None
    holdings = {}
    # top-level assignments (before any dated block) and dated blocks <= date
    depth = 0; cur_date = (0, 0, 0)
    for m in re.finditer(r"(\d+)\.(\d+)\.(\d+)\s*=\s*\{|\{|\}|(b_\w+)\s*=\s*(\w+)", txt):
        tok = m.group(0)
        if tok == "{": depth += 1
        elif tok == "}": depth -= 1; cur_date = (0, 0, 0) if depth == 0 else cur_date
        elif m.group(1):
            depth += 1; cur_date = tuple(int(m.group(i)) for i in (1, 2, 3))
        elif m.group(4) and m.group(5) in HOLD and cur_date <= date:
            holdings[m.group(4)] = m.group(5)
    built[county] = holdings

rows = []
for c in sorted(defined):
    rows.append((c, len(defined[c]), len(built.get(c, {})), maxset.get(c)))
os.makedirs("docs/evidence", exist_ok=True)
with open("docs/evidence/barony_stats.csv", "w") as out:
    out.write("county,defined,built,max_settlements\n")
    for r in rows: out.write(",".join("" if v is None else str(v) for v in r) + "\n")

d = [r[1] for r in rows]; b = [r[2] for r in rows if r[0] in built]
print(f"counties in landed_titles: {len(rows)}; with province history: {len(built)}")
print(f"defined per county: min {min(d)} median {st.median(d)} mean {st.mean(d):.2f} max {max(d)}  total {sum(d)}")
print(f"built @{'.'.join(map(str,date))}: min {min(b)} median {st.median(b)} mean {st.mean(b):.2f} max {max(b)}  total {sum(b)}")
hist = defaultdict(int)
for x in b: hist[x] += 1
print("built histogram:", dict(sorted(hist.items())))
ms = [r[3] for r in rows if r[3]]
print(f"max_settlements: median {st.median(ms)} mean {st.mean(ms):.2f} max {max(ms)}")
