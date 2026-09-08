"""``history/titles`` from CK2 ``history/titles``, one file per tier.

Three CK3 rules drive the shape:

* **No top-level keys.**  `verified`: 0 depth-1 keys across all 183 vanilla
  files.  Faerun happens to write none either (`verified`, 0 of 3420 files),
  but the writer still wraps any it finds in :data:`EARLY_DATE`.
* **``succession_laws`` is a braced list**, replacing per law *group*, while
  CK2 repeats ``law = x`` lines mixing succession, gender and a dozen
  unrelated groups.  :func:`ck2ck3.titles.tables.map_succession_laws` splits
  them; what it cannot place is written as a comment.
* **The title carries the government.**  CK2 derives it from the holder, so
  the line has to be synthesised: it is emitted once, in the first dated block
  that gives the title a holder.

Integrity, all three warn rather than guess:
``holder`` must name a character that exists in CK2 ``history/characters``
(otherwise ``holder = 0``, which vanilla itself uses), ``liege`` must name a
title the mod defines, and a holder must not predate its own birth.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from ..pdx import Block, Date, Node, write
from .ck2read import TIER_BY_PREFIX, Ck2CharacterStub, Ck2TitleHistory
from .tables import GovernmentChoice, map_succession_laws
from .text import Lines, slug, tail

#: A live CK3 title that no CK2 file gives a history still needs an entry:
#: ck3-tiger reports ``error(missing-item): <title> has no title history`` for
#: any title used as a ``liege``.  ``holder = 0`` is the vanilla way of saying
#: "exists, unheld" (`verified`, ``history/titles/k_saryarka.txt:9``).
STUB_HISTORY = (
    "# No CK2 history/titles file for this title. CK3 needs a history entry for",
    "# every title (ck3-tiger: \"has no title history\"); holder = 0 means unheld.",
)

#: The date CK2 top-level keys are wrapped in.  Earlier than any Faerun date
#: (the earliest is 1.1.1 itself, so this is the same instant) and legal CK3.
EARLY_DATE = "1.1.1"

#: CK2 dated title keys with no CK3 dated key.  Value = the reason.
COMMENT_ONLY: dict[str, str] = {
    "active": "CK3 expresses 'title does not exist yet' by having no holder before the date",
    "historical_nomad": "no CK3 equivalent",
    "holding_dynasty": "CK2 patrician bookkeeping; CK3 republics have no patrician families",
    "set_tribute_suzerain": "CK3 tributary_of loses CK2's permanent/tributary/vassal distinction",
    "clear_tribute_suzerain": "CK3 has no dated tributary clear",
    "set_global_flag": "CK2 flags become CK3 variables (lane events-decisions)",
    "insert_title_history": "CK2 key of the same name is unrelated to CK3 insert_title_history",
    "location": "CK2 province-modifier bookkeeping",
    "duration": "CK2 province-modifier bookkeeping",
    "who": "CK2 province-modifier bookkeeping",
    "type": "CK2 tribute-type bookkeeping",
    "years": "CK2 province-modifier bookkeeping",
    "percentage": "CK2 bookkeeping",
    "add_province_modifier": "province modifiers are not CK3 title history",
    "remove_province_modifier": "province modifiers are not CK3 title history",
    "add_building": "CK3 buildings live in history/provinces",
    "remove_building": "CK3 buildings live in history/provinces",
}

HEADER = (
    "# CK3 title history, converted from CK2 history/titles.",
    "# Every key sits inside a dated block: CK3 allows no top-level keys here",
    "# (verified: 0 depth-1 keys across all 183 vanilla files).",
    "# `government` is synthesised in the first block that sets a holder - CK2",
    "# derives government from the holder, CK3 from the title.",
    "# CK2 `law = x` lines become one succession_laws = { } list per date;",
    "# non-succession CK2 laws (voting power, centralisation) are comments.",
    "# CK2 effect = { } blocks are kept commented: porting CK2 effect syntax is",
    "# lane events-decisions, and an unknown effect id is a hard CK3 error.",
)


@dataclass
class HistoryResult:
    files: dict[str, str] = field(default_factory=dict)
    #: generated localisation for dated title renames.
    loc: dict[str, str] = field(default_factory=dict)
    counts: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


#: ``title -> [(date, ck2 holder id or None)]``, sorted.
Spans = dict[str, list[tuple[tuple[int, int, int], str | None]]]


def holder_spans(histories: Mapping[str, Ck2TitleHistory]) -> Spans:
    """The CK2 ``holder`` timeline of every title.

    Needed because CK3 rejects ``liege = X`` at a date when X has no *living*
    holder (ck3-tiger ``error(history): X has no holder at D`` /
    ``holder of X is not alive at D``, both with "setting the liege will not
    have effect here"), and CK2 writes exactly that in 963 places: it keeps a
    dead ruler as holder until the next succession entry.
    """
    out: Spans = {}
    for title, history in histories.items():
        spans: list[tuple[tuple[int, int, int], str | None]] = []
        for date, nodes in history.dated:
            for node in nodes:
                if node.key != "holder":
                    continue
                raw = str(node.value)
                spans.append(
                    ((date.year, date.month, date.day), None if raw in ("0", "-1") else raw)
                )
        out[title] = sorted(spans, key=lambda item: item[0])
    return out


def held_at(
    spans: Spans,
    title: str,
    date: Date,
    characters: Mapping[str, Ck2CharacterStub] | None = None,
) -> bool:
    """Does ``title`` have a *living* holder at ``date``?"""
    stamp = (date.year, date.month, date.day)
    holder: str | None = None
    for when, value in spans.get(title, ()):  # sorted
        if when > stamp:
            break
        holder = value
    if holder is None:
        return False
    if characters is None:
        return True
    stub = characters.get(holder)
    if stub is None:
        return False
    if stub.birth and stamp < (stub.birth.year, stub.birth.month, stub.birth.day):
        return False
    if stub.death and stamp > (stub.death.year, stub.death.month, stub.death.day):
        return False
    return True


@dataclass
class HistoryConfig:
    #: title id -> the government the title starts with.
    government: Mapping[str, GovernmentChoice]
    #: CK2 character id -> stub, for the holder integrity check.
    characters: Mapping[str, Ck2CharacterStub]
    #: every title id the mod defines as a live CK3 title.
    live_titles: frozenset[str]
    #: title id -> why it is not live, for the commented-out history blocks.
    dead_titles: Mapping[str, str] = field(default_factory=dict)
    #: title -> holder timeline, from :func:`holder_spans`.
    spans: Spans = field(default_factory=dict)
    prefix: str = "fae"
    #: county-capital baronies: CK3 executes their history on the county and
    #: logs "Trying to execute history in b_x capital barony title" otherwise.
    capital_baronies: frozenset[str] = frozenset()


def _stamp(date: Date) -> str:
    return f"{date.year}.{date.month}.{date.day}"


def _before(left: Date, right: Date) -> bool:
    return (left.year, left.month, left.day) < (right.year, right.month, right.day)


class _TitleWriter:
    def __init__(self, config: HistoryConfig, result: HistoryResult) -> None:
        self.cfg = config
        self.result = result
        self._name_keys: dict[str, str] = {}

    def _name_key(self, title: str, literal: str) -> str:
        key = f"tn_{self.cfg.prefix}_{slug(title)}_{slug(literal, 'name')}"
        self._name_keys[literal] = key
        self.result.loc[key] = literal
        self.result.loc.setdefault(f"{key}_adj", literal)
        return key

    def write(self, history: Ck2TitleHistory, out: Lines) -> None:
        title = history.id
        blocks: list[tuple[Date, list[Node]]] = []
        if history.toplevel:
            blocks.append((Date.parse(EARLY_DATE), list(history.toplevel)))
        blocks.extend(history.dated)
        blocks.sort(key=lambda item: (item[0].year, item[0].month, item[0].day))

        government = self.cfg.government.get(title)
        government_written = False
        out.line(0, f"{title} = {{")
        if government:
            out.comment(1, f"government derived: {government.reason}")
        for date, nodes in blocks:
            body = Lines()
            has_holder = self._date_block(title, date, nodes, body)
            if has_holder and government and not government_written:
                body.line(0, f"government = {government.government}")
                government_written = True
            text = body.text().rstrip("\n")
            if not text:
                continue
            out.line(1, f"{_stamp(date)} = {{")
            # body lines already carry their own relative indent
            for line in text.split("\n"):
                out.raw(f"\t\t{line}" if line else "")
            out.line(1, "}")
        out.line(0, "}")

    def _date_block(
        self, title: str, date: Date, nodes: list[Node], out: Lines
    ) -> bool:
        laws: list[str] = []
        has_holder = False
        for node in nodes:
            key = node.key
            value = node.value
            if key == "holder":
                has_holder = True
                out.line(0, self._holder(title, date, node))
            elif key == "liege":
                line = self._liege(title, date, node)
                if line:
                    out.line(0, line)
                else:
                    out.comment(0, f"CK2 liege = {value} dropped (see the run log)")
            elif key == "de_jure_liege":
                target = str(value)
                if target in self.cfg.live_titles or target == "0":
                    out.line(0, f"de_jure_liege = {target}")
                else:
                    out.comment(0, f"CK2 de_jure_liege = {target} is not a live title")
            elif key == "law":
                laws.append(str(value))
            elif key == "government":
                # handled by the government derivation; the explicit CK2 value
                # is already folded into GovernmentChoice for this title.
                out.comment(0, f"CK2 government = {value} (see the derived line)")
            elif key == "name":
                literal = str(value).strip('"')
                loc_key = self._name_key(title, literal)
                out.line(0, "effect = {")
                out.line(1, f"set_title_name = {loc_key}\t# CK2 name = {literal}")
                out.line(0, "}")
            elif key == "adjective":
                literal = str(value).strip('"')
                out.comment(
                    0,
                    f"CK2 adjective = {literal} - CK3 derives it as <name key>_adj",
                )
            elif key == "capital":
                county = str(value)
                if county in self.cfg.live_titles:
                    out.line(0, "effect = {")
                    out.line(1, f"set_capital_county = title:{county}")
                    out.line(0, "}")
                else:
                    out.comment(0, f"CK2 capital = {county} is not a live county title")
            elif key == "reset_name":
                out.line(0, "reset_name = yes")
            elif key == "effect" and isinstance(value, Block):
                out.comment(0, "CK2 effect = { } - port is lane events-decisions:")
                for line in write(value).rstrip("\n").split("\n"):
                    out.comment(0, line.strip() or "#")
            elif key in COMMENT_ONLY:
                out.comment(0, f"CK2 {key} = {self._short(value)} - {COMMENT_ONLY[key]}")
            elif key.startswith("b_"):
                out.comment(
                    0,
                    f"CK2 {key} = {self._short(value)} - a barony holding belongs "
                    "to history/provinces in CK3",
                )
            else:
                out.comment(0, f"CK2 {key} = {self._short(value)} - unmapped")
                self.result.warnings.append(
                    f"{title} {_stamp(date)}: unmapped CK2 key {key}"
                )
        if laws:
            government = self.cfg.government.get(title)
            mapping = map_succession_laws(
                laws,
                government=government.government if government else "feudal_government",
            )
            if mapping.laws:
                out.line(0, "succession_laws = {")
                for law in mapping.laws:
                    out.line(1, law)
                out.line(0, "}")
            for ck2_law, note in mapping.notes:
                out.comment(0, f"CK2 law = {ck2_law}: {note}")
            for ck2_law, reason in mapping.dropped:
                out.comment(0, f"CK2 law = {ck2_law} dropped: {reason}")
        return has_holder

    def _short(self, value: object) -> str:
        if isinstance(value, Block):
            return "{ ... }"
        return str(value)

    def _holder(self, title: str, date: Date, node: Node) -> str:
        raw = str(node.value)
        comment = f"\t{tail(node.trailing_comment).strip()}" if node.trailing_comment else ""
        if raw in ("0", "-1"):
            if title[:2] in ("b_", "c_"):
                # CK3: "Land associated barony/county X is given a null holder
                # (ie. it's set to be destroyed)" - a land title cannot be unheld.
                return f"# CK2 holder = 0 at {_stamp(date)}: land titles cannot be unheld in CK3{comment}"
            return f"holder = 0{comment}"
        stub = self.cfg.characters.get(raw)
        if stub is None:
            self.result.warnings.append(
                f"{title} {_stamp(date)}: holder {raw} is not in CK2 history/characters"
            )
            if title[:2] in ("b_", "c_"):
                return f"# CK2 holder = {raw} at {_stamp(date)}: no such character, land title left to the game"
            return f"holder = 0\t# CK2 holder = {raw}, no such character"
        if stub.birth and _before(date, stub.birth):
            self.result.warnings.append(
                f"{title} {_stamp(date)}: holder {raw} is born {stub.birth}"
            )
            comment = comment or f"\t# born {stub.birth}, CK2 holds from {_stamp(date)}"
        elif stub.death and _before(stub.death, date):
            # kept, not dropped: dropping would leave the title unheld and the
            # next CK2 holder inherits nothing.
            self.result.warnings.append(
                f"{title} {_stamp(date)}: holder {raw} died {stub.death}"
            )
        return f"holder = {self.cfg.prefix}_{raw}{comment}"

    def _liege(self, title: str, date: Date, node: Node) -> str | None:
        raw = str(node.value)
        if raw in ("0", "-1"):
            return "liege = 0"
        if raw not in self.cfg.live_titles:
            self.result.warnings.append(
                f"{title} {_stamp(date)}: liege {raw} is not a live title"
            )
            return None
        # CK3 requires the liege to be a strictly higher tier
        # (ck3-tiger error(title-tier)); CK2 allowed same-tier vassalage.
        own = TIER_BY_PREFIX.get(title[0], 9)
        liege = TIER_BY_PREFIX.get(raw[0], 0)
        if liege >= own:
            self.result.warnings.append(
                f"{title} {_stamp(date)}: liege {raw} is not a higher tier, dropped"
            )
            return None
        if not held_at(self.cfg.spans, raw, date, self.cfg.characters):
            self.result.warnings.append(
                f"{title} {_stamp(date)}: liege {raw} has no holder then, dropped"
            )
            return None
        return f"liege = {raw}"


def render(
    histories: Mapping[str, Ck2TitleHistory], config: HistoryConfig
) -> HistoryResult:
    """Render ``history/titles/<prefix>_<tier>.txt``, one file per CK2 tier."""
    result = HistoryResult()
    writer = _TitleWriter(config, result)
    per_tier: dict[str, Lines] = {}
    written = 0
    skipped = 0
    for title in sorted(histories):
        history = histories[title]
        tier = title[0]
        out = per_tier.get(tier)
        if out is None:
            out = Lines()
            for line in HEADER:
                out.raw(line)
            out.raw(f"# tier: {tier}_")
            out.raw("")
            per_tier[tier] = out
        if title in config.capital_baronies:
            out.comment(0, f"{title}: county-capital barony, CK3 executes its history on the county; kept commented")
            body = Lines()
            writer.write(history, body)
            out.commented_block(0, body.text().rstrip("\n").split("\n"))
            out.blank()
            skipped += 1
            continue
        if title not in config.live_titles:
            reason = config.dead_titles.get(title, "not a live CK3 title")
            out.comment(0, f"{title}: history kept commented - {reason}")
            body = Lines()
            writer.write(history, body)
            out.commented_block(0, body.text().rstrip("\n").split("\n"))
            out.blank()
            skipped += 1
            continue
        writer.write(history, out)
        out.blank()
        written += 1
    stubs = 0
    for title in sorted(config.live_titles):
        if title in histories:
            continue
        tier = title[0]
        if tier == "b":
            # vanilla baronies have no history; a `holder = 0` stub would set
            # the barony to be destroyed (titlehistory.cpp:325)
            continue
        out = per_tier.get(tier)
        if out is None:
            out = Lines()
            for line in HEADER:
                out.raw(line)
            out.raw(f"# tier: {tier}_")
            out.raw("")
            per_tier[tier] = out
        government = config.government.get(title)
        out.line(0, f"{title} = {{")
        for line in STUB_HISTORY:
            out.raw(f"\t{line}")
        out.line(1, f"{EARLY_DATE} = {{")
        if tier != "c":
            out.line(2, "holder = 0")
        else:
            out.comment(2, "no CK2 history: a county cannot be unheld, the game assigns a holder")
        if government:
            out.line(2, f"government = {government.government}")
        out.line(1, "}")
        out.line(0, "}")
        out.blank()
        stubs += 1

    tier_names = {"e": "empires", "k": "kingdoms", "d": "duchies", "c": "counties", "b": "baronies"}
    for tier, out in per_tier.items():
        name = tier_names.get(tier, tier)
        result.files[f"history/titles/{config.prefix}_{name}.txt"] = out.text()
    result.counts = {
        "titles_with_history": written,
        "history_stubs": stubs,
        "history_commented_out": skipped,
        "files": len(result.files),
    }
    return result
