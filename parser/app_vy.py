"""app_vy — visningslogik och tunn filinläsningspolicy för Streamlit-appens
första byggsteg (DEL A).

Ren transformationslogik (räkning, fältmappning) plus EN fail-closed-
policyfunktion (läs_och_maskera_fil) — ingen Streamlit-import här, så
modulen är fullt testbar utan UI-runtime. Se app.py för hur den används.

läs_och_maskera_fil finns här av samma skäl som ModellhämtningsFel-policyn
i ai_konfiguration.py: felpolicyn "visa aldrig rå exception-text" måste
kunna beteendetestas direkt, inte bara verifieras med en källkodsscan av
app.py.
"""

from __future__ import annotations

import copy
import html
from dataclasses import dataclass, replace
from decimal import Decimal
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Literal

from ackumulering import AckumuleringsResultat
from domain_model import SIEFil, Verifikation
from sekretesslager import Maskeringsbehov, Maskeringsresultat, maskera_siefil
from sie4_parser import parse_sie4
from spiris_adapter import foreslå_konto
from app_config import slå_upp_kontering


@dataclass
class Översikt:
    antal_verifikationer: int
    antal_tolkningsbehov: int
    antal_maskeringsbehov: int
    antal_sandningsbara_verifikationer: int
    antal_blockerade_verifikationer: int
    prosa_sandningsbar: Literal["ja", "nej"]


def bygg_oversikt(sie: SIEFil, resultat: Maskeringsresultat) -> Översikt:
    return Översikt(
        antal_verifikationer=len(sie.verifikationer),
        antal_tolkningsbehov=len(sie.tolkningsbehov),
        antal_maskeringsbehov=len(resultat.maskeringsbehov),
        antal_sandningsbara_verifikationer=len(resultat.sandningsbara_verifikationer),
        antal_blockerade_verifikationer=len(resultat.blockerade_verifikationer),
        # None täcker både "blockerad av olöst prosa-behov" och "ingen
        # prosa fanns alls" — sekretesslager.py:s eget kontrakt skiljer
        # inte mellan dem, så vi gör det konservativa valet här.
        prosa_sandningsbar="ja" if resultat.prosa_sandningsbar is not None else "nej",
    )


def maskeringsbehov_till_visningsrad(behov: Maskeringsbehov) -> dict[str, str]:
    return {
        "Plats": behov.plats,
        "Fältnamn": behov.fältnamn,
        "Misstänkt text": behov.misstänkt_text,
        "Träffkälla": behov.träffkälla,
        "Status": behov.status,
    }


def markera_kanslig_text(text: str, kansligt: str) -> str:
    """Markerar den känsliga delsträngen grafiskt (röd genomstrykning) i
    originaltexten, för Sektion 4:s 'så här kommer det maskeras'-förhandsvisning.
    HTML-escapar allt (renderas med unsafe_allow_html) så rå fritext aldrig kan
    injicera markup. No-op om delsträngen saknas eller är tom — får aldrig rama
    in hela texten."""
    säker_text = html.escape(text)
    if not kansligt or kansligt not in text:
        return säker_text

    säkert_kansligt = html.escape(kansligt)
    markering = (
        '<span style="color:#b00020;text-decoration:line-through">'
        f"{säkert_kansligt}</span>"
    )
    return säker_text.replace(säkert_kansligt, markering)


def nyckel_for_behov(behov: Maskeringsbehov, index: int) -> str:
    """Stabil OCH unik identitet per rad i granskningslistan. index gör
    nyckeln unik även när samma känsliga text flaggas på flera rader i samma
    verifikation (identisk plats/fältnamn/misstänkt_text) — annars krockar
    Streamlit-widgetnycklarna. Den innehållsbundna delen gör att nyckeln ändras
    mellan olika filer/datakällor."""
    return f"{index}|{behov.plats}|{behov.fältnamn}|{behov.misstänkt_text}"


# De tre lägen en rad kan ha i granskningen. Trelägesvalet finns för att
# "maskera" och "ingen maskering" båda är AKTIVA beslut som ska rensa raden ur
# åtgärdslistan — utan ett uttryckligt "avvakta" hade en obeslutad rad varit
# omöjlig att skilja från ett medvetet "nej", och undantagslistan hade fyllts
# av rader användaren aldrig tog ställning till.
BESLUT_MASKERA = "maskera"
BESLUT_INGEN_MASKERING = "ingen_maskering"
BESLUT_AVVAKTA = "avvakta"

_STATUS_FÖR_BESLUT = {
    BESLUT_MASKERA: "bekräftad_pii",
    BESLUT_INGEN_MASKERING: "godkänd_ej_pii",
    BESLUT_AVVAKTA: "väntar_granskning",
}


def _status_for_val(val: dict) -> str:
    """Läser ett UI-beslut. Stödjer både det nya trelägesfältet ("beslut") och
    det äldre booleska ("maskera"). Fail-closed: okänt eller saknat beslut
    maskeras — en rad släpps aldrig igenom av misstag."""
    beslut = val.get("beslut")
    if beslut is None and "maskera" in val:
        beslut = BESLUT_MASKERA if val["maskera"] else BESLUT_INGEN_MASKERING
    return _STATUS_FÖR_BESLUT.get(beslut, "bekräftad_pii")


def bygg_granskade_behov(
    behov_lista: list[Maskeringsbehov], beslut: dict[str, dict]
) -> list[Maskeringsbehov]:
    """Omvandlar Sektion 4:s UI-beslut (maskera / ingen maskering / avvakta +
    ev. manuellt överskriven text) till Maskeringsbehov redo för
    sekretesslager.uppdatera_efter_granskning. Fail-closed: saknas ett beslut
    för en rad maskeras den (bekräftad_pii), aldrig släpps igenom av misstag.
    Ingen rad tappas.

    Den överskrivna texten hamnar i ersättningstext — misstänkt_text lämnas
    orörd eftersom den är en del av radens identitet vid sammanslagningen i
    sekretesslagret."""
    granskade: list[Maskeringsbehov] = []
    for index, behov in enumerate(behov_lista):
        val = beslut.get(nyckel_for_behov(behov, index), {})
        text = val.get("text") or behov.misstänkt_text  # tom överskrivning -> behåll original
        granskade.append(
            replace(
                behov,
                status=_status_for_val(val),
                ersättningstext=text if text != behov.misstänkt_text else None,
            )
        )
    return granskade


def tillämpa_liggare(sie: SIEFil, liggare: dict[str, str]) -> SIEFil:
    """Pre-pass för Maskeringsliggaren: gör en global sök-och-ersätt av varje
    känt namn -> mask i alla fritextfält (vertext, sign, transtext, prosa) INNAN
    maskera_siefil körs. Kända namn flaggas då aldrig som nya maskeringsbehov och
    får stabila masker mellan filer/sessioner. Ren transformation som rör den
    LÅSTA maskeringskärnan inte alls; originalet lämnas orört (deepcopy)."""
    if not liggare:
        return sie

    def ersätt(text: str | None) -> str | None:
        if not text:
            return text
        for namn, mask in liggare.items():
            if namn in text:
                text = text.replace(namn, mask)
        return text

    maskerad = copy.deepcopy(sie)
    for verifikation in maskerad.verifikationer:
        verifikation.vertext = ersätt(verifikation.vertext)
        verifikation.sign = ersätt(verifikation.sign)
        for transaktion in verifikation.transaktioner:
            transaktion.transtext = ersätt(transaktion.transtext)
            transaktion.sign = ersätt(transaktion.sign)
    maskerad.prosa = ersätt(maskerad.prosa)
    return maskerad


def unika_namn_behov(behov_lista: list[Maskeringsbehov]) -> list[Maskeringsbehov]:
    """Ett representativt Maskeringsbehov per unikt misstänkt namn — så att varje
    namn visas EXAKT en gång i granskningen (Sektion 4), oavsett hur många
    verifikationer det förekommer i."""
    sedda: dict[str, Maskeringsbehov] = {}
    for behov in behov_lista:
        sedda.setdefault(behov.misstänkt_text, behov)
    return list(sedda.values())


def bygg_granskade_behov_per_namn(
    behov_lista: list[Maskeringsbehov], beslut_per_namn: dict[str, dict]
) -> list[Maskeringsbehov]:
    """Som bygg_granskade_behov, men ett beslut per unikt NAMN appliceras på ALLA
    behov som delar namnet (batch — ett klick avgör namnet i alla förekomster).
    Fail-closed: saknas beslut för ett namn maskeras det."""
    granskade: list[Maskeringsbehov] = []
    for behov in behov_lista:
        val = beslut_per_namn.get(behov.misstänkt_text, {})
        text = val.get("text") or behov.misstänkt_text
        granskade.append(
            replace(
                behov,
                status=_status_for_val(val),
                ersättningstext=text if text != behov.misstänkt_text else None,
            )
        )
    return granskade


def obeslutade_behov(behov_lista: list[Maskeringsbehov]) -> list[Maskeringsbehov]:
    """Bara de behov som fortfarande väntar på ett mänskligt beslut — det som
    ska visas i Åtgärder. Redan avgjorda rader (maskerade ELLER undantagna)
    försvinner därmed ur listan så fort maskeringen tillämpats. Samma
    statusfilter som navigering.ohanterade_maskeringsbehov räknar med, så
    listan och badgen kan aldrig säga emot varandra."""
    return [behov for behov in behov_lista if behov.status == "väntar_granskning"]


def namn_att_undanta(granskade: list[Maskeringsbehov]) -> set[str]:
    """De namn användaren aktivt markerat som 'Ingen maskering' och som därför
    ska in i undantagslistan. Alltid den FLAGGADE texten (misstänkt_text), inte
    ersättningstext — det är den strängen sekretesslagret matchar mot när den
    avgör om något ska flaggas igen."""
    return {
        behov.misstänkt_text
        for behov in granskade
        if behov.status == "godkänd_ej_pii" and behov.misstänkt_text
    }


def verifikation_till_visningsrad(verifikation: Verifikation) -> dict[str, str | int]:
    return {
        "Serie": verifikation.serie or "",
        "Vernr": verifikation.vernr or "",
        "Vertext": verifikation.vertext or "",
        "Antal transaktioner": len(verifikation.transaktioner),
    }


_STATUS_TILL_EMOJI: dict[str, str] = {"grön": "🟢", "gul": "🟡", "röd": "🔴"}


@dataclass
class Risksammanfattning:
    emoji_netto: str
    emoji_brutto: str
    etikett: str


def bygg_risksammanfattning(ackumulering: AckumuleringsResultat) -> Risksammanfattning:
    """Bygger en liten visuell risksammanfattning direkt från redan
    beräknade statusfält (status_netto/status_brutto) — ingen ny analys,
    bara en presentationsmappning ovanpå Modul 5:s eget beslut."""
    emoji_netto = _STATUS_TILL_EMOJI.get(ackumulering.status_netto, "⚪")
    emoji_brutto = _STATUS_TILL_EMOJI.get(ackumulering.status_brutto, "⚪")

    statusar = {ackumulering.status_netto, ackumulering.status_brutto}
    if "röd" in statusar:
        etikett = "Kräver uppmärksamhet"
    elif "gul" in statusar:
        etikett = "Bör granskas"
    else:
        etikett = "Ser rimligt ut"

    return Risksammanfattning(emoji_netto=emoji_netto, emoji_brutto=emoji_brutto, etikett=etikett)


@dataclass
class InläsningsResultat:
    sie: SIEFil | None
    maskeringsresultat: Maskeringsresultat | None
    felmeddelande: str | None


def läs_och_maskera_fil(
    sökväg: str | Path,
    liggare: dict[str, str] | None = None,
    undantagslista: set[str] | None = None,
    referenslista: set[str] | None = None,
) -> InläsningsResultat:
    """Läser och maskerar en SIE4-fil. Om en Maskeringsliggare anges körs en
    pre-pass (kända namn -> mask) INNAN maskera_siefil, så redan lärda namn
    aldrig flaggas på nytt. undantagslistan skickas vidare till sekretesslagret
    så att strängar användaren bedömt som icke-PII inte flaggas igen.
    referenslistan (fynd 6, namnreferens.las_namnreferens) auto-maskerar kända
    svenska namn via Lager 3a i stället för att flagga dem för granskning.
    Fail-closed: går inläsningen eller maskeringen fel av någon anledning visas
    ALDRIG den råa exception-texten — bara ett statiskt, generiskt
    felmeddelande."""
    try:
        sie = parse_sie4(sökväg)
        if liggare:
            sie = tillämpa_liggare(sie, liggare)
        maskeringsresultat = maskera_siefil(
            sie, referenslista=referenslista, undantagslista=undantagslista
        )
    except Exception:
        return InläsningsResultat(
            sie=None,
            maskeringsresultat=None,
            felmeddelande=(
                "Kunde inte läsa eller maskera filen. Kontrollera att "
                "filen är en giltig SIE4-fil."
            ),
        )

    return InläsningsResultat(sie=sie, maskeringsresultat=maskeringsresultat, felmeddelande=None)


def maskera_inlast_siefil(
    sie: SIEFil,
    liggare: dict[str, str] | None = None,
    undantagslista: set[str] | None = None,
    referenslista: set[str] | None = None,
) -> InläsningsResultat:
    """Kör en redan inläst SIEFil (t.ex. hämtad direkt från Spiris, utan
    fil-mellansteg) genom sekretesslagret, med samma valfria liggar-pre-pass,
    undantagslista och referenslista (fynd 6) som läs_och_maskera_fil. Samma
    fail-closed-policy och InläsningsResultat-kontrakt så app.py kan behandla en
    Spiris-hämtning exakt som en filuppladdning — ingen omaskerad data når
    någonsin Sektion 2–8."""
    try:
        if liggare:
            sie = tillämpa_liggare(sie, liggare)
        maskeringsresultat = maskera_siefil(
            sie, referenslista=referenslista, undantagslista=undantagslista
        )
    except Exception:
        return InläsningsResultat(
            sie=None,
            maskeringsresultat=None,
            felmeddelande="Kunde inte maskera datan från Spiris. Försök igen.",
        )

    return InläsningsResultat(sie=sie, maskeringsresultat=maskeringsresultat, felmeddelande=None)


# --- Fakturautkast: Smart Godkännande / HITL (Fas 7) -------------------------
#
# Pure, UI-fri logik bakom "skapa kundfaktura"-flödet: bygg ett granskningsbart
# utkast (konteringsmotorns förslag ELLER ett tidigare inlärt mönster ur
# konteringsminnet), låt en människa rätta det, och plocka ut den SLUTGILTIGA
# konteringen för inlärning. Själva POST:en (spiris_adapter.skapa_kundfaktura)
# och den krypterade lagringen (app_config.uppdatera_konteringsminne) ligger
# medvetet UTANFÖR den här filen — den rör bara draft-tillstånd, ingen I/O.

@dataclass
class Fakturaradsforslag:
    """En föreslagen fakturarad INNAN mänsklig granskning. kall_ur_minne
    skiljer 'föreslaget ur ett tidigare godkänt mönster för den här kunden'
    (självlärande delen) från 'konteringsmotorns regelbaserade AI-förslag' —
    så UI:t kan visa vilketdera det är, aldrig dölja källan för användaren."""

    beskrivning: str
    kategori: str
    belopp: Decimal
    antal: Decimal = Decimal("1")
    kontonr: str = ""
    kall_ur_minne: bool = False


def bygg_fakturautkast(
    kundnamn: str,
    fakturatyp: str,
    poster: list[dict],
    konteringsminne: dict[str, dict] | None = None,
) -> list[Fakturaradsforslag]:
    """Bygger ett granskningsbart fakturautkast: en Fakturaradsforslag per
    post, med kontonr förifyllt.

    Slår FÖRST upp kundens tidigare GODKÄNDA mönster
    (app_config.slå_upp_kontering) — hittas kategorin där, återanvänds den
    (den självlärande delen: "nästa gång... pre-konfigurera exakt de konton
    användaren tidigare godkänt"). Annars faller den tillbaka till
    konteringsmotorns regelbaserade förslag (spiris_adapter.foreslå_konto),
    som i sin tur är fail-closed på en okänd fakturatyp/kategori-kombination.

    poster: [{"beskrivning": str, "kategori": "arbete"|"materiel",
              "belopp": Decimal, "antal": Decimal (valfri, default 1)}]"""
    tidigare = slå_upp_kontering(konteringsminne or {}, kundnamn)
    tidigare_kontering: dict[str, str] = (tidigare or {}).get("kontering", {})

    utkast: list[Fakturaradsforslag] = []
    for post in poster:
        kategori = post["kategori"]
        if kategori in tidigare_kontering:
            kontonr = tidigare_kontering[kategori]
            kall_ur_minne = True
        else:
            kontonr = foreslå_konto(fakturatyp, kategori)
            kall_ur_minne = False
        utkast.append(
            Fakturaradsforslag(
                beskrivning=post["beskrivning"],
                kategori=kategori,
                belopp=post["belopp"],
                antal=post.get("antal", Decimal("1")),
                kontonr=kontonr,
                kall_ur_minne=kall_ur_minne,
            )
        )
    return utkast


def tillampa_kontonr_andringar(
    utkast: list[Fakturaradsforslag], andringar: dict[int, str]
) -> list[Fakturaradsforslag]:
    """Tillämpar mänskliga rättningar av kontonr (radindex -> nytt kontonr,
    t.ex. från Streamlit-textfält) på ett fakturautkast. Saknad/tom ändring
    för ett index lämnar raden orörd. Ren funktion — returnerar en NY lista,
    muterar inte indatan. En rättad rad markeras kall_ur_minne=False: det är
    inte längre "vad minnet sa" eller "vad AI:n gissade", det är ett
    fristående mänskligt beslut just nu."""
    resultat: list[Fakturaradsforslag] = []
    for i, rad in enumerate(utkast):
        nytt_kontonr = andringar.get(i)
        if nytt_kontonr and nytt_kontonr != rad.kontonr:
            resultat.append(replace(rad, kontonr=nytt_kontonr, kall_ur_minne=False))
        else:
            resultat.append(rad)
    return resultat


def kontering_fran_utkast(utkast: list[Fakturaradsforslag]) -> dict[str, str]:
    """Extraherar {kategori: kontonr} ur ett GODKÄNT fakturautkast — redo att
    läras in via app_config.uppdatera_konteringsminne. Det är den slutgiltiga,
    mänskligt bekräftade konteringen som lärs in (inte AI:ts råa förslag) —
    en rad som användaren rättade bidrar med sin RÄTTADE kontering."""
    return {rad.kategori: rad.kontonr for rad in utkast}


def fakturarader_for_betalning(utkast: list[Fakturaradsforslag]) -> list[dict]:
    """Konverterar ett GODKÄNT fakturautkast till dict-formen som
    spiris_adapter.losa_artikel_ider_for_fakturarader förväntar (kontonr
    per rad). Ren formkonvertering, ingen I/O — den LIVE artikel-uppslagning
    (kontonr -> ArticleId, se modulkommentaren i spiris_adapter.py om varför
    en kundfakturarad saknar ett eget kontofält) sker som ett SENARE,
    separat steg i app.py, inte här: den här funktionen förblir medvetet
    ren och I/O-fri, som resten av app_vy.py."""
    return [
        {
            "beskrivning": rad.beskrivning,
            "kategori": rad.kategori,
            "belopp": rad.belopp,
            "antal": rad.antal,
            "kontonr": rad.kontonr,
        }
        for rad in utkast
    ]


# --- AI-agenten (Tool Calling): tolka Verktygsanrop till utkast (Fas 9) ------
#
# chatt_klient.Verktygsanrop är RÅ, ovaliderad AI-indata (namn + en dict från
# Anthropics tool_use-block). De två funktionerna nedan är den ENDA bron
# mellan agentläget och det HITL-utkastbygge som redan finns ovan
# (bygg_fakturautkast m.fl.) — de validerar/normaliserar, men bygger ALDRIG
# själva ett utkast eller pratar med Spiris. AI:t föreslår bara VILKET
# verktyg och VILKA fält; människan (via app.py:s "Godkänn och Skicka")
# fattar alla faktiska beslut därefter, exakt som när utkastet startar från
# den manuella formulär-knappen i stället.

@dataclass
class KundutkastForslag:
    """Ett föreslaget kundutkast INNAN mänsklig granskning — skapa_kund-
    verktygets motsvarighet till Fakturaradsforslag. Redigerbart i chatt-
    UI:t (kundnamn/ar_privatperson) innan Godkänn och Skicka."""

    kundnamn: str
    ar_privatperson: bool


def tolka_kundverktygsanrop(indata: dict) -> KundutkastForslag:
    """Validerar/normaliserar AI:ts skapa_kund-verktygsanrop (chatt_klient.
    Verktygsanrop.indata) till ett granskningsbart KundutkastForslag.

    Fail-closed: saknas eller är kundnamnet tomt höjs ValueError — AI:t får
    ALDRIG utlösa ett kundutkast utan ett namn att visa för mänsklig
    granskning. ar_privatperson saknar en giltig default att gissa på (True
    ELLER False är båda ett påstående om verkligheten) och tolkas därför
    strikt (bool(...)) snarare än att anta ett värde AI:t inte angav."""
    kundnamn = str(indata.get("kundnamn") or "").strip()
    if not kundnamn:
        raise ValueError("AI:ts skapa_kund-anrop saknar ett kundnamn.")
    return KundutkastForslag(kundnamn=kundnamn, ar_privatperson=bool(indata.get("ar_privatperson")))


# Under den här likheten (difflib.SequenceMatcher.ratio(), 0.0–1.0) räknas
# namnet som en helt annan kund, inte en möjlig stavvariant — vald för att
# fånga enstaka-bokstavs-skillnader ("Karl"/"Carl") utan att börja föreslå
# namn som bara råkar dela några bokstäver.
FUZZY_KUNDMATCHNING_TRÖSKEL = 0.72
FUZZY_KUNDMATCHNING_MAX_ANTAL = 5


@dataclass
class Kundkandidat:
    """En BEFINTLIG Spiris-kund vars namn liknar sökningen men inte är en
    exakt träff. likhet är difflib-kvoten (0.0–1.0) — bara till för att
    sortera/visa, ingen affärslogik läser den vidare."""

    kund_id: str
    namn: str
    likhet: float


def sok_lika_kunder(
    kundnamn: str,
    kunder: list[dict],
    tröskel: float = FUZZY_KUNDMATCHNING_TRÖSKEL,
    max_antal: int = FUZZY_KUNDMATCHNING_MAX_ANTAL,
) -> list[Kundkandidat]:
    """Fuzzy-sökning (stdlib difflib — inget nytt beroende) efter kunder som
    LIKNAR kundnamn men inte är en exakt träff. Exakt träff hanteras separat
    i app.py:s 'sok_kund'-fas (case-insensitive ==) och exkluderas härifrån
    — den ska aldrig dyka upp som ett "menade du"-förslag på sig själv.

    Motiv: när kunden helt saknas ELLER namnet är tvetydigt (t.ex.
    "Karl Svensson" mot en redan befintlig "Carl Svensson") ska gränssnittet
    ALDRIG falla tillbaka på en fritext-motfråga — bara strukturerade
    knappval (se _rendera_fakturautkast:s 'kund_saknas'-fas i app.py).
    Den här funktionen levererar kandidaterna de knapparna renderas ur.

    Sorterad fallande efter likhet, trunkerad till max_antal."""
    sökt = kundnamn.strip().casefold()
    kandidater = []
    for kund in kunder:
        namn = (kund.get("Name") or "").strip()
        if not namn or namn.casefold() == sökt:
            continue
        likhet = SequenceMatcher(None, sökt, namn.casefold()).ratio()
        if likhet >= tröskel:
            kandidater.append(Kundkandidat(kund_id=kund.get("Id"), namn=namn, likhet=likhet))
    kandidater.sort(key=lambda k: k.likhet, reverse=True)
    return kandidater[:max_antal]


def _decimal_fran_verktygsindata(varde: Any) -> Decimal:
    """AI:ts verktygsindata ger tal som JSON-nummer (int/float), aldrig
    Decimal — samma gräns som Streamlits number_input redan korsar i
    _rendera_fakturautkast_formular i app.py. Decimal(str(...)) för att
    aldrig introducera en float-artefakt i beloppet självt."""
    if varde is None or varde == "":
        return Decimal("0")
    return Decimal(str(varde))


def tolka_fakturaverktygsanrop(indata: dict) -> dict[str, Any]:
    """Validerar/normaliserar AI:ts skapa_kundfaktura-verktygsanrop till
    samma 'tillstånd'-form app.py:s state-maskin redan använder efter det
    manuella formuläret — så BÅDA vägarna in (knapp-formulär eller AI-
    verktyg) landar i EXAKT samma efterföljande kod (sök kund -> bygg
    utkast -> granskning -> Godkänn och Skicka).

    Fail-closed på det AI:t MÅSTE ange (kundnamn, fakturatyp) — foreslå_konto
    höjer senare, i sin tur, om fakturatyp inte är en känd kategori. Ingen
    kontering görs här: det är fortfarande konteringsmotorns/konterings-
    minnets jobb, längre ned i samma kedja som det manuella formuläret
    redan använder."""
    kundnamn = str(indata.get("kundnamn") or "").strip()
    if not kundnamn:
        raise ValueError("AI:ts skapa_kundfaktura-anrop saknar ett kundnamn.")
    fakturatyp = str(indata.get("fakturatyp") or "").strip()
    if not fakturatyp:
        raise ValueError("AI:ts skapa_kundfaktura-anrop saknar en fakturatyp.")

    arbetskostnad = _decimal_fran_verktygsindata(indata.get("arbetskostnad"))
    materielkostnad = _decimal_fran_verktygsindata(indata.get("materielkostnad"))

    # Fynd B: ROT-uppgifterna (särskilt fastighetsägarens personnummer) samlas
    # ALDRIG in via AI:t längre — de tas i ett lokalt formulär (fasen
    # "rot_lokalt" i app.py). Även om ett verktygsanrop skulle råka bära dem
    # ignoreras de här: tomma värden tvingar fram den lokala kompletteringen.
    return {
        "kundnamn": kundnamn,
        "fakturatyp": fakturatyp,
        "arbetskostnad": arbetskostnad,
        "materielkostnad": materielkostnad,
        "fastighetsbeteckning": "",
        "personnummer": "",
        "arbetstimmar": Decimal("0"),
        "rot_avdrag": Decimal("0"),
    }


def bygg_ny_kund_payload(
    kundnamn: str,
    ar_privatperson: bool,
    orgnr_eller_personnr: str,
    adress: str = "",
    postnr: str = "",
    ort: str = "",
) -> dict[str, Any]:
    """Bygger POST-payloaden för en ny Spiris-kund (skapa 'ny_kund_uppgifter'-
    fasen i app.py, EFTER att kunden konstaterats sakna en exakt ELLER nära
    träff — se sok_lika_kunder). Name/IsPrivatePerson/CorporateIdentityNumber
    är samma bekräftade fältnamn som redan används i spiris_adapter.py
    (verifierade mot en riktig sandbox-POST i ett tidigare skede).

    OBS adressfälten (Address1/ZipCode/City): dessa är ÄNNU EJ verifierade
    mot en riktig sandbox-POST — samma typ av dokumenterat, medvetet gap som
    ROT-personnumret i spiris_adapter.bygg_rot_uppgifter hade innan DET
    verifierades. Bäst nuvarande gissning utifrån Visma eAccounting-API:ts
    övriga namnkonventioner (PascalCase, "City"/"ZipCode" på andra
    endpoints). Utelämnas helt om tomma, i stället för att skicka tomma
    strängar Spiris kanske avvisar."""
    payload: dict[str, Any] = {
        "Name": kundnamn,
        "IsPrivatePerson": ar_privatperson,
        "CorporateIdentityNumber": orgnr_eller_personnr,
    }
    if adress:
        payload["Address1"] = adress
    if postnr:
        payload["ZipCode"] = postnr
    if ort:
        payload["City"] = ort
    return payload


@dataclass
class Valfraga:
    """Ett förtydligande flervalsspörsmål AI:t begärt via efterfraga_val-
    verktyget (Fas 10) — chatt-UI:ts motsvarighet till KundutkastForslag/
    Fakturaradsforslag, fast för ett OBESVARAT klargörande i stället för
    ett granskningsbart utkast. Renderas som knappar (en per alternativ)
    direkt under AI:ts meddelande i app.py."""

    fraga: str
    alternativ: list[str]


def tolka_valverktygsanrop(indata: dict) -> Valfraga:
    """Validerar/normaliserar AI:ts efterfraga_val-verktygsanrop.

    Fail-closed: en tom fråga eller färre än två alternativ är inte ett
    meningsfullt flerval att rendera som knappar — AI:t får då hellre ett
    tydligt tolkningsfel (visat i chatten) än ett trasigt UI-block med noll
    eller en knapp."""
    fraga = str(indata.get("fraga") or "").strip()
    if not fraga:
        raise ValueError("AI:ts efterfraga_val-anrop saknar en fråga.")
    alternativ = [
        rensat for a in (indata.get("alternativ") or []) if (rensat := str(a).strip())
    ]
    if len(alternativ) < 2:
        raise ValueError("AI:ts efterfraga_val-anrop måste ange minst två alternativ.")
    return Valfraga(fraga=fraga, alternativ=alternativ)
