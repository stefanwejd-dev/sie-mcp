"""Kontotyp-vakten — se ARCHITECTURE_tillagg_kontotyp_vakt.md, avsnitt "Kontotyp-vakten (Modul 2, beslutat)"."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from decimal import Decimal

from domain_model import Konto, SIEFil

_INTERNMONSTER_MIN_KONTON = 3

_REFERENSMONSTER_KLASS = {1: "T", 2: "S", 3: "I"}
_REFERENSMONSTER_KOSTNADSKLASSER = range(4, 8)  # klass 4-7 -> K
_ATERFORING_AV_NEDSKRIVNING_SERIE = range(776, 779)  # undantag: förväntas I, inte K

INNEVARANDE_ÅR = 0


@dataclass
class Kontotypavvikelse:
    kontonr: str
    kontonamn: str
    angiven_typ: str
    forvantad_typ: str
    lager: list[str]
    stod_internmonster: str | None
    motivering: str
    saldo: Decimal


def _konto_saldo(sie: SIEFil, kontonr: str) -> Decimal:
    # Gap 1: balansräkningskonton
    # (T/S) har sitt saldo i #UB, resultaträkningskonton (K/I) i #RES.
    # #IB (föregående års utgående balans) är sista utväg. Saknas kontot
    # i alla tre källor är saldo 0 — ett giltigt, inte ett fantasi-, värde.
    for poster in (sie.utgående_balanser, sie.resultat, sie.ingående_balanser):
        for post in poster:
            if post.kontonr == kontonr and post.årsnr == INNEVARANDE_ÅR:
                return post.saldo
    return Decimal("0")


def _forvantad_typ_referensmonster(kontonr: str) -> str | None:
    serie = int(kontonr[:3])
    if serie in _ATERFORING_AV_NEDSKRIVNING_SERIE:
        return "I"

    klass = int(kontonr[0])
    if klass in _REFERENSMONSTER_KLASS:
        return _REFERENSMONSTER_KLASS[klass]
    if klass in _REFERENSMONSTER_KOSTNADSKLASSER:
        return "K"
    return None  # klass 0, 8, 9 — medvetet exkluderad, se ARCHITECTURE_tillagg_kontotyp_vakt.md


def hitta_internmonster_avvikelser(sie: SIEFil) -> list[Kontotypavvikelse]:
    serier: dict[str, list[Konto]] = defaultdict(list)
    for konto in sie.konton.values():
        if konto.typ is not None:
            serier[konto.kontonr[:3]].append(konto)

    avvikelser: list[Kontotypavvikelse] = []
    for serie, konton_i_serien in serier.items():
        if len(konton_i_serien) < _INTERNMONSTER_MIN_KONTON:
            continue

        rostetal = Counter(konto.typ for konto in konton_i_serien)
        flest_roster = max(rostetal.values())
        majoritetstyper = [typ for typ, antal in rostetal.items() if antal == flest_roster]
        if len(majoritetstyper) != 1:
            continue  # oavgjort — serien skippas helt, ingen flaggning

        majoritetstyp = majoritetstyper[0]
        totalt = len(konton_i_serien)
        stod = f"{flest_roster}/{totalt}"

        for konto in konton_i_serien:
            if konto.typ == majoritetstyp:
                continue
            avvikelser.append(
                Kontotypavvikelse(
                    kontonr=konto.kontonr,
                    kontonamn=konto.namn,
                    angiven_typ=konto.typ,
                    forvantad_typ=majoritetstyp,
                    lager=["internmonster"],
                    stod_internmonster=stod,
                    motivering=(
                        f"{flest_roster} av {totalt} konton i serie {serie} har typ "
                        f"{majoritetstyp}, men {konto.kontonr} är kodat som {konto.typ}."
                    ),
                    saldo=_konto_saldo(sie, konto.kontonr),
                )
            )

    return avvikelser


def hitta_referensmonster_avvikelser(sie: SIEFil) -> list[Kontotypavvikelse]:
    avvikelser: list[Kontotypavvikelse] = []
    for konto in sie.konton.values():
        if konto.typ is None:
            continue

        forvantad = _forvantad_typ_referensmonster(konto.kontonr)
        if forvantad is None or forvantad == konto.typ:
            continue

        avvikelser.append(
            Kontotypavvikelse(
                kontonr=konto.kontonr,
                kontonamn=konto.namn,
                angiven_typ=konto.typ,
                forvantad_typ=forvantad,
                lager=["referensmonster"],
                stod_internmonster=None,
                motivering=(
                    f"Konto {konto.kontonr} tillhör en kontoklass/serie som enligt "
                    f"BAS-referensmönstret förväntas vara typ {forvantad}, men är kodat som {konto.typ}."
                ),
                saldo=_konto_saldo(sie, konto.kontonr),
            )
        )

    return avvikelser


def analysera_kontotyper(sie: SIEFil) -> list[Kontotypavvikelse]:
    per_konto: dict[str, Kontotypavvikelse] = {
        avvikelse.kontonr: avvikelse for avvikelse in hitta_internmonster_avvikelser(sie)
    }

    for avvikelse in hitta_referensmonster_avvikelser(sie):
        befintlig = per_konto.get(avvikelse.kontonr)
        if befintlig is None:
            per_konto[avvikelse.kontonr] = avvikelse
            continue

        per_konto[avvikelse.kontonr] = Kontotypavvikelse(
            kontonr=befintlig.kontonr,
            kontonamn=befintlig.kontonamn,
            angiven_typ=befintlig.angiven_typ,
            forvantad_typ=befintlig.forvantad_typ,
            lager=[*befintlig.lager, *avvikelse.lager],
            stod_internmonster=befintlig.stod_internmonster,
            motivering=f"{befintlig.motivering} {avvikelse.motivering}",
            saldo=befintlig.saldo,
        )

    return list(per_konto.values())
