"""Writing the review sheets a lane leaves behind in *this* repository.

``ctx.write_*`` targets the generated mod, which is regenerated and never
reviewed as a diff. A dropped-key sheet is the opposite: it is the thing a
human reads to decide what to hand-author next, so it belongs in
``docs/evidence/`` under version control, like ``docs/evidence/last_run.md``.
"""

from __future__ import annotations

import csv
import io
from typing import Iterable, Sequence

from ..config import REPO_ROOT
from ..context import Context


def write_csv(
    ctx: Context, rel: str, header: Sequence[str], rows: Iterable[Sequence[object]]
) -> None:
    """Write ``docs/evidence/<...>.csv`` in this repository (honours dry-run)."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    path = REPO_ROOT / rel
    if ctx.dry_run:
        ctx.info(f"would write {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(buffer.getvalue(), encoding="utf-8")
    ctx.info(f"wrote {path}")
