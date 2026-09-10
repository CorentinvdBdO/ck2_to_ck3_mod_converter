#!/usr/bin/env python3
"""Build and verify `mappings/event_themes.csv` (CK2 art -> CK3 event theme).

Lane `events` (README §5 step 3). CK3 events carry a `theme = <id>`, which
picks the background art, icon and sound of the event window; CK2 instead
names a `picture = GFX_evt_*` illustration and a `border =
GFX_event_<shape>_frame_<category>` frame. The frame category is CK2's own
five-way classification of the event (religion / war / intrigue / economy /
diplomacy) and maps almost one-to-one onto a CK3 theme; the picture is the
finer signal where a CK3 theme happens to exist for the same subject.

So the table has two row families and the `events` step resolves in this
order: `picture` row, then `border` row, then the `default` theme.

Every `ck3_theme` is checked against the ids actually defined in the local
CK3 1.19 install's `common/event_themes/*.txt`; the script exits non-zero
listing any miss (same bar as `scripts/verify_ck3_keys.py`), so a theme id
guessed from its English name cannot reach the mod.

Usage: `uv run scripts/build_event_themes_csv.py [--check]`
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from ck2ck3.config import Config  # noqa: E402

OUT = REPO / "mappings" / "event_themes.csv"
PICTURES = REPO / "docs" / "evidence" / "events_pictures.csv"
THEME_KEY_RE = re.compile(r"^([a-z_0-9]+)\s*=\s*\{", re.M)

#: CK2 `border` frame category -> CK3 theme. CK2's frame is its own top-level
#: classification of the event and is set on 617 of the 1762 `new` events;
#: `verified` by reading `interface/*.gfx` frame names against the five CK2
#: focus categories. Shape (normal/letter/narrative/long) does not change the
#: subject, only the window, so all four shapes share a category's theme.
BORDER_THEMES: dict[str, tuple[str, str]] = {
    "religion": ("faith", "CK2 religion frame -> CK3 faith theme"),
    "war": ("war", "CK2 war frame -> CK3 war theme"),
    "intrigue": ("intrigue", "unchanged concept"),
    "economy": ("stewardship", "CK3 renamed the economy lifestyle to stewardship"),
    "diplomacy": ("diplomacy", "unchanged concept"),
}

#: CK2 `picture` id -> CK3 theme, curated. Only a picture whose subject has a
#: real CK3 theme is listed; everything else falls through to the border row
#: and then to `default`. Faerûn-specific art (dragons, mind flayers, the
#: Underdark, planes) has no CK3 counterpart on purpose - inventing one would
#: be worse than `default`.
PICTURE_THEMES: dict[str, tuple[str, str]] = {
    # -- faith ----------------------------------------------------------
    "GFX_evt_bishop": ("faith", "clergy"),
    "GFX_evt_imam": ("faith", "clergy"),
    "GFX_evt_relic_box": ("faith", "relic/reliquary"),
    "GFX_evt_angels_1": ("faith", "divine apparition"),
    "GFX_evt_angels_2": ("faith", "divine apparition"),
    "GFX_evt_religious_exultation": ("faith", "religious ceremony"),
    "GFX_evt_secluded_in_prayer": ("faith", "prayer"),
    "GFX_evt_tribal_shrine": ("faith", "shrine"),
    "GFX_evt_monastery_monks": ("faith", "monastery"),
    "GFX_evt_catching_heretic": ("faith", "heresy"),
    "GFX_evt_midwinter_blot_oldgods": ("faith", "pagan sacrifice"),
    "GFX_evt_viking_throneroom_oldgods": ("faith", "pagan hall"),
    # -- witchcraft / occult --------------------------------------------
    "GFX_evt_dark_prayer": ("witchcraft", "occult rite"),
    "GFX_evt_magic_ritual": ("witchcraft", "ritual"),
    "GFX_evt_magic_2": ("witchcraft", "ritual"),
    "GFX_evt_secret_ceremony": ("witchcraft", "secret rite"),
    "GFX_evt_vampire_1": ("witchcraft", "the nearest CK3 theme for undead flavour"),
    "GFX_evt_werewolf": ("witchcraft", "the nearest CK3 theme for lycanthropy"),
    "GFX_evt_death_knight": ("witchcraft", "the nearest CK3 theme for undead flavour"),
    "GFX_evt_shadowy_cabal": ("witchcraft", "cabal"),
    # -- learning --------------------------------------------------------
    "GFX_evt_wizard": ("learning", "scholarship; CK3 has no arcane theme"),
    "GFX_evt_wizard_2": ("learning", "scholarship; CK3 has no arcane theme"),
    "GFX_evt_library": ("learning", "library"),
    "GFX_evt_experiment": ("learning", "experiment"),
    "GFX_evt_scholar_1": ("learning", "scholar"),
    "GFX_evt_child_reading": ("education", "a child being taught"),
    "GFX_evt_book_carolingian_script": ("learning", "book/manuscript"),
    "GFX_evt_gathering_of_minds": ("learning", "council of scholars"),
    "GFX_evt_runecaster_1": ("learning", "runes; CK3 has no arcane theme"),
    # -- war / martial ----------------------------------------------------
    "GFX_evt_battle": ("battle", "battle"),
    "GFX_evt_died_battle": ("battle", "battle death"),
    "GFX_evt_carnage_1": ("battle", "battlefield carnage"),
    "GFX_evt_large_army": ("war", "army on the march"),
    "GFX_evt_steppe_mercenaries": ("war", "mercenary company"),
    "GFX_evt_siege": ("war", "siege"),
    "GFX_evt_northlander_raid": ("raid", "raid"),
    "GFX_evt_vikings_arriving_oldgods": ("raid", "raiders landing"),
    "GFX_evt_melee": ("martial", "melee at arms"),
    "GFX_evt_joust": ("martial", "joust"),
    "GFX_evt_duel_scene": ("martial", "duel"),
    "GFX_evt_weaponsmith": ("martial", "arms"),
    "GFX_evt_orcs": ("war", "hostile warband"),
    "GFX_evt_barbarian_1": ("war", "hostile warband"),
    "GFX_evt_bandits": ("war", "bandits"),
    # -- intrigue ---------------------------------------------------------
    "GFX_evt_shady_meeting": ("intrigue", "conspiracy"),
    "GFX_evt_whispers": ("intrigue", "rumour"),
    "GFX_evt_eavesdropping": ("intrigue", "eavesdropping"),
    "GFX_evt_gossip_1": ("intrigue", "gossip"),
    "GFX_evt_suspicious_noble": ("intrigue", "suspicion"),
    "GFX_evt_scandal": ("intrigue", "scandal"),
    "GFX_evt_torture": ("prison", "torture; CK3's prison theme covers the dungeon"),
    "GFX_evt_into_the_dungeon": ("dungeon", "dungeon"),
    # -- rule / realm ------------------------------------------------------
    "GFX_evt_council": ("realm", "council"),
    "GFX_evt_council_quarrelling": ("realm", "council dispute"),
    "GFX_evt_noble_in_castle": ("realm", "court"),
    "GFX_evt_courtiers_talking": ("court", "court chatter"),
    "GFX_evt_rival_rulers": ("unfriendly", "rivalry between rulers"),
    "GFX_evt_quarrel": ("unfriendly", "quarrel"),
    "GFX_evt_emissary": ("diplomacy", "envoy"),
    "GFX_evt_emissary_arabic": ("diplomacy", "envoy"),
    "GFX_evt_courier": ("diplomacy", "courier"),
    "GFX_evt_bad_news": ("diplomacy", "message"),
    # -- stewardship / economy ---------------------------------------------
    "GFX_evt_market": ("stewardship", "market"),
    "GFX_evt_busy_trading_dock_republic": ("stewardship", "trade"),
    "GFX_evt_treasure": ("stewardship", "treasure"),
    "GFX_evt_castle_construction": ("stewardship", "construction"),
    "GFX_evt_doge_republic": ("stewardship", "republic"),
    "GFX_evt_peasants": ("stewardship", "peasantry"),
    "GFX_evt_noble_haughty_talking_to_peasants": ("stewardship", "peasantry"),
    # -- personal / health --------------------------------------------------
    "GFX_evt_lovers": ("love", "lovers"),
    "GFX_evt_marriage": ("marriage", "wedding"),
    "GFX_evt_birth": ("pregnancy", "birth"),
    "GFX_evt_death": ("death", "death"),
    "GFX_evt_illness": ("physical_health", "illness"),
    "GFX_evt_recovery": ("recovery", "recovery"),
    "GFX_evt_stressed_ruler": ("mental_health", "stress"),
    "GFX_evt_lunatic": ("mental_health", "madness"),
    "GFX_evt_drunk": ("mental_health", "drink"),
    # -- activities ----------------------------------------------------------
    "GFX_evt_feast": ("feast_activity", "feast"),
    "GFX_evt_festival_1": ("festival_activity", "festival"),
    "GFX_evt_hunt": ("hunt_activity", "hunt"),
    "GFX_evt_jugglers": ("party", "entertainers"),
    # -- travel / places -------------------------------------------------------
    "GFX_evt_savage_frontier": ("travel", "wilderness journey"),
    "GFX_evt_adventurers": ("travel", "adventuring party on the road"),
    "GFX_evt_adventurers_2": ("travel", "adventuring party on the road"),
    "GFX_evt_adventurers_3": ("travel", "adventuring party on the road"),
    "GFX_evt_adventurers_4": ("travel", "adventuring party on the road"),
    "GFX_evt_rider_1": ("travel", "rider"),
    "GFX_evt_forest_a": ("travel", "forest"),
    "GFX_evt_forest_b": ("travel", "forest"),
    "GFX_evt_savannah_a": ("travel", "open country"),
    "GFX_evt_tribal_lands": ("travel", "open country"),
    "GFX_evt_burning_house": ("disaster", "fire"),
    "GFX_evt_burning_house_arabic": ("disaster", "fire"),
    "GFX_evt_norse_tempest": ("disaster", "storm"),
}


def installed_themes(ck3_game: Path) -> set[str]:
    """Every theme id defined in the CK3 install's `common/event_themes/`."""
    folder = ck3_game / "common" / "event_themes"
    ids: set[str] = set()
    for path in sorted(folder.glob("*.txt")):
        ids.update(THEME_KEY_RE.findall(path.read_text(encoding="utf-8-sig")))
    return ids


def rows() -> list[tuple[str, str, str, str, str]]:
    uses: dict[tuple[str, str], int] = {}
    if PICTURES.is_file():
        for row in csv.DictReader(open(PICTURES, encoding="utf-8")):
            uses[(row["field"], row["value"])] = int(row["uses"])

    out: list[tuple[str, str, str, str, str]] = []
    for shape in ("normal", "letter", "narrative", "long"):
        for category, (theme, note) in BORDER_THEMES.items():
            value = f"GFX_event_{shape}_frame_{category}"
            if (("border", value) not in uses) and shape != "normal":
                continue  # only emit shapes Faerûn actually uses, plus all five normals
            out.append(("border", value, theme, note, str(uses.get(("border", value), 0))))
    for value, (theme, note) in PICTURE_THEMES.items():
        out.append(("picture", value, theme, note, str(uses.get(("picture", value), 0))))
    out.sort(key=lambda r: (r[0], -int(r[4]), r[1]))
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="verify only, write nothing")
    parser.add_argument("--config", default=str(REPO / "configs" / "faerun.toml"))
    args = parser.parse_args()

    ck3_game = Config.load(args.config).ck3_game
    known = installed_themes(ck3_game)
    if not known:
        print(f"no event themes found under {ck3_game}/common/event_themes", file=sys.stderr)
        return 2

    table = rows()
    misses = sorted({r[2] for r in table} - known)
    if misses:
        print(f"MISSES: {len(misses)} theme ids not defined in CK3 1.19: {', '.join(misses)}", file=sys.stderr)
        return 1

    if args.check:
        on_disk = [tuple(r) for r in csv.reader(open(OUT, encoding="utf-8-sig"))][1:]
        if on_disk != [tuple(r) for r in table]:
            print(f"{OUT} is stale; re-run without --check", file=sys.stderr)
            return 1
        print(f"MISSES: 0 ({len(table)} rows, {len(known)} themes installed); table up to date")
        return 0

    with open(OUT, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["ck2_field", "ck2_value", "ck3_theme", "note", "faerun_new_uses"])
        writer.writerows(table)
    print(f"MISSES: 0 — wrote {OUT} ({len(table)} rows; {len(known)} themes installed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
