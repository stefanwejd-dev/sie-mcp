"""avstamning — lager 1b: kontoutdragsavstämning mot en utomstående källa.

Se hantverksbok/BOKSLUTSPROGRAMMET.md §4. Delar `Fynd`, motor och register
med `bokslutskontroll` (lager 1) — bygg dem som ett system, inte som två.

Beroendet går bara åt ETT håll: `avstamning` importerar `bokslutskontroll`
(registret, `Fynd`, `Kontext`), aldrig tvärtom — `bokslutskontroll/modell.py`
refererar `Utdrag` bara under `TYPE_CHECKING`. Importen av `.kontroller`
nedan fyller `bokslutskontroll.motor.KONTROLLER` med A-01–A-05, precis som
`bokslutskontroll/__init__.py` gör för K-01–K-15."""

from __future__ import annotations

from . import kontroller  # noqa: F401  — fyller KONTROLLER-registret
