"""spiris_adapter — ren mappning av rå Spiris/Visma eAccounting-JSON till
projektets domänmodell (SIEFil/Konto/Verifikation/Transaktion/Saldopost).

Ingen HTTP och ingen analyslogik här: exakt samma "domänmodellen som skarv"-
princip som resten av kodbasen. Så länge adaptern producerar samma
domänobjekt som sie4_parser.parse_sie4 gör, körs Modul 1–5, sekretesslagret
och app.py vidare helt oförändrade på levande Spiris-data.

Kontrakt mot spiris_klient.py: belopp/saldon kommer redan som Decimal (JSON
parsas med parse_float=Decimal där). Adaptern introducerar aldrig en float.
Se ARCHITECTURE_tillagg_spiris.md för mappningsbesluten (typtabell, UB/RES-
split, medvetna avgränsningar).
"""

from __future__ import annotations

import base64
import logging
from datetime import date, timedelta
from pathlib import Path
from decimal import Decimal
from typing import Any, Literal, Protocol

from domain_model import Konto, Saldopost, SIEFil, Transaktion, Verifikation
from namnreferens import las_namnreferens
from reskontra_tvatt import (
    Kundpost,
    Leverantorspost,
    ar_juridisk_person,
    normalisera_spiris_datum,
    tvatta_kundreskontra,
    tvatta_leverantorsreskontra,
)
from sekretesslager import innehaller_kant_personnamn, skapa_kontonamnsmaskerare
from spiris_klient import SpirisKlientFel

_logger = logging.getLogger(__name__)

Ktyp = Literal["T", "S", "K", "I"]

# Spiris/Visma-typnummer (GET /accountTypes) -> SIE #KTYP. Beslut a:
# 0-9 tillgångar->T, 10-19 kapital/skulder->S, 20-23 intäkter->I,
# 24-27 kostnader->K. 28 (finansiella intäkter OCH kostnader), 29
# (dispositioner/skatteposter) och 30 (resultat) är tvetydiga mellan K och I
# och mappas medvetet till None — kontotyp_vakt hoppar över typ=None, så det
# blir fail-closed (ingen gissad typ som sedan granskas mot sig själv),
# aldrig en tyst felklassning.
def spiris_typ_till_ktyp(typ: int | None) -> Ktyp | None:
    if typ is None:
        return None
    if 0 <= typ <= 9:
        return "T"
    if 10 <= typ <= 19:
        return "S"
    if 20 <= typ <= 23:
        return "I"
    if 24 <= typ <= 27:
        return "K"
    return None


def mappa_konto(rå: dict) -> Konto:
    return Konto(
        kontonr=str(rå["Number"]),
        namn=rå["Name"],
        typ=spiris_typ_till_ktyp(rå.get("Type")),
    )


def mappa_transaktion(rå_rad: dict) -> Transaktion:
    # SIE:s teckenkonvention återskapas: ett belopp är debet minus kredit.
    # Bägge är redan Decimal (klientens parse_float=Decimal), så resultatet
    # blir Decimal utan att någon float passeras.
    belopp = rå_rad["DebitAmount"] - rå_rad["CreditAmount"]
    return Transaktion(
        kontonr=str(rå_rad["AccountNumber"]),
        belopp=belopp,
        transtext=rå_rad.get("TransactionText"),
    )


def _harled_vernr(number_and_series: str, number_series: str | None) -> str:
    """"A12" med serie "A" -> "12". Fail-safe: går serieprefixet inte att
    skala av (serie saknas eller är inte ett prefix), behålls hela numret —
    ingen siffra tappas tyst."""
    if number_series and number_and_series.startswith(number_series):
        return number_and_series[len(number_series):]
    return number_and_series


def mappa_verifikation(rå: dict) -> Verifikation:
    return Verifikation(
        serie=rå.get("NumberSeries"),
        vernr=_harled_vernr(rå["NumberAndNumberSeries"], rå.get("NumberSeries")),
        verdatum=date.fromisoformat(rå["VoucherDate"]),
        vertext=rå.get("VoucherText"),
        regdatum=date.fromisoformat(rå["CreatedUtc"][:10]) if rå.get("CreatedUtc") else None,
        transaktioner=[mappa_transaktion(r) for r in rå.get("Rows", [])],
    )


def mappa_saldon(
    rå_saldon: list[dict], årsnr: int = 0
) -> tuple[list[Saldopost], list[Saldopost]]:
    """Delar kontosaldon i (utgående_balanser, resultat). Beslut b: splitten
    görs på kontoklass (nummerserien) — klass 1-2 är balanskonton (#UB),
    klass 3-8 är resultatkonton (#RES) — inte på Type-fältet, så saldovägen
    är oberoende av typmappningen. Nollsaldon utelämnas (samma som SIE-
    exportens beteende)."""
    utgående_balanser: list[Saldopost] = []
    resultat: list[Saldopost] = []
    for rad in rå_saldon:
        saldo = rad["Balance"]
        if saldo == 0:
            continue
        kontonr = str(rad["AccountNumber"])
        post = Saldopost(årsnr=årsnr, kontonr=kontonr, objektreferenser={}, saldo=saldo)
        if kontonr[:1] in ("1", "2"):
            utgående_balanser.append(post)
        else:
            resultat.append(post)
    return utgående_balanser, resultat


def filtrera_aktiva_konton(
    konton: dict[str, Konto],
    verifikationer: list[Verifikation],
    utgående_balanser: list[Saldopost],
    resultat: list[Saldopost],
) -> dict[str, Konto]:
    """Behåller bara konton med faktisk aktivitet — ett saldo (UB eller RES)
    eller minst en transaktion. Spiris /accounts returnerar hela
    standardkontoplanen (1400+ konton), och utan denna filtrering brusflaggar
    Modul 2 (kontotyp-vakt) inaktiva nollsaldo-konton. mappa_saldon har redan
    utelämnat nollsaldon, så ett kontonr i utgående_balanser/resultat innebär
    per definition ett skilt-från-noll-saldo."""
    aktiva = {post.kontonr for post in utgående_balanser}
    aktiva |= {post.kontonr for post in resultat}
    for verifikation in verifikationer:
        for transaktion in verifikation.transaktioner:
            aktiva.add(transaktion.kontonr)
    return {kontonr: konto for kontonr, konto in konton.items() if kontonr in aktiva}


class _Spirisklient(Protocol):
    """Det minimala klientkontrakt orkestreringen behöver — duck-typat, så
    LÄSVÄGARNA aldrig behöver bry sig om spiris_klient.SpirisKlient konkret
    (håller lagren fristående och testet kan injicera en fejk-klient).
    SKRIVVägarna (skapa_kund/skapa_kundfaktura) importerar däremot
    SpirisKlientFel rakt av, för att kunna logga fail-closed vid en
    misslyckad POST — testerna injicerar ändå en egen fejk-klient som kastar
    samma (importerbara) undantagstyp, så duck-typningen av SJÄLVA klienten
    påverkas inte."""

    def hamta_en(self, path: str, params: dict | None = ...) -> dict: ...
    def hamta_alla(self, path: str, params: dict | None = ...) -> list[dict]: ...
    def skicka(self, path: str, data: dict) -> dict: ...


def hamta_siefil_fran_spiris(
    klient: _Spirisklient, räkenskapsår_id: str, tom_datum: str
) -> SIEFil:
    """Limmet: hämtar de fyra endpoints som behövs och väver ihop dem till
    en komplett SIEFil via mapparna ovan. Gör INGEN egen HTTP och ingen
    analys — klienten sköter transporten, mapparna sköter översättningen, och
    resultatet är ett domänobjekt som glider rakt genom Modul 1–5 och
    sekretesslagret precis som en parse_sie4-läst fil."""
    företag = klient.hamta_en("/companysettings")
    råa_konton = klient.hamta_alla(f"/accounts/{räkenskapsår_id}")
    råa_verifikationer = klient.hamta_alla(f"/vouchers/{räkenskapsår_id}")
    råa_saldon = klient.hamta_alla(f"/accountbalances/{tom_datum}")

    konton = {}
    for rå in råa_konton:
        konto = mappa_konto(rå)
        konton[konto.kontonr] = konto

    verifikationer = [mappa_verifikation(rå) for rå in råa_verifikationer]
    utgående_balanser, resultat = mappa_saldon(råa_saldon)

    # Spiris /accounts ger hela standardkontoplanen; behåll bara aktiva konton
    # så Modul 2 inte brusflaggar inaktiva nollsaldo-konton.
    konton = filtrera_aktiva_konton(konton, verifikationer, utgående_balanser, resultat)

    return SIEFil(
        företagsnamn=företag.get("Name", ""),
        orgnr=företag.get("CorporateIdentityNumber"),
        valuta=företag.get("CurrencyCode", "SEK"),
        konton=konton,
        verifikationer=verifikationer,
        utgående_balanser=utgående_balanser,
        resultat=resultat,
    )


# --- Leverantörsreskontra (Fas C) -------------------------------------------

# Spiris PaymentStatus (SupplierInvoiceApi) -> läsbar svensk text.
_PAYMENT_STATUS_TEXT: dict[int, str] = {
    3: "Obetald",
    4: "Delbetald (förfallen)",
    5: "Delbetald",
    6: "Betald",
    7: "Förfallen",
    8: "Ej exporterad till betalfil",
    9: "Betald i bank",
    10: "Ej skickad till bank",
    11: "Väntar signering",
    12: "Makulerad",
}


def _betalstatus_text(kod) -> str:
    return _PAYMENT_STATUS_TEXT.get(kod, f"Status {kod}")


def bygg_reskontra_rader(rå_suppliers: list[dict], rå_fakturor: list[dict]) -> list[dict]:
    """Joinar leverantörsfakturor med leverantörer (för org.nr, som bara finns
    på /suppliers) och filtrerar till ÖPPNA poster (RemainingAmount != 0,
    beslut B) — betalda nollrader exkluderas. belopp = RemainingAmount, som
    summerar mot huvudbok 2440. Producerar tvatta_leverantorsreskontras indata.

    forfallodatum (Visma eAccounting "DueDate") krävs av
    fpa_motor.bygg_likviditetsprognos dag-för-dag-utflöden. Direkt indexering,
    inte .get: förfallodatum är lika grundläggande för en faktura som
    VoucherDate är för en verifikation (se mappa_verifikation ovan) — saknas
    det ska mappningen fail-closed:a med KeyError, inte tyst producera en
    likviditetsprognos med hål i. Sandbox-verifierat (live, 2026-07-19):
    "DueDate" finns på /supplierinvoices, format "YYYY-MM-DD" (ingen
    tidskomponent) — [:10]-slicen behövs alltså inte här, men behålls som
    samma försvar mot en fullständig datetime-sträng som CreatedUtc har ovan,
    ifall formatet skulle skilja sig mellan sandbox och produktion."""
    supplier_map = {s.get("Id"): s for s in rå_suppliers}
    rader: list[dict] = []
    for faktura in rå_fakturor:
        belopp = faktura.get("RemainingAmount", Decimal("0"))
        if belopp == 0:
            continue  # stängd/betald post — inte del av den aktuella reskontran
        supplier = supplier_map.get(faktura.get("SupplierId"), {})
        rader.append(
            {
                "namn": faktura.get("SupplierName") or supplier.get("Name") or "",
                "orgnr": supplier.get("CorporateIdentityNumber") or "",
                "belopp": belopp,
                "betalstatus": _betalstatus_text(faktura.get("PaymentStatus")),
                "forfallodatum": date.fromisoformat(faktura["DueDate"][:10]),
            }
        )
    return rader


def _bygg_namnvakt():
    """Namnvakten (`ar_kanslig_namn`) som reskontra_tvatt tar men som ingen
    anropare skickade in — parametern har haft `lambda _namn: False` som default
    sedan den skrevs, och användes bara i ett test. Följden: ett bolagsform-
    suffix räckte för att släppa igenom namnet, så "Anna Andersson AB" gick i
    klartext till AI:n. Org.nr-regeln är fortsatt det primära skyddet; det här
    är nätet under den. Referenslistan läses EN gång per hämtning."""
    referenslista = las_namnreferens()
    return lambda namn: innehaller_kant_personnamn(namn, referenslista)


def skapa_verifikat(klient: _Spirisklient, verifikat_data: dict) -> dict:
    """POSTar ett verifikat till Spiris (/vouchers).

    Ett verifikat påverkar räkenskaperna DIREKT och kan inte tas bort i
    efterhand — bara rättas med ett nytt verifikat. Ansvaret för innehållet
    ligger enligt bokföringslagen 5 kap. på den bokföringsskyldige.

    Postar ALDRIG av sig själv. Anropas bara efter ett explicit mänskligt
    godkännande i appen (se utfor_utkast och app.py:s Åtgärder-flik)."""
    try:
        skapat = klient.skicka("/vouchers", verifikat_data)
    except SpirisKlientFel:
        _logger.error("Kunde inte skapa verifikat i Spiris.")
        raise
    _logger.info("Verifikat skapat i Spiris (Id=%s).", skapat.get("Id"))
    return skapat


def skapa_verifikatutkast(klient: _Spirisklient, verifikat_data: dict) -> dict:
    """POSTar ett verifikatUTKAST till Spiris (/voucherdrafts).

    Skiljer sig från skapa_verifikat i EN avgörande egenskap: resultatet är
    återkalleligt. Ett utkast går att ändra (PUT) och ta bort (DELETE), och
    påverkar inte räkenskaperna förrän en människa befordrar det via
    /convert i Spiris eget gränssnitt.

    Den här funktionen befordrar ALDRIG. /convert anropas inte härifrån och
    exponeras inte över MCP — bokföringsakten hör hemma hos människan.

    Payloaden är densamma som för /vouchers: VoucherDraftApi har samma form
    som VoucherApi för de fält vi sätter (se _bygg_verifikat_payload)."""
    try:
        skapat = klient.skicka("/voucherdrafts", verifikat_data)
    except SpirisKlientFel:
        _logger.error("Kunde inte skapa verifikatutkast i Spiris.")
        raise
    _logger.info("Verifikatutkast skapat i Spiris (Id=%s).", skapat.get("Id"))
    return skapat


# CustomerInvoiceDraftApi kräver tre fält som CustomerInvoiceApi klarar sig
# utan i praktiken. Specen markerar dem som obligatoriska på BÅDA — men den
# skarpa vägen (bygg_kundfaktura_payload) utelämnar dem och gav ändå 201
# Created i en riktig sandbox-POST (2026-07-19). Ännu ett fall där specen och
# verkligheten går isär; därför sätts de bara på UTKASTvägen, som inte är
# live-verifierad, och den skarpa vägen lämnas orörd.
_UTKAST_STANDARD_EU_TREDJEPART = False
_UTKAST_STANDARD_TEXTRAD = False
_UTKAST_STANDARD_OMVAND_BYGGMOMS = False


def bygg_kundfakturautkast_payload(
    faktura_payload: dict, fakturarader: list[dict] | None = None
) -> dict:
    """Översätter en färdig /customerinvoices-payload till /customerinvoicedrafts.

    Ren transformation, ingen I/O — samma princip som bygg_kundfaktura_payload,
    och testbar utan klient. Utgår MEDVETET från den redan sandbox-verifierade
    fakturapayloaden i stället för att bygga en egen: allt som är verifierat om
    kontering, ROT och artikelrader gäller då oförändrat, och skillnaden mot
    utkastformatet blir synlig på ett enda ställe.

    Tre fält läggs till, alla obligatoriska enligt CustomerInvoiceDraftApi:
    EuThirdParty och RotReducedInvoicingType på fakturan, IsTextRow och
    ReversedConstructionServicesVatFree per rad.

    SANDBOX-VERIFIERAT 2026-08-06 (skrivprov mot riktiga utkast):
    ReversedConstructionServicesVatFree = False och ett HELT UTELÄMNAT fält ger
    IDENTISKT resultat — samma moms, samma radvärde tillbaka. Osäkerheten som
    stod här tidigare är alltså avförd: tillägget är beteendemässigt neutralt.

    Däremot avslöjade samma prov ett ANNAT och verkligt fel: byggmomsvägen
    fungerar inte alls, varken här eller på den skarpa vägen. Omvänd
    skattskyldighet kräver att kunden är flaggad OCH att radflaggan sätts till
    True — se kommentaren vid _KONTERINGSTABELL och RISKREGISTER R-15. Den
    här funktionen sätter medvetet inte True: en oflaggad kund avvisas då med
    HTTP 400, så rättningen kräver en kundkontroll som är ett eget beslut.

    Redan satta värden skrivs aldrig över: bär payloaden ROT-uppgifter har
    bygg_rot_uppgifter redan satt RotReducedInvoicingType, och det värdet
    gäller."""
    rows = faktura_payload.get("Rows", [])
    granskade = fakturarader if fakturarader is not None else []
    if granskade and len(granskade) != len(rows):
        # Fail-closed: kan raderna inte paras ihop går det inte att avgöra
        # vilken rad som är byggmoms, och en gissning ger fel moms.
        raise ValueError(
            f"Antalet granskade rader ({len(granskade)}) matchar inte "
            f"payloadens rader ({len(rows)}) — byggmoms kan inte avgöras."
        )

    utkast_payload = dict(faktura_payload)
    utkast_payload.setdefault("EuThirdParty", _UTKAST_STANDARD_EU_TREDJEPART)
    utkast_payload.setdefault("RotReducedInvoicingType", ROT_TYP_NORMAL)

    nya_rader: list[dict[str, Any]] = []
    for index, rad in enumerate(rows):
        # R-15: radflaggan är det ENDA som faktiskt utlöser omvänd
        # skattskyldighet (mätt 2026-08-06). Den härleds ur den GRANSKADE
        # radens kontonr — payloadens rad bär inget konto, eftersom en
        # Spiris-fakturarad konteras via artikeln.
        omvand = _UTKAST_STANDARD_OMVAND_BYGGMOMS
        if granskade:
            omvand = str(granskade[index].get("kontonr") or "") in BYGGMOMSKONTON
        nya_rader.append({
            **rad,
            "IsTextRow": rad.get("IsTextRow", _UTKAST_STANDARD_TEXTRAD),
            "ReversedConstructionServicesVatFree": rad.get(
                "ReversedConstructionServicesVatFree", omvand
            ),
        })
    utkast_payload["Rows"] = nya_rader
    return utkast_payload


def skapa_kundfakturautkast(klient: _Spirisklient, faktura_data: dict) -> dict:
    """POSTar ett kundfakturaUTKAST till Spiris (/customerinvoicedrafts).

    Samma återkallelighet som skapa_verifikatutkast, med ett extra skäl: en
    BOKFÖRD kundfaktura kan mejlas till en riktig mottagare och påverka riktig
    momsredovisning. Ett utkast kan varken mejlas eller bokföras förrän
    människan befordrar det i Spiris.

    Loggar aldrig kundnamn, personnummer eller belopp — bara artikel-ID,
    radantal och Spiris-ID, precis som skapa_kundfaktura."""
    try:
        skapat = klient.skicka("/customerinvoicedrafts", faktura_data)
    except SpirisKlientFel:
        _logger.error(
            "Kunde inte skapa kundfakturautkast i Spiris (%d rader, artiklar: %s).",
            len(faktura_data.get("Rows", [])),
            _artikel_ider_i_payload(faktura_data),
        )
        raise
    _logger.info(
        "Kundfakturautkast skapat i Spiris (Id=%s, %d rader, artiklar: %s).",
        skapat.get("Id"),
        len(faktura_data.get("Rows", [])),
        _artikel_ider_i_payload(faktura_data),
    )
    return skapat


def mappa_verifikatutkast(rå: dict) -> Verifikation:
    """VoucherDraftApi -> Verifikation, så att ETT och SAMMA maskeringslager
    (maskera_siefil) kan användas för utkast som för bokförda verifikat.

    Ett utkast har ännu inget verifikationsnummer — Spiris tilldelar det först
    vid /convert. `Id` används därför som vernr. Det är en opak identifierare,
    inte ett löpnummer, och docstringen finns för att ingen ska tolka det som
    att utkastet redan har fått sin plats i nummerserien.

    Fritexten (VoucherText, TransactionText) hämtas RÅ här och maskeras av
    maskera_siefil i spiris_rag — aldrig av den här funktionen. Samma
    ansvarsfördelning som mappa_verifikation.

    Radbeloppen läses med .get, INTE med mappa_transaktions direktindexering:
    på VoucherDraftRowApi är DebitAmount och CreditAmount valfria (bara
    AccountNumber är obligatoriskt), och ett halvfärdigt utkast där bara den
    ena sidan är ifylld är ett fullt normalt tillstånd. Att fälla hela
    listningen på det vore fel sorts fail-closed: här är ofullständighet
    innebörden, inte ett fel."""
    transaktioner = [
        Transaktion(
            kontonr=str(rad["AccountNumber"]),
            belopp=(rad.get("DebitAmount") or Decimal("0"))
            - (rad.get("CreditAmount") or Decimal("0")),
            transtext=rad.get("TransactionText"),
        )
        for rad in rå.get("Rows") or []
    ]
    return Verifikation(
        serie=rå.get("NumberSeries"),
        vernr=str(rå.get("Id") or ""),
        verdatum=date.fromisoformat(rå["VoucherDate"][:10]),
        vertext=rå.get("VoucherText"),
        regdatum=date.fromisoformat(rå["CreatedUtc"][:10]) if rå.get("CreatedUtc") else None,
        transaktioner=transaktioner,
    )


def _hitta_kund(klient: _Spirisklient, kundnamn: str) -> dict:
    """Slår upp EN kund på namn och returnerar hela det råa objektet.

    Fail-closed: en tvetydig eller utebliven träff höjer fel i stället för att
    gissa vilken kund som avses — en faktura till fel mottagare är värre än en
    faktura som inte skapas.

    Returnerar hela objektet, inte bara id:t, eftersom byggmomskontrollen
    behöver kundens ReverseChargeOnConstructionServices-flagga (se
    _kraver_byggmoms). Anroparen är alltid utfor_utkast lokalt — objektet går
    aldrig vidare till en AI."""
    namn = (kundnamn or "").strip().casefold()
    traffar = [
        k for k in klient.hamta_alla("/customers")
        if (k.get("Name") or "").strip().casefold() == namn
    ]
    if not traffar:
        raise SpirisKlientFel(f"Ingen kund med namnet {kundnamn!r} finns i Spiris.")
    if len(traffar) > 1:
        raise SpirisKlientFel(
            f"Flera kunder heter {kundnamn!r} — välj kund manuellt i Spiris."
        )
    return traffar[0]


def _hitta_kund_id(klient: _Spirisklient, kundnamn: str) -> str:
    """Kundens Spiris-id. Tunt omslag runt _hitta_kund."""
    return str(_hitta_kund(klient, kundnamn).get("Id") or "")


# --- Målet för en godkänd skrivning (Steg 4) --------------------------------
#
# MAL_UTKAST är STANDARD, och det är ett medvetet säkerhetsval. Ett bokfört
# verifikat kan enligt bokföringslagen 5 kap. inte tas bort — bara rättas med
# ett nytt. En bokförd kundfaktura kan dessutom mejlas till en riktig mottagare.
# Spiris utkastendpoints (/voucherdrafts, /customerinvoicedrafts) är däremot
# ÅTERKALLELIGA: de går att ändra (PUT) och ta bort (DELETE), och befordras till
# den skarpa posten först via /convert — i Spiris eget gränssnitt, av människan,
# med Spiris egen validering.
#
# Det flyttar alltså det oåterkalleliga momentet från VÅR sammanfattning till
# användarens eget bokföringsprogram. Appen kan fortfarande bokföra direkt
# (MAL_BOKFOR), men bara när människan uttryckligen väljer det.
#
# /convert exponeras ALDRIG över MCP. Att befordra ett utkast till en bokförd
# post är själva bokföringsakten och hör hemma hos människan.
MAL_UTKAST = "utkast"
MAL_BOKFOR = "bokfor"
GILTIGA_MAL: tuple[str, ...] = (MAL_UTKAST, MAL_BOKFOR)


def _bygg_verifikat_payload(nyttolast: dict) -> dict:
    """Verifikatets Spiris-payload. Delas av /vouchers och /voucherdrafts —
    VoucherDraftApi har samma form som VoucherApi för de fält vi sätter
    (NumberSeries, VoucherDate, VoucherText, Rows).

    Fältnamnen är SANDBOX-VERIFIERADE (2026-08-04) mot en riktig /vouchers-GET:
    verifikationstexten heter VoucherText (inte Description) och serien
    NumberSeries (inte VoucherSeries). Båda var fel i den första versionen och
    hade gett ett avvisat anrop."""
    return {
        "NumberSeries": nyttolast.get("verifikationsserie") or "A",
        "VoucherDate": nyttolast["transaktionsdatum"],
        "VoucherText": nyttolast["beskrivning"],
        "Rows": [
            {
                "AccountNumber": int(rad["konto"]),
                "DebitAmount": Decimal(str(rad.get("debet") or 0)),
                "CreditAmount": Decimal(str(rad.get("kredit") or 0)),
                "TransactionText": rad.get("text") or "",
            }
            for rad in nyttolast["rader"]
        ],
    }



def bygg_kontopayload(nyttolast: dict) -> dict:
    payload = {
        "Number": nyttolast["kontonr"],
        "Name": nyttolast["kontonamn"],
        "FiscalYearId": nyttolast["rakenskapsar_id"],
        "IsActive": nyttolast["aktiv"],
    }
    if "kontotyp" in nyttolast and nyttolast["kontotyp"] is not None:
        payload["Type"] = nyttolast["kontotyp"]
    if "momskod_id" in nyttolast and nyttolast["momskod_id"] is not None:
        payload["VatCodeId"] = nyttolast["momskod_id"]
    if "projekt_tillatet" in nyttolast and nyttolast["projekt_tillatet"] is not None:
        payload["IsProjectAllowed"] = nyttolast["projekt_tillatet"]
    if "kostnadsstalle_tillatet" in nyttolast and nyttolast["kostnadsstalle_tillatet"] is not None:
        payload["IsCostCenterAllowed"] = nyttolast["kostnadsstalle_tillatet"]
    if "sparrat_for_manuell_bokning" in nyttolast and nyttolast["sparrat_for_manuell_bokning"] is not None:
        payload["IsBlockedForManualBooking"] = nyttolast["sparrat_for_manuell_bokning"]
    return payload

_KONTO_ALLOWLIST = {
    "kontonamn": "Name",
    "aktiv": "IsActive",
    "kontotyp": "Type",
    "momskod_id": "VatCodeId",
    "projekt_tillatet": "IsProjectAllowed",
    "kostnadsstalle_tillatet": "IsCostCenterAllowed",
    "sparrat_for_manuell_bokning": "IsBlockedForManualBooking"
}

def bygg_kontoandring_payload(nuvarande: dict, andringar: dict) -> dict:
    if not andringar:
        raise ValueError("Inga ändringar angivna.")

    okanda = [nyckel for nyckel in andringar if nyckel not in _KONTO_ALLOWLIST]
    if okanda:
        giltiga = ", ".join(sorted(_KONTO_ALLOWLIST))
        raise SpirisKlientFel(
            f"Följande går inte att ändra på ett konto: "
            f"{sorted(okanda)}. Ändringsbara fält: {giltiga}."
        )

    uppdaterat = dict(nuvarande)
    for nyckel, varde in andringar.items():
        uppdaterat[_KONTO_ALLOWLIST[nyckel]] = varde
    return uppdaterat



def bygg_bokforingslas_payload(nyttolast: dict) -> dict:
    # U13.2: PUT /companysettings/accountinglocksettings
    return {
        "AccountingLockedAsOf": nyttolast["nytt_datum"]
    }

_ROTRUT_ALLOWLIST = {
    "RutMaxAmountForPersBelow65Year": "RutMaxAmountForPersBelow65Year", # To itself just for mapping
    "RutMaxAmountForPersOver65Year": "RutMaxAmountForPersOver65Year",
    "RutReducedInvoicingPercent": "RutReducedInvoicingPercent",
    "RotReducedInvoicingMaxAmount": "RotReducedInvoicingMaxAmount",
    "RotReducedInvoicingPercent": "RotReducedInvoicingPercent"
}

def bygg_rotrut_payload(nuvarande: dict, andringar: dict) -> dict:
    if not andringar:
        raise ValueError("Inga ändringar angivna.")

    okanda = [nyckel for nyckel in andringar if nyckel not in _ROTRUT_ALLOWLIST]
    if okanda:
        giltiga = ", ".join(sorted(_ROTRUT_ALLOWLIST))
        raise SpirisKlientFel(f"Följande går inte att ändra för ROT/RUT: {sorted(okanda)}. Ändringsbara fält: {giltiga}.")

    uppdaterat = dict(nuvarande)
    for nyckel, varde in andringar.items():
        uppdaterat[nyckel] = varde
    return uppdaterat


def utfor_utkast(
    klient: _Spirisklient, typ: str, nyttolast: dict, mal: str = MAL_UTKAST,
    granskad_mottagare: str | None = None,
) -> dict:
    """Utför ett MÄNSKLIGT GODKÄNT utkast mot Spiris.

    Enda vägen från ett MCP-föreslaget utkast till en faktisk skrivning. Får
    bara anropas efter `utkast.bekrafta_for_sandning`, som verifierar att
    nyttolasten är oförändrad sedan människan granskade den.

    Uppslagning av kund-id och artikel-id sker HÄR, inte när utkastet skapas:
    de är levande Spiris-data och kan ha ändrats sedan förslaget lades. Det som
    hashbindningen skyddar är användarens beslut (vem, vad, hur mycket) — inte
    de tekniska id:n som beslutet översätts till.

    `mal` följer SAMMA resonemang och ligger därför medvetet UTANFÖR den
    hashbundna nyttolasten: hashen binder VAD som ska skrivas (konton, belopp,
    datum, mottagare), inte VART det levereras. Människan får därmed välja
    destination vid godkännandet utan att utkastet ogiltigförklaras.

    Standard är MAL_UTKAST — en anropare som inte tar ställning får den
    återkalleliga vägen. Se kommentaren ovan.

    `granskad_mottagare` KRÄVS för de utåtriktade typerna (UTATRIKTADE_TYPER)
    och ska vara exakt den adress människan såg i godkännandevyn. Standardvärdet
    None är avsiktligt: en anropare som inte tar ställning kan alltså inte
    råka skicka ett mejl — den får ett fel. Se avsnittskommentaren för Steg 5."""
    if mal not in GILTIGA_MAL:
        giltiga = ", ".join(repr(m) for m in GILTIGA_MAL)
        raise SpirisKlientFel(f"Okänt mål: {mal!r}. Giltiga är: {giltiga}.")

    # Mottagargrinden. Kontrolleras HÄR, i den gemensamma vägen, så att en ny
    # utåtriktad typ inte kan läggas till utan att omfattas — samma resonemang
    # som villkorsspärren i mcp_server/server.py:_kor_spiris_verktyg.
    if typ in UTATRIKTADE_TYPER and not (granskad_mottagare or "").strip():
        raise SpirisKlientFel(
            f"Åtgärden {typ!r} når en tredje man och kräver en granskad "
            "mottagare. Ingenting skickades."
        )

    if typ == UTKASTTYP_FAKTURAUTSKICK:
        granskning = hamta_utskicksgranskning(klient, nyttolast["fakturanummer"])
        return skicka_faktura_epost(
            klient, granskning["faktura_id"], granskad_mottagare or "",
            nyttolast.get("amne") or "", nyttolast.get("meddelande") or "",
        )

    if typ == UTKASTTYP_BETALNINGSPAMINNELSE:
        granskning = hamta_utskicksgranskning(klient, nyttolast["fakturanummer"])
        avgift = nyttolast.get("drojsmalsavgift")
        return skicka_betalningspaminnelse(
            klient, granskning["faktura_id"], granskad_mottagare or "",
            Decimal(str(avgift)) if avgift is not None else None,
            nyttolast.get("amne") or "", nyttolast.get("meddelande") or "",
        )

    if typ == UTKASTTYP_BETALNINGSREGISTRERING:
        granskning = hamta_utskicksgranskning(klient, nyttolast["fakturanummer"])
        payload = bygg_betalningspayload(
            nyttolast["bankkonto_id"],
            nyttolast["betaldatum"],
            Decimal(str(nyttolast["belopp"])),
            granskning["valuta"],
            granskning["kvarvarande"],
            nyttolast.get("referens") or "",
        )
        return registrera_betalning(klient, granskning["faktura_id"], payload)

    if typ == UTKASTTYP_MAKULERING:
        granskning = hamta_utskicksgranskning(klient, nyttolast["fakturanummer"])
        return makulera_faktura(klient, granskning["faktura_id"])

    if typ == UTKASTTYP_SALJDOKUMENTUTSKICK:
        granskning = hamta_saljdokumentgranskning(
            klient, nyttolast["dokumenttyp"], nyttolast["nummer"]
        )
        return skicka_saljdokument_epost(
            klient, nyttolast["dokumenttyp"], granskning["dokument_id"],
            granskad_mottagare or "",
            nyttolast.get("amne") or "", nyttolast.get("meddelande") or "",
        )

    if typ == UTKASTTYP_EFAKTURAUTSKICK:
        granskning = hamta_efakturagranskning(klient, nyttolast["fakturanummer"])
        return skicka_efaktura(klient, granskning["faktura_id"])

    if typ == UTKASTTYP_SIE4IMPORT:
        # Filen läses HÄR, vid utförandet — utkastet bär bara sökvägen och de
        # granskade flaggorna. Innehållet har aldrig passerat en AI, och
        # nyttolastens hash binder användarens beslut (vilken fil, vilka
        # flaggor), inte filens bytes.
        sokvag = Path(nyttolast["sokvag"])
        try:
            innehall = sokvag.read_bytes()
        except OSError as e:
            raise SpirisKlientFel(
                f"Kunde inte läsa SIE4-filen {sokvag.name!r}. "
                "Ingenting har importerats."
            ) from e
        payload = bygg_sie4import_payload(
            innehall,
            importera_ingaende_balans=bool(nyttolast.get("ingaende_balans", False)),
            importera_kontonamn=bool(nyttolast.get("kontonamn", False)),
            mappa_konton=bool(nyttolast.get("mappa_konton", False)),
            arsavslut=bool(nyttolast.get("arsavslut", False)),
        )
        return importera_sie4(klient, payload)
        
    if typ == UTKASTTYP_UNDERLAGSKOPPLING:
        return klient.skicka("/attachmentlinks", nyttolast)

    if typ == UTKASTTYP_PERIODISERING:
        return klient.skicka("/allocationperiods", bygg_periodiseringspayload(nyttolast))

    if typ == UTKASTTYP_PERIODISERINGSANDRING:
        return klient.uppdatera("/allocationperiods", bygg_periodiseringspayload(nyttolast))

    if typ == UTKASTTYP_PERIODISERINGSBORTTAGNING:
        _id = nyttolast["leverantorsfakturautkast_id"]
        klient.ta_bort(f"/supplierinvoicedrafts/{_id}/allocationperiods")
        return {"borttaget": _id}


    if typ == UTKASTTYP_MASTERDATAANDRING:
        return andra_masterdata(
            klient, nyttolast["objekttyp"], nyttolast["objekt_id"],
            nyttolast["andringar"],
        )

    if typ == UTKASTTYP_UTKASTANDRING:
        return andra_utkast(
            klient, nyttolast["utkasttyp"], nyttolast["utkast_id"],
            nyttolast["andringar"]
        )

    if typ == UTKASTTYP_UTKASTBORTTAGNING:
        ta_bort_utkast(klient, nyttolast["utkasttyp"], nyttolast["utkast_id"])
        return {"borttaget": nyttolast["utkast_id"]}

    if typ == UTKASTTYP_UTKASTBOKFORING:
        return bokfor_utkast(klient, nyttolast["utkasttyp"], nyttolast["utkast_id"])


    if typ == UTKASTTYP_KONTO:
        return klient.skicka("/accounts", bygg_kontopayload(nyttolast))


    if typ == UTKASTTYP_BOKFORINGSLAS:
        return klient.uppdatera("/companysettings/accountinglocksettings", bygg_bokforingslas_payload(nyttolast))

    if typ == UTKASTTYP_ROTRUT:
        p = bygg_rotrut_payload(nyttolast["nuvarande"], nyttolast["andringar"])
        return klient.uppdatera("/companysettings/rotrut", p)

    if typ == UTKASTTYP_KONTOANDRING:
        # nyttolast innehåller 'rakenskapsar_id', 'kontonr', 'nuvarande' och 'andringar'
        # men vänta, utkast sparas utan `nuvarande` om den var stor, men
        # i U11 "hämta nuvarande konto, lägg ändringarna ovanpå"
        # Vi lägger `nuvarande` i nyttolast!
        p = bygg_kontoandring_payload(nyttolast["nuvarande"], nyttolast["andringar"])
        return klient.uppdatera(f"/accounts/{nyttolast['rakenskapsar_id']}/{nyttolast['kontonr']}", p)

    if typ == UTKASTTYP_MASTERDATABORTTAGNING:
        ta_bort_masterdata(
            klient, nyttolast["objekttyp"], nyttolast["objekt_id"]
        )
        # ta_bort_masterdata returnerar inget (204 utan kropp) — utkastkön vill
        # ändå ha ett resultat att spara.
        return {"borttaget": nyttolast["objekt_id"]}

    if typ == UTKASTTYP_LEVERANTORSFAKTURA:
        payload = bygg_leverantorsfakturautkast_payload(
            nyttolast["leverantor_id"],
            nyttolast["rader"],
            nyttolast.get("fakturanummer") or "",
            nyttolast.get("fakturadatum") or "",
            nyttolast.get("forfallodatum") or "",
            Decimal(str(nyttolast["totalbelopp"]))
            if nyttolast.get("totalbelopp") is not None else None,
            bool(nyttolast.get("kreditfaktura", False)),
        )
        return skapa_leverantorsfakturautkast(klient, payload)

    if typ == UTKASTTYP_ATTEST:
        objekttyp = nyttolast["objekttyp"]
        # Leverantörsfakturan slås upp så att ett fakturanummer räcker; en
        # momsrapport adresseras alltid med sitt id (spiris_momsrapporter ger
        # det redan).
        if objekttyp == "leverantorsfaktura":
            objekt_id = str(
                _hitta_leverantorsfaktura(klient, nyttolast["objekt"]).get("Id") or ""
            )
        else:
            objekt_id = str(nyttolast["objekt"])
        return attestera(klient, objekttyp, objekt_id, nyttolast["beslut"])

    if typ == UTKASTTYP_KVITTNING:
        return skapa_kvittning(klient, nyttolast["kreditfaktura_id"], nyttolast["payload"])

    if typ == UTKASTTYP_LEVERANTORSBETALNING:
        faktura = _hitta_leverantorsfaktura(klient, nyttolast["faktura"])
        payload = bygg_betalningspayload(
            nyttolast["bankkonto_id"],
            nyttolast["betaldatum"],
            Decimal(str(nyttolast["belopp"])),
            faktura.get("CurrencyCode") or "SEK",
            faktura.get("RemainingAmount"),
            nyttolast.get("referens") or "",
        )
        return registrera_leverantorsbetalning(
            klient, str(faktura.get("Id") or ""), payload
        )

    if typ == UTKASTTYP_SALJDOKUMENTATGARD:
        granskning = hamta_saljdokumentgranskning(
            klient, nyttolast["dokumenttyp"], nyttolast["nummer"]
        )
        return utfor_saljdokumentatgard(
            klient, nyttolast["dokumenttyp"], granskning["dokument_id"],
            nyttolast["atgard"],
        )

    if typ == "kund":
        # En kund har ingen utkastmotsvarighet i Spiris — `mal` är utan verkan
        # här. Det är inte en tyst avvikelse: en kundpost är inte en
        # bokföringshändelse, går att ändra (PUT) och att ta bort (DELETE),
        # och bär alltså inte den oåterkallelighet som motiverar utkastvägen.
        return skapa_kund(klient, nyttolast)

    if typ == "kundfaktura":
        kund = _hitta_kund(klient, nyttolast["kundnamn"])
        kund_id = str(kund.get("Id") or "")
        rader = [
            {
                "beskrivning": rad["beskrivning"],
                "belopp": Decimal(str(rad["pris"])),
                "antal": Decimal(str(rad["antal"])),
                "kontonr": rad.get("konto") or "",
            }
            for rad in nyttolast["rader"]
        ]
        # --- R-15: byggmomsgrinden ---------------------------------------
        # Uppmätt mot sandbox 2026-08-06: omvänd skattskyldighet uppstår BARA
        # när kunden är flaggad OCH fakturaraden bär
        # ReversedConstructionServicesVatFree=True. Fakturanivåns
        # ReverseChargeOnConstructionServices är HÄRLEDD ur kunden och går inte
        # att sätta. Två konsekvenser, båda fail-closed här:
        if _kraver_byggmoms(rader):
            if not kund.get("ReverseChargeOnConstructionServices"):
                raise SpirisKlientFel(
                    f"Kunden {nyttolast['kundnamn']!r} är inte registrerad för "
                    "omvänd skattskyldighet i Spiris. En byggmomsfaktura skulle "
                    "då debiteras full moms. Kryssa i omvänd skattskyldighet på "
                    "kunden i Spiris först — ingen faktura har skapats."
                )
            if mal != MAL_UTKAST:
                # /customerinvoices saknar radfältet HELT (CustomerInvoiceRowApi
                # har inget reverse-charge-fält). Byggmoms går alltså inte att
                # uttrycka på den skarpa vägen — en direktbokförd byggmomsfaktura
                # skulle ofrånkomligen få 25 % moms.
                raise SpirisKlientFel(
                    "Byggmoms (omvänd skattskyldighet) kan inte direktbokföras: "
                    "Spiris fakturarader saknar fältet på den vägen och momsen "
                    "skulle bli fel. Välj 'Skapa utkast i Spiris' i stället — "
                    "ingen faktura har skapats."
                )

        losta = losa_artikel_ider_for_fakturarader(klient, rader)
        idag = date.today()
        payload = bygg_kundfaktura_payload(
            kund_id,
            losta,
            nyttolast.get("fakturadatum") or idag.isoformat(),
            nyttolast.get("forfallodatum")
            or (idag + timedelta(days=30)).isoformat(),
        )
        if mal == MAL_UTKAST:
            return skapa_kundfakturautkast(
                klient, bygg_kundfakturautkast_payload(payload, losta)
            )
        return skapa_kundfaktura(klient, payload)

    if typ == "offertutkast":
        kund = _hitta_kund(klient, nyttolast["kundnamn"])
        kund_id = str(kund.get("Id") or "")
        rader_in = [
            {
                "beskrivning": rad["beskrivning"],
                "belopp": Decimal(str(rad["pris"])),
                "antal": Decimal(str(rad["antal"])),
                "kontonr": rad.get("konto") or "",
            }
            for rad in nyttolast["rader"]
        ]
        losta = losa_artikel_ider_for_fakturarader(klient, rader_in)
        kf_payload = bygg_kundfaktura_payload(kund_id, losta, "2000-01-01", "2000-01-01")
        
        pl = {
            "CustomerId": kund_id,
            "QuoteDate": nyttolast.get("offertdatum"),
            "DueDate": nyttolast.get("forfallodatum"),
            "Rows": kf_payload.get("Rows", []),
        }
        if nyttolast.get("valuta"): pl["CurrencyCode"] = nyttolast["valuta"]
        if nyttolast.get("inkl_moms") is not None: pl["IncludesVat"] = nyttolast["inkl_moms"]
        if nyttolast.get("leveransdatum"): pl["DeliveryDate"] = nyttolast["leveransdatum"]
        if nyttolast.get("kundreferens"): pl["CustomerReference"] = nyttolast["kundreferens"]
        if nyttolast.get("var_referens"): pl["CompanyReference"] = nyttolast["var_referens"]

        skapad = klient.skapa("/quotedrafts", pl)
        return {"offertutkast_id": skapad.get("Id"), "kund": nyttolast["kundnamn"]}

    if typ == "verifikat":
        payload = _bygg_verifikat_payload(nyttolast)
        if mal == MAL_UTKAST:
            return skapa_verifikatutkast(klient, payload)
        return skapa_verifikat(klient, payload)

    if typ == UTKASTTYP_BETALNINGSVERIFIKAT:
        payload = _bygg_betalningsverifikat_payload(nyttolast)
        return skapa_betalningsverifikat(klient, payload)

    raise SpirisKlientFel(f"Okänd utkasttyp: {typ!r}.")


def hamta_rakenskapsar(klient: _Spirisklient) -> list[dict]:
    """Räkenskapsåren från /fiscalyears, normaliserade och nyast först.

    Finns för att räkenskapsårets id är INDATA till nästan alla andra
    Spiris-vägar (`/accounts/{id}`, `/vouchers/{id}`) men hittills bara gick att
    få fram i Streamlit-appen. En MCP-klient hade ingen väg att upptäcka det och
    kunde därför i praktiken inte använda de verktyg som kräver det.

    Innehåller inga personuppgifter — bara id, datumintervall och låst-status —
    och behöver därför ingen maskering. Defensiv mot saknade fält: Spiris har
    historiskt varierat i fältnamn, och ett ofullständigt år ska inte fälla
    hela listan."""
    rader: list[dict] = []
    for rå in klient.hamta_alla("/fiscalyears"):
        rader.append(
            {
                "id": str(rå.get("Id") or ""),
                "startdatum": str(rå.get("StartDate") or "")[:10],
                "slutdatum": str(rå.get("EndDate") or "")[:10],
                "last": bool(rå.get("IsLockedForAccounting", False)),
            }
        )
    # Nyast först: det året en användare nästan alltid menar.
    return sorted(rader, key=lambda r: r["startdatum"], reverse=True)


# --- Steg 3: leverantörsfakturor, order, offerter, bank, moms --------------
# Genomgående princip: FÄLTALLOWLIST, inte fältsvartlista. Order- och
# offertobjekten i Spiris bär `Persons` (ROT-personnummer),
# `HouseWorkPropertyName` (fastighetsbeteckning), fakturaadresser och
# leveransadresser. Det som aldrig hämtas kan inte läcka — därför plockas bara
# de fält verktyget faktiskt behöver, i stället för att maskera bort resten.
#
# Betalningsidentifierare (BankGiroNumber, OcrNumber, kontonummer, IBAN)
# utesluts av samma skäl som DATASKYDD anger för maskeringen av bankgiro i
# fritext: de ska aldrig behöva nå en AI.


def _motpartsnamn(namn: str, orgnr: str, privatperson: bool, vakt) -> tuple[str, bool]:
    """(visningsnamn, maskerad) enligt EXAKT samma regel som reskontratvätten:
    juridisk person i klartext, allt annat som pseudonym. Fail-closed."""
    juridisk = ar_juridisk_person(namn, orgnr)
    maskera = privatperson or (not juridisk) or vakt(namn)
    if maskera:
        return ("[Maskerad motpart]", True)
    return (namn, False)


def hamta_leverantorsfakturor(klient: _Spirisklient) -> list[dict]:
    """Leverantörsfakturor med detalj — status, belopp, datum, kreditflagga.

    Skiljer sig från `hamta_reskontra` genom att ta med ÄVEN betalda fakturor
    och fakturanummer; reskontran visar bara öppna poster. Betalningsidentifierare
    (BankGiroNumber, OcrNumber) hämtas medvetet inte."""
    orgnr_for = {
        str(s.get("Id") or ""): (s.get("CorporateIdentityNumber") or "")
        for s in klient.hamta_alla("/suppliers")
    }
    vakt = _bygg_namnvakt()
    rader: list[dict] = []
    for f in klient.hamta_alla("/supplierinvoices"):
        namn = f.get("SupplierName") or ""
        visat, maskerad = _motpartsnamn(
            namn, orgnr_for.get(str(f.get("SupplierId") or ""), ""), False, vakt
        )
        rader.append(
            {
                # `id` tillkom med Steg 6: attest och betalningsregistrering
                # adresserar fakturan via dess Spiris-id, och utan det i
                # listan har en AI-klient ingen väg att peka ut den. Tredje
                # gången samma felklass — se hamta_bankkonton (Steg 3) och
                # hamta_offerter (sandbox-fyndet 2026-08-06). Opakt id, inte
                # en personuppgift.
                "id": str(f.get("Id") or ""),
                "leverantor": visat,
                "maskerad": maskerad,
                "fakturanummer": str(f.get("InvoiceNumber") or ""),
                "fakturadatum": str(f.get("InvoiceDate") or "")[:10],
                "forfallodatum": str(f.get("DueDate") or "")[:10],
                "totalbelopp": f.get("TotalAmount"),
                "kvarvarande": f.get("RemainingAmount"),
                "kreditfaktura": bool(f.get("IsCreditInvoice", False)),
                "valuta": f.get("CurrencyCode") or "",
            }
        )
    return rader


def hamta_kundfakturor(klient: _Spirisklient) -> list[dict]:
    """Kundfakturor med detalj — fakturanummer, datum, belopp, kvarvarande och
    kreditflagga. Används för drill-down från kundregistret.

    Fältallowlist: inga kontaktuppgifter, leveransadresser, betalnings-
    identifierare (OCR, bankgiro) eller ROT/RUT-uppgifter hämtas.
    Motpartsnamnet maskeras med samma namnvakt som kundregistret."""
    kund_orgnr = {
        str(c.get("Id") or ""): (c.get("CorporateIdentityNumber") or "")
        for c in klient.hamta_alla("/customers")
    }
    vakt = _bygg_namnvakt()
    rader: list[dict] = []
    for f in klient.hamta_alla("/customerinvoices"):
        namn = f.get("CustomerName") or ""
        visat, maskerad = _motpartsnamn(
            namn,
            kund_orgnr.get(str(f.get("CustomerId") or ""), ""),
            bool(f.get("CustomerIsPrivatePerson", False)),
            vakt,
        )
        rader.append(
            {
                "id": str(f.get("Id") or ""),
                "kund": visat,
                "maskerad": maskerad,
                "fakturanummer": str(f.get("InvoiceNumber") or ""),
                "fakturadatum": str(f.get("InvoiceDate") or "")[:10],
                "forfallodatum": str(f.get("DueDate") or "")[:10],
                "totalbelopp": f.get("TotalAmount"),
                "kvarvarande": f.get("RemainingAmount"),
                "kreditfaktura": bool(f.get("IsCreditInvoice", False)),
                "valuta": f.get("CurrencyCode") or "",
            }
        )
    return rader


def _saljdokument(klient: _Spirisklient, path: str, datumfalt: str) -> list[dict]:
    """Delad mappning för order och offerter — nästan samma objektform i Spiris.

    Fältallowlist: ROT-uppgifter (`Persons`, `HouseWork*`,
    `RotReducedInvoicingOrgNumber`), fakturaadress och leveransadress plockas
    ALDRIG.

    Två skillnader som bara syntes mot riktig sandbox-data (2026-08-04):
    beloppet heter `Amount` på en order men `TotalAmount` på en offert, och
    `Number` är tomt tills Spiris tilldelar ett nummer. Båda hanteras nedan;
    ett tomt nummer är ett giltigt tillstånd, inte ett fel."""
    vakt = _bygg_namnvakt()
    rader: list[dict] = []
    for d in klient.hamta_alla(path):
        visat, maskerad = _motpartsnamn(
            d.get("CustomerName") or "", "",
            bool(d.get("CustomerIsPrivatePerson", False)), vakt,
        )
        rader.append(
            {
                # `id` tillkom efter sandbox-rökprovet 2026-08-06: `Number` är
                # None på 3 av 5 offerter/ordrar i ett riktigt bolag (Spiris
                # tilldelar nummer först i ett senare skede). Utan ett stabilt
                # id fanns ingen väg att adressera ett onumrerat dokument, och
                # Steg 5b:s åtgärder var därmed oåtkomliga för just dem.
                # Opakt Spiris-ID, inte en personuppgift — samma resonemang som
                # motpart_id i kundreskontran.
                "id": str(d.get("Id") or ""),
                "nummer": str(d.get("Number") or ""),
                "kund": visat,
                "maskerad": maskerad,
                "datum": str(d.get(datumfalt) or "")[:10],
                "belopp_exkl_moms": d.get("Amount")
                if d.get("Amount") is not None
                else d.get("TotalAmount"),
                "moms": d.get("VatAmount"),
                "status": d.get("Status"),
                "valuta": d.get("CurrencyCode") or "",
                "antal_rader": len(d.get("Rows") or []),
            }
        )
    return rader


def hamta_order(klient: _Spirisklient) -> list[dict]:
    """Kundorder. Schemat är sandbox-verifierat 2026-08-04 (testorder skapad
    för att lära fältformen — `Number`, `Amount`, `VatAmount`, `Status`)."""
    return _saljdokument(klient, "/orders", "OrderDate")


def hamta_offerter(klient: _Spirisklient) -> list[dict]:
    """Offerter. Ligger på `/quotes` i Spiris — INTE `/offers`, som ger 404
    (det är Fortnox namn på samma sak)."""
    return _saljdokument(klient, "/quotes", "QuoteDate")



def hamta_offertutkast(klient: _Spirisklient) -> list[dict]:
    vakt = _bygg_namnvakt()
    rader = []
    for d in klient.hamta_alla("/quotedrafts"):
        visat, _ = _motpartsnamn(
            d.get("CustomerName") or "", "",
            False, vakt, # No CustomerIsPrivatePerson available, assume False for mask
        )
        rader.append({
            "Id": d.get("Id"),
            "Number": d.get("Number"),
            "CustomerId": d.get("CustomerId"),
            "CustomerName": visat,
            "CustomerNumber": d.get("CustomerNumber"),
            "QuoteDate": d.get("QuoteDate"),
            "DueDate": d.get("DueDate"),
            "DeliveryDate": d.get("DeliveryDate"),
            "CurrencyCode": d.get("CurrencyCode"),
            "TotalAmount": d.get("TotalAmount"),
            "VatAmount": d.get("VatAmount"),
            "RoundingsAmount": d.get("RoundingsAmount"),
            "Status": d.get("Status"),
            "Rows": d.get("Rows", []),
            "IncludesVat": d.get("IncludesVat"),
            "IsDomestic": d.get("IsDomestic"),
            "YourReference": d.get("YourReference") or d.get("CustomerReference"),
            "OurReference": d.get("OurReference") or d.get("CompanyReference"),
        })
    return rader


def hamta_bankkonton(klient: _Spirisklient) -> list[dict]:
    """Bankkonton med saldo och kopplat BAS-konto.
    
    Id tas med (opak Spiris-identifierare) eftersom det krävs som indata till
    /banktransactions.

    Kontonummer, IBAN och BBAN hämtas INTE: de är betalningsidentifierare och
    behövs inte för att beskriva likviditeten.

    Kontonamnet maskeras med `skapa_kontonamnsmaskerare` — INTE med reskontrans
    namnvakt. Skillnaden är avsiktlig: ett bankkontonamn är en etikett som
    användaren själv sätter ("Företagskonto", men lika gärna "Konto Anna
    Andersson"), precis som ett BAS-kontonamn. Reskontrans vakt fångar bara
    KÄNDA namn, eftersom den annars hade maskerat nästan varje svenskt
    bolagsnamn — den regeln passar motparter, inte egna etiketter.
    Läckproben hittade skillnaden: ett okänt namn i titelform passerade."""
    maskera = skapa_kontonamnsmaskerare(las_namnreferens())
    konton: list[dict] = []
    for b in klient.hamta_alla("/bankaccounts"):
        saldo = b.get("Balance")
        if isinstance(saldo, dict):
            saldo = saldo.get("Balance")
        konton.append(
            {
                "id": b.get("Id"),
                "namn": maskera(b.get("Name") or ""),
                "bas_konto": str(b.get("LedgerAccountNumber") or ""),
                "saldo": saldo,
                "valuta": b.get("CurrencyCode") or "",
                "typ": b.get("BankAccountTypeDescription") or "",
            }
        )
    return sorted(konton, key=lambda k: k["bas_konto"])


def hamta_momskoder(klient: _Spirisklient) -> list[dict]:
    """Momskoder med satser. Ren referensdata utan personuppgifter."""
    koder: list[dict] = []
    for v in klient.hamta_alla("/vatcodes"):
        koder.append(
            {
                "kod": v.get("Code") or "",
                "beskrivning": v.get("Description") or "",
                "momssats": v.get("VatRate"),
            }
        )
    return sorted(koder, key=lambda k: k["kod"])


def hamta_momsrapporter(klient: _Spirisklient) -> list[dict]:
    """INLÄMNADE momsdeklarationer från /vatreports.

    Skilj detta från den BERÄKNADE momsöversikten (fpa_motor.bygg_momsoversikt):
    den här listan är vad som faktiskt deklarerats, den andra är en härledning
    ur kontosaldon."""
    rapporter: list[dict] = []
    for r in klient.hamta_alla("/vatreports"):
        rapporter.append(
            {
                "id": str(r.get("Id") or ""),
                "period_start": str(r.get("StartDate") or "")[:10],
                "period_slut": str(r.get("EndDate") or "")[:10],
                "belopp": r.get("Amount") or r.get("TotalAmount"),
                "status": r.get("Status"),
            }
        )
    return rapporter


def hamta_artiklar(klient: _Spirisklient) -> list[dict]:
    """Artikelregistret, med MASKERADE artikelnamn och det BAS-konto varje
    artikel postar till.

    Kontokopplingen är det som gör listan användbar: en kundfakturarad har
    inget eget kontofält i Spiris (se `hitta_artikel_for_konto`), utan
    konteringen följer av artikelns kodning. Utan konto i listan kan varken en
    människa eller en assistent avgöra vilken artikel som är rätt för en viss
    intäkt.

    Artikelnamn är fritext som bolaget själv sätter ("Konsult Anna Andersson"
    är fullt möjligt), alltså samma PII-risk som kontonamn — därför samma
    maskering med EN delad tokengenerator för hela registret.

    Defensiv mot fältnamn: Spiris har varierat mellan `NetPrice` och
    `UnitPrice`, och en artikel utan pris ska inte fälla hela listan."""
    kodning_till_konto: dict[str, str] = {}
    for kodning in klient.hamta_alla("/articleaccountcodings"):
        konto = (
            kodning.get("DomesticSalesSubjectToVatAccountNumber")
            or kodning.get("DomesticSalesSubjectToReversedConstructionVatAccountNumber")
        )
        if kodning.get("Id") is not None and konto is not None:
            kodning_till_konto[str(kodning["Id"])] = str(konto)

    maskera = skapa_kontonamnsmaskerare(las_namnreferens())
    artiklar: list[dict] = []
    for rå in klient.hamta_alla("/articles"):
        pris = rå.get("NetPrice")
        if pris is None:
            pris = rå.get("UnitPrice")
        artiklar.append(
            {
                # `id` krävs av Steg 7:s masterdata-ändringar. FJÄRDE gången
                # samma felklass, efter hamta_bankkonton (Steg 3),
                # hamta_offerter (sandbox 2026-08-06) och
                # hamta_leverantorsfakturor (Steg 6): ett läsverktyg som inte
                # exponerar sin identifierare gör objektet oadresserbart, och
                # inget test fångar det.
                "id": str(rå.get("Id") or ""),
                "artikelnr": str(rå.get("Number") or ""),
                "namn": maskera(rå.get("Name") or ""),
                "pris": pris,
                "enhet": rå.get("UnitName") or rå.get("Unit") or "",
                "konto": kodning_till_konto.get(str(rå.get("CodingId") or ""), ""),
                "aktiv": bool(rå.get("Active", True)),
            }
        )
    return sorted(artiklar, key=lambda a: a["artikelnr"])


def hamta_foretagsinfo(klient: _Spirisklient) -> dict:
    """Företagsuppgifter från /companysettings.

    Företagsnamnet maskeras: en enskild firma kan heta som en fysisk person
    ("Anna Andersson AB" är ett verifierat fall från reskontratvätten), och
    namnet går härifrån rakt till en extern AI."""
    rå = klient.hamta_en("/companysettings")
    maskera = skapa_kontonamnsmaskerare(las_namnreferens())
    return {
        "namn": maskera(rå.get("Name") or ""),
        "organisationsnummer": rå.get("CorporateIdentityNumber") or "",
        "valuta": rå.get("CurrencyCode") or "",
        "momsregistrerad": bool(rå.get("ActivatedModules") or rå.get("VatNumber")),
    }


def hamta_kontoplan(klient: _Spirisklient, räkenskapsår_id: str) -> list[dict]:
    """Kontoplanen för ett räkenskapsår, med MASKERADE kontonamn.

    EN delad tokengenerator för hela kontoplanen: `maskera_kontonamn` skapar en
    ny generator per anrop, så räknaren hade nollställts för varje konto och tre
    olika personer blivit PERSON_1 allihop."""
    maskera = skapa_kontonamnsmaskerare(las_namnreferens())
    konton: list[dict] = []
    for rå in klient.hamta_alla(f"/accounts/{räkenskapsår_id}"):
        konto = mappa_konto(rå)
        konton.append(
            {
                "kontonr": konto.kontonr,
                "kontonamn": maskera(konto.namn),
                "kontotyp": konto.typ,
                "aktivt": bool(rå.get("Active", True)),
            }
        )
    return sorted(konton, key=lambda k: k["kontonr"])


def hamta_reskontra(klient: _Spirisklient) -> list[Leverantorspost]:
    """Hämtar leverantörsreskontran (/suppliers + /supplierinvoices), joinar
    och filtrerar via bygg_reskontra_rader, och kör resultatet genom
    GDPR-tvättmaskinen. Kräver ea:purchase-scope."""
    suppliers = klient.hamta_alla("/suppliers")
    fakturor = klient.hamta_alla("/supplierinvoices")
    return tvatta_leverantorsreskontra(
        bygg_reskontra_rader(suppliers, fakturor),
        ar_kanslig_namn=_bygg_namnvakt(),
    )


# --- Kundreskontra (Fas D) --------------------------------------------------

# Kund-PaymentStatus (CustomerInvoiceApi) — EGET enum, skilt från leverantörer.
_KUND_PAYMENT_STATUS_TEXT: dict[int, str] = {0: "Betald", 1: "Obetald", 2: "Förfallen"}


def _kund_betalstatus_text(kod) -> str:
    return _KUND_PAYMENT_STATUS_TEXT.get(kod, f"Status {kod}")


def bygg_kundreskontra_rader(rå_customers: list[dict], rå_fakturor: list[dict]) -> list[dict]:
    """Joinar kundfakturor med kunder (för org.nr) och filtrerar till ÖPPNA
    poster (RemainingAmount != 0, matchar huvudbok 1510). Sätter privatperson
    från CustomerIsPrivatePerson/IsPrivatePerson — en extra fail-closed-signal
    för B2C-kunder som tvättmaskinen respekterar.

    forfallodatum + motpart_id (Spiris CustomerId, redan använd som join-
    nyckel ovan — bara exponerad i utdatat här) krävs av
    fpa_motor.bygg_likviditetsprognos: förfallodatum för dag-för-dag-inflödet,
    motpart_id för att slå upp kundens historiska betalbeteende. Samma
    fail-closed-resonemang som leverantörssidan (se bygg_reskontra_rader) för
    varför förfallodatum indexeras direkt i stället för .get. Sandbox-
    verifierat (live, 2026-07-19): "DueDate" finns på /customerinvoices,
    format "YYYY-MM-DD".

    Se bygg_kundbetalhistorik_rader nedan för PaymentDate-kopplingen (Fas 6b):
    en SEPARAT extraktion ur samma /customerinvoices-svar, eftersom den
    filtrerar till motsatsen (bara BETALDA poster, inte öppna)."""
    customer_map = {c.get("Id"): c for c in rå_customers}
    rader: list[dict] = []
    for faktura in rå_fakturor:
        belopp = faktura.get("RemainingAmount", Decimal("0"))
        if belopp == 0:
            continue
        customer = customer_map.get(faktura.get("CustomerId"), {})
        rader.append(
            {
                "namn": faktura.get("CustomerName") or customer.get("Name") or "",
                "orgnr": customer.get("CorporateIdentityNumber") or "",
                "belopp": belopp,
                "betalstatus": _kund_betalstatus_text(faktura.get("PaymentStatus")),
                "privatperson": bool(
                    faktura.get("CustomerIsPrivatePerson") or customer.get("IsPrivatePerson")
                ),
                "forfallodatum": date.fromisoformat(faktura["DueDate"][:10]),
                "motpart_id": faktura.get("CustomerId") or "",
            }
        )
    return rader


def hamta_kundreskontra(klient: _Spirisklient) -> list[Kundpost]:
    """Hämtar kundreskontran (/customers + /customerinvoices), joinar och
    filtrerar via bygg_kundreskontra_rader, och kör genom GDPR-tvättmaskinen.
    Kräver ea:sales-scope (som redan begärs)."""
    customers = klient.hamta_alla("/customers")
    fakturor = klient.hamta_alla("/customerinvoices")
    return tvatta_kundreskontra(
        bygg_kundreskontra_rader(customers, fakturor),
        ar_kanslig_namn=_bygg_namnvakt(),
    )


# --- Kundbetalhistorik (Fas 6b): PaymentDate -> fpa_motor.berakna_kundbetalbeteende

def bygg_kundbetalhistorik_rader(rå_fakturor: list[dict]) -> list[dict]:
    """Extraherar betalhistorik ur RÅA kundfakturor (/customerinvoices),
    filtrerad och normaliserad för fpa_motor.berakna_kundbetalbeteende:
    {"motpart_id": str, "forfallodatum": date, "betaldatum": date}.

    Filtret på PaymentStatus == "Betald" är INTE kosmetiskt: sandbox-proben
    (2026-07-19) visade att PaymentDate kan vara satt på en faktura som
    FORTFARANDE är öppen (RemainingAmount != 0, PaymentStatus="Förfallen") —
    en delbetalning, inte en fullbetalning. En betalbeteende-profil byggd på
    delbetalningsdatum hade gett en systematiskt FÖR TIDIG bild av när kunden
    faktiskt gör upp fakturan — därför bara PaymentStatus == "Betald", inte
    "PaymentDate finns".

    Ingen tvätt av namn här (bara motpart_id, ett opakt Spiris-ID som inte är
    en personuppgift) — bara datumnormalisering, se
    reskontra_tvatt.normalisera_spiris_datum. Kräver INTE /customers: hela
    joinen mot en kunds identitet sker via motpart_id, som redan finns direkt
    på fakturaraden."""
    rader: list[dict] = []
    for faktura in rå_fakturor:
        if _kund_betalstatus_text(faktura.get("PaymentStatus")) != "Betald":
            continue
        rå_betaldatum = faktura.get("PaymentDate")
        if not rå_betaldatum:
            continue  # betald men inget registrerat betaldatum -> går inte att räkna
        rader.append(
            {
                "motpart_id": faktura.get("CustomerId") or "",
                "forfallodatum": normalisera_spiris_datum(faktura["DueDate"]),
                "betaldatum": normalisera_spiris_datum(rå_betaldatum),
            }
        )
    return rader


def hamta_kundbetalhistorik(klient: _Spirisklient) -> list[dict]:
    """Hämtar kundfakturornas betalhistorik (/customerinvoices) och filtrerar
    till bara betalda poster via bygg_kundbetalhistorik_rader — redo som
    indata till fpa_motor.berakna_kundbetalbeteende. Kräver ea:sales-scope
    (samma som hamta_kundreskontra).

    Egen, oberoende hämtning av /customerinvoices (delar den INTE med
    hamta_kundreskontra): de två filtrerar till varandras motsatser (öppna
    kontra betalda poster) ur samma råa svar — att bryta ut hämtningen till
    ett tredje, delat lager bara för att spara ETT nätverksanrop är inte värt
    komplexiteten i ett lokalt verktyg utan prestandakrav."""
    fakturor = klient.hamta_alla("/customerinvoices")
    return bygg_kundbetalhistorik_rader(fakturor)


# --- Konteringsmotor + skriv-funktioner (Fas 7: skapa_kundfaktura HITL) -----
#
# FÖRSTA skriv-kapabla funktionerna i den här modulen — allt annat i filen är
# läsning. Annan riskkategori: en lyckad POST skapar ett RIKTIGT
# affärsdokument i ett levande Spiris-bolag (kan mejlas till en riktig kund,
# påverka riktig momsredovisning). Därför:
#   - skapa_kund/skapa_kundfaktura postar ALDRIG som en direkt följd av en
#     analys eller ett AI-förslag — de anropas bara efter ett explicit
#     mänskligt "Godkänn och Skicka" (se app_vy.py:s utkasts-/gransknings-
#     funktioner och app.py:s knapp).
#   - Konteringsmotorn (foreslå_konto) är fail-closed: en fakturatyp/
#     kategori-kombination som INTE finns i tabellen höjer ValueError,
#     gissas ALDRIG fram — en felaktig kontering är en riktig postad
#     faktura, inte en lokalt rättbar analys.
#   - Alla POST-anrop loggas (utan personnummer/kundnamn i klartext — bara
#     kontonr, radantal och Spiris-ID:n) för spårbarhet.

FAKTURATYP_BYGGMOMS = "byggmoms"
FAKTURATYP_JURIDISK_PERSON = "juridisk_person"
FAKTURATYP_FYSISK_PERSON_UTAN_ROT = "fysisk_person_utan_rot"
FAKTURATYP_FYSISK_PERSON_MED_ROT = "fysisk_person_med_rot"

FAKTURATYPER: tuple[str, ...] = (
    FAKTURATYP_BYGGMOMS,
    FAKTURATYP_JURIDISK_PERSON,
    FAKTURATYP_FYSISK_PERSON_UTAN_ROT,
    FAKTURATYP_FYSISK_PERSON_MED_ROT,
)

KONTOKATEGORI_ARBETE = "arbete"
KONTOKATEGORI_MATERIEL = "materiel"

# Explicit, hårdkodad konteringstabell (fakturatyp, kategori) -> BAS-kontonr.
# En kombination som INTE finns här ska ALDRIG gissas fram — se foreslå_konto.
#
# ⚠ VERIFIERAT TRASIG BYGGMOMSVÄG (sandbox-skrivprov 2026-08-06).
# Att välja konto 3231 ger INTE omvänd skattskyldighet. Kontot väljer bara
# artikelkodning, och 3041 och 3231 löses ut till SAMMA artikel (kodningen
# "Tjänster 25% moms" bär båda kontona). Spiris avgör momsen på annat sätt:
#
#   omvänd skattskyldighet kräver BÅDA
#     1. kunden flaggad ReverseChargeOnConstructionServices = True, OCH
#     2. fakturaraden med ReversedConstructionServicesVatFree = True
#
#   Uppmätt: flaggad kund + radflagga True -> moms 0,00. Alla andra
#   kombinationer -> moms 250,00 på 1000 kr. En oflaggad kund med radflaggan
#   True AVVISAS med HTTP 400.
#
# Följden i dag: en faktura av typen "byggmoms" debiterar 25 % moms som inte
# ska debiteras. Se RISKREGISTER R-15. Tabellen nedan är alltså riktig som
# KONTERING men otillräcklig som momshantering.
#
# Reglerna är affärsbeslut från Arkitekten (Stefan), inte AI-inferens:
#   - Byggmoms/omvänd skattskyldighet: allt (arbete OCH material) på 3231.
#   - Juridisk person (vanlig moms): arbete 3041, material 3051.
#   - Fysisk person utan ROT: samma konton som juridisk person (3041/3051) —
#     ROT-fallet skiljer sig INTE i kontonr, bara i att fakturan flaggas
#     (se kraver_rot_flaggning/bygg_rot_uppgifter).
#   - Fysisk person med ROT: samma konton (3041/3051) + ROT-flaggning.
_KONTERINGSTABELL: dict[tuple[str, str], str] = {
    (FAKTURATYP_BYGGMOMS, KONTOKATEGORI_ARBETE): "3231",
    (FAKTURATYP_BYGGMOMS, KONTOKATEGORI_MATERIEL): "3231",
    (FAKTURATYP_JURIDISK_PERSON, KONTOKATEGORI_ARBETE): "3041",
    (FAKTURATYP_JURIDISK_PERSON, KONTOKATEGORI_MATERIEL): "3051",
    (FAKTURATYP_FYSISK_PERSON_UTAN_ROT, KONTOKATEGORI_ARBETE): "3041",
    (FAKTURATYP_FYSISK_PERSON_UTAN_ROT, KONTOKATEGORI_MATERIEL): "3051",
    (FAKTURATYP_FYSISK_PERSON_MED_ROT, KONTOKATEGORI_ARBETE): "3041",
    (FAKTURATYP_FYSISK_PERSON_MED_ROT, KONTOKATEGORI_MATERIEL): "3051",
}

_ROT_FAKTURATYPER = frozenset({FAKTURATYP_FYSISK_PERSON_MED_ROT})

# De BAS-konton som betyder omvänd skattskyldighet, HÄRLEDDA ur tabellen ovan
# i stället för hårdkodade. Ändras konteringstabellen följer den här mängden
# med — annars hade en ändring av byggmomskontot tyst kopplat bort
# momshanteringen och återskapat R-15.
BYGGMOMSKONTON: frozenset[str] = frozenset(
    konto for (typ, _kategori), konto in _KONTERINGSTABELL.items()
    if typ == FAKTURATYP_BYGGMOMS
)


def _kraver_byggmoms(fakturarader: list[dict]) -> bool:
    """True om någon rad konterats till ett byggmomskonto.

    Kontot är den enda signal om omvänd skattskyldighet som finns i BÅDA
    flödena: appens chattväg bär `fakturatyp` explicit, men MCP-vägen
    (forbered_kundfaktura) tar bara konto per rad. Att härleda ur kontot
    fångar därför båda — och kontot är dessutom det människan faktiskt
    granskar och kan rätta i utkastvyn."""
    return any(str(rad.get("kontonr") or "") in BYGGMOMSKONTON for rad in fakturarader)


def foreslå_konto(fakturatyp: str, kategori: str) -> str:
    """Slår upp BAS-kontonr för (fakturatyp, kategori) ur den explicita
    konteringstabellen ovan. Fail-closed: en okänd kombination höjer
    ValueError — kontering GISSAS ALDRIG fram. Detta är AI-FÖRSLAGET som
    visas för mänsklig granskning (app_vy.bygg_fakturautkast), inte den
    slutgiltiga konteringen — användaren kan alltid rätta den innan
    'Godkänn och Skicka'."""
    nyckel = (fakturatyp, kategori)
    if nyckel not in _KONTERINGSTABELL:
        raise ValueError(f"Okänd fakturatyp/kategori-kombination: {nyckel!r}")
    return _KONTERINGSTABELL[nyckel]


def kraver_rot_flaggning(fakturatyp: str) -> bool:
    """True om fakturatypen (fysisk person MED rotavdrag) kräver att
    arbetskostnaden flaggas för ROT i payloaden. Fail-closed på okänd typ —
    samma princip som foreslå_konto."""
    if fakturatyp not in FAKTURATYPER:
        raise ValueError(f"Okänd fakturatyp: {fakturatyp!r}")
    return fakturatyp in _ROT_FAKTURATYPER


# --- Live sandbox-facit (POST-verifierat 2026-07-19) -------------------------
#
# En kundfakturarad har INGET AccountNumber-fält alls — bekräftat både i
# Vismas OpenAPI-schema (CustomerInvoiceRowApi saknar helt ett kontofält) och
# genom en riktig POST mot sandboxen. Kontering sker i stället via ArticleId:
# raden pekar på en Article, vars CodingId pekar på en ArticleAccountCoding
# som bär FLERA möjliga kontonummer (ett för normal inhemsk moms, ett för
# byggmoms/omvänd skattskyldighet) — Spiris väljer rätt ett automatiskt.
# Kontering sker alltså på KODNINGSNIVÅ, inte per rad. Se
# hitta_artikel_for_konto/losa_artikel_ider_for_fakturarader nedan.
#
# Sandbox-bekräftade enum-värden (från Vismas OpenAPI-schema OCH en lyckad
# live-POST, 201 Created):
ROT_TYP_NORMAL = 0
ROT_TYP_ROT = 1
ROT_TYP_RUT = 2

ROT_FASTIGHETSTYP_LAGENHET = 1
ROT_FASTIGHETSTYP_FASTIGHET = 2

# WorkCostType (RADNIVÅ, inte invoice-nivå) — en av ~20 Rot/Rut-underkategorier
# i Vismas schema. RotConstructionWork (byggarbete) är den relevanta för
# "fysisk_person_med_rot"-scenariot i den här kodbasen.
ARBETSTYP_ROT_BYGGARBETE = 1


def bygg_rot_uppgifter(
    *,
    fastighetsbeteckning: str,
    personnummer_fastighetsagare: str,
    personer: list[dict[str, Any]],
    rot_typ: int = ROT_TYP_ROT,
    fastighetstyp: int = ROT_FASTIGHETSTYP_FASTIGHET,
    rot_belopp: Decimal | None = None,
) -> dict[str, Any]:
    """Bygger ROT-fälten för en /customerinvoices-POST-kropp.

    SANDBOX-BEKRÄFTAT (live POST mot sandboxen, 2026-07-19 — inte bara
    OpenAPI-schemat):
    - rot_typ: 0=Normal, 1=Rot, 2=Rut (default Rot, matchar
      "fysisk_person_med_rot"). fastighetstyp: 1=Lägenhet, 2=Fastighet
      (default Fastighet).
    - personnummer_fastighetsagare MÅSTE vara max 11 tecken — KORT
      personnummerformat ("ÅÅMMDD-XXXX"). Ett fullständigt personnummer med
      sekelprefix (13 tecken) AVVISAS av Spiris (bekräftat via ett faktiskt
      400-svar: "must be a string with a maximum length of 11").
    - "personer" (Vismas "Persons": [{"Ssn": str, "Amount": Decimal}, ...])
      är OBLIGATORISKT för alla ROT/RUT/grön teknik-fakturor.
      personnummer_fastighetsagare ENSAMT räcker INTE — bekräftat via ett
      faktiskt 400-svar ("Persons are required for domestic services...")
      innan detta fält lades till.
    - RotReducedInvoicingPercent och RotReducedInvoicingAutomaticDistribution
      FINNS INTE med här: de är READ-ONLY i Vismas schema (bekräftat) — att
      försöka sätta dem är meningslöst. rot_belopp (RotReducedInvoicingAmount)
      är VALFRITT: utelämnas det räknar Spiris ut avdraget automatiskt
      ("Default is automatic tax reduction calculation" — Vismas egen
      schembeskrivning).

    OFULLSTÄNDIGT VERIFIERAT: Spiris personnummer-validering i "personer"
    gick INTE att slutverifiera i sandboxen — två syntetiska testpersonnummer
    (inkl. projektets egen Luhn-giltiga GILTIGT_PERSONNUMMER_KORT) avvisades
    båda med SocialSecurityNumberIsInvalidException, och ingen
    privatperson-testkund fanns i sandboxen att låna ett riktigt personnummer
    från. Ett ROT-flöde måste alltså testas med ett FAKTISKT giltigt
    personnummer innan skarp användning — Luhn-giltigt är inte tillräckligt
    för Spiris egen validering."""
    if len(personnummer_fastighetsagare) > 11:
        raise ValueError(
            "personnummer_fastighetsagare måste vara max 11 tecken (kort "
            "format ÅÅMMDD-XXXX) — Spiris avvisar ett fullständigt "
            "personnummer med sekelprefix."
        )
    uppgifter: dict[str, Any] = {
        "RotReducedInvoicingType": rot_typ,
        "RotPropertyType": fastighetstyp,
        "RotReducedInvoicingPropertyName": fastighetsbeteckning,
        "RotReducedInvoicingOrgNumber": personnummer_fastighetsagare,
        "Persons": personer,
    }
    if rot_belopp is not None:
        uppgifter["RotReducedInvoicingAmount"] = rot_belopp
    return uppgifter


def hitta_artikel_for_konto(klient: _Spirisklient, kontonr: str) -> str:
    """Slår upp en BEFINTLIG artikel i Spiris vars kontokodning postar till
    det angivna BAS-kontonumret, och returnerar dess ArticleId.

    En kundfakturarad har inget eget kontofält (se modulkommentaren ovan) —
    det här är alltså det RIKTIGA konteringssteget, live mot Spiris, som
    ersätter det ursprungliga (felaktiga) antagandet att ett kontonr kunde
    skickas direkt på raden.

    Fail-closed: hittas ingen artikel kopplad till en kodning med detta
    kontonummer höjs ValueError. Skapar ALDRIG en ny artikel eller
    kontokodning själv — det är kontoplans-administration, ett beslut för en
    människa i Spiris webbgränssnitt, inte något den här funktionen gissar
    sig till."""
    kodnings_id_for_konto = {
        kodning["Id"]
        for kodning in klient.hamta_alla("/articleaccountcodings")
        if str(kodning.get("DomesticSalesSubjectToVatAccountNumber")) == kontonr
        or str(kodning.get("DomesticSalesSubjectToReversedConstructionVatAccountNumber")) == kontonr
    }
    if not kodnings_id_for_konto:
        raise ValueError(f"Ingen kontokodning i Spiris postar till konto {kontonr!r}.")

    for artikel in klient.hamta_alla("/articles"):
        if artikel.get("CodingId") in kodnings_id_for_konto:
            return artikel["Id"]
    raise ValueError(f"Ingen artikel i Spiris är kopplad till konto {kontonr!r}.")


def losa_artikel_ider_for_fakturarader(
    klient: _Spirisklient, fakturarader: list[dict]
) -> list[dict]:
    """Slår upp artikel_id för varje GRANSKAD fakturarad via dess (mänskligt
    godkända) kontonr, med hitta_artikel_for_konto. Sista steget innan
    bygg_kundfaktura_payload — separat från app_vy.py:s utkastbyggande,
    eftersom DEN funktionen medvetet är ren (ingen I/O), medan uppslaget
    här kräver en live klient.

    Cachear uppslag inom anropet (flera rader delar ofta samma kontonr) —
    ingen prestandarisk i det lokala verktyget med en handfull rader per
    faktura."""
    konto_till_artikel: dict[str, str] = {}
    resultat: list[dict] = []
    for rad in fakturarader:
        kontonr = rad["kontonr"]
        if kontonr not in konto_till_artikel:
            konto_till_artikel[kontonr] = hitta_artikel_for_konto(klient, kontonr)
        resultat.append({**rad, "artikel_id": konto_till_artikel[kontonr]})
    return resultat


def bygg_kundfaktura_payload(
    kund_id: str,
    fakturarader: list[dict],
    faktureringsdatum: str,
    forfallodatum: str,
    rot_uppgifter: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Bygger en Visma-formad /customerinvoices-POST-kropp ur en lista
    GRANSKADE, ARTIKEL-LÖSTA fakturarader (se losa_artikel_ider_for_
    fakturarader) — ren mappning, ingen egen kontering eller I/O här.

    fakturarader: [{"beskrivning": str, "belopp": Decimal,
                     "antal": Decimal (valfri, def. 1), "artikel_id": str,
                     "arbetstyp": int (valfri, ARBETSTYP_ROT_*),
                     "arbetstimmar": Decimal (KRÄVS av Spiris om arbetstyp
                     är satt — se nedan)}]

    SANDBOX-BEKRÄFTAT (live POST, 201 Created, 2026-07-19): CustomerId,
    InvoiceDate, DueDate ("ÅÅÅÅ-MM-DD" räcker, ingen tidskomponent behövs),
    Rows[].ArticleId/Text/UnitPrice/Quantity. En rad med "arbetstyp" satt
    MÅSTE också ha "arbetstimmar" >= 1 — Spiris avvisade annars
    (bekräftat via ett faktiskt 400-svar: "Cannot add rows with labour
    article, work type set, but with work hours < 1.00")."""
    rows: list[dict[str, Any]] = []
    for rad in fakturarader:
        artikel_id = rad.get("artikel_id")
        if not artikel_id:
            raise ValueError(f"Fakturarad saknar artikel_id (ej artikel-löst): {rad!r}")
        row: dict[str, Any] = {
            "ArticleId": artikel_id,
            "Text": rad["beskrivning"],
            "UnitPrice": rad["belopp"],
            "Quantity": rad.get("antal", Decimal("1")),
        }
        if rad.get("arbetstyp") is not None:
            if not rad.get("arbetstimmar"):
                raise ValueError(
                    f"Fakturarad med arbetstyp kräver arbetstimmar >= 1 "
                    f"(Spiris kräver WorkHours): {rad!r}"
                )
            row["WorkCostType"] = rad["arbetstyp"]
            row["WorkHours"] = rad["arbetstimmar"]
        rows.append(row)

    payload: dict[str, Any] = {
        "CustomerId": kund_id,
        "InvoiceDate": faktureringsdatum,
        "DueDate": forfallodatum,
        "Rows": rows,
    }
    if rot_uppgifter:
        payload.update(rot_uppgifter)
    return payload


def _artikel_ider_i_payload(faktura_data: dict) -> list[str]:
    """Säker logg-sammanfattning: bara artikel-ID:n, aldrig kundnamn/
    personnummer/belopp i klartext i loggen."""
    return sorted({str(rad.get("ArticleId")) for rad in faktura_data.get("Rows", [])})


def skapa_kund(klient: _Spirisklient, kund_data: dict) -> dict:
    """POSTar en ny kund till Spiris (/customers). kund_data är en redan
    validerad payload (Name, CorporateIdentityNumber, IsPrivatePerson, ...)
    som anroparen byggt — ingen egen validering eller kontering här, bara
    sändningen. Kräver ea:sales-scope.

    Postar ALDRIG av sig själv som en följd av en analys — anropa den bara
    efter ett explicit mänskligt godkännande (se app_vy.py/app.py). Loggat
    (utan personuppgifter — bara Spiris-ID) vid både lyckat och misslyckat
    anrop, för spårbarhet."""
    try:
        skapad = klient.skicka("/customers", kund_data)
    except SpirisKlientFel:
        _logger.error("Kunde inte skapa kund i Spiris.")
        raise
    _logger.info("Kund skapad i Spiris (Id=%s).", skapad.get("Id"))
    return skapad


def skapa_kundfaktura(klient: _Spirisklient, faktura_data: dict) -> dict:
    """POSTar en ny kundfaktura till Spiris (/customerinvoices). faktura_data
    är en redan validerad, MÄNSKLIGT GODKÄND payload — se
    bygg_kundfaktura_payload. Ingen egen kontering eller validering här,
    bara sändningen. Kräver ea:sales-scope.

    Postar ALDRIG av sig själv som en följd av en analys — anropa den bara
    efter ett explicit mänskligt "Godkänn och Skicka" (se app_vy.py/app.py).
    Loggat (utan kundnamn/personnummer/belopp — bara artikel-ID, radantal
    och Spiris-ID) vid både lyckat och misslyckat anrop, för spårbarhet."""
    try:
        skapad = klient.skicka("/customerinvoices", faktura_data)
    except SpirisKlientFel:
        _logger.error(
            "Kunde inte skapa kundfaktura i Spiris (%d rader, artiklar: %s).",
            len(faktura_data.get("Rows", [])),
            _artikel_ider_i_payload(faktura_data),
        )
        raise
    _logger.info(
        "Kundfaktura skapad i Spiris (Id=%s, %d rader, artiklar: %s).",
        skapad.get("Id"),
        len(faktura_data.get("Rows", [])),
        _artikel_ider_i_payload(faktura_data),
    )
    return skapad

_FAKTURATYP_ETIKETTER: dict[str, str] = {
    FAKTURATYP_JURIDISK_PERSON: 'Juridisk person (vanlig moms)',
    FAKTURATYP_FYSISK_PERSON_UTAN_ROT: 'Fysisk person (utan ROT)',
    FAKTURATYP_FYSISK_PERSON_MED_ROT: 'Fysisk person (med ROT)',
    FAKTURATYP_BYGGMOMS: 'Byggmoms (omvänd skattskyldighet)',
}


def hamta_kunder(klient: _Spirisklient, *, filter: str | None = None, select: list[str] | None = None, orderby: str | None = None, pagesize: int | None = None) -> list[dict]:
    """Kundregistret med maskerade motpartsnamn. Juridiska personer står i
    klartext, privatpersoner och okända namn som stabila pseudonymer.
    Innehåller varken kontaktuppgifter, adresser, organisationsnummer eller
    betalningsuppgifter; de hämtas aldrig. Fältallowlistad.
    """
    vakt = _bygg_namnvakt()
    rader: list[dict] = []
    for rå in klient.hamta_alla("/customers", filter=filter, select=select, orderby=orderby, pagesize=pagesize):
        visat, maskerad = _motpartsnamn(
            rå["Name"],
            rå.get("CorporateIdentityNumber") or "",
            bool(rå.get("IsPrivatePerson", False)),
            vakt,
        )
        rader.append({
            "id": rå.get("Id"),
            "kundnummer": rå.get("CustomerNumber"),
            "namn": visat,
            "maskerad": maskerad,
            "privatperson": bool(rå.get("IsPrivatePerson", False)),
            "valuta": rå.get("CurrencyCode") or "",
            "aktiv": bool(rå.get("IsActive", True)),
            "land": rå.get("InvoiceCountryCode") or "",
            "betalningsvillkor_id": rå.get("TermsOfPaymentId"),
            "obetalt_belopp": rå.get("UnpaidInvoicesAmount"),
        })
    return rader


def hamta_leverantorer(klient: _Spirisklient, *, filter: str | None = None, select: list[str] | None = None, orderby: str | None = None, pagesize: int | None = None) -> list[dict]:
    """Leverantörsregistret med maskerade motpartsnamn. Juridiska personer står i
    klartext, okända namn som stabila pseudonymer. Innehåller varken
    kontaktuppgifter, adresser, organisationsnummer eller betalningsidentifierare
    (bankkonto, IBAN, bankgiro, plusgiro); de hämtas aldrig. Fältallowlistad.
    """
    vakt = _bygg_namnvakt()
    rader: list[dict] = []
    for rå in klient.hamta_alla("/suppliers", filter=filter, select=select, orderby=orderby, pagesize=pagesize):
        visat, maskerad = _motpartsnamn(
            rå["Name"],
            rå.get("CorporateIdentityNumber") or "",
            False,
            vakt,
        )
        rader.append({
            "id": rå.get("Id"),
            "leverantorsnummer": rå.get("SupplierNumber"),
            "namn": visat,
            "maskerad": maskerad,
            "valuta": rå.get("CurrencyCode") or "",
            "aktiv": bool(rå.get("IsActive", True)),
            "land": rå.get("CountryCode") or "",
            "betalningsvillkor_id": rå.get("TermsOfPaymentId"),
            "obetalt_belopp": rå.get("UnpaidInvoicesAmount"),
        })
    return rader


_PROJEKTSTATUS: dict[int, str] = {1: "Pågående", 2: "Avslutat"}

def hamta_projekt(klient: _Spirisklient, *, filter: str | None = None, select: list[str] | None = None, orderby: str | None = None, pagesize: int | None = None) -> list[dict]:
    """Projektregistret med dubbla maskeringsregler: projektnamnet betraktas
    som en egen etikett och maskeras med en generell etikettmaskerare,
    medan eventuell kund betraktas som en motpart. Exkluderar Notes.
    """
    etikett_maskerare = skapa_kontonamnsmaskerare(las_namnreferens())
    motpart_vakt = _bygg_namnvakt()
    
    rader: list[dict] = []
    for rå in klient.hamta_alla("/projects", filter=filter, select=select, orderby=orderby, pagesize=pagesize):
        kund_namn = rå.get("CustomerName") or ""
        if kund_namn:
            visat_kund, maskerad_kund = _motpartsnamn(kund_namn, "", False, motpart_vakt)
        else:
            visat_kund, maskerad_kund = "", False
            
        status_kod = rå.get("Status")
        if status_kod in _PROJEKTSTATUS:
            status_str = _PROJEKTSTATUS[status_kod]
        else:
            status_str = f"Status {status_kod}"
            
        rader.append({
            "id": rå.get("Id"),
            "nummer": rå.get("Number"),
            "namn": etikett_maskerare(rå["Name"]),
            "startdatum": str(rå.get("StartDate") or "")[:10] if rå.get("StartDate") else "",
            "slutdatum": str(rå.get("EndDate") or "")[:10] if rå.get("EndDate") else "",
            "kund": visat_kund,
            "maskerad": maskerad_kund,
            "status": status_str,
        })
    return rader


def hamta_kostnadsstallen(klient: _Spirisklient, *, filter: str | None = None, select: list[str] | None = None, orderby: str | None = None, pagesize: int | None = None) -> list[dict]:
    """Kostnadsställen och dess poster, med etikettmaskering.
    Delar en och samma maskerare så att samma namn ger samma pseudonym."""
    etikett_maskerare = skapa_kontonamnsmaskerare(las_namnreferens())
    
    rader: list[dict] = []
    for rå in klient.hamta_alla("/costcenters", filter=filter, select=select, orderby=orderby, pagesize=pagesize):
        poster_rå = rå.get("Items") or []
        poster_ut = []
        for p in poster_rå:
            poster_ut.append({
                "id": p.get("Id"),
                "namn": etikett_maskerare(p.get("Name") or ""),
                "kortnamn": etikett_maskerare(p.get("ShortName") or ""),
                "aktiv": bool(p.get("IsActive", True)),
            })
            
        rader.append({
            "id": rå.get("Id"),
            "nummer": rå.get("Number"),
            "namn": etikett_maskerare(rå["Name"]),
            "aktiv": bool(rå.get("IsActive", True)),
            "poster": poster_ut,
        })
    return rader


def hamta_kontosaldo(klient: _Spirisklient, kontonr: str, per_datum: str, *, filter: str | None = None, select: list[str] | None = None, orderby: str | None = None, pagesize: int | None = None) -> dict:
    """Enskilt kontosaldo per datum. Returnerar ett dict (inte lista).
    Kontonamn maskeras med etikettmaskerare (egen etikett, inte motpart)."""
    etikett_maskerare = skapa_kontonamnsmaskerare(las_namnreferens())
    params = {}
    if filter: params["$filter"] = filter
    if select: params["$select"] = ",".join(select)
    if orderby: params["$orderby"] = orderby
    if pagesize: params["$pagesize"] = str(pagesize)
    rå = klient.hamta_en(f"/accountbalances/{kontonr}/{per_datum}", params=params or None)
    
    return {
        "kontonr": str(rå.get("AccountNumber", "")),
        "kontonamn": etikett_maskerare(rå.get("AccountName") or ""),
        "saldo": rå.get("Balance"),
        "kontotyp": spiris_typ_till_ktyp(rå.get("AccountType")),
    }


def hamta_referensdata(klient: _Spirisklient, typ: str, *, filter: str | None = None, select: list[str] | None = None, orderby: str | None = None, pagesize: int | None = None) -> list[dict]:
    """Dynamisk hämtning av referenslistor. Bara de entiteter vi explicit känner till."""
    giltiga = {
        "artiklar": "/articles",
        "kunder": "/customers",
        "leverantorer": "/suppliers",
        "projekt": "/projects",
        "kostnadsstallen": "/costcenters",
    }
    if typ not in giltiga:
        raise SpirisKlientFel(f"Okänd referenstyp: {typ!r}. Giltiga: {list(giltiga.keys())}")
    return klient.hamta_alla(giltiga[typ], filter=filter, select=select, orderby=orderby, pagesize=pagesize)


def hamta_verifikatutkast(klient: _Spirisklient) -> list[Verifikation]:
    """Hämtar obokförda verifikatutkast från Spiris och mappar till domänobjekt."""
    return [mappa_verifikatutkast(rå) for rå in klient.hamta_alla("/voucherdrafts")]


# --- Mutationer (Åtgärdsinitiering) -------------------------------------------


_REFERENSTYPER: dict[str, tuple[str, tuple[tuple[str, str], ...]]] = {
    "enheter":            ("/units",           (("id","Id"), ("kod","Code"),
                                                ("namn","Name"), ("forkortning","Abbreviation"))),
    "valutor":            ("/currencies",      (("kod","Code"),)),
    "betalningsvillkor":  ("/termsofpayments", (("id","Id"), ("namn","Name"),
                                                ("antal_dagar","NumberOfDays"),
                                                ("for_forsaljning","AvailableForSales"),
                                                ("for_inkop","AvailableForPurchase"))),
    "leveranssatt":       ("/deliverymethods", (("id","Id"), ("kod","Code"), ("namn","Name"))),
    "leveransvillkor":    ("/deliveryterms",   (("id","Id"), ("kod","Code"), ("namn","Name"))),
    "lander":             ("/countries",       (("kod","Code"), ("namn","Name"),
                                                ("eu_medlem","IsEuMember"))),
    "kontotyper":         ("/accountTypes",    (("typ","Type"), ("beskrivning","TypeDescription"))),
}

def hamta_referensdata(klient: _Spirisklient, typ: str, *, filter: str | None = None, select: list[str] | None = None, orderby: str | None = None, pagesize: int | None = None) -> list[dict]:
    """Referensdata från åtta olika endpoints.
    Ingen maskering här eftersom värderymden (måttenheter, valutakoder,
    landskoder, etc) annars hade matchat oskyldiga ord (tex "timme" till PERSON_1),
    vilket hade gjort verktyget oanvändbart utan att öka integritetsskyddet.
    """
    if typ == "momssatser":
        rader = []
        for rå in klient.hamta_alla("/vatcodesrates", filter=filter, select=select, orderby=orderby, pagesize=pagesize):
            rader.append({
                "id": rå.get("Id"),
                "kod": rå.get("Code"),
                "beskrivning": rå.get("Description"),
                "satser": [
                    {"datum": r.get("VatRateDate"), "momssats": r.get("VatRate")}
                    for r in rå.get("VatRates") or []
                ]
            })
        return rader

    if typ not in _REFERENSTYPER:
        giltiga = ", ".join(list(_REFERENSTYPER.keys()) + ["momssatser"])
        raise ValueError(f"Okänd referenstyp '{typ}'. Giltiga är: {giltiga}")

    path, fält = _REFERENSTYPER[typ]
    rader = []
    for rå in klient.hamta_alla(path, filter=filter, select=select, orderby=orderby, pagesize=pagesize):
        rad = {}
        for domännyckel, spirisfält in fält:
            rad[domännyckel] = rå.get(spirisfält)
        rader.append(rad)
        
    return rader


_BANKHANDELSE_STATUS: dict[str, str] = {
    "omatchade": "unmatched",
    "matchade": "matched",
}

def hamta_bankhandelser(
    klient: _Spirisklient,
    bankkonto_id: str,
    status: str = "omatchade",
    fran_datum: str | None = None,
    till_datum: str | None = None,
) -> list[dict]:
    """Banktransaktioner för ETT bankkonto, matchade eller omatchade mot
    bokföringen. Innehåller inga motpartsnamn, OCR-nummer eller kontonummer.
    
    En tom lista betyder att bolaget saknar aktivt bankavtal eller att inga
    händelser finns i perioden."""
    if status not in _BANKHANDELSE_STATUS:
        giltiga = ", ".join(f"'{k}'" for k in _BANKHANDELSE_STATUS)
        raise ValueError(f"Okänd status: {status}. Giltiga är: {giltiga}")

    params: dict = {}
    if fran_datum:
        params["fromDate"] = fran_datum
    if till_datum:
        params["toDate"] = till_datum

    path = f"/banktransactions/{bankkonto_id}/{_BANKHANDELSE_STATUS[status]}"
    
    handelser = []
    for h in klient.hamta_alla(path, params if params else None):
        konteringar = []
        for r in h.get("Rows") or []:
            konteringar.append({
                "verifikat_id": r.get("VoucherId"),
                "verifikatnummer": str(r.get("PaymentVoucherNumber") or ""),
                "belopp": r.get("AmountTransactionCurrency"),
                "kalla": r.get("Source"),
            })

        datum = str(h.get("TransactionDate") or "")[:10]
        handelser.append({
            "id": h["Id"],
            "datum": datum,
            "avstamd": bool(h.get("IsReconciled", False)),
            "belopp": h.get("TransactionAmount"),
            "originalbelopp": h.get("OriginalAmount"),
            "avgift": h.get("ChargeAmount"),
            "valuta": h.get("TransactionAmountCurrency") or "",
            "antal_konteringsrader": len(konteringar),
            "konteringar": konteringar,
        })
    return handelser


def hamta_avstamningslage(klient: _Spirisklient) -> list[dict]:
    """Hur mycket som är obokfört per bankkonto, sammanställt genom att läsa av
    varje konto och sedan hämta dess omatchade händelser."""
    sammanstallning = []
    for konto in hamta_bankkonton(klient):
        handelser = hamta_bankhandelser(klient, konto["id"], "omatchade")
        
        summa = Decimal("0")
        aldsta = None
        for h in handelser:
            if h["belopp"] is not None:
                summa += h["belopp"]
            
            if h["datum"]:
                if aldsta is None or h["datum"] < aldsta:
                    aldsta = h["datum"]

        sammanstallning.append({
            "bankkonto": konto["namn"],
            "bankkonto_id": konto["id"],
            "bas_konto": konto["bas_konto"],
            "antal_omatchade": len(handelser),
            "summa_omatchade": summa,
            "aldsta_omatchad": aldsta,
        })
    return sammanstallning


# --- Steg 5: kundfakturans livscykelåtgärder --------------------------------
#
# Fyra åtgärder på en BEFINTLIG kundfaktura. De skiljer sig från allt annat i
# den här modulen genom att två av dem är UTÅTRIKTADE: de skickar något till en
# tredje man (kunden) och kan inte kallas tillbaka. Steg 4:s lösning — att låta
# skrivningen landa i en återkallelig utkastkö — finns inte här. Det finns
# ingen utkastform för "mejla".
#
# Grinden är i stället MOTTAGARVISNING, och den är hårdkodad i utfor_utkast:
# en utåtriktad åtgärd kan inte utföras utan att anroparen skickar med den
# mottagare en MÄNNISKA faktiskt sett på skärmen. Skälet är konkret: EmailApi
# har ett VALFRITT Email-fält, och utelämnas det mejlar Spiris till kundens
# registrerade adress. Vi skulle alltså kunna skicka till en mottagare som
# ingen människa någonsin granskat — och AI:n kan per konstruktion inte se
# adressen, eftersom hamta_kunder (Steg 2) aldrig hämtar EmailAddress.
#
# Därför sätts Email ALLTID explicit till det granskade värdet. "Det som
# visades" och "det som skickades" blir då samma sträng, inte två oberoende
# uppslag mot ett register som kan ha ändrats däremellan.

UTKASTTYP_FAKTURAUTSKICK = "fakturautskick"
UTKASTTYP_BETALNINGSPAMINNELSE = "betalningspaminnelse"
UTKASTTYP_BETALNINGSREGISTRERING = "betalningsregistrering"
UTKASTTYP_MAKULERING = "makulering"
# Steg 5b: offert- och orderkedjan.
UTKASTTYP_SALJDOKUMENTUTSKICK = "saljdokumentutskick"
UTKASTTYP_EFAKTURAUTSKICK = "efakturautskick"
UTKASTTYP_SALJDOKUMENTATGARD = "saljdokumentatgard"

# Typer som når en tredje man. Kräver granskad mottagare i utfor_utkast.
UTATRIKTADE_TYPER: frozenset[str] = frozenset(
    {
        UTKASTTYP_FAKTURAUTSKICK,
        UTKASTTYP_BETALNINGSPAMINNELSE,
        UTKASTTYP_SALJDOKUMENTUTSKICK,
        UTKASTTYP_EFAKTURAUTSKICK,
    }
)

# InvoicePaymentApi.PaymentType (ur OpenAPI-schemat, ej sandbox-bekräftat).
BETALNING_DELBETALNING = 1
BETALNING_FULLBETALNING = 2


def _hitta_faktura(klient: _Spirisklient, fakturanummer: str) -> dict:
    """Slår upp EN kundfaktura på dess fakturanummer och returnerar det RÅA
    Spiris-objektet.

    Fail-closed på samma grund som _hitta_kund_id: en tvetydig eller utebliven
    träff höjer fel i stället för att gissa vilken faktura som avses. Att mejla
    eller makulera FEL faktura är värre än att inte göra något alls.

    Returnerar det råa objektet, inte en fältallowlistad vy: anroparen är appen
    lokalt (aldrig spiris_rag eller MCP), och den behöver CustomerEmail — som
    med flit aldrig får lämna datorn."""
    sokt = str(fakturanummer).strip()
    traffar = [
        f for f in klient.hamta_alla("/customerinvoices")
        if str(f.get("InvoiceNumber") or "").strip() == sokt
    ]
    if not traffar:
        raise SpirisKlientFel(f"Ingen kundfaktura med nummer {sokt!r} finns i Spiris.")
    if len(traffar) > 1:
        raise SpirisKlientFel(
            f"Flera kundfakturor har nummer {sokt!r} — åtgärda manuellt i Spiris."
        )
    return traffar[0]


def hamta_utskicksgranskning(klient: _Spirisklient, fakturanummer: str) -> dict:
    """Underlaget människan ska se INNAN hon godkänner en utåtriktad åtgärd.

    ANROPAS ALDRIG FRÅN spiris_rag ELLER MCP-SERVERN. Det här är den enda
    funktionen i modulen som medvetet returnerar en e-postadress och ett
    omaskerat kundnamn, och den finns bara för den lokala godkännandevyn i
    Streamlit. Gick den via ett MCP-verktyg läckte precis det som hamta_kunder
    är byggd för att aldrig hämta.

    `mottagare` är tom sträng om fakturan saknar registrerad e-postadress. Det
    är INTE ett fel här — det är ett giltigt tillstånd som vyn ska visa, och
    som utfor_utkast sedan vägrar skicka på."""
    fak = _hitta_faktura(klient, fakturanummer)
    return {
        "faktura_id": str(fak.get("Id") or ""),
        "fakturanummer": str(fak.get("InvoiceNumber") or ""),
        "mottagare": (fak.get("CustomerEmail") or "").strip(),
        "kund": fak.get("CustomerName") or fak.get("InvoiceCustomerName") or "",
        "totalbelopp": fak.get("TotalAmount"),
        "kvarvarande": fak.get("RemainingAmount"),
        "forfallodatum": str(fak.get("DueDate") or "")[:10],
        "senaste_paminnelse": str(fak.get("LastPaymentReminderSentDate") or "")[:10],
        "valuta": fak.get("CurrencyCode") or "SEK",
    }


def skicka_faktura_epost(
    klient: _Spirisklient, faktura_id: str, mottagare: str,
    amne: str = "", meddelande: str = "",
) -> dict:
    """Mejlar en BEFINTLIG kundfaktura till en GRANSKAD mottagare.

    `mottagare` är obligatorisk och sätts explicit i payloaden. EmailApi.Email
    är valfritt i Spiris — utelämnat mejlar Spiris till kundens registrerade
    adress, alltså till någon ingen människa sett. Det får inte kunna hända
    härifrån.

    Oåterkallelig: ett skickat mejl kan inte kallas tillbaka."""
    if not (mottagare or "").strip():
        raise SpirisKlientFel(
            "Ingen granskad mottagare angiven — fakturan mejlas inte."
        )
    payload: dict[str, Any] = {"Email": mottagare.strip()}
    if amne:
        payload["Subject"] = amne
    if meddelande:
        payload["Message"] = meddelande
    try:
        svar = klient.skicka(f"/customerinvoices/{faktura_id}/email", payload)
    except SpirisKlientFel:
        _logger.error("Kunde inte mejla kundfaktura (Id=%s).", faktura_id)
        raise
    # Aldrig mottagaradressen i loggen — den är en personuppgift.
    _logger.info("Kundfaktura mejlad (Id=%s).", faktura_id)
    return svar


def skicka_betalningspaminnelse(
    klient: _Spirisklient, faktura_id: str, mottagare: str,
    drojsmalsavgift: Decimal | None = None,
    amne: str = "", meddelande: str = "",
) -> dict:
    """Skickar en betalningspåminnelse för en BEFINTLIG kundfaktura till en
    GRANSKAD mottagare. Samma mottagarkrav och samma oåterkallelighet som
    skicka_faktura_epost.

    Dröjsmålsavgiften är VALFRI och skickas bara när den uttryckligen angetts.
    Noll och "ingen avgift" är olika saker, och en avgift som smyger in i en
    påminnelse är ett anspråk mot kunden som ingen bett om."""
    if not (mottagare or "").strip():
        raise SpirisKlientFel(
            "Ingen granskad mottagare angiven — påminnelsen skickas inte."
        )
    epost: dict[str, Any] = {"Email": mottagare.strip()}
    if amne:
        epost["Subject"] = amne
    if meddelande:
        epost["Message"] = meddelande
    payload: dict[str, Any] = {"EmailDetails": epost}
    if drojsmalsavgift is not None:
        payload["LatePaymentFee"] = drojsmalsavgift
    try:
        svar = klient.skicka(
            f"/customerinvoices/{faktura_id}/paymentreminders", payload
        )
    except SpirisKlientFel:
        _logger.error("Kunde inte skicka betalningspåminnelse (Id=%s).", faktura_id)
        raise
    _logger.info("Betalningspåminnelse skickad (Id=%s).", faktura_id)
    return svar


def bygg_betalningspayload(
    bankkonto_id: str, betaldatum: str, belopp: Decimal,
    valuta: str, kvarvarande: Decimal | None, referens: str = "",
) -> dict:
    """Bygger en /payments-POST-kropp. Ren mappning, ingen I/O.

    PaymentType härleds ur beloppet: täcker betalningen hela det kvarvarande
    beloppet är den en fullbetalning, annars en delbetalning. Är det
    kvarvarande beloppet OKÄNT (None) höjs fel i stället för att gissa — en
    delbetalning som felaktigt bokförs som fullbetalning stänger en fordran
    som fortfarande finns.

    Jämförelsen sker på BELOPPENS STORLEK, inte på deras tecken. Sandbox-mätt
    2026-08-06: `RemainingAmount` är NEGATIVT på leverantörsfakturor (skuld)
    och på kundkreditfakturor, men positivt på vanliga kundfakturor. En rak
    `belopp >= kvarvarande` gjorde därför VARJE delbetalning av en
    leverantörsfaktura till en fullbetalning — 500 kr mot en skuld på 1 000 kr
    räknades som fullt betald, eftersom 500 > −1 000."""
    if kvarvarande is None:
        raise ValueError(
            "Kvarvarande belopp är okänt — betalningstypen kan inte avgöras."
        )
    payload: dict[str, Any] = {
        "CompanyBankAccountId": bankkonto_id,
        "PaymentDate": betaldatum,
        "PaymentAmount": belopp,
        "PaymentCurrency": valuta,
        "PaymentType": (
            BETALNING_FULLBETALNING if abs(belopp) >= abs(kvarvarande)
            else BETALNING_DELBETALNING
        ),
    }
    if referens:
        payload["Reference"] = referens
    return payload


def registrera_betalning(
    klient: _Spirisklient, faktura_id: str, betalning_data: dict
) -> dict:
    """Registrerar en kundbetalning på en BEFINTLIG faktura.

    Inte utåtriktad — ingenting når kunden — men den påverkar räkenskaperna
    och reskontran direkt. Ingen utkastmotsvarighet finns i Spiris."""
    try:
        svar = klient.skicka(
            f"/customerinvoices/{faktura_id}/payments", betalning_data
        )
    except SpirisKlientFel:
        _logger.error("Kunde inte registrera betalning (Id=%s).", faktura_id)
        raise
    _logger.info(
        "Betalning registrerad (Id=%s, typ=%s).",
        faktura_id, betalning_data.get("PaymentType"),
    )
    return svar


def makulera_faktura(klient: _Spirisklient, faktura_id: str) -> dict:
    """Makulerar en BEFINTLIG kundfaktura (/void).

    Oåterkallelig och bokföringspåverkande. Tar ingen kropp — hela åtgärden
    ligger i sökvägen, vilket gör den lätt att utlösa av misstag. Därför sker
    den bara efter ett godkänt utkast, aldrig som följd av en analys."""
    try:
        svar = klient.skicka(f"/customerinvoices/{faktura_id}/void", {})
    except SpirisKlientFel:
        _logger.error("Kunde inte makulera kundfaktura (Id=%s).", faktura_id)
        raise
    _logger.info("Kundfaktura makulerad (Id=%s).", faktura_id)
    return svar


# --- Steg 5b: offert- och orderkedjan ---------------------------------------
#
# Samma två riskklasser som i Steg 5. Utskicken (offert/order per e-post,
# kundfaktura som e-faktura) når en tredje man och omfattas av mottagargrinden.
# Kedjeåtgärderna (godkänn offert, konvertera, slutför, makulera) når ingen
# utanför bolaget men ändrar dokumentens tillstånd oåterkalleligt.
#
# KREDITERING INGÅR INTE. `/customerinvoices/{id}/credit` har ett TOMT
# path-objekt i Spiris OpenAPI-spec — ingen dokumenterad metod, samma tillstånd
# som dryrun-endpointsen. Att gissa fram verb och kropp för en åtgärd som
# skapar en kreditfaktura mot en riktig kund vore precis den sortens gissning
# som resten av modulen är byggd för att undvika.

_SALJDOKUMENT: dict[str, str] = {"offert": "/quotes", "order": "/orders", "offertutkast": "/quotedrafts"}

# ElectronicInvoiceRequestApi.SendType. 1 = AutoInvoiceElectronic.
EFAKTURA_ELEKTRONISK = 1

# (dokumenttyp, åtgärd) -> (verb, sökvägssuffix, kropp).
# Hårdkodad och fail-closed: en kombination som inte står här utförs ALDRIG.
# Att konvertera en offert till en order är inte samma sak som att slutföra en
# order, och en tabell är det enda som gör skillnaden omöjlig att slarva bort.
_SALJDOKUMENTATGARDER: dict[tuple[str, str], tuple[str, str, dict]] = {
    ("offert", "godkann"): ("PUT", "accept", {}),
    # QuoteConversionApi.Type: 0 = OrderDraft, 1 = Order. Vi skapar en RIKTIG
    # order, inte ett orderutkast — annars vore åtgärdens namn missvisande.
    ("offert", "till_order"): ("POST", "converttoorder", {"Type": 1}),
    ("offert", "till_faktura"): ("POST", "converttocustomerinvoice", {}),
    ("order", "till_faktura"): ("POST", "convert", {}),
    ("order", "slutford"): ("POST", "completed", {}),
    ("order", "makulerad"): ("POST", "voided", {}),
    ("offertutkast", "till_offert"): ("PUT", "convert", {}),
    ("order", "till_backorder"): ("POST", "backorder", {}),
}


def _hitta_saljdokument(klient: _Spirisklient, dokumenttyp: str, nummer: str) -> dict:
    """Slår upp EN offert eller order på dess NUMMER eller dess ID.

    Att också godta id är inte bekvämlighet utan nödvändighet. Sandbox-provet
    2026-08-06 visade att `Number` är None på 3 av 5 offerter/ordrar i ett
    riktigt bolag — Spiris tilldelar numret först i ett senare skede. Ett
    onumrerat dokument hade annars varit omöjligt att adressera, och Steg 5b:s
    åtgärder oåtkomliga för just de dokument som oftast behöver dem (en
    offert som ännu inte skickats).

    En TOM söksträng matchar ingenting: annars hade den träffat varje
    onumrerat dokument på en gång och gjort tvetydighetskontrollen nedan till
    enda skyddet.

    Fail-closed på tvetydig eller utebliven träff, av samma skäl som
    _hitta_faktura."""
    if dokumenttyp not in _SALJDOKUMENT:
        giltiga = ", ".join(repr(t) for t in _SALJDOKUMENT)
        raise SpirisKlientFel(
            f"Okänd dokumenttyp: {dokumenttyp!r}. Giltiga är: {giltiga}."
        )
    sokt = str(nummer).strip()
    if not sokt:
        raise SpirisKlientFel(
            f"Inget nummer eller id angivet för {dokumenttyp}."
        )
    traffar = [
        d for d in klient.hamta_alla(_SALJDOKUMENT[dokumenttyp])
        if str(d.get("Number") or "").strip() == sokt
        or str(d.get("Id") or "").strip() == sokt
    ]
    if not traffar:
        raise SpirisKlientFel(
            f"Ingen {dokumenttyp} med nummer {sokt!r} finns i Spiris."
        )
    if len(traffar) > 1:
        raise SpirisKlientFel(
            f"Flera dokument av typen {dokumenttyp} har nummer {sokt!r} — "
            "åtgärda manuellt i Spiris."
        )
    return traffar[0]


def hamta_saljdokumentgranskning(
    klient: _Spirisklient, dokumenttyp: str, nummer: str
) -> dict:
    """Underlaget människan ska se innan en offert eller order mejlas.

    ANROPAS ALDRIG FRÅN spiris_rag ELLER MCP-SERVERN — samma skäl som
    hamta_utskicksgranskning.

    Till skillnad från en kundfaktura bär varken QuoteApi eller OrderApi någon
    e-postadress. Mottagaren måste därför slås upp via dokumentets CustomerId
    mot /customers. Saknas kopplingen är `mottagare` tom sträng, vilket är ett
    giltigt tillstånd som vyn visar och grinden sedan vägrar skicka på."""
    dok = _hitta_saljdokument(klient, dokumenttyp, nummer)
    kund_id = str(dok.get("CustomerId") or "")
    mottagare = ""
    if kund_id:
        kund = klient.hamta_en(f"/customers/{kund_id}")
        mottagare = (kund.get("EmailAddress") or "").strip()
    return {
        "dokument_id": str(dok.get("Id") or ""),
        "dokumenttyp": dokumenttyp,
        "nummer": str(dok.get("Number") or ""),
        "mottagare": mottagare,
        "kund": dok.get("CustomerName") or "",
        "status": dok.get("Status"),
    }


def hamta_efakturagranskning(klient: _Spirisklient, fakturanummer: str) -> dict:
    """Underlaget människan ska se innan en kundfaktura skickas som e-faktura.

    ANROPAS ALDRIG FRÅN spiris_rag ELLER MCP-SERVERN.

    En e-faktura går inte till en e-postadress utan till en registrerad
    AutoInvoice-mottagare. Den hämtas via /customers/{id}/autoinvoicerecipients,
    och `mottagare` sätts till "Namn (elektronisk adress)" — den sträng
    människan ser och godkänner. Saknar kunden en registrerad mottagare blir
    den tom, och grinden vägrar."""
    fak = _hitta_faktura(klient, fakturanummer)
    kund_id = str(fak.get("CustomerId") or "")
    mottagare = ""
    if kund_id:
        mottagare_rader = klient.hamta_alla(
            f"/customers/{kund_id}/autoinvoicerecipients"
        )
        if mottagare_rader:
            forsta = mottagare_rader[0]
            namn = (forsta.get("Name") or "").strip()
            adress = (forsta.get("ElectronicAddress") or "").strip()
            mottagare = f"{namn} ({adress})".strip() if (namn or adress) else ""
    return {
        "faktura_id": str(fak.get("Id") or ""),
        "fakturanummer": str(fak.get("InvoiceNumber") or ""),
        "mottagare": mottagare,
        "kund": fak.get("CustomerName") or "",
        "totalbelopp": fak.get("TotalAmount"),
    }


def skicka_saljdokument_epost(
    klient: _Spirisklient, dokumenttyp: str, dokument_id: str, mottagare: str,
    amne: str = "", meddelande: str = "",
) -> dict:
    """Mejlar en BEFINTLIG offert eller order till en GRANSKAD mottagare.

    Samma mottagarkrav och samma explicita Email-sättning som
    skicka_faktura_epost — EmailApi är samma schema för alla tre
    utskicksendpoints, och därmed samma fallgrop: utelämnat Email låter Spiris
    välja mottagare åt oss."""
    if not (mottagare or "").strip():
        raise SpirisKlientFel(
            f"Ingen granskad mottagare angiven — {dokumenttyp} mejlas inte."
        )
    if dokumenttyp not in _SALJDOKUMENT:
        raise SpirisKlientFel(f"Okänd dokumenttyp: {dokumenttyp!r}.")
    payload: dict[str, Any] = {"Email": mottagare.strip()}
    if amne:
        payload["Subject"] = amne
    if meddelande:
        payload["Message"] = meddelande
    path = f"{_SALJDOKUMENT[dokumenttyp]}/{dokument_id}/email"
    try:
        svar = klient.skicka(path, payload)
    except SpirisKlientFel:
        _logger.error("Kunde inte mejla %s (Id=%s).", dokumenttyp, dokument_id)
        raise
    _logger.info("%s mejlad (Id=%s).", dokumenttyp.capitalize(), dokument_id)
    return svar


def skicka_efaktura(
    klient: _Spirisklient, faktura_id: str, sandtyp: int = EFAKTURA_ELEKTRONISK
) -> dict:
    """Skickar en BEFINTLIG kundfaktura som e-faktura via AutoInvoice.

    Utåtriktad och oåterkallelig. Kräver att bolaget har AutoInvoice aktiverat
    och att kunden har en registrerad mottagare — det senare kontrolleras av
    hamta_efakturagranskning, inte här."""
    try:
        svar = klient.skicka(
            f"/customerinvoices/{faktura_id}/einvoice", {"SendType": sandtyp}
        )
    except SpirisKlientFel:
        _logger.error("Kunde inte skicka e-faktura (Id=%s).", faktura_id)
        raise
    _logger.info("E-faktura skickad (Id=%s, sandtyp=%s).", faktura_id, sandtyp)
    return svar


def utfor_saljdokumentatgard(
    klient: _Spirisklient, dokumenttyp: str, dokument_id: str, atgard: str
) -> dict:
    """Utför en kedjeåtgärd på en offert eller order enligt den hårdkodade
    tabellen ovan.

    Når ingen utanför bolaget, men ändrar dokumentets tillstånd oåterkalleligt
    — en konverterad offert kan inte konverteras tillbaka. Fail-closed på en
    kombination som inte finns i tabellen: den GISSAS aldrig fram.

    `godkann` använder klientens PUT (uppdatera), som tillkom i Steg 1 och
    fram till nu varit oanvänd — /quotes/{id}/accept är det första stället i
    kodbasen som faktiskt behöver verbet."""
    nyckel = (dokumenttyp, atgard)
    if nyckel not in _SALJDOKUMENTATGARDER:
        giltiga = ", ".join(f"{t}/{a}" for t, a in sorted(_SALJDOKUMENTATGARDER))
        raise SpirisKlientFel(
            f"Okänd åtgärd {atgard!r} för {dokumenttyp!r}. Giltiga är: {giltiga}."
        )
    verb, suffix, kropp = _SALJDOKUMENTATGARDER[nyckel]
    path = f"{_SALJDOKUMENT[dokumenttyp]}/{dokument_id}/{suffix}"
    try:
        if verb == "PUT":
            svar = klient.uppdatera(path, kropp)
        else:
            svar = klient.skicka(path, kropp)
    except SpirisKlientFel:
        _logger.error(
            "Kunde inte utföra %s på %s (Id=%s).", atgard, dokumenttyp, dokument_id
        )
        raise
    _logger.info(
        "Åtgärd %s utförd på %s (Id=%s).", atgard, dokumenttyp, dokument_id
    )
    return svar


# --- Steg 6: inköp och attest -----------------------------------------------
#
# Ingen av åtgärderna här når en tredje man, med ETT undantag som därför
# hanteras särskilt: ApprovalApi bär `RejectionMessage` och
# `RejectionMessageReceivers` — ett avslag kan alltså SKICKA ETT MEDDELANDE
# till namngivna mottagare. Den här modulen fyller aldrig i de fälten. Ett
# avslag härifrån är en statusändring, inte ett utskick. Behövs ett meddelande
# skriver människan det i Spiris, där hon ser vem som får det.
#
# Leverantörsfakturor går som standard till /supplierinvoicedrafts av samma
# skäl som kundfakturor (Steg 4): utkastet är ändringsbart och borttagbart,
# och befordras av människan. /supplierinvoicedrafts/{id}/convert exponeras
# aldrig — befordran är bokföringsakten.

UTKASTTYP_LEVERANTORSFAKTURA = "leverantorsfakturautkast"
UTKASTTYP_ATTEST = "attest"
UTKASTTYP_LEVERANTORSBETALNING = "leverantorsbetalning"
UTKASTTYP_KVITTNING = "kvittning"
UTKASTTYP_BETALNINGSVERIFIKAT = "betalningsverifikat"

# ApprovalApi.DocumentApprovalStatus.
ATTEST_GODKANN = 1
ATTEST_AVSLA = 2

_ATTESTBESLUT: dict[str, int] = {
    "godkann": ATTEST_GODKANN,
    "avsla": ATTEST_AVSLA,
}

# Vad som går att attestera, och var. Hårdkodad och fail-closed.
_ATTESTOBJEKT: dict[str, str] = {
    "leverantorsfaktura": "/approval/supplierinvoice",
    "momsrapport": "/approval/vatreport",
}


def _hitta_leverantorsfaktura(klient: _Spirisklient, nummer_eller_id: str) -> dict:
    """Slår upp EN leverantörsfaktura på fakturanummer ELLER Spiris-id.

    Id godtas eftersom leverantörens fakturanummer sätts av LEVERANTÖREN och
    därför kan kollidera mellan olika leverantörer — till skillnad från våra
    egna kundfakturanummer. Vid en kollision är id:t den enda entydiga vägen.

    Fail-closed på tvetydig eller utebliven träff: att attestera eller betala
    FEL faktura är värre än att inte göra något alls."""
    sokt = str(nummer_eller_id).strip()
    if not sokt:
        raise SpirisKlientFel("Inget fakturanummer eller id angivet.")
    traffar = [
        f for f in klient.hamta_alla("/supplierinvoices")
        if str(f.get("InvoiceNumber") or "").strip() == sokt
        or str(f.get("Id") or "").strip() == sokt
    ]
    if not traffar:
        raise SpirisKlientFel(
            f"Ingen leverantörsfaktura med nummer eller id {sokt!r} finns i Spiris."
        )
    if len(traffar) > 1:
        raise SpirisKlientFel(
            f"Flera leverantörsfakturor matchar {sokt!r} — använd fakturans id "
            "i stället för dess nummer."
        )
    return traffar[0]


def bygg_leverantorsfakturautkast_payload(
    leverantor_id: str,
    rader: list[dict],
    fakturanummer: str = "",
    fakturadatum: str = "",
    forfallodatum: str = "",
    totalbelopp: Decimal | None = None,
    kreditfaktura: bool = False,
) -> dict:
    """Bygger en /supplierinvoicedrafts-POST-kropp. Ren mappning, ingen I/O.

    rader: [{"konto": kontonr, "debet": tal, "kredit": tal, "text": radtext}]
    — samma form som ett verifikat, eftersom en leverantörsfaktura konteras
    rad för rad mot konton och INTE via artiklar (till skillnad från en
    kundfaktura, se hitta_artikel_for_konto).

    SupplierId, IsCreditInvoice och Rows är obligatoriska enligt
    SupplierInvoiceDraftApi. `totalbelopp` är det OCKSÅ i praktiken, trots att
    schemat säger motsatsen — sandbox-mätt 2026-08-06 avvisar Spiris ett utkast
    utan TotalAmount med:

        "The amount on standard account 2440, recievables is not equal
         with TotalAmountBaseCurrency"

    Utelämnat blir TotalAmount noll, och stämmer då inte mot skuldkontots rad.
    Beloppet härleds MEDVETET inte ur raderna: det är fakturans nominella
    belopp enligt leverantören, och att räkna fram det ur en kontering vore
    just den sortens inferens kodbasen undviker — särskilt för kreditfakturor,
    där tecknet vänder.

    OcrNumber sätts ALDRIG härifrån: det är en betalningsidentifierare, samma
    resonemang som för bankgiro i hamta_bankkonton."""
    if not leverantor_id:
        raise ValueError("leverantor_id saknas — utkastet kan inte kopplas.")
    if not rader:
        raise ValueError("leverantörsfakturan saknar rader.")
    if not totalbelopp:
        raise ValueError(
            "totalbelopp saknas. Spiris avvisar ett leverantörsfakturautkast "
            "vars TotalAmount inte stämmer mot skuldkontots rad — ange "
            "fakturans belopp enligt leverantören."
        )
    payload: dict[str, Any] = {
        "SupplierId": leverantor_id,
        "IsCreditInvoice": bool(kreditfaktura),
        "Rows": [
            {
                "AccountNumber": int(rad["konto"]),
                "DebitAmount": Decimal(str(rad.get("debet") or 0)),
                "CreditAmount": Decimal(str(rad.get("kredit") or 0)),
                "TransactionText": rad.get("text") or "",
                # LineNumber sätts explicit så raderna bär en uttrycklig,
                # stabil numrering. Sandbox-mätt 2026-08-06: utan fältet
                # numrerar Spiris raderna 0,1; med det behålls 1,2 — värdet
                # rundgår alltså.
                #
                # Vad detta INTE gör: styra i vilken ordning Spiris returnerar
                # raderna. Det observerades olika mellan två körningar med
                # samma numrering, och något sådant påstående görs därför inte.
                "LineNumber": index,
            }
            for index, rad in enumerate(rader, start=1)
        ],
    }
    if fakturanummer:
        payload["InvoiceNumber"] = str(fakturanummer)
    if fakturadatum:
        payload["InvoiceDate"] = fakturadatum
    if forfallodatum:
        payload["DueDate"] = forfallodatum
    if totalbelopp is not None:
        payload["TotalAmount"] = totalbelopp
    return payload


def skapa_leverantorsfakturautkast(klient: _Spirisklient, data: dict) -> dict:
    """POSTar ett leverantörsfakturaUTKAST (/supplierinvoicedrafts).

    Återkalleligt: går att ändra (PUT) och ta bort (DELETE). Befordras till en
    bokförd leverantörsfaktura via /convert — som ALDRIG anropas härifrån och
    aldrig exponeras över MCP."""
    try:
        skapat = klient.skicka("/supplierinvoicedrafts", data)
    except SpirisKlientFel:
        _logger.error(
            "Kunde inte skapa leverantörsfakturautkast (%d rader).",
            len(data.get("Rows", [])),
        )
        raise
    _logger.info(
        "Leverantörsfakturautkast skapat (Id=%s, %d rader).",
        skapat.get("Id"), len(data.get("Rows", [])),
    )
    return skapat


def attestera(
    klient: _Spirisklient, objekttyp: str, objekt_id: str, beslut: str
) -> dict:
    """Attesterar ett dokument (/approval/...). Godkänn eller avslå.

    Fyller ALDRIG i RejectionMessage eller RejectionMessageReceivers. Ett
    avslag härifrån är en statusändring, inte ett utskick — de fälten skickar
    ett meddelande till namngivna mottagare, och den här modulen komponerar
    aldrig ett meddelande till en människa. Behövs ett skriver användaren det
    i Spiris, där hon ser vem som får det.

    Fail-closed på okänd objekttyp eller okänt beslut: attest är ett
    ansvarstagande, inte en gissning."""
    if objekttyp not in _ATTESTOBJEKT:
        giltiga = ", ".join(repr(t) for t in _ATTESTOBJEKT)
        raise SpirisKlientFel(
            f"Okänd attestobjekttyp: {objekttyp!r}. Giltiga är: {giltiga}."
        )
    if beslut not in _ATTESTBESLUT:
        giltiga = ", ".join(repr(b) for b in _ATTESTBESLUT)
        raise SpirisKlientFel(
            f"Okänt attestbeslut: {beslut!r}. Giltiga är: {giltiga}."
        )
    path = f"{_ATTESTOBJEKT[objekttyp]}/{objekt_id}"
    try:
        svar = klient.uppdatera(path, {"DocumentApprovalStatus": _ATTESTBESLUT[beslut]})
    except SpirisKlientFel:
        _logger.error("Kunde inte attestera %s (Id=%s).", objekttyp, objekt_id)
        raise
    _logger.info("Attest %s utförd på %s (Id=%s).", beslut, objekttyp, objekt_id)
    return svar


def registrera_leverantorsbetalning(
    klient: _Spirisklient, faktura_id: str, betalning_data: dict
) -> dict:
    """Registrerar en betalning på en BEFINTLIG leverantörsfaktura.

    Delar payloadbyggare (bygg_betalningspayload) med kundsidan: Spiris
    använder samma InvoicePaymentApi för båda."""
    try:
        svar = klient.skicka(
            f"/supplierinvoices/{faktura_id}/payments", betalning_data
        )
    except SpirisKlientFel:
        _logger.error("Kunde inte registrera leverantörsbetalning (Id=%s).", faktura_id)
        raise
    _logger.info(
        "Leverantörsbetalning registrerad (Id=%s, typ=%s).",
        faktura_id, betalning_data.get("PaymentType"),
    )
    return svar


# --- Steg 7: masterdata-ändringar -------------------------------------------
#
# PUT NOLLAR UTELÄMNADE FÄLT. Sandbox-mätt 2026-08-06 på en egen testkund: en
# PUT med bara de obligatoriska fälten satte EmailAddress, InvoiceAddress1,
# Telephone och Note till None. (En helt partiell PUT — bara Id och Name —
# avvisas dessutom med 400: de obligatoriska fälten måste alltid med.)
#
# Det gör READ-MODIFY-WRITE obligatoriskt, och kopplar ihop med kodbasens
# integritetsdesign på ett skarpt sätt: hamta_kunder hämtar med flit ALDRIG
# e-post, telefon eller adress, så en AI kan inte förse oss med dem. En naiv
# uppdatering hade därför raderat precis de fält AI:n aldrig fick läsa.
#
# Därför: det NUVARANDE objektet hämtas LOKALT vid utförandet, ändringarna
# läggs ovanpå, och hela objektet skrivs tillbaka. AI:n bidrar bara med vad
# som ska ändras — aldrig med objektets övriga innehåll.
#
# Ändringsallowlisten är lika viktig som läsallowlisten: utan den kunde ett
# AI-förslag sätta vilket fält som helst i ett objekt människan bara ombetts
# godkänna en namnändring på.

UTKASTTYP_MASTERDATAANDRING = "masterdataandring"
UTKASTTYP_MASTERDATABORTTAGNING = "masterdataborttagning"

UTKASTTYP_UTKASTANDRING = "utkastandring"
UTKASTTYP_UTKASTBORTTAGNING = "utkastborttagning"
UTKASTTYP_UTKASTBOKFORING = "utkastbokforing"


# objekttyp -> (sökvägsprefix, {domännyckel: spirisfält})
_MASTERDATA: dict[str, tuple[str, dict[str, str]]] = {
    "kund": ("/customers", {
        "namn": "Name",
        "aktiv": "IsActive",
        "valuta": "CurrencyCode",
        "betalningsvillkor_id": "TermsOfPaymentId",
        "land": "InvoiceCountryCode",
        # Gör R-15:s förutsättning åtkomlig: byggmoms kräver att kunden är
        # flaggad, och utan den här nyckeln kunde flaggan bara sättas manuellt
        # i Spiris. Har i sin TUR en egen förutsättning — se
        # _kontrollera_byggmomsforutsattning.
        "omvand_byggmoms": "ReverseChargeOnConstructionServices",
    }),
    "leverantor": ("/suppliers", {
        "namn": "Name",
        "aktiv": "IsActive",
        "valuta": "CurrencyCode",
        "betalningsvillkor_id": "TermsOfPaymentId",
        "land": "CountryCode",
    }),
    "artikel": ("/articles", {
        "namn": "Name",
        "pris": "NetPrice",
        "aktiv": "IsActive",
    }),
    "projekt": ("/projects", {
        "namn": "Name",
        "startdatum": "StartDate",
        "slutdatum": "EndDate",
        "status": "Status",
    }),
    "bankkonto": ("/bankaccounts", {
        "namn": "Name",
        "aktiv": "IsActive",
    }),
}

# Bara dessa har en DELETE i Spiris. Artiklar och projekt går att INAKTIVERA
# (aktiv=False) men inte ta bort — och det är rimligt: de är refererade från
# historiska poster.
_BORTTAGBARA: frozenset[str] = frozenset({"kund", "leverantor", "bankkonto"})


def bygg_masterdatauppdatering(
    nuvarande: dict, andringar: dict, objekttyp: str
) -> dict:
    """Lägger ändringarna ovanpå det NUVARANDE objektet och returnerar hela
    objektet, redo för PUT. Ren funktion, ingen I/O.

    Fail-closed på en nyckel som inte står i ändringsallowlisten: ett
    AI-förslag ska inte kunna sätta ett fält människan aldrig ombetts
    granska.

    Returnerar hela objektet just för att PUT nollar det som utelämnas — se
    avsnittskommentaren ovan."""
    if objekttyp not in _MASTERDATA:
        giltiga = ", ".join(repr(t) for t in _MASTERDATA)
        raise SpirisKlientFel(
            f"Okänd objekttyp: {objekttyp!r}. Giltiga är: {giltiga}."
        )
    _, allowlist = _MASTERDATA[objekttyp]
    if not andringar:
        raise ValueError("Inga ändringar angivna.")

    okanda = [nyckel for nyckel in andringar if nyckel not in allowlist]
    if okanda:
        giltiga = ", ".join(sorted(allowlist))
        raise SpirisKlientFel(
            f"Följande går inte att ändra på en {objekttyp}: "
            f"{sorted(okanda)}. Ändringsbara fält: {giltiga}."
        )

    uppdaterat = dict(nuvarande)
    for nyckel, varde in andringar.items():
        uppdaterat[allowlist[nyckel]] = varde
    return uppdaterat


def _kontrollera_byggmomsforutsattning(
    objekttyp: str, nuvarande: dict, andringar: dict
) -> None:
    """Omvänd skattskyldighet kräver att kunden har ett momsregistreringsnummer.

    Sandbox-mätt 2026-08-06: en PUT som sätter
    ReverseChargeOnConstructionServices=True på en kund utan VatNumber avvisas
    med "VatNumber can not be null or empty when using
    ReverseChargeOnConstructionServices".

    Kontrollen finns för att göra det svaret begripligt. Utan den fick
    användaren ett naket "HTTP 400" på en åtgärd som ser trivial ut.

    `vatnummer` är MEDVETET inte ändringsbart härifrån: för en enskild firma
    är momsregistreringsnumret härlett ur innehavarens personnummer, och ett
    AI-förslag ska inte skriva in en sådan identifierare. Den hör hemma i
    Spiris egna kundformulär, hos människan."""
    if objekttyp != "kund" or not andringar.get("omvand_byggmoms"):
        return
    if not (nuvarande.get("VatNumber") or "").strip():
        raise SpirisKlientFel(
            "Kunden saknar momsregistreringsnummer i Spiris, och omvänd "
            "skattskyldighet kan inte aktiveras utan det. Lägg till numret på "
            "kunden i Spiris först — ingen ändring har gjorts."
        )



_UTKASTSLAG: dict[str, str] = {
    "verifikat": "/voucherdrafts",
    "kundfaktura": "/customerinvoicedrafts",
    "leverantorsfaktura": "/supplierinvoicedrafts",
    "offertutkast": "/quotedrafts",
}

_UTKASTANDRING: dict[str, tuple[str, dict[str, str]]] = {
    "verifikat": ("/voucherdrafts", {
        "datum": "VoucherDate",
        "text": "VoucherText",
        "serie": "NumberSeries",
        "rader": "Rows"
    }),
    "kundfaktura": ("/customerinvoicedrafts", {
        k: k for k in ['Rows', 'InvoiceDate', 'DueDate', 'DeliveryDate', 'YourReference', 'OurReference', 'BuyersOrderReference', 'ElectronicReference', 'InvoiceCustomerName', 'InvoiceAddress1', 'InvoiceAddress2', 'InvoicePostalCode', 'InvoiceCity', 'InvoiceCountryCode', 'DeliveryCustomerName', 'DeliveryAddress1', 'DeliveryAddress2', 'DeliveryPostalCode', 'DeliveryCity', 'DeliveryCountryCode', 'DeliveryMethodName', 'DeliveryTermName', 'DeliveryMethodCode', 'DeliveryTermCode', 'TermsOfPaymentId', 'IncludesVat', 'EuThirdParty', 'IsCreditInvoice']
    }),
    "leverantorsfaktura": ("/supplierinvoicedrafts", {
        k: k for k in ['Rows', 'InvoiceDate', 'DueDate', 'PaymentDate', 'InvoiceNumber', 'OcrNumber', 'Message', 'BankAccountId', 'IsCreditInvoice', 'SkipSendToBank', 'AccountingTemplateId']
    })
}

def bygg_utkastuppdatering(
    nuvarande: dict, andringar: dict, objekttyp: str
) -> dict:
    """Lägger ändringarna ovanpå det NUVARANDE objektet och returnerar hela
    objektet, redo för PUT. Ren funktion, ingen I/O.
    Fail-closed på en nyckel som inte står i ändringsallowlisten.
    Returnerar hela objektet just för att PUT nollar det som utelämnas."""
    if objekttyp not in _UTKASTANDRING:
        giltiga = ", ".join(repr(t) for t in _UTKASTANDRING)
        raise SpirisKlientFel(
            f"Okänd utkasttyp: {objekttyp!r}. Giltiga är: {giltiga}."
        )
    _, allowlist = _UTKASTANDRING[objekttyp]
    if not andringar:
        raise ValueError("Inga ändringar angivna.")

    okanda = [nyckel for nyckel in andringar if nyckel not in allowlist]
    if okanda:
        giltiga = ", ".join(sorted(allowlist))
        raise SpirisKlientFel(
            f"Följande går inte att ändra på ett {objekttyp}utkast: "
            f"{sorted(okanda)}. Ändringsbara fält: {giltiga}."
        )

    uppdaterat = dict(nuvarande)
    for nyckel, varde in andringar.items():
        uppdaterat[allowlist[nyckel]] = varde
    return uppdaterat


def andra_utkast(
    klient: _Spirisklient, typ: str, id: str, andringar: dict
) -> dict:
    """Läser utkastet, lägger på ändringarna och skriver tillbaka HELA
    utkastet."""
    if typ not in _UTKASTANDRING:
        giltiga = ", ".join(repr(t) for t in _UTKASTANDRING)
        raise SpirisKlientFel(f"Okänd utkasttyp: {typ!r}. Giltiga är: {giltiga}.")
    
    prefix, _ = _UTKASTANDRING[typ]
    nuvarande = klient.hamta_en(f"{prefix}/{id}")
    uppdaterat = bygg_utkastuppdatering(nuvarande, andringar, typ)
    try:
        svar = klient.uppdatera(f"{prefix}/{id}", uppdaterat)
    except SpirisKlientFel:
        _logger.error("Kunde inte uppdatera utkast %s (Id=%s).", typ, id)
        raise
    _logger.info(
        "Utkast uppdaterat: %s (Id=%s, fält=%s).",
        typ, id, sorted(andringar)
    )
    return svar


def ta_bort_utkast(klient: _Spirisklient, typ: str, id: str) -> None:
    """Tar bort ett utkast. Oåterkallelig DELETE."""
    if typ not in _UTKASTSLAG:
        giltiga = ", ".join(repr(t) for t in _UTKASTSLAG)
        raise SpirisKlientFel(f"Okänd utkasttyp: {typ!r}. Giltiga är: {giltiga}.")
    
    prefix = _UTKASTSLAG[typ]
    try:
        klient.ta_bort(f"{prefix}/{id}")
    except SpirisKlientFel:
        _logger.error("Kunde inte ta bort utkast %s (Id=%s).", typ, id)
        raise
    _logger.info("Utkast borttaget: %s (Id=%s).", typ, id)


def bokfor_utkast(klient: _Spirisklient, typ: str, id: str) -> dict:
    """Konverterar ett utkast till en bokförd post. Oåterkalleligt."""
    if typ not in _UTKASTSLAG:
        giltiga = ", ".join(repr(t) for t in _UTKASTSLAG)
        raise SpirisKlientFel(f"Okänd utkasttyp: {typ!r}. Giltiga är: {giltiga}.")
    
    prefix = _UTKASTSLAG[typ]
    try:
        # Konvertering görs alltid med POST och tom kropp, per specen U2.3.
        svar = klient.skicka(f"{prefix}/{id}/convert", None)
    except SpirisKlientFel:
        _logger.error("Kunde inte bokföra utkast %s (Id=%s).", typ, id)
        raise
    _logger.info("Utkast bokfört: %s (Id=%s).", typ, id)


def andra_masterdata(
    klient: _Spirisklient, objekttyp: str, objekt_id: str, andringar: dict
) -> dict:
    """Läser objektet, lägger på ändringarna och skriver tillbaka HELA
    objektet.

    Hämtningen sker här och inte när utkastet skapas: objektet är levande
    Spiris-data och kan ha ändrats sedan förslaget lades. Det som
    hashbindningen skyddar är användarens beslut (vad som ska ändras till
    vad), inte objektets övriga innehåll — samma resonemang som för
    uppslagning av kund-id i utfor_utkast."""
    if objekttyp not in _MASTERDATA:
        giltiga = ", ".join(repr(t) for t in _MASTERDATA)
        raise SpirisKlientFel(
            f"Okänd objekttyp: {objekttyp!r}. Giltiga är: {giltiga}."
        )
    prefix, _ = _MASTERDATA[objekttyp]
    nuvarande = klient.hamta_en(f"{prefix}/{objekt_id}")
    _kontrollera_byggmomsforutsattning(objekttyp, nuvarande, andringar)
    uppdaterat = bygg_masterdatauppdatering(nuvarande, andringar, objekttyp)
    try:
        svar = klient.uppdatera(f"{prefix}/{objekt_id}", uppdaterat)
    except SpirisKlientFel:
        _logger.error("Kunde inte uppdatera %s (Id=%s).", objekttyp, objekt_id)
        raise
    # Aldrig fältvärdena i loggen — de kan vara personuppgifter. Bara vilka
    # nycklar som rördes.
    _logger.info(
        "Masterdata uppdaterad: %s (Id=%s, fält=%s).",
        objekttyp, objekt_id, sorted(andringar),
    )
    return svar


def ta_bort_masterdata(
    klient: _Spirisklient, objekttyp: str, objekt_id: str
) -> None:
    """Tar bort ett masterdataobjekt. Klientens enda oåterkalleliga väg.

    Bara kund, leverantör och bankkonto går att ta bort i Spiris. Artiklar och
    projekt saknar DELETE — de INAKTIVERAS i stället (`aktiv=False` via
    andra_masterdata), vilket är rimligt eftersom de refereras från historiska
    poster."""
    if objekttyp not in _BORTTAGBARA:
        giltiga = ", ".join(sorted(_BORTTAGBARA))
        raise SpirisKlientFel(
            f"En {objekttyp} går inte att ta bort i Spiris. Borttagbara: "
            f"{giltiga}. Inaktivera i stället (aktiv=false)."
        )
    prefix, _ = _MASTERDATA[objekttyp]
    try:
        klient.ta_bort(f"{prefix}/{objekt_id}")
    except SpirisKlientFel:
        _logger.error("Kunde inte ta bort %s (Id=%s).", objekttyp, objekt_id)
        raise
    _logger.info("Masterdata borttagen: %s (Id=%s).", objekttyp, objekt_id)


# --- Steg 8: SIE4 in och ut -------------------------------------------------
#
# Två åtgärder med helt olika riskprofil, och de behandlas därefter.
#
# EXPORT är läsande men bär den STÖRSTA läckrisken i hela systemet: en SIE4-fil
# innehåller HELA bokföringen i klartext — varje motpartsnamn, varje
# verifikationstext, möjligen personnummer. Filens INNEHÅLL får därför aldrig
# nå ett MCP-verktyg. Adaptern laddar ner till en lokal, ACL-härdad katalog och
# returnerar bara metadata: namn, storlek, period, sökväg. Inte heller
# `TemporaryUrl` lämnas ut — den är en bärarnyckel till samma innehåll.
#
# IMPORT är den mest ingripande skrivningen i hela API:t: den kan skriva in en
# hel bokföring, öppningsbalanser och årsavslut i ett levande bolag. Den har
# ingen utkastmotsvarighet i Spiris. Därför gäller två saker:
#   - AI:n kan aldrig LEVERERA en fil. Den kan bara peka ut en sökväg, som
#     måste ligga under en katalog användaren själv konfigurerat.
#   - Sammanfattningen människan godkänner räknas fram ur filen med PROJEKTETS
#     EGEN SIE4-parser, inte ur AI:ns beskrivning av den. Utkastgrindens hela
#     premiss är att människan ser vad hon godkänner; en base64-blob är inte
#     något en människa kan granska.

UTKASTTYP_SIE4IMPORT = "sie4import"

UTKASTTYP_UNDERLAGSKOPPLING = "underlagskoppling"
UTKASTTYP_PERIODISERING = "periodisering"
UTKASTTYP_PERIODISERINGSANDRING = "periodiseringsandring"
UTKASTTYP_PERIODISERINGSBORTTAGNING = "periodiseringsborttagning"
UTKASTTYP_KONTO = "konto"
UTKASTTYP_KONTOANDRING = "kontoandring"
UTKASTTYP_BOKFORINGSLAS = "bokforingslas"
UTKASTTYP_ROTRUT = "rotrut"

def bygg_utkast_underlagskoppling(underlag_id: str, dokument_id: str, dokument_typ: str) -> dict:
    return {
        "titel": "Koppla underlag",
        "beskrivning": f"Koppla bilaga {underlag_id} till dokument {dokument_id} ({dokument_typ}).",
        "typ": UTKASTTYP_UNDERLAGSKOPPLING,
        "payload": {
            "DocumentId": dokument_id,
            "AttachmentIds": [underlag_id],
            "DocumentType": dokument_typ
        }
    }


# Sie4Api.Encoding. 1 = Codepage 437, 2 = Codepage 850, 3 = Codepage 1252(?).
# SIE-standarden föreskriver CP437; det är därför standardvärdet här.
SIE4_ENCODING_STANDARD = 1

_EXPORTKATALOG = "sie4export"


def hamta_sie4export_metadata(
    klient: _Spirisklient, fran_datum: str, till_datum: str
) -> dict:
    """Begär en SIE4-export och returnerar Spiris DocumentApi-svar RÅTT.

    Innehåller `TemporaryUrl` — en bärarnyckel till hela bokföringen. Det här
    är därför en INTERN funktion: anroparen är ladda_ner_sie4export lokalt,
    aldrig ett MCP-verktyg."""
    return klient.hamta_en(f"/sie4export/{fran_datum}/{till_datum}")


def ladda_ner_sie4export(
    klient: _Spirisklient, fran_datum: str, till_datum: str,
    hamtare=None,
) -> dict:
    """Laddar ner en SIE4-export till en lokal, ACL-härdad katalog och
    returnerar METADATA — aldrig innehållet, aldrig den temporära URL:en.

    `hamtare` injiceras för testbarhet: den tar en URL och returnerar bytes.
    Standardvägen använder httpx utan Authorization-header — den temporära
    URL:en pekar på ett annat värdnamn och bär sin egen behörighet.

    Filen skrivs under saker_lagring.state_dir(), samma härdning som
    utkastkön, eftersom den bär omaskerade personuppgifter.

    SANDBOX-VERIFIERAT 2026-08-06: exporten går att läsa tillbaka med
    projektets egen parse_sie4 (32 verifikationer, 234 konton ur testbolaget),
    MEN filen saknar #KTYP helt — alla 234 konton kom tillbaka utan kontotyp.
    Följden är att Modul 2 (kontotyp_vakt) inte kan arbeta på en Spiris-export:
    vakten hoppar över konton med typ=None, vilket är fail-closed men gör
    analysen tom. Vill man ha kontotyper får man gå den LIVE-vägen
    (hamta_kontoplan, som läser Type ur /accounts) i stället för via exporten."""
    dokument = hamta_sie4export_metadata(klient, fran_datum, till_datum)
    url = (dokument.get("TemporaryUrl") or "").strip()
    if not url:
        raise SpirisKlientFel(
            "Spiris lämnade ingen nedladdningslänk för SIE4-exporten."
        )

    if hamtare is None:
        def hamtare(lank: str) -> bytes:  # noqa: E306
            import httpx

            try:
                svar = httpx.get(lank, timeout=60.0, follow_redirects=True)
                svar.raise_for_status()
            except httpx.HTTPError as e:
                raise SpirisKlientFel(
                    "Kunde inte hämta SIE4-filen från Spiris."
                ) from e
            return svar.content

    innehall = hamtare(url)

    import saker_lagring

    katalog = saker_lagring.state_dir() / _EXPORTKATALOG
    katalog.mkdir(parents=True, exist_ok=True)
    saker_lagring._begransa_behorighet(katalog)

    namn = (dokument.get("Name") or "").strip() or (
        f"sie4_{fran_datum}_{till_datum}.se"
    )
    # Bara filnamnet — aldrig en sökväg ur ett externt svar.
    namn = Path(namn).name
    mal = katalog / namn
    mal.write_bytes(innehall)

    _logger.info(
        "SIE4-export sparad (%s, %d byte, %s–%s).",
        namn, len(innehall), fran_datum, till_datum,
    )
    return {
        "filnamn": namn,
        "sokvag": str(mal),
        "storlek_byte": len(innehall),
        "period_fran": fran_datum,
        "period_till": till_datum,
    }


def bygg_sie4import_payload(
    sie_innehall: bytes,
    importera_ingaende_balans: bool = False,
    importera_kontonamn: bool = False,
    mappa_konton: bool = False,
    arsavslut: bool = False,
    encoding: int = SIE4_ENCODING_STANDARD,
) -> dict:
    """Bygger en /sie4import-POST-kropp. Ren mappning, ingen I/O.

    Alla fyra flaggorna är FALSE som standard, och det är ett säkerhetsval:
    var och en av dem ändrar bokföringen på ett sätt användaren kanske inte
    avsåg. `arsavslut` (EndYearAdjustment) utför ett årsavslut;
    `importera_ingaende_balans` skriver ingående balanser. Den som vill ha dem
    får begära dem uttryckligen."""
    if not sie_innehall:
        raise ValueError("SIE4-filen är tom.")
    return {
        "SieData": base64.b64encode(sie_innehall).decode("ascii"),
        "Encoding": encoding,
        "MapLedgerAccount": bool(mappa_konton),
        "ImportOpeningBalance": bool(importera_ingaende_balans),
        "EndYearAdjustment": bool(arsavslut),
        "ImportAccountNames": bool(importera_kontonamn),
    }


def importera_sie4(klient: _Spirisklient, payload: dict) -> dict:
    """POSTar en SIE4-import (/sie4import).

    Den mest ingripande skrivningen i hela API:t: den kan skriva in en hel
    bokföring i ett levande bolag, och det finns ingen utkastform och ingen
    ångerväg. Anropas bara efter ett explicit mänskligt godkännande där
    sammanfattningen räknats fram ur FILEN, inte ur en AI-beskrivning."""
    try:
        svar = klient.skicka("/sie4import", payload)
    except SpirisKlientFel:
        _logger.error("SIE4-import misslyckades.")
        raise
    _logger.info("SIE4-import utförd.")
    return svar


def hamta_granskad_mottagare(
    klient: _Spirisklient, typ: str, nyttolast: dict
) -> str:
    """Slår upp den mottagare godkännandevyn ska VISA för en utåtriktad typ.

    Finns för att vyn (rum_render) inte ska behöva veta vilken
    granskningsfunktion varje utkasttyp kräver. Domänkunskapen bor här, i
    adaptern; vyn frågar bara efter en sträng att visa.

    Returnerar tom sträng när mottagaren saknas — ett giltigt tillstånd som
    vyn ska visa som ett hinder, inte som ett fel."""
    if typ == UTKASTTYP_FAKTURAUTSKICK or typ == UTKASTTYP_BETALNINGSPAMINNELSE:
        return hamta_utskicksgranskning(klient, nyttolast["fakturanummer"])["mottagare"]
    if typ == UTKASTTYP_SALJDOKUMENTUTSKICK:
        return hamta_saljdokumentgranskning(
            klient, nyttolast["dokumenttyp"], nyttolast["nummer"]
        )["mottagare"]
    if typ == UTKASTTYP_EFAKTURAUTSKICK:
        return hamta_efakturagranskning(klient, nyttolast["fakturanummer"])["mottagare"]
    raise SpirisKlientFel(f"Typen {typ!r} är inte utåtriktad och har ingen mottagare.")


def hamta_bokforingslas(klient: _Spirisklient) -> dict:
    rå = klient.hamta_en("/companysettings")
    return {
        "last_till_och_med": rå.get("AccountingLockedAsOf"),
        "lasintervall": rå.get("AccountingLockInterval"),
        "skattedeklarationsdatum": rå.get("TaxDeclarationDate")
    }

def hamta_kontoplan_alla(klient: _Spirisklient) -> list[dict]:
    """Kontoplan över alla räkenskapsår (GET /accounts)."""
    rader: list[dict] = []
    for rå in klient.hamta_alla("/accounts"):
        rader.append(
            {
                "kontonr": str(rå["Number"]),
                "kontonamn": str(rå["Name"]),
                "rakenskapsar_id": str(rå["FiscalYearId"]),
                "aktiv": bool(rå["IsActive"]),
                "kontotyp": spiris_typ_till_ktyp(rå.get("Type")),
                "kontotypstext": rå.get("TypeDescription"),
                "momskod_id": rå.get("VatCodeId"),
                "sparrat_for_manuell_bokning": bool(rå.get("IsBlockedForManualBooking", False)),
                "projekt_tillatet": bool(rå.get("IsProjectAllowed", False)),
                "kostnadsstalle_tillatet": bool(rå.get("IsCostCenterAllowed", False)),
            }
        )
    return rader
def hamta_verifikationer_alla(
    klient: _Spirisklient, fran_datum: str | None = None, till_datum: str | None = None
) -> list[dict]:
    """Hämtar alla verifikationer över alla räkenskapsår med datumfiltrering."""
    filter_delar = []
    if fran_datum:
        filter_delar.append(f"VoucherDate ge {fran_datum}T00:00:00.00Z")
    if till_datum:
        filter_delar.append(f"VoucherDate le {till_datum}T23:59:59.00Z")
    
    kwargs = {}
    if filter_delar:
        kwargs["filter"] = " and ".join(filter_delar)
        
    rader: list[dict] = []
    for rå in klient.hamta_alla("/vouchers", **kwargs):
        transaktioner = [mappa_transaktion(r) for r in rå.get("Rows", [])]
        rader.append(
            {
                "datum": rå["VoucherDate"][:10],
                "text": rå.get("VoucherText"),
                "rader": [
                    {
                        "kontonr": t.kontonr,
                        "belopp": t.belopp,
                        "transtext": t.transtext,
                    }
                    for t in transaktioner
                ],
                "id": rå.get("Id"),
                "nummer": rå.get("NumberAndNumberSeries"),
                "serie": rå.get("NumberSeries"),
                "verifikationstyp": rå.get("VoucherType"),
                "andrad": rå.get("ModifiedUtc"),
            }
        )
    return rader

def hamta_kontotransaktioner(klient: _Spirisklient, rakenskapsar_id: str, kontonr: str) -> list[dict]:
    """Alla transaktioner för ett konto under ett räkenskapsår (omaskerat)."""
    rader = []
    for rå in klient.hamta_alla(f"/vouchers/{rakenskapsar_id}"):
        ver = mappa_verifikation(rå)
        for tr in ver.transaktioner:
            if tr.kontonr == kontonr:
                rader.append({
                    "plats": f"serie={ver.serie} vernr={ver.vernr}",
                    "verdatum": str(ver.verdatum),
                    "transtext": tr.transtext or "",
                    "belopp": tr.belopp,
                })
    return rader

def hamta_kontosaldon(klient: _Spirisklient, rakenskapsar_id: str, tom_datum: str) -> list[dict]:
    """Ackumulerat utgående saldo (YTD) per konto fram till tom_datum (omaskerat)."""
    konton = {}
    for rå in klient.hamta_alla(f"/accounts/{rakenskapsar_id}"):
        konto = mappa_konto(rå)
        konton[konto.kontonr] = konto
        
    utgaende_balanser, resultat = mappa_saldon(klient.hamta_alla(f"/accountbalances/{tom_datum}"))
    
    data = []
    for post in list(utgaende_balanser) + list(resultat):
        konto = konton.get(post.kontonr)
        data.append({
            "kontonr": post.kontonr,
            "kontonamn": konto.namn if konto else "",
            "saldo": post.saldo,
        })
    return data

def hamta_momsoversikt(klient: _Spirisklient, per_datum: str) -> dict:
    """Omaskerad momsöversikt beräknad ur kontosaldon."""
    from decimal import Decimal
    rader = klient.hamta_alla(f"/accountbalances/{per_datum}")
    konton = [
        {
            "kontonr": str(rad["AccountNumber"]),
            "kontonamn": rad.get("AccountName", ""),
            "saldo": Decimal(str(rad.get("Balance", 0))),
        }
        for rad in rader
    ]
    from fpa_motor import bygg_momsoversikt
    return bygg_momsoversikt(konton, per_datum)

def mappa_periodisering(p: dict) -> dict:
    if not p:
        return {}
    mappad = {
        "id": p.get("Id"),
        "bokforingsdatum": p.get("BookkeepingDate"),
        "belopp": Decimal(str(p.get("Amount", 0))),
        "ar_kredit": p.get("IsCredit"),
        "debetkonto": p.get("DebitAccountNumber"),
        "kreditkonto": p.get("CreditAccountNumber"),
        "beskrivning": p.get("Description"),
        "status": p.get("Status"),
        "kalldatum": p.get("SourceDate"),
        "verifikationsnummer": p.get("NumberAndNumberSeries"),
        "kalltyp": p.get("AllocationPeriodSourceType"),
        "projekt_id": p.get("ProjectId"),
        "verifikat_id": p.get("VoucherId"),
        "leverantorsfaktura_id": p.get("SupplierInvoiceId"),
        "kundfaktura_id": p.get("CustomerInvoiceId"),
    }
    # U3.1 säger att Rows -> rader (REQ), så de måste mappas.
    # AllocationPeriodRowApi har ingen spec given i U3.1 men vi kan anta att det har några fält
    # U3.1 säger: "Radnummerfälten (*Row), CostCenterItemId1-3, VoucherFiscalYearId,
    # utkast-id:na och CreatedUtc/ModifiedUtc tas inte med."
    if "Rows" in p:
        rader = []
        for r in p["Rows"]:
            rad_mappad = {
                "id": r.get("Id"),
                "bokforingsdatum": r.get("BookkeepingDate"),
                "belopp": Decimal(str(r.get("Amount", 0)))
            }
            # Filtrera None
            rader.append({k: v for k, v in rad_mappad.items() if v is not None})
        mappad["rader"] = rader

    return {k: v for k, v in mappad.items() if v is not None}

def hamta_periodiseringar(klient: _Spirisklient) -> list[dict]:
    return [mappa_periodisering(p) for p in klient.hamta_alla("/allocationperiods")]


def hamta_ingaende_balans(klient: _Spirisklient) -> list[dict]:
    """Ingående balanser."""
    rader: list[dict] = []
    for rå in klient.hamta_alla("/fiscalyears/openingbalances"):
        rader.append(
            {
                "kontonr": str(rå["Number"]),
                "kontonamn": rå.get("Name", ""),
                "saldo": rå["Balance"],
            }
        )
    return rader
_ENKELUPPSLAG: dict[str, str] = {
    "kundfaktura":            "/customerinvoices",
    "leverantorsfaktura":     "/supplierinvoices",
    "order":                  "/orders",
    "offert":                 "/quotes",
    "kund":                   "/customers",
    "leverantor":             "/suppliers",
    "artikel":                "/articles",
    "projekt":                "/projects",
    "momsrapport":            "/vatreports",
    "offertutkast":           "/quotedrafts",
    "verifikatutkast":        "/voucherdrafts",
    "kundfakturautkast":      "/customerinvoicedrafts",
    "leverantorsfakturautkast": "/supplierinvoicedrafts",
    "periodiseringar":        "/allocationperiods",
    "bokforingslas":          "/companysettings",
    "rotrut":                 "/companysettings/rotrut",
}

class _EnkelKlient:
    def __init__(self, rå: dict):
        self.rå = rå
    def hamta_alla(self, path: str, **kwargs) -> list[dict]:
        return [self.rå]
    def hamta_en(self, path: str, **kwargs) -> dict:
        return self.rå

def hamta_ett(klient: _Spirisklient, typ: str, objekt_id: str) -> dict:
    """Rått enkeluppslag för djupfelsökning."""
    if not objekt_id or not objekt_id.strip():
        raise ValueError("objekt_id får inte vara tomt")
    if typ not in _ENKELUPPSLAG:
        raise ValueError(f"okänd typ: {typ}")
    
    rå = klient.hamta_en(f"{_ENKELUPPSLAG[typ]}/{objekt_id}")
    fk = _EnkelKlient(rå)
    
    if typ == "bokforingslas": return hamta_bokforingslas(fk)
    if typ == "kundfaktura": return hamta_kundfakturor(fk)[0]
    if typ == "leverantorsfaktura": return hamta_leverantorsfakturor(fk)[0]
    if typ == "order": return hamta_order(fk)[0]
    if typ == "offert": return hamta_offerter(fk)[0]
    if typ == "offertutkast": return hamta_offertutkast(fk)[0]
    if typ == "kund": return hamta_kunder(fk)[0]
    if typ == "leverantor": return hamta_leverantorer(fk)[0]
    if typ == "artikel": return hamta_artiklar(fk)[0]
    if typ == "projekt": return hamta_projekt(fk)[0]
    if typ == "momsrapport": return hamta_momsrapporter(fk)[0]
    if typ == "verifikatutkast": return {"verifikat": mappa_verifikatutkast(rå)}
    if typ in ("kundfakturautkast", "leverantorsfakturautkast"): return rå
    if typ == "periodiseringar": return {"periodisering": mappa_periodisering(rå)}
    return rå
def hamta_valutakurs(klient: _Spirisklient, datum: str, fran_valuta: str, till_valuta: str) -> dict:
    rå = klient.hamta_en("/currencies/exchangerate", params={"date": datum, "sourceCurrency": fran_valuta, "targetCurrency": till_valuta})
    return {
        "datum": rå.get("Date"),
        "fran_valuta": rå.get("SourceCurrency"),
        "till_valuta": rå.get("TargetCurrency"),
        "kurs": rå.get("Rate"),
    }

def hamta_anlaggningstillgangar(klient: _Spirisklient) -> list[dict]:
    etikett = skapa_kontonamnsmaskerare(las_namnreferens())
    rader = []
    for rå in klient.hamta_alla("/inventoryitems"):
        rader.append({
            "nummer": rå.get("Number"),
            "benamning": etikett(rå.get("Name") or ""),
            "anskaffningsvarde": rå.get("PurchasePrice"),
            "anskaffningsdatum": str(rå.get("PurchaseDate"))[:10] if rå.get("PurchaseDate") else None,
            "bokfort_varde": rå.get("CurrentValue"),
            "restvarde": rå.get("ResidualValue"),
            "livslangd_manader": rå.get("LifeSpanInMonths"),
            "senaste_avskrivning": str(rå.get("LatestDepreciationDate"))[:10] if rå.get("LatestDepreciationDate") else None,
            "status": rå.get("InventoryItemStatus"),
        })
    return rader

def hamta_kundreskontraposter(klient: _Spirisklient) -> list[dict]:
    rader = []
    for rå in klient.hamta_alla("/customerledgeritems"):
        rader.append({
            "kund_id": rå.get("CustomerId"),
            "fakturanr": rå.get("InvoiceNumber"),
            "fakturadatum": str(rå.get("InvoiceDate"))[:10] if rå.get("InvoiceDate") else None,
            "forfallodatum": str(rå.get("DueDate"))[:10] if rå.get("DueDate") else None,
            "belopp": rå.get("TotalAmountInvoiceCurrency"),
            "kvarvarande": rå.get("RemainingAmountInvoiceCurrency"),
            "ar_kredit": bool(rå.get("IsCreditInvoice", False)),
            "valuta": rå.get("CurrencyCode"),
            "verifikat_id": rå.get("VoucherId"),
            "id": rå.get("Id"),
            "betalreferens": rå.get("PaymentReferenceNumber"),
        })
    return rader

def hamta_anvandare(klient: _Spirisklient) -> list[dict]:
    vakt = _bygg_namnvakt()
    rader = []
    for rå in klient.hamta_alla("/users"):
        namn = f"{rå.get('FirstName', '')} {rå.get('LastName', '')}".strip()
        visat, _ = _motpartsnamn(namn, "", False, vakt)
        rader.append({
            "id": rå.get("Id"),
            "namn": visat,
            "aktiv": bool(rå.get("IsActive", False)),
            "ar_konsult": bool(rå.get("IsConsultant", False)),
            "far_attestera_leverantorsfakturor": bool(rå.get("HasPurchaseInvoicesApprovalPermission", False)),
            "far_attestera_momsrapporter": bool(rå.get("HasVATReportsApprovalPermission", False)),
        })
    return rader


def hamta_underlag(klient, include_matched: bool = False) -> list[dict]:
    return klient.hamta_alla("/attachments", params={"includeMatched": str(include_matched).lower()})

def hamta_underlag_fil(klient, underlag_id: str) -> tuple[dict, bytes]:
    url = f"https://eaccountingapi.vismaonline.com/v2/attachments/{underlag_id}"
    meta, content = klient.hamta_binart(url)
    
    if len(content) > 25 * 1024 * 1024:
        from parser.spiris_klient import SpirisKlientFel
        raise SpirisKlientFel("Underlaget är större än 25 MB och kan inte laddas ner.")
        
    return meta, content


def _bygg_betalningsverifikat_payload(nyttolast: dict) -> dict:
    return {
        "VoucherDate": nyttolast["transaktionsdatum"],
        "VoucherText": nyttolast["beskrivning"],
        "Rows": [
            {
                "AccountNumber": int(rad["konto"]),
                "DebitAmount": Decimal(str(rad.get("debet") or 0)),
                "CreditAmount": Decimal(str(rad.get("kredit") or 0)),
                "TransactionText": rad.get("text") or "",
            }
            for rad in nyttolast["rader"]
        ],
    }

def skapa_betalningsverifikat(klient: _Spirisklient, payload: dict) -> dict:
    return klient.skicka("/voucherwithoverunderpayment", payload)

def skapa_kvittning(klient: _Spirisklient, kreditfaktura_id: str, payload: dict) -> dict:
    ogiltiga = set(payload.keys()) - {"DebitInvoiceIds", "VoucherDate"}
    if ogiltiga:
        raise SpirisKlientFel(f"Endast DebitInvoiceIds och VoucherDate får skickas. Felaktiga nycklar: {ogiltiga}")
        
    debet_ids = payload.get("DebitInvoiceIds", [])
    if not debet_ids:
        raise SpirisKlientFel("DebitInvoiceIds får inte vara tom.")

    # Hämtningen görs vid utförandet, inte när förslaget läggs
    kandidater = hamta_kvittningskandidater(klient, kreditfaktura_id)
    kandidat_ids = {str(k.get("Id", "")) for k in kandidater}

    for d_id in debet_ids:
        if str(d_id) not in kandidat_ids:
            raise SpirisKlientFel(f"Debetfakturan {d_id} är inte en giltig kvittningskandidat.")

    return klient.skicka(f"/supplierinvoices/{kreditfaktura_id}/offset", payload)

def hamta_kvittningskandidater(klient: _Spirisklient, faktura_id: str) -> list[dict]:
    return klient.hamta_alla(f"/supplierinvoices/{faktura_id}/offsetcandidates")


def bygg_periodiseringspayload(nyttolast: dict) -> list[dict]:
    """Bygger payload för POST /allocationperiods (eller PUT)."""
    from decimal import Decimal
    if "antal_perioder" not in nyttolast or int(nyttolast["antal_perioder"]) < 1:
        raise ValueError("antal_perioder saknas eller är mindre än 1")
    if "belopp" not in nyttolast or Decimal(nyttolast["belopp"]) <= 0:
        raise ValueError("belopp saknas eller är inte större än 0")
        
    p = {
        "BookkeepingStartDate": nyttolast["startdatum"],
        "AmountToAllocate": nyttolast["belopp"],
        "AllocationAccountNumber": nyttolast["konto"],
        "NumberOfAllocationPeriods": nyttolast["antal_perioder"],
    }
    
    # Exakt ett kopplingspar krävs (noll eller två -> ValueError)
    pairs = 0
    if "VoucherId" in nyttolast and "VoucherRow" in nyttolast:
        p["VoucherId"] = nyttolast["VoucherId"]
        p["VoucherRow"] = nyttolast["VoucherRow"]
        pairs += 1
    if "SupplierInvoiceId" in nyttolast and "SupplierInvoiceRow" in nyttolast:
        p["SupplierInvoiceId"] = nyttolast["SupplierInvoiceId"]
        p["SupplierInvoiceRow"] = nyttolast["SupplierInvoiceRow"]
        pairs += 1
    if "SupplierInvoiceDraftId" in nyttolast and "SupplierInvoiceDraftRow" in nyttolast:
        p["SupplierInvoiceDraftId"] = nyttolast["SupplierInvoiceDraftId"]
        p["SupplierInvoiceDraftRow"] = nyttolast["SupplierInvoiceDraftRow"]
        pairs += 1
        
    if pairs != 1:
        raise ValueError("Exakt ett kopplingspar krävs (t.ex. VoucherId och VoucherRow).")
        
    return [p]


UNDERLAG_DOKUMENTTYPER: dict[str, tuple[str, str]] = {
    "Leverantörsfaktura": ("SupplierInvoice", "hamta_leverantorsfakturor"),
    "Verifikat": ("Voucher", "hamta_verifikationer_alla"),
}

def bygg_underlagskopplingspayload(underlag_id: str, dokument_id: str, dokument_typ: str) -> dict:
    """Bygger nyttolasten för attachmentlinks."""
    return {
        "DocumentId": dokument_id,
        "AttachmentIds": [underlag_id],
        "DocumentType": dokument_typ
    }

def hamta_en_verifikation(klient: _Spirisklient, rakenskapsar_id: str, verifikat_id: str) -> dict:
    """U17.1 — GET /vouchers/{fiscalyearId}/{voucherId}"""
    if not rakenskapsar_id or not verifikat_id:
        raise ValueError("Både rakenskapsar_id och verifikat_id måste anges")
    rå = klient.hamta_en(f"/vouchers/{rakenskapsar_id}/{verifikat_id}")
    return mappa_verifikation(rå)


def hamta_en_bankhandelse(klient: _Spirisklient, bankkonto_id: str, handelse_id: str) -> dict:
    """U17.2 — GET /banktransactions/{bankAccountId}/{bankTransactionId}"""
    if not bankkonto_id or not handelse_id:
        raise ValueError("Både bankkonto_id och handelse_id måste anges")
    h = klient.hamta_en(f"/banktransactions/{bankkonto_id}/{handelse_id}")
    
    konteringar = []
    for r in h.get("Rows") or []:
        konteringar.append({
            "verifikat_id": r.get("VoucherId"),
            "verifikatnummer": str(r.get("PaymentVoucherNumber") or ""),
            "belopp": r.get("AmountTransactionCurrency"),
            "kalla": r.get("Source"),
        })

    datum = str(h.get("TransactionDate") or "")[:10]
    return {
        "id": h["Id"],
        "datum": datum,
        "avstamd": bool(h.get("IsReconciled", False)),
        "belopp": h.get("TransactionAmount"),
        "originalbelopp": h.get("OriginalAmount"),
        "avgift": h.get("ChargeAmount"),
        "valuta": h.get("TransactionAmountCurrency") or "",
        "antal_konteringsrader": len(konteringar),
        "konteringar": konteringar,
    }


def hamta_prislistor(k, prislista_id: str | None = None) -> list[dict]:
    """U16.1 — spiris_prislistor"""
    if not prislista_id:
        rader = k.hamta_alla("/salespricelists")
        res = []
        for r in rader:
            res.append({
                "Id": r.get("Id"),
                "Name": r.get("Name"),
                "Number": r.get("Number"),
                "CurrencyCode": r.get("CurrencyCode"),
                "IsStandard": r.get("IsStandard"),
                "IsActive": r.get("IsActive"),
            })
        return res
    else:
        rader = k.hamta_alla(f"/salespricelists/prices/{prislista_id}")
        res = []
        for r in rader:
            res.append({
                "SalesPriceListId": r.get("SalesPriceListId"),
                "ArticleId": r.get("ArticleId"),
                "NetPrice": str(r.get("NetPrice")) if r.get("NetPrice") is not None else None,
                "GrossPrice": str(r.get("GrossPrice")) if r.get("GrossPrice") is not None else None,
                "CurrencyCode": r.get("CurrencyCode"),
            })
        return res


def hamta_rabattavtal(k) -> list[dict]:
    """U16.2 — spiris_rabattavtal"""
    rader = k.hamta_alla("/discountagreements")
    res = []
    for r in rader:
        res.append({
            "Id": r.get("Id"),
            "Name": r.get("Name"),
            "Number": r.get("Number"),
            "IsActive": r.get("IsActive"),
        })
    return res


def hamta_etiketter(k, typ: str) -> list[dict]:
    """U16.3 — spiris_etiketter"""
    if typ not in ("kund", "artikel"):
        raise ValueError(f"Okänd etiketttyp: {typ}. Måste vara 'kund' eller 'artikel'.")
        
    ep = "/customerlabels" if typ == "kund" else "/articlelabels"
    rader = k.hamta_alla(ep)
    res = []
    for r in rader:
        res.append({
            "Id": r.get("Id"),
            "Name": r.get("Name"),
            "Description": r.get("Description"),
        })
    return res
