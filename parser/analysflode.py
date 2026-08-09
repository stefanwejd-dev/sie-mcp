"""analysflode — orkestrerar Modul 1 (väsentlighet), Modul 2 (kontotyp),
Modul 4 (kontomatchning) och Modul 5 (ackumulering) till app.py:s Sektion 8.

Tunn orkestreringsnivå: ingen ny analyslogik, bara sekvensering av redan
testade byggstenar. Sekretessgränsen är avgörande — Modul 4 får ALDRIG se
annat än maskeringsresultat.sandningsbara_verifikationer, aldrig
sie.verifikationer direkt.

Arkitektbeslut (ursprungligen 2026-07-04; reviderat 2026-07-09, se
se ARCHITECTURE.md, avsnittet om Modul 5): tröskelvärdena föreslås numera som
TRANSPARENTA, redigerbara utgångsvärden — väsentlighetstal = 0,5 % av
omsättningen, utfallsväsentlighet = 75 % av det (berakna_standardtroskelvarden).
Procentsatserna och deras motivering visas öppet för revisorn (help-texter i
Sektion 8) och värdena kan alltid justeras manuellt. Skiftet från
"manuellt-tomt" behåller den ursprungliga principen — ingen DOLD procentsats,
ingen TYST policy — men lägger till ett pedagogiskt, härlett förslag som
revisorn äger och kan ändra. kor_analys tar fortfarande emot redan validerade
Decimal-argument.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from ackumulering import (
    AckumuleringsResultat,
    ackumulera,
    bygg_felaktigheter_fran_kontobedomningar,
    bygg_felaktigheter_fran_kontotypavvikelser,
)
from domain_model import SIEFil
from kontomatchning import bedöm_transaktioner
from kontotyp_vakt import analysera_kontotyper
from sekretesslager import Maskeringsresultat
from vasentlighet import Vasentlighetstal, berakna_vasentlighet


class TröskelvärdeFel(Exception):
    """Fail-closed-fel vid tolkning av manuellt inmatade tröskelvärden."""


def tolka_troskelvarden(
    utfallsväsentlighet_text: str, väsentlighetstal_text: str
) -> tuple[Decimal, Decimal]:
    """Tolkar användarens manuellt inmatade tröskelvärden. Fail-closed:
    tomt fält, ej tolkningsbart som tal, eller <= 0 ger TröskelvärdeFel.
    Ingen standardprocentsats används någonsin — värdena kommer alltid
    direkt från användarens egen bedömning."""
    try:
        utfallsväsentlighet = Decimal((utfallsväsentlighet_text or "").strip())
        väsentlighetstal = Decimal((väsentlighetstal_text or "").strip())
    except InvalidOperation as e:
        raise TröskelvärdeFel("Ange giltiga tal för båda tröskelvärdena.") from e

    if utfallsväsentlighet <= 0 or väsentlighetstal <= 0:
        raise TröskelvärdeFel("Tröskelvärdena måste vara större än noll.")

    return utfallsväsentlighet, väsentlighetstal


# Schabloner för de föreslagna (redigerbara) tröskelvärdena. Öppet redovisade
# procentsatser — inget döljs för revisorn.
VASENTLIGHET_PROCENT = Decimal("0.005")  # väsentlighetstal = 0,5 % av omsättningen
UTFALL_ANDEL = Decimal("0.75")           # utfallsväsentlighet = 75 % av väsentlighetstalet

VASENTLIGHETSTAL_HELP = (
    "Väsentlighetstalet är den beloppsnivå där ett fel bedöms kunna påverka en "
    "läsares beslut utifrån räkenskaperna. Förslaget är 0,5 % av omsättningen — "
    "en vanlig schablon i revisionspraxis (ISA 320), där omsättningen används "
    "som bas för resultatdrivna bolag eftersom den är stabil och svår att "
    "manipulera. Detta är ett utgångsvärde; justera fritt efter din egen "
    "professionella bedömning."
)
UTFALLSVASENTLIGHET_HELP = (
    "Utfallsväsentlighet (performance materiality) sätts LÄGRE än "
    "väsentlighetstalet — här 75 % av det — som en säkerhetsmarginal. Syftet är "
    "att summan av flera enskilt oväsentliga fel inte tillsammans ska kunna "
    "överstiga väsentlighetstalet utan att upptäckas. Justera fritt efter din "
    "professionella bedömning."
)


def berakna_standardtroskelvarden(omsattning: Decimal) -> tuple[Decimal, Decimal]:
    """Föreslår tröskelvärden ur omsättningen som TRANSPARENTA, redigerbara
    utgångsvärden (revisorn äger slutvärdet och kan alltid justera):

    - väsentlighetstal   = 0,5 % av omsättningen
    - utfallsväsentlighet = 75 % av väsentlighetstalet

    Avrundas till hela kronor. Returnerar (väsentlighetstal, utfallsväsentlighet).
    abs() på omsättningen är en ren skyddsåtgärd — tröskelvärden ska aldrig bli
    negativa oavsett hur basen råkar vara tecknad."""
    bas = abs(omsattning)
    väsentlighetstal = (bas * VASENTLIGHET_PROCENT).quantize(
        Decimal("1"), rounding=ROUND_HALF_UP
    )
    utfallsväsentlighet = (väsentlighetstal * UTFALL_ANDEL).quantize(
        Decimal("1"), rounding=ROUND_HALF_UP
    )
    return väsentlighetstal, utfallsväsentlighet


def belopp_fran_procent(procent: Decimal, bas: Decimal) -> Decimal:
    """Absolut belopp = procent % av bastalet, avrundat till hela kronor. Ren
    multiplikation — ingen division, så noll bas ger helt enkelt 0 kr."""
    return (bas * procent / Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def procent_fran_belopp(belopp: Decimal, bas: Decimal) -> Decimal | None:
    """Hur många procent (en decimal) beloppet utgör av bastalet. Bas = 0 ger
    None — procenten är då ODEFINIERAD (division med noll), aldrig en krasch och
    aldrig ett vilseledande 0 %."""
    if bas == 0:
        return None
    return (belopp / bas * Decimal("100")).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


@dataclass
class AnalysResultat:
    vasentlighetstal: Vasentlighetstal | None
    ackumulering: AckumuleringsResultat | None
    felmeddelande: str | None


def kor_analys(
    sie: SIEFil,
    maskeringsresultat: Maskeringsresultat,
    haiku_anropare: Callable[[list[dict], str | None], list[dict]],
    utfallsväsentlighet: Decimal,
    väsentlighetstal: Decimal,
) -> AnalysResultat:
    """Kör hela ISA 450-kedjan: Modul 1 + Modul 2 (på den oskyddade `sie`
    — numeriska saldon/#KTYP, ingen fritext) + Modul 4 (ENDAST på
    maskeringsresultat.sandningsbara_verifikationer) + Modul 5. Fail-closed
    vid ett oväntat internt fel i någon delmodul — ett statiskt, generiskt
    meddelande, aldrig rå exception-text."""
    # Fynd A: Modul 4 (och felaktighetsbygget) får kontonamn som når AI:n —
    # använd därför de MASKERADE kontonamnen, aldrig sie.konton (rå). Nyckeln
    # (kontonr) är oförändrad, så kontoplansvalideringen i kontomatchning
    # påverkas inte. berakna_vasentlighet/analysera_kontotyper arbetar däremot
    # på numeriska saldon/#KTYP i råa sie — ingen fritext, ingen PII.
    maskerade_konton = maskeringsresultat.maskerad_siefil.konton
    try:
        vasentlighetstal_resultat = berakna_vasentlighet(sie)
        avvikelser = analysera_kontotyper(sie)
        bedömningar = bedöm_transaktioner(
            maskeringsresultat.sandningsbara_verifikationer,
            maskerade_konton,
            haiku_anropare,
            prosa_kontext=maskeringsresultat.prosa_sandningsbar,
        )
    except Exception:
        return AnalysResultat(
            vasentlighetstal=None,
            ackumulering=None,
            felmeddelande="Kunde inte köra analysen. Kontrollera indata och försök igen.",
        )

    felaktigheter = bygg_felaktigheter_fran_kontotypavvikelser(
        avvikelser
    ) + bygg_felaktigheter_fran_kontobedomningar(bedömningar, maskerade_konton)

    return AnalysResultat(
        vasentlighetstal=vasentlighetstal_resultat,
        ackumulering=ackumulera(felaktigheter, utfallsväsentlighet, väsentlighetstal),
        felmeddelande=None,
    )
