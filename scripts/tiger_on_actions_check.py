"""ck3-tiger over the whole generated mod, summarised for lane `on-actions`.

Same shape as `scripts/tiger_titles_check.py` / the `events` lane's own
`docs/evidence/tiger_events_2026-09-10_summary.txt`: run ck3-tiger, then
print the by-kind and by-message tables plus every finding whose path is
under `events/` or `common/on_action/` - the two folders this lane touches.

Usage: `uv run scripts/tiger_on_actions_check.py <full_report.txt> [out_summary.txt]`
(the full report itself comes from `scripts/validate_output_mod.sh`).
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

KIND_RE = re.compile(r"^(fatal|error|warning|untidy|tips)\(([a-z0-9-]+)\): (.*)$")
PATH_RE = re.compile(r"^\s*-->.*?([A-Za-z0-9_./-]+\.(?:txt|yml))")


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    report = Path(sys.argv[1])
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else None

    by_kind: Counter[str] = Counter()
    by_message: Counter[str] = Counter()
    events_findings: Counter[str] = Counter()
    on_action_findings: Counter[str] = Counter()
    fatal_lines: list[str] = []

    current_kind = None
    current_msg = None
    lines = report.read_text(encoding="utf-8", errors="replace").splitlines()
    for i, line in enumerate(lines):
        m = KIND_RE.match(line.strip())
        if m:
            kind, sub, msg = m.groups()
            current_kind = f"{kind}({sub})"
            current_msg = f"{current_kind}: {msg.strip()}"
            by_kind[current_kind] += 1
            by_message[current_msg] += 1
            if kind == "fatal":
                fatal_lines.append(line.strip())
            continue
        pm = PATH_RE.search(line)
        if pm and current_msg:
            path = pm.group(1)
            if path.startswith("events/") or "/events/" in path:
                events_findings[current_msg] += 1
            elif path.startswith("common/on_action/") or "/common/on_action/" in path:
                on_action_findings[current_msg] += 1

    out_lines = ["--- by kind"]
    for kind, n in by_kind.most_common():
        out_lines.append(f"{n:7} {kind}")
    out_lines.append("--- by message (top 40)")
    for msg, n in by_message.most_common(40):
        out_lines.append(f"{n:7} {msg}")
    out_lines.append(f"--- fatal findings ({len(fatal_lines)})")
    out_lines.extend(fatal_lines)
    out_lines.append(f"--- findings under events/ ({sum(events_findings.values())})")
    for msg, n in events_findings.most_common():
        out_lines.append(f"{n:7} {msg}")
    out_lines.append(f"--- findings under common/on_action/ ({sum(on_action_findings.values())})")
    for msg, n in on_action_findings.most_common():
        out_lines.append(f"{n:7} {msg}")

    text = "\n".join(out_lines) + "\n"
    print(text)
    if out:
        out.write_text(text, encoding="utf-8")
        print(f"-> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
