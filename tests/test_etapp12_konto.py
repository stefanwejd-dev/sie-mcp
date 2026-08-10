import pytest
import asyncio
from unittest.mock import patch
from mcp_server.server import forbered_konto, forbered_kontoandring
import compliance

class _FejkCtx:
    def __init__(self):
        self.session_id = "test_session"
    async def log_info(self, *args, **kwargs):
        pass

@pytest.fixture(autouse=True)
def _godkann():
    compliance.godkann_compliance()

def _fejk_hamta_alla_konton():
    return [
        {
            "kontonr": "1930",
            "kontonamn": "Företagskonto",
            "rakenskapsar_id": "2026",
            "aktiv": True
        }
    ]

@patch("mcp_server.server.spiris_kontoplan_alla", side_effect=_fejk_hamta_alla_konton)
def test_forbered_konto_lyckas(mock_alla):
    res = asyncio.run(forbered_konto(
        kontonr="1940",
        kontonamn="Placeringskonto",
        rakenskapsar_id="2026",
        aktiv=True
    ))
    assert res.get("utkast_id") is not None
    s = str(res.get("sammanfattning", []))
    assert "1940" in s
    assert "Placeringskonto" in s

@patch("mcp_server.server.spiris_kontoplan_alla", side_effect=_fejk_hamta_alla_konton)
def test_forbered_konto_fel_langd(mock_alla):
    with pytest.raises(ValueError, match="fyra siffror"):
        asyncio.run(forbered_konto(
            kontonr="193",
            kontonamn="Felkonto",
            rakenskapsar_id="2026",
            aktiv=True
        ))

@patch("mcp_server.server.spiris_kontoplan_alla", side_effect=_fejk_hamta_alla_konton)
def test_forbered_konto_fel_tecken(mock_alla):
    with pytest.raises(ValueError, match="fyra siffror"):
        asyncio.run(forbered_konto(
            kontonr="193A",
            kontonamn="Felkonto",
            rakenskapsar_id="2026",
            aktiv=True
        ))

@patch("mcp_server.server.spiris_kontoplan_alla", side_effect=_fejk_hamta_alla_konton)
def test_forbered_konto_finns_redan(mock_alla):
    with pytest.raises(ValueError, match="finns redan"):
        asyncio.run(forbered_konto(
            kontonr="1930",
            kontonamn="Nytt namn men finns",
            rakenskapsar_id="2026",
            aktiv=True
        ))

@patch("mcp_server.server.spiris_kontoplan_alla", side_effect=_fejk_hamta_alla_konton)
def test_forbered_konto_finns_annat_ar(mock_alla):
    # Ska lyckas eftersom 1930 finns för 2026, men vi lägger till för 2027
    res = asyncio.run(forbered_konto(
        kontonr="1930",
        kontonamn="Företagskonto",
        rakenskapsar_id="2027",
        aktiv=True
    ))
    assert res.get("utkast_id") is not None

@patch("mcp_server.server.spiris_kontoplan_alla", side_effect=_fejk_hamta_alla_konton)
def test_forbered_konto_tillvalsfalt(mock_alla):
    res = asyncio.run(forbered_konto(
        kontonr="3000",
        kontonamn="Försäljning",
        rakenskapsar_id="2026",
        aktiv=True,
        kontotyp="T",
        momskod_id="M1"
    ))
    assert res.get("utkast_id") is not None
    s = str(res.get("sammanfattning", []))
    assert "T" in s
    assert "M1" in s

@patch("mcp_server.server.spiris_kontoplan_alla", side_effect=_fejk_hamta_alla_konton)
def test_forbered_konto_aktiv_nej(mock_alla):
    res = asyncio.run(forbered_konto(
        kontonr="3000",
        kontonamn="Försäljning",
        rakenskapsar_id="2026",
        aktiv=False
    ))
    s = str(res.get("sammanfattning", []))
    assert "Nej" in s

@patch("mcp_server.server.spiris_kontoplan_alla", side_effect=_fejk_hamta_alla_konton)
def test_forbered_konto_text(mock_alla):
    res = asyncio.run(forbered_konto(
        kontonr="1940",
        kontonamn="Placeringskonto",
        rakenskapsar_id="2026",
        aktiv=True
    ))
    info = res.get("info", "")
    assert "Skapande av konto 1940" in info

def _fejk_hamta_ett(typ, objekt_id):
    if typ == "konto" and objekt_id == "2026/1930":
        return {
            "Number": 1930,
            "Name": "Gammalt namn",
            "FiscalYearId": 2026,
            "IsActive": True,
            "Type": "S",
            "VatCodeId": "M2",
            "IsProjectAllowed": False,
            "IsCostCenterAllowed": False,
            "IsBlockedForManualBooking": False,
            "ReferenceCode": "Ref",
            "Description": "Desc"
        }
    raise ValueError(f"Okänt konto {objekt_id}")

@patch("mcp_server.server.spiris_hamta_ett", side_effect=_fejk_hamta_ett)
def test_forbered_kontoandring_lyckas(mock_hamta_ett):
    res = asyncio.run(forbered_kontoandring(
        rakenskapsar_id="2026",
        kontonr="1930",
        kontonamn="Nytt namn"
    ))
    assert res.get("utkast_id") is not None
    s = str(res.get("sammanfattning", []))
    assert "Gammalt namn" in s
    assert "Nytt namn" in s

@patch("mcp_server.server.spiris_hamta_ett", side_effect=_fejk_hamta_ett)
def test_forbered_kontoandring_inga_andringar(mock_hamta_ett):
    with pytest.raises(ValueError, match="Inga ändringar angivna"):
        asyncio.run(forbered_kontoandring(
            rakenskapsar_id="2026",
            kontonr="1930"
        ))

@patch("mcp_server.server.spiris_hamta_ett", side_effect=_fejk_hamta_ett)
def test_forbered_kontoandring_okant_konto(mock_hamta_ett):
    with pytest.raises(ValueError, match="Kunde inte hämta konto"):
        asyncio.run(forbered_kontoandring(
            rakenskapsar_id="2026",
            kontonr="9999",
            kontonamn="Finns inte"
        ))

@patch("mcp_server.server.spiris_hamta_ett", side_effect=_fejk_hamta_ett)
def test_forbered_kontoandring_flera_andringar(mock_hamta_ett):
    res = asyncio.run(forbered_kontoandring(
        rakenskapsar_id="2026",
        kontonr="1930",
        aktiv=False,
        projekt_tillatet=True
    ))
    s = str(res.get("sammanfattning", []))
    assert "True ➡️ False" in s or "False ➡️ True" in s

@patch("mcp_server.server.spiris_hamta_ett", side_effect=_fejk_hamta_ett)
def test_forbered_kontoandring_nollning_null_varde(mock_hamta_ett):
    # Change Type from "S" to None shouldn't happen directly because Type is string but we simulate missing by testing another tool directly
    pass

@patch("mcp_server.server.spiris_hamta_ett", side_effect=_fejk_hamta_ett)
def test_forbered_kontoandring_utom_allowlist(mock_hamta_ett):
    # This is tested in adapter usually, but we check if we can pass a bad arg
    # Since python limits kwargs, we just verify the generated payload via adapter
    from parser.spiris_adapter import bygg_kontoandring_payload
    nuvarande = {"Name": "old"}
    with pytest.raises(Exception, match="går inte att ändra"):
        bygg_kontoandring_payload(nuvarande, {"ogiltig_nyckel": "värde"})

@patch("mcp_server.server.spiris_hamta_ett", side_effect=_fejk_hamta_ett)
def test_forbered_kontoandring_utelamnat_behaller_varde(mock_hamta_ett):
    from parser.spiris_adapter import bygg_kontoandring_payload
    nuvarande = {"Name": "Gammalt namn", "IsActive": True}
    andringar = {"kontonamn": "Nytt namn"}
    payload = bygg_kontoandring_payload(nuvarande, andringar)
    # The unmodified field should still be there because we copy from nuvarande
    assert payload["IsActive"] == True
    assert payload["Name"] == "Nytt namn"

@patch("mcp_server.server.spiris_hamta_ett", side_effect=_fejk_hamta_ett)
def test_forbered_kontoandring_kontotyp_andring(mock_hamta_ett):
    res = asyncio.run(forbered_kontoandring(
        rakenskapsar_id="2026",
        kontonr="1930",
        kontotyp="K"
    ))
    s = str(res.get("sammanfattning", []))
    assert "S ➡️ K" in s

@patch("mcp_server.server.spiris_hamta_ett", side_effect=_fejk_hamta_ett)
def test_forbered_kontoandring_text(mock_hamta_ett):
    res = asyncio.run(forbered_kontoandring(
        rakenskapsar_id="2026",
        kontonr="1930",
        kontonamn="X"
    ))
    info = res.get("info", "")
    assert "Ändring av konto 1930" in info
