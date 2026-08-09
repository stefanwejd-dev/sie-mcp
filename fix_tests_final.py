import os
import re

# 1. Update test_etapp5.py
with open("tests/test_etapp5.py", "r", encoding="utf-8") as f:
    code = f.read()

code = code.replace(
    'with pytest.raises(ValueError, match="balanserar inte"):\n        asyncio.run(server.forbered_betalningsverifikat("Test", "2026-01-01", [{"konto": "1930", "debet": 100, "kredit": 0}]))',
    'svar = asyncio.run(server.forbered_betalningsverifikat("Test", "2026-01-01", [{"konto": "1930", "debet": 100, "kredit": 0}]))\n    assert svar["utkast_id"] is None'
)

code = code.replace(
    'assert "Förslag:" in res["meddelande"]',
    'assert "föreslås" in res["info"]'
)

with open("tests/test_etapp5.py", "w", encoding="utf-8") as f:
    f.write(code)

# 2. Update parser/spiris_rag.py
with open("parser/spiris_rag.py", "r", encoding="utf-8") as f:
    code = f.read()

if "skapa_motpartsmaskerare" not in code.splitlines()[38]:
    code = code.replace(
        'from sekretesslager import maskera_siefil, skapa_kontonamnsmaskerare',
        'from sekretesslager import maskera_siefil, skapa_kontonamnsmaskerare, skapa_motpartsmaskerare'
    )
    with open("parser/spiris_rag.py", "w", encoding="utf-8") as f:
        f.write(code)
