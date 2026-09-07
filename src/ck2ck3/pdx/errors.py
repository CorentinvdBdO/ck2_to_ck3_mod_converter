"""Errors and recoverable problems raised by the Paradox-script parser."""

from __future__ import annotations

from dataclasses import dataclass


class PdxError(Exception):
    """Base class for every error raised by :mod:`ck2ck3.pdx`."""


@dataclass
class Location:
    """A position in a source file. ``line`` and ``col`` are 1-based."""

    source: str
    line: int
    col: int

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.source}:{self.line}:{self.col}"


class PdxSyntaxError(PdxError):
    """A syntax error that carries ``file:line:col``.

    Never raised for a character the tokenizer merely does not know: the
    tokenizer stops on the first character it cannot classify instead of
    skipping it silently.
    """

    def __init__(self, message: str, location: Location) -> None:
        self.message = message
        self.location = location
        super().__init__(f"{location}: {message}")


@dataclass
class Problem:
    """A recoverable oddity found while parsing in lenient mode.

    Collected on :attr:`ck2ck3.pdx.nodes.Document.problems` so that nothing is
    dropped without a trace.
    """

    kind: str
    message: str
    location: Location

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.location}: {self.kind}: {self.message}"
