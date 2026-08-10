import os
from pathlib import Path

# 1. Fix parser/spiris_rag.py
fpath = "parser/spiris_rag.py"
content = Path(fpath).read_text(encoding="utf-8")

content = content.replace("async def hamta_prislistor", "def hamta_prislistor")
content = content.replace("async def hamta_rabattavtal", "def hamta_rabattavtal")
content = content.replace("async def hamta_etiketter", "def hamta_etiketter")
content = content.replace("await asynk_hamta_alla(", "k.hamta_alla(")

Path(fpath).write_text(content, encoding="utf-8")


# 2. Fix mcp_server/server.py
fpath2 = "mcp_server/server.py"
content2 = Path(fpath2).read_text(encoding="utf-8")

old_server = """@mcp.tool()
async def spiris_prislistor(prislista_id: str | None = None) -> list[dict]:
    \"\"\"Hämtar prislistor (KATEGORI_STRUKTUR).
    
    Om prislista_id inte anges returneras alla upplagda prislistor.
    Om prislista_id anges (från Id-fältet i en prislista) returneras alla artikelpriser i den listan.
    \"\"\"
    import parser.spiris_rag as spiris_rag
    k = bygg_klient()
    return await spiris_rag.hamta_prislistor(k, prislista_id)


@mcp.tool()
async def spiris_rabattavtal() -> list[dict]:
    \"\"\"Hämtar rabattavtal (KATEGORI_STRUKTUR).\"\"\"
    import parser.spiris_rag as spiris_rag
    k = bygg_klient()
    return await spiris_rag.hamta_rabattavtal(k)


@mcp.tool()
async def spiris_etiketter(typ: str) -> list[dict]:
    \"\"\"Hämtar etiketter för antingen kunder eller artiklar (KATEGORI_STRUKTUR).
    
    Args:
        typ: Måste vara antingen "kund" eller "artikel".
    \"\"\"
    import parser.spiris_rag as spiris_rag
    k = bygg_klient()
    return await spiris_rag.hamta_etiketter(k, typ)"""

new_server = """@mcp.tool()
async def spiris_prislistor(prislista_id: str | None = None) -> dict:
    \"\"\"Hämtar prislistor (KATEGORI_STRUKTUR).
    
    Om prislista_id inte anges returneras alla upplagda prislistor.
    Om prislista_id anges (från Id-fältet i en prislista) returneras alla artikelpriser i den listan.
    \"\"\"
    return await _kor_spiris_verktyg(lambda k: spiris_rag.hamta_prislistor(k, prislista_id), KATEGORI_STRUKTUR)


@mcp.tool()
async def spiris_rabattavtal() -> dict:
    \"\"\"Hämtar rabattavtal (KATEGORI_STRUKTUR).\"\"\"
    return await _kor_spiris_verktyg(lambda k: spiris_rag.hamta_rabattavtal(k), KATEGORI_STRUKTUR)


@mcp.tool()
async def spiris_etiketter(typ: str) -> dict:
    \"\"\"Hämtar etiketter för antingen kunder eller artiklar (KATEGORI_STRUKTUR).
    
    Args:
        typ: Måste vara antingen "kund" eller "artikel".
    \"\"\"
    return await _kor_spiris_verktyg(lambda k: spiris_rag.hamta_etiketter(k, typ), KATEGORI_STRUKTUR)"""

content2 = content2.replace(old_server, new_server)
Path(fpath2).write_text(content2, encoding="utf-8")

# 3. Fix tests/test_etapp16_strukturer.py
fpath3 = "tests/test_etapp16_strukturer.py"
content3 = Path(fpath3).read_text(encoding="utf-8")
content3 = content3.replace("asyncio.run(", "")
content3 = content3.replace("))", ")")
content3 = content3.replace('("ogiltig"))', '("ogiltig")')
content3 = content3.replace("def asynk_hamta_alla", "def hamta_alla")
Path(fpath3).write_text(content3, encoding="utf-8")
