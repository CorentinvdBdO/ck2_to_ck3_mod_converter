"""CK2 title/history readers and the CK3 writers of lane ``titles-history``.

Read side: :mod:`ck2ck3.titles.ck2read` (``common/landed_titles``,
``history/titles``, ``history/provinces``, ``common/bookmarks``,
``common/cultures``).  Write side: :mod:`ck2ck3.titles.landed`,
:mod:`ck2ck3.titles.provinces`, :mod:`ck2ck3.titles.history`,
:mod:`ck2ck3.titles.coa`, :mod:`ck2ck3.titles.bookmarks`.

Mapping tables and the derivations that have no 1:1 source
(government, succession law, holding type) live in
:mod:`ck2ck3.titles.tables`; the CK3-side facts behind them are in
``docs/formats_titles.md`` and ``docs/step_titles.md``.
"""
