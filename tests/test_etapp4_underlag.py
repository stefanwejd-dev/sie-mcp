import asyncio
import pytest
from pathlib import Path
from decimal import Decimal
import compliance
from mcp_server.server import (
    KATEGORI_UNDERLAG,
    spiris_underlag,
    spiris_hamta_underlag,
    forbered_underlagskoppling
)
from parser.spiris_klient import SpirisKlientFel

@pytest.fixture(autouse=True)
def _godkanda_villkor():
    compliance.godkann_compliance()

# Mock setup
class FakeKlient:
    def __init__(self, data=None, bin_data=None):
        self.data = data or []
        self.bin_data = bin_data or ({"FileName": "test.pdf", "ContentType": "application/pdf"}, b"fakecontent")
        self.log = []
    def hamta_alla(self, path, params=None):
        self.log.append(("GET", path, params))
        return self.data
    def hamta_binart(self, path):
        self.log.append(("GET_BIN", path))
        return self.bin_data

@pytest.fixture(autouse=True)
def _mock_spiris_rag(monkeypatch):
    from mcp_server import server
    
    async def mock_kor_spiris_verktyg(func, datakategori):
        if datakategori == KATEGORI_UNDERLAG:
            return {"data": await func(FakeKlient(data=[{
                "Id": "u1",
                "FileName": "Anna Andersson kvitto.pdf",
                "ContentType": "application/pdf",
                "AttachmentStatus": 1,
                "Type": 2,
                "AttachedDocumentType": 0,
                "DocumentId": None,
                "ImageDate": "2026-08-09T00:00:00Z",
                "TransactionDate": "2026-08-01T00:00:00Z",
                "DueDate": "2026-08-30T00:00:00Z",
                "InvoiceNumber": "123",
                "AmountInvoiceCurrency": Decimal("100.00"),
                "Vat": Decimal("25.00"),
                "CurrencyCode": "SEK",
                "SupplierName": "Anna Andersson",
                "TemporaryUrl": "https://secret.url",
                "SupplierCorporateIdentityNumber": "850101-1234",
                "Ocr": "12345",
                "Comment": "Secret note"
            }])), "info": "", "kategori": datakategori}
        else:
            return {"data": await func(FakeKlient()), "kategori": datakategori}
            
    monkeypatch.setattr(server, "_kor_spiris_verktyg", mock_kor_spiris_verktyg)

# U4.1 Tests
def test_kategori_finns():
    assert "underlag och bilagor" in KATEGORI_UNDERLAG
    assert "metadata" in KATEGORI_UNDERLAG

def test_kategori_anvands_av_verktygen(monkeypatch):
    kategorier = []
    async def mock_kor_spiris_verktyg(func, datakategori):
        kategorier.append(datakategori)
        return "ok"
    from mcp_server import server
    monkeypatch.setattr(server, "_kor_spiris_verktyg", mock_kor_spiris_verktyg)
    
    asyncio.run(spiris_underlag())
    assert KATEGORI_UNDERLAG in kategorier

# U4.2 Tests
def test_underlag_saknar_temporary_url():
    res = asyncio.run(spiris_underlag())
    rad = res["data"]["data"][0]
    assert "TemporaryUrl" not in rad
    assert "temporary_url" not in rad

def test_underlag_saknar_orgnr():
    res = asyncio.run(spiris_underlag())
    rad = res["data"]["data"][0]
    assert "SupplierCorporateIdentityNumber" not in rad
    assert "orgnr" not in rad

def test_underlag_saknar_kommentar_och_ocr():
    res = asyncio.run(spiris_underlag())
    rad = res["data"]["data"][0]
    assert "Ocr" not in rad
    assert "Comment" not in rad
    assert "ocr" not in rad
    assert "kommentar" not in rad

def test_underlag_filnamn_maskeras(monkeypatch):
    import parser.spiris_rag as rag
    monkeypatch.setattr(rag, "las_namnreferens", lambda: [("Anna Andersson", "Fysisk person 1")])
    res = asyncio.run(spiris_underlag())
    rad = res["data"]["data"][0]
    assert "Anna Andersson" not in rad["filnamn"]
    assert "PERSON_1" in rad["filnamn"] or "Maskerad" in rad["filnamn"]

def test_underlag_leverantor_maskeras(monkeypatch):
    import parser.spiris_rag as rag
    monkeypatch.setattr(rag, "las_namnreferens", lambda: [("Anna Andersson", "Fysisk person 1")])
    res = asyncio.run(spiris_underlag())
    rad = res["data"]["data"][0]
    assert "Anna Andersson" not in rad["leverantorsnamn"]
    assert rad["leverantorsnamn"] == "PERSON_1"

def test_underlag_include_matched_param(monkeypatch):
    from mcp_server import server
    import parser.spiris_rag as rag
    
    anrop = []
    async def mock_kor_spiris_verktyg(func, datakategori):
        class FKlient:
            def hamta_alla(self, path, params):
                anrop.append(params)
                return []
        return await func(FKlient())
        
    monkeypatch.setattr(server, "_kor_spiris_verktyg", mock_kor_spiris_verktyg)
    
    asyncio.run(spiris_underlag(include_matched=True))
    assert anrop[0]["includeMatched"] == "true"
    
    anrop.clear()
    asyncio.run(spiris_underlag(include_matched=False))
    assert anrop[0]["includeMatched"] == "false"

def test_underlag_ratt_datakategori():
    res = asyncio.run(spiris_underlag())
    assert res["kategori"] == KATEGORI_UNDERLAG

def test_underlag_har_ratt_falt_kvar():
    res = asyncio.run(spiris_underlag())
    rad = res["data"]["data"][0]
    assert "id" in rad
    assert "moms" in rad
    assert "belopp" in rad
    assert "transaktionsdatum" in rad
    
# U4.3 Tests
def test_hamta_underlag_ingen_fil_i_svaret(monkeypatch):
    from mcp_server import server
    async def mock_kor_spiris_verktyg(func, datakategori):
        k = FakeKlient(bin_data=({"FileName": "test.pdf", "ContentType": "application/pdf"}, b"content"))
        return await func(k)
    monkeypatch.setattr(server, "_kor_spiris_verktyg", mock_kor_spiris_verktyg)
    
    res = asyncio.run(spiris_hamta_underlag("u1"))
    assert "content" not in str(res).lower()
    assert "b64" not in str(res).lower()

def test_hamta_underlag_sparar_lokalt(monkeypatch, tmp_path):
    from mcp_server import server
    
    # Mock pathlib.Path.home to return tmp_path
    class MockPath:
        @staticmethod
        def home():
            return tmp_path
            
    monkeypatch.setattr("pathlib.Path.home", MockPath.home)
    
    async def mock_kor_spiris_verktyg(func, datakategori):
        k = FakeKlient(bin_data=({"FileName": "test.pdf", "ContentType": "application/pdf"}, b"filecontent"))
        return await func(k)
    monkeypatch.setattr(server, "_kor_spiris_verktyg", mock_kor_spiris_verktyg)
    
    res = asyncio.run(spiris_hamta_underlag("u1"))
    assert "sokvag" in res["data"]
    p = Path(res["data"]["sokvag"])
    assert p.exists()
    assert p.read_bytes() == b"filecontent"

def test_hamta_underlag_kastar_fel_vid_stor_fil(monkeypatch):
    from mcp_server import server
    async def mock_kor_spiris_verktyg(func, datakategori):
        # 26 MB
        k = FakeKlient(bin_data=({"FileName": "test.pdf", "ContentType": "application/pdf"}, b"0" * (26 * 1024 * 1024)))
        return await func(k)
    monkeypatch.setattr(server, "_kor_spiris_verktyg", mock_kor_spiris_verktyg)
    
    with pytest.raises(SpirisKlientFel) as exc:
        asyncio.run(spiris_hamta_underlag("u1"))
    assert "större än 25 MB" in str(exc.value)

def test_hamta_underlag_kategori(monkeypatch, tmp_path):
    from mcp_server import server
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    kategorier = []
    async def mock_kor_spiris_verktyg(func, datakategori):
        kategorier.append(datakategori)
        return "ok"
    monkeypatch.setattr(server, "_kor_spiris_verktyg", mock_kor_spiris_verktyg)
    
    asyncio.run(spiris_hamta_underlag("u1"))
    assert KATEGORI_UNDERLAG in kategorier

def test_hamta_underlag_retur_metadata(monkeypatch, tmp_path):
    from mcp_server import server
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    async def mock_kor_spiris_verktyg(func, datakategori):
        k = FakeKlient(bin_data=({"FileName": "test.pdf", "ContentType": "application/pdf"}, b"filecontent"))
        return await func(k)
    monkeypatch.setattr(server, "_kor_spiris_verktyg", mock_kor_spiris_verktyg)
    
    res = asyncio.run(spiris_hamta_underlag("u1"))
    assert res["data"]["filnamn"] == "test.pdf"
    assert res["data"]["storlek_byte"] == len(b"filecontent")
    assert res["data"]["filtyp"] == "application/pdf"
    
def test_hamta_underlag_fallback_namn(monkeypatch, tmp_path):
    from mcp_server import server
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    async def mock_kor_spiris_verktyg(func, datakategori):
        k = FakeKlient(bin_data=({}, b"filecontent"))
        return await func(k)
    monkeypatch.setattr(server, "_kor_spiris_verktyg", mock_kor_spiris_verktyg)
    
    res = asyncio.run(spiris_hamta_underlag("u1"))
    assert res["data"]["filnamn"] == "u1.pdf"

def test_forbered_underlagskoppling_skapar_utkast():
    res = asyncio.run(forbered_underlagskoppling("att1", "doc1", "Voucher"))
    assert res.get("utkast_id") is not None

def test_forbered_underlagskoppling_default_type():
    res = asyncio.run(forbered_underlagskoppling("att1", "doc1"))
    assert res.get("utkast_id") is not None
