"""Bokslutskontroller — deterministiskt kontrollskikt på SIEFil.

Se hantverksbok/BOKSLUTSKONTROLLER.md. Publikt API nedan.
"""

from __future__ import annotations

from .modell import Allvarlighet, Fynd, Konteringsrad, Kontext, Kontroll, Rattelseforslag, Regelhanvisning
from .motor import KONTROLLER, kor_kontroller, registrera
from . import kontroller  # noqa: F401  — fyller KONTROLLER-registret

__all__ = [
    "Allvarlighet",
    "Fynd",
    "Konteringsrad",
    "Kontext",
    "Kontroll",
    "KONTROLLER",
    "Rattelseforslag",
    "Regelhanvisning",
    "kor_kontroller",
    "registrera",
]
