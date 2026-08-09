import re
from pathlib import Path

server = Path("G:/My Drive/Claude Cowork/sie-mcp/mcp_server/server.py")
c = server.read_text("utf-8")

# Remove the subagent's spiris_hamta_ett tool
c = re.sub(
    r'@mcp\.tool\(\)\s*async def spiris_hamta_ett.*?return await _kor_spiris_verktyg[^\n]+\n[^\n]+\n',
    '',
    c,
    flags=re.DOTALL
)

# Append all the missing tools
u15_ser = '''
@mcp.tool()
async def spiris_hamta_ett(typ: str, objekt_id: str) -> dict:
    """Enkeluppslag av ett specifikt objekt (t.ex. kundfaktura, leverantörsfaktura, order, etc)."""
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

c += u15_ser

# Check aliases
if 'alias_hamta_ett = spiris_hamta_ett' not in c:
    c += '''
alias_hamta_ett = spiris_hamta_ett
alias_valutakurs = spiris_valutakurs
alias_anlaggningstillgangar = spiris_anlaggningstillgangar
alias_kundreskontraposter = spiris_kundreskontraposter
alias_anvandare = spiris_anvandare
'''
server.write_text(c, "utf-8")
