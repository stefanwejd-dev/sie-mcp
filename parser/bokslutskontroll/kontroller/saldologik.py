"""Grupp B — saldologik och avstämning: K-07–K-10.

Se hantverksbok/BOKSLUTSKONTROLLER.md §5, grupp B. Kontolistor och marginaler
hämtas ur regelregistret via `hamta_parameter` (B-4) — inga literaler i
koden."""

from __future__ import annotations

from decimal import Decimal

from domain_model import Saldopost

from ..modell import Fynd, Kontext
from ..motor import registrera
from ..regelkalla import hamta_parameter


def _summa(poster: list[Saldopost], kontonr_fran: int, kontonr_till: int, arsnr: int) -> Decimal:
    return sum(
        (
            p.saldo
            for p in poster
            if p.årsnr == arsnr and kontonr_fran <= int(p.kontonr) <= kontonr_till
        ),
        start=Decimal("0"),
    )


def _saldo_for_konto(poster: list[Saldopost], kontonr: str, arsnr: int) -> Decimal:
    for p in poster:
        if p.årsnr == arsnr and p.kontonr == kontonr:
            return p.saldo
    return Decimal("0")


@registrera("K-08")
def kontroll_k08(kontext: Kontext) -> list[Fynd]:
    avrakningskonton = hamta_parameter("avrakningskonton") or []
    sie = kontext.sie

    fynd: list[Fynd] = []
    for kontonr in avrakningskonton:
        saldo = _saldo_for_konto(sie.utgående_balanser, kontonr, kontext.arsnr)
        if abs(saldo) <= kontext.tolerans:
            continue
        fynd.append(
            Fynd(
                kontroll_id="K-08",
                rubrik="Avräkningskonto har kvarvarande saldo",
                allvarlighet="observation",
                motivering=f"Avräkningskonto {kontonr} har utgående saldo {saldo} kr.",
                konton=(kontonr,),
                belopp=saldo,
            )
        )
    return fynd


@registrera("K-09")
def kontroll_k09(kontext: Kontext) -> list[Fynd]:
    debetnormala = hamta_parameter("debetnormala") or []
    kreditnormala = hamta_parameter("kreditnormala") or []
    sie = kontext.sie

    fynd: list[Fynd] = []
    for post in sie.utgående_balanser:
        if post.årsnr != kontext.arsnr:
            continue
        kontonr_int = int(post.kontonr)

        for intervall in debetnormala:
            if int(intervall["fran"]) <= kontonr_int <= int(intervall["till"]):
                if post.saldo < -kontext.tolerans:
                    fynd.append(
                        Fynd(
                            kontroll_id="K-09",
                            rubrik="Saldo på fel sida",
                            allvarlighet="observation",
                            motivering=(
                                f"Konto {post.kontonr} ({intervall.get('benamning', '')}) är "
                                f"normalt debetsaldo men har utgående saldo {post.saldo} kr "
                                "(kreditsaldo)."
                            ),
                            konton=(post.kontonr,),
                            belopp=post.saldo,
                        )
                    )
                break

        for intervall in kreditnormala:
            if int(intervall["fran"]) <= kontonr_int <= int(intervall["till"]):
                if post.saldo > kontext.tolerans:
                    fynd.append(
                        Fynd(
                            kontroll_id="K-09",
                            rubrik="Saldo på fel sida",
                            allvarlighet="observation",
                            motivering=(
                                f"Konto {post.kontonr} ({intervall.get('benamning', '')}) är "
                                f"normalt kreditsaldo men har utgående saldo {post.saldo} kr "
                                "(debetsaldo)."
                            ),
                            konton=(post.kontonr,),
                            belopp=post.saldo,
                        )
                    )
                break

    return fynd


@registrera("K-07")
def kontroll_k07(kontext: Kontext) -> list[Fynd]:
    sie = kontext.sie
    # Utgående moms ligger på balanskonton (2610–2639), inte resultatkonton.
    utgående_moms = -_summa(sie.utgående_balanser, 2610, 2639, kontext.arsnr)
    omsattning = -_summa(sie.resultat, 3000, 3799, kontext.arsnr)

    if omsattning <= 0:
        return []

    momssats_normal = hamta_parameter("momssats_normal")
    marginal = hamta_parameter("moms_marginal")
    if momssats_normal is None or marginal is None:
        return []

    kvot = utgående_moms / omsattning
    övre_grans = momssats_normal + marginal
    if Decimal("0") <= kvot <= övre_grans:
        return []

    return [
        Fynd(
            kontroll_id="K-07",
            rubrik="Utgående moms i orimlig proportion till omsättningen",
            allvarlighet="observation",
            motivering=(
                f"Utgående moms ({utgående_moms} kr) är {kvot:.2%} av nettoomsättningen "
                f"({omsattning} kr), utanför det rimliga intervallet [0, {övre_grans:.2%}]. "
                "Grov rimlighetskontroll — se registrets kommentar för K-07."
            ),
            konton=("2610", "3000"),
        )
    ]


@registrera("K-10")
def kontroll_k10(kontext: Kontext) -> list[Fynd]:
    sie = kontext.sie
    avgift = _summa(sie.resultat, 7510, 7519, kontext.arsnr)
    lon = _summa(sie.resultat, 7000, 7399, kontext.arsnr)

    if lon <= 0:
        return []

    år = sie.räkenskapsår.get(kontext.arsnr)
    if år is None:
        return []

    procent = hamta_parameter("arbetsgivaravgift_procent", ar=år.start.year)
    marginal = hamta_parameter("arbetsgivaravgift_marginal")
    if procent is None or marginal is None:
        # Fail-closed, men SYNLIGT. Att bara returnera [] vore att låta
        # kontrollen se ut att ha körts och godkänt lönekostnaderna, när den i
        # själva verket aldrig utfördes — samma sorts tysta ingenting som
        # VARFOR.md handlar om. Registret bär bara de år någon fyllt i, och
        # procentsatsen ändras i två lagar per år (se K-10:s kommentar), så
        # detta INTRÄFFAR — det är inte ett teoretiskt fall.
        saknas = "procentsats" if procent is None else "marginal"
        return [
            Fynd(
                kontroll_id="K-10",
                rubrik="Arbetsgivaravgiften kunde inte kontrolleras",
                allvarlighet="upplysning",
                motivering=(
                    f"Arbetsgivaravgiftens {saknas} för år {år.start.year} saknas i "
                    f"regelregistret. Kontrollen utfördes inte, och lönekostnaderna "
                    f"är alltså varken godkända eller underkända av den."
                ),
                konton=("7000", "7510"),
            )
        ]

    kvot = avgift / lon
    if abs(kvot - procent) <= marginal:
        return []

    return [
        Fynd(
            kontroll_id="K-10",
            rubrik="Arbetsgivaravgift i orimlig proportion till lön",
            allvarlighet="observation",
            motivering=(
                f"Arbetsgivaravgifter ({avgift} kr) är {kvot:.2%} av lönesumman ({lon} kr) för "
                f"räkenskapsåret {år.start.year}, mot förväntade {procent:.2%} "
                f"(± {marginal:.2%}). Grov rimlighetskontroll — se registrets kommentar för K-10."
            ),
            konton=("7000", "7510"),
        )
    ]
