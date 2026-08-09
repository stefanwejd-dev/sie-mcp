"""Ackumulering — Modul 5: ISA 450-ackumulering.

Se ARCHITECTURE.md, avsnittet om Modul 5, för grundarkitekturen, och
tests/test_ackumulering.py:s moduldocstring för de tre kompletterande
arkitektbesluten (kontoplan-uppslagning för Modul 4:s riktning, att
"osäker" aldrig blir en Felaktighet i v1, samt att väsentlighetströsklarna
skickas in färdiga istället för att härledas här).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from domain_model import Konto
from kontomatchning import Kontobedömning
from kontotyp_vakt import Kontotypavvikelse

KORSNING_TILL_RIKTNING: dict[tuple[str, str], Literal["över", "under"]] = {
    ("K", "T"): "över",
    ("T", "K"): "under",
    ("I", "S"): "under",
    ("S", "I"): "över",
}


@dataclass
class Felaktighet:
    källa: Literal["modul2_kontotyp", "modul4_kontomatchning"]
    belopp: Decimal
    riktning: Literal["över", "under", "okänd"]
    kontonr: str
    kontonamn: str
    motivering: str
    plats: str | None = None


@dataclass
class AckumuleringsResultat:
    summa_netto: Decimal
    summa_brutto: Decimal
    status_netto: Literal["grön", "gul", "röd"]
    status_brutto: Literal["grön", "gul", "röd"]
    antal_felaktigheter: int
    antal_okänd_riktning: int
    felaktigheter: list[Felaktighet]


def härled_riktning_modul2(avvikelse: Kontotypavvikelse) -> Literal["över", "under", "okänd"]:
    return KORSNING_TILL_RIKTNING.get(
        (avvikelse.forvantad_typ, avvikelse.angiven_typ), "okänd"
    )


def härled_riktning_modul4(
    bedömning: Kontobedömning, kontoplan: dict[str, Konto]
) -> Literal["över", "under", "okänd"]:
    if bedömning.föreslaget_kontonr is None:
        return "okänd"

    bokfört_konto = kontoplan.get(bedömning.kontonr)
    föreslaget_konto = kontoplan.get(bedömning.föreslaget_kontonr)
    if bokfört_konto is None or föreslaget_konto is None:
        return "okänd"

    bokförd_typ = bokfört_konto.typ
    rätt_typ = föreslaget_konto.typ
    if bokförd_typ is None or rätt_typ is None:
        return "okänd"

    return KORSNING_TILL_RIKTNING.get((rätt_typ, bokförd_typ), "okänd")


def bygg_felaktigheter_fran_kontotypavvikelser(
    avvikelser: list[Kontotypavvikelse],
) -> list[Felaktighet]:
    return [
        Felaktighet(
            källa="modul2_kontotyp",
            belopp=avvikelse.saldo,
            riktning=härled_riktning_modul2(avvikelse),
            kontonr=avvikelse.kontonr,
            kontonamn=avvikelse.kontonamn,
            motivering=avvikelse.motivering,
        )
        for avvikelse in avvikelser
    ]


def bygg_felaktigheter_fran_kontobedomningar(
    bedömningar: list[Kontobedömning], kontoplan: dict[str, Konto]
) -> list[Felaktighet]:
    felaktigheter: list[Felaktighet] = []
    for bedömning in bedömningar:
        # "osäker" blir aldrig en Felaktighet i v1 (arkitektbeslut) — och
        # "matchning" är per definition inte en avvikelse att räkna.
        if bedömning.status != "avvikelse":
            continue

        konto = kontoplan.get(bedömning.kontonr)
        kontonamn = konto.namn if konto is not None else bedömning.kontonr

        felaktigheter.append(
            Felaktighet(
                källa="modul4_kontomatchning",
                belopp=bedömning.belopp,
                riktning=härled_riktning_modul4(bedömning, kontoplan),
                kontonr=bedömning.kontonr,
                kontonamn=kontonamn,
                motivering=bedömning.motivering or "",
                plats=bedömning.plats,
            )
        )
    return felaktigheter


def _troskelstatus(
    summa: Decimal, utfallsväsentlighet: Decimal, väsentlighetstal: Decimal
) -> Literal["grön", "gul", "röd"]:
    if summa < utfallsväsentlighet:
        return "grön"
    if summa > väsentlighetstal:
        return "röd"
    return "gul"


def ackumulera(
    felaktigheter: list[Felaktighet],
    utfallsväsentlighet: Decimal,
    väsentlighetstal: Decimal,
) -> AckumuleringsResultat:
    summa_brutto = sum((f.belopp for f in felaktigheter), start=Decimal("0"))
    summa_netto = sum(
        (
            f.belopp if f.riktning == "över"
            else -f.belopp if f.riktning == "under"
            else Decimal("0")
            for f in felaktigheter
        ),
        start=Decimal("0"),
    )
    antal_okänd_riktning = sum(1 for f in felaktigheter if f.riktning == "okänd")

    return AckumuleringsResultat(
        summa_netto=summa_netto,
        summa_brutto=summa_brutto,
        # Statusbedömningen sker mot absolutbeloppet av summa_netto — ett
        # stort netto-UNDERskott är lika allvarligt som ett lika stort
        # netto-ÖVERskott. Fältet summa_netto självt förblir signerat.
        status_netto=_troskelstatus(abs(summa_netto), utfallsväsentlighet, väsentlighetstal),
        status_brutto=_troskelstatus(summa_brutto, utfallsväsentlighet, väsentlighetstal),
        antal_felaktigheter=len(felaktigheter),
        antal_okänd_riktning=antal_okänd_riktning,
        felaktigheter=felaktigheter,
    )
