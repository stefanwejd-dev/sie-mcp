from __future__ import annotations
import pytest
from parser.spiris_adapter import (
    SpirisKlientFel,
    bygg_utkastuppdatering,
    andra_utkast,
    ta_bort_utkast,
    bokfor_utkast,
    _UTKASTANDRING,
    _UTKASTSLAG,
    UTKASTTYP_UTKASTANDRING,
    UTKASTTYP_UTKASTBORTTAGNING,
    UTKASTTYP_UTKASTBOKFORING,
    utfor_utkast,
)
import compliance

@pytest.fixture(autouse=True)
def _godkanda_villkor():
    compliance.godkann_compliance()

class _FejkKlient:
    def __init__(self, fake_data: dict = None):
        self.log = []
        self.fake_data = fake_data or {"Id": "1", "VoucherDate": "2026-01-01", "VoucherText": "Gammal", "NumberSeries": "A", "Rows": []}
    def hamta_en(self, path: str):
        self.log.append(("GET", path))
        return self.fake_data
    def uppdatera(self, path: str, data: dict):
        self.log.append(("PUT", path, data))
        return data
    def ta_bort(self, path: str):
        self.log.append(("DELETE", path))
    def skicka(self, path: str, data: dict | None = None):
        self.log.append(("POST", path, data))
        return {"id": "nytt"}

# U2.1 - forbered_utkastandring
def test_bygg_utkastuppdatering_korrekt():
    nuvarande = {"VoucherDate": "2026-01-01", "VoucherText": "Gammal", "NumberSeries": "A", "Rows": []}
    andringar = {"text": "Ny", "datum": "2026-01-02"}
    res = bygg_utkastuppdatering(nuvarande, andringar, "verifikat")
    assert res["VoucherText"] == "Ny"
    assert res["VoucherDate"] == "2026-01-02"
    assert res["NumberSeries"] == "A"

def test_bygg_utkastuppdatering_okand_typ():
    with pytest.raises(SpirisKlientFel, match="Okänd utkasttyp"):
        bygg_utkastuppdatering({}, {"text": "Ny"}, "okand")

def test_bygg_utkastuppdatering_okand_nyckel():
    with pytest.raises(SpirisKlientFel, match="går inte att ändra på ett verifikatutkast: \\['okand'\\]"):
        bygg_utkastuppdatering({}, {"okand": "Ny"}, "verifikat")

def test_bygg_utkastuppdatering_inga_andringar():
    with pytest.raises(ValueError, match="Inga ändringar angivna"):
        bygg_utkastuppdatering({}, {}, "verifikat")

def test_andra_utkast_anropar_klient():
    k = _FejkKlient()
    andra_utkast(k, "verifikat", "1", {"text": "Ny text"})
    assert k.log[0] == ("GET", "/voucherdrafts/1")
    assert k.log[1][0] == "PUT"
    assert k.log[1][1] == "/voucherdrafts/1"
    assert k.log[1][2]["VoucherText"] == "Ny text"

def test_andra_utkast_okand_typ():
    k = _FejkKlient()
    with pytest.raises(SpirisKlientFel, match="Okänd utkasttyp"):
        andra_utkast(k, "okand", "1", {"text": "Ny"})

def test_utfor_utkast_utkastandring():
    k = _FejkKlient()
    utfor_utkast(k, UTKASTTYP_UTKASTANDRING, {"utkasttyp": "verifikat", "utkast_id": "1", "andringar": {"text": "Ny"}})
    assert k.log[0] == ("GET", "/voucherdrafts/1")
    assert k.log[1][0] == "PUT"

# U2.2 - forbered_utkastborttagning
def test_ta_bort_utkast_korrekt():
    k = _FejkKlient()
    ta_bort_utkast(k, "verifikat", "1")
    assert k.log[0] == ("DELETE", "/voucherdrafts/1")

def test_ta_bort_utkast_okand_typ():
    k = _FejkKlient()
    with pytest.raises(SpirisKlientFel, match="Okänd utkasttyp"):
        ta_bort_utkast(k, "okand", "1")

def test_utfor_utkast_utkastborttagning():
    k = _FejkKlient()
    res = utfor_utkast(k, UTKASTTYP_UTKASTBORTTAGNING, {"utkasttyp": "verifikat", "utkast_id": "1"})
    assert k.log[0] == ("DELETE", "/voucherdrafts/1")
    assert res == {"borttaget": "1"}

# U2.3 - forbered_utkastbokforing
def test_bokfor_utkast_korrekt():
    k = _FejkKlient()
    bokfor_utkast(k, "verifikat", "1")
    assert k.log[0] == ("POST", "/voucherdrafts/1/convert", None)

def test_bokfor_utkast_okand_typ():
    k = _FejkKlient()
    with pytest.raises(SpirisKlientFel, match="Okänd utkasttyp"):
        bokfor_utkast(k, "okand", "1")

def test_bokfor_utkast_kundfaktura():
    k = _FejkKlient()
    bokfor_utkast(k, "kundfaktura", "2")
    assert k.log[0] == ("POST", "/customerinvoicedrafts/2/convert", None)

def test_bokfor_utkast_leverantorsfaktura():
    k = _FejkKlient()
    bokfor_utkast(k, "leverantorsfaktura", "3")
    assert k.log[0] == ("POST", "/supplierinvoicedrafts/3/convert", None)

def test_utfor_utkast_utkastbokforing():
    k = _FejkKlient()
    utfor_utkast(k, UTKASTTYP_UTKASTBOKFORING, {"utkasttyp": "verifikat", "utkast_id": "1"})
    assert k.log[0] == ("POST", "/voucherdrafts/1/convert", None)

import mcp_server.server as server_modul
import asyncio

def test_server_forbered_utkastandring(monkeypatch):
    monkeypatch.setattr(server_modul, "bygg_klient", lambda: _FejkKlient())
    res = asyncio.run(server_modul.forbered_utkastandring("verifikat", "1", {"text": "Ny"}))
    assert "Ändring av verifikatutkast föreslås" in res["info"]
    assert "verifikat" in res["info"]

def test_server_forbered_utkastborttagning(monkeypatch):
    import json
    async def mock_hamta_ett(typ, id, ctx=None):
        return json.dumps({"verifikat": {"datum": "2026-01-01", "text": "Test", "rader": []}})
    monkeypatch.setattr(server_modul, "bygg_klient", lambda: _FejkKlient())
    monkeypatch.setattr(server_modul, "spiris_hamta_ett", mock_hamta_ett)
    res = asyncio.run(server_modul.forbered_utkastborttagning("verifikat", "1"))
    assert "Borttagning av verifikatutkast föreslås" in res["info"]

def test_server_forbered_utkastbokforing(monkeypatch):
    import json
    async def mock_hamta_ett(typ, id, ctx=None):
        return json.dumps({"verifikat": {"datum": "2026-01-01", "text": "Test", "rader": []}})
    monkeypatch.setattr(server_modul, "bygg_klient", lambda: _FejkKlient())
    monkeypatch.setattr(server_modul, "spiris_hamta_ett", mock_hamta_ett)
    res = asyncio.run(server_modul.forbered_utkastbokforing("verifikat", "1"))
    assert "Bokföring av verifikatutkast föreslås" in res["info"]
