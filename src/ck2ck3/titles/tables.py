"""The three CK2 -> CK3 tables this lane has to *derive*, not copy.

CK2 and CK3 disagree about where three facts live, so none of them is a plain
key rename:

**holding type** — CK2 writes ``b_x = castle`` in province history, CK3 writes
``holding = castle_holding`` on the province that *is* the barony.  A flat
value map (:data:`HOLDING_MAP`); the two Faerun-invented types have no CK3
holding and fall back to ``city_holding`` with a comment.

**government** — CK2 stores no government anywhere on a character
(`verified`: 0 of 80 ``history/characters`` files mention one) and only 44
times on a title.  It derives the government from the ruler's primary title
plus religion and culture triggers.  CK3 makes the *title* authoritative, so
the converter has to synthesise the line: :func:`derive_government` implements
the table documented in ``docs/step_titles.md``.

**succession laws** — CK2 repeats ``law = x`` lines mixing succession order,
gender and a dozen unrelated law groups (crown authority, council voting
power); CK3 takes one braced ``succession_laws = { }`` list of ids from two
law groups.  :func:`map_succession_laws` splits and maps them, and returns the
CK2 laws it could not place so the caller can emit them as a comment.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

# --------------------------------------------------------------- holdings

#: CK2 holding type -> CK3 ``common/holdings`` id.
#: `verified` CK3 1.19 ``common/holdings/00_holdings.txt``: castle_holding,
#: city_holding, church_holding, tribal_holding, nomad_holding, herder_holding,
#: temple_citadel_holding.  CK2's FORT / HOSPITAL / TRADE_POST / FAMILY_PALACE
#: have no counterpart and are never a *province* holding in Faerun anyway.
HOLDING_MAP: dict[str, str] = {
    "castle": "castle_holding",
    "city": "city_holding",
    "temple": "church_holding",
    "tribal": "tribal_holding",
    # Faerun-invented city-type holdings (20 and 5 uses).  city_holding is the
    # CK2 base type they were cloned from; the flavour is lost.
    "ct_spelljammer_port": "city_holding",
    "ct_planar_portal": "city_holding",
    # CK2 "no holding" spellings.
    "none": "none",
    "0": "none",
}

#: CK2 holding types the converter maps to something else with a note.
HOLDING_NOTES: dict[str, str] = {
    "ct_spelljammer_port": "CK2 ct_spelljammer_port; no CK3 holding type, kept as city_holding",
    "ct_planar_portal": "CK2 ct_planar_portal; no CK3 holding type, kept as city_holding",
}


def map_holding(ck2_holding: str) -> tuple[str | None, str | None]:
    """``(ck3 holding id, note)``; ``(None, note)`` when nothing fits."""
    value = ck2_holding.strip().strip('"')
    ck3 = HOLDING_MAP.get(value)
    return ck3, HOLDING_NOTES.get(value)


# ------------------------------------------------------------- governments


def load_government_map(path: Path) -> dict[str, str]:
    """``mappings/government_map.csv`` -> CK2 government -> CK3 government.

    Rows whose ``ck3_government`` is ``(none - skip)`` (Faerun's disabled
    ``nomadic_government`` stub) and the two rows that describe a *title flag*
    rather than a CK2 government are left out of the value map; the flag rows
    are consumed by :data:`FLAG_GOVERNMENTS` instead.
    """
    out: dict[str, str] = {}
    if not path.exists():
        return out
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            ck2 = row["ck2_government"].strip()
            ck3 = row["ck3_government"].strip()
            if not ck2 or ck2.startswith("("):
                continue
            if not ck3 or ck3.startswith("("):
                continue
            out[ck2] = ck3
    return out


def load_government_laws(path: Path) -> dict[str, str]:
    """CK2 government -> the CK3 succession law ``government_map.csv`` wants."""
    out: dict[str, str] = {}
    if not path.exists():
        return out
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            ck2 = row["ck2_government"].strip()
            law = row["succession_law_to_emit"].strip()
            if ck2 and law and not ck2.startswith("("):
                out[ck2] = law
    return out


#: CK3 government for a CK2 *title flag*, in the order the derivation tests
#: them.  These are the ``government_map.csv`` rows whose ``ck2_government``
#: column is a parenthesised note rather than a CK2 government id, plus the
#: two landed_titles flags that row set covers.
FLAG_GOVERNMENTS: tuple[tuple[str, str, str], ...] = (
    # (CK2 landed_titles key, CK3 government, why)
    ("mercenary", "mercenary_government", "CK2 landed_titles mercenary = yes"),
    ("holy_order", "holy_order_government", "CK2 landed_titles holy_order = yes"),
    (
        "pirate",
        "landless_adventurer_government",
        "CK2 landed_titles pirate = yes; 1.13+ landless adventurer",
    ),
    ("tribe", "tribal_government", "CK2 landed_titles tribe = yes"),
)

#: The government every landed title falls back to.  CK3 needs a government on
#: the title, CK2 has nothing to read for most of them, and feudal is both the
#: CK2 baseline (``feudal_government`` is the widest ``potential``) and the
#: CK3 default that ``government_map.csv`` marks ``exact``.
DEFAULT_GOVERNMENT = "feudal_government"

#: Government for a title CK2 marks as a religious head
#: (``controls_religion`` / ``caliphate``).  CK2 derives theocracy from the
#: religion; the nearest CK3 title-level statement is theocracy_government,
#: whose faith gate the religions lane owns.
RELIGIOUS_HEAD_GOVERNMENT = "theocracy_government"

#: Government of a title declared in CK2 ``common/landed_titles/republics.txt``.
REPUBLIC_GOVERNMENT = "republic_government"


@dataclass(frozen=True)
class GovernmentChoice:
    """What :func:`derive_government` decided and the reason for it."""

    government: str
    reason: str
    derived: bool = True


def derive_government(
    *,
    title_id: str,
    keywords: dict[str, object],
    explicit_ck2: str | None = None,
    is_republic: bool = False,
    government_map: dict[str, str] | None = None,
) -> GovernmentChoice:
    """The CK3 government of one title, first match wins.

    Priority, and why each step is where it is:

    1. an explicit CK2 ``government = x`` in ``history/titles`` (44 uses) —
       the only place CK2 states a government outright, so it wins;
    2. ``mercenary`` / ``holy_order`` / ``pirate`` / ``tribe`` title flags —
       CK2 gates the matching government's ``potential`` on exactly these;
    3. a title declared in ``republics.txt`` — CK2's merchant-republic marker;
    4. ``controls_religion`` / ``caliphate`` — a religious head;
    5. :data:`DEFAULT_GOVERNMENT`.

    Steps 2-4 are the "derivation table" the lane brief asks for: CK2 assigns
    government from the primary title's flags, so the flags are the input.
    """
    government_map = government_map or {}
    if explicit_ck2:
        mapped = government_map.get(explicit_ck2)
        if mapped:
            return GovernmentChoice(
                mapped, f"CK2 history/titles government = {explicit_ck2}", derived=False
            )
        return GovernmentChoice(
            DEFAULT_GOVERNMENT,
            f"CK2 government {explicit_ck2} has no CK3 target in government_map.csv",
        )

    def flag(key: str) -> bool:
        value = keywords.get(key)
        if isinstance(value, bool):
            return value
        if isinstance(value, int):
            return bool(value)
        if isinstance(value, str):
            return value.lower() in ("yes", "true", "1")
        return False

    for key, government, why in FLAG_GOVERNMENTS:
        if flag(key):
            return GovernmentChoice(government, why)
    if is_republic:
        return GovernmentChoice(
            REPUBLIC_GOVERNMENT, "declared in CK2 common/landed_titles/republics.txt"
        )
    if flag("controls_religion") or flag("caliphate"):
        return GovernmentChoice(
            RELIGIOUS_HEAD_GOVERNMENT,
            "CK2 controls_religion / caliphate = yes (religious head)",
        )
    return GovernmentChoice(
        DEFAULT_GOVERNMENT, "no CK2 marker; feudal is the CK2 and CK3 baseline"
    )


# ----------------------------------------------------------- succession laws


@dataclass(frozen=True)
class LawTarget:
    """One row of the CK2 -> CK3 succession-law table."""

    ck3: str
    #: the CK3 law group the id belongs to; CK3 replaces per group, so at most
    #: one law of a group may be emitted for a date.
    group: str
    #: government the CK3 law needs; when the title's government differs the
    #: converter emits :attr:`fallback` instead and comments the CK2 law.
    requires_government: str | None = None
    fallback: str | None = None
    note: str | None = None


ORDER = "succession_order_laws"
GENDER = "succession_gender_laws"
TITLE = "title_succession_laws"

#: CK2 succession-order law -> CK3.  Ids checked against
#: ``common/laws/00_succession_laws.txt`` and
#: ``common/laws/01_title_succession_laws.txt`` (CK3 1.19).
SUCCESSION_LAWS: dict[str, LawTarget] = {
    # --- CK2 base, order ---------------------------------------------------
    "succ_gavelkind": LawTarget("partition_succession_law", ORDER),
    "succ_elective_gavelkind": LawTarget("confederate_partition_succession_law", ORDER),
    "succ_primogeniture": LawTarget("single_heir_succession_law", ORDER),
    "succ_ultimogeniture": LawTarget("single_heir_succession_law_youngest", ORDER),
    "succ_seniority": LawTarget(
        "single_heir_succession_law",
        ORDER,
        note="CK3 has no seniority; oldest dynast becomes oldest child",
    ),
    "succ_eldership": LawTarget(
        "single_heir_succession_law",
        ORDER,
        note="CK3 has no eldership; oldest dynast becomes oldest child",
    ),
    "succ_turkish_succession": LawTarget(
        "confederate_partition_succession_law",
        ORDER,
        note="CK3 has no Turkish succession; confederate partition is the nearest",
    ),
    "succ_nomad_succession": LawTarget("single_heir_succession_kurultai_law", ORDER),
    "succ_appointment": LawTarget("appointment_succession_law", ORDER),
    "succ_open_elective": LawTarget("acclamation_succession_law", ORDER),
    "succ_byzantine_elective": LawTarget("acclamation_succession_law", ORDER),
    "succ_patrician_elective": LawTarget(
        "city_succession_law",
        ORDER,
        note="CK3 has no patrician families; republican succession is the nearest",
    ),
    "succ_catholic_bishopric": LawTarget("bishop_theocratic_succession_law", ORDER),
    "succ_papal_succession": LawTarget("temporal_head_of_faith_succession_law", TITLE),
    # --- CK2 base, title-level elective -----------------------------------
    "succ_feudal_elective": LawTarget("feudal_elective_succession_law", TITLE),
    "succ_hre_elective": LawTarget("princely_elective_succession_law", TITLE),
    "succ_tanistry": LawTarget("gaelic_elective_succession_law", TITLE),
    # --- Faerun-custom ----------------------------------------------------
    "succ_nomadic_elective": LawTarget("single_heir_succession_kurultai_law", ORDER),
    "succ_magic_elective": LawTarget("feudal_elective_succession_law", TITLE),
    "succ_divine_elective": LawTarget("feudal_elective_succession_law", TITLE),
    "succ_popular_elective": LawTarget("feudal_elective_succession_law", TITLE),
    "succ_magic_dynastic": LawTarget("single_heir_succession_law", ORDER),
    "succ_divine_dynastic": LawTarget("single_heir_succession_law", ORDER),
    "succ_ordning": LawTarget(
        "tribal_elective_succession_law",
        TITLE,
        note="the Ordning caste ladder has no CK3 mechanic; tribal elective only",
    ),
    # Order-chosen successions: theocratic in CK3, but bishop_theocratic only
    # makes sense on a theocracy, so a feudal holder gets the elective instead.
    "succ_magic_wizard": LawTarget(
        "bishop_theocratic_succession_law",
        ORDER,
        requires_government="theocracy_government",
        fallback="feudal_elective_succession_law",
    ),
    "succ_magic_warlock": LawTarget(
        "bishop_theocratic_succession_law",
        ORDER,
        requires_government="theocracy_government",
        fallback="feudal_elective_succession_law",
    ),
    "succ_divine_cleric": LawTarget(
        "bishop_theocratic_succession_law",
        ORDER,
        requires_government="theocracy_government",
        fallback="feudal_elective_succession_law",
    ),
    "succ_divine_druid": LawTarget(
        "bishop_theocratic_succession_law",
        ORDER,
        requires_government="theocracy_government",
        fallback="feudal_elective_succession_law",
    ),
    "succ_divine_monk": LawTarget(
        "bishop_theocratic_succession_law",
        ORDER,
        requires_government="theocracy_government",
        fallback="feudal_elective_succession_law",
    ),
    "succ_yikaria": LawTarget(
        "bishop_theocratic_succession_law",
        ORDER,
        requires_government="theocracy_government",
        fallback="feudal_elective_succession_law",
    ),
    "succ_wychlaran": LawTarget(
        "bishop_theocratic_succession_law",
        ORDER,
        requires_government="theocracy_government",
        fallback="feudal_elective_succession_law",
    ),
    "succ_magister": LawTarget(
        "bishop_theocratic_succession_law",
        ORDER,
        requires_government="theocracy_government",
        fallback="feudal_elective_succession_law",
    ),
    "succ_bahamut": LawTarget(
        "bishop_theocratic_succession_law",
        ORDER,
        requires_government="theocracy_government",
        fallback="feudal_elective_succession_law",
    ),
    # --- gender -----------------------------------------------------------
    "agnatic_succession": LawTarget("male_only_law", GENDER),
    "cognatic_succession": LawTarget("male_preference_law", GENDER),
    "true_cognatic_succession": LawTarget("equal_law", GENDER),
    "enatic_cognatic_succession": LawTarget("female_preference_law", GENDER),
    "enatic_succession": LawTarget("female_only_law", GENDER),
}

#: CK2 laws that are not succession laws at all.  They are matched by prefix so
#: the whole ``*_voting_power_<n>`` / ``centralization_<n>`` family is covered
#: without listing every level.  CK3 has no dated equivalent for any of them
#: (crown authority is a realm law set in game, not in history).
NON_SUCCESSION_LAW_PREFIXES: tuple[str, ...] = (
    "banish_voting_power",
    "centralization",
    "execution_voting_power",
    "grant_title_voting_power",
    "imprison_voting_power",
    "law_voting_power",
    "revoke_title_law",
    "revoke_title_voting_power",
    "succession_voting_power",
    "war_voting_power",
    "ze_",
)

#: CK2 succession laws with no CK3 target of any kind.
UNMAPPED_SUCCESSION_LAWS: dict[str, str] = {
    "succ_offmap_succession": "CK2 offmap-power succession; CK3 has no offmap realms",
}


@dataclass
class LawMapping:
    """Result of :func:`map_succession_laws`."""

    #: CK3 law ids to put inside ``succession_laws = { }``, in group order.
    laws: list[str]
    #: ``(ck2 law, reason)`` for every CK2 law that produced no CK3 law.
    dropped: list[tuple[str, str]]
    #: ``(ck2 law, note)`` for laws that mapped but lost meaning.
    notes: list[tuple[str, str]]


_GROUP_ORDER = (ORDER, TITLE, GENDER)


def map_succession_laws(
    ck2_laws: list[str], *, government: str = DEFAULT_GOVERNMENT
) -> LawMapping:
    """Map the ``law = x`` lines of one CK2 dated block to CK3.

    CK3 replaces laws per group, so at most one law per group survives; a
    second CK2 law of the same group is dropped with a reason (CK2 itself
    cannot have two, but a converted file may list an order law twice across a
    repeated date).
    """
    chosen: dict[str, str] = {}
    dropped: list[tuple[str, str]] = []
    notes: list[tuple[str, str]] = []
    for law in ck2_laws:
        if law.startswith(NON_SUCCESSION_LAW_PREFIXES):
            dropped.append((law, "not a succession law; CK3 has no dated equivalent"))
            continue
        if law in UNMAPPED_SUCCESSION_LAWS:
            dropped.append((law, UNMAPPED_SUCCESSION_LAWS[law]))
            continue
        target = SUCCESSION_LAWS.get(law)
        if target is None:
            dropped.append((law, "unknown CK2 law"))
            continue
        ck3 = target.ck3
        if target.requires_government and target.requires_government != government:
            if not target.fallback:
                dropped.append(
                    (law, f"CK3 {ck3} needs {target.requires_government}")
                )
                continue
            notes.append(
                (
                    law,
                    f"{ck3} needs {target.requires_government}, holder is "
                    f"{government}; emitted {target.fallback}",
                )
            )
            ck3 = target.fallback
        group = target.group
        if group in chosen and chosen[group] != ck3:
            dropped.append((law, f"CK3 group {group} already set to {chosen[group]}"))
            continue
        chosen[group] = ck3
        if target.note:
            notes.append((law, target.note))
    laws = [chosen[g] for g in _GROUP_ORDER if g in chosen]
    return LawMapping(laws=laws, dropped=dropped, notes=notes)
