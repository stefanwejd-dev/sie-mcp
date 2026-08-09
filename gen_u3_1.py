import re

def main():
    # 1. Update spiris_adapter.py
    with open("parser/spiris_adapter.py", "r", encoding="utf-8") as f:
        adapter = f.read()

    new_mapping = """
def mappa_periodisering(p: dict) -> dict:
    if not p:
        return {}
    mappad = {
        "id": p.get("Id"),
        "bokforingsdatum": p.get("BookkeepingDate"),
        "belopp": Decimal(str(p.get("Amount", 0))),
        "ar_kredit": p.get("IsCredit"),
        "debetkonto": p.get("DebitAccountNumber"),
        "kreditkonto": p.get("CreditAccountNumber"),
        "beskrivning": p.get("Description"),
        "status": p.get("Status"),
        "kalldatum": p.get("SourceDate"),
        "verifikationsnummer": p.get("NumberAndNumberSeries"),
        "kalltyp": p.get("AllocationPeriodSourceType"),
        "projekt_id": p.get("ProjectId"),
        "verifikat_id": p.get("VoucherId"),
        "leverantorsfaktura_id": p.get("SupplierInvoiceId"),
        "kundfaktura_id": p.get("CustomerInvoiceId"),
    }
    # U3.1 säger att Rows -> rader (REQ), så de måste mappas.
    # AllocationPeriodRowApi har ingen spec given i U3.1 men vi kan anta att det har några fält
    # U3.1 säger: "Radnummerfälten (*Row), CostCenterItemId1-3, VoucherFiscalYearId,
    # utkast-id:na och CreatedUtc/ModifiedUtc tas inte med."
    if "Rows" in p:
        rader = []
        for r in p["Rows"]:
            rad_mappad = {
                "id": r.get("Id"),
                "bokforingsdatum": r.get("BookkeepingDate"),
                "belopp": Decimal(str(r.get("Amount", 0)))
            }
            # Filtrera None
            rader.append({k: v for k, v in rad_mappad.items() if v is not None})
        mappad["rader"] = rader

    return {k: v for k, v in mappad.items() if v is not None}

def hamta_periodiseringar(klient: _Spirisklient) -> list[dict]:
    return [mappa_periodisering(p) for p in klient.hamta_alla("/allocationperiods")]
"""
    if "def hamta_periodiseringar" not in adapter:
        adapter = adapter.replace(
            "def hamta_ingaende_balans",
            new_mapping + "\n\ndef hamta_ingaende_balans"
        )
        
    enkeluppslag = """
    "periodiseringar": "/allocationperiods",
"""
    if "\"periodiseringar\":" not in adapter:
        adapter = adapter.replace(
            "\"kundfakturor\": \"/customerinvoices\",",
            "\"kundfakturor\": \"/customerinvoices\",\n    \"periodiseringar\": \"/allocationperiods\","
        )

    # Note: U3.1 requires GET /allocationperiods/{id}. This is handled by ENKELUPPSLAG.
    # But wait, we need to map the output of ENKELUPPSLAG!
    # In `hamta_ett`, we do: if uppslagstyp == "...": return mappa_...
    hamta_ett_mapping = """
    if uppslagstyp == "periodiseringar":
        return {"periodisering": mappa_periodisering(svar)}
"""
    if "uppslagstyp == \"periodiseringar\"" not in adapter:
        adapter = adapter.replace(
            "if uppslagstyp == \"kundfakturor\":",
            hamta_ett_mapping + "\n    if uppslagstyp == \"kundfakturor\":"
        )

    with open("parser/spiris_adapter.py", "w", encoding="utf-8") as f:
        f.write(adapter)

    # 2. Update spiris_rag.py
    with open("parser/spiris_rag.py", "r", encoding="utf-8") as f:
        rag = f.read()

    new_rag = """
async def hamta_periodiseringar(klient, session) -> list[dict]:
    \"\"\"Hämtar periodiseringar och maskerar egress.\"\"\"
    anropa = lambda k: spiris_adapter.hamta_periodiseringar(k)
    rader = await spiris_session.utfor_med_session(
        klient, session, anropa, None, False
    )
    for p in rader:
        if "beskrivning" in p and p["beskrivning"]:
            p["beskrivning"] = sekretesslager.maskera_for_egress(p["beskrivning"])
    return rader
"""
    if "def hamta_periodiseringar" not in rag:
        rag = rag + "\n" + new_rag

    with open("parser/spiris_rag.py", "w", encoding="utf-8") as f:
        f.write(rag)

    # 3. Update mcp_server/server.py
    with open("mcp_server/server.py", "r", encoding="utf-8") as f:
        server = f.read()
    
    # No import needed, it uses spiris_rag.hamta_periodiseringar

    new_tool = """
@mcp.tool()
async def spiris_periodiseringar(ctx: Context | None = None) -> str:
    \"\"\"Hämtar periodiseringar (/allocationperiods).\"\"\"
    return await _las(
        ctx, KATEGORI_HUVUDBOK,
        lambda k, s: spiris_rag.hamta_periodiseringar(k, s),
        lambda data: data,  # råjson returneras
    )
"""
    if "async def spiris_periodiseringar" not in server:
        server = server.replace(
            "async def spiris_ingaende_balans",
            new_tool + "\n\n@mcp.tool()\nasync def spiris_ingaende_balans"
        )

    # 4. Update tests/test_mcp_lasande_bredd.py
    with open("tests/test_mcp_lasande_bredd.py", "r", encoding="utf-8") as f:
        test_bredd = f.read()

    if "\"spiris_periodiseringar\":" not in test_bredd:
        test_bredd = test_bredd.replace(
            "\"spiris_offerter\": lambda: spiris_offerter(),",
            "\"spiris_offerter\": lambda: spiris_offerter(),\n    \"spiris_periodiseringar\": lambda: spiris_periodiseringar(),"
        )
        test_bredd = test_bredd.replace(
            "    spiris_order,",
            "    spiris_order,\n    spiris_periodiseringar,"
        )

    with open("tests/test_mcp_lasande_bredd.py", "w", encoding="utf-8") as f:
        f.write(test_bredd)

    # 5. Update tests/test_mcp_villkorssparr.py
    with open("tests/test_mcp_villkorssparr.py", "r", encoding="utf-8") as f:
        test_sparr = f.read()

    if "spiris_periodiseringar()" not in test_sparr:
        test_sparr = test_sparr.replace(
            "        lambda: server_modul.spiris_offerter(),",
            "        lambda: server_modul.spiris_offerter(),\n        lambda: server_modul.spiris_periodiseringar(),"
        )
        test_sparr = test_sparr.replace(
            "| {\"spiris_order\", \"spiris_offerter\"}",
            "| {\"spiris_order\", \"spiris_offerter\", \"spiris_periodiseringar\"}"
        )

    with open("tests/test_mcp_villkorssparr.py", "w", encoding="utf-8") as f:
        f.write(test_sparr)

    # 6. Add tests in tests/test_etapp3_periodiseringar.py
    tests_e3 = """
from __future__ import annotations
import pytest
from decimal import Decimal
import json

from parser.spiris_adapter import mappa_periodisering, hamta_periodiseringar, hamta_ett, SpirisKlientFel

def test_mappa_periodisering_standard():
    in_data = {
        "Id": "p1",
        "BookkeepingDate": "2026-01-01",
        "Amount": 1000.5,
        "IsCredit": True,
        "DebitAccountNumber": 1930,
        "CreditAccountNumber": 2440,
        "Description": "Test desc",
        "Status": "Active",
        "SourceDate": "2026-01-01",
        "NumberAndNumberSeries": "A1",
        "AllocationPeriodSourceType": 1,
        "ProjectId": "proj1",
        "VoucherId": "v1",
        "SupplierInvoiceId": "s1",
        "CustomerInvoiceId": "c1",
        "Rows": [
            {"Id": "r1", "BookkeepingDate": "2026-02-01", "Amount": 100}
        ],
        "VoucherRow": "ignore",
        "TemporaryUrl": "ignore"
    }
    ut = mappa_periodisering(in_data)
    assert ut["id"] == "p1"
    assert ut["bokforingsdatum"] == "2026-01-01"
    assert ut["belopp"] == Decimal("1000.5")
    assert ut["ar_kredit"] is True
    assert ut["beskrivning"] == "Test desc"
    assert len(ut["rader"]) == 1
    assert ut["rader"][0]["id"] == "r1"
    assert "VoucherRow" not in ut
    assert "TemporaryUrl" not in ut

def test_mappa_periodisering_tom():
    assert mappa_periodisering({}) == {}

def test_hamta_periodiseringar_anropar_klient():
    class FejkKlient:
        def hamta_alla(self, path):
            assert path == "/allocationperiods"
            return [{"Id": "1"}]
    res = hamta_periodiseringar(FejkKlient())
    assert len(res) == 1
    assert res[0]["id"] == "1"

def test_hamta_ett_periodisering():
    class FejkKlient:
        def hamta_en(self, path):
            assert path == "/allocationperiods/1"
            return {"Id": "1"}
    res = hamta_ett(FejkKlient(), "periodiseringar", "1")
    assert "periodisering" in res
    assert res["periodisering"]["id"] == "1"

import parser.spiris_rag as spiris_rag
import saker_lagring
import asyncio

@pytest.mark.asyncio
async def test_rag_maskering_periodiseringar(monkeypatch):
    class FejkKlient:
        pass
    class FejkSession:
        client_id = "test"
    
    async def mock_utfor(klient, session, func, mask_func, a):
        return func(klient)
        
    monkeypatch.setattr(spiris_rag.spiris_session, "utfor_med_session", mock_utfor)
    monkeypatch.setattr(spiris_rag.spiris_adapter, "hamta_periodiseringar", lambda k: [{"beskrivning": "Johan Andersson"}])
    monkeypatch.setattr(spiris_rag.sekretesslager, "maskera_for_egress", lambda s: "MASKERAD")
    
    rader = await spiris_rag.hamta_periodiseringar(FejkKlient(), FejkSession())
    assert rader[0]["beskrivning"] == "MASKERAD"
"""
    with open("tests/test_etapp3_periodiseringar.py", "w", encoding="utf-8") as f:
        f.write(tests_e3)

if __name__ == "__main__":
    main()
