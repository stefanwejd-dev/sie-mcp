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
        belopp=1000.0,
        konto=1790,
        antal_perioder=12,
        verifikat_id="v1",
        verifikat_rad=1
    ))
    assert res.get("utkast_id") is not None
    assert "Periodisering på 1000.0 kr från 2026-01-01 föreslås" in res.get("info", "")

def test_forbered_periodisering_fel_noll_kopplingspar():
    res = asyncio.run(forbered_periodisering(
        startdatum="2026-01-01",
        belopp=1000.0,
        konto=1790,
        antal_perioder=12
    ))
    assert res.get("utkast_id") is None
    assert "Kunde inte skapa utkastet" in res.get("info", "")

def test_forbered_periodisering_fel_tva_kopplingspar():
    res = asyncio.run(forbered_periodisering(
        startdatum="2026-01-01",
        belopp=1000.0,
        konto=1790,
        antal_perioder=12,
        verifikat_id="v1",
        verifikat_rad=1,
        kundfaktura_id="k1",
        kundfaktura_rad=2
    ))
    assert res.get("utkast_id") is None
    assert "Kunde inte skapa utkastet" in res.get("info", "")

def test_forbered_periodisering_fel_antal_perioder():
    res = asyncio.run(forbered_periodisering(
        startdatum="2026-01-01",
        belopp=1000.0,
        konto=1790,
        antal_perioder=0,
        verifikat_id="v1",
        verifikat_rad=1
    ))
    assert res.get("utkast_id") is None
    assert "Kunde inte skapa utkastet" in res.get("info", "")

def test_forbered_periodisering_kundfaktura():
    res = asyncio.run(forbered_periodisering(
        startdatum="2026-01-01",
        belopp=1000.0,
        konto=1790,
        antal_perioder=12,
        kundfaktura_id="k1",
        kundfaktura_rad=1
    ))
    assert res.get("utkast_id") is not None

def test_forbered_periodisering_levfaktura():
    res = asyncio.run(forbered_periodisering(
        startdatum="2026-01-01",
        belopp=1000.0,
        konto=1790,
        antal_perioder=12,
        leverantorsfaktura_id="l1",
        leverantorsfaktura_rad=1
    ))
    assert res.get("utkast_id") is not None

def test_forbered_periodisering_levutkast():
    res = asyncio.run(forbered_periodisering(
        startdatum="2026-01-01",
        belopp=1000.0,
        konto=1790,
        antal_perioder=12,
        leverantorsfakturautkast_id="lu1",
        leverantorsfakturautkast_rad=1
    ))
    assert res.get("utkast_id") is not None

def test_forbered_periodisering_text_innehall():
    res = asyncio.run(forbered_periodisering(
        startdatum="2026-01-01",
        belopp=1000.0,
        konto=1790,
        antal_perioder=12,
        verifikat_id="v1",
        verifikat_rad=1
    ))
    text = res.get("info", "")
    assert "1000.0 kr" in text
    assert "2026-01-01" in text

def test_forbered_periodisering_ingen_startdatum():
    pass
