import re
from pathlib import Path

rag = Path("G:/My Drive/Claude Cowork/sie-mcp/parser/spiris_rag.py")
server = Path("G:/My Drive/Claude Cowork/sie-mcp/mcp_server/server.py")

c_rag = rag.read_text("utf-8")
u15_rag = '''
async def hamta_ett(klient: _Spirisklient, typ: str, objekt_id: str) -> dict[str, Any]:
    from spiris_adapter import hamta_ett as _adapter_hamta_ett
    res = await asyncio.to_thread(_adapter_hamta_ett, klient, typ, objekt_id)
    return _envelope(res if isinstance(res, list) else [res], antal_exkluderade=0)

async def hamta_valutakurs(klient: _Spirisklient, datum: str, fran_valuta: str, till_valuta: str) -> dict[str, Any]:
    from spiris_adapter import hamta_valutakurs as _adapter_valutakurs
    res = await asyncio.to_thread(_adapter_valutakurs, klient, datum, fran_valuta, till_valuta)
    return _envelope([res], antal_exkluderade=0)

async def hamta_anlaggningstillgangar(klient: _Spirisklient) -> dict[str, Any]:
    from spiris_adapter import hamta_anlaggningstillgangar as _adapter_anlaggningstillgangar
    res = await asyncio.to_thread(_adapter_anlaggningstillgangar, klient)
    return _envelope(res, antal_exkluderade=0)

async def hamta_kundreskontraposter(klient: _Spirisklient) -> dict[str, Any]:
    from spiris_adapter import hamta_kundreskontraposter as _adapter_kundreskontraposter
    res = await asyncio.to_thread(_adapter_kundreskontraposter, klient)
    return _envelope(res, antal_exkluderade=0)

async def hamta_anvandare(klient: _Spirisklient) -> dict[str, Any]:
    from spiris_adapter import hamta_anvandare as _adapter_anvandare
    res = await asyncio.to_thread(_adapter_anvandare, klient)
    return _envelope(res, antal_exkluderade=0)
'''
if "def hamta_ett(" not in c_rag:
    c_rag += u15_rag
rag.write_text(c_rag, "utf-8")

c_ser = server.read_text("utf-8")
u15_ser = '''
@mcp.tool()
async def spiris_hamta_ett(typ: str, objekt_id: str) -> dict:
    """Enkeluppslag av ett specifikt objekt (t.ex. kundfaktura, leverantörsfaktura, order, etc)."""
    # Kategori beror på typ:
    if typ in ("kund", "leverantor", "anvandare"): kat = KATEGORI_MOTPARTSREGISTER
    elif "utkast" in typ: kat = KATEGORI_UTKAST
    elif "faktura" in typ: kat = KATEGORI_RESKONTRA
    else: kat = KATEGORI_STRUKTUR
    return await _kor_spiris_verktyg(lambda k: spiris_rag.hamta_ett(k, typ, objekt_id), kat)

@mcp.tool()
async def spiris_valutakurs(datum: str, fran_valuta: str, till_valuta: str) -> dict:
    """Hämtar valutakurs."""
    return await _kor_spiris_verktyg(lambda k: spiris_rag.hamta_valutakurs(k, datum, fran_valuta, till_valuta), KATEGORI_STRUKTUR)

@mcp.tool()
async def spiris_anlaggningstillgangar() -> dict:
    """Hämtar anläggningstillgångar."""
    return await _kor_spiris_verktyg(lambda k: spiris_rag.hamta_anlaggningstillgangar(k), KATEGORI_HUVUDBOK)

@mcp.tool()
async def spiris_kundreskontraposter() -> dict:
    """Hämtar kundreskontraposter."""
    return await _kor_spiris_verktyg(lambda k: spiris_rag.hamta_kundreskontraposter(k), KATEGORI_RESKONTRA)

@mcp.tool()
async def spiris_anvandare() -> dict:
    """Hämtar användare (personuppgifter maskeras som motpart)."""
    return await _kor_spiris_verktyg(lambda k: spiris_rag.hamta_anvandare(k), KATEGORI_MOTPARTSREGISTER)
'''
if "def spiris_hamta_ett(" not in c_ser:
    c_ser += u15_ser
server.write_text(c_ser, "utf-8")
