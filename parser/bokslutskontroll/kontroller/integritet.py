"""Grupp A — bokföringsteknisk integritet: K-01–K-06, K-13, K-15.

Se hantverksbok/BOKSLUTSKONTROLLER.md §5, grupp A. Varje kontrolls rättsliga
grund står i regelverk/regelregister.toml, inte här."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from domain_model import Saldopost, Verifikation

from ..modell import Fynd, Kontext
from ..motor import registrera

_BALANS_FRAN, _BALANS_TILL = 1000, 2999
_RESULTAT_FRAN, _RESULTAT_TILL = 3000, 8999


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


def _verid(v: Verifikation) -> str:
    return f"{v.serie or ''}/{v.vernr or ''}"


@registrera("K-01")
def kontroll_k01(kontext: Kontext) -> list[Fynd]:
    sie = kontext.sie
    balans = _summa(sie.utgående_balanser, _BALANS_FRAN, _BALANS_TILL, kontext.arsnr)
    resultat = _summa(sie.resultat, _RESULTAT_FRAN, _RESULTAT_TILL, kontext.arsnr)
    diff = balans + resultat
    if abs(diff) <= kontext.tolerans:
        return []
    return [
        Fynd(
            kontroll_id="K-01",
            rubrik="Balansräkningen går inte ihop",
            allvarlighet="avvikelse",
            motivering=(
                f"Summan av utgående balanskonton (1000–2999) och resultatkonton "
                f"(3000–8999) är {diff} kr, inte 0 kr."
            ),
            belopp=diff,
        )
    ]


@registrera("K-02")
def kontroll_k02(kontext: Kontext) -> list[Fynd]:
    fynd: list[Fynd] = []
    for v in kontext.sie.verifikationer:
        summa = sum((t.belopp for t in v.transaktioner), start=Decimal("0"))
        if abs(summa) <= kontext.tolerans:
            continue
        fynd.append(
            Fynd(
                kontroll_id="K-02",
                rubrik="Verifikation i obalans",
                allvarlighet="avvikelse",
                motivering=f"Verifikationens transaktioner summerar till {summa} kr, inte 0 kr.",
                verifikationer=(_verid(v),),
                belopp=summa,
            )
        )
    return fynd


@registrera("K-03")
def kontroll_k03(kontext: Kontext) -> list[Fynd]:
    sie = kontext.sie
    föregående_ub = [p for p in sie.utgående_balanser if p.årsnr == -1]
    if not föregående_ub:
        return []

    föregående_per_konto = {p.kontonr: p.saldo for p in föregående_ub}
    ingående_per_konto = {
        p.kontonr: p.saldo for p in sie.ingående_balanser if p.årsnr == kontext.arsnr
    }

    fynd: list[Fynd] = []
    for kontonr in sorted(set(föregående_per_konto) | set(ingående_per_konto)):
        if not (_BALANS_FRAN <= int(kontonr) <= _BALANS_TILL):
            continue
        ib = ingående_per_konto.get(kontonr, Decimal("0"))
        ub_föreg = föregående_per_konto.get(kontonr, Decimal("0"))
        diff = ib - ub_föreg
        if abs(diff) <= kontext.tolerans:
            continue
        fynd.append(
            Fynd(
                kontroll_id="K-03",
                rubrik="Ingående balans bryter mot föregående års utgående",
                allvarlighet="avvikelse",
                motivering=(
                    f"Ingående balans på konto {kontonr} är {ib} kr, men föregående "
                    f"räkenskapsårs utgående balans var {ub_föreg} kr."
                ),
                konton=(kontonr,),
                belopp=diff,
            )
        )
    return fynd


@registrera("K-04")
def kontroll_k04(kontext: Kontext) -> list[Fynd]:
    sie = kontext.sie
    if not sie.verifikationer:
        return []

    trans_per_konto: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for v in sie.verifikationer:
        for t in v.transaktioner:
            trans_per_konto[t.kontonr] += t.belopp

    ib_per_konto = {p.kontonr: p.saldo for p in sie.ingående_balanser if p.årsnr == kontext.arsnr}
    ub_per_konto = {p.kontonr: p.saldo for p in sie.utgående_balanser if p.årsnr == kontext.arsnr}
    res_per_konto = {p.kontonr: p.saldo for p in sie.resultat if p.årsnr == kontext.arsnr}

    fynd: list[Fynd] = []
    for kontonr, ub in ub_per_konto.items():
        if not (_BALANS_FRAN <= int(kontonr) <= _BALANS_TILL):
            continue
        ib = ib_per_konto.get(kontonr, Decimal("0"))
        beräknat = ib + trans_per_konto.get(kontonr, Decimal("0"))
        diff = ub - beräknat
        if abs(diff) <= kontext.tolerans:
            continue
        fynd.append(
            Fynd(
                kontroll_id="K-04",
                rubrik="Saldot stämmer inte med årets transaktioner",
                allvarlighet="avvikelse",
                motivering=(
                    f"Utgående balans på konto {kontonr} är {ub} kr, men ingående balans "
                    f"plus årets transaktioner ger {beräknat} kr."
                ),
                konton=(kontonr,),
                belopp=diff,
            )
        )

    for kontonr, res in res_per_konto.items():
        if not (_RESULTAT_FRAN <= int(kontonr) <= _RESULTAT_TILL):
            continue
        beräknat = trans_per_konto.get(kontonr, Decimal("0"))
        diff = res - beräknat
        if abs(diff) <= kontext.tolerans:
            continue
        fynd.append(
            Fynd(
                kontroll_id="K-04",
                rubrik="Saldot stämmer inte med årets transaktioner",
                allvarlighet="avvikelse",
                motivering=(
                    f"Resultatet på konto {kontonr} är {res} kr, men årets transaktioner "
                    f"summerar till {beräknat} kr."
                ),
                konton=(kontonr,),
                belopp=diff,
            )
        )
    return fynd


@registrera("K-05")
def kontroll_k05(kontext: Kontext) -> list[Fynd]:
    sie = kontext.sie
    ub_2099 = _saldo_for_konto(sie.utgående_balanser, "2099", kontext.arsnr)
    if ub_2099 == 0:
        return []

    resultat_summa = _summa(sie.resultat, _RESULTAT_FRAN, _RESULTAT_TILL, kontext.arsnr)
    resultat_8999 = _saldo_for_konto(sie.resultat, "8999", kontext.arsnr)
    förväntat = -(resultat_summa - resultat_8999)
    diff = ub_2099 - förväntat
    if abs(diff) <= kontext.tolerans:
        return []
    return [
        Fynd(
            kontroll_id="K-05",
            rubrik="Årets resultat stämmer inte mot resultaträkningen",
            allvarlighet="avvikelse",
            motivering=(
                f"Utgående balans på konto 2099 är {ub_2099} kr, men -(resultaträkningens "
                f"summa 3000–8999 exklusive konto 8999) ger {förväntat} kr."
            ),
            konton=("2099",),
            belopp=diff,
        )
    ]


@registrera("K-06")
def kontroll_k06(kontext: Kontext) -> list[Fynd]:
    sie = kontext.sie
    år = sie.räkenskapsår.get(kontext.arsnr)
    if år is None:
        return []

    fynd: list[Fynd] = []
    for v in sie.verifikationer:
        fel_datum = sorted(
            {
                t.transdat
                for t in v.transaktioner
                if t.transdat is not None and (t.transdat < år.start or t.transdat > år.slut)
            }
        )
        if not fel_datum:
            continue
        datum_text = ", ".join(d.isoformat() for d in fel_datum)
        fynd.append(
            Fynd(
                kontroll_id="K-06",
                rubrik="Transaktionsdatum utanför räkenskapsåret",
                allvarlighet="avvikelse",
                motivering=(
                    f"Verifikation {_verid(v)} har transaktionsdatum ({datum_text}) utanför "
                    f"räkenskapsåret {år.start.isoformat()}–{år.slut.isoformat()}."
                ),
                verifikationer=(_verid(v),),
            )
        )
    return fynd


@registrera("K-13")
def kontroll_k13(kontext: Kontext) -> list[Fynd]:
    per_serie: dict[str | None, list[Verifikation]] = defaultdict(list)
    for v in kontext.sie.verifikationer:
        if v.vernr is None or not v.vernr.isdigit():
            continue
        per_serie[v.serie].append(v)

    fynd: list[Fynd] = []
    for serie, verifikationer in per_serie.items():
        verifikationer = sorted(verifikationer, key=lambda v: int(v.vernr))
        nummer = [int(v.vernr) for v in verifikationer]

        par = list(zip(verifikationer, verifikationer[1:]))
        luckor = [
            (int(f.vernr), int(d.vernr)) for f, d in par if int(d.vernr) != int(f.vernr) + 1
        ]
        ordningsbrott = [(f, d) for f, d in par if d.verdatum < f.verdatum]

        # Bara ändpunkterna, inte hela serien. Fältet finns för att peka ut var
        # man ska titta; en serie med 2 000 verifikat och en lucka gav tidigare
        # 2 000 referenser i MCP-svaret och i tabellen — att peka på allt är
        # samma sak som att inte peka. Ordningen bevaras (I-5): dict.fromkeys
        # avdubblar utan att sortera om.
        berorda: list[str] = []
        for f, d in par:
            if int(d.vernr) != int(f.vernr) + 1 or d.verdatum < f.verdatum:
                berorda.extend((_verid(f), _verid(d)))

        if not luckor and not ordningsbrott:
            continue

        delar = []
        if luckor:
            delar.append("lucka mellan " + ", ".join(f"{a}→{b}" for a, b in luckor))
        if ordningsbrott:
            delar.append(
                "verifikationsdatum minskar mellan "
                + ", ".join(f"{_verid(f)}→{_verid(d)}" for f, d in ordningsbrott)
            )

        fynd.append(
            Fynd(
                kontroll_id="K-13",
                rubrik="Lucka eller ordningsbrott i verifikationsserie",
                allvarlighet="avvikelse",
                motivering=f"Serie {serie or '(utan serie)'}: " + "; ".join(delar) + ".",
                verifikationer=tuple(dict.fromkeys(berorda)),
            )
        )
    return fynd


@registrera("K-15")
def kontroll_k15(kontext: Kontext) -> list[Fynd]:
    grupper: dict[tuple, list[Verifikation]] = defaultdict(list)
    for v in kontext.sie.verifikationer:
        if not v.transaktioner:
            continue
        nyckel = (v.verdatum, tuple(sorted((t.kontonr, t.belopp) for t in v.transaktioner)))
        grupper[nyckel].append(v)

    fynd: list[Fynd] = []
    for (verdatum, _rader), verifikationer in grupper.items():
        if len(verifikationer) < 2:
            continue
        fynd.append(
            Fynd(
                kontroll_id="K-15",
                rubrik="Möjlig dubbelbokförd verifikation",
                allvarlighet="observation",
                motivering=(
                    f"{len(verifikationer)} verifikationer daterade {verdatum.isoformat()} "
                    "har identisk uppsättning konton och belopp."
                ),
                verifikationer=tuple(_verid(v) for v in verifikationer),
            )
        )
    return fynd
