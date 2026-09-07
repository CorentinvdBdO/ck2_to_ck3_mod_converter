"""Where the physical-map step writes its output.

``docs/cli.md`` requires a step to write through ``ctx``, never through the
filesystem, so ``--dry-run`` is honest and the run log is complete.  The map
step also writes four PNGs, which no ``ctx.write_*`` method covers, so this
module defines the small surface the map pipeline actually needs and gives it
two implementations:

* :class:`DirectorySink` — writes straight to disk.  Used by the standalone
  entry point (``python -m ck2ck3.map.build``), which exists so the map can be
  built before the CLI is wired up.
* :class:`ContextSink` — delegates to a :class:`ck2ck3.context.Context`, so a
  CLI run is dry-run-safe and every file lands in the run log.

The binary path takes a *callable* rather than bytes: a 54 Mpx PNG is cheaper to
have PIL write to the final path than to serialise into memory first, and in a
dry run the callable is simply never invoked.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Protocol


class Sink(Protocol):
    """The write surface the map pipeline uses."""

    @property
    def dry_run(self) -> bool: ...

    def text(self, rel: str, content: str, *, bom: bool = False) -> Path:
        """Write a text file under the output mod. ``rel`` is POSIX-style."""
        ...

    def binary(self, rel: str, save: Callable[[Path], None]) -> Path:
        """Write a binary file by handing ``save`` the resolved path."""
        ...

    def info(self, message: str) -> None: ...

    def warn(self, message: str) -> None: ...


BOM = "﻿"


class DirectorySink:
    """Write to a plain directory."""

    def __init__(self, root: Path, *, dry_run: bool = False, verbose: bool = True):
        self.root = Path(root)
        self._dry_run = dry_run
        self.verbose = verbose
        self.written: list[Path] = []
        self.warnings: list[str] = []

    @property
    def dry_run(self) -> bool:
        return self._dry_run

    def _path(self, rel: str) -> Path:
        path = self.root / rel
        if not self._dry_run:
            path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def text(self, rel: str, content: str, *, bom: bool = False) -> Path:
        path = self._path(rel)
        if not self._dry_run:
            path.write_text(
                (BOM if bom else "") + content, encoding="utf-8", newline="\n"
            )
        self.written.append(path)
        return path

    def binary(self, rel: str, save: Callable[[Path], None]) -> Path:
        path = self._path(rel)
        if not self._dry_run:
            save(path)
        self.written.append(path)
        return path

    def info(self, message: str) -> None:
        if self.verbose:
            print(message, flush=True)

    def warn(self, message: str) -> None:
        self.warnings.append(message)
        if self.verbose:
            print(f"warning: {message}", flush=True)


class ContextSink:
    """Write through a CLI :class:`ck2ck3.context.Context`.

    ``ctx.write_text`` covers the text files.  Binary output goes through
    ``ctx.write_binary`` when the context has it, and otherwise falls back to
    writing the file and recording it by hand, so this lane does not hard-depend
    on a context method landing first.
    """

    def __init__(self, ctx):
        self.ctx = ctx
        self.written: list[Path] = []
        self.warnings: list[str] = []

    @property
    def dry_run(self) -> bool:
        return bool(getattr(self.ctx, "dry_run", False))

    def text(self, rel: str, content: str, *, bom: bool = False) -> Path:
        path = self.ctx.write_text(rel, (BOM if bom else "") + content)
        self.written.append(path)
        return path

    def binary(self, rel: str, save: Callable[[Path], None]) -> Path:
        write_binary = getattr(self.ctx, "write_binary", None)
        if callable(write_binary):
            path = write_binary(rel, save)
        else:  # pragma: no cover - only until Context gains write_binary
            path = self.ctx.out_path(rel)
            if not self.dry_run:
                path.parent.mkdir(parents=True, exist_ok=True)
                save(path)
            self.ctx.written.append(path)
        self.written.append(path)
        return path

    def info(self, message: str) -> None:
        self.ctx.info(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)
        self.ctx.warn(message)
