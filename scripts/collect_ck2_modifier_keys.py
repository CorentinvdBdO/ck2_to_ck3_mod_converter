#!/usr/bin/env python3
"""Collect the set of modifier keys used by the Faerun CK2 mod.

Parses `Faerun/Faerun/common/traits/*.txt` and `Faerun/Faerun/common/buildings/*.txt`
with a small Paradox-script tokenizer and writes a key-frequency table to
`docs/evidence/ck2_modifier_keys.csv`.

CK2 script is Windows-1252. Comments start with '#'.

Classification
--------------
A leaf assignment inside a trait block is either
  * a *trait field* (`education = yes`, `birth = 20`, `opposites = { ... }`) -- the
    authoritative list lives in the CK2 install at `common/traits/traits.info`; or
  * a *modifier* (`martial = 2`, `health = 0.5`, `vassal_opinion = 10`).
Inside a building block it is either a *building field* (`gold_cost`, `trigger`,
`upgrades_from`, ...) or a modifier.
Everything that is not a known field is reported as a modifier candidate.

Usage:
    python3 scripts/collect_ck2_modifier_keys.py [--faerun DIR] [--out CSV]
"""

from __future__ import annotations

import argparse
import csv
import re
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def default_faerun() -> Path:
    """Faerun clone lives in the main checkout; a git worktree sees it as a sibling."""
    for cand in (
        REPO / "Faerun" / "Faerun",
        REPO.parent / "ck2_to_ck3_mod_converter" / "Faerun" / "Faerun",
        REPO.parent.parent / "ck2_to_ck3_mod_converter" / "Faerun" / "Faerun",
    ):
        if (cand / "common" / "traits").is_dir():
            return cand
    return REPO / "Faerun" / "Faerun"

# --------------------------------------------------------------------------- #
# tokenizer
# --------------------------------------------------------------------------- #

TOKEN_RE = re.compile(
    r'"[^"\n]*"'          # quoted string
    r"|[{}=]"             # structural
    r"|[^\s{}=#]+"        # bare word / number
)


def strip_comments(text: str) -> str:
    out = []
    for line in text.splitlines():
        # no '#' inside quotes anywhere in CK2 trait/building files
        hash_at = line.find("#")
        if hash_at >= 0:
            line = line[:hash_at]
        out.append(line)
    return "\n".join(out)


def tokenize(text: str) -> list[str]:
    return TOKEN_RE.findall(strip_comments(text))


def walk(tokens: list[str]) -> list[tuple[tuple[str, ...], str, str | None]]:
    """Return (path, key, value) for every assignment.

    `path` is the tuple of enclosing block keys. A block-valued assignment
    (`key = { ... }`) is returned with value None and its body is recursed into.
    Bare list items (`opposites = { a b c }`) are not returned.
    """
    n = len(tokens)
    out: list[tuple[tuple[str, ...], str, str | None]] = []
    path: list[str] = []

    def block(i: int) -> int:
        while i < n:
            tok = tokens[i]
            if tok == "}":
                return i + 1
            if tok in ("{", "="):  # stray token, skip
                i += 1
                continue
            if i + 1 < n and tokens[i + 1] == "=":
                key = tok
                if i + 2 < n and tokens[i + 2] == "{":
                    out.append((tuple(path), key, None))
                    path.append(key)
                    i = block(i + 3)
                    path.pop()
                else:
                    out.append((tuple(path), key, tokens[i + 2] if i + 2 < n else ""))
                    i += 3
            else:
                i += 1  # bare list element
        return i

    block(0)
    return out


def parse_leaves(text: str) -> list[tuple[tuple[str, ...], str, str | None]]:
    return walk(tokenize(text))


# --------------------------------------------------------------------------- #
# known non-modifier keys
# --------------------------------------------------------------------------- #

# From the CK2 install: common/traits/traits.info (the "variables" list) plus the
# keys vanilla actually uses that the .info omits.
TRAIT_FIELDS = {
    "is_visible", "trigger", "hidden", "hidden_from_others", "same_trait_visibility",
    "congenital", "agnatic", "enatic", "birth", "inbred", "attribute", "personality",
    "leader", "random", "immortal", "lifestyle", "is_health", "is_epidemic",
    "is_illness", "incapacitating", "pilgrimage", "childhood", "in_hiding",
    "education", "opinions", "opposites", "combat", "country", "province",
    "ai_ambition", "ai_honor", "ai_rationality", "ai_greed", "ai_zeal",
    "ruler_designer_cost", "customizer", "leadership_traits", "inherit_chance",
    "both_parent_has_trait_inherit_chance", "cached", "cannot_marry",
    "cannot_inherit", "rebel_inherited", "blinding", "religious",
    "prevent_decadence", "caste_tier", "religious_branch", "command_modifier",
    "potential", "male_insult", "female_insult", "child_insult", "male_compliment",
    "female_compliment", "child_compliment", "male_insult_adj", "female_insult_adj",
    "child_insult_adj", "male_compliment_adj", "female_compliment_adj",
    "child_compliment_adj", "can_hold_titles", "is_symptom", "vice", "virtue",
    "succession_gfx",
    # used by vanilla / Faerun but absent from traits.info
    "priest", "monthly_character_prestige", "monthly_character_piety",  # <- modifiers, see below
    "random_creation", "graphical_culture", "muslim", "pagan", "cannot_inherit_x",
}
# monthly_character_* are genuine modifiers, drop them back out
TRAIT_FIELDS -= {"monthly_character_prestige", "monthly_character_piety"}

# Keys that are trait *structure* but whose children are modifiers.
MODIFIER_BEARING_BLOCKS = {"command_modifier"}
# Blocks whose contents are triggers/effects, never modifiers.
TRIGGER_BLOCKS = {
    "potential", "is_visible", "trigger", "opposites", "leadership_traits",
    "customizer", "opinions", "prerequisites", "upgrades_from", "AND", "OR", "NOT",
    "NOR", "NAND", "hidden_tooltip", "if", "else", "any_", "trigger_if",
}

BUILDING_FIELDS = {
    "desc", "trigger", "potential", "gold_cost", "build_time", "prestige_cost",
    "piety_cost", "ai_creation_factor", "extra_tech_building_start", "upgrades_from",
    "prerequisites", "add_number_to_name", "is_active_trigger", "tribal_type",
    "religious_branch", "culture", "culture_group", "religion", "religion_group",
    "hospital_level", "convert_to", "is_visible", "gold_cost_mult", "effect",
    "creation_effect", "destroy_effect", "on_completion", "ai_creation_factor_mult",
    "tech_bonus", "government", "capital", "port", "nomad_only", "monthly_character_",
    "replaces", "raise_levy_mult", "hard_prerequisites", "start", "type",
}


def classify(path: tuple[str, ...], key: str, kind: str) -> str:
    """Return 'modifier', 'field', or 'trigger'."""
    if any(p in TRIGGER_BLOCKS for p in path[1:]):
        return "trigger"
    fields = TRAIT_FIELDS if kind == "trait" else BUILDING_FIELDS
    if key in fields:
        return "field"
    if kind == "trait" and key in BUILDING_FIELDS and key not in TRAIT_FIELDS:
        # e.g. 'desc' does not occur in traits; be conservative
        return "field"
    return "modifier"


# --------------------------------------------------------------------------- #
# collection
# --------------------------------------------------------------------------- #

def collect(faerun: Path) -> tuple[Counter, dict[str, set[str]], dict[str, list[str]]]:
    freq: Counter = Counter()
    where: dict[str, set[str]] = defaultdict(set)
    samples: dict[str, list[str]] = defaultdict(list)

    def handle(files, kind: str, depth: int):
        for fp in sorted(files):
            text = fp.read_bytes().decode("cp1252", errors="replace")
            for path, key, val in parse_leaves(text):
                # traits: modifiers sit at depth 1 (inside the trait block) or inside
                #         command_modifier (depth 2)
                # buildings: modifiers sit at depth 2 (holding -> building -> key)
                if kind == "trait":
                    ok = len(path) == 1 or (len(path) == 2 and path[1] in MODIFIER_BEARING_BLOCKS)
                else:
                    ok = len(path) == 2
                if not ok:
                    continue
                cls = classify(path, key, kind)
                if cls != "modifier":
                    continue
                sub = "command_modifier" if (len(path) == 2 and path[1] == "command_modifier") else kind
                freq[key] += 1
                where[key].add(f"{sub}:{fp.name}")
                if len(samples[key]) < 3 and val is not None:
                    samples[key].append(f"{path[-1] if len(path)>1 else path[0]}={val}")

    handle((faerun / "common" / "traits").glob("*.txt"), "trait", 1)
    handle((faerun / "common" / "buildings").glob("*.txt"), "building", 2)
    return freq, where, samples


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--faerun", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=REPO / "docs" / "evidence" / "ck2_modifier_keys.csv")
    args = ap.parse_args()

    faerun = args.faerun or default_faerun()
    if not (faerun / "common" / "traits").is_dir():
        raise SystemExit(f"no Faerun trait dir under {faerun}")

    freq, where, samples = collect(faerun)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["ck2_key", "count", "sources", "samples"])
        for key, count in sorted(freq.items(), key=lambda kv: (-kv[1], kv[0])):
            w.writerow([key, count, ";".join(sorted(where[key])), ";".join(samples[key])])
    print(f"{len(freq)} distinct modifier keys, {sum(freq.values())} occurrences -> {args.out}")


if __name__ == "__main__":
    main()
