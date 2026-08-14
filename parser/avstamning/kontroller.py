"""avstamning.kontroller — A-01 … A-05.

Lager 1b, se hantverksbok/BOKSLUTSPROGRAMMET.md §4.5 steg 4. Registreras i
EXAKT samma register som lager 1:s K-01–K-15 — `bokslutskontroll.motor.
KONTROLLER` — via samma `registrera`-dekorator och samma `Fynd`-typ. En
avstämningsavvikelse och en bokslutsavvikelse är samma sak för användaren
och ska visas på samma sätt (§4.5).

Kontrollerna kör bara när `Kontext.utdrag` OCH `Kontext.avstamningskonto`
båda är satta — annars `[]` (§4.4: det finns ingen väg att stämma av ett
konto utan att användaren tillhandahåller källan och pekar ut kontot).
`avstamningskonto` måste dessutom finnas i registrets `avstamningsbara_
konton` — ett konto utanför den listan ger också `[]`, inte ett gissat
resultat.

Själva matchningslogiken — alla fyra passen, inklusive pass 3:s parkoppling
som ger A-03 — bor i `matchning.py` (§4.3/§4.3.1). Den här modulen gör bara
det sista steget: väver ihop en `Kontext` till listor `matcha()` kan ta emot,
och väver `Matchningsresultat` tillbaka till `Fynd`."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from bokslutskontroll.modell import Fynd, Kontext
from bokslutskontroll.motor import registrera
from bokslutskontroll.regelkalla import hamta_parameter

from .camt053 import Utdragsrad
from .matchning import matcha


def _verid(v) -> str:
    return f"{v.serie or ''}/{v.vernr or ''}"


def _bokforda_poster_med_verifikation(kontext: Kontext):
    """(Transaktion, Verifikation)-par för varje rad på avstämningskontot,
    i verifikationsordning."""
    par = []
    for v in kontext.sie.verifikationer:
        for t in v.transaktioner:
            if t.kontonr == kontext.avstamningskonto:
                par.append((t, v))
    return par


@dataclass(frozen=True)
class _Avstamningsdata:
    par: tuple  # tuple[tuple[Transaktion, Verifikation], ...]
    utdragsrader: tuple[Utdragsrad, ...]
    parkopplingar: tuple  # tuple[matchning.Parkoppling, ...]  — pass 3, A-03
    kvar_bokforda: tuple[int, ...]
    kvar_utdrag: tuple[int, ...]


def _berakna(kontext: Kontext) -> _Avstamningsdata | None:
    if kontext.utdrag is None or kontext.avstamningskonto is None:
        return None

    avstamningsbara = hamta_parameter("avstamningsbara_konton") or []
    if kontext.avstamningskonto not in avstamningsbara:
        return None

    fonster = hamta_parameter("matchningsfonster_dagar")
    beloppsdiff_kronor = hamta_parameter("avstamning_beloppsdiff_kronor")
    beloppsdiff_andel = hamta_parameter("avstamning_beloppsdiff_andel")
    if fonster is None or beloppsdiff_kronor is None or beloppsdiff_andel is None:
        return None

    par = _bokforda_poster_med_verifikation(kontext)
    bokforda = [t for t, _ in par]
    utdragsrader = list(kontext.utdrag.rader)

    resultat = matcha(
        bokforda,
        utdragsrader,
        matchningsfonster_dagar=fonster,
        avstamning_beloppsdiff_kronor=beloppsdiff_kronor,
        avstamning_beloppsdiff_andel=beloppsdiff_andel,
    )

    return _Avstamningsdata(
        par=tuple(par),
        utdragsrader=tuple(utdragsrader),
        parkopplingar=resultat.parkopplingar,
        kvar_bokforda=resultat.omatchade_bokforda,
        kvar_utdrag=resultat.omatchade_utdragsrader,
    )


@registrera("A-01")
def kontroll_a01(kontext: Kontext) -> list[Fynd]:
    data = _berakna(kontext)
    if data is None:
        return []

    fynd: list[Fynd] = []
    for j in data.kvar_utdrag:
        rad = data.utdragsrader[j]
        fynd.append(
            Fynd(
                kontroll_id="A-01",
                rubrik="Banktransaktion saknas i bokföringen",
                allvarlighet="avvikelse",
                motivering=(
                    f"Kontoutdraget har en rad daterad {rad.datum.isoformat()} på "
                    f"{rad.belopp} kr"
                    + (f" ({rad.text})" if rad.text else "")
                    + f" som saknar motsvarighet i bokföringen på konto {kontext.avstamningskonto}."
                ),
                konton=(kontext.avstamningskonto,),
                belopp=rad.belopp,
            )
        )
    return fynd


@registrera("A-02")
def kontroll_a02(kontext: Kontext) -> list[Fynd]:
    data = _berakna(kontext)
    if data is None:
        return []

    fynd: list[Fynd] = []
    for i in data.kvar_bokforda:
        transaktion, verifikation = data.par[i]
        datumtext = transaktion.transdat.isoformat() if transaktion.transdat else "okänt datum"
        fynd.append(
            Fynd(
                kontroll_id="A-02",
                rubrik="Bokförd post saknas på kontoutdraget",
                allvarlighet="observation",
                motivering=(
                    f"Verifikation {_verid(verifikation)} har en rad på konto "
                    f"{kontext.avstamningskonto} daterad {datumtext} på "
                    f"{transaktion.belopp} kr som saknar motsvarighet på kontoutdraget."
                ),
                konton=(kontext.avstamningskonto,),
                verifikationer=(_verid(verifikation),),
                belopp=transaktion.belopp,
            )
        )
    return fynd


@registrera("A-03")
def kontroll_a03(kontext: Kontext) -> list[Fynd]:
    """§4.3.1: en parkoppling är en gissning — motiveringen visar därför
    BÅDA radernas belopp och datum, aldrig bara skillnaden."""
    data = _berakna(kontext)
    if data is None:
        return []

    fynd: list[Fynd] = []
    for parkoppling in data.parkopplingar:
        transaktion, verifikation = data.par[parkoppling.bokford_index]
        rad = data.utdragsrader[parkoppling.utdrag_index]
        diff = transaktion.belopp - rad.belopp
        fynd.append(
            Fynd(
                kontroll_id="A-03",
                rubrik="Beloppet skiljer",
                allvarlighet="observation",
                motivering=(
                    f"Verifikation {_verid(verifikation)} daterad "
                    f"{transaktion.transdat.isoformat() if transaktion.transdat else 'okänt datum'} "
                    f"({transaktion.belopp} kr) och kontoutdragets rad daterad "
                    f"{rad.datum.isoformat()} ({rad.belopp} kr) parkopplades som samma "
                    f"händelse — skillnad {diff} kr. Detta är en gissning: bedöm om "
                    "parkopplingen är rimlig."
                ),
                konton=(kontext.avstamningskonto,),
                verifikationer=(_verid(verifikation),),
                belopp=diff,
            )
        )
    return fynd


@registrera("A-04")
def kontroll_a04(kontext: Kontext) -> list[Fynd]:
    if kontext.utdrag is None or kontext.avstamningskonto is None:
        return []
    if kontext.utdrag.utgaende_saldo is None:
        return []

    bokfort_ub = Decimal("0")
    for post in kontext.sie.utgående_balanser:
        if post.årsnr == kontext.arsnr and post.kontonr == kontext.avstamningskonto:
            bokfort_ub = post.saldo
            break

    diff = bokfort_ub - kontext.utdrag.utgaende_saldo
    if abs(diff) <= kontext.tolerans:
        return []

    return [
        Fynd(
            kontroll_id="A-04",
            rubrik="Utgående saldo stämmer inte",
            allvarlighet="avvikelse",
            motivering=(
                f"Bokfört utgående saldo på konto {kontext.avstamningskonto} är "
                f"{bokfort_ub} kr, men kontoutdragets slutsaldo är "
                f"{kontext.utdrag.utgaende_saldo} kr — skillnad {diff} kr."
            ),
            konton=(kontext.avstamningskonto,),
            belopp=diff,
        )
    ]


@registrera("A-05")
def kontroll_a05(kontext: Kontext) -> list[Fynd]:
    if kontext.utdrag is None or kontext.avstamningskonto is None:
        return []
    år = kontext.sie.räkenskapsår.get(kontext.arsnr)
    if år is None:
        return []

    start = kontext.utdrag.period_start
    slut = kontext.utdrag.period_slut
    if start is None or slut is None:
        return [
            Fynd(
                kontroll_id="A-05",
                rubrik="Kontoutdraget täcker inte hela räkenskapsåret",
                allvarlighet="upplysning",
                motivering=(
                    "Kontoutdragets period kunde inte fastställas, så avstämningen "
                    "kan inte bekräftas täcka hela räkenskapsåret."
                ),
                konton=(kontext.avstamningskonto,),
            )
        ]

    if start <= år.start and slut >= år.slut:
        return []

    return [
        Fynd(
            kontroll_id="A-05",
            rubrik="Kontoutdraget täcker inte hela räkenskapsåret",
            allvarlighet="upplysning",
            motivering=(
                f"Kontoutdraget täcker {start.isoformat()}–{slut.isoformat()}, men "
                f"räkenskapsåret är {år.start.isoformat()}–{år.slut.isoformat()}. "
                "Avstämningen är ofullständig och ska inte tolkas som ren."
            ),
            konton=(kontext.avstamningskonto,),
        )
    ]
