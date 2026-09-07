"""What a conversion step is handed: paths, parser, localisation, ids, logging.

A step never opens a file by itself and never prints: everything goes through
the :class:`Context`, so ``--dry-run`` is honest and the run log in
``docs/evidence/last_run.md`` is complete.
"""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass, field
from collections.abc import Callable
from pathlib import Path
from typing import Any, Iterable, Mapping

from . import ck2mod, csvloc
from .config import Config
from .pdx import Block, Document, parse_file, write, write_file
from .pdx.encoding import CK2_ENCODING, CK3_ENCODING, write_text


@dataclass
class StepResult:
    """What a step reports back. ``summary`` is the one line the CLI prints."""

    summary: str
    counts: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    written: list[Path] = field(default_factory=list)
    skipped: bool = False

    def count_line(self) -> str:
        return ", ".join(f"{k}={v}" for k, v in self.counts.items())


class IdAllocator:
    """Hands out CK3 numeric ids and remembers what each key was given.

    CK3 needs dense province, character and dynasty ids that do not collide
    with the ones another step already used, so every step asks the shared
    allocator instead of keeping its own counter.
    """

    def __init__(self, name: str, start: int = 1) -> None:
        self.name = name
        self.start = start
        self._next = start
        self._by_key: dict[str, int] = {}
        self._used: set[int] = set()

    def reserve(self, value: int) -> None:
        """Mark an id as taken (an id imported unchanged from CK2)."""
        self._used.add(value)

    def allocate(self, key: str | None = None) -> int:
        """Return a fresh id, or the id already given to ``key``."""
        if key is not None and key in self._by_key:
            return self._by_key[key]
        while self._next in self._used:
            self._next += 1
        value = self._next
        self._used.add(value)
        self._next += 1
        if key is not None:
            self._by_key[key] = value
        return value

    def get(self, key: str) -> int | None:
        return self._by_key.get(key)

    def mapping(self) -> dict[str, int]:
        return dict(self._by_key)

    def __len__(self) -> int:
        return len(self._used)


class Context:
    """Handed to every ``run(ctx)``."""

    def __init__(
        self,
        config: Config,
        *,
        dry_run: bool = False,
        logger: logging.Logger | None = None,
    ) -> None:
        self.config = config
        self.dry_run = dry_run
        self.log = logger or logging.getLogger("ck2ck3")
        self.out = config.out
        self.ck2_mod = config.ck2_mod
        self.ck2_game = config.ck2_game
        self.ck3_game = config.ck3_game
        #: Cross-step handoff, keyed by producing step (see docs/cli.md).
        self.data: dict[str, Any] = {}
        self.written: list[Path] = []
        self.warnings: list[str] = []
        self._allocators: dict[str, IdAllocator] = {}

    # -- paths -------------------------------------------------------------
    def ck2(self, *parts: str) -> Path:
        """A path inside the CK2 source mod."""
        return self.ck2_mod.joinpath(*parts)

    def ck3(self, *parts: str) -> Path:
        """A path inside the CK3 game folder (read-only reference)."""
        return self.ck3_game.joinpath(*parts)

    def out_path(self, *parts: str) -> Path:
        """A path inside the generated mod."""
        return self.out.joinpath(*parts)

    def ck2_script_files(self) -> list[Path]:
        return ck2mod.script_files(self.ck2_mod)

    # -- reading -----------------------------------------------------------
    def parse_ck2(self, *parts: str, lenient: bool = False) -> Document:
        """Parse a CK2 script file (Windows-1252 by default, sniffed)."""
        return parse_file(self.ck2(*parts), lenient=lenient)

    def parse_ck3(self, *parts: str, lenient: bool = False) -> Document:
        """Parse a CK3 game script file (UTF-8)."""
        return parse_file(self.ck3(*parts), encoding=CK3_ENCODING, lenient=lenient)

    def parse_path(self, path: Path, *, lenient: bool = False) -> Document:
        return parse_file(path, lenient=lenient)

    def read_ck2_csv(self, *parts: str) -> csvloc.LocFile:
        """Read one CK2 localisation CSV."""
        return csvloc.read_ck2_csv(self.ck2(*parts), CK2_ENCODING)

    def read_ck2_loc(self, language: str = "english") -> tuple[dict[str, str], list[str]]:
        """Read the whole CK2 localisation folder, merged."""
        return csvloc.read_ck2_loc(self.ck2_mod, language)

    # -- writing -----------------------------------------------------------
    def header(self, source: str | Path | None = None) -> str:
        """The banner every generated script file carries."""
        origin = f" from {source}" if source else ""
        return (
            f"# Generated by ck2ck3{origin}. Do not edit: regenerated on every run.\n"
        )

    def write_script(
        self,
        rel: str | Path,
        block: Block,
        *,
        source: str | Path | None = None,
        canonical: bool = False,
        header: bool = True,
    ) -> Path:
        """Write a parse tree as UTF-8 script under the output mod.

        ``header=False`` omits the generated-by banner, for a file whose reader
        is not the game script engine (``descriptor.mod``, read by the
        launcher).
        """
        path = self.out_path(str(rel))
        if not self.dry_run:
            write_file(
                block,
                path,
                header=self.header(source) if header else None,
                canonical=canonical,
            )
        self._record(path, len(write(block, canonical=canonical)))
        return path

    def write_commented_script(
        self,
        rel: str | Path,
        block: Block,
        *,
        source: str | Path | None = None,
        preamble: Iterable[str] = (),
    ) -> Path:
        """Write a parse tree as *commented-out* script (every line ``# ``-prefixed).

        The landing place for CK2 content that has no CK3 construct: the file is
        inert for the game, and a submod revives a block by stripping the
        prefixes. ``preamble`` lines are written verbatim after the banner.
        """
        path = self.out_path(str(rel))
        body = "".join(f"{line}\n" for line in preamble)
        body += write(block, commented=True)
        text = self.header(source) + body
        if not self.dry_run:
            write_text(path, text)
        self._record(path, len(text))
        return path

    def copy_file(self, rel: str | Path, source: Path) -> Path:
        """Copy a binary asset (``.dds``, ``.png``) into the output mod.

        Steps must not touch the filesystem themselves, so asset copies go
        through here: ``--dry-run`` stays honest and the run log stays complete.
        """
        path = self.out_path(str(rel))
        if not self.dry_run:
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, path)
        self._record(path, source.stat().st_size)
        return path

    def write_text(self, rel: str | Path, text: str) -> Path:
        """Write raw text (CSV, `.mod`, anything not a parse tree) as UTF-8."""
        path = self.out_path(str(rel))
        if not self.dry_run:
            write_text(path, text)
        self._record(path, len(text))
        return path

    def write_loc(
        self,
        rel: str | Path,
        entries: Mapping[str, str] | Iterable[tuple[str, str]],
        *,
        language: str = "english",
        version: int = 0,
        header_comments: Iterable[str] = (),
    ) -> Path:
        """Write a CK3 localisation ``.yml`` (UTF-8 with BOM, CRLF)."""
        path = self.out_path(str(rel))
        pairs = list(entries.items() if isinstance(entries, Mapping) else entries)
        if not self.dry_run:
            csvloc.write_ck3_yml(
                path,
                pairs,
                language=language,
                version=version,
                header_comments=[*header_comments, self.header().strip("#\n ")],
            )
        self._record(path, len(pairs))
        return path

    def write_binary(self, rel: str | Path, save: Callable[[Path], None]) -> Path:
        """Write a binary file by handing ``save`` the resolved output path.

        For output no ``write_*`` above covers: the map lane's four PNGs.  A
        callable rather than bytes because a 54 Mpx PNG is cheaper for PIL to
        write straight to the final path than to serialise into memory, and in a
        dry run the callable is never invoked at all.
        """
        path = self.out_path(str(rel))
        size = 0
        if not self.dry_run:
            path.parent.mkdir(parents=True, exist_ok=True)
            save(path)
            size = path.stat().st_size if path.exists() else 0
        self._record(path, size)
        return path

    def _record(self, path: Path, size: int) -> None:
        self.written.append(path)
        self.log.debug("%s %s (%d)", "would write" if self.dry_run else "wrote", path, size)

    # -- misc --------------------------------------------------------------
    def ids(self, name: str, start: int = 1) -> IdAllocator:
        """The shared id allocator called ``name`` (created on first use)."""
        if name not in self._allocators:
            self._allocators[name] = IdAllocator(name, start)
        return self._allocators[name]

    def warn(self, message: str) -> None:
        self.warnings.append(message)
        self.log.warning(message)

    def info(self, message: str) -> None:
        self.log.info(message)
