import asyncio
import pytest
from unittest.mock import MagicMock, patch

from mcp_server.server import forbered_kvittning

@pytest.fixture
def mock_klient():
    klient = MagicMock()
    with patch("mcp_server.server.bygg_klient", return_value=klient), \
         patch("mcp_server.server._villkor_godkanda", return_value=True):
        yield klient

@pytest.fixture
def mock_hamta_faktura():
    with patch("mcp_server.server.spiris_hamta_ett") as m:
        yield m

@pytest.fixture
def mock_kvittningskandidater():
    with patch("mcp_server.server.spiris_kvittningskandidater") as m:
        yield m

def test_forbered_kvittning_tom_debetlista(mock_klient):
    # DebitInvoiceIds får inte vara tom
    res = asyncio.run(forbered_kvittning("K1", [], "2026-08-10"))
    assert res.get("status") == "error"
    assert "Minst en debetfaktura" in res.get("info", "")

def test_forbered_kvittning_saknad_kreditfaktura(mock_klient, mock_hamta_faktura):
    mock_hamta_faktura.return_value = {"data": []}
    res = asyncio.run(forbered_kvittning("K1", ["D1"], "2026-08-10"))
    assert res.get("status") == "error"
    assert "Kreditfakturan hittades inte" in res.get("info", "")

def test_forbered_kvittning_ogiltig_kandidat(mock_klient, mock_hamta_faktura, mock_kvittningskandidater):
    mock_hamta_faktura.return_value = {"data": [{"Id": "K1", "InvoiceNumber": "1001"}]}
    # Kandidatlistan innehåller bara D1
    mock_kvittningskandidater.return_value = {
        "data": [{"faktura_id": "D1", "fakturanr": "1002", "kvarvarande": "500", "valuta": "SEK"}]
    }
    
    # Men vi försöker kvitta mot D1 och D2
    res = asyncio.run(forbered_kvittning("K1", ["D1", "D2"], "2026-08-10"))
    assert res.get("status") == "error"
    assert "D2 är inte en giltig kvittningskandidat" in res.get("info", "")

def test_forbered_kvittning_success(mock_klient, mock_hamta_faktura, mock_kvittningskandidater):
    mock_hamta_faktura.return_value = {"data": [{"Id": "K1", "InvoiceNumber": "1001"}]}
    mock_kvittningskandidater.return_value = {
        "data": [
            {"faktura_id": "D1", "fakturanr": "1002", "kvarvarande": "500.00", "valuta": "SEK"},
            {"faktura_id": "D2", "fakturanr": "1003", "kvarvarande": "200.00", "valuta": "SEK"}
        ]
    }
    
    res = asyncio.run(forbered_kvittning("K1", ["D1", "D2"], "2026-08-10"))
    
    # Det ska bli ett utkast (returnera en text med hash etc)
    assert isinstance(res, str) or (isinstance(res, dict) and res.get("status") != "error")
    
    if isinstance(res, str):
        # res är typiskt formaterad text
        assert "Kvittning mot 2 debetfaktura" in res
    else:
        assert "Kvittning mot 2 debetfaktura" in res.get("info", "")

# Test för själva utförandet (Adapter layer)
def test_skapa_kvittning_adapter(mock_klient):
    from parser.spiris_adapter import skapa_kvittning, SpirisKlientFel
    import pytest
    
    payload = {"DebitInvoiceIds": ["D1", "D2"], "VoucherDate": "2026-08-10"}
    
    # Om mock_klient.hamta_alla (kandidater) saknar D2:
    mock_klient.hamta_alla.return_value = [{"Id": "D1", "RemainingAmount": 500}]
    
    with pytest.raises(SpirisKlientFel, match="inte en giltig kvittningskandidat"):
        skapa_kvittning(mock_klient, "K1", payload)

def test_skapa_kvittning_adapter_success(mock_klient):
    from parser.spiris_adapter import skapa_kvittning
    
    payload = {"DebitInvoiceIds": ["D1"], "VoucherDate": "2026-08-10"}
    # D1 finns som kandidat
    mock_klient.hamta_alla.return_value = [{"Id": "D1", "RemainingAmount": 500}]
    
    skapa_kvittning(mock_klient, "K1", payload)
    
    mock_klient.skicka.assert_called_once_with("/supplierinvoices/K1/offset", payload)

def test_skapa_kvittning_adapter_exakt_tva_nycklar(mock_klient):
    from parser.spiris_adapter import skapa_kvittning, SpirisKlientFel
    import pytest
    
    payload = {"DebitInvoiceIds": ["D1"], "VoucherDate": "2026-08-10", "Extra": "Ogiltig"}
    mock_klient.hamta_alla.return_value = [{"Id": "D1", "RemainingAmount": 500}]
    
    # Wait, the spec says "ingenting annat får skickas". We should check this before sending.
    # We haven't implemented this check in skapa_kvittning yet! Let's do that!
    
    with pytest.raises(SpirisKlientFel, match="Endast DebitInvoiceIds och VoucherDate"):
        skapa_kvittning(mock_klient, "K1", payload)

