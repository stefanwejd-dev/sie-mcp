import os

fpath = "parser/spiris_adapter.py"
with open(fpath, "r", encoding="utf-8") as f:
    content = f.read()

new_funcs = '''
def hamta_en_verifikation(klient: _Spirisklient, rakenskapsar_id: str, verifikat_id: str) -> dict:
    """U17.1 — GET /vouchers/{fiscalyearId}/{voucherId}"""
    if not rakenskapsar_id or not verifikat_id:
        raise ValueError("Både rakenskapsar_id och verifikat_id måste anges")
    rå = klient.hamta_en(f"/vouchers/{rakenskapsar_id}/{verifikat_id}")
    return mappa_verifikation(rå)


def hamta_en_bankhandelse(klient: _Spirisklient, bankkonto_id: str, handelse_id: str) -> dict:
    """U17.2 — GET /banktransactions/{bankAccountId}/{bankTransactionId}"""
    if not bankkonto_id or not handelse_id:
        raise ValueError("Både bankkonto_id och handelse_id måste anges")
    h = klient.hamta_en(f"/banktransactions/{bankkonto_id}/{handelse_id}")
    
    konteringar = []
    for r in h.get("Rows") or []:
        konteringar.append({
            "verifikat_id": r.get("VoucherId"),
            "verifikatnummer": str(r.get("PaymentVoucherNumber") or ""),
            "belopp": r.get("AmountTransactionCurrency"),
            "kalla": r.get("Source"),
        })

    datum = str(h.get("TransactionDate") or "")[:10]
    return {
        "id": h["Id"],
        "datum": datum,
        "avstamd": bool(h.get("IsReconciled", False)),
        "belopp": h.get("TransactionAmount"),
        "originalbelopp": h.get("OriginalAmount"),
        "avgift": h.get("ChargeAmount"),
        "valuta": h.get("TransactionAmountCurrency") or "",
        "antal_konteringsrader": len(konteringar),
        "konteringar": konteringar,
    }
'''

content += new_funcs

with open(fpath, "w", encoding="utf-8") as f:
    f.write(content)
