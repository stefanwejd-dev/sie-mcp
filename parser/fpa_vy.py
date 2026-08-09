"""fpa_vy — tunn, testbar glue mellan en inläst SIEFil och FP&A-dashboardens
rendering (app.py, fliken Resultatrapport + Balansräkning).

Två ansvar, båda UI-fria så de kan enhetstestas utan Streamlit-runtime:

1. ADAPTER: bygg de strukturerade rapport-dictarna ur en redan inläst (och
   maskerad) SIEFil, genom att mata de HELT FRIKOPPLADE motorerna
   (bygg_resultatrapport / bygg_balansrapport) med konto-saldon. Samma väg
   oavsett om filen kommer från lokal uppladdning eller Spiris — båda landar i
   samma SIEFil. Ingen tecken- eller grupperingslogik här; motorn äger allt
   sådant.

2. UPPSTÄLLNING: display-config (svenska etiketter + ordning + radtyp) som
   dashboarden loopar över. Etiketter och ordning är frontend-ansvar; siffror,
   grupper och tecken kommer FÄRDIGA från motorn. Radtyp "grupp" = drill-down
   (har en matchande kontogrupp), "delsumma"/"summa" = uträknad subtotal.
"""

from __future__ import annotations

import html
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from domain_model import SIEFil
from fpa_motor import (
    FINANSIERINGSKALLOR,
    LIKVIDITETSPROGNOS_DAGAR,
    Finansieringspost,
    TYP_KALLA,
    berakna_kundbetalbeteende,
    berakna_wacc,
    leasing_utkopstillagg,
    bygg_balansrapport,
    bygg_kassaflodesanalys,
    bygg_likviditetsprognos,
    bygg_nyckeltal,
    bygg_resultatrapport,
    foreslagen_avkastning_eget_kapital,
    likviditetsstatus,
    nasta_momsforfallodag,
    personalkostnad_per_anstalld,
    simulera_investering,
    simulera_kapitalstack,
)
from reskontra_tvatt import Kundpost, Leverantorspost


def _rader_fran_saldoposter(sie: SIEFil, saldoposter: list) -> list[dict]:
    """Plockar {kontonr, kontonamn, saldo} ur SIE-saldoposter för innevarande
    räkenskapsår (årsnr 0). Ren datakälle-adaptering — inga tecken vänds, inga
    grupper sätts; det gör motorn."""
    rader: list[dict] = []
    for post in saldoposter:
        if post.årsnr != 0:
            continue
        konto = sie.konton.get(post.kontonr)
        rader.append(
            {
                "kontonr": post.kontonr,
                "kontonamn": konto.namn if konto is not None else "",
                "saldo": post.saldo,
            }
        )
    return rader


def _period(sie: SIEFil) -> tuple[str, str]:
    """Räkenskapsårets start- och slutdatum (yyyy-mm-dd) för årsnr 0, eller
    tomma strängar om årsinfo saknas."""
    år = sie.räkenskapsår.get(0)
    if år is None:
        return "", ""
    return str(år.start)[:10], str(år.slut)[:10]


def resultatrapport_fran_sie(sie: SIEFil) -> dict[str, Any]:
    """Bygger den strukturerade P&L-rapporten ur en SIEFil. En SIE-fil är en
    helårs-ögonblicksbild, så #RES motsvarar hela periodresultatet (öppning 0
    vid årsstart)."""
    start, slut = _period(sie)
    konto_perioder = _rader_fran_saldoposter(sie, sie.resultat)
    return bygg_resultatrapport(konto_perioder, start, slut)


def balansrapport_fran_sie(sie: SIEFil) -> dict[str, Any]:
    """Bygger den strukturerade balansräkningen ur en SIEFil (ögonblicksbild per
    räkenskapsårets slut). Skickar in både balans- (klass 1-2) och resultatkonton
    (klass 3-8) så motorn kan baka in årets resultat i Eget kapital."""
    _, per_datum = _period(sie)
    konton = _rader_fran_saldoposter(sie, list(sie.utgående_balanser) + list(sie.resultat))
    return bygg_balansrapport(konton, per_datum)


# Konto för den redan avstämda momsnettopositionen (Redovisningskonto för
# moms). Föredras framför fallback-intervallet nedan eftersom det ÄR den
# färdiga nettosumman efter en periodisk momsavstämning — ingen egen summering
# behövs då.
_MOMS_NETTOKONTO = "2650"
# Fallback om 2650 saknar saldo (bolaget har inte bokfört någon avstämning
# ännu): hela momsredovisningsintervallet, utgående (2610-2639) OCH ingående
# (2640-2649) moms tillsammans — en approximation av samma nettoposition.
_MOMS_FALLBACK_INTERVALL = (2610, 2649)


def momssaldo_fran_sie(sie: SIEFil) -> Decimal:
    """Nettosaldot för moms (skuld/fordran mot Skatteverket) för innevarande
    räkenskapsår, ur redan hämtade kontosaldon (sie.utgående_balanser) —
    INGET nytt Spiris-anrop krävs: /accountbalances hämtas redan av
    spiris_adapter.hamta_siefil_fran_spiris, som fyller utgående_balanser med
    HELA balansräkningen, momskontona inkluderat (se moduldocstring/
    likviditetsprognos_fran_reskontra).

    RAW SIE-tecken, precis som Leverantorspost.belopp/Kundpost.belopp:
    negativt = kreditsaldo = SKULD till Skatteverket (framtida utbetalning),
    positivt = debetsaldo = FORDRAN (framtida momsåterbäring). 0 om inget
    momskonto har något saldo alls."""
    rader = _rader_fran_saldoposter(sie, sie.utgående_balanser)
    nettokonto = next((r for r in rader if r["kontonr"] == _MOMS_NETTOKONTO), None)
    if nettokonto is not None:
        return nettokonto["saldo"]
    lo, hi = _MOMS_FALLBACK_INTERVALL
    return sum(
        (r["saldo"] for r in rader if lo <= int(r["kontonr"]) <= hi),
        Decimal("0"),
    )


def nyckeltal_fran_sie(sie: SIEFil) -> dict[str, Any]:
    """Bygger nyckeltalen ur en SIEFil genom att kedja P&L-, balans- och
    kassaflödesrapporten in i den frikopplade KPI-motorn (kassaflödet krävs för
    fritt_kassaflode). Ren komposition — ingen egen matematik."""
    return bygg_nyckeltal(
        resultatrapport_fran_sie(sie),
        balansrapport_fran_sie(sie),
        kassaflodesanalys_fran_sie(sie),
    )


def nyckeltal_med_personalkostnad(
    nyckeltal: dict, resultatrapport: dict, antal_anstallda: int | None
) -> dict:
    """Nyckeltal-dicten med personalkostnad_per_anstalld omräknad för ett LIVE
    ifyllt antal anställda. SIE4 saknar personalstyrka helt, så den siffran kan
    inte vara känd förrän EFTER att nyckeltalsrapporten redan är byggd — det är
    därför den här funktionen finns i stället för att bara skicka in
    antal_anstallda i bygg_nyckeltal från början.

    Muterar inte originalet — returnerar en kopia med bara den nyckeln ändrad.
    Räknar via SAMMA formel som motorn (fpa_motor.personalkostnad_per_anstalld):
    UI-lagret ska aldrig ha sin egen kopia av matten."""
    return {
        **nyckeltal,
        "personalkostnad_per_anstalld": personalkostnad_per_anstalld(
            resultatrapport["poster"]["personalkostnader"], antal_anstallda
        ),
    }


def dashboard_rendering_lage(
    *, datakälla_ar_spiris: bool, sie_finns: bool, spiris_data_finns: bool
) -> str:
    """Vilken källa FP&A-dashboarden ska renderas från: "spiris" (live-API),
    "fil" (inläst SIEFil) eller "ingen" (visa uppmaning). I Spiris-läge används
    ENBART live-data — den maskerade SIEFil:en är för Sektion 2-9, inte för
    dashboarden. Ren beslutslogik, testbar utan Streamlit."""
    if datakälla_ar_spiris:
        return "spiris" if spiris_data_finns else "ingen"
    return "fil" if sie_finns else "ingen"


def dashboard_saknar_data(data: dict) -> bool:
    """True om live-dashboarddatan i praktiken är tom (sandbox saknar poster för
    perioden): inga resultatkonton OCH inga balanskonton. Den syntetiska
    'Årets resultat'-raden (8999) räknas inte som innehåll."""
    resultat_konton = data["resultat"].get("konton", [])
    balans_konton = [
        konto for konto in data["balans"].get("konton", []) if konto.get("kontonr") != "8999"
    ]
    return not resultat_konton and not balans_konton


def innevarande_ar_intervall(idag: date | None = None) -> tuple[date, date]:
    """Innevarande kalenderår som (1 jan, 31 dec). Default för datumväljarna —
    de flesta bolag har räkenskapsår = kalenderår. Testbart via injicerat idag."""
    år = (idag or date.today()).year
    return date(år, 1, 1), date(år, 12, 31)


def valj_rakenskapsar_for_ar(räkenskapsår: list[dict], år: int) -> dict | None:
    """Väljer räkenskapsåret vars EndDate ligger i `år` (för att auto-välja
    innevarande år ur Spiris /fiscalyears-lista). None om inget matchar."""
    for post in räkenskapsår:
        if str(post.get("EndDate"))[:4] == str(år):
            return post
    return None


def default_datumintervall(räkenskapsår: list[dict]) -> tuple[date, date]:
    """Default start/slut för FP&A-datumväljarna: senaste räkenskapsåret (störst
    EndDate). Fallback till innevarande kalenderår om listan är tom. Rent
    datumval, testbart."""
    if not räkenskapsår:
        idag = date.today()
        return date(idag.year, 1, 1), date(idag.year, 12, 31)
    senaste = max(räkenskapsår, key=lambda år: str(år.get("EndDate"))[:10])
    start = date.fromisoformat(str(senaste.get("StartDate"))[:10])
    slut = date.fromisoformat(str(senaste.get("EndDate"))[:10])
    return start, slut


def kassaflodesanalys_fran_sie(sie: SIEFil) -> dict[str, Any]:
    """Bygger kassaflödesanalysen (indirekt metod) ur en SIEFil. Start-balansen
    byggs ur ingående balanser (#IB, resultatkonton = 0 vid årsstart) och
    slut-balansen ur utgående balanser + resultat, sedan matas allt in i den
    frikopplade kassaflödesmotorn. Ren komposition."""
    start_datum, slut_datum = _period(sie)
    balans_start = bygg_balansrapport(
        _rader_fran_saldoposter(sie, list(sie.ingående_balanser)), start_datum
    )
    return bygg_kassaflodesanalys(
        resultatrapport_fran_sie(sie), balans_start, balansrapport_fran_sie(sie)
    )


def rapporter_fran_sie(sie: SIEFil) -> dict[str, Any]:
    """De fyra FP&A-rapporterna ur en SIEFil, i EXAKT samma dict-form som
    spiris_rag.hamta_dashboard returnerar dem live ("resultat", "balans",
    "nyckeltal", "kassaflode").

    Gör att app.py kan behandla fil- och Spiris-vägen identiskt: en dict in,
    samma renderare ut — och att Investeringskalkylen kan plocka fram resultat-
    och balansrapporten ur båda källorna utan att veta vilken det är."""
    resultat = resultatrapport_fran_sie(sie)
    balans = balansrapport_fran_sie(sie)
    kassaflode = kassaflodesanalys_fran_sie(sie)
    return {
        "resultat": resultat,
        "balans": balans,
        # Kedjar de redan byggda rapporterna vidare i stället för att gå via
        # nyckeltal_fran_sie, som annars hade byggt om alla tre en gång till.
        "nyckeltal": bygg_nyckeltal(resultat, balans, kassaflode),
        "kassaflode": kassaflode,
    }


# --- Likviditetsprognos: reskontra -> fpa_motor-indata + Plotly-redo data ----
#
# SPIRIS-ENDAST: en SIE-fil bär ingen fakturanivå-data (inga förfallodatum,
# ingen reskontra alls), så det finns medvetet ingen "_fran_sie"-motsvarighet
# här — fpa_dashboard.rendera() (fil-vägen) anropar aldrig den här funktionen.
#
# Statusfärgerna (grön/gul/röd) är en FAST, reserverad statuspalett — inte
# kategoriska hues, och inte tänkta att klara det kategoriska ljushets-/
# kontrastgrinden (samma sätt som riskindikatorer alltid hanteras: se
# ackumulering.py:s "grön"/"gul"/"röd" och app_vy._STATUS_TILL_EMOJI, som är
# textetiketter/emoji, ALDRIG färg som enda bärare). Validerad mot
# dataviz-skriptet: grön/röd ligger på ΔE 4,1 för deuteranopi — under golvet,
# alltså INTE säkert särskiljbara för en färgblind användare på hue ensam.
# Mitigeringen är därför INTE en fjärde färg utan en POSITIONELL sekundärkod:
# fpa_dashboard ritar en nollinje (gränsen för röd) och, om en varningströskel
# är satt, en till linje vid tröskeln (gränsen för gul) — så gränserna går att
# läsa av Y-LÄGET, inte bara av hue. Se _rendera_likviditetsflik.
FARG_LIKVIDITET_GRON = "#0ca30c"
FARG_LIKVIDITET_GUL = "#fab219"
FARG_LIKVIDITET_ROD = "#d03b3b"
_STATUS_TILL_FARG: dict[str, str] = {
    "grön": FARG_LIKVIDITET_GRON,
    "gul": FARG_LIKVIDITET_GUL,
    "röd": FARG_LIKVIDITET_ROD,
}

# Egen, kategorisk färg (violett) för "historiskt sen kund"-lagret — medvetet
# UTANFÖR statuspaletten ovan (en historiskt sen kund är en identitet/
# annotering, inte ett tredje risktillstånd) och långt ifrån grön/gul/röds
# hue-familj. Kombineras i fpa_dashboard med en egen markörform (diamant, inte
# stapelns punkt) — färg bär aldrig identiteten ensam.
FARG_HISTORISKT_SEN_KUND = "#4a3aa7"

# Egen, kategorisk färg (teal) för momshändelsen — av SAMMA skäl som ovan
# UTANFÖR statuspaletten (moms är en identitet/annotering, inte ett fjärde
# risktillstånd). Validerad mot dataviz-skriptet tillsammans med de fyra
# ovanstående (grön/gul/röd/violett sen-kund): klarar kromagolv, CVD-
# separation och normalsyns-golv i BÅDE ljust och mörkt läge (de enda kvarv-
# arande FAIL/WARN hör till redan existerande #fab219/#4a3aa7, inte den här
# färgen). Kombineras i fpa_dashboard med en egen markörform (kvadrat, inte
# stapelns punkt eller sen-kunds diamant) — färg bär aldrig identiteten ensam.
FARG_MOMS = "#0e8f9e"


def likviditetsprognos_fran_reskontra(
    leverantorsreskontra: list[Leverantorspost] | None,
    kundreskontra: list[Kundpost] | None,
    nuvarande_kassa: Decimal,
    prognosdatum: date,
    kundbetalbeteende: dict[str, int | Decimal] | None = None,
    antal_dagar: int = LIKVIDITETSPROGNOS_DAGAR,
    varningströskel: Decimal | None = None,
    momssaldo: Decimal | None = None,
) -> dict[str, Any]:
    """Glue: mappar de redan GDPR-tvättade Leverantorspost/Kundpost-listorna
    (samma listor som redan visas via samtalsflode._reskontra_rader) till det
    dict-kontrakt fpa_motor.bygg_likviditetsprognos förväntar sig, och kör
    motorn. Ingen egen beräkning — bara namnbyten (leverantor/kund -> motpart,
    orgnr-baserad motpart_id redan satt på Kundpost).

    None-listor (t.ex. saknad ea:purchase/ea:sales-behörighet mot Spiris)
    tolkas som TOMMA listor, inte ett fel: en ofullständig reskontra ska ändå
    ge en prognos byggd på det som FINNS, inte blockera hela vyn.

    forfallodatum saknas (None) bara om posten byggdes utan Spiris-adaptern
    (t.ex. en handbyggd testpost) — sådana poster utelämnar medvetet
    "forfallodatum"-nyckeln så att fpa_motor:s egen fail-closed-validering
    ("saknar belopp/förfallodatum") fångar dem med samma felmeddelande som
    redan är testat där, i stället för att duplicera kontrollen här.

    momssaldo (se momssaldo_fran_sie) är den redan avstämda momsnetto-
    positionen, RAW SIE-tecken. None ELLER exakt 0 (inget momskonto med
    saldo) ger INGEN momshändelse alls — precis som en tom reskontra, ett
    fail-safe normaltillstånd, inte ett fel. Förfallodagen sätts alltid till
    nästa standard-momsdag (nasta_momsforfallodag) räknat från prognosdatum —
    motorn tar aldrig själv ställning till väggklockan."""

    def _leverantorsfaktura(post: Leverantorspost) -> dict:
        rad: dict[str, Any] = {"motpart": post.leverantor, "belopp": post.belopp}
        if post.forfallodatum is not None:
            rad["forfallodatum"] = post.forfallodatum
        return rad

    def _kundfaktura(post: Kundpost) -> dict:
        rad: dict[str, Any] = {
            "motpart": post.kund,
            "motpart_id": post.motpart_id,
            "belopp": post.belopp,
        }
        if post.forfallodatum is not None:
            rad["forfallodatum"] = post.forfallodatum
        return rad

    momshandelse = (
        {"belopp": momssaldo, "forfallodatum": nasta_momsforfallodag(prognosdatum)}
        if momssaldo
        else None
    )

    return bygg_likviditetsprognos(
        nuvarande_kassa,
        prognosdatum,
        [_leverantorsfaktura(post) for post in (leverantorsreskontra or [])],
        [_kundfaktura(post) for post in (kundreskontra or [])],
        kundbetalbeteende=kundbetalbeteende,
        antal_dagar=antal_dagar,
        varningströskel=varningströskel,
        momshandelse=momshandelse,
    )


def likviditetsprognos_med_varningstroskel(
    prognos: dict, varningströskel: Decimal | None
) -> dict[str, Any]:
    """Räknar om ENDAST statusfältet (grön/gul/röd) per dag med en
    varningströskel som blir känd EFTER att prognosen redan byggts — samma
    mönster som nyckeltal_med_personalkostnad ovan: en Streamlit-widgets
    värde (kronbeloppet användaren skriver in i likviditetsfliken) kan bara
    läsas av VID rendering, efter att bygg_likviditetsprognos redan körts.

    Återanvänder fpa_motor.likviditetsstatus (samma funktion motorn själv
    anropar) i stället för att duplicera tröskellogiken här — statusregeln
    ska ägas på EN plats. Muterar inte originalet; alla andra fält (kassa,
    händelser, lägsta_kassa, ...) förblir precis som motorn räknade dem."""
    return {
        **prognos,
        "dagar": [
            {**dag, "status": likviditetsstatus(dag["utgaende_kassa"], varningströskel)}
            for dag in prognos["dagar"]
        ],
    }


def likviditetsgraf_data(prognos: dict) -> dict[str, Any]:
    """Mappar en FÄRDIG likviditetsprognos (fpa_motor.bygg_likviditetsprognos)
    till Plotly-redo serier. Tre lager: dagsserien (kassa per dag, färgkodad
    efter status), en overlay av ENDAST de dagar som har minst en historiskt
    sen kundinbetalning, och en overlay av ENDAST den dag (om någon) som har
    en momshändelse — så UI:t kan visa vart och ett som ett eget,
    identifierbart lager (egen färg + egen markörform i fpa_dashboard) utan
    att räkna om något. Beloppen lämnas som Decimal; fpa_dashboard formaterar
    (samma ansvarsfördelning som stapeldata_resultat_bi ovan)."""
    dagar = prognos["dagar"]
    sena_dagar = [
        dag for dag in dagar if any(h["har_historisk_justering"] for h in dag["handelser"])
    ]
    moms_dagar = [dag for dag in dagar if any(h["typ"] == "moms" for h in dag["handelser"])]
    return {
        "datum": [dag["datum"] for dag in dagar],
        "kassa": [dag["utgaende_kassa"] for dag in dagar],
        "farg": [_STATUS_TILL_FARG.get(dag["status"], FARG_LIKVIDITET_GRON) for dag in dagar],
        "dag_nr": [dag["dag_nr"] for dag in dagar],
        "sen_kund_datum": [dag["datum"] for dag in sena_dagar],
        "sen_kund_kassa": [dag["utgaende_kassa"] for dag in sena_dagar],
        "sen_kund_dag_nr": [dag["dag_nr"] for dag in sena_dagar],
        "moms_datum": [dag["datum"] for dag in moms_dagar],
        "moms_kassa": [dag["utgaende_kassa"] for dag in moms_dagar],
        "moms_dag_nr": [dag["dag_nr"] for dag in moms_dagar],
    }


def likviditetsdagar_ur_punkter(punkter: list[dict]) -> list[int]:
    """Plockar dag_nr ur Plotly-selectionens punkter (varje punkt i
    likviditetsgrafen bär sitt dag_nr i customdata) — samma mönster som
    valda_segment_ur_punkter nedan. Tål allt frontend kan skicka: punkter utan
    customdata eller icke-numeriskt innehåll sorteras bort. Dubbletter tas
    bort, ordningen är klickordningen."""
    dagnummer: list[int] = []
    for punkt in punkter:
        customdata = punkt.get("customdata") or []
        if not customdata:
            continue
        try:
            dag_nr = int(customdata[0])
        except (TypeError, ValueError):
            continue
        if dag_nr not in dagnummer:
            dagnummer.append(dag_nr)
    return dagnummer


def vattenfall_kassaflode(rapport: dict) -> list[tuple[str, float, str]]:
    """Grupperar kassaflödet till vattenfallssteg (etikett, belopp, measure) för
    Plotly: brygga från Rörelseresultat till Årets kassaflöde. 'absolute' =
    startstapel, 'relative' = steg, 'total' = slutstapel. Stegen summerar till
    årets kassaflöde (ren omgruppering av motorns färdiga poster)."""
    lp = rapport["lopande"]["poster"]
    justeringar = (
        lp["finansnetto"]
        + lp["bokslutsdispositioner_skatt"]
        + lp["avskrivningar"]
        + lp["forandring_obeskattade_reserver"]
        + lp["forandring_avsattningar"]
    )
    rorelsekapital = (
        lp["forandring_varulager"]
        + lp["forandring_kortfristiga_fordringar"]
        + lp["forandring_kortfristiga_skulder"]
    )
    return [
        ("Rörelseresultat", float(lp["rorelseresultat"]), "absolute"),
        ("Justeringar", float(justeringar), "relative"),
        ("Rörelsekapital", float(rorelsekapital), "relative"),
        ("Investeringar", float(rapport["investering"]["summa"]), "relative"),
        ("Finansiering", float(rapport["finansiering"]["summa"]), "relative"),
        ("Årets kassaflöde", float(rapport["arets_kassaflode"]), "total"),
    ]


def konton_i_grupp(rapport: dict, grupp: str) -> list[dict]:
    """De (redan normaliserade, redan grupperade) kontona i en viss grupp — för
    drill-down-tabellen under en expander. Ren filtrering, ingen logik."""
    return [k for k in rapport["konton"] if k["grupp"] == grupp]


from formatering import formatera_tal
from formatering_ui import hamta_val

_TUSENTAL = " "  # non-breaking space: svensk tusentalsavgränsare som inte radbryts


def formatera_kr(varde: Any) -> str:
    """Formaterar ett Decimal/float-belopp som svenska kronor.
    Avänder formateringsval från UI."""
    return formatera_tal(varde, hamta_val()) + _TUSENTAL + "kr"


def stapeldata_resultat(rapport: dict) -> dict[str, float]:
    """De stora P&L-posterna för ett enkelt stapeldiagram (float för plottning).
    Motorn har redan normaliserat tecknen — intäkter/kostnader positiva."""
    poster = rapport["poster"]
    return {
        "Totala intäkter": float(poster["totala_intakter"]),
        "Totala kostnader": float(poster["totala_kostnader"]),
        "Rörelseresultat": float(poster["rorelseresultat"]),
    }


# BI-stapelfärger: intäkter grön, kostnader röd/orange, resultat blå.
FARG_INTAKT = "#2e9e5b"
FARG_KOSTNAD = "#e8743b"
FARG_RESULTAT = "#2f6fdb"


# Valbara graftyper för Resultatrapporten (st.radio i dashboarden).
GRAFTYPER: list[str] = ["Standard (Staplar)", "Vattenfallsdiagram"]


def stapeldata_resultat_bi(rapport: dict) -> list[tuple[str, float, str]]:
    """Tre staplar för P&L i BI-stil, i EXAKT ordning: (etikett, belopp, färg).
    Totala intäkter (grön), Kostnader (röd/orange), Resultat = rörelseresultat
    (blå) — 'Intäkter − Kostnader = Resultat'. Färg och ordning bor här."""
    poster = rapport["poster"]
    return [
        ("Totala intäkter", float(poster["totala_intakter"]), FARG_INTAKT),
        ("Kostnader", float(poster["totala_kostnader"]), FARG_KOSTNAD),
        ("Resultat", float(poster["rorelseresultat"]), FARG_RESULTAT),
    ]


def _negerat(värde: Any) -> float:
    """Negerar ett belopp och normaliserar -0.0 till 0.0 — annars renderas en
    nollkostnad som '-0 kr' i grafen."""
    return -float(värde) or 0.0


def vattenfall_resultat(rapport: dict) -> list[tuple[str, float, str]]:
    """P&L-resan som vattenfallssteg (etikett, belopp, measure) för Plotly:
    från Totala intäkter, ned genom kostnadsslagen, till Resultat.

    Kostnaderna bryts upp i sina tre beståndsdelar (KSV + övriga rörelsekostnader
    + av-/nedskrivningar = totala kostnader), så vattenfallet landar i exakt
    samma Resultat som stapeldiagrammet. Stegen är 'relative' (Plotly färgar dem
    increasing/decreasing = grönt/rött, samma färgspråk som staplarna) och sista
    stapeln är 'total' (blå)."""
    poster = rapport["poster"]
    return [
        ("Totala intäkter", float(poster["totala_intakter"]), "relative"),
        ("Kostnad sålda varor", _negerat(poster["kostnad_salda_varor"]), "relative"),
        ("Övriga rörelsekostnader", _negerat(poster["ovriga_rorelsekostnader"]), "relative"),
        ("Av- och nedskrivningar", _negerat(poster["avskrivningar"]), "relative"),
        ("Resultat", float(poster["rorelseresultat"]), "total"),
    ]


def resultattabell_rader(rapport: dict) -> list[dict]:
    """Rader för P&L-tabellen (st.dataframe): {"Post", "Belopp" (float, kr),
    "_summa"}. Beloppet är numeriskt så st.dataframe högerjusterar det och
    column_config kan tusentalsformatera. _summa = True för del-/slutsummor
    (Bruttovinst, EBITDA, Rörelseresultat, EBT, Årets resultat) som ska ha
    fetstil; False för de vanliga posterna. Följer RESULTAT_UPPSTALLNING."""
    poster = rapport["poster"]
    return [
        {
            "Post": etikett,
            # Hela kronor (som metric-korten) för en ren, konsekvent tabell.
            "Belopp": float(round(poster[nyckel])),
            "_summa": radtyp != "grupp",
        }
        for nyckel, etikett, radtyp in RESULTAT_UPPSTALLNING
    ]


_SAKNAS = "–"  # visas när ett nyckeltal är None (odefinierat) — aldrig ett falskt 0


def formatera_procent(kvot: Any) -> str:
    """Formaterar en kvot (0.573) som procent (57,3 %). None -> streck. Ren
    strängformatering; räknar inte om något. Icke-brytande mellanslag före
    procenttecknet, så det inte hamnar på egen rad i en smal kolumn."""
    if kvot is None:
        return _SAKNAS
    val = hamta_val()
    d = max(1, val.decimaler)
    return f"{float(kvot) * 100:.{d}f}".replace(".", val.decimalseparator) + _TUSENTAL + "%"


def formatera_procentenheter(fore: Any, efter: Any) -> str | None:
    """Förändringen mellan två kvoter uttryckt i procentenheter, för st.metric:s
    delta ("-30,5 p.e."). Returnerar None när deltat saknar mening — odefinierat
    värde eller ingen förändring — så Streamlit ritar inget delta i stället för
    en falsk nolla."""
    if fore is None or efter is None or fore == efter:
        return None
    val = hamta_val()
    d = max(1, val.decimaler)
    delta = (float(efter) - float(fore)) * 100
    tecken = "+" if delta > 0 else ""
    return f"{tecken}{delta:.{d}f}".replace(".", val.decimalseparator) + _TUSENTAL + "p.e."


def formatera_multipel(kvot: Any) -> str:
    """Formaterar en kvot som en multipel (2.3 -> "2,3x"). None -> streck."""
    if kvot is None:
        return _SAKNAS
    val = hamta_val()
    d = max(2, val.decimaler)
    return f"{float(kvot):.{d}f}".replace(".", val.decimalseparator) + "x"


def formatera_nyckeltal(värde: Any, format: str, som_procent: bool = True) -> str:
    """Formaterar ett nyckeltalsvärde enligt dess format ("procent" | "kr" |
    "multipel"). None (odefinierat ELLER ännu ej implementerad platshållare) ->
    streck. Procent-nyckeltal följer procent/kvot-toggeln; kr/multipel gör inte."""
    if värde is None:
        return _SAKNAS
    if format == "kr":
        return formatera_kr(värde)
    if format == "multipel":
        return formatera_multipel(värde)
    return formatera_procent(värde) if som_procent else formatera_multipel(värde)


def radbryt(lista: list, per_rad: int) -> list[list]:
    """Delar en lista i delrader om högst per_rad element — för en st.columns-
    layout som bryts på flera rader när många nyckeltal valts."""
    return [lista[i : i + per_rad] for i in range(0, len(lista), per_rad)]


# Tooltip-text (st.metric help) för soliditeten — exakt formulering enligt
# arkitektdirektiv, förklarar skillnaden mellan bokfört EK och justerat EK (JEK).
SOLIDITET_HELP = (
    "Soliditet visar hur stor del av företagets tillgångar som är finansierade "
    "med egna medel. En hög soliditet innebär låg finansiell risk.\n\n"
    "Standard: Räknar endast bokfört Eget Kapital.\n"
    "Justerat EK (JEK): Inkluderar den del av obeskattade reserver som efter "
    "avdragen bolagsskatt (20,6 %) tillhör ägarna, vilket ofta ger en högre och "
    "mer rättvisande bild av bolagets betalningsförmåga."
)

@dataclass(frozen=True)
class Nyckeltalsdef:
    """Katalogpost för ett nyckeltal: motor-nyckel, etikett, visningsformat
    ("procent" | "kr" | "multipel"), hjälptext, om det visas som default och om
    formeln är implementerad (annars platshållare tills matten byggts)."""

    nyckel: str
    etikett: str
    format: str
    hjalp: str
    default: bool = False
    implementerad: bool = True


# Katalogen driver st.multiselect + renderingen. De fyra första är default;
# resten är valbara platshållare vars formler byggs i nästa steg.
NYCKELTAL_KATALOG: list[Nyckeltalsdef] = [
    Nyckeltalsdef(
        "bruttomarginal", "Bruttomarginal", "procent",
        "Bruttovinst i förhållande till totala intäkter — hur mycket som blir kvar "
        "efter kostnad sålda varor.", default=True,
    ),
    Nyckeltalsdef(
        "rorelsemarginal", "Rörelsemarginal (EBIT)", "procent",
        "Rörelseresultat i förhållande till totala intäkter — lönsamheten i den "
        "löpande driften, före finansiella poster och skatt.", default=True,
    ),
    Nyckeltalsdef("soliditet", "Soliditet", "procent", SOLIDITET_HELP, default=True),
    Nyckeltalsdef(
        "kassalikviditet", "Kassalikviditet", "procent",
        "Likvida omsättningstillgångar (exkl. varulager) i förhållande till "
        "kortfristiga skulder — kortsiktig betalningsförmåga. Över 100 % anses sunt.",
        default=True,
    ),
    Nyckeltalsdef(
        "vinstmarginal", "Vinstmarginal", "procent",
        "Årets resultat i förhållande till totala intäkter — hur stor andel av "
        "varje omsatt krona som blir kvar efter alla kostnader, finansnetto och skatt.",
    ),
    Nyckeltalsdef(
        "ebitda", "EBITDA", "kr",
        "Rörelseresultat före av- och nedskrivningar — ett mått på det operativa "
        "kassaflödet, oberoende av bolagets investeringstakt och avskrivningsmetod.",
    ),
    Nyckeltalsdef(
        "ebita_marginal", "EBITA-marginal", "procent",
        "EBITA (rörelseresultat plus avskrivningar på immateriella tillgångar, "
        "t.ex. goodwill) i förhållande till totala intäkter. Till skillnad från "
        "EBITDA belastas EBITA fortfarande av avskrivningar på maskiner och "
        "byggnader — bara den immateriella delen läggs tillbaka.",
    ),
    Nyckeltalsdef(
        "roe", "Avkastning på eget kapital (ROE)", "procent",
        "Årets resultat i förhållande till eget kapital vid periodens slut — "
        "avkastningen ägarna får på sitt insatta kapital.",
    ),
    Nyckeltalsdef(
        "roa", "Avkastning på totalt kapital (ROA)", "procent",
        "Rörelseresultat i förhållande till balansomslutningen — hur effektivt "
        "bolagets samlade tillgångar genererar resultat, oavsett hur de är "
        "finansierade.",
    ),
    Nyckeltalsdef(
        "roce", "Avkastning på sysselsatt kapital (ROCE)", "procent",
        "Rörelseresultat i förhållande till sysselsatt kapital (balansomslutning "
        "minus kortfristiga skulder) — avkastningen på det kapital ägare och "
        "långivare bundit i bolaget.",
    ),
    Nyckeltalsdef(
        "skuldsattningsgrad", "Skuldsättningsgrad", "multipel",
        "Skulder (avsättningar, långfristiga och kortfristiga skulder — exkl. "
        "obeskattade reserver) i förhållande till eget kapital.",
    ),
    Nyckeltalsdef(
        "fritt_kassaflode", "Fritt kassaflöde", "kr",
        "Kassaflöde från löpande verksamhet minus investeringar — det som blir "
        "kvar för amortering, utdelning eller nya investeringar.",
    ),
    Nyckeltalsdef(
        "personalkostnad_per_anstalld", "Personalkostnad per anställd", "kr",
        "Personalkostnader delat på antal anställda. SIE4 innehåller ingen "
        "personalstyrka — ange antalet anställda ovanför korten för att räkna ut "
        "nyckeltalet.",
    ),
]

DEFAULT_NYCKELTAL: list[str] = [d.etikett for d in NYCKELTAL_KATALOG if d.default]


def valj_nyckeltal(valda_etiketter: list[str]) -> list[Nyckeltalsdef]:
    """Nyckeltalsdef:ar i EXAKT den ordning etiketterna ligger i valda_etiketter.
    Multiselect-ordningen = användarens 'drag and drop' — renderingen följer den,
    inte katalogordningen. Okända etiketter hoppas tyst över."""
    per_etikett = {d.etikett: d for d in NYCKELTAL_KATALOG}
    return [per_etikett[etikett] for etikett in valda_etiketter if etikett in per_etikett]


# --- Balansräkningen som staplad stapel ---------------------------------------
#
# Två staplar sida vid sida: Tillgångar mot Finansiering. Balanserar bokföringen
# är staplarna exakt lika höga — obalansen syns direkt som en höjdskillnad, och
# bekräftas av kontrolldiff i health check-bannern.
#
# Segmenten ligger på BAS 2-siffrig kontogruppsnivå (12 Maskiner och inventarier,
# 15 Kundfordringar, 19 Kassa och bank ...), en nivå finare än uppställningens
# huvudposter. Allt som inte har ett eget segment hamnar i en "Övrigt"-hink per
# stapel, vars belopp definieras som STAPELNS SLUTSUMMA MINUS de visade segmenten.
# Det är inte en genväg utan hela poängen: en BAS-grupp kan ha NEGATIVT saldo
# (t.ex. skatteskulder 2510 med debetsaldo), och negativa poster går inte att
# stapla. Hinken absorberar dem, så stapeln summerar exakt till slutsumman i
# stället för att bli för hög. Skulle hinken själv bli negativ krymper vi den
# genom att flytta ned det minsta visade segmentet i den — se _segment_for_stapel.
#
# FÄRG följer familjen och är bunden till segmentets IDENTITET, aldrig till dess
# storlek eller rang: tillgångar i blått spektrum, ägarkapital grönt, skulder
# orange. Ett segment som faller bort ur diagrammet får aldrig repaint:a de andra.
# Skalan är validerad med dataviz-validatorn (ljushetsband, kromagolv,
# CVD-separation för angränsande par): värsta angränsande par är ΔE 12,1 för
# tillgångsstapeln och 14,1 för finansieringsstapeln, mot kravet ≥ 12. Flera
# segment ligger under 3:1 kontrast mot ytan, vilket utlöser reliefregeln — därför
# bär varje segment en SYNLIG inline-etikett med namn och belopp, och den
# klassiska BAS-uppställningen finns som tabellvy. Identitet bärs aldrig av färg
# ensam. Övrigt-hinken är avsiktligt neutral grå: den är en restpost, inte en
# entitet, och ska läsas som recessiv.

FARG_BYGGNADER = "#1b4f9e"
FARG_MASKINER = "#2f6fdb"
FARG_VARULAGER = "#1d8ac4"
FARG_KUNDFORDRINGAR = "#39a7c9"
FARG_KASSA = "#7fb0f0"
FARG_EGET_KAPITAL = "#1f7a44"
FARG_OBESKATTADE_RESERVER = "#58c98a"
FARG_LANGFRISTIGA_SKULDER = "#b8521f"
FARG_LEVERANTORSSKULDER = "#e8743b"
FARG_UPPLUPNA_KOSTNADER = "#ee9a6e"
# Två neutrala grå: en sval för tillgångshinken, en varm för skuldhinken. De är
# avsiktliga neutraler (restposter, inte entiteter) och står därför utanför den
# kategoriska paletten och dess kromagolv — men de skiljer sig ändå åt, så att
# ingen legendrad delar swatch med en annan.
FARG_OVRIGT_TILLGANG = "#8792a3"
FARG_OVRIGT_SKULD = "#a1928a"

# Ett segment får inline-etikett bara om det är högt nog att rymma en rad text.
# Andelen är av stapelns slutsumma. Tröskeln är kalibrerad mot vad Plotly FAKTISKT
# renderar, inte mot teori: med 14 px FET text behöver raden ~24 px, vilket i den
# ritade plotytan motsvarar ~5 %. (3 % och 4 % visade sig för optimistiska — då
# gömde uniformtext texten ändå, och de två mekanismerna sa olika saker.) Tunnare
# segment identifieras av legend, hover och drill-down i stället för av en
# hoptryckt, oläslig etikett.
INLINE_TEXT_TROSKEL = 0.05

# Typografi i den grafiska vyn. Stora, feta etiketter i ett rent sans-snitt —
# siffror ska gå att läsa på en projektor, inte kisas fram.
TYPSNITT = "Inter, Segoe UI, Helvetica Neue, Arial, sans-serif"
INLINE_TEXT_STORLEK = 14
AXELTITEL_STORLEK = 18
LEGEND_STORLEK = 14
DIAGRAMTITEL_STORLEK = 20

# Textfärger inuti segmenten. Vilken som används avgörs per segment av
# kontrasten — aldrig hårdkodat till vit: sex av tolv segmentfärger är för ljusa
# för vit text (ned till 2,07:1, långt under WCAG:s 4,5:1).
TEXT_PA_MORK_YTA = "#ffffff"
TEXT_PA_LJUS_YTA = "#10151c"

STAPEL_TILLGANGAR = "Tillgångar"
STAPEL_FINANSIERING = "Finansiering"

# Stapelns slutsumma — den som segmenten MÅSTE summera till.
STAPEL_SLUTSUMMA: dict[str, str] = {
    STAPEL_TILLGANGAR: "summa_tillgangar",
    STAPEL_FINANSIERING: "summa_eget_kapital_och_skulder",
}

# Vyväxlaren i balansfliken. Den grafiska vyn är standard.
BALANSVYER: tuple[str, str] = ("Grafisk vy", "Klassisk BAS-uppställning")

# Rapportflikens undernavigering. Resultat- och balansrapporten är bolagets två
# finansiella grundrapporter och läses ihop; nyckeltalen och kassaflödet är egna
# analyser med egna kontroller och behåller därför egna flikar. Likviditets-
# prognosen är Spiris-ENDAST (kräver reskontra/förfallodatum en SIE-fil aldrig
# bär) — fliken finns alltid, men visar en förklarande text i fil-läge.
RAPPORTFLIKAR: tuple[str, str, str, str] = (
    "Resultat & Balansrapport",
    "Nyckeltal",
    "Kassaflöde",
    "Likviditetsprognos",
)


@dataclass(frozen=True)
class Balanssegment:
    """Ett färgat segment i en av de två staplarna.

    undergrupper är de BAS-kontogrupper segmentet omfattar — de styr BÅDE
    beloppet (summan av deras konton) och drill-downen (vilka konton som visas).
    kortnamn är inline-etiketten i stapeln, som måste rymmas i ett smalt block."""

    nyckel: str
    etikett: str
    kortnamn: str
    stapel: str
    undergrupper: tuple[str, ...]
    farg: str
    # "tillgang" | "kapital" | "skuld". Styr vilka segment som får flyttas ned i
    # Övrigt-hinken: hinken tar i första hand sin EGEN familj, så att t.ex.
    # obeskattade reserver (kapital) aldrig hamnar under etiketten "Övriga
    # skulder och avsättningar" och därmed påstår något falskt.
    familj: str = "tillgang"
    ar_ovrigt: bool = False


# Ordningen är staplingsordningen, nedifrån och upp: trögast tillgångar underst,
# mest efterställt kapital underst. Övrigt-hinken ligger alltid överst i sin stapel.
BALANS_SEGMENT: list[Balanssegment] = [
    Balanssegment(
        nyckel="byggnader_och_mark",
        etikett="Byggnader och mark",
        kortnamn="Byggnader",
        stapel=STAPEL_TILLGANGAR,
        undergrupper=("11",),
        farg=FARG_BYGGNADER,
    ),
    Balanssegment(
        nyckel="maskiner_och_inventarier",
        etikett="Maskiner och inventarier",
        kortnamn="Maskiner",
        stapel=STAPEL_TILLGANGAR,
        undergrupper=("12",),
        farg=FARG_MASKINER,
    ),
    Balanssegment(
        nyckel="varulager",
        etikett="Varulager",
        kortnamn="Varulager",
        stapel=STAPEL_TILLGANGAR,
        undergrupper=("14",),
        farg=FARG_VARULAGER,
    ),
    Balanssegment(
        nyckel="kundfordringar",
        etikett="Kundfordringar",
        kortnamn="Kundfordringar",
        stapel=STAPEL_TILLGANGAR,
        undergrupper=("15",),
        farg=FARG_KUNDFORDRINGAR,
    ),
    # BAS 18 (kortfristiga placeringar) hör till samma huvudpost som 19 i
    # uppställningen och slås ihop hit, precis som _grupp_och_tecken_balans gör.
    Balanssegment(
        nyckel="kassa_och_bank",
        etikett="Kassa och bank",
        kortnamn="Kassa",
        stapel=STAPEL_TILLGANGAR,
        undergrupper=("18", "19"),
        farg=FARG_KASSA,
    ),
    Balanssegment(
        nyckel="ovriga_tillgangar",
        etikett="Övriga tillgångar",
        kortnamn="Övrigt",
        stapel=STAPEL_TILLGANGAR,
        undergrupper=("10", "13", "16", "17"),
        farg=FARG_OVRIGT_TILLGANG,
        ar_ovrigt=True,
    ),
    Balanssegment(
        nyckel="eget_kapital",
        etikett="Eget kapital",
        kortnamn="Eget kapital",
        stapel=STAPEL_FINANSIERING,
        undergrupper=("20",),
        farg=FARG_EGET_KAPITAL,
        familj="kapital",
    ),
    Balanssegment(
        nyckel="obeskattade_reserver",
        etikett="Obeskattade reserver",
        kortnamn="Obesk. reserver",
        stapel=STAPEL_FINANSIERING,
        undergrupper=("21",),
        farg=FARG_OBESKATTADE_RESERVER,
        familj="kapital",
    ),
    Balanssegment(
        nyckel="langfristiga_skulder",
        etikett="Långfristiga skulder",
        kortnamn="Långfr. skulder",
        stapel=STAPEL_FINANSIERING,
        undergrupper=("23",),
        farg=FARG_LANGFRISTIGA_SKULDER,
        familj="skuld",
    ),
    Balanssegment(
        nyckel="leverantorsskulder",
        etikett="Leverantörsskulder m.m.",
        kortnamn="Lev.skulder",
        stapel=STAPEL_FINANSIERING,
        undergrupper=("24",),
        farg=FARG_LEVERANTORSSKULDER,
        familj="skuld",
    ),
    Balanssegment(
        nyckel="upplupna_kostnader",
        etikett="Upplupna kostnader och förutbetalda intäkter",
        kortnamn="Upplupet",
        stapel=STAPEL_FINANSIERING,
        undergrupper=("29",),
        farg=FARG_UPPLUPNA_KOSTNADER,
        familj="skuld",
    ),
    # Avsättningar (22) ligger i hinken, inte som eget segment: de är oftast noll
    # och färgbudgeten räcker inte till. Etiketten namnger dem, och hinken ingår
    # i summan — kapitalet försvinner alltså aldrig ur diagrammet.
    Balanssegment(
        nyckel="ovriga_skulder",
        etikett="Övriga skulder och avsättningar",
        kortnamn="Övrigt",
        stapel=STAPEL_FINANSIERING,
        undergrupper=("22", "25", "26", "27", "28"),
        farg=FARG_OVRIGT_SKULD,
        familj="skuld",
        ar_ovrigt=True,
    ),
]


def segment_med_nyckel(nyckel: str) -> Balanssegment | None:
    """Slår upp ett segment. Okänd nyckel ger None — en klick i grafen får aldrig
    krascha vyn, oavsett vad frontend skickar tillbaka."""
    for segment in BALANS_SEGMENT:
        if segment.nyckel == nyckel:
            return segment
    return None


def _belopp_per_undergrupp(balansrapport: dict) -> dict[str, Decimal]:
    """Summerar de normaliserade kontosaldona per BAS-kontogrupp. Motorn har redan
    vänt tecknen och satt undergrupp — här räknas bara ihop."""
    summor: dict[str, Decimal] = {}
    for konto in balansrapport["konton"]:
        undergrupp = konto["undergrupp"]
        summor[undergrupp] = summor.get(undergrupp, Decimal("0")) + konto["saldo"]
    return summor


def _segment_for_stapel(balansrapport: dict, stapel: str) -> tuple[list[dict], list[str]]:
    """Bygger EN stapels segment. Returnerar (segment, etiketter_som_hamnade_i_ovrigt).

    Invariant: summan av de returnerade segmentens belopp == stapelns slutsumma,
    exakt. Det är den invarianten som gör att de två staplarna blir lika höga när
    bokföringen balanserar — och den vi offrar granularitet för att hålla."""
    slutsumma = balansrapport["poster"][STAPEL_SLUTSUMMA[stapel]]
    per_undergrupp = _belopp_per_undergrupp(balansrapport)

    i_stapeln = [s for s in BALANS_SEGMENT if s.stapel == stapel]
    namngivna = [s for s in i_stapeln if not s.ar_ovrigt]
    ovrigt = next(s for s in i_stapeln if s.ar_ovrigt)

    def belopp(segment: Balanssegment) -> Decimal:
        return sum(
            (per_undergrupp.get(u, Decimal("0")) for u in segment.undergrupper),
            Decimal("0"),
        )

    if slutsumma <= 0:
        return [], []

    visade = [s for s in namngivna if belopp(s) > 0]
    nedflyttade: list[Balanssegment] = []
    # Negativa BAS-grupper gör att de positiva segmenten kan summera till MER än
    # stapelns slutsumma. Flytta då ned ett visat segment i Övrigt tills hinken är
    # icke-negativ igen. Deterministiskt, och totalen bevaras alltid.
    #
    # Valet av offer är inte "minsta först" rakt av: hinken tar i första hand sin
    # EGEN familj. Annars hade obeskattade reserver (kapital) kunnat hamna under
    # etiketten "Övriga skulder och avsättningar" — en etikett som då ljuger.
    # Inom familjen offras det minsta segmentet, så att så lite belopp som möjligt
    # döljs.
    def offerordning(segment: Balanssegment) -> tuple[int, Decimal]:
        return (0 if segment.familj == ovrigt.familj else 1, belopp(segment))

    while visade and slutsumma - sum((belopp(s) for s in visade), Decimal("0")) < 0:
        offer = min(visade, key=offerordning)
        visade.remove(offer)
        nedflyttade.append(offer)

    ovrigt_belopp = slutsumma - sum((belopp(s) for s in visade), Decimal("0"))
    # Hinken måste kunna drillas ned till exakt sitt eget belopp: den äger sina
    # egna undergrupper PLUS alla namngivna segment som inte visas (nedflyttade,
    # och de med noll- eller negativt saldo).
    dolda = [s for s in namngivna if s not in visade]
    ovrigt_undergrupper = ovrigt.undergrupper + tuple(u for s in dolda for u in s.undergrupper)

    # Skulle hinken ändå ha tvingats svälja en annan familj (alla egna offer
    # förbrukade) får den inte behålla sin familjeetikett. Neutral etikett i
    # stället för ett påstående som inte stämmer.
    ovrigt_etikett = ovrigt.etikett
    if any(s.familj != ovrigt.familj for s in nedflyttade):
        ovrigt_etikett = "Övriga poster"

    ut = [
        {
            "nyckel": s.nyckel,
            "etikett": s.etikett,
            "kortnamn": s.kortnamn,
            "stapel": s.stapel,
            "belopp": float(belopp(s)),
            "andel": float(belopp(s) / slutsumma),
            "farg": s.farg,
            "undergrupper": s.undergrupper,
        }
        for s in visade
    ]
    if ovrigt_belopp > 0:
        ut.append(
            {
                "nyckel": ovrigt.nyckel,
                "etikett": ovrigt_etikett,
                "kortnamn": ovrigt.kortnamn,
                "stapel": ovrigt.stapel,
                "belopp": float(ovrigt_belopp),
                "andel": float(ovrigt_belopp / slutsumma),
                "farg": ovrigt.farg,
                "undergrupper": ovrigt_undergrupper,
            }
        )
    return ut, [s.etikett for s in nedflyttade]


def _relativ_luminans(hexfarg: str) -> float:
    """WCAG 2.x relativ luminans för en #rrggbb-färg."""

    def kanal(varde: int) -> float:
        andel = varde / 255
        return andel / 12.92 if andel <= 0.03928 else ((andel + 0.055) / 1.055) ** 2.4

    r, g, b = (kanal(int(hexfarg[i : i + 2], 16)) for i in (1, 3, 5))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def kontrastkvot(forgrund: str, bakgrund: str) -> float:
    """WCAG-kontrastkvot mellan två #rrggbb-färger, 1:1 till 21:1."""
    ljus, mork = sorted((_relativ_luminans(forgrund), _relativ_luminans(bakgrund)), reverse=True)
    return (ljus + 0.05) / (mork + 0.05)


def text_farg(bakgrund: str) -> str:
    """Textfärgen som ger BÄST kontrast mot ett segments fyllning.

    Hårdkodad vit text hade sett bra ut på eget kapital (5,35:1) och katastrofal
    på kassa (2,24:1), obeskattade reserver (2,07:1) och upplupna kostnader
    (2,21:1) — alla långt under WCAG:s 4,5:1. Genom att välja per segment ligger
    sämsta kontrasten i hela diagrammet på 4,75:1. Färgen räknas ut, aldrig
    gissas."""
    return (
        TEXT_PA_MORK_YTA
        if kontrastkvot(TEXT_PA_MORK_YTA, bakgrund) >= kontrastkvot(TEXT_PA_LJUS_YTA, bakgrund)
        else TEXT_PA_LJUS_YTA
    )


def ryms_inline_text(andel: float) -> bool:
    """Är segmentet högt nog att rymma sin inline-etikett?

    Beslutet tas på segmentets ANDEL av stapeln, inte på pixlar: vy-lagret vet
    inte hur högt diagrammet renderas, och ett beslut i procent är dessutom
    testbart. Ett för tunt segment får ingen text alls — hellre ingen etikett än
    en hoptryckt, oläslig sådan (identiteten bärs av legend, hover och drill-down)."""
    return andel >= INLINE_TEXT_TROSKEL


def stapeldata_balans(balansrapport: dict) -> dict[str, Any]:
    """Mappar en FÄRDIG balansrapport till de två staplarnas segment.

    Kontraktet: varje stapels segment summerar EXAKT till stapelns slutsumma.
    Balanserar bokföringen blir staplarna alltså exakt lika höga. Nollposter
    utelämnas (ett nollhögt segment är bara en legendrad utan yta); negativa
    BAS-grupper absorberas i Övrigt-hinken i stället för att tyst förvanska
    stapelhöjden."""
    segment: list[dict] = []
    nedflyttade: list[str] = []
    for stapel in (STAPEL_TILLGANGAR, STAPEL_FINANSIERING):
        stapelsegment, stapel_nedflyttade = _segment_for_stapel(balansrapport, stapel)
        segment.extend(stapelsegment)
        nedflyttade.extend(stapel_nedflyttade)

    varning = None
    if nedflyttade:
        varning = (
            "Negativa saldon på BAS-gruppnivå gjorde att följande poster ryms i "
            "Övrigt i stället för i egna segment: " + ", ".join(nedflyttade) + ". "
            "Staplarna summerar fortfarande exakt till sina slutsummor — klicka på "
            "Övrigt för att se kontona."
        )
    elif not segment:
        varning = "Balansomslutningen är noll — det finns inget att visa."

    return {"segment": segment, "varning": varning}


def konton_i_segment(balansrapport: dict, undergrupper: tuple[str, ...]) -> list[dict]:
    """Kontona bakom ett segment, för drill-downen vid klick. Tar segmentets
    undergrupper (inte dess nyckel) eftersom Övrigt-hinkens innehåll bestäms av
    datat, inte av konfigurationen."""
    return [konto for konto in balansrapport["konton"] if konto["undergrupp"] in undergrupper]


def sortera_drilldown(konton: list[dict]) -> tuple[list[dict], list[dict]]:
    """Manage by exception: (aktiva, nollkonton).

    Aktiva konton (saldo ≠ 0) sorteras fallande på ABSOLUT belopp — ett stort
    negativt saldo är lika intressant som ett stort positivt och ska inte hamna
    längst ned. Kontonumret är sekundär, stabil sorteringsnyckel vid lika belopp.
    Nollkontona läggs för sig, sorterade på kontonummer, så att UI-lagret kan
    gömma dem bakom en expander i stället för att låta dem skymma sikten."""
    aktiva = [konto for konto in konton if konto["saldo"] != 0]
    nollkonton = [konto for konto in konton if konto["saldo"] == 0]
    aktiva.sort(key=lambda konto: (-abs(konto["saldo"]), konto["kontonr"]))
    nollkonton.sort(key=lambda konto: konto["kontonr"])
    return aktiva, nollkonton


def valda_segment_ur_punkter(punkter: list[dict]) -> list[str]:
    """Plockar segmentnycklar ur Plotly-selectionens punkter (varje stapelsegment
    bär sin nyckel i customdata).

    Tål allt frontend kan skicka: punkter utan customdata, okända nycklar och
    dubbletter (samma segment klickat två gånger) sorteras bort. Ordningen är
    klickordningen."""
    nycklar: list[str] = []
    for punkt in punkter:
        customdata = punkt.get("customdata") or []
        if not customdata:
            continue
        nyckel = str(customdata[0])
        if nyckel not in nycklar and segment_med_nyckel(nyckel) is not None:
            nycklar.append(nyckel)
    return nycklar


# --- Kapitalstack: investeringskalkylens vy-lager ----------------------------
#
# Formulärets display-config, Sankey-mappningen källor -> ny tillgång, och
# kompositionen av motorns delar (simulera_kapitalstack + berakna_wacc +
# bygg_nyckeltal). All matematik bor i fpa_motor; här bara etiketter, färger
# och ihopkoppling. UI-fritt, alltså testbart utan Streamlit-runtime.

# Posttypernas display-config. Etiketterna är MEDVETET vardagliga: "Eget
# kapital" och "Kassa" är bokföringstermer som en företagare läser som samma
# sak, trots att de gör olika saker i balansräkningen (ägarinsats ökar
# balansomslutningen, egna pengar byter bara form på tillgången). Skillnaden
# ligger nu i orden i stället för i facktermen — den korrekta termen står kvar
# som undertext i formuläret.
KAPITALSTACK_TYPER: tuple[str, ...] = ("lan", "agarinsats", "egna_pengar", "leasing")

TYPETIKETT: dict[str, str] = {
    "lan": "Lån",
    "agarinsats": "Ägarinsats",
    "egna_pengar": "Bolagets egna pengar",
    "leasing": "Leasing",
}

# Den bokföringstekniska termen bakom vardagsetiketten — visas som undertext.
TYP_FACKTERM: dict[str, str] = {
    "lan": "Långfristiga skulder",
    "agarinsats": "Eget kapital (nyemission/aktieägartillskott)",
    "egna_pengar": "Kassa och bank",
    "leasing": "Leasingavtal",
}

TYPFORKLARING: dict[str, str] = {
    "lan": "Extern finansiering med ränta — banklån, checkkredit, säljarrevers.",
    "agarinsats": (
        "NYA pengar som ägarna skjuter in i bolaget. Balansomslutningen växer."
    ),
    "egna_pengar": (
        "Pengar bolaget REDAN har på kontot. Balansomslutningen är oförändrad "
        "— kassan byter bara form till en anläggningstillgång."
    ),
    "leasing": "Du hyr tillgången i stället för att köpa den.",
}

# Kostnadsfältets etikett och hjälptext skiljer sig per typ: en ränta, ett
# avkastningskrav och en alternativkostnad är olika sorters tal.
KAPITALSTACK_KOSTNADSFALT: dict[str, tuple[str, str]] = {
    "lan": (
        "Ränta (%)",
        "Nominell låneränta. Räntan är avdragsgill, så efterskatte-WACC:en "
        "räknar med skatteskölden kd × (1 − bolagsskatt).",
    ),
    "agarinsats": (
        "Avkastningskrav (%)",
        "Ägarnas avkastningskrav. Förifylls med årets avkastning på eget "
        "kapital (årets resultat / eget kapital vid periodens slut) — ett "
        "förslag, inte en sanning. Betalas ur beskattad vinst: ingen skattesköld.",
    ),
    "egna_pengar": (
        "Alternativkostnad (%)",
        "Vad det kostar att tömma kassan: inlåningsränta, eller avkastningen "
        "pengarna hade gett någon annanstans. Egna pengar är ingen extern "
        "finansieringskälla och har ingen egen kapitalkostnad — talet är ditt.",
    ),
    "leasing": (
        "Leasingränta (%)",
        "Den ränta som ligger i leasingavgiften. Avgiften är avdragsgill och "
        "får därför skattesköld — men ett eventuellt utköpspris får det inte, "
        "eftersom utköpet är ett förvärv av en tillgång (K2 p. 10.12).",
    ),
}

# Startpunkt för ett tomt formulär: ETT lån och EN post egna pengar. Bara en
# utgångspunkt som summerar till 100 %, aldrig en rekommendation.
KAPITALSTACK_STANDARDRANTA = 5.0
KAPITALSTACK_STANDARD_ALTERNATIVKOSTNAD = 0.0
KAPITALSTACK_STANDARD_LEASINGRANTA = 4.0
KAPITALSTACK_STANDARD_LOPTID_AR = 3

# Sankey-färgerna följer balansstapelns familjespråk: skuld orange, kapital
# grönt, kassa blå. Den nya tillgången får anläggningstillgångarnas blå.
FARG_NY_INVESTERING = FARG_MASKINER
KAPITALSTACK_FARG: dict[str, str] = {
    "lan": FARG_LANGFRISTIGA_SKULDER,
    "agarinsats": FARG_EGET_KAPITAL,
    "egna_pengar": FARG_KASSA,
    "leasing": FARG_LEVERANTORSSKULDER,
}

# Leasingmetodens display-config. Texten är hela poängen med valet — därför
# ligger regelhänvisningarna här och inte bara i koden.
LEASINGMETODER: tuple[str, str] = ("operationell", "finansiell")

LEASINGMETOD_ETIKETT: dict[str, str] = {
    "operationell": "Operationell (linjär)",
    "finansiell": "Finansiell (effektivränta)",
}

LEASINGMETOD_FORKLARING: dict[str, str] = {
    "operationell": (
        "**Operationell leasing — du hyr.** Tillgången står kvar hos "
        "leasegivaren och hamnar aldrig i din balansräkning; du kostnadsför "
        "bara avgiften, fördelad **linjärt** över leasingperioden. Ett "
        "eventuellt utköp blir en ny tillgång först den dag du löser ut den.\n\n"
        "Det här är det vanliga för mindre bolag: K2 säger att *alla* "
        "leasingavtal ska redovisas som operationella (p. 7.10 och 9.4), och "
        "K3 låter en juridisk person välja samma sak (p. 20.29)."
    ),
    "finansiell": (
        "**Finansiell leasing — du äger i praktiken.** Riskerna och fördelarna "
        "med att äga har i allt väsentligt gått över på dig, så tillgången "
        "*och* skulden tas upp i balansräkningen (K3 p. 20.5). Avgiften delas "
        "i ränta och amortering enligt **effektivräntemetoden** (K3 p. 20.9) "
        "— räntan blir därför något lägre per år än en linjär fördelning.\n\n"
        "Talar för finansiell leasing: äganderätten övergår vid periodens "
        "slut, eller att utköpspriset är så lågt att det framstår som rimligt "
        "säkert att du kommer att utnyttja det (K3 p. 20.3)."
    ),
}

LEASING_VAL_HJALP = (
    "Valet styr både hur utköpspriset periodiseras och om leasingen alls "
    "syns i den projicerade balansräkningen."
)

NY_INVESTERING_NOD = "Ny investering"

# Kapitalstapelns enda kategori. Axeln är dold — konstanten finns för att
# Plotly ska stapla alla skikt på SAMMA rad, inte för att visas.
STAPEL_KAPITAL = "Finansiering"


def procentsumma(procent: list[int] | dict[str, int]) -> int:
    """Summan av kapitalstackens procentsatser. Måste bli 100."""
    varden = procent.values() if isinstance(procent, dict) else procent
    return sum(varden)


def kvot_fran_procent(varde: float | int) -> Decimal:
    """Procentsats (5.0) -> kvot (0.05). Går via str så flyttalets brus inte
    följer med in i Decimal-matematiken."""
    return Decimal(str(varde)) / Decimal("100")


def belopp_fran_procent(investering: Decimal, procent: list[int]) -> list[Decimal]:
    """Heltalsprocent -> delbelopp som summerar EXAKT till investeringen.

    Avrundningsresten läggs på den största posten. Utan det läcker ören ut ur
    balansräkningen, och motorns fail-closed-kontroll (posterna måste summera
    till investeringsbeloppet) slår till på en stack användaren upplever som
    korrekt.

    Anroparen ansvarar för att procentsatserna summerar till 100 — den
    kontrollen hör hemma i formuläret, där den kan visas live.
    """
    belopp = [
        (investering * Decimal(andel) / Decimal("100")).quantize(Decimal("0.01"))
        for andel in procent
    ]
    rest = investering - sum(belopp, Decimal("0"))
    if rest and belopp:
        storsta = max(range(len(belopp)), key=lambda i: belopp[i])
        belopp[storsta] += rest
    return belopp


def procent_fran_belopp(investering: Decimal, belopp: list[Decimal]) -> list[float]:
    """Delbelopp -> andelar i procent, för display bredvid beloppsfälten.
    Nollinvestering ger nollprocent i stället för division med noll."""
    if investering <= 0:
        return [0.0 for _ in belopp]
    return [round(float(del_ / investering) * 100, 1) for del_ in belopp]


def foreslaget_avkastningskrav_procent(
    resultatrapport: dict, balansrapport: dict
) -> float | None:
    """Förifyllt avkastningskrav på eget kapital, i procent — årets ROE.

    None när det inte går att härleda (negativt eller nollställt eget kapital,
    eller ett negativt resultat). Då ska UI:t säga det rent ut och låta
    användaren ange talet själv, inte förifylla en påhittad siffra."""
    kvot = foreslagen_avkastning_eget_kapital(resultatrapport, balansrapport)
    if kvot is None:
        return None
    return round(float(kvot) * 100, 1)


def kapitalstapel(poster: list[Finansieringspost]) -> dict[str, Any]:
    """Kapitalstacken som EN staplad stapel — ett färgskikt per källa.

    Varje skikt bär sin egen etikett (namn, belopp och andel av hela
    finansieringen) så att stapeln går att läsa utan legend eller hover.
    Ersätter Sankey-diagrammet, som la merparten av ytan på flödespilar mot
    en enda mottagarnod och därför blev otydligt så fort källorna blev fler.

    Skikten returneras i LÄSORDNING (samma ordning som formulärets rader,
    översta först). Renderaren staplar nerifrån och vänder därför på listan
    — ordningen bor här, inte i dashboarden.

    Färgen per skikt är typens, textfärgen räknas ut mot den med samma
    WCAG-logik som balansstapeln (text_farg). Ett för tunt skikt får ingen
    inline-text alls (ryms_inline_text) — hellre ingen etikett än en
    hoptryckt, oläslig sådan."""
    anvanda = [post for post in poster if post.belopp > 0]
    total = sum((post.belopp for post in anvanda), Decimal("0"))
    if not anvanda or total <= 0:
        return {
            "skikt": [],
            "total": Decimal("0"),
            "varning": "Ingen investering simulerad — ange ett belopp ovan.",
        }

    skikt = []
    for post in anvanda:
        andel = post.belopp / total
        farg = KAPITALSTACK_FARG[post.typ]
        skikt.append({
            "namn": post.namn,
            "belopp": post.belopp,
            "andel": andel,
            "farg": farg,
            "textfarg": text_farg(farg),
            "etikett": (
                f"{post.namn}<br>{formatera_kr(post.belopp)} · {formatera_procent(andel)}"
            ),
            "visa_etikett": ryms_inline_text(float(andel)),
        })
    return {"skikt": skikt, "total": total, "varning": None}


# Kapitalstacken ritades tidigare som ett Sankey-diagram (sankey_investering).
# Det ersattes av kapitalstapel: Sankey la merparten av ytan på flödespilar mot
# en enda mottagarnod, och blev otydligt så fort källorna blev fler än tre.
# sankey_data (hela balansräkningen, pro rata) finns kvar och används
# fortfarande av balansflödet.


# Vad som händer i balansräkningen per posttyp. Lån, ägarinsats och egna
# pengar återanvänder de befintliga mekanikförklaringarna (samma text som
# enkelkälle-simuleringen använder); leasingen har två egna, eftersom
# operationell leasing inte rör balansräkningen alls.
_LEASINGFORKLARING: dict[str, str] = {
    "operationell": (
        "Den operationellt leasade delen hamnar INTE i balansräkningen — "
        "tillgången står kvar hos leasegivaren och du kostnadsför avgiften "
        "löpande. Varken anläggningstillgångarna eller skulderna rör sig."
    ),
    "finansiell": (
        "Den finansiellt leasade delen tas upp som både tillgång och skuld. "
        "Anläggningstillgångarna och de långfristiga skulderna ökar lika "
        "mycket, precis som vid ett lån."
    ),
}


def _postforklaring(post: Finansieringspost) -> str:
    """Postens mekanikförklaring — vad den gör med balansräkningen."""
    if post.typ == "leasing":
        return _LEASINGFORKLARING[post.leasingmetod]
    return FINANSIERINGSFORKLARING[TYP_KALLA[post.typ]]


def narrativ_kapitalstack(
    nyckeltal_fore: dict,
    nyckeltal_efter: dict,
    belopp: Any,
    poster: list[Finansieringspost],
    wacc: dict,
    ej_aktiverat: Decimal = Decimal("0"),
) -> list[tuple[str, str]]:
    """Det narrativa lagret för kapitalstacken. Helt deterministiskt — ingen LLM,
    inga personuppgifter, och ingen mening som inte går att härleda ur de tal som
    skickas in. Riktningarna läses ur de faktiska värdena.

    Returnerar (etikett, text)-par, inte färdiga meningar: narrativet renderas
    som en tabell där etiketten är egen kolumn. Att slå ihop dem till en
    mening igen är trivialt (' '.join), att dela upp en mening i efterhand är
    det inte."""
    if belopp == 0:
        return [(
            "Ingen simulering",
            "Siffrorna visar balansräkningen som den ser ut i bokföringen.",
        )]

    anvanda = [post for post in poster if post.belopp > 0]
    delar = ", ".join(
        f"{post.namn.lower()} {formatera_kr(post.belopp)}"
        for post in sorted(anvanda, key=lambda post: -post.belopp)
    )
    rader = [("Investering", f"{formatera_kr(belopp)}, finansierad ur {delar}.")]

    if ej_aktiverat > 0:
        rader.append((
            "Aktiveras",
            f"{formatera_kr(belopp - ej_aktiverat)} bokförs som "
            f"anläggningstillgång. Resterande {formatera_kr(ej_aktiverat)} är "
            "operationell leasing och kostnadsförs löpande i stället — den "
            "delen syns aldrig i balansräkningen.",
        ))

    if wacc["wacc_efter_skatt"] is not None:
        rader.append((
            "Kapitalkostnad",
            f"WACC {formatera_procent(wacc['wacc_efter_skatt'])} efter skatt, "
            f"{formatera_procent(wacc['wacc_fore_skatt'])} före.",
        ))

    rader += [
        (etikett, _riktningstext(nyckeltal_fore.get(nyckel), nyckeltal_efter.get(nyckel)))
        for nyckel, etikett in SIMULERADE_NYCKELTAL
    ]
    rader += _leasingrader(anvanda)
    # Samma mekanikförklaring ska inte upprepas för två lån — unika, i ordning.
    sedda = set()
    for post in anvanda:
        forklaring = _postforklaring(post)
        if forklaring not in sedda:
            sedda.add(forklaring)
            rader.append(("Balanseffekt", forklaring))
    return rader


def _leasingrader(poster: list[Finansieringspost]) -> list[tuple[str, str]]:
    """En rad per leasingpost med utköp: vad utköpet kostar och hur det
    periodiserats. Utan den skulle utköpspriset påverka WACC:en osynligt."""
    rader = []
    for post in poster:
        tillagg = leasing_utkopstillagg(post)
        if tillagg <= 0:
            continue
        metod = "linjärt" if post.leasingmetod == "operationell" else "med effektivränta"
        rader.append((
            f"Utköp: {post.namn}",
            f"{formatera_kr(post.utkopspris)} fördelat {metod} över "
            f"{post.loptid_ar} år motsvarar {formatera_procent(tillagg)} per år "
            "ovanpå leasingräntan.",
        ))
    return rader


# CSS för narrativtabellen. Scopad till .sie-narrativ-tabell — inga andra
# tabeller i appen påverkas. Nyanserna anges som grå rgba() i stället för
# vitt/svart, så samma regler fungerar i både ljust och mörkt tema.
NARRATIV_TABELL_CSS = """\
<style>
.sie-narrativ-tabell {
    width: 100%;
    border-collapse: collapse;
    font-family: Inter, "Segoe UI", "Helvetica Neue", Arial, sans-serif;
    font-size: 0.9rem;
    margin: 0.4rem 0 0.2rem 0;
}
.sie-narrativ-tabell thead th {
    text-align: left;
    font-weight: 600;
    font-size: 0.8rem;
    letter-spacing: 0.02em;
    text-transform: uppercase;
    opacity: 0.7;
    padding: 0.45rem 0.7rem;
    border-bottom: 2px solid rgba(128, 128, 128, 0.35);
    border-right: 1px solid rgba(128, 128, 128, 0.12);
}
.sie-narrativ-tabell thead th:last-child { border-right: none; }
.sie-narrativ-tabell tbody td {
    padding: 0.5rem 0.7rem;
    border-right: 1px solid rgba(128, 128, 128, 0.12);
    border-bottom: 1px solid rgba(128, 128, 128, 0.08);
    vertical-align: top;
}
.sie-narrativ-tabell tbody td:last-child { border-right: none; }
/* Zebra-randning — diskret, gör raderna lätta att följa i sidled */
.sie-narrativ-tabell tbody tr:nth-child(even) {
    background-color: rgba(128, 128, 128, 0.08);
}
/* Etikettkolumnen: smal, fet, bryts inte */
.sie-narrativ-tabell .sie-narrativ-etikett {
    font-weight: 600;
    white-space: nowrap;
    width: 1%;
}
</style>
"""


def narrativtabell_html(rader: list[tuple[str, str]]) -> str:
    """Narrativet som en HTML-tabell i kalkylbladsstil: etikett och beskrivning
    i egna kolumner, zebra-randade rader.

    Texten är deterministiskt genererad av modulen själv — men postnamnen i
    den kommer från användarens egna inmatningar, så allt escapas. Ingen
    sträng når markupen oescapad."""
    delar = ['<table class="sie-narrativ-tabell">']
    delar.append(
        "<thead><tr>"
        '<th class="sie-narrativ-etikett">Post</th>'
        "<th>Vad simuleringen visar</th>"
        "</tr></thead><tbody>"
    )
    for etikett, text in rader:
        delar.append(
            f'<tr><td class="sie-narrativ-etikett">{html.escape(str(etikett))}</td>'
            f"<td>{html.escape(str(text))}</td></tr>"
        )
    delar.append("</tbody></table>")
    return "".join(delar)


def kapitalstack(
    resultatrapport: dict,
    balansrapport: dict,
    belopp: Any,
    poster: list[Finansieringspost],
) -> dict[str, Any]:
    """Hela investeringskalkylen i ett anrop, så dashboarden förblir en dum
    renderare: projicera stacken, räkna WACC, räkna om nyckeltalen med SAMMA
    KPI-motor som KPI-fliken använder, och formulera narrativet.

    Höjer ValueError via motorn om posterna inte summerar till
    investeringsbeloppet — vy-lagret ska ha stoppat det långt innan, men
    kontraktet gissar aldrig."""
    sim = simulera_kapitalstack(balansrapport, Decimal(str(belopp)), poster)
    balans_efter = sim["balans_efter"]

    wacc = berakna_wacc(poster)
    fore = bygg_nyckeltal(resultatrapport, balansrapport)["nyckeltal"]
    efter = bygg_nyckeltal(resultatrapport, balans_efter)["nyckeltal"]

    # Motorns varning är display-fri; beloppet formateras här.
    varning = sim["varning"]
    if varning:
        kassa = formatera_kr(balans_efter["poster"]["kassa_och_bank"])
        varning = f"{varning} Kassan hamnar på {kassa}."

    return {
        "balans_efter": balans_efter,
        "poster": sim["poster"],
        "aktiverat_belopp": sim["aktiverat_belopp"],
        "ej_aktiverat_belopp": sim["ej_aktiverat_belopp"],
        "wacc": wacc,
        "nyckeltal_fore": fore,
        "nyckeltal_efter": efter,
        "narrativ": narrativ_kapitalstack(
            fore, efter, sim["belopp"], sim["poster"], wacc, sim["ej_aktiverat_belopp"]
        ),
        "varning": varning,
    }


# --- Uppställningar (display-config: etikett, ordning, radtyp) ----------------
# (poster_nyckel, etikett, radtyp). radtyp: "grupp" = drill-down mot en
# kontogrupp med samma nyckel; "delsumma"/"summa" = uträknad subtotal utan
# drill-down. Ordningen är en klassisk svensk uppställning.

RESULTAT_UPPSTALLNING: list[tuple[str, str, str]] = [
    ("totala_intakter", "Totala intäkter", "grupp"),
    ("kostnad_salda_varor", "Kostnad sålda varor", "grupp"),
    ("bruttovinst", "Bruttovinst", "delsumma"),
    ("ovriga_rorelsekostnader", "Övriga rörelsekostnader", "grupp"),
    ("ebitda", "EBITDA", "delsumma"),
    ("avskrivningar", "Av- och nedskrivningar", "grupp"),
    ("rorelseresultat", "Rörelseresultat (EBIT)", "delsumma"),
    ("finansnetto", "Finansnetto", "grupp"),
    ("resultat_efter_finansiella", "Resultat efter finansiella poster (EBT)", "delsumma"),
    ("bokslutsdispositioner_skatt", "Bokslutsdispositioner & skatt", "grupp"),
    ("arets_resultat", "Årets resultat", "summa"),
]

BALANS_TILLGANGAR: list[tuple[str, str, str]] = [
    ("immateriella_anlaggningstillgangar", "Immateriella anläggningstillgångar", "grupp"),
    ("materiella_anlaggningstillgangar", "Materiella anläggningstillgångar", "grupp"),
    ("finansiella_anlaggningstillgangar", "Finansiella anläggningstillgångar", "grupp"),
    ("summa_anlaggningstillgangar", "Summa anläggningstillgångar", "delsumma"),
    ("varulager", "Varulager", "grupp"),
    ("kortfristiga_fordringar", "Kortfristiga fordringar", "grupp"),
    ("kassa_och_bank", "Kassa och bank", "grupp"),
    ("summa_omsattningstillgangar", "Summa omsättningstillgångar", "delsumma"),
    ("summa_tillgangar", "SUMMA TILLGÅNGAR", "summa"),
]

BALANS_EK_SKULDER: list[tuple[str, str, str]] = [
    ("eget_kapital", "Eget kapital", "grupp"),
    ("obeskattade_reserver", "Obeskattade reserver", "grupp"),
    ("avsattningar", "Avsättningar", "grupp"),
    ("langfristiga_skulder", "Långfristiga skulder", "grupp"),
    ("kortfristiga_skulder", "Kortfristiga skulder", "grupp"),
    ("summa_eget_kapital_och_skulder", "SUMMA EGET KAPITAL OCH SKULDER", "summa"),
]


def dela_uppstallning(
    uppstallning: list[tuple[str, str, str]],
) -> tuple[list[tuple[str, str, str]], tuple[str, str, str]]:
    """Delar en balansuppställning i (kroppsrader, slutsummerad).

    Balansräkningens två sidor har olika många rader OCH olika radtyper — vänster
    sida har sex drill-down-grupper och två delsummor, höger sida fem grupper och
    ingen delsumma. En expander är dessutom högre än en textrad. Att fylla ut den
    kortare sidan med tomma rader tills antalet stämmer räcker därför inte: raderna
    väger olika, och slutsummorna hamnar ändå på olika höjd.

    Lösningen är i stället att lyfta UT slutsummeraden ur kolumnen och rendera den
    som en gemensam fot över hela bredden. Då ligger de två slutsummorna garanterat
    på samma linje, oavsett hur många rader sidorna har.

    Kastar om uppställningen inte slutar med exakt en "summa"-rad — då stämmer inte
    antagandet som foten vilar på."""
    *kropp, sista = uppstallning
    if sista[2] != "summa" or any(radtyp == "summa" for _, _, radtyp in kropp):
        raise ValueError("Uppställningen måste sluta med exakt en summa-rad.")
    return kropp, sista


# Kassaflödesblock för drill-down-uppställningen: (block_nyckel, block_etikett,
# [(post_nyckel, post_etikett)]). Posterna kommer redan kassaflödestecknade från
# motorn och summerar till blockets summa.
KASSAFLODE_BLOCK: list[tuple[str, str, list[tuple[str, str]]]] = [
    (
        "lopande",
        "Den löpande verksamheten",
        [
            ("rorelseresultat", "Rörelseresultat"),
            ("finansnetto", "Finansnetto"),
            ("bokslutsdispositioner_skatt", "Bokslutsdispositioner & skatt"),
            ("avskrivningar", "Återläggning avskrivningar"),
            ("forandring_obeskattade_reserver", "Förändring obeskattade reserver"),
            ("forandring_avsattningar", "Förändring avsättningar"),
            ("forandring_varulager", "Förändring varulager"),
            ("forandring_kortfristiga_fordringar", "Förändring kortfristiga fordringar"),
            ("forandring_kortfristiga_skulder", "Förändring kortfristiga skulder"),
        ],
    ),
    (
        "investering",
        "Investeringsverksamheten",
        [("forandring_anlaggningstillgangar", "Förändring anläggningstillgångar (netto)")],
    ),
    (
        "finansiering",
        "Finansieringsverksamheten",
        [
            ("forandring_eget_kapital", "Förändring eget kapital (exkl. årets resultat)"),
            ("forandring_langfristiga_skulder", "Förändring långfristiga skulder"),
        ],
    ),
]


# --- Framtidens balansräkning: what-if, Sankey och narrativt lager -----------
#
# Balansräkningen som ett FLÖDE i stället för en tabell: finansieringskällorna
# till vänster strömmar in och finansierar tillgångarna till höger. Linjernas
# tjocklek är beloppen, så belåningsgraden syns direkt.

SIMULERING_MAX = 5_000_000        # slidertak (kr) för what-if-investeringen
SIMULERING_STEG = 100_000         # sliderns steglängd (kr)

# Sankey-nodfärger: eget kapital grönt, skulder orange, tillgångar blå — samma
# färgspråk som P&L-graferna.
_FARG_KAPITAL = FARG_INTAKT
_FARG_SKULD = FARG_KOSTNAD
_FARG_TILLGANG = FARG_RESULTAT

# Finansieringssidan, i uppställningsordning. Obeskattade reserver och
# avsättningar MÅSTE vara med: utan dem försvinner kapital ur diagrammet och
# flödena summerar inte till balansomslutningen. Obeskattade reserver färgas som
# kapital (79,4 % av dem tillhör ägarna, jfr JEK).
_SANKEY_FINANSIERING: list[tuple[str, str, str]] = [
    ("eget_kapital", "Eget kapital", _FARG_KAPITAL),
    ("obeskattade_reserver", "Obeskattade reserver", _FARG_KAPITAL),
    ("avsattningar", "Avsättningar", _FARG_SKULD),
    ("langfristiga_skulder", "Långfristiga skulder", _FARG_SKULD),
    ("kortfristiga_skulder", "Kortfristiga skulder", _FARG_SKULD),
]


def _sankey_tillgangar(poster: dict) -> list[tuple[str, Any, str]]:
    """Tillgångssidans tre noder. Omsättningstillgångarna visas EXKL. kassan,
    eftersom summa_omsattningstillgangar redan innehåller den — annars skulle
    kassan dubbelräknas och flödet överstiga balansomslutningen."""
    return [
        ("Anläggningstillgångar", poster["summa_anlaggningstillgangar"], _FARG_TILLGANG),
        (
            "Omsättningstillgångar (exkl. kassa)",
            poster["summa_omsattningstillgangar"] - poster["kassa_och_bank"],
            _FARG_TILLGANG,
        ),
        ("Kassa & bank", poster["kassa_och_bank"], _FARG_TILLGANG),
    ]


def sankey_data(balansrapport: dict) -> dict[str, Any]:
    """Mappar en FÄRDIG balansrapport till Plotly-Sankey: noder, nodfärger och
    länkar {"kalla", "mal", "varde"} (index in i noder, belopp som float).

    Flödena fördelas PRO RATA: varje finansieringskälla finansierar varje
    tillgångsslag i proportion till tillgångens andel av balansomslutningen.
    Det är den enda ärliga fördelningen — kapital är fungibelt, och bokföringen
    innehåller ingen koppling mellan en viss skuld och en viss tillgång. Ett
    öronmärkt 1:1-flöde hade påstått ett faktum som inte finns i datat.

    Kontraktet: summan av länkarna ut ur en källa = källans belopp, summan in i
    en tillgång = tillgångens belopp, och totalen = balansomslutningen.

    Nollposter utelämnas (nollflöden är bara brus). Negativa poster (t.ex.
    negativt eget kapital i ett förlustbolag) går inte att rita som flöden —
    de utelämnas och flaggas i "varning" i stället för att tyst förvanskas."""
    poster = balansrapport["poster"]
    summa_tillgangar = poster["summa_tillgangar"]

    kallor = [(etikett, poster[nyckel], färg) for nyckel, etikett, färg in _SANKEY_FINANSIERING]
    tillgangar = _sankey_tillgangar(poster)

    negativa = [etikett for etikett, belopp, _ in kallor + tillgangar if belopp < 0]
    kallor = [(e, b, f) for e, b, f in kallor if b > 0]
    tillgangar = [(e, b, f) for e, b, f in tillgangar if b > 0]

    noder = [etikett for etikett, _, _ in kallor + tillgangar]
    nodfarger = [färg for _, _, färg in kallor + tillgangar]

    varning = None
    if negativa:
        varning = (
            "Negativa poster kan inte ritas som flöden och har utelämnats: "
            + ", ".join(negativa)
            + ". Läs uppställningen nedan i stället."
        )

    lankar: list[dict[str, Any]] = []
    if summa_tillgangar > 0:
        for i, (_, kalla_belopp, _) in enumerate(kallor):
            for j, (_, tillgang_belopp, _) in enumerate(tillgangar):
                andel = tillgang_belopp / summa_tillgangar
                lankar.append(
                    {"kalla": i, "mal": len(kallor) + j, "varde": float(kalla_belopp * andel)}
                )
    elif varning is None:
        varning = "Balansomslutningen är noll — det finns inga flöden att visa."

    return {"noder": noder, "nodfarger": nodfarger, "lankar": lankar, "varning": varning}


# De nyckeltal som simuleringen berättar om, i den ordning de skrivs ut:
# (motor-nyckel, bestämd form som meningen inleds med).
SIMULERADE_NYCKELTAL: list[tuple[str, str]] = [
    ("soliditet", "Soliditeten"),
    ("kassalikviditet", "Kassalikviditeten"),
]

# Vad som faktiskt händer i balansräkningen per finansieringsform. Texten
# beskriver MEKANIKEN (vilka poster som rör sig), aldrig riktningen på ett
# nyckeltal — den läses ur de faktiska värdena i narrativ_simulering.
FINANSIERINGSFORKLARING: dict[str, str] = {
    "Långfristiga skulder": (
        "Anläggningstillgångarna och de långfristiga skulderna ökar lika mycket. "
        "Balansomslutningen växer medan det egna kapitalet står still. Kassan och "
        "de kortfristiga skulderna är oberörda."
    ),
    "Kortfristiga skulder": (
        "Anläggningstillgångarna och de kortfristiga skulderna ökar lika mycket. "
        "Både balansomslutningen och den kortsiktiga skuldbördan växer — en "
        "långsiktig tillgång finansieras med kortsiktiga pengar."
    ),
    "Minskning av kassa/bank": (
        "Kassan omvandlas till anläggningstillgångar. Balansomslutningen är "
        "oförändrad — tillgångarna byter bara form, från likvida till bundna."
    ),
    "Eget kapital": (
        "Anläggningstillgångarna och det egna kapitalet ökar lika mycket, t.ex. "
        "genom nyemission eller aktieägartillskott. Ingen ny skuld tas upp."
    ),
}


def _riktningstext(fore: Any, efter: Any) -> str:
    """Förändringen som fras, UTAN nyckeltalets namn. I narrativtabellen står
    namnet i egen kolumn; i den löpande texten sätts det framför av
    _riktningsmening."""
    if fore is None or efter is None:
        return "kan inte beräknas (nämnaren är noll)."
    if efter > fore:
        verb = "stiger"
    elif efter < fore:
        verb = "sjunker"
    else:
        return f"är oförändrad på {formatera_procent(fore)}."
    return f"{verb} från {formatera_procent(fore)} till {formatera_procent(efter)}."


def _riktningsmening(etikett: str, fore: Any, efter: Any) -> str:
    """En mening om ett nyckeltals förändring. Riktningen läses ur de FAKTISKA
    värdena — texten påstår aldrig något som siffrorna inte visar. Odefinierat
    (None) redovisas som odefinierat, aldrig som en falsk nolla."""
    return f"{etikett} {_riktningstext(fore, efter)}"


def narrativ_simulering(
    nyckeltal_fore: dict, nyckeltal_efter: dict, belopp: Any, finansieringskalla: str
) -> list[str]:
    """Det narrativa lagret som textrader: vad simuleringen gjorde, och vad den
    gjorde med nyckeltalen. Helt deterministiskt — ingen LLM, inga
    personuppgifter, inget som inte går att härleda ur de två KPI-dictarna."""
    if belopp == 0:
        return [
            "Ingen investering simulerad — siffrorna visar balansräkningen som "
            "den ser ut i bokföringen."
        ]
    if finansieringskalla not in FINANSIERINGSKALLOR:
        raise ValueError(f"Okänd finansieringskälla: {finansieringskalla!r}")

    rader = [
        f"Simulerad investering på {formatera_kr(belopp)}, finansierad via "
        f"{finansieringskalla.lower()}."
    ]
    rader += [
        _riktningsmening(etikett, nyckeltal_fore.get(nyckel), nyckeltal_efter.get(nyckel))
        for nyckel, etikett in SIMULERADE_NYCKELTAL
    ]
    rader.append(FINANSIERINGSFORKLARING[finansieringskalla])
    return rader


def simulering(
    resultatrapport: dict, balansrapport: dict, belopp: Any, finansieringskalla: str
) -> dict[str, Any]:
    """Hela what-if-kedjan i ett anrop, så dashboarden förblir en dum renderare:
    projicera investeringen, räkna om nyckeltalen med SAMMA KPI-motor som
    KPI-fliken använder (soliditetsformeln får aldrig dubbleras i UI-koden) och
    formulera narrativet. Returnerar även den simulerade balansrapporten, som
    Sankey-diagrammet ritas ur."""
    balans_efter = simulera_investering(balansrapport, belopp, finansieringskalla)
    fore = bygg_nyckeltal(resultatrapport, balansrapport)["nyckeltal"]
    efter = bygg_nyckeltal(resultatrapport, balans_efter)["nyckeltal"]

    # Motorns varning är display-fri; beloppet formateras här.
    varning = balans_efter["varning"]
    if varning:
        kassa = formatera_kr(balans_efter["poster"]["kassa_och_bank"])
        varning = f"{varning} Kassan hamnar på {kassa}."

    return {
        "balans_efter": balans_efter,
        "nyckeltal_fore": fore,
        "nyckeltal_efter": efter,
        "narrativ": narrativ_simulering(fore, efter, belopp, finansieringskalla),
        "varning": varning,
    }
