"""avstamning.matchning — deterministisk fyrapassmatchning mellan bokförda
poster och kontoutdragets rader.

Lager 1b, se hantverksbok/BOKSLUTSPROGRAMMET.md §4.3/§4.3.1/§4.5 steg 3. Ren
funktion utan sidoeffekter — samma disciplin som B-2 i
hantverksbok/BOKSLUTSKONTROLLER.md kräver av en kontroll: inga sidoeffekter,
ingen I/O, ingen klocka, inget nätverk. Testbart med syntetiska listor,
reproducerbart utfall.

Fyra pass, **aldrig en språkmodell**:

1. **Exakt:** samma datum OCH samma belopp.
2. **Nära i tid:** samma belopp, datum inom ± `matchningsfonster_dagar`
   (endast pass 1:s omatchade rester prövas) — markerad `sakerhet="nara"`.
3. **Parkoppling (§4.3.1):** de rester som blir kvar efter pass 1–2 kan inte
   längre matchas på belopp — A-03 handlar per definition om olika belopp.
   Pass 3 parar därför ihop rester som TROLIGEN avser samma händelse: datum
   inom fönstret, **samma tecken**, och en beloppsskillnad inom
   `max(avstamning_beloppsdiff_kronor, avstamning_beloppsdiff_andel × |belopp|)`.
   ALDRIG på motpart eller text — de är fritext och maskeras på MCP-vägen;
   en kontroll som läser fritext skulle ge olika utfall i appen och via MCP
   för samma bokföring (§4.3.1). En parkoppling är en gissning: greedy,
   minsta relativa skillnad global vinnare först.
4. **Rest:** allt som fortfarande är omatchat. `kontroller.py` (steg 4) gör
   resten till A-01 (utdragsrad utan bokförd motsvarighet) respektive A-02
   (bokförd post utan utdragsrad).

Ett belopp matchas mot **exakt en** motpart genom ALLA fyra passen: två
bokförda poster på samma belopp och en enda utdragsrad ger en match och EN
rest, inte två matcher (§4.3)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol

from .camt053 import Utdragsrad


class BokfordPost(Protocol):
    """Vad matchningen kräver av en "bokförd post" — en strukturell typ, inte
    `domain_model.Transaktion` direkt. Matchning.py importerar inte hela
    domänmodellen och förblir testbart med enkla stand-ins; `kontroller.py`
    (steg 4) skickar in riktiga `Transaktion`-objekt, som redan har båda
    fälten."""

    transdat: date | None
    belopp: Decimal


@dataclass(frozen=True)
class Match:
    """Ett matchat par (pass 1 eller 2) — lika belopp. Index syftar in i de
    listor som skickades till `matcha()`."""

    bokford_index: int
    utdrag_index: int
    sakerhet: str  # "exakt" | "nara"


@dataclass(frozen=True)
class Parkoppling:
    """Ett parkopplat par (pass 3) — TROLIGEN samma händelse, olika belopp.
    En gissning (§4.3.1): `kontroller.py` ska visa båda radernas belopp i
    A-03-fyndets motivering, aldrig bara skillnaden."""

    bokford_index: int
    utdrag_index: int


@dataclass(frozen=True)
class Matchningsresultat:
    matchningar: tuple[Match, ...]
    parkopplingar: tuple[Parkoppling, ...]
    omatchade_bokforda: tuple[int, ...]
    omatchade_utdragsrader: tuple[int, ...]


def _pass3_parkoppling(
    bokforda_poster: list[BokfordPost],
    utdragsrader: list[Utdragsrad],
    obokforda: set[int],
    outdragna: set[int],
    *,
    matchningsfonster_dagar: int,
    avstamning_beloppsdiff_kronor: Decimal,
    avstamning_beloppsdiff_andel: Decimal,
) -> tuple[tuple[Parkoppling, ...], tuple[int, ...], tuple[int, ...]]:
    """§4.3.1. Referensbeloppet för andelsgränsen är den BOKFÖRDA postens
    belopp (den redan kända sidan) — inte kontoutdragets. "Minsta belopp" i
    tiebreak-ordningen läses som `abs(bokförd post.belopp)` och "tidigast
    datum" som den bokförda postens `transdat`; specen preciserar inte vilken
    sida av paret dessa syftar på, så valet är dokumenterat här i stället för
    gissat tyst."""
    kandidater: list[tuple[Decimal, date, Decimal, int, int]] = []
    for i in obokforda:
        post = bokforda_poster[i]
        if post.transdat is None or post.belopp == 0:
            continue
        for j in outdragna:
            rad = utdragsrader[j]
            if rad.belopp == 0:
                continue
            if abs((rad.datum - post.transdat).days) > matchningsfonster_dagar:
                continue
            if (post.belopp > 0) != (rad.belopp > 0):
                continue  # olika tecken — inte samma händelse
            diff = abs(post.belopp - rad.belopp)
            grans = max(
                avstamning_beloppsdiff_kronor,
                avstamning_beloppsdiff_andel * abs(post.belopp),
            )
            if diff > grans:
                continue
            relativ_skillnad = diff / abs(post.belopp)
            kandidater.append((relativ_skillnad, post.transdat, abs(post.belopp), j, i))

    # Girigt: minsta relativa skillnad vinner globalt, sedan tidigast datum,
    # sedan minsta belopp, sedan radordningen i utdraget (j) — §4.3.1.
    kandidater.sort(key=lambda k: (k[0], k[1], k[2], k[3]))

    parkopplingar: list[Parkoppling] = []
    anvanda_bokforda: set[int] = set()
    anvanda_utdrag: set[int] = set()
    for _relativ, _datum, _belopp, j, i in kandidater:
        if i in anvanda_bokforda or j in anvanda_utdrag:
            continue
        parkopplingar.append(Parkoppling(bokford_index=i, utdrag_index=j))
        anvanda_bokforda.add(i)
        anvanda_utdrag.add(j)

    kvar_bokforda = tuple(sorted(obokforda - anvanda_bokforda))
    kvar_utdrag = tuple(sorted(outdragna - anvanda_utdrag))
    return tuple(parkopplingar), kvar_bokforda, kvar_utdrag


def matcha(
    bokforda_poster: list[BokfordPost],
    utdragsrader: list[Utdragsrad],
    *,
    matchningsfonster_dagar: int,
    avstamning_beloppsdiff_kronor: Decimal,
    avstamning_beloppsdiff_andel: Decimal,
) -> Matchningsresultat:
    """Matchar bokförda poster mot kontoutdragets rader i de fyra passen i
    §4.3/§4.3.1.

    Alla tal tas som argument, aldrig som literaler här (B-4 i
    BOKSLUTSKONTROLLER.md) — anroparen hämtar dem ur regelregistret och
    skickar in dem, så att matchningen förblir en ren funktion utan egen
    kännedom om var konfigurationen bor."""
    obokforda = set(range(len(bokforda_poster)))
    outdragna = set(range(len(utdragsrader)))
    matchningar: list[Match] = []

    # Pass 1 — exakt: samma datum och samma belopp. Iterationen sker över en
    # FIXERAD ögonblicksbild av obokforda (sorted() kopierar), medan
    # outdragna läses om för varje post — det är det som gör att en post
    # aldrig matchas mot en utdragsrad som redan gått åt en tidigare post.
    for i in sorted(obokforda):
        post = bokforda_poster[i]
        if post.transdat is None:
            continue
        for j in sorted(outdragna):
            rad = utdragsrader[j]
            if rad.datum == post.transdat and rad.belopp == post.belopp:
                matchningar.append(Match(bokford_index=i, utdrag_index=j, sakerhet="exakt"))
                obokforda.discard(i)
                outdragna.discard(j)
                break

    # Pass 2 — nära i tid: samma belopp, datum inom fönstret. Bland flera
    # kandidater väljs den med minst dagsskillnad (ties bryts på index) —
    # deterministiskt, men inte uttryckligen föreskrivet av §4.3.
    for i in sorted(obokforda):
        post = bokforda_poster[i]
        if post.transdat is None:
            continue
        kandidater = [
            j
            for j in outdragna
            if utdragsrader[j].belopp == post.belopp
            and abs((utdragsrader[j].datum - post.transdat).days) <= matchningsfonster_dagar
        ]
        if not kandidater:
            continue
        j = min(kandidater, key=lambda j: (abs((utdragsrader[j].datum - post.transdat).days), j))
        matchningar.append(Match(bokford_index=i, utdrag_index=j, sakerhet="nara"))
        obokforda.discard(i)
        outdragna.discard(j)

    # Pass 3 — parkoppling (§4.3.1): olika belopp, TROLIGEN samma händelse.
    parkopplingar, obokforda_kvar, outdragna_kvar = _pass3_parkoppling(
        bokforda_poster,
        utdragsrader,
        obokforda,
        outdragna,
        matchningsfonster_dagar=matchningsfonster_dagar,
        avstamning_beloppsdiff_kronor=avstamning_beloppsdiff_kronor,
        avstamning_beloppsdiff_andel=avstamning_beloppsdiff_andel,
    )

    # Pass 4 — rest: vad som blir kvar efter pass 3.
    return Matchningsresultat(
        matchningar=tuple(matchningar),
        parkopplingar=parkopplingar,
        omatchade_bokforda=obokforda_kvar,
        omatchade_utdragsrader=outdragna_kvar,
    )
