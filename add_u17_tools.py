import os
from pathlib import Path

fpath = "mcp_server/server.py"
content = Path(fpath).read_text(encoding="utf-8")

new_tools = '''

@mcp.tool()
async def spiris_verifikation(rakenskapsar_id: str, verifikation_id: str) -> dict:
    """Hämtar en specifik verifikation (KATEGORI_HUVUDBOK)."""
    return await _kor_spiris_verktyg(lambda k: spiris_rag.hamta_en_verifikation(k, rakenskapsar_id, verifikation_id), KATEGORI_HUVUDBOK)


@mcp.tool()
async def spiris_bankhandelse(bankkonto_id: str, handelse_id: str) -> dict:
    """Hämtar en specifik bankhändelse (KATEGORI_HUVUDBOK)."""
    return await _kor_spiris_verktyg(lambda k: spiris_rag.hamta_en_bankhandelse(k, bankkonto_id, handelse_id), KATEGORI_HUVUDBOK)
'''

# Find a good place to insert, maybe right before 'def _maskera' or something.
# We can just append it at the end of the file.
content += new_tools

Path(fpath).write_text(content, encoding="utf-8")
