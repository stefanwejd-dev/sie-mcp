"""Grupp C — bokslutsposter: K-11, K-12.

Se hantverksbok/BOKSLUTSKONTROLLER.md §5, grupp C."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from domain_model import Saldopost, Verifikation

from ..modell import Fynd, Kontext
from ..motor import registrera
from ..regelkalla import hamta_parameter

_KOSTNAD_FRAN, _KOSTNAD_TILL = 4000, 7999
_PERIODISERING_FORDRAN = (1700, 1799)
_PERIODISERING_SKULD = (2900, 2999)


def _summa(poster: list[Saldopost], kontonr_fran: int, kontonr_till: int, arsnr: int) -> Decimal:
    return sum(
        (
            p.saldo
            for p in poster
            if p.årsnr == arsnr and kontonr_fran <= int(p.kontonr) <= kontonr_till
        ),
        start=Decimal("0"),
    )


def _verid(v: Verifikation) -> str:
    return f"{v.serie or ''}/{v.vernr or ''}"


def _har_periodiseringsmotpart(v: Verifikation) -> bool:
    for t in v.transaktioner:
        kontonr_int = int(t.kontonr)
        if _PERIODISERING_FORDRAN[0] <= kontonr_int <= _PERIODISERING_FORDRAN[1]:
            return True
        if _PERIODISERING_SKULD[0] <= kontonr_int <= _PERIODISERING_SKULD[1]:
            return True
    return False


@registrera("K-11")
def kontroll_k11(kontext: Kontext) -> list[Fynd]:
    # Väsentlighet ej beräknbar (t.ex. ingen omsättning) — kontrollen väljer
    # aldrig ett eget gränsvärde, den ger noll fynd (§7 steg 5, acceptans).
    if kontext.utfallsvasentlighet is None:
        return []

    sie = kontext.sie
    år = sie.räkenskapsår.get(kontext.arsnr)
    if år is None:
        return []

    fonster_dagar = hamta_parameter("periodiseringsfonster_dagar")
    if fonster_dagar is None:
        return []
    fonster_start = år.slut - timedelta(days=fonster_dagar)

    fynd: list[Fynd] = []
    for v in sie.verifikationer:
        if not (fonster_start <= v.verdatum <= år.slut):
            continue

        kostnadsrader = [
            t
            for t in v.transaktioner
            if _KOSTNAD_FRAN <= int(t.kontonr) <= _KOSTNAD_TILL
            and abs(t.belopp) >= kontext.utfallsvasentlighet
        ]
        if not kostnadsrader:
            continue

        if _har_periodiseringsmotpart(v):
            continue

        belopp = sum((t.belopp for t in kostnadsrader), start=Decimal("0"))
        fynd.append(
            Fynd(
                kontroll_id="K-11",
                rubrik="Kostnad nära årsskiftet utan periodiseringsmotpart",
                allvarlighet="upplysning",
                motivering=(
                    f"Verifikation {_verid(v)} ({v.verdatum.isoformat()}) har en kostnadsrad på "
                    f"{belopp} kr, inom {fonster_dagar} dagar före räkenskapsårets slut, utan "
                    "någon rad på ett periodiseringskonto (1700–1799 eller 2900–2999). "
                    "Frånvaron av en periodiseringsmotpart bevisar ingenting — den pekar bara "
                    "ut var en människa bör titta."
                ),
                konton=tuple(t.kontonr for t in kostnadsrader),
                verifikationer=(_verid(v),),
                belopp=belopp,
            )
        )
    return fynd


@registrera("K-12")
def kontroll_k12(kontext: Kontext) -> list[Fynd]:
    tillgångsintervall = hamta_parameter("anlaggningstillgangar_avskrivningsbara")
    avskrivningsintervall = hamta_parameter("avskrivningskonton")
    if tillgångsintervall is None or avskrivningsintervall is None:
        return []

    sie = kontext.sie
    avskrivning_summa = _summa(
        sie.resultat,
        int(avskrivningsintervall["fran"]),
        int(avskrivningsintervall["till"]),
        kontext.arsnr,
    )
    if avskrivning_summa != 0:
        return []

    fran = int(tillgångsintervall["fran"])
    till = int(tillgångsintervall["till"])

    fynd: list[Fynd] = []
    for post in sie.utgående_balanser:
        if post.årsnr != kontext.arsnr:
            continue
        if not (fran <= int(post.kontonr) <= till):
            continue
        if post.saldo == 0:
            continue
        fynd.append(
            Fynd(
                kontroll_id="K-12",
                rubrik="Anläggningstillgång utan årets avskrivning",
                allvarlighet="observation",
                motivering=(
                    f"Konto {post.kontonr} har utgående balans {post.saldo} kr, men inget "
                    f"saldo finns bokfört på avskrivningskontona {avskrivningsintervall['fran']}"
                    f"–{avskrivningsintervall['till']} under räkenskapsåret."
                ),
                konton=(post.kontonr,),
                belopp=post.saldo,
            )
        )
    return fynd
