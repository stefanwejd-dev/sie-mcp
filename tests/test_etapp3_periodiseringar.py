
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

def test_rag_maskering_periodiseringar(monkeypatch):
    class FejkKlient:
        def hamta_alla(self, path):
            return [{"Description": "Johan Andersson"}]
    
    import parser.spiris_rag as spiris_rag_mod
    from dataclasses import dataclass
    @dataclass
    class FejkMaskering:
        text: str
    
    # Eftersom spiris_rag gör en lokal import, vi kan mocka sekretesslager direkt via sys.modules 
    # eller mocka maskera_chattmeddelande i parser.sekretesslager.
    import parser.sekretesslager
    import sys
    sys.modules["sekretesslager"] = parser.sekretesslager
    monkeypatch.setattr(parser.sekretesslager, "maskera_chattmeddelande", lambda s, ref=None: FejkMaskering("MASKERAD"))
    
    rader = spiris_rag.hamta_periodiseringar(FejkKlient())
    assert rader[0]["beskrivning"] == "MASKERAD"

