"""samtalsflode — orkestrerar den pedagogiska samtalsytan i app.py:s
Sektion 9 ("Fråga om filen").

bygg_saker_kontext är den ENDA platsen som avgör vad som får bli
AI-kontext — bygger uteslutande på redan vetta, aggregerade resultat
(app_vy.Översikt, vasentlighet.Vasentlighetstal,
ackumulering.AckumuleringsResultat/Felaktighet). ALDRIG rå
sie.tolkningsbehov[].råtext eller sie.företagsnamn/orgnr direkt — det är
exakt den typen av obehandlad fritext/identifierande data som
sekretesslagret finns för att skydda, och som aldrig får nå ett AI-anrop
oskyddad.

Medveten avgränsning för v1: sandningsbara_verifikationers fritext
(vertext/transtext) inkluderas INTE i kontexten, trots att den redan är
maskerad och lika säker som det Modul 4 skickar till Haiku idag. Räckvidd
minimeras avsiktligt till aggregerade fakta — det räcker för de
efterfrågade frågetyperna (sammanfatta/förklara/risker/analys) och håller
riskytan liten.

ställ_fraga är fail-closed på samma sätt som chatt_klient.py:s egen
anropare — ett oväntat fel ger ett fast, ärligt fallback-svar, aldrig en
krasch eller rå exception-text.

SVARSLÄGEN/FÖRESLAGNA_FRÅGOR (UX-lager, tillagt senare): svarsläge styr
bara formuleringen (vävs in i kontexten som skickas till AI:t, rör aldrig
chatt_klient.py:s eller ai_adapter.py:s kontrakt). FÖRESLAGNA_FRÅGOR är en
centraliserad, lätt-att-ändra lista — inte en ny beräkning eller
kärnlogik.

Fas 10 (interaktiva steg i chatten): ChattMeddelande är den enhetliga
byggstenen för app.py:s samtal_historik — ETT meddelande, inte längre ett
(fråga, svar)-par, så att BÅDE vanlig text OCH ett interaktivt flerval
(alternativ satt) kan visas via samma st.chat_message()-loop. ställ_fraga
(fil-läge, inget skrivbart mål) behåller MEDVETET sitt gamla
engångskontrakt — varje fråga besvaras isolerat, ingen historik skickas
med. ställ_fraga_till_agent (Spiris-kopplat agentläge) fick i Fas 10 ETT
NYTT kontrakt: den tar hela konversationshistoriken (list[dict] med
roll/text), inte en enda fråga — annars "glömmer" AI:t vad den frågade om
så fort en efterfraga_val-fråga (se chatt_klient.py) besvarats med en
knapptryckning, vilket var precis det som gjorde att assistenten fastnade
i textbaserade frågeloopar. Den skillnaden mellan de två är avsiktlig, inte
en halvfärdig migrering: fil-läget har inget flerstegsflöde att minnas
mellan, agentläget har det (skapa_kund/skapa_kundfaktura/efterfraga_val).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from analysflode import AnalysResultat
from app_vy import bygg_oversikt
from chatt_klient import AgentSvar
from domain_model import SIEFil
from reskontra_tvatt import maskera_for_egress
from sekretesslager import Maskeringsresultat

SvarsLäge = Literal["kort", "pedagogisk", "analytisk"]

SVARSLÄGEN: tuple[SvarsLäge, ...] = ("kort", "pedagogisk", "analytisk")

_SVARSLÄGE_INSTRUKTIONER: dict[SvarsLäge, str] = {
    "kort": (
        "Använd all din kunskap för att hitta det exakta svaret på frågan i datan, "
        "men svara maximalt kort och koncist. Gå rakt på sak (helst 2-3 meningar). "
        "Föregå inte med artighetsfraser. Om användaren uttryckligen ber om en lista "
        "eller tabell ska du givetvis leverera hela tabellen, men håll brödtexten extremt kort."
    ),
    "pedagogisk": (
        "Agera som en briljant och tålmodig mentor. Du har tillgång till hela företagets data "
        "och ska använda hela din analytiska förmåga för att besvara frågan, men du ska "
        "förklara det så att en icke-ekonom förstår. Göm ALDRIG undan relevant data eller "
        "siffror, utan översätt istället facktermer till klarspråk. Använd gärna konkreta, "
        "vardagliga liknelser (t.ex. privatekonomi, att driva ett bageri etc.) för att "
        "förklara vad siffrorna betyder i praktiken för företagaren. Om användaren ber "
        "om hela balansräkningen, ge dem hela, men väv in förklaringar av de svåra posterna."
    ),
    "analytisk": (
        "Agera som en sylvass, proaktiv CFO. Gör en djupdykning i datan och utnyttja hela din "
        "intelligens. Svara utförligt. Nöj dig inte med att bara återge siffrorna användaren "
        "frågar efter, utan sök proaktivt efter samband, trender, risker (t.ex. kassaflödesproblem "
        "eller tunga skulder) och avvikelser. Använd finansiella nyckeltal om det är relevant. "
        "NÄR du presenterar data eller finansiella rapporter SKA DU ALLTID presentera "
        "det strukturerat som tabeller (enligt den JSON-struktur du är instruerad att använda "
        "när listor presenteras), för att ge användaren en maximalt tydlig överblick."
    ),
}

@dataclass
class FöreslagenFråga:
    etikett: str
    fråga: str


@dataclass
class ChattMeddelande:
    """Fas 10: ETT meddelande i app.py:s samtal_historik — ersätter den
    gamla (fråga, svar)-tupel-listan, som bara kunde representera EN fråga
    + ETT textsvar och alltså inte hade plats för ett interaktivt
    flervalssteg (alternativ). roll är "user" eller "assistant", direkt
    återanvändbart som st.chat_message(roll)-argument.

    alternativ sätts ENDAST på ett assistant-meddelande som väntar på ett
    svar (AI:t anropade efterfraga_val, se chatt_klient.py) — gränssnittet
    renderar det som knappar precis under meddelandet, men BARA om det är
    det allra SISTA meddelandet i historiken (annars är frågan redan
    besvarad av nästa post i listan).

    strukturerat (fas 11) sätts när AI:t levererat sitt svar enligt
    svarskontrakt.py:s schema i stället för som fri markdown — då renderar
    chatt_renderare.py tabellen deterministiskt i stället för st.write.
    Sparas SERIALISERAT (dict, via .model_dump()) och inte som
    Pydantic-objekt: det är vad som överlever Streamlits rerun-cykel i
    session_state. text sätts ändå alltid — den är både fallback i UI:t och
    det agenten får se av sitt eget svar när historiken återsänds."""

    roll: Literal["user", "assistant"]
    text: str
    alternativ: list[str] | None = None
    strukturerat: dict | None = None


# Centraliserad så den är enkel att ändra/utöka på ett ställe. Bygger på
# appens faktiska syfte (sammanfatta/förklara/risker/väsentlighet/konton/
# ställning) — inte generiska AI-floskler. etikett är den korta
# knapptexten, fråga är vad som faktiskt skickas till AI:t.
FÖRESLAGNA_FRÅGOR: tuple[FöreslagenFråga, ...] = (
    FöreslagenFråga("Sammanfatta bolaget", "Sammanfatta bolaget och filen i stora drag."),
    FöreslagenFråga(
        "Förklara ekonomin", "Förklara bolagets ekonomi för någon som inte är ekonom."
    ),
    FöreslagenFråga(
        "Finns det risker?",
        "Finns det tydliga risker eller avvikelser jag borde känna till?",
    ),
    FöreslagenFråga("Väsentlighetstalen", "Vad betyder väsentlighetstalen i praktiken?"),
    FöreslagenFråga(
        "Problematiska konton", "Vilka konton verkar mest problematiska och varför?"
    ),
    FöreslagenFråga(
        "Ekonomisk ställning", "Är bolagets ekonomiska ställning stark eller svag just nu?"
    ),
    FöreslagenFråga(
        "Likviditetsprognosen",
        "Förklara likviditetsprognosen — riskerar kassan att bli negativ, och "
        "finns det kunder som brukar betala sent som påverkar den?",
    ),
)


def _kontosaldo_rader(sie: SIEFil, maskerade_konton: dict) -> list[str]:
    """Alternativ B: aggregerade kontosaldon (kontonr + kontonamn + saldo)
    så chatten kan svara på balansfrågor (kassa, totala leverantörsskulder,
    banksaldo). Fortfarande bara aggregerade siffror per konto — inga
    personnamn och ingen reskontra (den gränsen hör till C).

    Fynd A: kontonamn är INTE garanterat standard-BAS (i Visma kan användaren
    döpa om konton fritt, t.ex. 'Lön Anna Andersson'), så namnen tas ur de
    MASKERADE kontona (maskeringsresultat.maskerad_siefil.konton), aldrig ur
    råa sie.konton. Saldon (siffror) kommer fortsatt ur sie — de är inte PII."""

    def sektion(rubrik: str, poster: list) -> list[str]:
        if not poster:
            return []
        ut = ["", rubrik]
        for post in poster:
            konto = maskerade_konton.get(post.kontonr)
            namn = konto.namn if konto is not None else ""
            ut.append(f"- {post.kontonr} {namn}: {post.saldo} kr")
        return ut

    return sektion(
        "KONTOSALDON – BALANSRÄKNING (kontonr, kontonamn, utgående saldo):",
        sie.utgående_balanser,
    ) + sektion(
        "KONTOSALDON – RESULTATRÄKNING (kontonr, kontonamn, saldo):",
        sie.resultat,
    )


def _reskontra_rader(reskontra: list | None) -> list[str]:
    """Renderar den GDPR-tvättade leverantörsreskontran (Fas C). Namnen är
    redan tvättade av tvatta_leverantorsreskontra — juridiska personer i
    klartext, känsliga/fysiska personer som pseudonym. Duck-typat (leverantor/
    belopp/betalstatus) så samtalsflode inte behöver känna till reskontra_tvatt."""
    if not reskontra:
        return []
    rader = [
        "",
        "LEVERANTÖRSRESKONTRA (obetalda leverantörsfakturor; "
        "känsliga leverantörer är pseudonymiserade):",
    ]
    for post in reskontra:
        rader.append(f"- {post.leverantor}: {post.belopp} kr ({post.betalstatus})")
    return rader


def _kundreskontra_rader(kundreskontra: list | None) -> list[str]:
    """Renderar den GDPR-tvättade kundreskontran (Fas D). Juridiska kunder i
    klartext, privatpersoner som pseudonym. Duck-typat (kund/belopp/
    betalstatus)."""
    if not kundreskontra:
        return []
    rader = [
        "",
        "KUNDRESKONTRA (obetalda kundfakturor; "
        "känsliga kunder är pseudonymiserade):",
    ]
    for post in kundreskontra:
        rader.append(f"- {post.kund}: {post.belopp} kr ({post.betalstatus})")
    return rader


def _likviditetsprognos_rader(likviditetsprognos: dict | None) -> list[str]:
    """Sammanfattar en likviditetsprognos (fpa_motor.bygg_likviditetsprognos)
    till AGGREGERADE fakta — INTE de ~90 råa dagsraderna, i linje med modulens
    princip att bara skicka redan vetta sammanfattningar (se moduldocstring).

    Nämner explicit vilka motparter vars förväntade betalning är skiftad pga
    historiskt betalbeteende, så AI:t kan förklara VARFÖR en specifik dag i
    grafen ser ut som den gör — inte bara att den gör det. motpart är samma
    redan GDPR-tvättade visningsnamn som _kundreskontra_rader använder (via
    fpa_vy.likviditetsprognos_fran_reskontra), så ingen ny sekretessrisk
    introduceras här.

    Nämner även en ev. momshändelse (typ "moms" i alla_handelser) explicit —
    annars kan AI:t inte förklara varför kassan hoppar på nästa
    momsförfallodag, en av de vanligaste orsakerna till en missad
    kassaflödesprognos (se fpa_motor.bygg_likviditetsprognos/
    nasta_momsforfallodag)."""
    if not likviditetsprognos:
        return []
    rader = [
        "",
        f"LIKVIDITETSPROGNOS (dag-för-dag, {likviditetsprognos['antal_dagar']} dagar "
        f"framåt från {likviditetsprognos['prognosdatum']}):",
        f"- Nuvarande kassa: {likviditetsprognos['nuvarande_kassa']} kr",
        f"- Lägsta prognostiserade kassa: {likviditetsprognos['lagsta_kassa']} kr "
        f"(den {likviditetsprognos['lagsta_kassa_datum']})",
    ]
    första_underskott = likviditetsprognos["forsta_dag_med_underskott"]
    if första_underskott is not None:
        rader.append(f"- VARNING: kassan väntas bli negativ från och med {första_underskott}.")
    else:
        rader.append("- Kassan väntas förbli positiv under hela perioden.")

    sena_kunder: dict[str, int] = {}
    for händelse in likviditetsprognos["alla_handelser"]:
        if händelse["har_historisk_justering"]:
            namn = händelse["motpart"] or händelse["fakturanr"] or "okänd motpart"
            sena_kunder[namn] = händelse["dagar_justering"]
    if sena_kunder:
        rader.append(
            "- Kunder vars förväntade inbetalning är skiftad pga historiskt betalbeteende:"
        )
        for namn, dagar in sena_kunder.items():
            riktning = "sent" if dagar > 0 else "i förskott"
            rader.append(f"  - {namn}: brukar betala {abs(dagar)} dagar {riktning}")

    momshändelse = next(
        (h for h in likviditetsprognos["alla_handelser"] if h["typ"] == "moms"), None
    )
    if momshändelse is not None:
        riktning = "återbäring (inbetalning)" if momshändelse["belopp_signerat"] > 0 else "betalning"
        rader.append(
            f"- Moms: en {riktning} på {momshändelse['belopp']} kr väntas "
            f"{momshändelse['forfallodatum']} (nästa standardförfallodag)."
        )
    return rader


def bygg_saker_kontext(
    sie: SIEFil,
    maskeringsresultat: Maskeringsresultat,
    analys_resultat: AnalysResultat | None,
    reskontra: list | None = None,
    kundreskontra: list | None = None,
    likviditetsprognos: dict | None = None,
) -> str:
    """Bygger den säkra textkontext som skickas till AI:t. Innehåller
    ENDAST redan vetta, aggregerade fakta — se moduldocstring för exakt
    vad som medvetet utesluts och varför.

    **Egressgräns (P0, 2026-08-04).** Reskontraposterna maskeras HÄR, inte av
    anroparen. Sedan maskeringsgränsen flyttades håller `app.py` motpartsnamn i
    KLARTEXT (lokala snabbvyer ska visa riktiga namn), så den här funktionen
    kan inte längre anta att den får färdigtvättad data. Den tvättar därför
    själv. Anropet är idempotent — redan maskerade poster rörs inte."""
    reskontra = maskera_for_egress(reskontra) if reskontra else reskontra
    kundreskontra = maskera_for_egress(kundreskontra) if kundreskontra else kundreskontra

    översikt = bygg_oversikt(sie, maskeringsresultat)

    rader = [
        "FILÖVERSIKT:",
        f"- Antal verifikationer: {översikt.antal_verifikationer}",
        f"- Antal tolkningsbehov (oklarheter i filen): {översikt.antal_tolkningsbehov}",
        f"- Antal maskeringsbehov (känsliga uppgifter hittade): {översikt.antal_maskeringsbehov}",
        f"- Antal sandningsbara verifikationer: {översikt.antal_sandningsbara_verifikationer}",
        f"- Antal blockerade verifikationer: {översikt.antal_blockerade_verifikationer}",
    ]

    # Kontosaldon oberoende av om ISA 450-analysen körts — de är rena
    # balansfakta, inte analysresultat. Kontonamnen tas ur den maskerade
    # kontoplanen (fynd A), inte ur råa sie.konton.
    rader += _kontosaldo_rader(sie, maskeringsresultat.maskerad_siefil.konton)
    rader += _reskontra_rader(reskontra)
    rader += _kundreskontra_rader(kundreskontra)
    rader += _likviditetsprognos_rader(likviditetsprognos)

    if analys_resultat is None or analys_resultat.felmeddelande is not None:
        rader.append("")
        rader.append("ANALYS: Ingen ISA 450-analys är tillgänglig ännu (eller misslyckades).")
        return "\n".join(rader)

    v = analys_resultat.vasentlighetstal
    ack = analys_resultat.ackumulering
    rader += [
        "",
        "VÄSENTLIGHETSTAL:",
        f"- Omsättning: {v.omsattning} kr",
        f"- Resultat: {v.resultat} kr",
        f"- Balansomslutning: {v.balansomslutning} kr",
        f"- Eget kapital: {v.eget_kapital} kr",
        "",
        "ACKUMULERINGSRESULTAT (ISA 450):",
        f"- Nettosumma felaktigheter: {ack.summa_netto} kr (status: {ack.status_netto})",
        f"- Bruttosumma felaktigheter: {ack.summa_brutto} kr (status: {ack.status_brutto})",
        f"- Antal identifierade felaktigheter: {ack.antal_felaktigheter}",
        f"- Varav okänd riktning: {ack.antal_okänd_riktning}",
    ]

    if ack.felaktigheter:
        rader.append("")
        rader.append("IDENTIFIERADE FELAKTIGHETER:")
        for f in ack.felaktigheter:
            rader.append(
                f"- Konto {f.kontonr} ({f.kontonamn}): {f.belopp} kr, "
                f"riktning {f.riktning}, källa {f.källa}. Motivering: {f.motivering}"
            )

    return "\n".join(rader)


def ställ_fraga(
    fraga: str,
    kontext: str,
    chattanropare: Callable[[str, str], str],
    svarsläge: SvarsLäge = "pedagogisk",
) -> str:
    """Ställer en fråga mot AI:t med den redan byggda säkra kontexten.
    svarsläge styr bara HUR svaret formuleras (via en instruktion vävd in
    i kontexten) — fraga når anroparen helt oförändrad. Fail-closed: ett
    okänt svarsläge faller tillbaka till pedagogisk, och ett oväntat fel i
    chattanropare ger ett fast, ärligt fallback-svar — aldrig en krasch,
    aldrig rå exception-text."""
    instruktion = _SVARSLÄGE_INSTRUKTIONER.get(svarsläge, _SVARSLÄGE_INSTRUKTIONER["pedagogisk"])
    kontext_med_svarsläge = f"SVARSSTIL: {instruktion}\n\n{kontext}"
    try:
        return chattanropare(fraga, kontext_med_svarsläge)
    except Exception:
        return "Kunde inte få ett svar just nu. Försök igen om en stund."


def ställ_fraga_till_agent(
    meddelanden: list[dict[str, str]],
    kontext: str,
    agentanropare: Callable[[list[dict[str, str]], str], AgentSvar],
    svarsläge: SvarsLäge = "pedagogisk",
) -> AgentSvar:
    """Som ställ_fraga, men mot en AGENT-anropare (Fas 9: Tool Calling) —
    samma svarsläge-infogning i kontexten, men returnerar AgentSvar i
    stället för str (se chatt_klient.AgentSvar för varför agentläget har
    ett eget kontrakt). Ett eventuellt verktygsanrop AI:t begär når
    anroparen (app.py) OFÖRÄNDRAT — den här funktionen avgör aldrig själv
    vad ett verktygsanrop ska leda till.

    Fas 10: meddelanden är HELA konversationshistoriken (roll/text-dictar,
    äldst först, den senaste frågan sist) — inte en enda fråga, se
    moduldocstring för varför.

    Fail-closed: ett okänt svarsläge faller tillbaka till pedagogisk, och
    ett oväntat fel ger AgentSvar(text=<samma fasta fallback-text som
    ställ_fraga>) — aldrig en krasch, aldrig ett påhittat verktygsanrop."""
    instruktion = _SVARSLÄGE_INSTRUKTIONER.get(svarsläge, _SVARSLÄGE_INSTRUKTIONER["pedagogisk"])
    kontext_med_svarsläge = f"SVARSSTIL: {instruktion}\n\n{kontext}"
    try:
        return agentanropare(meddelanden, kontext_med_svarsläge)
    except Exception:
        return AgentSvar(text="Kunde inte få ett svar just nu. Försök igen om en stund.")
