import os
import re

path = "parser/spiris_adapter.py"
with open(path, "r", encoding="utf-8") as f:
    text = f.read()

# 1. Add UTKASTTYP_BETALNINGSVERIFIKAT
if 'UTKASTTYP_BETALNINGSVERIFIKAT' not in text:
    text = text.replace('UTKASTTYP_LEVERANTORSBETALNING = "leverantorsbetalning"', 'UTKASTTYP_LEVERANTORSBETALNING = "leverantorsbetalning"\nUTKASTTYP_BETALNINGSVERIFIKAT = "betalningsverifikat"')

# 2. Add handlers at end of file (or somewhere)
if 'def skapa_betalningsverifikat' not in text:
    funcs = """
def _bygg_betalningsverifikat_payload(nyttolast: dict) -> dict:
    return {
        "VoucherDate": nyttolast["transaktionsdatum"],
        "VoucherText": nyttolast["beskrivning"],
        "Rows": [
            {
                "AccountNumber": int(rad["konto"]),
                "DebitAmount": Decimal(str(rad.get("debet") or 0)),
                "CreditAmount": Decimal(str(rad.get("kredit") or 0)),
                "TransactionText": rad.get("text") or "",
            }
            for rad in nyttolast["rader"]
        ],
    }

def skapa_betalningsverifikat(klient: _Spirisklient, payload: dict) -> dict:
    return klient.skicka("/voucherwithoverunderpayment", payload)

def hamta_kvittningskandidater(klient: _Spirisklient, faktura_id: str) -> list[dict]:
    return klient.hamta_alla(f"/supplierinvoices/{faktura_id}/offsetcandidates")
"""
    text = text + "\n" + funcs

# 3. Add to utfor_utkast
utfor = """
    if typ == "verifikat":
        payload = _bygg_verifikat_payload(nyttolast)
        if mal == MAL_UTKAST:
            return skapa_verifikatutkast(klient, payload)
        return skapa_verifikat(klient, payload)

    if typ == UTKASTTYP_BETALNINGSVERIFIKAT:
        payload = _bygg_betalningsverifikat_payload(nyttolast)
        return skapa_betalningsverifikat(klient, payload)

    raise SpirisKlientFel(f"Okänd utkasttyp: {typ!r}.")"""

if 'if typ == UTKASTTYP_BETALNINGSVERIFIKAT:' not in text:
    text = re.sub(
        r'    if typ == "verifikat":\n        payload = _bygg_verifikat_payload\(nyttolast\)\n        if mal == MAL_UTKAST:\n            return skapa_verifikatutkast\(klient, payload\)\n        return skapa_verifikat\(klient, payload\)\n\n    raise SpirisKlientFel\(f"Okänd utkasttyp: \{typ!r\}\."\)',
        utfor.strip('\n'),
        text,
        flags=re.MULTILINE
    )

with open(path, "w", encoding="utf-8") as f:
    f.write(text)

