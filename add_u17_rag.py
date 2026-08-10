import os

fpath = "parser/spiris_rag.py"
with open(fpath, "r", encoding="utf-8") as f:
    content = f.read()

new_code = '''
def hamta_en_verifikation(k, rakenskapsar_id: str, verifikation_id: str) -> dict:
    """U17.1 — spiris_verifikation"""
    if not rakenskapsar_id or not verifikation_id:
        raise ValueError("Både rakenskapsar_id och verifikation_id måste anges")
    
    rå = k.hamta_en(f"/vouchers/{rakenskapsar_id}/{verifikation_id}")
    return mappa_verifikation(rå)


def hamta_en_bankhandelse(k, bankkonto_id: str, handelse_id: str) -> dict:
    """U17.2 — spiris_bankhandelse"""
    if not bankkonto_id or not handelse_id:
        raise ValueError("Både bankkonto_id och handelse_id måste anges")
        
    rå = k.hamta_en(f"/banktransactions/{bankkonto_id}/{handelse_id}")
    return {
        "Id": rå.get("Id"),
        "BankAccountId": rå.get("BankAccountId"),
        "Amount": str(rå.get("Amount")) if rå.get("Amount") is not None else None,
        "TransactionDate": rå.get("TransactionDate"),
        "Description": rå.get("Description"),
        "Reference": rå.get("Reference"),
        "MatchId": rå.get("MatchId")
    }
'''

content += new_code

with open(fpath, "w", encoding="utf-8") as f:
    f.write(content)
