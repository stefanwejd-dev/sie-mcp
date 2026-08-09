"""test_sekretess_lackprobe.py — bevis för att de fyra dokumenterade
klartextläckorna är stängda, hela vägen ut genom MCP-verktygen.

Bakgrunden: säkerhetsgenomgången 2026-08-03
hittade fyra hål där personuppgifter
nådde den externa AI:n i klartext, tre av dem TYST — utan blockering, flagga
eller räkning i `antal_exkluderade`. Åtgärderna (paket A och B) är implementerade,
men fanns länge dokumenterade som oimplementerade i statusdokumentet. Den här
sviten finns för att den frågan aldrig mer ska behöva avgöras genom att läsa en
statusruta: den kör verktygen och tittar på det faktiska utflödet.

Två saker prövas, och båda måste hålla:

1. **Ingen råtext i utflödet.** Varje läckkategori planteras i företagsnamn,
   kontonamn, verifikationstext och transaktionstext, och får inte förekomma i
   det serialiserade svar som MCP-klienten (= en extern AI) tar emot.
2. **Tystnaden är borta.** Det som hålls tillbaka ska räknas i
   `antal_exkluderade`. En läcka som stoppas men inte redovisas var halva
   ursprungsfyndet.

Läser någon detta för att uppdatera DISCLAIMER_AND_TERMS.md §6 eller
DATASKYDD.md §2.4: testet är facit för vad som är stängt. Avsnitt 6 i specen
listar vad som medvetet INTE täcks — de fallen prövas separat längst ned, som
dokumentation av kända begränsningar, inte som krav.
"""

from __future__ import annotations

import asyncio
import json
from decimal import Decimal

import pytest

import compliance
import mcp_server.server as server_modul
import sekretesslager
from mcp_server.server import (
    spiris_artiklar,
    spiris_balansrapport,
    spiris_bankkonton,
    spiris_dashboard,
    spiris_foretagsinfo,
    spiris_kassaflodesanalys,
    spiris_kontoplan,
    spiris_kontosaldon,
    spiris_kontotransaktioner,
    spiris_kundbetalbeteende,
    spiris_kundreskontra,
    spiris_leverantorsfakturor,
    spiris_leverantorsreskontra,
    spiris_momskoder,
    spiris_momsoversikt,
    spiris_momsrapporter,
    spiris_offerter,
    spiris_order,
    spiris_rakenskapsar,
    spiris_resultatrapport,
    spiris_sok_verifikationer,
)

# Luhn-giltiga testnummer (spec §10) — ett påhittat nummer faller på
# kontrollsiffran och ser då ut som en läcka fastän lagret fungerar.
LACKKATEGORIER = {
    "kyrilliskt_namn": "Владимир Петров",
    "kinesiskt_namn": "李明",
    "arabiskt_namn": "محمد علي",
    "grekiskt_namn": "Γεώργιος Παπαδόπουλος",
    "polsk_diakrit": "Krzysztof Wiśniewski",
    "samordningsnummer": "8506751232",
    "kortnummer": "4539578763621486",
    "genitiv": "Anderssons",
}

_COMPANY = {
    "Name": f"{LACKKATEGORIER['kyrilliskt_namn']} AB",
    "CorporateIdentityNumber": "556677-8899",
}
_ACCOUNTS = [
    {"Number": "1910", "Name": "Kassa", "Type": 9},
    {"Number": "1510", "Name": f"Fordran {LACKKATEGORIER['polsk_diakrit']}", "Type": 5},
    {"Number": "3041", "Name": f"Intäkt {LACKKATEGORIER['kinesiskt_namn']}", "Type": 20},
]
_BALANCES = [
    {"AccountNumber": 1910, "AccountName": "Kassa", "Balance": Decimal("500.00")},
    {"AccountNumber": 1510, "AccountName": f"Fordran {LACKKATEGORIER['polsk_diakrit']}",
     "Balance": Decimal("1000.00")},
    {"AccountNumber": 3041, "AccountName": f"Intäkt {LACKKATEGORIER['arabiskt_namn']}",
     "Balance": Decimal("-1500.00")},
]
_VOUCHERS = [{
    "NumberAndNumberSeries": "A1", "NumberSeries": "A", "VoucherDate": "2026-01-05",
    "VoucherText": (
        f"Faktura {LACKKATEGORIER['grekiskt_namn']}, {LACKKATEGORIER['genitiv']} hyra"
    ),
    "CreatedUtc": "2026-01-05T00:00:00Z",
    "Rows": [
        {"AccountNumber": 1510, "DebitAmount": Decimal("1000.00"),
         "CreditAmount": Decimal("0"),
         "TransactionText": (
             f"Konsult {LACKKATEGORIER['kyrilliskt_namn']} "
             f"pnr {LACKKATEGORIER['samordningsnummer']}"
         )},
        {"AccountNumber": 3041, "DebitAmount": Decimal("0"),
         "CreditAmount": Decimal("1000.00"),
         "TransactionText": (
             f"Kortköp {LACKKATEGORIER['kortnummer']} "
             f"till {LACKKATEGORIER['kinesiskt_namn']}"
         )},
    ],
}]


# Reskontrans motparter: en fysisk person, ett namn i obedömbar skrift och ett
# bolag med giltigt org.nr. De två första ska pseudonymiseras av
# reskontra_tvatt, det tredje får stå kvar (juridisk person är inte en
# personuppgift).
_SUPPLIERS = [
    {"Name": LACKKATEGORIER["kyrilliskt_namn"], "CorporateIdentityNumber": "",
     "SupplierNumber": "L1", "Id": "sup-1"},
    {"Name": "Scandinavian Photo AB", "CorporateIdentityNumber": "5566778899",
     "SupplierNumber": "L2", "Id": "sup-2"},
]
# Joinen sker på SupplierId och beloppet läses ur RemainingAmount (se
# spiris_adapter.bygg_reskontra_rader) — inte SupplierNumber/Balance.
_SUPPLIER_INVOICES = [
    {"SupplierId": "sup-1", "RemainingAmount": Decimal("700"),
     "PaymentStatus": 1, "DueDate": "2026-07-01", "InvoiceNumber": "F1"},
    {"SupplierId": "sup-2", "RemainingAmount": Decimal("1000"),
     "PaymentStatus": 1, "DueDate": "2026-07-15", "InvoiceNumber": "F2"},
]
_CUSTOMERS = [
    {"Name": LACKKATEGORIER["polsk_diakrit"], "OrganisationNumber": "",
     "CustomerNumber": "K1", "Id": "cus-1"},
]
_CUSTOMER_INVOICES = [
    {"CustomerId": "cus-1", "CustomerNumber": "K1", "Total": Decimal("500"),
     "RemainingAmount": Decimal("500"), "PaymentStatus": 1,
     "DueDate": "2026-07-10", "InvoiceNumber": "KF1"},
    {"CustomerId": "cus-1", "CustomerNumber": "K1", "Total": Decimal("300"),
     "RemainingAmount": Decimal("0"), "PaymentStatus": 0,
     "DueDate": "2026-05-10", "PaymentDate": "2026-05-14", "InvoiceNumber": "KF2"},
]
_ARTICLE_CODINGS = [{"Id": "cod-1", "DomesticSalesSubjectToVatAccountNumber": 3041}]
# Artikelnamn är fritext bolaget sätter — samma PII-risk som kontonamn.
_ARTICLES = [
    {"Id": "art-1", "Number": "10", "Name": f"Konsult {LACKKATEGORIER['kyrilliskt_namn']}",
     "NetPrice": 1500, "UnitName": "tim", "CodingId": "cod-1"},
]
# Steg 3: läckkategorierna planteras även i order, offert och bankkonto.
_ORDERS = [{"Number": "O1", "CustomerName": LACKKATEGORIER["grekiskt_namn"],
            "CustomerIsPrivatePerson": False, "OrderDate": "2026-07-05",
            "Amount": Decimal("100"), "VatAmount": Decimal("25"), "Status": 1,
            "CurrencyCode": "SEK", "Rows": [],
            "Persons": [{"Ssn": LACKKATEGORIER["samordningsnummer"]}],
            "HouseWorkPropertyName": "Villan 1:2", "InvoiceAddress1": "Storgatan 1"}]
_QUOTES = [{"QuoteNumber": "Q1", "CustomerName": LACKKATEGORIER["kinesiskt_namn"],
            "CustomerIsPrivatePerson": True, "QuoteDate": "2026-07-06",
            "Amount": Decimal("50"), "VatAmount": Decimal("12"), "Status": 1,
            "CurrencyCode": "SEK", "Rows": []}]
_BANKACCOUNTS = [{"Name": f"Konto {LACKKATEGORIER['polsk_diakrit']}",
                  "LedgerAccountNumber": "1930", "CurrencyCode": "SEK",
                  "Balance": {"Balance": Decimal("1")},
                  "Iban": "SE4550000000058398257466"}]
_VATCODES = [{"Code": "SE25", "Description": "Moms", "VatRate": Decimal("0.25")}]
_VATREPORTS = []
_FISCALYEARS = [
    {"Id": "fy-2026", "StartDate": "2026-01-01", "EndDate": "2026-12-31"},
]


class _FejkKlientMedLackor:
    def __init__(self) -> None:
        self.access_token = "AT"
        self.refresh_token = "RT"

    def hamta_en(self, path, params=None):
        if path == "/companysettings":
            return _COMPANY
        raise AssertionError(f"oväntad hamta_en: {path}")

    def hamta_alla(self, path, params=None):
        if path.startswith("/accounts/"):
            return _ACCOUNTS
        if path.startswith("/accountbalances/"):
            return _BALANCES
        if path.startswith("/vouchers/"):
            return _VOUCHERS
        if path == "/fiscalyears":
            return _FISCALYEARS
        if path == "/suppliers":
            return _SUPPLIERS
        if path == "/supplierinvoices":
            return _SUPPLIER_INVOICES
        if path == "/orders":
            return _ORDERS
        if path == "/quotes":
            return _QUOTES
        if path == "/bankaccounts":
            return _BANKACCOUNTS
        if path == "/vatcodes":
            return _VATCODES
        if path == "/vatreports":
            return _VATREPORTS
        if path == "/articles":
            return _ARTICLES
        if path == "/articleaccountcodings":
            return _ARTICLE_CODINGS
        if path == "/customers":
            return _CUSTOMERS
        if path == "/customerinvoices":
            return _CUSTOMER_INVOICES
        raise AssertionError(f"oväntad hamta_alla: {path}")


@pytest.fixture(autouse=True)
def _godkanda_villkor():
    compliance.godkann_compliance()


@pytest.fixture
def mcp_svar(monkeypatch, tmp_path):
    """Kör varje Spiris-verktyg mot den planterade datan och returnerar
    {verktygsnamn: serialiserat svar} — exakt det MCP-klienten skulle få."""
    monkeypatch.chdir(tmp_path)  # isolera revisionslogg/namnreferens från repo-roten
    monkeypatch.setattr(server_modul, "bygg_klient", lambda: _FejkKlientMedLackor())
    monkeypatch.setattr(server_modul, "spara_session", lambda k: None)
    return {
        "spiris_kontosaldon": asyncio.run(spiris_kontosaldon("fy-2026", "2026-12-31")),
        "spiris_kontotransaktioner": asyncio.run(
            spiris_kontotransaktioner("fy-2026", "3041")
        ),
        "spiris_sok_verifikationer": asyncio.run(
            spiris_sok_verifikationer("fy-2026", "faktura")
        ),
        "spiris_resultatrapport": asyncio.run(
            spiris_resultatrapport("2026-01-01", "2026-12-31")
        ),
        "spiris_balansrapport": asyncio.run(spiris_balansrapport("2026-12-31")),
        # Steg 1: de nya läsande vägarna prövas mot samma läckkategorier.
        "spiris_kassaflodesanalys": asyncio.run(
            spiris_kassaflodesanalys("2026-01-01", "2026-12-31")
        ),
        "spiris_dashboard": asyncio.run(spiris_dashboard("2026-01-01", "2026-12-31")),
        "spiris_rakenskapsar": asyncio.run(spiris_rakenskapsar()),
        "spiris_kontoplan": asyncio.run(spiris_kontoplan("fy-2026")),
        "spiris_foretagsinfo": asyncio.run(spiris_foretagsinfo()),
        "spiris_artiklar": asyncio.run(spiris_artiklar()),
        "spiris_leverantorsfakturor": asyncio.run(spiris_leverantorsfakturor()),
        "spiris_order": asyncio.run(spiris_order()),
        "spiris_offerter": asyncio.run(spiris_offerter()),
        "spiris_bankkonton": asyncio.run(spiris_bankkonton()),
        "spiris_momskoder": asyncio.run(spiris_momskoder()),
        "spiris_momsrapporter": asyncio.run(spiris_momsrapporter()),
        "spiris_momsoversikt": asyncio.run(spiris_momsoversikt("2026-12-31")),
        "spiris_leverantorsreskontra": asyncio.run(spiris_leverantorsreskontra()),
        "spiris_kundreskontra": asyncio.run(spiris_kundreskontra()),
        "spiris_kundbetalbeteende": asyncio.run(spiris_kundbetalbeteende()),
    }


# --- 1. Ingen råtext i något MCP-utflöde ------------------------------------


@pytest.mark.parametrize("kategori,ratext", sorted(LACKKATEGORIER.items()))
def test_ingen_lackkategori_nar_mcp_klienten(kategori, ratext, mcp_svar):
    for verktyg, svar in mcp_svar.items():
        serialiserat = json.dumps(svar, ensure_ascii=False, default=str)
        assert ratext not in serialiserat, (
            f"{verktyg} läckte {kategori} ({ratext!r}) i klartext till MCP-klienten"
        )


def test_blockerade_poster_redovisas_istallet_for_att_forsvinna_tyst(mcp_svar):
    """Tystnaden var halva ursprungsfyndet: data hölls tillbaka utan att
    räknas. Verifikatet med obedömbar skrift ska nu synas i räknaren."""
    transaktioner = mcp_svar["spiris_kontotransaktioner"]
    assert transaktioner["antal_exkluderade"] >= 1
    assert transaktioner["data"] == []


# --- 2. Lagren var för sig (snabb lokalisering när något går sönder) --------


def _falt(text: str, referenslista: set[str] | None = None) -> str:
    return sekretesslager._maskera_identifierande_falt(
        text, sekretesslager._Tokengenerator(), referenslista or set()
    )


@pytest.mark.parametrize(
    "text",
    [
        "Fordran Krzysztof Wiśniewski",   # A1: diakrit utanför latinsk grundklass
        "Konsult Jiří Novák",
        "Lön Ģirts Bērziņš",
    ],
)
def test_a1_diakriter_maskeras_helt_inte_delvis(text):
    ut = _falt(text)
    assert "PERSON" in ut
    # Den ursprungliga buggen gav PARTIELL maskering ('PERSON_1śniewski'):
    # efternamnets svans blev kvar. Inget ord ur originalet får finnas kvar.
    for ord_ in text.split()[1:]:
        assert ord_ not in ut


@pytest.mark.parametrize("text", ["Fordran 李明", "Leverantör محمد علي", "Betalning 한국"])
def test_a2_obedombar_skrift_far_egen_tokentyp(text):
    assert sekretesslager.MOTPART_TOKENTYP in _falt(text)


@pytest.mark.parametrize("text", ["Konsult Владимир Петров", "Fordran 李明"])
def test_a3_obedombar_skrift_blockerar_i_chatten(text):
    """Invariant 1: fritext FLAGGAR (blockerar verifikatet), fält MASKERAR."""
    assert sekretesslager.maskera_chattmeddelande(text).misstänkta_namn


def test_a4_samordningsnummer_utan_separator():
    assert "PERSONNUMMER" in _falt("Fordran 8506751232")
    assert "PERSONNUMMER" in _falt("Fordran 850675-1232")


def test_a5_genitiv_och_stabila_tokens():
    referens = {"Anna Andersson", "Andersson", "Anna", "Lars", "Larsson"}
    assert "Anderssons" not in _falt("Faktura Anderssons bil", referens)

    # Samma person → samma token; olika personer → olika token. Delad generator,
    # så räknaren nollställs inte mellan raderna.
    tokens = sekretesslager._Tokengenerator()
    rader = [
        sekretesslager._maskera_identifierande_falt(t, tokens, referens)
        for t in ("Lön Anna Andersson", "Lön Lars Larsson", "Lön Anna Andersson")
    ]
    assert rader[0] == rader[2], "samma person måste få samma token"
    assert rader[0] != rader[1], "två personer får aldrig dela token"


@pytest.mark.parametrize(
    "text", ["Kortköp 4539 5787 6362 1486", "Kortköp 4539-5787-6362-1486",
             "Kortköp 4539578763621486"]
)
def test_a6_kortnummer(text):
    assert "KORTNUMMER" in _falt(text)


def test_a7_utlandskt_telefonnummer():
    assert "TELEFON" in _falt("Ring +49 30 123456")


# --- 3. Inga nya falska träffar --------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "Omsättning 1 000 000 000 kr",
        "Faktura 2026-0456 förfaller",
        "Perioden 2026-07 22 000 kr",
        "1930 Företagskonto",
        "Belopp 1 234 5678 9012 3456 kr",  # Luhn faller — får inte bli kortnummer
    ],
)
def test_ekonomisk_text_ar_ororad(text):
    assert _falt(text) == text


# --- 4. Kända begränsningar (dokumentation, inte krav) ----------------------


@pytest.mark.parametrize(
    "text", ["Lön XERXES QOOLIO", "Lön xerxes qoolio", "Lön A. Svensson", "Lön Xerxes"]
)
def test_dokumenterade_begransningar_kvarstar(text):
    """Versala/gemena namn, initial + efternamn och mononymer fångas INTE.

    Testet påstår inte att detta är önskvärt — det låser fast vad DISCLAIMER
    §6 och DATASKYDD §2.4 måste fortsätta upplysa om. Ändras beteendet ska
    dokumentationen ändras i samma commit, och det här testet med den.
    """
    assert _falt(text) == text


def test_art9_attribut_maskeras_inte_medvetet():
    """Spec §6.1: attributet passerar med en stabil pseudonym. Det är en
    fältminimerings- och DPIA-fråga, inte ett maskeringsfel."""
    ut = _falt("Fackavgift Anna Andersson", {"Anna Andersson"})
    assert "Fackavgift" in ut and "Anna" not in ut
