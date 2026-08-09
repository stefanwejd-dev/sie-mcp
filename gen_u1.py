import re
from pathlib import Path
import os

adapter = Path("G:/My Drive/Claude Cowork/sie-mcp/parser/spiris_adapter.py")
server = Path("G:/My Drive/Claude Cowork/sie-mcp/mcp_server/server.py")
rag = Path("G:/My Drive/Claude Cowork/sie-mcp/parser/spiris_rag.py")
tests = Path("G:/My Drive/Claude Cowork/sie-mcp/tests/test_spiris_adapter.py")

# Update U1.5 in adapter
c = adapter.read_text("utf-8")
c = re.sub(
    r'def hamta_ett\(klient: _Spirisklient, typ: str, objekt_id: str\) -> dict:.*?(?=\n\n|\Z)',
    '''class _EnkelKlient:
    def __init__(self, rå: dict):
        self.rå = rå
    def hamta_alla(self, path: str, **kwargs) -> list[dict]:
        return [self.rå]

def hamta_ett(klient: _Spirisklient, typ: str, objekt_id: str) -> dict:
    """Rått enkeluppslag för djupfelsökning."""
    if not objekt_id or not objekt_id.strip():
        raise ValueError("objekt_id får inte vara tomt")
    if typ not in _ENKELUPPSLAG:
        raise ValueError(f"okänd typ: {typ}")
    
    rå = klient.hamta_en(f"{_ENKELUPPSLAG[typ]}/{objekt_id}")
    fk = _EnkelKlient(rå)
    
    if typ == "kundfaktura": return hamta_kundfakturor(fk)[0]
    if typ == "leverantorsfaktura": return hamta_leverantorsfakturor(fk)[0]
    if typ == "order": return hamta_order(fk)[0]
    if typ == "offert": return hamta_offerter(fk)[0]
    if typ == "kund": return hamta_kunder(fk)[0]
    if typ == "leverantor": return hamta_leverantorer(fk)[0]
    if typ == "artikel": return hamta_artiklar(fk)[0]
    if typ == "projekt": return hamta_projekt(fk)[0]
    if typ == "momsrapport": return hamta_momsrapporter(fk)[0]
    if typ == "verifikatutkast": return {"verifikat": mappa_verifikatutkast(rå)}
    if typ in ("kundfakturautkast", "leverantorsfakturautkast"): return rå
    return rå''',
    c, flags=re.DOTALL
)

# Also add U1.6 adapter functions
u16 = '''
def hamta_valutakurs(klient: _Spirisklient, datum: str, fran_valuta: str, till_valuta: str) -> dict:
    rå = klient.hamta_en("/currencies/exchangerate", params={"date": datum, "sourceCurrency": fran_valuta, "targetCurrency": till_valuta})
    return {
        "datum": rå.get("Date"),
        "fran_valuta": rå.get("SourceCurrency"),
        "till_valuta": rå.get("TargetCurrency"),
        "kurs": rå.get("Rate"),
    }

def hamta_anlaggningstillgangar(klient: _Spirisklient) -> list[dict]:
    etikett = skapa_kontonamnsmaskerare(las_namnreferens())
    rader = []
    for rå in klient.hamta_alla("/inventoryitems"):
        rader.append({
            "nummer": rå.get("Number"),
            "benamning": etikett(rå.get("Name") or ""),
            "anskaffningsvarde": rå.get("PurchasePrice"),
            "anskaffningsdatum": str(rå.get("PurchaseDate"))[:10] if rå.get("PurchaseDate") else None,
            "bokfort_varde": rå.get("CurrentValue"),
            "restvarde": rå.get("ResidualValue"),
            "livslangd_manader": rå.get("LifeSpanInMonths"),
            "senaste_avskrivning": str(rå.get("LatestDepreciationDate"))[:10] if rå.get("LatestDepreciationDate") else None,
            "status": rå.get("InventoryItemStatus"),
        })
    return rader

def hamta_kundreskontraposter(klient: _Spirisklient) -> list[dict]:
    rader = []
    for rå in klient.hamta_alla("/customerledgeritems"):
        rader.append({
            "kund_id": rå.get("CustomerId"),
            "fakturanr": rå.get("InvoiceNumber"),
            "fakturadatum": str(rå.get("InvoiceDate"))[:10] if rå.get("InvoiceDate") else None,
            "forfallodatum": str(rå.get("DueDate"))[:10] if rå.get("DueDate") else None,
            "belopp": rå.get("TotalAmountInvoiceCurrency"),
            "kvarvarande": rå.get("RemainingAmountInvoiceCurrency"),
            "ar_kredit": bool(rå.get("IsCreditInvoice", False)),
            "valuta": rå.get("CurrencyCode"),
            "verifikat_id": rå.get("VoucherId"),
            "id": rå.get("Id"),
            "betalreferens": rå.get("PaymentReferenceNumber"),
        })
    return rader

def hamta_anvandare(klient: _Spirisklient) -> list[dict]:
    vakt = _bygg_namnvakt()
    rader = []
    for rå in klient.hamta_alla("/users"):
        namn = f"{rå.get('FirstName', '')} {rå.get('LastName', '')}".strip()
        visat, _ = _motpartsnamn(namn, "", False, vakt)
        rader.append({
            "id": rå.get("Id"),
            "namn": visat,
            "aktiv": bool(rå.get("IsActive", False)),
            "ar_konsult": bool(rå.get("IsConsultant", False)),
            "far_attestera_leverantorsfakturor": bool(rå.get("HasPurchaseInvoicesApprovalPermission", False)),
            "far_attestera_momsrapporter": bool(rå.get("HasVATReportsApprovalPermission", False)),
        })
    return rader
'''
if "def hamta_valutakurs" not in c:
    c += u16
adapter.write_text(c, "utf-8")
