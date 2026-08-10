import os

# Fix test_etapp16_strukturer.py
fpath = "tests/test_etapp16_strukturer.py"
with open(fpath, "r", encoding="utf-8") as f:
    content = f.read()

content = content.replace("from parser.spiris_klient import _Spirisklient", "")

with open(fpath, "w", encoding="utf-8") as f:
    f.write(content)

# Fix spiris_rag.py
fpath2 = "parser/spiris_rag.py"
with open(fpath2, "r", encoding="utf-8") as f:
    content2 = f.read()

content2 = content2.replace("async def hamta_prislistor(k: _Spirisklient, ", "async def hamta_prislistor(k, ")
content2 = content2.replace("async def hamta_rabattavtal(k: _Spirisklient)", "async def hamta_rabattavtal(k)")
content2 = content2.replace("async def hamta_etiketter(k: _Spirisklient, typ: str)", "async def hamta_etiketter(k, typ: str)")

with open(fpath2, "w", encoding="utf-8") as f:
    f.write(content2)
