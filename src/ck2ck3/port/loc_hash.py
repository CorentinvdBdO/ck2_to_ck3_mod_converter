"""MURMUR3A over localisation keys, because CK3 hashes them and collisions lose.

CK3 stores localisation in a hash table keyed by MurmurHash3 x86_32 (seed 0) of
the key name. Two keys with the same hash collide and one of them silently
fails to load — ``ck3-tiger`` reports this as ``localization-key-collision``.

A generated key scheme is exposed to that: 11951 mechanical ``dynn_fae_<id>``
keys collided with two vanilla keys on the first run (`verified` 2026-09-07,
``dynn_fae_109`` vs ``Burnon`` at ``0x57BC1D19`` and ``dynn_fae_1215`` vs
``b_tradruk`` at ``0x0D6EC7CE``). So the dynasties step hashes its keys against
the vanilla key set and renames the few that clash, rather than hoping.

Verified against the hashes ck3-tiger printed for those two pairs.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

_MASK = 0xFFFFFFFF
_C1 = 0xCC9E2D51
_C2 = 0x1B873593

#: ``key:0 "text"`` at the start of a line; the same shape write_ck3_yml emits.
_KEY_RE = re.compile(r"^\s*([A-Za-z0-9_.\-]+):", re.MULTILINE)


def _rotl(value: int, bits: int) -> int:
    return ((value << bits) | (value >> (32 - bits))) & _MASK


def murmur3a(text: str, seed: int = 0) -> int:
    """MurmurHash3 x86_32 of ``text`` (UTF-8), the hash CK3 uses for loc keys.

    >>> f"0x{murmur3a('Burnon'):08X}"
    '0x57BC1D19'
    >>> murmur3a("dynn_fae_109") == murmur3a("Burnon")
    True
    """
    data = text.encode("utf-8")
    h = seed & _MASK
    tail = len(data) & 3
    for i in range(0, len(data) - tail, 4):
        k = int.from_bytes(data[i : i + 4], "little")
        k = (k * _C1) & _MASK
        k = _rotl(k, 15)
        k = (k * _C2) & _MASK
        h ^= k
        h = _rotl(h, 13)
        h = (h * 5 + 0xE6546B64) & _MASK
    if tail:
        k = int.from_bytes(data[len(data) - tail :].ljust(4, b"\0"), "little")
        k = (k * _C1) & _MASK
        k = _rotl(k, 15)
        k = (k * _C2) & _MASK
        h ^= k
    h ^= len(data)
    h ^= h >> 16
    h = (h * 0x85EBCA6B) & _MASK
    h ^= h >> 13
    h = (h * 0xC2B2AE35) & _MASK
    h ^= h >> 16
    return h


def keys_in_folder(folder: Path) -> set[str]:
    """Every localisation key defined under ``folder`` (``*.yml``, recursive)."""
    out: set[str] = set()
    if not folder.is_dir():
        return out
    for path in folder.rglob("*.yml"):
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        out.update(m.group(1) for m in _KEY_RE.finditer(text))
    out.discard("l_english")
    return out


def resolve_collisions(
    keys: Iterable[str], taken: Iterable[str], *, suffix: str = "x"
) -> dict[str, str]:
    """Rename the keys whose hash clashes with ``taken`` or with each other.

    Returns ``{original: replacement}`` for the keys that had to move; a key
    with no clash is absent from the mapping. The replacement appends ``_x``
    (then ``_xx``, …) until the hash is free, which is deterministic and keeps
    the key readable.

    >>> resolve_collisions(["dynn_fae_109"], ["Burnon"])
    {'dynn_fae_109': 'dynn_fae_109_x'}
    """
    used = {murmur3a(k) for k in taken}
    renames: dict[str, str] = {}
    for key in keys:
        candidate = key
        while murmur3a(candidate) in used:
            candidate = f"{candidate}_{suffix}"
        if candidate != key:
            renames[key] = candidate
        used.add(murmur3a(candidate))
    return renames
