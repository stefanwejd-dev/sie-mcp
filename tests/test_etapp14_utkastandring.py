import pytest
from parser.spiris_adapter import bygg_utkastuppdatering, SpirisKlientFel

# --- U14.1 Kundfaktura ---

def test_kf_framgang_och_obligatoriska():
    nuvarande = {
        "Id": "123",
        "InvoiceDate": "2026-01-01",
        "RotReducedInvoicingType": "rot",
        "EuThirdParty": False,
        "TotalAmount": 100
    }
    andringar = {
        "InvoiceDate": "2026-01-02",
        "YourReference": "Sven"
    }
    uppdaterat = bygg_utkastuppdatering(nuvarande, andringar, "kundfaktura")
    
    assert uppdaterat["InvoiceDate"] == "2026-01-02"
    assert uppdaterat["YourReference"] == "Sven"
    
    # Obligatoriska fält från spec (inkl. read-modify-write) ska finnas kvar
    # och serverägda fält också
    assert uppdaterat["RotReducedInvoicingType"] == "rot"
    assert uppdaterat["EuThirdParty"] is False
    assert uppdaterat["Id"] == "123"
    assert uppdaterat["TotalAmount"] == 100

def test_kf_las_motpart():
    with pytest.raises(SpirisKlientFel, match="CustomerId"):
        bygg_utkastuppdatering({"CustomerId": "1"}, {"CustomerId": "2"}, "kundfaktura")

def test_kf_las_valuta():
    with pytest.raises(SpirisKlientFel, match="InvoiceCurrencyCode"):
        bygg_utkastuppdatering({"InvoiceCurrencyCode": "SEK"}, {"InvoiceCurrencyCode": "EUR"}, "kundfaktura")

def test_kf_las_skatt():
    with pytest.raises(SpirisKlientFel, match="MaxAllowedTaxReductionAmount"):
        bygg_utkastuppdatering({}, {"MaxAllowedTaxReductionAmount": 100}, "kundfaktura")

def test_kf_las_serveragda():
    with pytest.raises(SpirisKlientFel, match="CreatedUtc"):
        bygg_utkastuppdatering({}, {"CreatedUtc": "2026-01-01"}, "kundfaktura")

def test_kf_las_harledda_belopp():
    with pytest.raises(SpirisKlientFel, match="TotalAmount"):
        bygg_utkastuppdatering({}, {"TotalAmount": 500}, "kundfaktura")

def test_kf_las_egna_resurser():
    with pytest.raises(SpirisKlientFel, match="Notes"):
        bygg_utkastuppdatering({}, {"Notes": []}, "kundfaktura")

def test_kf_las_byggtjanst():
    with pytest.raises(SpirisKlientFel, match="ReverseChargeOnConstructionServices"):
        bygg_utkastuppdatering({}, {"ReverseChargeOnConstructionServices": True}, "kundfaktura")

def test_kf_las_utanfor_omfattning():
    with pytest.raises(SpirisKlientFel, match="IsDirectDebit"):
        bygg_utkastuppdatering({}, {"IsDirectDebit": True}, "kundfaktura")


# --- U14.2 Leverantörsfaktura ---

def test_lf_framgang_och_obligatoriska():
    nuvarande = {
        "SupplierId": "SUP1",
        "IsCreditInvoice": False,
        "Rows": [{"ArticleNumber": "1"}],
        "Message": "Hej"
    }
    andringar = {
        "Message": "Nytt hej"
    }
    uppdaterat = bygg_utkastuppdatering(nuvarande, andringar, "leverantorsfaktura")
    
    assert uppdaterat["Message"] == "Nytt hej"
    assert uppdaterat["SupplierId"] == "SUP1"
    assert uppdaterat["IsCreditInvoice"] is False
    assert len(uppdaterat["Rows"]) == 1

def test_lf_las_motpart():
    with pytest.raises(SpirisKlientFel, match="SupplierNumber"):
        bygg_utkastuppdatering({}, {"SupplierNumber": "123"}, "leverantorsfaktura")

def test_lf_las_valuta():
    with pytest.raises(SpirisKlientFel, match="CurrencyCode"):
        bygg_utkastuppdatering({}, {"CurrencyCode": "EUR"}, "leverantorsfaktura")

def test_lf_las_harledda():
    with pytest.raises(SpirisKlientFel, match="VatHigh"):
        bygg_utkastuppdatering({}, {"VatHigh": 200}, "leverantorsfaktura")

def test_lf_las_serveragda():
    with pytest.raises(SpirisKlientFel, match="Id"):
        bygg_utkastuppdatering({}, {"Id": "22"}, "leverantorsfaktura")

def test_lf_las_attestkedjan():
    with pytest.raises(SpirisKlientFel, match="ApprovalStatus"):
        bygg_utkastuppdatering({}, {"ApprovalStatus": "1"}, "leverantorsfaktura")

def test_lf_las_periodisering():
    with pytest.raises(SpirisKlientFel, match="AllocationPeriods"):
        bygg_utkastuppdatering({}, {"AllocationPeriods": []}, "leverantorsfaktura")

def test_lf_las_egna_endpoints():
    with pytest.raises(SpirisKlientFel, match="Attachments"):
        bygg_utkastuppdatering({}, {"Attachments": 3}, "leverantorsfaktura")

def test_lf_las_utanfor_omfattning():
    with pytest.raises(SpirisKlientFel, match="IsQuickInvoice"):
        bygg_utkastuppdatering({}, {"IsQuickInvoice": True}, "leverantorsfaktura")
