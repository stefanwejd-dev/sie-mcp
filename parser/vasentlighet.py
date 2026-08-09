"""Väsentlighetsberäkning — se ARCHITECTURE.md, avsnitt "Väsentlighetsberäkning (Modul 1, beslutat)"."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from domain_model import Saldopost, SIEFil

INNEVARANDE_ÅR = 0

_OMSATTNING_KONTON = (3000, 3799)
_RESULTAT_KONTON = (3000, 8999)
_BALANSOMSLUTNING_KONTON = (1000, 1999)
_EGET_KAPITAL_UB_KONTON = (2010, 2099)


@dataclass
class Vasentlighetstal:
    omsattning: Decimal
    resultat: Decimal
    balansomslutning: Decimal
    eget_kapital: Decimal


def _summa_saldo(
    poster: list[Saldopost], konto_från: int, konto_till: int, årsnr: int = INNEVARANDE_ÅR
) -> Decimal:
    return sum(
        (post.saldo for post in poster if post.årsnr == årsnr and konto_från <= int(post.kontonr) <= konto_till),
        start=Decimal("0"),
    )


def berakna_vasentlighet(sie: SIEFil) -> Vasentlighetstal:
    resultat_totalt = _summa_saldo(sie.resultat, *_RESULTAT_KONTON)
    eget_kapital_ub = _summa_saldo(sie.utgående_balanser, *_EGET_KAPITAL_UB_KONTON)

    return Vasentlighetstal(
        omsattning=-_summa_saldo(sie.resultat, *_OMSATTNING_KONTON),
        resultat=-resultat_totalt,
        # Tillgångskonton (1000-1999) är debetnormala och lagras redan som positiva
        # tal i SIE4 — till skillnad från resultat/eget kapital (kreditnormala,
        # lagras negativt) ska balansomslutningen INTE negeras.
        balansomslutning=_summa_saldo(sie.utgående_balanser, *_BALANSOMSLUTNING_KONTON),
        eget_kapital=-(eget_kapital_ub + resultat_totalt),
    )
