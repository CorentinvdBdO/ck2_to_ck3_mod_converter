"""Step ``loc``: every CK2 localisation CSV becomes CK3 ``.yml``.

One output file per source CSV per language,
``localization/<lang>/<prefix>_<stem>_l_<lang>.yml``, so a diff of the
generated mod points straight back at the CK2 file that produced it. Keys keep
their CK2 name (``docs/DECISIONS.md``), which is what makes every other lane's
generated identifier resolve to text without a rename table.

The CSV quirks this has to survive are listed in ``docs/formats_loc.md``, the
text-code conversion in ``docs/loc_codes.md``.

Config (``[loc]``, all optional)::

    languages = ["english", "french"]   # default: english + every column
                                        # whose fill share reaches min_share
    min_share = 0.05
    key_map = "overrides/loc_keys.csv"  # ck2_key,ck3_key — applied last
    skip_vanilla_collisions = false
    vanilla_keys = "docs/evidence/ck3_vanilla_loc_keys.txt"
    unknown_codes = "custom"            # or "marker"
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path

from .. import ck2mod, loc_codes
from ..config import REPO_ROOT
from ..context import Context, StepResult
from ..csvloc import CK2_COLUMNS, LocFile, read_ck2_csv

DESCRIPTION = "convert the CK2 localisation CSVs into CK3 yml, one file per source"
OUTPUTS: tuple[str, ...] = ("localization",)

#: English is always written: a CK3 key with no english line falls back to
#: showing the raw key in every language (`verified` behaviour of CK3 1.19).
MANDATORY_LANGUAGE = "english"
#: A column has to be this full to be worth a file of its own.
DEFAULT_MIN_SHARE = 0.05
#: How many distinct unconverted codes to name in the run log before
#: collapsing the rest into one line.
WARN_LIMIT = 20
#: Anything outside this becomes ``_`` in an output filename.
UNSAFE_IN_NAME = re.compile(r"[^a-z0-9_]+")
#: A key CK3 can actually reference. Faerûn has 21 keys that cannot
#: (``Effect:``, ``§bCapital:``, ``d_twilit_land:adj``, ``Army Maintenance``);
#: they are CK2 UI strings, and a ``:`` or a space in the key would break the
#: ``.yml`` line itself. See ``docs/formats_loc.md`` §malformed keys.
VALID_KEY = re.compile(r"^[A-Za-z0-9_.\-]+$")


@dataclass
class LocConfig:
    """The ``[loc]`` table, with the defaults documented above."""

    languages: tuple[str, ...] | None = None
    min_share: float = DEFAULT_MIN_SHARE
    key_map: Path | None = None
    skip_vanilla_collisions: bool = False
    vanilla_keys: Path | None = None
    unknown_codes: str = "custom"

    @classmethod
    def from_raw(cls, raw: dict) -> "LocConfig":
        languages = raw.get("languages")
        unknown = str(raw.get("unknown_codes", "custom"))
        if unknown not in loc_codes.UNKNOWN_POLICIES:
            raise ValueError(
                f"[loc] unknown_codes must be one of "
                f"{', '.join(loc_codes.UNKNOWN_POLICIES)}, not {unknown!r}"
            )
        return cls(
            languages=tuple(str(x) for x in languages) if languages else None,
            min_share=float(raw.get("min_share", DEFAULT_MIN_SHARE)),
            key_map=_repo_path(raw.get("key_map")),
            skip_vanilla_collisions=bool(raw.get("skip_vanilla_collisions", False)),
            vanilla_keys=_repo_path(raw.get("vanilla_keys")),
            unknown_codes=unknown,
        )


def _repo_path(value) -> Path | None:
    if not value:
        return None
    path = Path(str(value)).expanduser()
    return path if path.is_absolute() else REPO_ROOT / path


def out_name(prefix: str, stem: str, language: str) -> str:
    """``fae_0000_titles_l_english.yml`` from ``0000_titles.csv``.

    CK3 requires the ``_l_<language>`` suffix and picks the language from it,
    not from the folder (`verified`: every vanilla file is named that way).
    """
    safe = UNSAFE_IN_NAME.sub("_", stem.lower()).strip("_")
    return f"{prefix}_{safe}_l_{language}.yml"


def language_shares(files: list[LocFile]) -> dict[str, float]:
    """Share of rows that have text, per language column.

    Faerûn fills english on 100.0% of rows and french/german/spanish on 70.1%
    each (`verified` 2026-09-07, ``docs/evidence/loc_quirks.md``).
    """
    filled: dict[str, int] = {}
    rows = 0
    for loc in files:
        languages = set(loc.languages.values()) or set(CK2_COLUMNS.values())
        for entry in loc:
            rows += 1
            for language in languages:
                if entry.values.get(language):
                    filled[language] = filled.get(language, 0) + 1
    return {lang: count / rows for lang, count in filled.items()} if rows else {}


def read_key_map(path: Path) -> dict[str, str]:
    """``ck2_key,ck3_key`` pairs, applied after everything else.

    A rename table exists so a later lane can change a generated id and still
    resolve the CK2 text (``docs/DECISIONS.md``). A header row is optional.
    """
    mapping: dict[str, str] = {}
    with open(path, encoding="utf-8-sig", newline="") as handle:
        for row in csv.reader(handle):
            if len(row) < 2:
                continue
            source, target = row[0].strip(), row[1].strip()
            if not source or not target or source.lower() == "ck2_key":
                continue
            mapping[source] = target
    return mapping


def read_vanilla_keys(path: Path) -> set[str]:
    """The cached CK3 vanilla key set (``scripts/build_ck3_vanilla_loc_keys.py``)."""
    return {
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    }


@dataclass
class Plan:
    """What the step decided to write, before anything is written."""

    languages: list[str] = field(default_factory=list)
    #: ``(csv stem, {key: text})`` per language, in source order.
    per_language: dict[str, list[tuple[str, dict[str, str]]]] = field(
        default_factory=dict
    )
    duplicates: list[tuple[str, str, str]] = field(default_factory=list)
    #: ``(file, line, key)`` for a key CK3 could never reference.
    invalid_keys: list[tuple[str, int, str]] = field(default_factory=list)
    renamed: int = 0
    vanilla_skipped: int = 0
    report: loc_codes.Report = field(default_factory=loc_codes.Report)


def build(ctx: Context, config: LocConfig) -> Plan:
    """Read every CSV and decide the exact file contents. Writes nothing."""
    paths = ck2mod.loc_files(ctx.ck2_mod)
    files = [read_ck2_csv(path) for path in paths]
    custom_loc = loc_codes.custom_loc_names(ctx.ck2_mod)
    plan = Plan()

    shares = language_shares(files)
    if config.languages is not None:
        plan.languages = list(config.languages)
    else:
        plan.languages = [MANDATORY_LANGUAGE] + sorted(
            lang
            for lang, share in shares.items()
            if lang != MANDATORY_LANGUAGE and share >= config.min_share
        )
    for language in plan.languages:
        ctx.info(f"{language}: {shares.get(language, 0.0):.1%} of rows filled")

    # Last definition wins: CK2 loads localisation in filename order and a
    # later file overrides an earlier one (docs/formats_loc.md §load order).
    owner: dict[str, str] = {}
    for loc, path in zip(files, paths):
        for entry in loc:
            if not entry.key:
                continue
            if not VALID_KEY.match(entry.key):
                plan.invalid_keys.append((path.name, entry.line, entry.key))
                continue
            if entry.key in owner and owner[entry.key] != path.name:
                plan.duplicates.append((entry.key, owner[entry.key], path.name))
            owner[entry.key] = path.name

    key_map = read_key_map(config.key_map) if config.key_map else {}
    vanilla: set[str] = set()
    if config.skip_vanilla_collisions and config.vanilla_keys:
        if config.vanilla_keys.is_file():
            vanilla = read_vanilla_keys(config.vanilla_keys)
        else:
            ctx.warn(
                f"[loc] skip_vanilla_collisions is on but {config.vanilla_keys} "
                "is missing; run scripts/build_ck3_vanilla_loc_keys.py"
            )

    for language in plan.languages:
        per_file: list[tuple[str, dict[str, str]]] = []
        for loc, path in zip(files, paths):
            entries: dict[str, str] = {}
            for entry in loc:
                key = entry.key
                if not key or owner.get(key) != path.name:
                    continue
                if not VALID_KEY.match(key):
                    continue
                # An empty cell falls back to english: a missing line makes
                # CK3 print the raw key (docs/formats_loc.md).
                text = entry.values.get(language) or entry.values.get(
                    MANDATORY_LANGUAGE, ""
                )
                if not text:
                    continue
                key = key_map.get(key, key)
                if key != entry.key:
                    plan.renamed += 1
                if key in vanilla:
                    plan.vanilla_skipped += 1
                    continue
                entries[key] = loc_codes.convert_text(
                    text,
                    custom_loc=custom_loc,
                    unknown=config.unknown_codes,
                    report=plan.report,
                )
            if entries:
                per_file.append((path.stem, entries))
        plan.per_language[language] = per_file
    return plan


def run(ctx: Context) -> StepResult:
    config = LocConfig.from_raw(ctx.config.raw.get("loc", {}))
    plan = build(ctx, config)

    written = []
    counts: dict[str, int] = {"files": 0}
    for language, per_file in plan.per_language.items():
        keys = 0
        for stem, entries in per_file:
            rel = Path("localization") / language / out_name(
                ctx.config.prefix, stem, language
            )
            written.append(
                ctx.write_loc(
                    rel,
                    entries,
                    language=language,
                    header_comments=[f"from {stem}.csv"],
                )
            )
            keys += len(entries)
        counts["files"] += len(per_file)
        counts[f"keys_{language}"] = keys

    report = plan.report
    counts["codes"] = report.total
    counts["codes_converted"] = report.converted
    counts["codes_unconverted"] = report.total - report.converted
    counts["colour_codes"] = sum(report.colours.values())
    counts["icon_codes"] = report.icons
    counts["stray_brackets"] = report.stray_brackets
    counts["stray_colour_marks"] = report.stray_colour_marks
    counts["duplicate_keys"] = len(plan.duplicates)
    counts["invalid_keys"] = len(plan.invalid_keys)
    if plan.renamed:
        counts["renamed_keys"] = plan.renamed
    if plan.vanilla_skipped:
        counts["vanilla_collisions_skipped"] = plan.vanilla_skipped

    warnings: list[str] = []
    for key, first, second in plan.duplicates[:WARN_LIMIT]:
        warnings.append(f"key {key!r} defined in both {first} and {second}; {second} wins")
    if len(plan.duplicates) > WARN_LIMIT:
        warnings.append(
            f"...and {len(plan.duplicates) - WARN_LIMIT} more duplicate keys"
        )
    for name, line, key in plan.invalid_keys[:WARN_LIMIT]:
        warnings.append(f"{name}:{line}: key {key!r} is not a legal CK3 key, skipped")
    if len(plan.invalid_keys) > WARN_LIMIT:
        warnings.append(
            f"...and {len(plan.invalid_keys) - WARN_LIMIT} more illegal keys"
        )
    ranked = sorted(report.unconverted.items(), key=lambda kv: -kv[1])
    for code, count in ranked[:WARN_LIMIT]:
        warnings.append(f"no CK3 equivalent for {code} ({count} occurrences)")
    if len(ranked) > WARN_LIMIT:
        warnings.append(
            f"...and {len(ranked) - WARN_LIMIT} more codes with no CK3 equivalent "
            f"(full table: docs/evidence/ck2_loc_codes.csv)"
        )
    if report.needs_scope:
        warnings.append(
            f"{sum(report.needs_scope.values())} codes need a saved scope in the "
            f"converted event ({len(report.needs_scope)} distinct); see "
            f"docs/loc_codes.md"
        )
    if report.needs_custom_loc:
        warnings.append(
            f"{sum(report.needs_custom_loc.values())} codes became Custom() calls "
            f"that nothing defines yet ({len(report.needs_custom_loc)} distinct)"
        )
    for warning in warnings:
        ctx.warn(warning)

    return StepResult(
        summary=(
            f"localisation: {counts['files']} yml in "
            f"{len(plan.per_language)} languages, "
            f"{counts.get('keys_' + MANDATORY_LANGUAGE, 0)} english keys, "
            f"{report.coverage():.1%} of {report.total} text codes converted"
        ),
        counts=counts,
        warnings=warnings,
        written=written,
    )
