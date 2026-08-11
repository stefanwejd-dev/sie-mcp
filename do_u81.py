import re

with open('parser/spiris_adapter.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace _adapter_underlag with hamta_underlag
content = content.replace("def _adapter_underlag(klient, include_matched: bool) -> list[dict]:", "def hamta_underlag(klient, include_matched: bool = False) -> list[dict]:")

# Replace _adapter_hamta_underlag_fil
pattern = r"def _adapter_hamta_underlag_fil\(klient, underlag_id: str\) -> dict\[str, Any\]:.*?(?=\n\n|\n[a-z])"
match = re.search(pattern, content, re.DOTALL)
if match:
    old_func = match.group(0)
    new_func = """def hamta_underlag_fil(klient, underlag_id: str) -> tuple[dict, bytes]:
    url = f"https://eaccountingapi.vismaonline.com/v2/attachments/{underlag_id}"
    meta, content = klient.hamta_binart(url)
    
    if len(content) > 25 * 1024 * 1024:
        from parser.spiris_klient import SpirisKlientFel
        raise SpirisKlientFel("Underlaget är större än 25 MB och kan inte laddas ner.")
        
    return meta, content"""
    content = content.replace(old_func, new_func)

with open('parser/spiris_adapter.py', 'w', encoding='utf-8') as f:
    f.write(content)

# Now fix spiris_rag.py to use hamta_underlag instead of _adapter_underlag
with open('parser/spiris_rag.py', 'r', encoding='utf-8') as f:
    rag = f.read()

rag = rag.replace("from parser.spiris_adapter import _adapter_underlag", "from parser.spiris_adapter import hamta_underlag")
rag = rag.replace("_adapter_underlag", "hamta_underlag")
rag = rag.replace("from parser.spiris_adapter import _adapter_hamta_underlag_fil", "from parser.spiris_adapter import hamta_underlag_fil")
rag = rag.replace("_adapter_hamta_underlag_fil", "hamta_underlag_fil")

# Also fix the return of hamta_underlag_fil in rag (it returned dict before, wait, no, rag converts it).
# Let's just fix it if needed:
rag = re.sub(
    r"data = await asyncio.to_thread\(hamta_underlag_fil, klient, underlag_id\)\n    from parser.spiris_rag import _envelope\n    return _envelope\(data, antal_exkluderade=0\)",
    "meta, content = await asyncio.to_thread(hamta_underlag_fil, klient, underlag_id)\n    from parser.spiris_rag import _envelope\n    # RAG shouldn't return binary, but if it does we just return meta.\n    return _envelope({'metadata': meta, 'storlek': len(content)}, antal_exkluderade=0)",
    rag
)

with open('parser/spiris_rag.py', 'w', encoding='utf-8') as f:
    f.write(rag)

print("U8.1 refactoring done.")
