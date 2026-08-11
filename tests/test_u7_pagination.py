from __future__ import annotations
import asyncio
from typing import Any
import pytest
import copy

from parser.spiris_rag import _envelope

# 1. Testa _envelope (den underliggande motorn)
def test_envelope_utan_limit_returnerar_allt():
    data = [{"id": i} for i in range(10)]
    svar = _envelope(data, 0, offset=0, limit=0)
    assert svar["totalt_antal"] == 10
    assert svar["visade"] == 10
    assert svar["trunkerat"] is False
    assert len(svar["data"]) == 10

def test_envelope_med_limit_och_mer_data_finns():
    data = [{"id": i} for i in range(10)]
    svar = _envelope(data, 0, offset=0, limit=5)
    assert svar["totalt_antal"] == 10
    assert svar["visade"] == 5
    assert svar["trunkerat"] is True
    assert "TRUNKERAT:" in svar["info"]
    assert "offset=5" in svar["info"]
    assert len(svar["data"]) == 5

def test_envelope_offset_och_limit_tillsammans():
    data = [{"id": i} for i in range(10)]
    svar = _envelope(data, 0, offset=5, limit=5)
    assert svar["totalt_antal"] == 10
    assert svar["visade"] == 5
    assert svar["trunkerat"] is False
    assert "TRUNKERAT" not in svar["info"]
    assert svar["data"][0]["id"] == 5

def test_envelope_trunkeringstexten_innehaller_korrekta_varderingar():
    data = [{"id": i} for i in range(15)]
    svar = _envelope(data, 2, offset=3, limit=5)
    assert svar["totalt_antal"] == 15
    assert svar["visade"] == 5
    assert svar["trunkerat"] is True
    assert svar["antal_exkluderade"] == 2
    assert "2 poster exkluderades" in svar["info"]
    assert "TRUNKERAT: Visar 5 av 15" in svar["info"]
    assert "offset=8" in svar["info"]
    assert "limit=5" in svar["info"]


# 2. Testa integrationen i verktygen via spiris_rag
import compliance

class DummyKlient:
    pass

@pytest.fixture(autouse=True)
def _mock_klient(monkeypatch, tmp_path):
    monkeypatch.setenv("SIE_MCP_DATAROT", str(tmp_path))
    compliance.godkann_compliance()

def test_spiris_kundfakturor_har_pagination(monkeypatch):
    import parser.spiris_rag as rag
    
    def mock_hamta_kundfakturor(k):
        return [{"fakturanr": str(i)} for i in range(12)]
    
    monkeypatch.setattr(rag, "_adapter_kundfakturor", mock_hamta_kundfakturor)
    
    klient = DummyKlient()
    svar = asyncio.run(rag.hamta_kundfakturor(klient, offset=2, limit=4))
        
    assert svar["totalt_antal"] == 12
    assert svar["visade"] == 4
    assert svar["trunkerat"] is True
    assert len(svar["data"]) == 4
    assert svar["data"][0]["fakturanr"] == "2"

def test_spiris_kundreskontra_har_pagination(monkeypatch):
    import parser.spiris_rag as rag
    
    class DummyKundPost:
        def __init__(self, i):
            self.kund = f"Kund {i}"
            self.belopp = 100
            self.betalstatus = "Obetald"
            self.maskerad = False
            self.forfallodatum = "2026-01-01"
            self.motpart_id = "123"
            
    def mock_hamta_kundreskontra(k):
        return [DummyKundPost(i) for i in range(10)]
    
    monkeypatch.setattr(rag, "_adapter_kundreskontra", mock_hamta_kundreskontra)
    monkeypatch.setattr(rag, "maskera_for_egress", lambda p: p)
    
    klient = DummyKlient()
    svar = asyncio.run(rag.hamta_kundreskontra_rag(klient, offset=0, limit=9))
    assert svar["totalt_antal"] == 10
    assert svar["visade"] == 9
    assert svar["trunkerat"] is True
    
def test_spiris_leverantorsreskontra_har_pagination(monkeypatch):
    import parser.spiris_rag as rag
    
    class DummyLevPost:
        def __init__(self, i):
            self.leverantor = f"Lev {i}"
            self.belopp = 100
            self.betalstatus = "Obetald"
            self.maskerad = False
            self.forfallodatum = "2026-01-01"
            self.motpart_id = "123"
            
    def mock_reskontra(k):
        return [DummyLevPost(i) for i in range(10)]
    
    monkeypatch.setattr(rag, "_adapter_reskontra", mock_reskontra)
    monkeypatch.setattr(rag, "maskera_for_egress", lambda p: p)
    
    klient = DummyKlient()
    svar = asyncio.run(rag.hamta_leverantorsreskontra(klient, offset=9, limit=10))
    assert svar["totalt_antal"] == 10
    assert svar["visade"] == 1
    assert svar["trunkerat"] is False
    assert len(svar["data"]) == 1

def test_spiris_underlag_har_pagination(monkeypatch):
    import parser.spiris_adapter as adapter
    import parser.spiris_rag as rag
    
    def mock_underlag(k, include_matched):
        return [{"Id": str(i)} for i in range(3)]
        
    monkeypatch.setattr(adapter, "hamta_underlag", mock_underlag)
    monkeypatch.setattr(rag, "skapa_kontonamnsmaskerare", lambda x: lambda text: text)
    
    klient = DummyKlient()
    svar = asyncio.run(rag.hamta_underlag(klient, include_matched=False, offset=0, limit=2))
    
    assert svar["totalt_antal"] == 3
    assert svar["visade"] == 2
    assert svar["trunkerat"] is True

def test_spiris_kontotransaktioner_har_pagination(monkeypatch):
    import parser.spiris_rag as rag
    from domain_model import SIEFil, Verifikation, Transaktion, Konto
    from datetime import date
    from decimal import Decimal
    
    def mock_bygg(*args, **kwargs):
        vers = []
        for i in range(5):
            t = Transaktion(kontonr="1910", belopp=Decimal("100"), transtext="Trx")
            v = Verifikation(serie="A", vernr=f"A{i}", verdatum=date(2026,1,1), vertext="Text", transaktioner=[t])
            vers.append(v)
        return SIEFil(
            konton={"1910": Konto("1910", "Kassa", 1)},
            verifikationer=vers
        )
    
    monkeypatch.setattr(rag, "_bygg_verifikat_sie", mock_bygg)
    monkeypatch.setattr(rag, "las_namnreferens", lambda: {})
    
    klient = DummyKlient()
    svar = asyncio.run(rag.hamta_kontotransaktioner(klient, "ar-id", "1910", offset=1, limit=2))
    assert svar["totalt_antal"] == 5
    assert svar["visade"] == 2
    assert svar["trunkerat"] is True
    assert len(svar["data"]) == 2

def test_spiris_verifikationer_alla_har_pagination(monkeypatch):
    import parser.spiris_rag as rag
    
    def mock_adapter(*args, **kwargs):
        return [
            {
                "serie": "A",
                "datum": "2026-01-01",
                "text": "Text",
                "rader": [{"kontonr": "1910", "belopp": "100", "transtext": "Trx"}]
            }
        ] * 6
    
    monkeypatch.setattr(rag, "_adapter_verifikationer_alla", mock_adapter)
    monkeypatch.setattr(rag, "las_namnreferens", lambda: {})
    
    klient = DummyKlient()
    svar = asyncio.run(rag.hamta_verifikationer_alla(klient, offset=4, limit=10))
    assert svar["totalt_antal"] == 6
    assert svar["visade"] == 2
    assert svar["trunkerat"] is False
    assert len(svar["data"]) == 2
