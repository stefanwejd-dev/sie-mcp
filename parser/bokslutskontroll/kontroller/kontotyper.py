"""Grupp C — K-14: bro till kontotyp_vakt.analysera_kontotyper.

Se hantverksbok/BOKSLUTSKONTROLLER.md §5, grupp C. Skriver ingen ny logik —
mappar bara Kontotypavvikelse till Fynd. parser/kontotyp_vakt.py är
oförändrad."""

from __future__ import annotations

from kontotyp_vakt import analysera_kontotyper

from ..modell import Fynd, Kontext
from ..motor import registrera


@registrera("K-14")
def kontroll_k14(kontext: Kontext) -> list[Fynd]:
    return [
        Fynd(
            kontroll_id="K-14",
            rubrik="Kontotypavvikelse",
            allvarlighet="observation",
            motivering=avvikelse.motivering,
            konton=(avvikelse.kontonr,),
            belopp=avvikelse.saldo,
        )
        for avvikelse in analysera_kontotyper(kontext.sie)
    ]
