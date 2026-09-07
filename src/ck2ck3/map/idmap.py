"""CK2 province id -> CK3 province id remap.

CK3 wants a dense ``1..N`` id space in ``definition.csv`` (row 0 first).  CK2
ids are sparse: Faerûn defines 2698 provinces but ``max_provinces = 2720`` and
some defined colours vanish when the bitmap is rescaled.  So the remap has to
happen *after* the pixel pass, and it takes the surviving-colour set as input.

The padding ocean is appended last so its id never shifts when a CK2 province
is added or lost upstream... except that ids before it do shift; that is why
``docs/evidence/province_id_map.csv`` is written on every run and why later
lanes must read it rather than assume anything.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from pathlib import Path

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

    @property
    def is_water(self) -> bool:
        """Sea, lake and river provinces all count as water for terrain."""
        return self.is_sea or self.is_lake or self.is_river


@dataclass
class IdMap:
    provinces: list[Ck3Province]
    #: CK2 id -> CK3 id
    ck2_to_ck3: dict[int, int]
    #: CK2 ids that were defined but got no CK3 province
    dropped: list[int]
    #: the padding-ocean province
    padding: Ck3Province

    def ck3(self, ck2_id: int) -> int | None:
        return self.ck2_to_ck3.get(ck2_id)

    def remap_ids(self, ck2_ids: list[int]) -> list[int]:
        """Remap a list, silently dropping ids that did not survive."""
        return [c for c in (self.ck2_to_ck3.get(i) for i in ck2_ids) if c is not None]

    def by_id(self) -> dict[int, Ck3Province]:
        return {p.id: p for p in self.provinces}


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


def render_id_map_csv(idmap: IdMap) -> str:
    """``docs/evidence/province_id_map.csv`` — the contract for later lanes.

    Later lanes must READ this file rather than assume the mapping: the ids of
    everything after a dropped CK2 province shift when upstream changes.
    """
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["ck2_id", "ck3_id", "r", "g", "b", "name", "kind"])
    for p in idmap.provinces:
        w.writerow(
            [
                "" if p.ck2_id is None else p.ck2_id,
                p.id,
                *p.rgb,
                p.name,
                _kind(p),
            ]
        )
    for ck2_id in idmap.dropped:
        w.writerow([ck2_id, "", "", "", "", "", "dropped"])
    return buf.getvalue()


def write_id_map_csv(idmap: IdMap, path: str | Path) -> None:
    """Convenience wrapper for the standalone entry point."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_id_map_csv(idmap), encoding="utf-8", newline="")


def _kind(p: Ck3Province) -> str:
    if p.is_lake:
        return "lake"
    if p.is_river:
        return "river"
    if p.is_sea:
        return "sea"
    if p.is_impassable:
        return "impassable"
    return "land"
