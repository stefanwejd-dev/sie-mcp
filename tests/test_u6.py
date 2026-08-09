import asyncio
import json
import pytest

import compliance
import mcp_server.server as server

def test_resurs_sparr_om_ogiltiga_villkor(monkeypatch, tmp_path):
    monkeypatch.setenv("SIE_MCP_DATAROT", str(tmp_path))
    svar = asyncio.run(server.res_foretag())
    data = json.loads(svar)
    assert "Blockerad: användarvillkoren" in data.get("info", "")

def test_resurser_ok_nar_godkanda(monkeypatch, tmp_path):
    monkeypatch.setenv("SIE_MCP_DATAROT", str(tmp_path))
    compliance.godkann_compliance()
    
    svar_foretag = asyncio.run(server.res_foretag())
    assert "Ingen giltig Spiris-session" in json.loads(svar_foretag).get("info", "")

    svar_ar = asyncio.run(server.res_rakenskapsar())
    assert "Ingen giltig Spiris-session" in json.loads(svar_ar).get("info", "")

    svar_plan = asyncio.run(server.res_kontoplan("ar-1"))
    assert "Ingen giltig Spiris-session" in json.loads(svar_plan).get("info", "")

    svar_villkor = server.res_villkor()
    data = json.loads(svar_villkor)
    assert data["godkant"] is True

def test_prompter():
    p1 = server.stam_av_banken()
    assert "Inget skrivs förrän" in p1

    p2 = server.granska_momsperioden()
    assert "Inget skrivs förrän" in p2
    
    p3 = server.manadsavstamning()
    assert "Inget skrivs förrän" in p3
    
    p4 = server.granska_kundfordringar()
    assert "Inget skrivs förrän" in p4

    p5 = server.forbered_bokslutsposter()
    assert "Inget skrivs förrän" in p5
