"""CK2 localisation text codes → CK3 data functions.

A CK2 localisation value carries four kinds of markup, all of which have to be
rewritten before the text can go into a CK3 ``.yml``:

``[Root.Religion.GetHighGodName]``
    a *text code*: a scope chain plus a terminal function. CK3 spells the same
    thing ``[ROOT.Char.GetFaith.HighGodName]``.
``§Y … §!``
    a colour code. CK3 uses named text formats, ``#M … #!``.
``$VALUE|R$``
    a variable. CK3 uses the same syntax, so these pass through.
``£gold£``
    an icon. CK3 uses ``@gold_icon!``; Faerûn only uses the numeric CK2 dice
    icons, which have no CK3 equivalent.

Anything without a CK3 equivalent is wrapped in a visible marker
``<!CK2:…!>`` rather than dropped or invented, and counted so the run log can
say how much text is affected — the converter never guesses (`docs/PROJECT.md`).

Where the tables come from
--------------------------
* frequencies: ``docs/evidence/ck2_loc_codes.csv``, built by
  ``scripts/collect_ck2_loc_codes.py`` over the Faerûn CSVs;
* the CK3 side: real usage in ``game/localization/english`` and the
  data-function names embedded in ``ck3-tiger`` v1.19.0. Every entry's evidence
  is listed in ``docs/loc_codes.md``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

#: Marker wrapped around anything that has no CK3 equivalent. Deliberately
#: visible in game: a silent drop hides a broken string, and CK3 would parse a
#: leftover ``[...]`` as a data function.
MARKER = "<!CK2:{}!>"

# --------------------------------------------------------------------------
# Scopes
# --------------------------------------------------------------------------

#: CK2 root scope word → CK3 loc scope. `verified` in CK3 1.19
#: ``localization/english``: ``[ROOT.Char.GetSheHe]``
#: (``traits_l_english.yml``), ``[THIS.Char.GetCulture.GetName]``,
#: ``[PREV.Char…]``.
ROOT_SCOPES: dict[str, str] = {
    "Root": "ROOT.Char",
    "This": "THIS.Char",
    "Prev": "PREV.Char",
    # `verified`: [MyRealmWindow.GetCharacter.GetPlayerHeir…], my_realm_window
    "Player": "GetPlayer",
}

#: CK2 ``From`` chains. CK3 localisation has **no** ``FROM`` scope (0 uses in
#: 1.19 ``localization/english``), so the converter uses a saved scope with a
#: fixed name; the event port has to ``save_scope_as`` it. See
#: ``docs/loc_codes.md`` §From and ``docs/DECISIONS.md``.
FROM_SCOPES: dict[str, str] = {
    "From": "ck2_from",
    "FromFrom": "ck2_fromfrom",
    "FromFromFrom": "ck2_fromfromfrom",
    "FromFromFromFrom": "ck2_fromfromfromfrom",
    "PrevPrev": "ck2_prevprev",
    "PrevPrevPrev": "ck2_prevprevprev",
}

#: A step inside a scope chain: CK2 property → CK3 getter. `verified` against
#: ``ck3-tiger`` v1.19.0's data-function list unless marked ``assumed``.
PATH_SCOPES: dict[str, str] = {
    "Capital": "GetCapitalLocation",   # [recipient.GetCapitalLocation.…]
    "Culture": "GetCulture",           # [actor.GetCulture.GetName]
    "Dynasty": "GetDynasty",
    "Father": "GetFather",
    "Holder": "GetHolder",
    "House": "GetHouse",
    "Liege": "GetLiege",               # [ROOT.Char.GetLiege.…]
    "Location": "GetLocation",
    "Mother": "GetMother",
    "Owner": "GetHolder",              # assumed: CK2 title owner = CK3 holder
    "PrimaryTitle": "GetPrimaryTitle",  # [actor.GetPrimaryTitle.GetName]
    "Religion": "GetFaith",            # [actor.GetFaith.GetName]
    "Spouse": "GetPrimarySpouse",      # [Character.…GetPrimarySpouse.…]
    "TopLiege": "GetTopLiege",
    "TrueReligion": "GetFaith",        # assumed: CK3 has one faith per char
    # [old_faith.GetReligiousHead.GetTitledFirstName], major_decisions_*
    "RelHead": "GetFaith.GetReligiousHead",
}

#: CK2 chain steps that CK3 dropped with the mechanic behind them. Anything
#: routed through one of these is marked, never guessed.
DEAD_PATH_SCOPES: dict[str, str] = {
    "Offmap": "offmap powers do not exist in CK3",
    "Society": "societies do not exist in CK3",
    "PlotTarget": "plots do not exist in CK3",
    "Plot": "plots do not exist in CK3",
    "Founder": "no CK3 society/bloodline founder scope",
    "Ruler": "offmap ruler; no CK3 equivalent",
    "Province": "CK2 province scope has no CK3 loc equivalent",
    "Job_chancellor": "CK2 council jobs are CK3 court positions",
    "Job_marshal": "CK2 council jobs are CK3 court positions",
    "Job_treasurer": "CK2 council jobs are CK3 court positions",
    "Job_spiritual": "CK2 council jobs are CK3 court positions",
    "Job_spymaster": "CK2 council jobs are CK3 court positions",
    "Governor": "offmap governor; no CK3 equivalent",
    "Guardian": "no CK3 guardian scope in localisation",
    "Regent": "no CK3 regent data function",
    "Host": "no CK3 host data function on a character",
    "Heir": "CK3 GetHeir is title-scoped, CK2 Heir is character-scoped",
    "OriginalOwner": "CK3 keeps no previous holder of a title",
    "province_saint": "CK2 province saints do not exist in CK3",
    "TrueHeir": "no CK3 equivalent",
}
# Faerûn writes the council jobs lower case (`Root.job_spiritual`), CK2
# vanilla upper case; accept both.
DEAD_PATH_SCOPES.update(
    {name.lower(): reason for name, reason in list(DEAD_PATH_SCOPES.items())}
)

# --------------------------------------------------------------------------
# Functions
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Function:
    """One CK2 terminal function and its CK3 form.

    ``ck3`` is the replacement (``""`` means "no CK3 equivalent"), ``prefix``
    a chain step CK3 needs that CK2 folded into the function name (CK2
    ``Root.Religion.GetHighGodName`` is CK3
    ``ROOT.Char.GetFaith.HighGodName``), ``cap`` appends CK3's ``|U``
    capitalisation suffix, ``note`` is the evidence or the caveat.
    """

    ck3: str
    prefix: str = ""
    cap: bool = False
    note: str = ""


def _cap(name: str, base: Function) -> Function:
    return Function(base.ck3, base.prefix, True, base.note)


#: CK2 function → CK3 function. Built from ``docs/evidence/ck2_loc_codes.csv``
#: in descending frequency; every ``Xxx``/``XxxCap`` pair is generated below.
FUNCTIONS: dict[str, Function] = {
    # names
    "GetFirstName": Function("GetFirstName"),
    "GetName": Function("GetName"),
    "GetFullName": Function("GetName", note="CK3 GetName is the full name"),
    "GetShortName": Function("GetShortUIName"),
    "GetTitledFirstName": Function("GetTitledFirstName"),
    "GetTitledFirstNameNoRegnal": Function(
        "GetTitledFirstName", note="assumed: CK3 has no no-regnal variant"
    ),
    "GetTitledName": Function(
        "GetTitledFirstName", note="assumed: CK3 has no title+full-name form"
    ),
    "GetTitledNameWithNick": Function("GetShortUIName", note="assumed"),
    "GetBestName": Function("GetTitledFirstName", note="assumed"),
    "GetFirstNameWithNick": Function("GetFirstName", note="CK3 folds the nickname in"),
    "GetNameWithNick": Function("GetName", note="CK3 folds the nickname in"),
    "GetNickname": Function("GetNickname"),
    "GetBaseName": Function("GetBaseName"),
    "GetFullBaseName": Function("GetBaseName", note="assumed"),
    # [SubjectContract.GetLiege.GetHouse.GetBaseNameNoTooltip],
    # government_l_english.yml — a CK2 dynasty is a CK3 house in practice.
    "GetDynName": Function("GetBaseName", prefix="GetHouse"),
    "GetOnlyDynastyName": Function("GetBaseName", prefix="GetHouse"),
    "GetLastWordInDynastyName": Function(
        "GetBaseName", prefix="GetHouse", note="assumed: CK3 has no last-word form"
    ),
    "GetHouseName": Function("GetBaseName", prefix="GetHouse"),
    # titles and tiers
    "GetTitle": Function("GetTitleAsName", note="CK2 GetTitle is the ruler title"),
    "GetRulerTitle": Function("GetTitleAsName", note="assumed"),
    "GetTier": Function("GetTier"),
    "GetAdjective": Function("GetAdjective"),
    "GetRealmName": Function("GetName", prefix="GetPrimaryTitle", note="assumed"),
    # pronouns and gendered words
    "GetSheHe": Function("GetSheHe"),
    "GetHerHis": Function("GetHerHis"),
    "GetHerHim": Function("GetHerHim"),
    "GetHerselfHimself": Function("GetHerselfHimself"),
    "GetWomanMan": Function("GetWomanMan"),
    "GetManWoman": Function("GetWomanMan", note="CK3 only ships the female-first form"),
    "GetManWomanOpp": Function("GetWomanMan", note="assumed"),
    "GetMenWomen": Function("GetWomenMen", note="assumed: CK3 female-first plural"),
    "GetLadyLord": Function("GetLadyLord"),
    "GetLordLady": Function("GetLadyLord", note="CK3 only ships the female-first form"),
    "GetHusbandWife": Function("GetWifeHusband", note="CK3 female-first form"),
    "GetWifeHusband": Function("GetWifeHusband"),
    # CK2 ships both orders of every gendered built-in; CK3 only the
    # female-first one.
    "GetHeShe": Function("GetSheHe"),
    "GetHisHer": Function("GetHerHis"),
    "GetHimHer": Function("GetHerHim"),
    "GetHimselfHerself": Function("GetHerselfHimself"),
    "GetBrotherSister": Function("Custom('SisterBrother')"),
    "GetHusbandWifeOpp": Function("GetWifeHusband", note="assumed"),
    "GetSubjectPronoun": Function("GetSheHe", note="assumed: CK2 subject pronoun"),
    "GetObjectPronoun": Function("GetHerHim", note="assumed: CK2 object pronoun"),
    "GetPossPronoun": Function("GetHerHis", note="assumed: CK2 possessive pronoun"),
    "GetReflexivePronoun": Function("GetHerselfHimself", note="assumed"),
    # faith and culture
    "GetHighGodName": Function("HighGodName", prefix="GetFaith"),
    "GetFaithName": Function("GetName", prefix="GetFaith"),
    # [actor.GetReligion.GetName], interactions_l_english.yml — CK2's religion
    # group is CK3's religion, CK2's religion is CK3's faith.
    "GetGroupName": Function("GetName", prefix="GetReligion"),
    # [ROOT.Char.GetFaith.PriestNeuterPlural], major_decisions_south_asia
    "GetPriestTitle": Function("PriestNeuter", prefix="GetFaith"),
    # [CHARACTER.GetFaith.ReligiousText], relationship_reasons_l_english.yml
    "GetScriptureName": Function("ReligiousText", prefix="GetFaith"),
    # [ROOT.Char.GetFaith.HouseOfWorshipPlural|U], government_l_english.yml
    "GetHouseOfWorship": Function("HouseOfWorship", prefix="GetFaith"),
    "GetCollectiveNoun": Function("GetCollectiveNoun", prefix="GetCulture"),
    # Relatives. CK3 ships the gendered words as vanilla customizable
    # localisations, so the port is a Custom() call (`verified`:
    # game/common/customizable_localization defines SisterBrother,
    # DaughterSon, MotherFather; [confusion_target.Custom('SisterBrother')]
    # in elder_events_l_english.yml).
    "GetSonDaughter": Function("Custom('DaughterSon')", note="CK3 order is daughter/son"),
    "GetDaughterSon": Function("Custom('DaughterSon')"),
    "GetSisterBrother": Function("Custom('SisterBrother')"),
    "GetFatherMother": Function("Custom('MotherFather')", note="CK3 order is mother/father"),
    "GetMotherFather": Function("Custom('MotherFather')"),
    "GetBoyGirl": Function("", note="no CK3 gendered child word"),
    "GetMasterMistress": Function("Custom('MistressMaster')", note="CK3 order is mistress/master"),
    "GetMistressMaster": Function("Custom('MistressMaster')"),
    "GetEmperorEmpress": Function("", note="no CK3 gendered emperor word"),
    # CK3 vanilla customizable localizations (game/common/customizable_
    # localization): QueenKing, MistressMaster, LassLad.
    "GetKingQueen": Function("Custom('QueenKing')", note="CK3 order is queen/king"),
    "GetQueenKing": Function("Custom('QueenKing')"),
    "GetLadLass": Function("Custom('LassLad')", note="CK3 order is lass/lad"),
    "GetLassLad": Function("Custom('LassLad')"),
    "GetPrincessPrince": Function("", note="no CK3 gendered prince word"),
    # mechanics CK3 does not have
    "GetSocietyRank": Function("", note="societies do not exist in CK3"),
    "GetJobTitle": Function("", note="CK2 council jobs are CK3 court positions"),
    "GetPlot": Function("", note="plots do not exist in CK3"),
    # [X.GetFaith.EvilGodName] / [X.GetFaith.HighGodName] are `verified` in
    # CK3 1.19 english loc. CK2's random pick out of a pantheon has no CK3
    # equivalent, so the high god stands in for it — lossy, see
    # docs/loc_codes.md.
    "GetRandomGodName": Function(
        "HighGodName", prefix="GetFaith", note="lossy: CK2 picked a random god"
    ),
    "GetRandomEvilGodName": Function("EvilGodName", prefix="GetFaith"),
    "GetPatronHighGodName": Function("", note="no CK3 patron-deity scope"),
}

# CK2 spells capitalisation with a ``Cap`` suffix, CK3 with ``|U``
# (`verified`: ``[ROOT.Char.GetSheHe|U]``, ``traits_l_english.yml``).
for _name, _fn in list(FUNCTIONS.items()):
    FUNCTIONS.setdefault(_name + "Cap", _cap(_name, _fn))

#: CK2 built-ins that only exist to inflect French, German or Spanish
#: (elision, articles, gendered endings). CK3 has no equivalent: its
#: translations carry the inflection in the string. Matched by prefix as well,
#: because the family is large and regular (``Get_le_TitledFirstName``,
#: ``Get_du_Realm``, …).
LANGUAGE_HELPER_PREFIXES: tuple[str, ...] = ("Get_",)
LANGUAGE_HELPERS: frozenset[str] = frozenset(
    {
        "Get_E",
        "GetOA",
        "GetOnA",
        "GetXA",
        "GetXSe",
        "GetNoneE",
        "GetIlElle",
        "GetIlElleCap",
        "GetLeLa",
        "GetLoLa",
        "GetElLa",
        "GetElElla",
        "GetLuiElle",
        "GetRleRla",
        "Getderdie",
        "GetDerDie",
        "Geteineine",
        "Getihnsie",
        "Getihmihr",
        "GetErEre",
        "GetrMale",
        "GetnMale",
        "GetinFemale",
        "GetMOCode",
    }
)

#: A scope word we recognise (so anything else is a CK2 event target name).
KNOWN_SCOPE_WORDS: frozenset[str] = frozenset(
    set(ROOT_SCOPES) | set(FROM_SCOPES) | set(PATH_SCOPES) | set(DEAD_PATH_SCOPES)
)

# --------------------------------------------------------------------------
# Colours and icons
# --------------------------------------------------------------------------

#: CK2 ``§X`` colour code → CK3 text format. CK3 names are `verified` in
#: ``game/gui/preload/textformatting.gui`` (1.19): ``M`` = ``mixed_value`` =
#: ``color_yellow``, ``N`` = ``negative_value`` = ``color_red``, ``P`` =
#: ``positive_value`` = ``color_green``, ``V`` = ``value`` = ``color_white``,
#: ``E`` = ``explanation_link`` = ``color_light_blue``, ``low`` =
#: ``color_dark_gray``, ``L`` = ``game_link`` = underline.
COLOURS: dict[str, str] = {
    "Y": "M",
    "R": "N",
    "G": "P",
    "W": "V",
    "B": "E",
    "Z": "low",
    "M": "G",
    "L": "L",
    "l": "L",
    "T": "T",
    "P": "P",
    "N": "N",
    "b": "E",
    "g": "P",
    "c": "E",
    "d": "low",
    "u": "UND",
    "U": "UND",
    "h": "high",
    "r": "N",
}
#: End-of-format marker: CK2 ``§!`` → CK3 ``#!``.
COLOUR_END = "#!"

CODE_RE = re.compile(r"\[([^\[\]\n;]{1,120})\]")
COLOUR_RE = re.compile("§(.)")
ICON_RE = re.compile("£([A-Za-z0-9_]*)£?")

# --------------------------------------------------------------------------
# Conversion
# --------------------------------------------------------------------------

#: Every status :func:`convert_code` can return. The first four count as
#: converted; ``language_helper`` and ``unmapped`` produce a marker.
STATUSES: tuple[str, ...] = (
    "mapped",
    "custom",
    "custom_unverified",
    "named_scope",
    "language_helper",
    "unmapped",
)

#: How to treat a ``[X.GetSomething]`` whose function is neither a CK2 engine
#: built-in nor defined by the mod. In CK2 such a name **is** a customizable
#: localisation (vanilla CK2 defines ~200 of them and this machine has no CK2
#: install to read), so ``"custom"`` emits the CK3 spelling of the same call
#: and warns; ``"marker"`` leaves a visible ``<!CK2:…!>`` instead.
UNKNOWN_POLICIES: tuple[str, ...] = ("custom", "marker")

#: What to do with a CK2 code that names a **defined** CK2 customizable
#: localisation. ``call`` emits the CK3 spelling of the same feature,
#: ``Custom('name')``; ``marker`` leaves the visible ``<!CK2:...!>`` instead.
#:
#: ``marker`` is the default because nothing ports
#: ``localisation/customizable_localisation`` yet, and a ``Custom()`` call to a
#: name CK3 does not know is not inert: `verified` 2026-09-08, 795 distinct
#: names in 4068 generated lines produced
#: ``jomini_custom_text.h:94: Object of type 'character' is not valid for
#: 'VampName'`` (`docs/evidence/game_load_2026-09-08.md`). Switch to ``call``
#: in the same commit that emits ``common/customizable_localization``.
CUSTOM_LOC_POLICIES: tuple[str, ...] = ("marker", "call")

#: What to do with a code whose first chain step is a **CK2 saved scope**
#: (``[christian.GetReligion.GetName]``, ``[saint_person.GetTitledFirstName]``).
#: CK3 references saved scopes the same way, so ``reference`` emits the chain
#: unchanged — but only an event, decision or on_action that ran
#: ``save_scope_as = christian`` puts the scope there, and nothing ports CK2's
#: events yet. CK3 answers an unresolvable one with
#: ``pdx_data_factory.cpp: Failed to find type 'christian' in
#: 'christian.GetReligion.GetName'`` and ``pdx_data_localize.cpp: Data error in
#: loc string '<key>'`` (`verified` 2026-09-08). ``marker`` leaves the visible
#: ``<!CK2:...!>`` until the event port ships.
NAMED_SCOPE_POLICIES: tuple[str, ...] = ("marker", "reference")

#: The chain heads the converter emits for a scope it resolved itself. Anything
#: else at the head of a generated chain is a saved scope.
CK3_CHAIN_HEADS: frozenset[str] = frozenset(
    {v.split(".")[0] for v in ROOT_SCOPES.values()}
)

#: The CK3 **vanilla** customizable localisations the mapping table above
#: targets. These resolve with no port of our own: `verified` 2026-09-08, all
#: six are declared in `game/common/customizable_localization/`
#: (`00_generic_character_words.txt`, `00_relations.txt`). Any other name in a
#: generated ``Custom('...')`` call is a name CK3 does not know, and every
#: evaluation of it is a ``jomini_custom_text.h`` error.
CK3_VANILLA_CUSTOM_LOC: frozenset[str] = frozenset(
    {
        "DaughterSon",
        "SisterBrother",
        "MotherFather",
        "MistressMaster",
        "QueenKing",
        "LassLad",
    }
)


@dataclass(frozen=True)
class CodeResult:
    """What one ``[...]`` code became."""

    text: str
    status: str
    scope_chain: str = ""
    function: str = ""
    note: str = ""

    @property
    def converted(self) -> bool:
        return self.status in ("mapped", "custom", "custom_unverified", "named_scope")


@dataclass
class Report:
    """Counts and per-code warnings for a whole conversion run."""

    statuses: dict[str, int] = field(default_factory=dict)
    #: ``code → occurrences`` for everything that did not convert.
    unconverted: dict[str, int] = field(default_factory=dict)
    #: ``code → occurrences`` for a converted code that needs a saved scope.
    needs_scope: dict[str, int] = field(default_factory=dict)
    #: ``code → occurrences`` for a ``Custom()`` call nothing defines yet.
    needs_custom_loc: dict[str, int] = field(default_factory=dict)
    #: ``code → occurrences`` for a CK2 customizable localisation that became a
    #: marker because ``[loc] custom_loc = "marker"``. Counted separately from
    #: :attr:`unconverted`: the *code* is mapped (CK3 has the same feature,
    #: spelled ``Custom('name')``), only the target folder is missing, so this
    #: is the size of the custom-loc port, not a coverage gap.
    custom_loc_markered: dict[str, int] = field(default_factory=dict)
    #: ``code → occurrences`` for a CK2 saved-scope reference that became a
    #: marker because ``[loc] named_scope = "marker"``. Same reasoning: the
    #: *code* is mapped, only the `save_scope_as` is missing.
    named_scope_markered: dict[str, int] = field(default_factory=dict)
    colours: dict[str, int] = field(default_factory=dict)
    icons: int = 0
    #: Square brackets the CK2 text left unbalanced (36 rows in Faerûn).
    stray_brackets: int = 0
    #: ``§`` with nothing usable after it (28 rows in Faerûn).
    stray_colour_marks: int = 0

    def add(self, result: CodeResult, code: str) -> None:
        self.statuses[result.status] = self.statuses.get(result.status, 0) + 1
        if result.status == "custom_unverified":
            self.needs_custom_loc[code] = self.needs_custom_loc.get(code, 0) + 1
        if result.status == "custom" and result.text.startswith("<!CK2:"):
            self.custom_loc_markered[code] = (
                self.custom_loc_markered.get(code, 0) + 1
            )
        if (
            result.status in ("named_scope", "mapped")
            and result.text.startswith("<!CK2:")
            and "saved scope" in result.note
        ):
            self.named_scope_markered[code] = (
                self.named_scope_markered.get(code, 0) + 1
            )
        if not result.converted:
            self.unconverted[code] = self.unconverted.get(code, 0) + 1
        elif result.status == "mapped" and "saved scope" in result.note:
            self.needs_scope[code] = self.needs_scope.get(code, 0) + 1

    @property
    def total(self) -> int:
        return sum(self.statuses.values())

    @property
    def converted(self) -> int:
        return sum(
            self.statuses.get(s, 0)
            for s in ("mapped", "custom", "custom_unverified", "named_scope")
        )

    def coverage(self) -> float:
        return self.converted / self.total if self.total else 1.0


def is_language_helper(function: str) -> bool:
    """True for a CK2 French/German/Spanish inflection built-in."""
    if function in LANGUAGE_HELPERS:
        return True
    return any(function.startswith(p) for p in LANGUAGE_HELPER_PREFIXES)


def convert_code(
    code: str,
    *,
    custom_loc: frozenset[str] | set[str] = frozenset(),
    unknown: str = "custom",
    custom_loc_policy: str = "marker",
    named_scope_policy: str = "marker",
) -> CodeResult:
    """Convert one CK2 text code, brackets included, to its CK3 form.

    ``custom_loc`` is the set of names defined in the mod's
    ``localisation/customizable_localisation``; a function found there becomes
    a CK3 ``Custom('name')`` call, which is the CK3 spelling of the same
    feature (`verified`: ``[lover.Custom('PurrGrowl')]``,
    ``elder_events_l_english.yml``).
    """
    inner = code[1:-1] if code.startswith("[") and code.endswith("]") else code
    inner = inner.strip()
    suffix = ""
    if "|" in inner:
        inner, _, suffix = inner.partition("|")
        suffix = "|" + suffix
    tokens = [t for t in inner.split(".") if t]
    if not tokens:
        return CodeResult(MARKER.format(inner), "unmapped", note="empty code")
    function = tokens[-1]
    scope_tokens = tokens[:-1]

    # -- the scope chain ---------------------------------------------------
    chain: list[str] = []
    note = ""
    if not scope_tokens:
        # A bare [GetFirstName] is CK2's Root (`assumed`, matches CK2 docs).
        chain.append(ROOT_SCOPES["Root"])
    else:
        head = scope_tokens[0]
        if head in ROOT_SCOPES:
            chain.append(ROOT_SCOPES[head])
        elif head in FROM_SCOPES:
            chain.append(FROM_SCOPES[head])
            note = (
                f"CK2 {head} has no CK3 loc scope; needs a saved scope "
                f"'{FROM_SCOPES[head]}' in the converted event"
            )
        elif head in DEAD_PATH_SCOPES:
            return CodeResult(
                MARKER.format(inner + suffix),
                "unmapped",
                head,
                function,
                DEAD_PATH_SCOPES[head],
            )
        else:
            # An event target saved in CK2 script; CK3 references saved
            # scopes the same way (`verified`: [lover.GetHerHis]).
            chain.append(head)
            note = f"CK2 event target '{head}' kept as a CK3 saved scope"
        for token in scope_tokens[1:]:
            if token in PATH_SCOPES:
                chain.append(PATH_SCOPES[token])
            elif token in DEAD_PATH_SCOPES:
                return CodeResult(
                    MARKER.format(inner + suffix),
                    "unmapped",
                    ".".join(scope_tokens),
                    function,
                    DEAD_PATH_SCOPES[token],
                )
            else:
                return CodeResult(
                    MARKER.format(inner + suffix),
                    "unmapped",
                    ".".join(scope_tokens),
                    function,
                    f"unknown CK2 chain step '{token}'",
                )

    scope_chain = ".".join(scope_tokens)
    status = "named_scope" if scope_tokens and scope_tokens[0] not in KNOWN_SCOPE_WORDS else "mapped"

    # -- the terminal function --------------------------------------------
    if function in custom_loc:
        if custom_loc_policy == "call":
            chain.append(f"Custom('{function}')")
            return CodeResult(
                f"[{'.'.join(chain)}{suffix}]",
                "custom",
                scope_chain,
                function,
                note or "CK2 customizable localisation; needs the custom-loc port",
            )
        return CodeResult(
            MARKER.format(inner + suffix),
            "custom",
            scope_chain,
            function,
            note
            or "CK2 customizable localisation, and nothing emits "
            "common/customizable_localization: a Custom() call to a name CK3 "
            "does not know is an error, not a blank",
        )
    if is_language_helper(function):
        return CodeResult(
            MARKER.format(inner + suffix),
            "language_helper",
            scope_chain,
            function,
            "CK2 French/German/Spanish inflection built-in; CK3 has none",
        )
    entry = FUNCTIONS.get(function)
    if entry is None:
        # Not a CK2 engine built-in: in CK2 that means a customizable
        # localisation, which CK3 spells Custom('name').
        if (
            unknown == "custom"
            and custom_loc_policy == "call"
            and function.startswith("Get")
        ):
            chain.append(f"Custom('{function}')")
            return CodeResult(
                f"[{'.'.join(chain)}{suffix}]",
                "custom_unverified",
                scope_chain,
                function,
                f"needs a CK3 customizable localization named '{function}'",
            )
        return CodeResult(
            MARKER.format(inner + suffix),
            "unmapped",
            scope_chain,
            function,
            f"no CK3 equivalent known for '{function}'",
        )
    if not entry.ck3:
        return CodeResult(
            MARKER.format(inner + suffix),
            "unmapped",
            scope_chain,
            function,
            entry.note,
        )
    # Everything the converter can resolve on its own starts the chain with a
    # CK3 scope word it chose itself (`ROOT.Char`, `PREV.Char`, `GetPlayer`).
    # Any other head is a **saved scope**: a CK2 event target (`relic_hunter`),
    # the `ck2_from` a `From` code needs, or a CK2 chain word used as a head
    # (`[Culture.GetName]`). All three need a `save_scope_as` that nothing runs
    # yet, so all three take the same policy.
    if (
        named_scope_policy == "marker"
        and chain
        and chain[0].split(".")[0] not in CK3_CHAIN_HEADS
    ):
        return CodeResult(
            MARKER.format(inner + suffix),
            status,
            scope_chain,
            function,
            "; ".join(
                x
                for x in (
                    note,
                    entry.note,
                    f"CK2 saved scope {chain[0]!r}, and nothing saves it yet: "
                    "an unresolvable scope reference is a data error in the loc "
                    "string, not a blank",
                )
                if x
            ),
        )
    if entry.prefix and (not chain or chain[-1] != entry.prefix):
        chain.append(entry.prefix)
    chain.append(entry.ck3)
    if entry.cap and "|" not in suffix:
        suffix = "|U"
    return CodeResult(
        f"[{'.'.join(chain)}{suffix}]",
        status,
        scope_chain,
        function,
        "; ".join(x for x in (note, entry.note) if x),
    )


def convert_colours(text: str, report: Report | None = None) -> str:
    """Rewrite ``§X … §!`` colour codes as CK3 ``#fmt … #!``."""

    def replace(match: re.Match[str]) -> str:
        letter = match.group(1)
        if report is not None:
            report.colours["§" + letter] = report.colours.get("§" + letter, 0) + 1
        if letter == "!":
            return COLOUR_END
        fmt = COLOURS.get(letter)
        if fmt is None:
            # A stray § (Faerûn has 28 of them, see docs/formats_loc.md):
            # dropping it is the only safe move, CK3 would render it raw.
            return ""
        return f"#{fmt} "

    return COLOUR_RE.sub(replace, text)


def convert_icons(text: str, report: Report | None = None) -> str:
    """Mark CK2 ``£icon£`` codes: CK3 has no equivalent for Faerûn's."""

    def replace(match: re.Match[str]) -> str:
        if report is not None:
            report.icons += 1
        return MARKER.format("icon_" + (match.group(1) or "?"))

    return ICON_RE.sub(replace, text)


def convert_text(
    text: str,
    *,
    custom_loc: frozenset[str] | set[str] = frozenset(),
    unknown: str = "custom",
    custom_loc_policy: str = "marker",
    named_scope_policy: str = "marker",
    report: Report | None = None,
) -> str:
    """Convert one localisation value: codes, colours and icons.

    ``$VAR$`` and ``$VAR|fmt$`` are left alone: CK3 uses the same syntax
    (`verified`: ``$RANSOM_COST|0$``, ``interactions_l_english.yml``).
    """

    out: list[str] = []
    cursor = 0
    for match in CODE_RE.finditer(text):
        out.append(_drop_stray_brackets(text[cursor : match.start()], report))
        result = convert_code(
            match.group(0),
            custom_loc=custom_loc,
            unknown=unknown,
            custom_loc_policy=custom_loc_policy,
            named_scope_policy=named_scope_policy,
        )
        if report is not None:
            report.add(result, match.group(0))
        out.append(result.text)
        cursor = match.end()
    out.append(_drop_stray_brackets(text[cursor:], report))
    converted = convert_colours("".join(out), report)
    # A ``§`` at the very end of a CK2 value has no letter to consume.
    if "§" in converted:
        if report is not None:
            report.stray_colour_marks += converted.count("§")
        converted = converted.replace("§", "")
    return convert_icons(converted, report)


def _drop_stray_brackets(chunk: str, report: Report | None) -> str:
    """Remove a ``[`` or ``]`` that is not part of a well-formed code.

    Faerûn has 36 rows with unbalanced brackets (``docs/formats_loc.md``); CK3
    would try to parse the leftover as a data function and print an error in
    its place, so the bracket goes and the words stay.
    """
    if "[" not in chunk and "]" not in chunk:
        return chunk
    if report is not None:
        report.stray_brackets += chunk.count("[") + chunk.count("]")
    return chunk.replace("[", "").replace("]", "")


#: ``name = X`` inside a CK2 ``customizable_localisation`` block.
CUSTOM_LOC_NAME_RE = re.compile(
    r'^[ \t]*name[ \t]*=[ \t]*"?([A-Za-z0-9_]+)"?', re.MULTILINE
)


def custom_loc_names(mod_dir) -> frozenset[str]:
    """Every ``customizable_localisation`` name defined by a CK2 mod.

    Faerûn defines 450 of them under
    ``localisation/customizable_localisation/*.txt`` (`verified` 2026-09-07);
    each becomes a CK3 ``Custom('name')`` call.
    """
    from pathlib import Path

    from .pdx.encoding import read_text

    folder = Path(mod_dir) / "localisation" / "customizable_localisation"
    names: set[str] = set()
    if not folder.is_dir():
        return frozenset()
    for path in sorted(folder.glob("*.txt")):
        text, _ = read_text(path, "auto")
        names.update(CUSTOM_LOC_NAME_RE.findall(text))
    return frozenset(names)
