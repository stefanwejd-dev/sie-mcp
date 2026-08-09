"""test_mcp_lasande_bredd.py — Steg 1: de nio nya läsande MCP-verktygen.

Steg 1 exponerade kapacitet som redan fanns och var testad i spiris_rag,
spiris_adapter och fpa_motor men saknade MCP-omslag. Den här sviten prövar
omslagen och de fyra egenskaper som gör dem säkra att exponera:

1. **Säkerhetsnoten finns i VARJE verktygssvar.** Parametriserat över hela
   registret, så ett framtida verktyg inte kan glömma den. Rapportverktygen
   saknade den fram till paket A — det upptäcktes genom att köra dem, inte
   genom att läsa koden.
2. **Fail-closed:** ett fel i Spiris-anropet ger ett strukturerat svar, aldrig
   ett undantag mot MCP-klienten.
3. **`maskerad`-flaggan följer med reskontran**, så klientmodellen kan skilja
   ett verkligt bolagsnamn från en pseudonym.
4. **Art. 30-loggen får rätt datakategori** per verktygsgrupp.

Villkorsspärren prövas i test_mcp_villkorssparr.py och läckskyddet i
test_sekretess_lackprobe.py — båda är parametriserade över registret och
täcker de nya verktygen där.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest

import compliance
import mcp_server.server as server_modul
import revisionslogg
from mcp_server.server import (
    spiris_kunder,
    spiris_leverantorer,
    spiris_projekt,
    spiris_kostnadsstallen,
    spiris_kontosaldo,
    spiris_kontosaldo,
    spiris_referensdata,
    spiris_bankhandelser,
    spiris_avstamningslage,
    spiris_kontosaldo,
    spiris_referensdata,
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
    spiris_likviditetsprognos,
    spiris_momskoder,
    spiris_momsoversikt,
    spiris_momsrapporter,
    spiris_offerter,
    spiris_order,
    spiris_rakenskapsar,
    spiris_resultatrapport,
    spiris_sok_verifikationer,
    spiris_verifikatutkast,
    spiris_sie4export,
)

_COMPANY = {"Name": "Testbolag AB", "CorporateIdentityNumber": "556677-8899",
            "CurrencyCode": "SEK"}
_ACCOUNTS = [
    {"Number": "1930", "Name": "Företagskonto", "Type": 9, "Active": True},
    {"Number": "3041", "Name": "Försäljning", "Type": 20, "Active": True},
]
_BALANCES = [
    {"AccountNumber": 1930, "AccountName": "Företagskonto", "Balance": Decimal("5000")},
    {"AccountNumber": 1510, "AccountName": "Kundfordringar", "Balance": Decimal("2000")},
    {"AccountNumber": 2440, "AccountName": "Leverantörsskulder", "Balance": Decimal("-1500")},
    {"AccountNumber": 3041, "AccountName": "Försäljning", "Balance": Decimal("-8000")},
]
_FISCALYEARS = [
    {"Id": "fy-2025", "StartDate": "2025-01-01", "EndDate": "2025-12-31",
     "IsLockedForAccounting": True},
    {"Id": "fy-2026", "StartDate": "2026-01-01", "EndDate": "2026-12-31"},
]
_SUPPLIERS = [
    {"Id": "sup-1", "Name": "Scandinavian Photo AB", "CorporateIdentityNumber": "5566778899"},
    {"Id": "sup-2", "Name": "Anna Andersson", "CorporateIdentityNumber": ""},
]
_SUPPLIER_INVOICES = [
    {"SupplierId": "sup-1", "SupplierName": "Scandinavian Photo AB",
     "RemainingAmount": Decimal("1000"), "TotalAmount": Decimal("1000"),
     "PaymentStatus": 1, "InvoiceNumber": "F100", "InvoiceDate": "2026-07-01",
     "DueDate": "2026-07-15", "CurrencyCode": "SEK", "IsCreditInvoice": False,
     # Betalningsidentifierare — får ALDRIG nå MCP-svaret.
     "BankGiroNumber": "5402-9913", "OcrNumber": "12345678"},
    {"SupplierId": "sup-2", "SupplierName": "Anna Andersson",
     "RemainingAmount": Decimal("700"), "TotalAmount": Decimal("700"),
     "PaymentStatus": 1, "InvoiceNumber": "F101", "InvoiceDate": "2026-06-20",
     "DueDate": "2026-07-01", "CurrencyCode": "SEK", "IsCreditInvoice": False},
]
_ARTICLE_CODINGS = [
    {"Id": "cod-1", "DomesticSalesSubjectToVatAccountNumber": 3041},
]
_ARTICLES = [
    {"Id": "art-2", "Number": "20", "Name": "Resa", "NetPrice": 500,
     "UnitName": "st", "CodingId": "cod-1", "Active": True},
    {"Id": "art-1", "Number": "10", "Name": "Konsulttimme", "NetPrice": 1500,
     "UnitName": "tim", "CodingId": "cod-1", "Active": True},
]

_CUSTOMERS = [{"Id": "cus-1", "Name": "Kundbolaget AB", "OrganisationNumber": "5566778899"}]
# Order/offert bär ROT-fält och adresser som aldrig får hämtas.
_ORDERS = [
    {"Number": "O1", "CustomerName": "Kundbolaget AB", "CustomerIsPrivatePerson": False,
     "OrderDate": "2026-07-05", "Amount": Decimal("3000"), "VatAmount": Decimal("750"),
     "Status": 1, "CurrencyCode": "SEK", "Rows": [{}],
     "Persons": [{"Ssn": "850615-1235"}], "HouseWorkPropertyName": "Villan 1:2",
     "InvoiceAddress1": "Storgatan 1", "InvoiceCity": "Stockholm"},
]
_QUOTES = [
    {"Number": "Q1", "CustomerName": "Anna Andersson",
     "CustomerIsPrivatePerson": True, "QuoteDate": "2026-07-06",
     # Offerter bär TotalAmount, order bär Amount — sandbox-verifierat.
     "TotalAmount": Decimal("500"), "VatAmount": Decimal("125"), "Status": 1,
     "CurrencyCode": "SEK", "Rows": [], "Persons": [], "InvoiceAddress1": "Vägen 2"},
]
_BANKACCOUNTS = [
    {"Name": "Företagskonto", "LedgerAccountNumber": "1930", "CurrencyCode": "SEK",
     "Balance": {"Balance": Decimal("5000")}, "BankAccountTypeDescription": "Checkkonto",
     "Bban": "12345678", "Iban": "SE4550000000058398257466"},
]
_VATCODES = [
    {"Code": "SE25", "Description": "Sverige Momspliktig försäljning", "VatRate": Decimal("0.25")},
]
_VATREPORTS = [
    {"Id": "vr-1", "StartDate": "2026-01-01", "EndDate": "2026-03-31",
     "Amount": Decimal("1250"), "Status": 1},
]
_CUSTOMER_INVOICES = [
    {"CustomerId": "cus-1", "RemainingAmount": Decimal("500"), "PaymentStatus": 1,
     "DueDate": "2026-07-10"},
    {"CustomerId": "cus-1", "RemainingAmount": Decimal("0"), "PaymentStatus": 0,
     "DueDate": "2026-05-10", "PaymentDate": "2026-05-14"},
]


class _FejkKlient:
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
            return []
        if path == "/fiscalyears":
            return _FISCALYEARS
        if path == "/suppliers":
            return _SUPPLIERS
        if path == "/supplierinvoices":
            return _SUPPLIER_INVOICES
        if path == "/articles":
            return _ARTICLES
        if path == "/articleaccountcodings":
            return _ARTICLE_CODINGS
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
        if path == "/customers":
            return _CUSTOMERS
        if path == "/customerinvoices":
            return _CUSTOMER_INVOICES
        raise AssertionError(f"oväntad hamta_alla: {path}")


@pytest.fixture(autouse=True)
def _uppkopplad(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    compliance.godkann_compliance()
    monkeypatch.setattr(server_modul, "bygg_klient", lambda: _FejkKlient())
    monkeypatch.setattr(server_modul, "spara_session", lambda k: None)


# Namn -> anropbart, med giltiga argument. Hålls i synk med registret av
# test_alla_spirisverktyg_ar_tackta (nedan).
ALLA_SPIRISVERKTYG = {
    "spiris_kontosaldon": lambda: spiris_kontosaldon("fy-2026", "2026-12-31"),
    "spiris_verifikatutkast": lambda: spiris_verifikatutkast(),
    "spiris_sie4export": lambda: spiris_sie4export("2026-01-01", "2026-12-31"),
    "spiris_kontotransaktioner": lambda: spiris_kontotransaktioner("fy-2026", "1930"),
    "spiris_sok_verifikationer": lambda: spiris_sok_verifikationer("fy-2026", "hyra"),
    "spiris_resultatrapport": lambda: spiris_resultatrapport("2026-01-01", "2026-12-31"),
    "spiris_balansrapport": lambda: spiris_balansrapport("2026-12-31"),
    "spiris_kassaflodesanalys": lambda: spiris_kassaflodesanalys("2026-01-01", "2026-12-31"),
    "spiris_dashboard": lambda: spiris_dashboard("2026-01-01", "2026-12-31"),
    "spiris_rakenskapsar": lambda: spiris_rakenskapsar(),
    "spiris_kontoplan": lambda: spiris_kontoplan("fy-2026"),
    "spiris_foretagsinfo": lambda: spiris_foretagsinfo(),
    "spiris_artiklar": lambda: spiris_artiklar(),
    "spiris_leverantorsfakturor": lambda: spiris_leverantorsfakturor(),
    "spiris_order": lambda: spiris_order(),
    "spiris_offerter": lambda: spiris_offerter(),
    "spiris_bankkonton": lambda: spiris_bankkonton(),
    "spiris_momskoder": lambda: spiris_momskoder(),
    "spiris_momsrapporter": lambda: spiris_momsrapporter(),
    "spiris_momsoversikt": lambda: spiris_momsoversikt("2026-12-31"),
    "spiris_leverantorsreskontra": lambda: spiris_leverantorsreskontra(),
    "spiris_kundreskontra": lambda: spiris_kundreskontra(),
    "spiris_kundbetalbeteende": lambda: spiris_kundbetalbeteende(),
    "spiris_likviditetsprognos": lambda: spiris_likviditetsprognos("2026-12-31"),
    "spiris_kunder": lambda: spiris_kunder(),
    "spiris_leverantorer": lambda: spiris_leverantorer(),
    "spiris_projekt": lambda: spiris_projekt(),
    "spiris_kostnadsstallen": lambda: spiris_kostnadsstallen(),
    "spiris_kontosaldo": lambda: spiris_kontosaldo("1930", "2026-12-31"),
    "spiris_referensdata": lambda: spiris_referensdata("enheter"),
    "spiris_bankhandelser": lambda: spiris_bankhandelser("bank-1"),
    "spiris_avstamningslage": lambda: spiris_avstamningslage(),
}


# --- 1. Säkerhetsnoten i varje svar ----------------------------------------


def test_alla_spirisverktyg_ar_tackta():
    """Metatest: registret och den här sviten får inte glida isär."""
    registrerade = {
        t.name for t in asyncio.run(server_modul.mcp.list_tools())
        if t.name.startswith("spiris_")
    }
    assert registrerade == set(ALLA_SPIRISVERKTYG)


@pytest.mark.parametrize("namn", sorted(ALLA_SPIRISVERKTYG))
def test_varje_verktygssvar_bar_sakerhetsnot(namn):
    """Injektionsvarningen är MCP-serverns enda kanal till klientmodellen — den
    kan inte sätta systemprompt. Saknas den i ett svar är det svaret oskyddat."""
    svar = asyncio.run(ALLA_SPIRISVERKTYG[namn]())
    assert "sakerhetsnot" in svar, f"{namn} saknar säkerhetsnot"
    assert "instruktioner" in svar["sakerhetsnot"]


# --- 2. Verktygen levererar faktiskt innehåll ------------------------------
# Utan de här testerna kan läck- och notproberna passera tomt: ett verktyg som
# returnerar [] läcker aldrig något men gör inte heller någon nytta.


def test_rakenskapsar_nyast_forst_och_last_flagga():
    data = asyncio.run(spiris_rakenskapsar())["data"]
    assert [r["id"] for r in data] == ["fy-2026", "fy-2025"]
    assert data[1]["last"] is True
    assert data[0]["startdatum"] == "2026-01-01"


def test_kontoplan_ar_sorterad_och_bar_kontotyp():
    data = asyncio.run(spiris_kontoplan("fy-2026"))["data"]
    assert [k["kontonr"] for k in data] == ["1930", "3041"]
    assert data[0]["kontonamn"] == "Företagskonto"


def test_artiklar_bar_kontokoppling_och_ar_sorterade():
    """Kontokopplingen är hela poängen: utan den kan varken en människa eller
    en assistent avgöra vilken artikel som är rätt för en viss intäkt."""
    data = asyncio.run(spiris_artiklar())["data"]
    assert [a["artikelnr"] for a in data] == ["10", "20"]
    assert data[0]["namn"] == "Konsulttimme"
    assert data[0]["konto"] == "3041"
    assert data[0]["pris"] == 1500


def test_foretagsinfo_returnerar_en_post():
    data = asyncio.run(spiris_foretagsinfo())["data"]
    assert len(data) == 1
    assert data[0]["organisationsnummer"] == "556677-8899"


def test_leverantorsreskontra_har_poster_och_maskerad_flagga():
    data = asyncio.run(spiris_leverantorsreskontra())["data"]
    assert len(data) == 2
    juridisk = [p for p in data if not p["maskerad"]]
    fysisk = [p for p in data if p["maskerad"]]
    assert juridisk and juridisk[0]["leverantor"] == "Scandinavian Photo AB"
    # Fysisk person pseudonymiseras — och flaggan MÅSTE följa med, annars kan
    # modellen inte veta att namnet inte är en identitet.
    assert fysisk and "Anna Andersson" not in str(fysisk)


def test_kundreskontra_bar_motpart_id():
    data = asyncio.run(spiris_kundreskontra())["data"]
    assert len(data) == 1
    assert data[0]["motpart_id"] == "cus-1"
    assert data[0]["maskerad"] is False  # giltigt org.nr -> juridisk person


def test_kundbetalbeteende_raknar_dagar():
    data = asyncio.run(spiris_kundbetalbeteende())["data"]
    assert data == [{"motpart_id": "cus-1", "snitt_dagar_forsent": Decimal("4")}]


def test_dashboard_bygger_alla_fyra_rapporterna():
    svar = asyncio.run(spiris_dashboard("2026-01-01", "2026-12-31"))
    assert {"resultat", "balans", "nyckeltal", "kassaflode"} <= set(svar)


def test_kassaflodesanalys_har_de_tre_blocken():
    """Kassaflödet är blockindelat (löpande/investering/finansiering) — det har
    ingen toppnivå-`poster` som resultat- och balansrapporterna har."""
    svar = asyncio.run(spiris_kassaflodesanalys("2026-01-01", "2026-12-31"))
    assert {"lopande", "investering", "finansiering", "period"} <= set(svar)
    assert "poster" in svar["lopande"]


# --- 2b. Steg 3: fältallowlisten ------------------------------------------
# Order- och offertobjekten i Spiris bär ROT-personnummer (`Persons`),
# fastighetsbeteckning (`HouseWorkPropertyName`) och fullständiga adresser.
# Leverantörsfakturor bär bankgiro och OCR. Inget av det hämtas — principen är
# ALLOWLIST, inte svartlista, eftersom det som aldrig hämtas inte kan läcka.


def test_leverantorsfakturor_bar_inga_betalningsidentifierare():
    svar = asyncio.run(spiris_leverantorsfakturor())
    text = str(svar)
    assert "5402-9913" not in text, "bankgiro läckte"
    assert "12345678" not in text, "OCR-nummer läckte"
    assert {p["fakturanummer"] for p in svar["data"]} == {"F100", "F101"}


def test_order_bar_varken_rotpersonnummer_adress_eller_fastighet():
    """Det farligaste fältet i hela Steg 3: Persons kan bära personnummer."""
    svar = asyncio.run(spiris_order())
    text = str(svar)
    assert "850615-1235" not in text, "ROT-personnummer läckte"
    assert "Villan 1:2" not in text, "fastighetsbeteckning läckte"
    assert "Storgatan 1" not in text, "fakturaadress läckte"
    assert "Stockholm" not in text
    assert svar["data"][0]["nummer"] == "O1"
    assert svar["data"][0]["moms"] == Decimal("750")


def test_offert_maskerar_privatperson():
    """CustomerIsPrivatePerson -> pseudonym, samma regel som reskontran."""
    svar = asyncio.run(spiris_offerter())
    post = svar["data"][0]
    assert post["maskerad"] is True
    # Offertens belopp ligger i TotalAmount, inte Amount (sandbox-verifierat).
    assert post["belopp_exkl_moms"] == Decimal("500")
    assert "Anna Andersson" not in str(svar)
    assert "Vägen 2" not in str(svar)


def test_bankkonton_bar_inga_kontonummer():
    svar = asyncio.run(spiris_bankkonton())
    text = str(svar)
    assert "SE4550000000058398257466" not in text, "IBAN läckte"
    assert "12345678" not in text, "BBAN läckte"
    post = svar["data"][0]
    assert post["bas_konto"] == "1930"
    assert post["saldo"] == Decimal("5000")  # uppackat ur den nästlade Balance


def test_momskoder_ar_ren_referensdata():
    data = asyncio.run(spiris_momskoder())["data"]
    assert data[0]["kod"] == "SE25"
    assert data[0]["momssats"] == Decimal("0.25")


def test_momsrapporter_ar_inlamnade_deklarationer():
    data = asyncio.run(spiris_momsrapporter())["data"]
    assert data[0]["period_start"] == "2026-01-01"


# --- 2c. Momsöversikten är INTE en deklaration ----------------------------


def test_momsoversikt_markerar_sig_som_berakning():
    """Den viktigaste egenskapen: den får aldrig kunna presenteras som ett
    deklarationsunderlag."""
    svar = asyncio.run(spiris_momsoversikt("2026-12-31"))
    assert svar["ar_deklaration"] is False
    assert "inte en momsdeklaration" in svar["info"]


def test_momsoversikt_summerar_ratt_tecken():
    """Utgående moms bokförs som kredit (negativt saldo) och ska redovisas som
    en positiv skuld; ingående moms är debet och redovisas positivt."""
    from fpa_motor import bygg_momsoversikt

    r = bygg_momsoversikt(
        [
            {"kontonr": "2611", "kontonamn": "Utg moms 25%", "saldo": Decimal("-2500")},
            {"kontonr": "2641", "kontonamn": "Ing moms", "saldo": Decimal("800")},
            {"kontonr": "2650", "kontonamn": "Momsavräkning", "saldo": Decimal("-100")},
            {"kontonr": "3041", "kontonamn": "Försäljning", "saldo": Decimal("-10000")},
        ],
        "2026-12-31",
    )
    assert r["poster"]["utgaende_moms"] == Decimal("2500")
    assert r["poster"]["ingaende_moms"] == Decimal("800")
    assert r["poster"]["att_betala"] == Decimal("1700")
    assert r["poster"]["momsavrakning"] == Decimal("-100")
    # Konton utanför momsserierna ska inte följa med
    assert [k["kontonr"] for k in r["konton"]] == ["2611", "2641", "2650"]


# --- 3. Likviditetsprognosens kassasaldo (arkitektbeslut D3) ---------------


def test_likviditetsprognos_hamtar_kassasaldo_ur_balansrapporten():
    """D3: modellen ska inte kunna gissa ett kassasaldo. Saldot tas ur
    balansräkningen och källan redovisas i svaret."""
    svar = asyncio.run(spiris_likviditetsprognos("2026-12-31"))
    assert svar["kassasaldo"] == Decimal("5000")  # konto 1930 ur _BALANCES
    assert svar["kassasaldo_kalla"] == "balansrapport"


def test_likviditetsprognos_redovisar_angivet_saldo_som_sadant():
    import spiris_rag

    svar = asyncio.run(
        spiris_rag.hamta_likviditetsprognos(
            _FejkKlient(), "2026-12-31", None, Decimal("123")
        )
    )
    assert svar["kassasaldo"] == Decimal("123")
    assert svar["kassasaldo_kalla"] == "angivet av anropare"


# --- 4. Fail-closed --------------------------------------------------------


@pytest.mark.parametrize("namn", sorted(ALLA_SPIRISVERKTYG))
def test_fel_i_spiris_ger_strukturerat_svar_inte_undantag(namn, monkeypatch):
    def _kraschar(*a, **k):
        raise RuntimeError("Spiris svarade 500: <rå text som inte får läcka>")

    monkeypatch.setattr(server_modul, "bygg_klient", lambda: _TrasigKlient())

    svar = asyncio.run(ALLA_SPIRISVERKTYG[namn]())

    assert isinstance(svar, dict)
    assert "rå text som inte får läcka" not in str(svar)


class _TrasigKlient(_FejkKlient):
    def hamta_en(self, path, params=None):
        raise RuntimeError("Spiris svarade 500: <rå text som inte får läcka>")

    def hamta_alla(self, path, params=None):
        raise RuntimeError("Spiris svarade 500: <rå text som inte får läcka>")


# --- 5. Lagergränsen ------------------------------------------------------


def test_mcp_servern_gar_aldrig_forbi_spiris_rag():
    """Arkitekturregel: MCP-verktyg anropar bara spiris_rag, aldrig
    spiris_adapter direkt.

    spiris_rag är maskerings- och envelopegränsen. Ett verktyg som importerar
    adaptern direkt kringgår både maskeringen och säkerhetsnoten — och det syns
    inte i något funktionstest, eftersom svaret ser rimligt ut. Därför ett
    statiskt test."""
    from pathlib import Path

    källa = Path(server_modul.__file__).read_text(encoding="utf-8")
    assert "import spiris_adapter" not in källa
    assert "from spiris_adapter" not in källa


# --- 6. Art. 30-loggens datakategorier -------------------------------------


@pytest.mark.parametrize(
    "namn,forvantad",
    [
        ("spiris_kontosaldon", server_modul.KATEGORI_HUVUDBOK),
        ("spiris_dashboard", server_modul.KATEGORI_HUVUDBOK),
        ("spiris_rakenskapsar", server_modul.KATEGORI_STRUKTUR),
        ("spiris_kontoplan", server_modul.KATEGORI_STRUKTUR),
        ("spiris_foretagsinfo", server_modul.KATEGORI_STRUKTUR),
        ("spiris_leverantorsreskontra", server_modul.KATEGORI_RESKONTRA),
        ("spiris_kundreskontra", server_modul.KATEGORI_RESKONTRA),
        ("spiris_likviditetsprognos", server_modul.KATEGORI_RESKONTRA),
    ],
)
def test_art30_loggen_far_ratt_datakategori(namn, forvantad):
    """Art. 30-registret måste vara riktigt. Före Steg 1 loggades allt som
    huvudboksdata, vilket blir en osann uppgift när reskontra tillkommer."""
    asyncio.run(ALLA_SPIRISVERKTYG[namn]())

    poster = revisionslogg.las_revisionslogg()
    assert poster, "inget loggades"
    assert poster[-1]["datakategorier"] == [forvantad]
