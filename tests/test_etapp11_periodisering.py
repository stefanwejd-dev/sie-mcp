import pytest
import asyncio
from decimal import Decimal
from unittest.mock import patch
from mcp_server.server import (
    forbered_periodiseringsandring,
    forbered_periodiseringsborttagning
)
import compliance

class _FejkCtx:
    def __init__(self):
        self.session_id = "test_session"
    async def log_info(self, *args, **kwargs):
        pass

@pytest.fixture(autouse=True)
def _godkann():
    compliance.godkann_compliance()

def _fejk_hamta_ett(typ, objekt_id):
    if typ == "periodiseringar" and objekt_id == "existerande_id":
        return {
            "periodisering": {
                "id": "existerande_id",
                "bokforingsdatum": "2025-01-01",
                "belopp": Decimal("500.00"),
                "debetkonto": "1790",
                "kreditkonto": "3000",
                "status": "Aktiv",
                "verifikat_id": "v1",
                "rader": [{}, {}, {}, {}, {}, {}] # 6 rader
            }
        }
    if typ == "leverantorsfakturautkast" and objekt_id == "utkast_1":
        # Fake a raw draft with allocation periods
        return {
            "Id": "utkast_1",
            "AllocationPeriods": [
                {
                    "Amount": 1000.0,
                    "NumberOfAllocationPeriods": 10
                },
                {
                    "Amount": 500.0,
                    "NumberOfAllocationPeriods": 5
                }
            ],
            "Rows": []
        }
    raise ValueError(f"okänd id: {objekt_id}")

@patch("mcp_server.server.spiris_hamta_ett", side_effect=_fejk_hamta_ett)
def test_forbered_periodiseringsandring_lyckas(mock_hamta_ett):
    res = asyncio.run(forbered_periodiseringsandring(
        plan_id="existerande_id",
        startdatum="2026-01-01",
        belopp="1000.00",
        konto=1790,
        antal_perioder=12,
        verifikat_id="v1",
        verifikat_rad=1
    ))
    assert res.get("utkast_id") is not None
    s = str(res.get("sammanfattning", []))
    assert "Nuvarande belopp" in s
    assert "500.00" in s
    assert "Nuvarande perioder" in s
    assert "Nytt belopp" in s
    assert "1,000.00" in s

@patch("mcp_server.server.spiris_hamta_ett", side_effect=_fejk_hamta_ett)
def test_forbered_periodiseringsandring_fel_koppling(mock_hamta_ett):
    with pytest.raises(ValueError, match="Exakt ett kopplingspar"):
        asyncio.run(forbered_periodiseringsandring(
            plan_id="existerande_id",
            startdatum="2026-01-01",
            belopp="1000.00",
            konto=1790,
            antal_perioder=12,
            verifikat_id="v1",
            verifikat_rad=1,
            leverantorsfaktura_id="lev1",
            leverantorsfaktura_rad=2
        ))

@patch("mcp_server.server.spiris_hamta_ett", side_effect=_fejk_hamta_ett)
def test_forbered_periodiseringsandring_noll_perioder(mock_hamta_ett):
    with pytest.raises(ValueError, match="måste vara >= 1"):
        asyncio.run(forbered_periodiseringsandring(
            plan_id="existerande_id",
            startdatum="2026-01-01",
            belopp="1000.00",
            konto=1790,
            antal_perioder=0,
            verifikat_id="v1",
            verifikat_rad=1
        ))

@patch("mcp_server.server.spiris_hamta_ett", side_effect=_fejk_hamta_ett)
def test_forbered_periodiseringsandring_negativt_belopp(mock_hamta_ett):
    with pytest.raises(ValueError, match="måste vara större än 0"):
        asyncio.run(forbered_periodiseringsandring(
            plan_id="existerande_id",
            startdatum="2026-01-01",
            belopp="-10.00",
            konto=1790,
            antal_perioder=12,
            verifikat_id="v1",
            verifikat_rad=1
        ))

@patch("mcp_server.server.spiris_hamta_ett", side_effect=_fejk_hamta_ett)
def test_forbered_periodiseringsandring_ogiltigt_plan_id(mock_hamta_ett):
    with pytest.raises(ValueError, match="Kunde inte hämta befintlig periodisering"):
        asyncio.run(forbered_periodiseringsandring(
            plan_id="ogiltigt_id",
            startdatum="2026-01-01",
            belopp="1000.00",
            konto=1790,
            antal_perioder=12,
            verifikat_id="v1",
            verifikat_rad=1
        ))

@patch("mcp_server.server.spiris_hamta_ett", side_effect=_fejk_hamta_ett)
def test_forbered_periodiseringsandring_noll_koppling(mock_hamta_ett):
    with pytest.raises(ValueError, match="Exakt ett kopplingspar"):
        asyncio.run(forbered_periodiseringsandring(
            plan_id="existerande_id",
            startdatum="2026-01-01",
            belopp="1000.00",
            konto=1790,
            antal_perioder=12
        ))

@patch("mcp_server.server.spiris_hamta_ett", side_effect=_fejk_hamta_ett)
def test_forbered_periodiseringsandring_text(mock_hamta_ett):
    res = asyncio.run(forbered_periodiseringsandring(
        plan_id="existerande_id",
        startdatum="2026-01-01",
        belopp="1234.56",
        konto=1790,
        antal_perioder=12,
        verifikat_id="v1",
        verifikat_rad=1
    ))
    info = res.get("info", "")
    assert "Ändring av periodisering" in info

# -- U11.2 tests --

@patch("mcp_server.server.spiris_hamta_ett", side_effect=_fejk_hamta_ett)
def test_forbered_periodiseringsborttagning_lyckas(mock_hamta_ett):
    res = asyncio.run(forbered_periodiseringsborttagning(
        leverantorsfakturautkast_id="utkast_1"
    ))
    assert res.get("utkast_id") is not None
    s = str(res.get("sammanfattning", []))
    assert "1000" in s or "1,000" in s
    assert "500" in s

@patch("mcp_server.server.spiris_hamta_ett", side_effect=_fejk_hamta_ett)
def test_forbered_periodiseringsborttagning_oaterkalleligt(mock_hamta_ett):
    res = asyncio.run(forbered_periodiseringsborttagning(
        leverantorsfakturautkast_id="utkast_1"
    ))
    info = res.get("info", "")
    assert "Oåterkalleligt" in info or "oåterkalleligt" in info.lower()

@patch("mcp_server.server.spiris_hamta_ett", side_effect=_fejk_hamta_ett)
def test_forbered_periodiseringsborttagning_hittades_ej(mock_hamta_ett):
    with pytest.raises(ValueError, match="Kunde inte hämta"):
        asyncio.run(forbered_periodiseringsborttagning(
            leverantorsfakturautkast_id="finns_inte"
        ))

def _fejk_hamta_ett_tom(typ, id):
    return {"Id": id, "AllocationPeriods": [], "Rows": []}

@patch("mcp_server.server.spiris_hamta_ett", side_effect=_fejk_hamta_ett_tom)
def test_forbered_periodiseringsborttagning_inga_periodiseringar(mock_hamta_ett):
    with pytest.raises(ValueError, match="Inga periodiseringar hittades"):
        asyncio.run(forbered_periodiseringsborttagning(
            leverantorsfakturautkast_id="utkast_2"
        ))

@patch("mcp_server.server.spiris_hamta_ett", side_effect=_fejk_hamta_ett)
def test_forbered_periodiseringsborttagning_endast_delete(mock_hamta_ett):
    res = asyncio.run(forbered_periodiseringsborttagning(
        leverantorsfakturautkast_id="utkast_1"
    ))
    info = res.get("info", "")
    assert "Ta bort" in info

@patch("mcp_server.server.spiris_hamta_ett", side_effect=_fejk_hamta_ett)
def test_forbered_periodiseringsborttagning_text(mock_hamta_ett):
    res = asyncio.run(forbered_periodiseringsborttagning(
        leverantorsfakturautkast_id="utkast_1"
    ))
    info = res.get("info", "")
    assert "enda DELETE-vägen" in info or "enskild periodisering" in info
