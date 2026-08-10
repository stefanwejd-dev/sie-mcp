import pytest

from parser.spiris_rag import hamta_en_verifikation, hamta_en_bankhandelse
from parser.spiris_klient import SpirisKlientFel

class MockKlient:
    def __init__(self, tvinga_fel=False):
        self.tvinga_fel = tvinga_fel
        
    def hamta_en(self, path: str, **kwargs):
        if self.tvinga_fel:
            raise SpirisKlientFel("Fel")
            
        if path == "/companysettings":
            return {"Name": "Testbolag", "CorporateIdentityNumber": "555555-5555"}
        
        if path.startswith("/vouchers/"):
            return {
                "VoucherDate": "2026-08-10",
                "VoucherText": "Test verifikat",
                "Rows": [
                    {"AccountNumber": 1930, "DebitAmount": 100, "CreditAmount": 0, "TransactionText": "Debet"},
                    {"AccountNumber": 3000, "DebitAmount": 0, "CreditAmount": 100, "TransactionText": "Kredit"}
                ],
                "NumberAndNumberSeries": "A12",
                "NumberSeries": "A",
                "VoucherType": 1
            }
            
        if path.startswith("/banktransactions/"):
            return {
                "Id": "t-1",
                "BankAccountId": "b-1",
                "Amount": 100.5,
                "TransactionDate": "2026-08-10T12:00:00",
                "Description": "Test betalning",
                "Reference": "INV-123",
                "MatchId": "m-1"
            }
        
        return {}


def test_hamta_en_verifikation_lyckas():
    k = MockKlient()
    res = hamta_en_verifikation(k, "fy-1", "v-1")
    assert res["serie"] == "A"
    assert res["vernr"] == "12"
    assert res["vertext"] == "Test verifikat"
    assert len(res["rader"]) == 2

def test_hamta_en_verifikation_saknar_arg():
    k = MockKlient()
    with pytest.raises(ValueError):
        hamta_en_verifikation(k, "", "v-1")
    with pytest.raises(ValueError):
        hamta_en_verifikation(k, "fy-1", "")

def test_hamta_en_verifikation_klientfel():
    k = MockKlient(tvinga_fel=True)
    with pytest.raises(SpirisKlientFel):
        hamta_en_verifikation(k, "fy-1", "v-1")

def test_hamta_en_verifikation_maskerad():
    class MockKlientSecret(MockKlient):
        def hamta_en(self, path: str, **kwargs):
            if path == "/companysettings":
                return {"Name": "Testbolag", "CorporateIdentityNumber": "555555-5555"}
            if path.startswith("/vouchers/"):
                return {
                    "VoucherDate": "2026-08-10",
                    "VoucherText": "Känslig Anna Andersson", # Borde maskeras eller döljas
                    "Rows": [
                        {"AccountNumber": 1930, "DebitAmount": 100, "CreditAmount": 0, "TransactionText": ""},
                        {"AccountNumber": 3000, "DebitAmount": 0, "CreditAmount": 100, "TransactionText": ""}
                    ],
                    "NumberAndNumberSeries": "A12",
                    "NumberSeries": "A",
                    "VoucherType": 1
                }
            return {}
    
    k = MockKlientSecret()
    res = hamta_en_verifikation(k, "fy-1", "v-1")
    # Anna Andersson maskeras av sekretesslagret till Pseudonym 1 eller liknande, eller döljs
    assert "Anna Andersson" not in res.get("vertext", "")

def test_hamta_en_bankhandelse_lyckas():
    k = MockKlient()
    res = hamta_en_bankhandelse(k, "b-1", "t-1")
    assert res["Id"] == "t-1"
    assert res["Amount"] == "100.5"
    assert res["Reference"] == "INV-123"

def test_hamta_en_bankhandelse_saknar_arg():
    k = MockKlient()
    with pytest.raises(ValueError):
        hamta_en_bankhandelse(k, "", "t-1")
    with pytest.raises(ValueError):
        hamta_en_bankhandelse(k, "b-1", "")

def test_hamta_en_bankhandelse_klientfel():
    k = MockKlient(tvinga_fel=True)
    with pytest.raises(SpirisKlientFel):
        hamta_en_bankhandelse(k, "b-1", "t-1")

