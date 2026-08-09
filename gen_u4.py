import os
import re

# 1. Update mcp_server/server.py
server_path = os.path.join("mcp_server", "server.py")
with open(server_path, "r", encoding="utf-8") as f:
    server_code = f.read()

kategori_underlag = 'KATEGORI_UNDERLAG = "underlag och bilagor (filnamn och metadata)"\n'
if "KATEGORI_UNDERLAG" not in server_code:
    server_code = server_code.replace(
        'KATEGORI_UTKAST = "utkastförslag (ej utfört)"',
        'KATEGORI_UTKAST = "utkastförslag (ej utfört)"\n' + kategori_underlag
    )

tools_code = '''
@mcp.tool()
async def spiris_underlag(include_matched: bool = False) -> str:
    """Listar underlag/bilagor i Spiris (t.ex. inscannade kvitton). Returnerar envelope.
    Filnamnet, som ofta innehåller fritext, och leverantörsnamnet maskeras via namnregistret.
    include_matched=False ger endast o-kopplade (obokförda) underlag."""
    return await _kor_spiris_verktyg(lambda k: spiris_rag.hamta_underlag(k, include_matched), KATEGORI_UNDERLAG)

@mcp.tool()
async def spiris_hamta_underlag(underlag_id: str) -> str:
    """Laddar ner ett underlag från Spiris (max 25 MB) och sparar det lokalt.
    Returnerar sökvägen till den sparade filen samt metadata, INTE filens innehåll.
    Detta verktyg maskerar inte innehållet inuti PDF/bilden."""
    return await _kor_spiris_verktyg(lambda k: spiris_rag.hamta_underlag_fil(k, underlag_id), KATEGORI_UNDERLAG)

@mcp.tool()
async def forbered_underlagskoppling(underlag_id: str, dokument_id: str, dokument_typ: str = "SupplierInvoice") -> str:
    """Skapar ett utkast för att koppla ett befintligt underlag till ett befintligt dokument.
    dokument_typ är oftast 'SupplierInvoice' (Leverantörsfaktura) eller 'Voucher' (Verifikat)."""
    async def _f(klient):
        import utkast
        from parser.spiris_adapter import bygg_utkast_underlagskoppling
        u = bygg_utkast_underlagskoppling(underlag_id, dokument_id, dokument_typ)
        return utkast.spara_utkast(u)
    return await _kor_spiris_verktyg(_f, KATEGORI_UTKAST)
'''

if "spiris_underlag" not in server_code:
    # Append to bottom before main
    server_code = server_code.replace(
        'if __name__ == "__main__":',
        tools_code + '\nif __name__ == "__main__":'
    )

with open(server_path, "w", encoding="utf-8") as f:
    f.write(server_code)

# 2. Update parser/spiris_rag.py
rag_path = os.path.join("parser", "spiris_rag.py")
with open(rag_path, "r", encoding="utf-8") as f:
    rag_code = f.read()

rag_tools = '''
async def hamta_underlag(klient, include_matched: bool) -> dict[str, Any]:
    """Hämtar underlag och maskerar fritext och motpart."""
    from parser.spiris_adapter import _adapter_underlag
    data = await asyncio.to_thread(_adapter_underlag, klient, include_matched)
    return _envelope(data, antal_exkluderade=0)

async def hamta_underlag_fil(klient, underlag_id: str) -> dict[str, Any]:
    """Laddar ner fil via klient och adapter."""
    from parser.spiris_adapter import _adapter_hamta_underlag_fil
    data = await asyncio.to_thread(_adapter_hamta_underlag_fil, klient, underlag_id)
    return _envelope(data, antal_exkluderade=0)
'''
if "hamta_underlag(" not in rag_code:
    rag_code += '\n' + rag_tools

with open(rag_path, "w", encoding="utf-8") as f:
    f.write(rag_code)

# 3. Update parser/spiris_adapter.py
adapter_path = os.path.join("parser", "spiris_adapter.py")
with open(adapter_path, "r", encoding="utf-8") as f:
    adapter_code = f.read()

adapter_utkast = '''
UTKASTTYP_UNDERLAGSKOPPLING = "underlagskoppling"

def bygg_utkast_underlagskoppling(underlag_id: str, dokument_id: str, dokument_typ: str) -> dict[str, Any]:
    payload = {
        "DocumentId": dokument_id,
        "AttachmentIds": [underlag_id],
        "DocumentType": dokument_typ
    }
    return bygg_utkastuppdatering(
        titel="Koppla underlag",
        beskrivning=f"Koppla bilaga {underlag_id} till dokument {dokument_id} ({dokument_typ}).",
        typ=UTKASTTYP_UNDERLAGSKOPPLING,
        payload=payload
    )
'''

adapter_func = '''
def _adapter_underlag(klient, include_matched: bool) -> list[dict[str, Any]]:
    # 1. Hämta data
    res = klient.hamta_alla("/attachments", params={"includeMatched": str(include_matched).lower()})
    
    # 2. Tvätta och mappa (U4.2 spec)
    from parser.sekretesslager import las_namnreferens, skapa_kontonamnsmaskerare
    from parser.reskontra_tvatt import maskera_for_egress
    maskera = skapa_kontonamnsmaskerare(las_namnreferens())
    
    tvattad = []
    for r in res:
        namn = r.get("SupplierName") or ""
        # maskera som motpart enligt U4.2 (juridisk person = klartext, fysisk = stabil, okänd = stabil)
        if namn:
            # We wrap it in a dummy list to use maskera_for_egress if we want, or just simple masking.
            # actually we can just pass it through maskera_for_egress:
            # maskera_for_egress takes a list of reskontra and returns tvättad
            # To be simple and comply with "maskeras som motpart, inte som etikett":
            # the easiest way is to let maskera_for_egress handle a dummy object, or use `maskera_for_egress` if it supports single strings?
            # It doesn't. We'll use the same logic or just maskera() for now, or build a dummy post.
            pass
            
        # I2: TemporaryUrl, SupplierCorporateIdentityNumber MUST NOT be present.
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
            "leverantorsnamn": maskera(r.get("SupplierName", ""))  # fallback to maskera, U4.2 says "som motpart", we can do a dummy
        })
    
    # Fix the leverantorsnamn using actual reskontra_tvatt if needed, but for now maskera() applies names.
    # U4.2: "maskeras som motpart, inte som etikett" -> This means using PII scrubber on physical person names.
    # In reskontra_tvatt, `maskera_namn` is used. We can import it.
    from parser.reskontra_tvatt import maskera_namn
    for t in tvattad:
        t["leverantorsnamn"] = maskera_namn(t["leverantorsnamn"])
    return tvattad

def _adapter_hamta_underlag_fil(klient, underlag_id: str) -> dict[str, Any]:
    # U4.3 spec
    url = f"https://eaccountingapi.vismaonline.com/v2/attachments/{underlag_id}"
    from pathlib import Path
    import os
    
    # We must use U0.3's hamta_binart
    meta, content = klient.hamta_binart(url)
    
    if len(content) > 25 * 1024 * 1024:
        from parser.spiris_klient import SpirisKlientFel
        raise SpirisKlientFel("Underlaget är större än 25 MB och kan inte laddas ner.")
        
    filnamn = meta.get("FileName") or f"{underlag_id}.pdf"
    
    import platform
    home = Path.home()
    if platform.system() == "Windows":
        dl_dir = home / "Downloads"
    else:
        dl_dir = home / "Downloads"
        
    sokvag = dl_dir / filnamn
    sokvag.write_bytes(content)
    
    return {
        "sokvag": str(sokvag),
        "filnamn": filnamn,
        "storlek_byte": len(content),
        "filtyp": meta.get("ContentType")
    }
'''

if "UTKASTTYP_UNDERLAGSKOPPLING" not in adapter_code:
    adapter_code = adapter_code.replace(
        'UTKASTTYP_SIE4IMPORT = "sie4import"',
        'UTKASTTYP_SIE4IMPORT = "sie4import"\n' + adapter_utkast
    )
    
    adapter_code = adapter_code.replace(
        'if typ == UTKASTTYP_SIE4IMPORT:',
        'if typ == UTKASTTYP_SIE4IMPORT:\n        res = klient.skicka("/sie4import", n)\n    if typ == UTKASTTYP_UNDERLAGSKOPPLING:\n        res = klient.skicka("/attachmentlinks", n)'
    )

if "_adapter_underlag" not in adapter_code:
    adapter_code += '\n' + adapter_func

with open(adapter_path, "w", encoding="utf-8") as f:
    f.write(adapter_code)

print("Etapp 4 scaffolded.")
