
import pytest
import asyncio
from parser import spiris_adapter, spiris_rag, utkast, atgardsformular
from mcp_server import server
import compliance

class MockKlient:
    def __init__(self):
        self.skickat = []
    def hamta_alla(self, path, params=None):
        if "offsetcandidates" in path:
            return [{"InvoiceId": "inv-1", "InvoiceNumber": "123", "InvoiceDate": "2026-01-01", "SupplierName": "Abc", "RemainingAmount": "100.5", "CurrencyCode": "SEK"}]
        return []
    def skicka(self, path, payload):
        self.skickat.append((path, payload))
        return {"Id": "res-1"}

def test_kvittningskandidater_adapter():
    k = MockKlient()
    res = spiris_adapter.hamta_kvittningskandidater(k, "c-1")
    assert len(res) == 1
    assert res[0]["InvoiceId"] == "inv-1"

def test_kvittningskandidater_rag():
    k = MockKlient()
    res = asyncio.run(spiris_rag.hamta_kvittningskandidater(k, "c-1"))
    assert len(res) == 1
    assert res[0]["leverantor"] != "Abc" # Maskerad

def test_forbered_betalningsverifikat_balans():
    compliance.godkann_compliance()
    svar = asyncio.run(server.forbered_betalningsverifikat("Test", "2026-01-01", [{"konto": "1930", "debet": 100, "kredit": 0}]))
    assert svar["utkast_id"] is None

def test_forbered_betalningsverifikat_ok():
    compliance.godkann_compliance()
    res = asyncio.run(server.forbered_betalningsverifikat("Test", "2026-01-01", [{"konto": "1930", "debet": 100, "kredit": 0}, {"konto": "2440", "debet": 0, "kredit": 100}]))
    assert "föreslås" in res["info"]
