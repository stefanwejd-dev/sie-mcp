"""Delad syntetisk SIEFil-byggare för bokslutskontroll-testerna.

Se hantverksbok/BOKSLUTSKONTROLLER.md §7, steg 2. Ingen fil läses — allt
byggs direkt som domain_model-objekt. Belopp anges som strängar och
konverteras till Decimal här, aldrig till float.

Standardanropet `bygg_sie()` ger en tom men balanserad bokföring: inga
konton, inga saldon, inga verifikationer. En tom mängd är balanserad per
definition, så en kontroll som vill pröva ett fynd måste själv lägga in det
underlag som gör bokföringen obalanserad."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from domain_model import Konto, Räkenskapsår, Saldopost, SIEFil, Transaktion, Verifikation


def _till_datum(varde: str) -> date:
    return date.fromisoformat(varde)


def _konto_namn(kontonr: str, konton: dict[str, str] | None) -> str:
    if konton and kontonr in konton:
        return konton[kontonr]
    return f"Konto {kontonr}"


def bygg_sie(
    *,
    konton: dict[str, str] | None = None,
    ib: dict[str, str] | None = None,
    ub: dict[str, str] | None = None,
    res: dict[str, str] | None = None,
    verifikationer: list[dict] | None = None,
    rakenskapsar: tuple[str, str] = ("2025-01-01", "2025-12-31"),
    foregaende_ub: dict[str, str] | None = None,
) -> SIEFil:
    ib = ib or {}
    ub = ub or {}
    res = res or {}
    foregaende_ub = foregaende_ub or {}
    verifikationer = verifikationer or []

    start = _till_datum(rakenskapsar[0])
    slut = _till_datum(rakenskapsar[1])

    räkenskapsår: dict[int, Räkenskapsår] = {0: Räkenskapsår(årsnr=0, start=start, slut=slut)}
    if foregaende_ub:
        try:
            föregående_start = start.replace(year=start.year - 1)
            föregående_slut = slut.replace(year=slut.year - 1)
        except ValueError:
            # 29 februari — förskjut till 28:e i skottårsfria fall.
            föregående_start = start.replace(year=start.year - 1, day=28)
            föregående_slut = slut.replace(year=slut.year - 1, day=28)
        räkenskapsår[-1] = Räkenskapsår(årsnr=-1, start=föregående_start, slut=föregående_slut)

    # Samla alla kontonummer som förekommer, så att varje konto som används
    # också finns i kontoplanen.
    alla_kontonr: set[str] = set(konton or {}) | set(ib) | set(ub) | set(res) | set(foregaende_ub)
    for verifikation in verifikationer:
        for rad in verifikation.get("rader", []):
            alla_kontonr.add(rad["kontonr"])

    kontoplan: dict[str, Konto] = {
        kontonr: Konto(kontonr=kontonr, namn=_konto_namn(kontonr, konton))
        for kontonr in sorted(alla_kontonr)
    }

    ingående_balanser = [
        Saldopost(årsnr=0, kontonr=kontonr, objektreferenser={}, saldo=Decimal(belopp))
        for kontonr, belopp in ib.items()
    ]
    utgående_balanser = [
        Saldopost(årsnr=0, kontonr=kontonr, objektreferenser={}, saldo=Decimal(belopp))
        for kontonr, belopp in ub.items()
    ] + [
        Saldopost(årsnr=-1, kontonr=kontonr, objektreferenser={}, saldo=Decimal(belopp))
        for kontonr, belopp in foregaende_ub.items()
    ]
    resultat = [
        Saldopost(årsnr=0, kontonr=kontonr, objektreferenser={}, saldo=Decimal(belopp))
        for kontonr, belopp in res.items()
    ]

    byggda_verifikationer: list[Verifikation] = []
    for verifikation in verifikationer:
        verdatum = _till_datum(verifikation["verdatum"])
        transaktioner = [
            Transaktion(
                kontonr=rad["kontonr"],
                belopp=Decimal(rad["belopp"]),
                objektreferenser={},
                transdat=_till_datum(rad["transdat"]) if rad.get("transdat") else None,
                transtext=rad.get("text"),
            )
            for rad in verifikation.get("rader", [])
        ]
        byggda_verifikationer.append(
            Verifikation(
                serie=verifikation.get("serie"),
                vernr=verifikation.get("vernr"),
                verdatum=verdatum,
                vertext=verifikation.get("vertext"),
                transaktioner=transaktioner,
            )
        )

    return SIEFil(
        sietyp=4,
        företagsnamn="Testbolaget AB",
        orgnr="5560000000",
        kontoplanstyp="BAS96",
        räkenskapsår=räkenskapsår,
        konton=kontoplan,
        ingående_balanser=ingående_balanser,
        utgående_balanser=utgående_balanser,
        resultat=resultat,
        verifikationer=byggda_verifikationer,
    )
