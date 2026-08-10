import pytest
import asyncio
from unittest.mock import patch, MagicMock
from mcp_server.server import spiris_offertutkast, forbered_offertutkast
from parser.spiris_adapter import _EnkelKlient, hamta_ett, utfor_utkast, SpirisKlientFel
import compliance
from parser.spiris_rag import _envelope

@pytest.fixture(autouse=True)
def _godkann():
    compliance.godkann_compliance()

@pytest.fixture(autouse=True)
def mock_klient():
    with patch("mcp_server.server.bygg_klient") as mock_bygg, patch("mcp_server.server.spara_session"):
        k = MagicMock()
        mock_bygg.return_value = k
        yield k

def _fejk_hamta_alla(path, **kwargs):
    if path == "/quotedrafts":
        return [{
            "Id": "O1",
            "Number": "1001",
            "CustomerId": "C1",
            "CustomerName": "Kalle Anka",
            "CustomerNumber": "123",
            "QuoteDate": "2026-08-01",
            "DueDate": "2026-09-01",
            "DeliveryDate": "2026-08-15",
            "CurrencyCode": "SEK",
            "TotalAmount": 1000.0,
            "VatAmount": 250.0,
            "RoundingsAmount": 0.0,
            "Status": "Draft",
            "Rows": [{"ArticleNumber": "A1"}],
            "IncludesVat": False,
            "IsDomestic": True,
            "YourReference": "Sven",
            "CustomerReference": None,
            "OurReference": None,
            "CompanyReference": "Kalle",
            "InvoiceAddress1": "Gatan 1",
            "Persons": [{"Name": "Pelle"}],
            "RotReducedInvoicingType": "rot",
            "Notes": "Hemligt",
            "BackgroundId": "B1",
            "TermsOfPayment": "30 dagar"
        }]
    if path == "/customers":
        return [{"Id": "C1", "Name": "Kalle Anka"}, {"Id": "C2", "Name": "Musse Pigg"}, {"Id": "C3", "Name": "AB"}, {"Id": "C4", "Name": "AB"}]
    if path == "/articleaccountcodings":
        return [{"Id": "KOD1", "DomesticSalesSubjectToVatAccountNumber": "3010"}]
    if path == "/articles":
        return [{"Id": "ART1", "CodingId": "KOD1"}]
    return []

# --- U15.1 ---

def test_spiris_offertutkast_lyckas(mock_klient):
    mock_klient.hamta_alla.side_effect = _fejk_hamta_alla
    res = asyncio.run(spiris_offertutkast())
    data = res["data"][0]
    
    assert data["Id"] == "O1"
    assert data["Number"] == "1001"
    assert data["TotalAmount"] == 1000.0
    assert "Maskerad" in data["CustomerName"]
    assert "InvoiceAddress1" not in data
    assert "Persons" not in data
    assert "RotReducedInvoicingType" not in data
    assert "Notes" not in data
    assert "BackgroundId" not in data
    assert "TermsOfPayment" not in data

def test_spiris_offertutkast_felhantering(mock_klient):
    mock_klient.hamta_alla.side_effect = Exception("API Fel")
    res = asyncio.run(spiris_offertutkast())
    assert "fel" in res["info"].lower() or "undantag" in res["info"].lower() or "fel" in str(res).lower()

def test_hamta_ett_offertutkast():
    klient = _EnkelKlient({
        "Id": "O2",
        "CustomerName": "Musse Pigg",
        "InvoiceAddress1": "Gatan 1",
    })
    res = hamta_ett(klient, "offertutkast", "O2")
    assert res["Id"] == "O2"
    assert "Maskerad" in res["CustomerName"]
    assert "InvoiceAddress1" not in res

def test_spiris_offertutkast_tomt(mock_klient):
    mock_klient.hamta_alla.return_value = []
    res = asyncio.run(spiris_offertutkast())
    assert len(res["data"]) == 0

def test_spiris_offertutkast_referenser(mock_klient):
    mock_klient.hamta_alla.side_effect = _fejk_hamta_alla
    res = asyncio.run(spiris_offertutkast())
    data = res["data"][0]
    assert data["YourReference"] == "Sven"
    assert data["OurReference"] == "Kalle"

def test_spiris_offertutkast_kategori(mock_klient):
    mock_klient.hamta_alla.side_effect = _fejk_hamta_alla
    res = asyncio.run(spiris_offertutkast())
    assert "sakerhetsnot" in res
    assert "extern part" in res["sakerhetsnot"]

# --- U15.2 ---

def test_forbered_offertutkast_ratt_payload(mock_klient):
    res = asyncio.run(forbered_offertutkast(
        kundnamn_eller_id="Kalle Anka",
        rader=[{"beskrivning": "Konsult", "antal": 10, "pris": 500, "konto": "3010"}],
        offertdatum="2026-08-01",
        forfallodatum="2026-09-01",
        valuta="SEK",
        inkl_moms=False,
        leveransdatum="2026-08-15",
        kundreferens="Sven",
        var_referens="Kalle"
    ))
    assert "bekraftelse" in res or "utkast_id" in res or "utkast" in res

def test_utfor_offertutkast_adapter(mock_klient):
    mock_klient.hamta_alla.side_effect = _fejk_hamta_alla
    mock_klient.skapa.return_value = {"Id": "Q1"}
    
    nyttolast = {
        "kundnamn": "Kalle Anka",
        "rader": [{"beskrivning": "Konsult", "antal": 10, "pris": 500, "konto": "3010"}],
        "offertdatum": "2026-08-01",
        "forfallodatum": "2026-09-01",
        "valuta": "SEK",
        "inkl_moms": False,
        "leveransdatum": "2026-08-15",
        "kundreferens": "Sven",
        "var_referens": "Kalle"
    }
    
    res = utfor_utkast(mock_klient, "offertutkast", nyttolast)
    assert res["offertutkast_id"] == "Q1"
    
    skapa_args = mock_klient.skapa.call_args[0]
    assert skapa_args[0] == "/quotedrafts"
    payload = skapa_args[1]
    
    assert payload["CustomerId"] == "C1"
    assert payload["QuoteDate"] == "2026-08-01"
    assert payload["DueDate"] == "2026-09-01"
    assert payload["CurrencyCode"] == "SEK"
    assert payload["IncludesVat"] is False
    assert payload["DeliveryDate"] == "2026-08-15"
    assert payload["CustomerReference"] == "Sven"
    assert payload["CompanyReference"] == "Kalle"
    
    assert len(payload["Rows"]) == 1
    rad = payload["Rows"][0]
    assert rad["Text"] == "Konsult"
    assert rad["Quantity"] == 10.0
    assert rad["UnitPrice"] == 500.0

def test_utfor_offertutkast_endast_obligatoriska(mock_klient):
    mock_klient.hamta_alla.side_effect = _fejk_hamta_alla
    mock_klient.skapa.return_value = {"Id": "Q2"}
    
    nyttolast = {
        "kundnamn": "Musse Pigg",
        "rader": [],
        "offertdatum": "2026-08-01",
        "forfallodatum": "2026-09-01",
    }
    
    res = utfor_utkast(mock_klient, "offertutkast", nyttolast)
    assert res["offertutkast_id"] == "Q2"
    
    payload = mock_klient.skapa.call_args[0][1]
    assert payload["CustomerId"] == "C2"
    assert "CurrencyCode" not in payload
    assert "DeliveryDate" not in payload

def test_utfor_offertutkast_kund_saknas(mock_klient):
    mock_klient.hamta_alla.side_effect = _fejk_hamta_alla
    
    nyttolast = {
        "kundnamn": "Finns Inte",
        "rader": [],
        "offertdatum": "2026-08-01",
        "forfallodatum": "2026-09-01",
    }
    with pytest.raises(SpirisKlientFel, match="Ingen kund med namnet"):
        utfor_utkast(mock_klient, "offertutkast", nyttolast)

def test_utfor_offertutkast_kund_tvetydig(mock_klient):
    mock_klient.hamta_alla.side_effect = _fejk_hamta_alla
    nyttolast = {
        "kundnamn": "AB",
        "rader": [],
        "offertdatum": "2026-08-01",
        "forfallodatum": "2026-09-01",
    }
    with pytest.raises(SpirisKlientFel, match="Flera kunder"):
        utfor_utkast(mock_klient, "offertutkast", nyttolast)

def test_forbered_offertutkast_tomma_datum(mock_klient):
    res = asyncio.run(forbered_offertutkast(
        kundnamn_eller_id="Kalle",
        rader=[],
        offertdatum="",
        forfallodatum=""
    ))
    assert "bekraftelse" in res or "utkast_id" in res or "utkast" in res

def test_forbered_offertutkast_None_valuta(mock_klient):
    res = asyncio.run(forbered_offertutkast(
        kundnamn_eller_id="Kalle",
        rader=[],
        offertdatum="2026-01-01",
        forfallodatum="2026-01-31",
        valuta=None
    ))
    assert "bekraftelse" in res or "utkast_id" in res or "utkast" in res

def test_forbered_offertutkast_felaktiga_rader(mock_klient):
    res = asyncio.run(forbered_offertutkast(
        kundnamn_eller_id="Kalle",
        rader=[{"beskrivning": "Fel", "pris": "asdf"}],
        offertdatum="2026-01-01",
        forfallodatum="2026-01-31",
    ))
    assert "bekraftelse" in res or "utkast_id" in res or "utkast" in res

# --- U15.3 forbered_saljdokumentutkastatgard ---

from mcp_server.server import forbered_saljdokumentatgard, forbered_utkastborttagning
from parser.spiris_adapter import utfor_saljdokumentatgard, SpirisKlientFel

def test_forbered_offertutkast_till_offert(mock_klient):
    res = asyncio.run(forbered_saljdokumentatgard("offertutkast", "O1", "till_offert"))
    assert "bekraftelse" in res or "utkast_id" in res or "utkast" in res

def test_forbered_order_till_backorder(mock_klient):
    res = asyncio.run(forbered_saljdokumentatgard("order", "OR1", "till_backorder"))
    assert "bekraftelse" in res or "utkast_id" in res or "utkast" in res

def test_forbered_offertutkast_ogiltig_atgard(mock_klient):
    res = asyncio.run(forbered_saljdokumentatgard("offertutkast", "O1", "godkann"))
    assert res.get("utfort") is False or res.get("status") == "error"

def test_utfor_saljdokumentatgard_offertutkast_till_offert(mock_klient):
    mock_klient.hamta_alla.return_value = [{"Id": "Q1", "Number": "O1"}]
    utfor_saljdokumentatgard(mock_klient, "offertutkast", "O1", "till_offert")
    
    anrop = mock_klient.uppdatera.call_args[0]
    assert anrop[0] == "/quotedrafts/O1/convert"
    assert anrop[1] == {}

def test_utfor_saljdokumentatgard_order_till_backorder(mock_klient):
    mock_klient.hamta_alla.return_value = [{"Id": "OR1", "Number": "OR1"}]
    utfor_saljdokumentatgard(mock_klient, "order", "OR1", "till_backorder")
    
    anrop = mock_klient.skicka.call_args[0]
    assert anrop[0] == "/orders/OR1/backorder"
    assert anrop[1] == {}

def test_forbered_borttagning_offertutkast(mock_klient):
    with patch("mcp_server.server.spiris_hamta_ett", return_value='{"QuoteDate": "2026-08-01", "CustomerName": "Kalle", "TotalAmount": 1000}'):
        res = asyncio.run(forbered_utkastborttagning("offertutkast", "O1"))
        assert "bekraftelse" in res or "utkast_id" in res or "utkast" in res

def test_utfor_borttagning_offertutkast(mock_klient):
    from parser.spiris_adapter import utfor_utkast
    
    with patch("parser.spiris_adapter.hamta_ett") as mock_hamta:
        mock_hamta.return_value = {"Id": "Q1"}
        nyttolast = {"utkasttyp": "offertutkast", "utkast_id": "Q1"}
        
        utfor_utkast(mock_klient, "utkastborttagning", nyttolast, "utkast")
        pass

def test_utfor_borttagning_offertutkast_real(mock_klient):
    from parser.spiris_adapter import utfor_utkast
    with patch("parser.spiris_adapter.hamta_ett") as mock_hamta:
        mock_hamta.return_value = {"Id": "Q1"}
        nyttolast = {"utkasttyp": "offertutkast", "utkast_id": "Q1"}
        utfor_utkast(mock_klient, "utkastborttagning", nyttolast, "utkast")
        
        anrop = mock_klient.ta_bort.call_args[0]
        assert anrop[0] == "/quotedrafts/Q1"
