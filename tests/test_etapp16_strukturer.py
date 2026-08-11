import pytest
import asyncio

from parser.spiris_adapter import hamta_prislistor, hamta_rabattavtal, hamta_etiketter

class MockKlient:
    def __init__(self):
        self.anrop = []
    
    def hamta_alla(self, url, **kwargs):
        self.anrop.append(url)
        if "/salespricelists" == url:
            return [{"Id": "l-1", "Name": "Lista 1", "Number": 1, "CurrencyCode": "SEK", "IsStandard": True, "IsActive": True, "Note": "Hemlig"}]
        elif url.startswith("/salespricelists/prices/"):
            return [{"SalesPriceListId": "l-1", "ArticleId": "a-1", "NetPrice": 100, "GrossPrice": 125, "CurrencyCode": "SEK", "ChangedUtc": "2026"}]
        elif url == "/discountagreements":
            return [{"Id": "d-1", "Name": "Rabatt", "Number": 1, "IsActive": True, "Notes": "Hemlig"}]
        elif url == "/customerlabels":
            return [{"Id": "c-1", "Name": "VIP", "Description": "VIP Kund"}]
        elif url == "/articlelabels":
            return [{"Id": "a-1", "Name": "Premium", "Description": "Premium Artikel"}]
        return []

def test_prislistor_alla():
    k = MockKlient()
    res = hamta_prislistor(k)
    assert len(res) == 1
    assert res[0]["Name"] == "Lista 1"
    assert "Note" not in res[0]
    assert k.anrop == ["/salespricelists"]

def test_prislistor_priser():
    k = MockKlient()
    res = hamta_prislistor(k, "l-1")
    assert len(res) == 1
    assert res[0]["NetPrice"] == "100"
    assert "ChangedUtc" not in res[0]
    assert k.anrop == ["/salespricelists/prices/l-1"]

def test_rabattavtal():
    k = MockKlient()
    res = hamta_rabattavtal(k)
    assert len(res) == 1
    assert res[0]["Name"] == "Rabatt"
    assert "Notes" not in res[0]
    assert k.anrop == ["/discountagreements"]

def test_etiketter_kund():
    k = MockKlient()
    res = hamta_etiketter(k, "kund")
    assert len(res) == 1
    assert res[0]["Name"] == "VIP"
    assert k.anrop == ["/customerlabels"]

def test_etiketter_artikel():
    k = MockKlient()
    res = hamta_etiketter(k, "artikel")
    assert len(res) == 1
    assert res[0]["Name"] == "Premium"
    assert k.anrop == ["/articlelabels"]

def test_etiketter_ogiltig():
    k = MockKlient()
    with pytest.raises(ValueError):
        hamta_etiketter(k, "ogiltig")
