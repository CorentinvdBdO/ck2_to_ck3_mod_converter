"""CK2 province id -> CK3 province ids, and the dense CK3 id space.

CK3 wants a dense ``1..N`` id space in ``definition.csv`` (row 0 first).  CK2
ids are sparse: Faerûn defines 2698 provinces but ``max_provinces = 2720`` and
some defined colours vanish when the bitmap is rescaled.  So the remap has to
happen *after* the pixel pass, and it takes the surviving-colour set as input.

The padding ocean is appended last so its id never shifts when a CK2 province
is added or lost upstream... except that ids before it do shift; that is why
``docs/evidence/province_id_map.csv`` is written on every run and why later
lanes must read it rather than assume anything.

Since lane ``baronies`` the mapping is **one-to-many**: a CK2 county becomes
one CK3 province per built holding (``docs/step_map_baronies.md``).  So

* ``ck2_to_ck3`` still gives *one* id per CK2 province — the county capital's
  barony — because that is what a strait's ``Through`` column and a sea-zone
  range need;
* ``ck2_to_all`` gives every id, which is what a region list needs;
* land barony ids come **first** and in CK2 ``landed_titles`` hierarchy order,
  so neighbouring baronies get neighbouring ids, and water ids follow in
  ascending CK2 order so ``sea_zones`` stays a handful of ``RANGE``s.
"""

from __future__ import annotations

import csv
import hashlib
import io
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from .baronies import Barony, BaronyPlan
from .ck2read import Ck2Province


@dataclass(frozen=True)
class Ck3Province:
    id: int
    rgb: tuple[int, int, int]
    name: str
    #: CK2 id, or ``None`` for provinces the converter had to add (padding ocean)
    ck2_id: int | None
    is_sea: bool = False
    is_lake: bool = False
    is_impassable: bool = False
    is_river: bool = False
    #: CK2 barony key (``b_castle_waterdeep``) when this province is a barony
    barony: str | None = None
    #: CK2 county key the barony belongs to
    county: str | None = None
    #: CK3 holding type (``castle_holding``, ...)
    holding: str | None = None
    #: growth label from :class:`~ck2ck3.map.baronies.BaronyPlan`, 0 if none
    label: int = 0

    @property
    def is_barony(self) -> bool:
        return self.barony is not None

    @property
    def is_water(self) -> bool:
        """Sea, lake and river provinces all count as water for terrain."""
        return self.is_sea or self.is_lake or self.is_river


@dataclass
class IdMap:
    provinces: list[Ck3Province]
    #: CK2 id -> the *primary* CK3 id (the county capital's barony)
    ck2_to_ck3: dict[int, int]
    #: CK2 ids that were defined but got no CK3 province
    dropped: list[int]
    #: the padding-ocean province
    padding: Ck3Province
    #: CK2 id -> every CK3 id it became, primary first
    ck2_to_all: dict[int, list[int]] = field(default_factory=dict)
    #: growth label -> CK3 id, for painting the raster
    label_to_id: dict[int, int] = field(default_factory=dict)

    def ck3(self, ck2_id: int) -> int | None:
        return self.ck2_to_ck3.get(ck2_id)

    def all_ck3(self, ck2_id: int) -> list[int]:
        one = self.ck2_to_ck3.get(ck2_id)
        return self.ck2_to_all.get(ck2_id, [] if one is None else [one])

    def remap_ids(self, ck2_ids: list[int]) -> list[int]:
        """Every CK3 id of every listed CK2 province, order preserved.

        One CK2 county is several CK3 baronies now, so a region that named a
        CK2 province must name all of its baronies or the region loses land.
        Duplicates are removed, ids that did not survive are dropped.
        """
        out: list[int] = []
        seen: set[int] = set()
        for i in ck2_ids:
            for c in self.all_ck3(i):
                if c not in seen:
                    seen.add(c)
                    out.append(c)
        return out

    def by_id(self) -> dict[int, Ck3Province]:
        return {p.id: p for p in self.provinces}

    def baronies(self) -> list[Ck3Province]:
        return [p for p in self.provinces if p.is_barony]


def build(
    ck2_provinces: list[Ck2Province],
    surviving_ck2_ids: set[int],
    *,
    sea_ids: set[int],
    lake_ids: set[int],
    impassable_ids: set[int] = frozenset(),  # type: ignore[assignment]
    river_ids: set[int] = frozenset(),  # type: ignore[assignment]
    padding_rgb: tuple[int, int, int],
    padding_name: str,
) -> IdMap:
    """Assign dense CK3 ids, in ascending CK2 id order.

    Ascending CK2 order keeps the diff between two conversion runs small and
    keeps nearby CK2 ids nearby in CK3, which matters for the ``sea_zones``
    ranges in ``default.map`` (they are written as ``RANGE { first last }``).
    """
    _reject_colour_collision(ck2_provinces, padding_rgb)

    out: list[Ck3Province] = []
    mapping: dict[int, int] = {}
    dropped: list[int] = []
    next_id = 1
    for p in sorted(ck2_provinces, key=lambda x: x.id):
        if p.id not in surviving_ck2_ids:
            dropped.append(p.id)
            continue
        out.append(
            Ck3Province(
                id=next_id,
                rgb=p.rgb,
                name=p.name,
                ck2_id=p.id,
                # sea / lake / river are mutually exclusive in CK3: an id in
                # `river_provinces` must NOT also be in `sea_zones`
                # (verified: vanilla river_provinces RANGE { 628 630 } is
                # absent from every sea_zones list in map_data/default.map).
                # CK2 has no such rule - its major_rivers are a subset of its
                # sea_zones - so the exclusion happens here.
                is_sea=(
                    p.id in sea_ids
                    and p.id not in lake_ids
                    and p.id not in river_ids
                ),
                is_lake=p.id in lake_ids and p.id not in river_ids,
                is_impassable=p.id in impassable_ids,
                is_river=p.id in river_ids,
            )
        )
        mapping[p.id] = next_id
        next_id += 1

    padding = Ck3Province(
        id=next_id, rgb=padding_rgb, name=padding_name, ck2_id=None, is_sea=True
    )
    out.append(padding)
    return IdMap(provinces=out, ck2_to_ck3=mapping, dropped=dropped, padding=padding)


def _reject_colour_collision(
    ck2_provinces: list[Ck2Province], padding_rgb: tuple[int, int, int]
) -> None:
    """The padding colour must not collide with a CK2 province colour."""
    used = {p.rgb for p in ck2_provinces}
    if padding_rgb in used:
        clash = next(p for p in ck2_provinces if p.rgb == padding_rgb)
        raise ValueError(
            f"provinces.ocean_rgb {padding_rgb} collides with CK2 province "
            f"{clash.id} ({clash.name}); pick another padding colour"
        )
    for reserved in ((0, 0, 0), (255, 255, 255)):
        if padding_rgb == reserved:
            raise ValueError(f"provinces.ocean_rgb must not be {reserved}")


#: colours no barony may take: reserved by CK3 or already used by a CK2
#: province that survives unchanged (water, wasteland, the padding ocean).
RESERVED_COLOURS = frozenset({(0, 0, 0), (255, 255, 255)})


def barony_colour(key: str, taken: set[tuple[int, int, int]]) -> tuple[int, int, int]:
    """A stable, unique colour for a barony, derived from its title id.

    A hash rather than a counter, so adding a barony upstream does not recolour
    every barony after it: the diff in ``provinces.png`` stays local.  BLAKE2b
    because Python's own ``hash()`` is salted per process and would make the
    output non-reproducible (``docs/design_map.md`` §B.7).

    On a collision the search walks the 24-bit colour space upwards from the
    hash.  With a few thousand baronies in 16.7 M colours the first probe
    almost always wins, and the walk is deterministic for a given input set.
    """
    digest = hashlib.blake2b(key.encode("utf-8"), digest_size=8).digest()
    base = int.from_bytes(digest, "big") & 0xFFFFFF
    for probe in range(1 << 24):
        c = (base + probe) & 0xFFFFFF
        rgb = ((c >> 16) & 255, (c >> 8) & 255, c & 255)
        if rgb not in taken and rgb not in RESERVED_COLOURS:
            return rgb
    raise ValueError("ran out of province colours")  # pragma: no cover


def build_with_baronies(
    ck2_provinces: Sequence[Ck2Province],
    surviving_ck2_ids: set[int],
    plan: BaronyPlan,
    *,
    sea_ids: set[int],
    lake_ids: set[int],
    impassable_ids: set[int] = frozenset(),  # type: ignore[assignment]
    river_ids: set[int] = frozenset(),  # type: ignore[assignment]
    padding_rgb: tuple[int, int, int],
    padding_name: str,
) -> IdMap:
    """Dense CK3 ids for a barony-split map.

    Order: every land barony first, in CK2 ``landed_titles`` hierarchy order
    (empire, kingdom, duchy, county, barony), then every CK2 province that is
    *not* split — water, wasteland, and land with no county history — in
    ascending CK2 id, then the padding ocean.

    Baronies before water is what keeps the ``sea_zones`` ranges in
    ``default.map`` contiguous: CK2 numbers its sea provinces in blocks, and
    those blocks survive the remap only if nothing is interleaved with them.
    """
    _reject_colour_collision(list(ck2_provinces), padding_rgb)
    by_ck2 = {p.id: p for p in ck2_provinces}

    taken: set[tuple[int, int, int]] = {p.rgb for p in ck2_provinces}
    taken.add(padding_rgb)

    out: list[Ck3Province] = []
    primary: dict[int, int] = {}
    all_ids: dict[int, list[int]] = {}
    label_to_id: dict[int, int] = {}
    next_id = 1

    split: dict[int, list[Barony]] = {}
    label_of: dict[int, int] = {}
    for i, b in enumerate(plan.placed):
        split.setdefault(b.ck2_province, []).append(b)
        label_of[id(b)] = i + 1

    for b in sorted(plan.placed, key=lambda x: (x.order, x.key)):
        src = by_ck2.get(b.ck2_province)
        rgb = barony_colour(b.key, taken)
        taken.add(rgb)
        prov = Ck3Province(
            id=next_id,
            rgb=rgb,
            name=b.key,
            ck2_id=b.ck2_province,
            barony=b.key,
            county=b.county,
            holding=b.holding,
            label=label_of[id(b)],
        )
        out.append(prov)
        label_to_id[prov.label] = next_id
        bucket = all_ids.setdefault(b.ck2_province, [])
        if b.is_capital or b.ck2_province not in primary:
            primary[b.ck2_province] = next_id
            bucket.insert(0, next_id)
        else:
            bucket.append(next_id)
        if src is None:  # pragma: no cover - selections come from the raster
            raise ValueError(f"barony {b.key} names unknown CK2 province {b.ck2_province}")
        next_id += 1

    for p in sorted(ck2_provinces, key=lambda x: x.id):
        if p.id not in surviving_ck2_ids or p.id in split:
            continue
        out.append(
            Ck3Province(
                id=next_id,
                rgb=p.rgb,
                name=p.name,
                ck2_id=p.id,
                is_sea=(
                    p.id in sea_ids
                    and p.id not in lake_ids
                    and p.id not in river_ids
                ),
                is_lake=p.id in lake_ids and p.id not in river_ids,
                is_impassable=p.id in impassable_ids,
                is_river=p.id in river_ids,
            )
        )
        primary[p.id] = next_id
        all_ids[p.id] = [next_id]
        next_id += 1

    dropped = [
        p.id for p in sorted(ck2_provinces, key=lambda x: x.id)
        if p.id not in surviving_ck2_ids
    ]
    padding = Ck3Province(
        id=next_id, rgb=padding_rgb, name=padding_name, ck2_id=None, is_sea=True
    )
    out.append(padding)
    return IdMap(
        provinces=out,
        ck2_to_ck3=primary,
        dropped=dropped,
        padding=padding,
        ck2_to_all=all_ids,
        label_to_id=label_to_id,
    )


def render_id_map_csv(idmap: IdMap) -> str:
    """``docs/evidence/province_id_map.csv`` — the contract for later lanes.

    Later lanes must READ this file rather than assume the mapping: the ids of
    everything after a dropped CK2 province shift when upstream changes.
    """
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(
        ["ck2_id", "ck3_id", "r", "g", "b", "name", "kind", "barony", "county", "holding"]
    )
    for p in idmap.provinces:
        w.writerow(
            [
                "" if p.ck2_id is None else p.ck2_id,
                p.id,
                *p.rgb,
                p.name,
                _kind(p),
                p.barony or "",
                p.county or "",
                p.holding or "",
            ]
        )
    for ck2_id in idmap.dropped:
        w.writerow([ck2_id, "", "", "", "", "", "dropped", "", "", ""])
    return buf.getvalue()


def write_id_map_csv(idmap: IdMap, path: str | Path) -> None:
    """Convenience wrapper for the standalone entry point."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_id_map_csv(idmap), encoding="utf-8", newline="")


def _kind(p: Ck3Province) -> str:
    if p.is_barony:
        return "barony"
    if p.is_lake:
        return "lake"
    if p.is_river:
        return "river"
    if p.is_sea:
        return "sea"
    if p.is_impassable:
        return "impassable"
    return "land"
