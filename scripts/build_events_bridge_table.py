#!/usr/bin/env python3
"""Bridge table: vanilla CK2 events Faerûn keeps/modifies -> CK3 vanilla
counterpart (README §5 step 2).

**Coverage is partial by design** (`assumed`, this session): CK3 restructured
CK2's per-file flavour-event model into a handful of shared systems (schemes,
lifestyles, activities, relations) plus DLC-flavour files, so there is no way
to name 8454 individual CK3 counterparts without inventing them. Instead this
script curates a **file-level** correspondence — one counterpart per vanilla
CK2 event *file* (`FILE_COUNTERPARTS` below), each backed by the CK3 events
tree actually containing that file/folder (`docs/evidence/ck3_events_tree.txt`)
or, where CK3 dropped the mechanic outright, a `none` row with a one-line
reason from `docs/mechanics_inventory.md`. That one counterpart is then
applied to every `kept`/`modified` CK2 event id in the file, confidence
`low` (a system match, not a verified per-event one) unless noted otherwise
in `FILE_COUNTERPARTS`. This covers the 40 vanilla files with the most
`kept`+`modified` events — 4760 of 8454 (56.3 %, `verified` via
`scripts/events_provenance_summary.py` against `docs/evidence/events_provenance.csv`
2026-09-08). The remaining 162 files are untouched; add a `FILE_COUNTERPARTS`
row and re-run to extend.

No event-id-level CK3 match was invented: every row you can trust as
"this exact CK3 event" would need one, and none were found (`verified`
2026-09-08: no CK3 event file or comment names a CK2 id or the string
"CK2"/"Crusader Kings II" — `grep -r` came back empty).

Usage:
    uv run scripts/build_events_bridge_table.py [--ck2-game DIR]
        [--evidence-csv CSV] [--out CSV]
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from events_provenance import DEFAULT_CK2_GAME, collect_events  # noqa: E402

#: vanilla CK2 event file (relative to the CK2 install) -> counterpart.
#: `ck3`: a CK3 events/-relative file (the representative file of a folder,
#: line 1 cited as the evidence anchor for a *system*, not one event) or ""
#: for `none`. `kind`: "event_folder" (a CK3 file/folder covers the same
#: theme), "system" (a named CK3 mechanic with no events/ file, e.g. dynasty
#: legacies), or "none" (CK3 has nothing here). `confidence`: `medium` when
#: the theme match is specific and the CK3 file exists nowhere else
#: (e.g. `tribal_events.txt` <-> `HF_tribal_events.txt`), `low` when it is a
#: broad or uncertain thematic match. `reason` is the one-line justification;
#: for `none` rows it is required.
FILE_COUNTERPARTS: dict[str, tuple[str, str, str, str]] = {
    "events/traits_effects_events.txt": (
        "",
        "none",
        "low",
        "generic trait-add/remove narration called by scripted_effects; CK3 applies "
        "trait effects directly (add_trait/remove_trait), no dedicated narration file",
    ),
    "events/plot_events.txt": (
        "scheme_events/murder_scheme/murder_ongoing_events.txt",
        "event_folder",
        "medium",
        "CK2 'plots' (murder/etc.) -> CK3 schemes; scheme_events/murder_scheme is the "
        "closest single folder, though CK3 schemes span several scheme types",
    ),
    "events/friends_rivals_events.txt": (
        "relations_events/friendship_events.txt",
        "event_folder",
        "medium",
        "CK2 friend/rival opinion events -> CK3 relations_events/friendship_events.txt "
        "+ rivalry_events.txt (both exist; friendship cited as anchor)",
    ),
    "events/rip_flavor_events.txt": (
        "dlc/ce1/epidemic_events.txt",
        "event_folder",
        "low",
        "Reaper's Due (RIP) death/disease flavour; CE1 DLC epidemic_events.txt is the "
        "nearest CK3 disease-flavour file, but RIP's scope is much broader (mourning, "
        "funerals, death types) than CE1's epidemics alone",
    ),
    "events/HFP_pregnancy_events.txt": (
        "pregnancy_events.txt",
        "event_folder",
        "medium",
        "direct theme and filename match; CK3 kept a single top-level pregnancy_events.txt",
    ),
    "events/mnm_hermetics_events.txt": (
        "",
        "none",
        "n/a",
        "Monks & Mystics secret societies have no CK3 equivalent "
        "(docs/mechanics_inventory.md: Societies -> stub, biggest gap)",
    ),
    "events/on_action_events.txt": (
        "",
        "none",
        "n/a",
        "generic on_action-triggered housekeeping events with no shared theme; CK3's "
        "own on_action-triggered events are scattered by theme across the whole tree",
    ),
    "events/HF_sway_events.txt": (
        "scheme_events/sway_scheme/sway_ongoing_events.txt",
        "event_folder",
        "medium",
        "CK2 Holy Fury 'sway' interaction -> CK3 sway scheme, same verb kept",
    ),
    "events/HF_bloodline_events.txt": (
        "legacy_events/dynasty_legacy_events.txt",
        "event_folder",
        "low",
        "CK3 has no bloodlines; dynasty legacies is the nearest per-dynasty permanent "
        "bonus system (docs/mechanics_inventory.md suggests this mapping)",
    ),
    "events/HF_antagonize_events.txt": (
        "",
        "none",
        "n/a",
        "CK3 has no antagonize scheme or interaction of this shape",
    ),
    "events/mnm_assassins_events.txt": (
        "scheme_events/murder_scheme/murder_ongoing_events.txt",
        "event_folder",
        "medium",
        "Monks & Mystics assassins society flavour -> CK3's generic murder scheme",
    ),
    "events/ambition_events.txt": (
        "",
        "none",
        "n/a",
        "CK3 replaced CK2 ambitions with lifestyle perks/focus tracks; no event chain "
        "(docs/mechanics_inventory.md: Objectives -> stub)",
    ),
    "events/mnm_artifacts_events.txt": (
        "artifacts/artifact_events.txt",
        "event_folder",
        "medium",
        "direct theme match; CK3 kept a top-level artifacts/ events folder",
    ),
    "events/HF_religious_events.txt": (
        "religion_events/faith_conversion_events.txt",
        "event_folder",
        "low",
        "Holy Fury religious-authority flavour spans several CK3 religion_events/ "
        "files; faith_conversion_events.txt cited as the broadest anchor",
    ),
    "events/mnm_secret_religious_societies_events.txt": (
        "",
        "none",
        "n/a",
        "secret societies have no CK3 equivalent (docs/mechanics_inventory.md)",
    ),
    "events/rip_eternal_life_events.txt": (
        "death_events/death_management_events.txt",
        "event_folder",
        "low",
        "Reaper's Due death-postponement flavour; CK3's death_management_events.txt "
        "is the nearest file but CK3 has no postponement mechanic itself",
    ),
    "events/wol_seduction_events.txt": (
        "scheme_events/seduce_scheme/seduce_ongoing_events.txt",
        "event_folder",
        "medium",
        "Way of Life seduction interaction -> CK3 seduce scheme, same verb kept",
    ),
    "events/trait_notification.txt": (
        "",
        "none",
        "n/a",
        "CK3 shows trait gain/loss via a UI toast notification, not an event",
    ),
    "events/mnm_devil_worshipers_events.txt": (
        "",
        "none",
        "n/a",
        "secret societies have no CK3 equivalent (docs/mechanics_inventory.md)",
    ),
    "events/HF_tribal_events.txt": (
        "government_events/tribal_events.txt",
        "event_folder",
        "medium",
        "direct government-type match; CK3 kept a dedicated tribal_events.txt",
    ),
    "events/cm_murder_plot_events.txt": (
        "scheme_events/murder_scheme/murder_ongoing_events.txt",
        "event_folder",
        "medium",
        "Charlemagne-era murder plot flavour -> CK3's generic murder scheme",
    ),
    "events/HFP_health_events.txt": (
        "health_events.txt",
        "event_folder",
        "medium",
        "direct theme and filename match",
    ),
    "events/childhood_personality_traits_events.txt": (
        "education_and_childhood/child_personality_events.txt",
        "event_folder",
        "medium",
        "direct theme match; CK3 split childhood personality across two files, "
        "child_personality_events.txt cited as the anchor",
    ),
    "events/feast_events.txt": (
        "activities/feast_activity/feast_events.txt",
        "event_folder",
        "medium",
        "CK3 restructured the feast from a standalone event chain into the feast "
        "activity; feast_activity/feast_events.txt is its flavour-event file",
    ),
    "events/ze_childhood_events.txt": (
        "education_and_childhood/childhood_events.txt",
        "event_folder",
        "medium",
        "direct theme match",
    ),
    "events/regency_events.txt": (
        "",
        "none",
        "n/a",
        "CK3 regency is automatic (age of majority), no dedicated event chain",
    ),
    "events/various_traits_events.txt": (
        "trait_specific_events/trait_specific_events.txt",
        "event_folder",
        "low",
        "grab-bag trait-flavour file; CK3's trait_specific_events/ is the nearest "
        "equivalent grab-bag but the individual traits rarely line up",
    ),
    "events/wol_war_events.txt": (
        "war_events/war_events.txt",
        "event_folder",
        "medium",
        "direct theme and filename match",
    ),
    "events/rumours_events.txt": (
        "",
        "none",
        "n/a",
        "CK3 has no rumour mechanic or event chain",
    ),
    "events/wol_business_events.txt": (
        "",
        "none",
        "n/a",
        "CK2 Way of Life hobby/business-interest flavour has no CK3 counterpart found",
    ),
    "events/guardian_events.txt": (
        "education_and_childhood/childhood_education_events.txt",
        "event_folder",
        "low",
        "CK2 guardian-assignment flavour; CK3 education events are the nearest theme "
        "but CK3's guardian mechanic itself is simpler (single relation, no events)",
    ),
    "events/oldgods_pagan_feasts.txt": (
        "",
        "none",
        "n/a",
        "Old Gods (pagan reformation) pagan-feast flavour not ported to CK3 in this "
        "form; no matching CK3 file found",
    ),
    "events/married_life_events.txt": (
        "relations_events/spouse_events.txt",
        "event_folder",
        "medium",
        "direct theme match",
    ),
    "events/republic_trade_events.txt": (
        "",
        "none",
        "n/a",
        "CK3 1.19 has no merchant-republic play (docs/mechanics_inventory.md: "
        "Mercenaries, republics, holy orders -> republics limited)",
    ),
    "events/job_flavour_events.txt": (
        "councillor_task_events/steward_task_events.txt",
        "event_folder",
        "low",
        "CK2 council-job flavour -> CK3 councillor task events, restructured per "
        "council role; steward cited as the anchor",
    ),
    "events/jd_chinese_diplomacy_events.txt": (
        "dlc/tgp/tgp_china_yearly_events.txt",
        "event_folder",
        "low",
        "Jade Dragon (China) diplomacy flavour; CK3's later China-flavour DLC "
        "(tgp_china_* files) is the nearest theme match, unverified DLC identity",
    ),
    "events/wol_intrigue_events.txt": (
        "lifestyles/intrigue_lifestyle/intrigue_scheming_events.txt",
        "event_folder",
        "medium",
        "Way of Life intrigue flavour -> CK3 intrigue lifestyle events",
    ),
    "events/rip_seclusion_events.txt": (
        "",
        "none",
        "n/a",
        "Reaper's Due seclusion (illness hiding) flavour; no matching CK3 file found",
    ),
    "events/ze_adolescence_events.txt": (
        "education_and_childhood/coming_of_age_events.txt",
        "event_folder",
        "medium",
        "direct theme match",
    ),
    "events/gbc_events.txt": (
        "",
        "none",
        "n/a",
        "unidentified vanilla CK2 DLC prefix; no CK3 match found without further research",
    ),
}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ck2-game", type=Path, default=DEFAULT_CK2_GAME)
    ap.add_argument(
        "--evidence-csv",
        type=Path,
        default=REPO / "docs" / "evidence" / "events_provenance.csv",
    )
    ap.add_argument(
        "--out", type=Path, default=REPO / "mappings" / "events_ck2_ck3_vanilla.csv"
    )
    args = ap.parse_args(argv)

    # Re-parse only the covered vanilla files, to recover a real line number
    # per event id (events_provenance.csv itself does not keep one).
    covered_files = set(FILE_COUNTERPARTS)
    all_events = collect_events(args.ck2_game)
    line_of: dict[str, tuple[str, int]] = {}
    for eid, defs in all_events.items():
        for d in defs:
            if d.file in covered_files:
                line_of[eid] = (d.file, d.line)
                break

    with args.evidence_csv.open(encoding="utf-8") as fh:
        prov_rows = list(csv.DictReader(fh))

    out_rows = []
    for r in prov_rows:
        if r["status"] not in ("kept", "modified"):
            continue
        vfile = r["vanilla_file"]
        if vfile not in FILE_COUNTERPARTS:
            continue
        ck3, kind, confidence, reason = FILE_COUNTERPARTS[vfile]
        file_line = line_of.get(r["id"])
        ev_ck2 = f"{file_line[0]}:{file_line[1]}" if file_line else f"{vfile}:?"
        ev_ck3 = f"game/events/{ck3}:1" if ck3 else "n/a"
        out_rows.append(
            {
                "ck2_id": r["id"],
                "ck2_status": r["status"],
                "ck2_kind": r["kind"],
                "ck3_counterpart": ck3,
                "ck3_kind": kind,
                "confidence": confidence,
                "evidence_ck2": ev_ck2,
                "evidence_ck3": ev_ck3,
                "reason": reason,
            }
        )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(
            fh,
            fieldnames=[
                "ck2_id",
                "ck2_status",
                "ck2_kind",
                "ck3_counterpart",
                "ck3_kind",
                "confidence",
                "evidence_ck2",
                "evidence_ck3",
                "reason",
            ],
        )
        w.writeheader()
        w.writerows(out_rows)

    total_covered_events = len(out_rows)
    with args.evidence_csv.open(encoding="utf-8") as fh:
        all_kept_mod = sum(
            1 for row in csv.DictReader(fh) if row["status"] in ("kept", "modified")
        )
    print(
        f"{args.out}: {total_covered_events} rows "
        f"({len(FILE_COUNTERPARTS)} vanilla files) of {all_kept_mod} kept+modified "
        f"events ({100 * total_covered_events / all_kept_mod:.1f}% coverage)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
