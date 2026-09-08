"""The step registry.

A step is a module ``ck2ck3.steps.<name>`` that defines:

``run(ctx) -> StepResult | str | None``
    the work; ``ctx`` is a :class:`ck2ck3.context.Context`.
``OUTPUTS: tuple[str, ...]``
    the output-mod subtrees the step owns. Two steps must not share one, so a
    lane can be re-run without clobbering another lane's files.
``DESCRIPTION: str``
    one line, shown by ``ck2ck3 --list-steps``.

Adding a step: drop the module in this package and add its name to
:data:`DEFAULT_ORDER`. See `docs/cli.md` for the contract in full.
"""

from __future__ import annotations

import importlib
import pkgutil
from types import ModuleType

#: Steps run in this order when ``--steps`` is not given.
DEFAULT_ORDER: tuple[str, ...] = (
    "clean",
    "descriptor",
    # Before every content step: it only writes empty shadows of vanilla files,
    # and a later step that really fills one of those folders must win.
    "tc_template",
    "map",
    # Before `cultures`: a CK3 name list needs `dynasty_names`, CK2 keeps
    # dynasty names globally in common/dynasties rather than per culture, and a
    # name list with fewer than MINIMUM_DYNASTY_NAMES (2) of them is an error
    # at load and leaves CK3 with no name to mint a generated character's
    # dynasty from (docs/evidence/game_load_2026-09-08.md).
    "dynasties",
    "cultures",
    "religions",
    "titles",
    "history_titles",
    "bookmarks",
    "traits",
    "characters",
    "loc",
    # Last on purpose: `tests` asserts what the earlier steps wrote, by
    # reading the generated mod back.
    "tests",
)


class UnknownStep(Exception):
    pass


class BadStep(Exception):
    """The module exists but does not honour the step contract."""


def available() -> list[str]:
    """Every step module in this package, sorted."""
    return sorted(m.name for m in pkgutil.iter_modules(__path__))


def load(name: str) -> ModuleType:
    """Import a step module and check the contract."""
    if name not in available():
        raise UnknownStep(f"unknown step {name!r}; available: {', '.join(available())}")
    module = importlib.import_module(f"{__name__}.{name}")
    if not callable(getattr(module, "run", None)):
        raise BadStep(f"step {name!r} has no run(ctx)")
    if not isinstance(getattr(module, "OUTPUTS", None), tuple):
        raise BadStep(f"step {name!r} has no OUTPUTS tuple")
    return module


def describe(name: str) -> str:
    return getattr(load(name), "DESCRIPTION", "")


def resolve(names: list[str] | None) -> list[str]:
    """Turn a ``--steps`` list into the ordered list of steps to run."""
    if not names:
        return list(DEFAULT_ORDER)
    wanted: list[str] = []
    for name in names:
        name = name.strip()
        if not name:
            continue
        if name == "all":
            wanted.extend(DEFAULT_ORDER)
            continue
        load(name)  # raises UnknownStep
        wanted.append(name)
    seen: set[str] = set()
    return [n for n in wanted if not (n in seen or seen.add(n))]
