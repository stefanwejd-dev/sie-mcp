"""fpa_motor — de rena räknemotorerna bakom FP&A-dashboarden.

HELT frikopplade: ingen datakälla, ingen klient, ingen async, ingen I/O och
ingen Streamlit. Funktionerna tar färdiga listor av konto-saldon eller färdiga
rapport-dictar och returnerar nya dictar. Det är därför exakt samma motorer
driver fil-vägen (en inläst SIEFil) och Spiris-vägen (live-API): båda matar in
samma sorts saldon.

Här bor all kunskap om BAS-intervall, SIE-tecken, svenska uppställningsregler
och finansiell matematik — aldrig i vy-lagret:

  bygg_resultatrapport      P&L enligt BAS
  bygg_balansrapport        balansräkning, med årets resultat inbakat i EK
  bygg_nyckeltal            svenska standardnyckeltal som kvoter
  bygg_kassaflodesanalys    indirekt metod, kontrolldiff = 0 by construction
  simulera_investering      what-if: EN finansieringskälla
  simulera_kapitalstack     what-if: flera källor samtidigt
  berakna_wacc              vägd kapitalkostnad, före och efter skatt
  berakna_kundbetalbeteende historiskt snitt dagar-för-sent per kund
  bygg_likviditetsprognos   dag-för-dag kassaprognos, 90 dagar framåt
  nasta_momsforfallodag     nästa standardförfallodag (den 12:e) för moms

Motorerna är display-fria: de formaterar aldrig ett belopp och skriver aldrig
en varningstext med siffror i. Fail-closed: okända indata höjer ValueError i
stället för att gissas.

Bröts ut ur spiris_rag.py, som numera bara innehåller de async RAG-verktyg som
hämtar och maskerar data åt en LLM. Motorerna hade inget med hämtning att göra.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Literal


# --- Resultatrapport (P&L) --------------------------------------------------

def _grupp_och_tecken(kontonr: int) -> tuple[str, int]:
    """Mappar ETT resultatkonto till sin P&L-grupp (för drill-down) och sitt
    display-tecken (för teckennormalisering). Här — inte i frontend — bor
    kunskapen om BAS-intervall och SIE-kredittecken.

    Tecknet vänds så att kontonivån matchar poster-raderna: intäkter positiva,
    kostnader positiva, finansiella poster som ett nettoresultat. Grupperna är en
    ren partition som reconcilierar mot poster (KSV + övriga rörelsekostnader +
    avskrivningar = totala kostnader). Avskrivningar prövas före den generella
    klass 4-7-hinken eftersom intervallet ligger inuti den."""
    if 3000 <= kontonr <= 3999:
        return "totala_intakter", -1
    if 4000 <= kontonr <= 4999:
        return "kostnad_salda_varor", 1
    if 7700 <= kontonr <= 7899:
        return "avskrivningar", 1
    if 4000 <= kontonr <= 7999:
        return "ovriga_rorelsekostnader", 1
    if 8000 <= kontonr <= 8499:
        return "finansnetto", -1
    if 8800 <= kontonr <= 8999:
        return "bokslutsdispositioner_skatt", 1
    return "ovrigt", 1


def bygg_resultatrapport(
    konto_perioder: list[dict], start_datum: str, slut_datum: str
) -> dict[str, Any]:
    """REN beräkningsmotor — helt frikopplad från datakällan (ingen klient,
    ingen fil, ingen async). Tar redan uträknade PERIODSALDON per konto
    (kontonr, kontonamn, saldo) och aggregerar en strukturerad BAS-P&L. Byt
    datakälla (SIE-fil idag, ERP-API imorgon) utan att röra motorn.

    Inkommande saldon är SIE-tecknade (klass 3 kreditnormal/negativ, klass 4-8
    debetnormal/positiv). Aggregaten (poster) räknas på dessa råa tecken, men
    kontonivån (konton) normaliseras — tecken vänds och en grupp sätts per konto
    — så att frontend kan förbli en helt 'dum' renderare."""
    resultatkonton = [k for k in konto_perioder if k["kontonr"][:1] in "345678"]

    def summa(från: int, till: int) -> Decimal:
        return sum(
            (k["saldo"] for k in resultatkonton if från <= int(k["kontonr"]) <= till),
            Decimal("0"),
        )

    totala_intakter = -summa(3000, 3999)
    kostnad_salda_varor = summa(4000, 4999)
    bruttovinst = totala_intakter - kostnad_salda_varor
    avskrivningar = summa(7700, 7899)
    # BAS 7810-7819: avskrivningar på IMMATERIELLA anläggningstillgångar (t.ex.
    # goodwill), en delmängd av avskrivningar-hinken ovan. Skiljer EBITA från
    # EBITDA: EBITDA lägger tillbaka ALLA av-/nedskrivningar, EBITA bara den
    # immateriella delen — materiella avskrivningar (maskiner, byggnader) belastar
    # fortfarande EBITA, precis som definitionen kräver.
    avskrivningar_immateriella = summa(7810, 7819)
    totala_kostnader = summa(4000, 7999)  # alla rörelsekostnader (klass 4-7)
    # Restposten (5000-7699 + 7900-7999): allt i totala_kostnader utom KSV och
    # avskrivningar. Matchar kontogruppen ovriga_rorelsekostnader så drill-down
    # blir helt dum — varje grupp har en poster-total.
    ovriga_rorelsekostnader = totala_kostnader - kostnad_salda_varor - avskrivningar
    # BAS 7000-7699: löner, sociala avgifter, pensioner och övriga personalkost-
    # nader. En delmängd av ovriga_rorelsekostnader ovan (ändrar alltså ingen
    # befintlig summa) — egen post för personalkostnad-nyckeltalet.
    personalkostnader = summa(7000, 7699)
    rorelseresultat = totala_intakter - totala_kostnader
    ebitda = rorelseresultat + avskrivningar
    ebita = rorelseresultat + avskrivningar_immateriella
    finansnetto = -summa(8000, 8499)  # intäkter positiva, kostnader minskar
    resultat_efter_finansiella = rorelseresultat + finansnetto
    bokslutsdispositioner_skatt = summa(8800, 8999)
    arets_resultat = resultat_efter_finansiella - bokslutsdispositioner_skatt

    if start_datum[:4] != slut_datum[:4]:
        info = (
            "VARNING: start_datum och slut_datum ligger i olika kalenderår. "
            "Resultatkonton nollställs vid räkenskapsårsskifte, så periodresultatet "
            "kan bli felaktigt (v1 hanterar inte korsande räkenskapsår)."
        )
    else:
        info = f"Periodresultat {start_datum} till {slut_datum}."

    # Normaliserad kontonivå för drill-down: tecken vänt + grupp satt, så en grupps
    # konton summerar exakt till sin poster-rad (frontend behöver bara loopa).
    konton_ut: list[dict] = []
    for k in resultatkonton:
        grupp, tecken = _grupp_och_tecken(int(k["kontonr"]))
        konton_ut.append(
            {
                "kontonr": k["kontonr"],
                "kontonamn": k.get("kontonamn", ""),
                "saldo": tecken * k["saldo"],
                "grupp": grupp,
            }
        )

    return {
        "period": {"start_datum": start_datum, "slut_datum": slut_datum},
        "poster": {
            "totala_intakter": totala_intakter,
            "kostnad_salda_varor": kostnad_salda_varor,
            "bruttovinst": bruttovinst,
            "ovriga_rorelsekostnader": ovriga_rorelsekostnader,
            "personalkostnader": personalkostnader,
            "totala_kostnader": totala_kostnader,
            "avskrivningar": avskrivningar,
            "avskrivningar_immateriella": avskrivningar_immateriella,
            "ebitda": ebitda,
            "ebita": ebita,
            "rorelseresultat": rorelseresultat,
            "finansnetto": finansnetto,
            "resultat_efter_finansiella": resultat_efter_finansiella,
            "bokslutsdispositioner_skatt": bokslutsdispositioner_skatt,
            "arets_resultat": arets_resultat,
        },
        "konton": konton_ut,
        "antal_exkluderade": 0,
        "info": info,
    }


# --- Balansräkning ----------------------------------------------------------

def _grupp_och_tecken_balans(kontonr: int) -> tuple[str, int]:
    """BAS-grupp + display-tecken för ETT balanskonto (klass 1-2). Tillgångar
    (klass 1) är debetnormala/positiva och behålls; eget kapital och skulder
    (klass 2) är kreditnormala/negativa och vänds till positivt. Precis som i
    resultatrapporten bor kunskapen om BAS-intervall och SIE-tecken här, inte i
    frontend."""
    if 1000 <= kontonr <= 1099:
        return "immateriella_anlaggningstillgangar", 1
    if 1100 <= kontonr <= 1299:
        return "materiella_anlaggningstillgangar", 1
    if 1300 <= kontonr <= 1399:
        return "finansiella_anlaggningstillgangar", 1
    if 1400 <= kontonr <= 1499:
        return "varulager", 1
    if 1500 <= kontonr <= 1799:
        return "kortfristiga_fordringar", 1
    if 1800 <= kontonr <= 1999:
        return "kassa_och_bank", 1  # inkl. kortfristiga placeringar 1800-1899
    if 2000 <= kontonr <= 2099:
        return "eget_kapital", -1
    if 2100 <= kontonr <= 2199:
        return "obeskattade_reserver", -1
    if 2200 <= kontonr <= 2299:
        return "avsattningar", -1
    if 2300 <= kontonr <= 2399:
        return "langfristiga_skulder", -1
    if 2400 <= kontonr <= 2999:
        return "kortfristiga_skulder", -1
    return "ovrigt", 1


def _undergrupp_balans(kontonr: int) -> str:
    """BAS-kontogrupp (den 2-siffriga nivån) för ETT balanskonto: 12 = maskiner
    och inventarier, 15 = kundfordringar, 19 = kassa och bank, och så vidare.

    En nivå finare än _grupp_och_tecken_balans, som slår ihop dem till
    uppställningens huvudposter. Kunskapen om BAS-nivåerna bor här i motorn, inte
    i frontend — vyn grupperar bara på den nyckel den får."""
    return str(kontonr // 100)


# BAS-serier för moms. Utgående moms (skuld) ligger i 261x, ingående moms
# (fordran) i 264x, och 2650 är avräkningskontot där nettot samlas.
MOMS_UTGAENDE = "261"
MOMS_INGAENDE = "264"
MOMS_AVRAKNING = "2650"


# --- Reskontraanalys: åldersanalys och påminnelseförslag --------------------

# Åldersintervall i dagar efter förfallodag. Klassisk indelning; gränserna är
# konstanter så att en vy kan visa dem utan att duplicera dem.
ALDERSINTERVALL = ((0, 30), (31, 60), (61, 90), (91, None))

# Hur många dagar en kund får överskrida sitt EGET mönster innan posten blir
# röd. Utan marginal blir en kund som normalt betalar 12 dagar sent röd redan
# på dag 13, vilket gör hela listan röd varje dag.
PAMINNELSE_MARGINAL_DAGAR = 3


def bygg_aldersanalys(poster: list, idag: date) -> dict[str, Any]:
    """Grupperar öppna poster efter hur länge de varit förfallna.

    `poster` är Kundpost/Leverantorspost — funktionen läser bara `belopp` och
    `forfallodatum`, så den fungerar för båda. Poster utan förfallodatum
    hamnar i "okänt" i stället för att tyst räknas som ej förfallna."""
    hinkar: dict[str, dict[str, Any]] = {}
    for fran, till in ALDERSINTERVALL:
        etikett = f"{fran}–{till}" if till else f"{fran}+"
        hinkar[etikett] = {"antal": 0, "belopp": Decimal("0")}
    hinkar["ej_forfallna"] = {"antal": 0, "belopp": Decimal("0")}
    hinkar["okant"] = {"antal": 0, "belopp": Decimal("0")}

    for post in poster:
        belopp = abs(post.belopp)
        if post.forfallodatum is None:
            hink = "okant"
        else:
            dagar = (idag - post.forfallodatum).days
            if dagar <= 0:
                hink = "ej_forfallna"
            else:
                hink = next(
                    (f"{f}–{t}" if t else f"{f}+")
                    for f, t in ALDERSINTERVALL
                    if (t is None and dagar >= f) or (t is not None and f <= dagar <= t)
                )
        hinkar[hink]["antal"] += 1
        hinkar[hink]["belopp"] += belopp

    return {
        "per_datum": idag.isoformat(),
        "hinkar": hinkar,
        "totalt_belopp": sum((abs(p.belopp) for p in poster), Decimal("0")),
        "totalt_antal": len(poster),
    }


def bygg_paminnelseforslag(
    kundposter: list,
    kundbetalbeteende: dict[str, Decimal] | None,
    idag: date,
    marginal_dagar: int = PAMINNELSE_MARGINAL_DAGAR,
) -> dict[str, Any]:
    """Delar förfallna kundfakturor i två grupper efter kundens EGET mönster.

    Den bärande idén: absoluta dagar säger lite. En kund som alltid betalar 12
    dagar sent är inte ett problem på dag 5 — men en kund som alltid betalar i
    tid och nu är 5 dagar sen är en tidig varningssignal som en vanlig
    reskontralista missar helt.

        röd  — dagar_forsent > normal + marginal   (kunden har brutit sitt mönster)
        gul  — dagar_forsent > 0, men inom mönstret (förfallen, men väntat)

    **Kund utan känd betalhistorik hamnar i RÖD** (arkitektbeslut B1) och
    märks `saknar_historik`. En ny kund som inte betalar är värd att kontakta,
    och att tyst lägga den i gult vore att dölja den.

    Rangordning inom varje grupp: belopp × dagar över mönstret. Det lyfter en
    stor faktura som precis brutit mönstret över en liten som är kroniskt sen.
    """
    beteende = kundbetalbeteende or {}
    rod: list[dict] = []
    gul: list[dict] = []

    for post in kundposter:
        if post.forfallodatum is None:
            continue
        dagar_forsent = (idag - post.forfallodatum).days
        if dagar_forsent <= 0:
            continue

        normal = beteende.get(post.motpart_id)
        saknar_historik = normal is None
        normal_dagar = Decimal("0") if saknar_historik else Decimal(str(normal))
        overskott = Decimal(dagar_forsent) - normal_dagar

        rad = {
            "kund": post.kund,
            "belopp": abs(post.belopp),
            "forfallodatum": post.forfallodatum,
            "dagar_forsent": dagar_forsent,
            "normalt_monster_dagar": None if saknar_historik else normal_dagar,
            "dagar_over_monster": overskott,
            "saknar_historik": saknar_historik,
            "motpart_id": post.motpart_id,
            # Prioritet: stort belopp som precis brutit mönstret först.
            "prioritet": abs(post.belopp) * max(overskott, Decimal("1")),
        }

        if saknar_historik or overskott > marginal_dagar:
            rod.append(rad)
        else:
            gul.append(rad)

    nyckel = lambda r: r["prioritet"]  # noqa: E731
    return {
        "per_datum": idag.isoformat(),
        "marginal_dagar": marginal_dagar,
        "rod": sorted(rod, key=nyckel, reverse=True),
        "gul": sorted(gul, key=nyckel, reverse=True),
        "rod_belopp": sum((r["belopp"] for r in rod), Decimal("0")),
        "gul_belopp": sum((r["belopp"] for r in gul), Decimal("0")),
    }


def bygg_momsoversikt(konton_saldon: list[dict], per_datum: str) -> dict[str, Any]:
    """BERÄKNAD momsöversikt ur kontosaldon — INTE en momsdeklaration.

    Härleder utgående moms (261x), ingående moms (264x) och nettot per ett
    datum. Detta är en summering av bokförda saldon, ingenting annat:

    - Den tar inte hänsyn till periodisering, omvänd skattskyldighet, EU-handel,
      import, vinstmarginalbeskattning eller korrigeringar.
    - Den vet inte vilken redovisningsperiod som gäller för bolaget.
    - Den är inte avstämd mot Skatteverket och kan skilja sig från vad som
      faktiskt ska deklareras.

    Den som vill se vad som FAKTISKT deklarerats ska läsa de inlämnade
    rapporterna (`spiris_adapter.hamta_momsrapporter`) — det är två olika saker
    och får aldrig blandas ihop.

    Teckenkonvention: momsskuld bokförs som kredit (negativt saldo i SIE), så
    utgående moms vänds till ett positivt skuldbelopp. Ingående moms är debet
    (positivt) och redovisas som positiv fordran. `att_betala` är utgående minus
    ingående — positivt = att betala in, negativt = att få tillbaka."""
    utgaende = Decimal("0")
    ingaende = Decimal("0")
    avrakning = Decimal("0")
    rader: list[dict] = []

    for konto in konton_saldon:
        kontonr = str(konto.get("kontonr") or "")
        saldo = konto.get("saldo") or Decimal("0")
        if kontonr == MOMS_AVRAKNING:
            avrakning += saldo
            grupp = "avrakning"
        elif kontonr.startswith(MOMS_UTGAENDE):
            utgaende += -saldo  # kredit -> positiv skuld
            grupp = "utgaende"
        elif kontonr.startswith(MOMS_INGAENDE):
            ingaende += saldo
            grupp = "ingaende"
        else:
            continue
        rader.append(
            {
                "kontonr": kontonr,
                "kontonamn": konto.get("kontonamn") or "",
                "saldo": saldo,
                "grupp": grupp,
            }
        )

    return {
        "per_datum": per_datum,
        "poster": {
            "utgaende_moms": utgaende,
            "ingaende_moms": ingaende,
            "att_betala": utgaende - ingaende,
            "momsavrakning": avrakning,
        },
        "konton": sorted(rader, key=lambda r: r["kontonr"]),
        "ar_deklaration": False,
        "info": (
            "BERÄKNAD översikt ur bokförda saldon — inte en momsdeklaration. "
            "Tar inte hänsyn till periodisering, omvänd skattskyldighet, "
            "EU-handel eller korrigeringar, och är inte avstämd mot "
            "Skatteverket. Kontrollera mot bokföringen innan den används."
        ),
    }


def bygg_balansrapport(konton_saldon: list[dict], per_datum: str) -> dict[str, Any]:
    """REN balansmotor — frikopplad från datakällan (ingen klient, ingen fil,
    ingen async). Tar utgående saldon per konto (klass 1-8) vid EN tidpunkt och
    aggregerar en strukturerad BAS-balansräkning.

    Årets resultat (klass 3-8) räknas dynamiskt och bakas in som en egen rad
    under Eget kapital, så att debet = kredit oavsett om filen är löpande
    (resultatet ligger kvar på resultatkonton) eller bokslutsförd (resultatet
    redan konterat mot 2099, klass 3-8 = 0). kontrolldiff bevisar balansen.

    Inkommande saldon är SIE-tecknade; kontonivån normaliseras (tecken vänt +
    grupp satt) så frontend förblir en 'dum' renderare."""

    def summa(från: int, till: int) -> Decimal:
        return sum(
            (k["saldo"] for k in konton_saldon if från <= int(k["kontonr"]) <= till),
            Decimal("0"),
        )

    # Årets resultat = -Σ(klass 3-8): positivt för vinst, matchar EK-sidans tecken.
    arets_resultat = -summa(3000, 8999)

    immateriella = summa(1000, 1099)
    materiella = summa(1100, 1299)
    finansiella = summa(1300, 1399)
    summa_anlaggning = immateriella + materiella + finansiella
    varulager = summa(1400, 1499)
    kortfr_fordringar = summa(1500, 1799)
    kassa_och_bank = summa(1800, 1999)
    summa_omsattning = varulager + kortfr_fordringar + kassa_och_bank
    summa_tillgangar = summa_anlaggning + summa_omsattning

    # EK/skulder vänds till positivt (-1); årets resultat bakas in i eget kapital.
    eget_kapital = -summa(2000, 2099) + arets_resultat
    obeskattade_reserver = -summa(2100, 2199)
    avsattningar = -summa(2200, 2299)
    langfristiga_skulder = -summa(2300, 2399)
    kortfristiga_skulder = -summa(2400, 2999)
    summa_ek_och_skulder = (
        eget_kapital
        + obeskattade_reserver
        + avsattningar
        + langfristiga_skulder
        + kortfristiga_skulder
    )

    kontrolldiff = summa_tillgangar - summa_ek_och_skulder

    # Normaliserad kontonivå: bara balanskonton (klass 1-2) + inbakad resultatrad.
    konton_ut: list[dict] = []
    for k in konton_saldon:
        n = int(k["kontonr"])
        if not 1000 <= n <= 2999:
            continue
        grupp, tecken = _grupp_och_tecken_balans(n)
        konton_ut.append(
            {
                "kontonr": k["kontonr"],
                "kontonamn": k.get("kontonamn", ""),
                "saldo": tecken * k["saldo"],
                "grupp": grupp,
                "undergrupp": _undergrupp_balans(n),
            }
        )
    konton_ut.append(
        {
            "kontonr": "8999",
            "kontonamn": "Årets resultat",
            "saldo": arets_resultat,
            "grupp": "eget_kapital",
            # Syntetisk rad, inte ett BAS-balanskonto: den hör hemma i eget
            # kapital (BAS 20), inte i sin egen kontogrupp 89.
            "undergrupp": "20",
        }
    )

    if kontrolldiff != 0:
        info = (
            f"VARNING: balansräkningen balanserar inte (kontrolldiff={kontrolldiff}). "
            "Debet och kredit går inte ihop — kontrollera datakällan."
        )
    else:
        info = f"Balansräkning per {per_datum} (balanserar, kontrolldiff = 0)."

    return {
        "per_datum": per_datum,
        "poster": {
            "immateriella_anlaggningstillgangar": immateriella,
            "materiella_anlaggningstillgangar": materiella,
            "finansiella_anlaggningstillgangar": finansiella,
            "summa_anlaggningstillgangar": summa_anlaggning,
            "varulager": varulager,
            "kortfristiga_fordringar": kortfr_fordringar,
            "kassa_och_bank": kassa_och_bank,
            "summa_omsattningstillgangar": summa_omsattning,
            "summa_tillgangar": summa_tillgangar,
            "eget_kapital": eget_kapital,
            "arets_resultat": arets_resultat,
            "obeskattade_reserver": obeskattade_reserver,
            "avsattningar": avsattningar,
            "langfristiga_skulder": langfristiga_skulder,
            "kortfristiga_skulder": kortfristiga_skulder,
            "summa_eget_kapital_och_skulder": summa_ek_och_skulder,
            "kontrolldiff": kontrolldiff,
        },
        "konton": konton_ut,
        "antal_exkluderade": 0,
        "info": info,
    }


# --- What-If: simulerad investering -----------------------------------------

# De finansieringsformer användaren kan välja i dashboardens what-if-reglage.
# Ordningen styr selectboxen; strängarna är motorns kontrakt (fail-closed).
FINANSIERINGSKALLOR: list[str] = [
    "Långfristiga skulder",
    "Kortfristiga skulder",
    "Minskning av kassa/bank",
    "Eget kapital",
]

# Vilken skuld-/kapitalpost som växer när investeringen finansieras därifrån.
# "Minskning av kassa/bank" saknas medvetet: den finansieras på tillgångssidan.
_FINANSIERINGSPOST: dict[str, str] = {
    "Långfristiga skulder": "langfristiga_skulder",
    "Kortfristiga skulder": "kortfristiga_skulder",
    "Eget kapital": "eget_kapital",
}


def simulera_investering(
    balansrapport: dict, belopp: Decimal | int, finansieringskalla: str
) -> dict[str, Any]:
    """REN what-if-motor: projicerar en hypotetisk investering på en FÄRDIG
    balansrapport och returnerar en ny rapport. Muterar inte originalet.

    Investeringen aktiveras alltid som en materiell anläggningstillgång (t.ex.
    en serverhall). Motparten avgörs av finansieringskällan: en skuld- eller
    kapitalpost växer lika mycket (balansomslutningen ökar), eller så minskar
    kassan (balansomslutningen är oförändrad — tillgångarna byter bara form).
    Dubbel bokföring håller by construction: kontrolldiff förblir 0.

    Resultatet är en projektion på POSTNIVÅ och saknar därför medvetet nyckeln
    "konton": en simulerad investering kan inte hänföras till enskilda konton,
    och en oförändrad drill-down under en förändrad summa vore en lögn. Använd
    originalrapporten för drill-down.

    Fail-closed: okänd finansieringskälla och negativa belopp höjer ValueError —
    motorn gissar aldrig. En kassafinansiering större än kassan tillåts
    (bokföringsmässigt möjlig) men flaggas i "varning"."""
    belopp = Decimal(belopp)
    if belopp < 0:
        raise ValueError(f"Investeringsbeloppet får inte vara negativt: {belopp}")
    if finansieringskalla not in FINANSIERINGSKALLOR:
        raise ValueError(f"Okänd finansieringskälla: {finansieringskalla!r}")

    poster = dict(balansrapport["poster"])
    poster["materiella_anlaggningstillgangar"] += belopp
    poster["summa_anlaggningstillgangar"] += belopp

    varning = None
    if finansieringskalla == "Minskning av kassa/bank":
        poster["kassa_och_bank"] -= belopp
        poster["summa_omsattningstillgangar"] -= belopp
        if poster["kassa_och_bank"] < 0:
            # Ingen sifferformatering här: motorn är display-fri. Vy-lagret
            # lägger till det formaterade beloppet ur poster["kassa_och_bank"].
            varning = (
                "Investeringen är större än kassan och ger en negativ kassa. "
                "Bokföringsmässigt möjligt, men i praktiken krävs extern "
                "finansiering."
            )
    else:
        poster[_FINANSIERINGSPOST[finansieringskalla]] += belopp
        poster["summa_tillgangar"] += belopp
        poster["summa_eget_kapital_och_skulder"] += belopp

    poster["kontrolldiff"] = (
        poster["summa_tillgangar"] - poster["summa_eget_kapital_och_skulder"]
    )

    return {
        "per_datum": balansrapport["per_datum"],
        "poster": poster,
        "simulering": {"belopp": belopp, "finansieringskalla": finansieringskalla},
        "varning": varning,
        "info": balansrapport["info"],
    }


# --- Nyckeltal / KPI:er -----------------------------------------------------

# Svensk bolagsskatt. Används på två ställen som måste hålla ihop: den dolda
# ägarandelen i obeskattade reserver (JEK) och skatteskölden på räntekostnader
# i WACC. En enda konstant, så de aldrig kan glida isär.
BOLAGSSKATT = Decimal("0.206")

# 79,4 % av obeskattade reserver räknas som dolt eget kapital (JEK) — resten är
# latent bolagsskatt.
_JEK_ANDEL = Decimal("1") - BOLAGSSKATT


def _kvot(täljare: Decimal, nämnare: Decimal) -> Decimal | None:
    """Kvot täljare/nämnare, eller None om nämnaren är noll — odefinierat är en
    ärligare signal än 0 (0 % marginal ≠ vilande bolag)."""
    if nämnare == 0:
        return None
    return täljare / nämnare


def personalkostnad_per_anstalld(
    personalkostnader: Decimal, antal_anstallda: int | Decimal | None
) -> Decimal | None:
    """Personalkostnader / antal anställda. Egen, publik funktion (inte bara ett
    fält inuti bygg_nyckeltal) eftersom antal anställda inte finns i SIE4 — talet
    måste anges av användaren i UI:t, EFTER att nyckeltalsrapporten redan är
    byggd. Vy-lagret räknar om just den här kvoten live när fältet fylls i, och
    ska då använda SAMMA formel som motorn — inte en egen kopia av matten.

    None om antal_anstallda inte angetts eller är 0 (odefinierad kvot, inte en
    påhittad nolla)."""
    if antal_anstallda is None:
        return None
    return _kvot(personalkostnader, Decimal(antal_anstallda))


def bygg_nyckeltal(
    resultatrapport: dict,
    balansrapport: dict,
    kassaflodesanalys: dict | None = None,
    antal_anstallda: int | Decimal | None = None,
) -> dict[str, Any]:
    """REN, frikopplad KPI-motor: tar de FÄRDIGA P&L- och balans-dictarna och
    räknar svenska standardnyckeltal som KVOTER (Decimal) — frontend formaterar
    till procent eller multipel. Bygger inte om något: läser bara redan
    uträknade, teckennormaliserade poster.

    Soliditet beräknas i två varianter: klassisk (bokfört EK) och justerad (JEK,
    inkl. dold del av obeskattade reserver). Odefinierade kvoter (nämnare = 0)
    returneras som None.

    Två nyckeltal kräver data UTÖVER de två färdiga rapporterna och är därför
    valfria parametrar, None om de inte ges:

    - fritt_kassaflode behöver kassaflödesanalysen (två balansräkningar, start
      och slut) — en enskild balansrapport räcker inte. Saknas den (t.ex. i ett
      what-if-scenario utan tidsdimension) blir nyckeltalet None, men det räknas
      INTE som en "nämnare saknas"-brist i info-texten: det är data som aldrig
      gavs in, inte en kvot som gick sönder.
    - personalkostnad_per_anstalld behöver antal anställda, som SIE4 inte
      innehåller alls (den siffran finns bara i årsredovisningens förvaltnings-
      berättelse). Samma icke-brist-hantering som fritt_kassaflode."""
    rp = resultatrapport["poster"]
    bp = balansrapport["poster"]

    totala_intakter = rp["totala_intakter"]
    summa_tillgangar = bp["summa_tillgangar"]
    kortfristiga_skulder = bp["kortfristiga_skulder"]
    eget_kapital = bp["eget_kapital"]

    # Justerat eget kapital: bokfört EK + dold, ägartillhörig del av obeskattade
    # reserver. Likvida tillgångar = omsättningstillgångar exkl. varulager.
    justerat_eget_kapital = eget_kapital + bp["obeskattade_reserver"] * _JEK_ANDEL
    likvida_tillgangar = bp["kassa_och_bank"] + bp["kortfristiga_fordringar"]

    # Sysselsatt kapital (för ROCE): balansomslutning minus kortfristiga skulder,
    # dvs EK + obeskattade reserver + avsättningar + långfristiga skulder. Antar
    # (som brukligt när räntebärande/icke räntebärande skuld inte är uppdelad i
    # datat) att kortfristiga skulder är icke räntebärande.
    sysselsatt_kapital = summa_tillgangar - kortfristiga_skulder

    # Skulder exkl. obeskattade reserver — samma avgränsning som den KLASSISKA
    # (icke-JEK) soliditeten ovan använder för eget kapital, för konsekvens.
    skulder_exkl_obeskattade_reserver = (
        bp["avsattningar"] + bp["langfristiga_skulder"] + kortfristiga_skulder
    )

    nyckeltal = {
        "bruttomarginal": _kvot(rp["bruttovinst"], totala_intakter),
        "rorelsemarginal": _kvot(rp["rorelseresultat"], totala_intakter),
        "vinstmarginal": _kvot(rp["arets_resultat"], totala_intakter),
        "ebita_marginal": _kvot(rp["ebita"], totala_intakter),
        "soliditet": _kvot(eget_kapital, summa_tillgangar),
        "soliditet_jek": _kvot(justerat_eget_kapital, summa_tillgangar),
        "kassalikviditet": _kvot(likvida_tillgangar, kortfristiga_skulder),
        # ROE läser av VERKLIGHETEN, inklusive negativa tal — till skillnad från
        # foreslagen_avkastning_eget_kapital (ett avkastningskravs-FÖRSLAG som
        # medvetet döljer förlustår, se dess docstring). Ett nyckeltal ljuger
        # aldrig genom att gömma en dålig siffra.
        "roe": _kvot(rp["arets_resultat"], eget_kapital),
        # ROA: SIE ger bara ett NETTO finansnetto, inte uppdelat i finansiella
        # intäkter/kostnader — den klassiska formeln (rörelseresultat + finans-
        # iella intäkter) går alltså inte att räkna utan att gissa fram en
        # uppdelning. Använder EBIT rakt av i stället för att gissa.
        "roa": _kvot(rp["rorelseresultat"], summa_tillgangar),
        "roce": _kvot(rp["rorelseresultat"], sysselsatt_kapital),
        "skuldsattningsgrad": _kvot(skulder_exkl_obeskattade_reserver, eget_kapital),
    }

    # info bedöms ENDAST på kvoterna ovan — inte på ebitda/fritt_kassaflode/
    # personalkostnad_per_anstalld nedan, som kan vara None av ett HELT annat
    # skäl (data inte given) än en nämnare som är noll.
    saknade = [namn for namn, värde in nyckeltal.items() if värde is None]
    if saknade:
        info = "Kunde inte beräkna (nämnare saknas/noll): " + ", ".join(saknade) + "."
    else:
        info = "Alla nyckeltal beräknade."

    # EBITDA är inte en kvot — den kommer redan färdigräknad från P&L-motorn.
    nyckeltal["ebitda"] = rp["ebitda"]

    nyckeltal["fritt_kassaflode"] = (
        kassaflodesanalys["lopande"]["summa"] + kassaflodesanalys["investering"]["summa"]
        if kassaflodesanalys is not None
        else None
    )

    # Lazy: rör inte rp["personalkostnader"] alls om antal_anstallda inte gavs —
    # då ska ett minimalt/what-if-resultat som saknar den posten inte krascha.
    nyckeltal["personalkostnad_per_anstalld"] = (
        personalkostnad_per_anstalld(rp["personalkostnader"], antal_anstallda)
        if antal_anstallda is not None
        else None
    )

    return {"nyckeltal": nyckeltal, "info": info}


# --- Kapitalstack: flerkällefinansiering och WACC ----------------------------
#
# Kapitalstacken delar EN investering över flera finansieringskällor samtidigt.
# Motorn är ren: den projicerar, väger och räknar — den formaterar aldrig, och
# den gissar aldrig. Okänd källa, negativa belopp och andelar som inte summerar
# till 100 % höjer ValueError i stället för att tyst normaliseras.

# Kapitalstackens källor -> motsvarande finansieringskälla i simulera_investering.
# "Kassa" är intern finansiering: den byter tillgångsslag i stället för att växa
# balansomslutningen.
# --- Kapitalstackens finansieringsposter ------------------------------------
#
# Stacken var tidigare en dict med källans NAMN som nyckel, och exakt tre fasta
# källor. Det gick därför inte att ha två lån med olika ränta (nyckeln krockar)
# eller en källa användaren döpt själv. Nu är den en LISTA av poster med eget
# id, och det är postens TYP — inte dess namn — som avgör allt som måste bli
# rätt: balanseffekt, skattesköld och kostnadsfältets innebörd.

FinansieringsTyp = Literal["lan", "agarinsats", "egna_pengar", "leasing"]

# Operationell eller finansiell leasing. Skillnaden är inte kosmetisk: den
# avgör BÅDE om den leasade tillgången alls hamnar i leasetagarens
# balansräkning och hur leasingavgifterna periodiseras.
#
#   operationell  K2 p. 7.10/9.4: "alla leasingavtal ska redovisas som
#                 operationella" — tillgången står kvar hos leasegivaren och
#                 aktiveras alltså INTE här. K3 p. 20.13: kostnaden fördelas
#                 LINJÄRT över leasingperioden. K3 p. 20.29 låter dessutom en
#                 juridisk person redovisa även finansiella avtal så här.
#   finansiell    K3 p. 20.5: tillgång OCH skuld tas upp i balansräkningen.
#                 K3 p. 20.9: avgifterna fördelas enligt EFFEKTIVRÄNTEMETODEN,
#                 alltså geometriskt, inte linjärt.
Leasingmetod = Literal["operationell", "finansiell"]

# Vilken av simulera_investerings finansieringskällor varje typ motsvarar.
# Leasing saknas medvetet: den avgörs av leasingmetoden, se _finansieringskalla.
# Publik: vy-lagret slår upp mekanikförklaringen (FINANSIERINGSFORKLARING) på
# källnamnet, och den mappningen ska finnas på ETT ställe.
TYP_KALLA: dict[str, str] = {
    "lan": "Långfristiga skulder",
    "agarinsats": "Eget kapital",
    "egna_pengar": "Minskning av kassa/bank",
}

# Bara räntan på skuldkapital är avdragsgill, alltså bara den får skattesköld.
# Avkastningskrav på eget kapital betalas ur beskattad vinst; kassans
# alternativkostnad är inte en avdragsgill kostnad alls. Leasingavgiften är
# avdragsgill och behandlas som skuldkapital — men utköpsdelen är det inte,
# se berakna_wacc.
_TYP_HAR_SKATTESKOLD: dict[str, bool] = {
    "lan": True,
    "agarinsats": False,
    "egna_pengar": False,
    "leasing": True,
}


@dataclass(frozen=True)
class Finansieringspost:
    """EN finansieringskälla i kapitalstacken.

    belopp är delbeloppet i kronor — inte en andel. Andelen är en VYSAK som
    räknas fram för display; beloppet är sanningen. Det gör att formulärets
    procent- och beloppsläge kan mata samma motor utan två kodvägar.

    kostnad är en KVOT (0.05 = 5 %), som resten av motorn.

    utkopspris/loptid_ar/leasingmetod används bara när typ == "leasing".
    """

    id: str
    namn: str
    typ: FinansieringsTyp
    belopp: Decimal
    kostnad: Decimal
    utkopspris: Decimal | None = None
    loptid_ar: int | None = None
    leasingmetod: Leasingmetod = "operationell"

    def __post_init__(self) -> None:
        # Fail-closed redan i konstruktorn: en ogiltig post ska inte kunna
        # existera och sedan tyst räknas fel längre ned i kedjan.
        if self.typ not in _TYP_HAR_SKATTESKOLD:
            raise ValueError(f"Okänd finansieringstyp: {self.typ!r}")
        if self.belopp < 0:
            raise ValueError(f"Finansieringsbeloppet får inte vara negativt: {self.belopp}")
        if self.kostnad < 0:
            raise ValueError(f"Kapitalkostnaden får inte vara negativ: {self.kostnad}")
        if self.typ == "leasing":
            if self.leasingmetod not in ("operationell", "finansiell"):
                raise ValueError(f"Okänd leasingmetod: {self.leasingmetod!r}")
            if self.utkopspris is not None and self.utkopspris < 0:
                raise ValueError("Utköpspriset får inte vara negativt.")
            if self.loptid_ar is not None and self.loptid_ar <= 0:
                raise ValueError("Leasingperioden måste vara minst ett år.")


def _finansieringskalla(post: Finansieringspost) -> str | None:
    """Vilken balanseffekt posten ger — None när den inte ska aktiveras alls.

    Operationell leasing ger None: den leasade tillgången står kvar hos
    leasegivaren (K2 p. 9.4) och blir aldrig en anläggningstillgång hos
    leasetagaren förrän den eventuellt löses ut (K2 p. 10.12). Att aktivera
    den ändå vore att visa en balansräkning bolaget inte har.
    """
    if post.typ == "leasing":
        return "Långfristiga skulder" if post.leasingmetod == "finansiell" else None
    return TYP_KALLA[post.typ]


def aktiveras(post: Finansieringspost) -> bool:
    """Hamnar postens belopp i balansräkningen som anläggningstillgång?"""
    return _finansieringskalla(post) is not None


def leasing_utkopstillagg(post: Finansieringspost) -> Decimal:
    """Utköpspriset omräknat till ett ÅRLIGT kostnadspåslag på leasingen.

    Ett utköp på 20 % av det leasade beloppet efter 5 år är en real kostnad
    som annars inte syns i WACC:en. Den fördelas över löptiden med samma
    metod som avtalets klassificering kräver:

      operationell   linjärt, (B/L) / n                     (K3 p. 20.13)
      finansiell     geometriskt, (1 + B/L)^(1/n) − 1       (K3 p. 20.9,
                     effektivräntemetoden)

    Skillnaden är verklig men liten: 20 % på 5 år ger 4,00 % linjärt mot
    3,71 % geometriskt. Den linjära är alltid den högre — geometrisk
    periodisering tar hänsyn till att påslaget i sin tur förräntas.

    Noll när posten inte är leasing, saknar utköp eller löptid, eller när det
    leasade beloppet är noll (ett påslag på ingenting är inte en kostnad).
    """
    if post.typ != "leasing":
        return Decimal("0")
    if not post.utkopspris or not post.loptid_ar or post.belopp <= 0:
        return Decimal("0")

    kvot = post.utkopspris / post.belopp
    ar = Decimal(post.loptid_ar)
    if post.leasingmetod == "finansiell":
        return (Decimal("1") + kvot) ** (Decimal("1") / ar) - Decimal("1")
    return kvot / ar


def foreslagen_avkastning_eget_kapital(
    resultatrapport: dict, balansrapport: dict
) -> Decimal | None:
    """Årets avkastning på eget kapital, som KVOT — förslag på avkastningskrav.

    Nämnaren är det egna kapitalet vid periodens SLUT (samma nämnarkonvention som
    soliditeten använder). Ett genomsnittligt eller ingående EK vore lika
    försvarbart och ger ett annat tal; valet är därför dokumenterat, inte dolt.

    None när talet inte går att beräkna eller inte går att tolka som ett
    avkastningskrav: EK ≤ 0 (ett förlustbolag har ingen meningsfull ROE) eller ett
    negativt resultat. Ett negativt avkastningskrav är inte ett krav."""
    eget_kapital = balansrapport["poster"]["eget_kapital"]
    arets_resultat = resultatrapport["poster"]["arets_resultat"]
    if eget_kapital <= 0 or arets_resultat < 0:
        return None
    return _kvot(arets_resultat, eget_kapital)


def simulera_kapitalstack(
    balansrapport: dict, belopp: Decimal | int, poster: list[Finansieringspost]
) -> dict[str, Any]:
    """Projicerar EN investering finansierad ur FLERA källor samtidigt.

    posternas belopp måste summera EXAKT till investeringsbeloppet. Varje post
    körs genom den redan testade simulera_investering, kedjad över den
    föregåendes utfall — den dubbla bokföringen håller post för post
    (kontrolldiff förblir 0).

    Operationellt leasade poster AKTIVERAS INTE: tillgången står kvar hos
    leasegivaren (K2 p. 9.4), så bolaget får varken en anläggningstillgång
    eller en skuld av dem. De ingår ändå i stacken — de finansierar ju
    anskaffningen — men bara som kostnad. Det är därför "aktiverat_belopp" kan
    vara mindre än "belopp", och skillnaden ligger i "ej_aktiverat_belopp".

    Fail-closed: negativt belopp eller poster som inte summerar till
    investeringsbeloppet höjer ValueError. Ingen tyst normalisering — en stack
    som inte går ihop är ett fel, inte något att gissa sig runt."""
    belopp = Decimal(belopp)
    if belopp < 0:
        raise ValueError(f"Investeringsbeloppet får inte vara negativt: {belopp}")

    summa = sum((post.belopp for post in poster), Decimal("0"))
    if summa != belopp:
        raise ValueError(
            f"Finansieringsposterna summerar till {summa}, inte till "
            f"investeringsbeloppet {belopp}."
        )

    rapport = balansrapport
    varningar: list[str] = []
    aktiverat = Decimal("0")
    for post in poster:
        if post.belopp <= 0:
            continue
        kalla = _finansieringskalla(post)
        if kalla is None:
            continue  # operationell leasing: kostnad, inte tillgång
        rapport = simulera_investering(rapport, post.belopp, kalla)
        aktiverat += post.belopp
        if rapport["varning"]:
            varningar.append(rapport["varning"])

    return {
        "balans_efter": {
            **rapport,
            "simulering": {"belopp": belopp, "aktiverat_belopp": aktiverat},
            "varning": varningar[0] if varningar else None,
        },
        "poster": list(poster),
        "belopp": belopp,
        "aktiverat_belopp": aktiverat,
        "ej_aktiverat_belopp": belopp - aktiverat,
        "varning": varningar[0] if varningar else None,
    }


def berakna_wacc(
    poster_in: list[Finansieringspost],
    skattesats: Decimal = BOLAGSSKATT,
) -> dict[str, Any]:
    """Vägd genomsnittlig kapitalkostnad för EN investering, före och efter skatt.

    Vikterna är posternas andel av investeringen, inte av bolagets hela
    balansräkning: det är den här investeringens kapitalkostnad som beräknas.
    Operationellt leasade poster väger med — de aktiveras visserligen inte i
    balansräkningen, men de kostar pengar och ger tillgången samma nytta.

    Skatteskölden läggs bara på skuldkapital (_TYP_HAR_SKATTESKOLD):
    efterskattekostnaden är kd × (1 − skattesats). Eget kapital och kassa bär
    full kostnad.

    Leasingens UTKÖPSTILLÄGG (leasing_utkopstillagg) läggs ovanpå räntan men
    får INGEN skattesköld: löpande leasingavgifter är avdragsgilla, men
    utköpet är ett förvärv av en tillgång (K2 p. 10.12) — inte en avdragsgill
    kostnad. Leasing är därför den enda posttypen vars kostnad delas i en
    skuggad och en oskuggad del.

    Ett nollbelopp ger WACC None — inte 0 %. En investering som inte görs har
    ingen kapitalkostnad, och 0 % vore ett påstående om gratis kapital."""
    total = sum((post.belopp for post in poster_in), Decimal("0"))
    if total <= 0:
        return {"wacc_fore_skatt": None, "wacc_efter_skatt": None, "skatteskold": None, "poster": []}

    poster: list[dict[str, Any]] = []
    for post in poster_in:
        if post.belopp <= 0:
            continue
        tillagg = leasing_utkopstillagg(post)
        kostnad = post.kostnad + tillagg
        if _TYP_HAR_SKATTESKOLD[post.typ]:
            # Skölden bara på grundkostnaden; utköpstillägget bär full vikt.
            efter = post.kostnad * (Decimal("1") - skattesats) + tillagg
        else:
            efter = kostnad
        vikt = post.belopp / total
        poster.append(
            {
                "id": post.id,
                "kalla": post.namn,
                "typ": post.typ,
                "belopp": post.belopp,
                "vikt": vikt,
                "kostnad_fore_skatt": kostnad,
                "kostnad_efter_skatt": efter,
                "utkopstillagg": tillagg,
                "bidrag_fore_skatt": vikt * kostnad,
                "bidrag_efter_skatt": vikt * efter,
            }
        )

    wacc_fore = sum((p["bidrag_fore_skatt"] for p in poster), Decimal("0"))
    wacc_efter = sum((p["bidrag_efter_skatt"] for p in poster), Decimal("0"))
    return {
        "wacc_fore_skatt": wacc_fore,
        "wacc_efter_skatt": wacc_efter,
        "skatteskold": wacc_fore - wacc_efter,
        "poster": poster,
    }


# --- Kassaflödesanalys (indirekt metod) -------------------------------------

def bygg_kassaflodesanalys(
    resultatrapport: dict, balansrapport_start: dict, balansrapport_slut: dict
) -> dict[str, Any]:
    """REN kassaflödesmotor (indirekt metod) — frikopplad från datakällan. Tar
    tre färdiga dicts: P&L för perioden samt balansräkningen vid periodens start
    (IB) och slut (UB).

    Härleds ur balansidentiteten så att kontrolldiff = 0 by construction: ALLA
    icke-kassaflödespåverkande balansförändringar (avskrivningar, Δ obeskattade
    reserver, Δ avsättningar) återläggs i Löpande verksamhet enligt svensk
    K3-standard. Posterna kommer redan teckennormaliserade (positiva) från
    balans-/P&L-motorn; här sätts kassaflödestecknet per post så att varje blocks
    poster summerar till blockets summa (dumt frontend-kontrakt)."""
    rp = resultatrapport["poster"]
    sp = balansrapport_start["poster"]
    up = balansrapport_slut["poster"]

    def delta(nyckel: str) -> Decimal:
        return up[nyckel] - sp[nyckel]

    avskrivningar = rp["avskrivningar"]

    # Löpande: rörelseresultat, finansiella poster/skatt, icke-kassaposter
    # (avskrivningar, Δ obesk. reserver, Δ avsättningar) och Δ rörelsekapital.
    # Ökning av tillgång binder kapital (−), ökning av skuld frigör (+).
    lopande_poster = {
        "rorelseresultat": rp["rorelseresultat"],
        "finansnetto": rp["finansnetto"],
        "bokslutsdispositioner_skatt": -rp["bokslutsdispositioner_skatt"],
        "avskrivningar": avskrivningar,
        "forandring_obeskattade_reserver": delta("obeskattade_reserver"),
        "forandring_avsattningar": delta("avsattningar"),
        "forandring_varulager": -delta("varulager"),
        "forandring_kortfristiga_fordringar": -delta("kortfristiga_fordringar"),
        "forandring_kortfristiga_skulder": delta("kortfristiga_skulder"),
    }
    summa_lopande = sum(lopande_poster.values(), Decimal("0"))

    # Investering: −capex = −(Δ anläggningstillgångar + årets avskrivningar).
    # Avskrivningarna återförs hit från Löpande så nettot blir −Δ AT.
    investering_poster = {
        "forandring_anlaggningstillgangar": -(
            delta("summa_anlaggningstillgangar") + avskrivningar
        ),
    }
    summa_investering = sum(investering_poster.values(), Decimal("0"))

    # Finansiering: Δ eget kapital EXKL. årets resultat (nyemission/utdelning)
    # + Δ långfristiga skulder.
    ek_exkl_resultat = (up["eget_kapital"] - rp["arets_resultat"]) - sp["eget_kapital"]
    finansiering_poster = {
        "forandring_eget_kapital": ek_exkl_resultat,
        "forandring_langfristiga_skulder": delta("langfristiga_skulder"),
    }
    summa_finansiering = sum(finansiering_poster.values(), Decimal("0"))

    arets_kassaflode = summa_lopande + summa_investering + summa_finansiering
    forandring_kassa = delta("kassa_och_bank")
    kontrolldiff = arets_kassaflode - forandring_kassa

    if kontrolldiff != 0:
        info = (
            f"VARNING: kassaflödet stämmer inte (kontrolldiff={kontrolldiff}). "
            "Årets kassaflöde matchar inte förändringen i kassa & bank."
        )
    else:
        info = "Kassaflödet balanserar (kontrolldiff = 0)."

    return {
        "period": {
            "start_datum": balansrapport_start.get("per_datum", ""),
            "slut_datum": balansrapport_slut.get("per_datum", ""),
        },
        "lopande": {"poster": lopande_poster, "summa": summa_lopande},
        "investering": {"poster": investering_poster, "summa": summa_investering},
        "finansiering": {"poster": finansiering_poster, "summa": summa_finansiering},
        "arets_kassaflode": arets_kassaflode,
        "forandring_kassa": forandring_kassa,
        "kontrolldiff": kontrolldiff,
        "info": info,
    }


# --- Likviditetsprognos (dag-för-dag) ----------------------------------------
#
# Motorn tar ÖPPNA fakturor (redan filtrerade på RemainingAmount != 0 uppströms
# — se spiris_adapter.bygg_reskontra_rader/bygg_kundreskontra_rader) och
# projicerar kassan dag för dag. Samma "motorn normaliserar tecken internt"-
# princip som resten av filen: leverantörsfakturor kommer med RAW SIE-tecken
# (negativt, = RemainingAmount rakt av, matchar Leverantorspost.belopp),
# kundfakturor positivt (matchar Kundpost.belopp) — anroparen skickar in data
# oförändrad, motorn tar abs() själv.

LIKVIDITETSPROGNOS_DAGAR = 90


def berakna_kundbetalbeteende(betalda_kundfakturor: list[dict]) -> dict[str, Decimal]:
    """Räknar historiskt snitt antal dagar en kund betalar för sent (negativt
    = betalar i förskott, 0 = exakt i tid) ur redan BETALDA fakturor:

        {"motpart_id": str, "forfallodatum": date, "betaldatum": date}

    Returnerar {motpart_id: snitt_dagar_forsent}. En rad utan motpart_id
    hoppas över (kan inte kopplas till någon profil — normalt, inte ett
    datafel). En rad MED motpart_id men utan datum är däremot ett datafel och
    höjer ValueError: går inte att räkna ett snitt på data som inte finns.

    Fristående, testbar funktion (samma mönster som personalkostnad_per_
    anstalld/foreslagen_avkastning_eget_kapital) — bygg_likviditetsprognos tar
    bara emot den FÄRDIGA dicten och behöver aldrig se historiken själv."""
    dagar_forsent: dict[str, list[int]] = {}
    for faktura in betalda_kundfakturor:
        motpart_id = faktura.get("motpart_id") or ""
        if not motpart_id:
            continue
        if "forfallodatum" not in faktura or "betaldatum" not in faktura:
            raise ValueError(
                f"Betald kundfaktura för {motpart_id!r} saknar förfallodatum/betaldatum: "
                f"{faktura!r}"
            )
        dagar = (faktura["betaldatum"] - faktura["forfallodatum"]).days
        dagar_forsent.setdefault(motpart_id, []).append(dagar)

    return {
        motpart_id: sum(värden, Decimal(0)) / Decimal(len(värden))
        for motpart_id, värden in dagar_forsent.items()
    }


def likviditetsstatus(kassa: Decimal, varningströskel: Decimal | None) -> str:
    """grön/gul/röd — samma semantiska vokabulär som ackumulering._troskelstatus,
    inte hex/emoji: den här filen är display-fri, vy-lagret gör färgmappningen
    (jfr app_vy._STATUS_TILL_EMOJI). röd kräver ingen extern tröskel (kassa < 0
    är alltid rött). gul KRÄVER en explicit varningströskel — precis som
    ackumulering.py tar in väsentlighetstalen som parametrar i stället för att
    hitta på ett eget procenttal, gissar den här funktionen aldrig en
    varningsnivå. Ges ingen tröskel blir det alltså binärt grön/röd.

    Public (inte _-prefixad): fpa_vy.likviditetsprognos_med_varningstroskel
    återanvänder den här för att räkna om ENDAST statusfältet när en
    varningströskel blir känd EFTER att prognosen redan byggts (en Streamlit-
    widgets värde kan bara läsas av vid rendering) — samma mönster som
    nyckeltal_med_personalkostnad i fpa_vy.py. Statuslogiken ska ägas av
    motorn på EN plats, aldrig dupliceras i vy-lagret."""
    if kassa < 0:
        return "röd"
    if varningströskel is not None and kassa < varningströskel:
        return "gul"
    return "grön"


def _validera_faktura(faktura: dict, etikett: str) -> None:
    if "belopp" not in faktura or "forfallodatum" not in faktura:
        raise ValueError(f"{etikett} saknar belopp/förfallodatum: {faktura!r}")


# Skatteverkets vanligaste förfallodag för momsbetalning/momsåterbäring.
# v1-förenkling: alltid EXAKT den 12:e, oavsett veckodag (Skatteverket flyttar
# i praktiken till nästa bankdag om den 12:e är en helg) — dokumenterat, inte
# dolt. Ingen egen konstant per bolagsstorlek (mindre bolag kan ha den 26:e i
# stället) — se nasta_momsforfallodag:s dag_i_manaden-parameter för att
# override:a per anrop.
MOMS_STANDARDFORFALLODAG = 12


def nasta_momsforfallodag(fran_datum: date, dag_i_manaden: int = MOMS_STANDARDFORFALLODAG) -> date:
    """Nästa standardförfallodatum för moms EFTER (eller PÅ) fran_datum: samma
    dag_i_manaden denna månad om den inte redan passerats, annars nästa
    månads. Ren datummatte utan väggklocka — fran_datum är ett explicit
    argument, precis som prognosdatum är det överallt annars i den här filen.

    fran_datum.day == dag_i_manaden räknas som ATT dagen precis inträffar
    (ger denna månads datum, inte nästa) — konsekvent med
    bygg_likviditetsprognos:s egen dag_index, där en redan förfallen faktura
    (datum <= prognosdatum) klipps till dag 1 i stället för att hoppa över."""
    år, månad = fran_datum.year, fran_datum.month
    if fran_datum.day > dag_i_manaden:
        månad += 1
        if månad > 12:
            månad = 1
            år += 1
    return date(år, månad, dag_i_manaden)


def bygg_likviditetsprognos(
    nuvarande_kassa: Decimal,
    prognosdatum: date,
    obetalda_leverantorsfakturor: list[dict],
    obetalda_kundfakturor: list[dict],
    kundbetalbeteende: dict[str, int | Decimal] | None = None,
    antal_dagar: int = LIKVIDITETSPROGNOS_DAGAR,
    varningströskel: Decimal | None = None,
    momshandelse: dict | None = None,
) -> dict[str, Any]:
    """REN, frikopplad likviditetsmotor: projicerar kassan dag för dag utifrån
    redan hämtade öppna fakturor. Ingen datakälla, ingen klient, ingen
    väggklocka — prognosdatum ("idag") är ett explicit argument, exakt som
    start_datum/slut_datum/per_datum är strängar resten av filen aldrig
    härleder ur systemtiden.

    INDATA per faktura (leverantör):
        {"fakturanr": str, "motpart": str,   # valfria, bara för UI-förklaring
         "belopp": Decimal,                  # RAW SIE-tecken, negativt
         "forfallodatum": date}

    INDATA per faktura (kund):
        {"fakturanr": str, "motpart": str,   # valfria
         "motpart_id": str,                  # krav för betalbeteende-slagning;
                                              # "" -> ingen historik -> 0 dagar
         "belopp": Decimal,                  # RAW SIE-tecken, positivt
         "forfallodatum": date}

    INDATA momshandelse (valfri, None = ingen momshändelse i prognosen):
        {"belopp": Decimal,                  # RAW SIE-tecken (konto 2650 el.
                                              # motsv.): negativt = SKULD
                                              # (utbetalning), positivt =
                                              # FORDRAN (återbäring/inbetalning)
         "forfallodatum": date}               # t.ex. nasta_momsforfallodag(...)
    Exakt EN post (inte en lista): den redan avstämda NETTOpositionen mot
    Skatteverket, inte enskilda momskonton. Motparten sätts alltid till
    "Skatteverket" i utdatan. Justeras ALDRIG av kundbetalbeteende (det är en
    skatteskuld/fordran, inte en kundrelation).

    kundbetalbeteende (se berakna_kundbetalbeteende) skiftar en kundfakturas
    FÖRVÄNTADE inbetalningsdag: justerat_datum = forfallodatum +
    snitt_dagar_forsent. Leverantörsutbetalningar och momshändelsen justeras
    ALDRIG — bolaget styr sina egna utbetalningar och sin momsredovisning,
    och det är bara kundsidans betalbeteende uppdraget bad om att modellera.

    En faktura vars (ev. justerade) datum ligger PÅ eller FÖRE prognosdatum
    klipps till dag 1 (redan förfallet, väntas falla in omedelbart). En
    faktura vars datum ligger EFTER fönstrets sista dag utelämnas helt — den
    hör inte hemma i en {antal_dagar}-dagarsprognos, precis som
    bygg_resultatrapport bara summerar transaktioner innanför sin period.

    UTDATA: en kedjad dagsserie (varje dags utgående_kassa blir nästa dags
    ingående) plus en fullständig händelselista per dag OCH i en plattad
    "alla_handelser"-lista, rik nog för ett UI att rendera en interaktiv graf
    och identifiera/färgkoda enskilda händelser (t.ex. historiskt sena
    kunder — se "dagar_justering"/"har_historisk_justering" per händelse) utan
    att själv behöva räkna om något.

    Fail-closed: en fakturarad utan belopp/förfallodatum eller ett
    icke-positivt antal_dagar höjer ValueError — motorn gissar aldrig fram ett
    datum eller ett belopp. Fail-safe: en kundfaktura utan motpart_id, eller
    en motpart_id utan känd betalhistorik, ger 0 dagars justering — det är ett
    normalt tillstånd (ny kund), inte ett datafel."""
    if antal_dagar <= 0:
        raise ValueError(f"antal_dagar måste vara positivt: {antal_dagar}")
    kundbetalbeteende = kundbetalbeteende or {}

    def dag_index(datum: date) -> int:
        # Dag 1 = prognosdatum. Redan förfallet (datum <= prognosdatum) klipps
        # till dag 1 i stället för att räknas som ett negativt/nollte index.
        return max(1, (datum - prognosdatum).days + 1)

    handelser_per_dag: dict[int, list[dict]] = {}

    for i, faktura in enumerate(obetalda_leverantorsfakturor):
        _validera_faktura(faktura, "Leverantörsfaktura")
        forfallodatum = faktura["forfallodatum"]
        dag = dag_index(forfallodatum)
        if dag > antal_dagar:
            continue
        belopp = abs(faktura["belopp"])
        handelser_per_dag.setdefault(dag, []).append(
            {
                "handelse_id": f"leverantorsfaktura_{i}",
                "typ": "leverantorsutbetalning",
                "fakturanr": faktura.get("fakturanr", ""),
                "motpart": faktura.get("motpart", ""),
                "motpart_id": "",
                "belopp": belopp,
                "belopp_signerat": -belopp,
                "forfallodatum": forfallodatum,
                "justerat_datum": forfallodatum,
                "dagar_justering": 0,
                "har_historisk_justering": False,
            }
        )

    for i, faktura in enumerate(obetalda_kundfakturor):
        _validera_faktura(faktura, "Kundfaktura")
        forfallodatum = faktura["forfallodatum"]
        motpart_id = faktura.get("motpart_id") or ""
        dagar_justering = int(kundbetalbeteende.get(motpart_id, 0)) if motpart_id else 0
        justerat_datum = forfallodatum + timedelta(days=dagar_justering)
        dag = dag_index(justerat_datum)
        if dag > antal_dagar:
            continue
        belopp = abs(faktura["belopp"])
        handelser_per_dag.setdefault(dag, []).append(
            {
                "handelse_id": f"kundfaktura_{i}",
                "typ": "kundinbetalning",
                "fakturanr": faktura.get("fakturanr", ""),
                "motpart": faktura.get("motpart", ""),
                "motpart_id": motpart_id,
                "belopp": belopp,
                "belopp_signerat": belopp,
                "forfallodatum": forfallodatum,
                "justerat_datum": justerat_datum,
                "dagar_justering": dagar_justering,
                "har_historisk_justering": dagar_justering != 0,
            }
        )

    if momshandelse is not None:
        _validera_faktura(momshandelse, "Momshändelse")
        forfallodatum = momshandelse["forfallodatum"]
        dag = dag_index(forfallodatum)
        if dag <= antal_dagar:
            belopp_signerat = momshandelse["belopp"]
            handelser_per_dag.setdefault(dag, []).append(
                {
                    "handelse_id": "moms_0",
                    "typ": "moms",
                    "fakturanr": "",
                    "motpart": "Skatteverket",
                    "motpart_id": "",
                    "belopp": abs(belopp_signerat),
                    "belopp_signerat": belopp_signerat,
                    "forfallodatum": forfallodatum,
                    "justerat_datum": forfallodatum,
                    "dagar_justering": 0,
                    "har_historisk_justering": False,
                }
            )

    dagar_ut: list[dict] = []
    ingående = nuvarande_kassa
    lägsta_kassa = nuvarande_kassa
    lägsta_kassa_datum = prognosdatum
    första_dag_med_underskott: date | None = None

    for dag_nr in range(1, antal_dagar + 1):
        datum = prognosdatum + timedelta(days=dag_nr - 1)
        handelser = handelser_per_dag.get(dag_nr, [])
        kundinbetalningar = sum(
            (h["belopp"] for h in handelser if h["typ"] == "kundinbetalning"), Decimal("0")
        )
        leverantorsutbetalningar = sum(
            (h["belopp"] for h in handelser if h["typ"] == "leverantorsutbetalning"), Decimal("0")
        )
        # Signerad (till skillnad från de två ovan, som är summor av abs-belopp):
        # en momshändelse kan vara EN utbetalning (skuld) ELLER EN inbetalning
        # (fordran/återbäring) — belopp_signerat bär redan rätt tecken.
        moms_forandring = sum(
            (h["belopp_signerat"] for h in handelser if h["typ"] == "moms"), Decimal("0")
        )
        netto = kundinbetalningar - leverantorsutbetalningar + moms_forandring
        utgående = ingående + netto

        if utgående < lägsta_kassa:
            lägsta_kassa = utgående
            lägsta_kassa_datum = datum
        if första_dag_med_underskott is None and utgående < 0:
            första_dag_med_underskott = datum

        dagar_ut.append(
            {
                "dag_nr": dag_nr,
                "datum": datum,
                "ingaende_kassa": ingående,
                "kundinbetalningar": kundinbetalningar,
                "leverantorsutbetalningar": leverantorsutbetalningar,
                "moms_forandring": moms_forandring,
                "netto_forandring": netto,
                "utgaende_kassa": utgående,
                "status": likviditetsstatus(utgående, varningströskel),
                "handelser": handelser,
            }
        )
        ingående = utgående

    # Plattad vy över samtliga händelser (alla dagar), var och en taggad med
    # sitt dag_nr/datum — så ett UI slipper själv flatta dagar[*]["handelser"]
    # för att t.ex. rendera en klickbar händelselista bredvid grafen.
    alla_handelser = [
        {"dag_nr": dag["dag_nr"], "datum": dag["datum"], **handelse}
        for dag in dagar_ut
        for handelse in dag["handelser"]
    ]

    if första_dag_med_underskott is not None:
        info = (
            f"VARNING: kassan väntas bli negativ från och med "
            f"{första_dag_med_underskott.isoformat()}."
        )
    else:
        info = f"Kassan väntas förbli positiv genom hela {antal_dagar}-dagarsperioden."

    return {
        "prognosdatum": prognosdatum,
        "nuvarande_kassa": nuvarande_kassa,
        "antal_dagar": antal_dagar,
        "dagar": dagar_ut,
        "alla_handelser": alla_handelser,
        "lagsta_kassa": lägsta_kassa,
        "lagsta_kassa_datum": lägsta_kassa_datum,
        "forsta_dag_med_underskott": första_dag_med_underskott,
        "info": info,
    }
