import os

fpath = "mcp_server/server.py"
with open(fpath, "r", encoding="utf-8") as f:
    content = f.read()

new_tools = '''
@mcp.tool()
async def spiris_prislistor(prislista_id: str | None = None) -> list[dict]:
    """Hämtar prislistor (KATEGORI_STRUKTUR).
    
    Om prislista_id inte anges returneras alla upplagda prislistor.
    Om prislista_id anges (från Id-fältet i en prislista) returneras alla artikelpriser i den listan.
    """
    import parser.spiris_rag as spiris_rag
    k = bygg_klient()
    return await spiris_rag.hamta_prislistor(k, prislista_id)


@mcp.tool()
async def spiris_rabattavtal() -> list[dict]:
    """Hämtar rabattavtal (KATEGORI_STRUKTUR)."""
    import parser.spiris_rag as spiris_rag
    k = bygg_klient()
    return await spiris_rag.hamta_rabattavtal(k)


@mcp.tool()
async def spiris_etiketter(typ: str) -> list[dict]:
    """Hämtar etiketter för antingen kunder eller artiklar (KATEGORI_STRUKTUR).
    
    Args:
        typ: Måste vara antingen "kund" eller "artikel".
    """
    import parser.spiris_rag as spiris_rag
    k = bygg_klient()
    return await spiris_rag.hamta_etiketter(k, typ)
'''

# Find a good place to insert, maybe right before 'def _maskera' or something.
# Better: just append it before # --- Fältbyggare --- or similar.
# Let's see if we can insert it at the end of the file. Actually, at the end of the tool definitions.

# Let's grep for 'def forbered_offertutkast' and insert before it?
# Or insert it before the alias tools.
'''
