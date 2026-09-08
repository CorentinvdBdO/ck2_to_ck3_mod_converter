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
    key_map = "overrides/loc_keys.csv"  # ck2_key,ck3_key[,rename|copy]
    skip_vanilla_collisions = false
    vanilla_keys = "docs/evidence/ck3_vanilla_loc_keys.txt"
    unknown_codes = "custom"            # or "marker"
    custom_loc = "marker"               # or "call"
    named_scope = "marker"              # or "reference"
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
    custom_loc: str = "marker"
    named_scope: str = "marker"

    @classmethod
    def from_raw(cls, raw: dict) -> "LocConfig":
        languages = raw.get("languages")
        unknown = str(raw.get("unknown_codes", "custom"))
        if unknown not in loc_codes.UNKNOWN_POLICIES:
            raise ValueError(
                f"[loc] unknown_codes must be one of "
                f"{', '.join(loc_codes.UNKNOWN_POLICIES)}, not {unknown!r}"
            )
        custom = str(raw.get("custom_loc", "marker"))
        if custom not in loc_codes.CUSTOM_LOC_POLICIES:
            raise ValueError(
                f"[loc] custom_loc must be one of "
                f"{', '.join(loc_codes.CUSTOM_LOC_POLICIES)}, not {custom!r}"
            )
        scope = str(raw.get("named_scope", "marker"))
        if scope not in loc_codes.NAMED_SCOPE_POLICIES:
            raise ValueError(
                f"[loc] named_scope must be one of "
                f"{', '.join(loc_codes.NAMED_SCOPE_POLICIES)}, not {scope!r}"
            )
        return cls(
            languages=tuple(str(x) for x in languages) if languages else None,
            min_share=float(raw.get("min_share", DEFAULT_MIN_SHARE)),
            key_map=_repo_path(raw.get("key_map")),
            skip_vanilla_collisions=bool(raw.get("skip_vanilla_collisions", False)),
            vanilla_keys=_repo_path(raw.get("vanilla_keys")),
            unknown_codes=unknown,
            custom_loc=custom,
            named_scope=scope,
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


@dataclass
class KeyMap:
    """The ``[loc] key_map`` table: which CK3 keys a CK2 key is emitted under.

    Two modes, because the lanes hand over two different things:

    * ``rename`` — the CK2 key is *replaced*. The ``traits`` lane's
      ``abdominal_pain -> trait_abdominal_pain``: CK3 never reads the bare id
      as a loc key, so keeping it would be 1100 dead strings.
    * ``copy`` — the CK3 key is emitted **in addition to** the CK2 key. The
      ``titles`` lane's ``k_neverwinter -> k_neverwinter_adj`` and the
      ``religions`` lane's ``ADEPT -> ADEPT_plural``: CK3 needs both, and a
      rename would leave the title with no name at all.

    A CK2 key may carry several rows; the text is emitted under every target.
    """

    #: ck2 key -> the CK3 keys to emit it under, in table order.
    targets: dict[str, tuple[str, ...]] = field(default_factory=dict)
    #: ck2 keys that keep their own name as well (any row said ``copy``).
    keep_source: set[str] = field(default_factory=set)

    def keys_for(self, key: str) -> tuple[str, ...]:
        """Every CK3 key ``key``'s text goes to (``(key,)`` when unmapped)."""
        targets = self.targets.get(key)
        if not targets:
            return (key,)
        if key in self.keep_source:
            return (key, *(t for t in targets if t != key))
        return targets

    def __len__(self) -> int:
        return len(self.targets)


#: ``mode`` column values. Default is ``rename`` so the pre-existing
#: two-column tables keep behaving as they did.
KEY_MAP_MODES = ("rename", "copy")


def read_key_map(path: Path) -> KeyMap:
    """``ck2_key,ck3_key[,mode]`` rows; header and ``#`` comments optional.

    Regenerate the Faerûn table with ``scripts/build_loc_key_map.py``, which
    concatenates every ``mappings/loc_key_renames_*.csv`` with the right mode
    per source lane.
    """
    key_map = KeyMap()
    with open(path, encoding="utf-8-sig", newline="") as handle:
        for row in csv.reader(handle):
            if len(row) < 2 or row[0].lstrip().startswith("#"):
                continue
            source, target = row[0].strip(), row[1].strip()
            if not source or not target or source.lower() == "ck2_key":
                continue
            mode = (row[2].strip().lower() if len(row) > 2 and row[2].strip()
                    else "rename")
            if mode not in KEY_MAP_MODES:
                raise ValueError(
                    f"{path}: {source} -> {target}: mode must be one of "
                    f"{', '.join(KEY_MAP_MODES)}, not {mode!r}"
                )
            if target != source:
                existing = key_map.targets.get(source, ())
                if target not in existing:
                    key_map.targets[source] = (*existing, target)
            if mode == "copy":
                key_map.keep_source.add(source)
    return key_map


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
    #: Lines written under a ``[loc] key_map`` target rather than the CK2
    #: key: renames plus the extra ``copy`` targets.
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

    key_map = read_key_map(config.key_map) if config.key_map else KeyMap()
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
                converted = loc_codes.convert_text(
                    text,
                    custom_loc=custom_loc,
                    unknown=config.unknown_codes,
                    custom_loc_policy=config.custom_loc,
                    named_scope_policy=config.named_scope,
                    report=plan.report,
                )
                for target in key_map.keys_for(key):
                    if target != entry.key:
                        plan.renamed += 1
                    if target in vanilla:
                        plan.vanilla_skipped += 1
                        continue
                    entries[target] = converted
            if entries:
                per_file.append((path.stem, entries))
        plan.per_language[language] = per_file
    return plan


def run(ctx: Context) -> StepResult:
    config = LocConfig.from_raw(ctx.config.raw.get("loc", {}))
    plan = build(ctx, config)
    name_loc: dict[str, str] = dict(
        ctx.data.get("cultures", {}).get("name_loc", {})
    )
    if not name_loc:
        ctx.warn(
            "no name-list tokens from step `cultures` in this pass; "
            f"localization/*/{ctx.config.prefix}_names_l_*.yml not written, so "
            "every name in common/culture/name_lists shows as its raw key "
            "(run `cultures` in the same pass)"
        )

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
        # The `cultures` step's name-list tokens. A CK3 male_names/female_names
        # entry is a localisation key, not a display string (77 736 "Missing
        # loc X" errors without it, `verified` 2026-09-08), and CK2 kept the
        # literals in common/cultures rather than in a CSV, so they reach this
        # step through ctx.data rather than through a source file.
        if name_loc:
            written.append(
                ctx.write_loc(
                    Path("localization") / language
                    / f"{ctx.config.prefix}_names_l_{language}.yml",
                    name_loc,
                    language=language,
                    header_comments=[
                        "name-list token -> the CK2 literal it stands for "
                        "(step cultures)"
                    ],
                )
            )
            counts["files"] += 1
            keys += len(name_loc)
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
    counts["name_list_keys"] = len(name_loc)
    counts["custom_loc_markered"] = sum(report.custom_loc_markered.values())
    counts["custom_loc_names"] = len(report.custom_loc_markered)
    counts["named_scope_markered"] = sum(report.named_scope_markered.values())
    counts["named_scope_names"] = len(report.named_scope_markered)
    counts["duplicate_keys"] = len(plan.duplicates)
    counts["invalid_keys"] = len(plan.invalid_keys)
    if plan.renamed:
        counts["key_map_keys"] = plan.renamed
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
    if report.named_scope_markered:
        warnings.append(
            f"{sum(report.named_scope_markered.values())} references to a CK2 "
            f"saved scope ({len(report.named_scope_markered)} distinct) became "
            "visible markers, because nothing ports CK2's events and so nothing "
            "runs save_scope_as: CK3 answers an unresolvable scope with "
            "\"pdx_data_localize.cpp: Data error in loc string '<key>'\". Set "
            '[loc] named_scope = "reference" in the commit that ships the event '
            "port"
        )
    if report.needs_custom_loc:
        warnings.append(
            f"{sum(report.needs_custom_loc.values())} codes became Custom() "
            f"calls that nothing defines yet "
            f"({len(report.needs_custom_loc)} distinct). CK3 answers each with "
            "jomini_custom_text.h: \"Object of type 'character' is not valid "
            "for '<name>'\" - see docs/evidence/game_load_2026-09-08.md"
        )
    if report.custom_loc_markered:
        warnings.append(
            f"{sum(report.custom_loc_markered.values())} CK2 "
            f"customizable-localisation codes "
            f"({len(report.custom_loc_markered)} distinct) became visible "
            "markers, because nothing emits common/customizable_localization "
            "and a Custom() call to a name CK3 does not know is an error per "
            'evaluation. That count is the size of the port; set [loc] '
            'custom_loc = "call" in the commit that ships it'
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
