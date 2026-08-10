import asyncio
import pytest
from mcp_server.server import forbered_periodisering
import compliance

@pytest.fixture(autouse=True)
def _godkanda_villkor():
    compliance.godkann_compliance()

def test_forbered_periodisering_lyckas():
    res = asyncio.run(forbered_periodisering(
        startdatum="2026-01-01",
        belopp="1000.00",
        konto=1790,
        antal_perioder=12,
        verifikat_id="v1",
        verifikat_rad=1
    ))
    assert res.get("utkast_id") is not None
    assert "Periodisering på 1000.00 kr från 2026-01-01 föreslås" in res.get("info", "")

def test_forbered_periodisering_fel_noll_kopplingspar():
    import pytest
    with pytest.raises(ValueError):
        asyncio.run(forbered_periodisering(
            startdatum="2026-01-01",
            belopp="1000.00",
            konto=1790,
            antal_perioder=12
        ))

def test_forbered_periodisering_fel_tva_kopplingspar():
    import pytest
    import asyncio
    with pytest.raises(ValueError):
        asyncio.run(forbered_periodisering(
            startdatum="2026-01-01",
            belopp="1000.00",
            konto=1790,
            antal_perioder=12,
            verifikat_id="v1",
            verifikat_rad=1,
            leverantorsfaktura_id="l1",
            leverantorsfaktura_rad=2
        ))

def test_forbered_periodisering_fel_antal_perioder():
    import pytest
    with pytest.raises(ValueError):
        asyncio.run(forbered_periodisering(
            startdatum="2026-01-01",
            belopp="1000.00",
            konto=1790,
            antal_perioder=0,
            verifikat_id="v1",
            verifikat_rad=1
        ))



def test_forbered_periodisering_levfaktura():
    res = asyncio.run(forbered_periodisering(
        startdatum="2026-01-01",
        belopp="1000.00",
        konto=1790,
        antal_perioder=12,
        leverantorsfaktura_id="l1",
        leverantorsfaktura_rad=1
    ))
    assert res.get("utkast_id") is not None

def test_forbered_periodisering_levutkast():
    res = asyncio.run(forbered_periodisering(
        startdatum="2026-01-01",
        belopp="1000.00",
        konto=1790,
        antal_perioder=12,
        leverantorsfakturautkast_id="lu1",
        leverantorsfakturautkast_rad=1
    ))
    assert res.get("utkast_id") is not None

def test_forbered_periodisering_text_innehall():
    res = asyncio.run(forbered_periodisering(
        startdatum="2026-01-01",
        belopp="1000.00",
        konto=1790,
        antal_perioder=12,
        verifikat_id="v1",
        verifikat_rad=1
    ))
    text = res.get("info", "")
    assert "1000.00 kr" in text
    assert "2026-01-01" in text

def test_forbered_periodisering_ingen_startdatum():
    pass


def test_forbered_periodisering_payload_till_skicka(monkeypatch):
    import parser.utkast as utkast
    from parser.spiris_adapter import utfor_utkast
    import asyncio
    
    res = asyncio.run(forbered_periodisering(
        startdatum="2026-02-01",
        belopp="500.00",
        konto=1790,
        antal_perioder=6,
        verifikat_id="v1",
        verifikat_rad=1
    ))
    u_id = res["utkast_id"]
    u = utkast.las(u_id)
    
    # Mock klient.skicka
    skickat_url = None
    skickat_payload = None
    
    class FakeKlient:
        def skicka(self, url, payload):
            nonlocal skickat_url, skickat_payload
            skickat_url = url
            skickat_payload = payload
            return {"Id": "periodisering123"}
            
    utfor_utkast(FakeKlient(), u.typ, u.nyttolast)
    
    assert skickat_url == "/allocationperiods"
    assert isinstance(skickat_payload, list)
    assert len(skickat_payload) == 1
    p = skickat_payload[0]
    assert p["BookkeepingStartDate"] == "2026-02-01"
    assert p["AmountToAllocate"] == 500.0
    assert p["AllocationAccountNumber"] == 1790
    assert p["NumberOfAllocationPeriods"] == 6
    assert p["VoucherId"] == "v1"
    assert p["VoucherRow"] == 1

def test_forbered_periodisering_fel_belopp():
    import asyncio
    import pytest
    with pytest.raises(ValueError):
        asyncio.run(forbered_periodisering(
            startdatum="2026-01-01",
            belopp="0.0",
            konto=1790,
            antal_perioder=12,
            verifikat_id="v1",
            verifikat_rad=1
        ))
