"""Configuration: one TOML file per converted mod.

See `configs/faerun.toml` for the reference file and `docs/cli.md` for the key
reference. Relative paths resolve against the converter repository root, so the
CLI behaves the same wherever it is run from.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .pdx.tokens import Date

#: Repository root: ``src/ck2ck3/config.py`` → three levels up.
REPO_ROOT = Path(__file__).resolve().parents[2]


class ConfigError(Exception):
    """The config file is missing a key or holds a value of the wrong shape."""


@dataclass(frozen=True)
class MapConfig:
    """Map geometry. Placeholders until lane `map-physical` measures them."""

    #: CK3 target province-map size in pixels, ``[width, height]``.
    dimensions: tuple[int, int] = (8192, 4096)
    #: Multiplier applied to the CK2 source pixels before pasting.
    scale: float = 1.0
    #: Where the scaled CK2 map lands on the CK3 canvas, ``[x, y]``.
    offset: tuple[int, int] = (0, 0)
    #: Filled in by lane `map-physical`; kept here so no other lane guesses.
    source_dimensions: tuple[int, int] | None = None


@dataclass(frozen=True)
class Config:
    path: Path
    name: str
    prefix: str
    version: str
    supported_version: str
    tags: tuple[str, ...]
    replace_paths: tuple[str, ...]
    bookmark_date: str
    ck2_game: Path
    ck2_mod: Path
    ck3_game: Path
    out: Path
    map: MapConfig = field(default_factory=MapConfig)
    raw: dict[str, Any] = field(default_factory=dict, compare=False)

    @property
    def bookmark(self) -> Date:
        return Date.parse(self.bookmark_date)

    @classmethod
    def load(cls, path: str | Path, *, out: str | Path | None = None) -> "Config":
        """Read a TOML config; ``out`` overrides ``[paths] out``."""
        path = Path(path)
        if not path.is_file():
            raise ConfigError(f"config file not found: {path}")
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
        mod = _table(raw, "mod", path)
        paths = _table(raw, "paths", path)
        map_raw = raw.get("map", {})
        return cls(
            path=path,
            name=_str(mod, "name", path, "mod"),
            prefix=_str(mod, "prefix", path, "mod"),
            version=str(mod.get("version", "0.0.0")),
            supported_version=str(mod.get("supported_version", "1.19.*")),
            tags=tuple(str(t) for t in mod.get("tags", ("Total Conversion",))),
            replace_paths=tuple(str(p) for p in mod.get("replace_paths", ())),
            bookmark_date=_str(mod, "bookmark_date", path, "mod"),
            ck2_game=_path(paths, "ck2_game", path),
            ck2_mod=_path(paths, "ck2_mod", path),
            ck3_game=_path(paths, "ck3_game", path),
            out=Path(out).expanduser().resolve()
            if out
            else _path(paths, "out", path),
            map=MapConfig(
                dimensions=_pair(map_raw, "dimensions", (8192, 4096), int),
                scale=float(map_raw.get("scale", 1.0)),
                offset=_pair(map_raw, "offset", (0, 0), int),
                source_dimensions=(
                    _pair(map_raw, "source_dimensions", (0, 0), int)
                    if "source_dimensions" in map_raw
                    else None
                ),
            ),
            raw=raw,
        )


def _table(raw: dict[str, Any], name: str, path: Path) -> dict[str, Any]:
    value = raw.get(name)
    if not isinstance(value, dict):
        raise ConfigError(f"{path}: missing [{name}] table")
    return value


def _str(table: dict[str, Any], key: str, path: Path, name: str) -> str:
    if key not in table:
        raise ConfigError(f"{path}: missing [{name}] {key}")
    return str(table[key])


def _path(table: dict[str, Any], key: str, path: Path) -> Path:
    if key not in table:
        raise ConfigError(f"{path}: missing [paths] {key}")
    value = Path(str(table[key])).expanduser()
    if not value.is_absolute():
        value = REPO_ROOT / value
    return value


def _pair(table: dict[str, Any], key: str, default, cast):
    value = table.get(key, default)
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ConfigError(f"[map] {key} must be a two-element list")
    return (cast(value[0]), cast(value[1]))
