import os
import re

# 1. parser/utkast.py
path_utkast = "parser/utkast.py"
with open(path_utkast, "r", encoding="utf-8") as f:
    code = f.read()
if '"betalningsverifikat"' not in code:
    code = code.replace('"verifikat",', '"verifikat",\n    "betalningsverifikat",')
    with open(path_utkast, "w", encoding="utf-8") as f:
        f.write(code)

# 2. parser/spiris_adapter.py
path_adapter = "parser/spiris_adapter.py"
with open(path_adapter, "r", encoding="utf-8") as f:
    code = f.read()

if "UTKASTTYP_BETALNINGSVERIFIKAT" not in code:
    # Add constant
    code = code.replace('UTKASTTYP_ATTEST = "attest"', 'UTKASTTYP_ATTEST = "attest"\nUTKASTTYP_BETALNINGSVERIFIKAT = "betalningsverifikat"')
    
    # Add payload builder
    builder_code = """
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
    code = code.replace('def _bygg_verifikat_payload(', builder_code + '\ndef _bygg_verifikat_payload(')

    # Add to utfor_utkast
    utfor_code = """
    if typ == UTKASTTYP_BETALNINGSVERIFIKAT:
        payload = _bygg_betalningsverifikat_payload(nyttolast)
        return skapa_betalningsverifikat(klient, payload)

    raise SpirisKlientFel"""
    code = code.replace('    raise SpirisKlientFel', utfor_code)
    
    with open(path_adapter, "w", encoding="utf-8") as f:
        f.write(code)

# 3. parser/spiris_rag.py
path_rag = "parser/spiris_rag.py"
with open(path_rag, "r", encoding="utf-8") as f:
    code = f.read()

if "hamta_kvittningskandidater" not in code:
    code = code.replace('from spiris_adapter import (', 'from spiris_adapter import (\n    hamta_kvittningskandidater as _adapter_kvittningskandidater,')
    
    rag_code = """
async def hamta_kvittningskandidater(klient, faktura_id: str) -> list[dict]:
    kandidater = await asyncio.to_thread(_adapter_kvittningskandidater, klient, faktura_id)
    maskerare = skapa_motpartsmaskerare(las_namnreferens())
    return [
        {
            "faktura_id": k.get("InvoiceId") or "",
            "fakturanr": k.get("InvoiceNumber") or "",
            "fakturadatum": k.get("InvoiceDate") or "",
            "leverantor": maskerare.maskera(k.get("SupplierName") or ""),
            "kvarvarande": str(k.get("RemainingAmount") or "0"),
            "valuta": k.get("CurrencyCode") or "",
        }
        for k in kandidater
    ]
"""
    code += rag_code
    with open(path_rag, "w", encoding="utf-8") as f:
        f.write(code)

# 4. parser/atgardsformular.py
path_atg = "parser/atgardsformular.py"
with open(path_atg, "r", encoding="utf-8") as f:
    code = f.read()

if "BETALNINGSVERIFIKAT" not in code:
    form_code = """
def _betalningsverifikat_nyttolast(v: dict) -> dict:
    try:
        rader = json.loads(v.get("rader", "[]"))
    except json.JSONDecodeError:
        raise ValueError("Rader måste vara giltig JSON.")
        
    if not isinstance(rader, list):
        raise ValueError("Rader måste vara en JSON-lista.")
        
    debet = kredit = 0.0
    for rad in rader:
        if not isinstance(rad, dict):
            continue
        debet += float(rad.get("debet") or 0)
        kredit += float(rad.get("kredit") or 0)
        
    if abs(debet - kredit) > 0.005 or not rader:
        raise ValueError(f"Verifikatet balanserar inte. Debet: {debet:.2f}, Kredit: {kredit:.2f}")

    return {
        "beskrivning": v.get("beskrivning", ""),
        "transaktionsdatum": v.get("datum", ""),
        "rader": rader,
    }

BETALNINGSVERIFIKAT = Atgardsformular(
    utkasttyp="betalningsverifikat",
    rubrik="Nytt betalningsverifikat",
    ikon="💸",
    falt=(
        Falt("beskrivning", "Beskrivning", "text"),
        Falt("datum", "Datum", "datum"),
        Falt("rader", "Rader (konto/debet/kredit/text)", "text", hjalptext="JSON-lista med rader"),
    ),
    bygg_nyttolast=_betalningsverifikat_nyttolast,
    bygg_sammanfattning=_verifikat_sammanfattning
)
"""
    code = code.replace("ALLA_FORMULAR = [", form_code + "\nALLA_FORMULAR = [\n    BETALNINGSVERIFIKAT,")
    
    # Also add it to __all__ or exports if any? Wait, python doesn't strictly need it unless __all__ is used.
    # Let's check for __all__? There isn't any in atgardsformular.py.
    
    with open(path_atg, "w", encoding="utf-8") as f:
        f.write(code)

# 5. mcp_server/server.py
path_server = "mcp_server/server.py"
with open(path_server, "r", encoding="utf-8") as f:
    code = f.read()

if "spiris_kvittningskandidater" not in code:
    server_code = """
@mcp.tool()
async def spiris_kvittningskandidater(faktura_id: str) -> dict:
    '''Hämtar kvittningskandidater för en kreditfaktura (leverantör).'''
    return await _kor_spiris_verktyg(lambda k: spiris_rag.hamta_kvittningskandidater(k, faktura_id), KATEGORI_RESKONTRA)

@mcp.tool()
async def forbered_betalningsverifikat(
    beskrivning: str,
    transaktionsdatum: str,
    rader: list[dict],
    ctx: Context | None = None,
) -> dict:
    '''Förbereder ett betalningsverifikat för över- eller underbetalning.
    
    rader: lista med {"konto": kontonummer, "debet": tal, "kredit": tal, "text": radtext}.
    Måste balansera.'''
    _rensade: list[dict] = []
    _debet = _kredit = 0.0
    for _rad in rader:
        _d = float(_rad.get("debet") or 0)
        _k = float(_rad.get("kredit") or 0)
        _rensade.append({
            "konto": str(_rad.get("konto") or ""), "debet": _d, "kredit": _k,
            "text": str(_rad.get("text") or ""),
        })
        _debet += _d
        _kredit += _k
    sammanfattning = [
        ["Beskrivning", beskrivning],
        ["Datum", transaktionsdatum],
        ["Debet", f"{_debet:,.2f}"],
        ["Kredit", f"{_kredit:,.2f}"],
    ]
    if abs(_debet - _kredit) > 0.005 or not _rensade:
        raise ValueError(f"Verifikatet balanserar inte! Debet: {_debet:.2f}, Kredit: {_kredit:.2f}")

    def _bygg(u_id: str):
        utkast.skapa(
            utkasttyp="betalningsverifikat",
            utkast_id=u_id,
            varden={
                "beskrivning": beskrivning,
                "datum": transaktionsdatum,
                "rader": json.dumps(_rensade),
            },
        )
    return await _kor_utkastverktyg(
        _bygg, ctx, f"Förslag: betalningsverifikat på {_debet:,.2f} kr", sammanfattning
    )
"""
    code += server_code
    with open(path_server, "w", encoding="utf-8") as f:
        f.write(code)

# 6. tests/test_etapp5.py
test_code = """
import pytest
import asyncio
from parser import spiris_adapter, spiris_rag, utkast, atgardsformular
from mcp_server import server

class MockKlient:
    def __init__(self):
        self.skickat = []
    def hamta_alla(self, path, params=None):
        if "offsetcandidates" in path:
            return [{"InvoiceId": "inv-1", "InvoiceNumber": "123", "InvoiceDate": "2026-01-01", "SupplierName": "Abc", "RemainingAmount": "100.5", "CurrencyCode": "SEK"}]
        return []
    def skicka(self, path, payload):
        self.skickat.append((path, payload))
        return {"Id": "res-1"}

def test_kvittningskandidater_adapter():
    k = MockKlient()
    res = spiris_adapter.hamta_kvittningskandidater(k, "c-1")
    assert len(res) == 1
    assert res[0]["InvoiceId"] == "inv-1"

@pytest.mark.asyncio
async def test_kvittningskandidater_rag():
    k = MockKlient()
    res = await spiris_rag.hamta_kvittningskandidater(k, "c-1")
    assert len(res) == 1
    assert res[0]["leverantor"] != "Abc" # Maskerad

def test_forbered_betalningsverifikat_balans():
    with pytest.raises(ValueError, match="balanserar inte"):
        asyncio.run(server.forbered_betalningsverifikat("Test", "2026-01-01", [{"konto": "1930", "debet": 100, "kredit": 0}]))

def test_forbered_betalningsverifikat_ok():
    res = asyncio.run(server.forbered_betalningsverifikat("Test", "2026-01-01", [{"konto": "1930", "debet": 100, "kredit": 0}, {"konto": "2440", "debet": 0, "kredit": 100}]))
    assert "Förslag:" in res["data"]
"""
with open("tests/test_etapp5.py", "w", encoding="utf-8") as f:
    f.write(test_code)

# Ensure tests imports are correct for new functions
def add_to_lasande(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        code = f.read()
    if "spiris_kvittningskandidater" not in code:
        code = code.replace("spiris_hamta_underlag,\n)", "spiris_hamta_underlag,\n    spiris_kvittningskandidater,\n)")
        code = code.replace('"spiris_hamta_underlag":', '"spiris_kvittningskandidater": lambda: spiris_kvittningskandidater("123"),\n    "spiris_hamta_underlag":')
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(code)

def add_to_sparr(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        code = f.read()
    if "spiris_kvittningskandidater" not in code:
        code = code.replace("spiris_hamta_underlag,\n)", "spiris_hamta_underlag,\n    spiris_kvittningskandidater,\n)")
        code = code.replace('"spiris_hamta_underlag":', '"spiris_kvittningskandidater": ("123",),\n    "spiris_hamta_underlag":')
        code = code.replace('"spiris_hamta_underlag": spiris_hamta_underlag,', '"spiris_kvittningskandidater": spiris_kvittningskandidater,\n    "spiris_hamta_underlag": spiris_hamta_underlag,')
        if '"forbered_betalningsverifikat"' not in code:
            code = code.replace('{"forbered_periodisering",', '{"forbered_periodisering", "forbered_betalningsverifikat",')
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(code)

add_to_lasande("tests/test_mcp_lasande_bredd.py")
add_to_sparr("tests/test_mcp_villkorssparr.py")
