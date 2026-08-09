import os
import re

# 1. FIX spiris_rag.py to add hamta_underlag_fil
rag_path = os.path.join("parser", "spiris_rag.py")
with open(rag_path, "r", encoding="utf-8") as f:
    rag_code = f.read()

if "hamta_underlag_fil" not in rag_code:
    rag_code += '''
async def hamta_underlag_fil(klient, underlag_id: str) -> dict:
    from parser.spiris_adapter import _adapter_hamta_underlag_fil
    import asyncio
    data = await asyncio.to_thread(_adapter_hamta_underlag_fil, klient, underlag_id)
    from parser.spiris_rag import _envelope
    return _envelope(data, antal_exkluderade=0)
'''
    with open(rag_path, "w", encoding="utf-8") as f:
        f.write(rag_code)

# 2. FIX utkast.py to add underlagskoppling to GILTIGA_TYPER
utkast_path = os.path.join("parser", "utkast.py")
with open(utkast_path, "r", encoding="utf-8") as f:
    utkast_code = f.read()

if '"underlagskoppling"' not in utkast_code:
    utkast_code = utkast_code.replace('"sie4import",', '"sie4import",\n    "underlagskoppling",')
    with open(utkast_path, "w", encoding="utf-8") as f:
        f.write(utkast_code)

# 3. FIX tests (mock las_namnreferens)
test_path = os.path.join("tests", "test_etapp4_underlag.py")
with open(test_path, "r", encoding="utf-8") as f:
    test_code = f.read()

test_code = test_code.replace('def test_underlag_filnamn_maskeras():', 'def test_underlag_filnamn_maskeras(monkeypatch):\n    import parser.sekretesslager as sek\n    monkeypatch.setattr(sek, "las_namnreferens", lambda: [("Anna Andersson", "Fysisk person 1")])')
test_code = test_code.replace('def test_underlag_leverantor_maskeras():', 'def test_underlag_leverantor_maskeras(monkeypatch):\n    import parser.sekretesslager as sek\n    monkeypatch.setattr(sek, "las_namnreferens", lambda: [("Anna Andersson", "Fysisk person 1")])')

# Also fix the _f in server to use mock utkast.skapa by removing the mock inside the test and using monkeypatch properly.
# Oh, my previous test patch for test_forbered_underlagskoppling_skapar_utkast actually does mock `utkast.skapa`. Let's see if it works after utkast_code fix.
# Wait, the tool is called via `asyncio.run(forbered_underlagskoppling("att1", "doc1"))`. The tool imports `utkast` inside the function, so it uses `sys.modules["parser.utkast"]`. `monkeypatch.setattr(utkast, "skapa", ...)` should work.
# Wait! In the mock `mock_kor_spiris_verktyg`, we completely bypassed `_f`? No, we didn't!
# `_f` isn't called! `_kor_spiris_verktyg` in the test mock was returning `{"data": await func(FakeKlient()), "kategori": datakategori}`!
# But `func` in `forbered_underlagskoppling` is `_f`. So it calls `_f(FakeKlient())`, which calls `utkast.skapa`!
# Let's fix test_forbered_underlagskoppling_skapar_utkast mock just in case.

with open(test_path, "w", encoding="utf-8") as f:
    f.write(test_code)
