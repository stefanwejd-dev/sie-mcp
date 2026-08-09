import re
import os

# 1. FIX ADAPTER
adapter_path = os.path.join("parser", "spiris_adapter.py")
with open(adapter_path, "r", encoding="utf-8") as f:
    adapter_code = f.read()

adapter_code = re.sub(
    r'def _adapter_underlag.*?return tvattad',
    '''def _adapter_underlag(klient, include_matched: bool) -> list[dict]:
    return klient.hamta_alla("/attachments", params={"includeMatched": str(include_matched).lower()})''',
    adapter_code,
    flags=re.DOTALL
)

adapter_code = re.sub(
    r'def bygg_utkast_underlagskoppling.*?payload=payload\n    \)',
    '''def bygg_utkast_underlagskoppling(underlag_id: str, dokument_id: str, dokument_typ: str) -> dict:
    return {
        "titel": "Koppla underlag",
        "beskrivning": f"Koppla bilaga {underlag_id} till dokument {dokument_id} ({dokument_typ}).",
        "typ": UTKASTTYP_UNDERLAGSKOPPLING,
        "payload": {
            "DocumentId": dokument_id,
            "AttachmentIds": [underlag_id],
            "DocumentType": dokument_typ
        }
    }''',
    adapter_code,
    flags=re.DOTALL
)

with open(adapter_path, "w", encoding="utf-8") as f:
    f.write(adapter_code)

# 2. FIX RAG
rag_path = os.path.join("parser", "spiris_rag.py")
with open(rag_path, "r", encoding="utf-8") as f:
    rag_code = f.read()

rag_code = re.sub(
    r'def hamta_underlag.*?return _envelope\(data, antal_exkluderade=0\)',
    '''def hamta_underlag(klient, include_matched: bool) -> dict:
    from parser.spiris_adapter import _adapter_underlag
    from parser.sekretesslager import skapa_kontonamnsmaskerare
    
    rå_data = asyncio.run_coroutine_threadsafe(
        asyncio.to_thread(_adapter_underlag, klient, include_matched), 
        asyncio.get_running_loop()
    ).result() if asyncio.get_running_loop().is_running() else _adapter_underlag(klient, include_matched)
    
    maskera = skapa_kontonamnsmaskerare(las_namnreferens())
    
    tvattad = []
    for r in rå_data:
        tvattad.append({
            "id": r.get("Id"),
            "filnamn": maskera(r.get("FileName", "")),
            "filtyp": r.get("ContentType"),
            "status": r.get("AttachmentStatus"),
            "typ": r.get("Type"),
            "kopplad_dokumenttyp": r.get("AttachedDocumentType"),
            "dokument_id": r.get("DocumentId"),
            "bilddatum": r.get("ImageDate"),
            "transaktionsdatum": r.get("TransactionDate"),
            "forfallodatum": r.get("DueDate"),
            "fakturanummer": r.get("InvoiceNumber"),
            "belopp": r.get("AmountInvoiceCurrency"),
            "moms": r.get("Vat"),
            "valuta": r.get("CurrencyCode"),
            "leverantorsnamn": maskera(r.get("SupplierName") or "")
        })
        
    return _envelope(tvattad, antal_exkluderade=0)''',
    rag_code,
    flags=re.DOTALL
)

# wait, `asyncio.run_coroutine_threadsafe` is wrong for `await asyncio.to_thread`.
# the function is async, so I can just await!
rag_code = rag_code.replace('''rå_data = asyncio.run_coroutine_threadsafe(
        asyncio.to_thread(_adapter_underlag, klient, include_matched), 
        asyncio.get_running_loop()
    ).result() if asyncio.get_running_loop().is_running() else _adapter_underlag(klient, include_matched)''',
    '''rå_data = await asyncio.to_thread(_adapter_underlag, klient, include_matched)''')

# Fix hamta_underlag definition to be async
rag_code = rag_code.replace('def hamta_underlag(klient, include_matched: bool) -> dict:', 'async def hamta_underlag(klient, include_matched: bool) -> dict:')

with open(rag_path, "w", encoding="utf-8") as f:
    f.write(rag_code)
