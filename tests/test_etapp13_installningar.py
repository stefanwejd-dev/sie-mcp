import pytest
import asyncio
import datetime
from unittest.mock import patch
from mcp_server.server import spiris_bokforingslas, forbered_bokforingslas, forbered_rotrut
import compliance

class _FejkCtx:
    def __init__(self):
        self.session_id = "test_session"
    async def log_info(self, *args, **kwargs):
        pass

@pytest.fixture(autouse=True)
def _godkann():
    compliance.godkann_compliance()


@pytest.fixture(autouse=True)
def _mock_klient():
    with patch("mcp_server.server.bygg_klient"), patch("mcp_server.server.spara_session"):
        yield


# -- U13.1 tests (4 tests) --
def _fejk_hamta_bokforingslas(kategori):
    return {"data": [{
        "last_till_och_med": "2026-01-01",
        "lasintervall": 1,
        "skattedeklarationsdatum": "2026-02-01"
    }]}
def _fejk_hamta_bokforingslas_tomt(kategori):
    return {"data": [{
        "last_till_och_med": None,
        "lasintervall": 0,
        "skattedeklarationsdatum": None
    }]}

@patch("mcp_server.server.spiris_rag.hamta_bokforingslas", side_effect=_fejk_hamta_bokforingslas)
def test_spiris_bokforingslas_lyckas(mock_rag):
    res = asyncio.run(spiris_bokforingslas())
    data = res["data"][0]
    assert data["last_till_och_med"] == "2026-01-01"

@patch("mcp_server.server.spiris_rag.hamta_bokforingslas", side_effect=_fejk_hamta_bokforingslas_tomt)
def test_spiris_bokforingslas_tomt(mock_rag):
    res = asyncio.run(spiris_bokforingslas())
    data = res["data"][0]
    assert data["last_till_och_med"] is None

@patch("mcp_server.server.spiris_rag.hamta_bokforingslas", side_effect=Exception("API Fel"))
def test_spiris_bokforingslas_fel(mock_rag):
    res = asyncio.run(spiris_bokforingslas())
    assert "info" in res and "Fel" in res["info"]

@patch("mcp_server.server.spiris_rag.hamta_bokforingslas", side_effect=_fejk_hamta_bokforingslas)
def test_spiris_bokforingslas_text(mock_rag):
    res = asyncio.run(spiris_bokforingslas())
    data = res.get("data", [{}])[0]
    assert "last_till_och_med" in data

# -- U13.2 tests (10 tests) --
def _fejk_hamta_ett_bokforingslas(typ, id):
    if typ == "bokforingslas":
        return {"last_till_och_med": "2026-01-01"}
    raise ValueError("Okänd")

@patch("mcp_server.server.spiris_hamta_ett", side_effect=_fejk_hamta_ett_bokforingslas)
def test_forbered_bokforingslas_lyckas(mock_hamta_ett):
    # Today is 2026-08-10. So any date up to today is fine.
    idag = datetime.date.today().isoformat()
    res = asyncio.run(forbered_bokforingslas(nytt_datum=idag))
    assert res.get("utkast_id") is not None
    info = res.get("info", "")
    s = str(res.get("sammanfattning", []))
    assert "OÅTERKALLELIGT" in s or "Oåterkalleligt" in s.upper()
    assert "2026-01-01" in s
    assert idag in s

@patch("mcp_server.server.spiris_hamta_ett", side_effect=_fejk_hamta_ett_bokforingslas)
def test_forbered_bokforingslas_tidigare_an_nuvarande(mock_hamta_ett):
    # D1a-spärr
    with pytest.raises(ValueError, match="senare än nuvarande"):
        asyncio.run(forbered_bokforingslas(nytt_datum="2025-12-31"))

@patch("mcp_server.server.spiris_hamta_ett", side_effect=_fejk_hamta_ett_bokforingslas)
def test_forbered_bokforingslas_samma_som_nuvarande(mock_hamta_ett):
    # D1a-spärr
    with pytest.raises(ValueError, match="senare än nuvarande"):
        asyncio.run(forbered_bokforingslas(nytt_datum="2026-01-01"))

@patch("mcp_server.server.spiris_hamta_ett", side_effect=_fejk_hamta_ett_bokforingslas)
def test_forbered_bokforingslas_framtiden(mock_hamta_ett):
    # D1a-spärr
    framtid = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
    with pytest.raises(ValueError, match="framtiden"):
        asyncio.run(forbered_bokforingslas(nytt_datum=framtid))

@patch("mcp_server.server.spiris_hamta_ett", side_effect=_fejk_hamta_ett_bokforingslas)
def test_forbered_bokforingslas_tomt_datum(mock_hamta_ett):
    # D1a-spärr
    with pytest.raises(ValueError, match="får inte vara tomt"):
        asyncio.run(forbered_bokforingslas(nytt_datum=""))

@patch("mcp_server.server.spiris_hamta_ett", side_effect=_fejk_hamta_ett_bokforingslas)
def test_forbered_bokforingslas_fel_format(mock_hamta_ett):
    with pytest.raises(ValueError, match="formatet"):
        asyncio.run(forbered_bokforingslas(nytt_datum="01-01-2026"))

def _fejk_hamta_ett_inget_las(typ, id):
    return {"last_till_och_med": None}

@patch("mcp_server.server.spiris_hamta_ett", side_effect=_fejk_hamta_ett_inget_las)
def test_forbered_bokforingslas_inget_tidigare_las(mock_hamta_ett):
    # D1a-spärr: if no lock, any non-future date is okay
    idag = datetime.date.today().isoformat()
    res = asyncio.run(forbered_bokforingslas(nytt_datum=idag))
    assert res.get("utkast_id") is not None
    s = str(res.get("sammanfattning", []))
    assert "(Inget lås)" in s

@patch("mcp_server.server.spiris_hamta_ett", side_effect=Exception("API Nere"))
def test_forbered_bokforingslas_kan_inte_hamta(mock_hamta_ett):
    with pytest.raises(ValueError, match="Kunde inte hämta"):
        asyncio.run(forbered_bokforingslas(nytt_datum="2026-01-01"))

@patch("mcp_server.server.spiris_hamta_ett", side_effect=_fejk_hamta_ett_bokforingslas)
def test_forbered_bokforingslas_text_utkast(mock_hamta_ett):
    idag = datetime.date.today().isoformat()
    res = asyncio.run(forbered_bokforingslas(nytt_datum=idag))
    info = res.get("info", "")
    assert "Framflyttning" in info

@patch("mcp_server.server.spiris_hamta_ett", side_effect=_fejk_hamta_ett_inget_las)
def test_forbered_bokforingslas_inget_tidigare_las_gammalt_datum(mock_hamta_ett):
    # Should work
    res = asyncio.run(forbered_bokforingslas(nytt_datum="1999-01-01"))
    assert res.get("utkast_id") is not None


# -- U13.3 tests (8 tests) --
def _fejk_hamta_ett_rotrut(typ, id):
    return {
        "RutMaxAmountForPersBelow65Year": 25000,
        "RutMaxAmountForPersOver65Year": 50000,
        "RutReducedInvoicingPercent": 50,
        "RotReducedInvoicingMaxAmount": 50000,
        "RotReducedInvoicingPercent": 30
    }

@patch("mcp_server.server.spiris_hamta_ett", side_effect=_fejk_hamta_ett_rotrut)
def test_forbered_rotrut_lyckas(mock_hamta_ett):
    res = asyncio.run(forbered_rotrut(
        RutReducedInvoicingPercent="49"
    ))
    assert res.get("utkast_id") is not None
    s = str(res.get("sammanfattning", []))
    assert "50 ➡️ 49.0" in s

@patch("mcp_server.server.spiris_hamta_ett", side_effect=_fejk_hamta_ett_rotrut)
def test_forbered_rotrut_inga_andringar(mock_hamta_ett):
    with pytest.raises(ValueError, match="Inga ändringar"):
        asyncio.run(forbered_rotrut())

@patch("mcp_server.server.spiris_hamta_ett", side_effect=_fejk_hamta_ett_rotrut)
def test_forbered_rotrut_fel_procent_over(mock_hamta_ett):
    with pytest.raises(ValueError, match="100"):
        asyncio.run(forbered_rotrut(RutReducedInvoicingPercent="101"))

@patch("mcp_server.server.spiris_hamta_ett", side_effect=_fejk_hamta_ett_rotrut)
def test_forbered_rotrut_fel_procent_under(mock_hamta_ett):
    with pytest.raises(ValueError, match="0"):
        asyncio.run(forbered_rotrut(RutReducedInvoicingPercent="-1"))

@patch("mcp_server.server.spiris_hamta_ett", side_effect=_fejk_hamta_ett_rotrut)
def test_forbered_rotrut_fel_belopp_noll(mock_hamta_ett):
    with pytest.raises(ValueError, match="> 0"):
        asyncio.run(forbered_rotrut(RutMaxAmountForPersBelow65Year="0"))

@patch("mcp_server.server.spiris_hamta_ett", side_effect=_fejk_hamta_ett_rotrut)
def test_forbered_rotrut_fel_belopp_negativt(mock_hamta_ett):
    with pytest.raises(ValueError, match="> 0"):
        asyncio.run(forbered_rotrut(RotReducedInvoicingMaxAmount="-500"))

@patch("mcp_server.server.spiris_hamta_ett", side_effect=Exception("API error"))
def test_forbered_rotrut_kan_inte_hamta(mock_hamta_ett):
    with pytest.raises(ValueError, match="Kunde inte hämta"):
        asyncio.run(forbered_rotrut(RutReducedInvoicingPercent="50"))

@patch("mcp_server.server.spiris_hamta_ett", side_effect=_fejk_hamta_ett_rotrut)
def test_forbered_rotrut_flera_andringar(mock_hamta_ett):
    res = asyncio.run(forbered_rotrut(
        RotReducedInvoicingMaxAmount="60000",
        RutMaxAmountForPersOver65Year="75000"
    ))
    assert res.get("utkast_id") is not None
    s = str(res.get("sammanfattning", []))
    assert "50000 ➡️ 75000.0" in s
    assert "50000 ➡️ 60000.0" in s
